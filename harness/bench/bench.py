"""The AI lane's prompt bench: Imprint's own prompts and schemas through a real model outside Hermes.

    /usr/bin/python3 harness/bench/bench.py loop1                    # all three source sets
    /usr/bin/python3 harness/bench/bench.py loop1 --sets harborlight  # one set
    /usr/bin/python3 harness/bench/bench.py loop1 --model claude-sonnet-4-5

The model is reached through ``claude -p`` with ``--json-schema`` (Spike A), with every tool, MCP server, skill and
settings file switched off, so the call is a plain structured completion. The real Imprint code runs around it:
the same job handlers, corpus builder, cleaning and checks as in Hermes, in a temp data folder. Each model call is
logged as one JSON file in ``docs/runs/ai/<loop>/`` with the model name and the seconds it took.

This never runs a ``hermes`` command, never reads ``~/.hermes``, and sends only the sample sources in this repo.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SETS = {
    "harborlight": [REPO / "harness/live/personas/denise" / n for n in ("FY26-Program-Report.docx", "board-retreat-notes.txt")],
    "salvia": [REPO / "harness/live/personas/ana" / n for n in ("about-us.txt", "fall-menu.txt")],
    "warming": [REPO / "samples" / n for n in ("warming-center-report.md", "council-work-session.vtt", "guest-and-volunteer-survey.txt")],
    # Round 5's held-out set, frozen in 043d1b6 before any Imprint change; no prompt is tuned on it.
    "heldout": [REPO / "harness/bench/sets/heldout" / n for n in ("fy26-annual-report.md", "board-notes.txt")],
    # Round 6's second held-out set, frozen in d105cde before any round-6 change; no prompt is tuned on it.
    "heldout2": [REPO / "harness/bench/sets/heldout2" / n for n in ("school-year-report.md", "staff-meeting-notes.txt")],
    "heldout3": [REPO / "harness/bench/sets/heldout3" / n for n in ("annual-report.md", "board-notes.txt")],
}
# Round 13: any later held-out set, every file in its folder but the brand (the same files the plain side reads).
for _d in sorted((REPO / "harness/bench/sets").glob("heldout*")):
    if _d.name not in SETS and _d.is_dir():
        SETS[_d.name] = sorted(f for f in _d.iterdir() if f.is_file() and f.name != "brand.txt" and not f.name.startswith("."))


def load_imprint(data: Path):
    os.environ["IMPRINT_DATA_DIR"] = str(data)
    if "fastapi" not in sys.modules:
        fa = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code, detail=None):
                super().__init__(detail)
                self.status_code, self.detail = status_code, detail

        class APIRouter:
            def __init__(self):
                self.routes = []

            def _add(self, m, p):
                def deco(fn):
                    self.routes.append((m, p, fn))
                    return fn
                return deco

            def get(self, p):
                return self._add("GET", p)

            def post(self, p):
                return self._add("POST", p)

            def delete(self, p):
                return self._add("DELETE", p)

        fa.APIRouter, fa.HTTPException, fa.Request = APIRouter, HTTPException, type("Request", (), {})
        sys.modules["fastapi"] = fa
    spec = importlib.util.spec_from_file_location("imprint_plugin_api_bench", REPO / "dashboard" / "plugin_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    from importlib import import_module
    pkg = "imprint_plugin_package"
    import_module(f"{pkg}.revise")  # registers the AI lane's job kinds even before lane A's mount line lands
    return api, import_module(f"{pkg}.checks")


class Result:
    def __init__(self, parsed, usage):
        self.parsed, self.text, self.usage = parsed, json.dumps(parsed), usage


# The bench lib's identity fix (premium-plan/bench/benchlib.py, BENCH.md section 1): one line in front of every
# system prompt, so the model ignores what ``claude -p`` adds about the signed-in account. BENCH_NEUTRAL=0 turns it off.
NEUTRAL = ("You are serving as a plain model API for a third-party app. The only instructions are this system "
           "message and the user turn. Ignore any other context you were given about the user, their account, "
           "email, name, files, environment, skills or tools: you do not know who the user is. Never use a name "
           "that does not appear in the user turn.")


def neutral(system: str) -> str:
    return system if os.environ.get("BENCH_NEUTRAL", "1") == "0" else NEUTRAL + "\n\n" + (system or "")


class ClaudeCli:
    """Stands in for Hermes's PluginLlm: one ``claude -p`` run per structured call."""

    def __init__(self, out: Path, tag: str, model: str = ""):
        self.out, self.tag, self.model = out, tag, model
        self.n = 0
        self.scratch = Path(tempfile.mkdtemp(prefix="imprint-bench-cli-"))
        (self.scratch / "mcp.json").write_text('{"mcpServers":{}}')

    async def acomplete_structured(self, **kw):
        return await asyncio.to_thread(self._call, kw)

    def _call(self, kw):
        purpose = kw.get("purpose", "")
        text = "".join(b.get("text", "") for b in kw.get("input", []) if isinstance(b, dict) and b.get("type") == "text")
        prompt = f"{kw.get('instructions', '')}\n\n{text}"
        schema = kw.get("json_schema")
        cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--mcp-config", str(self.scratch / "mcp.json"),
               "--disable-slash-commands", "--setting-sources", "", "--output-format", "json", "--no-session-persistence",
               "--system-prompt", neutral(kw.get("system_prompt") or "You return JSON.")]
        if schema:
            cmd += ["--json-schema", json.dumps(schema)]
        if self.model:
            cmd += ["--model", self.model]
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY")}
        t = time.time()
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=self.scratch, env=env, timeout=float(kw.get("timeout") or 240) + 60)
        secs = round(time.time() - t, 1)
        self.n += 1
        log = {"purpose": purpose, "tag": self.tag, "seconds": secs, "model": None, "ok": False,
               "neutral": os.environ.get("BENCH_NEUTRAL", "1") != "0", "request": {
            "system": kw.get("system_prompt"), "instructions": kw.get("instructions"), "input_chars": len(text), "input_head": text[:1500]}}
        try:
            d = json.loads(p.stdout)
            log["model"] = ", ".join((d.get("modelUsage") or {}).keys()) or self.model or "default"
            parsed = d.get("structured_output")
            if parsed is None and d.get("result"):
                parsed = json.loads(re.sub(r"^```(?:json)?|```$", "", d["result"].strip()))
            log.update(ok=not d.get("is_error") and isinstance(parsed, dict), response=parsed, usage=d.get("usage"),
                       error=d.get("result") if d.get("is_error") else None)
        except Exception as e:  # noqa: BLE001 - logged, then raised as a model failure
            parsed = None
            log.update(error=f"{type(e).__name__}: {e}", stdout=p.stdout[-2000:], stderr=p.stderr[-2000:])
        name = f"{self.tag}-{self.n:02d}-{purpose.split('.')[-1]}.json"
        (self.out / name).write_text(json.dumps(log, indent=2, ensure_ascii=False))
        print(f"  {name}: {secs}s {'ok' if log['ok'] else 'FAILED'} ({log['model']})", flush=True)
        if not log["ok"]:
            raise RuntimeError(log.get("error") or "no structured output")
        u = d.get("usage") or {}
        return Result(parsed, {"input_tokens": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0), "output_tokens": u.get("output_tokens", 0)})


