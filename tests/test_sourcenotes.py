"""Source notes: every number and quote on a deck or a one-pager beside the sentence it came from, set as letter pages
in the brand and exported as a PDF. No model call. The rows are the proof's own claims; a number kept on purpose says
so; source text is escaped; an entry is never split across pages; and the drawn pages are measured (nothing cut off,
nothing over the foot) with the browser the designs use."""
import re
import shutil
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, fake_model, kits, service
from test_revise import KIT, harborlight, made

SN = import_module(f"{PKG}.sourcenotes")
HD = import_module(f"{PKG}.htmldeck")
DS = import_module(f"{PKG}.designs")
CHROME = HD.browser_available()


def claim(value, slides, status="exact", kind="number", **kw):
    return {"kind": kind, "value": value, "status": status, "slides": slides, "source_n": kw.get("n", 1),
            "source": kw.get("source", "FY26 Program Report"), "locator": kw.get("locator", "“The waitlist”"),
            "line": kw.get("line", {"before": "At year end,", "match": value, "after": "adults were on the waitlist."}),
            "math": kw.get("math")}


PROOF = {"kind": "deck", "title": "A sixth site", "slides": [{"i": 0, "title": "A sixth site"}, {"i": 1, "title": "Demand is outgrowing our seats"},
                                                              {"i": 2, "title": "287 adults are waiting"}],
         "claims": {
             "c1": claim("287", [0, 1, 2]),
             "c2": claim("936", [1], line={"before": "up from", "match": "936", "after": "the year before."}),
             "c3": claim("212", [1], status="computed", math={"text": "1,148 − 936 = 212"}),
             "c4": claim("I read my granddaughter a bedtime story", [2], kind="quote",
                         line={"before": "", "match": "“I read my granddaughter a bedtime story,” said a learner.", "after": ""}),
             "c5": claim("1,200", [2], status="kept", line={"before": "Harborlight enrolled 1,148 adult learners.", "match": "", "after": ""}),
             "c6": claim("3,000", [2], status="missing", line=None, source="", locator=""),
             "c7": claim("90", [1], status="brief", line=None),
         }}


class Rows(unittest.TestCase):
    def test_claims_are_grouped_by_the_first_slide_that_shows_them(self):
        gs = SN.rows(PROOF)
        self.assertEqual([g["label"] for g in gs], ["Slide 1", "Slide 2", "Slide 3"])
        self.assertEqual(gs[0]["entries"][0]["value"], "287")
        self.assertEqual(gs[0]["entries"][0]["also"], [2, 3], "listed once, the other slides named")
        self.assertEqual([e["value"] for e in gs[1]["entries"]], ["936", "212"], "a number from the person's own request is not a source note")
        self.assertEqual(gs[1]["title"], "Demand is outgrowing our seats")
        self.assertEqual(gs[1]["entries"][1]["math"], "1,148 − 936 = 212")
        self.assertTrue(gs[2]["entries"][0]["quote"])
        self.assertEqual(gs[0]["entries"][0]["locator"], "The waitlist")

    def test_the_summary_counts_and_never_overclaims(self):
        s = SN.summary(SN.rows(PROOF), 2)
        self.assertIn("5 numbers and 1 quote on this deck, from 2 sources.", s)
        self.assertIn("1 figure was kept on purpose and is not in the sources.", s)
        self.assertIn("1 figure is not in the sources.", s)
        clean = {**PROOF, "claims": {k: PROOF["claims"][k] for k in ("c1", "c2")}}
        self.assertEqual(SN.summary(SN.rows(clean), 1), "2 numbers on this deck, from 1 source. Each is shown beside the sentence it came from.")
        self.assertEqual(SN.summary([], 0), "This piece carries no numbers or quotes to trace.")

    def test_a_one_pager_is_one_group_with_no_slide_names(self):
        pr = {"kind": "onepager", "title": "Budget request", "slides": [{"i": 0, "title": "Budget request"}], "claims": {"c1": claim("287", [0])}}
        gs = SN.rows(pr)
        self.assertEqual((len(gs), gs[0]["label"], gs[0]["entries"][0]["also"]), (1, "", []))
        page = SN.pages("Budget request", gs, [], kind="onepager")[0]["html"]
        self.assertNotIn("sn-slide", page)
        self.assertIn("on this page", page)


