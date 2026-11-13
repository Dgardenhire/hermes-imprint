import io
import re
import unittest

from _load import kits, colors, fonts, checks, starter_kits, store, reset, ROOT


def ttf_bytes(name="inter-400.ttf"):
    return (ROOT / "fonts" / name).read_bytes()


class Colors(unittest.TestCase):
    def test_known_ratios(self):
        self.assertAlmostEqual(colors.contrast("#00bde3", "#ffffff"), 2.24, places=1)
        self.assertAlmostEqual(colors.contrast("#ffbe2e", "#ffffff"), 1.66, places=1)
        self.assertAlmostEqual(colors.contrast("#000000", "#ffffff"), 21.0, places=1)

    def test_roles_by_measured_contrast(self):
        k = kits.get("uswds")
        sw = {s["hex"]: s["label"] for s in kits.palette(k)["swatches"]}
        self.assertEqual(sw["#00bde3"], "Rules only")
        self.assertEqual(sw["#ffbe2e"], "Fills only")
        self.assertEqual(sw["#005ea2"], "Text")

    def test_a_weak_head_color_never_sets_text(self):
        k = kits.normalize({"name": "Pale", "paper": "#ffffff", "ink": "#111111", "colors": [{"hex": "#9fd3ff", "role": "head"}]})
        pal = kits.palette(k)
        self.assertEqual(pal["head"], "#111111")
        self.assertTrue(all(p["passes"] for p in pal["pairs"]))
        self.assertEqual(pal["downgraded"][0]["hex"], "#9fd3ff")

    def test_band_text_picks_what_reads(self):
        k = kits.normalize({"name": "B", "paper": "#ffffff", "ink": "#111111", "colors": [{"hex": "#ffd23f", "role": "band"}]})
        pal = kits.palette(k)
        self.assertGreaterEqual(colors.contrast(pal["band_text"], pal["band"]), 4.5)


