"""Studio screenshots of the three designs and a mixed deck, at 1280 and 1440, light and dark.

    /usr/bin/python3 harness/shoot_studio.py OUT_DIR [PORT]

Seeds a data folder with the Harborlight sample and recorded designs (harness/designs-harborlight.json: written by a model,
cleaned, drawn and traced here, no model call), starts the live harness server on it, drives the page in headless Chromium
(muted) and writes PNGs. Never touches ~/.hermes, never runs a hermes command."""
import json, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8821
DATA = Path(tempfile.mkdtemp(prefix="imprint-studio-shots-"))

seed = f'''
import os, sys, json
sys.path.insert(0, {str(ROOT / "tests")!r})
from importlib import import_module
from _load import service, store
os.environ["IMPRINT_DATA_DIR"] = {str(DATA)!r}
D = import_module("imprint_plugin_package.designs")
st = service.open_sample()
kit = (store.get_setting("prefs", {{}}) or {{}}).get("kit")
rec = json.load(open({str(ROOT / "harness" / "designs-harborlight.json")!r}))
ids = {{o["kind"]: o["id"] for o in st["outputs"]}}
for kind in ("deck", "onepager"):
    D.seed(ids[kind], kit, rec[kind])
brief_path = os.environ.get("BRIEF_JSON")
if brief_path and os.path.exists(brief_path):
    k = import_module("imprint_plugin_package.kits").save_new({{"name": "Site look", "colors": [{{"hex": "#c2a05b", "role": "accent"}}, {{"hex": "#001e42", "role": "head"}}],
        "paper": "#f3efe7", "ink": "#001028", "style_brief": json.load(open(brief_path))}})
    ids["kit"] = k["id"]
print(json.dumps(ids))
'''
r = subprocess.run(["/usr/bin/python3", "-c", seed], capture_output=True, text=True, cwd=str(ROOT))
if r.returncode:
    print(r.stderr[-2000:]); sys.exit(1)
IDS = json.loads(r.stdout.strip().splitlines()[-1])
srv = subprocess.Popen(["/usr/bin/python3", str(ROOT / "harness/live/server.py"), str(PORT), "--data", str(DATA), "--voice-stub"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/harness/index.html", timeout=2); break
        except Exception:
            time.sleep(0.5)
    API = f"http://127.0.0.1:{PORT}/api/"

    def call(path, body=None):
        req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None, method="POST" if body is not None else "GET", headers={"content-type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=120).read())

    from playwright.sync_api import sync_playwright
    SIZES = [(1280, 800, "light"), (1280, 800, "dark"), (1440, 900, "light"), (1440, 900, "dark")]
    errs = []

    def open_designs(b, w, h, theme):
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"http://127.0.0.1:{PORT}/harness/index.html?live=1&theme={theme}")
        pg.wait_for_selector(".imp-nb", timeout=30000)
        pg.wait_for_timeout(800)
        pg.evaluate(f"import('/desktop/plugin.js').then(m => m.designsFor('{IDS['deck']}'))")
        pg.wait_for_selector(".ip-ds-thumb img", timeout=30000)
        pg.wait_for_timeout(1200)
        return pg

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--mute-audio", "--autoplay-policy=user-gesture-required"])
        for w, h, theme in SIZES:
            pg = open_designs(b, w, h, theme)
            pg.screenshot(path=str(OUT / f"studio-three-options-{w}-{theme}.png"))
            pg.close()
        # mix: slide 1 and 2 from Editorial, 3 and 4 from Data board, the rest from Statement
        v = call(f"outputs/{IDS['deck']}/designs")
        n = len(v["final"]["slides"])
        picks = [{"d": "editorial" if i <= 2 else "databoard" if i <= 4 else "statement", "i": i} for i in range(1, n + 1)]
        call(f"outputs/{IDS['deck']}/designs/pick", {"picks": picks})
        for w, h, theme in SIZES:
            pg = open_designs(b, w, h, theme)
            pg.evaluate("document.querySelector('.ip-ds-mine').scrollIntoView({block:'start'})")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=str(OUT / f"studio-mixed-deck-{w}-{theme}.png"))
            small = pg.evaluate("""[...document.querySelectorAll('.ip-ds *')].filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && e.getClientRects().length && parseFloat(getComputedStyle(e).fontSize) < 12).map(e => e.textContent.trim().slice(0, 30)).slice(0, 5)""")
            if small: print("UNDER 12px", w, theme, small)
            sel = pg.evaluate("document.querySelectorAll('.imp select').length")
            if sel: print("native select present", w, theme)
            pg.close()
        if "kit" in IDS:
            for w, h, theme in SIZES[:4]:
                pg = b.new_page(viewport={"width": w, "height": h})
                pg.goto(f"http://127.0.0.1:{PORT}/harness/index.html?live=1&theme={theme}")
                pg.wait_for_selector(".imp-nb", timeout=30000)
                pg.evaluate(f"import('/desktop/plugin.js').then(m => m.openKit('{IDS['kit']}'))")
                pg.wait_for_selector("[aria-label='Style brief']", timeout=20000)
                pg.evaluate("document.querySelector(\"[aria-label='Style brief']\").scrollIntoView({block:'start'})")
                pg.wait_for_timeout(900)
                pg.screenshot(path=str(OUT / f"studio-style-brief-{w}-{theme}.png"))
                pg.close()
        b.close()
    print("page errors:", errs[:3])
finally:
    srv.terminate()
    import shutil; shutil.rmtree(DATA, ignore_errors=True)