class Pages(unittest.TestCase):
    def test_the_page_says_what_each_figure_rests_on(self):
        page = "".join(p["html"] for p in SN.pages("A sixth site", SN.rows(PROOF), [{"n": 1, "title": "FY26 Program Report", "where": "The waitlist"}]))
        self.assertIn("At year end, <mark>287</mark> adults were on the waitlist.", page)
        self.assertIn("also on slides 2, 3", page)
        self.assertIn("1,148 − 936 = 212", page)
        self.assertIn("Worked out", page)
        self.assertIn("Kept on purpose", page)
        self.assertIn("No sentence in the sources holds this figure.", page)
        self.assertIn("Not in the sources", page)
        self.assertEqual(page.count("““"), 0, "the source's own quotation marks are not doubled")
        self.assertIn("<h2>Sources</h2>", page)

    def test_source_text_is_escaped_and_only_allowed_markup_is_written(self):
        bad = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        pr = {"kind": "deck", "title": bad, "slides": [{"i": 0, "title": bad}],
              "claims": {"c1": claim("287", [0], source=bad, locator=bad, line={"before": bad, "match": "287", "after": bad})}}
        pages = SN.pages(bad, SN.rows(pr), [{"n": 1, "title": bad, "where": bad}], brand_name=bad, date=bad)
        for p in pages:
            self.assertNotIn("<script", p["html"])
            self.assertNotIn("<img src=x", p["html"])
            self.assertIn("&lt;script&gt;", p["html"])
            cleaned, removed = HD.sanitize(p["html"])
            self.assertEqual(removed, [], "the cleaner finds nothing to take out")
        tags = set(re.findall(r"<([a-z0-9]+)[ >]", "".join(p["html"] for p in pages)))
        self.assertLessEqual(tags, {"div", "span", "p", "h1", "h2", "b", "mark", "img"})

    def test_an_entry_is_never_split_and_a_slide_name_never_ends_a_page(self):
        claims = {f"c{i}": claim(str(1000 + i), [i // 4], line={"before": "A long sentence about the program " * 4, "match": str(1000 + i),
                                                                 "after": "and what followed in the year after " * 3}) for i in range(48)}
        pr = {"kind": "deck", "title": "A long deck", "slides": [{"i": i, "title": f"The point of slide {i + 1} stated as a full sentence"} for i in range(12)],
              "claims": claims}
        gs = SN.rows(pr)
        laid = SN.paginate(gs, [{"n": 1, "title": "Report", "where": ""}], 700, 870)
        self.assertGreater(len(laid), 3)
        entries = [b[1]["value"] for page in laid for b in page if b[0] == "entry"]
        self.assertEqual(entries, [str(1000 + i) for i in range(48)], "every entry once, in order")
        for page in laid:
            self.assertNotEqual(page[-1][0], "group", "a slide's name is never left alone at the foot")
            self.assertEqual(page[0][0], "group", "every page opens by saying which slide it is on")
        self.assertEqual(laid[-1][-1][0], "sources")

    def test_a_dark_brand_is_turned_over_for_print(self):
        dark = {"vars": {"--paper": "#121316", "--ink": "#f2f2f2", "--brand": "#ffffff", "--accent": "#ffd400"}, "fonts": []}
        v = SN.on_paper(dark)["vars"]
        self.assertEqual((v["--paper"], v["--brand"]), ("#ffffff", "#121316"))
        self.assertEqual(v["--accent"], "#121316", "an accent too pale for white gives way to the brand's dark")
        light = {"vars": {"--paper": "#faf7f2", "--ink": "#222222", "--brand": "#0e5e6f"}, "fonts": []}
        self.assertIs(SN.on_paper(light), light)


