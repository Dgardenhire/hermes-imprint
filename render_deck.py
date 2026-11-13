"""The deck: the slides as scenes (systems.py composes each one in the kit's design system), shown in the pane
and written out as a PowerPoint file and a PDF from the very same elements.

- **Pane**: ``deck_tree`` gives every slide as positioned nodes (scene.nodes), so the preview is the export.
- **PowerPoint** (python-pptx). The slide master carries the kit: its theme colors (``dk1`` ink, ``lt1`` paper,
  ``dk2`` heading color, ``accent1`` the accent ...), its theme fonts (the heading family as the major font, the
  body family as the minor font), the paper as the master background, and the logo in the corner. Every slide
  sits on a real layout (Title Slide, Title and Content, Section Header, Comparison, Title Only) with its heading
  in the title placeholder and its points in the body placeholder as native bullets, so outline view, Designer,
  the accessibility checker and Reset Slide all see titled slides. Everything else in the scene (rules, bars,
  fields, pictures, labels) is a native shape or text box at the scene's own position. A slide set on a ground
  other than the paper hides the master's logo and carries the version that reads on that ground.
- **PDF** (reportlab). 16:9 pages with the kit's TrueType faces embedded, drawn by scene.draw_pdf.

A PNG or JPG logo is placed in both. An SVG logo shows in the preview only, and a check says so.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

try:
    from . import colors as C
    from . import content as K
    from . import fonts as F
    from . import render_pdf as RP
    from . import scene as SC
    from . import systems as SY
except ImportError:  # loaded loose
    import colors as C  # type: ignore
    import content as K  # type: ignore
    import fonts as F  # type: ignore
    import render_pdf as RP  # type: ignore
    import scene as SC  # type: ignore
    import systems as SY  # type: ignore

SLIDE_W, SLIDE_H = 960.0, 540.0  # points, 13.333 x 7.5 in


class DeckUnavailable(RuntimeError):
    pass


def _marks(refs: list, idx: dict) -> str:
    nums = sorted({idx[r] for r in refs or [] if r in idx})
    return ",".join(str(i) for i in nums)


def source_line(refs: list, passages: dict, limit: int = 3, places: bool = True) -> str:
    """"Warming center report, p. 2, p. 4; Council work session, 0:14": the passages behind a slide, by source."""
    by, order = {}, []
    for r in refs or []:
        info = passages.get(r)
        if not info:
            continue
        t = info.get("source_title") or "Source"
        if t not in by:
            by[t] = []
            order.append(t)
        loc = (info.get("locator") or "") if places else ""
        if loc and loc not in by[t]:
            by[t].append(loc)
    parts = [t + (", " + ", ".join(by[t][:3]) if by[t] else "") for t in order[:limit]]
    return "; ".join(parts)


_INTERNAL = re.compile(r"(?i)\b(notes?|minutes|memo|internal|meeting|call|transcript|e-?mail|draft)\b")


def is_internal(title: str) -> bool:
    """Loop 3 (critics 12): a source the funder never sees (board notes, meeting minutes, an internal memo). It stays a
    source for checking and in the speaker notes; a slide's visible source line names only the report and the
    public documents."""
    return bool(_INTERNAL.search(title or ""))


def public_refs(refs: list, passages: dict) -> list:
    return [r for r in refs or [] if not is_internal((passages.get(r) or {}).get("source_title", ""))]


def _slide_refs(sl: dict) -> list:
    refs = list(sl.get("refs") or [])
    for lst in ("bullets", "left_items", "right_items", "bars", "steps", "figures", "rows", "els"):
        refs += [it.get("ref") for it in sl.get(lst) or [] if isinstance(it, dict) and it.get("ref")]
    out = []
    for r in refs:
        if r and r not in out:
            out.append(r)
    return out


def slides(doc: dict, kit: dict, idx: dict, rows: list, date: str, passages: Optional[dict] = None) -> list:
    """Plain slide specs, in order: what each slide says, its source marks ("1,2"), its source line, the section it
    belongs to and its number. A title slide first and a sources slide last when the kit lists sources."""
    rules = kit.get("rules") or {}
    show_date = rules.get("date", True)
    lists_sources = bool(rules.get("sources"))
    passages = passages or {}
    if lists_sources and not sources_page(doc):
        idx = {}  # no Sources page: each foot names its sources, so no marks point at a missing list
    out = [{"kind": "title", "title": doc.get("title", ""), "sub": doc.get("subtitle", ""), "org": kit.get("org") or "",
            "date": date if show_date else "", **({"photo": doc["photo"]} if (doc.get("photo") or {}).get("name") else {})}]
    section, n_section, n_exhibit, n_figures = "", 0, 0, 0
    for sl in doc.get("slides") or []:
        t, refs = sl.get("type"), sl.get("refs") or []
        item = lambda it: (it.get("text", ""), _marks([it["ref"]] if it.get("ref") else refs, idx))
        shown = public_refs(_slide_refs(sl), passages)
        src = source_line(shown, passages) if lists_sources else ""
        short = source_line(shown, passages, places=False) if lists_sources else ""
        base = {"section": section, "src": src, "src_short": short}
        if t == "spec":  # loop 4: the model's own layout, in the brand's roles
            out.append({**base, "kind": "spec", "head": sl.get("heading", ""), "els": sl.get("els") or [],
                        "ground": sl.get("ground") or "paper", "footer": sl.get("footer", True)})
            continue
        if t == "section":
            n_section += 1
            section = sl.get("heading", "")
            out.append({"kind": t, "head": sl.get("heading", ""), "sub": sl.get("subtitle", ""), "n": n_section, "marks": _marks(refs, idx)})
        elif t == "content":
            bl = sl.get("bullets") or []
            if sl.get("shape") in ("money", "table") and sum(1 for b in bl if b.get("figure")) >= 2:
                # round 16: one table, the line's words in the first column and its amount right-aligned in the second;
                # the whole (a budget, a total, a gap) set bold on a heavier rule; lines with no amount under it
                rows = [(b.get("text", ""), b.get("figure", ""), item(b)[1],
                         bool(re.search(r"(?i)(\btotal\b|\bgap\b|in hand$|budget$|cost$)", b.get("text", "").strip())))
                        for b in bl if b.get("figure")]
                out.append({**base, "kind": "table", "head": sl.get("heading", ""), "rows": rows,
                            "note": " ".join(t if re.search(r"[.!?:;)]$", t) else t + "."
                                             for t in (b.get("text", "") for b in bl if not b.get("figure")))})
                continue
            if sum(1 for b in bl if b.get("figure")) >= 2:  # points that lead with their numbers: a ledger, figure first
                out.append({**base, "kind": "ledger", "head": sl.get("heading", ""), "items": [item(b) for b in bl],
                            "figs": [b.get("figure", "") for b in bl]})
            else:
                out.append({**base, "kind": t, "head": sl.get("heading", ""),
                            "items": [(_lead(b), item(b)[1]) for b in bl], **({"comp": sl["comp"]} if sl.get("comp") else {}),
                            **({"split": sl["split"]} if sl.get("split") else {})})
        elif t == "figures":
            figs = [(f.get("value", ""), f.get("label", ""), f.get("context", ""),
                     _marks([f["ref"]] if f.get("ref") else refs, idx)) for f in sl.get("figures") or []]
            n_figures += 1
            if n_figures >= 2 and len(figs) >= 2 and not sl.get("plain"):
                # round 10 (critics 7, 8, 9): one four-up grid per deck. Every later figures slide is a ledger, each
                # figure large in its own column with what it counts beside it, and nothing padded after the label
                out.append({**base, "kind": "ledger", "head": sl.get("heading", ""), "from_figures": True,
                            "items": [(_ledger_line(l, ctx), m) for _v, l, ctx, m in figs], "figs": [v for v, *_r in figs]})
            else:
                out.append({**base, "kind": t, "head": sl.get("heading", ""), "note": sl.get("note", ""),
                            "figs": [(v, l, ctx if _row_context(l, ctx) else "", m) for v, l, ctx, m in figs]})
        elif t == "stat":
            out.append({**base, "kind": t, "value": sl.get("value", ""), "label": sl.get("label", ""), "context": sl.get("context", ""),
                        "marks": _marks(refs, idx)})
        elif t == "quote":
            out.append({**base, "kind": t, "quote": sl.get("quote", ""), "who": sl.get("who", ""), "marks": _marks(refs, idx),
                        **({"note": sl["note"]} if sl.get("note") else {}),
                        **({"photo": doc["photo"]} if (doc.get("photo") or {}).get("name") else {})})
        elif t == "comparison" and len(sl.get("rows") or []) >= 2:
            out.append({**base, "kind": "matched", "head": sl.get("heading", ""),
                        "labels": (sl.get("left_label", "") or "Today", sl.get("right_label", "") or "With the plan"),
                        "rows": [(r.get("label", ""), r.get("left", ""), r.get("right", ""),
                                  _marks([r["ref"]] if r.get("ref") else refs, idx)) for r in sl.get("rows") or []]})
        elif t == "comparison":
            out.append({**base, "kind": t, "head": sl.get("heading", ""),
                        "cols": [(sl.get("left_label", ""), [item(b) for b in sl.get("left_items") or []]),
                                 (sl.get("right_label", ""), [item(b) for b in sl.get("right_items") or []])]})
        elif t == "exhibit":
            n_exhibit += 1
            bars = [(b.get("label", ""), b.get("value", ""), SY.parse_value(b.get("value", "")),
                     _marks([b["ref"]] if b.get("ref") else refs, idx)) for b in sl.get("bars") or []]
            hi = next((i for i, b in enumerate(sl.get("bars") or []) if b.get("accent") is True), None)
            out.append({**base, "kind": t, "head": sl.get("heading", ""), "subhead": sl.get("subhead", ""), "unit": sl.get("unit", ""),
                        "note": sl.get("note", ""), "bars": bars, "hi": hi, "exhibit_n": n_exhibit})
        elif t == "timeline":
            steps = [(st.get("when", ""), st.get("text", ""), _marks([st["ref"]] if st.get("ref") else refs, idx)) for st in sl.get("steps") or []]
            out.append({**base, "kind": t, "head": sl.get("heading", ""), "steps": steps})
        elif t == "image":
            out.append({**base, "kind": t, "head": sl.get("heading", ""), "caption": sl.get("caption", ""), "picture": sl.get("picture") or "",
                        "marks": _marks(refs, idx)})
        else:
            out.append({"kind": "closing", "head": sl.get("heading", ""), "text": sl.get("text", ""), "cta": sl.get("cta", ""),
                        "amount": sl.get("amount", ""), "amount_label": sl.get("amount_label", ""),
                        "marks": _marks(refs, idx), "required": list(rules.get("required") or [])})
    for sl, sp in zip(doc.get("slides") or [], out[1:]):
        if sl.get("headline") and sp.get("head") == sl.get("heading") and sp.get("kind") not in ("section", "quote"):
            # loop 3: the slide states its point; the draft's topic title sits small above it
            sp["eyebrow"], sp["head"] = sl.get("heading", ""), sl["headline"]
    cv = doc.get("cover") if isinstance(doc.get("cover"), dict) else None
    if cv and cv.get("els"):  # loop 4: the cover the model designed
        out[0] = {"kind": "spec", "cover": True, "head": doc.get("title", ""), "els": cv["els"], "ground": cv.get("ground") or "primary",
                  "footer": False, "section": "", "src": "", "src_short": ""}
    cover = None if cv and cv.get("els") else cover_figure(doc, idx)
    if cover:
        out[0]["fig"] = cover
    cap = doc.get("max_slides") if isinstance(doc.get("max_slides"), int) else None
    if cap:
        lists_sources = False  # the person's length holds: each slide's foot names its sources, the notes list them all
    if lists_sources and rows and sources_page(doc):
        out.append({"kind": "sources", "head": "Sources", "section": "",
                    "items": [(f"{r['title']}" + (f", {', '.join(r['locators'][:4])}" if r["locators"] else ""), "") for r in rows
                              if not is_internal(r.get("title", ""))]})
    for i, sp in enumerate(out, start=1):
        sp["num"] = i
    return out


_STOP = {"with", "over", "from", "that", "this", "their", "they", "have", "were", "into", "each", "about"}


def _words(t: str) -> set:
    return {re.sub(r"(?:ing|ed|s)$", "", w) for w in re.findall(r"[a-z]{4,}", (t or "").lower()) if w not in _STOP}


def _adds(label: str, context: str) -> bool:
    """Whether a figure's context line says something its label doesn't. "Grants from foundations in FY2026" under
    "From foundation grants" repeats it, so the row shows its label alone (round 10, critics 7 and 9)."""
    if _hedged(context):
        return True  # "Staff estimate" under "More learners a year" says what kind of number it is: it always stays
    cw = _words(context)
    if not cw:
        return False
    return len(cw & _words(label)) / len(cw) < 0.34


def _row_context(label: str, context: str) -> bool:
    """Whether a figure row shows its context line: when it hedges the number ("Staff estimate"), or adds something in
    a few words ("At year end"), or names a place, program or date the label doesn't ("The most in Harborlight's
    history"). A long plain descriptor ("A corps of tutors working with our learners") is padding: the label stands
    alone (round 10, critics 7 and 9)."""
    if not context or not context.strip():
        return False
    if _hedged(context):
        return True
    if not _adds(label, context):
        return False
    words = context.split()
    named = any(w[:1].isupper() or any(ch.isdigit() for ch in w) for w in words[1:])
    return len(words) <= 5 or named


def _hedged(t: str) -> bool:
    try:
        from . import checks as CK
    except ImportError:
        import checks as CK  # type: ignore
    return bool(CK.hedges_in(t or "") & {"estimate", "expect", "plan"})


def _ledger_line(label: str, context: str) -> str:
    """A figure's words on a ledger row: what it counts, then a short context only when it adds something ("Adults
    waiting: at year end") or hedges the number ("staff estimate"). Round 10 (critics 7, 9): a long descriptor read as
    padding ("Volunteer tutors: a corps of tutors working with our learners"), so that row shows its label alone. A
    context that carries its own number is left off, so every number on the row stays the one its source traces."""
    label, context = (label or "").strip(), (context or "").strip()
    if not context or K.claim_spans(context):
        return label
    if not label:
        return context
    if not _row_context(label, context):
        return label  # "Volunteer tutors: a corps of tutors working with our learners" pads; the label alone stays
    return f"{label}: {context[:1].lower() + context[1:] if context[:1].isupper() and not context[1:2].isupper() else context}"


def sources_page(doc: dict) -> bool:
    """Whether the deck ends on a Sources page. Only when the person asked for one (round 8: a near-empty last page
    read as filler): otherwise each slide's foot names its sources and the speaker notes list every passage."""
    return bool(doc.get("sources_page")) and not isinstance(doc.get("max_slides"), int)


