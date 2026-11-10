"""What the routes call. Sources, kits, outputs, proofs, checks, exports, Ask, and the jobs behind them."""

from __future__ import annotations

import asyncio
import copy
import re
import shutil
import time
from pathlib import Path
from typing import Optional

try:
    from . import checks as CK
    from . import colors as C
    from . import content as K
    from . import fonts as F
    from . import guide as G
    from . import imports as IM
    from . import ingest as I
    from . import jobs as J
    from . import kits as KITS
    from . import layout as L
    from . import logos as LG
    from . import render_deck as RD
    from . import render_graphic as RG
    from . import render_html as RH
    from . import render_pdf as RP
    from . import runtime as R
    from . import scene as SC
    from . import sitekit as S
    from . import sitestyle as SST
    from . import store
except ImportError:  # loaded loose
    import checks as CK  # type: ignore
    import colors as C  # type: ignore
    import content as K  # type: ignore
    import fonts as F  # type: ignore
    import guide as G  # type: ignore
    import imports as IM  # type: ignore
    import ingest as I  # type: ignore
    import jobs as J  # type: ignore
    import kits as KITS  # type: ignore
    import layout as L  # type: ignore
    import logos as LG  # type: ignore
    import render_deck as RD  # type: ignore
    import render_graphic as RG  # type: ignore
    import render_html as RH  # type: ignore
    import render_pdf as RP  # type: ignore
    import runtime as R  # type: ignore
    import scene as SC  # type: ignore
    import sitekit as S  # type: ignore
    import sitestyle as SST  # type: ignore
    import store  # type: ignore

LLM = None  # tests put a stand-in here; inside Hermes the model is resolved on first use
MAX_SOURCES_PER_OUTPUT = 12


def model(output_id: Optional[str] = None) -> R.Model:
    def meter(purpose, usage):
        store.record_usage(purpose, usage, output_id)

    def cap():
        v = store.get_setting("daily_token_cap")
        return int(v) if v else None
    return R.Model(llm=LLM, meter=meter, cap=cap, used_today=store.tokens_today)


SAMPLE_DATE = "October 1, 2026"  # the sample's own day: after the September 13 retreat, before the October 21 vote


def out_date(out: dict) -> str:
    """The date an output carries: the day it was made, or the sample's own day while the sample is open (so its
    pages don't call a past board vote upcoming)."""
    try:
        in_sample = R.sample_open() or (store.root() / "sample.json").exists()  # the sample folder carries its mark
    except Exception:
        in_sample = False
    return SAMPLE_DATE if in_sample else nice_date(out.get("created_at"))


def nice_date(t: Optional[float] = None) -> str:
    lt = time.localtime(t or time.time())
    return time.strftime("%B ", lt) + str(lt.tm_mday) + time.strftime(", %Y", lt)


# ---------------------------------------------------------------- sources --

def source_row(r: dict) -> dict:
    inc = r.get("included")
    return {"id": r["id"], "title": r["title"], "kind": r["kind"], "origin": r.get("origin") or "", "bytes": r.get("bytes") or 0,
            "chars": r.get("chars") or 0, "units": r.get("units") or 0, "unit_label": r.get("unit_label") or "",
            "truncated": bool(r.get("truncated")), "note": r.get("note") or "", "created_at": r.get("created_at"),
            "included": True if inc is None else bool(inc), "summary": r.get("summary") or "",
            "questions": store.loads(r.get("questions"), []) or [], "summary_state": r.get("summary_state") or "",
            "sample": R.sample_open()}


def list_sources() -> list:
    return [source_row(r) for r in store.q("SELECT * FROM sources ORDER BY created_at DESC")]


