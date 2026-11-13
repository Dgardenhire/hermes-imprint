"""The graphic: one information graphic (1080 x 1350, 4:5), composed in the kit's design system (systems.py) and
written out as PNG, SVG and PDF from the same scene the pane shows.

One message per graphic: the headline states it, the chart shows it with every value labeled where it sits, and the
source line names where each figure came from. Numbers are the sources' own, checked like every other output.
"""

from __future__ import annotations

import io
from typing import Optional

try:
    from . import render_deck as RD
    from . import scene as SC
    from . import systems as SY
except ImportError:  # loaded loose
    import render_deck as RD  # type: ignore
    import scene as SC  # type: ignore
    import systems as SY  # type: ignore


def _marks(refs, idx):
    return RD._marks(refs, idx)


def spec(doc: dict, kit: dict, idx: dict, passages: dict) -> dict:
    """What the system draws: the headline and dek, the values as ``(label, value, number, marks)``, the steps, the
    takeaway, and the source line (only when the kit lists sources)."""
    items = doc.get("items") or []
    steps = doc.get("steps") or []
    refs = list(doc.get("dek_refs") or []) + [it.get("ref") for it in items + steps if it.get("ref")] + list(doc.get("takeaway_refs") or [])
    lists = bool((kit.get("rules") or {}).get("sources"))
    return {"kicker": doc.get("kicker", ""), "headline": doc.get("headline", ""), "dek": doc.get("dek", ""),
            "dek_marks": _marks(doc.get("dek_refs"), idx), "form": doc.get("form") or "bars", "unit": doc.get("unit", ""),
            "bars": [(it.get("label", ""), it.get("value", ""), SY.parse_value(it.get("value", "")), _marks([it.get("ref")], idx)) for it in items],
            "steps": [(st.get("when", ""), st.get("text", ""), _marks([st.get("ref")], idx)) for st in steps],
            "hi": next((i for i, it in enumerate(items) if it.get("accent") is True), None),
            "takeaway": doc.get("takeaway", ""), "take_marks": _marks(doc.get("takeaway_refs"), idx),
            "src": RD.source_line([r for r in refs if r], passages, limit=4) if lists else ""}


def scene(doc: dict, kit: dict, pal: dict, faces: dict, idx: dict, passages: dict) -> tuple:
    ty = SC.Type(RD.faces_for(kit, faces))
    sysm = SY.for_kit(kit, pal, ty, RD.system_of(kit))
    return sysm.graphic(spec(doc, kit, idx, passages)), ty


def tree(doc: dict, kit: dict, pal: dict, faces: dict, idx: dict, passages: dict, logo_urls: Optional[dict] = None) -> tuple:
    sc, ty = scene(doc, kit, pal, faces, idx, passages)
    node = SC.nodes(sc, ty, cls="ip-scene ip-graphic", logos=logo_urls)
    return {"t": "div", "c": f"ip-visual ip-visual-{RD.system_of(kit)}", "k": [node]}, sc


def render_png(doc, kit, pal, faces, idx, passages, logo=None, scale: float = 2.0) -> bytes:
    sc, ty = scene(doc, kit, pal, faces, idx, passages)
    return SC.png(sc, ty, scale=scale, logos=RD.logo_bytes(logo))


def render_svg(doc, kit, pal, faces, idx, passages, logo_urls: Optional[dict] = None) -> str:
    sc, ty = scene(doc, kit, pal, faces, idx, passages)
    return SC.svg(sc, ty, logos=logo_urls, title=doc.get("headline", ""))


def render_pdf(doc, kit, pal, faces, idx, passages, logo=None) -> bytes:
    from reportlab.pdfgen import canvas as rlcanvas
    sc, ty = scene(doc, kit, pal, faces, idx, passages)
    buf = io.BytesIO()
    c = rlcanvas.Canvas(buf, pagesize=(sc["w"], sc["h"]), pageCompression=1, initialFontName=ty.name("body"))
    c.setTitle(doc.get("headline", "Graphic"))
    c.setAuthor(kit.get("org") or "")
    c.setCreator("Letterpress for Hermes")
    SC.draw_pdf(c, sc, ty, logos=RD.logo_bytes(logo))
    c.showPage()
    c.save()
    return buf.getvalue()
