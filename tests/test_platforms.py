"""Every MUST import route reads the same on Mac, Windows and Linux.

What differs between the three is not the readers but what reaches them: Windows paths with backslashes and
drive letters, zips written with backslash names, files saved with a byte order mark and CRLF line endings,
and folders whose names differ in case (Linux is case-sensitive). Each route below gets the Windows and Linux
shapes of the same input and must come out the same. iWork is Mac only and says so.
"""
import base64
import io
import json
import unittest
import zipfile

from _load import api, imports, ingest, kits, reset, run, service, sitekit, ROOT

INTER = (ROOT / "fonts" / "inter-400.ttf").read_bytes()
PNG_1PX = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
CSS = ":root {\n  --bg: #fbf7f0;\n  --fg: #1f1a16;\n  --accent: #9a5a2f;\n  --font-display: Georgia, serif;\n}\n"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4"/></svg>'


def windows_text(s: str) -> str:
    """How Notepad saves it: a byte order mark and CRLF line endings."""
    return "\ufeff" + s.replace("\n", "\r\n")


class Req:
    """A JSON request the way the pane sends a base64 upload."""
    def __init__(self, body):
        self._b = json.dumps(body).encode("utf-8")
        self.headers = {"content-type": "application/json"}

    async def body(self):
        return self._b

    async def stream(self):
        yield self._b


def upload(filename, data):
    return Req({"filename": filename, "data": base64.b64encode(data).decode("ascii")})


class Names(unittest.TestCase):
    def test_base_name_from_every_system(self):
        for raw in ("deck.pptx", "/home/ana/brand/deck.pptx", "C:\\Users\\Ana\\Brand\\deck.pptx", "C:deck.pptx",
                    "\\\\server\\share\\deck.pptx", "C:\\fakepath\\deck.pptx", "Brand/deck.pptx"):
            with self.subTest(raw=raw):
                self.assertEqual(ingest.base_name(raw), "deck.pptx")
                self.assertEqual(imports.base_name(raw), "deck.pptx")
        self.assertEqual(ingest.base_name(".."), "")

    def test_relative_paths_inside_packages(self):
        self.assertEqual(imports.clean_rel("project\\fonts\\Inter.ttf"), "project/fonts/Inter.ttf")
        self.assertEqual(imports.clean_rel("./project//tokens.json"), "project/tokens.json")
        for bad in ("../evil", "..\\evil", "/etc/passwd", "\\evil", "C:\\evil", "c:/evil", "a/../../b"):
            with self.subTest(bad=bad):
                self.assertIsNone(imports.clean_rel(bad))

    def test_source_files_keep_their_name_and_type_from_a_windows_path(self):
        self.assertEqual(ingest.ext_of("C:\\Users\\Ana\\Board Memo.DOCX"), ".docx")
        self.assertEqual(ingest.label_title("C:\\Users\\Ana\\board_memo-october.pdf"), "Board memo october")


