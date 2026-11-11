"""Nov 10 fixes: finding a browser on any system, stale 'writing' designs, and the shorter design loop."""
import asyncio
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

from _load import PKG, ROOT, jobs, reset, service, store

B = import_module(f"{PKG}.browser")
HD = import_module(f"{PKG}.htmldeck")
D = import_module(f"{PKG}.designs")
SS = import_module(f"{PKG}.sitestyle")


class BrowserLookup(unittest.TestCase):
    def find(self, plat, have=(), on_path=(), env=None):
        have, on_path = set(have), dict(on_path)
        return B.find(platform=plat, environ=env or {"HOME": "/Users/x"}, exists=lambda p: p in have, which=lambda n: on_path.get(n))

    def test_mac_prefers_chrome_then_chromium_edge_brave(self):
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        edge = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        brave = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        self.assertEqual(self.find("mac", [chrome, edge]), chrome)
        self.assertEqual(self.find("mac", [brave, edge]), edge)
        self.assertEqual(self.find("mac", [brave]), brave)

    def test_mac_per_user_applications_folder(self):
        p = "/Users/x/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        self.assertEqual(self.find("mac", [p]), p)

    def test_windows_program_files_and_edge(self):
        env = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)", "LOCALAPPDATA": r"C:\Users\x\AppData\Local"}
        cands = B.candidates("win", env)
        self.assertTrue(any(c.endswith("chrome.exe") and "Program Files (x86)" in c for c in cands))
        edge = next(c for c in cands if c.endswith("msedge.exe"))
        self.assertEqual(self.find("win", [edge], env=env), edge)
        local = next(c for c in cands if "AppData" in c and c.endswith("chrome.exe"))
        self.assertEqual(self.find("win", [local], env=env), local)

    def test_linux_names_on_path(self):
        self.assertEqual(self.find("linux", on_path={"chromium-browser": "/usr/bin/chromium-browser"}), "/usr/bin/chromium-browser")
        self.assertEqual(self.find("linux", on_path={"microsoft-edge": "/usr/bin/microsoft-edge", "brave-browser": "/usr/bin/b"}), "/usr/bin/microsoft-edge")
        self.assertEqual(self.find("linux", on_path={"google-chrome": "/opt/gc", "chromium": "/usr/bin/chromium"}), "/opt/gc")

    def test_environment_override_wins_and_a_bad_one_falls_through(self):
        env = {"HOME": "/Users/x", B.ENV_VAR: "/opt/mybrowser/chrome"}
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        self.assertEqual(self.find("mac", ["/opt/mybrowser/chrome", chrome], env=env), "/opt/mybrowser/chrome")
        self.assertEqual(self.find("mac", [chrome], env=env), chrome)  # the override points nowhere: use the usual places

    def test_nothing_found_is_none_and_the_message_says_what_to_do(self):
        self.assertIsNone(self.find("linux"))
        self.assertIn("IMPRINT_BROWSER", B.NOT_FOUND)
        self.assertIn("Template version", B.NOT_FOUND)

    def test_sitestyle_uses_the_same_lookup(self):
        orig = B.find
        B.find = lambda *a, **k: "/x/browser"
        try:
            self.assertEqual(SS.find_chrome(), "/x/browser")
        finally:
            B.find = orig

    def test_a_missing_browser_stops_a_draw_with_a_plain_message(self):
        orig = B.find
        B.find = lambda *a, **k: None
        try:
            with self.assertRaises(HD.NoBrowser) as cm:
                HD._chrome(["--version"])
            self.assertIsInstance(cm.exception, ValueError)
            self.assertFalse(HD.browser_available())
        finally:
            B.find = orig


