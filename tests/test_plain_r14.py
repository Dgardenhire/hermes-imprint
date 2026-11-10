"""Round 14: the plain draft's numbers set as exhibits in code (bars, a figures grid, money in parts, a quote slide),
every draft line kept; the split rule fires on measured height; a share worked out on its own slide is never flagged."""
import unittest
from importlib import import_module

from _load import PKG, kits
from test_revise import KIT

K = import_module(f"{PKG}.content")
RD = import_module(f"{PKG}.render_deck")

DRAFT = """Slide 1: Sample Roof Repair
A proposal

Slide 2: Falls: what homeowners told us
12-month follow-up calls for homes completed in FY2025
Before repairs: 19 of 52 reported a fall in the prior year (37%)
After repairs: 7 of 52 reported a fall in the following year (13%)
Caveats:
Self-reported: people may forget or not mention a fall

Slide 3: The ask: $115,000
Second-crew cost: $230,000
Lead gift: $115,000 (50%)
County: $60,000 (pending the commissioners' budget vote)
Donors: $55,000
Without the lead gift: we hire only the tradesperson

Slide 4: FY2026 results
84 homes served, against a goal of 80
412 repair jobs completed
131 safety installations
1,930 volunteer hours
Our walk-through found problems in 61 of 84 homes

Slide 5: Loretta, 81
"I do my own laundry again."

Slide 6: The ask, in parts
Budget: $68,500
Artists: $44,000
Van: $9,600
Show: $8,900
Evaluation: $6,000
In hand: $23,500
Fees: $12,000
Arts council: $11,500
Remaining gap: $45,000
"""


class Shape(unittest.TestCase):
    def setUp(self):
        self.slides = K.parse_plain(DRAFT)
        self.doc = K.shape_plain(K.plain_doc(self.slides, {}))

    def test_every_draft_line_is_kept(self):
        lines = K.shaped_lines(self.doc)
        for s in self.slides:
            for t in [s["title"]] + s["lines"]:
                self.assertTrue(any(t in x or x in t for x in lines), t)

    def test_before_after_shares_are_bars_and_the_rest_continues(self):
        ex = [s for s in self.doc["slides"] if s["type"] == "exhibit" and s["heading"].startswith("Falls")][0]
        self.assertEqual([b["value"] for b in ex["bars"]], ["37%", "13%"])
        self.assertEqual(ex["subhead"], "12-month follow-up calls for homes completed in FY2025")
        # round 15: the lines after the bars sit under them as the note, never on a "(continued)" slide
        self.assertEqual(ex["note"], "Caveats: Self-reported: people may forget or not mention a fall")
        self.assertFalse(any("(continued)" in (s.get("heading") or "") for s in self.doc["slides"]))

    def test_funding_mix_is_one_money_table(self):
        # round 16: a money list is one table (amount beside the line's own words), never bars or a numbered list
        t = [s for s in self.doc["slides"] if s.get("shape") == "money" and s["heading"] == "The ask: $115,000"][0]
        self.assertEqual([b.get("figure") for b in t["bullets"] if b.get("figure")][:3], ["$230,000", "$115,000", "$60,000"])
        self.assertIn("Without the lead gift: we hire only the tradesperson", [b["text"] for b in t["bullets"]])

    def test_number_led_lines_make_one_figures_grid(self):
        # round 15: four figures with more lines after them stay one slide (the grid has no room for the rest)
        res = [s for s in self.doc["slides"] if s.get("heading") == "FY2026 results"]
        self.assertEqual(len(res), 1)
        self.assertEqual(len(self.doc["slides"]), 5)

    def test_quote_line_is_a_quote_slide(self):
        q = [s for s in self.doc["slides"] if s["type"] == "quote"][0]
        self.assertEqual(q["quote"], "I do my own laundry again.")
        self.assertEqual(q["who"], "Loretta, 81")

    def test_money_in_parts_is_one_table(self):
        t = [s for s in self.doc["slides"] if s.get("shape") == "money" and s["heading"].startswith("The ask, in parts")]
        self.assertEqual(len(t), 1)  # one slide, every line kept
        self.assertEqual(t[0]["bullets"][0]["figure"], "$68,500")
        # loop 3 fix 3: the gap is the headline, so its line left the table (never lost: K.shaped_lines holds it)
        self.assertEqual(t[0].get("headline"), "Remaining gap: $45,000")
        self.assertNotIn("Remaining gap: $45,000", [b.get("line") for b in t[0]["bullets"]])
        self.assertIn("Remaining gap: $45,000", K.shaped_lines(self.doc))