def _save_source(kind: str, title: str, origin: str, ext: str, data: Optional[bytes], blocks: list, units: int,
                 unit_label: str, sha: str) -> dict:
    existing = store.one("SELECT * FROM sources WHERE sha256=?", (sha,))
    if existing:
        row = source_row(existing)
        row["duplicate"] = True
        return row
    packed = I.pack(blocks)
    packed, truncated = I.cap_blocks(packed)
    if not packed:
        raise I.Refused("Imprint found no readable text in that.")
    sid = store.new_id("s")
    chars = sum(len(t) for _l, t in packed)
    note = "Only the first 400,000 characters were kept." if truncated else ""
    if data is not None:
        store.write_bytes(store.root() / "sources" / f"{sha}{ext}", data)
    store.run("INSERT INTO sources(id, sha256, kind, title, origin, ext, bytes, chars, units, unit_label, truncated, note, created_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (sid, sha, kind, title[:160], origin[:400], ext, len(data or b""), chars, units, unit_label, int(truncated), note, store.now()))
    store.many("INSERT INTO passages(source_id, seq, locator, text) VALUES(?,?,?,?)",
               [(sid, i, loc, text) for i, (loc, text) in enumerate(packed)])
    return source_row(store.one("SELECT * FROM sources WHERE id=?", (sid,)))


def read_file(filename: str, data: bytes) -> dict:
    ext = I.check_upload(filename, len(data))
    sha = I.sha256(data)
    dup = store.one("SELECT * FROM sources WHERE sha256=?", (sha,))
    if dup:
        row = source_row(dup)
        row["duplicate"] = True
        return row
    if ext == ".pdf":
        blocks, units, label = I.read_pdf(data)
        kind = "PDF"
    elif ext == ".docx":
        blocks, units, label = I.read_docx(data)
        kind = "Word"
    elif ext in I.TRANSCRIPT_EXT:
        blocks, units, label = I.read_transcript(data.decode("utf-8", "replace"))
        kind = "Transcript"
    else:
        text = data.decode("utf-8", "replace")
        if re.search(r"^\s*(WEBVTT|\d+\s*\n\s*\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->)", text[:400]):
            blocks, units, label = I.read_transcript(text)
            kind = "Transcript"
        else:
            blocks, units, label = I.read_text(text)
            kind = "Markdown" if ext in (".md", ".markdown") else "Text"
    return _save_source(kind, I.label_title(filename), filename, ext, data, blocks, units, label, sha)


def add_text(title: str, text: str) -> dict:
    if not isinstance(text, str) or not text.strip():
        raise I.Refused("Paste some text first.")
    if len(text) > I.MAX_PASTE:
        raise I.Refused("That is more than 400,000 characters. Save it as a file and add the file instead.")
    title = (title or "").strip()[:120] or I.label_title(text.strip().split("\n", 1)[0][:60])
    data = text.encode("utf-8")
    blocks, units, label = I.read_text(text)
    return _save_source("Pasted", title, "pasted", ".txt", data, blocks, units, label, I.sha256(data))


EXTRACT_CHARS = 90000  # Hermes caps a tool's answer near 100,000 characters


def _safe_public_url(url: str) -> bool:
    """The address rules every web read follows before anything is sent: http or https only, no user name or
    password in it, and a host that resolves to a public address (Hermes's own check), so a link can never point
    the person's web tool at their own machine, their network or a cloud metadata address."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    if u.scheme.lower() not in ("http", "https") or not u.hostname or u.username or u.password:
        return False
    try:
        _make, is_safe = I._client_factory()
    except Exception:
        return False
    try:
        return bool(is_safe(url))
    except Exception:
        return False


def _extract(url: str) -> Optional[dict]:
    """The page through the person's own Hermes web tool (``web_extract``), as ``{url, title, text}``, or ``None``
    when the tool isn't set up here (then Imprint reads the page itself, through the same safe client)."""
    try:
        res = R.dispatch_bounded("web_extract", {"urls": [url], "char_limit": EXTRACT_CHARS}, 90.0)
    except R.ToolUnavailable:
        return None
    items = res.get("results") if isinstance(res, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    it = items[0]
    final = str(it.get("url") or url)
    if it.get("error"):
        err = str(it["error"]).lower()
        if "blocked" in err or "private" in err:
            raise I.Refused(I.UNSAFE)
        return None
    text = str(it.get("content") or "")
    if not text.strip():
        return None
    if final != url and not _safe_public_url(final):
        raise I.Refused(I.UNSAFE)
    return {"url": final, "title": str(it.get("title") or "")[:160], "text": text[:I.MAX_CHARS]}


async def read_url(url: str) -> dict:
    url = I.normalize_url(url)
    if not await asyncio.to_thread(_safe_public_url, url):
        raise I.Refused(I.UNSAFE)
    got = await asyncio.to_thread(_extract, url)
    if got:
        blocks, units, label = I.read_text(got["text"])
        host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", got["url"]).split("/")[0])
        return _save_source("Web page", (got["title"] or host)[:160], got["url"], ".html", None, blocks, units, label,
                            I.sha256(got["url"].encode("utf-8") + got["text"][:200000].encode("utf-8")))
    fetched = await I.fetch(url, max_bytes=I.MAX_BYTES)
    blocks, units, label, title = I.read_page(fetched)
    host = re.sub(r"^www\.", "", re.sub(r"^https?://", "", fetched["url"]).split("/")[0])
    data = fetched.get("raw") or fetched.get("body", "").encode("utf-8")
    return _save_source("Web page", (title or host)[:160], fetched["url"], ".html", None, blocks, units, label,
                        I.sha256(fetched["url"].encode("utf-8") + data[:200000]))


def set_included(source_ids: list, on: bool) -> list:
    """Tick or untick sources for the notebook: the chat answers from, and the Studio builds from, ticked ones only."""
    for sid in source_ids:
        store.run("UPDATE sources SET included=? WHERE id=?", (1 if on else 0, sid))
    return list_sources()


def included_ids() -> list:
    return [r["id"] for r in store.q("SELECT id FROM sources WHERE COALESCE(included, 1)=1 ORDER BY created_at")]


MAX_READER_PASSAGES = 800


def source_view(source_id: str) -> dict:
    """One source with its passages, for the reader a citation opens."""
    row = store.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not row:
        raise ValueError("That source is gone. It may have been deleted.")
    rows = store.q("SELECT id, seq, locator, text FROM passages WHERE source_id=? ORDER BY seq LIMIT ?", (source_id, MAX_READER_PASSAGES))
    return {"source": source_row(row), "passages": [{"ref": f"P{r['id']}", "locator": r["locator"], "text": r["text"]} for r in rows],
            "more": (store.one("SELECT COUNT(*) AS n FROM passages WHERE source_id=?", (source_id,)) or {}).get("n", 0) > len(rows)}


SUMMARY_CHARS = 14000


def summarize_soon(row: Optional[dict]) -> Optional[dict]:
    """Start the short summary for a source that was just read, unless it has one or one is on the way."""
    if not row or row.get("duplicate") or row.get("summary"):
        return None
    try:
        return J.start("summarize", f"summarize:{row['id']}", {"source_id": row["id"]})
    except Exception:  # a summary is a nicety; the source is already saved
        return None


@J.handler("summarize")
async def job_summarize(job_id: str, p: dict) -> dict:
    sid = p.get("source_id") or ""
    row = store.one("SELECT * FROM sources WHERE id=?", (sid,))
    if not row:
        raise J.JobError("That source is gone.", "gone")
    store.run("UPDATE sources SET summary_state='running' WHERE id=?", (sid,))
    J.step(job_id, f"Reading {row['title']}")
    text, used = [], 0
    for r in store.q("SELECT locator, text FROM passages WHERE source_id=? ORDER BY seq", (sid,)):
        chunk = f"({r['locator']}) {r['text']}"
        if used + len(chunk) > SUMMARY_CHARS:
            break
        text.append(chunk)
        used += len(chunk)
    body = f"=== SOURCE: {row['title']} ({row['kind']}) ===\n" + "\n".join(text)
    try:
        raw = await model().structured(system=K.SYSTEM, instructions=K.SUMMARY_RULES, body=R.redact(body), schema=K.SUMMARY_SCHEMA,
                                       purpose="summarize", max_tokens=500, timeout=90)
        got = K.clean_summary(raw)
    except (R.ModelError, ValueError) as e:
        store.run("UPDATE sources SET summary_state='failed' WHERE id=?", (sid,))
        raise J.JobError(str(e) if isinstance(e, R.ModelError) else "The summary came back empty. Press Retry.", "summary")
    store.run("UPDATE sources SET summary=?, questions=?, summary_state='ready' WHERE id=?",
              (got["summary"], store.dumps(got["questions"]), sid))
    return {"source": source_row(store.one("SELECT * FROM sources WHERE id=?", (sid,)))}


def delete_source(source_id: str) -> None:
    row = store.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not row:
        raise ValueError("That source is gone already.")
    store.run("DELETE FROM passages WHERE source_id=?", (source_id,))
    store.run("DELETE FROM sources WHERE id=?", (source_id,))
    p = store.root() / "sources" / f"{row['sha256']}{row.get('ext') or ''}"
    if p.exists():
        p.unlink()


def passages_for(source_ids: list) -> tuple:
    """``(sources, passages_by_source, passages_by_ref)`` for the chosen sources."""
    if not source_ids:
        return [], {}, {}
    marks = ",".join("?" * len(source_ids))
    srcs = store.q(f"SELECT * FROM sources WHERE id IN ({marks})", source_ids)
    order = {sid: i for i, sid in enumerate(source_ids)}
    srcs.sort(key=lambda s: order.get(s["id"], 99))
    rows = store.q(f"SELECT * FROM passages WHERE source_id IN ({marks}) ORDER BY source_id, seq", source_ids)
    by_source, by_ref = {}, {}
    titles = {s["id"]: s["title"] for s in srcs}
    for r in rows:
        by_source.setdefault(r["source_id"], []).append(r)
        by_ref[f"P{r['id']}"] = {"text": r["text"], "locator": r["locator"], "source_id": r["source_id"],
                                 "source_title": titles.get(r["source_id"], "Source")}
    return srcs, by_source, by_ref


def passage(ref: str) -> dict:
    m = re.fullmatch(r"P(\d+)", ref or "")
    row = store.one("SELECT p.*, s.title AS source_title FROM passages p JOIN sources s ON s.id=p.source_id WHERE p.id=?",
                    (int(m.group(1)),)) if m else None
    if not row:
        raise ValueError("That passage is gone. Its source may have been deleted.")
    return {"ref": ref, "text": row["text"], "locator": row["locator"], "source_title": row["source_title"],
            "source_id": row["source_id"]}


def _corpus(source_ids: list, with_ids: bool = False) -> tuple:
    srcs, by_source, by_ref = passages_for(source_ids)
    if not srcs:
        raise J.JobError("Choose at least one source first.", "no_sources")
    text, ids = I.corpus(srcs, by_source)
    if with_ids:
        return R.redact(text), srcs, by_ref, {f"P{i}" for i in ids}
    return R.redact(text), srcs, by_ref


# ---------------------------------------------------------------- kits --

def kit_view(kit_id: str) -> dict:
    kit = KITS.get(kit_id)
    pal = KITS.palette(kit)
    faces = KITS.faces(kit)
    return {"kit": kit, "palette": pal, "faces": _face_view(faces), "summary": KITS.summary(kit),
            "colophon": F.colophon(faces, 0).split(". Drawn")[0] + ".", "logo": KITS.logo_data_url(kit),
            "logo_alt": KITS.logo_data_url(kit, alt=True), "logo_check": _logo_check(kit, pal),
            "look": KITS.look_of(kit), "substitutions": F.substitutions(faces), "deck": KITS.deck_system(kit)}


def _logo_check(kit: dict, pal: dict) -> Optional[str]:
    """A plain note for the bench when the logo would vanish on the kit's band or paper."""
    v = KITS.logo_variants(kit, pal)
    p = LG.pill(kit, "deck", v)
    return p["label"] if p else None


def logo_srcs(kit: dict, pal: dict) -> tuple:
    """``({"paper": url, "band": url}, variants)``: the logo as it goes on each ground."""
    v = KITS.logo_variants(kit, pal)
    srcs = {place: (x or {}).get("data_url") for place, x in v.items()}
    return (srcs if any(srcs.values()) else None), v


def _face_view(faces: dict) -> dict:
    return {role: {k: f.get(k) for k in ("wanted", "used", "key", "css", "weight", "style", "substituted", "note", "source")}
            for role, f in faces.items()}


def font_file(key: str) -> dict:
    """Base64 bytes for one resolved face key, for the pane's FontFace."""
    if not re.fullmatch(r"[ub]-[a-z0-9-]+-\d{3}-(normal|italic)", key or ""):
        raise ValueError("Imprint doesn't have that font.")
    if key.startswith("b-"):
        for fam, w, s, fn, _c in F.BUNDLED:
            k = f"b-{re.sub(r'[^a-z0-9]+', '-', fam.lower())}-{w}-{s}"
            if k == key:
                return {"key": key, "family": fam, "weight": w, "style": s, "data": F.font_bytes_b64(str(F.BUNDLED_DIR / fn))}
        raise ValueError("Imprint doesn't have that font.")
    for d in KITS.kits_dir().iterdir():
        kit = store.read_json(d / "kit.json") or {}
        for f in kit.get("fonts") or []:
            k = f"u-{re.sub(r'[^a-z0-9]+', '-', (f.get('family') or '').lower())}-{int(f.get('weight') or 400)}-{f.get('style') or 'normal'}"
            name = f.get("file") if isinstance(f.get("file"), str) else ""
            if not KITS.FONT_FILE.fullmatch(name):
                continue
            p = d / "fonts" / name
            if k == key and p.is_file():
                return {"key": key, "family": f["family"], "weight": f.get("weight"), "style": f.get("style"),
                        "data": F.font_bytes_b64(str(p))}
    raise ValueError("Imprint doesn't have that font.")


async def read_site(url: str) -> dict:
    return _draft_view(await read_site_raw(url))


async def read_site_raw(url: str) -> dict:
    url = I.normalize_url(url)
    fetched = await I.fetch(url)
    if I.looks_blocked(fetched.get("status", 0), fetched.get("body", "")):
        raise I.Blocked("That site didn't let Imprint read it. Add a logo and colors by hand, or start from a starter kit.")
    if fetched.get("status", 0) >= 400:
        raise I.Refused(f"That page answered with an error ({fetched['status']}). Check the address.")
    css = []
    for link in S.stylesheet_links(fetched["body"], fetched["url"])[:S.MAX_STYLESHEETS]:
        try:
            got = await I.fetch(link, max_bytes=S.MAX_CSS_BYTES, accept="text/css,*/*;q=0.5", stop_at_cap=True)
            if got.get("status", 0) < 400:
                css.append(got.get("body", ""))
        except I.Refused:
            continue
    draft = S.draft_from(fetched["body"], css, fetched["url"], nice_date())
    # Voice notes: a draft from the page's own words, if the model is reachable. Colors never come from it.
    blocks, _title = I.html_to_blocks(fetched["body"])
    page_text = "\n".join(t for _l, t in blocks)[:12000]
    if len(page_text) > 300:
        try:
            v = await model().structured(system=K.SYSTEM, instructions=S.VOICE_RULES, body=R.redact(page_text),
                                         schema=S.VOICE_SCHEMA, purpose="site_voice", max_tokens=900, timeout=90)
            draft["voice"].update({"notes": str(v.get("notes") or "")[:1200], "delivery": str(v.get("delivery") or "")[:400],
                                   "never": [str(w)[:60] for w in (v.get("never") or [])][:6], "draft": True})
        except R.ModelError as e:
            draft["voice_note"] = "Voice notes were left for you to write: " + str(e)
    else:
        draft["voice_note"] = "The page had too little text to draft voice notes from."
    draft["_url"] = fetched["url"]
    return draft


def _draft_view(draft: dict) -> dict:
    kit = KITS.normalize(draft)
    kit["id"], kit["version"] = "draft", 0
    pal = KITS.palette(kit)
    faces = F.resolve_kit(kit, None)
    return {"draft": {**kit, "found": draft.get("found"), "voice_note": draft.get("voice_note", "")}, "palette": pal,
            "faces": _face_view(faces), "substitutions": F.substitutions(faces)}


async def build_guided(params: dict) -> dict:
    fixed = params.get("fixed") or {}
    subject = params.get("subject") or {}
    refs = []
    for ref in (params.get("refs") or [])[:3]:
        if ref.get("kit_id"):
            try:
                k = KITS.get(ref["kit_id"])
                refs.append({"label": f"Kit {k['name']}", "summary": G.ref_summary_from_kit(k)})
            except KITS.KitError:
                continue
        elif ref.get("url"):
            try:
                v = await read_site(ref["url"])
                d = v["draft"]
                refs.append({"label": f"Website {ref['url']}", "summary": G.ref_summary_from_kit({**d, "id": "ref"})})
            except (I.Refused, ValueError) as e:
                refs.append({"label": f"Website {ref['url']}", "summary": f"could not be read ({e})"})
        elif ref.get("draft_id"):
            try:
                d = IM.view(ref["draft_id"])
                refs.append({"label": "Your logo or brand sheet", "summary": G.ref_summary_from_kit({**IM._preview_kit(d["kit"]), "id": "ref"})})
            except (IM.Refused, ValueError):
                continue
        elif ref.get("note"):
            refs.append({"label": "Described", "summary": str(ref["note"])[:400]})
    recent = KITS.repeats()
    raw = await model().structured(system=G.SYSTEM, instructions=G.instructions(recent),
                                   body=R.redact(G.body_text(fixed, subject, refs)), schema=G.SCHEMA,
                                   purpose="guide", max_tokens=5000, timeout=180)
    drafts = G.finish(raw, fixed, recent, subject)
    out = []
    for d in drafts:
        pal = KITS.palette(d["kit"])
        faces = F.resolve_kit(d["kit"], None)
        out.append({**d, "palette": pal, "faces": _face_view(faces), "substitutions": F.substitutions(faces)})
    return {"proposals": out, "references": refs, "recent": recent}


# ---------------------------------------------------------------- outputs --

def _output(output_id: str) -> dict:
    row = store.one("SELECT * FROM outputs WHERE id=?", (output_id,))
    if not row:
        raise ValueError("That output is gone. Make it again from your sources.")
    row["source_ids"] = store.loads(row["source_ids"], [])
    row["kit_ids"] = store.loads(row["kit_ids"], [])
    row["neutral"] = store.loads(row["neutral"])
    return row


def list_outputs(n: int = 20, thumbs: bool = False) -> list:
    rows = store.q("SELECT id, kind, title, source_ids, kit_ids, status, tokens_in, tokens_out, created_at FROM outputs ORDER BY created_at DESC LIMIT ?", (n,))
    sample = R.sample_open()
    for r in rows:
        r["source_ids"] = store.loads(r["source_ids"], [])
        r["kit_ids"] = store.loads(r["kit_ids"], [])
        r["building"] = r.get("status") != "ready"
        r["sample"] = sample
    if thumbs:
        for r, uri in zip(rows, _parallel([(thumb, (r,)) for r in rows])):
            r["thumb"] = uri
    return rows


def _store_render(output_id: str, kit: dict, doc: dict, reverted: Optional[list] = None, note: str = "") -> None:
    store.run("INSERT INTO renders(output_id, kit_id, kit_version, content, voice_note, decisions, created_at) VALUES(?,?,?,?,?,?,?) "
              "ON CONFLICT(output_id, kit_id) DO UPDATE SET kit_version=excluded.kit_version, content=excluded.content, "
              "voice_note=excluded.voice_note, created_at=excluded.created_at",
              (output_id, kit["id"], kit.get("version", 1), store.dumps({"doc": doc, "reverted": reverted or []}), note,
               store.dumps({}), store.now()))
    KITS.record_look(kit, K.kind_of(doc))


async def _voice(output_id: str, neutral: dict, kit: dict) -> dict:
    """The voice pass for one kit, checked against the neutral draft, and stored."""
    reverted: list = []
    voiced = neutral
    kind = K.kind_of(neutral)
    try:
        raw = await model(output_id).structured(
            system=K.SYSTEM, instructions=K.voice_instructions(kit), body=store.dumps(neutral),
            schema=K.schema_for(kind), purpose="voice", max_tokens=5000 if kind != "onepager" else 3000, timeout=170)
        voiced, reverted = K.keep_facts(neutral, raw)
        if kind == "deck" and neutral.get("from_outline"):
            for vs, ns in zip(voiced.get("slides") or [], neutral.get("slides") or []):
                for f in ("heading", "label") if ns.get("type") == "stat" else ("heading",):
                    if ns.get(f):
                        vs[f] = ns[f]  # an approved outline title stays word for word through the voice pass
    except R.ModelError as e:
        voiced, reverted = copy.deepcopy(neutral), ["all"]
        note = str(e)
    else:
        note = ""
    store.run("INSERT INTO renders(output_id, kit_id, kit_version, content, voice_note, decisions, created_at) VALUES(?,?,?,?,?,?,?) "
              "ON CONFLICT(output_id, kit_id) DO UPDATE SET kit_version=excluded.kit_version, content=excluded.content, "
              "voice_note=excluded.voice_note, created_at=excluded.created_at",
              (output_id, kit["id"], kit.get("version", 1), store.dumps({"doc": voiced, "reverted": reverted}), note,
               store.dumps({}), store.now()))
    KITS.record_look(kit, kind)
    return {"kit_id": kit["id"], "reverted": reverted}


@J.handler("make")
async def job_make(job_id: str, p: dict) -> dict:
    kind = p.get("kind") or "onepager"
    if kind not in K.READY_KINDS:
        raise J.JobError(f"{K.KINDS.get(kind, 'That output')} is coming. Make a one-pager for now.", "coming")
    source_ids = [s for s in p.get("source_ids") or []][:MAX_SOURCES_PER_OUTPUT]
    kit_ids = [k for k in p.get("kit_ids") or [] if k][:2]
    if not kit_ids:
        raise J.JobError("Choose a kit first.", "no_kit")
    kits = [KITS.get(k) for k in kit_ids]
    brief = (p.get("brief") or "").strip()[:1200] or K.DEFAULT_BRIEF.get(kind, K.DEFAULT_BRIEF["onepager"])
    corpus, srcs, by_ref = _corpus(source_ids)
    output_id = p.get("output_id") or store.new_id("o")
    t = store.now()
    store.run("INSERT OR IGNORE INTO outputs(id, kind, title, source_ids, brief, kit_ids, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
              (output_id, kind, "", store.dumps(source_ids), brief, store.dumps(kit_ids), "writing", t, t))
    store.set_setting(f"notes:{output_id}", [n for n in (p.get("note_ids") or []) if isinstance(n, str)][:20])
    outline = _outline_for(p.get("outline_id"), kind)
    try:
        return await _make_body(job_id, output_id, kind, kits, brief + notes_brief(p.get("note_ids") or []), corpus,
                                pictures=bool(p.get("pictures")), outline=outline, n_sources=len(srcs))
    except J.Stopped:
        _keep_stopped(output_id, kits)
        raise
    except BaseException:
        # A half-made output (no draft, or a kit never set) is no use to anyone and Retry makes a fresh one.
        try:
            delete_output(output_id)
        except Exception:
            pass
        raise


def _keep_stopped(output_id: str, kits: list) -> None:
    """Stop during a make: once the slides are written they are kept (a brand not set yet shows the plain wording);
    before that there is nothing to keep."""
    row = store.one("SELECT neutral FROM outputs WHERE id=?", (output_id,))
    neutral = store.loads((row or {}).get("neutral"))
    if not neutral:
        try:
            delete_output(output_id)
        except Exception:
            pass
        return
    for k in kits:
        store.run("INSERT OR IGNORE INTO renders(output_id, kit_id, kit_version, content, voice_note, decisions, created_at) VALUES(?,?,?,?,?,?,?)",
                  (output_id, k["id"], k.get("version", 1), store.dumps({"doc": neutral, "reverted": []}), "", store.dumps({}), store.now()))
    store.run("UPDATE outputs SET status='ready', updated_at=? WHERE id=?", (store.now(), output_id))
    store.record_made(output_id)


def _outline_for(outline_id, kind: str) -> Optional[dict]:
    """The saved outline a make job builds from, or ``None``. Only a deck is built from an outline."""
    if not outline_id:
        return None
    if kind != "deck":
        raise J.JobError("An outline builds a deck. Choose Deck, or make this without the outline.", "outline_kind")
    try:
        from . import revise as RV
    except ImportError:  # loaded loose
        import revise as RV  # type: ignore
    try:
        o = RV.get_outline(outline_id)
    except ValueError as e:
        raise J.JobError(str(e), "gone")
    if not o.get("slides"):
        raise J.JobError("That outline has no slides. Add one, then build it.", "gone")
    return o


def outline_schema(n: int) -> dict:
    sc = copy.deepcopy(K.DECK_SCHEMA)
    sc["properties"]["slides"]["minItems"] = n
    sc["properties"]["slides"]["maxItems"] = n
    sc["properties"]["slides"]["description"] = f"Exactly {n} slides, in the outline's order."
    return sc


def follow_outline(neutral: dict, outline: dict) -> dict:
    """The deck with exactly the outline's slides, in its order, with its titles. Each outline slide takes the written
    slide at its own place when the type matches, else the first unused one of its type, else the one at its place."""
    got = list(neutral.get("slides") or [])
    want = outline.get("slides") or []
    if len(got) < len(want):
        raise R.ModelError(R.CUT_OFF, "cut_off")
    used, out = set(), []
    for i, o in enumerate(want):
        j = i if i < len(got) and i not in used and got[i].get("type") == o.get("type") else None
        if j is None:
            j = next((k for k, sl in enumerate(got) if k not in used and sl.get("type") == o.get("type")), None)
        if j is None:
            j = i if i not in used else next(k for k in range(len(got)) if k not in used)
        used.add(j)
        sl = copy.deepcopy(got[j])
        title = K.one_claim(K.strip_period(o.get("title") or ""))
        if title and sl.get("type") == "stat":
            sl["label"] = title  # a stat's title is its label (content.apply_outline does the same)
        elif title and sl.get("type") != "quote":
            sl["heading"] = title
        sl["refs"] = list(dict.fromkeys((sl.get("refs") or []) + [r for r in (o.get("refs") or []) if r]))
        out.append(sl)
    return {**neutral, "slides": out}


def _passages_of(output_id: str) -> dict:
    row = store.one("SELECT source_ids FROM outputs WHERE id=?", (output_id,))
    return passages_for(store.loads((row or {}).get("source_ids")) or [])[2]


async def _repair(job_id: str, output_id: str, neutral: dict, outline: Optional[dict], corpus: str, case: str = "",
                  spine: bool = False) -> dict:
    """The deck's own faults, repaired once before the voice pass (P6 round 3): money figures of a budget or funding
    mix not shown on any slide, a number set big on two slides, sourced facts whose relation words drifted, and
    (round 5) a slide whose points cite none of the passages its outline title rests on. One
    model call gets the deck and the list; its answer is kept only when it has fewer faults and the same slides."""
    by_ref = _passages_of(output_id)
    found = CK.deck_problems(neutral, by_ref)
    if spine:  # a checked case is the spine: a budget figure the case left out is a choice, not a fault (round 11)
        found["money"] = []
    found["off_title"] = CK.off_title(neutral, outline)  # points that back none of the title's passages (round 5)
    found["unsourced"] = CK.unsourced(neutral, by_ref)  # numbers and quotes no source holds (round 6)
    found["case"] = CK.case_left_out(case, neutral, by_ref)  # evidence the pass's own case names but no slide shows
    found["filler"] = CK.filler(neutral, by_ref)  # points that say the title again (round 8)
    rebuild = {f["i"] for f in found["filler"] if f.get("rebuild")}
    n0 = CK.problem_count(found)
    if not n0:
        return CK.keep_qualifiers(CK.trim_repeats(neutral), by_ref)[0]
    J.step(job_id, f"Fixing {n0} thing{'s' if n0 != 1 else ''} the checks found")
    n = len(neutral.get("slides") or [])
    try:
        raw = await model(output_id).structured(system=K.SYSTEM, instructions=K.repair_instructions(found),
                                                body=corpus + "\n\nTHE DECK\n" + store.dumps(neutral),
                                                schema=outline_schema(n), purpose="repair", max_tokens=6000, timeout=220)
        fixed = K.clean_for("deck", raw)
    except (R.ModelError, ValueError):
        return CK.keep_qualifiers(CK.trim_repeats(neutral), by_ref)[0]
    if len(fixed.get("slides") or []) != n:
        return CK.keep_qualifiers(CK.trim_repeats(neutral), by_ref)[0]
    changed = [i for i, (a, b) in enumerate(zip(fixed["slides"], neutral["slides"])) if a.get("type") != b.get("type")]
    if any(i not in rebuild or fixed["slides"][i].get("type") not in ("figures", "exhibit", "stat") for i in changed):
        return CK.keep_qualifiers(CK.trim_repeats(neutral), by_ref)[0]
    if changed:  # a filler slide rebuilt as figures keeps its place and its approved title
        for i in changed:
            if fixed["slides"][i].get("type") != "stat":  # a stat says its title as its label
                fixed["slides"][i]["heading"] = neutral["slides"][i].get("heading", "")
            fixed["slides"][i]["refs"] = list(dict.fromkeys((fixed["slides"][i].get("refs") or []) + (neutral["slides"][i].get("refs") or [])))
        if outline:
            keep = {i: fixed["slides"][i] for i in changed}
            stub = copy.deepcopy(fixed)
            for i in changed:
                stub["slides"][i] = copy.deepcopy(neutral["slides"][i])
            fixed = follow_outline(stub, outline)
            for i, sl in keep.items():
                fixed["slides"][i] = sl
    elif outline:
        fixed = follow_outline(fixed, outline)
    for k in ("from_outline", "max_slides", "sources_page"):
        if k in neutral:
            fixed[k] = neutral[k]
    fixed["title"], fixed["subtitle"] = neutral.get("title", ""), neutral.get("subtitle", "")
    n1 = CK.problem_count({**CK.deck_problems(fixed, by_ref), **({"money": []} if spine else {}), "off_title": CK.off_title(fixed, outline),
                           "unsourced": CK.unsourced(fixed, by_ref), "case": CK.case_left_out(case, fixed, by_ref),
                           "filler": CK.filler(fixed, by_ref)})
    return CK.keep_qualifiers(CK.trim_repeats(fixed if n1 < n0 else neutral), by_ref)[0]


_LENGTH = re.compile(r"\b(\d{1,2})(?:\s*(?:to|-|\u2013|or)\s*(\d{1,2}))?[\s-]*slides?\b", re.I)


def length_cap(brief: str) -> Optional[int]:
    """The most slides a request names, title slide included: "A 7 to 9 slide funder deck" gives 9."""
    m = _LENGTH.search(brief or "")
    if not m:
        return None
    n = int(m.group(2) or m.group(1))
    return n if 3 <= n <= 30 else None


ARGUE = True  # round 11: a deck made with no approved outline is argued first (``_argue``), then laid out on that spine


async def _argue(job_id: str, output_id: str, brief: str, corpus: str) -> Optional[dict]:
    """The case before any slide (round 11): one call drafts it as a development director would (lead, steps in
    order, the reader's strongest objection and the sources' answer, the ask as the sources state it, and every
    instruction the notes give for the deck), code checks it against the sources (``checks.argument_problems``), and
    one repair call fixes what fails. Kept only when it holds or the repair has fewer faults. Returns the case with
    its ``faults`` (what still fails, for the record), or ``None`` when no usable case came back."""
    by_ref = _passages_of(output_id)
    cap = length_cap(brief)
    noted = CK.notes_length(by_ref)  # a length the notes give for this deck holds over the request's (round 11b)
    if noted and (not cap or noted < cap):
        cap = noted
    slides_max = (cap - 1) if cap else 0
    fixed_steps = 4 if K.ASK_SLIDE else 3  # lead, counter, closing (and the ask slide)
    sc = K.argument_schema(points_max=(slides_max - fixed_steps) if slides_max >= fixed_steps + 2 else 5)
    J.step(job_id, "Drafting the case")
    try:
        arg = await model(output_id).structured(system=K.SYSTEM, instructions=K.argument_instructions(brief, slides_max),
                                                body=corpus, schema=sc, purpose="argument", max_tokens=5000, timeout=240)
    except (R.ModelError, ValueError):
        return None
    if not isinstance(arg, dict) or not (arg.get("lead") or {}).get("heading") or not arg.get("points"):
        return None
    faults = CK.argument_problems(arg, by_ref)
    if faults:
        J.step(job_id, f"Fixing {len(faults)} thing{'s' if len(faults) != 1 else ''} in the case")
        try:
            fixed = await model(output_id).structured(system=K.SYSTEM, instructions=K.argument_repair_instructions(faults),
                                                      body=corpus + "\n\nTHE CASE\n" + store.dumps(arg), schema=sc,
                                                      purpose="argument_repair", max_tokens=5000, timeout=240)
            if isinstance(fixed, dict) and (fixed.get("lead") or {}).get("heading") and fixed.get("points"):
                f2 = CK.argument_problems(fixed, by_ref)
                if len(f2) < len(faults):
                    arg, faults = fixed, f2
        except (R.ModelError, ValueError):
            pass
    if slides_max and len(K.argument_steps(arg)) > slides_max:  # the request's length holds: drop the last points
        arg["points"] = arg["points"][:max(1, slides_max - len(K.argument_steps(arg)) + len(arg["points"]))]
    arg["faults"] = faults
    arg["slides_max"] = cap or 0  # title slide included
    store.set_setting(f"argument_of:{output_id}", store.dumps(arg))
    return arg


PLAIN = True  # round 13: a deck made with no approved outline starts from the plain one-pass draft (``_make_plain``)


def _plain_sources(by_ref: dict) -> list:
    """``[(name, text)]``: each source's passages in order, as plain text with no labels, the way a person pastes it."""
    order, texts = [], {}
    for ref in sorted(by_ref, key=lambda r: int(re.sub(r"\D", "", r) or 0)):
        p = by_ref[ref]
        name = p.get("source_title") or "Source"
        if name not in texts:
            order.append(name)
            texts[name] = []
        texts[name].append(p.get("text", ""))
    return [(n, R.redact("\n\n".join(texts[n]))) for n in order]


def plain_stage2(doc: dict, by_ref: dict, kit: dict, brief: str = "") -> tuple:
    """``(doc, flags, splits)``: the draft's doc traced (a number no source holds becomes a flagged blank), set by what
    its numbers are (``content.shape_plain``: figures, tables, bars, quotes), then split to fit on measured height."""
    g = CK.grounding(doc, by_ref, brief=brief)
    doc, flags = K.flag_unsupported(g["doc"], g["items"], by_ref)
    doc = K.shape_plain(doc)
    doc, splits = RD.split_to_fit(doc, kit, KITS.palette(kit), KITS.faces(kit), by_ref)
    return doc, flags, splits


SPEC = True  # loop 4: the model designs each slide (spec.py); Imprint brands, traces and checks it


def _spec_mod():
    try:
        from . import spec as SP
    except ImportError:  # loaded loose
        import spec as SP  # type: ignore
    return SP


def spec_cap(brief: str, slides: list) -> Optional[int]:
    """The most frames a designed deck may have: the request's length, and never more than the draft's own count
    (the draft already holds the notes' limit)."""
    caps = [c for c in (length_cap(brief or ""), len(slides) if slides else None) if c]
    return min(caps) if caps else None


def spec_doc(specs: list, slides: list, by_ref: dict, brief: str = "") -> dict:
    """The deck doc from the model's slide specs: the first is the cover, each element traced to its closest passage."""
    SP = _spec_mod()
    try:
        from . import revise as RV
    except ImportError:  # loaded loose
        import revise as RV  # type: ignore
    title = slides[0]["title"] if slides else ""
    doc = {"title": title, "subtitle": "", "slides": [], "plain": True, "spec": True}
    specs = [sp for sp in SP._list(specs) if isinstance(sp, dict) and any(SP.clean_el(e) for e in SP._list(sp.get("els")))]
    cap = spec_cap(brief, slides)
    if cap and len(specs) > cap:
        specs = specs[:cap - 1] + specs[-1:]  # the length holds (the cover counts); the closing ask is never the one cut
    for n, sp in enumerate(specs):
        els = [c for c in (SP.clean_el(e) for e in SP._list(sp.get("els"))[:SP.MAX_ELS]) if c]  # model output: typed here
        refs = []
        for e in els:
            words = " ".join(t for _s, t in SP.el_fields(e))
            if words and re.search(r"\w", words):
                r = K._best_ref(words, by_ref)
                if r:
                    e["ref"] = r
                    if r not in refs:
                        refs.append(r)
        heading = SP._text(sp.get("title")) or next((e["text"] for e in els if e.get("style") == "title" and e.get("text")), "") \
            or (slides[n]["title"] if n < len(slides) else "")
        sl = {"type": "spec", "heading": heading, "els": els, "refs": refs, "ground": SP._word(sp.get("ground")) or "paper",
              "footer": sp.get("footer", n > 0) is not False}
        if n == 0:
            doc["cover"] = {**sl, "ground": SP._word(sp.get("ground")) or "primary", "footer": False}
            doc["title"] = heading or title
        else:
            doc["slides"].append(sl)
    return doc


def spec_problems(doc: dict, kit: dict, by_ref: dict) -> dict:
    """``{frame: [problem]}``: what the measured slides still get wrong (frame 0 is the cover)."""
    idx, rows = L.source_index(doc, by_ref)
    scs, _ty = RD.scenes(doc, kit, KITS.palette(kit), KITS.faces(kit), idx, rows, "", by_ref)
    return {i: sc["problems"] for i, sc in enumerate(scs) if sc.get("problems")}


async def _spec_design(job_id: str, output_id: str, by_ref: dict, draft: str, slides: list, kit: dict, brief: str):
    """Loop 4 stage: one call designs every slide as a spec in brand roles; each slide the measure finds broken goes
    back to the model once, alone. Then every number and quote is traced, and one no source holds becomes a flagged
    blank. ``(doc, flags, record)`` or ``None`` (the caller keeps the shaped draft)."""
    SP = _spec_mod()
    J.step(job_id, "Designing each slide")
    try:
        raw = await model(output_id).structured(system=SP.SPEC_SYSTEM, instructions="",
                                                body=SP.spec_prompt(_plain_sources(by_ref), draft, SP.brand_line(kit)),
                                                schema=SP.SPEC_SCHEMA, purpose="spec_design", max_tokens=20000, timeout=600)
    except (R.ModelError, ValueError):
        return None
    specs = SP._list(raw.get("slides")) if isinstance(raw, dict) else []
    cap = spec_cap(brief, slides)
    if cap and len([s for s in specs if isinstance(s, dict) and SP._list(s.get("els"))]) > cap:
        try:  # once: the same design held to the length, never a slide silently cut
            raw2 = await model(output_id).structured(
                system=SP.SPEC_SYSTEM, instructions="", schema=SP.SPEC_SCHEMA, purpose="spec_design", max_tokens=20000, timeout=600,
                body=SP.spec_prompt(_plain_sources(by_ref), draft, SP.brand_line(kit)) + f"\n\nThe deck must have at most {cap} slides, the cover included.")
            s2 = SP._list(raw2.get("slides")) if isinstance(raw2, dict) else []
            if 2 <= len([s for s in s2 if isinstance(s, dict) and SP._list(s.get("els"))]) <= cap:
                specs = s2
        except (R.ModelError, ValueError):
            pass
    if len([s for s in specs if isinstance(s, dict) and SP._list(s.get("els"))]) < 2:
        return None
    doc = spec_doc(specs, slides, by_ref, brief)
    probs = spec_problems(doc, kit, by_ref)
    record = {"slides": 1 + len(doc["slides"]), "problems": {str(k): v for k, v in probs.items()}, "fixed": []}
    if probs:
        J.step(job_id, f"Fixing {len(probs)} slide{'s' if len(probs) != 1 else ''} that did not fit")

        async def fix(frame, plist):
            sl = doc["cover"] if frame == 0 else doc["slides"][frame - 1]
            ask = {k: sl.get(k) for k in ("ground", "footer")}
            ask["title"] = sl.get("heading", "")
            ask["els"] = [{k: v for k, v in e.items() if k != "ref"} for e in sl["els"]]
            try:
                r = await model(output_id).structured(system=SP.SPEC_SYSTEM, instructions="", body=SP.fix_prompt(ask, plist),
                                                      schema=SP.FIX_SCHEMA, purpose="spec_fix", max_tokens=8000, timeout=300)
            except (R.ModelError, ValueError):
                return frame, None
            return frame, r if isinstance(r, dict) and SP._list(r.get("els")) else None

        got = await asyncio.gather(*(fix(f, p) for f, p in probs.items()))
        for frame, new in got:
            if not new:
                continue
            trial = copy.deepcopy(doc)
            one = spec_doc([new, new] if frame else [new, {"els": [{"type": "text", "text": ""}]}], [], by_ref)
            if (frame == 0 and "cover" not in one) or (frame and not one["slides"]):
                continue  # the fix came back with nothing drawable; the first design stands
                trial["cover"] = one["cover"]
            else:
                trial["slides"][frame - 1] = {**one["slides"][0], "footer": new.get("footer", True) is not False}
            before = len(probs.get(frame) or [])
            after = len(spec_problems(trial, kit, by_ref).get(frame) or [])
            if after < before:
                doc = trial
                record["fixed"].append({"frame": frame, "before": before, "after": after})
        record["left"] = {str(k): v for k, v in spec_problems(doc, kit, by_ref).items()}
    g = CK.grounding(doc, by_ref, brief=brief)
    doc, flags = K.flag_unsupported(g["doc"], g["items"], by_ref)
    record["dropped_numbers"] = SP.words_kept(slides, [doc["cover"]] + doc["slides"])
    return doc, flags, record


async def _make_plain(job_id: str, output_id: str, kits: list, brief: str) -> dict:
    """Round 13. Stage 1: one unconstrained call drafts the deck exactly as the bench's plain prompt does (its system
    framing, its words, the sources as plain text), with the slides as plain text instead of python-pptx code. The raw
    draft is kept. Stage 2, all in code, none of it rewording: the draft mapped onto the doc line for line (checked to
    hold every line verbatim, in order; one retry otherwise), every number and quote traced, what the sources do not
    hold turned into a flagged blank, the brand, slides split (never trimmed) to fit, and the titles saved as the
    outline the person can edit."""
    by_ref = _passages_of(output_id)
    prompt = K.plain_prompt(_plain_sources(by_ref), brief)
    J.step(job_id, "Drafting the deck")
    slides, draft = [], ""
    for attempt in range(2):
        try:
            raw = await model(output_id).structured(system=K.PLAIN_SYSTEM, instructions="", body=prompt, schema=K.PLAIN_SCHEMA,
                                                    purpose="plain_draft", max_tokens=12000, timeout=420)
        except (R.ModelError, ValueError):
            if attempt:
                raise
            continue
        draft = (raw or {}).get("draft") or ""
        slides = K.parse_plain(draft)
        if len(slides) >= 2:
            doc = K.plain_doc(slides, by_ref)
            if K.keeps_draft(doc, slides):
                break
        slides = []
    if not slides:
        raise R.ModelError(R.CUT_OFF, "cut_off")
    store.set_setting(f"plain_draft_of:{output_id}", draft)
    J.step(job_id, f"Checking {_count_numbers(doc)} numbers against your sources")
    kit = kits[0]
    designed = await _spec_design(job_id, output_id, by_ref, draft, slides, kit, brief) if SPEC else None
    if designed:
        sdoc, flags, rec = designed
        outline_doc = doc
        doc, splits = sdoc, []
        store.set_setting(f"spec_record_of:{output_id}", store.dumps(rec))
    else:
        J.step(job_id, "Setting it in " + kit["name"])
        doc, flags, splits = plain_stage2(doc, by_ref, kit, brief)
        outline_doc = doc
    store.set_setting(f"plain_record_of:{output_id}", store.dumps({"flags": flags, "splits": splits, "slides": len(slides),
                                                                    "spec": bool(designed)}))
    try:
        from . import revise as RV
    except ImportError:  # loaded loose
        import revise as RV  # type: ignore
    try:
        row = store.one("SELECT source_ids FROM outputs WHERE id=?", (output_id,)) or {}
        sids = store.loads(row.get("source_ids")) or []
        import secrets
        oid = "ol_" + secrets.token_hex(6)
        o_slides = [c for c in (RV.clean_outline_slide(s, by_ref, set(by_ref), sids) for s in K.plain_outline(outline_doc)) if c]
        store.set_setting(f"outline:{oid}", {"outline_id": oid, "source_ids": sids, "brief": {"what": brief}, "slides": o_slides,
                                             "warnings": [], "created_at": store.now(), "updated_at": store.now()})
        store.set_setting(f"outline_of:{output_id}", oid)
    except Exception:  # the outline is a convenience: the deck stands without it
        pass
    store.run("UPDATE outputs SET title=?, neutral=?, status='voicing', updated_at=? WHERE id=?",
              (doc.get("title") or "", store.dumps(doc), store.now(), output_id))
    for k in kits:  # the draft's words in every brand: no voice pass rewords it
        _store_render(output_id, k, doc)
    store.run("UPDATE outputs SET status='ready', updated_at=? WHERE id=?", (store.now(), output_id))
    store.record_made(output_id)
    return {"output_id": output_id, "plain": {"flags": flags, "splits": splits}}


async def _make_body(job_id: str, output_id: str, kind: str, kits: list, brief: str, corpus: str, pictures: bool = False,
                     outline: Optional[dict] = None, n_sources: int = 0) -> dict:
    if kind == "deck" and not outline and PLAIN:
        return await _make_plain(job_id, output_id, kits, brief)
    n = len((outline or {}).get("slides") or [])
    if n_sources:
        J.step(job_id, f"Reading {n_sources} source{'s' if n_sources != 1 else ''}")
    argument = None
    if kind == "deck" and not outline and ARGUE:
        argument = await _argue(job_id, output_id, brief, corpus)
        if argument:
            cap = argument.get("slides_max") or length_cap(brief)
            outline = K.argument_outline(argument, f"{cap} slides" if cap else "")
            n = len(outline["slides"])
    J.step(job_id, f"Writing {n + 1} slides from your outline" if outline and not argument
           else f"Writing {n + 1} slides from the case" if argument else "Writing from your sources")  # the title slide counts
    if kind == "deck":
        # Round 6: one pass with every source in view plans the case and writes every slide in the first brand's
        # voice; the outline, when the person approved one, is its spine. Round 11: with no outline, the checked case
        # is the spine. Code does the rest (shape, brand, checks).
        instructions = K.onepass_instructions(brief, None if argument else outline, kits[0] if kits else None, argument)
        schema = (K.onepass_schema(n, pictures=pictures) if outline
                  else K.onepass_schema(cap_after_title=(length_cap(brief) or 0) - 1, pictures=pictures))
    else:
        instructions = K.instructions_for(kind, brief, outline=outline) if outline else K.instructions_for(kind, brief)
        schema = outline_schema(n) if outline else K.schema_for(kind)
    raw = await model(output_id).structured(system=K.SYSTEM, instructions=instructions, body=corpus, schema=schema,
                                            purpose="write", max_tokens=4000 if kind == "onepager" else 8000,
                                            timeout=220 if kind != "deck" else 300)
    try:
        neutral = K.clean_for(kind, raw)
    except ValueError:
        raise R.ModelError(R.CUT_OFF, "cut_off")
    if kind == "deck" and isinstance(raw, dict) and isinstance(raw.get("case"), str):
        store.set_setting(f"case_of:{output_id}", raw["case"][:1200])  # the pass's own plan, kept for the record
    if kind == "deck" and K.asks_for_sources(" ".join([brief or "", str((outline or {}).get("brief") or "")])):
        neutral["sources_page"] = True  # only when asked: otherwise sources sit in each slide's foot and the notes
    if kind == "deck" and not outline:
        cap = length_cap(brief)
        if cap:
            neutral["max_slides"] = cap  # a length the request names holds, the Sources page included
    if outline:
        neutral = follow_outline(neutral, outline)
        neutral["from_outline"] = True  # the voice pass keeps the approved titles (P6 round 2)
        try:
            from . import revise as RV
        except ImportError:  # loaded loose
            import revise as RV  # type: ignore
        cap = RV.max_slides(outline.get("brief"))
        if cap:
            neutral["max_slides"] = cap  # the person's length: the Sources page counts toward it (render_deck.slides)
        if outline.get("outline_id"):
            store.set_setting(f"outline_of:{output_id}", outline.get("outline_id"))
    if kind == "deck":
        case = K.argument_text(argument) if argument else (
            raw.get("case") if isinstance(raw, dict) and isinstance(raw.get("case"), str) else "")
        neutral = await _repair(job_id, output_id, neutral, outline, corpus, case, spine=bool(argument))
        if argument:
            neutral = K.fit_closing(neutral)
    J.step(job_id, f"Checking {_count_numbers(neutral)} numbers against your sources")
    store.run("UPDATE outputs SET title=?, neutral=?, status='voicing', updated_at=? WHERE id=?",
              (neutral.get("title") or neutral.get("headline") or "", store.dumps(neutral), store.now(), output_id))
    if kind == "deck" and pictures:
        await _make_pictures(job_id, output_id, neutral)
    J.step(job_id, "Setting it in " + " and ".join(k["name"] for k in kits))
    if kind == "deck":  # the one pass wrote in the first brand's voice; a second brand gets its own voice pass
        _store_render(output_id, kits[0], neutral)
        await asyncio.gather(*[_voice(output_id, neutral, k) for k in kits[1:]])
    else:
        await asyncio.gather(*[_voice(output_id, neutral, k) for k in kits])
    if kind == "audio":
        for k in kits:
            J.step(job_id, f"Recording it in {k['name']}'s voice")
            await speak(output_id, k)
    store.run("UPDATE outputs SET status='ready', updated_at=? WHERE id=?", (store.now(), output_id))
    store.record_made(output_id)
    return {"output_id": output_id, **({"argument": {k: v for k, v in argument.items() if k not in ("faults", "slides_max")}} if argument else {})}


# ---------------------------------------------------------------- pictures --
# An image slide asks the person's own Hermes image tool (``image_generate``) for one photograph from the
# slide's description. The picture is decoration behind a sourced line, never a fact. When the tool isn't set
# up, or answers with anything that isn't a plain image, the slide is set as a type-only statement instead and
# a check says so.

PICTURE_TIMEOUT = 150.0
MAX_PICTURE = 20 * 1024 * 1024
MAX_PICTURES = 2


def _picture_bytes(res) -> Optional[bytes]:
    """The image the tool made, read only from where Hermes keeps generated images (its cache folder) or from a
    public https address through the same safe client every web read uses."""
    img = res.get("image") if isinstance(res, dict) else None
    if not isinstance(img, str) or not img:
        return None
    if img.startswith("https://"):
        try:
            got = asyncio.run(I.fetch(img, max_bytes=MAX_PICTURE, accept="image/*"))
        except I.Refused:
            return None
        return got.get("raw") if got.get("status", 0) < 400 else None
    try:
        home = store.root().resolve().parents[1]
        p = Path(img).resolve()
    except (OSError, IndexError):
        return None
    if not p.is_absolute() or not p.is_file() or (home / "cache") not in p.parents:
        return None
    if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or p.stat().st_size > MAX_PICTURE:
        return None
    return p.read_bytes()


def picture_prompt(text: str) -> str:
    """The picture's description as the image tool gets it: words only. Web addresses, email addresses, long codes
    and digits are taken out, so nothing a hostile source slipped into the model's prompt can ride along to the
    person's image provider."""
    t = re.sub(r"(?i)\b(?:https?://|www\.)\S+", " ", text or "")
    t = re.sub(r"\S+@\S+", " ", t)
    t = re.sub(r"\b[A-Za-z0-9_\-]{20,}\b", " ", t)
    t = re.sub(r"[^A-Za-z ,.'\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:400]


def clean_picture(data: bytes) -> Optional[bytes]:
    """A plain JPEG (at most 1920 wide, no metadata) from a PNG, JPEG or WebP, or ``None`` for anything else."""
    import io
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.format not in ("PNG", "JPEG", "WEBP") or im.width * im.height > 40_000_000:
            return None
        im.load()
        im = im.convert("RGB")
        if im.width > 1920:
            im = im.resize((1920, round(im.height * 1920 / im.width)), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=86, optimize=True)
        return out.getvalue()
    except Exception:
        return None


async def _make_pictures(job_id: str, output_id: str, neutral: dict) -> None:
    asks = [(i, sl) for i, sl in enumerate(neutral.get("slides") or []) if sl.get("type") == "image" and sl.get("prompt")][:MAX_PICTURES]
    if not asks:
        return
    folder = store.root() / "outputs" / output_id
    folder.mkdir(parents=True, exist_ok=True)
    made, missed = 0, 0
    for n, (i, sl) in enumerate(asks, start=1):
        J.step(job_id, "Asking your image tool for a picture" + (f" ({n} of {len(asks)})" if len(asks) > 1 else ""))
        prompt = (picture_prompt(sl["prompt"]) + " Photograph, natural light, no text, no lettering, no logos, no watermark.")[:600]
        try:
            res = await asyncio.to_thread(R.dispatch_bounded, "image_generate", {"prompt": prompt, "aspect_ratio": "landscape"}, PICTURE_TIMEOUT)
            raw = await asyncio.to_thread(_picture_bytes, res)
            data = clean_picture(raw) if raw else None
        except R.ToolUnavailable:
            data = None
        if not data:
            missed += 1
            continue
        name = f"picture-{i + 1}.jpg"
        store.write_bytes(folder / name, data)
        sl["picture"] = name
        made += 1
    store.set_setting(f"pictures:{output_id}", {"made": made, "missed": missed})
    store.run("UPDATE outputs SET neutral=?, updated_at=? WHERE id=?", (store.dumps(neutral), store.now(), output_id))


def _picture_urls(output_id: str, doc: dict) -> dict:
    """The slides' pictures as small JPEG data URLs for the pane (the exports use the full files)."""
    import base64
    import io
    out = {}
    for sl in doc.get("slides") or []:
        name = sl.get("picture")
        data = picture_data(output_id, name) if name else None
        if not data:
            continue
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert("RGB")
            if im.width > 1100:
                im = im.resize((1100, round(im.height * 1100 / im.width)), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=80)
            out[name] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            continue
    return out


def _pictures(output_id: str, doc: dict) -> dict:
    return {sl["picture"]: d for sl in doc.get("slides") or [] if sl.get("picture")
            for d in [picture_data(output_id, sl["picture"])] if d}


def picture_data(output_id: str, name: str) -> Optional[bytes]:
    if not re.fullmatch(r"picture-\d{1,2}\.jpg", name or ""):
        return None
    p = store.root() / "outputs" / output_id / name
    return p.read_bytes() if p.is_file() else None


# ---------------------------------------------------------------- audio --

NO_VOICE = ("Imprint couldn't record this: your Hermes voice isn't set up here. Turn on text to speech in Hermes "
            "Settings, then press Record again. The script is ready to read or export now.")
VOICE_FAILED = "Your Hermes voice didn't finish the recording. Press Record again, or export the script."
VOICE_SLOW = "Your Hermes voice took too long to answer, so Imprint stopped waiting. Press Record again, or export the script."
TTS_TIMEOUT = 300.0
AUDIO_EXT = {".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".opus": "audio/ogg", ".wav": "audio/wav", ".m4a": "audio/mp4",
             ".aac": "audio/aac", ".flac": "audio/flac"}
MAX_AUDIO = 60 * 1024 * 1024


def audio_state(output_id: str, kit_id: str) -> dict:
    return store.get_setting(f"audio:{output_id}:{kit_id}", {}) or {}


def _gather_audio(paths: list, folder: Path, base: str) -> Path:
    """The recording as one file in the output's folder. MP3 parts are joined frame to frame; other formats
    keep their first part (Hermes joins its own chunks when it can)."""
    good = []
    for p in paths:
        try:
            q = Path(str(p))
        except TypeError:
            continue
        if q.is_file() and q.suffix.lower() in AUDIO_EXT and 0 < q.stat().st_size <= MAX_AUDIO:
            good.append(q)
    if not good:
        raise R.ToolUnavailable("no audio file came back")
    ext = good[0].suffix.lower()
    dest = folder / f"{base}{ext}"
    if len(good) > 1 and ext == ".mp3" and all(g.suffix.lower() == ".mp3" for g in good):
        store.write_bytes(dest, b"".join(g.read_bytes() for g in good))
    elif good[0].resolve() != dest.resolve():
        store.write_bytes(dest, good[0].read_bytes())  # through the one write path, so it stays in the data folder
    return dest


async def speak(output_id: str, kit: dict) -> dict:
    """Record one kit's script through the user's own Hermes voice. Never raises: the outcome is stored."""
    key = f"audio:{output_id}:{kit['id']}"
    try:
        doc = _doc_for(output_id, kit)
    except ValueError as e:
        store.set_setting(key, {"status": "failed", "error": str(e)})
        return audio_state(output_id, kit["id"])
    text = K.script_text(doc)
    folder = store.root() / "outputs" / output_id
    folder.mkdir(parents=True, exist_ok=True)
    base = f"audio-brief-{_slug(kit['name'])}"
    args = {"text": text, "output_path": str(folder / f"{base}-take.mp3"), "instructions": K.delivery_for(kit)}
    store.set_setting(key, {"status": "recording"})

    async def tts(a: dict):
        # A voice that never answers must not hold the job open: give up after TTS_TIMEOUT and say so.
        return await asyncio.to_thread(R.dispatch_bounded, "text_to_speech", a, TTS_TIMEOUT)

    try:
        try:
            res = await tts(args)
        except R.ToolUnavailable as e:
            if "denied" not in str(e).lower() and "output_path" not in str(e).lower():
                raise
            res = await tts({k: v for k, v in args.items() if k != "output_path"})
        paths = (res.get("file_paths") if isinstance(res, dict) else None) or [res.get("file_path") if isinstance(res, dict) else None]
        dest = await asyncio.to_thread(_gather_audio, [p for p in paths if p], folder, base)
    except R.ToolUnavailable as e:
        low = str(e).lower()
        msg = VOICE_SLOW if low == "timed out" else NO_VOICE if (
            "unknown tool" in low or "not available" in low or "not configured" in low or "no tts" in low
            or "text_to_speech failed" in low or "requirements" in low) else VOICE_FAILED
        _log_audio(e)
        store.set_setting(key, {"status": "failed", "error": msg, "code": "no_voice" if msg == NO_VOICE else "voice_failed"})
        return audio_state(output_id, kit["id"])
    for tmp in folder.glob(f"{base}-take*"):
        if tmp.resolve() != dest.resolve():
            try:
                tmp.unlink()
            except OSError:
                pass
    store.set_setting(key, {"status": "ready", "file": dest.name, "mime": AUDIO_EXT.get(dest.suffix.lower(), "audio/mpeg"),
                            "bytes": dest.stat().st_size, "words": len(re.findall(r"\w+", text)),
                            "kit_version": kit.get("version", 1), "at": store.now()})
    return audio_state(output_id, kit["id"])


def _log_audio(e: BaseException) -> None:
    import logging
    logging.getLogger("hermes.plugins.imprint").warning("imprint: recording failed: %s", str(e)[:300])


def audio_file(output_id: str, kit_id: str) -> dict:
    """The recording's bytes for the pane's player, as base64 (the pane makes a Blob URL from it)."""
    import base64
    st = audio_state(output_id, kit_id)
    if st.get("status") != "ready":
        raise ValueError("There is no recording for this kit yet.")
    p = store.root() / "outputs" / output_id / st["file"]
    if not p.is_file():
        raise ValueError("The recording is gone. Press Record again.")
    data = p.read_bytes()
    return {"mime": st.get("mime") or "audio/mpeg", "bytes": len(data), "data": base64.b64encode(data).decode("ascii")}


@J.handler("speak")
async def job_speak(job_id: str, p: dict) -> dict:
    out = _output(p["output_id"])
    if out.get("kind") != "audio":
        raise J.JobError("Only an audio brief can be recorded.", "not_audio")
    kit = KITS.get(p["kit_id"])
    J.step(job_id, f"Recording it in {kit['name']}'s voice")
    st = await speak(out["id"], kit)
    if st.get("status") != "ready":
        raise J.JobError(st.get("error") or VOICE_FAILED, st.get("code") or "voice_failed")
    return {"output_id": out["id"], "audio": st}


@J.handler("voice")
async def job_voice(job_id: str, p: dict) -> dict:
    out = _output(p["output_id"])
    if not out.get("neutral"):
        raise J.JobError("That output has no draft yet. Make it again.", "no_draft")
    kit = KITS.get(p["kit_id"])
    J.step(job_id, f"Setting it in {kit['name']}")
    res = await _voice(out["id"], out["neutral"], kit)
    kit_ids = out["kit_ids"]
    slot = int(p.get("slot", 1))
    while len(kit_ids) <= slot:
        kit_ids.append(kit["id"])
    kit_ids[slot] = kit["id"]
    store.run("UPDATE outputs SET kit_ids=?, updated_at=? WHERE id=?", (store.dumps(kit_ids[:2]), store.now(), out["id"]))
    return {"output_id": out["id"], **res}


@J.handler("read_file")
def job_read_file(job_id: str, p: dict) -> dict:
    path = store.root() / "uploads" / p["upload"]
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise J.JobError("The upload is gone. Add the file again.", "gone")
    J.step(job_id, f"Reading {p.get('filename', 'the file')}")
    try:
        row = read_file(p.get("filename") or "file", data)
        summarize_soon(row)
        return {"source": row}
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@J.handler("read_url")
async def job_read_url(job_id: str, p: dict) -> dict:
    J.step(job_id, "Reading the page")
    row = await read_url(p["url"])
    summarize_soon(row)
    return {"source": row}


@J.handler("site_kit")
async def job_site_kit(job_id: str, p: dict) -> dict:
    J.step(job_id, "Reading the site's colors and fonts")
    raw = await read_site_raw(p["url"])
    did = IM.from_site_draft(raw, raw.get("_url") or p["url"])
    brief, note = await _site_style_brief(job_id, raw.get("_url") or p["url"])
    if brief or note:
        data = IM._row(did)
        if brief:
            data["kit"]["style_brief"] = brief
        if note:
            data.setdefault("warnings", []).append(note)
        store.run("UPDATE kit_drafts SET data=? WHERE id=?", (store.dumps(data), did))
    return {"draft": import_view(did)}


@J.handler("kit_style_brief")
async def job_kit_style_brief(job_id: str, p: dict) -> dict:
    """Capture a site's look for a kit you already have: its style brief is added to the kit (colors and fonts stay as they are)."""
    kit = KITS.get(p["kit_id"])
    url = I.normalize_url(p["url"])
    brief, note = await _site_style_brief(job_id, url)
    if not brief:
        raise J.JobError(note or "The style brief could not be made.", "failed")
    KITS.update(kit["id"], {"style_brief": brief})
    return {"kit": kit_view(kit["id"])}


async def _site_style_brief(job_id: str, url: str) -> tuple:
    """``(brief, note)``: the site opened in headless Chrome, a few pages photographed and measured, the model's brief of what it
    looks like. Any failure leaves the colors and fonts as they were and says why in one plain sentence (``note``)."""
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="imprint-sitestyle-"))
    try:
        J.step(job_id, "Opening the site in a browser to see how it looks")
        cap = await asyncio.get_event_loop().run_in_executor(None, lambda: SST.capture(url, work))
        brief = await SST.write_brief(model(), cap, url, step=lambda t: J.step(job_id, t))
        return brief, ""
    except (ValueError, R.ModelError) as e:
        return None, "The style brief was left out: " + str(e)
    except Exception:
        return None, "The style brief was left out: the site could not be photographed. The colors and fonts were still read."
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- import --

SAMPLE_PAGE = {
    "title": "Riverside readers logged 18,400 hours this summer",
    "dek": "The library's summer reading program reached every branch for the first time, and more teens finished than ever.",
    "dek_refs": [], "stat": {"value": "18,400", "label": "reading hours logged from June 2 to August 15", "ref": ""},
    "sections": [
        {"heading": "Who took part", "body": "Families signed up at all six branches. Teens made up a third of finishers, up from a fifth last year.", "refs": []},
        {"heading": "What it cost", "body": "Books and prizes came to $21,300, most of it from the Friends of the Library.", "refs": []},
        {"heading": "What changes next year", "body": "Branches will add evening hours in July and a reading log that works on a phone.", "refs": []}],
    "points": [{"text": "1,920 readers signed up", "ref": ""}, {"text": "6 branches took part", "ref": ""}],
    "quote": None, "next": "The board reviews next summer's plan in March.",
}


SAMPLE_DECK = {
    "title": "Summer reading reached every branch",
    "subtitle": "A season review for the library board",
    "slides": [
        {"type": "section", "heading": "What the summer did", "subtitle": "June 2 to August 15, six branches", "refs": []},
        {"type": "exhibit", "heading": "Teens finished at every branch, and most at Eastside", "unit": "Teens who finished, by branch",
         "bars": [{"label": "Eastside", "value": "212", "ref": ""}, {"label": "Main", "value": "164", "ref": ""},
                  {"label": "Riverview", "value": "98", "ref": ""}, {"label": "Northgate", "value": "71", "ref": ""}], "refs": []},
        {"type": "stat", "value": "18,400", "label": "reading hours logged", "context": "Up from 12,900 last summer.", "refs": []},
        {"type": "timeline", "heading": "The season, start to finish", "refs": [],
         "steps": [{"when": "June 2", "text": "Sign-ups open at six branches", "ref": ""}, {"when": "July 1", "text": "Evening hours begin", "ref": ""},
                   {"when": "August 15", "text": "Logs close and prizes go out", "ref": ""}]},
        {"type": "quote", "quote": "My son read more this summer than all of last year.", "who": "A parent at Eastside", "refs": []},
        {"type": "closing", "heading": "What the board decides", "text": "Evening hours in July at every branch.", "cta": "Vote at the March meeting", "refs": []},
    ],
}

SAMPLE_VISUAL = {
    "kicker": "Summer reading", "headline": "Eastside's teens finished more than any other branch",
    "dek": "Teens who finished the summer reading program, by branch, June 2 to August 15.", "dek_refs": [], "form": "bars",
    "unit": "Teens who finished", "items": SAMPLE_DECK["slides"][1]["bars"], "steps": [],
    "takeaway": "Evening hours drew the most teens, so the board is asked to add them everywhere.", "takeaway_refs": [],
}


def specimen(raw: dict) -> dict:
    """A kit's real compositions on a built-in sample: the title, an exhibit, a big number, a timeline, a quote and the
    closing slide, and its graphic, as pane nodes. For the kit library and the bench, so a kit is judged by what it
    makes, not by a swatch."""
    if raw.get("kit_id"):
        kit = KITS.get(raw["kit_id"])
    else:
        kit = KITS.normalize(raw.get("kit") if isinstance(raw.get("kit"), dict) else {})
        kit["id"], kit["version"] = "draft", 0
    pal, faces = KITS.palette(kit), F.resolve_kit(kit, KITS.kit_dir(kit["id"]) if kit.get("id") not in ("draft", None) else None)
    sample = {**kit, "rules": {**kit["rules"], "sources": False}}
    logo = logo_srcs(kit, pal)[0] if kit.get("id") != "draft" else None
    tree, _scs = RD.deck_tree(SAMPLE_DECK, sample, pal, faces, {}, nice_date(), logo_urls=logo, idx={}, rows=[])
    which = [0, 2, 3, 4, 5, 6] if raw.get("all") else [0, 2]
    slides = [tree["k"][i] for i in which if i < len(tree["k"])]
    gtree, _g = RG.tree(SAMPLE_VISUAL, sample, pal, faces, {}, {}, logo_urls=logo) if raw.get("all") else (None, None)
    return {"slides": slides, "graphic": gtree, "system": RD.system_of(kit), "fonts": sorted({f["key"] for f in faces.values() if f.get("key")})}


def _sample() -> tuple:
    """The page a draft kit is proofed on: the person's latest one-pager draft, or a built-in sample."""
    row = store.one("SELECT id, neutral, source_ids, created_at FROM outputs WHERE kind='onepager' AND neutral IS NOT NULL ORDER BY created_at DESC LIMIT 1")
    if row:
        doc = store.loads(row["neutral"])
        if isinstance(doc, dict) and doc.get("sections"):
            _s, _b, by_ref = passages_for(store.loads(row["source_ids"], []) or [])
            return doc, by_ref, nice_date(row.get("created_at"))
    return SAMPLE_PAGE, {}, nice_date()


def import_view(draft_id: str) -> dict:
    return IM.view(draft_id, sample=_sample())


def import_read(kind: str, text: str = "", files: Optional[dict] = None, mode: str = "", filename: str = "", data: bytes = b"") -> dict:
    fd = IM.read(kind, text=text, files=files, mode=mode, filename=filename, data=data)
    return import_view(IM.create(fd))


def import_save(draft_id: str) -> dict:
    kit = IM.save(draft_id)
    KITS.record_look(kit, "kit")
    return kit_view(kit["id"])


IMAGE_NO_VISION = ("Your model couldn't read the image. Pick a model that can see images in Hermes Settings, "
                   "or paste your color codes instead.")


@J.handler("image_kit")
async def job_image_kit(job_id: str, p: dict) -> dict:
    path = store.root() / "uploads" / p["upload"]
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        raise J.JobError("The upload is gone. Add the image again.", "gone")
    try:
        name = p.get("filename") or "image.png"
        why = IM.image_problem(name, data)
        if why:
            raise J.JobError(why, "bad_image")
        J.step(job_id, "Your model is reading the image")
        try:
            raw = await model().structured(system=K.SYSTEM, instructions=IM.IMAGE_RULES,
                                           body="The image is attached. Read its brand look.", schema=IM.IMAGE_SCHEMA,
                                           purpose="image_kit", max_tokens=1200, timeout=120,
                                           images=[{"type": "image", "data": data, "mime_type": IM.image_mime(name), "file_name": name}])
        except R.ModelError as e:
            if e.code in ("no_model", "cut_off"):
                raise J.JobError(IMAGE_NO_VISION, "no_vision")
            raise
        return {"draft": import_view(IM.create(IM.image_found(raw, name, data)))}
    finally:
        try:
            path.unlink()
        except OSError:
            pass


@J.handler("guide")
async def job_guide(job_id: str, p: dict) -> dict:
    J.step(job_id, "Drafting three kits")
    return await build_guided(p)


@J.handler("ask")
async def job_ask(job_id: str, p: dict) -> dict:
    q = (p.get("question") or "").strip()
    if not q:
        raise J.JobError("Type a question first.", "empty")
    corpus, srcs, by_ref, shown = _corpus(p.get("source_ids") or [], with_ids=True)
    history = store.q("SELECT role, content FROM chats ORDER BY id DESC LIMIT 6")[::-1]
    convo = "\n".join(f"{'Person' if h['role'] == 'user' else 'You'}: {h['content'][:1500]}" for h in history)
    body = f"{corpus}\n\nCONVERSATION SO FAR:\n{convo or '(none)'}\n\nQUESTION: {R.redact(q[:2000])}"
    J.step(job_id, "Reading your sources")
    raw = await model().structured(system=K.SYSTEM, instructions=K.ASK_RULES, body=body, schema=K.ASK_SCHEMA,
                                   purpose="ask", max_tokens=1800, timeout=150)
    answer = re.sub(r"\s+\n", "\n", str(raw.get("answer") or "")).strip()[:6000]
    if not answer:
        raise R.ModelError(R.CUT_OFF, "cut_off")
    inline = [f"P{m}" for m in re.findall(r"\[P(\d+)\]", answer)]
    refs = []
    # A citation counts only when it names a passage the model was actually shown from the ticked sources: a label
    # it made up, one from a source that was unticked, or one past the part of a long source that fit is dropped,
    # and its bracket comes out of the answer with it.
    for r in inline + [K._ref(x) for x in raw.get("refs") or []]:
        if r and r in by_ref and r in shown and r not in refs:
            refs.append(r)
    follow = [str(f).strip()[:140] for f in (raw.get("followups") or []) if str(f).strip()][:3]
    t = store.now()
    store.run("INSERT INTO chats(role, content, source_ids, created_at) VALUES('user', ?, ?, ?)", (q[:2000], store.dumps(p.get("source_ids") or []), t))
    cid = store.run("INSERT INTO chats(role, content, refs, followups, source_ids, created_at) VALUES('assistant', ?, ?, ?, ?, ?)",
                    (answer, store.dumps(refs), store.dumps(follow), store.dumps(p.get("source_ids") or []), t + 0.001))
    return {"chat": chat_row(store.one("SELECT * FROM chats WHERE id=?", (cid,)), by_ref)}


def chat_row(r: dict, by_ref: Optional[dict] = None) -> dict:
    refs = store.loads(r.get("refs"), []) or []
    chips = []
    if refs:
        if by_ref is None:
            _s, _b, by_ref = passages_for(store.loads(r.get("source_ids"), []) or [])
        for i, ref in enumerate(refs, start=1):
            info = (by_ref or {}).get(ref)
            if info:
                chips.append({"n": i, "ref": ref, "title": info["source_title"], "locator": info["locator"], "source_id": info.get("source_id")})
    text = r["content"]
    for c in chips:
        text = text.replace(f"[{c['ref']}]", f"[{c['n']}]")
    text = re.sub(r"\s*\[P\d+\]", "", text)
    text = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", text)
    return {"id": r["id"], "role": r["role"], "text": text, "chips": chips, "followups": store.loads(r.get("followups"), []) or [],
            "created_at": r.get("created_at"), "pinned": bool(r.get("pinned")),
            "sources": len(store.loads(r.get("source_ids"), []) or []),
            **(K.split_answer(text) if r.get("role") == "assistant" else {"lead": "", "detail": "", "more": ""})}


def chats(n: int = 40) -> list:
    rows = store.q("SELECT * FROM chats ORDER BY id DESC LIMIT ?", (n,))[::-1]
    return [chat_row(r) for r in rows]


def clear_chats() -> None:
    store.run("DELETE FROM chats")


# ---------------------------------------------------------------- notes --
# A note is an answer the person pinned, or a line they typed. Notes steer what the Studio makes: they go into the
# brief as the points to build around. Facts still come only from passages, so a note can't slip in a number.

MAX_NOTES = 60
MAX_NOTE = 4000


def note_row(r: dict) -> dict:
    refs = store.loads(r.get("refs"), []) or []
    chips = []
    if refs:
        marks = ",".join("?" * len(refs))
        rows = store.q(f"SELECT p.id, p.locator, p.source_id, s.title FROM passages p JOIN sources s ON s.id=p.source_id WHERE p.id IN ({marks})",
                       [int(x[1:]) for x in refs if re.fullmatch(r"P\d+", x)])
        info = {f"P{x['id']}": x for x in rows}
        for i, ref in enumerate(refs, start=1):
            if ref in info:
                chips.append({"n": i, "ref": ref, "title": info[ref]["title"], "locator": info[ref]["locator"], "source_id": info[ref]["source_id"]})
    return {"id": r["id"], "text": r["text"], "chips": chips, "chat_id": r.get("chat_id"), "created_at": r.get("created_at")}


def list_notes() -> list:
    return [note_row(r) for r in store.q("SELECT * FROM notes ORDER BY created_at DESC LIMIT ?", (MAX_NOTES,))]


def add_note(text: str = "", chat_id: Optional[int] = None) -> dict:
    """Pin a chat answer (its words and citations as shown) or keep a typed line."""
    if store.one("SELECT COUNT(*) AS n FROM notes")["n"] >= MAX_NOTES:
        raise ValueError(f"The notebook holds {MAX_NOTES} notes. Remove one first.")
    refs, sids = [], []
    if chat_id is not None:
        r = store.one("SELECT * FROM chats WHERE id=? AND role='assistant'", (int(chat_id),))
        if not r:
            raise ValueError("That answer is gone. Ask again, then pin it.")
        dup = store.one("SELECT * FROM notes WHERE chat_id=?", (int(chat_id),))
        if dup:
            return note_row(dup)
        shown = chat_row(r)
        text, refs, sids = shown["text"], [c["ref"] for c in shown["chips"]], store.loads(r.get("source_ids"), []) or []
        store.run("UPDATE chats SET pinned=1 WHERE id=?", (int(chat_id),))
    text = re.sub(r"[ \t]+", " ", (text or "")).strip()
    if not text:
        raise ValueError("Type the note first.")
    if len(text) > MAX_NOTE:
        raise ValueError("That note is too long. Keep it under 4,000 characters.")
    nid = store.new_id("n")
    store.run("INSERT INTO notes(id, text, refs, source_ids, chat_id, created_at) VALUES(?,?,?,?,?,?)",
              (nid, text, store.dumps(refs), store.dumps(sids), chat_id, store.now()))
    return note_row(store.one("SELECT * FROM notes WHERE id=?", (nid,)))


def delete_note(note_id: str) -> None:
    r = store.one("SELECT * FROM notes WHERE id=?", (note_id,))
    if not r:
        raise ValueError("That note is gone already.")
    store.run("DELETE FROM notes WHERE id=?", (note_id,))
    if r.get("chat_id") is not None:
        store.run("UPDATE chats SET pinned=0 WHERE id=?", (r["chat_id"],))


def notes_brief(note_ids: list) -> str:
    """The notes a make was asked to build around, as plain lines for the brief (numbers inside are the person's
    own words; the grounding check still looks every number up in the passages)."""
    if not note_ids:
        return ""
    marks = ",".join("?" * len(note_ids))
    rows = store.q(f"SELECT text FROM notes WHERE id IN ({marks}) ORDER BY created_at", note_ids)
    lines = [re.sub(r"\s*\[\d+\]", "", r["text"]).strip()[:600] for r in rows]
    return ("\n\nBuild it around these notes the person pinned (their points, not new facts; cite the passages):\n"
            + "\n".join(f"- {x}" for x in lines if x)) if lines else ""


# ---------------------------------------------------------------- proofs --

def required_on(output_id: str, kit: dict) -> bool:
    """Whether this kit's required lines print on this output. A starter kit's lines (Docket's "Not legal
    advice.") are opt-in per output, so swapping a starter in never adds a disclaimer to someone's document;
    the lines on the person's own kit (their 501(c)(3) line) print unless they leave them off this output."""
    choice = (store.get_setting(f"required:{output_id}", {}) or {}).get(kit["id"])
    if choice is not None:
        return bool(choice)
    return not kit.get("starter")


def kit_for_output(output_id: str, kit: dict) -> dict:
    """The kit as it applies to one output: its required lines only when they are on for this output."""
    lines = (kit.get("rules") or {}).get("required") or []
    if not lines or required_on(output_id, kit):
        return kit
    return {**kit, "rules": {**kit["rules"], "required": []}}


def set_required(output_id: str, kit_id: str, on: bool) -> dict:
    _output(output_id)
    KITS.get(kit_id)
    d = store.get_setting(f"required:{output_id}", {}) or {}
    d[kit_id] = bool(on)
    store.set_setting(f"required:{output_id}", d)
    return output_view(output_id)


def _pill_required(output_id: str, kit: dict, page_text: str) -> Optional[dict]:
    lines = (kit.get("rules") or {}).get("required") or []
    if not lines:
        return None
    if not required_on(output_id, kit):
        return {"id": "required", "tone": "good", "label": f"{kit['name']}'s required line left off this output",
                "items": lines, "action": {"do": "require", "label": "Add it to this output"}}
    p = CK.pill_required(lines, page_text)
    if p and p["tone"] == "good":
        p["action"] = {"do": "unrequire", "label": "Leave it off this output"}
    return p


def proof(output_id: str, kit_id: str) -> dict:
    """One kit's proof: the voiced content with code-enforced voice rules, the tree, the checks."""
    out = _output(output_id)
    rend = store.one("SELECT * FROM renders WHERE output_id=? AND kit_id=?", (output_id, kit_id))
    full_kit = KITS.get(kit_id)
    kit = kit_for_output(output_id, full_kit)
    if not rend:
        return {"output_id": output_id, "kit_id": kit_id, "status": "missing", "kit": KITS.summary(kit)}
    body = store.loads(rend["content"], {})
    doc = body.get("doc") or out["neutral"]
    decisions = _decisions(output_id)
    _srcs, _by_source, by_ref = passages_for(out["source_ids"])
    doc, swaps = K.apply_pairs(doc, kit["voice"].get("pairs") or [])
    g = CK.grounding(doc, by_ref, decisions, brief=out.get("brief") or "")
    doc = g["doc"]
    pal = KITS.palette(kit)
    faces = KITS.faces(kit)
    date = out_date(out)
    logo, variants = logo_srcs(kit, pal)
    kind = K.kind_of(doc)
    idx, _rows = L.source_index(doc, by_ref)
    long_slides = []
    if kind == "deck":
        tree, scs = RD.deck_tree(doc, kit, pal, faces, by_ref, date, logo_urls=logo, images=_picture_urls(output_id, doc), idx=idx, rows=_rows)
        page_text = "\n".join(SC.text_of(sc) for sc in scs)
        long_slides = RD.long_slides(scs)
    elif kind == "visual":
        tree, gsc = RG.tree(doc, kit, pal, faces, idx, by_ref, logo_urls=logo)
        page_text = SC.text_of(gsc)
        long_slides = [1] if gsc.get("long") else []
    else:
        tree = L.tree(doc, kit, pal, faces, by_ref, date=date, logo=logo)
        page_text = L.text_of(tree)
    traces, resolve = CK.trace_table(g["items"], by_ref, idx, computed=TRACE_COMPUTED)
    tree = L.mark_traces(tree, resolve)
    claims, passages_used, _claim_of = CK.claims_map(g["items"], by_ref, idx, frame_of if kind == "deck" else None)
    tag_claims(tree, traces, claims, kind)
    # Round 10 (critic 9, S12): the rows are read after tagging, so a figure the cover repeats (the 287) puts the cover
    # in its claim's slides, and the reverse trace lights the cover with the slides that cite the same sentence.
    frames = proof_frames(doc, kind, claims)
    for _cid, c in claims.items():
        for r in [c.get("ref")] if c.get("ref") and c.get("status") not in ("missing", "kept", "brief") else []:
            if r in passages_used:
                passages_used[r]["slides"] = sorted(set(passages_used[r]["slides"]) | set(c.get("slides") or []))
    pills = [CK.pill_sources(g), CK.pill_contrast(pal), CK.pill_never(doc, kit["voice"].get("never") or [], swaps),
             _pill_required(output_id, full_kit, page_text), CK.pill_fonts(F.substitutions(faces), F.stands_in(faces)),
             CK.pill_voice(body.get("reverted") or [])]
    pills.append(LG.pill(kit, "deck" if kind in ("deck", "visual") else kind, variants))
    pills.append(CK.pill_wording(CK.wording(doc, by_ref)))  # a superlative its cited passage never uses (P6 round 2)
    if kind == "deck":
        pills.append(CK.pill_money_shown(CK.money_not_shown(doc, by_ref)))  # money figures no slide shows (round 3)
        pills.append(CK.pill_repeats(CK.repeats(doc)))  # a number set big on two slides (round 3)
        pills.append(CK.pill_drift(CK.drift(doc, by_ref)))  # relation words that drifted from the source (round 3)
    if long_slides:
        what = "The graphic's text runs long" if kind == "visual" else (
            f"Slide {long_slides[0]} runs long" if len(long_slides) == 1 else "Slides " + ", ".join(map(str, long_slides)) + " run long")
        pills.append({"id": "fit", "tone": "warn", "items": ["Some text was set at its smallest size and still needs more room. "
                                                             "Shorten the wording with Fix the wording, or remove a point."],
                      "label": what + "; shorten the wording"})
    if kind == "deck":
        pic = store.get_setting(f"pictures:{output_id}", {}) or {}
        if pic.get("missed"):
            pills.append({"id": "pictures", "tone": "warn", "items": ["Turn on image generation in Hermes Settings, then make the deck again."],
                          "label": "Picture slide set as type: your Hermes image tool didn't answer"})
    lp = KITS.logo_path(kit)
    if lp is not None and lp.suffix.lower() == ".svg":
        pills.append({"id": "logo", "tone": "warn", "items": [],
                      "label": "SVG logo shows here; add a PNG for " + ("PowerPoint and PDF" if kind == "deck" else "the PDF")})
    extra = {"kind": kind}
    if kind == "deck":
        extra["slide_count"] = RD.slide_count(doc, kit, _rows)
    if kind == "audio":
        mins = L.script_minutes(doc)
        extra["minutes"] = mins
        extra["audio"] = {k: v for k, v in audio_state(output_id, kit_id).items() if k in ("status", "error", "code", "bytes", "mime", "kit_version")}
        extra.update(audio_timeline(doc, by_ref, idx, out.get("brief") or ""))
        pills.append(CK.pill_length(mins, out.get("brief") or ""))
    pills = [p for p in pills if p]
    n_sources = len({by_ref[r]["source_id"] for r in _refs_in(doc) if r in by_ref})
    stale = int(rend.get("kit_version") or 0) != int(kit.get("version") or 1)
    return {**extra, "output_id": output_id, "kit_id": kit_id, "status": "ready", "kit": KITS.summary(kit), "kit_version": kit.get("version"),
            "stale_voice": stale, "tree": tree, "checks": pills, "blocked": CK.blocking(pills),
            "colophon": F.colophon(faces, n_sources), "bar": pal["bar"], "faces": _face_view(faces),
            "fonts": sorted({f["key"] for f in faces.values() if f.get("key")}), "title": doc.get("title") or doc.get("headline", ""),
            "grounding": CK.public_items([i for i in g["items"] if i["status"] in ("missing", "kept", "moved")]),
            "traces": traces, "claims": claims, "slides": frames, "passages_used": passages_used,
            "stamp": stamp(claims),
            "voice_note": rend.get("voice_note") or ""}


TRACE_COMPUTED = True  # the pane draws a head for "computed" trace cards (loop2-pane); claims always say it


def frame_of(path: str) -> int:
    """The frame a deck field lands on: 0 is the title slide, ``slides.N...`` is frame N + 1."""
    parts = (path or "").split(".")
    if len(parts) >= 2 and parts[0] == "slides" and parts[1].isdigit():
        return int(parts[1]) + 1
    return 0


def _slide_title(sl: dict) -> str:
    if sl.get("heading"):
        return sl["heading"]
    if sl.get("type") == "stat":
        return " ".join(x for x in (sl.get("value"), sl.get("label")) if x)
    if sl.get("type") == "quote":
        return sl.get("quote") or ""
    return sl.get("text") or ""


def proof_frames(doc: dict, kind: str, claims: dict) -> list:
    """``proof.slides``: one row per frame (0-based; frame 0 is the title slide). A one-pager, a graphic or a
    script is one frame."""
    def ids(i):
        return [cid for cid, c in claims.items() if i in (c.get("slides") or [])]
    if kind != "deck":
        refs = list(dict.fromkeys(_refs_in(doc)))
        return [{"i": 0, "type": kind, "title": doc.get("title") or doc.get("headline") or "", "refs": refs, "claims": ids(0)}]
    rows = [{"i": 0, "type": "title", "title": doc.get("title") or "", "refs": [], "claims": ids(0)}]
    for n, sl in enumerate(doc.get("slides") or [], start=1):
        refs = list(dict.fromkeys([r for r in (sl.get("refs") or []) if r] + [it.get("ref") for k in K.SLIDE_LISTS
                                                                              for it in (sl.get(k) or []) if isinstance(it, dict) and it.get("ref")]))
        rows.append({"i": n, "type": sl.get("type") or "content", "title": _slide_title(sl), "refs": refs, "claims": ids(n)})
    return rows


def _vals(v) -> tuple:
    got = K.numbers(str(v or ""))
    if not got and K.value_of(str(v or "")):
        got = [K.value_of(str(v or ""))]  # a number written as a word ("Nine")
    return tuple(got)


def tag_claims(tree: dict, traces: list, claims: dict, kind: str) -> None:
    """Put each claim's id on the node object of its number span (``node["tr"] = "c12"``, contract F), next to the
    trace index the pane reads (``a.tr``). On an exhibit, the bar drawn just before a traced value gets the same id,
    so hovering the bar traces it. Spans with no claim (a date, a page number) get nothing."""
    def claim_for(i: int, frame: Optional[int]) -> Optional[str]:
        t = traces[i] if 0 <= i < len(traces) else None
        if not t:
            return None
        tv = _vals(t.get("value"))
        cands = [cid for cid, c in claims.items() if (tv and _vals(c["value"]) == tv) or (not tv and c["value"] == t.get("value"))]
        if frame is not None:
            cands = [cid for cid in cands if frame in (claims[cid].get("slides") or [])] or cands
        missing = t.get("status") == "missing"
        best = [cid for cid in cands if (claims[cid]["status"] == "missing") == missing] or cands
        return best[0] if best else None

    def first_claim(node, frame):
        a = node.get("a") or {}
        if isinstance(a.get("tr"), int):
            cid = claim_for(a["tr"], frame)
            if cid:
                node["tr"] = cid
                sl = claims[cid].setdefault("slides", [])
                if frame is not None and frame not in sl:
                    sl.append(frame)  # the cover repeats the deck's key figure: that frame shows the claim too
                    sl.sort()
                return cid
        got = None
        for k in node.get("k") or []:
            if isinstance(k, dict):
                c = first_claim(k, frame)
                got = got or c
        return got

    def walk_frame(sc, frame, bars=True):
        kids = [k for k in sc.get("k") or [] if isinstance(k, dict)]
        found = [first_claim(k, frame) for k in kids]
        def short_text(n):
            out = []

            def w(x):
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict):
                    for y in x.get("k") or []:
                        w(y)
            w(n)
            return len("".join(out).strip()) <= 14

        def is_rect(k):
            return "ip-sc-r" in str(k.get("c") or "").split()

        # A bar is followed by its labels (the category, then the value, in either order) before the next shape.
        # It traces the first short label that carries a claim; a rule followed by a headline traces nothing.
        for j, k in enumerate(kids if bars else []):
            if not is_rect(k) or found[j]:
                continue
            for m in range(j + 1, min(j + 4, len(kids))):
                if is_rect(kids[m]):
                    break
                if found[m] and short_text(kids[m]):
                    k["tr"] = found[m]
                    break

    if kind == "deck":
        frames = [k for k in tree.get("k") or [] if isinstance(k, dict) and "ip-scene" in str(k.get("c") or "")]
        for n, sc in enumerate(frames):
            walk_frame(sc, n, bars=any(k in str(sc.get("c") or "") for k in ("ip-sk-exhibit", "ip-sk-spec")))
    else:
        walk_frame(tree, 0)


