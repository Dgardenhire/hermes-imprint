import io
import unittest

from _load import ingest, service, store, reset, SAMPLES


class Reading(unittest.TestCase):
    def setUp(self):
        reset()

    def test_markdown_keeps_heading_locators(self):
        s = service.read_file("warming-center-report.md", (SAMPLES / "warming-center-report.md").read_bytes())
        locs = {p["locator"] for p in store.q("SELECT locator FROM passages WHERE source_id=?", (s["id"],))}
        self.assertIn("“What it cost”", locs)

    def test_transcript_keeps_timestamps_and_speakers(self):
        s = service.read_file("council-work-session.vtt", (SAMPLES / "council-work-session.vtt").read_bytes())
        rows = store.q("SELECT locator, text FROM passages WHERE source_id=?", (s["id"],))
        self.assertTrue(all(r["locator"].startswith("[") for r in rows))
        self.assertIn("Director Lindqvist:", rows[0]["text"])
        self.assertEqual(s["kind"], "Transcript")

    def test_srt(self):
        srt = "1\n00:00:01,000 --> 00:00:04,000\nHello there.\n\n2\n00:01:05,000 --> 00:01:07,000\nSecond line.\n"
        s = service.read_file("talk.srt", srt.encode())
        self.assertEqual([r["locator"] for r in store.q("SELECT locator FROM passages WHERE source_id=?", (s["id"],))], ["[0:01]", "[1:05]"])

    def test_pdf_pages(self):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        for i in range(3):
            c.drawString(72, 700, f"Page {i + 1} says the budget was ${(i + 1) * 100},000 this year.")
            c.showPage()
        c.save()
        s = service.read_file("budget.pdf", buf.getvalue())
        locs = [r["locator"] for r in store.q("SELECT locator FROM passages WHERE source_id=? ORDER BY seq", (s["id"],))]
        self.assertEqual(locs, ["p. 1", "p. 2", "p. 3"])

    def test_docx_headings(self):
        import docx
        d = docx.Document()
        d.add_heading("Budget", 1)
        d.add_paragraph("The program cost $40,000.")
        buf = io.BytesIO()
        d.save(buf)
        s = service.read_file("plan.docx", buf.getvalue())
        self.assertEqual(store.one("SELECT locator FROM passages WHERE source_id=?", (s["id"],))["locator"], "“Budget”")

    def test_duplicates_by_sha(self):
        data = (SAMPLES / "guest-and-volunteer-survey.txt").read_bytes()
        a = service.read_file("a.txt", data)
        b = service.read_file("b.txt", data)
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["duplicate"])

    def test_refusals_say_why(self):
        cases = [("talk.mp3", b"x" * 10, "transcript"), ("old.doc", b"x", ".docx"), ("pic.png", b"x", "can't read"),
                 ("empty.txt", b"", "empty"), ("big.pdf", b"x" * (ingest.MAX_BYTES + 1), "25 MB")]
        for name, data, words in cases:
            with self.subTest(name=name):
                with self.assertRaises(ingest.Refused) as cm:
                    service.read_file(name, data)
                self.assertIn(words, str(cm.exception))

    def test_scanned_and_locked_pdfs_refused(self):
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.rect(10, 10, 100, 100)
        c.showPage()
        c.save()
        with self.assertRaises(ingest.Refused) as cm:
            service.read_file("scan.pdf", buf.getvalue())
        self.assertIn("no text layer", str(cm.exception))
        from pypdf import PdfReader, PdfWriter
        w = PdfWriter()
        w.append(PdfReader(io.BytesIO(buf.getvalue())))
        w.encrypt("secret")
        out = io.BytesIO()
        w.write(out)
        with self.assertRaises(ingest.Refused) as cm:
            service.read_file("locked.pdf", out.getvalue())
        self.assertIn("password", str(cm.exception))

    def test_damaged_files(self):
        for name in ("bad.pdf", "bad.docx"):
            with self.assertRaises(ingest.Refused):
                service.read_file(name, b"not really a document at all")

    def test_huge_text_is_capped_and_says_so(self):
        s = service.read_file("long.txt", ((("word " * 20) + ".\n\n") * 4500).encode())
        self.assertTrue(s["truncated"])
        self.assertLessEqual(s["chars"], ingest.MAX_CHARS)
        self.assertIn("400,000", s["note"])

    def test_paste_limits(self):
        with self.assertRaises(ingest.Refused):
            service.add_text("", "   ")
        with self.assertRaises(ingest.Refused):
            service.add_text("", "x" * (ingest.MAX_PASTE + 1))

    def test_delete_source_removes_rows_and_file(self):
        s = service.read_file("survey.txt", (SAMPLES / "guest-and-volunteer-survey.txt").read_bytes())
        sha = store.one("SELECT sha256 FROM sources WHERE id=?", (s["id"],))["sha256"]
        service.delete_source(s["id"])
        self.assertIsNone(store.one("SELECT * FROM sources WHERE id=?", (s["id"],)))
        self.assertEqual(store.q("SELECT * FROM passages WHERE source_id=?", (s["id"],)), [])
        self.assertFalse((store.root() / "sources" / f"{sha}.txt").exists())


