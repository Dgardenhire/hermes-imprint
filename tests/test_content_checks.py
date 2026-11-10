import unittest

from _load import content as K, checks as CK

PASSAGES = {
    "P1": {"text": "The season cost $318,400. The city paid $205,000.", "locator": "p. 2", "source_id": "s1", "source_title": "Report"},
    "P2": {"text": "Over the season the center recorded 2,914 overnight stays by 412 different guests.", "locator": "p. 1", "source_id": "s1", "source_title": "Report"},
    "P3": {"text": 'One guest wrote: "Having a place to go when it drops below freezing is the difference."', "locator": "para. 4", "source_id": "s2", "source_title": "Survey"},
}


def doc(**over):
    d = {"title": "A cold winter", "dek": "The center was busy.", "dek_refs": [], "stat": {"value": "2,914", "label": "overnight stays", "ref": "P2"},
         "sections": [{"heading": "Cost", "body": "The season cost $318,400.", "refs": ["P1"]}],
         "points": [{"text": "412 guests stayed.", "ref": "P2"}], "quote": None, "next": "The council meets in April."}
    d.update(over)
    return d


class Numbers(unittest.TestCase):
    def test_normalized(self):
        self.assertEqual(K.numbers("It cost $318,400, or 91 percent of 2.50 and 3.0%"), ["318400", "91%", "2.5", "3%"])


class Clean(unittest.TestCase):
    def test_periods_off_headings_and_refs_normalized(self):
        c = K.clean_onepager({"title": "Big news.", "dek": "x", "sections": [{"heading": "Cost.", "body": "b", "refs": ["p 12", "P12", "junk"]}], "points": [], "next": ""})
        self.assertEqual(c["title"], "Big news")
        self.assertEqual(c["sections"][0]["heading"], "Cost")
        self.assertEqual(c["sections"][0]["refs"], ["P12"])
        with self.assertRaises(ValueError):
            K.clean_onepager({"title": "", "sections": []})


class VoicePass(unittest.TestCase):
    def test_changed_number_is_reverted(self):
        neutral = doc()
        voiced = doc(title="A brutal winter", sections=[{"heading": "What it cost", "body": "The season ran about $320,000.", "refs": ["P1"]}])
        merged, reverted = K.keep_facts(neutral, voiced)
        self.assertEqual(merged["title"], "A brutal winter")
        self.assertEqual(merged["sections"][0]["heading"], "What it cost")
        self.assertEqual(merged["sections"][0]["body"], "The season cost $318,400.")
        self.assertIn("sections.0.body", reverted)

    def test_refs_and_quote_always_from_neutral(self):
        neutral = doc(quote={"text": "Having a place to go", "who": "A guest", "ref": "P3"})
        voiced = doc(quote={"text": "A reworded quote", "who": "Someone", "ref": "P9"})
        voiced["sections"][0]["refs"] = ["P9"]
        merged, _ = K.keep_facts(neutral, voiced)
        self.assertEqual(merged["quote"]["text"], "Having a place to go")
        self.assertEqual(merged["sections"][0]["refs"], ["P1"])

    def test_garbage_voice_keeps_neutral(self):
        merged, reverted = K.keep_facts(doc(), {"nonsense": True})
        self.assertEqual(reverted, ["all"])
        self.assertEqual(merged, doc())

    def test_pairs_enforced_in_code_keeping_case(self):
        d = doc(dek="Utilize the hall. We utilize it in order to help.")
        out, changes = K.apply_pairs(d, [{"say": "use", "not": "utilize"}, {"say": "to", "not": "in order to"}])
        self.assertEqual(out["dek"], "Use the hall. We use it to help.")
        self.assertEqual(len(changes), 2)

    def test_never_hits_skip_quotes(self):
        d = doc(quote={"text": "we leverage it", "ref": "P3"}, next="We will leverage the grant.")
        self.assertEqual([h["path"] for h in K.never_hits(d, ["leverage"])], ["next"])

    def test_voice_instructions_carry_the_kit(self):
        txt = K.voice_instructions({"name": "Docket", "voice": {"notes": "Formal.", "never": ["very"], "pairs": [{"say": "use", "not": "utilize"}]}})
        self.assertIn("Never say: very", txt)
        self.assertIn('say "use", not "utilize"', txt)


