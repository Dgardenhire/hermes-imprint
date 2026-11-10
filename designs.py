"""Designs: for a deck, a one-pager or a graphic, the model lays the piece out itself in three different directions, each
drawn by Chrome, looked at and fixed. The person picks one, or mixes slides across the three, then refines it with element
edits and a revise box. Everything rests on ``htmldeck`` (the engine) and on the checked content the notebook already made:
the three directions share the same words and the same number trace.

What lives here is the product around the engine: the brand kit as the engine's brand, three options running at once with a
progress line, the picked or mixed result, its versions, and its exports. The template path (the proof, the canvas, the
outline, versions and exports of the existing output) is untouched: designs sit beside it."""

from __future__ import annotations

import asyncio
import base64
import copy
import io
import re
import shutil
import threading
import time
from importlib import import_module
from pathlib import Path
from typing import Optional

try:
    from . import checks as CK
    from . import htmldeck as HD
    from . import jobs as J
    from . import kits as KITS
    from . import runtime as R
    from . import sitestyle as SST
    from . import store
except ImportError:  # loaded loose
    import checks as CK  # type: ignore
    import htmldeck as HD  # type: ignore
    import jobs as J  # type: ignore
    import kits as KITS  # type: ignore
    import runtime as R  # type: ignore
    import sitestyle as SST  # type: ignore
    import store  # type: ignore

DIRS = ("editorial", "databoard", "statement")
HD_KIND = {"deck": "deck", "onepager": "onepager", "visual": "graphic"}
OFFERED = tuple(HD_KIND)
FORMATS = {"deck": {"pdf": "PDF of the slides", "pptx": "PowerPoint (slide pictures with notes)"},
           "onepager": {"pdf": "PDF", "png": "PNG image"},
           "visual": {"pdf": "PDF", "png": "PNG image"}}
MAX_VERSIONS = 20
ROUNDS = 2  # look-and-fix rounds per design (htmldeck.make adds up to two more while a layout problem is left)
_locks: dict = {}
_lock_guard = threading.Lock()


def _service():
    try:
        return import_module(__package__ + ".service") if __package__ else import_module("service")
    except ImportError:  # pragma: no cover
        return import_module("service")


# ---------------------------------------------------------------- state on disk --

def folder(oid: str) -> Path:
    return store.root() / "outputs" / oid / "designs"


def _lock(oid: str) -> threading.Lock:
    with _lock_guard:
        return _locks.setdefault(oid, threading.Lock())


def load(oid: str) -> dict:
    return store.read_json(folder(oid) / "state.json", None) or {"options": {}, "final": None, "versions": [], "kept": []}


def save(oid: str, st: dict) -> None:
    folder(oid).mkdir(parents=True, exist_ok=True)
    store.write_json(folder(oid) / "state.json", st)


def _png_list(d: Path) -> list:
    return sorted(str(p) for p in d.glob("s[0-9][0-9].png"))


# ---------------------------------------------------------------- the brand --

def _mix(a: str, b: str, t: float) -> str:
    A = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    B = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * (1 - t) + y * t):02x}" for x, y in zip(A, B))


def _face_files(face: dict) -> list:
    """The font files of a face's family that sit beside the one resolved: the bundled families ship several weights and an
    italic, so the model can ask for bold or italic and get the real file. Any other file stands for every weight."""
    out = []
    f = face.get("file")
    if not f or not Path(f).is_file():
        return out
    fam = face.get("used") or face.get("wanted") or "Font"
    slug = re.sub(r"[^a-z0-9]+", "-", fam.lower()).strip("-")
    sib = [p for p in Path(f).parent.glob(f"{slug}-*.ttf") if re.fullmatch(rf"{re.escape(slug)}-\d{{3}}(?:-italic)?\.ttf", p.name)]
    for p in sorted(sib):
        m = re.fullmatch(rf"{re.escape(slug)}-(\d{{3}})(-italic)?\.ttf", p.name)
        out.append({"family": fam, "weight": m.group(1), "style": "italic" if m.group(2) else "normal", "file": p})
    if not out:
        out.append({"family": fam, "weight": "100 900", "style": "normal", "file": Path(f)})
    return out


