"""P6 round 2: evidence slides (figures, points that lead with a figure, matched before/after rows, the ask's amount),
the length that counts the Sources page, the wording check and the money coverage check."""

import unittest

from importlib import import_module

import _load  # noqa: F401  (loads the package on a temp data folder)

PKG = _load.PKG
CK = import_module(f"{PKG}.checks")
K = import_module(f"{PKG}.content")
RD = import_module(f"{PKG}.render_deck")

PASS = {
    "P1": {"text": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners, up from 936 the year before.", "locator": "Who we served",
           "source_title": "FY26 Program Report (Sample)"},
    "P2": {"text": "A corps of 214 volunteer tutors gave 9,870 tutoring hours. The average tutor stayed 14 months.",
           "locator": "Volunteers", "source_title": "FY26 Program Report (Sample)"},
    "P3": {"text": "Foundation grants provided $640,000, individual donors gave $388,000, and the city paid $295,000.",
           "locator": "Money", "source_title": "FY26 Program Report (Sample)"},
    "P4": {"text": "January 21 was the busiest night, with 64 guests.", "locator": "p. 2", "source_title": "Warming center report (Sample)"},
}

RAW = {"title": "A sixth site", "subtitle": "For funders", "slides": [
    {"type": "figures", "heading": "Tutors stay", "refs": ["P2"],
     "figures": [{"value": "214", "label": "volunteer tutors", "context": "One on one", "ref": "P2"},
                 {"value": "9,870", "label": "tutoring hours", "ref": "P2"},
                 {"value": "14 months", "label": "average stay", "ref": "P2"}]},
    {"type": "content", "heading": "The corps", "refs": ["P2"],
     "bullets": [{"figure": "214", "text": "volunteer tutors", "ref": "P2"}, {"figure": "9,870", "text": "hours given", "ref": "P2"},
                 {"figure": "14 months", "text": "average stay", "ref": "P2"}]},
    {"type": "comparison", "heading": "Today and with the plan", "refs": ["P1"], "left_label": "Today", "right_label": "With a sixth site",
     "rows": [{"label": "Learners", "left": "936", "right": "1,148", "ref": "P1"}, {"label": "Tutors", "left": "214", "right": "More", "ref": "P2"}]},
    {"type": "closing", "heading": "Back the site", "text": "Help", "cta": "Fund it", "amount": "$640,000", "amount_label": "Foundation grants",
     "refs": ["P3"]},
]}


class Clean(unittest.TestCase):
    def test_new_fields_survive_cleaning(self):
        d = K.clean_deck(RAW)
        s = d["slides"]
        self.assertEqual([f["value"] for f in s[0]["figures"]], ["214", "9,870", "14 months"])
        self.assertEqual([b.get("figure") for b in s[1]["bullets"]], ["214", "9,870", "14 months"])
        self.assertEqual(len(s[2]["rows"]), 2)
        self.assertEqual(s[3]["amount"], "$640,000")

    def test_every_number_is_a_checked_field(self):
        d = K.clean_deck(RAW)
        paths = {p for p, _t, _r in K.field_texts(d)}
        for p in ("slides.0.figures.2", "slides.1.bullets.0.figure", "slides.2.rows.1", "slides.3.amount"):
            self.assertIn(p, paths)
        g = CK.grounding(d, PASS)
        self.assertFalse(g["missing"], g["missing"])

    def test_voice_rules_never_rewrite_a_figure(self):
        d = K.clean_deck(RAW)
        out, changes = K.apply_pairs(d, [{"not": "tutors", "say": "teachers"}])
        self.assertEqual(out["slides"][1]["bullets"][0]["figure"], "214")
        self.assertEqual(out["slides"][1]["bullets"][0]["text"], "volunteer teachers")


class Specs(unittest.TestCase):
    def specs(self, doc, sources=True):
        kit = {"rules": {"sources": sources}}
        idx, rows = {"P1": 1, "P2": 1, "P3": 1}, [{"title": "FY26 Program Report (Sample)", "locators": ["Money"]}]
        return RD.slides(doc, kit, idx, rows, "", PASS)

    def test_kinds(self):
        sp = self.specs(K.clean_deck(RAW))
        # round 8: no Sources page unless the person asks for one; the feet and the notes name the sources
        self.assertEqual([s["kind"] for s in sp], ["title", "figures", "ledger", "matched", "closing"])
        self.assertTrue(sp[1]["src"])
        asked = {**K.clean_deck(RAW), "sources_page": True}
        self.assertEqual(self.specs(asked)[-1]["kind"], "sources")
        self.assertTrue(K.asks_for_sources("A funder deck that ends with a sources page"))
        self.assertFalse(K.asks_for_sources("A short deck for funders about the sixth site"))
        self.assertNotIn("fig", sp[0])  # no opening exhibit: the cover shows no figure, so none is set big twice (round 3)

    def test_sources_page_counts_toward_the_length(self):
        doc = {**K.clean_deck(RAW), "sources_page": True}
        self.assertEqual(self.specs(doc)[-1]["kind"], "sources")
        doc["max_slides"] = 5  # title + 4 slides fill it: the Sources page goes, the feet still name the sources
        sp = self.specs(doc)
        self.assertEqual(len(sp), 5)
        self.assertNotEqual(sp[-1]["kind"], "sources")
        self.assertTrue(sp[1]["src"])
        self.assertFalse([f for f in sp[1]["figs"] if f[3]])  # no source marks pointing at a Sources page that isn't there
        self.assertEqual(RD.slide_count(doc, {"rules": {"sources": True}}, [{"title": "x"}]), 5)


class Wording(unittest.TestCase):
    def test_a_superlative_the_source_never_uses_is_flagged(self):
        doc = {"title": "t", "slides": [{"type": "stat", "value": "64", "label": "guests on the coldest night", "refs": ["P4"]},
                                        {"type": "stat", "value": "64", "label": "guests on the busiest night", "refs": ["P4"]}]}
        hits = CK.wording(doc, PASS)
        self.assertEqual([h["word"] for h in hits], ["coldest"])
        self.assertIn("coldest", CK.pill_wording(hits)["label"])
        self.assertIsNone(CK.pill_wording([]))

    def test_money_passages_no_slide_cites(self):
        doc = K.clean_deck(RAW)
        self.assertEqual(CK.money_left_out(doc, PASS), [])
        doc["slides"] = doc["slides"][:2]
        left = CK.money_left_out(doc, PASS)
        self.assertEqual([x["ref"] for x in left], ["P3"])
        self.assertIn("Money", CK.pill_money(left)["label"])


if __name__ == "__main__":
    unittest.main()