class StaleWriting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reset()
        st = service.open_sample()
        cls.oid = next(o["id"] for o in st["outputs"] if o["kind"] == "deck")

    def seed(self, status="writing"):
        D.save(self.oid, {"kit_id": "x", "kind": "deck", "final": None, "versions": [], "kept": [],
                          "options": {d: {"status": status, "step": "fixing, round 1"} for d in D.DIRS}})

    def test_a_dead_run_is_marked_interrupted_and_the_button_is_free(self):
        self.seed()
        v = D.view(self.oid)
        self.assertFalse(v["building"])
        for o in v["options"]:
            self.assertEqual(o["status"], "failed")
            self.assertEqual(o["error"], "Interrupted. Press Design three options again.")

    def test_finished_options_are_left_alone(self):
        self.seed()
        st = D.load(self.oid)
        st["options"]["editorial"] = {"status": "ready", "slides": [], "step": ""}
        D.save(self.oid, st)
        self.assertEqual(D.reconcile(self.oid), 2)
        self.assertEqual(D.load(self.oid)["options"]["editorial"]["status"], "ready")

    def test_a_live_job_keeps_its_writing_state(self):
        self.seed()
        orig = jobs.live
        jobs.live = lambda kind, oid: True
        try:
            self.assertEqual(D.reconcile(self.oid), 0)
            self.assertTrue(D.view(self.oid)["building"])
        finally:
            jobs.live = orig

    def test_startup_pass_covers_every_output_on_disk(self):
        self.seed()
        self.assertGreaterEqual(D.reconcile_all(), 3)
        self.assertEqual(D.reconcile_all(), 0)


W = {1: "aa", 2: "bb", 3: "cc", 4: "dd", 5: "ee"}  # words, not digits: a bare number would be traced and flagged


class FakeLLM:
    def __init__(self, changes):
        self.calls = []
        self.changes = changes  # list per fix call: slide numbers the "model" rewrites

    async def structured(self, **kw):
        self.calls.append(kw)
        if kw["purpose"] == "htmldeck.write":
            return {"slides": [{"html": f"<div><h1>slide {W[i]}</h1></div>", "notes": ""} for i in (1, 2, 3, 4)]}
        n = len([c for c in self.calls if c["purpose"] == "htmldeck.fix"])
        ch = self.changes[min(n - 1, len(self.changes) - 1)]
        return {"slides": [{"index": i, "html": f"<div><h1>fixed {W[i]} round {W[n]}</h1></div>"} for i in ch]}


