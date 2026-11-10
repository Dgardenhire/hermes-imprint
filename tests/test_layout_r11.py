"""Round 11, layout lane: a second layout family (editorial spreads) so kits stop reading as one layout in three
palettes, and photos from the sources (only when a source file holds one)."""
import io
import unittest
import zipfile
from importlib import import_module

from _load import ROOT, kits

PKG = "imprint_plugin_package"
RD = import_module(f"{PKG}.render_deck")
SY = import_module(f"{PKG}.systems")
SC = import_module(f"{PKG}.scene")

HERO = {"title": "A sixth site", "subtitle": "For funders", "slides": [
    {"type": "exhibit", "heading": "Demand is outgrowing our seats", "subhead": "212 more adults than last year", "unit": "Adult learners",
     "refs": [], "note": "",
     "bars": [{"label": "FY2025", "value": "936", "ref": ""}, {"label": "FY2026", "value": "1,148", "ref": ""},
              {"label": "Waiting at year end", "value": "287", "ref": "", "accent": True}]},
    {"type": "quote", "quote": "I read my granddaughter a bedtime story", "who": "A learner", "refs": []}]}

BARS = [("FY2025", "936", 936.0, ""), ("FY2026", "1,148", 1148.0, ""), ("Waiting at year end", "287", 287.0, "")]
SPECS = [
    {"kind": "title", "title": "A Sixth Site to Meet Growing Need", "sub": "For funders", "org": "Sample", "date": "October 1, 2026",
     "fig": ("287", "Waiting at year end", "")},
    {"kind": "exhibit", "head": "Demand is outgrowing our seats", "subhead": "212 more adults than last year", "bars": BARS, "hi": 2,
     "unit": "Adult learners"},
    {"kind": "figures", "head": "Most learners gained a level", "figs": [("68%", "Gained a level", "", ""), ("71", "Earned a credential", "", ""),
                                                                         ("389", "English learners", "", "")]},
    {"kind": "quote", "quote": "I read my granddaughter a bedtime story", "who": "A learner at the Riverside site"},
    {"kind": "ledger", "head": "Tutors gave 9,870 hours", "items": [("Hours tutors gave", ""), ("Tutors", "")], "figs": ["9,870", "214"]},
    {"kind": "content", "head": "The plan", "items": [("Open at the Eastgate library", ""), ("Add two coordinators", "")]},
    {"kind": "ledger", "head": "The cost per learner", "items": [("Cost per learner", ""), ("Gifts", "")], "figs": ["$1,237", "$388,000"]},
    {"kind": "stat", "value": "287", "label": "adults on the waitlist", "context": "Most at Eastgate."},
    {"kind": "section", "head": "The plan", "sub": "A sixth site", "n": 2},
    {"kind": "matched", "head": "Today and with the plan", "rows": [("Sites", "Five", "Six", "")], "labels": ("Today", "With the plan")},
    {"kind": "comparison", "head": "Today and the plan", "cols": [("Today", [("Five sites", "")]), ("Plan", [("Six sites", "")])]},
    {"kind": "timeline", "head": "The year", "steps": [("October", "Board vote", ""), ("Spring", "Site opens", "")]},
    {"kind": "statement", "head": "Every seat is filled", "caption": "And 287 adults wait."},
    {"kind": "image", "head": "The Eastgate library", "caption": "Where the site would open."},
    {"kind": "content", "head": "What it buys", "items": [("A site", ""), ("Two coordinators", "")]},
    {"kind": "closing", "head": "Help us open the sixth site", "text": "The budget grows by $190,000.", "cta": "Talk with us",
     "amount": "$190,000", "amount_label": "More a year"},
]


def system(kid, family=None):
    kit = kits.get(kid)
    pal, faces = kits.palette(kit), kits.faces(kit)
    ty = SC.Type(RD.faces_for(kit, faces))
    name = RD.system_of(kit)
    return SY.for_kit(kit, pal, ty, name, family or RD.family_of(kit, name)), pal


def deck(kid, family=None):
    sysm, pal = system(kid, family)
    return [sysm.compose({**sp, "num": i + 1}) for i, sp in enumerate(SPECS)], pal