def style_hint(kit: dict) -> str:
    """The kit's own layout family and density, as a starting style the model may follow or depart from."""
    bits = []
    if kit.get("layout"):
        bits.append(f"the kit's layout family is '{kit['layout']}'")
    if kit.get("density"):
        bits.append(f"its density is {kit['density']}")
    if kit.get("starter"):
        bits.append(f"it is the studio kit {kit.get('name', '')}")
    if not bits:
        return ""
    return ("STARTING STYLE from the brand kit: " + "; ".join(bits) + ". Treat it as a starting point: follow it where it helps the "
            "design direction below and depart from it where the content or the direction needs something else.")


def brand_for(kit: dict) -> tuple:
    """``(brand dict for htmldeck.kit_css, brand text for the model, logo data URI)`` from a kit."""
    pal = KITS.palette(kit)
    faces = KITS.faces(kit)
    paper, ink, head = pal["paper"], pal["ink"], pal["head"]
    v = {"--brand": head, "--brand-tint": _mix(paper, head, 0.10), "--brand-mid": _mix(paper, head, 0.55), "--paper": paper, "--ink": ink,
         "--muted": _mix(ink, paper, 0.35), "--rule": pal.get("rule") or _mix(paper, ink, 0.2), "--band": pal.get("band") or head,
         "--band-text": pal.get("band_text") or paper, "--accent": pal.get("accent") or head, "--cta": pal.get("accent") or head}
    for role in ("accent2", "highlight", "fill"):
        if pal.get(role):
            v["--accent2"] = pal[role]
            break
    fonts = _face_files(faces["heading"]) + _face_files(faces["body"])
    brand = {"heading": faces["heading"].get("used") or "Arial", "body": faces["body"].get("used") or "Georgia", "vars": v, "fonts": fonts}
    voice = kit.get("voice") or {}
    lines = [f"Brand: {kit.get('name', '')}." + (f" {kit['org']}." if kit.get("org") else ""),
             f"Headline face {brand['heading']} (var(--font-heading)), body face {brand['body']} (var(--font-body)); quotes in italic body.",
             "CSS variables you may use: " + "; ".join(f"{k} = {x}" for k, x in v.items()) + ".",
             "Roles: --brand primary (headlines, bands, chart marks); --brand-tint and --brand-mid are tints of it; --paper the ground; "
             "--ink body text; --muted secondary text; --rule hairlines; --accent for one emphasis per piece, never as a fill for large "
             "areas; --cta for a call to action only, never for data."]
    if voice.get("notes"):
        lines.append("Voice: " + str(voice["notes"])[:400])
    if voice.get("never"):
        lines.append("Never write: " + ", ".join(map(str, voice["never"][:20])) + ".")
    req = (kit.get("rules") or {}).get("required") or []
    if req:
        lines.append("Every piece ends with this line, small, exactly: " + " ".join(map(str, req)))
    lines.append('The logo is <img src="imprint:logo" alt="">, at least 56px wide, never stretched.')
    sb = SST.brief_text(kit.get("style_brief"))
    if sb:
        lines.append(sb)
    ls = _service().logo_srcs(kit, pal)[0] or {}
    logo = ls.get("paper") or next(iter(ls.values()), "")
    return brand, "\n".join(lines), logo


def _ctx(oid: str, kit_id: str) -> dict:
    S = _service()
    out = S._output(oid)
    if out["kind"] not in OFFERED:
        raise ValueError("Designs are for decks, one-pagers and graphics.")
    kit = S.kit_for_output(oid, KITS.get(kit_id))
    _s, _b, by_ref = S.passages_for(out["source_ids"])
    passages = {k: {"text": v["text"]} for k, v in by_ref.items()}
    doc = S._doc_for(oid, kit)
    brand, brand_text, logo = brand_for(kit)
    return {"out": out, "kit": kit, "passages": passages, "doc": doc, "brand": brand, "brand_text": brand_text, "logo": logo,
            "hd": HD_KIND[out["kind"]], "css": HD.kit_css(brand, HD_KIND[out["kind"]])}