def _lead(b: dict) -> str:
    """A point with its figure in front ("74 percent of guests ..."), for a list where most points have none."""
    t, f = b.get("text", ""), b.get("figure") or ""
    if not f or f in t:
        return t
    w = t.split(" ", 1)[0]
    if w[:1].isupper() and not any(ch.isupper() for ch in w[1:]):
        t = t[:1].lower() + t[1:]  # the text says what the figure counts: "214 volunteer tutors", not "214 Volunteer tutors"
    if re.search(r"(%|percent)$", f) and not t.lower().startswith(("of ", "of\u00a0")):
        t = "of " + t  # "74 percent of guests named ..."
    return f"{f} {t}"


def cover_figure(doc: dict, idx: dict) -> Optional[tuple]:
    """The number the deck argues from, for the cover: ``(value, label, marks)``. The opening exhibit's finding bar
    (a number the chart shows, never a headline), else None."""
    sls = doc.get("slides") or []
    money = lambda v: bool(re.search(r"[$£€]", v or ""))
    lead = next((sl for sl in sls if sl.get("type") not in ("section", "quote")), {})
    for sl in sls:
        # the deck's opening exhibit is its case; a later one (a funding mix, a side finding) is not the cover's number
        if sl is lead and sl.get("type") == "exhibit" and not any(money(b.get("value")) for b in sl.get("bars") or []):
            b = next((b for b in sl.get("bars") or [] if b.get("accent") is True), None)
            if b and b.get("value"):
                lab = b.get("label", "")
                if sl.get("unit") and (re.search(r"\d", lab) or len(lab.split()) <= 2):
                    lab = f"{sl['unit']}, {lab[:1].lower() + lab[1:]}" if lab else sl["unit"]  # "64" alone says nothing: "Guests housed, 2025-26 season"
                return (b["value"], lab, _marks([b["ref"]] if b.get("ref") else sl.get("refs") or [], idx))
    return None  # no opening exhibit: the cover carries the title alone, so no slide's big number is shown twice (round 3)


