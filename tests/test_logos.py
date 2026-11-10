"""The invisible-logo problem (Nov 8 persona run): a teal lighthouse on a teal band, a sage leaf on a sage band.
Imprint measures the mark against the ground it sits on and knocks it out, or uses the kit's reversed logo."""
import io
import unittest
import zipfile
from pathlib import Path

from _load import add_samples, fake_model, logos, make, reset, service

PERSONAS = Path(__file__).resolve().parent.parent / "harness" / "live" / "personas"
TEAL = "#0e5e6f"


def harbor_kit(layout="banner"):
    k = service.KITS.save_new({**service.KITS.get("plain-notice"), "name": "Harborlight", "layout": layout,
                               "paper": "#faf7f2", "ink": "#2b2b2b",
                               "colors": [{"hex": TEAL, "role": "band"}, {"hex": TEAL, "role": "head"}, {"hex": "#f2a900", "role": "rule"}]})
    service.KITS.set_logo(k["id"], "harborlight-logo.png", (PERSONAS / "denise" / "harborlight-logo.png").read_bytes())
    return service.KITS.get(k["id"])


def png_colors(data):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    return {px[:3] for px in im.getdata() if px[3] > 200}


class Measure(unittest.TestCase):
    def setUp(self):
        reset()

    def test_teal_mark_on_teal_band_is_knocked_out_and_reads_on_paper(self):
        kit = harbor_kit()
        v = service.KITS.logo_variants(kit)
        self.assertEqual(v["band"]["mode"], "knockout")
        self.assertLess(v["band"]["share"], logos.ENOUGH)
        self.assertEqual(v["paper"]["mode"], "as_is")
        cols = png_colors(v["band"]["data"])
        self.assertIn((255, 255, 255), cols, "the teal that vanished is set in the band's text color")
        self.assertTrue(any(r > 200 and 120 < g < 200 and b < 60 for r, g, b in cols), "the gold stroke keeps its own color")
        flat = png_colors(logos.knockout_png((PERSONAS / "denise" / "harborlight-logo.png").read_bytes(), "#ffffff"))
        self.assertEqual(flat, {(255, 255, 255)}, "with no ground, the whole shape is one color")

    def test_sage_leaf_on_sage_band(self):
        reset()
        k = service.KITS.save_new({**service.KITS.get("plain-notice"), "name": "Salvia", "paper": "#f6f1e7", "ink": "#2a2a2a",
                                   "colors": [{"hex": "#2f4f3e", "role": "band"}, {"hex": "#c8553d", "role": "accent"}]})
        service.KITS.set_logo(k["id"], "salvia-logo.png", (PERSONAS / "ana" / "salvia-logo.png").read_bytes())
        v = service.KITS.logo_variants(service.KITS.get(k["id"]))
        self.assertEqual(v["band"]["mode"], "knockout")

    def test_svg_knockout_recolors_every_fill(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path fill="#0E5E6F" d="M0 0h10v10z"/><circle r="2" stroke="black"/></svg>'
        out = logos.knockout_svg(svg, "#ffffff").decode()
        self.assertNotIn("0E5E6F", out)
        self.assertNotIn("black", out)
        self.assertIn('<svg fill="#ffffff"', out)

    def test_the_kits_reversed_logo_wins_over_a_knockout(self):
        kit = harbor_kit()
        from PIL import Image
        im = Image.new("RGBA", (40, 20), (255, 255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        service.KITS.set_logo(kit["id"], "logo-white.png", buf.getvalue(), alt=True)
        kit = service.KITS.get(kit["id"])
        self.assertEqual(kit["logo_alt"], {"file": "logo-reversed.png", "kind": "png"})
        v = service.KITS.logo_variants(kit)
        self.assertEqual(v["band"]["mode"], "alternate")
        self.assertEqual(v["paper"]["mode"], "as_is", "the main logo still goes on paper")
        dup = service.KITS.duplicate(kit["id"])
        self.assertTrue(service.KITS.logo_path(dup, alt=True).is_file())

    def test_reversed_logo_name_is_held_to_the_one_shape(self):
        self.assertIsNone(service.KITS.safe_logo({"file": "../x.png", "kind": "png"}, "logo-reversed"))
        self.assertIsNone(service.KITS.safe_logo({"file": "logo.png", "kind": "png"}, "logo-reversed"))
        self.assertIsNone(service.KITS.safe_logo({"file": "evil.png", "kind": "png"}, "evil"))


class EveryPageType(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.kit = harbor_kit()
        self.ids = [s["id"] for s in add_samples()]

    def _out(self, kind):
        j = make(self.ids, [self.kit["id"]], kind=kind, brief=f"A {kind} for the board")
        self.assertEqual(j["status"], "done", j)
        return j["result"]["output_id"]

    def test_one_pager_proof_html_and_pdf(self):
        oid = self._out("onepager")
        pr = service.proof(oid, self.kit["id"])
        pill = next(p for p in pr["checks"] if p["id"] == "logo")
        self.assertIn("on the band", pill["label"])
        band_url = service.KITS.logo_variants(self.kit)["band"]["data_url"]
        self.assertIn(band_url, str(pr["tree"]), "the band's masthead carries the knocked-out mark")
        page = Path(service.export(oid, self.kit["id"], "html")["path"]).read_text()
        self.assertIn(band_url, page)
        from pypdf import PdfReader
        pdf = PdfReader(service.export(oid, self.kit["id"], "pdf")["path"])
        self.assertTrue(pdf.pages[0].images, "the logo is drawn on the PDF band")

    def test_deck_band_slides_hide_the_master_logo_and_carry_the_knockout(self):
        from pptx import Presentation
        oid = self._out("deck")
        r = service.export(oid, self.kit["id"], "pptx")
        prs = Presentation(r["path"])
        self.assertTrue(any(sh.shape_type == 13 for sh in prs.slide_master.shapes))
        first = prs.slides[0]
        self.assertEqual(first._element.get("showMasterSp"), "0")
        self.assertTrue(any(sh.shape_type == 13 for sh in first.shapes))
        light = [s for s in prs.slides if s._element.get("showMasterSp") != "0"]
        self.assertTrue(light, "paper slides keep the master's logo")
        self.assertTrue(service.export(oid, self.kit["id"], "pdf")["bytes"] > 0)


if __name__ == "__main__":
    unittest.main()
