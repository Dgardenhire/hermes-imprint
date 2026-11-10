import json, sys
from pathlib import Path
WT = Path.home() / "Desktop/LINCHPIN-Claude/hermes-imprint-wt-l2-deck8"
sys.path.insert(0, str(WT / "harness/bench"))
import bench as B
r = json.load(open(WT / "docs/runs/ai/loop2/r8e-result.json"))
api, CK = B.load_imprint(WT / ".l2-data/bench/r8e")
S = api.service
pr = S.proof(r["output_id"], r["kit"]["id"])
print("stamp:", pr["stamp"], "| blocked:", pr["blocked"], "| frames:", len(pr["slides"]))
words = {cid: c for cid, c in pr["claims"].items() if not any(ch.isdigit() for ch in str(c["value"]))}
print("word claims:", [(c["value"], c["status"], c["slides"], (c.get("line") or {}).get("match")) for c in words.values()])
hits = []
def walk(n):
    if isinstance(n, dict):
        if n.get("tr") in words: hits.append((n.get("x"), n["tr"]))
        for k in n.get("k") or []: walk(k)
walk(pr["tree"])
print("spans carrying a word claim:", hits)
