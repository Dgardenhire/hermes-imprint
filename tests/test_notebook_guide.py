"""The notebook guide on the Harborlight sources: both asks, a likely question on reserves against the budget
rise, and nothing shown that does not cite a passage the model was shown."""
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, ROOT, fake_model, jobs, reset, service

NG = import_module(f"{PKG}.notebook_guide")
DENISE = ROOT / "harness" / "live" / "personas" / "denise"


def harborlight():
    reset()
    rows = [service.read_file(n, (DENISE / n).read_bytes()) for n in ("FY26-Program-Report.docx", "board-retreat-notes.txt")]
    _srcs, _b, by_ref = service.passages_for([r["id"] for r in rows])
    find = lambda phrase: next(r for r, p in by_ref.items() if phrase in p["text"])
    return [r["id"] for r in rows], by_ref, find


def scripted(find):
    """What a good model returns, with refs found by phrase (the ids depend on the data folder)."""
    p_served, p_wait, p_money, p_rec, p_board = (find("enrolled 1,148"), find("287 adults"), find("Operating expenses"),
                                                 find("approve an FY2027 budget"), find("reserves stand at 3.2"))
    return {
        "guide": [{"text": "Harborlight enrolled 1,148 adult learners in FY2026, up from 936 the year before.", "refs": [p_served]},
                  {"text": "Another 287 adults ended the year on the waitlist.", "refs": [p_wait]},
                  {"text": "Staff propose a $1,610,000 budget for FY2027 that adds a sixth site.", "refs": [p_rec]}],
        "asks": [{"who": "The board", "what": "A one-page summary of the FY2027 budget request", "by": "October 21", "kind": "onepager",
                  "refs": [p_board], "brief": {"who": "Board members", "goal": "Vote on the FY2027 budget", "length": "One page"}},
                 {"who": "Board members", "what": "A short deck for funders about the sixth site", "by": "", "kind": "deck",
                  "refs": [p_board], "brief": {"who": "Funders", "goal": "Fund the sixth site", "length": "About 8 slides"}}],
        "questions": [{"text": "Reserves stand at 3.2 months against a 4-month target. Can Harborlight add a site while the budget rises $190,000?",
                       "refs": [p_board, p_rec, p_money]},
                      {"text": "Would 180 more seats a year be enough for a waitlist of 287?", "refs": [p_rec, p_wait]}],
    }


class Job(unittest.TestCase):
    def test_harborlight_guide_asks_and_questions(self):
        ids, by_ref, find = harborlight()
        llm = fake_model()
        llm.queue.append(scripted(find))
        j = jobs.start("notebook_guide", "t:ng", {"source_ids": ids}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "done", j["error"])
        r = j["result"]
        self.assertEqual(r["by"], "Written by your Hermes model")
        self.assertEqual(len(r["guide"]), 3)
        self.assertEqual(len(r["asks"]), 2)
        for a in r["asks"]:
            self.assertEqual(a["chips"][0]["source"], "Board retreat notes")
            self.assertEqual(a["chips"][0]["source_n"], 2)
        self.assertEqual([a["kind"] for a in r["asks"]], ["onepager", "deck"])
        self.assertEqual(r["asks"][0]["by"], "October 21")
        q = r["questions"][0]["text"]
        for want in ("3.2 months", "4-month", "$190,000"):
            self.assertIn(want, q)
        self.assertTrue(all(x["suggestion"] for x in r["questions"]))
        self.assertEqual(NG.last()["asks"][1]["what"], "A short deck for funders about the sixth site")
        call = llm.calls[-1]
        self.assertEqual(call["purpose"], "letterpress.notebook_guide")
        self.assertIs(call["json_schema"], NG.SCHEMA)

    def test_a_reply_with_nothing_usable_fails_with_retry(self):
        ids, _by_ref, _find = harborlight()
        llm = fake_model()
        llm.queue += [{"guide": [{"text": "Something.", "refs": ["P999"]}], "asks": [], "questions": []}] * 2
        j = jobs.start("notebook_guide", "t:ng2", {"source_ids": ids}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "failed")
        self.assertIn("Retry", j["error"] + " Retry")


class Clean(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.shown = set(self.by_ref)

    def clean(self, raw):
        return NG.clean(raw, self.by_ref, self.shown, self.ids)

    def test_an_ask_without_a_valid_ref_is_dropped(self):
        raw = scripted(self.find)
        raw["asks"][0]["refs"] = ["P999"]
        got = self.clean(raw)
        self.assertEqual([a["what"] for a in got["asks"]], ["A short deck for funders about the sixth site"])

    def test_an_ask_citing_a_passage_with_no_request_is_dropped(self):
        raw = scripted(self.find)
        raw["asks"][1]["refs"] = [self.find("287 adults")]
        self.assertEqual(len(self.clean(raw)["asks"]), 1)

    def test_a_ref_the_model_was_not_shown_is_dropped(self):
        raw = scripted(self.find)
        p_board = self.find("reserves stand at 3.2")
        got = NG.clean(raw, self.by_ref, self.shown - {p_board}, self.ids)
        self.assertEqual(got["asks"], [])

    def test_a_sentence_with_an_invented_number_is_dropped(self):
        raw = scripted(self.find)
        raw["guide"][1]["text"] = "Another 312 adults ended the year on the waitlist."
        texts = [g["text"] for g in self.clean(raw)["guide"]]
        self.assertNotIn("Another 312 adults ended the year on the waitlist.", texts)
        self.assertEqual(len(texts), 2)

    def test_a_worked_out_number_needs_both_passages_cited(self):
        raw = scripted(self.find)
        raw["questions"][0]["refs"] = [self.find("reserves stand at 3.2"), self.find("approve an FY2027 budget")]
        texts = [q["text"] for q in self.clean(raw)["questions"]]
        self.assertFalse(any("$190,000" in t for t in texts))

    def test_dates_in_a_sentence_are_not_checked_as_numbers(self):
        raw = scripted(self.find)
        raw["guide"].append({"text": "The board votes on October 21.", "refs": [self.find("reserves stand at 3.2")]})
        self.assertIn("The board votes on October 21.", [g["text"] for g in self.clean(raw)["guide"]])


if __name__ == "__main__":
    unittest.main()