# ---------------------------------------------------------------- scoping, saving an option --

def _scoped(slides: list, d: str) -> list:
    return [{"html": HD.scope_classes(s["html"], f"{d[:2]}{i}_"), "notes": s.get("notes", "")} for i, s in enumerate(slides, 1)]


def _save_option(oid: str, d: str, r: dict) -> dict:
    slides = _scoped(r["slides"], d)
    tr = HD.trace(slides, r["passages"]) if r.get("passages") else r["trace"]
    opt = {"status": "ready", "slides": slides, "flags": tr["flags"], "counts": tr["counts"], "problems": r["render"]["problems"],
           "removed": r.get("removed", []), "rounds": r.get("rounds", 0), "made_at": store.now()}
    with _lock(oid):
        st = load(oid)
        st["options"][d] = opt
        save(oid, st)
    return opt


def _set_status(oid: str, d: str, status: str, step: str = "", error: str = "") -> None:
    with _lock(oid):
        st = load(oid)
        o = st["options"].setdefault(d, {})
        o.update({"status": status, "step": step, "error": error})
        save(oid, st)


# ---------------------------------------------------------------- make the three --

@J.handler("designs")
async def job_designs(job_id: str, p: dict) -> dict:
    oid, kit_id = p["output_id"], p["kit_id"]
    cx = _ctx(oid, kit_id)
    kind, hd = cx["out"]["kind"], cx["hd"]
    content = HD.content_text(cx["doc"], hd)
    llm = _service().model(oid)
    hint = style_hint(cx["kit"])
    with _lock(oid):
        old = load(oid)
        st = {"kit_id": kit_id, "kind": kind, "options": {d: {"status": "writing", "step": "waiting"} for d in DIRS}, "final": old.get("final"),
              "versions": old.get("versions", []), "kept": old.get("kept", [])}
        save(oid, st)
    shutil.rmtree(folder(oid) / "tmp", ignore_errors=True)
    steps = {d: "waiting" for d in DIRS}

    def report():
        J.step(job_id, "Designing three options: " + " · ".join(f"{HD.DIRECTIONS[hd][d]['name']} {steps[d]}" for d in DIRS))

    async def one(d: str):
        def step(t):
            steps[d] = t
            _set_status(oid, d, "writing", t)
            report()
        try:
            r = await HD.make(llm, cx["brand"], cx["brand_text"], cx["passages"], content, folder(oid) / d, d, cx["logo"], ROUNDS, hd, step=step, style_hint=hint)
            r["passages"] = cx["passages"]
            _save_option(oid, d, r)
            steps[d] = "done"
        except J.Stopped:
            raise
        except Exception as e:  # one direction failing never costs the others
            steps[d] = "failed"
            _set_status(oid, d, "failed", "", str(e)[:200] if isinstance(e, (ValueError, R.ModelError)) else "It did not come back. Try this one again.")
        report()

    report()
    await asyncio.gather(*[one(d) for d in DIRS])
    st = load(oid)
    ready = [d for d in DIRS if (st["options"].get(d) or {}).get("status") == "ready"]
    if not ready:
        raise J.JobError("None of the three designs came back. Press Retry.", "failed")
    if not st.get("final"):
        compose(oid, [{"d": ready[0], "i": i} for i in range(1, len(st["options"][ready[0]]["slides"]) + 1)], label=HD.DIRECTIONS[hd][ready[0]]["name"])
    return {"output_id": oid, "ready": ready}


# ---------------------------------------------------------------- pick and mix --

