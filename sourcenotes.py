"""Source notes: a leave-behind for a deck or a one-pager that shows, for every number and quote on it, the sentence
in the person's own sources it came from.

Nothing here calls a model. The rows are the proof's own claims (``service.proof``: the same trace the pane shows when
a number is hovered), set as letter pages in the brand's faces and colours, and drawn by the browser the designs use
(``htmldeck``: a page that can fetch nothing, measured after it is drawn). A number kept on purpose says so; a number
worked out from two others shows the sum.

    rows(proof)                       -> the entries, grouped by slide
    pages(title, groups, sources, …)  -> [{"html"}] letter pages, paginated here
    export(output_id, kit_id, path)   -> the PDF
"""

from __future__ import annotations

import html
import math
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional

try:
    from . import colors as C
    from . import htmldeck as HD
except ImportError:  # loaded loose
    import colors as C  # type: ignore
    import htmldeck as HD  # type: ignore

KIND = "onepager"  # US Letter at 96 px to the inch, the one-pager's own page
W, H = HD.FORMATS[KIND]["w"], HD.FORMATS[KIND]["h"]
FORMAT_LABEL = "Source notes (PDF)"

# What each trace status reads as beside its figure, in plain words.
STATUS_WORDS = {"exact": "As written", "close": "Same value", "computed": "Worked out", "kept": "Kept on purpose",
                "missing": "Not in the sources", "brief": "From your request"}

CSS = """
.sn{position:absolute;inset:0;background:var(--paper);color:var(--ink);padding:60px 72px 0 72px;font-family:var(--font-body);font-size:14px;line-height:1.45}
.sn-run{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--brand);padding-bottom:9px}
.sn-kicker{font-family:var(--font-heading);font-weight:700;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--brand)}
.sn-pg{font-family:var(--font-heading);font-size:12px;color:var(--muted);letter-spacing:.04em}
.sn-title{font-family:var(--font-heading);font-weight:700;font-size:30px;line-height:1.12;color:var(--brand);margin-top:26px;max-width:600px;letter-spacing:-.005em}
.sn-sum{font-size:14px;color:var(--muted);margin-top:10px;max-width:560px}
.sn-mast{padding-bottom:22px}
.sn-group{display:flex;gap:14px;align-items:baseline;border-top:1px solid var(--rule);padding-top:13px;margin-top:6px}
.sn-group.is-top{border-top:0}
.sn-group.is-bare{padding-top:4px}
.sn-slide{flex:none;width:132px;font-family:var(--font-heading);font-weight:700;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.sn-head{font-family:var(--font-heading);font-weight:700;font-size:15px;line-height:1.25;color:var(--ink)}
.sn-row{display:flex;gap:14px;padding:11px 0 12px 0}
.sn-fig{flex:none;width:132px}
.sn-val{font-family:var(--font-heading);font-weight:700;font-size:24px;line-height:1.05;color:var(--brand);font-variant-numeric:tabular-nums lining-nums;overflow-wrap:anywhere}
.sn-val.is-long{font-size:17px;line-height:1.15}
.sn-val.is-quote{font-size:40px;line-height:.8;padding-top:6px}
.sn-st{font-size:12px;color:var(--muted);margin-top:4px}
.sn-row.is-open .sn-val,.sn-row.is-open .sn-st{color:var(--accent)}
.sn-body{flex:1;min-width:0}
.sn-line{font-size:14px;line-height:1.45}
.sn-line.is-quote{font-style:italic}
.sn-line mark{background:var(--brand-tint);color:var(--ink);font-weight:700;padding:1px 1px;border-radius:2px}
.sn-math{font-family:var(--font-heading);font-weight:700;font-size:13px;color:var(--ink);margin-bottom:3px;font-variant-numeric:tabular-nums lining-nums}
.sn-src{font-size:12px;color:var(--muted);margin-top:4px}
.sn-src b{font-family:var(--font-heading);font-weight:700;color:var(--brand);margin-right:5px}
.sn-list{border-top:2px solid var(--brand);margin-top:14px;padding-top:12px}
.sn-list h2{font-family:var(--font-heading);font-weight:700;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--brand);margin-bottom:6px}
.sn-item{display:flex;gap:10px;padding:4px 0;font-size:13px;line-height:1.4}
.sn-item b{flex:none;width:18px;font-family:var(--font-heading);font-weight:700;color:var(--brand)}
.sn-item span{color:var(--muted)}
.sn-foot{position:absolute;left:72px;right:72px;bottom:34px;display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--rule);padding-top:10px;font-size:12px;color:var(--muted)}
.sn-foot img{height:24px;width:auto;display:block}
"""

_e = lambda s: html.escape(str(s or ""), quote=True)


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _is_noted(c: dict) -> bool:
    return c.get("kind") in ("number", "money", "count", "percent", "quote") or bool(c.get("value"))


