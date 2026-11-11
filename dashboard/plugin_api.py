"""Imprint's routes. Mounted by Hermes at /api/plugins/imprint/.

The page (desktop/plugin.js) reaches these through ``ctx.rest``. Anything slow (a model call, a web
read, reading a large file) starts a job and returns its id at once; the page polls ``GET /jobs/<id>``.
No request waits on a model, so the 30-second ``ctx.rest`` limit never matters.

Every model call runs here, through Hermes's plugin LLM facade, on the user's own model. Hermes wraps
each request in the requesting profile's settings scope, so the facade and ``plugin_data_dir`` follow
the active profile.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import logging
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

_ROOT = Path(__file__).resolve().parents[1]


def _package():
    """Load the plugin's modules as one package under the name ``register`` also uses."""
    name = "imprint_plugin_package"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load the Imprint package")
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[name] = pkg
        spec.loader.exec_module(pkg)
    from importlib import import_module
    return tuple(import_module(f"{name}.{m}") for m in ("service", "kits", "jobs", "store", "ingest", "runtime", "imports"))


service, kits, jobs, store, ingest, runtime, imports = _package()
_log = logging.getLogger("hermes.plugins.imprint")
router = APIRouter()

try:
    jobs.recover()
except Exception:  # a damaged database must not keep the page from loading; /state reports it
    _log.exception("imprint: could not check for interrupted jobs")
try:  # a design run cut off by a restart leaves its options saying "writing": mark them interrupted
    importlib.import_module("imprint_plugin_package.designs").reconcile_all()
except Exception:
    _log.exception("imprint: could not check for interrupted designs")
try:
    imports.expire()
except Exception:
    _log.exception("imprint: could not clear old kit drafts")
importlib.import_module("imprint_plugin_package.revise").routes().mount(router, "imprint_plugin_package")
importlib.import_module("imprint_plugin_package.designs").routes().mount(router, "imprint_plugin_package")


def _fail(e):
    if isinstance(e, HTTPException):
        raise e
    if isinstance(e, (ValueError, kits.KitError, imports.Refused)):
        raise HTTPException(status_code=400, detail=str(e) or "That request isn't valid.")
    if isinstance(e, runtime.ModelError):
        raise HTTPException(status_code=502, detail=str(e))
    _log.exception("imprint: unexpected error")
    raise HTTPException(status_code=500, detail="Something went wrong on Imprint's side. Try again.")


def _body(body) -> dict:
    if not isinstance(body, dict):
        raise ValueError("That request isn't valid.")
    return body


def _ids(v, prefix: str, limit: int = 50) -> list:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, str) and re.fullmatch(prefix + r"_[a-f0-9]{12}", x)][:limit]


def _kit_id(v) -> str:
    if isinstance(v, str) and (v in kits.STARTER_IDS or re.fullmatch(r"k_[a-f0-9]{12}", v)):
        return v
    raise ValueError("Choose a brand.")


# ---------------------------------------------------------------- state --

@router.get("/state")
async def get_state():
    try:
        return service.state()
    except Exception as e:
        _fail(e)


@router.post("/prefs")
async def post_prefs(body: dict):
    try:
        b = _body(body)
        keep = {k: b[k] for k in ("pair", "output", "tab", "rail", "kit") if k in b}
        prefs = {**(store.get_setting("prefs", {}) or {}), **keep}
        store.set_setting("prefs", prefs)
        return prefs
    except Exception as e:
        _fail(e)


@router.post("/settings")
async def post_settings(body: dict):
    try:
        b = _body(body)
        cap = b.get("daily_token_cap")
        if cap in (None, "", 0, "0"):
            store.set_setting("daily_token_cap", None)
        else:
            n = int(cap)
            if n < 1000 or n > 50_000_000:
                raise ValueError("Set the daily limit between 1,000 and 50,000,000 tokens, or leave it off.")
            store.set_setting("daily_token_cap", n)
        return service.usage()
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- jobs --

@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if not re.fullmatch(r"j_[a-f0-9]{12}", job_id):
        raise HTTPException(status_code=404, detail="That job is gone. Start it again.")
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="That job is gone.")
    return j


@router.post("/sample/open")
async def post_sample_open():
    try:
        return await asyncio.to_thread(service.open_sample)
    except Exception as e:
        _fail(e)


