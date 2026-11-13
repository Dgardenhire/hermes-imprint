"""P6, the plain side: the prompt a capable person would type into Hermes with code execution, through a real model.

    /usr/bin/python3 harness/bench/p6_plain.py harborlight|salvia|warming OUT_DIR

One ``claude -p`` call (no tools, the bench lib's neutral line on, the same default model as Letterpress's side) gets
the sources as plain text and one request: "Make a 7 to 9 slide funder deck as a .pptx using python-pptx. Use our
brand colors ...". The system prompt describes the code tool a Hermes chat has: the reply's Python block is run in
a working folder with python-pptx installed. The harness saves the reply and the script, runs the script in
OUT_DIR/<set>/, and when it fails gives the model one retry with the error, as a person would. Every call keeps a
run log (``run-NN.json``) with the model name and seconds. Nothing here handicaps the plain side: it gets the same
sources, the same brand colors Letterpress uses, and as many output tokens as it wants.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
from childenv import child_env  # noqa: E402  the model-written script gets only the allowlisted names
import bench as B  # noqa: E402

BRANDS = {
    # Harborlight: as its brand guide PDF names them (Letterpress's import read the same five).
    "harborlight": "Harbor Teal #0E5E6F, Sunrise Gold #F2A900, Lighthouse Red #C0392B, background #FAF7F2, text #2B2B2B",
    # Salvia Kitchen and the warming center get the studio system Letterpress used for them, so both sides share a palette.
    "salvia": "Ultramarine #1F44C7, Poster Black #111111, Stock gray #F1F1EF, background #FFFFFF, text #111111",
    "warming": "Tab Red #C2362B, Press Black #1A1A1A, Data Blue #2B5D8A, Panel #EBE6DD, Gridline #D9D4CC, background #FBFAF7, text #1A1A1A",
    # The held-out set's own brand.txt, as written; Letterpress imports the same file as pasted colors.
    "heldout": "Pine Green #2F5D3A, Brass #C8902E, Charcoal #262624, background #FAF8F3, font Work Sans",
    "heldout2": "Deep Plum #4A2545, Copper #B5663A, Slate #2F3640, background #F4F5F7, font Source Sans 3",
    "heldout3": "Heather #5B3A6E, Marigold #D9962B, Charcoal #2B2B2B, background #FAF7F2, font Source Sans 3",
}
SYSTEM = ("You are a helpful assistant in a desktop chat app with a Python code tool. When you write a Python script "
          "in one ```python block, the app runs it in the person's working folder (Python 3.9, python-pptx 1.0 "
          "installed, no network) and gives the person any files it saves.")
REQUEST = "Make a 7 to 9 slide funder deck as a .pptx using python-pptx. Use our brand colors: {brand}."


def text_of(f: Path) -> str:
    if f.suffix.lower() == ".docx":
        xml = zipfile.ZipFile(f).read("word/document.xml").decode("utf-8")
        paras = []
        for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
            t = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p))
            if t.strip():
                paras.append(t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'"))
        return "\n\n".join(paras)
    return f.read_text(encoding="utf-8")


def claude(prompt: str, out: Path, n: int) -> dict:
    scratch = Path(tempfile.mkdtemp(prefix="p6-plain-cli-"))
    (scratch / "mcp.json").write_text('{"mcpServers":{}}')
    cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--mcp-config", str(scratch / "mcp.json"), "--disable-slash-commands",
           "--setting-sources", "", "--output-format", "json", "--no-session-persistence", "--system-prompt", B.neutral(SYSTEM)]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY")}
    t = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=scratch, env=env, timeout=900)
    secs = round(time.time() - t, 1)
    d = json.loads(p.stdout)
    log = {"side": "plain", "seconds": secs, "model": ", ".join((d.get("modelUsage") or {}).keys()), "neutral": os.environ.get("BENCH_NEUTRAL", "1") != "0",
           "system": SYSTEM, "prompt": prompt, "reply": d.get("result"), "usage": d.get("usage"), "is_error": d.get("is_error")}
    (out / f"run-{n:02d}.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(f"  run-{n:02d}: {secs}s ({log['model']})", flush=True)
    return log


def script_of(reply: str) -> str:
    blocks = re.findall(r"```python\s*\n(.*?)```", reply or "", re.S)
    return max(blocks, key=len) if blocks else ""


def execute(script: str, out: Path, n: int) -> dict:
    (out / f"make_deck-{n:02d}.py").write_text(script)
    before = {p.name for p in out.glob("*.pptx")}
    t = time.time()
    p = subprocess.run(["/usr/bin/python3", f"make_deck-{n:02d}.py"], cwd=out, capture_output=True, text=True, timeout=300, env=child_env())
    made = sorted({p.name for p in out.glob("*.pptx")} - before)
    return {"returncode": p.returncode, "seconds": round(time.time() - t, 1), "stdout": p.stdout[-3000:], "stderr": p.stderr[-3000:], "pptx": made}


def main():
    name, root = sys.argv[1], Path(sys.argv[2])
    out = root / name
    out.mkdir(parents=True, exist_ok=True)
    files = B.SETS[name]
    src = "\n\n".join(f"=== {f.name} ===\n{text_of(f)}" for f in files)
    if name not in BRANDS:  # round 13: a later held-out set's own brand.txt, as written, on one line
        BRANDS[name] = ", ".join(l.strip() for l in (B.REPO / f"harness/bench/sets/{name}/brand.txt").read_text().splitlines() if l.strip())
    prompt = f"Here are our documents.\n\n{src}\n\n{REQUEST.format(brand=BRANDS[name])}"
    t0 = time.time()
    first = claude(prompt, out, 1)
    script = script_of(first["reply"])
    ran = execute(script, out, 1) if script else {"returncode": None, "stderr": "no python block in the reply", "pptx": []}
    tries = [ran]
    if ran["returncode"] != 0 or not ran["pptx"]:
        retry = (f"{prompt}\n\nYou wrote:\n```python\n{script}\n```\n\nIt failed with:\n```\n{(ran.get('stderr') or ran.get('stdout') or '')[-2500:]}\n```\n"
                 "Please fix it.")
        second = claude(retry, out, 2)
        script = script_of(second["reply"])
        ran = execute(script, out, 2) if script else {"returncode": None, "stderr": "no python block in the reply", "pptx": []}
        tries.append(ran)
    summary = {"set": name, "seconds_total": round(time.time() - t0, 1), "tries": tries, "brand": BRANDS[name], "request": REQUEST.format(brand=BRANDS[name])}
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("set", "seconds_total")} | {"tries": [{k: t.get(k) for k in ("returncode", "pptx")} for t in tries]}), flush=True)


if __name__ == "__main__":
    main()
