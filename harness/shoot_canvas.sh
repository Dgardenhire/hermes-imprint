#!/bin/sh
# Letterpress canvas lane, Loop 2: shots S09 to S17 and S20 of the hero brief, with DOM checks, on the REAL routes.
#
#   SEED=<data folder> sh harness/shoot_canvas.sh [OUT_DIR]     shots + checks (default OUT_DIR: .l2-data/shots)
#   SEED=<data folder> sh harness/shoot_canvas.sh serve [PORT]  just the real-model harness, for looking around
#
# SEED is a data folder holding the Harborlight notebook made by the real model (the two sources, the Harborlight
# brand, a pinned answer, and real-model decks); it is copied to a temp folder first, so the seed never changes.
# Default SEED: .l2-data/seed. The live harness (harness/live/server.py) runs with its model replaced by the bench
# adapter (harness/bench/bench.py ClaudeCli: one `claude -p` run per structured call, tools and settings off), so
# Stronger headline, Turn into a chart, Fix it for me and the graphic options are real model calls, each logged as
# one JSON run log in OUT_DIR/runs/. Nothing is stood in: the page talks to the real routes, and the script
# registers no request routes (a check asserts it).
#
# Needs /usr/bin/python3 with Playwright and its Chromium (always launched with --mute-audio and
# --autoplay-policy=user-gesture-required), the built desktop/plugin.js (node vendor/hermes-ui-kit/scripts/
# build.mjs .), the `claude` CLI, and network for React from esm.sh. Exit code 1 when any check fails.
# Never touches ~/.hermes and never runs a hermes command.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=/usr/bin/python3
WORK="$ROOT/.l2-data"
SEED="${SEED:-$WORK/seed}"
mkdir -p "$WORK"
[ -d "$SEED" ] || { echo "No seed data folder at $SEED (set SEED=...)" >&2; exit 2; }

serve() { # serve PORT DATA LOGS: the live harness with the real model (exec, so killing the job kills the server)
  exec "$PY" - "$ROOT" "$1" "$2" "$3" <<'PYEOF'
import sys, time, types
from pathlib import Path
WT, PORT, DATA, LOGS = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3], Path(sys.argv[4])
LOGS.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(WT / "harness" / "bench"))
import bench  # the AI lane's real-model adapter (claude -p)
fake = types.ModuleType("persona_model")
fake.PersonaModel = lambda: bench.ClaudeCli(LOGS, "canvas-" + time.strftime("%H%M%S"), "")
sys.modules["persona_model"] = fake
server_py = WT / "harness" / "live" / "server.py"
head = server_py.read_text().split('\nif __name__ == "__main__":\n    port', 1)[0]
sys.argv = [str(server_py), str(PORT), "--data", DATA]
ns = {"__name__": "__main__", "__file__": str(server_py)}
exec(compile(head, str(server_py), "exec"), ns)
print(f"Letterpress live harness, real model, http://127.0.0.1:{PORT}/harness/index.html?live=1  data {DATA}  logs {LOGS}", flush=True)
ns["serve"](PORT).serve_forever()
PYEOF
}

PORT=${PORT:-8833}
[ "$1" = "serve" ] && PORT=${2:-$PORT}
if curl -s -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then echo "Port $PORT is in use; set PORT=..." >&2; exit 2; fi
D="$(mktemp -d "$WORK/shoot.XXXXXX")"
cp -R "$SEED/." "$D/"
if [ "$1" = "serve" ]; then
  export BENCH_NEUTRAL=1
  serve "$PORT" "$D" "$WORK/serve-runs"
  exit 0
fi
OUT="${1:-$WORK/shots}"
mkdir -p "$OUT/runs"
export BENCH_NEUTRAL=1
serve "$PORT" "$D" "$OUT/runs" >"$OUT/runs/server.log" 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -rf "$D"' EXIT
curl -s --retry 30 --retry-connrefused --retry-delay 1 -o /dev/null "http://127.0.0.1:$PORT/api/state"
"$PY" - "http://127.0.0.1:$PORT" "$OUT" "${ONLY:-}" <<'PYEOF'
"""Canvas lane shots and DOM checks against the real-model live harness. No request routing: every answer comes
from the real routes. Usage: shoot.py BASE OUT_DIR [ONLY]"""
import json, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1], Path(sys.argv[2]).resolve()
ONLY = set(sys.argv[3].split(",")) if len(sys.argv) > 3 and sys.argv[3] else None
ARGS = ["--mute-audio", "--autoplay-policy=user-gesture-required"]
RED, GREEN = "e5484d", "30a46c"
results, shots, routed = [], [], []


