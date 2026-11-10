"""Loop 2 AI lane bench: the hero exhibit through a real model, and Imprint's side of the P6 prompt bench.

    /usr/bin/python3 harness/bench/loop2.py build harborlight --tag hero1 [--question "..."]
    /usr/bin/python3 harness/bench/loop2.py build salvia --tag p6-salvia --kit stage
    /usr/bin/python3 harness/bench/loop2.py render OUT_DIR RESULT.json [RESULT.json ...]

``build`` runs the real Imprint code, one source set per process, in a data folder under ``.l2-data/bench/`` (never
``~/.hermes``), with every model call through ``claude -p`` (``bench.ClaudeCli``, the bench lib's neutral line on).
Steps: the sources and their summaries, the notebook guide, the brand (Harborlight: imported from its brand guide
PDF plus logo, no model; other sets: a studio kit), the outline from the guide's deck ask (or the P6 brief), the
deck built from that outline, and, when ``--question`` is given, one chat answer. Every call leaves a run log in
``docs/runs/ai/loop2/``; the result JSON beside them holds the docs (neutral and in the brand), the outline, the
guide, the answer and the checks, so ``render`` can redraw the deck later from the same docs.

Make from an outline is the backend lane's route (contract D). Until it lands, this harness gives the write call
the outline the way the route will: ``content.instructions_for(kind, brief, outline)`` and ``content.apply_outline``
on the write result only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench as B  # noqa: E402

REPO = B.REPO
RUNS = REPO / "docs" / "runs" / "ai" / "loop2"
DATA = REPO / ".l2-data" / "bench"
DENISE = REPO / "harness/live/personas/denise"
P6_BRIEF = {"who": "Funders", "goal": "Decide to fund this work", "length": "7 to 9 slides"}
SPEC = True  # loop 4: with --plain, the model designs each slide as a spec (spec.py); --nospec keeps the shaped draft
PLAIN = False  # round 13: --plain makes the deck from the plain one-pass draft (service._make_plain), no outline step
ONEPASS = False  # round 6: --onepass makes the deck with no outline step, as the product's default make does
ROUTE = True  # build the deck through the real outline_id route (round 2); False reproduces round 1's harness glue


def build(set_name: str, tag: str, kit_id: str, question: str, p6: bool) -> dict:
    data = DATA / tag
    data.mkdir(parents=True, exist_ok=True)
    api, CK = B.load_imprint(data)
    service, jobs, store = api.service, api.jobs, api.store
    from importlib import import_module
    K = import_module("imprint_plugin_package.content")
    RV = import_module("imprint_plugin_package.revise")
    kits = import_module("imprint_plugin_package.kits")
    store.forget_everything()
    RUNS.mkdir(parents=True, exist_ok=True)
    llm = B.ClaudeCli(RUNS, tag)
    state = {"outline": None}
    orig_call = llm._call

    def call(kw):  # the write call gets the approved outline, as POST /outputs {outline_id} will give it
        if state["outline"] and kw.get("purpose", "").endswith("write"):
            kw = {**kw, "instructions": K.instructions_for("deck", state["brief_text"], state["outline"])}
        r = orig_call(kw)
        if state["outline"] and kw.get("purpose", "").endswith("write"):
            r.parsed = K.apply_outline(r.parsed, state["outline"])
            r.text = json.dumps(r.parsed)
        return r
    llm._call = call
    service.LLM = llm
    service.PLAIN = PLAIN
    service.SPEC = SPEC
    res = {"set": set_name, "tag": tag, "steps": {}, "started": time.time()}

    def done(kind, params, label):
        t = time.time()
        j = jobs.start(kind, f"bench:{label}:{time.time()}", params, wait=True)
        j = jobs.get(j["id"])
        res["steps"][label] = {"status": j["status"], "seconds": round(time.time() - t, 1), "error": j["error"]}
        print(f"{label}: {j['status']} {res['steps'][label]['seconds']}s {j['error'] or ''}", flush=True)
        return j

    files = B.SETS[set_name]
    rows = [service.read_file(f.name, f.read_bytes()) for f in files]
    ids = [r["id"] for r in rows]
    res["sources"] = [f.name for f in files]
    if set_name == "harborlight" and kit_id == "brand":
        t = time.time()
        d = service.import_read("pdf", filename="Harborlight-Brand-Guide-2025.pdf", data=(DENISE / "Harborlight-Brand-Guide-2025.pdf").read_bytes())
        kv = service.import_save(d["draft_id"])
        kit_id = (kv.get("kit") or kv)["id"]
        kits.set_logo(kit_id, "harborlight-logo.png", (DENISE / "harborlight-logo.png").read_bytes())
        res["steps"]["brand"] = {"status": "done", "seconds": round(time.time() - t, 1)}
    if set_name.startswith("heldout") and kit_id == "brand":  # its brand.txt, through the paste import (no model)
        t = time.time()
        d = service.import_read("paste", text=(REPO / f"harness/bench/sets/{set_name}/brand.txt").read_text())
        kv = service.import_save(d["draft_id"])
        kit_id = (kv.get("kit") or kv)["id"]
        res["steps"]["brand"] = {"status": "done", "seconds": round(time.time() - t, 1)}
    kit = kits.get(kit_id)
    res["kit"] = {"id": kit_id, "name": kit.get("name"), "colors": kit.get("colors"), "paper": kit.get("paper"), "ink": kit.get("ink"),
                  "kit_json": kit}
    t0 = time.time()
    started = [jobs.start("summarize", f"bench:sum:{sid}", {"source_id": sid}) for sid in ids]
    g = jobs.start("notebook_guide", f"bench:guide:{tag}", {"source_ids": ids})
    while any((jobs.get(x["id"]) or {}).get("status") == "running" for x in started + [g]):
        time.sleep(0.25)
    res["guide_and_summaries_seconds"] = round(time.time() - t0, 1)
    g = jobs.get(g["id"])
    res["steps"]["notebook_guide"] = {"status": g["status"], "error": g["error"]}
    guide = g["result"] or {}
    res["guide"] = guide
    asks = guide.get("asks") or []
    deck_ask = next((a for a in asks if a.get("kind") == "deck"), {})
    brief = dict(P6_BRIEF) if p6 else (deck_ask.get("brief") or dict(P6_BRIEF))
    if p6 and deck_ask.get("brief", {}).get("goal"):
        brief["goal"] = deck_ask["brief"]["goal"]
    res["brief"] = brief
    t_deck = time.time()
    if ONEPASS or PLAIN:  # round 6: the product's default make, no outline step (the one pass plans and writes together)
        outline = {}
    else:
        o = done("outline", {"source_ids": ids, "brief": brief, "ask": deck_ask if not p6 else {}}, "outline")
        outline = o["result"] or {}
    res["outline"] = outline
    state["outline"] = outline if outline.get("slides") else None
    state["brief_text"] = f"{deck_ask.get('what') or 'A funder deck'} for {brief.get('who')}" if not p6 else "A 7 to 9 slide funder deck"
    if ONEPASS and p6:  # the request the one pass gets: the P6 length and reader, with the guide's goal for the deck
        state["brief_text"] = f"A 7 to 9 slide funder deck for {brief.get('who') or 'Funders'}. Goal: {brief.get('goal') or 'Decide to fund this work'}"
    if PLAIN:  # round 13: the request word for word as the plain prompt's ("Make a 7 to 9 slide funder deck.")
        state["brief_text"] = "A 7 to 9 slide funder deck"
    if ROUTE:  # round 2: the real make-from-outline route (service._outline_for, follow_outline, max_slides)
        state["outline"] = None
    m = done("make", {"kind": "deck", "source_ids": ids, "kit_ids": [kit_id], "brief": state["brief_text"],
                      **({"outline_id": outline.get("outline_id")} if ROUTE and outline.get("slides") else {})}, "make_deck")
    res["deck_seconds"] = round(time.time() - t_deck, 1)
    oid = (m["result"] or {}).get("output_id")
    if oid:
        out = service._output(oid)
        res["output_id"] = oid
        res["case"] = store.get_setting(f"case_of:{oid}")
        res["plain_draft"] = store.get_setting(f"plain_draft_of:{oid}")  # round 13: the raw stage-1 draft
        res["plain_record"] = json.loads(store.get_setting(f"plain_record_of:{oid}") or "null")
        res["spec_record"] = json.loads(store.get_setting(f"spec_record_of:{oid}") or "null")  # loop 4
        res["argument"] = json.loads(store.get_setting(f"argument_of:{oid}") or "null")  # round 11: the checked case
        res["neutral"] = out["neutral"]
        res["live"] = service._doc_for(oid, kit)
        _s, _b, by_ref = service.passages_for(ids)
        res["passages"] = {r: {k: p.get(k) for k in ("text", "locator", "source_title", "source_id")} for r, p in by_ref.items()}
        gr = CK.grounding(res["live"], by_ref)
        res["grounding"] = [{k: i.get(k) for k in ("path", "value", "shown", "status", "kind")} for i in gr["items"]]
        res["exhibits"] = [s for s in res["live"]["slides"] if s.get("type") == "exhibit"]
        view = service.output_view(oid)
        pr = (view.get("proofs") or [{}])[0]
        res["check"] = [c["label"] for c in pr.get("checks") or [] if c.get("id") == "sources"]
        res["pills"] = [{k: c.get(k) for k in ("id", "tone", "label")} for c in pr.get("checks") or []]
        res["slide_count"] = pr.get("slide_count")
    if question:
        a = done("ask", {"question": question, "source_ids": ids}, "ask")
        chat = (a["result"] or {}).get("chat") or {}
        res["answer"] = {"question": question, "text": chat.get("text"), **K.split_answer(chat.get("text") or "")}
        res["answer"]["detail_words"] = K._wc(res["answer"]["detail"])
    res["seconds"] = round(time.time() - res["started"], 1)
    (RUNS / f"{tag}-result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    return res


def remap(src: Path, tag: str) -> Path:
    """Round 14: stage 2 again (code only, no model call) on a build's kept plain draft, in that build's data folder
    and brand, written as a new result under ``tag``. The draft and its run log are the original build's."""
    r = json.loads(Path(src).read_text())
    api, CK = B.load_imprint(DATA / r["tag"])
    from importlib import import_module
    K = import_module("imprint_plugin_package.content")
    kits = import_module("imprint_plugin_package.kits")
    kit = kits.get(r["kit"]["id"])
    by_ref = {k: {**v, "ref": k} for k, v in r["passages"].items()}
    slides = K.parse_plain(r["plain_draft"])
    doc = K.plain_doc(slides, by_ref)
    assert K.keeps_draft(doc, slides)
    doc, flags, splits = api.service.plain_stage2(doc, by_ref, kit, "A 7 to 9 slide funder deck")
    lines = K.shaped_lines(doc)
    want = [t for s_ in slides for t in [s_["title"]] + s_["lines"]]
    missing = [t for t in want if not any(t in x or x in t for x in lines)]
    out = {**r, "data_tag": r["tag"], "tag": tag, "from": str(src), "live": doc, "neutral": doc,
           "plain_record": {"flags": flags, "splits": splits, "slides": len(slides), "missing_lines": missing}}
    g = CK.grounding(doc, by_ref)
    out["grounding"] = [{k: i.get(k) for k in ("path", "value", "shown", "status", "kind")} for i in g["items"]]
    p = RUNS / f"{tag}-result.json"
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(tag, "flags", flags, "splits", splits, "missing", missing, "types", [s_.get("type") + ("/" + s_["shape"] if s_.get("shape") else "") for s_ in doc["slides"]])
    return p