class Starters(unittest.TestCase):
    def test_studio_kits_each_bring_their_own_system(self):
        """The studio kits lead the library: five or more, each with its own deck system, page layout, ground and type
        (a pairing plus a label face), and none a recolor of a classic starter."""
        studio = [k for k in starter_kits.STARTERS if k.get("studio")]
        self.assertGreaterEqual(len(studio), 5)
        for field in ("deck", "layout"):
            self.assertEqual(len({k[field] for k in studio}), len(studio), field)
        types = {(k["type"]["heading"]["family"], k["type"]["body"]["family"], k["type"]["label"]["family"]) for k in studio}
        self.assertEqual(len(types), len(studio))
        classic = [k for k in starter_kits.STARTERS if not k.get("studio")]
        for k in studio:
            with self.subTest(kit=k["id"]):
                look = (k["layout"], k["paper"], k["type"]["heading"]["family"], k["type"]["body"]["family"])
                self.assertNotIn(look, [(o["layout"], o["paper"], o["type"]["heading"]["family"], o["type"]["body"]["family"]) for o in classic])
                self.assertTrue(k.get("method") and k.get("signature"))
                self.assertIsNone(kits.get(k["id"]).get("logo"))

    def test_at_least_eight_originals_that_really_differ(self):
        originals = [k for k in starter_kits.STARTERS if k["id"] != "uswds" and not k.get("credit") and not k.get("studio")]
        self.assertGreaterEqual(len(originals), 8)
        pairs = {(k["type"]["heading"]["family"], k["type"]["body"]["family"]) for k in originals}
        self.assertEqual(len(pairs), len(originals), "two originals share a type pairing")
        looks = {(k["layout"], k["paper"]) for k in originals}
        self.assertEqual(len(looks), len(originals))
        self.assertGreaterEqual(len({k["layout"] for k in originals}), 5)

    def test_adapted_looks_add_range_and_never_name_a_company(self):
        adapted = [k for k in starter_kits.STARTERS if k.get("credit") == "open-design"]
        self.assertGreaterEqual(len(adapted), 3)
        others = [k for k in starter_kits.STARTERS if k not in adapted]
        for a in adapted:
            with self.subTest(kit=a["id"]):
                look = (a["layout"], a["paper"], tuple(sorted(c["hex"] for c in a["colors"])))
                self.assertNotIn(look, [(o["layout"], o["paper"], tuple(sorted(c["hex"] for c in o["colors"]))) for o in others])
                self.assertIn("Open Design", a["origin_note"])
                self.assertIsNone(kits.get(a["id"]).get("logo"))
        text = (str(adapted) + (ROOT / "NOTICE").read_text()).lower()
        for name in ("stripe", "linear", "airbnb", "spotify", "shopify", "vercel", "figma", "github.com/stripe", "nvidia",
                     "openai", "apple", "tesla", "canva", "notion", "sohne", "söhne", "cereal"):
            self.assertIsNone(re.search(r"\b" + re.escape(name) + r"\b", text), name)

    def test_licensed_typefaces_are_named_as_stood_in_for(self):
        k = kits.get("payments-violet")
        faces = kits.faces(k)
        self.assertTrue(faces["heading"]["stands_in"])
        self.assertFalse(faces["heading"]["substituted"])
        self.assertIn("Inter (an open font standing in for a licensed one)", fonts.colophon(faces, 2))
        pill = checks.pill_fonts(fonts.substitutions(faces), fonts.stands_in(faces))
        self.assertEqual(pill["tone"], "good")
        self.assertIn("stands in for a licensed typeface", pill["label"])
        plain = kits.faces(kits.get("plain-notice"))
        self.assertNotIn("standing in", fonts.colophon(plain, 1))

    def test_featured_starters_are_few(self):
        featured = [k for k in kits.list_all() if k["starter"] and k["featured"]]
        self.assertTrue(4 <= len(featured) <= 5, len(featured))

    def test_every_starter_passes_contrast_and_has_a_voice(self):
        for s in starter_kits.STARTERS:
            with self.subTest(kit=s["id"]):
                k = kits.get(s["id"])
                pal = kits.palette(k)
                self.assertTrue(all(p["passes"] for p in pal["pairs"]))
                self.assertTrue(k["voice"]["notes"] and k["voice"]["delivery"])
                self.assertIsNone(k.get("logo"), "starter kits never carry a logo")

    def test_no_real_organization_or_contest_in_starters(self):
        text = str(starter_kits.STARTERS).lower()
        for word in ("hackathon", "hermes", "mozilla", "linchpin", "nous", "contest"):
            self.assertNotIn(word, text)

    def test_uswds_colophon_names_its_real_fonts(self):
        f = kits.faces(kits.get("uswds"))
        self.assertEqual(fonts.colophon(f, 3), "Set in Merriweather and Public Sans. Drawn from 3 sources.")