def want(s):
    return ONLY is None or s in ONLY


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def api(path, body=None):
    req = urllib.request.Request(f"{BASE}/api/{path}", data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def text_of(n):
    return "" if not isinstance(n, dict) or n.get("t") == "sup" else (n.get("x") or "") + "".join(text_of(k) for k in n.get("k") or [])


def spans(n, out):
    """Every drawn node that carries a claim id: (claim id, its text, its tag)."""
    if not isinstance(n, dict):
        return out
    t = n.get("tr") if isinstance(n.get("tr"), str) else (n.get("a") or {}).get("tr")
    if isinstance(t, str):
        out.append((t, text_of(n), n.get("t")))
    for k in n.get("k") or []:
        spans(k, out)
    return out


# ---- pick the decks from the real data: the hero exhibit (a bar for 287), a drawn worked-out number, an edit deck
decks = [api(f"outputs/{o['id']}") for o in api("state")["outputs"] if o["kind"] == "deck"]
def frames(o):
    return [k for k in o["proofs"][0]["tree"]["k"] if "ip-scene" in str(k.get("c") or "")]
HERO = COMP = EDIT = None
for o in decks:
    p = o["proofs"][0]
    for f, sc in enumerate(frames(o)):
        drawn = spans(sc, [])
        if HERO is None and "exhibit" in str(sc.get("c")) and any(p["claims"].get(c, {}).get("value") == "287" and tag == "div" for c, _t, tag in drawn):
            HERO = (o, f)
        if COMP is None and any(p["claims"].get(c, {}).get("status") == "computed" and tag == "span" for c, _t, tag in drawn):
            COMP = (o, f, next(t for c, t, tag in drawn if p["claims"].get(c, {}).get("status") == "computed" and tag == "span"))
    for f, row in enumerate(p["slides"]):
        if EDIT is None and row.get("type") == "content" and "1,148" in row.get("title", ""):
            EDIT = (o, f)
for _kind in ("content", "comparison", "figures"):  # a deck built round 8 may carry no plain content slide
    EDIT = EDIT or next(((o, f) for o in decks for f, r in enumerate(o["proofs"][0]["slides"]) if r.get("type") == _kind and r.get("title")), None)
check("data: a real-model deck with the hero exhibit (a 287 bar)", HERO, HERO and f"{HERO[0]['id']} frame {HERO[1]}")
check("data: a real-model deck with a drawn worked-out number", COMP, COMP and f"{COMP[0]['id']} frame {COMP[1]} '{COMP[2]}'")
check("data: a real-model deck with a content slide to edit", EDIT, EDIT and f"{EDIT[0]['id']} frame {EDIT[1]}")
(OUT / "decks.json").write_text(json.dumps({"hero": HERO and [HERO[0]["id"], HERO[1]], "computed": COMP and [COMP[0]["id"], COMP[1], COMP[2]],
                                            "edit": EDIT and [EDIT[0]["id"], EDIT[1]]}, indent=1))


def open_page(pw, w, h, theme="light", accent=None, reduced=False, oid=None, frame=None):
    b = pw.chromium.launch(args=ARGS)
    ctx = b.new_context(viewport={"width": w, "height": h}, reduced_motion="reduce" if reduced else "no-preference", device_scale_factor=1)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    q = f"live=1&theme={theme}" + (f"&accent={accent}" if accent else "")
    pg.goto(f"{BASE}/harness/index.html?{q}")
    pg.wait_for_selector("html[data-ready='1']", timeout=60000)
    pg.evaluate(f"import('/desktop/plugin.js').then(m => m.view('{oid}'))")
    pg.wait_for_selector(".ip-cv-slide", timeout=20000)
    pg.evaluate("document.fonts.ready")
    if frame is not None:
        goto_frame(pg, frame)
    pg.wait_for_timeout(500)
    return b, pg, errs


def goto_frame(pg, f):
    pg.evaluate(f"document.querySelector(\".ip-cv-thumb[data-frame='{f}']\").click()")
    pg.wait_for_timeout(350)


def set_look(pg, theme=None, size=None):
    if theme:
        pg.evaluate(f"document.documentElement.dataset.theme = '{theme}'; document.documentElement.classList.toggle('dark', {str(theme == 'dark').lower()})")
    if size:
        pg.set_viewport_size({"width": size[0], "height": size[1]})
    pg.wait_for_timeout(450)


def shot(pg, name):
    p = OUT / f"{name}.png"
    pg.screenshot(path=str(p))
    shots.append(p.name)
    return p


def rect(pg, sel):
    return pg.evaluate(f"(() => {{ const e = document.querySelector({json.dumps(sel)}); return e ? e.getBoundingClientRect().toJSON() : null }})()")


def base_checks(pg, tag):
    m = pg.evaluate("""() => {
      const r = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null }
      const small = []
      for (const el of document.querySelectorAll('.ip-cv *')) {
        if (el.closest('[role=img]') || el.closest('.ip-cv-art')) continue
        const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
        if (!own) continue
        const cs = getComputedStyle(el)
        if (cs.visibility === 'hidden' || cs.display === 'none' || el.getClientRects().length === 0) continue
        if (parseFloat(cs.fontSize) < 12) small.push(el.className + ':' + cs.fontSize + ':' + el.textContent.trim().slice(0, 20))
      }
      const chrome = [...document.querySelectorAll('.ip-cv-head, .ip-cv-strip, .ip-cv-revise, .ip-cv-film [aria-label], .ip-cv-bar, .ip-cv-card')]
        .map(e => e.innerText + ' ' + [...e.querySelectorAll('[aria-label]')].map(x => x.getAttribute('aria-label')).join(' ')).join(' ')
      const words = (chrome.match(/\\btokens?\\b|\\bclaims?\\b|\\bpassages?\\b|\\bscenes?\\b|grounding|trace table|\\bkit\\b/ig) || [])
      const head = [...document.querySelectorAll('.ip-cv-head button')].map(b => b.innerText.trim())
      const stamp = document.querySelector('.ip-cv-stamp')
      return { stage: r('.ip-cv-stage').width, slide: r('.ip-cv-slide').width, strip: r('.ip-cv-strip').width, rev: (r('.ip-cv-revise') || { width: 0 }).width, revBtn: [...document.querySelectorAll('.ip-cv-head button')].some(b => b.innerText.trim().startsWith('Revise')), small, words,
               selects: document.querySelectorAll('select').length, sw: document.body.scrollWidth, ww: window.innerWidth, dsw: document.documentElement.scrollWidth,
               head, stamp: stamp ? stamp.innerText.trim() : '' }
    }""")
    check(f"{tag}: no native select", m["selects"] == 0, str(m["selects"]))
    check(f"{tag}: no horizontal page scroll", m["sw"] <= m["ww"] and m["dsw"] <= m["ww"], f"body {m['sw']}, page {m['dsw']}, window {m['ww']}")
    check(f"{tag}: no live text under 12px outside the slide", not m["small"], "; ".join(m["small"][:4]))
    check(f"{tag}: no inside words in the chrome", not m["words"], ",".join(m["words"]))
    check(f"{tag}: no Delete beside Export (Delete is in More)", "Delete" not in m["head"] and "Export" in m["head"], " | ".join(m["head"]))
    check(f"{tag}: the stamp is one sentence", m["stamp"].count(".") == 1 and m["stamp"].endswith("."), m["stamp"])
    cut = pg.evaluate("""() => [...document.querySelectorAll('.ip-cv-head *, .ip-cv-num *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()))
      .filter(e => e.clientWidth > 0 && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent.trim().slice(0, 30))""")
    check(f"{tag}: no title, stamp or source name is cut", not cut, " | ".join(cut))
    return m


def headline_px(pg):
    return pg.evaluate("""() => {
      const art = document.querySelector('.ip-cv-slide .ip-cv-art'); if (!art) return 0
      const s = art.getBoundingClientRect().width / art.offsetWidth
      let best = 0
      for (const e of art.querySelectorAll('.ip-sc-t')) if (e.textContent.trim().split(/\\s+/).length >= 3) best = Math.max(best, parseFloat(getComputedStyle(e).fontSize))
      return best * s
    }""")


def scroll_state(pg):
    return pg.evaluate("[document.scrollingElement, ...document.querySelectorAll('*')].filter(e => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1).map(e => e.scrollTop + ',' + e.scrollLeft).join('|')")


def hover(pg, cid=None, value=None, tag="span"):
    if cid is None:
        cid = pg.evaluate(f"[...document.querySelectorAll('.ip-cv-slide span[data-cid]')].find(e => e.textContent === {json.dumps(value)})?.dataset.cid")
    el = pg.query_selector(f".ip-cv-slide {tag}[data-cid='{cid}']")
    bb = el.bounding_box()
    t0 = time.time()
    pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
    pg.wait_for_selector(".ip-cv-card", timeout=2000)
    return cid, time.time() - t0


def unhover(pg):
    pg.mouse.move(3, pg.viewport_size["height"] - 3)
    pg.wait_for_timeout(200)


def trace_info(pg):
    return pg.evaluate("""() => {
      const card = document.querySelector('.ip-cv-card'), film = document.querySelector('.ip-cv-film')
      const c = card && card.getBoundingClientRect(), f = film && film.getBoundingClientRect()
      // every routed line: its points, whether any segment inside the slide crosses a word, and where it ends
      const slide = document.querySelector('.ip-cv-slide'), so = slide && slide.getBoundingClientRect()
      const words = []
      if (slide) { const w = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT), rg = document.createRange()
        for (let t = w.nextNode(); t; t = w.nextNode()) { if (!t.textContent.trim()) continue; rg.selectNodeContents(t); for (const r of rg.getClientRects()) words.push({ r, t: t.textContent.trim() }) } }
      const crossings = [], ends = []
      for (const g of document.querySelectorAll('.ip-cv-paths g')) {
        const pts = JSON.parse(g.dataset.pts || '[]')
        ends.push(pts[pts.length - 1])
        for (let i = 1; i < pts.length; i++) {
          const [a, b] = [pts[i - 1], pts[i]]
          const box = { l: Math.min(a[0], b[0]), r: Math.max(a[0], b[0]), t: Math.min(a[1], b[1]), b: Math.max(a[1], b[1]) }
          if (!so || box.r < so.left || box.l > so.right) continue
          // walk the segment (it may run on a slant) and test each point against each word
          const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 2))
          for (const { r, t } of words) {
            if (i === pts.length - 1 && r.left - 2 <= b[0] && r.right + 2 >= b[0] && r.top - 2 <= b[1] && r.bottom + 2 >= b[1]) continue
            for (let k = 0; k <= n; k++) { const x = a[0] + (b[0] - a[0]) * k / n, y = a[1] + (b[1] - a[1]) * k / n
              if (x > r.left && x < r.right && y > r.top && y < r.bottom) { crossings.push(t); break } }
          }
        }
      }
      const sw = [...document.querySelectorAll('.ip-cv-path')].map(e => parseFloat(getComputedStyle(e).strokeWidth))
      const pts = [...document.querySelectorAll('.ip-cv-paths g')].map(g => JSON.parse(g.dataset.pts || '[]'))
      return { lines: document.querySelectorAll('.ip-cv-paths g').length, crossings, ends, sw, pts, lit: [...document.querySelectorAll('.ip-cv-strip .ip-cv-n.is-lit')].map(e => e.textContent),
               card: card ? card.innerText : '', overlap: !!(c && f && c.bottom > f.top && c.top < f.bottom && c.right > f.left && c.left < f.right),
               cardHits: (() => { if (!c || !so) return []; const out = []
                 for (const { r, t } of words) if (r.left < c.right && r.right > c.left && r.top < c.bottom && r.bottom > c.top) out.push(t)
                 for (const e of slide.querySelectorAll('.ip-cv-hot')) { const r = e.getBoundingClientRect(); if (r.left < c.right && r.right > c.left && r.top < c.bottom && r.bottom > c.top) out.push('a bar') }
                 return out })() }
    }""")


def hero_run(pw, size, theme, accent=None, tagx=""):
    o, f = HERO
    p = o["proofs"][0]
    w, h = size
    tag = f"{w}x{h} {theme}{(' ' + tagx) if tagx else ''}"
    sfx = f"{w}-{theme}" + (f"-{tagx}" if tagx else "")
    b, pg, errs = open_page(pw, w, h, theme, accent, oid=o["id"], frame=f)
    try:
        m = base_checks(pg, tag)
        if w >= 1280:
            check(f"{tag}: evidence strip is 200px", abs(m["strip"] - 200) < 0.6, str(m["strip"]))
        else:
            check(f"{tag}: evidence strip folds to a 40px rail so the slide keeps its size", abs(m["strip"] - 40) < 0.6, f"strip {m['strip']}, slide {m['slide']}")
        check(f"{tag}: Revise is a labeled button in the head, no side rail", m["revBtn"] and m["rev"] == 0, f"button {m['revBtn']}, rail {m['rev']}")
        cue = pg.evaluate("(document.querySelector('.ip-cv-cue') || {}).innerText || ''")
        check(f"{tag}: the first-open cue shows", cue == "Point at any number to see where it came from.", cue)
        nums = pg.evaluate("[...document.querySelectorAll('.ip-cv-num')].map(e => e.innerText.replace(/\\s+/g, ' ').trim())")
        check(f"{tag}: Numbers on this slide lists each number with its source", len(nums) >= 3 and any(x.startswith("287") for x in nums), " | ".join(nums))
        if w == 1440:
            check(f"{tag}: slide 880px or wider", m["slide"] >= 880, str(m["slide"]))
        hp = headline_px(pg)
        check(f"{tag}: S09 headline 36px or more on screen", hp >= 36, f"{hp:.1f}px")
        dates = pg.evaluate("[...document.querySelectorAll('.ip-cv-slide [data-cid]')].map(e => e.textContent).filter(t => /October|^FY20\\d\\d$|^20\\d\\d$/.test(t))")
        check(f"{tag}: no date carries an underline", not dates, ",".join(dates))
        if want("S09"):
            shot(pg, f"S09-canvas-frame0-{sfx}")
        if w == 1024:
            fl = pg.evaluate("({arrow: !!document.querySelector('.ip-cv-arrow.is-r'), clip: document.querySelector('.ip-cv-film').scrollWidth > document.querySelector('.ip-cv-film').clientWidth})")
            check(f"{tag}: the filmstrip clips and shows its arrow", fl["arrow"] and fl["clip"], str(fl))
            for _ in range(6):
                if not pg.query_selector(".ip-cv-arrow.is-r"):
                    break
                pg.click(".ip-cv-arrow.is-r"); pg.wait_for_timeout(450)
            last = pg.evaluate("(() => { const t = [...document.querySelectorAll('.ip-cv-thumb')].pop().getBoundingClientRect(), f = document.querySelector('.ip-cv-film').getBoundingClientRect(); return t.right <= f.right + 1 && t.left >= f.left - 1 })()")
            check(f"{tag}: the last thumbnail is reachable", last)
            shot(pg, f"S09-filmstrip-end-{sfx}")
            return
        # S10: hover the 287 bar
        cid287 = next(c for c, cl in p["claims"].items() if cl["value"] == "287")
        s0 = scroll_state(pg)
        _c, secs = hover(pg, cid=cid287, tag="div")
        pg.wait_for_timeout(200)
        ti = trace_info(pg)
        check(f"{tag}: S10 hover 287 bar: the card shows in under 200 ms", secs < 0.2, f"{secs * 1000:.0f} ms")
        check(f"{tag}: S10 one 2px line", ti["lines"] == 1 and ti["sw"] == [2.0], f"{ti['lines']} lines, widths {ti['sw']}")
        check(f"{tag}: S10 the line crosses no word on the slide", not ti["crossings"], ",".join(ti["crossings"]))
        bar = pg.evaluate(f"(() => {{ const r = document.querySelector(\".ip-cv-slide div[data-cid='{cid287}']\").getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom] }})()")
        e = ti["ends"][0] if ti["ends"] else [0, 0]
        check(f"{tag}: S10 the line lands on the 287 bar's left end, at its middle", abs(e[0] - bar[0]) <= 3 and abs(e[1] - (bar[1] + bar[3]) / 2) <= 3, f"end {e}, bar {[round(v) for v in bar]}")
        legs = len(ti["pts"][0]) - 1 if ti["pts"] else 0
        check(f"{tag}: S10 one straight run or one elbow out of the strip (no bracket)", 2 <= legs <= 3, f"{legs} legs: {ti['pts'][:1]}")
        tinted = pg.evaluate(f"document.querySelector(\".ip-cv-slide span[data-cid='{cid287}']\").classList.contains('is-lit')")
        check(f"{tag}: S10 the 287 beside the bar is tinted", tinted)
        check(f"{tag}: S10 the card covers no word or bar on the slide", not ti["cardHits"], ",".join(ti["cardHits"]))
        cue2 = pg.evaluate("!!document.querySelector('.ip-cv-cue')")
        check(f"{tag}: the cue is gone after the first hover", not cue2)
        check(f"{tag}: S10 only '287' is lit in the strip", ti["lit"] == ["287"], str(ti["lit"]))
        check(f"{tag}: S10 the card never covers the filmstrip", not ti["overlap"])
        check(f"{tag}: S10 hovering scrolled nothing", s0 == scroll_state(pg))
        if want("S10"):
            shot(pg, f"S10-trace-287-{sfx}")
        if accent == RED:
            col = pg.evaluate("""() => { const e = [...document.querySelectorAll('.ip-cv-slide span.ip-cv-claim')].find(x => !x.classList.contains('is-missing') && !x.classList.contains('is-lit'));
              const probe = document.createElement('span'); probe.style.color = 'var(--hk-bad-fill)'; document.querySelector('.ip-cv').appendChild(probe)
              const bad = getComputedStyle(probe).color; probe.remove(); return { line: e && getComputedStyle(e).textDecorationColor, bad } }""")
            check(f"{tag}: a valid number's underline is not the error color", col["line"] and col["line"] != col["bad"], str(col))
        unhover(pg)
        # S12: the waitlist sentence clicked in the strip
        ref = next(r for r, pu in p["passages_used"].items() if "287 adults" in pu["text"])
        want_frames = sorted({f2 for f2, row in enumerate(p["slides"]) if any(
            ref in ([cl.get("ref")] + [x.get("ref") for x in (cl.get("math") or {}).get("operands") or []]) for cl in (p["claims"].get(c) for c in row["claims"]) if cl)})
        pg.click(".ip-cv-ev-s:has-text('287 adults were on the waitlist')"); pg.wait_for_timeout(300)
        hits = pg.evaluate("[...document.querySelectorAll('.ip-cv-thumb.is-hit')].map(e => +e.dataset.frame)")
        check(f"{tag}: S12 the waitlist sentence outlines exactly the slides whose numbers cite it", sorted(hits) == want_frames, f"{hits} vs {want_frames}")
        rev = pg.evaluate("[...document.querySelectorAll('.ip-cv-slide .is-rev')].map(e => e.textContent || 'a bar')")
        check(f"{tag}: S12 the matching numbers on this slide are tinted too", rev and "287" in rev, str(rev))
        if want("S12"):
            shot(pg, f"S12-trace-reverse-{sfx}")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(150)
        if w == 1440 and theme == "light" and not tagx:
            pg.evaluate("document.querySelector('.ip-cv-slide .ip-cv-claim').focus({preventScroll: true})"); pg.wait_for_timeout(150)
            first = pg.evaluate("document.activeElement.textContent")
            pg.keyboard.press("Tab"); pg.wait_for_timeout(150)
            nxt = pg.evaluate("({t: document.activeElement.textContent, claim: document.activeElement.classList.contains('ip-cv-claim'), card: !!document.querySelector('.ip-cv-card')})")
            check(f"{tag}: Tab moves to the next number and its card opens", nxt["claim"] and nxt["t"] != first and nxt["card"], f"{first} -> {nxt['t']}")
            pg.keyboard.press("Enter"); pg.wait_for_timeout(120)
            pinned = pg.evaluate("document.querySelectorAll('.ip-cv-claim.is-pinned').length")
            pg.keyboard.press("Escape"); pg.wait_for_timeout(120)
            check(f"{tag}: Enter pins, Escape unpins", pinned == 1 and pg.evaluate("document.querySelectorAll('.ip-cv-claim.is-pinned').length") == 0)
    finally:
        check(f"{tag}: no console errors", not errs, "; ".join(errs[:3]))
        b.close()


def computed_run(pw, size, theme, accent=None, tagx=""):
    o, f, value = COMP
    w, h = size
    tag = f"{w}x{h} {theme}{(' ' + tagx) if tagx else ''} S11"
    sfx = f"{w}-{theme}" + (f"-{tagx}" if tagx else "")
    b, pg, errs = open_page(pw, w, h, theme, accent, oid=o["id"], frame=f)
    try:
        cid = next(c for c, cl in o["proofs"][0]["claims"].items() if cl["status"] == "computed" and cl["value"] in value)
        cl = o["proofs"][0]["claims"][cid]
        hover(pg, cid=cid); pg.wait_for_timeout(250)
        ti = trace_info(pg)
        where = f"{cl['source']}, {cl['locator'].strip('“”')}"
        check(f"{tag}: the card shows the math and the source name and section", cl["math"]["text"] in ti["card"] and where in ti["card"], ti["card"].replace("\n", " / "))
        check(f"{tag}: the math uses a real minus sign", "−" in ti["card"])
        ops = sorted(x["value"] for x in cl["math"]["operands"])
        check(f"{tag}: both operands lit in the strip, one line each", sorted(ti["lit"]) == ops and ti["lines"] == len(ops), f"{ti['lit']} / {ti['lines']} lines")
        check(f"{tag}: the card never covers the filmstrip", not ti["overlap"])
        check(f"{tag}: the card covers no word or bar on the slide", not ti["cardHits"], ",".join(ti["cardHits"]))
        check(f"{tag}: the lines cross no word on the slide", not ti["crossings"], ",".join(ti["crossings"]))
        shot(pg, f"S11-trace-computed-{sfx}")
    finally:
        check(f"{tag}: no console errors", not errs, "; ".join(errs[:3]))
        b.close()


def wait_job(pg, sel, limit=300):
    t = time.time()
    pg.wait_for_selector(sel, timeout=limit * 1000)
    return round(time.time() - t, 1)


def select_headline(pg):
    idx = pg.evaluate("""(() => { let best = -1, size = 0; document.querySelectorAll('.ip-cv-slide [data-el]').forEach(e => { const fs = parseFloat(getComputedStyle(e).fontSize);
      if (e.textContent.trim().length > 2 && fs > size) { size = fs; best = e.dataset.el } }); return best })()""")
    bb = pg.query_selector(f".ip-cv-slide [data-el='{idx}']").bounding_box()
    pg.mouse.click(bb["x"] + bb["width"] - 24, bb["y"] + bb["height"] / 2)
    pg.wait_for_timeout(350)
    return idx


def edit_run(pw):
    """S13 Stronger headline, Keep and Undo; S14 Turn into a chart; S15 Fix it for me; S16 Export ready. One real model
    call each; every size and theme is shot from the same page by resizing and switching the theme."""
    o, f = EDIT
    b, pg, errs = open_page(pw, 1440, 900, "light", oid=o["id"], frame=f)
    try:
        idx = select_headline(pg)
        sel = rect(pg, f".ip-cv-slide [data-el='{idx}']")
        bar = rect(pg, ".ip-cv-bar")
        check("S13: the floating bar sits above the selection", bar and bar["bottom"] <= sel["top"] + 1, f"bar bottom {bar and bar['bottom']:.0f}, selection top {sel['top']:.0f}")
        live = pg.evaluate(f"document.querySelector(\".ip-cv-slide [data-el='{idx}']\").innerText.replace(/\\s+/g, ' ').trim()")
        pg.click(".ip-cv-bar-btn:has-text('Stronger headline')")
        pg.wait_for_timeout(1500)
        shot(pg, "S13-edit-headline-working-1440-light")
        secs = wait_job(pg, ".ip-cv-opt, .ip-cv-card-s[role=alert]")
        pg.wait_for_timeout(400)
        info = pg.evaluate("""() => ({ slide: document.querySelector('.ip-cv-slide').getBoundingClientRect().width, opts: document.querySelectorAll('.ip-cv-opt').length,
          primary: document.querySelectorAll('.ip-cv-opt.is-on button').length, use: [...document.querySelectorAll('.ip-cv-opt:not(.is-on) button')].map(b => b.innerText.trim()),
          now: (document.querySelector('.ip-cv-now-t') || {}).innerText || '', revActs: document.querySelectorAll('.ip-cv-revise .ip-cv-rev-act').length })""")
        check("S13: three options came back from the real model", info["opts"] == 3, f"{info['opts']} options in {secs} s")
        check("S13: one primary Keep, the others Use this", info["primary"] == 1 and set(info["use"]) == {"Use this"}, str(info))
        check("S13: no action buttons repeated in Revise", info["revActs"] == 0)
        check("S13: the slide stays 880px or wider with Revise open", info["slide"] >= 880, str(info["slide"]))
        check("S13: 'Now' shows the slide's live text exactly", info["now"] == live, f"{info['now']!r} vs {live!r}")
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size)
            shot(pg, f"S13-edit-headline-{name}")
        set_look(pg, "light", (1440, 900))
        fl = pg.evaluate("({arrow: !!document.querySelector('.ip-cv-arrow.is-r'), clip: document.querySelector('.ip-cv-film').scrollWidth > document.querySelector('.ip-cv-film').clientWidth})")
        if fl["clip"]:
            check("Revise open: the clipped filmstrip shows its arrow", fl["arrow"], str(fl))
        before = live  # the stage shows the chosen option as a preview now, so the slide's own text is the one read before
        pg.click(".ip-cv-opt.is-on button:has-text('Keep')")
        pg.wait_for_selector(".ip-cv-head button:has-text('Undo')", timeout=15000); pg.wait_for_timeout(600)
        kept = pg.evaluate(f"(document.querySelector(\".ip-cv-slide [data-el='{idx}']\") || {{}}).innerText")
        check("Keep: the slide changes and Undo shows at the top", kept and kept.replace("\n", " ").strip() != before, f"{before!r} -> {kept!r}")
        unhover(pg)
        shot(pg, "S13-kept-undo-1440-light")
        pg.click(".ip-cv-head button:has-text('Undo')"); pg.wait_for_timeout(2500)
        back = pg.evaluate(f"document.querySelector(\".ip-cv-slide [data-el='{idx}']\").innerText.replace(/\\s+/g, ' ').trim()")
        check("Undo: the slide is back as it was", back == before, f"{back!r}")
        # S15: the headline changed to a number not in the sources, through Edit text (the real edit route)
        select_headline(pg)
        pg.click(".ip-cv-bar-btn:has-text('Edit text')"); pg.wait_for_timeout(250)
        new = "1,200 learners in one year"
        pg.fill("#ip-cv-edit", new)
        pg.click(".ip-cv-revise button:has-text('Save')")
        pg.wait_for_selector(".ip-cv-flag", timeout=15000); pg.wait_for_timeout(500); unhover(pg)
        pre = pg.evaluate("({accept: [...document.querySelectorAll('.ip-cv-revise button')].some(b => b.innerText.trim() === 'Accept'), fix: [...document.querySelectorAll('.ip-cv-revise button')].some(b => b.innerText.trim() === 'Fix it for me'), flag: document.querySelector('.ip-cv-flag').innerText, exp: document.querySelector('.ip-cv-export button').getAttribute('aria-disabled')})")
        check("S15 before the click: the flag in plain words and Fix it for me, no Accept", pre["fix"] and not pre["accept"] and "isn’t in your sources" in pre["flag"], pre["flag"].replace("\n", " / "))
        check("S15: Export is held while a number is not in the sources", pre["exp"] == "true")
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size); shot(pg, f"S15-fix-it-flag-{name}")
        set_look(pg, "light", (1440, 900))
        pg.click(".ip-cv-flag button:has-text('Fix it for me')")
        secs = wait_job(pg, ".ip-cv-diff, .ip-cv-flag[role=alert]")
        pg.wait_for_timeout(400)
        post = pg.evaluate("({accept: [...document.querySelectorAll('.ip-cv-revise button')].some(b => b.innerText.trim() === 'Accept'), fix: [...document.querySelectorAll('.ip-cv-revise button')].some(b => b.innerText.trim() === 'Fix it for me'), diff: (document.querySelector('.ip-cv-diff') || {}).innerText || ''})")
        check("S15 after the click: the word-by-word change and Accept, no Fix it for me", post["accept"] and not post["fix"], f"{post['diff']!r} in {secs} s")
        check("S15: the change reads 1,148 adult learners", "1,148" in post["diff"], post["diff"])
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size); shot(pg, f"S15-fix-it-{name}")
        set_look(pg, "light", (1440, 900))
        pg.click(".ip-cv-flag button:has-text('Accept')")
        pg.wait_for_function("!document.querySelector('.ip-cv-flag')", timeout=15000); pg.wait_for_timeout(600)
        st = pg.evaluate("({stamp: document.querySelector('.ip-cv-stamp').innerText.trim(), exp: document.querySelector('.ip-cv-export button').getAttribute('aria-disabled')})")
        _n = st["stamp"].split(" ")
        check("S16: after Accept the stamp says every number matches and Export turns on", len(_n) == 5 and _n[0] == _n[2] and st["stamp"].endswith("numbers match.") and st["exp"] is None, str(st))
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size); unhover(pg); shot(pg, f"S16-export-ready-{name}")
        set_look(pg, "light", (1440, 900))
        # S14: Turn into a chart, on the first content slide whose numbers allow it
        p = api(f"outputs/{o['id']}")["proofs"][0]
        cand = [f2 for f2, row in sorted(enumerate(p["slides"]), key=lambda x: x[1].get("type") != "comparison") if row.get("type") in ("comparison", "content") and len({p["claims"][c]["value"] for c in row["claims"] if p["claims"][c]["status"] in ("exact", "close", "computed") and p["claims"][c]["kind"] != "quote"}) >= 2]
        if not cand:
            check("S14: a content slide with two or more matching numbers", False)
            return
        goto_frame(pg, cand[0]); select_headline(pg)
        pg.click(".ip-cv-bar-btn:has-text('Turn into a chart')")
        t0 = time.time()
        pg.wait_for_timeout(800)
        done = "document.querySelector('.ip-cv-revise .ip-cv-card-s') && !document.querySelector('.ip-cv-revise .ip-cv-spin')"
        pg.wait_for_function(done, timeout=300000)
        if not pg.query_selector(".ip-cv-opt") and pg.query_selector(".ip-cv-revise .ip-cv-card-s button:has-text('Retry')"):
            check("S14: the first chart did not pass the check, so the slide stayed (shown, then Retry pressed once)", True)
            shot(pg, "S14-edit-chart-unchanged-1440-light")
            pg.click(".ip-cv-revise .ip-cv-card-s button:has-text('Retry')"); pg.wait_for_timeout(800)
            pg.wait_for_function(done, timeout=300000)
        secs = round(time.time() - t0, 1)
        pg.wait_for_timeout(600)
        s14 = pg.evaluate("({opts: document.querySelectorAll('.ip-cv-opt').length, minis: document.querySelectorAll('.ip-cv-revise .ip-cv-mini').length, keep: [...document.querySelectorAll('.ip-cv-opt.is-on button')].map(b => [b.innerText.trim(), b.disabled]), chk: [...document.querySelectorAll('.ip-cv-opt .ip-cv-chk')].map(e => e.innerText), msg: document.querySelector('.ip-cv-revise .ip-cv-card-s').innerText})")
        check("S14: the old slide above the new, drawn in the brand", s14["opts"] >= 1 and s14["minis"] >= 2, f"{s14} in {secs} s")
        check("S14: Keep is on only with the re-check passed", all(not d for _t, d in s14["keep"]) and all("match" in c for c in s14["chk"]), str(s14["keep"]) + str(s14["chk"]))
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size); shot(pg, f"S14-edit-chart-{name}")
    finally:
        check("edit run: no console errors", not errs, "; ".join(errs[:3]))
        b.close()