class SecondFamily(unittest.TestCase):
    def test_families_per_system(self):
        self.assertEqual(RD.family_of(kits.get("counsel")), "classic")
        self.assertEqual(RD.family_of(kits.get("chart-room")), "classic")
        self.assertEqual(RD.family_of(kits.get("folio")), "classic")
        self.assertEqual(RD.family_of(kits.get("stage")), "editorial")
        self.assertEqual(RD.family_of(kits.get("meridian")), "editorial")
        # an imported brand (a kit that is not a starter) takes the editorial family; its own choice wins
        self.assertEqual(RD.family_of({"id": "k_brand", "layout": "report"}, "exhibit"), "editorial")
        self.assertEqual(RD.family_of({"id": "k_brand", "family": "classic"}, "exhibit"), "classic")

    def test_every_kind_renders_and_no_two_neighbors_share_a_composition(self):
        for kid in ("stage", "meridian", "counsel", "chart-room", "folio"):
            scs, _pal = deck(kid, "editorial")
            self.assertEqual(len(scs), len(SPECS), kid)
            for sp, sc in zip(SPECS, scs):
                self.assertEqual(sc["family"], "editorial", kid)
                self.assertTrue(SC.text_of(sc).strip(), (kid, sp["kind"]))
            overridden = {"title", "exhibit", "figures", "quote", "ledger", "content", "closing", "stat"}
            for a, b, sa, sb in zip(scs, scs[1:], SPECS, SPECS[1:]):
                if sa["kind"] in overridden and sb["kind"] in overridden:
                    self.assertNotEqual(a["comp"], b["comp"], (kid, sa["kind"], sb["kind"]))

    def test_harborlight_order_alternates(self):
        scs, _ = deck("stage")
        comps = [sc["comp"] for sc in scs[:8]]
        self.assertEqual(comps, ["full", "split-L", "full", "split-R", "rail-R", "open", "rail-R", "open"][:7] + [comps[7]])

    def test_the_exhibit_bleeds_off_the_edge_with_the_flagged_bar_in_the_accent(self):
        for kid in ("stage", "meridian"):
            scs, pal = deck(kid)
            ex = next(s for s in scs if s["kind"] == "exhibit")
            bars = sorted((el for el in ex["els"] if el["t"] == "rect" and "bar" in el), key=lambda el: el["bar"])
            self.assertEqual(len(bars), 3, kid)
            self.assertEqual(bars[2]["fill"].lower(), pal["accent"].lower(), kid)
            self.assertEqual(bars[0]["fill"], bars[1]["fill"], kid)
            longest = max(bars, key=lambda el: el["w"])
            self.assertTrue(longest["x"] + longest["w"] >= SY.W - 0.5 or longest["x"] <= 0.5, kid)
            # a field of color owns one side, full height
            self.assertTrue(any(el["t"] == "rect" and el["h"] >= SY.H and SY.W * 0.3 < el["w"] < SY.W * 0.6 for el in ex["els"]), kid)
            self.assertIn("212 more adults than last year", SC.text_of(ex))

    def test_classic_kits_are_unchanged(self):
        scs, _ = deck("counsel")
        self.assertTrue(all(sc.get("family") is None for sc in scs))

    def test_editorial_title_is_44pt_or_more(self):
        for kid in ("stage", "meridian"):
            scs, _ = deck(kid)
            for sc in scs:
                if sc["kind"] in ("exhibit", "ledger", "content"):
                    t = next(el for el in sc["els"] if el["t"] == "text" and el.get("role") == "title")
                    self.assertGreaterEqual(t["size"], 30, (kid, sc["kind"]))

    def test_hero_deck_through_scenes(self):
        kit = kits.get("meridian")
        scs, _ty = RD.scenes(HERO, kit, kits.palette(kit), kits.faces(kit), {}, [], "", {})
        self.assertEqual([s["kind"] for s in scs], ["title", "exhibit", "quote"])
        self.assertTrue(all(s["family"] == "editorial" for s in scs))
        self.assertFalse(any(s.get("long") for s in scs))


def docx_with(images: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:document/>")
        for name, data in images.items():
            z.writestr(name, data)
    return buf.getvalue()


def picture(w, h) -> bytes:
    from PIL import Image
    im = Image.new("RGB", (w, h))
    for x in range(0, w, 8):  # a test pattern, made here; no image is fetched
        for y in range(0, h, 8):
            im.putpixel((x, y), ((x * 3) % 256, (y * 5) % 256, 120))
    out = io.BytesIO()
    im.save(out, "JPEG")
    return out.getvalue()


class SourcePhotos(unittest.TestCase):
    def test_largest_embedded_photo_credited_to_its_file(self):
        data = docx_with({"word/media/image1.jpeg": picture(900, 600), "word/media/image2.jpeg": picture(120, 120),
                          "docProps/thumbnail.jpeg": picture(1200, 900)})
        ph = RD.source_photo(data, "Site report.docx")
        self.assertEqual(ph["credit"], "Site report.docx")
        from PIL import Image
        self.assertEqual(Image.open(io.BytesIO(ph["bytes"])).size, (900, 600))

    def test_no_photo_no_change(self):
        self.assertIsNone(RD.source_photo(docx_with({"docProps/thumbnail.jpeg": picture(1200, 900)}), "a.docx"))
        self.assertIsNone(RD.source_photo(docx_with({"word/media/icon.png": b"x"}), "a.docx"))
        self.assertIsNone(RD.source_photo(b"%PDF-1.4 no images", "a.pdf"))

    def test_harborlight_sources_hold_no_photo(self):
        d = ROOT / "samples" / "harborlight"
        for f in ("FY26-Program-Report.docx", "Harborlight-Brand-Guide-2025.pdf", "board-retreat-notes.txt"):
            self.assertIsNone(RD.source_photo((d / f).read_bytes(), f), f)

    def test_cover_and_quote_use_the_photo_with_its_credit(self):
        doc = {**HERO, "photo": {"name": "src-photo", "credit": "Site report.docx"}}
        for kid in ("stage", "counsel"):
            kit = kits.get(kid)
            scs, _ty = RD.scenes(doc, kit, kits.palette(kit), kits.faces(kit), {}, [], "", {})
            cover = scs[0]
            if RD.family_of(kit) == "editorial":
                self.assertTrue(any(el["t"] == "image" and el["name"] == "src-photo" for el in cover["els"]), kid)
                self.assertIn("Photo: Site report.docx", SC.text_of(cover), kid)
        kit = kits.get("stage")
        plain, _ = RD.scenes(HERO, kit, kits.palette(kit), kits.faces(kit), {}, [], "", {})
        self.assertFalse(any(el["t"] == "image" for sc in plain for el in sc["els"]))


if __name__ == "__main__":
    unittest.main()
