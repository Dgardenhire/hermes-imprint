"""The HTML design engine: untrusted markup is cleaned, every number is traced to the passages it cites, the page is
drawn by Chrome without a network, and the loop sanitizes what the model returns (including fixes)."""
import asyncio
import json
import shutil
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, ROOT

HD = import_module(f"{PKG}.htmldeck")
P = {"P1": {"text": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five sites, up from 936 the year before."},
     "P4": {"text": "At year end, 287 adults were on the waitlist. The average wait was nine weeks."}}


class Sanitize(unittest.TestCase):
    def clean(self, raw):
        return HD.sanitize(raw)

    def test_scripts_handlers_links_frames_and_addresses_are_gone(self):
        raw = ('<div onclick="x()" style="background:url(http://e/x.png)"><script>alert(1)</script><iframe src="http://e"></iframe>'
               '<a href="http://e">go</a><img src="http://e/p.png"><img src="letterpress:logo"><form action="http://e"><input></form>'
               '<style>@import url(http://e/a.css);.s1-a{background:url(https://e/b.png)}</style><object data="x"></object>'
               '<svg><foreignObject><div>hi</div></foreignObject><use href="http://e#a"/></svg></div>')
        out, removed = self.clean(raw)
        for bad in ("<script", "alert", "<iframe", "href", "http", "onclick", "<form", "<input", "<object", "foreignobject", "@import"):
            self.assertNotIn(bad, out.lower(), bad)
        self.assertIn('src="letterpress:logo"', out)
        self.assertTrue(removed)

    def test_no_picture_but_the_logo_survives_and_brand_variables_do(self):
        px = "data:image/png;base64,iVBORw0KGgo="
        out, rm = self.clean(f'<div style="color:var(--brand)"><img src="{px}"><img src="letterpress:logo"><svg viewBox="0 0 9 9"><rect data-value="5" width="3" height="3"/></svg></div>')
        self.assertNotIn(px, out)  # a picture could carry a number nobody traces
        self.assertIn('src="letterpress:logo"', out)
        self.assertIn("var(--brand)", out)
        self.assertIn('<rect data-value="5" width="3" height="3"/>', out)
        self.assertTrue(rm)

    def test_a_number_drawn_by_css_is_removed(self):
        out, _ = self.clean('<style>.s1-a::after{content:"9,999"}</style><div class="s1-a">x</div>')
        self.assertNotIn("9,999", out)

    def test_css_escapes_do_not_hide_an_address(self):
        out, _ = self.clean('<div style="background:u\\72l(http://e/x)">x</div>')
        self.assertNotIn("http", out)


class Trace(unittest.TestCase):
    def test_sourced_numbers_pass_and_unsupported_ones_are_flagged(self):
        html = ('<h1 data-source="P1">Enrollment rose to 1,148 adults from 936</h1><p data-source="P4">287 adults wait for 99 weeks</p>'
                '<p>We served 4,321 people</p><svg><rect data-value="936" data-source="P1"/><rect data-value="777" data-source="P1"/></svg>')
        t = HD.trace([{"html": html}], P)
        bad = {f["value"] for f in t["flags"]}
        self.assertEqual(bad, {"99", "4,321", "777"})
        self.assertFalse(t["ok"])

    def test_a_worked_out_number_needs_both_sources_cited_on_its_own_element(self):
        ok = HD.trace([{"html": '<p data-source="P1">212 more learners than the year before</p>'}], P)
        self.assertTrue(ok["ok"], ok["flags"])
        bad = HD.trace([{"html": '<p data-source="P4">212 more learners than the year before</p>'}], P)
        self.assertFalse(bad["ok"])

    def test_neighbouring_elements_never_fuse_into_one_number(self):
        t = HD.trace([{"html": '<p data-source="P1"><span>936</span><span>1,148</span></p>'}], P)
        self.assertTrue(t["ok"], t["flags"])

    def test_a_number_written_as_a_word_is_a_claim_too(self):
        ok = HD.trace([{"html": '<p data-source="P4">Adults wait nine weeks on average</p>'}], P)
        self.assertTrue(ok["ok"], ok["flags"])
        bad = HD.trace([{"html": '<p data-source="P4">Adults wait twelve weeks on average</p>'}], P)
        self.assertEqual([f["value"] for f in bad["flags"]], ["twelve"])

    def test_a_slides_own_number_is_not_a_claim_but_a_lone_figure_is(self):
        self.assertTrue(HD.trace([{"html": "<p>a</p>"}, {"html": "<span>2</span>"}], P)["ok"])
        self.assertFalse(HD.trace([{"html": "<p>a</p>"}, {"html": "<span>287</span>"}], P)["ok"])

    def test_dates_and_years_need_no_source(self):
        self.assertTrue(HD.trace([{"html": "<p>October 21, FY2027, slide 3</p>"}], P)["ok"])


BRAND = {"heading": "Montserrat", "body": "Lora", "vars": {"--brand": "#0e5e6f", "--paper": "#faf7f2"},
         "fonts": [{"family": "Montserrat", "weight": 700, "file": ROOT / "fonts" / "montserrat-700.ttf"}]}


@unittest.skipUnless(Path(HD.CHROME).exists(), "needs Chrome")
class Render(unittest.TestCase):
    def test_render_measures_cut_text_and_draws_no_network(self):
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        try:
            slides = [{"html": '<div style="padding:96px;background:var(--paper);height:100%"><h1 style="font:700 80px var(--font-heading);color:var(--brand)">Hello</h1>'
                               '<p style="font-size:14px">tiny</p><img src="http://example.invalid/x.png"></div>'},
                      {"html": '<div style="width:2400px;height:300px;background:#000"></div>'}]
            slides = [{"html": HD.sanitize(s["html"])[0]} for s in slides]
            r = HD.render(slides, HD.kit_css(BRAND), out)
            self.assertEqual(len(r["png"]), 2)
            self.assertTrue(r["pdf"] and Path(r["pdf"]).stat().st_size > 1000)
            kinds = {(p["slide"], p["kind"]) for p in r["problems"]}
            self.assertIn((1, "small"), kinds)
            self.assertIn((2, "outside"), kinds)
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_the_brand_ground_logo_is_its_own_token_and_falls_back_to_the_paper_one(self):
        html = HD.sanitize('<div><img src="letterpress:logo" alt=""><img src="letterpress:logo-band" alt=""></div>')[0]
        self.assertIn("letterpress:logo-band", html)
        pg = HD.page([{"html": html}], "", {"paper": "data:image/png;base64,AAAA", "band": "data:image/png;base64,BBBB"})
        self.assertIn('src="data:image/png;base64,AAAA"', pg)
        self.assertIn('src="data:image/png;base64,BBBB"', pg)
        pg = HD.page([{"html": html}], "", "data:image/png;base64,AAAA")
        self.assertEqual(pg.count('src="data:image/png;base64,AAAA"'), 2)
        self.assertNotIn("letterpress:logo", pg)

    def test_the_page_policy_allows_no_script_but_the_measuring_one(self):
        pg = HD.page([{"html": "<p>x</p>"}], "")
        self.assertIn("script-src 'none'", pg)
        self.assertIn("default-src 'none'", pg)
        pg = HD.page([{"html": "<p>x</p>"}], "", measure=True)
        tag, digest = HD._script_tag(26, fill=True)  # decks also measure how full each slide is
        self.assertIn(f"script-src 'sha256-{digest}'", pg)


    def test_a_slide_with_an_empty_lower_half_or_an_empty_middle_band_is_flagged_and_a_full_one_is_not(self):
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        H = "position:absolute;left:96px;font:700 72px var(--font-heading);margin:0"
        foot = '<p style="position:absolute;left:96px;bottom:40px;font-size:26px;margin:0">Source: Harborlight</p>'
        try:
            top_only = f'<div style="height:100%;background:var(--paper)"><h1 style="{H};top:96px">Most adults wait nine weeks</h1><p style="position:absolute;left:96px;top:220px;font-size:32px;margin:0">At the Eastgate and Riverside sites</p>{foot}</div>'
            gap = f'<div style="height:100%"><h1 style="{H};top:96px">Most adults wait nine weeks</h1><p style="position:absolute;left:96px;bottom:110px;font-size:32px;margin:0">At the Eastgate and Riverside sites</p>{foot}</div>'
            full = (f'<div style="height:100%"><h1 style="{H};top:96px">Most adults wait nine weeks</h1>'
                    '<div style="position:absolute;left:96px;right:96px;top:260px;bottom:140px;background:var(--brand)"></div>'
                    f'<p style="position:absolute;left:96px;bottom:110px;font-size:32px;margin:0">At the Eastgate and Riverside sites</p>{foot}</div>')
            r = HD.render([{"html": HD.sanitize(h)[0]} for h in (top_only, gap, full)], HD.kit_css(BRAND), out, pdf=False)
            empty = {p["slide"] for p in r["problems"] if p["kind"] == "empty"}
            self.assertEqual(empty, {1, 2}, r["problems"])
        finally:
            shutil.rmtree(out, ignore_errors=True)

class Loop(unittest.TestCase):
    def test_an_unsafe_slide_on_the_final_round_is_blanked_and_the_outputs_are_drawn_again(self):
        class LLM:
            async def structured(self, **kw):
                return {"slides": [{"html": "<div><marquee>x</marquee><p data-source='P4'>287 adults wait</p></div>"}]}
        real_sanitize, real_render, calls = HD.sanitize, HD.render, []
        HD.sanitize = lambda m: (m, [])  # a cleaner that let it through
        HD.render = lambda *a, **k: (calls.append(1), real_render(*a, **k))[1]
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        try:
            r = asyncio.run(HD.make(LLM(), BRAND, "brand", P, "content", out, "editorial", rounds=0, kind="graphic"))
            self.assertEqual(r["slides"][0]["html"], "")
            self.assertGreaterEqual(len(calls), 2)  # drawn, found unsafe, drawn again without it
            self.assertIn("rejected", {p["kind"] for p in r["render"]["problems"]})
            self.assertTrue(r["trace"]["ok"])  # nothing left to trace: the traced text is the drawn text
            from PIL import Image  # the picture on disk is the blank slide
            im = Image.open(r["render"]["png"][0]).convert("RGB")
            self.assertEqual(len(set(im.resize((8, 8)).getdata())), 1)
        except ImportError:
            pass
        finally:
            HD.sanitize, HD.render = real_sanitize, real_render
            shutil.rmtree(out, ignore_errors=True)

    def test_the_loop_sanitizes_the_first_draft_and_the_fixes(self):
        class LLM:
            def __init__(self):
                self.n = 0

            async def structured(self, **kw):
                self.n += 1
                if kw["purpose"].endswith("write"):
                    return {"slides": [{"html": '<div onclick="x()"><script>1</script><p data-source="P4">287 adults wait</p></div>', "notes": "n"}]}
                return {"slides": [{"index": 1, "html": '<div><p data-source="P4">287 adults wait</p><a href="http://e">x</a></div>'},
                                   {"index": 9, "html": "<div>ignored</div>"}, {"index": "x"}, "bad"]}
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        try:
            r = asyncio.run(HD.make(LLM(), BRAND, "brand", P, "content", out, "editorial", rounds=1, kind="graphic"))
            self.assertEqual(len(r["slides"]), 1)
            joined = r["slides"][0]["html"]
            self.assertNotIn("href", joined)
            self.assertNotIn("onclick", joined)
            self.assertTrue(r["trace"]["ok"])
            self.assertEqual(r["slides"][0]["notes"], "n")
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_every_output_kind_has_three_distinct_directions(self):
        for kind in HD.FORMATS:
            d = HD.DIRECTIONS[kind]
            self.assertEqual(len(d), 3)
            self.assertEqual(len({v["brief"] for v in d.values()}), 3)
            for name in d:
                sysm, instr, body = HD.write_prompt("brand", "src", "content", name, kind)
                self.assertIn(str(HD.FORMATS[kind]["w"]), instr)


if __name__ == "__main__":
    unittest.main()


class Bypasses(unittest.TestCase):
    """The ways round the cleaner a security review found, each as a test."""

    def test_escaped_style_close_does_not_become_a_real_one(self):
        raw = '<style>.a{content:"x"}\\3c/style\\3e<script>alert(1)</script></style><p>t</p>'
        out, _ = HD.sanitize(raw)
        self.assertNotIn("<script", out.lower())
        self.assertNotIn("</style><", out.lower().replace("</style><p>", ""))
        self.assertEqual(out.lower().count("</style"), out.lower().count("<style"))

    def test_escaped_markup_in_a_style_attribute_is_dropped(self):
        out, rm = HD.sanitize('<div style="background:\\3c img src=x\\3e">x</div>')
        self.assertNotIn("\\3c", out)
        self.assertTrue(rm)

    def test_raw_angle_bracket_in_style_text_drops_the_block(self):
        out, _ = HD.sanitize("<style>.a{}</style><b>x</b><style>.b{}</style>")
        self.assertNotIn("<b>x</b>", out.split("</style>")[0])
        out, rm = HD.sanitize("<style>.a:after{content:'<img src=x onerror=1>'}</style><p>t</p>")
        self.assertNotIn("onerror", out)

    def test_style_inside_svg_mask_or_pattern_is_never_kept(self):
        for wrap in ("svg", "svg><mask", "svg><pattern", "svg><g"):
            raw = f"<{wrap}><style>*{{x:1}}</style><p>after</p></svg>"
            out, _ = HD.sanitize(raw)
            self.assertNotIn("<style", out, wrap)

    def test_markup_that_would_not_parse_the_same_twice_is_dropped(self):
        out, rm = HD.sanitize("<style></style  ><p>x</p>")
        self.assertIn("<p>x</p>", out)
        self.assertTrue(HD.sanitize(out)[0] == out)  # the cleaner's own output is a fixed point

    def test_css_content_numbers_counters_and_escapes(self):
        cases = ['.a::after{content:"287"}', ".a::after{content:counter(n)}", ".a{counter-reset:n 286}.a::before{counter-increment:n}",
                 '.a::after{content:"\\32 87"}', ".a::after{content:attr(data-x)}", ".a::after{content:counters(n,'.')}",
                 '.a::after{co\\6e tent:"287"}', '.a::after{coun\\74er-increment:n}', '.a::after{content:"2" "8"}']
        for css in cases:
            out, _ = HD.sanitize(f"<style>{css}</style><p class='a'>x</p>")
            low = out.lower()
            self.assertNotIn("287", low, css)
            self.assertNotIn("counter", low.replace("counter-", "x"), css)
            self.assertNotIn("attr(", low, css)
            self.assertNotRegex(low, r"content:\s*[\"'][^\"']*\d", css)

    def test_other_properties_that_end_in_content_are_left_alone(self):
        css = ".a{display:flex;justify-content:space-between;align-content:center;place-content:center}"
        out, rm = HD.sanitize(f"<style>{css}</style><p class='a'>x</p>")
        self.assertIn("justify-content:space-between", out)
        self.assertIn("align-content:center", out)
        self.assertFalse(rm)

    def test_plain_string_content_and_none_are_kept(self):
        out, rm = HD.sanitize('<style>.a::before{content:"\u201c"}.b::after{content:none}.c::after{content:"\u2014"}</style>')
        self.assertIn("content:none", out)
        self.assertIn("\u201c", out)
        self.assertFalse(rm)

    def test_any_backslash_escape_drops_the_whole_block_unrewritten(self):
        for css in ('.a{color:red}.b{co\\6e tent:"1"}', '.a{background:u\\72l(http://e/x)}', '.a{content:"\\201C"}'):
            out, rm = HD.sanitize(f"<style>{css}</style><p class='a'>x</p>")
            self.assertNotIn("<style>.", out, css)
            self.assertNotIn("color:red", out, css)  # the harmless part went with it: dropped, not repaired
            self.assertTrue(any("backslash" in r for r in rm), css)

    def test_a_nested_deletion_cannot_rebuild_a_forbidden_word(self):
        for css in (".a{width:exprexpressionession(1)}", ".a{background:url(htt@importp://e)}", ".a{x:@im@importport url(http://e)}",
                    ".a::after{content:counter(n)}"):
            out, rm = HD.sanitize(f"<style>{css}</style><p class='a'>x</p>")
            for word in ("expression(", "@import", "http", "counter("):
                self.assertNotIn(word, out.lower(), css)  # whatever is left is exactly what was written: nothing is rebuilt
            self.assertTrue(rm or "exprexpressionession" in css, css)
        self.assertEqual(HD.sanitize("<style>.a{width:exprexpressionession(1)}</style>")[0], "<style>.a{width:exprexpressionession(1)}</style>")

    def test_meta_and_base_are_stripped_at_assembly(self):
        pg = HD.page([{"html": '<meta http-equiv="refresh" content="0;url=file:///etc/passwd"><base href="file:///"><p>x</p>'}], "")
        self.assertNotIn("refresh", pg)
        self.assertNotIn("<base", pg)

    @unittest.skipUnless(Path(HD.CHROME).exists(), "needs Chrome")
    def test_the_browsers_own_parse_rejects_what_the_allowlist_never_named(self):
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        try:
            r = HD.render([{"html": "<div><marquee>x</marquee><p onclick='1'>y</p></div>"}], HD.kit_css(BRAND), out, pdf=False)
            kinds = {(p["kind"], p["what"]) for p in r["problems"]}
            self.assertIn(("unsafe", "<marquee>"), kinds)
            self.assertIn(("unsafe", "onclick"), kinds)
        finally:
            shutil.rmtree(out, ignore_errors=True)


class ForgedReports(unittest.TestCase):
    """A slide must not be able to write the measuring script's report for it."""

    class R:
        def __init__(self, err):
            self.stderr = err

    def test_the_report_needs_this_renders_nonce_one_match_and_a_console_line(self):
        n = "abc123"
        import json as _j
        body = _j.dumps([{"slide": 1, "kind": "cut", "what": "x"}])
        good = '[1:2:INFO:CONSOLE(9)] "LETTERPRESSREPORT-%s:%s:ENDREPORT-%s", source: file:///x (9)' % (n, body, n)
        self.assertEqual([p["kind"] for p in HD._read_report(self.R(good), n, 4)], ["cut"])
        self.assertEqual(HD._read_report(self.R(good), n, 4)[0]["slide"], 4)
        for err in ("", good.replace(n, "other"), good + "\n" + good, "LETTERPRESSREPORT-%s:[]:ENDREPORT-%s" % (n, n),  # not from a console line
                    '[1:2:INFO:CONSOLE(9)] "LETTERPRESSREPORT-%s:{}:ENDREPORT-%s"' % (n, n), '[1:2:INFO:CONSOLE(9)] "LETTERPRESSREPORT-%s:[bad:ENDREPORT-%s"' % (n, n)):
            got = HD._read_report(self.R(err), n, 1)
            self.assertEqual([p["kind"] for p in got], ["unsafe"], err)

    @unittest.skipUnless(Path(HD.CHROME).exists(), "needs Chrome")
    def test_a_slide_that_prints_a_clean_report_still_shows_its_overflow(self):
        out = Path(tempfile.mkdtemp(prefix="imp-test-"))
        try:
            fake = "LETTERPRESSREPORT-000000000000000000000000:[]:ENDREPORT-000000000000000000000000 LETTERPRESSREPORT:[]:ENDREPORT"
            html = f'<div><p>{fake}</p><div style="width:2600px;height:200px;background:#000"></div></div>'
            r = HD.render([{"html": HD.sanitize(html)[0]}], HD.kit_css(BRAND), out, pdf=False)
            self.assertIn("outside", {p["kind"] for p in r["problems"]})
            self.assertNotIn("no-report", {p["kind"] for p in r["problems"]})
        finally:
            shutil.rmtree(out, ignore_errors=True)


class Spawned(unittest.TestCase):
    """The browser that draws the designs is started the way subprocess uses posix_spawn (a full path, close_fds=False),
    never through fork: a forked child can crash in a macOS fork handler before it runs (see sitestyle._spawn)."""

    def test_the_drawing_browser_is_started_without_fork(self):
        from unittest import mock
        seen = {}

        def fake_run(cmd, **kw):
            seen.update(kw, cmd=cmd)
            return HD.subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.object(HD, "browser_path", lambda: "/Applications/Some Browser.app/Contents/MacOS/Some Browser"), \
                mock.patch.object(HD.subprocess, "run", fake_run):
            HD._chrome(["--version"])
        self.assertIs(seen["close_fds"], False)
        self.assertTrue(seen["cmd"][0].startswith("/"))
        self.assertNotIn("preexec_fn", seen)
