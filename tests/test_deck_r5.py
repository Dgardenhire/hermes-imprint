"""Round 5: the outline is checked once more as its reader would (``review_outline``), and a built slide whose points
cite none of its title's passages is sent to the one repair call."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, store
from test_revise import harborlight

RV = import_module(f"{PKG}.revise")
CK = import_module(f"{PKG}.checks")
K = import_module(f"{PKG}.content")


def finish(kind, params):
    j = jobs.start(kind, f"t:{kind}:{store.now()}", params, wait=True)
    return jobs.get(j["id"])


class Review(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()
        f = self.find
        self.draft = {"slides": [
            {"title": "Enrollment grew by 212 adults in one year", "type": "exhibit", "refs": [f("enrolled 1,148")]},
            {"title": "Volunteers gave 9,870 hours of tutoring", "type": "stat", "refs": [f("214 volunteer")]},
            {"title": "A sixth site would serve 180 more learners a year", "type": "content", "refs": [f("approve an FY2027")]},
            {"title": "Fund the sixth site", "type": "closing", "refs": [f("approve an FY2027")]},
        ]}

    def test_the_review_revises_the_outline_and_says_what_changed(self):
        f = self.find
        rev = {"slides": self.draft["slides"][:3] + [
            {"title": "287 adults ended the year waiting for a seat", "type": "stat", "refs": [f("287 adults")]},
            {"title": "Fund the $190,000 increase for the sixth site", "type": "closing", "refs": [f("approve an FY2027"), f("Operating expenses")]}],
            "changes": [{"text": "Added the 287 adults on the waitlist", "refs": [f("287 adults")]},
                        {"text": "The closing now asks for the $190,000 increase", "refs": [f("approve an FY2027"), f("Operating expenses")]},
                        {"text": "Cut the 31% growth slide", "refs": [f("enrolled 1,148")]}]}
        self.llm.queue.extend([self.draft, rev])
        j = finish("outline", {"source_ids": self.ids, "brief": {"who": "Funders", "goal": "Fund the sixth site", "length": "7 to 9 slides"}})
        self.assertEqual(j["status"], "done", j["error"])
        o = j["result"]
        self.assertEqual(o["slides"][-1]["title"], "Fund the $190,000 increase for the sixth site")
        self.assertEqual(o["slides"][-1]["check"]["status"], "ok")
        texts = [r["text"] for r in o["review"]]
        self.assertEqual(texts[:2], ["Added the 287 adults on the waitlist", "The closing now asks for the $190,000 increase"])
        self.assertNotIn("Cut the 31% growth slide", texts)  # 31% is in no passage, so the note is not shown
        self.assertTrue(o["review"][0]["chips"])
        self.assertEqual(self.llm.calls[-1]["purpose"], "letterpress.outline_review")
        self.assertEqual(RV.get_outline(o["outline_id"])["review"], o["review"])

    def test_a_review_that_adds_an_unsourced_number_is_not_kept(self):
        f = self.find
        bad = {"slides": self.draft["slides"][:3] + [{"title": "Fund the $250,000 we need", "type": "closing", "refs": [f("approve an FY2027")]}],
               "changes": [{"text": "The closing now asks for $250,000", "refs": [f("approve an FY2027")]}]}
        self.llm.queue.extend([self.draft, bad])
        o = finish("outline", {"source_ids": self.ids, "brief": {}})["result"]
        self.assertEqual(o["slides"][-1]["title"], "Fund the sixth site")
        self.assertEqual(o["review"], [])

    def test_a_review_that_only_re_cites_a_slide_is_kept(self):
        f = self.find
        rev = {"slides": [dict(sl) for sl in self.draft["slides"]],
               "changes": [{"text": "The plan slide now cites the waitlist passage", "refs": [f("287 adults")]}]}
        rev["slides"][2] = {**rev["slides"][2], "refs": [f("approve an FY2027"), f("287 adults")]}
        self.llm.queue.extend([self.draft, rev])
        o = finish("outline", {"source_ids": self.ids, "brief": {}})["result"]
        self.assertIn(f("287 adults"), o["slides"][2]["refs"])
        self.assertEqual([r["text"] for r in o["review"]], ["The plan slide now cites the waitlist passage"])

    def test_an_unchanged_outline_has_no_review(self):
        self.llm.queue.extend([self.draft, {**self.draft, "changes": []}])
        o = finish("outline", {"source_ids": self.ids, "brief": {}})["result"]
        self.assertEqual(o["review"], [])
        self.assertEqual([s["title"] for s in o["slides"]], [s["title"] for s in self.draft["slides"]])


class Length(unittest.TestCase):
    def test_a_review_may_cut_to_the_briefs_shortest_length(self):
        eight = [{}] * 8
        self.assertEqual(RV.min_kept(eight, {"length": "7 to 9 slides"}), 6)
        self.assertEqual(RV.min_kept(eight, {}), 7)
        self.assertEqual(RV.min_kept([{}] * 4, {"length": "7 to 9 slides"}), 4)


class OffTitle(unittest.TestCase):
    OUT = {"slides": [{"title": "Three farms grow our produce", "type": "content", "refs": ["F1"]},
                      {"title": "Fund the kitchen", "type": "closing", "refs": ["F2"]}]}

    def test_points_that_cite_none_of_the_titles_passages_are_found(self):
        d = {"slides": [{"type": "content", "heading": "Three farms grow our produce", "refs": ["F1", "M1"],
                         "bullets": [{"text": "Squash soup", "ref": "M1"}, {"text": "Apple tart", "ref": "M1"}]},
                        {"type": "closing", "heading": "Fund the kitchen", "refs": ["F2"]}]}
        got = CK.off_title(d, self.OUT)
        self.assertEqual([(g["path"], g["want"], g["got"]) for g in got], [("slides.0", ["F1"], ["M1"])])
        self.assertIn("Rewrite its points from F1", K.repair_instructions({"off_title": got}))
        self.assertEqual(CK.problem_count({"off_title": got}), 1)

    def test_one_point_from_the_titles_passage_is_enough(self):
        d = {"slides": [{"type": "content", "heading": "Three farms grow our produce", "refs": ["F1"],
                         "bullets": [{"text": "Squash from Ridge Farm", "ref": "F1"}, {"text": "Apple tart", "ref": "M1"}]},
                        {"type": "closing", "heading": "Fund the kitchen", "refs": ["F2"]}]}
        self.assertEqual(CK.off_title(d, self.OUT), [])
        self.assertEqual(CK.off_title(d, None), [])


if __name__ == "__main__":
    unittest.main()