def notes_for(doc: dict, passages: dict) -> list:
    """Speaker notes per slide: the passages behind it, by source and locator. The cover's notes hold the draft's cover
    lines that did not fit under the title (loop 3 fix 3), word for word."""
    notes = [" ".join(doc.get("cover_note") or [])]
    for sl in doc.get("slides") or []:
        seen, lines = set(), []
        for r in _slide_refs(sl):
            info = passages.get(r)
            if info and r not in seen:
                seen.add(r)
                lines.append(f"{info.get('source_title', 'Source')}, {info.get('locator', '')}".strip(", "))
        notes.append("Sources: " + "; ".join(lines) if lines else "")
    return notes


def faces_for(kit: dict, faces: Optional[dict]) -> dict:
    return faces if faces else F.resolve_kit(kit, None)


def system_of(kit: dict) -> str:
    if kit.get("deck") in SY.SYSTEMS:
        return kit["deck"]
    try:
        from . import kits as KITS
    except ImportError:  # loaded loose
        import kits as KITS  # type: ignore
    return KITS.deck_system(kit)


def source_photo(data: bytes, filename: str, min_side: int = 400) -> Optional[dict]:
    """The largest photo embedded in a source file (a .docx's word/media, a .pdf's JPEG image streams), as
    ``{"bytes", "ext", "credit"}`` credited to the file, or None. Only a real photo counts: at least ``min_side``
    pixels on its short side, never the document's own page thumbnail (docProps/thumbnail) or a tiny icon. Nothing
    is generated and nothing is fetched."""
    name = (filename or "").lower()
    found = []
    try:
        if name.endswith(".docx"):
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    if info.filename.startswith("word/media/") and info.file_size <= 20_000_000 and \
                            info.filename.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png"):
                        found.append((z.read(info.filename), info.filename.lower().rsplit(".", 1)[-1]))
        elif name.endswith(".pdf"):
            for m in re.finditer(rb"<<(?:(?!>>).){0,600}?/Subtype\s*/Image(?:(?!>>).){0,600}?>>\s*stream\r?\n", data, re.S):
                head = m.group(0)
                if b"DCTDecode" not in head:
                    continue
                end = data.find(b"endstream", m.end())
                if end > m.end():
                    found.append((data[m.end():end].rstrip(b"\r\n"), "jpg"))
    except Exception:  # noqa: BLE001 - a file we can't open holds no photo we can use
        return None
    best = None
    for b, ext in found:
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(b))
            w, h = im.size
        except Exception:  # noqa: BLE001
            continue
        if min(w, h) >= min_side and (best is None or w * h > best[0]):
            best = (w * h, b, "jpg" if ext in ("jpg", "jpeg") else "png")
    if not best:
        return None
    return {"bytes": best[1], "ext": best[2], "credit": Path(filename).name}