class ShorterLoop(unittest.TestCase):
    def run_make(self, problems_by_round, changes, rounds=2):
        """problems_by_round: list of dicts {slide: kind} for each render, last one repeating."""
        out = Path(tempfile.mkdtemp(prefix="imp-loop-"))
        draws = []
        orig = HD.render_safe

        def fake(slides, css, out_dir, logo="", kind="deck", pdf=False, only=None):
            k = len(draws)
            draws.append(None if only is None else sorted(only))
            drawn = range(1, len(slides) + 1) if only is None else only
            pngs = []
            for i in drawn:
                p = Path(out_dir) / f"s{i:02d}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"\x89PNG")
                pngs.append(str(p))
            spec = problems_by_round[min(k, len(problems_by_round) - 1)]
            return {"png": pngs, "pdf": None, "problems": [{"slide": s, "kind": kind_, "what": "x"} for s, kind_ in spec.items() if s in drawn or only is None]}
        HD.render_safe = fake
        llm = FakeLLM(changes)
        brand = {"heading": "Arial", "body": "Georgia", "vars": {"--brand": "#123456", "--paper": "#ffffff", "--ink": "#000000"}, "fonts": []}
        try:
            r = asyncio.run(HD.make(llm, brand, "brand", {"P1": {"text": "t"}}, "content", out, "editorial", "", rounds, "deck"))
        finally:
            HD.render_safe = orig
        return r, llm, draws

    def fixes(self, llm):
        return [c for c in llm.calls if c["purpose"] == "htmldeck.fix"]

    def test_stops_after_the_first_look_when_the_fix_leaves_nothing(self):
        r, llm, draws = self.run_make([{}], [[2]])
        self.assertEqual(len(self.fixes(llm)), 1)
        self.assertEqual(draws, [None, [2]])  # only the changed slide is drawn again
        self.assertEqual(r["rounds"], 1)

    def test_the_first_look_is_always_taken_even_when_the_measuring_is_clean(self):
        r, llm, draws = self.run_make([{}], [[]])
        self.assertEqual(len(self.fixes(llm)), 1)  # the model still looks at the pictures once
        self.assertEqual(len(self.fixes(llm)[0]["images"]), 4)

    def test_a_fix_that_changes_nothing_ends_the_loop(self):
        r, llm, _ = self.run_make([{1: "overlap"}], [[]])
        self.assertEqual(len(self.fixes(llm)), 1)

    def test_extra_rounds_stop_when_the_hard_problems_are_not_going_down(self):
        r, llm, _ = self.run_make([{1: "overlap"}], [[1]], rounds=1)
        self.assertEqual(len(self.fixes(llm)), 1)  # the old loop ran three more

    def test_extra_rounds_continue_while_each_round_helps_and_are_capped_at_two(self):
        seq = [{1: "overlap", 2: "cut", 3: "cut", 4: "cut"}, {1: "overlap", 2: "cut", 3: "cut"}, {1: "overlap", 2: "cut"}, {1: "overlap"}, {1: "cut"}]
        r, llm, _ = self.run_make(seq, [[1, 2, 3, 4]] * 4, rounds=1)
        self.assertEqual(len(self.fixes(llm)), 3)  # 1 + the two extra

    def test_later_rounds_send_only_the_slides_that_still_have_problems(self):
        seq = [{1: "overlap", 2: "overlap", 3: "cut"}, {2: "overlap", 3: "cut"}, {3: "cut"}, {}]
        r, llm, draws = self.run_make(seq, [[1, 2, 3], [2, 3], [3]], rounds=3)
        f = self.fixes(llm)
        self.assertEqual(len(f[0]["images"]), 4)
        self.assertEqual(len(f[1]["images"]), 2)
        self.assertEqual(len(f[2]["images"]), 1)
        self.assertNotIn("fixed aa", f[2]["body"])
        self.assertNotIn("fixed bb", f[2]["body"])
        self.assertIn("fixed cc", f[2]["body"])
        self.assertIn("Only slide 3", f[2]["instructions"])
        self.assertLess(f[2]["max_tokens"], f[0]["max_tokens"])


@unittest.skipUnless(Path(HD.CHROME).exists(), "needs Chrome")
class DrawSubset(unittest.TestCase):
    def test_only_the_named_slides_are_drawn_and_reported(self):
        import shutil
        out = Path(tempfile.mkdtemp(prefix="imp-only-"))
        try:
            brand = {"heading": "Arial", "body": "Georgia", "vars": {"--brand": "#123456", "--paper": "#ffffff", "--ink": "#000000"}, "fonts": []}
            slides = [{"html": f"<div><h1>slide {w}</h1></div>"} for w in ("aa", "bb", "cc")]
            full = HD.render_safe(slides, HD.kit_css(brand), out)
            self.assertEqual(len(full["png"]), 3)
            mtimes = {Path(p).name: Path(p).stat().st_mtime_ns for p in full["png"]}
            part = HD.render_safe(slides, HD.kit_css(brand), out, only=[2])
            self.assertEqual([Path(p).name for p in part["png"]], ["s02.png"])
            self.assertEqual(Path(out / "s01.png").stat().st_mtime_ns, mtimes["s01.png"])  # untouched
        finally:
            shutil.rmtree(out, ignore_errors=True)