def rows(pr: dict) -> list:
    """The proof's claims as groups in reading order: ``[{"frame", "label", "title", "entries": [...]}]``. A claim that
    several slides repeat is listed once, under the first, with the others named."""
    kind = pr.get("kind") or "onepager"
    frames = {int(f.get("i") or 0): f for f in pr.get("slides") or []}
    groups: dict = {}
    for _cid, c in (pr.get("claims") or {}).items():
        if not isinstance(c, dict) or not _is_noted(c) or c.get("status") == "brief":
            continue
        on = sorted(int(x) for x in (c.get("slides") or [0]))
        first = on[0] if on else 0
        line = c.get("line") if isinstance(c.get("line"), dict) else None
        m = c.get("math") if isinstance(c.get("math"), dict) else None
        entry = {"value": _clean(c.get("value")), "quote": c.get("kind") == "quote", "status": c.get("status") or "missing",
                 "before": _clean((line or {}).get("before")), "match": _clean((line or {}).get("match")),
                 "after": _clean((line or {}).get("after")), "math": _clean((m or {}).get("text")),
                 "n": c.get("source_n"), "source": _clean(c.get("source")), "locator": _clean(c.get("locator")).strip("“”\""),
                 "also": [f + 1 for f in on[1:]] if kind == "deck" else []}
        g = groups.setdefault(first, {"frame": first, "label": f"Slide {first + 1}" if kind == "deck" else "",
                                      "title": _clean((frames.get(first) or {}).get("title")).rstrip(" ,;:"), "entries": []})
        g["entries"].append(entry)
    return [groups[k] for k in sorted(groups)]


def summary(groups: list, n_sources: int, kind: str = "deck") -> str:
    """One factual sentence for the top of the notes: what was counted and how it stands."""
    es = [e for g in groups for e in g["entries"]]
    nums, quotes = [e for e in es if not e["quote"]], [e for e in es if e["quote"]]
    kept = sum(1 for e in es if e["status"] == "kept")
    opens = sum(1 for e in es if e["status"] == "missing")
    what = " and ".join(x for x in (_plural(len(nums), "number") if nums else "", _plural(len(quotes), "quote") if quotes else "") if x)
    if not what:
        return "This piece carries no numbers or quotes to trace."
    where = "this deck" if kind == "deck" else "this page"
    s = f"{what[0].upper() + what[1:]} on {where}, from {_plural(n_sources, 'source')}. Each is shown beside the sentence it came from."
    if kept:
        s += f" {_plural(kept, 'figure')} {'was' if kept == 1 else 'were'} kept on purpose and {'is' if kept == 1 else 'are'} not in the sources."
    if opens:
        s += f" {_plural(opens, 'figure')} {'is' if opens == 1 else 'are'} not in the sources."
    return s


# ---------------------------------------------------------------- setting the pages --

def _entry_html(e: dict) -> str:
    open_ = e["status"] in ("missing", "kept")
    if e["quote"]:
        fig = '<div class="sn-val is-quote">“</div>'
    else:
        fig = f'<div class="sn-val{" is-long" if len(e["value"]) > 9 else ""}">{_e(e["value"])}</div>'
    fig += f'<div class="sn-st">{_e(STATUS_WORDS.get(e["status"], "Checked"))}</div>'
    body = ""
    if e["math"]:
        body += f'<div class="sn-math">{_e(e["math"])}</div>'
    if e["before"] or e["match"] or e["after"]:
        if e["quote"]:
            said = e["match"] or e["before"]
            a, b = ("", "") if re.search(r"[“”\"]", said) else ("“", "”")  # the source's sentence may carry its own marks
            body += f'<p class="sn-line is-quote">{a}{_e(said)}{b}</p>'
        else:
            mark = f'<mark>{_e(e["match"])}</mark>' if e["match"] else ""
            sp_a = " " if e["before"] and e["match"] and not e["before"].endswith(("$", "(", "“", "-", "–")) else ""
            sp_b = " " if e["after"] and (e["match"] or e["before"]) and not re.match(r"[.,;:!?%)’”]", e["after"]) else ""
            body += f'<p class="sn-line">{_e(e["before"])}{sp_a}{mark}{sp_b}{_e(e["after"])}</p>'
    elif open_:
        body += '<p class="sn-line">No sentence in the sources holds this figure.</p>'
    if e["source"]:
        where = _e(e["source"]) + (f", {_e(e['locator'])}" if e["locator"] else "")
        lead = "Closest: " if e["status"] == "missing" else ""
        also = (" · also on slide" + ("s " if len(e["also"]) > 1 else " ") + ", ".join(map(str, e["also"]))) if e["also"] else ""
        body += f'<p class="sn-src">{"<b>" + _e(e["n"]) + "</b>" if e["n"] else ""}{lead}{where}{_e(also)}</p>'
    return f'<div class="sn-row{" is-open" if open_ else ""}"><div class="sn-fig">{fig}</div><div class="sn-body">{body}</div></div>'


