"""Layout regression check for the Brands page: nothing wider than the page, columns reflow as space shrinks.

    /usr/bin/python3 harness/check_layout.py [PORT]

Starts the live harness server on a throwaway data folder, opens the Brands tab with the "Earlier starters" list
expanded at 1100, 1280, 1440, 1728 and 2000 px (each at 100, 125 and 150 percent browser zoom, done by shrinking the
CSS viewport), and fails if the Brands scroller has to scroll sideways, any card or button ends past the right edge of
the page area, or the Studio brands grid does not step down 4, 3, 2, 1 columns as the area narrows. Needs the
Playwright Python package and network for React (esm.sh) like the screenshots do. Never touches ~/.hermes.

This is the guard for the bug where a one-column grid sized itself to its widest child (four 300 px cards) and pushed
the fourth column off the right edge. The fix is minmax(0,1fr) on the page grids in desktop/src/plugin.js."""
import json, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8851
WIDTHS = [1100, 1280, 1440, 1728, 2000]
ZOOMS = [1.0, 1.25, 1.5]
SIDEBAR = 232  # the harness window keeps a 232 px sidebar beside the plugin page, as Hermes Desktop does

JS = """() => {
  const kits = document.querySelector('.imp-kits')
  const kr = kits.getBoundingClientRect()
  const past = [...kits.querySelectorAll('*')].filter(n => { const r = n.getBoundingClientRect(); return r.width > 0 && r.right > kr.right + 0.5 })
    .slice(0, 5).map(n => n.tagName.toLowerCase() + '.' + String(n.className).split(' ')[0])
  const cols = sel => { const el = document.querySelector(sel); return el ? getComputedStyle(el).gridTemplateColumns.split(' ').length : 0 }
  return { client: kits.clientWidth, scroll: kits.scrollWidth, past, studio: cols('.imp-studio-kits'), list: cols('.imp-kitlist'),
           doc: document.documentElement.scrollWidth, win: innerWidth }
}"""


def main():
    data = Path(tempfile.mkdtemp(prefix="letterpress-layout-"))
    srv = subprocess.Popen(["/usr/bin/python3", str(ROOT / "harness/live/server.py"), str(PORT), "--data", str(data / "data"), "--voice-stub"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bad, rows = [], []
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/harness/index.html", timeout=2); break
            except Exception:
                time.sleep(0.5)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(data / "chrome"), args=["--mute-audio"], viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            prev_studio = {}
            for z in ZOOMS:
                studio_by_width = []
                for w in WIDTHS:
                    pg.set_viewport_size({"width": round(w / z), "height": round(900 / z)})
                    pg.goto(f"http://127.0.0.1:{PORT}/harness/index.html?live=1&theme=dark&tab=kits")
                    pg.wait_for_selector(".imp-studio-kits .imp-sk", timeout=60000)
                    pg.wait_for_timeout(800)
                    pg.wait_for_selector(".imp-linkish", timeout=60000)
                    if not pg.query_selector(".imp-kitlist"):
                        pg.click(".imp-linkish", timeout=60000); pg.wait_for_selector(".imp-kitlist", timeout=60000)
                    pg.wait_for_timeout(400)
                    m = pg.evaluate(JS)
                    tag = f"{w}px at {int(z * 100)}%"
                    rows.append((tag, m))
                    if m["scroll"] > m["client"] + 1:
                        bad.append(f"{tag}: Brands scrolls sideways ({m['scroll']} > {m['client']})")
                    if m["past"]:
                        bad.append(f"{tag}: past the right edge: {', '.join(m['past'])}")
                    if m["doc"] > m["win"]:
                        bad.append(f"{tag}: the whole page scrolls sideways ({m['doc']} > {m['win']})")
                    # a card needs 300 px (Studio, 22 px gaps) or 280 px (list, 16 px gaps); the page has 40 px of side padding
                    area = m["client"] - 40
                    for name, need, gap, got in (("Studio brands", 300, 22, m["studio"]), ("Earlier starters", 280, 16, m["list"])):
                        most = max(1, int((area + gap) // (need + gap)))
                        if got > most:
                            bad.append(f"{tag}: {name} has {got} columns in {area}px (room for {most})")
                    studio_by_width.append(m["studio"])
                if studio_by_width != sorted(studio_by_width):
                    bad.append(f"{int(z * 100)}%: Studio columns do not step down as the window narrows: {studio_by_width}")
            ctx.close()
    finally:
        srv.terminate()
        try: srv.wait(timeout=10)
        except Exception: srv.kill()
        shutil.rmtree(data, ignore_errors=True)
    for tag, m in rows:
        print(f"{tag:>14}  area {m['client']:>4}  scroll {m['scroll']:>4}  Studio cols {m['studio']}  list cols {m['list']}")
    if bad:
        print("\nFAIL"); print("\n".join(bad)); sys.exit(1)
    print("\nOK: no Brands content past the visible width at any size")


main()