class Routes(unittest.TestCase):
    """One test per MUST route in SPEC.md (I-2 to I-8), each fed the Windows and Linux shape."""

    def setUp(self):
        reset()

    def test_i2_manual_build_with_logo_and_font_from_windows_paths(self):
        kit = kits.save_new({"name": "Harbor Mill", "paper": "#ffffff", "ink": "#111111", "colors": [{"hex": "#0b4f45", "role": "head"}]})
        v = run(api.post_kit_logo(kit["id"], upload("C:\\Users\\Ana\\Pictures\\Logo Final.PNG", PNG_1PX)))
        self.assertTrue(v["logo"])
        self.assertEqual(kits.get(kit["id"])["logo"]["file"], "logo.png")
        v = run(api.post_kit_font(kit["id"], upload("/home/ana/.fonts/Inter-Regular.ttf", INTER)))
        self.assertEqual(v["kit"]["fonts"][-1]["family"], "Inter")

    def test_i2_paste_with_windows_line_endings(self):
        a = imports.read("paste", text="#1A4480  #F4EFE6\n#B8441F\nrgb(27, 27, 27)")
        b = imports.read("paste", text=windows_text("#1A4480  #F4EFE6\n#B8441F\nrgb(27, 27, 27)"))
        self.assertEqual([c["hex"] for c in a["colors"]], [c["hex"] for c in b["colors"]])

    def test_i3_css_file_from_windows_and_linux(self):
        drafts = []
        for name, text in (("C:\\Users\\Ana\\Brand\\tokens.css", windows_text(CSS)), ("/home/ana/brand/tokens.css", CSS)):
            with self.subTest(name=name):
                d = run(api.post_kit_import_file(upload(name, text.encode("utf-8"))))["draft"]
                drafts.append(d)
                self.assertEqual(d["kit"]["paper"], "#fbf7f0")
                self.assertIn("#9a5a2f", [c["hex"] for c in d["kit"]["colors"]])
        self.assertEqual(drafts[0]["kit"]["colors"], drafts[1]["kit"]["colors"])

    def test_i4_website_reader_with_crlf_markup(self):
        page = ("<html><head><title>Harbor Mill</title><style>\n:root{--brand:#0b4f45}\nbody{color:#1b1b1b;background:#ffffff}\n"
                "h1{color:#0b4f45;font-family:Fraunces, serif}\n</style></head><body><h1>Hi</h1></body></html>")
        unix = sitekit.draft_from(page, [], "https://harbormill.example/", "November 8, 2026")
        win = sitekit.draft_from(page.replace("\n", "\r\n"), [], "https://harbormill.example/", "November 8, 2026")
        self.assertEqual(unix["colors"], win["colors"])
        self.assertEqual(unix["paper"], win["paper"])
        d = service.import_view(imports.from_site_draft(win, "https://harbormill.example/"))
        self.assertEqual(d["kind"], "site")

    def test_i5_open_design_folder_whatever_the_case_and_separators(self):
        manifest = json.dumps({"schemaVersion": "od-design-system-project/v1", "id": "harbor-press", "name": "Harbor Press", "category": "Editorial"})
        tokens = ":root{--bg:#fbf7f0;--fg:#1f1a16;--accent:#9a5a2f;--font-display:Georgia, serif}"
        mac = {"manifest.json": manifest, "tokens.css": tokens, "DESIGN.md": "# Harbor"}
        linux = {"Manifest.json": manifest, "TOKENS.css": tokens, "design.md": "# Harbor"}
        win = {"harbor-press\\manifest.json": windows_text(manifest), "harbor-press\\tokens.css": windows_text(tokens)}
        out = [imports.read("open-design", files=f) for f in (mac, linux, win)]
        for f in out:
            self.assertEqual(f["label"], "Harbor Press")
            self.assertEqual({c["hex"] for c in f["colors"]}, {c["hex"] for c in out[0]["colors"]})
        self.assertNotIn("components.html", str(out))

    def test_i6_claude_design_folder_from_windows_and_linux(self):
        tokens = json.dumps({"color": {"themes": ["Day"], "tokens": [
            {"name": "surface", "value": {"Day": "#fafaf7"}, "usage": "background of pages"},
            {"name": "text", "value": {"Day": "#1d1d1b"}, "usage": "body text"},
            {"name": "brand", "value": {"Day": "#c2410c"}, "usage": "primary brand color"}]}})
        font = "data:font/ttf;base64," + base64.b64encode(INTER).decode()
        logo = "data:image/svg+xml;base64," + base64.b64encode(SVG).decode()
        mac = {"project/design-system.json": '{"name": "Quarry"}', "project/tokens.json": tokens,
               "project/fonts/Inter.ttf": font, "project/assets/Logos/mark.svg": logo}
        win = {"project\\design-system.json": windows_text('{"name": "Quarry"}'), "project\\Tokens.json": windows_text(tokens),
               "project\\fonts\\Inter.ttf": font, "project\\assets\\Logos\\mark.svg": logo}
        linux = {"Project/design-system.json": '{"name": "Quarry"}', "Project/tokens.json": tokens,
                 "Project/Fonts/Inter.ttf": font, "Project/Assets/Logos/mark.svg": logo}
        out = [imports.read("claude-design", files=f) for f in (mac, win, linux)]
        for f in out:
            self.assertEqual(f["label"], "Quarry")
            self.assertEqual([c["hex"] for c in f["colors"]], [c["hex"] for c in out[0]["colors"]])
            self.assertEqual([x["family"] for x in f["fonts"]], ["Inter"])
            self.assertEqual([lg["name"] for lg in f["logos"]], ["mark.svg"])

    def _cd_zip(self, sep="/", root="Quarry"):
        tokens = json.dumps({"color": {"themes": ["Day"], "tokens": [
            {"name": "surface", "value": {"Day": "#fafaf7"}, "usage": "background of pages"},
            {"name": "text", "value": {"Day": "#1d1d1b"}, "usage": "body text"},
            {"name": "brand", "value": {"Day": "#c2410c"}, "usage": "primary brand color"}]}})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, data in ((["design-system.json"], b'{"name": "Quarry"}'), (["tokens.json"], tokens.encode()),
                              (["fonts", "Inter.ttf"], INTER), (["assets", "Logos", "mark.svg"], SVG)):
                info = zipfile.ZipInfo(sep.join([root, "project", *rel]))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, data)
        return buf.getvalue()

    def test_i6_claude_design_zip_written_on_windows_reads_like_one_from_a_mac(self):
        mac = imports.read_claude_design_zip(self._cd_zip("/"))
        win = imports.read_claude_design_zip(self._cd_zip("\\"))
        self.assertEqual(mac["label"], win["label"])
        self.assertEqual(mac["colors"], win["colors"])
        self.assertEqual([f["family"] for f in win["fonts"]], ["Inter"])
        self.assertEqual([lg["name"] for lg in win["logos"]], ["mark.svg"])
        d = run(api.post_kit_import_file(upload("C:\\Users\\Ana\\Downloads\\Quarry.zip", self._cd_zip("\\"))))["draft"]
        self.assertEqual(d["kit"]["paper"], "#fafaf7")

    def test_i6_zip_paths_that_climb_or_are_absolute_are_refused_on_every_system(self):
        for bad in ("..\\evil.txt", "C:\\evil.txt", "\\evil.txt", "Quarry\\..\\..\\evil.txt"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                z.writestr("Quarry/tokens.json", "{}")
                z.writestr(zipfile.ZipInfo(bad), "x")
            with self.subTest(bad=bad), self.assertRaises(imports.Refused):
                imports.read_claude_design_zip(buf.getvalue())

    def test_i7_pptx_from_a_windows_download_folder(self):
        from _load import render_deck
        kit = kits.get("docket")
        doc = {"title": "A deck", "subtitle": "", "slides": [{"type": "content", "heading": "H", "bullets": [{"text": "x", "ref": ""}], "refs": []}]}
        data = render_deck.render_pptx(doc, kit, kits.palette(kit), {}, [], {})
        d = run(api.post_kit_import_file(upload("C:\\Users\\Ana\\Downloads\\Canva design.pptx", data)))["draft"]
        self.assertEqual(d["kit"]["paper"], kit["paper"])
        self.assertEqual(d["kit"]["imported_from"]["label"], "Canva design")

    def test_i8_dtcg_file_from_windows_with_a_byte_order_mark(self):
        tokens = json.dumps({"color": {"$type": "color", "brand": {"$value": "#0b5cad"}, "background": {"$value": "#ffffff"},
                                       "text": {"$value": "#111111"}}}, indent=2)
        a = run(api.post_kit_import_file(upload("D:\\Brand\\brand.tokens.json", windows_text(tokens).encode("utf-8"))))["draft"]
        b = run(api.post_kit_import_file(upload("/home/ana/brand.tokens.json", tokens.encode("utf-8"))))["draft"]
        self.assertEqual(a["kit"]["colors"], b["kit"]["colors"])
        self.assertEqual(a["kit"]["imported_from"]["label"], "brand")

    def test_iwork_is_mac_only_and_says_how(self):
        for name in ("Pitch.key", "C:\\Users\\Ana\\Pitch.key", "Report.pages"):
            with self.subTest(name=name), self.assertRaises(imports.Refused) as cm:
                imports.kind_from_name(name)
            self.assertIn("Mac", str(cm.exception))
            self.assertIn("PowerPoint", str(cm.exception))


class PaneRoutes(unittest.TestCase):
    """The pane lists each MUST route, and labels the one Mac-only route as Mac only."""

    def test_every_route_is_offered_and_iwork_is_labeled(self):
        src = (ROOT / "desktop" / "src" / "plugin.js").read_text()
        block = src[src.index("const ROUTES = ["):src.index("]", src.index("const ROUTES = ["))]
        for rid in ("'paste'", "'css'", "'open-design'", "'claude-design'", "'pptx'", "'dtcg'", "'keynote'"):
            self.assertIn(rid, block)
        keynote = [ln for ln in block.splitlines() if "'keynote'" in ln][0]
        self.assertIn("Mac only", keynote)

    def test_folder_reads_match_names_without_case(self):
        src = (ROOT / "desktop" / "src" / "plugin.js").read_text()
        fn = src[src.index("async function readFolder"):src.index("function ImportPanel")]
        self.assertIn("toLowerCase()", fn)
        self.assertNotIn("files.list(id, base + 'fonts')", fn)


if __name__ == "__main__":
    unittest.main()