class Screen(unittest.TestCase):
    """What the Designs screen is told, and its source."""
    @classmethod
    def setUpClass(cls):
        reset()
        st = service.open_sample()
        cls.oid = next(o["id"] for o in st["outputs"] if o["kind"] == "deck")

    def test_the_view_says_plainly_when_no_browser_is_found(self):
        orig = B.find
        B.find = lambda *a, **k: None
        try:
            v = D.view(self.oid)
        finally:
            B.find = orig
        self.assertFalse(v["browser"]["ok"])
        self.assertIn("Install Google Chrome", v["browser"]["message"])

    def test_a_design_job_refuses_up_front_without_a_browser(self):
        orig = B.find
        B.find = lambda *a, **k: None
        try:
            j = jobs.start("designs", f"designs:{self.oid}:nobrowser", {"output_id": self.oid, "kit_id": "x"}, wait=True)
        finally:
            B.find = orig
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "failed")
        self.assertIn("IMPRINT_BROWSER", j["error"])

    def test_a_running_design_reports_how_long_it_has_been_going(self):
        import time
        D.save(self.oid, {"kit_id": "x", "kind": "deck", "final": None, "versions": [], "kept": [],
                          "options": {d: {"status": "writing", "step": "writing", "t0": time.time() - 130} for d in D.DIRS}})
        orig = jobs.live
        jobs.live = lambda kind, oid: True
        try:
            v = D.view(self.oid)
        finally:
            jobs.live = orig
        self.assertTrue(all(125 <= o["elapsed"] <= 140 for o in v["options"]))

    def test_slide_number_badges_sit_beside_the_picture_never_over_it(self):
        src = (ROOT / "desktop" / "src" / "designs.js").read_text()
        import re
        for sel in (".ip-ds-n", ".ip-ds-from"):
            rule = re.search(re.escape(sel) + r"\{([^}]*)\}", src).group(1)
            self.assertNotIn("position:absolute", rule, sel)
            self.assertNotIn("rgba(0,0,0", rule, sel)
        self.assertIn("flex-direction:column", re.search(r"\.ip-ds-thumb\{([^}]*)\}", src).group(1))
        self.assertNotIn("top:4px", re.search(r"\.ip-ds-tick\{([^}]*)\}", src).group(1))  # the tick no longer covers the slide's corner

    def test_the_built_bundle_carries_the_fix(self):
        bundle = (ROOT / "desktop" / "plugin.js").read_text()
        self.assertIn(".ip-ds-n{position:static", bundle)
        self.assertIn("ip-ds-nobrowser", bundle)


class AudioBar(unittest.TestCase):
    def css(self, sel):
        import re
        src = (ROOT / "desktop" / "src" / "plugin.js").read_text()
        return re.search(re.escape(sel) + r"\{([^}]*)\}", src).group(1)

    def test_the_not_recorded_bar_sits_in_the_flow_above_the_script(self):
        off = self.css(".imp-player.is-off")
        self.assertIn("position:relative", off)
        self.assertNotIn("sticky", off)
        self.assertIn("z-index:auto", off)
        self.assertIn("z-index:0", self.css(".imp-player+.imp-proof"))  # the script never paints over the bar, nor the bar over it

    def test_the_recorded_bar_sticks_below_the_real_header_height_not_a_guess(self):
        top = self.css(".imp-player")
        self.assertIn("var(--imp-head-h", top)
        self.assertNotIn("top:64px", top)
        src = (ROOT / "desktop" / "src" / "plugin.js").read_text()
        self.assertIn("--imp-head-h", src.split("function Viewer")[1] if "function Viewer" in src else src)

    def test_the_built_bundle_has_it(self):
        self.assertIn("--imp-head-h", (ROOT / "desktop" / "plugin.js").read_text())


