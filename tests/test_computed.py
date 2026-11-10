"""Worked-out numbers: a number no source writes passes as computed when it is one operation on two numbers in
the passages the same element cites, and the element's words name the operation. The Harborlight cases are the
product owner's acceptance table (premium-plan/imprint/lanes/ai-brief.md, section 2)."""
import unittest

from _load import checks as CK, content as K, layout as L

SRC = "FY26 Program Report"
PASSAGES = {
    "P1": {"text": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five neighborhood sites, up from 936 the "
                   "year before. Of those learners, 412 were working toward a high school equivalency credential and 389 were "
                   "English language learners.\nSixty-eight percent of learners who stayed at least 12 weeks gained one or more "
                   "reading levels on the CASAS assessment. Seventy-one learners earned a high school equivalency credential, "
                   "the most in the organization's history.",
           "locator": "Who we served", "source_id": "s1", "source_title": SRC},
    "P2": {"text": "A corps of 214 volunteer tutors gave 9,870 tutoring hours. The average tutor stayed 14 months. Harborlight "
                   "employs 11 full-time staff, including four site coordinators.",
           "locator": "Volunteers and staff", "source_id": "s1", "source_title": SRC},
    "P3": {"text": "Operating expenses for FY2026 were $1,420,000. Program costs were 81 percent of spending. Foundation grants "
                   "provided $640,000, individual donors gave $388,000, and the city's adult education contract paid "
                   "$295,000.\nThe cost per learner was $1,237.",
           "locator": "Money", "source_id": "s1", "source_title": SRC},
    "P4": {"text": "At year end, 287 adults were on the waitlist, most of them at the Eastgate and Riverside sites. The average "
                   "wait was nine weeks.", "locator": "The waitlist", "source_id": "s1", "source_title": SRC},
    "P5": {"text": "Staff recommend that the board approve an FY2027 budget of $1,610,000, which adds a sixth site at the "
                   "Eastgate branch library and two site coordinators. Staff estimate the sixth site would serve 180 more "
                   "learners a year and cut the waitlist in half.",
           "locator": "Recommendation to the board", "source_id": "s1", "source_title": SRC},
    "P8": {"text": "The treasurer reported that reserves stand at 3.2 months of operating expenses, below the board's target of "
                   "4 months.\nThe board asked staff to bring a one-page summary of the FY2027 budget request to the October 21 "
                   "board meeting.", "locator": "para. 3", "source_id": "s2", "source_title": "Board retreat notes"},
}


def page(body, refs):
    return {"title": "Harborlight in FY2026", "dek": "", "dek_refs": [], "stat": None,
            "sections": [{"heading": "This year", "body": body, "refs": refs}], "points": [], "quote": None, "next": ""}


def item(body, refs, value):
    g = CK.grounding(page(body, refs), PASSAGES)
    hits = [i for i in g["items"] if i["kind"] == "number" and i["value"] == value]
    assert hits, f"no item for {value}: {g['items']}"
    return hits[0], g


class AcceptanceTable(unittest.TestCase):
    def test_difference_212_more_adults(self):
        it, _ = item("212 more adults than last year.", ["P1"], "212")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["op"], "difference")
        self.assertEqual(it["math"]["text"], "1,148 − 936 = 212")
        self.assertEqual([o["value"] for o in it["math"]["operands"]], ["1,148", "936"])
        self.assertEqual(it["math"]["operands"][0]["line"]["match"], "1,148")
        self.assertEqual(it["ref"], "P1")

    def test_percent_change_up_23(self):
        it, _ = item("Up 23% in one year.", ["P1"], "23%")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["op"], "pct_change")
        self.assertEqual(it["math"]["text"], "(1,148 − 936) ÷ 936 = 22.6%, shown as 23%")
        self.assertEqual(it["math"]["result"], "22.6%")

    def test_planted_invented_percent_up_31_is_flagged(self):
        it, g = item("Up 31% in one year.", ["P1"], "31%")
        self.assertEqual(it["status"], "missing")
        self.assertIn(it, g["missing"])

    def test_operands_outside_the_cited_passages_never_count(self):
        it, _ = item("212 more adults than last year.", ["P4"], "212")
        self.assertEqual(it["status"], "missing")

    def test_money_difference_across_two_cited_passages(self):
        it, _ = item("$190,000 more than last year.", ["P3", "P5"], "190000")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["text"], "1,610,000 − 1,420,000 = 190,000")
        self.assertEqual({o["ref"] for o in it["math"]["operands"]}, {"P3", "P5"})

    def test_money_difference_needs_both_passages(self):
        it, _ = item("$190,000 more than last year.", ["P5"], "190000")
        self.assertEqual(it["status"], "missing")

    def test_sum(self):
        it, _ = item("Together, 801 learners were working toward a credential or learning English.", ["P1"], "801")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["op"], "sum")
        self.assertEqual(it["math"]["text"], "412 + 389 = 801")

    def test_ratio_exact(self):
        it, _ = item("Enrolled learners outnumber the waitlist 4 times over.", ["P1", "P4"], "4")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["op"], "ratio")
        self.assertEqual(it["math"]["text"], "1,148 ÷ 287 = 4")

    def test_ratio_rounded_at_the_precision_shown(self):
        it, _ = item("Each tutor gave about 46 hours on average.", ["P2"], "46")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["text"], "9,870 ÷ 214 = 46.1, shown as 46")

    def test_1200_learners_is_missing_and_the_closest_line_names_1148(self):
        it, _ = item("1,200 learners enrolled this year.", ["P1"], "1200")
        self.assertEqual(it["status"], "missing")
        self.assertEqual(it["closest"]["ref"], "P1")
        self.assertIn("1,148", it["line"]["text"])