class Share(unittest.TestCase):
    def test_a_part_over_a_total_on_the_slide_is_not_flagged(self):
        doc = {"title": "T", "subtitle": "", "slides": [{"type": "content", "heading": "The ask", "bullets": [
            {"text": "Second-crew cost: $230,000"}, {"text": "Lead gift: $115,000 (50%)"}, {"text": "Other: 31%"}]}]}
        passages = {"p1": {"text": "The second crew costs $230,000. We ask $115,000."}}
        items = [{"path": "slides.0.bullets.1", "kind": "number", "status": "missing", "shown": "50%", "value": "50%"},
                 {"path": "slides.0.bullets.2", "kind": "number", "status": "missing", "shown": "31%", "value": "31%"}]
        out, flags = K.flag_unsupported(doc, items, passages)
        self.assertEqual([f["was"] for f in flags], ["31%"])
        self.assertIn("(50%)", out["slides"][0]["bullets"][1]["text"])


class Overrun(unittest.TestCase):
    def test_text_past_the_foot_band_is_an_overrun(self):
        sc = {"h": 1080, "els": [{"t": "text", "y": 900, "bottom": 1050}, {"t": "text", "y": 1046, "bottom": 1060}]}
        self.assertTrue(RD.overruns(sc))
        sc["els"] = sc["els"][1:]
        self.assertFalse(RD.overruns(sc))


class EditedQuote(unittest.TestCase):
    def test_a_quote_close_to_a_source_sentence_takes_the_source_words(self):
        doc = {"title": "T", "subtitle": "", "slides": [{"type": "content", "heading": "In her words", "bullets": [
            {"text": "\u201cI can read my granddaughter her bedtime stories now.\u201d"}, {"text": "\u201cThe moon sang me home.\u201d"}]}]}
        passages = {"p1": {"text": "Sample. She said: \u201cNow I can read my granddaughter her bedtime story.\u201d"}}
        items = [{"path": "slides.0.bullets.0", "kind": "quote", "status": "missing", "shown": "I can read my granddaughter her bedtime stories now."},
                 {"path": "slides.0.bullets.1", "kind": "quote", "status": "missing", "shown": "The moon sang me home."}]
        out, flags = K.flag_unsupported(doc, items, passages)
        self.assertEqual(out["slides"][0]["bullets"][0]["text"], "\u201cNow I can read my granddaughter her bedtime story.\u201d")
        self.assertEqual([f["was"] for f in flags], ["The moon sang me home."])


if __name__ == "__main__":
    unittest.main()


class FigureRows(unittest.TestCase):
    def test_lines_with_numbers_become_a_figures_row_and_two_shares_read_across(self):
        figs, cap = K._figure_rows(["In FY2026 we turned down 11 performance requests", "September: 41 percent agreed. May: 74 percent agreed.",
                                    "The reason we said no: one van and one touring cast"])
        self.assertEqual([v for _i, v, _l in figs], ["11", "41% → 74%"])
        self.assertEqual(cap, ["The reason we said no: one van and one touring cast"])  # words unchanged, set as the caption

    def test_an_address_line_is_never_a_figure(self):
        self.assertIsNone(K._figure_rows(["Kettle Lane | The Granary, 2nd Floor", "Plain words only"]))
