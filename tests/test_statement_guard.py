"""The Statement design that came back as bare grey slides (live run, Nov 11): the cause (one content:attr() rule cost each slide
its whole stylesheet), the fix (only the bad rule goes), and the guard (a broken design is made once more, then falls back to
the template version, and is never offered broken)."""
import json
import re
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, Result, jobs, reset, service, store

D = import_module(f"{PKG}.designs")
HD = import_module(f"{PKG}.htmldeck")
CHROME = Path(HD.CHROME).exists()
FX = json.loads((Path(__file__).parent / "fixtures" / "statement_unstyled_nov11.json").read_text())

# Slide 2 as the model wrote it, before the cleaner: the stored markup plus the stylesheet the cleaner emptied. The only
# rule that cannot be kept is the slide number drawn from data-page.
RAW2 = ('<div class="s2-slide"><style>.s2-slide{position:relative;width:1920px;height:1080px;background:var(--paper);color:var(--brand)}'
        '.s2-fig{position:absolute;left:96px;bottom:300px;margin:0;font-size:320px;font-weight:800;line-height:.95}'
        '.s2-pn::after{content:attr(data-page)}.s2-pn{position:absolute;right:96px;bottom:96px;font-size:26px}</style>'
        '<p class="s2-fig" data-value="212" data-source="P1">212</p><span class="s2-pn" data-page="2"></span>'
        '<img class="s2-logo" src="imprint:logo" alt=""></div>')


class TheStoredFailure(unittest.TestCase):
    def test_the_stored_slides_are_what_the_guard_calls_broken(self):
        slides = FX["slides"]
        self.assertFalse(HD.unstyled(slides[0]["html"]))       # the title slide had its styles
        self.assertTrue(all(HD.unstyled(s["html"]) for s in slides[1:]))  # slides 2 to 8: <style></style>, nothing else
        why = HD.broken(slides, [{"kind": "small"}] * FX["hard_problems"])
        self.assertTrue(any("no styling" in w for w in why), why)
        self.assertTrue(any("36 layout problems" in w for w in why), why)
        self.assertIn("attr(", FX["removed"][0])

    def test_one_bad_rule_now_costs_only_that_rule(self):
        out, rm = HD.sanitize(RAW2)
        self.assertFalse(HD.unstyled(out))
        self.assertIn(".s2-fig{position:absolute", out)
        self.assertIn(".s2-pn{position:absolute", out)
        self.assertNotIn("attr(", out)
        self.assertEqual(rm, ["<style>: 1 CSS rule dropped (attr()"])

    def test_salvage_never_leaves_a_forbidden_construct_and_escapes_still_drop_all(self):
        for css in (".a{color:red}.b{background:url(http://e/x)}", ".a{color:red}@media print{.b{content:counter(n)}}",
                    ".a{color:red}.b::after{content:\"9\"}", ".a{color:red}.b{x:@import}"):
            out, rm = HD.sanitize(f"<style>{css}</style><p class='a'>x</p>")
            self.assertIn(".a{color:red}", out, css)
            self.assertIsNone(HD._forbidden(re.search(r"<style>(.*?)</style>", out).group(1)), css)
            self.assertTrue(rm, css)
        out, _ = HD.sanitize('<style>.a{color:red}.b{co\\6e tent:"1"}</style><p>x</p>')
        self.assertNotIn("color:red", out)  # an escape anywhere still drops the whole block, unrewritten
        out, _ = HD.sanitize("<style>.a{color:red}.b{background:url(http://e)</style><p>x</p>")  # unbalanced: judged whole
        self.assertNotIn("color:red", out)

    def test_the_brief_no_longer_invites_css_drawn_text(self):
        self.assertIn("attr()", HD.rules("deck"))
        brief = HD.DIRECTIONS["deck"]["statement"]["brief"]
        self.assertIn("no slide number", brief)
        self.assertNotIn("slide number and the logo are the only", brief)

    def test_the_template_version_is_styled_and_keeps_every_number(self):
        slides = HD.template_slides(FX["doc"], "statement")
        self.assertEqual(len(slides), len(FX["doc"]["slides"]) + 1)
        self.assertFalse(any(HD.unstyled(s["html"]) for s in slides))
        self.assertEqual(HD.broken(slides, []), [])
        text = " ".join(s["html"] for s in slides)
        for s in FX["doc"]["slides"]:
            for v in [s.get("value")] + [b.get("value") for b in s.get("bars") or []] + [f.get("value") for f in s.get("figures") or []]:
                if v:
                    self.assertIn(v, text)
        grounds = [re.search(r"background:(var\(--[a-z-]+\))", s["html"]).group(1) for s in slides]
        self.assertTrue(all(a != b for a, b in zip(grounds[1:], grounds[2:])), grounds)  # statement alternates its grounds