WPM = 150.0


def length_label(minutes: float, brief: str = "") -> str:
    """"About 3 min": the length asked for when the script runs within a quarter of it, else the script's own length."""
    want = CK.target_minutes(brief)
    if want and want * 0.75 <= minutes <= want * 1.25 + 0.15:
        return f"About {int(round(want * 60))} sec" if want < 1 else f"About {want:g} min"
    if minutes < 1:
        return f"About {max(10, int(round(minutes * 60 / 10.0)) * 10)} sec"
    return f"About {max(1, int(round(minutes)))} min"


def _words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _line_chips(sentence: str, refs: list, by_ref: dict, idx: dict) -> list:
    """The passages a spoken sentence rests on: the ones that hold its numbers, else the segment's first."""
    nums = K.numbers(sentence)
    hit = [r for r in refs if r in by_ref and nums and any(n in K.numbers(by_ref[r]["text"]) for n in nums)]
    use = hit or [r for r in refs if r in by_ref][:1]
    return [{"ref": r, "n": i, "source_n": idx.get(r), "source": by_ref[r].get("source_title", ""),
             "locator": (by_ref[r].get("locator") or "").strip("“”")} for i, r in enumerate(use, start=1)]


def audio_timeline(doc: dict, by_ref: dict, idx: dict, brief: str = "") -> dict:
    """``length_label`` and ``chapters`` for an audio brief, timed at a steady 150 words a minute: each chapter
    ``{i, heading, start_s, dur_s, lines: [{text, start_s, chips}]}``; the title is read first and the recap last."""
    t = _words(doc.get("title")) * 60.0 / WPM
    chapters = []
    segs = [(seg.get("heading") or "", seg.get("text") or "", seg.get("refs") or []) for seg in doc.get("segments") or []]
    if doc.get("recap"):
        segs.append(("Recap", doc["recap"], list(dict.fromkeys(r for _h, _t, rs in segs for r in rs))))
    for i, (head, text, refs) in enumerate(segs):
        start = t
        t += _words(head) * 60.0 / WPM
        lines = []
        for sent in [x for x in re.split(r"(?<=[.!?])\s+", text.strip()) if x]:
            lines.append({"text": sent, "start_s": round(t, 1), "chips": _line_chips(sent, refs, by_ref, idx)})
            t += _words(sent) * 60.0 / WPM
        chapters.append({"i": i, "heading": head, "start_s": round(start, 1), "dur_s": round(t - start, 1), "lines": lines})
    minutes = round(t / 60.0, 1)
    return {"length_label": length_label(minutes, brief), "seconds": round(t, 1), "chapters": chapters}