class Grounding(unittest.TestCase):
    def test_all_traced(self):
        g = CK.grounding(doc(), PASSAGES)
        self.assertEqual(g["missing"], [])
        self.assertEqual(CK.pill_sources(g)["tone"], "good")

    def test_number_in_another_passage_moves_the_citation(self):
        d = doc(sections=[{"heading": "Who", "body": "412 different guests came.", "refs": ["P1"]}])
        g = CK.grounding(d, PASSAGES)
        self.assertEqual(g["fixed"][0]["ref"], "P2")
        self.assertIn("P2", g["doc"]["sections"][0]["refs"])

    def test_invented_number_blocks_with_closest_match(self):
        d = doc(points=[{"text": "The season cost $350,000.", "ref": "P1"}])
        g = CK.grounding(d, PASSAGES)
        pill = CK.pill_sources(g)
        self.assertEqual(pill["tone"], "bad")
        self.assertTrue(pill["blocking"])
        self.assertEqual(pill["label"], "1 number not found in sources")
        self.assertEqual(g["missing"][0]["closest"]["ref"], "P1")

    def test_keeping_on_purpose_is_a_warning_not_a_block(self):
        d = doc(points=[{"text": "The season cost $350,000.", "ref": "P1"}])
        key = CK.grounding(d, PASSAGES)["missing"][0]["key"]
        g = CK.grounding(d, PASSAGES, {key: "keep"})
        pill = CK.pill_sources(g)
        self.assertEqual(pill["tone"], "warn")
        self.assertFalse(pill.get("blocking"))

    def test_quotes_match_normalized_and_invented_quotes_fail(self):
        ok = doc(quote={"text": "having a place to go when it drops below  freezing", "ref": "P3"})
        self.assertEqual(CK.grounding(ok, PASSAGES)["missing"], [])
        bad = doc(quote={"text": "We saved every life this winter", "ref": "P3"})
        self.assertEqual(CK.grounding(bad, PASSAGES)["missing"][0]["kind"], "quote")

    def test_unknown_citation_is_flagged(self):
        d = doc(sections=[{"heading": "x", "body": "No numbers.", "refs": ["P99"]}])
        self.assertEqual(CK.grounding(d, PASSAGES)["missing"][0]["kind"], "ref")


class Pills(unittest.TestCase):
    def test_contrast_and_fonts_and_required(self):
        self.assertEqual(CK.pill_contrast({"pairs": [{"ratio": 2.0, "passes": False}]})["tone"], "bad")
        self.assertIn("Times in place of Merriweather", CK.pill_fonts([{"role": "heading", "wanted": "Merriweather", "used": "Times"}])["label"])
        self.assertEqual(CK.pill_required(["Not legal advice."], "page text")["tone"], "bad")
        self.assertIsNone(CK.pill_required([], ""))
        self.assertTrue(CK.blocking([{"blocking": True}, None]))


if __name__ == "__main__":
    unittest.main()


class PersonaFalseAlarms(unittest.TestCase):
    """Nov 8 persona run: three of five blocks were false alarms. Each is a test now."""

    P = {
        "P1": {"text": "\"I read my granddaughter a bedtime story for the first time this spring,\" said a learner at Riverside.",
               "locator": "para. 3", "source_id": "s1", "source_title": "Learner stories"},
        "P2": {"text": "Sixty-eight percent of learners who stayed 12 weeks gained a reading level. Seventy-one learners earned a credential.",
               "locator": "p. 2", "source_id": "s2", "source_title": "Program report"},
        "P3": {"text": "The board meets in October. Harborlight enrolled 1,148 adult learners. Order by phone at 555-0142.",
               "locator": "p. 1", "source_id": "s3", "source_title": "Board notes"},
    }

    def test_quote_ending_in_a_period_matches_a_source_comma(self):
        d = doc(stat=None, points=[], sections=[{"heading": "x", "body": "y", "refs": ["P3"]}],
                quote={"text": "I read my granddaughter a bedtime story for the first time this spring.", "who": "A learner", "ref": "P3"})
        g = CK.grounding(d, self.P)
        self.assertEqual(g["missing"], [])
        self.assertEqual(g["doc"]["quote"]["ref"], "P1", "the wrong citation is corrected, so the PDF cites the right source")

    def test_curly_quote_marks_and_case_do_not_decide(self):
        self.assertTrue(CK.find_quote("“I Read my granddaughter a bedtime story”", self.P, ["P1"]))

    def test_spelled_out_numbers_match_digits(self):
        d = doc(stat=None, sections=[{"heading": "Results", "body": "68 percent gained a level and 71 earned a credential.", "refs": ["P2"]}],
                points=[])
        self.assertEqual(CK.grounding(d, self.P)["missing"], [])
        self.assertEqual(K.spelled_numbers("Sixty-eight percent, two hundred and five, three million"), ["68%", "205", "3million"])

    def test_numbers_from_the_brief_are_known(self):
        d = doc(stat=None, title="Salvia Kitchen in 90 seconds", sections=[{"heading": "x", "body": "Enrolled 1,148.", "refs": ["P3"]}], points=[])
        self.assertEqual([i["value"] for i in CK.grounding(d, self.P)["missing"]], ["90"])
        g = CK.grounding(d, self.P, brief="A 90-second audio brief for the office lunch crowd")
        self.assertEqual(g["missing"], [])
        self.assertIn("1 from your request", CK.pill_sources(g)["label"])

    def test_closest_passage_searches_every_source(self):
        d = doc(stat=None, points=[], sections=[{"heading": "x", "body": "About 144 fewer people would be waiting on the literacy list.", "refs": ["P2"]}],
                quote={"text": "I read my granddaughter a bedtime story every night now", "who": "", "ref": "P2"})
        g = CK.grounding(d, self.P)
        q = [i for i in g["missing"] if i["kind"] == "quote"][0]
        self.assertEqual(q["closest"]["ref"], "P1")
        self.assertEqual(q["line"]["source"], "Learner stories")
        self.assertTrue(q["line"]["text"].startswith("\"I read my granddaughter"))

    def test_not_found_items_come_first_and_keep_their_written_form(self):
        d = doc(stat={"value": "1,148", "label": "learners", "ref": "P1"}, points=[],
                sections=[{"heading": "x", "body": "It reached 9,999 people.", "refs": ["P3"]}])
        g = CK.grounding(d, self.P)
        self.assertEqual(g["items"][0]["status"], "missing")
        self.assertEqual(g["items"][0]["shown"], "9,999")
        moved = [i for i in g["items"] if i["status"] == "moved"][0]
        self.assertEqual(moved["shown"], "1,148")
        self.assertEqual(moved["line"]["text"], "Harborlight enrolled 1,148 adult learners.")

    def test_a_phone_number_is_one_figure(self):
        self.assertEqual(K.numbers("Call 555-0142 or (405) 555-0142."), ["tel5550142", "tel4055550142"])
        d = doc(stat=None, points=[], sections=[{"heading": "x", "body": "Order by phone at 555-0142.", "refs": ["P3"]}])
        items = [i for i in CK.grounding(d, self.P)["items"] if i["kind"] == "number"]
        self.assertEqual([(i["shown"], i["status"]) for i in items], [("555-0142", "ok")])