class Bare:
    """A stand-in model. ``bad`` sets how many Statement writes come back as the live failure did (no styling at all)."""
    def __init__(self, bad):
        self.bad, self.calls = bad, []

    async def acomplete_structured(self, **kw):
        purpose = kw.get("purpose", "")
        statement = "DESIGN DIRECTION: Statement" in kw["instructions"]
        self.calls.append((purpose, statement))
        if purpose.endswith("fix"):
            return Result(parsed={"slides": []})
        if statement and sum(1 for p, s in self.calls if s and p.endswith("write")) <= self.bad:
            return Result(parsed={"slides": [{"html": FX["slides"][1]["html"], "notes": "n"}] * 3})
        return Result(parsed={"slides": [{"html": '<div><style>.a{font:700 70px var(--font-heading);color:var(--brand);padding:96px}</style>'
                                                  '<h1 class="a" data-source="P1">1,148 adult learners</h1></div>', "notes": "n"}] * 3})


@unittest.skipUnless(CHROME, "needs Chrome")
class TheGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()
        st = service.open_sample()
        cls.deck = next(o["id"] for o in st["outputs"] if o["kind"] == "deck")
        cls.kit = (store.get_setting("prefs", {}) or {}).get("kit")

    def setUp(self):
        D.ROUNDS = 0

    def run_with(self, bad):
        llm = Bare(bad)
        service.LLM = llm
        j = jobs.start("designs", f"designs:{self.deck}:{self.kit}:guard{bad}", {"output_id": self.deck, "kit_id": self.kit}, wait=True)
        self.assertEqual(jobs.get(j["id"])["status"], "done", jobs.get(j["id"]).get("error"))
        writes = sum(1 for p, s in llm.calls if s and p.endswith("write"))
        opt = D.load(self.deck)["options"]["statement"]
        card = next(o for o in D.view(self.deck)["options"] if o["d"] == "statement")
        return writes, opt, card

    def test_broken_once_is_made_again_and_kept(self):
        writes, opt, card = self.run_with(1)
        self.assertEqual(writes, 2)
        self.assertFalse(opt["template"])
        self.assertFalse(card["template"])
        self.assertFalse(any(HD.unstyled(s["html"]) for s in opt["slides"]))

    def test_broken_twice_falls_back_to_the_template_version_and_says_so(self):
        writes, opt, card = self.run_with(99)
        self.assertEqual(writes, 2)  # bounded: one retry, never a third write
        self.assertTrue(opt["template"])
        self.assertEqual(opt["status"], "ready")
        self.assertTrue(card["template"])
        self.assertEqual(card["name"], "Statement (template version)")
        self.assertFalse(any(HD.unstyled(s["html"]) for s in opt["slides"]))
        self.assertEqual(HD.broken(opt["slides"], opt["problems"]), [])
        self.assertEqual(len(card["thumbs"]), len(opt["slides"]))
        # the other two designs were not touched by the guard
        other = D.load(self.deck)["options"]["editorial"]
        self.assertFalse(other["template"])


if __name__ == "__main__":
    unittest.main()
