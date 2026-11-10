"""Designs in the Studio: three options per deck, one-pager and graphic; the pick and the mix; element edits, revise, versions and
exports; the number trace on the result. The model is a stand-in that writes HTML; Chrome is real."""
import json
import shutil
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, ROOT, Result, jobs, reset, service, store

D = import_module(f"{PKG}.designs")
HD = import_module(f"{PKG}.htmldeck")
CHROME = Path(HD.CHROME).exists()


class Writer:
    """A stand-in model: writes three slides per direction from the first sources it is given, one revised slide on revise."""
    def __init__(self, bad_number=False):
        self.calls = []
        self.bad = bad_number

    async def acomplete_structured(self, **kw):
        purpose = kw.get("purpose", "")
        self.calls.append(purpose)
        text = kw["input"][0]["text"]
        d = "databoard" if "DESIGN DIRECTION: Data board" in kw["instructions"] else "statement" if "DESIGN DIRECTION: Statement" in kw["instructions"] else "editorial"
        if purpose.endswith("revise"):
            return Result(parsed={"slides": [{"index": 1, "html": '<div><style>.z{font:700 60px var(--font-heading);color:var(--brand)}</style><h1 class="z" data-source="P4">287 adults are waiting</h1></div>'}]})
        if purpose.endswith("fix"):
            return Result(parsed={"slides": []})
        n = 3 if "Design the deck from CONTENT" in kw["instructions"] else 1
        col = {"editorial": "var(--brand)", "databoard": "var(--accent)", "statement": "var(--ink)"}[d]
        extra = '<p data-source="P4">and 9999 more</p>' if self.bad else ""
        slides = [{"html": f'<div><style>.a{{font:700 70px var(--font-heading);color:{col};padding:96px}}</style><h1 class="a" data-source="P1">1,148 adult learners in {d}</h1>{extra}</div>', "notes": f"note {i}"}
                  for i in range(1, 4)]
        return Result(parsed={"slides": slides if n == 3 else slides[:1]})