CHECKED = ("exact", "close", "computed")


def stamp(claims: dict) -> str:
    """The proof's stamp. Counts exact, close and worked-out numbers; says so plainly when none are left to check."""
    nums = [c for c in claims.values() if c.get("kind") != "quote"]
    if not nums:
        return "No numbers to check."
    bad = [c for c in nums if c.get("status") not in CHECKED + ("kept", "brief")]
    good = [c for c in nums if c.get("status") in CHECKED]
    if bad:
        return f"{len(bad)} number{'s' if len(bad) != 1 else ''} not found in your sources."
    if not good:
        return "No numbers to check."
    return "The 1 number matches your sources." if len(good) == 1 else f"All {len(good)} numbers match your sources."


def _count_numbers(doc: dict) -> int:
    try:
        return len({n for _p, t, _r in K.field_texts(doc) for _raw, n, _a, _b in K.claim_spans(t)})
    except Exception:
        return 0


def _refs_in(doc: dict) -> list:
    if K.kind_of(doc) != "onepager":
        return [r for _p, _t, rs in K.field_texts(doc) for r in rs if r]
    refs = list(doc.get("dek_refs") or [])
    for s in doc.get("sections") or []:
        refs += s.get("refs") or []
    for p in doc.get("points") or []:
        refs.append(p.get("ref"))
    for k in ("stat", "quote"):
        if doc.get(k):
            refs.append(doc[k].get("ref"))
    return [r for r in refs if r]


