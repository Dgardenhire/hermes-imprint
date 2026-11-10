"""Loop 4 security fixes: a model-written slide spec is untrusted input. Sizes and coordinates are finite and clamped,
every fitting loop is bounded, and a worked-out number proves itself only from its own sources' passages."""
import copy
import time
import unittest
from importlib import import_module

from _load import PKG, service, kits
from test_revise import KIT, harborlight
from test_plain_r13 import DRAFT
from test_spec_l4 import SPECS

K = import_module(f"{PKG}.content")
CK = import_module(f"{PKG}.checks")
RD = import_module(f"{PKG}.render_deck")
SP = import_module(f"{PKG}.spec")
L = import_module(f"{PKG}.layout")

HOSTILE = [1e308, float("nan"), float("inf"), float("-inf"), -40, "huge", None, True, "1" * 400]


class Sizes(unittest.TestCase):
    def test_size_and_number_helpers_clamp(self):
        for v in HOSTILE:
            with self.subTest(v=v):
                s = SP._size(v, 14.0)
                self.assertTrue(s == 14.0 or SP.SIZE_MIN <= s <= SP.SIZE_MAX)
                self.assertTrue(abs(SP._num(v, 0.0)) < float("inf"))
        self.assertEqual(SP._size(500, 0), SP.SIZE_MAX)
        self.assertEqual(SP._size(2, 0), SP.SIZE_MIN)
        self.assertIsNone(SP.parse_value("1" * 400))
        x, y, w, h = SP.box({"x": float("inf"), "y": float("nan"), "w": 1e308, "h": -5})
        self.assertTrue(all(abs(v) <= SP.COORD_MAX for v in (x, y, w, h)) and h == 0)

    def test_hostile_sizes_render_quickly(self):
        ids, by_ref, _f = harborlight()
        for v in HOSTILE:
            with self.subTest(v=v):
                sl = copy.deepcopy(SPECS["slides"])
                for s in sl:
                    for el in s["els"]:
                        el["size"] = v
                        el["label_size"] = v
                        el["note_size"] = v
                        el["title_size"] = v
                doc = service.spec_doc(sl, K.parse_plain(DRAFT), by_ref)
                k = kits.get(KIT)
                idx, rows = L.source_index(doc, by_ref)
                t = time.time()
                scs, _ty = RD.scenes(doc, k, kits.palette(k), kits.faces(k), idx, rows, "", by_ref)
                self.assertLess(time.time() - t, 10)
                self.assertEqual(len(scs), len(sl))

    def test_oversized_lists_are_capped(self):
        ids, by_ref, _f = harborlight()
        sl = copy.deepcopy(SPECS["slides"])
        sl[1]["els"][1]["items"] = [{"label": f"Y{i}", "value": str(i)} for i in range(5000)]
        sl[2]["els"].append({"type": "table", "x": 40, "y": 300, "w": 500, "h": 200,
                             "rows": [[str(i)] * 500 for i in range(5000)]})
        doc = service.spec_doc(sl, K.parse_plain(DRAFT), by_ref)
        k = kits.get(KIT)
        idx, rows = L.source_index(doc, by_ref)
        t = time.time()
        RD.scenes(doc, k, kits.palette(k), kits.faces(k), idx, rows, "", by_ref)
        self.assertLess(time.time() - t, 20)


def _passages():
    return {
        "P1": {"text": "Program costs were $500,000 in FY2026.", "locator": "a", "source_id": "s_report", "source_title": "Report"},
        "P2": {"text": "The board heard that a neighboring group raised $300,000.", "locator": "b", "source_id": "s_other",
               "source_title": "Clipping"},
        "P3": {"text": "Staff costs were $120,000.", "locator": "c", "source_id": "s_report", "source_title": "Report"},
    }


def _doc(text, ref):
    return {"title": "", "subtitle": "", "slides": [{"type": "spec", "title": "x", "els": [
        {"type": "figure", "value": text, "label": "gap", "ref": ref}]}]}


class ComputedScope(unittest.TestCase):
    def status(self, text, ref):
        g = CK.grounding(_doc(text, ref), _passages())
        return {i["value"]: i for i in g["items"] if i["kind"] == "number"}

    def test_uncited_number_that_hits_arithmetic_elsewhere_stays_flagged(self):
        it = self.status("$200,000", None)["200000"]   # 500,000 - 300,000 across two different sources, no citation
        self.assertEqual(it["status"], "missing")
        self.assertIn("Possible match", it.get("detail", ""))

    def test_cited_number_may_not_borrow_an_operand_from_another_source(self):
        it = self.status("$200,000", "P1")["200000"]   # P1 is the report; 300,000 is only in the clipping
        self.assertEqual(it["status"], "missing")

    def test_cited_number_worked_out_within_its_own_source(self):
        it = self.status("$380,000", "P1")["380000"]   # 500,000 - 120,000, both in the report (P1 cited, P3 same source)
        self.assertEqual(it["status"], "computed")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- wrong types in every field (fuzz) --

