"""Hover a number, see its source: every traced number in a proof carries its source mark and a trace card
quoting the source line it came from."""
import re
import unittest

from _load import checks as CK, content as K, layout as L, service, render_html, add_samples, make, fake_model, reset

PASSAGES = {
    "P1": {"text": "Intro line. The season cost $318,400. The city paid $205,000 from the general fund.", "locator": "page 2",
           "source_id": "s1", "source_title": "Board memo"},
    "P2": {"text": "Over the season the center recorded 2,914 overnight stays by 412 different guests.", "locator": "page 1",
           "source_id": "s1", "source_title": "Board memo"},
    "P3": {"text": "Of guests asked, 91 percent said they felt safe.", "locator": "para. 3", "source_id": "s2",
           "source_title": "Survey"},
}


def doc(**over):
    d = {"title": "412 guests kept warm", "dek": "Open from December 1 to March 15.", "dek_refs": ["P2"],
         "stat": {"value": "2,914", "label": "overnight stays", "ref": "P2"},
         "sections": [{"heading": "Cost", "body": "The season cost $318,400 and the city paid 205,000 dollars.", "refs": ["P1"]}],
         "points": [{"text": "91% felt safe.", "ref": "P3"}, {"text": "Volunteers gave 3,600 hours.", "ref": "P2"}],
         "quote": None, "next": "The council meets in April."}
    d.update(over)
    return d


def walk(node, out):
    if "ip-num" in (node.get("c") or "").split():
        out.append(node)
    for k in node.get("k") or []:
        walk(k, out)
    return out


def words(node):
    """The page's text without source marks, spacing ignored."""
    if node.get("t") == "sup":
        return ""
    return re.sub(r"\s+", "", (node.get("x") or "") + "".join(words(k) for k in node.get("k") or []))


def marks(node, out):
    if (node.get("c") or "").split() == ["ip-ref"]:
        out.append(node.get("x"))
    for k in node.get("k") or []:
        marks(k, out)
    return out


class SourceLine(unittest.TestCase):
    def test_sentence_holding_the_number_with_the_number_marked(self):
        line = CK.source_line(PASSAGES["P1"]["text"], "$318,400", "318400")
        self.assertEqual((line["before"], line["match"], line["after"]), ("The season cost ", "$318,400", "."))
        self.assertTrue(line["exact"])

    def test_same_value_written_another_way_is_a_close_match(self):
        line = CK.source_line(PASSAGES["P3"]["text"], "91%", "91%")
        self.assertEqual(line["match"], "91 percent")
        self.assertFalse(line["exact"])

    def test_a_number_inside_a_bigger_number_is_not_a_match(self):
        self.assertIsNone(CK.source_line("We served 4,120 meals.", "412", "412"))
        self.assertEqual(CK.source_line("We served 4,120 meals and 412 guests.", "412", "412")["before"], "We served 4,120 meals and ")

    def test_long_sentences_are_cut_around_the_number(self):
        text = "word " * 120 + "the total was 77 and then " + "more " * 120 + "end."
        line = CK.source_line(text, "77", "77")
        self.assertLessEqual(len(line["before"]) + len(line["after"]), CK.LINE_MAX + 4)
        self.assertTrue(line["before"].startswith("…") and line["after"].endswith("…"))