def _lines(text: str, per_line: int) -> int:
    return max(1, math.ceil(len(text) / per_line))


def _entry_h(e: dict, per_line: int) -> float:
    sent = " ".join(x for x in (e["before"], e["match"], e["after"]) if x) or "No sentence in the sources holds this figure."
    right = _lines(sent, per_line) * 20.5 + (22 if e["math"] else 0)
    if e["source"]:
        right += 4 + _lines(e["source"] + e["locator"] + ("x" * 22 if e["also"] else ""), int(per_line * 1.15)) * 17
    left = (38 if e["quote"] else 26 * _lines(e["value"], 9 if len(e["value"]) <= 9 else 13)) + 22
    return 23 + max(left, right)


def _group_h(g: dict, per_line: int) -> float:
    if not g["label"]:
        return 12
    return 20 + _lines(g["title"] or "x", int(per_line * 0.8)) * 19 + 6


def paginate(groups: list, sources: list, first_room: float, room: float, per_line: int = 70) -> list:
    """``[[block, ...], ...]``: one list of blocks per page. A block is ``("group", g, top)``, ``("entry", e)`` or
    ``("sources", rows)``. A slide's name never sits alone at the foot of a page, and an entry is never split."""
    pages, cur, left = [], [], first_room

    def turn():
        nonlocal cur, left
        pages.append(cur)
        cur, left = [], room

    for g in groups:
        need = _group_h(g, per_line) + (_entry_h(g["entries"][0], per_line) if g["entries"] else 0)
        if cur and need > left:
            turn()
        cur.append(("group", g, not cur))
        left -= _group_h(g, per_line)
        for k, e in enumerate(g["entries"]):
            h = _entry_h(e, per_line)
            if k and h > left:
                turn()
                cur.append(("group", {**g, "title": g["title"], "cont": True}, True))
                left -= _group_h(g, per_line)
            cur.append(("entry", e))
            left -= h
    if sources:
        h = 52 + sum(8 + 18.5 * _lines(r["title"] + " " + r["where"], int(per_line * 1.2)) for r in sources)
        if cur and h > left:
            turn()
        cur.append(("sources", sources))
    if cur or not pages:
        pages.append(cur)
    return pages


def _foot(brand_name: str, date: str, logo: bool = True) -> str:
    left = " · ".join(x for x in (_e(brand_name), _e(date)) if x)
    mark = f'<img src="{HD._LOGO}" alt="">' if logo else ""
    return f'<div class="sn-foot"><span>{left}</span>{mark}</div>'


def pages(title: str, groups: list, sources: list, date: str = "", brand_name: str = "", kind: str = "deck",
          per_line: int = 70, squeeze: float = 1.0, logo: bool = True) -> list:
    """The notes as letter pages, ``[{"html", "notes"}]``, the shape ``htmldeck.render`` draws. ``squeeze`` under 1
    gives every page less room (the caller lowers it when a drawn page ran over)."""
    title = _clean(title) or "Untitled"
    sm = summary(groups, len(sources), kind)
    mast_h = 44 + 26 + _lines(title, 34) * 34 + 10 + _lines(sm, 76) * 20.5 + 22
    room = (H - 60 - 34 - 92) * squeeze  # the page less its top margin, running head and foot
    laid = paginate(groups, sources, room - (mast_h - 34), room, per_line)
    out = []
    for n, blocks in enumerate(laid, 1):
        run = (f'<div class="sn-run"><span class="sn-kicker">Source notes</span>'
               f'<span class="sn-pg">{n} / {len(laid)}</span></div>')
        mast = (f'<div class="sn-mast"><h1 class="sn-title">{_e(title)}</h1><p class="sn-sum">{_e(sm)}</p></div>' if n == 1 else "")
        body = []
        for b in blocks:
            if b[0] == "group":
                g = b[1]
                if not g["label"]:  # a one-pager is one frame: its name is already the title above
                    body.append(f'<div class="sn-group is-bare{" is-top" if n > 1 else ""}"></div>')
                    continue
                lab = _e(g["label"]) + (", cont." if g.get("cont") else "")
                body.append(f'<div class="sn-group{" is-top" if b[2] and n > 1 else ""}"><span class="sn-slide">{lab}</span>'
                            f'<span class="sn-head">{_e(g["title"])}</span></div>')
            elif b[0] == "entry":
                body.append(_entry_html(b[1]))
            else:
                items = "".join(f'<div class="sn-item"><b>{_e(r["n"])}</b><p>{_e(r["title"])}'
                                + (f' <span>{_e(r["where"])}</span>' if r["where"] else "") + "</p></div>" for r in b[1])
                body.append(f'<div class="sn-list"><h2>Sources</h2>{items}</div>')
        out.append({"html": f'<div class="sn">{run}{mast}{"".join(body)}{_foot(brand_name, date, logo)}</div>', "notes": ""})
    return out


