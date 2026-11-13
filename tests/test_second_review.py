"""The second security review's tests (docs/SECURITY-AUDIT.md, "Second review"). Each class names the finding it
closes. The hostile PDFs are built by hand here (a few KB each), the way an attacker would write them."""
import base64
import io
import json
import os
import subprocess
import sys
import threading
import time
import unittest
import zipfile
import zlib
from pathlib import Path

from _load import api, imports, ingest, reset, run, service

REPO = Path(__file__).resolve().parent.parent
CANVA = REPO / "harness" / "live" / "personas" / "ana" / "Salvia Kitchen Brand Kit.pptx"


def _pdf(objs: list) -> bytes:
    out = bytearray(b"%PDF-1.7\n")
    offs = []
    for i, body in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offs)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, x)
    return bytes(out)


def _stream(data: bytes, extra: bytes = b"") -> bytes:
    d = zlib.compress(data, 9)
    return b"<< " + extra + b"/Length %d /Filter /FlateDecode >>\nstream\n" % len(d) + d + b"\nendstream"


def form_bomb(paints: int, form_ops: bytes) -> bytes:
    """One page that paints the same form XObject ``paints`` times. A few KB on disk; pypdf walks the form's
    operators again on every paint, and keeps every piece of text it finds."""
    form = _stream(form_ops, b"/Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> ")
    return _pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [6 0 R] /Count 1 >>",
                 b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", form, _stream(b"q /X0 Do Q\n" * paints),
                 b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> "
                 b"/XObject << /X0 4 0 R >> >> /Contents 5 0 R >>"])


TEXT_FORM = b"BT /F1 12 Tf 72 700 Td (Primary #1A4480 for headlines) Tj ET\n" * 20_000  # 640 KB of text per paint
PATH_FORM = b"0 0 m 1 1 l\n" * 60_000  # no text at all: only the clock can stop it


class Req:
    def __init__(self, body):
        self._b = json.dumps(body).encode("utf-8")
        self.headers = {"content-type": "application/json"}

    async def body(self):
        return self._b

    async def stream(self):
        yield self._b


class F9_PdfReadsAreBoundedInsideForms(unittest.TestCase):
    """F9: a form XObject painted many times made one small page extract for minutes (a brand guide, in the
    request handler) or hours (a source), holding all of its text. Both readers now stop on a text budget and a
    clock checked on every operator, inside forms too, and the guide is read off the event loop."""

    def setUp(self):
        reset()

    def test_guide_pdf_form_painted_many_times_stops_at_the_text_budget(self):
        data = form_bomb(300, TEXT_FORM)  # unbounded: 300 paints x 640 KB = 190 MB of text, minutes of parsing
        self.assertLess(len(data), 20_000)
        t = time.monotonic()
        fd = imports.read_pdf_guide(data, "guide.pdf")
        self.assertLess(time.monotonic() - t, 15)
        self.assertIn("#1a4480", [c["hex"] for c in fd["colors"]])

    def test_source_pdf_form_painted_many_times_keeps_only_its_budget(self):
        t = time.monotonic()
        blocks, pages, _unit = ingest.read_pdf(form_bomb(300, TEXT_FORM))
        self.assertLess(time.monotonic() - t, 20)
        self.assertEqual(pages, 1)
        self.assertLessEqual(sum(len(b[1]) for b in blocks), ingest.MAX_CHARS + 1)

    def test_a_form_with_no_text_stops_at_the_clock(self):
        data = form_bomb(400, PATH_FORM)  # no text to count, so only the deadline stops it
        old = (imports.GUIDE_SECONDS, ingest.PDF_SECONDS)
        imports.GUIDE_SECONDS = ingest.PDF_SECONDS = 1
        try:
            t = time.monotonic()
            with self.assertRaises(imports.Refused):
                imports.read_pdf_guide(data, "guide.pdf")
            self.assertLess(time.monotonic() - t, 10)
            t = time.monotonic()
            with self.assertRaises(ingest.Refused):
                ingest.read_pdf(data)
            self.assertLess(time.monotonic() - t, 10)
        finally:
            imports.GUIDE_SECONDS, ingest.PDF_SECONDS = old

    def test_the_stop_is_not_swallowed_by_pypdfs_per_form_handler(self):
        from pypdf import PdfReader
        page = PdfReader(io.BytesIO(form_bomb(50, TEXT_FORM))).pages[0]
        text, stopped = ingest.pdf_page_text(page, 5_000, time.monotonic() + 60)
        self.assertTrue(stopped)
        self.assertLessEqual(len(text), 5_000)
        self.assertIn("Primary #1A4480", text)

    def test_file_imports_are_read_off_the_event_loop(self):
        seen = []
        real = service.import_read

        def spy(*a, **kw):
            seen.append(threading.current_thread() is threading.main_thread())
            return {"stub": True}
        service.import_read = spy
        try:
            for name in ("guide.pdf", "deck.pptx", "design.zip"):
                r = run(api.post_kit_import_file(Req({"filename": name, "data": base64.b64encode(b"x").decode()})))
                self.assertEqual(r, {"draft": {"stub": True}})
        finally:
            service.import_read = real
        self.assertEqual(seen, [False, False, False])