def compose(oid: str, picks: list, label: str = "") -> dict:
    """The result from ``picks``: ``[{"d": direction, "i": slide number}]`` in the order wanted. Slides keep their own scoped
    CSS, so a slide from one design never reaches another. The pictures are the options' own pictures."""
    with _lock(oid):
        st = load(oid)
        kind = st.get("kind") or _service()._output(oid)["kind"]
        if kind != "deck":
            picks = picks[:1]
        slides, fdir = [], folder(oid) / "final"
        shutil.rmtree(fdir, ignore_errors=True)
        fdir.mkdir(parents=True, exist_ok=True)
        for n, pk in enumerate(picks, 1):
            d, i = pk.get("d"), pk.get("i")
            opt = (st["options"].get(d) or {})
            if d not in DIRS or opt.get("status") != "ready" or not isinstance(i, int) or not 1 <= i <= len(opt["slides"]):
                raise ValueError("Pick a slide from a design that is ready.")
            src = copy.deepcopy(opt["slides"][i - 1])
            png = folder(oid) / d / f"s{i:02d}.png"
            if png.exists():
                shutil.copy(png, fdir / f"s{n:02d}.png")
            src["from"] = f"{d}:{i}"
            slides.append(src)
        if not slides:
            raise ValueError("Pick at least one slide.")
        ds = {s["from"].split(":")[0] for s in slides}
        st["final"] = {"slides": slides, "label": label or ("Mixed" if len(ds) > 1 else HD.DIRECTIONS[HD_KIND[kind]][next(iter(ds))]["name"])}
        _snapshot(st, st["final"]["label"])
        save(oid, st)
    return load(oid)


def _snapshot(st: dict, label: str) -> None:
    v = {"id": f"v{int(time.time() * 1000)}", "at": store.now(), "label": label, "slides": copy.deepcopy(st["final"]["slides"])}
    st["versions"] = ([v] + (st.get("versions") or []))[:MAX_VERSIONS]


def restore(oid: str, version_id: str) -> dict:
    with _lock(oid):
        st = load(oid)
        v = next((x for x in st.get("versions") or [] if x["id"] == version_id), None)
        if not v:
            raise ValueError("That version is gone.")
        st["final"] = {"slides": copy.deepcopy(v["slides"]), "label": v["label"]}
        save(oid, st)
    return redraw_final(oid)


def keep(oid: str, key: str, on: bool = True) -> dict:
    with _lock(oid):
        st = load(oid)
        k = [x for x in st.get("kept") or [] if x != key]
        if on:
            k.append(key)
        st["kept"] = k[-200:]
        save(oid, st)
    return view(oid)


# ---------------------------------------------------------------- redraw, edit, revise --

def redraw_final(oid: str) -> dict:
    """Draw the result again (after an edit, a revise or a restore) so its pictures are exactly its markup."""
    st = load(oid)
    cx = _ctx(oid, st["kit_id"])
    slides = [dict(s) for s in st["final"]["slides"]]
    r = HD.render_safe(slides, cx["css"], folder(oid) / "final", cx["logo"], cx["hd"])
    with _lock(oid):
        st = load(oid)
        st["final"]["slides"] = [dict(a, html=b["html"]) for a, b in zip(st["final"]["slides"], slides)]
        st["final"]["problems"] = r["problems"]
        save(oid, st)
    return st


@J.handler("designs_apply")
async def job_apply(job_id: str, p: dict) -> dict:
    oid = p["output_id"]
    st = load(oid)
    if not st.get("final"):
        raise J.JobError("Pick a design first.", "failed")
    cx = _ctx(oid, st["kit_id"])
    op = p.get("op")
    if op == "edit":
        J.step(job_id, "Applying your edit")
        slides = [dict(s) for s in st["final"]["slides"]]
        i = int(p["slide"]) - 1
        if not 0 <= i < len(slides):
            raise J.JobError("That slide is gone.", "failed")
        new, ok = HD.set_text(slides[i]["html"], int(p["el"]), str(p.get("text") or ""))
        if not ok:
            raise J.JobError("That line is gone. Open the slide again.", "failed")
        slides[i]["html"] = new
        with _lock(oid):
            st = load(oid)
            st["final"]["slides"] = slides
            _snapshot(st, f"Edited slide {i + 1}")
            save(oid, st)
        J.step(job_id, "Drawing it again")
        await asyncio.get_event_loop().run_in_executor(None, lambda: redraw_final(oid))
        return {"output_id": oid}
    if op == "revise":
        instruction = re.sub(r"\s+", " ", str(p.get("instruction") or "")).strip()[:600]
        if not instruction:
            raise J.JobError("Say what to change.", "failed")
        llm = _service().model(oid)
        slides = [dict(s) for s in st["final"]["slides"]]
        only = p.get("slide")
        if isinstance(only, int) and 1 <= only <= len(slides):
            instruction = f"On slide {only} only: {instruction}"
        r = await HD.revise(llm, cx["brand_text"], cx["passages"], slides, instruction, cx["css"], folder(oid) / "final", cx["logo"], cx["hd"],
                            step=lambda t: J.step(job_id, "Revising: " + t))
        with _lock(oid):
            st = load(oid)
            st["final"]["slides"] = [dict(a, html=b["html"], notes=b.get("notes", a.get("notes", ""))) for a, b in zip(st["final"]["slides"], r["slides"])]
            st["final"]["problems"] = r["render"]["problems"]
            _snapshot(st, "Revised: " + instruction[:40])
            save(oid, st)
        return {"output_id": oid, "changed": r["changed"]}
    raise J.JobError("Unknown change.", "failed")