class Export(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()
        self.oid = made(self.find, self.llm)
        self.work = Path(tempfile.mkdtemp(prefix="letterpress-notes-test-"))

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def keep_the_flag(self):
        pr = service.proof(self.oid, KIT)
        for g in pr["grounding"]:
            if g["status"] == "missing":
                service.decide(self.oid, g["key"], "keep")

    def test_the_format_is_offered_for_decks_and_one_pagers(self):
        self.assertEqual(service.FORMATS["deck"]["notes"], SN.FORMAT_LABEL)
        self.assertEqual(service.FORMATS["onepager"]["notes"], SN.FORMAT_LABEL)
        self.assertNotIn("notes", service.FORMATS["audio"])
        self.assertIn("notes", service.output_view(self.oid)["formats"])

    def test_the_rows_are_the_proofs_own_claims(self):
        self.keep_the_flag()
        pr = service.proof(self.oid, KIT)
        es = [e for g in SN.rows(pr) for e in g["entries"]]
        self.assertEqual(len(es), len([c for c in pr["claims"].values() if c["status"] != "brief"]))
        by = {e["value"]: e for e in es}
        self.assertEqual((by["287"]["status"], by["287"]["match"], by["287"]["source"]), ("exact", "287", "FY26 Program Report"))
        self.assertEqual(by["1,200"]["status"], "kept")

    def test_a_draft_with_an_open_flag_is_not_exported(self):
        with self.assertRaises(ValueError):
            service.export(self.oid, KIT, "notes")  # the same gate every export passes: 1,200 is not in the sources

    def test_no_browser_says_so(self):
        self.keep_the_flag()
        was = HD.browser_available
        HD.browser_available = lambda: False
        try:
            with self.assertRaises(ValueError) as cm:
                service.export(self.oid, KIT, "notes")
            self.assertIn("browser", str(cm.exception))
        finally:
            HD.browser_available = was

    @unittest.skipUnless(CHROME, "needs Chrome")
    def test_export_writes_a_pdf_in_the_brand_with_no_model_call(self):
        self.keep_the_flag()
        calls = len(self.llm.calls)
        ex = service.export(self.oid, KIT, "notes")
        self.assertTrue(ex["name"].endswith("-source-notes.pdf"), ex["name"])
        data = Path(ex["path"]).read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 8000)
        self.assertEqual(len(self.llm.calls), calls)
        self.assertEqual(list(Path(tempfile.gettempdir()).glob("letterpress-notes-*/source-notes.pdf")), [], "the scratch folder is gone")

    @unittest.skipUnless(CHROME, "needs Chrome")
    def test_the_drawn_pages_fit_even_with_long_sentences_in_a_wide_face(self):
        claims = {f"c{i}": claim(f"${1000 + i},000", [i // 5], line={
            "before": "Staff recommend that the board approve a budget for the coming fiscal year of", "match": f"${1000 + i},000",
            "after": ", which adds a sixth site at the Eastgate branch library and two site coordinators, " * (1 + i % 3)},
            locator="“Recommendation to the board of directors at the September retreat”") for i in range(30)}
        pr = {"kind": "deck", "title": "A sixth site for Harborlight and the two coordinators who would staff it from the first day",
              "slides": [{"i": i, "title": "Staff estimate a sixth site would serve 180 more learners a year and cut the waitlist in half"} for i in range(6)],
              "claims": claims}
        for kid in (KIT, "poster-block"):
            brand, _text, logo = DS.brand_for(kits.get(kid))
            got = SN.draw(pr["title"], SN.rows(pr), [{"n": 1, "title": "FY26 Program Report", "where": "Money, The waitlist"}],
                          HD.kit_css(SN.on_paper(brand), SN.KIND), logo, self.work / kid, date="October 1, 2026", brand_name="Harborlight")
            self.assertEqual(got["problems"], [], kid)
            self.assertEqual(len(got["png"]), len(got["pages"]), kid)
            self.assertTrue(got["pdf"] and Path(got["pdf"]).read_bytes().startswith(b"%PDF"), kid)
            drawn = "".join(p["html"] for p in got["pages"])
            self.assertEqual(drawn.count('class="sn-row'), 30, kid)


if __name__ == "__main__":
    unittest.main()