@router.post("/sample/close")
async def post_sample_close():
    try:
        return await asyncio.to_thread(service.close_sample)
    except Exception as e:
        _fail(e)


@router.post("/graphics/keep")
async def post_graphic_keep(body: dict):
    try:
        b = _body(body)
        job_id = b.get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"j_[a-f0-9]{12}", job_id):
            raise ValueError("Those graphics are gone. Make them again.")
        return service.keep_graphic(job_id, b.get("choice"), _kit_id(b.get("kit_id")))
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/add-graphic")
async def post_add_graphic(output_id: str, body: dict):
    try:
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("That output is gone. Make it again from your sources.")
        b = _body(body)
        job_id = b.get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"j_[a-f0-9]{12}", job_id):
            raise ValueError("Those graphics are gone. Make them again.")
        return service.add_graphic(output_id, job_id, b.get("choice"))
    except Exception as e:
        _fail(e)


@router.post("/jobs/{job_id}/stop")
async def post_stop(job_id: str):
    try:
        if not re.fullmatch(r"j_[a-f0-9]{12}", job_id):
            raise ValueError("That job is gone. Start it again.")
        return jobs.stop(job_id)
    except Exception as e:
        _fail(e)


@router.post("/jobs/{job_id}/retry")
async def post_retry(job_id: str):
    try:
        if not re.fullmatch(r"j_[a-f0-9]{12}", job_id):
            raise ValueError("That job is gone. Start it again.")
        return jobs.retry(job_id)
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- sources --

async def _read_capped(request: Request, limit: int, too_big: str) -> bytes:
    """The request body, refused as soon as it passes ``limit`` bytes (never read whole into memory first)."""
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > limit:
        raise ValueError(too_big)
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise ValueError(too_big)
        chunks.append(chunk)
    return b"".join(chunks)


async def _upload(request: Request):
    """One file from a multipart upload (``ctx.rest`` upload), or ``{filename, data}`` base64 JSON."""
    ctype = request.headers.get("content-type", "")
    too_big = "That file is over 25 MB. Split it, or add the pages you need."
    if ctype.startswith("multipart/"):
        # Starlette's form parser spools file parts to a temporary file with no size limit, so the body is read
        # here first, stopping at the cap, and the parser is handed only those bytes (Request.stream replays
        # ``_body`` when it is set). Nothing past the cap is read, held, or written to disk.
        request._body = await _read_capped(request, ingest.MAX_BYTES + 256 * 1024, too_big)
        try:
            form = await request.form(max_files=1, max_fields=8)
        except TypeError:  # an older Starlette without the limits; the body is already capped above
            form = await request.form()
        f = form.get("file")
        if f is None or not hasattr(f, "read"):
            raise ValueError("No file came through. Try adding it again.")
        data = await f.read(ingest.MAX_BYTES + 1)
        return getattr(f, "filename", "") or "file", data
    import json as _json
    raw = await _read_capped(request, (ingest.MAX_BYTES * 4) // 3 + 64 * 1024, too_big)
    try:
        b = _json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        raise ValueError("That file didn't come through whole. Try adding it again.")
    if not isinstance(b, dict) or not isinstance(b.get("data"), str):
        raise ValueError("No file came through. Try adding it again.")
    if len(b["data"]) > (ingest.MAX_BYTES * 4) // 3 + 8:
        raise ValueError("That file is over 25 MB. Split it, or add the pages you need.")
    try:
        data = base64.b64decode(b["data"], validate=True)
    except Exception:
        raise ValueError("That file didn't come through whole. Try adding it again.")
    return str(b.get("filename") or "file"), data


@router.post("/sources/file")
async def post_source_file(request: Request):
    try:
        filename, data = await _upload(request)
        filename = ingest.base_name(filename)[:200]
        ingest.check_upload(filename, len(data))
        token = store.new_id("u")
        store.write_bytes(store.root() / "uploads" / token, data)
        return {"job": jobs.start("read_file", f"file:{ingest.sha256(data)}", {"upload": token, "filename": filename})}
    except Exception as e:
        _fail(e)


@router.post("/sources/text")
async def post_source_text(body: dict):
    try:
        b = _body(body)
        row = service.add_text(b.get("title") or "", b.get("text") or "")
        service.summarize_soon(row)
        return {"source": row}
    except Exception as e:
        _fail(e)


@router.post("/sources/url")
async def post_source_url(body: dict):
    try:
        url = ingest.normalize_url(_body(body).get("url") or "")
        return {"job": jobs.start("read_url", f"url:{url}", {"url": url})}
    except Exception as e:
        _fail(e)


@router.post("/sources/include")
async def post_sources_include(body: dict):
    """Tick or untick sources for the notebook."""
    try:
        b = _body(body)
        ids = _ids(b.get("ids"), "s", limit=500)
        if not ids:
            raise ValueError("Choose a source first.")
        return {"sources": service.set_included(ids, bool(b.get("on")))}
    except Exception as e:
        _fail(e)


def _source_id(v) -> str:
    if isinstance(v, str) and re.fullmatch(r"s_[a-f0-9]{12}", v):
        return v
    raise ValueError("That source is gone. It may have been deleted.")


@router.get("/sources/{source_id}")
async def get_source(source_id: str):
    """One source and its passages, for the reader a citation opens."""
    try:
        return service.source_view(_source_id(source_id))
    except Exception as e:
        _fail(e)


@router.post("/sources/{source_id}/summarize")
async def post_source_summarize(source_id: str):
    try:
        sid = _source_id(source_id)
        if not store.one("SELECT id FROM sources WHERE id=?", (sid,)):
            raise ValueError("That source is gone. It may have been deleted.")
        return {"job": jobs.start("summarize", f"summarize:{sid}", {"source_id": sid})}
    except Exception as e:
        _fail(e)


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str):
    try:
        if not re.fullmatch(r"s_[a-f0-9]{12}", source_id):
            raise ValueError("That source is gone. It may have been deleted.")
        service.delete_source(source_id)
        return {"sources": service.list_sources(), "storage": service.storage()}
    except Exception as e:
        _fail(e)


