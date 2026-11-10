"""Round 8: a number written as a word is a claim, checked and traced like a figure ("Nine weeks: the average wait for
a seat" matches "The average wait was nine weeks"); ordinary words ("one of the sites") are never claims."""
import unittest

from _load import checks as CK, content as K, layout as L

P = {
    "P4": {"text": "At year end, 287 adults were on the waitlist, most of them at the Eastgate and Riverside sites. "
                   "The average wait was nine weeks.", "locator": "The waitlist", "source_id": "s1",
           "source_title": "FY26 Program Report"},
    "P5": {"text": "Staff estimate a sixth site would serve 180 more learners a year and cut the waitlist in half.",
           "locator": "Recommendation to the board", "source_id": "s1", "source_title": "FY26 Program Report"},
}


def deck(heading, bullets=(), refs=("P4",)):
    return {"title": "", "subtitle": "", "slides": [{"type": "content", "heading": heading, "refs": list(refs),
                                                       "bullets": [{"text": b, "ref": refs[0]} for b in bullets]}]}


class Rule(unittest.TestCase):
    def test_claims_and_ordinary_words(self):
        got = lambda t: [(r, v) for r, v, _a, _b in K.claim_spans(t)]
        self.assertEqual(got("Nine weeks: the average wait for a seat"), [("Nine", "9")])
        self.assertEqual(got("Seventy-one learners finished"), [("Seventy-one", "71")])
        self.assertEqual(got("sixty-eight percent stayed"), [("sixty-eight percent", "68%")])
        self.assertEqual(got("cut the waitlist in half"), [("half", "1/2")])
        self.assertEqual(got("twice as many adults"), [("twice", "2x")])
        self.assertEqual(got("a nine-week wait"), [("nine", "9")])
        for plain in ("one of the sites", "no one waited", "in the second half of the year", "a third site",
                      "three things to remember", "the season in four numbers", "a two-page summary", "one year",
                      "Eastgate is one of two sites", "The first two bars show enrollment"):
            self.assertEqual(got(plain), [], plain)
        self.assertEqual(got("1,148 learners waited nine weeks"), [("1,148", "1148"), ("nine", "9")])


class Checked(unittest.TestCase):
    def test_nine_weeks_matches_its_source_and_is_traced(self):
        d = deck("Nine weeks: the average wait for a seat")
        g = CK.grounding(d, P)
        nums = [i for i in g["items"] if i["kind"] == "number"]
        self.assertEqual([(i["shown"], i["status"], i["ref"]) for i in nums], [("Nine", "ok", "P4")])
        claims, _used, claim_of = CK.claims_map(g["items"], P, {"P4": 1, "P5": 1})
        self.assertEqual([c["status"] for c in claims.values()], ["exact"])
        self.assertEqual(list(claims.values())[0]["line"]["match"], "nine")
        self.assertTrue(claim_of("slides.0.heading", "Nine"))
        traces, resolve = CK.trace_table(g["items"], P, {"P4": 1})
        tree = L.mark_traces({"t": "h2", "x": "Nine weeks: the average wait for a seat"}, resolve)
        spans = [k for k in tree.get("k") or [] if "ip-num" in (k.get("c") or "")]
        self.assertEqual([s["x"] for s in spans], ["Nine"])

    def test_a_spelled_number_no_source_holds_is_flagged(self):
        g = CK.grounding(deck("Twelve weeks: the average wait for a seat"), P)
        self.assertEqual([(i["shown"], i["status"]) for i in g["missing"]], [("Twelve", "missing")])

    def test_a_word_count_in_prose_is_never_flagged(self):
        g = CK.grounding(deck("The waitlist is long", bullets=("Two problems need attention",)), P)
        self.assertEqual(g["missing"], [])
        g2 = CK.grounding(deck("The waitlist is long", bullets=("Two problems need attention", "Eleven weeks is the wait")), P)
        self.assertEqual(g2["missing"], [])  # body prose: never flagged

    def test_ordinary_one_is_not_checked(self):
        g = CK.grounding(deck("Riverside is one of the sites with a waitlist"), P)
        self.assertEqual([i for i in g["items"] if i["kind"] == "number"], [])

    def test_half_matches_in_half_and_fifty_percent(self):
        g = CK.grounding(deck("A sixth site would cut the waitlist in half", refs=("P5",)), P)
        self.assertEqual([(i["shown"], i["status"]) for i in g["items"] if i["kind"] == "number"], [("half", "ok")])
        p = {"P9": {"text": "Half of the learners stayed.", "locator": "", "source_id": "s", "source_title": "S"}}
        self.assertTrue(CK.find_number("1/2", p, ["P9"]))
        p2 = {"P9": {"text": "50% of the learners stayed.", "locator": "", "source_id": "s", "source_title": "S"}}
        self.assertTrue(CK.check_line("Half of the learners stayed", ["P9"], p2)["ok"])

    def test_check_line_reads_words(self):
        self.assertTrue(CK.check_line("The average wait was nine weeks", ["P4"], P)["ok"])
        # In prose a word number the sources don't hold is a plain count, not a claim: never flagged (Loop 2 S18:
        # "Two problems need attention" was flagged in an audio brief). Headlines and figures still flag it.
        self.assertTrue(CK.check_line("The average wait was eleven weeks", ["P4"], P)["ok"])

    def test_stamp_counts_the_word(self):
        from _load import service
        g = CK.grounding(deck("Nine weeks: the average wait for a seat"), P)
        claims, _u, _c = CK.claims_map(g["items"], P, {"P4": 1})
        self.assertEqual(service.stamp(claims), "The 1 number matches your sources.")