class F10_GuideFontPatternsAreLinear(unittest.TestCase):
    """F10: guide_fonts ran two backtracking patterns over the whole 200,000-character guide text: 42 s for a run
    of "if a" and 86 s for a run of weights, each one regex call holding the GIL (the whole Hermes backend
    stalls). They now read only short lines, and the fallback pattern only around lines that mention installing."""

    HOSTILE = {
        "if-runs": "if a " * 40_000,
        "install lines": "\n".join(["if a is not installed " * 18] * 500),
        "weights": "Headlines: Montserrat" + " bold" * 40_000 + " x",
        "weight lines": "\n".join(["Headlines: montserrat" + " bold" * 70 + " x"] * 2_000),
    }

    def test_hostile_guide_text_reads_fast(self):
        for label, text in self.HOSTILE.items():
            with self.subTest(label):
                t = time.monotonic()
                imports.guide_fonts(text[:imports.MAX_GUIDE_TEXT])
                self.assertLess(time.monotonic() - t, 2)

    def test_real_guide_lines_still_read(self):
        text = ("Typography\nHeadlines: Montserrat Bold or ExtraBold. Sentence case.\nBody text: Lora Regular, 11 pt.\n"
                "If Montserrat is not\ninstalled, use Arial Bold.\nIf Lora isn't available, use Georgia.")
        self.assertEqual(imports.guide_fonts(text), ("Montserrat, Arial", "Lora, Georgia"))


def _patched_pptx(fix) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(CANVA.read_bytes()))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for it in src.infolist():
            z.writestr(it.filename, fix(it.filename, src.read(it.filename)))
    return out.getvalue()


class F11_PowerPointSizesAreHeldToTheFormat(unittest.TestCase):
    """F11: a 400-digit shape or slide size is a valid int that overflowed the ranking's float division
    (OverflowError, a 500). Sizes are now held to the ranges the format allows."""

    def test_huge_sizes_read_instead_of_crashing(self):
        import re
        big = b"9" * 400
        cases = {
            "shape": lambda n, d: re.sub(rb'<a:ext cx="\d+" cy="\d+"', b'<a:ext cx="' + big + b'" cy="' + big + b'"', d)
            if n.startswith("ppt/slides/slide") else d,
            "slide": lambda n, d: re.sub(rb'<p:sldSz cx="\d+" cy="\d+"', b'<p:sldSz cx="' + big + b'" cy="' + big + b'"', d)
            if n == "ppt/presentation.xml" else d,
        }
        for label, fix in cases.items():
            with self.subTest(label):
                fd = imports.read_pptx(_patched_pptx(fix), "Canva design.pptx")
                self.assertTrue(fd["colors"])

    def test_the_real_file_ranks_as_before(self):
        fd = imports.read_pptx(CANVA.read_bytes(), CANVA.name)
        paper = [c["hex"] for c in fd["colors"] if c["hint"] == "paper"]
        self.assertEqual(len(paper), 1)


class F12_LiveHarnessStaysOutOfHermes(unittest.TestCase):
    """F12: harness/live ships in the plugin folder (Hermes installs the whole repo). Importing server.py replaced
    fastapi in sys.modules and pointed Letterpress at a temp folder; it now refuses to be imported. Its Host and
    Origin checks are in test_live_harness.LiveMode."""

    def test_server_refuses_to_be_imported(self):
        code = ("import importlib.util, os, sys\n"
                "had = 'fastapi' in sys.modules\n"
                f"spec = importlib.util.spec_from_file_location('letterpress.harness.live.server', {str(REPO / 'harness' / 'live' / 'server.py')!r})\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "try:\n    spec.loader.exec_module(m)\nexcept ImportError as e:\n    print('refused', e)\n"
                "print('fastapi untouched' if ('fastapi' in sys.modules) == had else 'fastapi replaced')\n"
                "print('data dir set' if os.environ.get('LETTERPRESS_DATA_DIR') else 'data dir untouched')\n")
        env = {k: v for k, v in os.environ.items() if k != "LETTERPRESS_DATA_DIR"}
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env)
        self.assertIn("refused", r.stdout, r.stdout + r.stderr)
        self.assertIn("fastapi untouched", r.stdout)
        self.assertIn("data dir untouched", r.stdout)

    def test_no_shipped_module_reaches_the_harness(self):
        for p in list(REPO.glob("*.py")) + list((REPO / "dashboard").glob("*.py")):
            text = p.read_text(encoding="utf-8")
            with self.subTest(p.name):
                self.assertNotIn("harness", "\n".join(ln for ln in text.splitlines() if "import" in ln))
                self.assertNotIn("persona_model", text)
        bundle = (REPO / "desktop" / "plugin.js").read_text(encoding="utf-8")
        self.assertNotIn("harness/", bundle)


class F13_HtmlExportTokensCannotLoad(unittest.TestCase):
    """F13 (depth): the export's style tokens dropped ``;{}<>`` but let ``url(...)`` through, and the export's own
    rules paint tokens into url-taking properties (``background:var(--k-band)``). Every token is a checked value
    today; a value that could load is now dropped."""

    def test_a_token_that_would_load_is_dropped(self):
        from _load import render_html
        tree = {"t": "div", "c": "ip-page", "a": {"style": {
            "--k-band": "url(https://tracker.example/p.gif)", "--k-paper": "image-set('https://x.example/a.png' 1x)",
            "--k-ink": "\\75rl(https://x.example)", "--k-accent": "#1a4480", "--k-head-font": '"imp-b-inter-700-normal", "Inter", sans-serif'}},
            "k": [{"t": "p", "x": "Hello"}]}
        out = render_html.export_page(tree, {}, "T")
        self.assertNotIn("tracker.example", out)
        self.assertNotIn("x.example", out)
        self.assertIn("--k-accent:#1a4480", out)
        self.assertIn("Inter", out)
        self.assertNotRegex(out.split("<style>")[0] + out.split("</style>")[1], r"https?://")


if __name__ == "__main__":
    unittest.main()