class Library(unittest.TestCase):
    def setUp(self):
        reset()

    def raw(self, name="Mine"):
        return {"name": name, "paper": "#ffffff", "ink": "#1b1b1b", "colors": [{"hex": "#0d5566", "role": "head"}],
                "layout": "margin", "voice": {"never": "leverage, synergy", "pairs": [{"say": "use", "not": "utilize"}]}}

    def test_unlimited_custom_kits(self):
        for i in range(15):
            kits.save_new(self.raw(f"Kit {i}"))
        mine = [k for k in kits.list_all() if not k["starter"]]
        self.assertEqual(len(mine), 15)
        self.assertGreaterEqual(len(kits.list_all()), 25)

    def test_edits_bump_the_version(self):
        k = kits.save_new(self.raw())
        k2 = kits.update(k["id"], {"name": "Renamed"})
        self.assertEqual(k2["version"], 2)
        self.assertEqual(k2["voice"]["never"], ["leverage", "synergy"])

    def test_editing_a_starter_makes_a_copy(self):
        k = kits.update("docket", {"org": "Eastside Legal Clinic"})
        self.assertFalse(k["starter"])
        self.assertEqual(k["name"], "Docket (yours)")
        self.assertEqual(kits.get("docket")["org"], "")

    def test_bad_kits_get_plain_reasons(self):
        for raw, words in [({"name": ""}, "name"), ({"name": "x", "paper": "#ffffff", "ink": "#eeeeee", "colors": [{"hex": "#000", "role": "head"}]}, "4.5:1"),
                           ({"name": "x", "paper": "nope"}, "hex"), ({"name": "x", "colors": []}, "brand color")]:
            with self.subTest(raw=raw):
                with self.assertRaises(kits.KitError) as cm:
                    kits.normalize(raw)
                self.assertIn(words, str(cm.exception))

    def test_starters_cannot_be_deleted_or_branded(self):
        with self.assertRaises(kits.KitError):
            kits.delete("plain-notice")
        with self.assertRaises(kits.KitError):
            kits.set_logo("plain-notice", "logo.png", b"\x89PNG....")

    def test_logo_rules(self):
        k = kits.save_new(self.raw())
        with self.assertRaises(kits.KitError):
            kits.set_logo(k["id"], "logo.gif", b"GIF89a")
        with self.assertRaises(kits.KitError):
            kits.set_logo(k["id"], "logo.png", b"not a png")
        with self.assertRaises(kits.KitError):
            kits.set_logo(k["id"], "logo.svg", b"hello")
        k = kits.set_logo(k["id"], "logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="4" height="4"/></svg>')
        self.assertTrue(kits.logo_data_url(k).startswith("data:image/svg+xml;base64,"))
        k = kits.remove_logo(k["id"])
        self.assertIsNone(k["logo"])

    def test_fonts_upload_and_resolve(self):
        k = kits.save_new({**self.raw(), "type": {"heading": {"family": "Crimson Pro", "stack": "Crimson Pro, serif"}}})
        k = kits.add_font(k["id"], "MyFace.ttf", ttf_bytes("crimson-pro-400.ttf"))
        self.assertEqual(k["fonts"][0]["family"], "Crimson Pro")
        f = kits.faces(k)["heading"]
        self.assertEqual(f["source"], "upload")
        self.assertFalse(f["substituted"])

    def test_postscript_fonts_are_refused_with_the_reason(self):
        k = kits.save_new(self.raw())
        with self.assertRaises(kits.KitError) as cm:
            kits.add_font(k["id"], "x.otf", b"OTTO" + b"\x00" * 200)
        self.assertIn(".ttf", str(cm.exception))

    def test_duplicate_and_delete(self):
        k = kits.save_new(self.raw())
        d = kits.duplicate(k["id"])
        self.assertNotEqual(d["id"], k["id"])
        kits.delete(k["id"])
        with self.assertRaises(kits.KitError):
            kits.get(k["id"])
        with self.assertRaises(kits.KitError):
            kits.get("../../etc")

    def test_recent_looks_are_recorded(self):
        for _ in range(3):
            kits.record_look(kits.get("night-desk"), "onepager")
        r = kits.repeats()
        self.assertEqual(r["layout"]["headline"], 3)
        self.assertEqual(r["type_pair"]["Anton / Inter"], 3)


class FontResolution(unittest.TestCase):
    def test_bundled_exact(self):
        f = fonts.resolve({"family": "Libre Caslon Display", "stack": "Libre Caslon Display, Georgia, serif"}, {})
        self.assertEqual((f["used"], f["source"], f["substituted"]), ("Libre Caslon Display", "bundled", False))

    def test_stack_fallback_to_builtin(self):
        # a missing family whose stack falls to a system face embeds the nearest bundled face (what the PNG draws)
        f = fonts.resolve({"family": "Proxima Nova", "stack": "Proxima Nova, Helvetica Neue, sans-serif"}, {})
        self.assertEqual((f["used"], f["substituted"], f["pdf"], f["source"]), ("Inter", True, None, "bundled"))
        # a kit that asks for the built-in face itself keeps it
        f = fonts.resolve({"family": "Helvetica", "stack": "Helvetica, Arial, sans-serif"}, {})
        self.assertEqual((f["used"], f["substituted"], f["pdf"]), ("Helvetica", False, "Helvetica"))
        f = fonts.resolve({"family": "Times New Roman", "stack": "Times New Roman, serif"}, {})
        self.assertFalse(f["substituted"])

    def test_missing_italic_is_said(self):
        f = fonts.resolve({"family": "Anton"}, {}, style="italic")
        self.assertIn("no italic", f["note"])


if __name__ == "__main__":
    unittest.main()


class KitFilesStayInside(unittest.TestCase):
    """A kit's logo and fonts can only name files Letterpress wrote into that kit's own folder."""

    def setUp(self):
        reset()
        self.secret = store.root().parent / "secret.env"
        self.secret.write_text("API_KEY=do-not-leak")

    def raw(self, **extra):
        return {"name": "Harbor", "paper": "#ffffff", "ink": "#111111", "colors": [{"hex": "#0b4f45", "role": "head"}], **extra}

    def test_a_logo_path_from_the_page_is_dropped(self):
        for bad in ({"file": "../../secret.env", "kind": "png"}, {"file": "/etc/hosts", "kind": "svg"},
                    {"file": "logo.png", "kind": "exe"}, {"file": "logo.svg", "kind": "png"}, "logo.png"):
            with self.subTest(logo=bad):
                k = kits.save_new(self.raw(logo=bad))
                self.assertIsNone(k["logo"])
                self.assertIsNone(kits.logo_data_url(k))
                self.assertIsNone(kits.logo_path(k))

    def test_a_logo_written_by_hand_into_kit_json_is_not_read(self):
        k = kits.save_new(self.raw())
        d = kits.kit_dir(k["id"])
        on_disk = store.read_json(d / "kit.json")
        on_disk["logo"] = {"file": "../../secret.env", "kind": "png"}
        store.write_json(d / "kit.json", on_disk)
        self.assertIsNone(kits.logo_data_url(kits.get(k["id"])))

    def test_font_paths_from_the_page_are_dropped(self):
        k = kits.save_new(self.raw(fonts=[{"family": "X", "weight": 400, "style": "normal", "file": "../../../secret.env"}]))
        self.assertEqual(k["fonts"], [])
        self.assertEqual(kits.normalize(self.raw(fonts=[{"family": "X", "file": "../x.ttf"}, {"family": "Y", "file": "y-400-normal.ttf"}]))["fonts"],
                         [{"family": "Y", "weight": 400, "style": "normal", "file": "y-400-normal.ttf"}])

    def test_duplicate_never_copies_a_named_path(self):
        k = kits.save_new(self.raw())
        d = kits.kit_dir(k["id"])
        on_disk = store.read_json(d / "kit.json")
        on_disk["logo"] = {"file": "../../secret.env", "kind": "png"}
        store.write_json(d / "kit.json", on_disk)
        dup = kits.duplicate(k["id"])
        self.assertIsNone(dup["logo"])
        self.assertFalse(any(p.name == "secret.env" for p in kits.kits_dir().rglob("*")))

    def test_a_real_logo_and_font_still_work(self):
        k = kits.save_new(self.raw())
        import struct
        import zlib
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(b"\0\0\0\0")) + chunk(b"IEND", b""))  # a real 1 x 1 PNG
        k = kits.set_logo(k["id"], "mark.png", png)
        self.assertEqual(k["logo"], {"file": "logo.png", "kind": "png"})
        self.assertTrue(kits.logo_data_url(k).startswith("data:image/png;base64,"))
        k = kits.add_font(k["id"], "inter.ttf", ttf_bytes())
        self.assertTrue(k["fonts"] and kits.FONT_FILE.fullmatch(k["fonts"][0]["file"]))
        dup = kits.duplicate(k["id"])
        self.assertEqual(dup["logo"], {"file": "logo.png", "kind": "png"})
        self.assertEqual(len(dup["fonts"]), 1)