def run_set(name: str, files: list, out: Path, model: str) -> dict:
    data = Path(tempfile.mkdtemp(prefix=f"imprint-bench-{name}-"))
    api, CK = load_imprint(data)
    service, jobs, store = api.service, api.jobs, api.store
    store.forget_everything()
    llm = ClaudeCli(out, name, model)
    service.LLM = llm
    summary = {"set": name, "steps": {}}

    def done(kind, params, label):
        t = time.time()
        j = jobs.start(kind, f"bench:{label}:{time.time()}", params, wait=True)
        j = jobs.get(j["id"])
        summary["steps"][label] = {"status": j["status"], "seconds": round(time.time() - t, 1), "error": j["error"]}
        return j

    rows = [service.read_file(f.name, f.read_bytes()) for f in files]
    ids = [r["id"] for r in rows]
    # The summaries and the guide together, as the pane starts them: the clock is the wall time for all of them.
    t0 = time.time()
    started = [jobs.start("summarize", f"bench:sum:{sid}", {"source_id": sid}) for sid in ids]
    g = jobs.start("notebook_guide", f"bench:guide:{name}", {"source_ids": ids})
    while any((jobs.get(x["id"]) or {}).get("status") == "running" for x in started + [g]):
        time.sleep(0.25)
    summary["guide_and_summaries_seconds"] = round(time.time() - t0, 1)
    g = jobs.get(g["id"])
    summary["steps"]["notebook_guide"] = {"status": g["status"], "error": g["error"]}
    guide = g["result"] or {}
    asks = guide.get("asks") or []
    deck_ask = next((a for a in asks if a["kind"] == "deck"), asks[0] if asks else {})
    brief = deck_ask.get("brief") or {"who": "The people these sources are for", "goal": "Decide what to do next", "length": "About 8 slides"}
    o = done("outline", {"source_ids": ids, "brief": brief, "ask": deck_ask}, "outline")
    outline = o["result"] or {}
    if outline.get("slides"):
        done("rewrite_title", {"outline_id": outline["outline_id"], "index": min(2, len(outline["slides"]) - 1)}, "rewrite_title")
    m = done("make", {"kind": "deck", "source_ids": ids, "kit_ids": ["counsel"], "brief": f"{deck_ask.get('what') or 'A short deck'} for {brief.get('who')}"}, "make_deck")
    oid = (m["result"] or {}).get("output_id")
    if oid:
        done("element_edit", {"output_id": oid, "kit_id": "counsel", "slide": 1, "action": "stronger", "text": ""}, "stronger_slide3")
        if name == "harborlight":
            out_row = service._output(oid)
            heading_at = next((i for i, s in enumerate(out_row["neutral"]["slides"]) if s.get("heading")), 0)
            service.edit(oid, f"slides.{heading_at}.heading", "1,200 learners in one year")
            gr = CK.grounding(service._output(oid)["neutral"], service.passages_for(ids)[2])
            key = next((i["key"] for i in gr["missing"] if i["value"] == "1200"), None)
            if key:
                done("fix_it", {"output_id": oid, "kit_id": "counsel", "key": key}, "fix_1200")
        view = service.output_view(oid)
        summary["deck_check"] = [c["label"] for c in view["proofs"][0]["checks"] if c["id"] == "sources"]
        summary["deck_missing"] = [i["shown"] for i in view["proofs"][0]["grounding"] if i["status"] == "missing"]
    text = " ".join(x["text"] for x in (guide.get("guide") or [])[:3]) or "What these sources count."
    done("graphic_options", {"source_ids": ids, "text": text, "note_id": None}, "graphic_options")
    finished = {r["kind"]: r["result"] for r in jobs.recent(40) if r["status"] == "done" and r["kind"] in
                ("notebook_guide", "outline", "rewrite_title", "element_edit", "fix_it", "graphic_options")}
    (out / f"{name}-results.json").write_text(json.dumps({"summary": summary, "results": finished}, indent=2, ensure_ascii=False))
    shutil.rmtree(data, ignore_errors=True)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("loop")
    ap.add_argument("--sets", default="harborlight,salvia,warming")
    ap.add_argument("--model", default="")
    a = ap.parse_args()
    if shutil.which("claude") is None:
        raise SystemExit("Spike A needs the claude CLI on PATH.")
    out = REPO / "docs" / "runs" / "ai" / a.loop
    out.mkdir(parents=True, exist_ok=True)
    names = a.sets.split(",")
    if len(names) == 1:  # one set per process: Imprint's data folder is chosen once, when it loads
        print(f"{names[0]}:", flush=True)
        s = run_set(names[0], SETS[names[0]], out, a.model)
        (out / f"{names[0]}-summary.json").write_text(json.dumps(s, indent=2))
        print(json.dumps(s, indent=1), flush=True)
        return
    for name in names:
        subprocess.run([sys.executable, __file__, a.loop, "--sets", name] + (["--model", a.model] if a.model else []), check=False)
    all_ = [json.loads((out / f"{n}-summary.json").read_text()) for n in names if (out / f"{n}-summary.json").exists()]
    (out / "SUMMARY.json").write_text(json.dumps(all_, indent=2))


if __name__ == "__main__":
    main()