def family_of(kit: dict, name: Optional[str] = None) -> str:
    """The layout family the kit's slides are composed in: its own choice, else the editorial family for the poster
    and keynote systems and for an imported brand (a kit that is not one of the starters), else the classic one."""
    if kit.get("family") in SY.FAMILIES:
        return kit["family"]
    name = name or system_of(kit)
    if name in SY.EDITORIAL_SYSTEMS:
        return "editorial"
    try:
        from . import kits as KITS
    except ImportError:  # loaded loose
        import kits as KITS  # type: ignore
    if kit.get("id") and kit["id"] not in KITS.STARTER_IDS and not kit.get("studio"):
        return "editorial"
    return "classic"


def scenes(doc: dict, kit: dict, pal: dict, faces: dict, idx: dict, rows: list, date: str = "", passages: Optional[dict] = None) -> tuple:
    """``(scenes, type)``: every slide composed in the kit's design system, in its layout family."""
    ty = SC.Type(faces_for(kit, faces))
    name = system_of(kit)
    sysm = SY.for_kit(kit, pal, ty, name, family_of(kit, name))
    return [sysm.compose(sp) for sp in slides(doc, kit, idx, rows, date, passages)], ty


def logo_bytes(logo) -> dict:
    """``{"paper": bytes, "band": bytes}`` for the PDF, PNG and PowerPoint (PNG or JPG only)."""
    out = {}
    for place in ("paper", "band"):
        r = RP.raster(logo, place)
        if r is None:
            continue
        if isinstance(r, (str, Path)):
            out[place] = Path(r).read_bytes()
        else:
            r.seek(0)
            out[place] = r.read()
    return out


