"""Render the demo brief in every starter kit (PDF, proof PDF, HTML) and write the pane fixtures.

    /usr/bin/python3 harness/render_samples.py <out-dir>

Runs outside Hermes with a scripted stand-in model that returns harness/demo_content.py, so the pages
are realistic and repeatable. Writes nothing outside <out-dir> and a temporary data folder."""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="letterpress-render-"))
OUT.mkdir(parents=True, exist_ok=True)
os.environ["LETTERPRESS_DATA_DIR"] = tempfile.mkdtemp(prefix="letterpress-render-data-")
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "harness"))
from _load import service, jobs, kits, store, Result  # noqa: E402
import demo_content  # noqa: E402

VOICES = {
    "plain-notice": {"title": "The warming center kept 412 people out of the cold"},
    "docket": {"title": "Warming center season results and two decisions for April 8"},
    "night-desk": {"title": "412 people. 87 nights. No one turned away"},
    "studio-italic": {"title": "Every cold night, a warm room"},
    "almanac": {"title": "A winter of warm nights on Maple Street"},
    "open-letter": {"title": "What 87 cold nights taught us"},
}


class Scripted:
    def __init__(self, doc):
        self.doc = doc

    async def acomplete_structured(self, **kw):
        if kw.get("purpose", "").endswith("write"):
            return Result(parsed=self.doc)
        d = json.loads(kw["input"][0]["text"])
        return Result(parsed=d)


def main(kit_ids=None):
    srcs = []
    for name in ("warming-center-report.md", "council-work-session.vtt", "guest-and-volunteer-survey.txt"):
        srcs.append(service.read_file(name, (ROOT / "samples" / name).read_bytes()))
    ids = [s["id"] for s in srcs]
    _s, _b, by_ref = service.passages_for(ids)
    doc = demo_content.grounded(by_ref)
    service.LLM = Scripted(doc)
    kit_ids = kit_ids or [k["id"] for k in kits.STARTERS]
    made = {}
    for i in range(0, len(kit_ids), 2):
        pair = kit_ids[i:i + 2]
        j = jobs.start("make", f"r:{pair}", {"kind": "onepager", "source_ids": ids, "kit_ids": pair, "brief": "A one-page brief"}, wait=True)
        j = jobs.get(j["id"])
        if j["status"] != "done":
            print("FAILED", pair, j["error"])
            continue
        oid = j["result"]["output_id"]
        for k in pair:
            made[k] = oid
            if k in VOICES:
                service.edit(oid, "title", VOICES[k]["title"])
    for k, oid in made.items():
        for fmt in ("pdf", "html"):
            e = service.export(oid, k, fmt)
            dst = OUT / f"{k}.{ 'pdf' if fmt == 'pdf' else 'html'}"
            dst.write_bytes(Path(e["path"]).read_bytes())
    print(OUT)
    return made, ids


if __name__ == "__main__":
    main(sys.argv[2:] or None)
