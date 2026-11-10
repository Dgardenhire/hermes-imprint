#!/bin/sh
# Imprint pane lane (Loop 2): shots S01 to S08, S18 and S19 of the hero brief, with a DOM check for every "Accept" line.
#
#   REAL=1 sh harness/shoot_pane.sh OUT_DIR [SEED_DIR]
#
# Runs the live harness (harness/live/server.py, unchanged) on a fresh data folder inside this repo
# (.l2-data/shoot), with REAL=1 the model is the bench adapter (claude -p, harness/bench/bench.py ClaudeCli) and every
# call leaves a run log in OUT_DIR/runs. S01 is the fresh folder. Then "Open the sample" (POST sample/open, the
# backend's recorded real-model notebook). With SEED_DIR (a data folder a real model made), the folder starts as a
# copy of it, S01 is skipped and the sample route is not used; the log says which. ONLY=S01 stops after S01.
# Sizes: 1440x900 light, 1440x900 dark, 1280x800 light; S19 at 1024x768. Headless Chromium, muted, no autoplay.
# Needs: /usr/bin/python3 with Playwright, the built desktop/plugin.js, network for React from esm.sh.
# Never touches ~/.hermes and never runs a hermes command. Exit 1 when any check fails.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/.l2-data/pane-shots}"
SEED="${2:-}"
PORT="${PORT:-8812}"
PY=/usr/bin/python3
mkdir -p "$OUT/runs"
DATA="$ROOT/.l2-data/shoot"
rm -rf "$DATA"; mkdir -p "$DATA"
[ -n "$SEED" ] && cp -R "$SEED"/. "$DATA"/
export BENCH_NEUTRAL=1
SERVER_PID=""
start_server() {
  if [ -n "$REAL" ]; then
    "$PY" - "$ROOT" "$PORT" "$DATA" "$OUT/runs" > "$OUT/server.log" 2>&1 <<'PYEOF' &
import sys, time, types
from pathlib import Path
WT, PORT, DATA, LOGS = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
sys.path.insert(0, str(WT / "harness" / "bench"))
import bench  # the AI lane's claude -p adapter; every call is logged as JSON in LOGS
fake = types.ModuleType("persona_model")
fake.PersonaModel = lambda: bench.ClaudeCli(LOGS, "pane-" + time.strftime("%H%M%S"), "")
sys.modules["persona_model"] = fake
src = (WT / "harness" / "live" / "server.py").read_text()
head = src.split('\nif __name__ == "__main__":\n    port', 1)[0]
sys.argv = [str(WT / "harness" / "live" / "server.py"), str(PORT), "--data", DATA, "--voice-stub"]
ns = {"__name__": "__main__", "__file__": sys.argv[0]}
exec(compile(head, sys.argv[0], "exec"), ns)
print(f"pane shoot server, real model, on {PORT}, data {DATA}", flush=True)
ns["serve"](PORT).serve_forever()
PYEOF
  else
    "$PY" "$ROOT/harness/live/server.py" "$PORT" --data "$DATA" --voice-stub > "$OUT/server.log" 2>&1 &
  fi
  SERVER_PID=$!
  curl --retry 20 --retry-connrefused --retry-delay 1 -s -o /dev/null "http://127.0.0.1:$PORT/harness/index.html"
}
trap '[ -n "$SERVER_PID" ] && kill $SERVER_PID 2>/dev/null; true' EXIT
# Never drive a server this script did not start (another lane may hold the port).
if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/"; then echo "port $PORT is in use; pick another with PORT=" >&2; exit 2; fi
start_server
set +e
"$PY" - "$PORT" "$OUT" "$DATA" "$SEED" <<'PYEOF'
"""Drives the pane in headless Chromium and checks each shot's Accept lines in the DOM."""
import json, shutil, subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

PORT, OUT, DATA, SEED = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
BASE = f"http://127.0.0.1:{PORT}/harness/index.html?live=1"
API = f"http://127.0.0.1:{PORT}/api/"
SIZES = [("1440", 1440, 900, "light"), ("1440", 1440, 900, "dark"), ("1280", 1280, 800, "light")]
results, log = [], {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "shots": [], "notes": []}
BANNED = ["tokens", "Answers come only from", "passages", "grounding", "trace table"]