if __name__ == "__main__":
    unittest.main()


class Filler(unittest.TestCase):
    """Round 8: a point that says the title again is named, and a list of them is rebuilt as figures."""
    def test_restating_points_are_found_and_the_slide_is_rebuilt(self):
        d = deck("Most adults on the waitlist are at the Eastgate and Riverside sites",
                 ["Most adults on the waitlist wait at Eastgate or Riverside", "The average wait for a seat was nine weeks",
                  "Adults were still on the waitlist at year end"])
        f = CK.filler(d, P)
        self.assertEqual(len(f), 1)
        self.assertTrue(f[0]["rebuild"])
        self.assertIn("Most adults on the waitlist wait at Eastgate or Riverside", f[0]["restating"])
        self.assertNotIn("The average wait for a seat was nine weeks", f[0]["restating"])
        # P4 holds two numbers, so the slide becomes one big number, not a padded row of figures
        self.assertEqual(f[0]["as"], "stat")
        self.assertIn("Rebuild it as one big number", K.repair_instructions({"filler": f}))
        self.assertIn("Rebuild it as a figures slide", K.repair_instructions({"filler": [{**f[0], "as": "figures"}]}))
        self.assertEqual(CK.problem_count({"filler": f}), 1)

    def test_points_that_add_facts_are_not_filler(self):
        d = deck("Staff estimate a sixth site would serve 180 more learners a year",
                 ["The sixth site would open at the Eastgate branch library", "Staff estimate the new site would cut the waitlist in half"],
                 refs=("P5",))
        self.assertEqual(CK.filler(d, P), [])


class Figures(unittest.TestCase):
    def test_two_figures_slides_never_share_the_four_up(self):
        from _load import render_deck as RD
        fig = lambda h: {"type": "figures", "heading": h, "refs": ["P4"], "figures": [
            {"value": "287", "label": "Adults waiting", "context": "At year end", "ref": "P4"},
            {"value": "nine weeks", "label": "Average wait", "context": "", "ref": "P4"},
            {"value": "180", "label": "More learners a year", "context": "Staff estimate", "ref": "P5"}]}
        doc = {"title": "t", "slides": [fig("One"), {"type": "quote", "quote": "q", "who": "w", "refs": ["P4"]}, fig("Two"), fig("Three")]}
        kinds = [s["kind"] for s in RD.slides(doc, {"rules": {"sources": True}}, {}, [], "", P)]
        self.assertEqual(kinds, ["title", "figures", "quote", "ledger", "ledger"])  # round 10: one four-up per deck
        led = RD.slides(doc, {"rules": {}}, {}, [], "", P)[3]
        self.assertEqual(led["figs"], ["287", "nine weeks", "180"])
        self.assertEqual(led["items"][0][0], "Adults waiting: at year end")
        self.assertEqual(RD._ledger_line("Average time a tutor stayed", "Tutors stay with learners over time"),
                         "Average time a tutor stayed")
