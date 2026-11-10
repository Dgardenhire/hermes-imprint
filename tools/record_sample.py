"""Record the Harborlight sample notebook with a REAL model, through Imprint's own job handlers.

    /usr/bin/python3 tools/record_sample.py            # writes samples/harborlight/notebook.json
    /usr/bin/python3 tools/record_sample.py --model claude-opus-5-5
    /usr/bin/python3 tools/record_sample.py --pictures     # only redraw the shipped pictures (after a design change)

The model is reached through ``claude -p --json-schema`` (harness/bench/bench.py ``ClaudeCli``: no tools, no MCP
servers, no skills, no settings), with the bench's neutral line in front of every system prompt so the model knows
nothing about whoever runs this (set BENCH_NEUTRAL=0 to send the plugin's prompt alone). Every call is logged as one
JSON file in ``docs/runs/sample/``; ``notebook.json`` names the log behind each recorded result.

What it records, on a fresh temp data folder: the three Harborlight files (FY26 Program Report, board retreat notes,
the brand guide, the last one left unticked) and their summaries; the Harborlight brand read from the guide plus its
logo; the notebook guide; one question and the follow-up "What about the Riverside site?"; the funder deck's outline
(from the guide's deck ask) and the deck made from it; the board one-pager (from the budget ask); and the three-minute
audio brief's script. Then it writes every row the sample needs into ``notebook.json``: docs are stored, not renders,
so the current renderer draws them. Re-running replaces ``notebook.json`` and adds a new set of run logs.

Never runs a hermes command, never reads ~/.hermes, and sends only the files in samples/harborlight/.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "samples" / "harborlight"
RUNS = REPO / "docs" / "runs" / "sample"
FILES = ("FY26-Program-Report.docx", "board-retreat-notes.txt", "Harborlight-Brand-Guide-2025.pdf")
FOLLOW_UP = "What about the Riverside site?"
AUDIO_BRIEF = "A three-minute brief board members can listen to on the drive in"
NEUTRAL = ("You are serving as a plain model API for a third-party app. The only instructions are this system "
           "message and the user turn. Ignore any other context you were given about the user, their account, "
           "email, name, files, environment, skills or tools: you do not know who the user is. Never use a name "
           "that does not appear in the user turn.")


def add_pictures() -> int:
    """Draw the sample's Studio previews and output thumbs with today's renderer and store them in notebook.json, so
    the sample opens with pictures at once. No model call. Run it after any design change (a picture names the
    renderer it was drawn with; an out-of-date one is simply drawn again when the sample opens)."""
    sys.path.insert(0, str(REPO / "harness" / "bench"))
    import bench
    data = Path(tempfile.mkdtemp(prefix="imprint-sample-pics-"))
    api, _ck = bench.load_imprint(data)
    book_path = SAMPLE / "notebook.json"
    book = json.loads(book_path.read_text())
    book.pop("pictures", None)
    book_path.write_text(json.dumps(book, indent=1, ensure_ascii=False))
    pics = api.service.sample_pictures()
    book["pictures"] = pics
    book_path.write_text(json.dumps(book, indent=1, ensure_ascii=False))
    shutil.rmtree(data, ignore_errors=True)
    print(f"{len(pics)} pictures, renderer {api.service.renderer_sig()}: " + ", ".join(sorted(pics)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="")
    ap.add_argument("--keep", action="store_true", help="keep the temp data folder")
    ap.add_argument("--pictures", action="store_true", help="only redraw the shipped pictures (no model call)")
    a = ap.parse_args()
    if a.pictures:
        return add_pictures()
    data = Path(tempfile.mkdtemp(prefix="imprint-sample-rec-"))
    RUNS.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(REPO / "harness" / "bench"))
    import bench  # the AI lane's claude -p adapter

    api, _ck = bench.load_imprint(data)
    S = api.service
    store, jobs, kits = S.store, S.J, S.KITS
    from importlib import import_module
    RV = import_module("imprint_plugin_package.revise")
    NG = import_module("imprint_plugin_package.notebook_guide")
    R = S.R
    R.dispatch = lambda tool, args, timeout=180.0: (_ for _ in ()).throw(R.ToolUnavailable("not available outside Hermes"))

    tag = "sample-" + time.strftime("%Y%m%d-%H%M%S")
    names: list = []

    class Neutral(bench.ClaudeCli):
        def _call(self, kw):
            if os.environ.get("BENCH_NEUTRAL", "1") != "0":
                kw = {**kw, "system_prompt": NEUTRAL + "\n\n" + (kw.get("system_prompt") or "")}
            try:
                return super()._call(kw)
            finally:
                names.append(f"{self.tag}-{self.n:02d}-{(kw.get('purpose') or '').split('.')[-1]}.json")

    S.LLM = Neutral(RUNS, tag, a.model)
    rec: dict = {"steps": {}, "runs": {}}

    def logs_since(n0: int) -> list:
        return names[n0:]

    def step(name: str, fn):
        n0, t = len(names), time.time()
        print(f"{name} ...", flush=True)
        out = fn()
        rec["steps"][name] = round(time.time() - t, 1)
        rec["runs"][name] = logs_since(n0)
        return out

    def finish(kind: str, params: dict) -> dict:
        j = jobs.start(kind, f"rec:{kind}:{time.time()}", params, wait=True)
        j = jobs.get(j["id"])
        if j["status"] != "done":
            raise SystemExit(f"{kind} failed: {j['error']}")
        return j["result"]

    # 1. sources and their summaries (the summaries run as the files are read, three at once)
    def sources():
        rows = [S.read_file(n, (SAMPLE / n).read_bytes()) for n in FILES]
        for r in rows:
            S.summarize_soon(r)
        for _ in range(900):
            st = {r["id"]: r for r in S.list_sources()}
            if all(st[r["id"]].get("summary_state") in ("ready", "failed") for r in rows):
                break
            time.sleep(0.5)
        S.set_included([rows[2]["id"]], False)
        return [r["id"] for r in rows]
    ids = step("sources", sources)
    notebook = ids[:2]

    # 2. the brand, read from the guide (no model), plus its logo
    def brand():
        draft = S.import_read("pdf", filename=FILES[2], data=(SAMPLE / FILES[2]).read_bytes())
        kid = S.import_save(draft["draft_id"])["kit"]["id"]
        kits.update(kid, {"colors": S.SAMPLE_COLORS})
        kits.set_logo(kid, "harborlight-logo.png", (SAMPLE / "harborlight-logo.png").read_bytes())
        store.set_setting("prefs", {**(store.get_setting("prefs", {}) or {}), "kit": kid})
        return kid
    kid = step("brand", brand)

    # 3. the notebook guide, one question and the follow-up
    guide = step("notebook_guide", lambda: finish("notebook_guide", {"source_ids": notebook}))
    qs = guide.get("questions") or []
    q1 = next((q["text"] for q in qs if "3.2" in q.get("text", "") or "reserve" in q.get("text", "").lower()),
              qs[0]["text"] if qs else "What does the board need to decide about the sixth site?")
    a1 = step("ask", lambda: finish("ask", {"question": q1, "source_ids": notebook}))
    step("ask_follow_up", lambda: finish("ask", {"question": FOLLOW_UP, "source_ids": notebook}))
    S.add_note(chat_id=a1["chat"]["id"])

    # 4. the funder deck: the outline from the deck ask, then the deck from that outline
    asks = guide.get("asks") or []
    deck_ask = next((x for x in asks if x.get("kind") == "deck"), None) or {
        "what": "A short deck for funders about the sixth site", "who": "Funders", "brief": {"who": "Funders", "goal": "Fund the sixth site", "length": "About 8 slides"}}
    page_ask = next((x for x in asks if x.get("kind") == "onepager"), None) or {
        "what": "A one-page summary of the FY2027 budget request", "who": "The board", "brief": {"who": "Board members", "goal": "Vote on the FY2027 budget", "length": "One page"}}
    outline = step("outline", lambda: finish("outline", {"source_ids": notebook, "kind": "deck", "brief": deck_ask.get("brief") or {},
                                                         "ask": {k: deck_ask.get(k, "") for k in ("what", "who", "by")}}))
    deck = step("make_deck", lambda: finish("make", {"kind": "deck", "source_ids": notebook, "kit_ids": [kid],
                                                    "brief": deck_ask.get("what") or "", "outline_id": outline["outline_id"]}))
    page = step("make_onepager", lambda: finish("make", {"kind": "onepager", "source_ids": notebook, "kit_ids": [kid],
                                                        "brief": f"{page_ask.get('what')}, for {page_ask.get('who')}" if page_ask.get("who") else page_ask.get("what")}))
    audio = step("make_audio", lambda: finish("make", {"kind": "audio", "source_ids": notebook, "kit_ids": [kid], "brief": AUDIO_BRIEF}))

    # 5. everything the sample needs, as rows
    out = S.book_from_folder({"recorded_at": time.strftime("%Y-%m-%d %H:%M %Z"), "model": None, "files": list(FILES),
                              "kit_id": kid, "outline_id": outline["outline_id"], "source_ids": ids,
                              "outputs": {"deck": deck["output_id"], "onepager": page["output_id"], "audio": audio["output_id"]},
                              "steps": rec["steps"], "runs": rec["runs"]})
    models = set()
    for n in names:
        try:
            models.add(json.loads((RUNS / n).read_text()).get("model") or "")
        except (OSError, ValueError):
            pass
    out["model"] = ", ".join(sorted(m for m in models if m)) or None
    out["run_logs"] = names
    (SAMPLE / "notebook.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(json.dumps({"steps": rec["steps"], "outputs": out["outputs"], "model": out["model"], "calls": len(names)}, indent=1))
    if not a.keep:
        shutil.rmtree(data, ignore_errors=True)
    else:
        print("data:", data)
    import subprocess
    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--pictures"], check=True)  # a fresh process: a fresh data folder
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