JUNK = [None, True, 0, -3, 7.5, 1e308, float("nan"), "x" * 50, "", [], [1, None, {}], {}, {"a": 1}, ["a", ["b"]], 10 ** 30]
FIELDS = ["type", "x", "y", "w", "h", "size", "label_size", "note_size", "title_size", "style", "align", "anchor", "orient",
          "color", "fill", "text", "title", "value", "label", "note", "who", "ref", "bullets", "items", "header", "rows", "total"]
TYPES = ["text", "list", "figure", "bars", "stack", "table", "quote", "callout", "rect", "line", "dot"]


def _render(doc, by_ref):
    k = kits.get(KIT)
    idx, rows = L.source_index(doc, by_ref)
    return RD.scenes(doc, k, kits.palette(k), kits.faces(k), idx, rows, "", by_ref)


class WrongTypes(unittest.TestCase):
    def test_every_field_every_type_every_junk_value(self):
        ids, by_ref, _f = harborlight()
        good = {"x": 60, "y": 120, "w": 400, "h": 200, "text": "Families served rose to 212", "value": "212", "label": "families",
                "items": ["One", "Two"], "header": ["Year", "Families"], "rows": [["FY25", "180"], ["FY26", "212"]], "total": ["", "392"]}
        t = time.time()
        n = 0
        for ty in TYPES:
            for f in FIELDS:
                for junk in JUNK:
                    el = {**good, "type": ty, f: junk}
                    if ty in ("bars", "stack") and f != "items":
                        el["items"] = [{"label": "FY25", "value": "180"}, {"label": "FY26", "value": junk}]
                    specs = [{"els": [{"type": "text", "text": "Cover", "style": "title"}]},
                             {"title": junk, "ground": junk, "els": [el, junk, {"type": "text", "text": "after", "x": 60, "y": 400, "w": 300, "h": 40}]}]
                    with self.subTest(type=ty, field=f, junk=repr(junk)[:30]):
                        doc = service.spec_doc(copy.deepcopy(specs), K.parse_plain(DRAFT), by_ref)
                        scs, _ty = _render(doc, by_ref)
                        self.assertEqual(len(scs), 2)
                        SP.fields(doc["slides"][0], "slides.0")
                        CK.grounding(doc, {r: p for r, p in by_ref.items()} if isinstance(by_ref, dict) else {})
                        n += 1
        self.assertGreater(n, 4000)
        self.assertLess(time.time() - t, 240)

    def test_bad_element_is_skipped_and_recorded_not_fatal(self):
        sysm_doc = {"type": "spec", "heading": "x", "footer": True,
                    "els": [{"type": "text", "text": "kept", "x": 60, "y": 60, "w": 300, "h": 60},
                            {"type": "figure", "value": "1", "x": 60, "y": 200, "w": 200, "h": 120}]}
        k = kits.get(KIT)
        C = SP.Composer.__new__(SP.Composer)
        real = SP.Composer.figure
        try:
            SP.Composer.figure = lambda self, *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
            ids, by_ref, _f = harborlight()
            doc = {"title": "t", "subtitle": "", "plain": True, "spec": True,
                   "cover": {**sysm_doc, "footer": False}, "slides": [sysm_doc]}
            scs, _ty = _render(doc, by_ref)
        finally:
            SP.Composer.figure = real
        probs = scs[1].get("problems") or []
        self.assertTrue(any(p["kind"] == "bad" and p["el"] == 1 for p in probs), probs)
        self.assertTrue(any("kept" in str(e.get("text", "")) or "kept" in str(e) for e in scs[1]["els"]))

    def test_model_reply_shapes(self):
        ids, by_ref, _f = harborlight()
        for specs in (None, 5, "slides", {}, [5, "x", None], [{"els": 5}, {"els": {"a": 1}}], [{"els": [5, "x"]}, {"els": [[]]}]):
            with self.subTest(specs=repr(specs)[:30]):
                doc = service.spec_doc(specs, K.parse_plain(DRAFT), by_ref)
                self.assertEqual(doc["slides"], [])

    def test_set_field_on_junk_paths_returns_false(self):
        doc = {"cover": {"els": [5]}, "slides": [{"els": [{"type": "table", "rows": 5}, {"type": "list", "items": {"a": 1}}]}]}
        for path in ("cover.els.0", "slides.0.els.0.rows.0", "slides.0.els.1.items.0", "slides.9.els.0", "slides.x.els.0", "bogus"):
            with self.subTest(path=path):
                self.assertFalse(SP.set_field(doc, path, lambda s: s + "!"))

    def test_clean_el_is_idempotent_and_typed(self):
        el = {"type": "BARS", "x": "40", "size": float("inf"), "text": {"a": 1}, "items": [{"label": 3, "value": None}, 7],
              "header": "Year", "rows": [["a", 1.5, None], "bad"], "ref": ["P1"], "bullets": "yes"}
        c = SP.clean_el(el)
        self.assertEqual(c, SP.clean_el(c))
        self.assertEqual(c["type"], "bars")
        self.assertNotIn("x", c)
        self.assertNotIn("size", c)
        self.assertEqual(c["text"], "")
        self.assertEqual(c["items"], [{"label": "3", "value": "", "highlight": False}])
        self.assertEqual(c["header"], [])
        self.assertEqual(c["rows"], [["a", "1.5", ""]])
        self.assertNotIn("ref", c)
        self.assertNotIn("bullets", c)