# ---------------------------------------------------------------- what the pane shows --

def _thumb(path: Path, width: int = 480) -> str:
    try:
        from PIL import Image
        cache = path.parent / "t" / f"{path.stem}-{width}.png"
        if not cache.exists() or cache.stat().st_mtime < path.stat().st_mtime:
            cache.parent.mkdir(exist_ok=True)
            im = Image.open(path).convert("RGB")
            im.thumbnail((width, width * 2))
            buf = io.BytesIO()
            im.save(buf, "PNG", optimize=True)
            cache.write_bytes(buf.getvalue())
        return "data:image/png;base64," + base64.b64encode(cache.read_bytes()).decode("ascii")
    except Exception:
        return ""


def slide_image(oid: str, which: str, n: int) -> str:
    """The big picture of one slide: ``which`` is a direction or ``final``."""
    if which not in DIRS + ("final",) or not isinstance(n, int) or n < 1:
        raise ValueError("No such slide.")
    p = folder(oid) / which / f"s{n:02d}.png"
    if not p.exists():
        raise ValueError("That slide isn't drawn yet.")
    return _thumb(p, 1100)


def _flag_key(f: dict) -> str:
    return f"{f.get('value')}|{(f.get('text') or '')[:40]}"


def view(oid: str) -> dict:
    S = _service()
    out = S._output(oid)
    st = load(oid)
    kind = out["kind"]
    hd = HD_KIND.get(kind)
    if not hd:
        return {"available": False}
    names = HD.DIRECTIONS[hd]
    kept = set(st.get("kept") or [])
    options = []
    for d in DIRS:
        o = st["options"].get(d) or {}
        n = len(o.get("slides") or [])
        pngs = _png_list(folder(oid) / d) if o.get("status") == "ready" else []
        options.append({"d": d, "name": names[d]["name"], "blurb": re.split(r"(?<=[.])\s", names[d]["brief"])[0], "status": o.get("status") or "none",
                        "step": o.get("step") or "", "error": o.get("error") or "", "slides": n,
                        "flags": len(o.get("flags") or []), "problems": [p for p in o.get("problems") or [] if p.get("kind") in HD.HARD],
                        "thumbs": [_thumb(Path(p)) for p in pngs]})
    final = None
    flags: list = []
    if st.get("final"):
        sl = st["final"]["slides"]
        cx_passages = None
        try:
            _s, _b, by_ref = S.passages_for(out["source_ids"])
            cx_passages = {k: {"text": v["text"]} for k, v in by_ref.items()}
        except Exception:
            pass
        tr = HD.trace(sl, cx_passages) if cx_passages is not None else {"flags": [], "counts": {}}
        for f in tr["flags"]:
            f = dict(f, key=_flag_key(f), kept=_flag_key(f) in kept)
            flags.append(f)
        fdir = folder(oid) / "final"
        final = {"label": st["final"].get("label", ""), "problems": [p for p in st["final"].get("problems", []) if p.get("kind") in HD.HARD],
                 "slides": [{"n": i, "from": s.get("from", ""), "thumb": _thumb(fdir / f"s{i:02d}.png"),
                             "elements": HD.elements(s["html"])[:40], "notes": s.get("notes", "")} for i, s in enumerate(sl, 1)],
                 "counts": tr["counts"]}
    open_flags = [f for f in flags if not f["kept"]]
    return {"available": True, "output_id": oid, "kind": kind, "kit_id": st.get("kit_id"), "options": options, "final": final, "flags": flags,
            "open_flags": len(open_flags), "versions": [{"id": v["id"], "label": v["label"], "at": v["at"]} for v in st.get("versions") or []],
            "formats": FORMATS[kind], "made": any(o["status"] == "ready" for o in options),
            "building": any(o["status"] == "writing" for o in options)}


