"""Outputs that don't look templated (Nov 8 persona run): layouts differ in composition, a flyer reads as a
flyer with items and prices, and no page leaves its bottom third empty."""
import copy
import unittest

from _load import checks, content, kits, layout, render_pdf, service, starter_kits

MENU = {"title": "Fall office catering", "dek": "Boxed lunches and trays.", "dek_refs": ["P1"],
        "stat": {"value": "$16", "label": "per boxed lunch", "ref": "P1"},
        "sections": [{"heading": "Add-ons", "body": "", "refs": ["P1"],
                      "items": [{"name": "Agua fresca by the gallon", "price": "$28", "note": ""},
                                {"name": "Churro bites", "price": "$3", "note": "Per person"}]},
                     {"heading": "How to order", "body": "We need 72 hours notice.", "refs": ["P1"]}],
        "points": [{"text": "214 events catered last year", "ref": "P1"}], "quote": None,
        "next": "Order by phone at 555-0142."}
PASSAGES = {"P1": {"text": "Boxed lunches, $16 per person. Add-ons: agua fresca by the gallon, $28. Churro bites, $3 per person. "
                           "We need 72 hours notice. We catered 214 events. Order by phone at 555-0142.",
                   "locator": "para. 1", "source_id": "s1", "source_title": "Fall menu"}}


def classes(node, out=None):
    out = out if out is not None else set()
    out.update((node.get("c") or "").split())
    for k in node.get("k") or []:
        classes(k, out)
    return out


class Menu(unittest.TestCase):
    def test_items_survive_cleaning_and_are_checked(self):
        doc = content.clean_onepager(copy.deepcopy(MENU))
        self.assertEqual(doc["sections"][0]["items"][0], {"name": "Agua fresca by the gallon", "price": "$28", "note": ""})
        g = checks.grounding(doc, PASSAGES)
        self.assertEqual(g["missing"], [])
        prices = [i["shown"] for i in g["items"] if i["path"].startswith("sections.0.items")]
        self.assertEqual(prices, ["$28", "$3"])
        doc["sections"][0]["items"][1]["price"] = "$4"
        self.assertEqual([i["shown"] for i in checks.grounding(doc, PASSAGES)["missing"]], ["$4"])

    def test_menu_brief_asks_for_items(self):
        self.assertIn("as an item", content.onepager_instructions("A menu flyer for office managers"))
        self.assertNotIn("as an item", content.onepager_instructions("A board brief"))

    def test_remove_a_flagged_item(self):
        doc = copy.deepcopy(MENU)
        service._remove(doc, "sections.0.items.1", "sections.0.items.1|number|4")
        self.assertEqual([i["name"] for i in doc["sections"][0]["items"]], ["Agua fresca by the gallon"])


class Families(unittest.TestCase):
    def tree(self, kit_id, doc=MENU):
        kit = kits.get(kit_id)
        return layout.tree(doc, kit, kits.palette(kit), kits.faces(kit), PASSAGES, date="Nov 8")

    def test_flyer_reads_as_a_flyer(self):
        c = classes(self.tree("market-board"))
        for want in ("ip-flyer", "ip-flyer-stamp", "ip-menu", "ip-menu-price", "ip-flyer-cta"):
            self.assertIn(want, c)

    def test_report_has_figures_and_sideheads(self):
        c = classes(self.tree("board-report"))
        for want in ("ip-report", "ip-figures", "ip-report-row", "ip-sidehead"):
            self.assertIn(want, c)

    def test_starters_cover_cover_flyer_and_report_families_and_the_shelf_shows_each(self):
        layouts = {k["layout"] for k in starter_kits.STARTERS}
        self.assertTrue({"banner", "headline", "flyer", "report", "letter", "margin", "bulletin"} <= layouts)
        shelf = [k["layout"] for k in starter_kits.STARTERS if k.get("featured")]
        self.assertEqual(len(shelf), len(set(shelf)), "each featured starter shows a different composition")

    def test_menu_kit_hides_source_marks_by_default(self):
        self.assertFalse(kits.get("market-board")["rules"]["sources"])


class FillsThePage(unittest.TestCase):
    def test_a_short_draft_is_set_larger_in_the_pdf(self):
        from pypdf import PdfReader
        import io
        for kid in ("market-board", "board-report", "plain-notice"):
            kit = kits.get(kid)
            pal, faces = kits.palette(kit), kits.faces(kit)
            names = render_pdf.register_faces(faces)
            k = render_pdf.fill_scale(MENU, kit, pal, faces, {}, [], "", names, 612 - 92, 600, kit["layout"])
            self.assertGreater(k, 1.05, kid)
            pdf = render_pdf.render(MENU, kit, pal, faces, {}, [], "Set in x.", date="Nov 8")
            self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages), 1)

    def test_pane_and_html_pin_the_foot_to_the_bottom(self):
        self.assertIn(".ip-inner>.ip-foot,.ip-main>.ip-foot{margin-top:auto}", layout.PROOF_CSS)
        self.assertIn(".ip-flyer-cta{", layout.PROOF_CSS)


if __name__ == "__main__":
    unittest.main()