def _decisions(output_id: str) -> dict:
    return store.get_setting(f"decisions:{output_id}", {}) or {}


def output_view(output_id: str) -> dict:
    out = _output(output_id)
    return {"id": out["id"], "kind": out["kind"], "title": out["title"], "brief": out["brief"], "status": out["status"],
            "source_ids": out["source_ids"], "kit_ids": out["kit_ids"], "tokens": (out.get("tokens_in") or 0) + (out.get("tokens_out") or 0),
            "created_at": out["created_at"], "formats": FORMATS.get(out["kind"], FORMATS["onepager"]),
            "proofs": [proof(output_id, k) for k in out["kit_ids"]], "versions": store.versions(output_id)}


def decide(output_id: str, key: str, action: str) -> dict:
    """Keep a flagged item on purpose, or remove it from every kit's version."""
    out = _output(output_id)
    if action == "keep":
        d = _decisions(output_id)
        d[key] = "keep"
        store.set_setting(f"decisions:{output_id}", d)
        store.set_setting(f"decision-log:{output_id}", (store.get_setting(f"decision-log:{output_id}", []) or []) +
                          [{"key": key, "action": "keep", "at": store.now()}])
    elif action == "remove":
        path = key.split("|", 1)[0]
        docs = [("neutral", out["neutral"])]
        for r in store.q("SELECT kit_id, content FROM renders WHERE output_id=?", (output_id,)):
            docs.append((r["kit_id"], store.loads(r["content"], {})))
        for who, doc in docs:
            target = doc if who == "neutral" else doc.get("doc")
            if not target:
                continue
            _remove(target, path, key)
            if who == "neutral":
                store.run("UPDATE outputs SET neutral=?, updated_at=? WHERE id=?", (store.dumps(target), store.now(), output_id))
            else:
                store.run("UPDATE renders SET content=? WHERE output_id=? AND kit_id=?", (store.dumps(doc), output_id, who))
    else:
        raise ValueError("Choose keep or remove.")
    return output_view(output_id)