def source_rows(index_rows: list) -> list:
    """``layout.source_index``'s rows as the closing list: ``[{"n", "title", "where"}]``."""
    out = []
    for r in index_rows or []:
        locs = [_clean(x).strip("“”\"") for x in (r.get("locators") or []) if _clean(x)]
        where = ", ".join(locs[:6]) + (f", and {len(locs) - 6} more" if len(locs) > 6 else "")
        out.append({"n": r.get("n"), "title": _clean(r.get("title")) or "Source", "where": where})
    return out


# ---------------------------------------------------------------- drawing --

def on_paper(brand: dict) -> dict:
    """The brand for a page that gets printed: a brand whose ground is dark is turned over (its dark becomes the
    ink of the headings on white), so the notes never print a page of solid colour. A light brand is unchanged."""
    v = dict(brand.get("vars") or {})
    paper = C.norm(v.get("--paper") or "") or "#ffffff"
    if C.is_light(paper):
        return brand
    accent = C.norm(v.get("--accent") or "") or paper
    v.update({"--paper": "#ffffff", "--ink": "#1a1a1a", "--brand": paper, "--brand-tint": C.mix("#ffffff", paper, 0.10),
              "--brand-mid": C.mix("#ffffff", paper, 0.55), "--muted": "#5c5c5c", "--rule": "#c8c8c8",
              "--accent": accent if C.contrast(accent, "#ffffff") >= 3 else paper})
    return {**brand, "vars": v}



OVER = ("outside", "cut", "cut-sideways", "overlap", "unsafe")


def draw(title: str, groups: list, sources: list, css: str, logo: str, out_dir, date: str = "", brand_name: str = "",
         kind: str = "deck", pdf: bool = True) -> dict:
    """Set the pages and draw them. If a drawn page ran past its foot, set them again with less on each page (twice at
    most). Returns ``{"pages", "png", "pdf", "problems"}``: ``problems`` is what the measuring script still found."""
    got, laid = {"png": [], "pdf": None, "problems": []}, []
    for squeeze, per_line in ((1.0, 70), (0.9, 60), (0.76, 50)):
        laid = pages(title, groups, sources, date, brand_name, kind, per_line=per_line, squeeze=squeeze, logo=bool(logo))
        got = HD.render(laid, css + CSS, out_dir, logo, pdf=False, kind=KIND)
        got["problems"] = [p for p in got["problems"] if p["kind"] in OVER]
        if not got["problems"]:
            break
        for f in Path(out_dir).glob("s*.png"):  # the next setting may have fewer or more pages
            f.unlink()
    if pdf:
        path = Path(out_dir) / "source-notes.pdf"
        HD.export_pdf(laid, css + CSS, path, logo, KIND)
        got["pdf"] = str(path) if path.exists() else None
    return {**got, "pages": laid}


def _service():
    try:
        from . import service as S
    except ImportError:  # loaded loose
        import service as S  # type: ignore
    return S


def export(output_id: str, kit_id: str, path) -> str:
    """The source notes for one output in one brand, as a PDF at ``path``."""
    S = _service()
    try:
        from . import designs as DS, layout as L
    except ImportError:  # loaded loose
        import designs as DS, layout as L  # type: ignore
    if not HD.browser_available():
        raise ValueError(HD.B.NOT_FOUND)
    pr = S.proof(output_id, kit_id)
    if pr.get("status") != "ready":
        raise ValueError("That kit's version isn't ready yet.")
    out = S._output(output_id)
    kit = S.kit_for_output(output_id, S.KITS.get(kit_id))
    _s, _b, by_ref = S.passages_for(out["source_ids"])
    _idx, index_rows = L.source_index(S._doc_for(output_id, kit), by_ref)
    brand, _text, logo = DS.brand_for(kit)
    work = Path(tempfile.mkdtemp(prefix="imprint-notes-"))
    try:
        printed = on_paper(brand)
        if printed is not brand:
            logo = ""  # the mark was chosen for the brand's dark ground; on white it may not show, so it is left off
        got = draw(pr.get("title") or out.get("title") or "", rows(pr), source_rows(index_rows), HD.kit_css(printed, KIND), logo, work,
                   date=S.out_date(out), brand_name=kit.get("org") or kit.get("name") or "", kind=pr.get("kind") or "deck")
        if not got["pdf"]:
            raise ValueError("The file could not be made. Try again.")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(got["pdf"], path)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return str(path)
