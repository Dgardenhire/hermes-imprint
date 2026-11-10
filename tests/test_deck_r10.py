"""Round 10 (third panel, critics 7, 8, 9): Fix it for me keeps the hedge ("staff estimate") and names the same source
as the flag; the cover's big figure is traced; one four-up grid per deck; graphic options lead with the question."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, kits, service
from test_revise import KIT, finish, harborlight

CK = import_module(f"{PKG}.checks")


def estimate_deck(find):
    served, wait, rec = find("enrolled 1,148"), find("287 adults"), find("approve an FY2027")
    return {"title": "A sixth site for Harborlight", "subtitle": "For funders", "slides": [
        {"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "", "refs": [wait]},
        {"type": "content", "heading": "Staff estimate 1,200 more learners a year", "refs": [rec], "bullets": [
            {"text": "The sixth site sits at the Eastgate branch library", "ref": rec},
            {"text": "It adds two site coordinators", "ref": rec}]},
        {"type": "closing", "heading": "Fund the sixth site", "text": "Every new seat shortens the wait.", "cta": "Talk with us", "refs": [served]},
    ]}


class FixKeepsTheHedge(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()
        self.llm.deck = lambda ps: estimate_deck(self.find)
        j = jobs.start("make", "t:r10", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT], "brief": "A deck for funders"}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "done", j["error"])
        self.oid = j["result"]["output_id"]
        live = service._doc_for(self.oid, kits.get(KIT))
        g = CK.grounding(live, service.passages_for(self.ids)[2])
        self.item = next(i for i in g["missing"] if i["value"] == "1200")

    def test_unit_hedges(self):
        p = self.by_ref[self.find("approve an FY2027")]["text"]
        self.assertEqual(CK.hedges_dropped("Staff estimate 1,200 more learners a year", "180 more learners in one year", p),
                         ["estimate", "plan"])  # neither of the source's hedges kept
        self.assertEqual(CK.hedges_dropped("Staff estimate 1,200 more learners a year", "Staff estimate the site would serve 180 more learners a year", p), [])
        self.assertEqual(CK.hedges_dropped("About 300 adults waited", "287 adults were on the waitlist", ""), ["about"])
        self.assertEqual(CK.hedges_dropped("287 adults waited", "287 adults were on the waitlist", ""), [])
        self.assertEqual(CK.hedges_in("The vote is in May"), set())  # the month is not a hedge

    def test_a_fix_that_drops_the_estimate_is_asked_again_then_kept(self):
        self.llm.queue.append({"text": "180 more learners in one year"})
        self.llm.queue.append({"text": "Staff estimate 180 more learners a year"})
        n = len(self.llm.calls)
        r = finish("fix_it", {"output_id": self.oid, "kit_id": KIT, "key": self.item["key"]})["result"]
        self.assertEqual(len(self.llm.calls) - n, 2)
        self.assertIn("KEEP THESE WORDS", self.llm.calls[-1]["input"][0]["text"])
        self.assertEqual(r["status"], "ok", r["check"])
        self.assertIn("estimate", r["after"].lower())
        self.assertIn("180", r["after"])

    def test_a_fix_that_drops_it_twice_changes_nothing(self):
        self.llm.queue.append({"text": "180 more learners in one year"})
        self.llm.queue.append({"text": "180 more learners each year"})
        r = finish("fix_it", {"output_id": self.oid, "kit_id": KIT, "key": self.item["key"]})["result"]
        self.assertEqual(r["status"], "unchanged")
        self.assertEqual(r["after"], r["before"])
        self.assertIn("estimate", r["check"]["label"])

    def test_the_flag_and_the_fix_name_the_same_source(self):
        self.llm.queue.append({"text": "Staff estimate 180 more learners a year"})
        r = finish("fix_it", {"output_id": self.oid, "kit_id": KIT, "key": self.item["key"]})["result"]
        self.assertEqual(r["source_ref"], self.item["closest"]["ref"])
        self.assertEqual(r["source_ref"], self.find("approve an FY2027"))
        self.assertEqual(r["chips"][0]["locator"].strip("“”"), "Recommendation to the board")


if __name__ == "__main__":
    unittest.main()


class CoverInTheReverseTrace(unittest.TestCase):
    def test_the_cover_287_lights_with_the_slides_that_cite_the_waitlist(self):
        from test_revise import deck, made
        ids, by_ref, find = harborlight()
        llm = fake_model()
        d = deck(find)
        d["slides"][0]["bars"][2]["accent"] = True
        llm.deck = lambda ps: d
        j = jobs.start("make", "t:r10-cover", {"kind": "deck", "source_ids": ids, "kit_ids": [KIT], "brief": "A deck for funders"}, wait=True)
        oid = jobs.get(j["id"])["result"]["output_id"]
        pr = service.proof(oid, KIT)
        wait = find("287 adults")
        c287 = [cid for cid, c in pr["claims"].items() if c["value"] == "287"]
        self.assertTrue(c287)
        self.assertIn(0, pr["claims"][c287[0]]["slides"])
        self.assertIn(c287[0], pr["slides"][0]["claims"])  # the cover row carries the claim the reverse trace reads
        self.assertIn(0, pr["passages_used"][wait]["slides"])


class GraphicOptionsAnswerTheQuestion(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()

    def opts(self):
        served, rec, res = self.find("enrolled 1,148"), self.find("approve an FY2027"), self.find("reserves stand")
        grants = {"headline": "Enrollment grew in one year", "form": "compare", "takeaway": "More adults came.",
                  "items": [{"label": "FY2025", "value": "936", "ref": served}, {"label": "FY2026", "value": "1,148", "ref": served}]}
        reserves = {"headline": "Reserves sit below target as the budget rises", "form": "figures", "takeaway": "The rise needs care.",
                    "items": [{"label": "Reserves, months", "value": "3.2 months", "ref": res},
                              {"label": "FY2027 budget", "value": "$1,610,000", "ref": rec}]}
        return grants, reserves

    def test_the_option_that_answers_the_pinned_question_comes_first(self):
        grants, reserves = self.opts()
        self.llm.queue.append({"options": [grants, reserves]})
        note = "Reserves stand at 3.2 months against a 4-month target while the budget rises to $1,610,000."
        j = finish("graphic_options", {"source_ids": self.ids, "text": note, "question": "Can our reserves carry the budget rise?"})
        self.assertEqual(j["status"], "done", j["error"])
        self.assertEqual([o["form"] for o in j["result"]["options"]], ["figures", "compare"])
        self.assertIn("THE QUESTION", self.llm.calls[-1]["input"][0]["text"])

    def test_a_timeline_may_not_invent_an_order(self):
        grants, _r = self.opts()
        wait, rec = self.find("287 adults"), self.find("approve an FY2027")
        tl = {"headline": "The waitlist grew as the vote neared", "form": "timeline", "takeaway": "Time matters.",
              "steps": [{"when": "Year end", "text": "287 adults were on the waitlist before the vote", "ref": wait},
                        {"when": "FY2027", "text": "Staff recommend a budget of $1,610,000", "ref": rec}]}
        self.llm.queue.append({"options": [tl, grants]})
        j = finish("graphic_options", {"source_ids": self.ids, "text": "287 adults are waiting."})
        self.assertEqual([o["form"] for o in j["result"]["options"]], ["compare"])
        self.assertEqual(j["result"]["dropped"], 1)
