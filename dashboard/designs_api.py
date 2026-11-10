"""The designs routes: three model-designed options for a deck, one-pager or graphic, the pick and the mix, element edits,
revise, versions and exports. Shapes: docs/API-DESIGNS.md.

Added to Imprint's own router the way revise_api.py does it. Every route that calls a model or draws with Chrome starts a job
and returns ``{job}`` at once; inputs are checked here and everything the model sees is read on the server."""

from __future__ import annotations

import logging
import re
from importlib import import_module

from fastapi import HTTPException

_log = logging.getLogger("hermes.plugins.imprint")


def mount(router, pkg: str = "imprint_plugin_package") -> list:
    service = import_module(f"{pkg}.service")
    jobs = import_module(f"{pkg}.jobs")
    kits = import_module(f"{pkg}.kits")
    runtime = import_module(f"{pkg}.runtime")
    D = import_module(f"{pkg}.designs")
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
        _log.exception("imprint: unexpected error in a designs route")
        raise HTTPException(status_code=500, detail="Something went wrong on Imprint's side. Try again.")

    def body_of(b) -> dict:
        if not isinstance(b, dict):
            raise ValueError("That request isn't valid.")
        return b

    def out_id(v: str) -> str:
        if not re.fullmatch(r"o_[a-f0-9]{12}", v or ""):
            raise ValueError("That output is gone. Make it again from your sources.")
        service._output(v)
        return v

    def kit_id(v) -> str:
        if isinstance(v, str) and (v in kits.STARTER_IDS or re.fullmatch(r"k_[a-f0-9]{12}", v)):
            return v
        raise ValueError("Choose a brand first.")

    @route("POST", "/outputs/{output_id}/designs")
    async def post_designs(output_id: str, body: dict):
        """Design the three options (or again). The kit defaults to the output's first."""
        try:
            oid = out_id(output_id)
            out = service._output(oid)
            if out["kind"] not in D.OFFERED:
                raise ValueError("Designs are for decks, one-pagers and graphics.")
            k = kit_id(body_of(body).get("kit_id") or (out["kit_ids"] or [None])[0])
            return {"job": jobs.start("designs", f"designs:{oid}:{k}", {"output_id": oid, "kit_id": k})}
        except Exception as e:
            fail(e)

    @route("GET", "/outputs/{output_id}/designs")
    async def get_designs(output_id: str):
        try:
            return D.view(out_id(output_id))
        except Exception as e:
            fail(e)

    @route("GET", "/outputs/{output_id}/designs/slide/{which}/{n}")
    async def get_design_slide(output_id: str, which: str, n: int):
        try:
            return {"img": D.slide_image(out_id(output_id), which, int(n))}
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/pick")
    async def post_design_pick(output_id: str, body: dict):
        """``{direction}``: every slide of one design. ``{picks: [{d, i}]}``: the mix, in order."""
        try:
            oid = out_id(output_id)
            b = body_of(body)
            st = D.load(oid)
            if isinstance(b.get("picks"), list):
                picks = [{"d": str(x.get("d")), "i": x.get("i")} for x in b["picks"][:60] if isinstance(x, dict)]
                label = ""
            else:
                d = b.get("direction")
                if d not in D.DIRS or (st["options"].get(d) or {}).get("status") != "ready":
                    raise ValueError("Pick a design that is ready.")
                picks = [{"d": d, "i": i} for i in range(1, len(st["options"][d]["slides"]) + 1)]
                label = ""
            D.compose(oid, picks, label)
            return D.view(oid)
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/edit")
    async def post_design_edit(output_id: str, body: dict):
        try:
            oid = out_id(output_id)
            b = body_of(body)
            slide, el = b.get("slide"), b.get("el")
            if not isinstance(slide, int) or not isinstance(el, int) or not isinstance(b.get("text"), str):
                raise ValueError("That edit isn't valid.")
            return {"job": jobs.start("designs_apply", f"designs_apply:{oid}:edit:{slide}:{el}", {"output_id": oid, "op": "edit", "slide": slide, "el": el, "text": b["text"][:600]})}
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/revise")
    async def post_design_revise(output_id: str, body: dict):
        try:
            oid = out_id(output_id)
            b = body_of(body)
            ins = re.sub(r"\s+", " ", str(b.get("instruction") or "")).strip()[:600]
            if not ins:
                raise ValueError("Say what to change.")
            slide = b.get("slide") if isinstance(b.get("slide"), int) else None
            return {"job": jobs.start("designs_apply", f"designs_apply:{oid}:revise:{ins}:{slide}", {"output_id": oid, "op": "revise", "instruction": ins, "slide": slide})}
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/restore")
    async def post_design_restore(output_id: str, body: dict):
        try:
            oid = out_id(output_id)
            vid = str(body_of(body).get("version") or "")
            if not re.fullmatch(r"v\d{10,16}", vid):
                raise ValueError("That version is gone.")
            D.restore(oid, vid)
            return D.view(oid)
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/keep")
    async def post_design_keep(output_id: str, body: dict):
        try:
            b = body_of(body)
            return D.keep(out_id(output_id), str(b.get("key") or "")[:200], bool(b.get("on", True)))
        except Exception as e:
            fail(e)

    ingest = import_module(f"{pkg}.ingest")

    @route("POST", "/kits/{kit_id}/style-brief")
    async def post_kit_style_brief(kit_id: str, body: dict):
        """Open a website in a browser, photograph a few of its pages and write a style brief into this kit."""
        try:
            if not re.fullmatch(r"k_[a-f0-9]{12}", kit_id or ""):
                raise ValueError("Save the brand first, then capture a style brief for it.")
            url = ingest.normalize_url(str(body_of(body).get("url") or ""))
            return {"job": jobs.start("kit_style_brief", f"style_brief:{kit_id}:{url}", {"kit_id": kit_id, "url": url})}
        except Exception as e:
            fail(e)

    @route("POST", "/outputs/{output_id}/designs/export")
    async def post_design_export(output_id: str, body: dict):
        try:
            return D.export(out_id(output_id), str(body_of(body).get("format") or "pdf"))
        except Exception as e:
            fail(e)

    return added