class Tracing(unittest.TestCase):
    def proof(self, d=None):
        g = CK.grounding(d or doc(), PASSAGES)
        idx, _rows = L.source_index(g["doc"], PASSAGES)
        traces, resolve = CK.trace_table(g["items"], PASSAGES, idx)
        tree = L.tree(g["doc"], {"layout": "banner", "rules": {"sources": True}}, {"paper": "#fff", "ink": "#111", "head": "#111",
                      "accent": "#123", "accent_text": "#123", "rule": "#ccc", "bar": []}, {}, PASSAGES, date="Nov 7, 2026")
        return traces, L.mark_traces(tree, resolve), tree

    def test_every_checked_number_is_wrapped_with_its_trace(self):
        traces, tree, plain = self.proof()
        nums = walk(tree, [])
        shown = {n["x"] for n in nums}
        for v in ("412", "2,914", "$318,400", "205,000", "91%", "3,600"):
            self.assertIn(v, shown)
        for n in nums:
            t = traces[n["a"]["tr"]]
            self.assertEqual(t["value"], n["x"])
        by = {n["x"]: traces[n["a"]["tr"]] for n in nums}
        self.assertEqual(by["$318,400"]["status"], "exact")
        self.assertEqual(by["$318,400"]["source"], "Board memo")
        self.assertEqual(by["$318,400"]["locator"], "page 2")
        self.assertEqual(by["$318,400"]["line"]["match"], "$318,400")
        self.assertEqual(by["205,000"]["status"], "exact")
        self.assertEqual(by["91%"]["status"], "close")
        self.assertEqual(by["91%"]["line"]["match"], "91 percent")
        self.assertEqual(by["3,600"]["status"], "missing")
        self.assertEqual(by["91%"]["n"], 2)
        # The page's words are unchanged: the trace only wraps them.
        self.assertEqual(words(tree), words(plain))

    def test_each_traced_number_shows_its_source_mark(self):
        traces, tree, _plain = self.proof()
        for n in walk(tree, []):
            t = traces[n["a"]["tr"]]
            sup = [k for k in n.get("k") or [] if k.get("t") == "sup"]
            if t["status"] in ("exact", "close") and n["x"] not in ("1", "15"):
                self.assertEqual([s["x"] for s in sup], [str(t["n"])], n["x"])
            if t["status"] == "missing":
                self.assertEqual(sup, [])

    def test_field_citation_drops_sources_the_numbers_already_show(self):
        _t, tree, plain = self.proof()
        before, after = marks(plain, []), marks(tree, [])
        self.assertLess(len(after), len(before))
        # The volunteers point's number is not in the sources, so its own citation stays.
        point = next(p for p in walk(tree, []) if p["x"] == "3,600")
        self.assertTrue(point)
        self.assertIn("1", after)

    def test_dates_are_traced_without_a_mark_that_reads_as_part_of_the_date(self):
        _t, tree, _p = self.proof()
        days = [n for n in walk(tree, []) if n["x"] in ("1", "15")]
        self.assertEqual(len(days), 2)
        self.assertTrue(all(not n.get("k") for n in days))

    def test_dates_footers_and_source_lists_are_left_alone(self):
        _t, tree, _p = self.proof()
        def find(node, cls):
            if cls in (node.get("c") or "").split():
                return node
            for k in node.get("k") or []:
                r = find(k, cls)
                if r:
                    return r
        self.assertEqual(walk(find(tree, "ip-date") or {}, []), [])
        self.assertEqual(walk(find(tree, "ip-sources") or {}, []), [])

    def test_text_outside_the_checked_fields_is_not_traced(self):
        traces, resolve = CK.trace_table(CK.grounding(doc(), PASSAGES)["items"], PASSAGES, {"P1": 1, "P2": 1, "P3": 2})
        self.assertIsNone(resolve("Printed Nov 7, 2026", "2026"))
        self.assertIsNotNone(resolve("2,914", "2,914"))
        self.assertIsNotNone(resolve("“The season cost $318,400 and the city paid 205,000 dollars.”", "$318,400"))


class ProofsCarryTraces(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.ids = [s["id"] for s in add_samples()]

    def test_one_pager_deck_and_script_all_trace(self):
        for kind in ("onepager", "deck", "audio"):
            j = make(self.ids, ["plain-notice", "docket"], kind=kind) if kind != "onepager" else make(self.ids, ["plain-notice", "docket"])
            self.assertEqual(j["status"], "done", j["error"])
            v = service.output_view(j["result"]["output_id"])
            for p in v["proofs"]:
                nums = walk(p["tree"], [])
                self.assertTrue(nums, f"{kind} {p['kit_id']} has no traced numbers")
                self.assertTrue(all(0 <= n["a"]["tr"] < len(p["traces"]) for n in nums))
                for t in p["traces"]:
                    self.assertIn(t["status"], ("exact", "close", "missing", "kept"))
                    if t["status"] in ("exact", "close"):
                        self.assertTrue(t["source"] and t["line"] and t["line"]["match"], t)
                self.assertNotIn("field", (p["grounding"] or [{}])[0] if p["grounding"] else {})

    def test_html_export_is_the_finished_page_with_footnotes_not_trace_marks(self):
        import re
        from pathlib import Path
        j = make(self.ids, ["plain-notice"])
        r = service.export(j["result"]["output_id"], "plain-notice", "html")
        page = Path(r["path"]).read_text()
        self.assertNotIn("ip-ref-num", page, "per-number trace marks belong to the proof only")
        self.assertNotIn("ip-num", page)
        self.assertIn('<a href="#ip-src-1">1</a>', page)
        self.assertIn('id="ip-src-1"', page)
        self.assertNotIn("Drawn from", page, "no colophon on the finished page")
        self.assertNotIn('class="bar"', page)
        self.assertIsNone(re.search(r"\d<sup", page), "a mark never sits flush against a figure")
        self.assertNotIn("tabindex", page.lower())
        self.assertNotIn(" tr=", page)

if __name__ == "__main__":
    unittest.main()