def call(method, path, body=None, timeout=900):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def check(shot, name, ok, detail=""):
    results.append({"shot": shot, "check": name, "ok": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {shot}  {name}  {detail}"[:240], flush=True)


def page_for(b, w, h, theme, extra=""):
    pg = b.new_page(viewport={"width": w, "height": h})
    pg._errs = []
    pg.on("pageerror", lambda e: pg._errs.append(str(e)))
    pg.goto(f"{BASE}&theme={theme}{extra}")
    pg.wait_for_selector(".imp-nb", timeout=30000)
    pg.wait_for_timeout(1200)
    return pg


def shoot(pg, sid, name, tag, theme):
    path = OUT / f"{sid}-{name}-{tag}-{theme}.png"
    for attempt in range(3):  # a page playing audio can be slow to settle; try again before giving up
        try:
            pg.screenshot(path=str(path), timeout=60000)
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise
            pg.wait_for_timeout(1500)
    log["shots"].append(str(path))
    tz = pg.evaluate("""(() => { const t = document.querySelector('.imp-toast'); if (!t) return null; const a = t.getBoundingClientRect(), n = document.querySelector('.ip-cv-nums');
        const b = n && n.getBoundingClientRect(); return [t.textContent, !!(b && b.width && a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top)] })()""")
    if tz:
        log["notes"].append(f"{sid} {tag} {theme}: toast showing: {tz[0]}")
        check(sid, f"toast not over the numbers row ({tag} {theme})", not tz[1], tz[0])
    cut = pg.evaluate("""[...document.querySelectorAll('.imp strong, .imp h1, .imp h2, .imp h3, .imp-stamp, .imp-viewer-title *, .imp-reader-name, .imp-mcard-title, .imp-tile span, .imp-q, .imp-scope')].filter(e => {
        if (!e.getClientRects().length || e.closest('.ip-page, .ip-scene, .imp-tile-pic, .imp-mcard-pic, .imp-scard, .ip-cv')) return false  // .ip-cv: the canvas lane's own head
        const s = getComputedStyle(e); return (s.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) || (s.webkitLineClamp !== 'none' && e.scrollHeight > e.clientHeight + 1) })
        .map(e => e.textContent.trim().slice(0, 40))""")
    check(sid, f"no title or stamp cut ({tag} {theme})", not cut, json.dumps(cut)[:200])
    if pg._errs:
        check(sid, f"no page errors ({tag} {theme})", False, "; ".join(pg._errs[:3]))
    return path


def common(pg, sid, tag):
    txt = pg.evaluate("document.querySelector('.imp').innerText")
    for w in BANNED:
        check(sid, f"no '{w}' on screen ({tag})", w.lower() not in txt.lower())
    check(sid, f"no 'Kit' label ({tag})", not any(t.strip() in ("Kit", "Kits") for t in txt.split("\n")))
    check(sid, f"no native select ({tag})", pg.evaluate("document.querySelectorAll('.imp select').length") == 0)
    small = pg.evaluate("""[...document.querySelectorAll('.imp *')].filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
        && e.getClientRects().length && parseFloat(getComputedStyle(e).fontSize) < 12 && !e.closest('.ip-page, .ip-scene, .imp-tile-pic, .imp-mcard-pic')).map(e => e.textContent.trim().slice(0, 30)).slice(0, 5)""")
    check(sid, f"no live text under 12px ({tag})", not small, json.dumps(small))


def no_scroll(pg):
    return pg.evaluate("[document.scrollingElement.scrollWidth <= innerWidth, document.scrollingElement.scrollHeight <= innerHeight, document.querySelector('.imp').scrollHeight <= document.querySelector('.imp').clientHeight + 1]")


with sync_playwright() as p:
    b = p.chromium.launch(args=["--mute-audio", "--autoplay-policy=user-gesture-required"])

    # ---- S01 first open (fresh folder) ----
    for tag, w, h, theme in ([] if SEED else SIZES):
        pg = page_for(b, w, h, theme)
        pg.wait_for_timeout(1500)
        shoot(pg, "S01", "first-open", tag, theme)
        txt = pg.evaluate("document.querySelector('.imp').innerText")
        check("S01", f"promise sentence ({tag} {theme})", "Ask questions of your documents, then make a deck, one-pager, graphic or audio brief in your brand. Every number is checked against your sources." in txt)
        prim = pg.evaluate("[...document.querySelectorAll('.imp [data-slot=button][data-variant=default]')].filter(b => b.getClientRects().length).map(b => b.textContent)")
        check("S01", f"exactly one primary button, Open the sample ({tag} {theme})", prim == ["Open the sample"], json.dumps(prim))
        tiles = pg.evaluate("[...document.querySelectorAll('.imp-tile')].map(t => !!t.querySelector('img'))")
        check("S01", f"Studio tiles are img ({tag} {theme})", len(tiles) == 4 and all(tiles), json.dumps(tiles))
        fp = pg.evaluate("[!!document.querySelector('.imp-first-pic img'), (document.querySelector('.imp-first-pic figcaption') || {}).textContent || '', [...document.querySelectorAll('.imp-tile-pic img')].map(i => i.alt)]")
        check("S01", f"the middle shows the sample's exhibit slide with its caption ({tag} {theme})", fp[0] and fp[1] == "Every number links to the sentence it came from.", json.dumps(fp[:2]))
        check("S01", f"tiles in the sample brand ({tag} {theme})", fp[2] and all("Harborlight" in a for a in fp[2]), json.dumps(fp[2]))
        check("S01", f"no dashed drop box ({tag} {theme})", pg.evaluate("![...document.querySelectorAll('.imp *')].some(e => getComputedStyle(e).borderStyle.includes('dashed') && e.offsetWidth > 120)"))
        common(pg, "S01", f"{tag} {theme}")
        pg.close()

    import os
    if os.environ.get("ONLY") == "S01":
        b.close()
        fails = [r for r in results if not r["ok"]]
        log.update(checks=results, passed=len(results) - len(fails), failed=len(fails))
        (OUT / "shoot-log-S01.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
        print(f"\n{len(results) - len(fails)} of {len(results)} checks pass.")
        sys.exit(1 if fails else 0)

    # ---- open the sample (or start from SEED_DIR) ----
    if SEED:
        log["notes"].append(f"started from a copy of {SEED}; S01 and the sample route not used")
    else:
        t0 = time.time()
        call("POST", "sample/open", {})
        log["notes"].append(f"sample/open took {time.time() - t0:.2f} s")
        check("S02", "sample opens in under 3 s", time.time() - t0 < 3, f"{time.time() - t0:.2f} s")
    log["sample_route"] = not SEED

    pages = {}
    for tag, w, h, theme in SIZES:
        pg = page_for(b, w, h, theme)
        pg.wait_for_selector(".imp-gd-text", timeout=60000)
        pg.wait_for_timeout(800)
        pages[(tag, theme)] = pg

    # ---- S02 sample notebook ----
    for (tag, theme), pg in pages.items():
        shoot(pg, "S02", "sample-open", tag, theme)
        ns = no_scroll(pg)
        check("S02", f"three columns, no page scroll ({tag} {theme})", all(ns), json.dumps(ns))
        aw = pg.evaluate("document.querySelector('.imp-ask').getBoundingClientRect().width")
        check("S02", f"Ask {'420' if tag == '1440' else '400'}px or wider ({tag} {theme})", aw >= (420 if tag == "1440" else 400), f"{aw:.0f}px")
        asks = pg.evaluate("[...document.querySelectorAll('.imp-askcard')].map(c => ({pill: (c.querySelector('.imp-spill-name') || {}).textContent, make: [...c.querySelectorAll('button')].some(b => b.textContent === 'Make')}))")
        check("S02", f"two ask cards with board-retreat-notes.txt and Make ({tag} {theme})", len(asks) == 2 and all(a["pill"] == "board-retreat-notes.txt" and a["make"] for a in asks), json.dumps(asks))
        qs = pg.evaluate("[...document.querySelectorAll('.imp-gd .imp-qrow')].map(q => q.textContent)")
        check("S02", f"a question names 3.2 months and $190,000 ({tag} {theme})", any("3.2" in q and "190,000" in q for q in qs), json.dumps(qs)[:200])
        mk = pg.evaluate("[document.querySelectorAll('.imp-makerow .imp-make').length, document.querySelectorAll('.imp-studio .imp-tile').length, [...document.querySelectorAll('.imp-made .imp-mcard-pic img')].filter(i => i.src.startsWith('data:image/')).length]")
        check("S02", f"Studio: four small make buttons, no make tiles, Made is the one gallery of real pictures ({tag} {theme})", mk[0] == 4 and mk[1] == 0 and mk[2] >= 1, json.dumps(mk))
        dc = pg.evaluate("[[...document.querySelectorAll('.imp-studio .imp-h3')].map(e => e.textContent), document.querySelectorAll('.imp-srcpane .imp-tag, .imp-studio .imp-tag').length, (document.querySelector('.imp-ask').innerText.match(/Written by your Hermes model/g) || []).length, document.querySelectorAll('.imp-top .imp-tag').length]")
        check("S02", f"no Suggested block in Studio ({tag} {theme})", "Suggested" not in dc[0], json.dumps(dc[0]))
        check("S02", f"Sample only in the top bar ({tag} {theme})", dc[1] == 0 and dc[3] == 1, json.dumps([dc[1], dc[3]]))
        check("S02", f"model credit at most once in Ask ({tag} {theme})", dc[2] <= 1, str(dc[2]))
        common(pg, "S02", f"{tag} {theme}")

    # ---- S03 chat answer: the first likely question, asked for real on the first page ----
    first = pages[("1440", "light")]
    q = first.evaluate("(() => { const qs = [...document.querySelectorAll('.imp-gd .imp-qrow')]; const q = qs.find(x => x.textContent.includes('3.2')) || qs[0]; q.click(); return q.textContent })()")
    first.wait_for_selector(".imp-reading", timeout=5000)
    check("S03", "reading card shows within 300 ms", True)
    first.wait_for_function("!document.querySelector('.imp-reading')", timeout=300000)
    first.wait_for_timeout(1000)
    scroll_to = """q => { const el = [...document.querySelectorAll('.imp-q')].reverse().find(x => x.textContent === q); const s = document.querySelector('.imp-chat-scroll'); if (el && s) {
        s.scrollTop = el.offsetTop - 14; const top = s.getBoundingClientRect().top;
        const cut = [...s.querySelectorAll('p, li, h2, h3, .imp-a-foot, .imp-q')].filter(e => { const r = e.getBoundingClientRect(); return r.height && r.top < top - 1 && r.bottom > top + 1 }).sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
        if (cut) s.scrollTop -= top + 6 - cut.getBoundingClientRect().top } return !!el }"""
    top_cut = """(() => { const s = document.querySelector('.imp-chat-scroll'); const top = s.getBoundingClientRect().top;
        return [...s.querySelectorAll('p, li, .imp-a-foot, .imp-q')].filter(e => { const r = e.getBoundingClientRect(); return r.height && r.top < top - 1 && r.bottom > top + 1 }).map(e => e.textContent.slice(0, 40)) })()"""
    fold = """(() => { const a = [...document.querySelectorAll('.imp-a')].slice(-1)[0]; const f = a.querySelector('.imp-a-fold[aria-expanded]'); return [f ? f.textContent : '', document.querySelector('.imp-scope').textContent] })()"""
    for (tag, theme), pg in pages.items():
        if pg is not first:
            pg.reload(); pg.wait_for_selector(".imp-a", timeout=30000); pg.wait_for_timeout(800)
        pg.evaluate(scroll_to, q); pg.wait_for_timeout(300)
        shoot(pg, "S03", "chat-answer", tag, theme)
        last = "[...document.querySelectorAll('.imp-a')].slice(-1)[0]"
        check("S03", f"numbered chips ({tag} {theme})", pg.evaluate(f"{last}.querySelectorAll('.imp-cite').length") > 0)
        vis = pg.evaluate(f"""(() => {{ const a = {last}; const r = b => {{ const x = b.getBoundingClientRect(); return x.bottom <= innerHeight && x.top >= 0 && x.width > 0 }};
            const bs = [...a.querySelectorAll('button')]; return [bs.some(b => b.textContent.trim() === 'Pin' && r(b)), bs.some(b => b.textContent.includes('Make from this') && r(b))] }})()""")
        check("S03", f"Pin and Make from this visible without hover ({tag} {theme})", all(vis), json.dumps(vis))
        by = pg.evaluate(f"(() => {{ const e = {last}.querySelector('.imp-by'); return e ? [e.textContent, getComputedStyle(e).fontSize] : null }})()")
        check("S03", f"Written by your Hermes model at 12px ({tag} {theme})", by and by[0] == "Written by your Hermes model" and by[1] == "12px", json.dumps(by))
        nby = pg.evaluate("(document.querySelector('.imp-ask').innerText.match(/Written by your Hermes model/g) || []).length")
        check("S03", f"model credit once in Ask ({tag} {theme})", nby == 1, str(nby))
        lead = pg.evaluate(f"(() => {{ const e = {last}.querySelector('.imp-a-lead'); const r = e.getBoundingClientRect(); return [getComputedStyle(e).fontWeight, r.bottom <= innerHeight] }})()")
        check("S03", f"bold lead above the fold ({tag} {theme})", int(lead[0]) >= 600 and lead[1], json.dumps(lead))
        check("S03", f"sources folded ({tag} {theme})", pg.evaluate(f"!{last}.querySelector('.imp-a-src')"))
        fl = pg.evaluate(fold)
        check("S03", f"the answer's source count is no more than the ticked count ({tag} {theme})", int(fl[0].split()[0]) <= int(fl[1].split()[0]), json.dumps(fl))
        check("S03", f"no line cut at the top of Ask ({tag} {theme})", not pg.evaluate(top_cut), json.dumps(pg.evaluate(top_cut)))
        common(pg, "S03", f"{tag} {theme}")
    log["S03_question"] = q

    # ---- S04 follow-up ----
    first.fill(".imp-composer textarea", "What about the Riverside site?")
    first.keyboard.press("Meta+Enter")
    first.wait_for_selector(".imp-reading", timeout=5000)
    first.wait_for_function("!document.querySelector('.imp-reading')", timeout=300000)
    first.wait_for_timeout(1000)
    ans = first.evaluate("[...document.querySelectorAll('.imp-a')].slice(-1)[0].innerText")
    log["S04_answer"] = ans[:1500]
    for (tag, theme), pg in pages.items():
        if pg is not first:
            pg.reload(); pg.wait_for_selector(".imp-a", timeout=30000); pg.wait_for_timeout(800)
        pg.evaluate(scroll_to, "What about the Riverside site?"); pg.wait_for_timeout(300)
        shoot(pg, "S04", "chat-followup", tag, theme)
        fl = pg.evaluate(fold)
        check("S04", f"the answer's source count is no more than the ticked count ({tag} {theme})", int(fl[0].split()[0]) <= int(fl[1].split()[0]), json.dumps(fl))
        check("S04", f"no line cut at the top of Ask ({tag} {theme})", not pg.evaluate(top_cut), json.dumps(pg.evaluate(top_cut)))
    check("S04", "the follow-up answer refers to the earlier turn (waitlist, sixth site or Eastgate)", any(w in ans for w in ("waitlist", "sixth site", "Eastgate", "earlier")), ans[:160])

    # ---- S05 reader: chip 2 of the follow-up answer ----
    for (tag, theme), pg in pages.items():
        pg.evaluate("(() => { const a = [...document.querySelectorAll('.imp-a')].slice(-1)[0]; const c = [...a.querySelectorAll('.imp-cite')].find(x => x.textContent === '2') || a.querySelector('.imp-cite'); c.click() })()")
        pg.wait_for_selector(".imp-pass.is-cited", timeout=15000); pg.wait_for_timeout(700)
        shoot(pg, "S05", "reader", tag, theme)
        f = pg.evaluate("(() => { const p = document.querySelector('.imp-pass.is-cited p'); const s = getComputedStyle(p); return [s.fontFamily, s.fontSize] })()")
        check("S05", f"passage highlighted, Source Serif 4 at 15px ({tag} {theme})", "Source Serif 4" in f[0] and f[1] == "15px", json.dumps(f))
        rc = pg.evaluate("""(() => { const h = document.querySelector('.imp-reader-back').getBoundingClientRect().bottom;
            const rows = [...document.querySelectorAll('.imp-reader-body > *:not(ol), .imp-passages > li')];
            const first = rows.find(r => r.getBoundingClientRect().bottom > h + 1); const c = document.querySelector('.imp-pass.is-cited').getBoundingClientRect();
            return [first ? first.getBoundingClientRect().top >= h - 1 : false, c.top >= h - 1 && c.top < innerHeight] })()""")
        check("S05", f"the reader's first line is whole and the cited passage shows ({tag} {theme})", all(rc), json.dumps(rc))
        pg.evaluate("document.querySelector('.imp-reader-back button').click()")

    # ---- S06 brief, pre-filled from the funder ask ----
    for (tag, theme), pg in pages.items():
        pg.evaluate("(() => { const c = [...document.querySelectorAll('.imp-askcard')].find(x => /deck/i.test(x.textContent)) || document.querySelectorAll('.imp-askcard')[1]; c.querySelector('[data-slot=button]').click() })()")
        pg.wait_for_selector(".imp-brief", timeout=5000); pg.wait_for_timeout(400)
        shoot(pg, "S06", "brief-prefilled", tag, theme)
        vals = pg.evaluate("[...document.querySelectorAll('.imp-brief input, .imp-brief textarea')].map(x => x.value)")
        check("S06", f"who, goal and length filled ({tag} {theme})", len(vals) == 3 and all(v.strip() for v in vals), json.dumps(vals))
        prim = pg.evaluate("[...document.querySelectorAll('.imp [data-slot=button][data-variant=default]')].filter(b => b.getClientRects().length).map(b => b.textContent)")
        check("S06", f"one primary: Write the outline ({tag} {theme})", prim == ["Write the outline"], json.dumps(prim))
        check("S06", f"no council placeholder ({tag} {theme})", "council" not in pg.evaluate("document.querySelector('.imp-flow').innerText").lower())

    # ---- S07 outline, written for real on the first page ----
    first.get_by_role("button", name="Write the outline").click()
    first.wait_for_selector(".imp-ol-row", timeout=300000)
    first.wait_for_timeout(1500)
    fl = first.evaluate("import('/desktop/plugin.js').then(m => m.flowNow())")
    olid = fl["outline"]["outline_id"]
    log["outline_id"] = olid
    for (tag, theme), pg in pages.items():
        if pg is not first:
            pg.evaluate(f"import('/desktop/plugin.js').then(m => m.openOutline('{olid}', '{(fl.get('ask') or {}).get('id', '')}'))")
            pg.wait_for_selector(".imp-ol-row", timeout=15000); pg.wait_for_timeout(1200)
        pg.evaluate("document.querySelector('.imp-ol-row:not(.is-fixed)').focus()"); pg.wait_for_timeout(200)
        shoot(pg, "S07", "outline", tag, theme)
        rows = pg.evaluate("[...document.querySelectorAll('.imp-ol-row:not(.is-fixed)')].map(r => ({t: r.querySelector('.imp-ol-title').textContent, g: !!r.querySelector('.imp-ol-type svg'), c: r.querySelectorAll('.imp-locchip').length}))")
        check("S07", f"7 to 10 titles ({tag} {theme})", 7 <= len(rows) <= 10, str(len(rows)))
        check("S07", f"each title under 15 words ({tag} {theme})", all(len(r["t"].split()) < 15 for r in rows), json.dumps([r["t"] for r in rows if len(r["t"].split()) >= 15]))
        check("S07", f"each row has a glyph and a source chip ({tag} {theme})", all(r["g"] and r["c"] >= 1 for r in rows), json.dumps([r for r in rows if not (r["g"] and r["c"])])[:200])
        cnt = pg.evaluate("[document.querySelector('.imp-outline-head strong').textContent, document.querySelector('.imp-outline .imp-flow-from').textContent, document.querySelectorAll('.imp-ol-row.is-fixed').length]")
        log["outline_slides"] = len(rows) + 1
        check("S07", f"count includes the title slide, head and footer agree ({tag} {theme})", cnt[2] == 1 and cnt[0] == f"{len(rows) + 1} slides" and cnt[1].startswith(f"{len(rows) + 1} slides"), json.dumps(cnt))
        mv = pg.evaluate("[...document.querySelectorAll('.imp-ol-row.is-focus .imp-ol-acts button')].map(b => b.getAttribute('aria-label') || b.textContent)")
        check("S07", f"Move up and Move down on the focused row ({tag} {theme})", "Move up" in mv and "Move down" in mv, json.dumps(mv))

    # ---- S08 build: started for real on the first page, watched on the others ----
    first.get_by_role("button", name="Build", exact=True).click()
    first.wait_for_timeout(1500)
    fl = first.evaluate("import('/desktop/plugin.js').then(m => m.flowNow())")
    jid = fl["build"]["id"]
    for (tag, theme), pg in pages.items():
        if pg is not first:
            pg.evaluate(f"import('/desktop/plugin.js').then(m => m.showBuild('{jid}', '{olid}', '{(fl.get('ask') or {}).get('id', '')}'))")
    first.wait_for_timeout(7000)
    for (tag, theme), pg in pages.items():
        shoot(pg, "S08", "build-progress", tag, theme)
        st = pg.evaluate("[!![...document.querySelectorAll('.imp-flow button')].find(b => b.textContent.includes('Stop')), [...document.querySelectorAll('.imp-flow .imp-steps li')].map(li => [li.className, li.querySelector('.imp-secs').textContent])]")
        check("S08", f"Stop button ({tag} {theme})", st[0])
        check("S08", f"seconds on every step ({tag} {theme})", all(s[1].endswith(" s") for s in st[1]), json.dumps(st[1]))
        check("S08", f"no Untitled row in Made ({tag} {theme})", "Untitled" not in pg.evaluate("document.querySelector('.imp-studio').innerText"))
    first.wait_for_function("!document.querySelector('.imp-flow')", timeout=600000)
    first.wait_for_selector(".ip-cv", timeout=180000)  # the finished deck opens once its pictures are drawn
    first.wait_for_timeout(2500)
    shoot(first, "S08b", "build-done-canvas", "1440", "light")
    log["deck_built"] = first.evaluate("import('/desktop/plugin.js').then(m => (m.stateNow().outputs || [])[0])")
    room = first.evaluate("[(document.querySelector('.imp-room-rail') || {getBoundingClientRect: () => ({width: 0})}).getBoundingClientRect().width, document.querySelector('.imp').innerText]")
    n = log.get("outline_slides")
    check("S08b", "the notebook stays as a 56px rail beside the canvas", round(room[0]) == 56, f"{room[0]}px")
    check("S08b", f"the canvas names the outline's count ({n} slides)", bool(n) and f"{n} slides" in room[1], f"outline {n}")
    first.click(".imp-room-tab:has-text('Ask')"); first.wait_for_timeout(700)
    shoot(first, "S08c", "canvas-ask-open", "1440", "light")
    check("S08c", "Ask opens over the canvas", first.evaluate("!!document.querySelector('.imp-dock.is-ask .imp-composer') && !!document.querySelector('.ip-cv')"))
    first.keyboard.press("Escape"); first.wait_for_timeout(300)

    for pg in pages.values():
        pg.close()

    # ---- S18 audio brief ----
    st = call("GET", "state")
    aud = next((o for o in st["outputs"] if o["kind"] == "audio"), None)
    if not aud:
        check("S18", "an audio brief exists", False)
    else:
        for tag, w, h, theme in SIZES:
            pg = page_for(b, w, h, theme)
            pg.evaluate(f"import('/desktop/plugin.js').then(m => m.view('{aud['id']}'))")
            pg.wait_for_selector(".imp-viewer .imp-proof", timeout=30000); pg.wait_for_timeout(1500)
            if not pg.query_selector(".imp-viewer audio"):  # not recorded yet: record with the harness voice stub (silent, never played)
                rec = pg.query_selector(".imp-player [data-slot=button]")
                if rec:
                    rec.click()
                    pg.wait_for_selector(".imp-viewer audio", state="attached", timeout=180000)
                    pg.wait_for_timeout(1500)
            has_audio = pg.evaluate("!!document.querySelector('.imp-viewer audio')")
            if has_audio:
                pg.evaluate("document.querySelector('.imp-viewer audio').muted = true")
                pg.click(".imp-play")  # a user gesture, so play() is allowed; the browser is muted too
                pg.wait_for_timeout(600)
                pg.evaluate("(() => { const a = document.querySelector('.imp-viewer audio'); if (a.duration) a.currentTime = a.duration * 0.3 })()")
                pg.wait_for_timeout(1500)
            shoot(pg, "S18", "audio-brief", tag, theme)
            d = pg.evaluate("[document.querySelectorAll('.imp-viewer select').length, document.querySelectorAll('.imp-viewer sup').length, document.querySelectorAll('.imp-stamp').length, document.querySelectorAll('.imp-mark').length, document.querySelector('.imp-viewer-title').innerText, !!document.querySelector('.imp-playing'), !!document.querySelector('.imp-viewer .imp-failed')]")
            check("S18", f"no select, no sup, one stamp, no crop marks ({tag} {theme})", d[0] == 0 and d[1] == 0 and d[2] == 1 and d[3] == 0, json.dumps(d[:4]))
            check("S18", f"length label About 3 min ({tag} {theme})", "About 3 min" in d[4], d[4])
            ch = pg.evaluate("""[...document.querySelectorAll('.imp-viewer .imp-linechip')].map(c => { const t = (c.nextSibling && c.nextSibling.textContent) || ''; return !c.nextSibling || /^[.!?]/.test(t.trimStart()) || !c.parentElement.nextSibling })""")
            check("S18", f"one chip per sentence, at its end ({tag} {theme})", ch and all(ch), f"{len(ch)} chips, {ch.count(False)} mid-sentence")
            check("S18", f"a chapter is playing ({tag} {theme})", d[5] and has_audio, json.dumps([has_audio, d[5]]))
            check("S18", f"no error box ({tag} {theme})", not d[6])
            rv = pg.evaluate("[[...document.querySelectorAll('.imp-sheet.is-script .ip-num')].filter(n => !n.classList.contains('is-missing') && getComputedStyle(n).textDecorationLine !== 'none').length, document.querySelectorAll('.imp-sheet.is-script h2 .imp-linechip').length, /End quote/.test(document.querySelector('.imp-sheet.is-script').innerText)]")
            check("S18", f"reading view: no underlined number, no chip on a chapter heading, no spoken quote marks ({tag} {theme})", rv[0] == 0 and rv[1] == 0 and not rv[2], json.dumps(rv))
            sb = pg.evaluate("""(() => { const c = [...document.querySelectorAll('.imp-viewer .imp-linechip')]; const ink = getComputedStyle(document.querySelector('.ip-page')).getPropertyValue('--k-ink').trim();
                const rgb = h => { const m = h.match(/^#(..)(..)(..)$/); return m ? `rgb(${parseInt(m[1],16)}, ${parseInt(m[2],16)}, ${parseInt(m[3],16)})` : h };
                return [c.filter(x => x.getBoundingClientRect().width > 60).length, c.filter(x => !x.closest('p, h2, h3, li')).length, c.every(x => getComputedStyle(x).color === rgb(ink)),
                  document.querySelector('.imp-viewer-head [aria-disabled=true]') ? 'held' : 'live', document.querySelector('.imp-stamp').dataset.tone] })()""")
            check("S18", f"no stray box: every chip sits on a line, none wider than 60px ({tag} {theme})", sb[0] == 0 and sb[1] == 0, json.dumps(sb[:2]))
            check("S18", f"chips in the brand's ink, readable on the page ({tag} {theme})", sb[2], json.dumps(sb[2]))
            check("S18", f"Export held exactly when a number is flagged ({tag} {theme})", (sb[3] == 'held') == (sb[4] == 'bad'), json.dumps(sb[3:]))
            common(pg, "S18", f"{tag} {theme}")
            pg.close()

    # ---- S18b the audio brief with a number that isn't in the sources: Export waits ----
    if aud:
        import sqlite3
        row = None
        for db in sorted(DATA.rglob("imprint.db")):  # the sample notebook keeps its own database under sample/
            con = sqlite3.connect(str(db)); row = con.execute("SELECT neutral FROM outputs WHERE id=?", (aud["id"],)).fetchone(); con.close()
            if row: break
        neutral = json.loads(row[0])
        seg0 = neutral["segments"][0]["text"]
        planted = seg0.replace("than the year before,", "than the year before, up 31%,", 1) if "than the year before," in seg0 else seg0.rstrip(".") + ", up 31%."
        call("POST", f"outputs/{aud['id']}/edit", {"path": "segments.0.text", "text": planted})
        log["notes"].append("S18b: planted 'up 31%' in chapter 1 by a typed edit (no model), then undone")
        for tag, w, h, theme in SIZES:
            pg = page_for(b, w, h, theme)
            pg.evaluate(f"import('/desktop/plugin.js').then(m => m.view('{aud['id']}'))")
            pg.wait_for_selector(".imp-viewer .imp-proof", timeout=30000); pg.wait_for_timeout(1200)
            pg.focus(".imp-export [data-slot=button]"); pg.wait_for_timeout(400)
            shoot(pg, "S18b", "audio-held", tag, theme)
            e = pg.evaluate("""(() => { const b = document.querySelector('.imp-export [data-slot=button]'); const w = document.querySelector('.imp-why');
                return [b.getAttribute('aria-disabled'), w ? w.textContent : '', w ? getComputedStyle(w).opacity : '0', document.querySelector('.imp-stamp').innerText,
                  [...document.querySelectorAll('.imp-stamp-row [data-slot=button]')].map(x => x.textContent)] })()""")
            check("S18b", f"Export held with its reason on focus ({tag} {theme})", e[0] == "true" and "first" in e[1] and e[2] == "1", json.dumps(e[:3]))
            check("S18b", f"the stamp names the number ({tag} {theme})", "31%" in e[3], e[3])
            pg.click(".imp-export [data-slot=button]", force=True); pg.wait_for_timeout(300)  # force: Playwright treats aria-disabled as not clickable
            check("S18b", f"clicking a held Export opens nothing ({tag} {theme})", not pg.query_selector(".imp-export .imp-menu"))
            check("S18b", f"a Fix it button ({tag} {theme})", "Fix it" in e[4], json.dumps(e[4]))
            if tag == "1440" and theme == "light":
                pg.click(".imp-stamp-row [data-slot=button]"); pg.wait_for_timeout(700)
                shoot(pg, "S18b", "audio-fix-open", tag, theme)
                check("S18b", "Fix it opens the number with Fix the wording, Remove it, Keep it", pg.evaluate("(() => { const g = document.querySelector('.imp-gitem[data-status]'); return !!g && /Remove it/.test(g.innerText) && /Keep it/.test(g.innerText) })()"))
            pg.close()
        call("POST", f"outputs/{aud['id']}/undo", {})

    # ---- S19 narrow ----
    pg = page_for(b, 1024, 768, "light")
    pg.wait_for_timeout(800)
    shoot(pg, "S19", "narrow", "1024", "light")
    rail = pg.evaluate("document.querySelector('.imp-srcpane').getBoundingClientRect().width")
    check("S19", "Sources is a 56px rail", round(rail) == 56, f"{rail}px")
    ns = no_scroll(pg)
    check("S19", "no horizontal or page scroll", all(ns), json.dumps(ns))
    check("S19", "Studio stays the third column", pg.evaluate("(() => { const a = document.querySelector('.imp-ask').getBoundingClientRect(), s = document.querySelector('.imp-studio').getBoundingClientRect(); return s.left >= a.right - 1 && s.top === a.top })()"))
    pg.evaluate("document.querySelector('.imp-rail-btn').click()"); pg.wait_for_timeout(500)
    shoot(pg, "S19b", "narrow-rail-open", "1024", "light")
    common(pg, "S19", "1024")
    pg.close()
    b.close()

fails = [r for r in results if not r["ok"]]
log.update(checks=results, passed=len(results) - len(fails), failed=len(fails))
(OUT / "shoot-log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
print(f"\n{len(results) - len(fails)} of {len(results)} checks pass. Log: {OUT / 'shoot-log.json'}")
sys.exit(1 if fails else 0)
PYEOF
STATUS=$?
exit $STATUS
