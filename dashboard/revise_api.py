"""The AI lane's routes: the notebook guide, the outline, slide edits, Fix it for me, graphic options, and Keep,
Discard and Undo. Shapes: docs/API-NOTEBOOK.md, section 4.

Hermes's router and the live harness's stand-in router both take routes through ``router.get/post/delete``
decorators (the stand-in has no ``include_router``), so this file adds its routes to Imprint's own router:

    importlib.import_module("imprint_plugin_package.revise").routes().mount(router, "imprint_plugin_package")

Every route that calls a model starts a job and returns ``{job}`` at once. Inputs are checked here; everything
the model sees comes from the person's own data, read on the server.
"""

from __future__ import annotations

import logging
import re
from importlib import import_module

from fastapi import HTTPException

_log = logging.getLogger("hermes.plugins.imprint")


def mount(router, pkg: str = "imprint_plugin_package") -> list:
    """Add the routes to ``router``. Returns the ``(method, path)`` pairs added."""
    service = import_module(f"{pkg}.service")
    jobs = import_module(f"{pkg}.jobs")
    store = import_module(f"{pkg}.store")
    kits = import_module(f"{pkg}.kits")
    runtime = import_module(f"{pkg}.runtime")
    NG = import_module(f"{pkg}.notebook_guide")
    RV = import_module(f"{pkg}.revise")
    added = []

    def route(method: str, path: str):
        def deco(fn):
            getattr(router, method.lower())(path)(fn)
            added.append((method, path))
            return fn
        return deco

    def fail(e):
        if isinstance(e, HTTPException):
            raise e
        if isinstance(e, (ValueError, kits.KitError)):
            raise HTTPException(status_code=400, detail=str(e) or "That request isn't valid.")
        if isinstance(e, runtime.ModelError):
            raise HTTPException(status_code=502, detail=str(e))
        _log.exception("imprint: unexpected error in a revise route")
        raise HTTPException(status_code=500, detail="Something went wrong on Imprint's side. Try again.")

    def body_of(b) -> dict:
        if not isinstance(b, dict):
            raise ValueError("That request isn't valid.")
        return b

    def ids(v, prefix: str, limit: int = 50) -> list:
        if not isinstance(v, list):
            return []
        return [x for x in v if isinstance(x, str) and re.fullmatch(prefix + r"_[a-f0-9]{12}", x)][:limit]

    def sources(b: dict) -> list:
        got = ids(b.get("source_ids"), "s")
        if not got:
            raise ValueError("Tick at least one source first.")
        return got

    def out_id(v: str) -> str:
        if not re.fullmatch(r"o_[a-f0-9]{12}", v or ""):
            raise ValueError("That output is gone. Make it again from your sources.")
        return v

    def job_id(v) -> str:
        if not isinstance(v, str) or not re.fullmatch(r"j_[a-f0-9]{12}", v):
            raise ValueError("That suggestion is gone. Ask for it again.")
        return v

    def kit_id(v) -> str:
        if isinstance(v, str) and (v in kits.STARTER_IDS or re.fullmatch(r"k_[a-f0-9]{12}", v)):
            return v
        raise ValueError("Choose a brand first.")

    def short(v, n: int) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:n]

    def brief_of(v) -> dict:
        v = v if isinstance(v, dict) else {}
        return {"who": short(v.get("who"), 120), "goal": short(v.get("goal"), 200), "length": short(v.get("length"), 60)}

    # ------------------------------------------------------------ notebook guide --

    @route("POST", "/notebook/guide")
    async def post_notebook_guide(body: dict):
        try:
            src = sources(body_of(body))
            return {"job": jobs.start("notebook_guide", f"notebook_guide:{','.join(sorted(src))}", {"source_ids": src})}
        except Exception as e:
            fail(e)

    @route("GET", "/notebook/guide")
    async def get_notebook_guide():
        try:
            return {"guide": NG.last()}
        except Exception as e:
            fail(e)

    # ------------------------------------------------------------ outline --

    @route("POST", "/outlines")
    async def post_outline(body: dict):
        try:
            b = body_of(body)
            src = sources(b)
            brief = brief_of(b.get("brief"))
            ask = b.get("ask") if isinstance(b.get("ask"), dict) else {}
            ask = {"what": short(ask.get("what"), 160), "who": short(ask.get("who"), 60), "by": short(ask.get("by"), 40)}
            key = f"outline:{','.join(sorted(src))}:{brief['who']}:{brief['goal']}:{brief['length']}:{store.now()}"
            return {"job": jobs.start("outline", key, {"source_ids": src, "brief": brief, "ask": ask, "kind": "deck"})}
        except Exception as e:
            fail(e)

    @route("GET", "/outlines/{outline_id}")
    async def get_outline(outline_id: str):
        try:
            return RV.get_outline(outline_id)
        except Exception as e:
            fail(e)

    @route("POST", "/outlines/{outline_id}/rewrite")
    async def post_outline_rewrite(outline_id: str, body: dict):
        try:
            o = RV.get_outline(outline_id)
            i = body_of(body).get("index")
            if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < len(o["slides"]):
                raise ValueError("Pick a slide in the outline first.")
            return {"job": jobs.start("rewrite_title", f"rewrite:{outline_id}:{i}:{store.now()}", {"outline_id": outline_id, "index": i})}
        except Exception as e:
            fail(e)

    @route("POST", "/outlines/{outline_id}")
    async def post_outline_save(outline_id: str, body: dict):
        try:
            slides = body_of(body).get("slides")
            if not isinstance(slides, list):
                raise ValueError("That outline didn't come through. Try again.")
            clean = [{"title": short(s.get("title"), 160), "type": short(s.get("type"), 20),
                      "refs": [r for r in (s.get("refs") or []) if isinstance(r, str) and re.fullmatch(r"P\d{1,9}", r)][:8]}
                     for s in slides if isinstance(s, dict)]
            return RV.save_outline(outline_id, clean)
        except Exception as e:
            fail(e)

    # ------------------------------------------------------------ slide edits, fix, graphics --

    @route("POST", "/outputs/{output_id}/element-edit")
    async def post_element_edit(output_id: str, body: dict):
        try:
            oid, b = out_id(output_id), body_of(body)
            action = b.get("action")
            if action not in RV.ACTIONS:
                raise ValueError("Pick Shorter, Stronger headline, Turn into a chart, or type what to add.")
            slide = b.get("slide")
            if not isinstance(slide, int) or isinstance(slide, bool) or not 0 <= slide < 40:
                raise ValueError("Select a slide first.")
            params = {"output_id": oid, "kit_id": kit_id(b.get("kit_id")), "slide": slide, "action": action,
                      "text": short(b.get("text"), 200) if action == "typed" else ""}
            return {"job": jobs.start("element_edit", f"edit:{oid}:{slide}:{action}:{params['text']}:{store.now()}", params)}
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/fix")
    async def post_fix(output_id: str, body: dict):
        try:
            oid, b = out_id(output_id), body_of(body)
            key = b.get("key")
            if not isinstance(key, str) or not re.fullmatch(r"[\w.]{1,80}\|(?:number|quote)\|.{1,400}", key, re.S):
                raise ValueError("That flag is gone. The text may have changed.")
            return {"job": jobs.start("fix_it", f"fix:{oid}:{key}", {"output_id": oid, "kit_id": kit_id(b.get("kit_id")), "key": key})}
        except Exception as e:
            fail(e)

    @route("POST", "/graphics/options")
    async def post_graphic_options(body: dict):
        try:
            b = body_of(body)
            src = sources(b)
            note = ids([b.get("note_id")], "n", limit=1)
            text = short(b.get("text"), 3000)
            if not note and not text:
                raise ValueError("Pin an answer first, then make a graphic from it.")
            kit_id = str(b.get("kit_id") or "")[:64]
            params = {"source_ids": src, "note_id": note[0] if note else None, "text": "" if note else text,
                      "kit_id": kit_id if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", kit_id) else ""}
            return {"job": jobs.start("graphic_options", f"graphics:{','.join(sorted(src))}:{params['note_id']}:{text}:{store.now()}", params)}
        except Exception as e:
            fail(e)

    # ------------------------------------------------------------ keep, discard, undo --

    @route("POST", "/outputs/{output_id}/keep")
    async def post_keep(output_id: str, body: dict):
        try:
            oid, b = out_id(output_id), body_of(body)
            choice = b.get("choice", 0)
            if not isinstance(choice, int) or isinstance(choice, bool):
                raise ValueError("Pick one of the options first.")
            RV.keep(oid, job_id(b.get("job_id")), choice)
            return service.output_view(oid)
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/discard")
    async def post_discard(output_id: str, body: dict):
        try:
            out_id(output_id)
            return RV.discard(job_id(body_of(body).get("job_id")))
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/undo")
    async def post_undo(output_id: str, body: dict):
        try:
            oid = out_id(output_id)
            RV.undo(oid)
            return service.output_view(oid)
        except Exception as e:
            fail(e)

    return added
