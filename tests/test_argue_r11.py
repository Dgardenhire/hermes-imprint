"""Round 11: a deck is argued before it is laid out. One call drafts the case (lead, steps, the reader's objection
and the sources' answer, the ask, the notes' instructions); code checks it against the sources; one repair; then the
deck write takes it as a fixed spine (same steps, same order, the counter-case on its own slide)."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, store, service
from test_revise import KIT, deck, harborlight

CK = import_module(f"{PKG}.checks")
K = import_module(f"{PKG}.content")


def case(find, **over):
    served, wait, rec, tutors = find("enrolled 1,148"), find("287 adults"), find("approve an FY2027"), find("214 volunteer")
    a = {"reader": "Funders deciding on the sixth site.",
         "instructions": [],
         "lead": {"heading": "287 adults are waiting for a seat", "type": "exhibit",
                  "evidence": [{"text": "287 adults were on the waitlist at year end", "refs": [wait]},
                               {"text": "1,148 adults enrolled, up from 936", "refs": [served]}]},
         "points": [{"heading": "Volunteers already carry the work", "type": "stat",
                     "evidence": [{"text": "214 volunteer tutors", "refs": [tutors]}]},
                    {"heading": "Enrollment grew by 212 adults", "type": "content",
                     "evidence": [{"text": "212 more adults enrolled than the year before", "refs": [served]}]}],
         "counter": {"objection": "Can you afford a sixth site?", "heading": "The budget plan pays for the site", "type": "content",
                     "evidence": [{"text": "The FY2027 budget rises to $1,610,000", "refs": [rec]}]},
         "ask": {"heading": "Help open the sixth site", "amount": "$190,000 more a year", "buys": ["The sixth site"], "by_when": "",
                 "rest": "", "report": "", "refs": [find("Operating expenses for FY2026"), rec], "none_in_sources": False}}
    a.update(over)
    return a


class Argument(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()

    def test_a_true_case_has_no_faults_and_becomes_the_outline_in_order(self):
        a = case(self.find)
        self.assertEqual(CK.argument_problems(a, self.by_ref), [], CK.argument_problems(a, self.by_ref))
        o = K.argument_outline(a, "9 slides")
        self.assertEqual([s["title"] for s in o["slides"]], ["287 adults are waiting for a seat", "Volunteers already carry the work",
                                                              "Enrollment grew by 212 adults", "The budget plan pays for the site",
                                                              "Help open the sixth site"])
        self.assertEqual([s["type"] for s in o["slides"]], ["exhibit", "stat", "content", "content", "closing"])

    def test_the_notes_length_holds(self):
        self.assertEqual(CK.notes_length({"N": {"text": "Odalys to make a short deck. No more than eight slides."}}), 8)
        self.assertEqual(CK.notes_length({"N": {"text": "Tobiah to make a short deck. Seven or eight slides at most."}}), 8)
        self.assertIsNone(CK.notes_length({"N": {"text": "We showed eight slides at the gala."}}))

    def test_the_ask_slide_sits_before_the_closing_and_its_money_must_reach_the_deck(self):
        K.ASK_SLIDE = True  # off in the product since round 11b; its code is kept and tested
        self.addCleanup(setattr, K, "ASK_SLIDE", False)
        a = case(self.find)
        a["ask"]["slide"] = {"heading": "Other funders already carry most of the cost", "type": "figures",
                             "evidence": [{"text": "Foundation grants provided $640,000", "refs": [self.find("Operating expenses for FY2026")]}]}
        a["ask"]["rest"] = "Individual donors gave $388,000"
        steps = K.argument_steps(a)
        self.assertEqual([s["role"] for s in steps][-2:], ["ask slide", "ask"])
        self.assertEqual(K.argument_outline(a)["slides"][-2]["type"], "figures")
        self.assertIn("$388,000", K.argument_text(a))
        self.assertIn("THE ASK IN ITS PARTS", K.argument_block(a))
        self.assertEqual(CK.argument_problems(a, self.by_ref), [])

    def test_an_invented_number_a_placeholder_and_a_missing_amount_are_faults(self):
        a = case(self.find)
        a["points"][0]["evidence"][0]["text"] = "Up 31% in one year"
        a["ask"] = dict(a["ask"], amount="", buys=["[What the money pays for]"])
        what = " ".join(f["what"] for f in CK.argument_problems(a, self.by_ref))
        self.assertIn("31%", what)
        self.assertIn("placeholder", what)
        self.assertIn("no amount", what)
        a["ask"] = dict(a["ask"], buys=["A sixth site"], none_in_sources=True)
        what = " ".join(f["what"] for f in CK.argument_problems(a, self.by_ref))
        self.assertNotIn("no amount", what)

    def test_every_instruction_the_notes_give_for_the_deck_must_be_listed_and_placed(self):
        notes = {"N1": {"text": "Tobiah to make a short deck. Marguerite: start with the children who are waiting. "
                                "Priya: show what a breakdown day costs children."}}
        got = [n["text"] for n in CK.notes_instructions(notes)]
        self.assertEqual(len(got), 2, got)
        a = case(self.find, instructions=[{"said": "start with the children who are waiting", "refs": ["N1"], "met_by": "lead"}])
        what = " ".join(f["what"] for f in CK.argument_problems(a, {**self.by_ref, **notes}))
        self.assertIn("breakdown day", what)
        self.assertNotIn("start with the children", what)
        a["instructions"].append({"said": "show what a breakdown day costs children", "refs": ["N1"], "met_by": "point 9"})
        what = " ".join(f["what"] for f in CK.argument_problems(a, {**self.by_ref, **notes}))
        self.assertIn("not a step of the case", what)

    def test_the_make_job_argues_first_and_the_deck_follows_the_case(self):
        a = case(self.find)
        self.llm.argument = [a]
        good = deck(self.find)
        self.llm.deck = lambda ps: {"case": "The case.", "title": good["title"], "subtitle": good["subtitle"],
                                    "slides": [good["slides"][0], good["slides"][1], good["slides"][3], good["slides"][3], good["slides"][6]]}
        j = jobs.start("make", f"t:r11:{store.now()}", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                                      "brief": "A 7 to 9 slide funder deck"}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "done", j["error"])
        purposes = [c["purpose"] for c in self.llm.calls]
        self.assertEqual(purposes[:2], ["letterpress.argument", "letterpress.write"])
        w = next(c for c in self.llm.calls if c["purpose"] == "letterpress.write")
        self.assertIn("THE CASE, drafted and checked", w["instructions"])
        self.assertIn("COUNTER-CASE", w["instructions"])
        self.assertNotIn("COVERAGE.", w["instructions"])  # the general coverage rule adds slides the case did not ask for
        self.assertEqual(w["json_schema"]["properties"]["slides"]["maxItems"], 5)
        oid = j["result"]["output_id"]
        heads = [s.get("heading") or s.get("label") for s in service._output(oid)["neutral"]["slides"]]
        self.assertEqual(heads, ["287 adults are waiting for a seat", "Volunteers already carry the work", "Enrollment grew by 212 adults",
                                 "The budget plan pays for the site", "Help open the sixth site"])
        self.assertEqual(j["result"]["argument"]["lead"]["heading"], "287 adults are waiting for a seat")
        self.assertTrue(store.get_setting(f"argument_of:{oid}"))

    def test_a_faulty_case_gets_one_repair_and_no_case_falls_back_to_the_one_pass(self):
        bad = case(self.find)
        bad["points"][0]["evidence"][0]["text"] = "Up 31% in one year"
        self.llm.argument = [bad, case(self.find)]
        self.llm.deck = lambda ps: {"case": "c", **deck(self.find)}
        j = jobs.get(jobs.start("make", f"t:r11b:{store.now()}", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                                                "brief": "A 7 to 9 slide funder deck"}, wait=True)["id"])
        self.assertEqual(j["status"], "done", j["error"])
        purposes = [c["purpose"] for c in self.llm.calls]
        self.assertEqual(purposes[:3], ["letterpress.argument", "letterpress.argument_repair", "letterpress.write"])
        self.llm.calls.clear()
        self.llm.argument = None
        j = jobs.get(jobs.start("make", f"t:r11c:{store.now()}", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                                                "brief": "A 7 to 9 slide funder deck"}, wait=True)["id"])
        self.assertEqual(j["status"], "done", j["error"])
        w = next(c for c in self.llm.calls if c["purpose"] == "letterpress.write")
        self.assertIn('First write "case"', w["instructions"])
        self.assertNotIn("argument", j["result"])


if __name__ == "__main__":
    unittest.main()
