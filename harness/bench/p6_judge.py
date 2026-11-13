"""P6 blind judging: three fresh critics per source set, each shown only two unlabeled contact sheets and the sources.

    /usr/bin/python3 harness/bench/p6_judge.py ROUND_DIR --letterpress SET=DIR ... --plain SET=DIR ... [--critics 3]

For each set: a contact sheet of each deck (``sheet.py``, no names), saved as A.png and B.png with the side
shuffled per set; the key goes to ROUND_DIR/KEY.json. The critic sees copies in a fresh temp folder outside the
repo and the bench folder (so a file name or a nearby folder can't tell it which is which), runs as
``claude -p --tools Read --allowedTools Read`` with the bench lib's neutral line, no MCP, no settings, no session,
and is given only the two image paths and the source text. Every answer is saved raw (ROUND_DIR/<set>/critic-N.json)
with its seconds and model.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench as B  # noqa: E402
import p6_plain as PP  # noqa: E402
import sheet as SH  # noqa: E402

ASK = """You are judging two slide decks made for the same request: "{request}" They were made from the source
documents below. Each deck is shown as one contact sheet image with every slide in order:

Deck A: {a}
Deck B: {b}

Open both images with the Read tool and look at every slide closely. Then answer:
1. Which deck would you send to the funder, A or B? Why, in two or three sentences?
2. Score each deck from 1 to 10 on: accuracy against the sources, clarity of the argument, and design.
3. Name every number in either deck that is not in the sources and cannot be worked out from them. Say which deck.

End your reply with one JSON object on its own line, exactly this shape:
{{"send": "A" or "B", "A": {{"accuracy": n, "clarity": n, "design": n}}, "B": {{"accuracy": n, "clarity": n, "design": n}}, "invented": [{{"deck": "A" or "B", "number": "...", "why": "..."}}]}}

THE SOURCES
{sources}"""


def critic(prompt: str, cwd: Path, out: Path) -> dict:
    (cwd / "mcp.json").write_text('{"mcpServers":{}}')
    cmd = ["claude", "-p", "--tools", "Read", "--allowedTools", "Read", "--strict-mcp-config", "--mcp-config", str(cwd / "mcp.json"),
           "--disable-slash-commands", "--setting-sources", "", "--output-format", "json", "--no-session-persistence",
           "--system-prompt", B.neutral("You are a careful reviewer of funder decks. You judge only what you see in the two images and the sources given.")]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY")}
    t = time.time()
    p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=cwd, env=env, timeout=900)
    secs = round(time.time() - t, 1)
    try:
        d = json.loads(p.stdout)
    except ValueError:
        d = {"result": p.stdout[-3000:], "is_error": True, "stderr": p.stderr[-2000:]}
    text = d.get("result") or ""
    parsed = None
    for m in reversed(list(re.finditer(r"\{.*\}", text))):
        try:
            parsed = json.loads(m.group(0))
            break
        except ValueError:
            continue
    if parsed is None:
        tail = text[text.rfind('{"send"'):] if '{"send"' in text else ""
        try:
            parsed = json.loads(tail) if tail else None
        except ValueError:
            parsed = None
    log = {"seconds": secs, "model": ", ".join((d.get("modelUsage") or {}).keys()), "num_turns": d.get("num_turns"),
           "is_error": d.get("is_error"), "reply": text, "parsed": parsed, "prompt_head": prompt[:900]}
    out.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    return log


def main():
    a = sys.argv[1:]
    root = Path(a[0])
    n_critics = int(a[a.index("--critics") + 1]) if "--critics" in a else 3
    pl = {}
    if "--plain" in a:
        i = a.index("--plain") + 1
        while i < len(a) and not a[i].startswith("--"):
            k, v = a[i].split("=", 1)
            pl[k] = v
            i += 1
    imp = {}
    i = a.index("--letterpress") + 1
    while i < len(a) and not a[i].startswith("--"):
        k, v = a[i].split("=", 1)
        imp[k] = v
        i += 1
    root.mkdir(parents=True, exist_ok=True)
    key_path = root / "KEY.json"
    key = json.loads(key_path.read_text()) if key_path.exists() else {}
    rng = random.SystemRandom()
    jobs = []
    for name in imp:
        d = root / name
        d.mkdir(parents=True, exist_ok=True)
        if name not in key:
            key[name] = {"A": rng.choice(["letterpress", "plain"])}
            key[name]["B"] = "plain" if key[name]["A"] == "letterpress" else "letterpress"
        side_dir = {"letterpress": Path(imp[name]), "plain": Path(pl[name])}
        for letter in ("A", "B"):
            SH.sheet(side_dir[key[name][letter]], d / f"{letter}.png", cols=3, width=640)
        src = "\n\n".join(f"=== {f.name} ===\n{PP.text_of(f)}" for f in B.SETS[name])
        for c in range(1, n_critics + 1):
            tmp = Path(tempfile.mkdtemp(prefix="deck-review-"))
            shutil.copy(d / "A.png", tmp / "A.png")
            shutil.copy(d / "B.png", tmp / "B.png")
            prompt = ASK.format(request="Make a 7 to 9 slide funder deck", a=tmp / "A.png", b=tmp / "B.png", sources=src)
            jobs.append((name, c, prompt, tmp, d / f"critic-{c}.json"))
    key_path.write_text(json.dumps(key, indent=2))
    with ThreadPoolExecutor(max_workers=9) as ex:
        logs = list(ex.map(lambda j: (j[0], j[1], critic(j[2], j[3], j[4])), jobs))
    for name, c, log in logs:
        p = log["parsed"] or {}
        print(name, c, log["seconds"], "send:", p.get("send"), "A:", p.get("A"), "B:", p.get("B"), flush=True)


if __name__ == "__main__":
    main()
