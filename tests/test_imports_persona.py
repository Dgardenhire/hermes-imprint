"""Kit import quality from the Nov 8 persona run: a brand guide PDF (Denise), its color page pasted, and a
Canva-style PowerPoint on Office's default theme (Ana)."""
import unittest
from pathlib import Path

from _load import fonts, imports, reset, service

PERSONAS = Path(__file__).resolve().parent.parent / "harness" / "live" / "personas"
GUIDE = PERSONAS / "denise" / "Harborlight-Brand-Guide-2025.pdf"
CANVA = PERSONAS / "ana" / "Salvia Kitchen Brand Kit.pptx"
COLOR_PAGE = """Color
Harbor Teal
HEX #0E5E6F   PMS 3155 C   CMYK 100 / 30 / 30 / 40
Primary. Headlines, the logo, bands.
Sunrise Gold
HEX #F2A900   PMS 130 C   CMYK 0 / 30 / 100 / 0
Accent. Use sparingly: rules, callouts, one number.
Lighthouse Red
HEX #C0392B   PMS 7621 C   CMYK 10 / 90 / 90 / 5
Calls to action only.
Warm Gray
HEX #5B5651   PMS Warm Gray 11 C   CMYK 0 / 10 / 15 / 70
Secondary text.
Paper
HEX #FAF7F2
Backgrounds.
Ink
HEX #2B2B2B
Body text.
"""


def roles(kit):
    return {c["role"]: c["hex"] for c in kit["colors"]}


class PastedColorPage(unittest.TestCase):
    def test_labels_beside_codes_decide_the_roles(self):
        kit = imports.build(imports.read_paste(COLOR_PAGE))
        self.assertEqual(kit["paper"], "#faf7f2")
        self.assertEqual(kit["ink"], "#2b2b2b")
        r = roles(kit)
        self.assertEqual(r["head"], "#0e5e6f", "Primary. Headlines, the logo, bands.")
        self.assertEqual(r["accent"], "#f2a900")
        self.assertNotEqual(r.get("band"), "#c0392b", "calls to action only never becomes the band")
        self.assertEqual(kit["layout"], "banner")
        pal = service.KITS.palette(service.KITS.normalize({**kit, "name": "x"}))
        self.assertEqual(pal["band"] or pal["head"], "#0e5e6f", "the band is the primary teal")

    def test_names_are_kept_and_no_color_appears_twice(self):
        kit = imports.build(imports.read_paste(COLOR_PAGE))
        hexes = [c["hex"] for c in kit["colors"]]
        self.assertEqual(len(hexes), len(set(hexes)))
        names = {c["hex"]: c["name"] for c in kit["colors"]}
        self.assertEqual(names["#0e5e6f"], "Harbor Teal")
        self.assertEqual(names["#c0392b"], "Lighthouse Red")

    def test_one_line_labels(self):
        fd = imports.read_paste("Primary: #1A4480\nCalls to action only: #D83933\nBackground #FFFFFF\nText #1B1B1B")
        kit = imports.build(fd)
        self.assertEqual((kit["paper"], kit["ink"]), ("#ffffff", "#1b1b1b"))
        self.assertEqual(roles(kit)["head"], "#1a4480")
        self.assertNotIn("#d83933", [c["hex"] for c in kit["colors"] if c["role"] == "band"])

    def test_duplicate_primary_from_css_shows_once(self):
        kit = imports.build(imports.read_css(":root{--primary:#1a4480;--bg:#ffffff;--fg:#1b1b1b}"))
        self.assertEqual([c["hex"] for c in kit["colors"]].count("#1a4480"), 1)


