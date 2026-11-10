"""Loop 2 design: the hero exhibit in every studio system, the one-pager set as a scene, and the exports that come
from it (PDF with no proof furniture, HTML with the scene stylesheet, PowerPoint with titles and native bars)."""
import io
import unittest
from importlib import import_module

from _load import add_samples, fake_model, kits, layout, make, reset, service

PKG = "imprint_plugin_package"
RD = import_module(f"{PKG}.render_deck")
RG = import_module(f"{PKG}.render_graphic")
SC = import_module(f"{PKG}.scene")
STUDIO = ("counsel", "chart-room", "stage", "folio", "meridian")

HERO_DECK = {"title": "A sixth site", "subtitle": "For funders", "slides": [
    {"type": "exhibit", "heading": "Demand is outgrowing our seats", "subhead": "212 more adults than last year", "unit": "Adult learners",
     "refs": [], "note": "",
     "bars": [{"label": "FY2025", "value": "936", "ref": ""}, {"label": "FY2026", "value": "1,148", "ref": ""},
              {"label": "Waiting at year end", "value": "287", "ref": "", "accent": True}]},
    {"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "Most at Eastgate and Riverside.", "refs": []},
    {"type": "quote", "quote": "I read my granddaughter a bedtime story", "who": "A learner", "refs": []}]}

PAGE = {"title": "The budget request, on one page", "dek": "Staff ask the board to approve a budget of $1,610,000.", "dek_refs": [],
        "stat": {"value": "287", "label": "adults on the waitlist", "ref": ""},
        "sections": [{"heading": "Who we served", "body": "Harborlight enrolled 1,148 adult learners, up from 936.", "refs": []},
                     {"heading": "The money", "body": "Operating expenses were $1,420,000.", "refs": []}],
        "points": [{"text": "1,148 adults enrolled", "ref": ""}, {"text": "71 learners earned a credential", "ref": ""}],
        "quote": {"text": "I read my granddaughter a bedtime story.", "who": "A learner", "ref": ""},
        "next": "The board votes on October 21."}


def hero(kid):
    kit = kits.get(kid)
    pal, faces = kits.palette(kit), kits.faces(kit)
    scs, ty = RD.scenes(HERO_DECK, kit, pal, faces, {}, [], "November 8, 2026", {})
    return kit, pal, next(s for s in scs if s["kind"] == "exhibit")


class HeroExhibit(unittest.TestCase):
    def test_title_is_44pt_or_more_in_every_system(self):
        for kid in STUDIO:
            _k, _p, sc = hero(kid)
            title = next(el for el in sc["els"] if el["t"] == "text" and el.get("role") == "title")
            self.assertGreaterEqual(title["size"], 44, kid)
            self.assertEqual(" ".join(title["lines"]).lower(), "demand is outgrowing our seats", kid)

    def test_the_accent_bar_is_the_flagged_one_and_the_rest_share_a_tint(self):
        for kid in STUDIO:
            _k, pal, sc = hero(kid)
            bars = sorted((el for el in sc["els"] if el["t"] == "rect" and "bar" in el), key=lambda el: el["bar"])
            self.assertEqual(len(bars), 3, kid)
            self.assertEqual(bars[2]["fill"].lower(), pal["accent"].lower(), kid)
            self.assertEqual(bars[0]["fill"], bars[1]["fill"], kid)
            self.assertNotEqual(bars[0]["fill"].lower(), pal["accent"].lower(), kid)

    def test_subhead_shows_and_no_exhibit_eyebrow(self):
        for kid in STUDIO:
            _k, _p, sc = hero(kid)
            text = SC.text_of(sc)
            self.assertIn("212 more adults than last year", text, kid)
            self.assertNotIn("Exhibit 1", text, kid)
            self.assertNotIn("EXHIBIT", text, kid)
            self.assertFalse(sc.get("long"), kid)

    def test_without_a_flag_the_largest_bar_is_the_finding(self):
        doc = {**HERO_DECK, "slides": [{**HERO_DECK["slides"][0], "bars": [{**b, "accent": False} for b in HERO_DECK["slides"][0]["bars"]]}]
               + HERO_DECK["slides"][1:]}
        kit = kits.get("counsel")
        pal, faces = kits.palette(kit), kits.faces(kit)
        scs, _ty = RD.scenes(doc, kit, pal, faces, {}, [], "", {})
        sc = next(s for s in scs if s["kind"] == "exhibit")
        bars = sorted((el for el in sc["els"] if el["t"] == "rect" and "bar" in el), key=lambda el: el["bar"])
        self.assertEqual(bars[1]["fill"].lower(), pal["accent"].lower())

    def test_graphic_honors_the_accent_item(self):
        vis = {"kicker": "Literacy", "headline": "Demand is outgrowing our seats", "dek": "", "dek_refs": [], "form": "bars", "unit": "",
               "items": [{"label": "FY2025", "value": "936", "ref": ""}, {"label": "FY2026", "value": "1,148", "ref": ""},
                         {"label": "Waiting", "value": "287", "ref": "", "accent": True}],
               "steps": [], "takeaway": "", "takeaway_refs": []}
        for kid in STUDIO:
            kit = kits.get(kid)
            pal, faces = kits.palette(kit), kits.faces(kit)
            sc, _ty = RG.scene(vis, kit, pal, faces, {}, {})
            bars = sorted((el for el in sc["els"] if el["t"] == "rect" and "bar" in el), key=lambda el: el["bar"])
            self.assertEqual(bars[2]["fill"].lower(), pal["accent"].lower(), kid)


class PageScene(unittest.TestCase):
    def test_studio_kits_set_the_one_pager_as_a_letter_scene(self):
        for kid in STUDIO:
            kit = kits.get(kid)
            pal, faces = kits.palette(kit), kits.faces(kit)
            tree = layout.tree(PAGE, kit, pal, faces, {}, date="November 8, 2026")
            self.assertIn("ip-scene", tree["c"].split(), kid)
            self.assertEqual(tree["a"]["style"]["--ar"], "612.0 / 792.0", kid)
            text = layout.text_of(tree)
            for want in ("The budget request, on one page", "287", "The board votes on October 21."):
                self.assertIn(want, text, kid)
            # a line that only names a date is set as a date line, not under "What we ask"
            self.assertNotIn("WHAT WE ASK", text, kid)
            ask = dict(PAGE, next="Approve the $1,610,000 budget on October 21.")
            self.assertIn("WHAT WE ASK", layout.text_of(layout.tree(ask, kit, pal, faces, {}, date="November 8, 2026")), kid)

    def test_earlier_starters_keep_their_html_family(self):
        kit = kits.get("plain-notice")
        tree = layout.tree(PAGE, kit, kits.palette(kit), kits.faces(kit), {}, date="")
        self.assertTrue(tree["c"].startswith("ip-page"))

    def test_page_text_fits(self):
        for kid in STUDIO:
            kit = kits.get(kid)
            sc, _ty = layout.page_scene(PAGE, kit, kits.palette(kit), kits.faces(kit), {}, "")
            self.assertFalse(sc.get("long"), kid)
            for el in sc["els"]:
                self.assertLessEqual(el["x"] + el["w"], 612.5, (kid, el.get("lines")))


class PageExports(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.ids = [s["id"] for s in add_samples()]

    def test_studio_one_pager_pdf_and_html_come_from_the_scene(self):
        j = make(self.ids, ["counsel"], kind="onepager", brief="A one-pager")
        self.assertEqual(j["status"], "done", j)
        oid = j["result"]["output_id"]
        pr = service.proof(oid, "counsel")
        self.assertIn("ip-scene", pr["tree"]["c"].split())
        from pathlib import Path
        from pypdf import PdfReader
        pdf = PdfReader(service.export(oid, "counsel", "pdf")["path"])
        self.assertEqual(len(pdf.pages), 1)
        box = pdf.pages[0].mediabox
        self.assertEqual((round(float(box.width)), round(float(box.height))), (612, 792))
        text = pdf.pages[0].extract_text()
        self.assertNotIn("Set in", text)
        html = Path(service.export(oid, "counsel", "html")["path"]).read_text()
        self.assertIn(".ip-sc-t", html)


class PdfTracking(unittest.TestCase):
    def test_a_tracked_label_does_not_space_out_the_next_text(self):
        from reportlab.pdfgen import canvas as rlcanvas
        kit = kits.get("counsel")
        ty = SC.Type(RD.faces_for(kit, kits.faces(kit)))
        c = SC.Canvas(ty, 200, 100, "#ffffff")
        c.text("LABEL", 10, 10, 180, 20, face="label", size=12, track=0.2, color="#000000")
        c.text("Body text", 10, 40, 180, 20, face="body", size=12, color="#000000")
        buf = io.BytesIO()
        pdf = rlcanvas.Canvas(buf, pagesize=(200, 100), pageCompression=0)
        SC.draw_pdf(pdf, c.scene, ty)
        pdf.showPage()
        pdf.save()
        data = buf.getvalue()
        self.assertIn(b"2.4 Tc", data)
        self.assertIn(b"0 Tc", data.split(b"2.4 Tc", 1)[1])


class GraphicCraft(unittest.TestCase):
    """Round 7: the logo keeps its own place, side-by-side values never touch, big numbers hold the page, and a brand
    whose face falls back to a system font still embeds the bundled face in its PDF."""
    PAIR = {"kicker": "The cost", "headline": "The request is higher than last year's spending", "dek": "", "dek_refs": [],
            "form": "compare", "unit": "", "items": [{"label": "FY2026 expenses", "value": "$1,420,000", "ref": ""},
                                                    {"label": "FY2027 request", "value": "$1,610,000", "ref": "", "accent": True}],
            "steps": [], "takeaway": "", "takeaway_refs": []}

    def test_logo_node_is_a_positioned_box(self):
        sc = {"w": 100, "h": 100, "bg": "#fff", "els": [{"t": "logo", "x": 80, "y": 90, "w": 15, "h": 5, "place": "paper", "align": "right"}]}
        node = SC.nodes(sc, SC.Type(kits.faces(kits.get("counsel"))), logos={"paper": "data:image/png;base64,AA=="})["k"][0]
        self.assertEqual(node["t"], "div")
        self.assertEqual(node["a"]["style"]["--x"], "80.000")
        self.assertEqual(node["k"][0]["t"], "img")

    def test_compare_values_never_overlap(self):
        for kid in STUDIO:
            kit = kits.get(kid)
            pal, faces = kits.palette(kit), kits.faces(kit)
            sc, ty = RG.scene(self.PAIR, kit, pal, faces, {}, {})
            vals = [el for el in sc["els"] if el["t"] == "text" and el["lines"][0] in ("$1,420,000", "$1,610,000")]
            self.assertEqual(len(vals), 2, kid)
            a, b = sorted(vals, key=lambda el: el["x"])
            self.assertLess(a["x"] + ty.width(a["lines"][0], a["face"], a["size"]), b["x"], kid)

    def test_big_numbers_fill_the_page(self):
        doc = dict(self.PAIR, form="figures", items=[{"label": "Adults on the waitlist", "value": "287", "ref": "", "accent": True},
                                                     {"label": "More learners a year", "value": "180", "ref": ""}])
        kit = kits.get("counsel")
        sc, _ty = RG.scene(doc, kit, kits.palette(kit), kits.faces(kit), {}, {})
        figs = [el for el in sc["els"] if el["t"] == "text" and el["lines"][0] in ("287", "180")]
        self.assertGreaterEqual(min(el["size"] for el in figs), 150)
        self.assertGreater(max(el["y"] for el in figs) - min(el["y"] for el in figs), 250)

    def test_fallback_brand_pdf_embeds_bundled_face(self):
        kit = dict(kits.get("counsel"), type={"heading": {"family": "Montserrat", "stack": "Montserrat, Arial", "weight": 700},
                                              "body": {"family": "Lora", "stack": "Lora, Georgia"}})
        faces = __import__(f"{PKG}.fonts", fromlist=["x"]).resolve_kit(kit)
        pdf = RG.render_pdf(self.PAIR, kit, kits.palette(kit), faces, {}, {})
        self.assertNotIn(b"/BaseFont /Helvetica", pdf)


if __name__ == "__main__":
    unittest.main()
