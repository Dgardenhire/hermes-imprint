"""The proof tree: one structure per layout family, shared by the pane preview and the HTML export.

``tree`` turns the content, the kit's palette and its resolved fonts into plain nodes:
``{"t": tag, "c": class, "x": text}`` or ``{"t": tag, "c": class, "k": [children]}``. The pane walks the
nodes into React elements (tags from a fixed list, text only as text), and ``render_html`` writes the
same nodes as markup with the same stylesheet, so the HTML export is the preview. The PDF follows the
same families in reportlab (render_pdf.py).

Kit tokens become CSS variables on the page node (``--k-paper``, ``--k-head-font`` ...), scoped to that
proof, so a kit never restyles the plugin around it.
"""

from __future__ import annotations

import re
from typing import Optional

try:
    from . import content as K
except ImportError:  # loaded loose
    import content as K  # type: ignore

TAGS = {"div", "section", "header", "footer", "h1", "h2", "h3", "p", "span", "sup", "ul", "ol", "li", "img",
        "blockquote", "strong", "em", "figure", "figcaption", "hr", "small"}


def n(t: str, c: str = "", x: Optional[str] = None, k: Optional[list] = None, **attrs) -> dict:
    node = {"t": t}
    if c:
        node["c"] = c
    if x is not None:
        node["x"] = x
    if k is not None:
        node["k"] = [i for i in k if i]
    if attrs:
        node["a"] = attrs
    return node


def source_index(doc: dict, passages: dict) -> tuple:
    """Number the sources in order of first citation. Returns ``(ref_to_number, footer_rows)``."""
    order, rows, by_ref = {}, [], {}
    refs = []
    if K.kind_of(doc) != "onepager":  # decks and scripts: in reading order
        for _p, _t, rs in K.field_texts(doc):
            refs += [r for r in rs if r]
    for sec in doc.get("sections") or []:
        refs += sec.get("refs") or []
    for key in ("stat", "quote"):
        if doc.get(key) and doc[key].get("ref"):
            refs.append(doc[key]["ref"])
    for p in doc.get("points") or []:
        if p.get("ref"):
            refs.append(p["ref"])
    refs += doc.get("dek_refs") or []
    for r in refs:
        info = passages.get(r)
        if not info:
            continue
        sid = info.get("source_id")
        if sid not in order:
            order[sid] = len(order) + 1
            rows.append({"n": order[sid], "title": info.get("source_title", "Source"), "locators": []})
        row = rows[order[sid] - 1]
        if info.get("locator") and info["locator"] not in row["locators"]:
            row["locators"].append(info["locator"])
        by_ref[r] = order[sid]
    return by_ref, rows


def _marks(refs: list, idx: dict) -> Optional[dict]:
    nums = sorted({idx[r] for r in refs or [] if r in idx})
    if not nums:
        return None
    return n("sup", "ip-ref", ",".join(str(i) for i in nums))


def _para(text: str, refs: list, idx: dict, cls: str = "ip-body") -> dict:
    return n("p", cls, k=[n("span", "", text), _marks(refs, idx)])


def tokens(kit: dict, pal: dict, faces: dict) -> dict:
    t = kit.get("type") or {}
    head = faces.get("heading") or {}
    body = faces.get("body") or {}
    return {
        "--k-paper": pal["paper"], "--k-ink": pal["ink"], "--k-head": pal["head"], "--k-accent": pal["accent"],
        "--k-accent-text": pal["accent_text"], "--k-rule": pal["rule"],
        "--k-band": pal.get("band") or pal["head"], "--k-band-text": pal.get("band_text") or pal["paper"],
        "--k-fill": pal.get("fill") or "transparent", "--k-fill-text": pal.get("fill_text") or pal["ink"],
        "--k-highlight": pal.get("highlight") or "transparent",
        "--k-head-font": head.get("css") or "sans-serif", "--k-body-font": body.get("css") or "serif",
        "--k-head-weight": str(head.get("weight") or 700), "--k-head-style": head.get("style") or "normal",
        "--k-head-case": "uppercase" if (t.get("heading") or {}).get("case") == "upper" else "none",
        "--k-head-track": "0.03em" if (t.get("heading") or {}).get("case") == "upper" else "-0.01em",
        "--k-scale": str(t.get("scale") or 1.25),
        "--k-gap": {"airy": "1.35", "medium": "1", "dense": "0.78"}.get(kit.get("density"), "1"),
    }


def _sources_footer(kit: dict, rows: list) -> Optional[dict]:
    if not (kit.get("rules") or {}).get("sources") or not rows:
        return None
    items = [n("li", "", f"{r['title']}" + (f", {', '.join(r['locators'][:6])}" if r["locators"] else ""), id=f"ip-src-{r['n']}")
             for r in rows]
    return n("div", "ip-sources", k=[n("h3", "ip-sources-head", "Sources"), n("ol", "ip-sources-list", k=items)])


def _required(kit: dict) -> Optional[dict]:
    req = (kit.get("rules") or {}).get("required") or []
    if not req:
        return None
    return n("div", "ip-required", k=[n("p", "", r) for r in req])