def reduced_run(pw, theme):
    o, f = HERO
    b, pg, errs = open_page(pw, 1440, 900, theme, reduced=True, oid=o["id"], frame=f)
    try:
        cid287 = next(c for c, cl in o["proofs"][0]["claims"].items() if cl["value"] == "287")
        hover(pg, cid=cid287, tag="div"); pg.wait_for_timeout(300)
        ti = trace_info(pg)
        vis = pg.evaluate("(() => { const s = document.querySelector('.ip-cv-paths'); return s ? getComputedStyle(s).display !== 'none' : false })()")
        check(f"S20 {theme}: no line is drawn with reduced motion", not vis)
        check(f"S20 {theme}: the tint and the card show", ti["lit"] == ["287"] and ti["card"], str(ti["lit"]))
        shot(pg, f"S20-trace-reduced-motion-1440-{theme}")
    finally:
        check(f"S20 {theme}: no console errors", not errs, "; ".join(errs[:3]))
        b.close()


def graphic_run(pw):
    """S17: three graphics from the pinned answer, through the pane's Make a graphic seam (loop2-pane)."""
    notes = api("state").get("notes") or []
    b, pg, errs = open_page(pw, 1440, 900, "light", oid=HERO[0]["id"])
    try:
        has = pg.evaluate("import('/desktop/plugin.js').then(m => typeof m.makeGraphic === 'function')")
        check("S17: the pane's Make a graphic seam is in the bundle", has and notes, f"seam {has}, {len(notes)} pinned answers")
        if not has or not notes:
            return
        pg.evaluate("document.querySelector('.ip-cv-head button').click()"); pg.wait_for_timeout(400)
        pg.evaluate(f"import('/desktop/plugin.js').then(m => m.makeGraphic('{notes[0]['id']}'))")
        secs = wait_job(pg, ".ip-go-opt, .ip-go .ip-cv-card-s[role=alert]")
        pg.wait_for_timeout(1200)
        g = pg.evaluate("({opts: document.querySelectorAll('.ip-go-opt').length, arts: document.querySelectorAll('.ip-go-opt .ip-cv-art').length, forms: [...document.querySelectorAll('.ip-go-opt figcaption strong')].map(e => e.innerText)})")
        check("S17: three different forms side by side in the brand", g["opts"] == 3 and g["arts"] == 3 and len(set(g["forms"])) == 3, f"{g} in {secs} s")
        span = pg.query_selector(".ip-go-opt .ip-cv-claim")
        if span:
            bb = span.bounding_box(); pg.mouse.move(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); pg.wait_for_timeout(300)
        tr = pg.evaluate("[...document.querySelectorAll('.ip-go-trace mark')].map(m => m.innerText)")
        check("S17: a value in a graphic traces to its sentence", span and tr and tr[0] == span.text_content(), f"{span and span.text_content()} -> {tr}")
        for look, size, name in (("light", (1440, 900), "1440-light"), ("dark", (1440, 900), "1440-dark"), ("light", (1280, 800), "1280-light")):
            set_look(pg, look, size); shot(pg, f"S17-graphic-options-{name}")
        set_look(pg, "light", (1440, 900))
        k = next((i for i, f2 in enumerate(g["forms"]) if f2 != "Timeline"), None)
        if k is not None:
            if k:
                pg.click(f".ip-go-opt:nth-child({k + 1}) button:has-text('Use this')"); pg.wait_for_timeout(300)
            deck_id = next(o["id"] for o in api("state")["outputs"] if o["kind"] == "deck")
            v0 = len(api(f"outputs/{deck_id}")["versions"])
            pg.click(".ip-go-opt.is-on button:has-text('Add to the deck')"); pg.wait_for_timeout(2500)
            v1 = api(f"outputs/{deck_id}")["versions"]
            check("S17: Add to the deck saves the graphic as a new deck version", len(v1) == v0 + 1 and v1[-1]["reason"].startswith("Added a graphic"), str(v1[-1]))
            n0 = len([o for o in api("state")["outputs"] if o["kind"] == "visual"])
            pg.click(".ip-go-opt.is-on button:has-text('Save as PNG')"); pg.wait_for_timeout(3000)
            n1 = len([o for o in api("state")["outputs"] if o["kind"] == "visual"])
            check("S17: Save as PNG keeps the graphic and exports it", n1 == n0 + 1, f"{n0} -> {n1} graphics")
            shot(pg, "S17-graphic-saved-1440-light")
    finally:
        check("S17: no console errors", not errs, "; ".join(errs[:3]))
        b.close()


