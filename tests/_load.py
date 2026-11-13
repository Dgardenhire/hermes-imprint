"""Load Letterpress for tests: a temporary data folder, the package loaded the way the dashboard loads it, a
stand-in for fastapi when it is not installed (system Python), and a fake model that writes from the
labeled corpus it is given, so every claim it makes really is in a passage."""
import asyncio
import json
import logging
import os
import re
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
os.environ["LETTERPRESS_DATA_DIR"] = tempfile.mkdtemp(prefix="letterpress-test-")
logging.getLogger("hermes.plugins.letterpress").setLevel(logging.CRITICAL)

try:
    import fastapi  # noqa: F401
except ImportError:
    fa = types.ModuleType("fastapi")

    class HTTPException(Exception):
        def __init__(self, status_code, detail=None):
            super().__init__(detail)
            self.status_code, self.detail = status_code, detail

    class APIRouter:
        def __init__(self):
            self.routes = []

        def _add(self, method, path):
            def deco(fn):
                self.routes.append((method, path, fn))
                return fn
            return deco

        def get(self, path):
            return self._add("GET", path)

        def post(self, path):
            return self._add("POST", path)

        def delete(self, path):
            return self._add("DELETE", path)

    class Request:  # only the type is needed at import
        pass

    fa.APIRouter, fa.HTTPException, fa.Request = APIRouter, HTTPException, Request
    sys.modules["fastapi"] = fa

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location("plugin_api_under_test", ROOT / "dashboard" / "plugin_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
service, kits, jobs, store, ingest, runtime = api.service, api.kits, api.jobs, api.store, api.ingest, api.runtime
service.PLAIN = False  # round 13: the older tests drive the argued path; test_plain_r13 turns the plain draft on
PKG = "letterpress_plugin_package"
from importlib import import_module  # noqa: E402

content = import_module(f"{PKG}.content")
checks = import_module(f"{PKG}.checks")
colors = import_module(f"{PKG}.colors")
fonts = import_module(f"{PKG}.fonts")
layout = import_module(f"{PKG}.layout")
render_html = import_module(f"{PKG}.render_html")
render_pdf = import_module(f"{PKG}.render_pdf")
sitekit = import_module(f"{PKG}.sitekit")
guide = import_module(f"{PKG}.guide")
starter_kits = import_module(f"{PKG}.starter_kits")
imports = import_module(f"{PKG}.imports")
render_deck = import_module(f"{PKG}.render_deck")
logos = import_module(f"{PKG}.logos")
HTTPException = sys.modules["fastapi"].HTTPException


class Result:
    def __init__(self, parsed=None, text=None, usage=None):
        self.parsed = parsed
        self.text = text if text is not None else (json.dumps(parsed) if parsed is not None else "")
        self.usage = usage or {"input_tokens": 1200, "output_tokens": 300}


PASSAGE = re.compile(r"\[(P\d+)\] \(([^)]*)\) (.+)")


def passages_in(body):
    return [(m.group(1), m.group(2), m.group(3)) for m in PASSAGE.finditer(body)]


def first_sentence(text):
    return re.split(r"(?<=[.!?])\s+", text.strip())[0]


class FakeLlm:
    """Stands in for PluginLlm. Records every call. Answers from ``queue`` first (a dict, a string, or an
    exception to raise), else writes a grounded answer from the corpus in the call."""

    def __init__(self):
        self.calls = []
        self.queue = []
        self.trust_error_on_task = False

    async def acomplete_structured(self, **kw):
        self.calls.append(kw)
        if self.trust_error_on_task and kw.get("task"):
            err = type("PluginLlmTrustError", (Exception,), {})
            raise err("Plugin 'letterpress' cannot route through auxiliary task 'letterpress_write'")
        if kw.get("purpose", "").endswith(("argument", "argument_repair")):  # round 11: the case before the deck;
            arg = getattr(self, "argument", None)          # a test sets ``argument`` (a dict, or a list for draft
            if isinstance(arg, list):                      # then repair); none means no case, and the queue is kept
                arg = arg.pop(0) if arg else None
            return Result(parsed=arg)
        if self.queue:
            item = self.queue.pop(0)
            if isinstance(item, BaseException):
                raise item
            if isinstance(item, str):
                return Result(parsed=None, text=item)
            return Result(parsed=item)
        purpose = kw.get("purpose", "")
        body = kw["input"][0]["text"]
        return Result(parsed=self.answer(purpose, body, kw))

    def answer(self, purpose, body, kw):
        schema = kw.get("json_schema")
        if purpose.endswith("write") and (schema is content.DECK_SCHEMA or "case" in (schema or {}).get("properties", {})):
            return self.deck(passages_in(body))
        if purpose.endswith("write") and schema is content.AUDIO_SCHEMA:
            return self.audio(passages_in(body))
        if purpose.endswith("write") and schema is content.VISUAL_SCHEMA:
            return self.visual(passages_in(body))
        if purpose.endswith("summarize"):
            ps = re.findall(r"\(([^)]*)\) (.+)", body)
            first = first_sentence(ps[0][1]) if ps else "A short source."
            return {"summary": f"A source that says: {first}", "questions": ["What did it cost?", "Who came?", "What happens next?"]}
        if purpose.endswith("voice") and schema is content.VISUAL_SCHEMA:
            doc = json.loads(body)
            doc["headline"] = "In short, " + doc["headline"][0].lower() + doc["headline"][1:]
            return doc
        if purpose.endswith("voice") and schema is not content.ONEPAGER_SCHEMA:
            doc = json.loads(body)
            doc["title"] = "Here is " + doc["title"][0].lower() + doc["title"][1:]
            for sl in doc.get("slides", []):
                if sl.get("heading"):
                    sl["heading"] = sl["heading"] + " now"
            for seg in doc.get("segments", []):
                seg["heading"] = "Next up"
            return doc
        if purpose.endswith("write"):
            ps = passages_in(body)
            with_num = [p for p in ps if re.search(r"\d", p[2])]
            secs = []
            for ref, loc, text in (with_num or ps)[:3]:
                secs.append({"heading": "What the sources say", "body": first_sentence(text), "refs": [ref]})
            stat_p = next((p for p in ps if "2,914" in p[2]), with_num[0] if with_num else ps[0])
            m = re.search(r"\d[\d,]*", stat_p[2])
            return {"title": "What the warming center did this winter", "dek": "The center kept people warm through a hard winter.",
                    "dek_refs": [ps[0][0]], "stat": {"value": m.group(0) if m else "1", "label": "overnight stays", "ref": stat_p[0]},
                    "sections": secs or [{"heading": "Summary", "body": "The sources describe the program.", "refs": [ps[0][0]]}],
                    "points": [{"text": first_sentence(ps[-1][2])[:150], "ref": ps[-1][0]}],
                    "quote": None, "next": "The council takes up next season in April."}
        if purpose.endswith("voice"):
            doc = json.loads(body)
            doc["title"] = doc["title"].replace("What", "Here is what")
            for s in doc.get("sections", []):
                s["heading"] = "In short"
            return doc
        if purpose.endswith("ask"):
            ps = passages_in(body)
            ref = ps[0][0] if ps else "P1"
            return {"answer": f"The center opened on December 1. [{ref}]", "refs": [ref],
                    "followups": ["What did the season cost?", "How many guests stayed?", "What do staff recommend?"]}
        if purpose.endswith("image_kit"):
            assert any(b.get("type") == "image" for b in kw["input"]), "no image block"
            return {"colors": [{"hex": "#0b3d5c", "role": "head"}, {"hex": "#f6f1e7", "role": "paper"}, {"hex": "#1a1a1a", "role": "ink"},
                               {"hex": "#e0a526", "role": "accent"}], "heading_font": "Libre Caslon Display", "body_font": "Inter",
                    "serif_headings": True, "layout": "letter", "is_logo": True, "name": "Harbor Mill Co-op"}
        if purpose.endswith("site_voice"):
            return {"notes": "Plain and direct.", "delivery": "Steady.", "never": ["utilize"]}
        if purpose.endswith("guide"):
            base = {"name": "Harbor Plain", "why": "It fits.", "signature": "A band.", "layout": "banner", "paper": "#ffffff",
                    "ink": "#111111", "colors": [{"hex": "#0b4f45", "role": "head"}], "heading": {"family": "Inter", "weight": 700},
                    "body": {"family": "Inter"}, "density": "medium", "voice": {"notes": "Plain.", "delivery": "Steady."}}
            return {"proposals": [dict(base), dict(base, name="Second"), dict(base, name="Third", paper="#222222", ink="#333333")]}
        return {}


def _deck(self, ps):
    with_num = [p for p in ps if re.search(r"\d", p[2])]
    stat_p = next((p for p in ps if "2,914" in p[2]), with_num[0] if with_num else ps[0])
    m = re.search(r"2,914", stat_p[2]) or re.search(r"\d[\d,]*\d|\d", stat_p[2])
    bullets = [{"text": first_sentence(t)[:150], "ref": r} for r, _l, t in (with_num or ps)[:3]]
    return {"title": "The warming center season", "subtitle": "For the council work session",
            "slides": [{"type": "section", "heading": "What happened this winter", "subtitle": "Open every night it was cold", "refs": [ps[0][0]]},
                       {"type": "stat", "value": m.group(0) if m else "1", "label": "overnight stays", "context": "The center never turned anyone away.", "refs": [stat_p[0]]},
                       {"type": "content", "heading": "What the sources say", "bullets": bullets, "refs": [ps[0][0]]},
                       {"type": "comparison", "heading": "This season and next", "left_label": "This season", "left_items": bullets[:2],
                        "right_label": "Next season", "right_items": bullets[1:3], "refs": [ps[0][0]]},
                       {"type": "closing", "heading": "The decision", "text": "The council takes up next season in April.", "cta": "Decide on the second site", "refs": []}]}


def _audio(self, ps):
    with_num = [p for p in ps if re.search(r"\d", p[2])]
    segs = [{"heading": "What happened", "text": first_sentence(t), "refs": [r]} for r, _l, t in (with_num or ps)[:4]]
    return {"title": "The warming center in three minutes", "segments": segs, "recap": "Three things to remember: it opened, it filled, and it needs a decision."}


def _visual(self, ps):
    with_num = [p for p in ps if re.search(r"\$\d[\d,]*", p[2])] or [p for p in ps if re.search(r"\d", p[2])]
    items = []
    for r, _l, t in with_num:
        for m in re.finditer(r"\$\d[\d,]*\d|\d[\d,]*\d", t):
            items.append({"label": f"Figure {chr(65 + len(items))}", "value": m.group(0), "ref": r})
            if len(items) == 4:
                break
        if len(items) == 4:
            break
    return {"kicker": "Winter shelter", "headline": "The season in four numbers", "dek": "What the sources count.",
            "dek_refs": [ps[0][0]], "form": "bars", "unit": "As the sources give them", "items": items,
            "takeaway": "The council decides on a second site.", "takeaway_refs": []}


FakeLlm.deck = _deck
FakeLlm.audio = _audio
FakeLlm.visual = _visual


def fake_model():
    llm = FakeLlm()
    service.LLM = llm
    return llm


def run(coro):
    return asyncio.run(coro)


def reset():
    import shutil
    store.forget_everything()
    d = Path(os.environ["LETTERPRESS_DATA_DIR"])
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)


def add_samples():
    out = []
    for name in ("warming-center-report.md", "council-work-session.vtt", "guest-and-volunteer-survey.txt"):
        out.append(service.read_file(name, (SAMPLES / name).read_bytes()))
    return out


def make(source_ids, kit_ids, brief="A one-page brief for the council", kind="onepager"):
    j = jobs.start("make", f"t:{kind}:{brief}:{kit_ids}", {"kind": kind, "source_ids": source_ids, "kit_ids": kit_ids, "brief": brief}, wait=True)
    return jobs.get(j["id"])