def _org_line(kit: dict, date: str, logo: Optional[str], cls: str = "ip-org") -> dict:
    show_date = (kit.get("rules") or {}).get("date", True)
    return n("div", cls, k=[
        n("img", "ip-logo", src=logo) if logo else None,
        n("span", "ip-org-name", kit.get("org") or "") if kit.get("org") else None,
        n("span", "ip-date", date) if show_date and date else None,
    ])


def _stat(doc: dict, idx: dict, cls: str = "ip-stat") -> Optional[dict]:
    st = doc.get("stat")
    if not st:
        return None
    return n("div", cls, k=[n("div", "ip-stat-value", st["value"]),
                            n("p", "ip-stat-label", k=[n("span", "", st.get("label", "")), _marks([st.get("ref")], idx)])])


def _points(doc: dict, idx: dict, ordered: bool = False, head: Optional[str] = None) -> Optional[dict]:
    pts = doc.get("points") or []
    if not pts:
        return None
    lst = n("ol" if ordered else "ul", "ip-points", k=[n("li", "", k=[n("span", "", p["text"]), _marks([p.get("ref")], idx)]) for p in pts])
    return n("div", "ip-points-wrap", k=[n("h3", "ip-points-head", head) if head else None, lst])


def _quote(doc: dict, idx: dict) -> Optional[dict]:
    q = doc.get("quote")
    if not q:
        return None
    return n("blockquote", "ip-quote", k=[n("p", "ip-quote-text", k=[n("span", "", f"“{q['text']}”"), _marks([q.get("ref")], idx)]),
                                          n("p", "ip-quote-who", q["who"]) if q.get("who") else None])


def _menu(items: list) -> Optional[dict]:
    """Items with prices as a list a reader can scan: name, a dotted leader, the price, a note under it."""
    if not items:
        return None
    rows = []
    for it in items:
        rows.append(n("li", "ip-menu-item", k=[
            n("p", "ip-menu-line", k=[n("span", "ip-menu-name", it.get("name", "")),
                                      n("span", "ip-menu-dots") if it.get("price") else None,
                                      n("span", "ip-menu-price", it["price"]) if it.get("price") else None]),
            n("p", "ip-menu-note", it["note"]) if it.get("note") else None]))
    return n("ul", "ip-menu", k=rows)


def _section(s: dict, idx: dict, cls: str = "ip-section") -> dict:
    items = s.get("items") or []
    body = _para(s["body"], s.get("refs"), idx) if s.get("body") else None
    if items and body is None:  # the section's citation sits on its heading when it is only a list
        head = n("h2", "ip-h2", k=[n("span", "", s.get("heading", "")), _marks(s.get("refs"), idx)])
    else:
        head = n("h2", "ip-h2", s.get("heading", ""))
    return n("section", cls, k=[head, body, _menu(items)])


def _sections(doc: dict, idx: dict, cls: str = "ip-sections", runin: bool = False) -> dict:
    out = []
    for s in doc.get("sections") or []:
        if s.get("items"):
            out.append(_section(s, idx))
            continue
        if runin:
            out.append(n("p", "ip-body ip-runin", k=[n("strong", "ip-runin-head", s["heading"] + ". " if s.get("heading") else ""),
                                                      n("span", "", s["body"]), _marks(s.get("refs"), idx)]))
        else:
            out.append(_section(s, idx))
    return n("div", cls, k=out)


def _next(doc: dict, cls: str = "ip-next") -> Optional[dict]:
    return n("p", cls, doc["next"]) if doc.get("next") else None


def logo_on(logo, place: str) -> Optional[str]:
    """The logo for one ground. ``logo`` is a data URL, or ``{"paper": url, "band": url}`` when the mark has a
    knocked-out or reversed version for the band (logos.py)."""
    if isinstance(logo, dict):
        return logo.get(place) or logo.get("paper")
    return logo


def uses_scene_page(kit: dict) -> bool:
    """The studio kits and imported brands set their one-pager as a scene in their design system; the earlier
    starters keep their HTML layout families."""
    if kit.get("id") == "draft":  # the import bench's sample page keeps its own family until the brand is saved
        return False
    return bool(kit.get("studio") or kit.get("origin") == "import")


NUM_LEAD = re.compile(r"^\s*([$£€]?\d[\d,]*(?:\.\d+)?\s*(?:%|percent\b|million\b|billion\b)?)\s+(.+)$")