class Precision(unittest.TestCase):
    def test_one_decimal_percent_matches_to_one_decimal(self):
        it, _ = item("Enrollment is up 22.6% on last year.", ["P1"], "22.6%")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["text"], "(1,148 − 936) ÷ 936 = 22.6%")

    def test_one_decimal_percent_that_is_off_is_missing(self):
        it, _ = item("Enrollment is up 22.9% on last year.", ["P1"], "22.9%")
        self.assertEqual(it["status"], "missing")

    def test_whole_difference_must_be_exact(self):
        it, _ = item("211 more adults than last year.", ["P1"], "211")
        self.assertEqual(it["status"], "missing")

    def test_half_up_rounding(self):
        passages = {"P9": {"text": "We had 200 members in 2024 and 245 members now.", "locator": "x", "source_id": "s9", "source_title": "T"}}
        m = CK.computed_match("23%", "23%", "Up 23% since then", passages, ["P9"])
        self.assertIsNotNone(m)  # 22.5% rounds half up to 23
        self.assertEqual(m["text"], "(245 − 200) ÷ 200 = 22.5%, shown as 23%")
        self.assertIsNone(CK.computed_match("22%", "22%", "Up 22% since then", passages, ["P9"]))


class Bounds(unittest.TestCase):
    def test_more_than_200_learners_is_a_true_bound_on_212(self):
        it, _ = item("Enrollment grew by more than 200 learners in one year.", ["P1"], "200")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["text"], "1,148 \u2212 936 = 212, shown as more than 200")

    def test_a_bound_too_far_from_the_truth_is_missing(self):
        it, _ = item("Enrollment grew by more than 100 learners in one year.", ["P1"], "100")
        self.assertEqual(it["status"], "missing")  # 212 is more than 100, but a reader hears about 100
        it, _ = item("Enrollment grew by more than 250 learners in one year.", ["P1"], "250")
        self.assertEqual(it["status"], "missing")

    def test_nearly_and_about_a_source_number(self):
        it, _ = item("Nearly 1,150 adults enrolled.", ["P1"], "1150")
        self.assertEqual(it["math"]["text"], "1,148, shown as nearly 1,150")
        it, _ = item("Nearly 1,140 adults enrolled.", ["P1"], "1140")
        self.assertEqual(it["status"], "missing")  # "nearly" means the true value is at or below it
        it, _ = item("About 1,150 adults enrolled.", ["P1"], "1150")
        self.assertEqual((it["status"], it["math"]["op"], it["math"]["text"]), ("computed", "bound", "1,148, shown as about 1,150"))
        it, _ = item("Nearly 290 adults are waiting.", ["P4"], "290")
        self.assertEqual(it["math"]["text"], "287, shown as nearly 290")


