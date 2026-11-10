"""P6 round 3: money figures shown (not only cited), a number set big once, relation words kept, one claim per
title, points that all lead with a figure or none do, and the repair the make job runs before the voice pass."""

import unittest

from importlib import import_module

import _load  # noqa: F401  (loads the package on a temp data folder)

PKG = _load.PKG
CK = import_module(f"{PKG}.checks")
K = import_module(f"{PKG}.content")
RD = import_module(f"{PKG}.render_deck")

PASS = {
    "P2": {"text": "A corps of 214 volunteer tutors gave 9,870 tutoring hours. The average tutor stayed 14 months.",
           "locator": "Volunteers", "source_title": "FY26 Program Report (Sample)"},
    "P3": {"text": "Foundation grants provided $640,000, individual donors gave $388,000, and the city paid $295,000.",
           "locator": "Money", "source_title": "FY26 Program Report (Sample)"},
    "P4": {"text": "At year end, 287 adults were on the waitlist, most of them at the Eastgate and Riverside sites.",
           "locator": "The waitlist", "source_title": "FY26 Program Report (Sample)"},
    "P5": {"text": "Staff estimate the sixth site would serve 180 more learners a year.", "locator": "Plan",
           "source_title": "FY26 Program Report (Sample)"},
}


def deck(*slides):
    return {"title": "A sixth site", "subtitle": "For funders", "slides": list(slides)}


class Money(unittest.TestCase):
    def test_a_cited_passage_still_needs_its_figures_shown(self):
        d = deck({"type": "closing", "heading": "Fund it", "text": "Grants gave $640,000.", "refs": ["P3"]})
        left = CK.money_not_shown(d, PASS)
        self.assertEqual(left[0]["ref"], "P3")
        self.assertEqual(left[0]["missing"], ["$388,000", "$295,000"])
        self.assertIn("$388,000", CK.pill_money_shown(left)["label"])

    def test_all_figures_shown_passes(self):
        d = deck({"type": "exhibit", "heading": "Who pays", "refs": ["P3"],
                  "bars": [{"label": "Grants", "value": "$640,000", "ref": "P3"}, {"label": "Donors", "value": "$388,000", "ref": "P3"},
                           {"label": "City", "value": "$295,000", "ref": "P3"}]})
        self.assertEqual(CK.money_not_shown(d, PASS), [])


    def test_a_price_list_is_not_a_budget(self):
        menu = {"M1": {"text": "Boxed lunches are $16 per person; trays are $24 per person.", "locator": "Menu", "source_title": "Menu (Sample)"}}
        d = deck({"type": "closing", "heading": "Fund it", "text": "Help", "refs": ["M1"]})
        self.assertEqual(CK.money_not_shown(d, menu), [])


class Repeats(unittest.TestCase):
    def test_a_number_set_big_twice_is_found_and_the_cover_counts(self):
        d = deck({"type": "exhibit", "heading": "Need is outgrowing our capacity as 287 adults wait", "refs": ["P4"],
                  "bars": [{"label": "Waiting", "value": "287", "ref": "P4", "accent": True}, {"label": "Seats", "value": "200", "ref": "P4"}]},
                 {"type": "figures", "heading": "The corps", "refs": ["P2"],
                  "figures": [{"value": "214", "label": "tutors", "ref": "P2"}, {"value": "9,870", "label": "hours", "ref": "P2"},
                              {"value": "14 months", "label": "average stay", "ref": "P2"}, {"value": "287", "label": "waiting", "ref": "P4"}]},
                 {"type": "content", "heading": "214 tutors give the hours", "refs": ["P2"],
                  "bullets": [{"text": "Tutors", "figure": "214", "ref": "P2"}, {"text": "Hours", "figure": "9,870", "ref": "P2"}]})
        hits = {h["number"]: h for h in CK.repeats(d)}
        self.assertEqual(hits["287"]["first"], "cover")
        self.assertIn("slides.0.heading", hits["287"]["again"])
        self.assertIn("slides.2.heading", hits["214"]["again"])
        fixed = CK.trim_repeats(d)
        self.assertEqual([f["value"] for f in fixed["slides"][1]["figures"]], ["214", "9,870", "14 months"])

    def test_a_year_is_not_a_repeat(self):
        d = deck({"type": "figures", "heading": "In 2026", "refs": ["P2"], "figures": []},
                 {"type": "content", "heading": "Plans for 2026", "refs": ["P2"], "bullets": [{"text": "x", "ref": "P2"}]})
        self.assertEqual(CK.repeats(d), [])

    def test_cover_only_from_the_opening_exhibit(self):
        d = deck({"type": "figures", "heading": "The corps", "refs": ["P2"],
                  "figures": [{"value": "214", "label": "tutors", "ref": "P2"}, {"value": "9,870", "label": "hours", "ref": "P2"},
                              {"value": "14 months", "label": "average stay", "ref": "P2"}]})
        self.assertIsNone(RD.cover_figure(d, {}))


