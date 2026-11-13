"""Harborlight through the HTML design engine: three design options per output, on a model of your choice.

    /usr/bin/python3 harness/render_html_options.py OUT_DIR --model sonnet|haiku [--kinds deck,onepager,graphic] [--rounds 2]

The model is reached through ``claude -p`` (this harness only; inside Hermes the engine uses Letterpress's own runtime).
The checked content is the Harborlight sample's own deck, one-pager and graphic docs, so all three options per output share
the same content and number trace. Writes ``OUT/<kind>-<direction>/s01.png ... deck.pdf``, ``result.json`` and a contact
sheet per output. Chrome runs with its own scratch profile folder, deleted afterward."""
import asyncio, base64, json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["LETTERPRESS_DATA_DIR"] = tempfile.mkdtemp(prefix="letterpress-html-")
sys.path.insert(0, str(ROOT / "tests"))
from importlib import import_module  # noqa: E402
from _load import service, store  # noqa: E402

HD = import_module("letterpress_plugin_package.htmldeck")
OUT = Path(sys.argv[1]).resolve()
MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "sonnet"
KINDS = (sys.argv[sys.argv.index("--kinds") + 1] if "--kinds" in sys.argv else "deck,onepager,graphic").split(",")
ROUNDS = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 2
DIRS = (sys.argv[sys.argv.index("--dirs") + 1] if "--dirs" in sys.argv else "editorial,databoard,statement").split(",")
DOCS = Path("/tmp/claude-501/imp")
FONTS = ROOT / "fonts"


sys.path.insert(0, str(ROOT / 'harness'))
from claude_cli import ClaudeCLI  # noqa: E402


def main():
    st = service.open_sample()
    kid = (store.get_setting("prefs", {}) or {}).get("kit")
    kit = service.KITS.get(kid)
    passages = {f"P{p['id']}": {"text": p["text"]} for p in store.q("SELECT id, text FROM passages ORDER BY id")}
    pal = service.KITS.palette(kit)
    paper, brand, ink = pal["paper"], pal["head"], pal["ink"]

    def mix(a, b, t):
        A = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; B = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(A, B))
    vars_ = {"--brand": brand, "--brand-tint": mix(paper, brand, 0.10), "--brand-mid": mix(paper, brand, 0.55), "--paper": paper,
             "--ink": ink, "--muted": "#5b5651", "--accent": "#f2a900", "--cta": pal["accent"], "--rule": pal["rule"]}
    brand_dict = {"heading": "Montserrat", "body": "Lora", "vars": vars_, "fonts": [
        {"family": "Montserrat", "weight": w, "file": FONTS / f"montserrat-{w}.ttf"} for w in (400, 600, 700, 800)] + [
        {"family": "Lora", "weight": 400, "file": FONTS / "lora-400.ttf"},
        {"family": "Lora", "weight": 400, "style": "italic", "file": FONTS / "lora-400-italic.ttf"}]}
    brand_text = (
        "Harborlight Literacy Project (first use), Harborlight after. Say adult learners, never students, clients, or at-risk. "
        "Headlines in sentence case. Headlines: heading face (Montserrat) bold or extra bold. Body: body face (Lora); quotes in italic.\n"
        "CSS variables you may use: " + "; ".join(f"{k} = {v}" for k, v in vars_.items()) + ".\n"
        "Roles: --brand primary (headlines, bands, the logo, chart marks); --brand-tint and --brand-mid for tints of it; --paper "
        "background; --ink body text; --muted secondary text; --accent (gold) sparingly, for rules, callouts, one number; --cta "
        "(red) for calls to action only, never for data. Every printed piece ends with: Harborlight Literacy Project is a 501(c)(3) "
        "nonprofit. EIN 47-1928361. (cite P11)\nThe logo is a teal circle with a gold bar, <img src=\"letterpress:logo\" alt=\"\">, "
        "kept at least 56px wide and never stretched.")
    logo = "data:image/png;base64," + base64.b64encode((ROOT / "samples/harborlight/harborlight-logo.png").read_bytes()).decode()
    docs = {"deck": json.load(open(DOCS / "main-doc.json")), "onepager": json.load(open(DOCS / "main-onepager.json"))}
    vis = import_module("letterpress_plugin_package.harness_visual") if False else None
    src = (ROOT / "harness/render_harborlight.py").read_text()
    ns = {}
    exec(src[src.index("VISUAL = "):src.index("ONEPAGER = ")], ns)
    docs["graphic"] = ns["VISUAL"]
    sem = None

    async def one(kind, d):
        wd = OUT / f"{kind}-{d}"; wd.mkdir(parents=True, exist_ok=True)
        llm = ClaudeCLI(MODEL, wd)
        if "--rerender" in sys.argv:  # no model: the saved markup is cleaned again by the current cleaner, drawn and traced
            old = json.load(open(wd / "result.json"))
            slides, removed = [], []
            for sl in old["slides"]:
                clean, rm = HD.sanitize(sl["html"]); removed += rm
                slides.append({"html": clean, "notes": sl.get("notes", "")})
            css = HD.kit_css(brand_dict, kind)
            rr = HD.render_safe(slides, css, wd, logo, kind)
            tr = HD.trace(slides, passages)
            json.dump({"slides": slides, "trace": tr["counts"], "flags": tr["flags"], "problems": rr["problems"], "removed": list(dict.fromkeys(removed)),
                       "calls": old.get("calls", [])}, open(wd / "result.json", "w"), indent=1)
            print(kind, d, "trace", tr["counts"], "problems", len(rr["problems"]), "flags", len(tr["flags"]), "removed", len(removed), flush=True)
            return
        async with sem:
            try:
                r = await HD.make(llm, brand_dict, brand_text, passages, HD.content_text(docs[kind], kind), wd, d, logo, ROUNDS, kind)
            except Exception as e:
                (wd / "error.txt").write_text(repr(e)); print("FAIL", kind, d, repr(e)[:200]); return
        json.dump({"slides": r["slides"], "trace": r["trace"]["counts"], "flags": r["trace"]["flags"], "problems": r["render"]["problems"],
                   "removed": r["removed"], "calls": llm.calls}, open(wd / "result.json", "w"), indent=1)
        (wd / "slides.html").write_text(HD.page(r["slides"], HD.kit_css(brand_dict, kind), logo, kind=kind))
        print(kind, d, "trace", r["trace"]["counts"], "problems", len(r["render"]["problems"]), "flags", len(r["trace"]["flags"]), flush=True)

    async def run():
        nonlocal sem
        sem = asyncio.Semaphore(4)
        await asyncio.gather(*[one(k, d) for k in KINDS for d in DIRS])
    asyncio.run(run())


main()