def page_spec(doc: dict, kit: dict, passages: dict, date: str = "", idx: Optional[dict] = None, rows: Optional[list] = None) -> dict:
    """What the page scene draws: the one-pager's fields, its source marks, figures from the points that lead with a
    number, and the numbered source rows."""
    if idx is None or rows is None:
        idx, rows = source_index(doc, passages)

    def mk(refs):
        nums = sorted({idx[r] for r in refs or [] if r in idx})
        return ",".join(str(i) for i in nums)

    rules = kit.get("rules") or {}
    figs = []
    for pt in doc.get("points") or []:
        m = NUM_LEAD.match(pt.get("text") or "")
        if m:
            figs.append((m.group(1).strip(), m.group(2).strip(), mk([pt.get("ref")])))
    st = doc.get("stat")
    q = doc.get("quote")
    return {"title": doc.get("title", ""), "dek": doc.get("dek", ""), "dek_marks": mk(doc.get("dek_refs")),
            "org": kit.get("org") or "", "date": date if rules.get("date", True) else "",
            "stat": {"value": st["value"], "label": st.get("label", ""), "marks": mk([st.get("ref")])} if st else None,
            "figures": figs[:3],
            "sections": [{"heading": sc.get("heading", ""), "body": sc.get("body", ""), "marks": mk(sc.get("refs"))}
                         for sc in doc.get("sections") or []],
            "quote": {"text": q["text"], "who": q.get("who", ""), "marks": mk([q.get("ref")])} if q else None,
            "chart": {"title": (doc.get("chart") or {}).get("title", ""), "unit": (doc.get("chart") or {}).get("unit", ""),
                      "bars": [(b.get("label", ""), b.get("value", ""), _num(b.get("value", "")), mk([b.get("ref")]))
                               for b in (doc.get("chart") or {}).get("bars") or []],
                      "hi": next((i for i, b in enumerate((doc.get("chart") or {}).get("bars") or []) if b.get("accent") is True), None)}
            if (doc.get("chart") or {}).get("bars") else None,
            "next": doc.get("next", ""),
            "sources": [r["title"] + (", " + ", ".join(r["locators"][:4]) if r["locators"] else "") for r in rows]
            if rules.get("sources", True) else []}


def _num(v: str):
    try:
        from . import systems as SY
    except ImportError:  # loaded loose
        import systems as SY  # type: ignore
    return SY.parse_value(v)


def page_scene(doc: dict, kit: dict, pal: dict, faces: dict, passages: dict, date: str = "", idx: Optional[dict] = None,
               rows: Optional[list] = None) -> tuple:
    """``(scene, type)`` for a one-pager set as a scene, or ``(None, None)`` for a kit that keeps its HTML family."""
    if not uses_scene_page(kit) or K.kind_of(doc) != "onepager":
        return None, None
    try:
        from . import render_deck as RD
        from . import scene as SC
        from . import systems as SY
    except ImportError:  # loaded loose
        import render_deck as RD  # type: ignore
        import scene as SC  # type: ignore
        import systems as SY  # type: ignore
    ty = SC.Type(RD.faces_for(kit, faces))
    sysm = SY.for_kit(kit, pal, ty, RD.system_of(kit))
    return sysm.page(page_spec(doc, kit, passages, date, idx, rows)), ty


def tree(doc: dict, kit: dict, pal: dict, faces: dict, passages: dict, date: str = "", logo=None) -> dict:
    kind = K.kind_of(doc)
    if kind == "onepager" and uses_scene_page(kit):
        try:
            from . import scene as SC
        except ImportError:  # loaded loose
            import scene as SC  # type: ignore
        sc, ty = page_scene(doc, kit, pal, faces, passages, date)
        logos = logo if isinstance(logo, dict) else ({"paper": logo, "band": logo} if logo else None)
        return SC.nodes(sc, ty, cls="ip-scene ip-onepage", logos=logos)
    if kind in ("deck", "visual"):
        pass  # scenes pick the logo for each ground themselves
    else:
        logo = logo_on(logo, "band" if (kit.get("layout") or "banner") == "banner" and kind == "onepager" else "paper")
    if kind == "deck":
        try:
            from . import render_deck as RD
        except ImportError:  # loaded loose
            import render_deck as RD  # type: ignore
        return RD.deck_tree(doc, kit, pal, faces, passages, date, logo_urls=logo if isinstance(logo, dict) else {"paper": logo, "band": logo})[0]
    if kind == "visual":
        try:
            from . import render_graphic as RG
        except ImportError:  # loaded loose
            import render_graphic as RG  # type: ignore
        idx, _rows = source_index(doc, passages)
        return RG.tree(doc, kit, pal, faces, idx, passages, logo_urls=logo if isinstance(logo, dict) else {"paper": logo})[0]
    if kind == "audio":
        return script_tree(doc, kit, pal, faces, passages, date, logo)
    idx, rows = source_index(doc, passages)
    layout = kit.get("layout") or "banner"
    build = {"banner": _banner, "headline": _headline, "margin": _margin, "letter": _letter, "bulletin": _bulletin,
             "flyer": _flyer, "report": _report}.get(layout, _banner)
    body = build(doc, kit, idx, rows, date, logo)
    return n("div", f"ip-page ip-{layout}" + (" ip-dark" if pal.get("dark") else ""), k=body, style=tokens(kit, pal, faces))