def deck_tree(doc: dict, kit: dict, pal: dict, faces: dict, passages: dict, date: str = "", logo_urls: Optional[dict] = None,
              images: Optional[dict] = None, idx: Optional[dict] = None, rows: Optional[list] = None) -> tuple:
    """``(tree, scenes)`` for the pane: a column of slides, each the scene the exports draw."""
    try:
        from . import layout as L
    except ImportError:  # loaded loose
        import layout as L  # type: ignore
    if idx is None or rows is None:
        idx, rows = L.source_index(doc, passages)
    scs, ty = scenes(doc, kit, pal, faces, idx, rows, date, passages)
    kids = [SC.nodes(sc, ty, cls="ip-scene", images=images, logos=logo_urls, extra_class=f"ip-sk-{sc['kind']}") for sc in scs]
    name = system_of(kit)
    return {"t": "div", "c": f"ip-deck ip-deck-{name}" + (" ip-dark" if pal.get("dark") else ""), "k": kids}, scs


def long_slides(scs: list) -> list:
    return [sc["num"] for sc in scs if sc.get("long")]


# ---------------------------------------------------------------- PowerPoint --

def _pptx():
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
        from pptx.opc.constants import RELATIONSHIP_TYPE as RT
        from pptx.util import Emu, Pt
    except ImportError:
        raise DeckUnavailable("PowerPoint export needs the python-pptx library, which isn't installed. Reinstall Letterpress to add it.")
    return locals()


A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def theme_xml(blob: bytes, kit: dict, pal: dict) -> bytes:
    """The master's theme with the kit's colors and fonts in place."""
    from lxml import etree
    root = etree.fromstring(blob)
    ns = {"a": A_NS}
    others = [c["hex"] for c in kit.get("colors") or [] if c["hex"] not in (pal["accent"], pal["head"])]
    accents = [pal["accent"], pal.get("accent2") or pal["head"], pal.get("band") or pal["head"], pal.get("fill") or pal["rule"],
               pal["rule"]] + others
    want = {"dk1": pal["ink"], "lt1": pal["paper"], "dk2": pal["head"], "lt2": pal.get("fill") or C.mix(pal["ink"], pal["paper"], 0.92),
            "accent1": accents[0], "accent2": accents[1], "accent3": accents[2], "accent4": accents[3], "accent5": accents[4],
            "accent6": accents[5] if len(accents) > 5 else pal["ink"], "hlink": pal["accent_text"], "folHlink": pal["head"]}
    scheme = root.find(".//a:clrScheme", ns)
    if scheme is not None:
        scheme.set("name", (kit.get("name") or "Letterpress")[:60])
        for tag, hexcolor in want.items():
            el = scheme.find(f"a:{tag}", ns)
            if el is None:
                continue
            for child in list(el):
                el.remove(child)
            etree.SubElement(el, f"{{{A_NS}}}srgbClr", val=hexcolor.lstrip("#").upper())
    fonts = root.find(".//a:fontScheme", ns)
    if fonts is not None:
        fonts.set("name", (kit.get("name") or "Letterpress")[:60])
        for tag, role in (("majorFont", "heading"), ("minorFont", "body")):
            latin = fonts.find(f"a:{tag}/a:latin", ns)
            if latin is not None:
                latin.set("typeface", ((kit.get("type") or {}).get(role) or {}).get("family") or "Calibri")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
LAYOUT = {"title": 0, "content": 1, "sources": 1, "section": 2, "closing": 2, "comparison": 4, "stat": 5, "quote": 5}


def _widen_layouts(prs, ratio: float) -> None:
    """The default template is 4:3. Widen the master's and every layout's placeholders to 16:9, so a slide
    reset or a new slide from a layout lands where the deck's own slides do."""
    shapes = list(prs.slide_master.placeholders)
    for lay in prs.slide_layouts:
        shapes += list(lay.placeholders)
    for ph in shapes:
        try:
            if ph.left is not None and ph.width is not None:
                ph.left, ph.width = int(ph.left * ratio), int(ph.width * ratio)
        except (AttributeError, ValueError):
            continue


def _title_color_from_theme(master) -> None:
    """Master titles take the theme's second dark color (the kit's heading color), not the body ink."""
    for clr in master._element.iter(f"{{{A_NS}}}schemeClr"):
        parent = clr.getparent()
        if parent is not None and parent.tag == f"{{{A_NS}}}solidFill":
            anc = parent.getparent()
            if anc is not None and anc.getparent() is not None and anc.getparent().tag == f"{{{A_NS}}}lvl1pPr":
                lvl = anc.getparent().getparent()
                if lvl is not None and lvl.tag == f"{{{P_NS}}}titleStyle":
                    clr.set("val", "tx2")


