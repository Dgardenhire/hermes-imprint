"""Fonts never come from the network: Letterpress ships only the OFL files in fonts/ (each hash pinned in SOURCES.txt), a kit's own uploads
are the only other source, and anything else is an honest, named substitution."""
import hashlib
import re
import unittest

from _load import fonts, kits, starter_kits, ROOT

FONT_HOSTS = re.compile(r"fonts\.googleapis|fonts\.gstatic|use\.typekit|fonts\.adobe|fontshare|cdnfonts|jsdelivr[^\s'\"]*font"
                        r"|https?://[^\s'\"]+\.(?:ttf|otf|woff2?)\b", re.I)


class Bundled(unittest.TestCase):
    def test_every_bundled_face_is_in_the_repo_and_licensed(self):
        ofl = (ROOT / "fonts" / "OFL.txt").read_text()
        self.assertIn("SIL Open Font License", ofl)
        for fam, _w, _s, fn, _c in fonts.BUNDLED:
            with self.subTest(file=fn):
                self.assertTrue((ROOT / "fonts" / fn).is_file())
                self.assertIn(fam.split()[0], ofl)

    def test_nothing_in_fonts_that_is_not_listed(self):
        listed = {fn for *_x, fn, _c in fonts.BUNDLED}
        on_disk = {p.name for p in (ROOT / "fonts").iterdir() if p.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2")}
        self.assertEqual(on_disk, listed)

    def test_every_font_file_matches_its_recorded_hash(self):
        """fonts/SOURCES.txt pins each file's SHA-256: a swapped or added file fails here."""
        recorded = dict(reversed(m.groups()) for m in re.finditer(r"^([0-9a-f]{64})  (\S+\.ttf)$",
                                                                   (ROOT / "fonts" / "SOURCES.txt").read_text(), re.M))
        on_disk = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "fonts").glob("*.ttf")}
        self.assertEqual(on_disk, recorded)

    def test_every_bundled_file_is_a_truetype_font(self):
        for *_x, fn, _c in fonts.BUNDLED:
            with self.subTest(file=fn):
                self.assertEqual((ROOT / "fonts" / fn).read_bytes()[:4], b"\x00\x01\x00\x00")

    def test_no_code_fetches_a_font(self):
        files = [p for p in ROOT.glob("*.py")] + [ROOT / "dashboard" / "plugin_api.py", ROOT / "desktop" / "src" / "plugin.js"]
        for p in files:
            with self.subTest(file=p.name):
                self.assertIsNone(FONT_HOSTS.search(p.read_text()), p.name)


class Starters(unittest.TestCase):
    def test_starters_use_only_bundled_or_built_in_faces(self):
        for s in starter_kits.STARTERS:
            faces = kits.faces(kits.get(s["id"]))
            for role in ("heading", "body"):
                with self.subTest(kit=s["id"], role=role):
                    f = faces[role]
                    self.assertIn(f["source"], ("bundled", "builtin"))
                    if f["source"] == "bundled":
                        self.assertTrue(f["file"].startswith(str(ROOT / "fonts")))

    def test_no_starter_substitutes(self):
        subs = {s["id"]: fonts.substitutions(kits.faces(kits.get(s["id"]))) for s in starter_kits.STARTERS}
        self.assertEqual([k for k, v in subs.items() if v], [])

    def test_us_web_design_system_is_set_in_its_own_fonts(self):
        faces = kits.faces(kits.get("uswds"))
        want = {"heading": ("Merriweather", 700, "normal"), "body": ("Public Sans", 400, "normal"),
                "body_bold": ("Public Sans", 700, "normal"), "body_italic": ("Public Sans", 400, "italic")}
        for role, (fam, w, st) in want.items():
            with self.subTest(role=role):
                f = faces[role]
                self.assertEqual((f["used"], f["weight"], f["style"], f["source"]), (fam, w, st, "bundled"))
                self.assertFalse(f["substituted"] or f["note"])
        self.assertNotIn(" in place of ", fonts.colophon(faces, 3))

    def test_a_licensed_face_is_never_asked_for(self):
        for s in starter_kits.STARTERS:
            if s.get("credit") != "open-design":
                continue
            for role in ("heading", "body"):
                self.assertTrue(any(fam == s["type"][role]["family"] for fam, *_r in fonts.BUNDLED), (s["id"], role))


if __name__ == "__main__":
    unittest.main()