class Guards(unittest.TestCase):
    def test_no_operation_words_no_computed(self):
        it, _ = item("We counted 212 adults.", ["P1"], "212")
        self.assertEqual(it["status"], "missing")

    def test_years_are_not_operands(self):
        passages = {"P9": {"text": "In 2026 we had 2,000 visits.", "locator": "x", "source_id": "s9", "source_title": "T"}}
        self.assertIsNone(CK.computed_match("26", "26", "26 more than", passages, ["P9"]))

    def test_percents_are_not_operands(self):
        passages = {"P9": {"text": "81 percent went to programs and 19 percent to overhead.", "locator": "x", "source_id": "s9", "source_title": "T"}}
        self.assertIsNone(CK.computed_match("62", "62", "62 more than", passages, ["P9"]))

    def test_money_shown_needs_money_operands(self):
        passages = {"P9": {"text": "We served 1,610,000 meals after 1,420,000 the year before.", "locator": "x", "source_id": "s9", "source_title": "T"}}
        self.assertIsNone(CK.computed_match("$190,000", "190000", "$190,000 more than", passages, ["P9"]))

    def test_number_written_in_the_source_stays_exact(self):
        it, _ = item("936 adults the year before, and more since.", ["P1"], "936")
        self.assertEqual(it["status"], "ok")


class Dates(unittest.TestCase):
    def check(self, text, raw, want):
        a = text.index(raw)
        self.assertEqual(CK.is_date_number(text, a, a + len(raw)), want, f"{raw!r} in {text!r}")

    def test_dates_years_days_and_counters(self):
        self.check("The board votes on October 21.", "21", True)
        self.check("The board votes on 21 October.", "21", True)
        self.check("In fiscal year 2026, we grew.", "2026", True)
        self.check("See slide 4 for the chart.", "4", True)
        self.check("Doors open at 9:30 a.m.", "30", True)
        self.check("Due 10/21/2026.", "21", True)
        self.check("The 2025-26 season", "26", True)
        self.check("The 2025\u201326 season", "26", True)

    def test_grounding_never_flags_a_date(self):
        doc = page("The 2025-26 season ended March 15, and the board votes on October 21, 2026.", ["P1"])
        g = CK.grounding(doc, PASSAGES)
        self.assertEqual(g["missing"], [])  # found dates are still traced, as before; a date is never flagged

    def test_real_numbers_are_claims(self):
        self.check("287 adults were on the waitlist.", "287", False)
        self.check("Reserves stand at 3.2 months.", "3.2", False)
        self.check("The average wait was 9 weeks.", "9", False)
        self.check("We served 2,026 learners.", "2,026", False)


class Cards(unittest.TestCase):
    def test_trace_card_shows_the_math_and_the_source(self):
        doc = page("212 more adults than last year.", ["P1"])
        g = CK.grounding(doc, PASSAGES)
        idx, _rows = L.source_index(doc, PASSAGES)
        traces, resolve = CK.trace_table(g["items"], PASSAGES, idx, computed=True)
        i, n = resolve("212 more adults than last year.", "212")
        card = traces[i]
        self.assertEqual(card["status"], "computed")
        self.assertEqual(card["math"]["text"], "1,148 − 936 = 212")
        self.assertEqual((card["source"], card["locator"]), (SRC, "Who we served"))
        self.assertEqual(n, 1)

    def test_todays_pane_gets_only_the_statuses_it_knows(self):
        """desktop/src/plugin.js has trace heads for exact, close, missing, kept and brief only; an unknown status
        throws there (TRACE_HEAD[t.status] is not a function). Until lane A adds one, a worked-out number is a
        close card that still carries its math."""
        doc = page("212 more adults than last year.", ["P1"])
        g = CK.grounding(doc, PASSAGES)
        idx, _rows = L.source_index(doc, PASSAGES)
        traces, resolve = CK.trace_table(g["items"], PASSAGES, idx)
        card = traces[resolve("212 more adults than last year.", "212")[0]]
        self.assertEqual((card["status"], card["worked"]), ("close", True))
        self.assertEqual(card["math"]["text"], "1,148 \u2212 936 = 212")
        self.assertTrue(all(t["status"] in ("exact", "close", "missing", "kept", "brief") for t in traces))

    def test_sources_pill_counts_worked_out_numbers(self):
        g = CK.grounding(page("212 more adults than last year, and 936 the year before.", ["P1"]), PASSAGES)
        pill = CK.pill_sources(g)
        self.assertEqual(pill["tone"], "good")
        self.assertIn("1 worked out from them", pill["label"])