def _face_family(kit: dict, face: str) -> str:
    t = kit.get("type") or {}
    if face == "heading":
        return (t.get("heading") or {}).get("family") or "Calibri"
    if face == "label" and (t.get("label") or {}).get("family"):
        return t["label"]["family"]
    return (t.get("body") or {}).get("family") or "Calibri"


def render_pptx(doc: dict, kit: dict, pal: dict, idx: dict, rows: list, passages: dict, date: str = "",
                logo=None, faces: Optional[dict] = None, pictures: Optional[dict] = None) -> bytes:
    """A real PowerPoint deck from the same scenes the pane and the PDF draw. Each slide sits on a layout from the kit's
    slide master: its title in the title placeholder, its points in the body placeholder as native bullets, and every
    other element a native shape, picture or text box where the scene puts it."""
    P = _pptx()
    from lxml import etree
    prs = P["Presentation"]()
    ratio = 12192000 / prs.slide_width
    prs.slide_width, prs.slide_height = P["Emu"](12192000), P["Emu"](6858000)
    _widen_layouts(prs, ratio)
    rgb = lambda h: P["RGBColor"].from_string(h.lstrip("#").upper())
    pt = P["Pt"]
    emu = lambda points: P["Emu"](int(points * 12700))

    master = prs.slide_master
    theme = master.part.part_related_by(P["RT"].THEME)
    theme._blob = theme_xml(theme.blob, kit, pal)
    _title_color_from_theme(master)
    master.background.fill.solid()
    master.background.fill.fore_color.rgb = rgb(pal["paper"])
    logos = logo_bytes(logo)

    def pic_size(data):
        from PIL import Image
        try:
            return Image.open(io.BytesIO(data)).size
        except Exception:
            return 1, 1

    logo_on_master = False
    if logos.get("paper"):
        try:  # the master has no add_picture; place the picture through its part, as slides do
            image_part, rid = master.part.get_or_add_image_part(io.BytesIO(logos["paper"]))
            w, h = image_part.image.size
            ph = 26.0
            pw = min(ph * w / h if h else ph, 160.0)
            master.shapes._spTree.add_pic(master.shapes._next_shape_id, "Logo", "", rid,
                                          emu(SLIDE_W - 36 - pw), emu(22), emu(pw), emu(ph))
            logo_on_master = True
        except Exception:
            logo_on_master = False

    scs, ty = scenes(doc, kit, pal, faces_for(kit, faces), idx, rows, date, passages)
    notes = notes_for(doc, passages)
    weight = lambda face: ty.weight(face)

    def frame(shape, el, anchor="top"):
        x, y, w, h = el["x"], el["y"], el["w"] * 1.04 + 2, max(el["h"], el.get("lead", 0))
        if el.get("align") == "center":
            x -= el["w"] * 0.02 + 1
        elif el.get("align") == "right":
            x -= el["w"] * 0.04 + 2
        shape.left, shape.top, shape.width, shape.height = emu(x), emu(y), emu(w), emu(h)
        tf = shape.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = P["MSO_ANCHOR"].TOP
        try:
            tf.auto_size = None
        except Exception:
            pass
        return tf

    def para(tf, el, first, bullet=None, space=0.0):
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        p.alignment = {"left": P["PP_ALIGN"].LEFT, "center": P["PP_ALIGN"].CENTER, "right": P["PP_ALIGN"].RIGHT}[el.get("align") or "left"]
        p.line_spacing = pt(el["lead"])
        p.space_before = pt(max(0.0, space))
        pPr = p._p.get_or_add_pPr()
        for old in list(pPr):
            if old.tag in (f"{{{A_NS}}}buNone", f"{{{A_NS}}}buChar", f"{{{A_NS}}}buClr", f"{{{A_NS}}}buFont"):
                pPr.remove(old)
        if bullet:
            pPr.set("marL", str(int(30 * 12700)))
            pPr.set("indent", str(-int(30 * 12700)))
            clr = etree.SubElement(pPr, f"{{{A_NS}}}buClr")
            etree.SubElement(clr, f"{{{A_NS}}}srgbClr", val=bullet[1].lstrip("#").upper())
            etree.SubElement(pPr, f"{{{A_NS}}}buFont", typeface="Arial")
            etree.SubElement(pPr, f"{{{A_NS}}}buChar", char=bullet[0])
        else:
            pPr.set("marL", "0")
            pPr.set("indent", "0")
            etree.SubElement(pPr, f"{{{A_NS}}}buNone")
        for li, line in enumerate(el["lines"]):  # the scene's own line breaks, as soft breaks, so PowerPoint sets the same lines
            if li:
                p.add_line_break()
            r = p.add_run()
            r.text = line
            f = r.font
            f.size, f.name = pt(el["size"]), _face_family(kit, el["face"])
            f.bold = weight(el["face"]) >= 600
            f.italic = ty.style(el["face"]) == "italic"
            f.color.rgb = rgb(el["color"])
            if el.get("track"):
                f._rPr.set("spc", str(int(el["track"] * el["size"] * 100)))
        if el.get("marks"):
            m = p.add_run()
            m.text = "\u2009" + el["marks"]
            m.font.size, m.font.name = pt(max(el["size"] * 0.5, 9)), _face_family(kit, el["face"])
            m.font.color.rgb = rgb(el["color"])
            m.font._rPr.set("baseline", "30000")
        return p

    def ph(slide, i):
        for shp in slide.placeholders:
            if shp.placeholder_format.idx == i:
                return shp
        return None

    def drop_unused(slide, keep):
        for shp in list(slide.placeholders):
            if shp.placeholder_format.idx not in keep:
                shp._element.getparent().remove(shp._element)

    def shape_rect(slide, el, oval=False):
        shp = slide.shapes.add_shape(9 if oval else 1, emu(el["x"]), emu(el["y"]), emu(max(el["w"], 0.5)), emu(max(el["h"], 0.5)))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(el["fill"])
        shp.line.fill.background()
        shp.shadow.inherit = False
        if el.get("op") is not None:
            clr = shp.fill._xPr.find(f".//{{{A_NS}}}srgbClr")
            if clr is not None:
                etree.SubElement(clr, f"{{{A_NS}}}alpha", val=str(int(float(el["op"]) * 100000)))
        return shp

    def picture(slide, el, data, cover=True):
        try:
            iw, ih = pic_size(data)
            if cover:
                pic = slide.shapes.add_picture(io.BytesIO(data), emu(el["x"]), emu(el["y"]), emu(el["w"]), emu(el["h"]))
                box, img = el["w"] / el["h"], iw / ih if ih else 1
                if img > box:
                    cut = (1 - box / img) / 2
                    pic.crop_left = pic.crop_right = cut
                elif img < box:
                    cut = (1 - img / box) / 2
                    pic.crop_top = pic.crop_bottom = cut
            else:
                k = min(el["w"] / iw, el["h"] / ih) if iw and ih else 1
                w, h = iw * k, ih * k
                x = el["x"] if el.get("align") != "right" else el["x"] + el["w"] - w
                slide.shapes.add_picture(io.BytesIO(data), emu(x), emu(el["y"] + (el["h"] - h) / 2), emu(w), emu(h))
        except Exception:
            pass

    LAYOUT_OF = {"title": 0, "content": 1, "sources": 1, "section": 2, "closing": 2, "comparison": 4}
    for sc in scs:
        k = sc["kind"]
        s = prs.slides.add_slide(prs.slide_layouts[LAYOUT_OF.get(k, 5)])
        on_paper = sc["bg"].lower() == pal["paper"].lower()
        s.background.fill.solid()  # every slide states its ground, so another app reading the file sees the paper
        s.background.fill.fore_color.rgb = rgb(sc["bg"])
        if not on_paper:
            if logo_on_master:
                s._element.set("showMasterSp", "0")  # the master's logo is set for the paper; this slide carries its own
        texts = [el for el in sc["els"] if el["t"] == "text"]
        title_el = next((el for el in texts if el.get("role") == "title"), None)
        if title_el is None and texts:  # a slide with no heading (a big number, a quote): its largest real line titles it
            words = [el for el in texts if len(" ".join(el["lines"]).strip("“”\"' ")) >= 3] or texts
            title_el = max(words, key=lambda el: el["size"])
        body_els = [el for el in texts if el.get("role") == "body"] if k in ("content", "sources", "comparison") else []
        use_body = k in ("content", "sources") and len(body_els) >= 1
        keep = {0, 1} if use_body or k in ("title", "section", "closing") else {0}
        drop_unused(s, keep)
        marker = next((el for el in sc["els"] if el.get("mk")), None)
        for el in sc["els"]:
            t = el["t"]
            if el.get("mk") and use_body:
                continue  # the bullet is the paragraph's own (native), not a drawn square
            if t in ("rect", "dot"):
                shape_rect(s, el, oval=(t == "dot"))
            elif t == "image" and (pictures or {}).get(el.get("name")):
                picture(s, el, pictures[el["name"]], cover=True)
            elif t == "logo":
                if not on_paper or not logo_on_master:
                    data = logos.get(el.get("place")) or logos.get("paper")
                    if data:
                        picture(s, el, data, cover=False)
            elif t == "text":
                if el is title_el:
                    tf = frame(ph(s, 0), el)
                    para(tf, el, True)
                elif use_body and el in body_els:
                    continue
                else:
                    tf = frame(s.shapes.add_textbox(emu(el["x"]), emu(el["y"]), emu(el["w"]), emu(el["h"])), el)
                    para(tf, el, True)
        if use_body:
            body = ph(s, 1)
            x0 = min(el["x"] for el in body_els)
            box = {"x": x0 - (30 if marker else 0), "y": body_els[0]["y"], "w": max(el["x"] + el["w"] for el in body_els) - x0 + (30 if marker else 0),
                   "h": body_els[-1]["bottom"] - body_els[0]["y"], "align": "left"}
            tf = frame(body, box)
            prev = None
            for i, el in enumerate(body_els):
                mk = None
                if marker:
                    mk = ("\u25aa" if marker["t"] == "rect" and marker["w"] <= 12 else "\u2013", marker.get("fill") or pal["accent"])
                para(tf, el, i == 0, bullet=mk, space=0 if prev is None else el["y"] - prev["bottom"])
                prev = el
        for shp in list(s.placeholders):  # an empty placeholder left on a layout would show its prompt text
            if shp.placeholder_format.idx != 0 and shp.has_text_frame and not shp.text_frame.text.strip():
                shp._element.getparent().remove(shp._element)
        note = notes[sc["num"] - 1] if 0 <= sc["num"] - 1 < len(notes) else ""
        if note:
            s.notes_slide.notes_text_frame.text = note
    prs.core_properties.title = doc.get("title", "Deck")[:200]
    prs.core_properties.author = kit.get("org") or ""
    prs.core_properties.comments = "Made with Letterpress for Hermes"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- PDF --