class BrandGuidePdf(unittest.TestCase):
    def setUp(self):
        reset()

    def test_reads_codes_labels_fonts_and_name(self):
        fd = imports.read("pdf", data=GUIDE.read_bytes(), filename=GUIDE.name)
        self.assertEqual(fd["kind"], "pdf")
        self.assertEqual(fd["name"], "Harborlight")
        kit = imports.build(fd)
        self.assertEqual(roles(kit)["head"], "#0e5e6f")
        self.assertEqual(kit["type"]["heading"]["stack"], "Montserrat, Arial")
        self.assertEqual(kit["type"]["body"]["stack"], "Lora, Georgia")
        self.assertEqual(kit["origin_note"], "Read from a brand guide PDF")

    def test_a_pdf_routes_to_the_guide_reader_and_lands_as_a_draft(self):
        self.assertEqual(imports.kind_from_name("Harborlight-Brand-Guide-2025.pdf"), "pdf")
        draft = service.import_read("pdf", filename=GUIDE.name, data=GUIDE.read_bytes())
        self.assertTrue(draft["can_save"], draft["checks"])
        self.assertTrue(draft["proof"]["tree"])

    def test_a_guide_with_no_codes_says_what_to_do(self):
        from reportlab.pdfgen import canvas
        import io
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "Our colors are on the next page.")
        c.save()
        with self.assertRaises(imports.Refused) as e:
            imports.read_pdf_guide(buf.getvalue())
        self.assertIn("paste it under Paste color codes", str(e.exception))

    def test_drawn_swatches_are_read_when_there_are_no_codes(self):
        from reportlab.pdfgen import canvas
        import io
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        for i in range(3):
            c.setFillColorRGB(0.0549, 0.3686, 0.4353)
            c.rect(72, 600 - i * 60, 80, 40, fill=1, stroke=0)
        c.save()
        fd = imports.read_pdf_guide(buf.getvalue())
        self.assertIn("#0e5e6f", [x["hex"] for x in fd["colors"]])

    def test_unknown_file_refusal_offers_a_way_forward(self):
        with self.assertRaises(imports.Refused) as e:
            imports.kind_from_name("guide.indd")
        self.assertIn("copy the page with your color codes", str(e.exception))


class CanvaPowerPoint(unittest.TestCase):
    def test_ranks_by_what_the_slides_use(self):
        fd = imports.read_pptx(CANVA.read_bytes(), CANVA.name)
        kit = imports.build(fd)
        self.assertEqual(kit["paper"], "#f6efe3", "her cream, not the theme's white")
        self.assertEqual(kit["ink"], "#3a3a3a")
        hexes = [c["hex"] for c in kit["colors"]]
        for office in ("#1f497d", "#4f81bd", "#c0504d", "#9bbb59"):
            self.assertNotIn(office, hexes)
            self.assertTrue(any(s["what"] == office for s in fd["skipped"]))
        self.assertIn("#c8553d", hexes, "terracotta kept")
        self.assertIn("#e9b44c", hexes, "saffron kept")
        self.assertEqual(roles(kit)["head"], "#2f4a3a")
        self.assertEqual(kit["type"]["heading"]["family"], "Playfair Display")
        self.assertEqual(kit["type"]["body"]["family"], "Poppins")
        self.assertEqual(kit["name"], "Salvia Kitchen")


class NearestOpenFont(unittest.TestCase):
    def test_missing_families_fall_to_the_nearest_bundled_face(self):
        f = fonts.resolve({"family": "Playfair Display", "weight": 700}, {})
        self.assertEqual(f["used"], "Libre Caslon Display")
        self.assertTrue(f["substituted"])
        self.assertEqual(fonts.resolve({"family": "Poppins"}, {})["used"], "Inter")
        self.assertEqual(fonts.resolve({"family": "Cormorant", "stack": "Cormorant, Georgia"}, {})["used"], "Crimson Pro")
        f = fonts.resolve({"family": "Raleway", "stack": "Raleway, Arial", "weight": 700}, {})
        self.assertEqual((f["used"], f["source"], f["pdf"], f["weight"]), ("Inter", "bundled", None, 700),
                         "a stack that falls to Arial embeds the bundled face the preview draws, never base-14 Helvetica")

    def test_the_harborlight_guide_faces_are_bundled_now(self):
        """Montserrat and Lora ship in fonts/ (Nov 9), so the sample brand is set in its own faces, not stand-ins."""
        f = fonts.resolve({"family": "Montserrat", "stack": "Montserrat, Arial", "weight": 700}, {})
        self.assertEqual((f["used"], f["source"], f["substituted"]), ("Montserrat", "bundled", False))
        f = fonts.resolve({"family": "Lora", "stack": "Lora, Georgia"}, {})
        self.assertEqual((f["used"], f["source"], f["substituted"]), ("Lora", "bundled", False))


if __name__ == "__main__":
    unittest.main()