class Relation(unittest.TestCase):
    def test_drift_found(self):
        d = deck({"type": "figures", "heading": "The corps", "refs": ["P2"],
                  "figures": [{"value": "14 months", "label": "Time a tutor stays", "context": "Tutors stay over a year", "ref": "P2"},
                              {"value": "214", "label": "tutors", "ref": "P2"}, {"value": "9,870", "label": "hours", "ref": "P2"}]},
                 {"type": "content", "heading": "The waitlist", "refs": ["P4"],
                  "bullets": [{"text": "Most adults on the waitlist live near Eastgate", "ref": "P4"}]},
                 {"type": "closing", "heading": "A sixth site would serve 180 more learners", "text": "", "refs": ["P5"]})
        got = {(h["path"], h["word"]) for h in CK.drift(d, PASS)}
        self.assertIn(("slides.0.figures.0", "average"), got)
        self.assertIn(("slides.0.figures.0", "over a year"), got)
        self.assertIn(("slides.1.bullets.0", "live near"), got)
        self.assertIn(("slides.2.heading", "estimate"), got)

    def test_kept_relation_words_pass(self):
        d = deck({"type": "figures", "heading": "The corps", "refs": ["P2"],
                  "figures": [{"value": "14 months", "label": "Average time a tutor stayed", "ref": "P2"},
                              {"value": "214", "label": "tutors", "ref": "P2"}, {"value": "9,870", "label": "hours", "ref": "P2"}]},
                 {"type": "closing", "heading": "Staff estimate a sixth site would serve 180 more learners", "text": "", "refs": ["P5"]})
        self.assertEqual(CK.drift(d, PASS), [])

    def test_voice_may_not_add_a_relation(self):
        n = deck({"type": "content", "heading": "The waitlist", "refs": ["P4"],
                  "bullets": [{"text": "Most adults on the waitlist wait at Eastgate", "ref": "P4"},
                              {"text": "Riverside has a waitlist too", "ref": "P4"}, {"text": "Both sites are full", "ref": "P4"}]},
                 {"type": "closing", "heading": "Fund it", "text": "Help", "refs": ["P4"]},
                 {"type": "closing", "heading": "Fund it", "text": "Help", "refs": ["P4"]})
        v = K.clean_deck(n)
        v["slides"][0]["bullets"][0]["text"] = "Most adults on the waitlist live near Eastgate"
        merged, reverted = K.keep_facts(K.clean_deck(n), v)
        self.assertEqual(merged["slides"][0]["bullets"][0]["text"], "Most adults on the waitlist wait at Eastgate")
        self.assertIn("slides.0.bullets.0.text", reverted)


    def test_a_dropped_qualifier_goes_back_in(self):
        p = {"P1": {"text": "Sixty-eight percent of learners who stayed at least 12 weeks gained a level.", "locator": "x", "source_title": "y"}}
        d = deck({"type": "figures", "heading": "Learners who stayed 12 weeks gained a level", "refs": ["P1"], "figures": []})
        out, fixed = CK.keep_qualifiers(d, p)
        self.assertEqual(out["slides"][0]["heading"], "Learners who stayed at least 12 weeks gained a level")
        self.assertEqual(fixed, ["slides.0.heading"])


class Craft(unittest.TestCase):
    def test_one_claim_per_title(self):
        self.assertEqual(K.one_claim("Need is outgrowing our capacity as 287 adults wait for a seat"), "Need is outgrowing our capacity")
        self.assertEqual(K.one_claim("Grants, donors and the city fund a cost of $1,237 per learner"),
                         "Grants, donors and the city fund a cost of $1,237 per learner")

    def test_points_all_with_a_figure_or_none(self):
        d = K.clean_deck(deck({"type": "content", "heading": "The plan", "refs": ["P5"],
                               "bullets": [{"text": "More learners a year", "figure": "180", "ref": "P5"},
                                           {"text": "The site opens at the Eastgate library", "ref": "P5"},
                                           {"text": "Site coordinators", "figure": "2", "ref": "P5"}]},
                              {"type": "closing", "heading": "Fund it", "text": "Help", "refs": []},
                              {"type": "closing", "heading": "Fund it", "text": "Help", "refs": []}))
        b = d["slides"][0]["bullets"]
        self.assertFalse(any(x.get("figure") for x in b))
        self.assertEqual(b[0]["text"], "180 more learners a year")
        sp = RD.slides(d, {"rules": {}}, {}, [], "", PASS)
        self.assertEqual(sp[1]["kind"], "content")

    def test_problem_count_and_repair_prompt(self):
        d = deck({"type": "closing", "heading": "Fund it", "text": "Grants gave $640,000.", "refs": ["P3"]})
        p = CK.deck_problems(d, PASS)
        self.assertEqual(CK.problem_count(p), 2)
        txt = K.repair_instructions(p)
        self.assertIn("$388,000", txt)
        self.assertIn("same headings word for word", txt)


if __name__ == "__main__":
    unittest.main()