@router.get("/passages/{ref}")
async def get_passage(ref: str):
    try:
        return service.passage(ref)
    except Exception as e:
        _fail(e)


@router.post("/forget")
async def post_forget(body: dict):
    try:
        if _body(body).get("confirm") != "forget everything":
            raise ValueError("Type the confirmation words to forget everything.")
        store.forget_everything()
        return service.state()
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- kits --

@router.get("/kits/{kit_id}")
async def get_kit(kit_id: str):
    try:
        return service.kit_view(_kit_id(kit_id))
    except Exception as e:
        _fail(e)


@router.post("/kits")
async def post_kit(body: dict):
    try:
        b = _body(body)
        raw = b.get("kit") if isinstance(b.get("kit"), dict) else b
        k = kits.save_new(raw)
        return service.kit_view(k["id"])
    except Exception as e:
        _fail(e)


@router.post("/kits/preview")
async def post_kit_preview(body: dict):
    """Palette, roles and fonts for an unsaved kit, so the editor shows contrast as you type."""
    try:
        b = _body(body)
        return service._draft_view(b.get("kit") if isinstance(b.get("kit"), dict) else b)
    except Exception as e:
        _fail(e)


@router.post("/kits/specimen")
async def post_kit_specimen(body: dict):
    """A kit's own slides and graphic on a built-in sample (``kit_id``, or an unsaved ``kit`` from the bench)."""
    try:
        b = _body(body)
        raw = {"all": bool(b.get("all"))}
        if b.get("kit_id") is not None:
            raw["kit_id"] = _kit_id(b.get("kit_id"))
        elif isinstance(b.get("kit"), dict):
            raw["kit"] = b["kit"]
        else:
            raise ValueError("Choose a brand.")
        return await asyncio.to_thread(service.specimen, raw)
    except Exception as e:
        _fail(e)


@router.post("/kits/from-site")
async def post_kit_from_site(body: dict):
    try:
        url = ingest.normalize_url(_body(body).get("url") or "")
        return {"job": jobs.start("site_kit", f"site:{url}", {"url": url})}
    except Exception as e:
        _fail(e)


MAX_IMPORT_JSON = 40 * 1024 * 1024


def _draft_id(v) -> str:
    if isinstance(v, str) and re.fullmatch(r"d_[a-f0-9]{12}", v):
        return v
    raise ValueError("That draft is gone. Import the file again.")