with sync_playwright() as pw:
    if HERO and (want("S09") or want("S10") or want("S12")):
        hero_run(pw, (1440, 900), "light")
        hero_run(pw, (1440, 900), "dark")
        hero_run(pw, (1280, 800), "light")
        hero_run(pw, (1440, 900), "light", RED, "red")
        hero_run(pw, (1440, 900), "light", GREEN, "green")
        hero_run(pw, (1024, 768), "light")
    if COMP and want("S11"):
        computed_run(pw, (1440, 900), "light")
        computed_run(pw, (1440, 900), "dark")
        computed_run(pw, (1280, 800), "light")
        computed_run(pw, (1440, 900), "light", RED, "red")
        computed_run(pw, (1440, 900), "light", GREEN, "green")
    if EDIT and any(want(x) for x in ("S13", "S14", "S15", "S16")):
        edit_run(pw)
    if HERO and want("S20"):
        reduced_run(pw, "light")
        reduced_run(pw, "dark")
    if want("S17"):
        graphic_run(pw)
    check("no request routes registered (no stand-ins)", not routed, str(routed))
    sheet = OUT / "contact-sheet.html"
    cells = "".join(f'<figure><img src="{n}"><figcaption>{n[:-4]}</figcaption></figure>' for n in shots)
    sheet.write_text("<!doctype html><meta charset=utf-8><style>body{margin:0;padding:24px;background:#1b1d22;color:#e8eaee;font:13px -apple-system,sans-serif}"
                     "main{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}figure{margin:0}img{width:100%;display:block;border:1px solid #333}"
                     "figcaption{padding:6px 0}</style><h1 style='font-size:16px'>Letterpress canvas, Loop 2: real routes, real-model data</h1><main>" + cells + "</main>")
    b = pw.chromium.launch(args=ARGS); pg = b.new_page(viewport={"width": 1800, "height": 1200})
    pg.goto(sheet.as_uri()); pg.wait_for_timeout(800); pg.screenshot(path=str(OUT / "contact-sheet.png"), full_page=True); b.close()

fails = [r for r in results if not r[1]]
(OUT / "checks.txt").write_text("\n".join(("PASS " if ok else "FAIL ") + n + (f"  ({d})" if d else "") for n, ok, d in results) + "\n")
print(f"\n{len(results) - len(fails)} of {len(results)} checks pass; {len(shots)} shots in {OUT}")
sys.exit(1 if fails else 0)
PYEOF