def _drop_sentences(text: str, value: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    return " ".join(x for x in sentences if value not in x and value not in x.replace(",", ""))


def _remove(doc: dict, path: str, key: str) -> None:
    """Take a flagged item out: the list item it sits in, or the sentences that carry the value."""
    parts = path.split(".")
    value = key.split("|")[2] if key.count("|") >= 2 else ""
    kind = K.kind_of(doc)
    if kind == "deck":
        if parts[0] == "slides" and len(parts) >= 2:
            i = int(parts[1])
            slides = doc.get("slides") or []
            if i >= len(slides):
                return
            sl = slides[i]
            if len(parts) >= 4 and parts[2] in K.SLIDE_LISTS:
                lst = sl.get(parts[2]) or []
                j = int(parts[3])
                if j < len(lst):
                    lst.pop(j)
                if parts[2] == "bullets" and not lst:
                    slides.pop(i)
            elif len(parts) == 3:
                field = parts[2]
                if field in ("value", "quote") or (field in ("label", "context", "text") and sl.get("type") == "stat"):
                    slides.pop(i)
                else:
                    sl[field] = _drop_sentences(sl.get(field, ""), value)
        elif path in ("title", "subtitle"):
            doc[path] = _drop_sentences(doc.get(path, ""), value) or (doc.get(path, "") if path == "title" else "")
        return
    if kind == "audio":
        if parts[0] == "segments" and len(parts) == 3:
            i = int(parts[1])
            segs = doc.get("segments") or []
            if i < len(segs):
                segs[i][parts[2]] = _drop_sentences(segs[i].get(parts[2], ""), value)
                if not segs[i].get("text"):
                    segs.pop(i)
        elif path in ("title", "recap"):
            doc[path] = _drop_sentences(doc.get(path, ""), value) or (doc.get(path, "") if path == "title" else "")
        return
    if path in ("stat", "quote"):
        doc[path] = None
    elif parts[0] == "points" and len(parts) >= 2:
        i = int(parts[1])
        if i < len(doc.get("points") or []):
            doc["points"].pop(i)
    elif parts[0] == "sections" and len(parts) == 4 and parts[2] == "items":
        items = doc["sections"][int(parts[1])].get("items") or []
        if int(parts[3]) < len(items):
            items.pop(int(parts[3]))
    elif parts[0] == "sections" and len(parts) == 3:
        sec = doc["sections"][int(parts[1])]
        field = parts[2]
        kept = _drop_sentences(sec.get(field, ""), value)
        if field == "body" and not kept:
            doc["sections"].pop(int(parts[1]))
        else:
            sec[field] = kept
    elif path in ("dek", "next", "title"):
        doc[path] = _drop_sentences(doc.get(path, ""), value) or ("" if path != "title" else doc.get(path, ""))


EDITABLE = (r"(title|dek|next|subtitle|recap|stat\.value|stat\.label|quote\.text|sections\.\d\.(heading|body)|points\.\d\.text"
            r"|slides\.\d{1,2}\.(heading|subtitle|value|label|context|quote|who|text|cta|left_label|right_label)"
            r"|slides\.\d{1,2}\.(bullets|left_items|right_items)\.\d\.text|segments\.\d\.(heading|text))")


def edit(output_id: str, path: str, text: str) -> dict:
    """Change one field's words in the draft and in every kit's version (facts are shared across kits)."""
    out = _output(output_id)
    text = (text or "").strip()
    if not text:
        raise ValueError("Type the new wording first, or remove the item.")
    if len(text) > 900:
        raise ValueError("That is too long for one field.")
    allowed = re.fullmatch(EDITABLE, path or "")
    if not allowed:
        raise ValueError("That part can't be edited here.")
    store._ensure_v1(output_id)  # the wording before this edit stays one Undo away
    neutral = out["neutral"]
    try:
        K.set_path(neutral, path, text)
    except (KeyError, IndexError, TypeError):
        raise ValueError("That part is gone from the draft.")
    store.run("UPDATE outputs SET neutral=?, updated_at=? WHERE id=?", (store.dumps(neutral), store.now(), output_id))
    for r in store.q("SELECT kit_id, content FROM renders WHERE output_id=?", (output_id,)):
        body = store.loads(r["content"], {})
        try:
            K.set_path(body["doc"], path, text)
        except (KeyError, IndexError, TypeError):
            continue
        store.run("UPDATE renders SET content=? WHERE output_id=? AND kit_id=?", (store.dumps(body), output_id, r["kit_id"]))
    store.add_version(output_id, neutral, "Edited text")
    return output_view(output_id)


# ---------------------------------------------------------------- export --

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "imprint"


FORMATS = {
    "onepager": {"pdf": "PDF", "proof": "Proof PDF with crop marks", "html": "HTML page"},
    "deck": {"pptx": "PowerPoint (.pptx)", "pdf": "PDF of the slides"},
    "audio": {"audio": "Audio file (MP3)", "script": "Script (text)", "pdf": "Script PDF"},
    "visual": {"png": "PNG image", "svg": "SVG (scales to any size)", "pdf": "PDF"},
}
BASE_NAME = {"onepager": "brief", "deck": "deck", "audio": "audio-brief", "visual": "graphic"}


def export(output_id: str, kit_id: str, fmt: str) -> dict:
    pr = proof(output_id, kit_id)
    if pr.get("status") != "ready":
        raise ValueError("That kit's version isn't ready yet.")
    if pr["blocked"]:
        raise ValueError("Something in this draft isn't in your sources. Fix it, remove it, or keep it on purpose, then export.")
    out = _output(output_id)
    kit = kit_for_output(output_id, KITS.get(kit_id))
    kind = pr.get("kind") or "onepager"
    if fmt not in FORMATS.get(kind, {}):
        raise ValueError("Choose one of: " + ", ".join(FORMATS.get(kind, FORMATS["onepager"]).values()) + ".")
    folder = store.root() / "outputs" / output_id
    folder.mkdir(parents=True, exist_ok=True)
    base = f"{BASE_NAME.get(kind, 'brief')}-{_slug(kit['name'])}"
    doc = _doc_for(output_id, kit)
    _s, _b, by_ref = passages_for(out["source_ids"])
    idx, rows = L.source_index(doc, by_ref)
    # A kit that lists no sources (a menu, a flyer for customers) gets no source marks on the finished
    # file either: a mark with no list to point at is noise. The proof keeps every trace.
    marks = bool((kit.get("rules") or {}).get("sources"))
    midx = idx if marks else {}
    date = out_date(out)
    pal, faces = KITS.palette(kit), KITS.faces(kit)
    if kind == "deck":
        pics = _pictures(output_id, doc)
        try:
            if fmt == "pptx":
                data = RD.render_pptx(doc, kit, pal, midx, rows, by_ref, date=date, logo=KITS.logo_variants(kit, pal), faces=faces,
                                      pictures=pics)
                name = f"{base}.pptx"
            else:
                data = RD.render_pdf(doc, kit, pal, faces, midx, rows, "", date=date, logo=KITS.logo_variants(kit, pal), passages=by_ref,
                                     pictures=pics)
                name = f"{base}.pdf"
        except RD.DeckUnavailable as e:
            raise ValueError(str(e))
    elif kind == "visual":
        if fmt == "png":
            data, name = RG.render_png(doc, kit, pal, faces, midx, by_ref, logo=KITS.logo_variants(kit, pal)), f"{base}.png"
        elif fmt == "svg":
            data, name = RG.render_svg(doc, kit, pal, faces, midx, by_ref, logo_urls=logo_srcs(kit, pal)[0]).encode("utf-8"), f"{base}.svg"
        else:
            data, name = RG.render_pdf(doc, kit, pal, faces, midx, by_ref, logo=KITS.logo_variants(kit, pal)), f"{base}.pdf"
    elif kind == "audio" and fmt == "audio":
        st = audio_state(output_id, kit_id)
        p = folder / st.get("file", "") if st.get("status") == "ready" else None
        if p is None or not p.is_file():
            raise ValueError("There is no recording for this kit yet. Press Record, or export the script.")
        return {"path": str(p), "name": p.name, "folder": str(folder), "bytes": p.stat().st_size}
    elif kind == "audio" and fmt == "script":
        lines = [K.script_text(doc)]
        if marks and rows:
            lines += ["", "Sources"]
            lines += [f"{r['n']}. {r['title']}" + (f", {', '.join(r['locators'][:6])}" if r["locators"] else "") for r in rows]
        data = ("\n".join(lines) + "\n").encode("utf-8")
        name = f"{base}-script.txt"
    elif fmt in ("pdf", "proof"):
        is_proof = fmt == "proof"
        data = RP.render(_script_as_page(doc) if kind == "audio" else doc, kit, pal, faces, idx if is_proof else midx, rows,
                         pr["colophon"], date=date, logo=KITS.logo_variants(kit, pal), proof=is_proof)
        name = f"{base}{'-script' if kind == 'audio' else ''}{'-proof' if is_proof else ''}.pdf"
    else:
        tree = L.tree(doc, kit, pal, faces, by_ref, date=date, logo=logo_srcs(kit, pal)[0])
        data = RH.export_page(tree, faces, pr["title"], marks=marks).encode("utf-8")
        name = f"{base}.html"
    path = folder / name
    store.write_bytes(path, data)
    store.write_json(folder / f"content-{kind}-{_slug(kit['name'])}.json", {"doc": doc, "kit": kit["id"], "kit_version": kit.get("version")})
    return {"path": str(path), "name": name, "folder": str(folder), "bytes": len(data)}


def _script_as_page(doc: dict) -> dict:
    """The audio script in the one-pager's shape, so the script PDF uses the kit's page layout."""
    return {"title": doc.get("title", ""), "dek": "", "dek_refs": [], "stat": None, "points": [], "quote": None,
            "sections": [{"heading": s.get("heading", ""), "body": s.get("text", ""), "refs": s.get("refs") or []}
                         for s in doc.get("segments") or []],
            "next": doc.get("recap", "")}


def _doc_for(output_id: str, kit: dict) -> dict:
    out = _output(output_id)
    rend = store.one("SELECT * FROM renders WHERE output_id=? AND kit_id=?", (output_id, kit["id"]))
    doc = (store.loads(rend["content"], {}) if rend else {}).get("doc") or out["neutral"]
    doc, _ = K.apply_pairs(doc, kit["voice"].get("pairs") or [])
    _s, _b, by_ref = passages_for(out["source_ids"])
    return CK.grounding(doc, by_ref, _decisions(output_id), brief=out.get("brief") or "")["doc"]


def delete_output(output_id: str) -> None:
    _output(output_id)
    store.run("DELETE FROM renders WHERE output_id=?", (output_id,))
    store.drop_versions(output_id)
    store.run("DELETE FROM outputs WHERE id=?", (output_id,))
    import shutil
    folder = store.root() / "outputs" / output_id
    if folder.exists():
        shutil.rmtree(folder)


# ---------------------------------------------------------------- state --

def deps() -> dict:
    out = {}
    for mod, label in (("pypdf", "PDF reading"), ("docx", "Word reading"), ("reportlab", "PDF export"), ("pptx", "Deck export")):
        try:
            __import__(mod)
            out[mod] = {"ok": True, "label": label}
        except ImportError:
            out[mod] = {"ok": False, "label": label}
    return out


def storage() -> dict:
    root = store.root()
    return {"bytes": store.folder_size(root), "sources": store.one("SELECT COUNT(*) AS n FROM sources")["n"],
            "outputs": store.one("SELECT COUNT(*) AS n FROM outputs")["n"],
            "kits": len([d for d in KITS.kits_dir().iterdir() if (d / "kit.json").exists()])}


def usage() -> dict:
    return {"today": store.tokens_today(), "cap": store.get_setting("daily_token_cap")}


def state() -> dict:
    outs, prev = _parallel([(list_outputs, (20, True)), (previews, ())])
    return {"sources": list_sources(), "kits": KITS.list_all(), "outputs": outs, "jobs": J.running(),
            "sample": sample_state(), "previews": prev,
            "prefs": store.get_setting("prefs", {}) or {}, "usage": usage(), "deps": deps(), "storage": storage(),
            "layouts": KITS.LAYOUTS, "kinds": K.KINDS, "ready_kinds": list(K.READY_KINDS), "fonts": F.bundled_families(),
            "today": nice_date(), "proof_css": L.PROOF_CSS + SC.SCENE_CSS, "notes": list_notes(), "deck_systems": KITS.DECK_SYSTEMS}


# ---------------------------------------------------------------- the sample notebook --
# ``samples/harborlight/`` ships the three Harborlight files (fictional, marked "Sample") and ``notebook.json``: a
# recording of real-model results (tools/record_sample.py). Opening the sample switches Imprint to ``<data>/sample/``,
# built from that recording the first time (no model call) and reused after; the shipped folder is only read.
# Closing goes back to the person's own folder, which nothing here touches. Docs are stored, not renders, so the
# current renderer draws them.

SAMPLE_SRC = Path(__file__).resolve().parent / "samples" / "harborlight"
SAMPLE_NAME = "Harborlight Literacy"
SAMPLE_KIT_NAME = "Harborlight"
# The Harborlight brand as the sample sets it: Harbor Teal for headlines and the band, Lighthouse Red as the one accent
# (the guide's own colors; Sunrise Gold is left out so the exhibit's one highlighted number reads in red).
SAMPLE_COLORS = [{"hex": "#0E5E6F", "role": "head", "name": "Harbor Teal"}, {"hex": "#0E5E6F", "role": "band", "name": "Harbor Teal"},
                 {"hex": "#C0392B", "role": "accent", "name": "Lighthouse Red"}]
SAMPLE_TABLES = ("sources", "passages", "chats", "notes", "outputs", "renders", "output_versions")
_book_cache: dict = {}


def sample_book() -> Optional[dict]:
    """The recorded sample, or ``None`` when it isn't there."""
    p = SAMPLE_SRC / "notebook.json"
    try:
        st = p.stat()
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    if _book_cache.get("key") != key:
        import hashlib
        raw = p.read_bytes()
        try:
            book = store.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            book = None
        if not isinstance(book, dict) or not isinstance(book.get("tables"), dict):
            return None
        book["sig"] = hashlib.sha256(raw).hexdigest()[:16]
        _book_cache.update(key=key, book=book)
    return _book_cache["book"]


def sample_state() -> dict:
    return {"available": sample_book() is not None, "open": R.sample_open(), "name": SAMPLE_NAME, "label": "Sample"}


def _build_sample(book: dict) -> None:
    """Fill the (empty) sample folder from the recording. Called with the sample folder active."""
    import hashlib
    store.forget_everything()  # the sample folder only: it is the active one now
    for t in SAMPLE_TABLES:
        rows = book["tables"].get(t) or []
        if not rows:
            continue
        cols = list(rows[0].keys())
        have = {r["name"] for r in store.q(f"PRAGMA table_info({t})")}
        cols = [c for c in cols if c in have]
        store.many(f"INSERT OR REPLACE INTO {t}({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})",
                   [[r.get(c) for c in cols] for r in rows])
    for k, v in (book.get("settings") or {}).items():
        store.set_setting(k, v)
    shipped = {}
    for f in SAMPLE_SRC.iterdir():
        if f.is_file() and f.name != "notebook.json":
            shipped[hashlib.sha256(f.read_bytes()).hexdigest()] = f
    for s in book["tables"].get("sources") or []:
        f = shipped.get(s.get("sha256"))
        if f is not None:
            store.write_bytes(store.root() / "sources" / f"{s['sha256']}{s.get('ext') or f.suffix}", f.read_bytes())
    import base64
    kid = book.get("kit_id")
    if kid and re.fullmatch(r"k_[a-f0-9]{12}", kid):
        for rel, b64 in (book.get("kit_files") or {}).items():
            if ".." in Path(rel).parts or Path(rel).is_absolute():
                continue
            store.write_bytes(KITS.kits_dir() / kid / rel, base64.b64decode(b64))
    for name, uri in (book.get("pictures") or {}).items():  # pictures drawn when it was recorded, by their cache names
        if re.fullmatch(r"[a-z0-9-]{1,90}\.txt", name or "") and isinstance(uri, str) and uri.startswith("data:image/"):
            store.write_bytes(store.root() / "previews" / name, uri.encode("utf-8"))
    store.write_json(store.root() / "sample.json", {"sig": book["sig"], "built_at": store.now()})


def open_sample() -> dict:
    book = sample_book()
    if book is None:
        raise ValueError("The sample isn't installed. Reinstall Imprint to get it back.")
    base = R.base_dir()
    if not R.sample_open():
        store.write_bytes(base / R.SAMPLE_FLAG, b"1")
    mark = store.read_json(store.root() / "sample.json", {}) or {}
    if mark.get("sig") != book["sig"] or not (store.root() / store.DB_NAME).exists():
        try:
            _build_sample(book)
        except BaseException:
            close_sample()
            raise
    return state()


def close_sample() -> dict:
    flag = R.base_dir() / R.SAMPLE_FLAG
    try:
        flag.unlink()
    except FileNotFoundError:
        pass
    store.conn()  # reopen the person's own folder now
    return state()


# ---------------------------------------------------------------- pictures of outputs --
# ``state.previews``: the Studio tiles, drawn in the active brand from the sample's recorded docs (present before the
# sample is opened). ``outputs[i].thumb``: the first slide or the top of the page, about 480px wide. Both are cached
# on disk under ``previews/`` by what they show, so a state call draws nothing it drew before.

THUMB_W = 480
# The files that decide how a picture looks. A cached picture names their fingerprint, so a design change draws fresh
# pictures instead of showing old ones (the sample ships its pictures under the fingerprint it was recorded with).
RENDER_FILES = ("render_deck.py", "render_graphic.py", "render_pdf.py", "scene.py", "systems.py", "layout.py", "kits.py",
                "starter_kits.py", "colors.py", "fonts.py")
_render_sig: list = []


def renderer_sig() -> str:
    if not _render_sig:
        import hashlib
        h = hashlib.sha256()
        here = Path(__file__).resolve().parent
        for name in RENDER_FILES:
            try:
                h.update((here / name).read_bytes())
            except OSError:
                pass
        _render_sig.append(h.hexdigest()[:10])
    return _render_sig[0]


def _doc_sig(doc) -> str:
    import hashlib
    return hashlib.sha256(store.dumps(doc).encode()).hexdigest()[:10]
PREVIEW_W = 640


def _png_data(png: bytes, width: int, crop_ratio: Optional[float] = None) -> str:
    """A data URI for ``png`` scaled to ``width`` (and cut to ``crop_ratio`` height/width from the top), JPEG when
    that is smaller."""
    import base64
    import io
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if crop_ratio:
        im = im.crop((0, 0, im.width, min(im.height, int(im.width * crop_ratio))))
    if im.width != width:
        im = im.resize((width, max(1, int(im.height * width / im.width))), Image.LANCZOS)
    a, b = io.BytesIO(), io.BytesIO()
    im.save(a, "PNG", optimize=True)
    im.save(b, "JPEG", quality=86, optimize=True)
    if a.tell() <= 80 * 1024 or a.tell() <= b.tell():
        return "data:image/png;base64," + base64.b64encode(a.getvalue()).decode()
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def _cached(name: str, draw) -> Optional[str]:
    path = store.root() / "previews" / (re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")[:90] + ".txt")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        uri = draw()
    except Exception as e:  # a picture that can't be drawn leaves its tile plain; the reason is logged
        _log_preview(e)
        return None
    if uri:
        store.write_bytes(path, uri.encode("utf-8"))
    return uri


def _log_preview(e: BaseException) -> None:
    import logging
    logging.getLogger("hermes.plugins.imprint").warning("imprint: preview not drawn: %s: %s", type(e).__name__, e)


def _deck_png(doc: dict, kit: dict, by_ref: dict, pick: str = "title", width: int = THUMB_W) -> bytes:
    pal, faces = KITS.palette(kit), KITS.faces(kit)
    idx, rows = L.source_index(doc, by_ref)
    scs, ty = RD.scenes(doc, kit, pal, faces, idx, rows, nice_date(), by_ref)
    sc = scs[0]
    if pick == "exhibit":
        sc = next((s for s in scs if s.get("kind") == "exhibit"), None) or next((s for s in scs if s.get("kind") == "stat"), scs[min(1, len(scs) - 1)])
    return SC.png(sc, ty, scale=width / sc["w"], logos=RD.logo_bytes(KITS.logo_variants(kit, pal)))


def _page_png(doc: dict, kit: dict, by_ref: dict, width: int = THUMB_W) -> bytes:
    """The top of a one-pager: its PDF page drawn to an image (macOS ``sips``), else the masthead set as a scene."""
    pal, faces = KITS.palette(kit), KITS.faces(kit)
    idx, rows = L.source_index(doc, by_ref)
    try:
        import shutil as _sh
        import subprocess
        import tempfile
        if _sh.which("sips"):
            pdf = RP.render(doc, kit, pal, faces, idx, rows, F.colophon(faces, 1), date=nice_date(), logo=KITS.logo_variants(kit, pal))
            with tempfile.TemporaryDirectory(prefix="imprint-thumb-") as d:
                src, dst = Path(d) / "p.pdf", Path(d) / "p.png"
                src.write_bytes(pdf)
                subprocess.run(["sips", "-s", "format", "png", "-Z", str(width * 2), str(src), "--out", str(dst)],
                               capture_output=True, timeout=20, check=True)
                return dst.read_bytes()
    except Exception as e:
        _log_preview(e)
    return _card_png(kit, doc.get("title") or "", [doc.get("dek") or ""], width)


def _card_png(kit: dict, title: str, lines: list, width: int = THUMB_W, label: str = "") -> bytes:
    """A small brand card: the band, a title and up to three lines, set in the brand's faces and colors."""
    pal, faces = KITS.palette(kit), KITS.faces(kit)
    ty = SC.Type(faces)
    W, H = 960.0, 540.0
    cv = SC.Canvas(ty, W, H, pal["paper"])
    band = pal.get("band") or pal["head"]
    band_text = pal.get("band_text") or pal["paper"]
    cv.rect(0, 0, W, 84, band)
    cv.text(label or (kit.get("org") or kit.get("name") or ""), 56, 26, W - 112, 36, face="label", size=20, color=band_text, upper=True, track=0.08)
    top = cv.text(title, 56, 124, W - 112, 150, face="heading", size=46, min_size=30, lead=1.08, color=pal["head"])["bottom"]
    y = top + 30
    for i, ln in enumerate([x for x in lines if x][:3]):
        cv.rect(56, y + 6, 6, 30, pal["accent"])
        y = cv.text(ln, 82, y, W - 140, 90, face="body", size=26, min_size=20, lead=1.25, color=pal["ink"])["bottom"] + 22
    return SC.png(cv.done(), ty, scale=width / W)


def _audio_png(doc: dict, kit: dict, width: int = THUMB_W) -> bytes:
    heads = [s.get("heading") or "" for s in doc.get("segments") or [] if s.get("heading")][:3]
    mins = L.script_minutes(doc)
    return _card_png(kit, doc.get("title") or "Audio brief", [f"{i}. {h}" for i, h in enumerate(heads, start=1)], width,
                     label=f"Audio brief, about {max(1, round(mins))} min")


def _visual_png(doc: dict, kit: dict, by_ref: dict, width: int = THUMB_W) -> bytes:
    pal, faces = KITS.palette(kit), KITS.faces(kit)
    idx, _rows = L.source_index(doc, by_ref)
    png = RG.render_png(doc, kit, pal, faces, idx, by_ref, logo=KITS.logo_variants(kit, pal), scale=1.0)
    return png


_pic_memo: dict = {}
_pic_lock = __import__("threading").Lock()


def _picture(kind: str, doc: dict, kit: dict, by_ref: dict, width: int, deck_pick: str = "title") -> bytes:
    """One raster, drawn once per process for the same doc, brand, pick and width (a one-pager's preview and its thumb
    share one page drawing)."""
    import hashlib
    width = PREVIEW_W * 2  # draw once at the larger size; _png_data scales down
    key = hashlib.sha256(store.dumps([kind, doc, kit.get("id"), kit.get("version"), deck_pick if kind == "deck" else ""]).encode()).hexdigest()
    with _pic_lock:
        if key in _pic_memo:
            return _pic_memo[key]
    png = _draw_picture(kind, doc, kit, by_ref, width, deck_pick)
    with _pic_lock:
        if len(_pic_memo) > 64:
            _pic_memo.clear()
        _pic_memo[key] = png
    return png


def _draw_picture(kind: str, doc: dict, kit: dict, by_ref: dict, width: int, deck_pick: str = "title") -> bytes:
    if kind == "deck":
        return _deck_png(doc, kit, by_ref, deck_pick, width)
    if kind == "audio":
        return _audio_png(doc, kit, width)
    if kind == "visual":
        return _visual_png(doc, kit, by_ref, width)
    return _page_png(doc, kit, by_ref, width)


def _book_by_ref(book: dict) -> dict:
    titles = {s["id"]: s["title"] for s in book["tables"].get("sources") or []}
    return {f"P{p['id']}": {"text": p["text"], "locator": p["locator"], "source_id": p["source_id"],
                            "source_title": titles.get(p["source_id"], "Source")} for p in book["tables"].get("passages") or []}


def _book_doc(book: dict, kind: str) -> Optional[dict]:
    oid = (book.get("outputs") or {}).get(kind)
    for r in book["tables"].get("renders") or []:
        if r.get("output_id") == oid:
            d = (store.loads(r.get("content"), {}) or {}).get("doc")
            if d:
                return d
    row = next((o for o in book["tables"].get("outputs") or [] if o.get("id") == oid), None)
    return store.loads(row.get("neutral")) if row else None


def sample_visual(deck: dict) -> Optional[dict]:
    """The sample's graphic: the deck's exhibit as one bar chart (the same checked numbers)."""
    ex = next((s for s in deck.get("slides") or [] if s.get("type") == "exhibit" and len(s.get("bars") or []) >= 2), None)
    if not ex:
        return None
    return {"headline": ex.get("heading") or deck.get("title") or "", "form": "bars", "takeaway": ex.get("note") or ex.get("subhead") or "",
            "items": [{"label": b.get("label", ""), "value": b.get("value", ""), "ref": b.get("ref")} for b in ex["bars"]]}


def active_kit() -> dict:
    kid = (store.get_setting("prefs", {}) or {}).get("kit")
    if kid:
        try:
            return KITS.get(kid)
        except Exception:
            pass
    return KITS.get(KITS.list_all()[0]["id"])


def previews() -> dict:
    """``{deck, onepager, visual, audio}``: each ``{img, w, h, kit_id, kit_name}`` or ``None``."""
    book = sample_book()
    out = {"deck": None, "onepager": None, "visual": None, "audio": None}
    if book is None:
        return out
    shown = _first_open_previews(book)
    if shown:
        return {**out, **shown}
    try:
        kit = active_kit()
    except Exception as e:
        _log_preview(e)
        return out
    by_ref = _book_by_ref(book)
    deck = _book_doc(book, "deck")
    docs = {"deck": deck, "onepager": _book_doc(book, "onepager"), "audio": _book_doc(book, "audio"),
            "visual": sample_visual(deck) if deck else None}
    def one(kind, doc):
        name = f"preview-{kind}-{kit['id']}-v{kit.get('version', 1)}-{_doc_sig(doc)}-{renderer_sig()}"
        return kind, _cached(name, lambda: _png_data(_picture(kind, doc, kit, by_ref, PREVIEW_W * 2, "exhibit"), PREVIEW_W,
                                                     0.75 if kind == "onepager" else None))
    for kind, uri in _parallel([(one, (k, d)) for k, d in docs.items() if d]):
        if uri:
            out[kind] = {"img": uri, "w": PREVIEW_W, "h": _uri_h(uri), "kit_id": kit["id"], "kit_name": kit.get("name", "")}
    return out


def _first_open_previews(book: dict) -> dict:
    """Before anything is added, the tiles show the sample in its own brand (the pictures it was recorded with), so
    the first screen pictures what "Open the sample" opens. Empty once the person has a source or the sample is open."""
    try:
        if R.sample_open() or store.q("SELECT 1 FROM sources LIMIT 1"):
            return {}
    except Exception:
        return {}
    kid = book.get("kit_id") or ""
    slug = kid.replace("_", "-")
    pics = book.get("pictures") or {}
    out = {}
    for kind in ("deck", "onepager", "visual", "audio"):
        name = next((n for n in sorted(pics) if n.startswith(f"preview-{kind}-{slug}-")), None)
        uri = pics.get(name) if name else None
        if isinstance(uri, str) and uri.startswith("data:image/"):
            out[kind] = {"img": uri, "w": PREVIEW_W, "h": _uri_h(uri), "kit_id": kid, "kit_name": SAMPLE_KIT_NAME}
    return out if len(out) == 4 else {}


_warmed: set = set()


def _warm_faces() -> None:
    """Register every brand's faces with the PDF engine once, on one thread, before pictures are drawn side by side."""
    for k in KITS.list_all():
        key = (k.get("id"), k.get("version"))
        if key in _warmed:
            continue
        try:
            SC.Type(KITS.faces(KITS.get(k["id"])))
            _warmed.add(key)
        except Exception:
            pass


def _parallel(calls: list) -> list:
    """Draw pictures side by side (Pillow and the page raster release the interpreter while they work)."""
    if len(calls) <= 1:
        return [fn(*a) for fn, a in calls]
    _warm_faces()
    import contextvars
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(4, len(calls))) as ex:
        futs = [ex.submit(contextvars.copy_context().run, fn, *a) for fn, a in calls]
        return [f.result() for f in futs]


def _uri_h(uri: str) -> int:
    import base64
    import io
    from PIL import Image
    try:
        return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).height
    except Exception:
        return 0