@unittest.skipUnless(CHROME, "needs Chrome")
class Designs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()
        st = service.open_sample()
        cls.deck = next(o["id"] for o in st["outputs"] if o["kind"] == "deck")
        cls.one = next(o["id"] for o in st["outputs"] if o["kind"] == "onepager")
        cls.kit = (store.get_setting("prefs", {}) or {}).get("kit")

    def setUp(self):
        D.ROUNDS = 0
        self.llm = Writer()
        service.LLM = self.llm

    def make(self, oid):
        j = jobs.start("designs", f"designs:{oid}:{self.kit}:{len(self.llm.calls)}", {"output_id": oid, "kit_id": self.kit}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "done", j.get("error"))
        return D.view(oid)

    def test_make_gives_three_distinct_options_and_a_result(self):
        v = self.make(self.deck)
        self.assertEqual([o["d"] for o in v["options"]], ["editorial", "databoard", "statement"])
        self.assertTrue(all(o["status"] == "ready" and len(o["thumbs"]) == 3 and o["thumbs"][0].startswith("data:image/png") for o in v["options"]))
        self.assertEqual(len(v["final"]["slides"]), 3)
        self.assertEqual(len({s["html"] for d in D.DIRS for s in D.load(self.deck)["options"][d]["slides"]}), 9)

    def test_one_pager_and_graphic_kinds_get_one_slide_each(self):
        v = self.make(self.one)
        self.assertEqual(v["kind"], "onepager")
        self.assertTrue(all(o["slides"] == 1 for o in v["options"]))

    def test_pick_one_direction_and_mix_across_directions(self):
        self.make(self.deck)
        D.compose(self.deck, [{"d": "statement", "i": i} for i in (1, 2, 3)])
        self.assertEqual([s["from"] for s in D.load(self.deck)["final"]["slides"]], ["statement:1", "statement:2", "statement:3"])
        D.compose(self.deck, [{"d": "editorial", "i": 1}, {"d": "databoard", "i": 2}, {"d": "statement", "i": 3}, {"d": "editorial", "i": 1}])
        st = D.load(self.deck)
        self.assertEqual(st["final"]["label"], "Mixed")
        self.assertEqual([s["from"] for s in st["final"]["slides"]], ["editorial:1", "databoard:2", "statement:3", "editorial:1"])
        # slides from different designs never share a class name, so one's CSS cannot reach another
        import re
        names = [set(re.findall(r'class="([^"]*)"', s["html"])[0].split()) for s in st["final"]["slides"][:3]]
        self.assertFalse(names[0] & names[1] or names[1] & names[2] or names[0] & names[2])
        self.assertEqual(len(D.view(self.deck)["final"]["slides"]), 4)
        with self.assertRaises(ValueError):
            D.compose(self.deck, [{"d": "nope", "i": 1}])
        with self.assertRaises(ValueError):
            D.compose(self.deck, [{"d": "editorial", "i": 99}])
        with self.assertRaises(ValueError):
            D.compose(self.deck, [])

    def test_element_edit_is_traced_flagged_and_export_waits_until_kept(self):
        self.make(self.deck)
        D.compose(self.deck, [{"d": "editorial", "i": 1}])
        els = D.view(self.deck)["final"]["slides"][0]["elements"]
        el = next(e["index"] for e in els if "1,148" in e["text"])
        j = jobs.start("designs_apply", "e1", {"output_id": self.deck, "op": "edit", "slide": 1, "el": el, "text": "7,777 adult learners"}, wait=True)
        self.assertEqual(jobs.get(j["id"])["status"], "done", jobs.get(j["id"]).get("error"))
        v = D.view(self.deck)
        self.assertEqual(v["open_flags"], 1)
        self.assertEqual(v["flags"][0]["value"], "7,777")
        with self.assertRaises(ValueError):
            D.export(self.deck, "pdf")
        D.keep(self.deck, v["flags"][0]["key"], True)
        self.assertEqual(D.view(self.deck)["open_flags"], 0)
        out = D.export(self.deck, "pdf")
        self.assertTrue(Path(out["path"]).stat().st_size > 1000)

    def test_a_number_the_model_got_wrong_is_flagged_not_shipped(self):
        self.llm.bad = True
        v = self.make(self.deck)
        self.assertTrue(all(o["flags"] >= 3 for o in v["options"]))
        self.assertGreaterEqual(v["open_flags"], 1)
        with self.assertRaises(ValueError):
            D.export(self.deck, "pdf")

    def test_revise_makes_a_version_and_restore_goes_back(self):
        self.make(self.deck)
        D.compose(self.deck, [{"d": "editorial", "i": i} for i in (1, 2, 3)])
        before = D.load(self.deck)["final"]["slides"][0]["html"]
        j = jobs.start("designs_apply", "r1", {"output_id": self.deck, "op": "revise", "instruction": "Make the first headline about the waitlist", "slide": 1}, wait=True)
        self.assertEqual(jobs.get(j["id"])["status"], "done", jobs.get(j["id"]).get("error"))
        st = D.load(self.deck)
        self.assertIn("287 adults are waiting", st["final"]["slides"][0]["html"])
        self.assertIn("Revised", st["versions"][0]["label"])
        vid = next(v["id"] for v in st["versions"] if v["label"] != st["versions"][0]["label"])
        D.restore(self.deck, vid)
        self.assertNotIn("287 adults are waiting", D.load(self.deck)["final"]["slides"][0]["html"])

    def test_exports_pdf_and_pptx_with_notes(self):
        self.make(self.deck)
        D.compose(self.deck, [{"d": "databoard", "i": i} for i in (1, 2, 3)])
        pdf = D.export(self.deck, "pdf")
        self.assertTrue(pdf["name"].endswith(".pdf"))
        pp = D.export(self.deck, "pptx")
        from pptx import Presentation
        prs = Presentation(pp["path"])
        self.assertEqual(len(prs.slides), 3)
        self.assertIn("note 1", prs.slides[0].notes_slide.notes_text_frame.text)
        self.assertIn("Sources:", prs.slides[0].notes_slide.notes_text_frame.text)

    def test_one_failing_direction_does_not_cost_the_others(self):
        orig = self.llm.acomplete_structured

        async def flaky(**kw):
            if "DESIGN DIRECTION: Statement" in kw["instructions"] and kw["purpose"].endswith("write"):
                raise ValueError("no")
            return await orig(**kw)
        self.llm.acomplete_structured = flaky
        v = self.make(self.deck)
        self.assertEqual({o["d"]: o["status"] for o in v["options"]}, {"editorial": "ready", "databoard": "ready", "statement": "failed"})

    def test_the_existing_template_output_is_untouched(self):
        before = service.output_view(self.deck)["proofs"][0]["status"]
        self.make(self.deck)
        self.assertEqual(service.output_view(self.deck)["proofs"][0]["status"], before)
        self.assertIn("pdf", service.output_view(self.deck)["formats"])


class Brand(unittest.TestCase):
    def test_the_kit_becomes_the_brand_and_a_starting_style(self):
        reset()
        service.open_sample()
        kit = service.KITS.get((store.get_setting("prefs", {}) or {}).get("kit"))
        brand, text, logo = D.brand_for(kit)
        self.assertEqual(brand["heading"], "Montserrat")
        self.assertEqual(brand["vars"]["--brand"], "#0e5e6f")
        self.assertTrue({f["weight"] for f in brand["fonts"] if f["family"] == "Montserrat"} >= {"400", "700"})
        self.assertIn("--cta", text)
        self.assertTrue(logo.startswith("data:image/png"))
        self.assertIn("layout family", D.style_hint(kit))


if __name__ == "__main__":
    unittest.main()
