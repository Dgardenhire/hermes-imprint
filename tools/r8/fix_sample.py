"""S16 through claude -p: '1,200 learners in one year' planted on the waitlist slide; the fix must fit its points."""
import asyncio, json, sys
from pathlib import Path
WT = Path.home() / "Desktop/LINCHPIN-Claude/hermes-imprint-wt-l2-deck8"
sys.path.insert(0, str(WT / "harness/bench"))
import bench as B
data = WT / ".l2-data/bench/r8f"; data.mkdir(parents=True, exist_ok=True)
api, CK = B.load_imprint(data)
S = api.service
from importlib import import_module
K = import_module("imprint_plugin_package.content"); RV = import_module("imprint_plugin_package.revise")
R = import_module("imprint_plugin_package.runtime") if False else None
d = json.load(open(sys.argv[1])); pas = d["passages"]
doc = json.loads(json.dumps(d["neutral"]))
doc["slides"][1]["heading"] = "1,200 learners in one year"
S.LLM = B.ClaudeCli(WT / "docs/runs/ai/loop2", "r8f")
path = "slides.1.heading"
text = doc["slides"][1]["heading"]
rest = RV._slide_rest(doc, path)
old = (CK.closest(text, pas, list(pas)) or {}).get("ref")
ref = (CK.closest(text + " " + " ".join(rest), pas, list(pas)) or {}).get("ref") or old
p = pas[ref]
body = f"THE SENTENCE\n{text}\n\nTHE WRONG PART\n1,200\n\nTHE CLOSEST PASSAGE\n[{ref}] ({p['locator']}) {p['text']}"
body += "\n\nTHE REST OF THE SLIDE\n" + "\n".join(f"- {t}" for t in rest[:8])
print("passage by sentence alone:", old, "| with the slide:", ref)
raw = asyncio.run(S.model().structured(system=K.SYSTEM, instructions=RV.FIX_RULES, body=body, schema=RV.FIX_SCHEMA,
                                       purpose="fix_it", max_tokens=300, timeout=60))
after = K.strip_period(raw.get("text", ""))
print("before:", text); print("rest:", rest); print("after:", after)
print("check:", CK.check_line(after, [ref], pas, all_ids=[ref]))