@router.post("/kits/import")
async def post_kit_import(request: Request):
    """Paste, CSS, a folder's files (Open Design, Claude Design) or a token file's text. Ends in a draft."""
    try:
        raw = await _read_capped(request, MAX_IMPORT_JSON, "That import is too big. Pick the folder's token files only.")
        import json as _json
        try:
            b = _json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            raise ValueError("That import didn't come through whole. Try again.")
        b = _body(b)
        kind = str(b.get("kind") or "")
        if kind not in ("paste", "css", "open-design", "claude-design", "dtcg"):
            raise ValueError("Choose what to import.")
        files = b.get("files") if isinstance(b.get("files"), dict) else None
        if files is not None:
            files = {str(k)[:200]: v for k, v in list(files.items())[:60] if isinstance(v, str)}
        text = b.get("text") if isinstance(b.get("text"), str) else ""
        return {"draft": service.import_read(kind, text=text, files=files, mode=str(b.get("mode") or "")[:40],
                                             filename=str(b.get("filename") or "")[:200])}
    except Exception as e:
        _fail(e)


@router.post("/kits/import/file")
async def post_kit_import_file(request: Request):
    """One file: a brand guide .pdf, .pptx, .css, a token file, a Claude Design .zip, or a PNG or JPG of a logo or brand
    sheet (read by the person's model)."""
    try:
        filename, data = await _upload(request)
        filename = ingest.base_name(filename)[:200]
        kind = imports.kind_from_name(filename)
        if not data:
            raise ValueError("That file is empty.")
        if kind == "image":
            why = imports.image_problem(filename, data)
            if why:
                raise ValueError(why)
            token = store.new_id("u")
            store.write_bytes(store.root() / "uploads" / token, data)
            return {"job": jobs.start("image_kit", f"image:{ingest.sha256(data)}", {"upload": token, "filename": filename})}
        if kind in ("pptx", "claude-design-zip", "pdf"):
            # Read off the event loop: a brand guide or a deck can take seconds to parse, and the dashboard's other
            # requests (this pane and every other plugin's) wait on the loop while it does.
            return {"draft": await asyncio.to_thread(service.import_read, kind, filename=filename, data=data)}
        if len(data) > imports.MAX_DTCG and kind == "dtcg":
            raise ValueError("This token file is too big for one brand. Export just your brand colors and type.")
        text = data.decode("utf-8", "replace")
        return {"draft": service.import_read(kind, text=text, filename=filename)}
    except Exception as e:
        _fail(e)


@router.get("/kits/import/{draft_id}")
async def get_kit_import(draft_id: str):
    try:
        return service.import_view(_draft_id(draft_id))
    except Exception as e:
        _fail(e)


@router.post("/kits/import/{draft_id}/save")
async def post_kit_import_save(draft_id: str):
    try:
        return service.import_save(_draft_id(draft_id))
    except Exception as e:
        _fail(e)


@router.post("/kits/import/{draft_id}")
async def post_kit_import_update(draft_id: str, body: dict):
    try:
        did = _draft_id(draft_id)
        imports.update(did, _body(body).get("patch") or {})
        return service.import_view(did)
    except Exception as e:
        _fail(e)


@router.delete("/kits/import/{draft_id}")
async def delete_kit_import(draft_id: str):
    try:
        imports.discard(_draft_id(draft_id))
        return {"ok": True}
    except Exception as e:
        _fail(e)


@router.post("/kits/guide")
async def post_kit_guide(body: dict):
    try:
        b = _body(body)
        fx = b.get("fixed") if isinstance(b.get("fixed"), dict) else {}
        strs = lambda v, n, each: [str(x)[:each] for x in (v if isinstance(v, list) else []) if isinstance(x, str) and x.strip()][:n]
        fixed = {"name": str(fx.get("name") or "")[:60], "org": str(fx.get("org") or "")[:80],
                 "colors": strs(fx.get("colors"), 12, 24), "fonts": strs(fx.get("fonts"), 4, 80),
                 "notes": str(fx.get("notes") or "")[:1000]}
        subject = b.get("subject") if isinstance(b.get("subject"), dict) else {}
        params = {"fixed": {k: v for k, v in fixed.items() if v},
                  "subject": {k: str(v)[:3000] for k, v in subject.items()
                              if k in ("reader", "job", "work", "only", "sample") and isinstance(v, str)},
                  "refs": [{k: str(v)[:400] for k, v in r.items() if k in ("kit_id", "url", "note", "draft_id") and isinstance(v, str)}
                           for r in (b.get("refs") or []) if isinstance(r, dict)][:3]}
        return {"job": jobs.start("guide", f"guide:{store.now()}", params)}
    except Exception as e:
        _fail(e)