class Claims(unittest.TestCase):
    def deck(self):
        return {"title": "A sixth site for Harborlight", "subtitle": "For funders",
                "slides": [{"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "The board votes on October 21.", "refs": ["P4", "P8"]},
                           {"type": "stat", "value": "23%", "label": "more learners than last year", "context": "212 more adults than last year.", "refs": ["P1"]},
                           {"type": "stat", "value": "1,200", "label": "learners", "context": "Up 31% in one year.", "refs": ["P1"]},
                           {"type": "stat", "value": "287", "label": "still waiting", "context": "Most at Eastgate and Riverside.", "refs": ["P4"]}]}

    def test_claims_map_shapes_and_rules(self):
        doc = self.deck()
        g = CK.grounding(doc, PASSAGES)
        idx, _rows = L.source_index(doc, PASSAGES)
        frame = lambda path: int(path.split(".")[1]) + 1 if path.startswith("slides.") else 0
        claims, used, claim_of = CK.claims_map(g["items"], PASSAGES, idx, frame)
        values = {c["value"]: c for c in claims.values()}
        self.assertNotIn("21", values)  # a date is never a claim
        self.assertEqual(values["287"]["status"], "exact")
        self.assertEqual(values["287"]["slides"], [1, 4])  # one claim shared by both slides
        self.assertEqual(values["287"]["line"]["match"], "287")
        self.assertEqual(values["23%"]["status"], "computed")
        self.assertEqual(values["23%"]["kind"], "percent")
        self.assertEqual(values["212"]["math"]["text"], "1,148 − 936 = 212")
        self.assertEqual(values["212"]["math"]["operands"][0]["source_n"], values["212"]["source_n"])
        self.assertEqual(values["1,200"]["status"], "missing")
        self.assertTrue(values["1,200"]["fixable"])
        self.assertEqual(values["31%"]["status"], "missing")
        self.assertEqual(set(used), {"P1", "P4"})
        self.assertEqual(used["P4"]["slides"], [1, 4])
        self.assertEqual(claim_of("slides.1.context", "212"), [k for k, c in claims.items() if c["value"] == "212"][0])
        self.assertIsNone(claim_of("slides.0.context", "21"))
        for c in claims.values():
            self.assertEqual(set(c), {"kind", "value", "status", "ref", "source_n", "source", "locator", "line", "math", "slides", "key", "fixable"})


if __name__ == "__main__":
    unittest.main()


class HeroExhibit(unittest.TestCase):
    """The deck's main chart: two periods, the pressure number marked accent, and the worked-out change in the
    subhead, which the checker passes as computed (212 = 1,148 - 936)."""

    def setUp(self):
        from test_revise import harborlight
        self.ids, self.by_ref, self.find = harborlight()

    def raw(self):
        served, wait = self.find("enrolled 1,148"), self.find("287 adults")
        return {"title": "A sixth site", "subtitle": "For funders", "slides": [
            {"type": "section", "heading": "Who we serve"},
            {"type": "exhibit", "heading": "Exhibit 1: Demand is outgrowing our seats", "subhead": "212 more adults than last year.",
             "unit": "Adults", "refs": [served, wait],
             "bars": [{"label": "FY2025", "value": "936", "ref": served, "accent": False},
                      {"label": "FY2026", "value": "1,148", "ref": served, "accent": False},
                      {"label": "Waiting at year end", "value": "287", "ref": wait, "accent": True},
                      {"label": "Extra", "value": "71", "ref": served, "accent": True}]},
            {"type": "closing", "heading": "Fund the sixth site", "text": "Every seat shortens the wait."}]}

    def test_clean_keeps_one_accent_and_the_subhead_and_drops_the_eyebrow(self):
        ex = K.clean_deck(self.raw())["slides"][1]
        self.assertEqual(ex["heading"], "Demand is outgrowing our seats")
        self.assertEqual(ex["subhead"], "212 more adults than last year")
        self.assertEqual([b.get("accent", False) for b in ex["bars"]], [False, False, True, False])
        self.assertEqual([b["label"] for b in ex["bars"][:2]], ["FY2025", "FY2026"])

    def test_212_in_the_subhead_is_computed(self):
        doc = K.clean_deck(self.raw())
        g = CK.grounding(doc, self.by_ref)
        it = next(i for i in g["items"] if i.get("path") == "slides.1.subhead" and i["value"] == "212")
        self.assertEqual(it["status"], "computed")
        self.assertEqual(it["math"]["op"], "difference")
        self.assertFalse(any(i.get("value") in ("2025", "2026") for i in g["items"]))  # FY2025 is a label, not a claim

    def test_the_voice_pass_keeps_the_accent_and_may_reword_the_subhead(self):
        doc = K.clean_deck(self.raw())
        voiced = K.clean_deck(self.raw())
        voiced["slides"][1]["subhead"] = "That is 212 more adults than the year before"
        voiced["slides"][1]["bars"][2].pop("accent")
        merged, reverted = K.keep_facts(doc, voiced)
        self.assertEqual(merged["slides"][1]["subhead"], "That is 212 more adults than the year before")
        self.assertTrue(merged["slides"][1]["bars"][2]["accent"])
        voiced["slides"][1]["subhead"] = "300 more adults than last year"
        merged, reverted = K.keep_facts(doc, voiced)
        self.assertIn("slides.1.subhead", reverted)

    def test_a_deck_from_an_outline_takes_its_titles(self):
        doc = K.clean_deck(self.raw())
        outline = {"slides": [{"title": "Harborlight serves adults", "type": "section"},
                              {"title": "Need for seats is outgrowing our sites", "type": "exhibit"},
                              {"title": "Fund the sixth site this year", "type": "closing"}]}
        got = K.apply_outline(doc, outline)
        self.assertEqual([s["heading"] for s in got["slides"]], [o["title"] for o in outline["slides"]])
        self.assertIn("THE OUTLINE", K.instructions_for("deck", "For funders", outline))
        self.assertIn("2. [exhibit] Need for seats is outgrowing our sites", K.instructions_for("deck", "For funders", outline))
        short = {"slides": outline["slides"][:2]}
        self.assertEqual(K.apply_outline(doc, short), doc)  # a different count keeps the model's slides


class SeasonsAreNeverWorkedOut(unittest.TestCase):
    def test_the_second_half_of_a_season_is_a_date_not_a_difference(self):
        passages = {"P1": {"text": "Staff moved 64 guests into housing, up from 29 the season before, and 38 found shelter.",
                           "locator": "Housing", "source_title": "Report", "source_id": "s1"}}
        doc = {"title": "T", "subtitle": "", "slides": [{"type": "exhibit", "heading": "Housing moves rose", "refs": ["P1"],
                                                         "bars": [{"label": "2024-25 season", "value": "29", "ref": "P1"},
                                                                  {"label": "2025-26 season", "value": "64", "ref": "P1"}]}]}
        g = CK.grounding(doc, passages)
        st = {(i["path"], i["value"]): i["status"] for i in g["items"]}
        self.assertEqual(st[("slides.0.bars.1", "26")], "date")
        self.assertEqual(st[("slides.0.bars.0", "25")], "date")
        self.assertEqual(st[("slides.0.bars.1", "64")], "ok")
        self.assertEqual(CK.pill_sources(g)["label"].count("worked out"), 0)


class FiguresOnStats(unittest.TestCase):
    def test_a_spelled_stat_value_is_set_in_figures_and_still_matches(self):
        self.assertEqual(K.as_figure("Seventy-one"), "71")
        self.assertEqual(K.as_figure("Sixty-eight percent"), "68%")
        self.assertEqual(K.as_figure("nine weeks"), "nine weeks")
        self.assertEqual(K.as_figure("1,148"), "1,148")
        doc = K.clean_deck({"title": "T", "subtitle": "", "slides": [{"type": "stat", "value": "Seventy-one", "label": "earned a credential", "refs": ["P1"]},
                                                                    {"type": "section", "heading": "a"}, {"type": "section", "heading": "b"}]})
        self.assertEqual(doc["slides"][0]["value"], "71")
        passages = {"P1": {"text": "Seventy-one learners earned a high school equivalency credential.", "locator": "x", "source_title": "R", "source_id": "s"}}
        g = CK.grounding(doc, passages)
        self.assertEqual([i["status"] for i in g["items"] if i["value"] == "71"], ["ok"])


class RaiseByCue(unittest.TestCase):
    def test_raise_by_names_a_difference(self):
        by = {"P3": {"text": "Operating expenses in FY2026 were $1,420,000.", "locator": "Money"},
              "P5": {"text": "Staff recommend an FY2027 budget of $1,610,000.", "locator": "Rec"}}
        ok = CK.check_line("Can the board raise spending by $190,000, from $1,420,000 to $1,610,000?", ["P3", "P5"], by)
        bad = CK.check_line("Can the board raise spending by $230,000, from $1,420,000 to $1,610,000?", ["P3", "P5"], by)
        self.assertEqual(ok["items"][0]["status"], "computed")
        self.assertEqual(bad["items"][0]["status"], "missing")