def render_pdf(doc: dict, kit: dict, pal: dict, faces: dict, idx: dict, rows: list, colophon: str, date: str = "",
               logo=None, passages: Optional[dict] = None, pictures: Optional[dict] = None) -> bytes:
    rl = RP._rl()
    scs, ty = scenes(doc, kit, pal, faces, idx, rows, date, passages)
    logos = logo_bytes(logo)
    buf = io.BytesIO()
    c = rl["rlcanvas"].Canvas(buf, pagesize=(SLIDE_W, SLIDE_H), pageCompression=1, initialFontName=ty.name("body"))
    c.setTitle(doc.get("title", "Deck"))
    c.setAuthor(kit.get("org") or "")
    c.setCreator("Letterpress for Hermes")
    for sc in scs:
        SC.draw_pdf(c, sc, ty, pictures=pictures, logos=logos)
        if colophon and sc["num"] == 1:  # only when asked for; the finished deck carries no production note
            c.setFillColor(rl["rlc"].HexColor(pal["ink"]))
            c.setFont(ty.name("body"), 9)
            c.drawString(64, 14, colophon[:150])
        c.showPage()
    c.save()
    return buf.getvalue()


def slide_count(doc: dict, kit: dict, rows: list) -> int:
    n = 1 + len(doc.get("slides") or [])
    cap = doc.get("max_slides") if isinstance(doc.get("max_slides"), int) else None
    return n + (1 if (kit.get("rules") or {}).get("sources") and rows and not cap and sources_page(doc) else 0)