class WebsiteColors(unittest.TestCase):
    """'Build from a website' puts the brand's dominant colors first and keeps error reds and small buttons in their place."""
    F = ROOT / "tests" / "fixtures"

    def draft(self, name, url):
        sitekit = import_module(f"{PKG}.sitekit")
        return sitekit.draft_from((self.F / f"{name}.html").read_text(), [(self.F / f"{name}.css").read_text()], url, "Nov 10, 2026")

    def roles(self, d):
        return {c["hex"]: c["role"] for c in d["colors"]}

    def test_navy_and_gold_site_gets_navy_for_the_head_not_the_error_red(self):
        d = self.draft("site_navy_gold", "https://harborvane.example/")
        by = {c["role"]: c["hex"] for c in d["colors"]}
        self.assertEqual(by["head"], "#002147")
        self.assertNotIn("#dc2626", [c["hex"] for c in d["colors"]])
        self.assertIn("#c2a05b", [c["hex"] for c in d["colors"]])  # the gold is kept
        self.assertEqual(d["paper"], "#f4f1ea")  # the cream the page sits on, not the white of text on dark

    def test_the_kit_made_from_it_heads_in_navy(self):
        S = import_module(f"{PKG}.imports")
        kits = import_module(f"{PKG}.kits")
        did = S.from_site_draft(self.draft("site_navy_gold", "https://harborvane.example/"), "https://harborvane.example/")
        kit = S._row(did)["kit"] if hasattr(S, "_row") else None
        self.assertIsNotNone(kit)
        pal = kits.palette(kit)
        self.assertEqual(pal["head"], "#002147")

    def test_a_python_org_style_site_stays_blue_and_yellow(self):
        d = self.draft("site_python_style", "https://pythonic.example/")
        by = {c["role"]: c["hex"] for c in d["colors"]}
        self.assertEqual(by["head"], "#3776ab")
        hexes = [c["hex"] for c in d["colors"]]
        self.assertIn("#ffd43b", hexes)
        self.assertNotIn("#c0392b", hexes)

    def test_a_color_used_only_in_alerts_and_buttons_does_not_become_the_head_even_when_it_is_the_most_repeated(self):
        sitekit = import_module(f"{PKG}.sitekit")
        css = "body{background:#fff;color:#111}.site-header{background:#123a6b}h1{color:#123a6b}" + "".join(
            f".error-{n}{{color:#d11}}.btn-x{n}{{background:#d11;border-color:#d11}}" for n in range(12))
        d = sitekit.draft_from("<p>x</p>", [css], "https://a.example", "today")
        self.assertEqual({c["role"]: c["hex"] for c in d["colors"]}["head"], "#123a6b")

    def test_variables_count_for_every_place_they_are_used(self):
        sitekit = import_module(f"{PKG}.sitekit")
        css = (":root{--brand:#123a6b;--alert:#d11}body{background:#fff}.site-header{background:var(--brand)}h1{color:var(--brand)}"
               ".hero{background:var(--brand)}.x1{color:#d11}.x2{color:#d11}.x3{color:#d11}.x4{color:#d11}.x5{color:#d11}")
        d = sitekit.draft_from("<p>x</p>", [css], "https://a.example", "today")
        self.assertEqual({c["role"]: c["hex"] for c in d["colors"]}["head"], "#123a6b")

    def test_a_site_whose_only_color_is_red_still_gets_red(self):
        sitekit = import_module(f"{PKG}.sitekit")
        d = sitekit.draft_from("<p>x</p>", ["body{background:#fff;color:#111}h1{color:#b3202a}.site-header{background:#b3202a}"], "https://a.example", "today")
        self.assertEqual({c["role"]: c["hex"] for c in d["colors"]}["head"], "#b3202a")


class HostileStylesheet(unittest.TestCase):
    def finish(self, css, limit=1.5):
        import gc
        import time
        sitekit = import_module(f"{PKG}.sitekit")
        # This thread's CPU time with the collector paused, not the wall clock: under load the wall clock also
        # counted other programs and full collections (the same flake as test_imports.Css, Nov 11).
        gc.collect()
        gc.disable()
        try:
            t = time.thread_time()
            sitekit.draft_from("<p>x</p>", [css], "https://a.example", "today")
            took = time.thread_time() - t
        finally:
            gc.enable()
        self.assertLess(took, limit)

    def test_a_200kb_selector_is_cut_before_matching(self):
        self.finish("body{background:#fff;color:#111}h1{color:#123a6b}" + ("a-" * 100000) + "header{background:#123a6b}")
        self.finish("." + "header-" * 30000 + "{color:#123a6b}" + "," .join(["x"] * 5000) + "{color:#111}")

    def test_thousands_of_declarations_and_rules(self):
        self.finish("body{background:#fff}" + "".join(f".a{n}{{color:#12{n % 10}a6b;background:#00{n % 10}447}}" for n in range(40000)))
        self.finish(".x{" + "color:#123a6b;" * 60000 + "}")