@router.post("/kits/{kit_id}")
async def post_kit_update(kit_id: str, body: dict):
    try:
        k = kits.update(_kit_id(kit_id), _body(body).get("kit") or {})
        return service.kit_view(k["id"])
    except Exception as e:
        _fail(e)


@router.post("/kits/{kit_id}/duplicate")
async def post_kit_duplicate(kit_id: str):
    try:
        return service.kit_view(kits.duplicate(_kit_id(kit_id))["id"])
    except Exception as e:
        _fail(e)


@router.delete("/kits/{kit_id}")
async def delete_kit(kit_id: str):
    try:
        kits.delete(_kit_id(kit_id))
        return {"kits": kits.list_all()}
    except Exception as e:
        _fail(e)


@router.post("/kits/{kit_id}/logo")
async def post_kit_logo(kit_id: str, request: Request):
    try:
        filename, data = await _upload(request)
        kits.set_logo(_kit_id(kit_id), ingest.base_name(filename), data)
        return service.kit_view(kit_id)
    except Exception as e:
        _fail(e)


@router.delete("/kits/{kit_id}/logo")
async def delete_kit_logo(kit_id: str):
    try:
        kits.remove_logo(_kit_id(kit_id))
        return service.kit_view(kit_id)
    except Exception as e:
        _fail(e)


@router.post("/kits/{kit_id}/logo-reversed")
async def post_kit_logo_reversed(kit_id: str, request: Request):
    try:
        filename, data = await _upload(request)
        kits.set_logo(_kit_id(kit_id), ingest.base_name(filename), data, alt=True)
        return service.kit_view(kit_id)
    except Exception as e:
        _fail(e)


@router.delete("/kits/{kit_id}/logo-reversed")
async def delete_kit_logo_reversed(kit_id: str):
    try:
        kits.remove_logo(_kit_id(kit_id), alt=True)
        return service.kit_view(kit_id)
    except Exception as e:
        _fail(e)


@router.post("/kits/{kit_id}/fonts")
async def post_kit_font(kit_id: str, request: Request):
    try:
        filename, data = await _upload(request)
        kits.add_font(_kit_id(kit_id), ingest.base_name(filename), data)
        return service.kit_view(kit_id)
    except Exception as e:
        _fail(e)


@router.get("/fonts/{key}")
async def get_font(key: str):
    try:
        return service.font_file(key)
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- outputs --

@router.post("/outputs")
async def post_output(body: dict):
    try:
        b = _body(body)
        source_ids = _ids(b.get("source_ids"), "s")
        if not source_ids:
            raise ValueError("Choose at least one source first.")
        kit_ids = [_kit_id(k) for k in (b.get("kit_ids") or [])[:2]]
        if not kit_ids:
            raise ValueError("Choose a brand first.")
        kind = b.get("kind") if b.get("kind") in ("onepager", "deck", "audio", "visual", "report") else "onepager"
        brief = str(b.get("brief") or "")[:1200]
        note_ids = _ids(b.get("note_ids"), "n", limit=20)
        key = f"make:{kind}:{','.join(sorted(source_ids))}:{','.join(kit_ids)}:{brief}:{','.join(note_ids)}"
        pictures = bool(b.get("pictures")) and kind == "deck"
        key += ":pic" if pictures else ""
        params = {"kind": kind, "source_ids": source_ids, "kit_ids": kit_ids, "brief": brief, "note_ids": note_ids, "pictures": pictures}
        outline_id = b.get("outline_id")
        if outline_id:
            if not isinstance(outline_id, str) or not re.fullmatch(r"ol_[a-f0-9]{12}", outline_id):
                raise ValueError("That outline is gone. Write it again.")
            params["outline_id"] = outline_id
            key += ":" + outline_id
        return {"job": jobs.start("make", key, params)}
    except Exception as e:
        _fail(e)