# ---------------------------------------------------------------- split to fit (round 13) --
CONTINUED = " (continued)"
ROOMY = "open"  # the content composition with the most room: the points in two full-width columns


def split_to_fit(doc: dict, kit: dict, pal: dict, faces: dict, passages: Optional[dict] = None, date: str = "",
                 rounds: int = 30) -> tuple:
    """``(doc, splits)``: a point list that does not fit its slide is split into two slides, the second under the same
    heading with "(continued)", until every slide fits. No point is trimmed, shortened or dropped to fit. ``splits``
    names each split as ``(doc slide index, points kept, points moved)``; a one-point slide that still runs long is
    left as it is (it cannot be split without cutting a sentence)."""
    try:
        from . import layout as L
    except ImportError:  # loaded loose
        import layout as L  # type: ignore
    import copy as _copy
    doc = _copy.deepcopy(doc)
    passages = passages or {}
    splits = []
    for _ in range(rounds):
        idx, rows = L.source_index(doc, passages)
        scs, _ty = scenes(doc, kit, pal, faces, idx, rows, date, passages)
        hit = None
        for i, sl in enumerate(doc.get("slides") or []):
            if i + 1 < len(scs) and (scs[i + 1].get("long") or overruns(scs[i + 1])) and sl.get("type") == "content" \
                    and len(sl.get("bullets") or []) >= 2 and sl.get("comp") != ROOMY:
                hit = i
                break
        if hit is None:
            break
        sl = doc["slides"][hit]
        # Round 15: the slide count holds (the notes' limit and the draft's own count). Text that does not fit moves to
        # the composition that holds the most (the points in two full-width columns, set down to the type floor); a
        # slide is never added and never headed "(continued)".
        sl["comp"] = ROOMY
        splits.append((hit, "moved to " + ROOMY))
        continue
        bl = sl["bullets"]
        k = (len(bl) + 1) // 2
        head = sl.get("heading", "")
        a = {**sl, "bullets": bl[:k], "refs": _refs_of(bl[:k], sl.get("refs"))}
        b = {**sl, "bullets": bl[k:], "refs": _refs_of(bl[k:], sl.get("refs")),
             "heading": head if head.endswith(CONTINUED) else head + CONTINUED}
        doc["slides"][hit:hit + 1] = [a, b]
        splits.append((hit, k, len(bl) - k))
    return doc, splits


def overruns(sc: dict, foot: float = 44.0) -> bool:
    """Round 14: whether set text runs into the footer band. Each block can fit its own box while the stack of many
    short points still ends past the foot's top, so the measured bottoms decide, not the block's own long mark."""
    h = sc.get("h") or 0
    for el in sc.get("els") or []:
        if el.get("t") != "text" or el.get("y", 0) >= h - foot - 16:
            continue  # the foot's own lines (source, folio) sit in the band
        if el.get("bottom", 0) > h - foot:
            return True
    return False


def _refs_of(bullets: list, fallback) -> list:
    out = []
    for b in bullets:
        if b.get("ref") and b["ref"] not in out:
            out.append(b["ref"])
    return out or list(fallback or [])
