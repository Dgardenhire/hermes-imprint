"""P6 judging by a different model family (round 11): GPT through ``codex exec -i A.png -i B.png``, not Claude.

    /usr/bin/python3 harness/bench/p6_judge_codex.py ROUND_DIR --sets heldout,heldout2 [--runs 3]

ROUND_DIR holds ``letterpress-a/<set>/{A,B}.png`` and ``letterpress-b/<set>/{A,B}.png`` (the same contact sheets the Claude
critics saw, made by ``p6_judge.py``). Each run judges both orders, so position cancels. The question and the scoring
are ``p6_judge.ASK`` word for word, except that the two decks are named as the first and second attached image
instead of file paths. Each judge runs in a fresh temp folder outside the repo (read-only sandbox, ephemeral session,
no user config beyond auth), sees only the two images and the source text, and its raw reply is saved to
``ROUND_DIR/codex/<order>/<set>/run-N.json`` with its seconds.
"""

from __future__ import annotations

import json
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
import p6_judge as PJ  # noqa: E402
import p6_plain as PP  # noqa: E402

SYSTEM = "You are a careful reviewer of funder decks. You judge only what you see in the two images and the sources given. Do not run any commands."


def judge(prompt: str, a: Path, b: Path, out: Path) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="deck-review-"))
    shutil.copy(a, tmp / "A.png")
    shutil.copy(b, tmp / "B.png")
    last = tmp / "last.txt"
    cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "-C", str(tmp),
           "-i", str(tmp / "A.png"), "-i", str(tmp / "B.png"), "-o", str(last), "-"]
    t = time.time()
    p = subprocess.run(cmd, input=SYSTEM + "\n\n" + prompt, capture_output=True, text=True, cwd=tmp, timeout=900)
    secs = round(time.time() - t, 1)
    text = last.read_text() if last.exists() else ""
    parsed = None
    for m in reversed(list(re.finditer(r"\{.*\}", text))):
        try:
            parsed = json.loads(m.group(0))
            break
        except ValueError:
            continue
    model = ""
    m = re.search(r"^model:\s*(\S+)", p.stderr or "", re.M) or re.search(r"model:\s*(\S+)", p.stdout or "")
    if m:
        model = m.group(1)
    log = {"seconds": secs, "model": model, "returncode": p.returncode, "reply": text, "parsed": parsed,
           "stderr_tail": (p.stderr or "")[-1500:], "prompt_head": prompt[:900]}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, indent=2, ensure_ascii=False))
    return log


def main():
    a = sys.argv[1:]
    root = Path(a[0])
    sets = a[a.index("--sets") + 1].split(",") if "--sets" in a else ["heldout", "heldout2"]
    runs = int(a[a.index("--runs") + 1]) if "--runs" in a else 3
    jobs = []
    for name in sets:
        src = "\n\n".join(f"=== {f.name} ===\n{PP.text_of(f)}" for f in B.SETS[name])
        prompt = PJ.ASK.format(request="Make a 7 to 9 slide funder deck", a="the first attached image",
                               b="the second attached image", sources=src)
        prompt = prompt.replace("Open both images with the Read tool and look", "Look")
        for order in ("letterpress-a", "letterpress-b"):
            d = root / order / name
            for r in range(1, runs + 1):
                jobs.append((order, name, r, prompt, d / "A.png", d / "B.png", root / "codex" / order / name / f"run-{r}.json"))
    with ThreadPoolExecutor(max_workers=6) as ex:
        logs = list(ex.map(lambda j: (j[0], j[1], j[2], judge(j[3], j[4], j[5], j[6])), jobs))
    for order, name, r, log in logs:
        p = log["parsed"] or {}
        print(order, name, r, log["seconds"], log["model"], "send:", p.get("send"), "A:", p.get("A"), "B:", p.get("B"), flush=True)


if __name__ == "__main__":
    main()
