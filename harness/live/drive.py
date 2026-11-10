"""Replay the Nov 8 persona run against live mode and render everything a reviewer needs to look at.

    /usr/bin/python3 harness/live/drive.py OUT_DIR [--port 8791]

Starts harness/live/server.py on a fresh temp data folder, then, through the real routes:
- Denise: sources (Word report, board notes), a kit imported from her brand guide PDF with her logo, a
  one-pager in her kit beside Board Report, the deck; the derived "144" is fixed through Fix the wording.
- Ana: sources (menu, about us), a kit imported from her Canva PowerPoint with her logo, a menu flyer in
  her kit beside Market Board, a 90-second audio brief.
Writes to OUT_DIR: every export (PDF, proof PDF, HTML, PPTX, deck PDF, script), PNGs of each PDF page
(pdftoppm), each HTML export at 390px phone width, the pane in light and dark, and a summary.json with
each proof's checks. Needs Playwright for Python (pane and phone shots) and pdftoppm; it skips what is
missing and says so. Nothing is written outside OUT_DIR and the temp data folder.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
P = HERE / "personas"


def main() -> None:
    out = Path(sys.argv[1]).resolve()
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8791
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp(prefix="imprint-drive-"))
    srv = subprocess.Popen([sys.executable, str(HERE / "server.py"), str(port), "--data", str(data)],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/api/state", timeout=2)
                break
            except Exception:
                time.sleep(0.25)
        summary = run(base, out)
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        shots(base, out, summary)
        rasterize(out)
        print(json.dumps({k: v for k, v in summary.items() if k != "proofs"}, indent=2))
    finally:
        srv.terminate()
        shutil.rmtree(data, ignore_errors=True)


def call(base: str, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + "/api/" + path, data=data, method=method,
                                 headers={"content-type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def upload(base: str, path: str, file: Path):
    return call(base, "POST", path, {"filename": file.name, "data": base64.b64encode(file.read_bytes()).decode()})


def wait(base: str, job: dict) -> dict:
    for _ in range(600):
        j = call(base, "GET", f"jobs/{job['id']}")
        if j["status"] in ("done", "failed"):
            if j["status"] == "failed":
                raise RuntimeError(j)
            return j
        time.sleep(0.1)
    raise TimeoutError(job)


def source(base: str, file: Path) -> str:
    return wait(base, upload(base, "sources/file", file)["job"])["result"]["source"]["id"]


def kit_from(base: str, file: Path, logo: Path) -> dict:
    draft = upload(base, "kits/import/file", file)["draft"]
    kit = call(base, "POST", f"kits/import/{draft['draft_id']}/save", {})
    kid = kit["kit"]["id"]
    upload(base, f"kits/{kid}/logo", logo)
    return {"id": kid, "draft": {k: draft[k] for k in ("kit", "skipped", "checks")}}


def make(base: str, kind: str, srcs: list, kits: list, brief: str) -> dict:
    j = wait(base, call(base, "POST", "outputs", {"kind": kind, "source_ids": srcs, "kit_ids": kits, "brief": brief})["job"])
    return call(base, "GET", f"outputs/{j['result']['output_id']}")


def export(base: str, out: Path, oid: str, kid: str, fmt: str, name: str) -> str:
    r = call(base, "POST", f"outputs/{oid}/export", {"kit_id": kid, "format": fmt})
    dst = out / name
    shutil.copy(r["path"], dst)
    return dst.name


def run(base: str, out: Path) -> dict:
    s = {"exports": [], "proofs": {}}
    d_src = [source(base, P / "denise" / "FY26-Program-Report.docx"), source(base, P / "denise" / "board-retreat-notes.txt")]
    harbor = kit_from(base, P / "denise" / "Harborlight-Brand-Guide-2025.pdf", P / "denise" / "harborlight-logo.png")
    s["denise_kit"] = harbor["draft"]["kit"]
    one = make(base, "onepager", d_src, [harbor["id"], "board-report"], "A one-page brief for the October 21 board vote on the FY2027 budget")
    for p in one["proofs"]:
        s["proofs"][f"denise-onepager-{p['kit_id']}"] = [c["label"] for c in p["checks"]]
        for g in p["grounding"]:
            if g["status"] == "missing" and g["kind"] == "number":  # the model's derived "144": fix the wording
                ctx = (g.get("context") or "").replace(", about 144 fewer people waiting", "")
                one = call(base, "POST", f"outputs/{one['id']}/edit", {"path": g["path"], "text": ctx})
    call(base, "POST", "prefs", {"pair": [harbor["id"], "board-report"]})
    for kid, tag in ((harbor["id"], "harborlight"), ("board-report", "board-report")):
        for fmt, ext in (("pdf", "pdf"), ("proof", "proof.pdf"), ("html", "html")):
            s["exports"].append(export(base, out, one["id"], kid, fmt, f"denise-{tag}.{ext}"))
    deck = make(base, "deck", d_src, [harbor["id"], "market-board"], "A short deck board members can use with funders")
    s["proofs"]["denise-deck"] = [c["label"] for p in deck["proofs"] for c in p["checks"]]
    for g in [g for p in deck["proofs"] for g in p["grounding"] if g["status"] == "missing"]:
        deck = call(base, "POST", f"outputs/{deck['id']}/decide", {"key": g["key"], "action": "keep"})
    s["exports"] += [export(base, out, deck["id"], harbor["id"], "pptx", "denise-deck.pptx"),
                     export(base, out, deck["id"], harbor["id"], "pdf", "denise-deck.pdf")]

    a_src = [source(base, P / "ana" / "fall-menu.txt"), source(base, P / "ana" / "about-us.txt")]
    salvia = kit_from(base, P / "ana" / "Salvia Kitchen Brand Kit.pptx", P / "ana" / "salvia-logo.png")
    s["ana_kit"] = salvia["draft"]["kit"]
    kit = call(base, "GET", f"kits/{salvia['id']}")["kit"]
    kit["layout"], kit["rules"] = "flyer", {**kit["rules"], "sources": False}
    call(base, "POST", f"kits/{salvia['id']}", {"kit": kit})
    menu = make(base, "onepager", a_src, [salvia["id"], "market-board"], "A menu flyer for office managers ordering fall catering")
    s["proofs"]["ana-menu"] = [c["label"] for p in menu["proofs"] for c in p["checks"]]
    for kid, tag in ((salvia["id"], "salvia"), ("market-board", "market-board")):
        s["exports"] += [export(base, out, menu["id"], kid, "pdf", f"ana-{tag}.pdf"), export(base, out, menu["id"], kid, "html", f"ana-{tag}.html")]
    audio = make(base, "audio", a_src, [salvia["id"]], "A 90-second audio brief for office managers")
    s["proofs"]["ana-audio"] = [c["label"] for p in audio["proofs"] for c in p["checks"]]
    s["exports"].append(export(base, out, audio["id"], salvia["id"], "script", "ana-audio-script.txt"))
    s["ids"] = {"denise_onepager": one["id"], "denise_deck": deck["id"], "ana_menu": menu["id"], "ana_audio": audio["id"],
                "harbor": harbor["id"], "salvia": salvia["id"]}
    return s


def shots(base: str, out: Path, s: dict) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright for Python is not installed: pane and phone shots skipped.")
        return
    ids = s["ids"]
    views = [("pane-denise-onepager", f"tab=proofs&kind=onepager&pair={ids['harbor']},board-report"),
             ("pane-denise-deck", f"tab=proofs&kind=deck&pair={ids['harbor']},market-board"),
             ("pane-ana-menu", f"tab=proofs&kind=onepager&pair={ids['salvia']},market-board"),
             ("pane-kits", "tab=kits")]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for theme in ("light", "dark"):
            pg = b.new_page(viewport={"width": 1500, "height": 1000})
            for name, q in views:
                if "menu" in name:  # the pane opens the latest one-pager; select the menu by pair and reload
                    call(base, "POST", "prefs", {"pair": [ids["salvia"], "market-board"], "output": ids["ana_menu"]})
                elif "denise-onepager" in name:
                    call(base, "POST", "prefs", {"pair": [ids["harbor"], "board-report"], "output": ids["denise_onepager"]})
                pg.goto(f"{base}/harness/index.html?live=1&theme={theme}&{q}")
                pg.wait_for_selector("html[data-ready='1']", timeout=30000)
                pg.wait_for_timeout(2500)
                pg.screenshot(path=str(out / f"{name}-{theme}.png"))
            pg.close()
        phone = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        for f in sorted(out.glob("*.html")):
            phone.goto(f.as_uri())
            phone.wait_for_timeout(300)
            over = phone.evaluate("() => document.documentElement.scrollWidth - innerWidth")
            s.setdefault("phone_overflow_px", {})[f.name] = over
            phone.screenshot(path=str(out / f"{f.stem}-phone.png"), full_page=True)
        b.close()
    (out / "summary.json").write_text(json.dumps(s, indent=2))


def rasterize(out: Path) -> None:
    if shutil.which("qlmanage"):  # macOS Quick Look draws the PowerPoint's first slide as PowerPoint would lay it out
        for f in sorted(out.glob("*.pptx")):
            subprocess.run(["qlmanage", "-t", "-s", "1400", "-o", str(out), str(f)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    if not shutil.which("pdftoppm"):
        print("pdftoppm is not installed: PDF pages not rendered to PNG.")
        return
    for f in sorted(out.glob("*.pdf")):
        subprocess.run(["pdftoppm", "-png", "-r", "70", str(f), str(out / f.stem)], check=False)


if __name__ == "__main__":
    main()