def render(out_dir: Path, results: list) -> None:
    """Every slide of each result's brand doc, one PNG per slide, one process per result (each loads Imprint on
    that build's own data folder, where its brand and logo live)."""
    for path in results:
        subprocess.run([sys.executable, __file__, "render1", str(out_dir), str(path)], check=False)


def render1(out_dir: Path, path: Path) -> None:
    """Imprint's own renderer: ``render_deck.scenes`` then ``scene.png`` (the scene the canvas, the PDF and the
    PowerPoint share), with the logo as the exports draw it (``kits.logo_variants``). Deterministic from the doc."""
    r = json.loads(Path(path).read_text())
    api, CK = B.load_imprint(DATA / r.get("data_tag", r["tag"]))
    from importlib import import_module
    kits = import_module("imprint_plugin_package.kits")
    layout = import_module("imprint_plugin_package.layout")
    RD = import_module("imprint_plugin_package.render_deck")
    SC = import_module("imprint_plugin_package.scene")
    kit = api.service.kit_for_output(r["output_id"], kits.get(r["kit"]["id"])) if r.get("output_id") else kits.get(r["kit"]["id"])
    by_ref = {k: {**v, "ref": k} for k, v in r["passages"].items()}
    doc = CK.grounding(r["live"], by_ref)["doc"]
    pal, faces = kits.palette(kit), kits.faces(kit)
    idx, rows = layout.source_index(doc, by_ref)
    scs, ty = RD.scenes(doc, kit, pal, faces, idx, rows, "" if r.get("data_tag") else "November 9, 2026", by_ref)
    logos = RD.logo_bytes(kits.logo_variants(kit, pal))
    d = out_dir / r["tag"]
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("slide-*.png"):
        old.unlink()
    for i, sc in enumerate(scs, start=1):
        (d / f"slide-{i:02d}.png").write_bytes(SC.png(sc, ty, scale=2.0, logos=logos))
    print(r["tag"], len(scs), "slides ->", d, "long:", [sc["num"] for sc in scs if sc.get("long")], flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("build", "render", "render1", "remap"))
    ap.add_argument("args", nargs="+")
    ap.add_argument("--tag", default="")
    ap.add_argument("--kit", default="brand")
    ap.add_argument("--question", default="")
    ap.add_argument("--p6", action="store_true")
    ap.add_argument("--onepass", action="store_true")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--nospec", action="store_true")
    a = ap.parse_args()
    global ONEPASS, PLAIN, SPEC
    ONEPASS, PLAIN, SPEC = a.onepass, a.plain, not a.nospec
    if a.mode == "build":
        r = build(a.args[0], a.tag or a.args[0], a.kit, a.question, a.p6)
        print(json.dumps({"exhibits": r.get("exhibits"), "check": r.get("check"), "steps": r["steps"],
                          "answer": r.get("answer")}, indent=1, ensure_ascii=False))
    elif a.mode == "remap":
        remap(Path(a.args[0]), a.tag)
    elif a.mode == "render":
        render(Path(a.args[0]), a.args[1:])
    else:
        render1(Path(a.args[0]), Path(a.args[1]))


if __name__ == "__main__":
    main()
