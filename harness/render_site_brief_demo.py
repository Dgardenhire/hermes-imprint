"""One site, two kits: colors and fonts only, and colors and fonts plus the style brief captured from how the site looks.
Both feed the same Harborlight deck content to the same three design directions, so the difference is the brief.

    /usr/bin/python3 harness/render_site_brief_demo.py OUT_DIR https://linchpin.studio --model sonnet

Opens the site read-only in headless Chrome (robots respected; the home page and up to three linked pages), reads its CSS with
the older reader, asks the model for the brief from the screenshots and measured styles, then designs the deck for both kits."""
import asyncio, json, os, re, sys, tempfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["IMPRINT_DATA_DIR"] = tempfile.mkdtemp(prefix="imprint-sitedemo-")
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT / "harness"))
from importlib import import_module  # noqa: E402
from _load import service, store, kits  # noqa: E402
from claude_cli import ClaudeCLI  # noqa: E402

PKG = "imprint_plugin_package"
SS, HD, D, SK = (import_module(f"{PKG}.{m}") for m in ("sitestyle", "htmldeck", "designs", "sitekit"))
OUT = Path(sys.argv[1]).resolve(); OUT.mkdir(parents=True, exist_ok=True)
URL = sys.argv[2]
MODEL = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "sonnet"
DIRS = (sys.argv[sys.argv.index("--dirs") + 1] if "--dirs" in sys.argv else "editorial,databoard,statement").split(",")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Imprint (reads a few pages a person asked for)"})
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")


def _robots_fetch(url):  # the harness runs outside Hermes, so it supplies the robots.txt read itself
    import urllib.error
    try:
        return 200, get(url)
    except urllib.error.HTTPError as e:
        return e.code, ""


SS.ROBOTS_FETCH = _robots_fetch


async def main():
    capdir = OUT / "capture"
    capf = capdir / "cap.json"
    if capf.exists():
        cap = json.loads(capf.read_text())
    else:
        cap = SS.capture(URL, capdir)
        capf.write_text(json.dumps(cap))
    print("captured", [p["url"] for p in cap["pages"]], flush=True)
    briefp = OUT / "brief.json"
    if briefp.exists():
        brief = json.loads(briefp.read_text())
    else:
        brief = await SS.write_brief(ClaudeCLI(MODEL, OUT / "brief-work"), cap, URL, step=print)
        briefp.write_text(json.dumps(brief, indent=1))
    print(json.dumps(brief, indent=1)[:1500], flush=True)
    page = get(URL)
    css = []
    for link in SK.stylesheet_links(page, URL)[:SK.MAX_STYLESHEETS]:
        try:
            css.append(get(link))
        except Exception:
            pass
    draft = SK.draft_from(page, css, URL, "November 9, 2026")
    draft["name"] = "Site colors and fonts"
    base = kits.save_new({**draft, "origin": "site"})
    styled = kits.save_new({**draft, "name": "Site colors, fonts and style brief", "origin": "site", "style_brief": brief})
    service.open_sample()
    st = service.open_sample()
    passages = {f"P{p['id']}": {"text": p["text"]} for p in store.q("SELECT id, text FROM passages ORDER BY id")}
    doc = json.load(open("/tmp/claude-501/imp/main-doc.json"))
    content = HD.content_text(doc, "deck")
    sem = asyncio.Semaphore(4)

    async def one(tag, kit, d):
        brand, text, logo = D.brand_for(kit)
        wd = OUT / f"{tag}-{d}"
        async with sem:
            r = await HD.make(ClaudeCLI(MODEL, wd), brand, text, passages, content, wd, d, logo, 2, "deck", style_hint=D.style_hint(kit))
        json.dump({"slides": r["slides"], "flags": r["trace"]["flags"], "problems": r["render"]["problems"]}, open(wd / "result.json", "w"))
        print(tag, d, "flags", len(r["trace"]["flags"]), "problems", len(r["render"]["problems"]), flush=True)

    await asyncio.gather(*[one(t, k, d) for t, k in (("plain", base), ("brief", styled)) for d in DIRS])

asyncio.run(main())
