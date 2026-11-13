"""Round 6: a deck is written in one pass with every source in view (the case first, then every slide, in the first
brand's voice); code checks every number and quote, and one repair call fixes only what fails."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, kits, store, service
from test_revise import KIT, deck, harborlight

CK = import_module(f"{PKG}.checks")
K = import_module(f"{PKG}.content")


def make(ids, brief="A 7 to 9 slide funder deck", **extra):
    j = jobs.start("make", f"t:r6:{store.now()}", {"kind": "deck", "source_ids": ids, "kit_ids": [KIT], "brief": brief, **extra}, wait=True)
    return jobs.get(j["id"])


class OnePass(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()

    def test_one_call_writes_the_deck_and_no_voice_pass_runs_for_the_first_brand(self):
        good = deck(self.find)
        for sl in good["slides"]:  # a deck with no faults, so the repair call is not needed
            if sl.get("heading") == "1,200 learners in one year":
                sl["heading"] = "1,148 learners in one year"
        self.llm.deck = lambda ps: {"case": "Funders must see the waitlist.", **good}
        j = make(self.ids)
        self.assertEqual(j["status"], "done", j["error"])
        purposes = [c["purpose"] for c in self.llm.calls]
        self.assertEqual(purposes.count("letterpress.write"), 1)
        self.assertNotIn("letterpress.voice", purposes)
        w = next(c for c in self.llm.calls if c["purpose"] == "letterpress.write")
        self.assertIn("case", w["json_schema"]["properties"])
        self.assertEqual(w["json_schema"]["properties"]["slides"]["maxItems"], 8)  # 9 with the title slide
        self.assertNotIn("image", w["json_schema"]["properties"]["slides"]["items"]["properties"]["type"]["enum"])  # no pictures asked
        self.assertEqual(w["json_schema"]["required"][0], "case")
        self.assertIn('First write "case"', w["instructions"])
        self.assertIn("every source in view", w["instructions"])
        oid = j["result"]["output_id"]
        self.assertEqual(store.get_setting(f"case_of:{oid}"), "Funders must see the waitlist.")
        self.assertEqual(service._output(oid)["neutral"]["max_slides"], 9)  # the length the request names holds
        self.assertEqual(service.output_view(oid)["proofs"][0]["status"], "ready")

    def test_a_number_no_source_holds_goes_to_the_one_repair_call(self):
        self.llm.deck = lambda ps: deck(self.find)  # "1,200 learners in one year": 1,200 is in no passage
        j = make(self.ids)
        self.assertEqual(j["status"], "done", j["error"])
        rep = [c for c in self.llm.calls if c["purpose"] == "letterpress.repair"]
        self.assertEqual(len(rep), 1)
        self.assertIn("shows 1200", rep[0]["instructions"])

    def test_the_voice_is_in_the_one_pass(self):
        kit = {"name": "Docket", "voice": {"notes": "Formal.", "never": ["very"], "pairs": [{"say": "use", "not": "utilize"}]}}
        t = K.onepass_instructions("A deck", None, kit)
        self.assertIn("VOICE. Write every line in the voice of Docket: Formal.", t)
        self.assertIn("Never say: very.", t)
        self.assertIn('say "use", not "utilize"', t)

    def test_an_approved_outline_is_the_spine(self):
        o = {"slides": [{"title": "Demand is outgrowing our seats", "type": "exhibit", "refs": ["P3"]},
                        {"title": "Fund the sixth site", "type": "closing", "refs": ["P9"]}]}
        t = K.onepass_instructions("A deck", o)
        self.assertIn("THE OUTLINE, which the person approved", t)
        self.assertIn("1. [exhibit] Demand is outgrowing our seats (passages: P3)", t)
        sc = K.onepass_schema(2)
        self.assertEqual((sc["properties"]["slides"]["minItems"], sc["properties"]["slides"]["maxItems"]), (2, 2))
        self.assertNotIn("case", K.DECK_SCHEMA["properties"])  # repair and voice keep the plain deck shape

    def test_length_cap_reads_the_request(self):
        self.assertEqual(service.length_cap("A 7 to 9 slide funder deck"), 9)
        self.assertEqual(service.length_cap("About 8 slides for the October 21 meeting"), 8)
        self.assertIsNone(service.length_cap("A deck for the October 21 meeting"))

    def test_unsourced_lists_numbers_and_quotes(self):
        d = deck(self.find)
        got = CK.unsourced(d, self.by_ref)
        self.assertIn("1200", [u["value"] for u in got])
        self.assertTrue(all(u["kind"] in ("number", "quote", "ref") for u in got))

    def test_evidence_the_case_names_but_no_slide_shows_goes_to_repair(self):
        d = deck(self.find)
        case = "Enrollment rose to 1,148 and 287 adults wait. The average tutor stayed 14 months, from 2019 on."
        got = CK.case_left_out(case, d, self.by_ref)
        nums = [c["number"] for c in got]
        self.assertNotIn("1,148", nums)  # on the exhibit
        self.assertNotIn("287", nums)
        self.assertNotIn("2019", nums)  # a year is never evidence
        self.assertIn("14", nums)
        self.assertIn("The deck's own case names 14", K.repair_instructions({"case": got}))


if __name__ == "__main__":
    unittest.main()