@router.get("/outputs/{output_id}")
async def get_output(output_id: str):
    try:
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        return service.output_view(output_id)
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/kit")
async def post_output_kit(output_id: str, body: dict):
    """Swap the kit in one slot: the wording is redone in the new kit's voice; the facts stay."""
    try:
        b = _body(body)
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        kit_id = _kit_id(b.get("kit_id"))
        slot = 0 if b.get("slot") in (0, "0") else 1
        return {"job": jobs.start("voice", f"voice:{output_id}:{kit_id}:{slot}", {"output_id": output_id, "kit_id": kit_id, "slot": slot})}
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/decide")
async def post_decide(output_id: str, body: dict):
    try:
        b = _body(body)
        return service.decide(output_id, str(b.get("key") or "")[:600], b.get("action"))
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/required")
async def post_required(output_id: str, body: dict):
    """Print a kit's required lines on this output, or leave them off it."""
    try:
        b = _body(body)
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        return service.set_required(output_id, _kit_id(b.get("kit_id")), bool(b.get("on")))
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/edit")
async def post_edit(output_id: str, body: dict):
    try:
        b = _body(body)
        return service.edit(output_id, str(b.get("path") or ""), b.get("text"))
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/export")
async def post_export(output_id: str, body: dict):
    try:
        b = _body(body)
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        return service.export(output_id, _kit_id(b.get("kit_id")), str(b.get("format") or "pdf"))
    except Exception as e:
        _fail(e)


@router.get("/outputs/{output_id}/audio/{kit_id}")
async def get_output_audio(output_id: str, kit_id: str):
    try:
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        return service.audio_file(output_id, _kit_id(kit_id))
    except Exception as e:
        _fail(e)


@router.post("/outputs/{output_id}/speak")
async def post_speak(output_id: str, body: dict):
    """Record (or record again) one kit's audio brief through the user's own Hermes voice."""
    try:
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        kit_id = _kit_id(_body(body).get("kit_id"))
        return {"job": jobs.start("speak", f"speak:{output_id}:{kit_id}:{store.now()}", {"output_id": output_id, "kit_id": kit_id})}
    except Exception as e:
        _fail(e)


@router.delete("/outputs/{output_id}")
async def delete_output(output_id: str):
    try:
        if not re.fullmatch(r"o_[a-f0-9]{12}", output_id):
            raise ValueError("No such output.")
        service.delete_output(output_id)
        return {"outputs": service.list_outputs(), "storage": service.storage()}
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- ask --

@router.get("/chats")
async def get_chats():
    try:
        return {"chats": service.chats()}
    except Exception as e:
        _fail(e)


@router.delete("/chats")
async def delete_chats():
    try:
        service.clear_chats()
        return {"chats": []}
    except Exception as e:
        _fail(e)


# ---------------------------------------------------------------- notes --

@router.get("/notes")
async def get_notes():
    try:
        return {"notes": service.list_notes()}
    except Exception as e:
        _fail(e)


@router.post("/notes")
async def post_note(body: dict):
    """Pin a chat answer (``chat_id``) or keep a typed note (``text``)."""
    try:
        b = _body(body)
        cid = b.get("chat_id")
        if cid is not None and not (isinstance(cid, int) and not isinstance(cid, bool) and 0 < cid < 10**12):
            raise ValueError("That answer is gone. Ask again, then pin it.")
        text = b.get("text") if isinstance(b.get("text"), str) else ""
        return {"note": service.add_note(text=text[:service.MAX_NOTE + 1], chat_id=cid), "notes": service.list_notes()}
    except Exception as e:
        _fail(e)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str):
    try:
        if not re.fullmatch(r"n_[a-f0-9]{12}", note_id):
            raise ValueError("That note is gone already.")
        service.delete_note(note_id)
        return {"notes": service.list_notes()}
    except Exception as e:
        _fail(e)


@router.post("/ask")
async def post_ask(body: dict):
    try:
        b = _body(body)
        q = str(b.get("question") or "").strip()
        if not q:
            raise ValueError("Type a question first.")
        if len(q) > 2000:
            raise ValueError("That question is too long. Keep it under 2,000 characters.")
        source_ids = _ids(b.get("source_ids"), "s")
        if not source_ids:
            raise ValueError("Choose at least one source first.")
        return {"job": jobs.start("ask", f"ask:{q}:{','.join(source_ids)}", {"question": q, "source_ids": source_ids})}
    except Exception as e:
        _fail(e)