def _banner(doc, kit, idx, rows, date, logo):
    return [
        n("header", "ip-band", k=[_org_line(kit, date, logo, "ip-org ip-org-band"),
                                  n("h1", "ip-title ip-title-band", doc["title"])]),
        n("div", "ip-inner", k=[
            n("p", "ip-dek", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
            n("div", "ip-banner-grid", k=[
                n("div", "ip-banner-side", k=[_stat(doc, idx, "ip-stat ip-stat-fill"), _points(doc, idx, head="At a glance")]),
                _sections(doc, idx, "ip-sections ip-banner-main"),
            ]),
            _quote(doc, idx),
            _next(doc),
            n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
        ]),
    ]


def _headline(doc, kit, idx, rows, date, logo):
    return [n("div", "ip-inner", k=[
        _org_line(kit, date, logo),
        n("h1", "ip-title ip-title-big", k=[n("span", "ip-hl", doc["title"])]),
        n("div", "ip-head-row", k=[
            n("p", "ip-dek ip-dek-big", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
            _stat(doc, idx, "ip-stat ip-stat-inline"),
        ]),
        _sections(doc, idx, "ip-sections ip-tiles"),
        _points(doc, idx),
        _quote(doc, idx),
        _next(doc),
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])]


def _margin(doc, kit, idx, rows, date, logo):
    return [n("div", "ip-inner ip-margin-grid", k=[
        n("div", "ip-rail", k=[_stat(doc, idx, "ip-stat ip-stat-rail"), _points(doc, idx, head="Key points"), _quote(doc, idx),
                                _sources_footer(kit, rows)]),
        n("div", "ip-main", k=[
            _org_line(kit, date, logo),
            n("h1", "ip-title", doc["title"]),
            n("p", "ip-dek", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
            _sections(doc, idx),
            _next(doc),
            n("footer", "ip-foot", k=[_required(kit)]),
        ]),
    ])]


def _letter(doc, kit, idx, rows, date, logo):
    show_date = (kit.get("rules") or {}).get("date", True)
    memo = [n("div", "ip-memo-row", k=[n("span", "ip-memo-label", "Re"), n("span", "ip-memo-value", doc["title"])])]
    if show_date and date:
        memo.append(n("div", "ip-memo-row", k=[n("span", "ip-memo-label", "Date"), n("span", "ip-memo-value", date)]))
    if kit.get("org"):
        memo.append(n("div", "ip-memo-row", k=[n("span", "ip-memo-label", "From"), n("span", "ip-memo-value", kit["org"])]))
    return [n("div", "ip-inner ip-letter-col", k=[
        n("div", "ip-letterhead", k=[n("img", "ip-logo", src=logo) if logo else None]),
        n("div", "ip-memo", k=memo),
        n("hr", "ip-memo-rule"),
        n("p", "ip-dek ip-lead", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
        _sections(doc, idx, "ip-sections ip-letter-body", runin=True),
        _stat(doc, idx, "ip-stat ip-stat-letter"),
        _points(doc, idx, ordered=True, head="Findings"),
        _quote(doc, idx),
        _next(doc, "ip-next ip-signoff"),
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])]


def _bulletin(doc, kit, idx, rows, date, logo):
    return [n("div", "ip-inner", k=[
        n("header", "ip-nameplate", k=[_org_line(kit, date, logo), n("h1", "ip-title", doc["title"]),
                                       n("p", "ip-dek", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)])]),
        n("div", "ip-bulletin-grid", k=[
            n("div", "ip-bulletin-side", k=[_stat(doc, idx, "ip-stat ip-stat-fill"), _points(doc, idx, head="This week")]),
            _sections(doc, idx, "ip-sections ip-bulletin-cols"),
        ]),
        _quote(doc, idx),
        _next(doc),
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])]


def _flyer(doc, kit, idx, rows, date, logo):
    """A flyer or a menu: a centered head, the one number as a stamp, the offer in columns, and the call to
    action on the kit's band at the foot of the sheet, where a reader's eye ends."""
    st = doc.get("stat")
    pts = doc.get("points") or []
    return [n("div", "ip-inner ip-flyer", k=[
        n("header", "ip-flyer-head", k=[
            _org_line(kit, date, logo, "ip-org ip-org-center"),
            n("h1", "ip-title ip-title-flyer", doc["title"]),
            n("p", "ip-dek ip-flyer-dek", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
        ]),
        n("div", "ip-flyer-stamp", k=[n("div", "ip-stat-value", st["value"]),
                                      n("p", "ip-stat-label", k=[n("span", "", st.get("label", "")), _marks([st.get("ref")], idx)])])
        if st else None,
        _sections(doc, idx, "ip-sections ip-flyer-cols"),
        n("ul", "ip-flyer-points", k=[n("li", "", k=[n("span", "", p["text"]), _marks([p.get("ref")], idx)]) for p in pts]) if pts else None,
        _quote(doc, idx),
        n("p", "ip-flyer-cta", doc["next"]) if doc.get("next") else None,
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])]


def _report(doc, kit, idx, rows, date, logo):
    """A report page: title and summary, a row of key figures, then each section with its heading set in
    the margin beside it, and the quote pulled out between rules."""
    st = doc.get("stat")
    figs = []
    if st:
        figs.append(n("div", "ip-figure ip-figure-lead", k=[n("div", "ip-stat-value", st["value"]),
                                                           n("p", "ip-stat-label", k=[n("span", "", st.get("label", "")), _marks([st.get("ref")], idx)])]))
    for p in (doc.get("points") or [])[:3]:
        figs.append(n("div", "ip-figure", k=[n("p", "", k=[n("span", "", p["text"]), _marks([p.get("ref")], idx)])]))
    rows_out = []
    for s in doc.get("sections") or []:
        rows_out.append(n("section", "ip-report-row", k=[
            n("h2", "ip-h2 ip-sidehead", s.get("heading", "")),
            n("div", "ip-report-text", k=[_para(s["body"], s.get("refs"), idx) if s.get("body") else None, _menu(s.get("items") or [])])]))
    return [n("div", "ip-inner ip-report", k=[
        _org_line(kit, date, logo),
        n("h1", "ip-title ip-title-report", doc["title"]),
        n("p", "ip-dek ip-report-dek", k=[n("span", "", doc.get("dek", "")), _marks(doc.get("dek_refs"), idx)]),
        n("div", "ip-figures", k=figs) if figs else None,
        n("div", "ip-report-body", k=rows_out),
        n("div", "ip-pull", k=[_quote(doc, idx)]) if doc.get("quote") else None,
        _next(doc),
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])]


# ---------------------------------------------------------------- deck --
# Decks and graphics are composed as scenes in render_deck / render_graphic (systems.py); ``tree`` hands them over.


# ---------------------------------------------------------------- audio script --

def script_minutes(doc: dict) -> float:
    words = len(re.findall(r"\w+", K.script_text(doc)))
    return round(words / 150.0, 1)


def script_tree(doc: dict, kit: dict, pal: dict, faces: dict, passages: dict, date: str = "", logo: Optional[str] = None) -> dict:
    """The narrator's script, set in the kit: signposts as heads, each passage cited, the recap last."""
    idx, rows = source_index(doc, passages)
    segs = []
    for i, seg in enumerate(doc.get("segments") or []):
        segs.append(n("section", "ip-seg", k=[
            n("h2", "ip-seg-head", k=[n("span", "ip-seg-num", f"{i + 1:02d}"), n("span", "", seg.get("heading", ""))]),
            _para(seg.get("text", ""), seg.get("refs"), idx, "ip-body ip-seg-text")]))
    mins = script_minutes(doc)
    return n("div", "ip-page ip-script" + (" ip-dark" if pal.get("dark") else ""), k=[n("div", "ip-inner", k=[
        _org_line(kit, date, logo),
        n("p", "ip-script-kicker", f"Audio brief, about {max(1, round(mins))} min"),
        n("h1", "ip-title", doc.get("title", "")),
        n("div", "ip-segs", k=segs),
        n("div", "ip-recap", k=[n("h3", "ip-points-head", "Recap"), n("p", "", doc.get("recap", ""))]) if doc.get("recap") else None,
        n("footer", "ip-foot", k=[_sources_footer(kit, rows), _required(kit)]),
    ])], style=tokens(kit, pal, faces))


# ---------------------------------------------------------------- traced numbers --
# In the pane, every number that was checked against the sources becomes its own focusable span with its
# source number right after it, so the reader sees where each figure came from and can open its trace card.
# The field's own citation drops a source the numbers inside it already show. Exports keep field citations.

NO_TRACE = {"ip-ref", "ip-slide-num", "ip-seg-num", "ip-sources", "ip-s-sources", "ip-org", "ip-s-org", "ip-date",
            "ip-s-date", "ip-script-kicker", "ip-required", "ip-memo-label", "ip-sources-head"}
BLOCK_TAGS = {"p", "li", "blockquote", "h1", "h2", "h3"}
BLOCK_CLASSES = {"ip-stat", "ip-sk-stat"}


MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DATE_BEFORE = re.compile(r"(?:\b" + MONTH + r"\s+(?:\d{1,2},?\s+)?)$", re.I)


def _is_date_part(text: str, a: int, raw: str) -> bool:
    """A day or a year in a written date ("December 1", "March 15, 2026"): traced, but given no source mark,
    which would read as part of the date."""
    return bool(re.fullmatch(r"\d{1,4}", raw)) and bool(DATE_BEFORE.search(text[max(0, a - 24):a]))


def _split_numbers(text: str, resolve) -> tuple:
    parts, last, used, hit = [], 0, set(), False
    for raw, _v, a, b in K.claim_spans(text):  # figures, and numbers written as words ("Nine weeks")
        got = resolve(text, raw)
        if not got:
            continue
        i, num = got
        hit = True
        if a > last:
            parts.append(n("span", "", text[last:a]))
        if num and _is_date_part(text, a, raw):
            num = None
        mark = [n("sup", "ip-ref ip-ref-num", str(num))] if num else None
        parts.append(n("span", "ip-num", raw, k=mark, tr=i))
        if num:
            used.add(num)
        last = b
    if not hit:
        return None, used
    if last < len(text):
        parts.append(n("span", "", text[last:]))
    return parts, used


def _prune_marks(node: dict, covered: set) -> Optional[dict]:
    if "ip-ref" in (node.get("c") or "").split() and "ip-ref-num" not in (node.get("c") or "").split():
        nums = [x for x in (node.get("x") or "").split(",") if x.strip()]
        left = [x for x in nums if not x.strip().isdigit() or int(x) not in covered]
        if not left:
            return None
        return {**node, "x": ",".join(left)}
    if node.get("k"):
        kids = [_prune_marks(c, covered) for c in node["k"]]
        return {**node, "k": [c for c in kids if c]}
    return node


def mark_traces(tree: dict, resolve) -> dict:
    """A copy of ``tree`` with each traced number wrapped as ``{"t": "span", "c": "ip-num", "a": {"tr": i}}``.

    ``resolve(text, raw)`` (checks.trace_table) says which trace a number belongs to, or ``None`` for text that
    is not a checked field (dates, slide numbers, source lists). Within a paragraph, list item or stat, a field
    citation that only repeats sources the numbers already show is dropped."""

    def walk(node: dict, block: Optional[set]) -> dict:
        classes = set((node.get("c") or "").split())
        if classes & NO_TRACE:
            return node
        own = None
        if block is None and (node.get("t") in BLOCK_TAGS or classes & BLOCK_CLASSES):
            own = set()
        scope = own if own is not None else block
        out = {k: v for k, v in node.items() if k not in ("x", "k")}
        kids = []
        if node.get("x"):
            parts, used = _split_numbers(node["x"], resolve)
            if parts is None:
                out["x"] = node["x"]
            else:
                kids += parts
                if scope is not None:
                    scope.update(used)
        kids += [walk(c, scope) for c in node.get("k") or []]
        if kids:
            out["k"] = kids
        if own:
            out = _prune_marks(out, own) or out
        return out

    return walk(tree, None)


def text_of(node: dict) -> str:
    parts = []
    if node.get("x"):
        parts.append(node["x"])
    for c in node.get("k") or []:
        parts.append(text_of(c))
    return " ".join(p for p in parts if p)


# The proof stylesheet. Every color and font is a kit variable set on .ip-page, so two proofs side by
# side never share a token. Sizes are in em of the page's base size (13px in the pane, 16px in HTML).
PROOF_CSS = """
.ip-page{--ip-base:13px;font-size:var(--ip-base);background:var(--k-paper);color:var(--k-ink);font-family:var(--k-body-font);
  line-height:1.5;text-align:left;container-type:inline-size;position:relative;overflow-wrap:break-word;
  -webkit-font-smoothing:antialiased;--g:calc(1em * var(--k-gap))}
.ip-page *{box-sizing:border-box}
.ip-page p,.ip-page h1,.ip-page h2,.ip-page h3,.ip-page ul,.ip-page ol,.ip-page blockquote{margin:0}
.ip-page:not(.ip-deck){display:flex;flex-direction:column}
.ip-inner{padding:calc(var(--g)*2.2) calc(var(--g)*2.4) calc(var(--g)*1.8);display:flex;flex-direction:column;gap:calc(var(--g)*1.1);flex:1 0 auto}
.ip-inner>.ip-foot,.ip-main>.ip-foot{margin-top:auto}
.ip-title,.ip-h2,.ip-stat-value,.ip-points-head,.ip-sources-head,.ip-runin-head,.ip-memo-label{font-family:var(--k-head-font);
  font-weight:var(--k-head-weight);font-style:var(--k-head-style);text-transform:var(--k-head-case);letter-spacing:var(--k-head-track);color:var(--k-head)}
.ip-title{font-size:min(calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale)), 8.5cqw);line-height:1.08}
.ip-h2{font-size:calc(1em * var(--k-scale) * var(--k-scale));line-height:1.18;margin-bottom:.3em}
.ip-dek{font-size:calc(1em * var(--k-scale));line-height:1.4}
.ip-body{font-size:1em}
.ip-section{display:grid;gap:.25em;break-inside:avoid}
.ip-sections{display:grid;gap:calc(var(--g)*1.1)}
.ip-ref{font-family:var(--k-body-font);font-size:max(12px,.68em);font-weight:600;color:var(--k-accent-text);margin-left:.18em;vertical-align:super;line-height:0}
.ip-org{display:flex;align-items:center;gap:.8em;flex-wrap:wrap;font-size:max(12px,.92em)}
.ip-org-name{font-weight:600}
.ip-date{margin-left:auto}
.ip-logo{max-height:2.4em;max-width:9em;object-fit:contain}
.ip-stat{display:grid;gap:.2em;break-inside:avoid}
.ip-stat-value{font-size:calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale) * 1.1);line-height:1;color:var(--k-accent);font-variant-numeric:lining-nums tabular-nums}
.ip-stat-label{font-size:max(12px,.95em)}
.ip-stat-fill{background:var(--k-fill);color:var(--k-fill-text);padding:1em 1.1em}
.ip-points-head,.ip-sources-head{font-size:1em;margin-bottom:.35em}
.ip-points{padding-left:1.15em;display:grid;gap:.35em}
.ip-points li::marker{color:var(--k-accent)}
.ip-quote{border-left:3px solid var(--k-accent);padding:.2em 0 .2em 1em;display:grid;gap:.3em;break-inside:avoid}
.ip-quote-text{font-size:calc(1em * var(--k-scale));font-style:italic;line-height:1.38}
.ip-quote-who{font-size:max(12px,.92em);font-weight:600}
.ip-next{font-weight:700;color:var(--k-accent-text);font-size:1.05em}
.ip-foot{display:grid;gap:.8em;border-top:1px solid var(--k-rule);padding-top:.9em;font-size:max(12px,.92em)}
.ip-foot:empty{display:none}
.ip-sources-list{padding-left:1.3em;display:grid;gap:.15em}
.ip-required p{font-weight:600}

/* Banner: the kit's band carries the masthead and the title in reversed type */
.ip-band{background:var(--k-band);color:var(--k-band-text);padding:calc(var(--g)*1.6) calc(var(--g)*2.4) calc(var(--g)*1.5);display:grid;gap:.8em}
.ip-band .ip-title,.ip-band .ip-org{color:var(--k-band-text)}
.ip-banner-grid{display:grid;gap:calc(var(--g)*1.4);grid-template-columns:1fr}
@container (min-width:560px){.ip-banner-grid{grid-template-columns:minmax(0,1fr) minmax(0,2fr)}}
.ip-banner-side{display:grid;gap:calc(var(--g)*1.1);align-content:start}

/* Headline: the title is the event; the kit's highlight sits under it like a marker stroke */
.ip-title-big{font-size:min(calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale)), 10.5cqw);line-height:1.04}
.ip-hl{background-image:linear-gradient(transparent 62%, var(--k-highlight) 62%, var(--k-highlight) 92%, transparent 92%);
  box-decoration-break:clone;-webkit-box-decoration-break:clone}
.ip-dark .ip-hl{background-image:none;color:var(--k-head);text-decoration:underline;text-decoration-color:var(--k-highlight);text-decoration-thickness:.07em;text-underline-offset:.1em}
.ip-head-row{display:grid;gap:calc(var(--g)*1.2);grid-template-columns:1fr;align-items:end}
@container (min-width:560px){.ip-head-row{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}}
.ip-dek-big{font-size:max(12px,min(calc(1em * var(--k-scale) * var(--k-scale)), 3.9cqw))}
.ip-stat-inline{border-top:3px solid var(--k-accent);padding-top:.6em}
.ip-tiles{grid-template-columns:1fr}
@container (min-width:520px){.ip-tiles{grid-template-columns:1fr 1fr}}
.ip-tiles .ip-section{border-top:1px solid var(--k-rule);padding-top:.7em}

/* Margin rail: figures and sources in a narrow column, the argument beside it */
.ip-inner.ip-margin-grid{display:grid;grid-template-columns:1fr;padding:0;align-content:stretch}
.ip-rail{display:grid;gap:calc(var(--g)*1.2);align-content:start;padding:calc(var(--g)*2.2) calc(var(--g)*1.2) calc(var(--g)*1.8) calc(var(--g)*1.6);
  border-top:1px solid var(--k-rule);font-size:max(12px,.94em)}
.ip-margin-grid>.ip-main{order:-1}
@container (min-width:520px){.ip-inner.ip-margin-grid{grid-template-columns:minmax(0,1fr) minmax(0,2.3fr)}
  .ip-margin-grid>.ip-main{order:0} .ip-margin-grid>.ip-rail{border-top:0;border-right:1px solid var(--k-rule)}}
.ip-main{display:flex;flex-direction:column;gap:calc(var(--g)*1.05);padding:calc(var(--g)*2.2) calc(var(--g)*2.2) calc(var(--g)*1.8) calc(var(--g)*1.6)}
.ip-stat-rail .ip-stat-value{font-size:calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale))}
.ip-rail .ip-sources{border-top:1px solid var(--k-rule);padding-top:.8em}

/* Letter: a memo head, one reading column, run-in heads */
.ip-letter-col{max-width:44em}
.ip-letterhead:empty{display:none}
.ip-memo{display:grid;gap:.25em}
.ip-memo-row{display:grid;grid-template-columns:4.2em 1fr;gap:.6em;align-items:baseline}
.ip-memo-label{font-size:max(12px,.92em);color:var(--k-accent-text)}
.ip-memo-row:first-child .ip-memo-value{font-family:var(--k-head-font);font-weight:var(--k-head-weight);font-style:var(--k-head-style);
  font-size:calc(1em * var(--k-scale) * var(--k-scale));line-height:1.2;color:var(--k-head)}
.ip-memo-rule{border:0;border-top:2px solid var(--k-rule);margin:0}
.ip-lead{font-size:calc(1em * var(--k-scale))}
.ip-runin-head{font-size:1em}
.ip-letter-body{gap:calc(var(--g)*.85)}
.ip-stat-letter{grid-template-columns:auto 1fr;align-items:center;gap:1em;background:var(--k-fill);color:var(--k-fill-text);padding:.8em 1em}
.ip-stat-letter .ip-stat-value{font-size:calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale))}
.ip-signoff{font-style:italic}

/* Bulletin: a nameplate, a side column of what to do, sections set in columns */
.ip-nameplate{display:grid;gap:.5em;border-bottom:3px solid var(--k-head);padding-bottom:calc(var(--g)*.9)}
.ip-bulletin-grid{display:grid;gap:calc(var(--g)*1.3);grid-template-columns:1fr}
@container (min-width:560px){.ip-bulletin-grid{grid-template-columns:minmax(0,1fr) minmax(0,2fr)}}
.ip-bulletin-side{display:grid;gap:calc(var(--g)*1.1);align-content:start}
.ip-bulletin-cols{display:block}
@container (min-width:640px){.ip-bulletin-cols{columns:2;column-gap:calc(var(--g)*1.6);column-rule:1px solid var(--k-rule)}}
.ip-bulletin-cols .ip-section{margin-bottom:calc(var(--g)*1.1)}

/* Menus and price lists: name, dotted leader, price; a note under it */
.ip-menu{list-style:none;padding:0;display:grid;gap:.55em;margin-top:.2em}
.ip-menu-item{display:grid;gap:.1em;break-inside:avoid}
.ip-menu-line{display:flex;align-items:baseline;gap:.4em}
.ip-menu-name{font-weight:600}
.ip-menu-dots{flex:1;border-bottom:1px dotted var(--k-rule);transform:translateY(-.25em);min-width:1em}
.ip-menu-price{font-family:var(--k-head-font);font-weight:var(--k-head-weight);color:var(--k-accent-text);font-variant-numeric:lining-nums tabular-nums;white-space:nowrap}
.ip-menu-note{font-size:max(12px,.92em)}

/* Flyer: centered head, a stamp for the one number, the offer in columns, the call to action on the band */
.ip-flyer{gap:calc(var(--g)*1.3)}
.ip-flyer-head{display:grid;gap:.6em;justify-items:center;text-align:center;border-bottom:4px solid var(--k-accent);padding-bottom:calc(var(--g)*1.1)}
.ip-org-center{justify-content:center}
.ip-org-center .ip-date{margin-left:0}
.ip-title-flyer{font-size:min(calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale)), 11cqw);line-height:1.02;text-align:center}
.ip-flyer-dek{text-align:center;max-width:34em}
.ip-flyer-stamp{align-self:center;display:grid;justify-items:center;text-align:center;gap:.15em;background:var(--k-fill);color:var(--k-fill-text);
  padding:.9em 1.6em;border-radius:999px;border:2px solid var(--k-accent)}
.ip-flyer-cols{display:grid;grid-template-columns:1fr;gap:calc(var(--g)*1.3)}
@container (min-width:520px){.ip-flyer-cols{grid-template-columns:1fr 1fr;column-gap:calc(var(--g)*2)}}
.ip-flyer-cols .ip-h2{border-bottom:1px solid var(--k-rule);padding-bottom:.2em}
.ip-flyer-points{list-style:none;padding:0;display:flex;flex-wrap:wrap;justify-content:center;gap:.5em 1.4em;font-weight:600}
.ip-flyer-points li::before{content:"";display:inline-block;width:.5em;height:.5em;border-radius:50%;background:var(--k-accent);margin-right:.5em;vertical-align:.08em}
.ip-flyer-cta{background:var(--k-band);color:var(--k-band-text);font-family:var(--k-head-font);font-weight:var(--k-head-weight);
  font-size:calc(1em * var(--k-scale) * var(--k-scale));line-height:1.25;text-align:center;padding:.8em 1em;margin-top:auto}
.ip-flyer-cta+.ip-foot{margin-top:0}

/* Report: summary, key figures in a row, side-heads beside each section, a pulled quote */
.ip-title-report{max-width:18em}
.ip-report-dek{max-width:36em}
.ip-figures{display:grid;grid-template-columns:1fr;gap:calc(var(--g)*1)}
@container (min-width:520px){.ip-figures{grid-template-columns:repeat(auto-fit,minmax(0,1fr))}}
.ip-figure{border-top:3px solid var(--k-accent);padding-top:.6em;display:grid;gap:.2em;align-content:start;font-weight:600}
.ip-figure-lead .ip-stat-value{font-size:calc(1em * var(--k-scale) * var(--k-scale) * var(--k-scale) * var(--k-scale))}
.ip-report-body{display:grid;gap:calc(var(--g)*1.2)}
.ip-report-row{display:grid;grid-template-columns:1fr;gap:.3em;border-top:1px solid var(--k-rule);padding-top:.8em;break-inside:avoid}
@container (min-width:520px){.ip-report-row{grid-template-columns:minmax(0,1fr) minmax(0,2.8fr);gap:calc(var(--g)*1.6)}}
.ip-sidehead{font-size:calc(1em * var(--k-scale));margin:0}
.ip-report-text{display:grid;gap:.5em}
.ip-pull .ip-quote{border-left:0;border-top:2px solid var(--k-accent);border-bottom:2px solid var(--k-accent);padding:.8em 0}
.ip-pull .ip-quote-text{font-size:calc(1em * var(--k-scale) * var(--k-scale))}

/* Decks and graphics are scenes (scene.SCENE_CSS); their slides are positioned, measured drawings. */

/* Audio script: signposts numbered, the recap set apart */
.ip-script-kicker{font-weight:600;color:var(--k-accent-text);font-size:max(12px,.92em)}
.ip-segs{display:grid;gap:calc(var(--g)*1.05)}
.ip-seg{display:grid;gap:.3em}
.ip-seg-head{font-family:var(--k-head-font);font-weight:var(--k-head-weight);font-style:var(--k-head-style);text-transform:var(--k-head-case);
  letter-spacing:var(--k-head-track);color:var(--k-head);font-size:calc(1em * var(--k-scale));display:flex;gap:.6em;align-items:baseline}
.ip-seg-num{font-variant-numeric:tabular-nums;color:var(--k-accent);font-size:max(12px,.8em)}
.ip-seg-text{font-size:1.04em;line-height:1.55}
.ip-recap{background:var(--k-fill);color:var(--k-fill-text);padding:1em 1.1em;display:grid;gap:.35em}
"""
