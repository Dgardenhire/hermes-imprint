"""Run the round-8 repair on the shipped sample deck (which has the filler slide) through claude -p."""
import asyncio, json, sys
from pathlib import Path
WT = Path.home() / "Desktop/LINCHPIN-Claude/hermes-imprint-wt-l2-deck8"
sys.path.insert(0, str(WT / "harness/bench"))
import bench as B
data = WT / ".l2-data/bench/r8d"; data.mkdir(parents=True, exist_ok=True)
api, CK = B.load_imprint(data)
S = api.service
from importlib import import_module
J = import_module("imprint_plugin_package.jobs")
K = import_module("imprint_plugin_package.content")
d = json.load(open(sys.argv[1]))
neu, pas = d["neutral"], d["passages"]
S.LLM = B.ClaudeCli(WT / "docs/runs/ai/loop2", "r8d")
S._passages_of = lambda oid: pas
J.step = lambda *a, **k: print("step:", a[1:])
corpus = "\n\n".join(f"[{r}] ({p.get('source_title','')}, {p.get('locator','')}) {p['text']}" for r, p in pas.items())
print("filler before:", CK.filler(neu, pas))
fixed = asyncio.run(S._repair("j", "o", neu, None, corpus, ""))
print("filler after:", CK.filler(fixed, pas))
for i, sl in enumerate(fixed["slides"]):
    print(i, sl["type"], sl.get("heading"), [(f.get("value"), f.get("label")) for f in sl.get("figures") or []] or [b.get("text") for b in sl.get("bullets") or []])
json.dump({"neutral": fixed, "passages": pas}, open(sys.argv[2], "w"))