def thumb(row: dict) -> Optional[str]:
    """An output's first slide or the top of its page, about 480px wide, in its first brand."""
    if row.get("status") != "ready" or not row.get("kit_ids"):
        return None
    kit_id = row["kit_ids"][0]
    try:
        kit = KITS.get(kit_id)
    except Exception:
        return None
    rend = store.one("SELECT content, created_at FROM renders WHERE output_id=? AND kit_id=?", (row["id"], kit_id))
    if not rend:
        return None
    out = store.one("SELECT neutral, source_ids, updated_at FROM outputs WHERE id=?", (row["id"],)) or {}
    stamp = int(float(out.get("updated_at") or 0) * 1000)
    name = f"thumb-{row['id']}-{kit_id}-v{kit.get('version', 1)}-{stamp}-{renderer_sig()}"

    def draw():
        doc = (store.loads(rend["content"], {}) or {}).get("doc") or store.loads(out.get("neutral"), {})
        _s, _b, by_ref = passages_for(store.loads(out.get("source_ids"), []) or [])
        kind = K.kind_of(doc)
        return _png_data(_picture(kind, doc, kit_for_output(row["id"], kit), by_ref, THUMB_W * 2), THUMB_W,
                         0.75 if kind == "onepager" else None)
    return _cached(name, draw)