@unittest.skipUnless(Path(HD.CHROME).exists(), "needs Chrome")
class ShapesOverText(unittest.TestCase):
    """Live run, Nov 10 evening: a 68% dot grid drew 106 dots and its last row sat on the caption. The overlap check
    only compared text with text, so the fix loop never saw it. A small shape over text is now an overlap; text placed
    wholly inside a shape (a label in a badge) still passes."""

    BRAND = {"heading": "Arial", "body": "Georgia", "vars": {"--brand": "#0e5e6f", "--rule": "#c8c6c0", "--paper": "#ffffff", "--ink": "#000000"}, "fonts": []}

    def draw(self, html):
        import shutil
        out = Path(tempfile.mkdtemp(prefix="imp-shape-"))
        try:
            r = HD.render([{"html": html}], HD.kit_css(self.BRAND), out, pdf=False)
            return [p for p in r["problems"] if p["kind"] == "overlap"]
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_a_dot_grid_spilling_onto_its_caption_is_an_overlap(self):
        dots = "<i></i>" * 106
        html = ("<div><style>.g{position:absolute;left:96px;top:220px;display:grid;grid-template-columns:repeat(10,52px);gap:14px}"
                ".g i{display:block;width:52px;height:52px;border-radius:50%;background:var(--rule)}"
                ".c{position:absolute;left:96px;top:896px;font-size:30px}</style>"
                f"<div class='g'>{dots}</div><p class='c'>Filled dots: learners who gained a level.</p></div>")
        found = self.draw(html)
        self.assertTrue(found, "the dots over the caption were not reported")
        self.assertIn("Filled dots", found[0]["what"])

    def test_a_label_inside_a_badge_and_a_grid_that_fits_pass(self):
        dots = "<i></i>" * 100
        html = ("<div><style>.g{position:absolute;left:96px;top:220px;display:grid;grid-template-columns:repeat(10,52px);gap:14px}"
                ".g i{display:block;width:52px;height:52px;border-radius:50%;background:var(--rule)}"
                ".c{position:absolute;left:96px;top:896px;font-size:30px}"
                ".b{position:absolute;left:1200px;top:300px;width:90px;height:90px;border-radius:50%;background:var(--brand);"
                "display:flex;align-items:center;justify-content:center}.b span{color:#fff;font-size:30px}</style>"
                f"<div class='g'>{dots}</div><p class='c'>Filled dots: learners who gained a level.</p>"
                "<div class='b'><span>68</span></div></div>")
        self.assertEqual(self.draw(html), [])


class RoutesLoadOnce(unittest.TestCase):
    """Live, Nov 10 after a restart: "module 'imprint_revise_api' has no attribute 'mount'" on /state and /chats, sent
    together. The route loader registered the module before it finished loading, so the second request got a half-loaded
    one, and every call failed until Hermes restarted."""

    def check(self, owner, name):
        import sys
        import threading
        import types
        mod = import_module(f"{PKG}.{owner}")
        sys.modules[name] = types.ModuleType(name)  # a half-loaded leftover: no mount
        got, errors = [], []

        def load():
            try:
                got.append(mod.routes())
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)
        threads = [threading.Thread(target=load) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(got), 8)
        self.assertTrue(all(hasattr(m, "mount") for m in got))
        self.assertEqual(len({id(m) for m in got}), 1)

    def test_revise_routes(self):
        self.check("revise", "imprint_revise_api")

    def test_designs_routes(self):
        self.check("designs", "imprint_designs_api")
