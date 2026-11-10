"""Loop 3 fix 2 (critics on held-out 11 and 12): the big figure is the number the line is about, topic titles get a
headline from the slide's own lines, internal notes never show in a visible source line, a quote slide is never a
list and a long list is two unnumbered columns split by kind. (Sample data only.)"""
import unittest
from importlib import import_module

from _load import PKG

K = import_module(f"{PKG}.content")
RD = import_module(f"{PKG}.render_deck")


class KeyFigure(unittest.TestCase):
    def test_count_not_the_duration(self):
        self.assertEqual(K.key_figure("Completed all 16 weeks: 19 (73% completion rate, up from 67%)"), "19")

    def test_end_of_a_growth(self):
        self.assertEqual(K.key_figure("Total enrollment would grow from 26 to 36 apprentices"), "36")
        self.assertEqual(K.key_figure("Average score fell from 8.9 to 8.3, down 0.6 points"), "8.3")

    def test_range_is_never_halved(self):
        self.assertEqual(K.key_figure("The nearest supermarket is 35 to 50 minutes each way"), "35 to 50 min")
        self.assertEqual(K.key_figure("Expected first year: 450 to 550 additional households"), "450 to 550")

    def test_label_count_and_plain_lead(self):
        self.assertEqual(K.key_figure("Waitlist at the end of FY2026: 31 people"), "31")
        self.assertEqual(K.key_figure("Apprentices enrolled: 26 (up from 18 in FY2025)"), "26")
        self.assertEqual(K.key_figure("14 of 19 graduates were working within 90 days (74%)"), "14")

    def test_figures_row_uses_it(self):
        figs, _cap = K._figure_rows(["Apprentices enrolled: 26 (up from 18)", "Completed all 16 weeks: 19 (73%)",
                                     "Bikes refurbished: 482 (up from 310)"])
        self.assertEqual([v for _i, v, _l in figs], ["26", "19", "482"])


def _doc(slides):
    return {"title": "Sample", "subtitle": "", "plain": True, "slides": [
        {"type": "content", "heading": h, "refs": ["P1"], "bullets": [{"text": t, "ref": "P1"} for t in lines]} for h, lines in slides]}


class Headlines(unittest.TestCase):
    def test_topic_titles(self):
        for t in ("Who We Are", "Why an Evening Cohort", "The Eastern Route", "FY2026 Results (July 1, 2025 to June 30, 2026)"):
            self.assertTrue(K.is_topic_title(t), t)
        for t in ("Our Ask: $95,000 for the Eastern Route", "Distance Is a Health Barrier"):
            self.assertFalse(K.is_topic_title(t), t)

    def test_headline_is_a_draft_line_and_title_stays(self):
        lines = ["Waitlist at the end of FY2026: 31 people", "22 of them can only attend in the evening",
                 "Total enrollment would grow from 26 to 36 apprentices"]
        d = K.shape_plain(_doc([("Why an Evening Cohort", lines)]))
        sl = d["slides"][0]
        self.assertEqual(sl["heading"], "Why an Evening Cohort")
        self.assertEqual(sl["headline"], "Total enrollment would grow from 26 to 36 apprentices")
        self.assertIn(sl["headline"], lines)
        self.assertIn(("slides.0.headline", sl["headline"], ["P1"]), K.field_texts(d))
        # loop 3 fix 3: the headline's line leaves the body (its words are the headline), the other two stay as figures
        self.assertNotIn(sl["headline"], sl["lines"])
        self.assertEqual([f["value"] for f in sl["figures"]], ["31", "22"])

    def test_money_slide_states_the_gap(self):
        lines = ["Instructor: $52,000", "Stipends: $30,000", "Total cost: $96,000", "Committed by the county: $36,000",
                 "Remaining gap, our request: $60,000"]
        sl = K.shape_plain(_doc([("What the Cohort Costs", lines)]))["slides"][0]
        self.assertEqual(sl["headline"], "Remaining gap, our request: $60,000")

    def test_spec_gets_eyebrow(self):
        d = K.shape_plain(_doc([("The Route", ["Five stops start in January", "29 households already drive to our stops"])]))
        specs = RD.slides(d, {"rules": {}}, {}, [], "", {})
        self.assertEqual(specs[1]["eyebrow"], "The Route")
        self.assertEqual(specs[1]["head"], d["slides"][0]["headline"])


class QuotesAndLists(unittest.TestCase):
    def test_quote_with_takeaway_is_a_quote(self):
        sl = K.shape_plain(_doc([("In a Customer's Words", ['"The truck comes every Tuesday now."', "Sample D., Elm stop",
                                                            "A fixed weekly stop makes a habit"])]))["slides"][0]
        self.assertEqual(sl["type"], "quote")
        self.assertEqual(sl["note"], "A fixed weekly stop makes a habit")
        self.assertNotIn("headline", sl)

    def test_attribution_before_the_quote(self):
        sl = K.shape_plain(_doc([("In a Graduate's Words", ["Sample M., spring cohort", '"I learned to look at a problem."'])]))["slides"][0]
        self.assertEqual((sl["type"], sl["who"], sl["quote"]), ("quote", "Sample M., spring cohort", "I learned to look at a problem."))

    def test_long_list_splits_by_kind(self):
        lines = ["Adults with a sample condition", "Vouchers and a monthly check-in", "Six months of visits",
                 "Most kept their visits", "Caveat: there was no comparison group", "Dropouts are not counted",
                 "This is an early signal, not proof"]
        sl = K.shape_plain(_doc([("Sample Pilot", lines)]))["slides"][0]
        self.assertEqual((sl.get("comp"), sl.get("split")), ("open", 4))


class Sources(unittest.TestCase):
    def test_internal_notes_never_on_the_face(self):
        p = {"P1": {"source_title": "Report", "locator": "para. 2"}, "P2": {"source_title": "Notes", "locator": "para. 3"}}
        d = {"title": "Sample", "slides": [{"type": "content", "heading": "Sample results", "refs": ["P1", "P2"],
                                            "bullets": [{"text": "a", "ref": "P1"}, {"text": "b", "ref": "P2"}]}]}
        sp = RD.slides(d, {"rules": {"sources": True}}, {}, [], "", p)[1]
        self.assertNotIn("Notes", sp["src"] + sp["src_short"])
        self.assertIn("Report", sp["src"])
        self.assertIn("Notes, para. 3", RD.notes_for(d, p)[1])


if __name__ == "__main__":
    unittest.main()