def sample_pictures() -> dict:
    """Open the shipped sample in the active (temporary) data folder, draw its Studio previews and thumbs in its own
    brand, and return them by cache name, ready to ship in ``notebook.json`` (tools/record_sample.py --pictures)."""
    st = open_sample()
    folder = store.root() / "previews"
    got = {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.txt"))} if folder.exists() else {}
    close_sample()
    return {k: v for k, v in got.items() if k.startswith(("preview-", "thumb-"))} if st else {}


def book_from_folder(meta: dict) -> dict:
    """The active data folder as a sample recording (``notebook.json``): every row the sample needs, the brand's
    files, and ``meta`` (kit_id, outline_id, outputs, source_ids, runs...). tools/record_sample.py writes it."""
    import base64
    out = {"format": 1, "name": SAMPLE_NAME, "label": "Sample", **meta, "tables": {}, "settings": {}, "kit_files": {}}
    for t in SAMPLE_TABLES:
        out["tables"][t] = store.q(f"SELECT * FROM {t}")
    for r in store.q("SELECT key, value FROM settings"):
        if not r["key"].startswith(("audio:", "revise_discarded:")):
            out["settings"][r["key"]] = store.loads(r["value"])
    kid = meta.get("kit_id")
    kdir = KITS.kits_dir() / kid if kid else None
    if kdir and kdir.is_dir():
        for f in sorted(kdir.rglob("*")):
            if f.is_file():
                out["kit_files"][str(f.relative_to(kdir))] = base64.b64encode(f.read_bytes()).decode()
    return out


# ---------------------------------------------------------------- a picked graphic --
# The canvas offers three graphics (the AI lane's ``graphic_options`` job). The person keeps one as its own graphic
# output (PNG, SVG, PDF through the usual export), or adds it to a deck as an exhibit slide (a new version).

def _graphic_option(job_id: str, choice) -> tuple:
    try:
        from . import revise as RV
    except ImportError:  # loaded loose
        import revise as RV  # type: ignore
    job = J.get(job_id) if isinstance(job_id, str) else None
    if not job or job.get("kind") != "graphic_options" or job.get("status") != "done":
        raise ValueError("Those graphics are gone. Make them again.")
    opts = (job.get("result") or {}).get("options") or []
    if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(opts):
        raise ValueError("Pick one of the graphics first.")
    spec = copy.deepcopy(opts[choice].get("spec") or {})
    source_ids = (job.get("result") or {}).get("source_ids") or (job.get("params") or {}).get("source_ids") or []
    return spec, source_ids, RV


def keep_graphic(job_id: str, choice, kit_id: str) -> dict:
    """``{output_id}``: the picked graphic saved as a graphic output in ``kit_id``, re-checked first."""
    spec, source_ids, RV = _graphic_option(job_id, choice)
    kit = KITS.get(kit_id)
    _s, _b, by_ref = passages_for(source_ids)
    try:
        doc = K.clean_visual(spec)
    except ValueError:
        raise ValueError("That graphic didn't come through. Make the graphics again.")
    if not RV._visual_ok(doc, by_ref):
        raise ValueError("A number in that graphic no longer matches your sources. Make the graphics again.")
    oid, t = store.new_id("o"), store.now()
    store.run("INSERT INTO outputs(id, kind, title, source_ids, brief, neutral, kit_ids, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (oid, "visual", doc.get("headline") or "", store.dumps(source_ids), "A graphic from your notebook", store.dumps(doc),
               store.dumps([kit["id"]]), "ready", t, t))
    store.run("INSERT INTO renders(output_id, kit_id, kit_version, content, voice_note, decisions, created_at) VALUES(?,?,?,?,?,?,?)",
              (oid, kit["id"], kit.get("version", 1), store.dumps({"doc": doc, "reverted": []}), "", store.dumps({}), t))
    store.record_made(oid)
    return {"output_id": oid}


def graphic_slide(spec: dict) -> dict:
    """A graphic as a deck exhibit slide: its numbers as bars, its headline as the heading, its takeaway as the note."""
    items = [i for i in spec.get("items") or [] if isinstance(i, dict)][:6]
    bars = [{k: v for k, v in {"label": i.get("label", ""), "value": i.get("value", ""), "ref": i.get("ref"),
                                "accent": i.get("accent")}.items() if v is not None} for i in items]
    refs = list(dict.fromkeys([i.get("ref") for i in items if i.get("ref")] + list(spec.get("takeaway_refs") or [])))
    return {"type": "exhibit", "heading": K.strip_period(spec.get("headline") or ""), "unit": spec.get("unit") or "",
            "bars": bars, "note": spec.get("takeaway") or "", "refs": refs}


def add_graphic(output_id: str, job_id: str, choice) -> dict:
    """Add the picked graphic to a deck as an exhibit slide, before its closing slide, as a new version."""
    spec, _src, RV = _graphic_option(job_id, choice)
    out = _output(output_id)
    if out["kind"] != "deck":
        raise ValueError("Graphics go into a deck. Open a deck first.")
    if spec.get("form") == "timeline" or len(spec.get("items") or []) < 2:
        raise ValueError("Only a graphic with two or more numbers can go into a deck as a chart.")
    _s, _b, by_ref = passages_for(out["source_ids"])
    slide = graphic_slide(spec)
    if not slide["refs"] or any(r not in by_ref for r in slide["refs"]) or RV.check_slide(slide, by_ref)["status"] != "ok":
        raise ValueError("That graphic uses sources this deck doesn't, or a number no longer matches. Make the graphics from this deck's sources.")
    doc = copy.deepcopy(out["neutral"])
    slides = doc.get("slides") or []
    at = len(slides) - 1 if slides and slides[-1].get("type") == "closing" else len(slides)
    slides.insert(at, slide)
    doc["slides"] = slides
    store.add_version(output_id, doc, f"Added a graphic, slide {at + 2}")
    return output_view(output_id)
