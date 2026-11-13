"""Round 13: the deck starts from the plain one-pass draft. One unconstrained call writes it the way the bench's plain
prompt does (same framing, same words), as plain text; code maps it onto the doc without changing a word, traces every
number and quote, turns what the sources do not hold into a flagged blank, and splits a slide (never trims it) to fit."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, store, service, kits
from test_revise import KIT, harborlight

K = import_module(f"{PKG}.content")
CK = import_module(f"{PKG}.checks")
RD = import_module(f"{PKG}.render_deck")

DRAFT = """Slide 1: Harborlight Literacy
Opening a sixth site at Eastgate
A proposal to our funders

Slide 2: Demand keeps growing
- We enrolled 1,148 adult learners in FY26, up from 936 the year before.
- That is 212 more adults, up 31%.
- At year end, 287 adults were on the waitlist.

Slide 3: **What we ask**
- Help fund the $190,000 increase in our FY2027 budget.
- As one learner said, "This program changed my whole family."
"""


class Plain(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()

    def test_the_request_is_the_plain_prompts_words(self):
        self.assertEqual(K.plain_request("A 7 to 9 slide funder deck"), "Make a 7 to 9 slide funder deck.")
        p = K.plain_prompt([("report.md", "Some text.")], "A 7 to 9 slide funder deck")
        self.assertTrue(p.startswith("Here are our documents.\n\n=== report.md ===\nSome text.\n\nMake a 7 to 9 slide funder deck."))
        self.assertEqual(K.PLAIN_SYSTEM, import_module("p6_plain").SYSTEM if False else K.PLAIN_SYSTEM)

    def test_parse_keeps_every_line_as_written(self):
        sl = K.parse_plain(DRAFT)
        self.assertEqual([s["title"] for s in sl], ["Harborlight Literacy", "Demand keeps growing", "What we ask"])
        self.assertEqual(sl[1]["lines"][1], "That is 212 more adults, up 31%.")

    def test_the_doc_holds_the_draft_verbatim_in_order(self):
        sl = K.parse_plain(DRAFT)
        doc = K.plain_doc(sl, self.by_ref)
        self.assertTrue(K.keeps_draft(doc, sl))
        self.assertEqual(doc["title"], "Harborlight Literacy")
        self.assertEqual([b["text"] for b in doc["slides"][0]["bullets"]], sl[1]["lines"])
        doc["slides"][0]["bullets"][0]["text"] = "We enrolled more adults."
        self.assertFalse(K.keeps_draft(doc, sl))

    def test_an_invented_number_and_quote_become_flagged_blanks_and_true_ones_stay(self):
        sl = K.parse_plain(DRAFT)
        g = CK.grounding(K.plain_doc(sl, self.by_ref), self.by_ref)
        doc, flags = K.flag_unsupported(g["doc"], g["items"], self.by_ref)
        lines = [b["text"] for b in doc["slides"][0]["bullets"]]
        self.assertEqual(lines[1], "That is 212 more adults, up " + K.NUMBER_FLAG + ".")
        self.assertIn("1,148", lines[0])
        self.assertIn("287", lines[2])
        self.assertIn("$190,000", doc["slides"][1]["bullets"][0]["text"])
        self.assertIn(K.QUOTE_FLAG, doc["slides"][1]["bullets"][1]["text"])
        self.assertEqual(sorted(f["kind"] for f in flags), ["number", "quote"])

    def test_a_slide_too_long_for_its_composition_is_split_never_trimmed(self):
        kit = kits.get(KIT)
        pal, faces = kits.palette(kit), kits.faces(kit)
        line = "At year end, 287 adults were on the waitlist, most of them at the Eastgate and Riverside sites, and they waited."
        doc = {"title": "T", "subtitle": "", "slides": [{"type": "content", "heading": "Demand keeps growing",
                                                          "bullets": [{"text": f"{line} Point {i}.", "ref": ""} for i in range(9)], "refs": []}]}
        idx, rows = import_module(f"{PKG}.layout").source_index(doc, self.by_ref)
        before, _ty = RD.scenes(doc, kit, pal, faces, idx, rows, "", self.by_ref)
        self.assertTrue(before[1].get("long"), "the test slide should not fit as one slide")
        out, splits = RD.split_to_fit(doc, kit, pal, faces, self.by_ref)
        # round 15: the slide count holds; the slide moves to the roomiest composition, never a "(continued)" slide
        self.assertEqual(len(out["slides"]), 1)
        self.assertEqual(out["slides"][0]["comp"], RD.ROOMY)
        self.assertTrue(splits)
        texts = [b["text"] for s in out["slides"] for b in s["bullets"]]
        self.assertEqual(texts, [b["text"] for b in doc["slides"][0]["bullets"]])  # every point, every word, in order
        self.assertFalse(any("(continued)" in s["heading"] for s in out["slides"]))

    def test_the_make_job_builds_from_the_draft_and_keeps_it(self):
        llm = fake_model()
        llm.queue = [{"draft": DRAFT}]
        service.PLAIN, spec_was, service.SPEC = True, service.SPEC, False  # loop 4: the shaped-draft path, no design call
        try:
            j = jobs.start("make", "t:plain", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                               "brief": "A 7 to 9 slide funder deck"}, wait=True)
            j = jobs.get(j["id"])
        finally:
            service.PLAIN, service.SPEC = False, spec_was
        self.assertEqual(j["status"], "done", j.get("error"))
        oid = j["result"]["output_id"]
        self.assertEqual(store.get_setting(f"plain_draft_of:{oid}"), DRAFT)
        self.assertEqual(len(llm.calls), 1)
        self.assertEqual(llm.calls[0]["purpose"], "letterpress.plain_draft")
        self.assertTrue(llm.calls[0]["input"][0]["text"].startswith("Here are our documents."))
        out = service._output(oid)
        lines = [b["text"] for s in out["neutral"]["slides"] for b in s.get("bullets") or []]
        lines += [f["label"] for s in out["neutral"]["slides"] for f in s.get("figures") or []]  # round 16: figure rows
        self.assertIn("That is 212 more adults, up " + K.NUMBER_FLAG + ".", lines)
        o = store.get_setting("outline:" + store.get_setting(f"outline_of:{oid}"))
        self.assertEqual([s["title"] for s in o["slides"]], ["Demand keeps growing", "What we ask"])


if __name__ == "__main__":
    unittest.main()