class AnswerShape(unittest.TestCase):
    """A chat answer leads with one sentence, then about 120 words of detail, then the rest behind More."""

    def test_split(self):
        from _load import content as K
        lead = "Reserves stand at 3.2 months [1], short of the 4-month target [1]."
        para = " ".join(["Detail"] * 70) + "."
        rest = " ".join(["Later"] * 70) + "."
        got = K.split_answer(f"{lead}\n\n{para}\n\n{rest}")
        self.assertEqual(got["lead"], lead)
        self.assertEqual(got["detail"], para)
        self.assertEqual(got["more"], rest)
        self.assertEqual(K.split_answer("Yes [1].")["more"], "")

    def test_a_run_on_first_paragraph_gives_up_its_first_sentence(self):
        from _load import content as K
        text = "The budget rises $190,000 [2]. " + " ".join(["It"] * 50) + " grows. Reserves stay at 3.2 months [1]."
        got = K.split_answer(text)
        self.assertEqual(got["lead"], "The budget rises $190,000 [2].")
        self.assertTrue(got["detail"].endswith("Reserves stay at 3.2 months [1]."))

    def test_one_long_detail_paragraph_is_cut_at_a_sentence(self):
        from _load import content as K
        sent = " ".join(["word"] * 30) + "."
        got = K.split_answer("Lead [1].\n\n" + " ".join([sent] * 6))
        self.assertEqual(len(got["detail"].split()), 120)
        self.assertEqual(len(got["more"].split()), 60)

    def test_shorthand_nouns_are_caught(self):
        from _load import content as K
        self.assertTrue(K.SHORTHAND.search("Stayers make real gains"))
        self.assertFalse(K.SHORTHAND.search("Learners who stay make real gains"))


class OnePagerChart(unittest.TestCase):
    def test_the_chart_is_kept_and_checked(self):
        from _load import content as K, checks as CK
        raw = {"title": "T", "dek": "D", "sections": [{"heading": "H", "body": "B.", "refs": ["P1"]}], "points": [], "next": "N",
               "chart": {"title": "Enrollment grew in one year", "unit": "Adults",
                         "bars": [{"label": "FY2025", "value": "936", "ref": "P1"}, {"label": "FY2026", "value": "1,148", "ref": "P1", "accent": True}]}}
        doc = K.clean_onepager(raw)
        self.assertEqual(doc["chart"]["bars"][1]["accent"], True)
        passages = {"P1": {"text": "Harborlight enrolled 1,148 adult learners, up from 936 the year before.", "locator": "x", "source_title": "R", "source_id": "s"}}
        g = CK.grounding(doc, passages)
        self.assertEqual(sorted(i["value"] for i in g["items"] if i.get("path", "").startswith("chart.bars")), ["1148", "936"])
        self.assertNotIn("chart", K.clean_onepager({**raw, "chart": {"title": "x", "bars": [{"label": "a", "value": "1", "ref": "P1"}]}}))


class Caps(unittest.TestCase):
    def test_a_capped_heading_never_cuts_a_number(self):
        from _load import content as K
        h = "Salvia Kitchen grew from neighbors' parties in 2019 to a commercial kitchen in 2022"
        got = K.clean_deck({"title": "T", "subtitle": "", "slides": [
            {"type": "timeline", "heading": h, "steps": [{"when": "2019", "text": "Parties", "ref": "P1"}, {"when": "2022", "text": "Kitchen", "ref": "P1"}]},
            {"type": "section", "heading": "a"}, {"type": "section", "heading": "b"}]})["slides"][0]["heading"]
        self.assertTrue(h.startswith(got))
        self.assertFalse(got.endswith(" 2"))
        self.assertLessEqual(len(got), 80)