# ---------------------------------------------------------------- exports --

def export(oid: str, fmt: str) -> dict:
    S = _service()
    v = view(oid)
    kind = v.get("kind")
    if not v.get("final"):
        raise ValueError("Pick a design first.")
    if fmt not in FORMATS.get(kind, {}):
        raise ValueError("Choose one of: " + ", ".join(FORMATS[kind].values()) + ".")
    if v["open_flags"]:
        raise ValueError("Fix or keep the numbers that aren’t in your sources first.")
    st = load(oid)
    cx = _ctx(oid, st["kit_id"])
    out = folder(oid) / "export"
    out.mkdir(parents=True, exist_ok=True)
    base = {"deck": "deck", "onepager": "brief", "visual": "graphic"}[kind] + "-" + re.sub(r"[^a-z0-9]+", "-", (cx["kit"].get("name") or "kit").lower()).strip("-") + "-designed"
    slides = [dict(s) for s in st["final"]["slides"]]
    if fmt == "pdf":
        path = out / f"{base}.pdf"
        HD.export_pdf(slides, cx["css"], path, cx["logo"], cx["hd"])
    elif fmt == "png":
        src = folder(oid) / "final" / "s01.png"
        path = out / f"{base}.png"
        shutil.copy(src, path)
    else:
        pngs = _png_list(folder(oid) / "final")
        if len(pngs) != len(slides):
            redraw_final(oid)
            pngs = _png_list(folder(oid) / "final")
        path = out / f"{base}.pptx"
        HD.pptx(pngs, slides, path, cx["out"].get("title") or "Deck")
    if not path.exists():
        raise ValueError("The file could not be made. Try again.")
    return {"path": str(path), "name": path.name, "folder": str(out), "bytes": path.stat().st_size}


# ---------------------------------------------------------------- recorded options (tests and the harness; no model) --

def seed(oid: str, kit_id: str, recorded: dict, pick: Optional[str] = None) -> dict:
    """Store options written earlier (``{direction: [{html, notes}]}``): cleaned, drawn and traced here, never trusted as they
    stand. Nothing calls a model."""
    cx = _ctx(oid, kit_id)
    with _lock(oid):
        old = load(oid)
        save(oid, {"kit_id": kit_id, "kind": cx["out"]["kind"], "options": {}, "final": None, "versions": old.get("versions", []), "kept": []})
    for d, slides in recorded.items():
        clean = []
        for s in slides:
            h, _rm = HD.sanitize(s["html"])
            clean.append({"html": h, "notes": s.get("notes", "")})
        r = HD.render_safe(clean, cx["css"], folder(oid) / d, cx["logo"], cx["hd"])
        _save_option(oid, d, {"slides": clean, "render": r, "passages": cx["passages"], "removed": []})
    st = load(oid)
    ready = [d for d in DIRS if (st["options"].get(d) or {}).get("status") == "ready"]
    first = pick if pick in ready else ready[0]
    compose(oid, [{"d": first, "i": i} for i in range(1, len(st["options"][first]["slides"]) + 1)], label=HD.DIRECTIONS[cx["hd"]][first]["name"])
    return view(oid)


def routes():
    """``dashboard/designs_api.py``, loaded by path (the dashboard folder is not part of the package)."""
    import importlib.util
    import sys
    name = "imprint_designs_api"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "dashboard" / "designs_api.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load Imprint's designs routes")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]