class Web(unittest.TestCase):
    def test_html_text_skips_chrome(self):
        page = "<html><title>Notes</title><nav>Menu Home About</nav><script>evil()</script><h2>Plan</h2><p>The plan opens 14 new beds in the spring season.</p><footer>copyright line here ok</footer></html>"
        blocks, title = ingest.html_to_blocks(page)
        self.assertEqual(title, "Notes")
        self.assertEqual(blocks, [("“Plan”", "The plan opens 14 new beds in the spring season.")])

    def test_bot_walls_are_detected(self):
        self.assertTrue(ingest.looks_blocked(403, "<title>Just a moment...</title><div id=cf-chl>"))
        self.assertTrue(ingest.looks_blocked(503, "challenge-platform"))
        self.assertFalse(ingest.looks_blocked(200, "<p>" + "real text " * 3000 + "</p>"))
        with self.assertRaises(ingest.Blocked):
            ingest.read_page({"status": 403, "body": "Attention Required! | Cloudflare", "type": "text/html"})

    def test_urls(self):
        self.assertEqual(ingest.normalize_url("example.org/x"), "https://example.org/x")
        for bad in ("", "file:///etc/passwd", "javascript:alert(1)", "ftp://x.org"):
            with self.subTest(bad=bad):
                with self.assertRaises(ingest.Refused):
                    ingest.normalize_url(bad)

    def test_fetch_needs_hermes_safe_client(self):
        import asyncio
        with self.assertRaises(ingest.Refused):
            asyncio.run(ingest.fetch("https://example.org"))


class Corpus(unittest.TestCase):
    def test_each_source_gets_a_fair_share(self):
        srcs = [{"id": "a", "title": "Short", "kind": "Text"}, {"id": "b", "title": "Long", "kind": "Text"}]
        pas = {"a": [{"id": 1, "locator": "para. 1", "text": "short " * 20}],
               "b": [{"id": i, "locator": f"para. {i}", "text": "long " * 200} for i in range(2, 80)]}
        text, ids = ingest.corpus(srcs, pas, budget=20000)
        self.assertIn(1, ids)
        self.assertLessEqual(len(text), 21000)
        self.assertIn("=== SOURCE 2: Long", text)
        self.assertIn("[P1] (para. 1)", text)


if __name__ == "__main__":
    unittest.main()


class ZipBombs(unittest.TestCase):
    def test_a_docx_that_unpacks_huge_is_refused_before_reading(self):
        import io as _io
        import zipfile
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml", b"\0" * (40 * 1024 * 1024))
        with self.assertRaises(ingest.Refused) as cm:
            ingest.read_docx(buf.getvalue())
        self.assertIn("unpacks", str(cm.exception))

    def test_a_damaged_docx_says_so(self):
        with self.assertRaises(ingest.Refused):
            ingest.read_docx(b"PK\x03\x04 not really")
