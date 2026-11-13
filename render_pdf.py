"""The PDF export, in reportlab, following the same five layout families as the preview.

- The kit's TrueType fonts are embedded (subset by reportlab); a substituted face is the PDF's own
  Times, Helvetica or Courier, and the colophon says which.
- The page is always one US Letter page: the body is fitted with ``KeepInFrame(mode="shrink")``, so a
  long draft gets slightly smaller type rather than a second page. Body text never drops below 9.5pt;
  past that the export asks for a shorter draft instead.
- The kit's color bar and the colophon print only on the proof (``proof=True``), with a slug around the
  trim, crop marks and the PDF trim box, the way a printer's proof looks. The finished PDF carries neither.
- A PNG or JPG logo is placed; an SVG logo shows in the preview and HTML only, and a check says so.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Optional

try:
    from . import colors as C
except ImportError:  # loaded loose
    import colors as C  # type: ignore

LETTER = (612.0, 792.0)
SLUG = 36.0
MIN_BODY = 9.5


class PdfUnavailable(RuntimeError):
    pass


def _rl():
    try:
        import reportlab  # noqa: F401
        from reportlab.lib import colors as rlc
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (Flowable, Frame, KeepInFrame, ListFlowable, ListItem, Paragraph, Spacer, Table,
                                        TableStyle)
        from reportlab.pdfgen import canvas as rlcanvas
    except ImportError:
        raise PdfUnavailable("PDF export needs the reportlab library, which isn't installed. Reinstall Letterpress to add it.")
    return locals()


def raster(logo, place: str = "paper"):
    """A drawable PNG or JPG for one ground, or ``None``. ``logo`` is a Path, or the variants from
    ``kits.logo_variants`` (``{"paper": {data, kind, ...}, "band": {...}}``) so a mark that would vanish on
    the band is drawn knocked out there. SVG logos show in the preview and HTML only."""
    if isinstance(logo, dict):
        v = logo.get(place) or logo.get("paper")
        if not v or v.get("kind") not in (".png", ".jpg", ".jpeg"):
            return None
        return io.BytesIO(v["data"])
    if logo is not None and Path(logo).suffix.lower() in (".png", ".jpg", ".jpeg"):
        return logo
    return None


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_registered: set = set()


def register_faces(faces: dict) -> dict:
    """Register each embedded face once; returns role -> reportlab font name."""
    rl = _rl()
    names = {}
    for role, f in faces.items():
        if f.get("file"):
            name = f"imp-{f['key']}"
            if name not in _registered:
                try:
                    font = rl["TTFont"](name, f["file"])
                    # Static instances of one family often share a PostScript name (Inter Regular and Bold
                    # both say "Inter-Regular"); reportlab keys faces by that name, so one weight would
                    # silently replace the other. Each registered face gets its own name.
                    font.face.name = font.face.name + b"-" + re.sub(r"[^A-Za-z0-9-]", "", f["key"]).encode("ascii")
                    rl["pdfmetrics"].registerFont(font)
                    _registered.add(name)
                except Exception:
                    names[role] = f.get("pdf") or "Helvetica"
                    continue
            names[role] = name
        else:
            names[role] = f.get("pdf") or "Helvetica"
    body = names.get("body", "Helvetica")
    fam = f"imp-fam-{body}"
    try:
        rl["pdfmetrics"].registerFontFamily(fam, normal=body, bold=names.get("body_bold", body),
                                            italic=names.get("body_italic", body), boldItalic=names.get("body_bold", body))
    except Exception:
        pass
    return names


def styles(kit: dict, pal: dict, names: dict, shrink: float = 1.0) -> dict:
    rl = _rl()
    PS = rl["ParagraphStyle"]
    hx = rl["rlc"].HexColor
    base = {"airy": 11.0, "medium": 10.5, "dense": 10.0}.get(kit.get("density"), 10.5) * shrink
    sc = float((kit.get("type") or {}).get("scale") or 1.25)
    head, body = names.get("heading", "Helvetica-Bold"), names.get("body", "Helvetica")
    bold = names.get("body_bold", body)
    ink, headc, acc, acct = hx(pal["ink"]), hx(pal["head"]), hx(pal["accent"]), hx(pal["accent_text"])
    gap = {"airy": 1.3, "medium": 1.0, "dense": 0.8}.get(kit.get("density"), 1.0)
    layout = kit.get("layout")
    title_size = min(base * sc ** (4.6 if layout == "headline" else 3.6), 54 if layout == "headline" else 34)

    def ps(name, **kw):
        d = dict(fontName=body, fontSize=base, leading=base * 1.42, textColor=ink, alignment=rl["TA_LEFT"], spaceAfter=0)
        d.update(kw)
        return PS(name, **d)

    return {
        "base": base, "gap": gap,
        "title": ps("title", fontName=head, fontSize=title_size, leading=title_size * 1.08, textColor=headc),
        "title_band": ps("title_band", fontName=head, fontSize=min(title_size, 30), leading=min(title_size, 30) * 1.1,
                         textColor=hx(pal.get("band_text") or pal["paper"])),
        "org_band": ps("org_band", fontSize=base * 0.95, textColor=hx(pal.get("band_text") or pal["paper"])),
        "org": ps("org", fontSize=base * 0.95),
        "dek": ps("dek", fontSize=base * sc, leading=base * sc * 1.38),
        "h2": ps("h2", fontName=head, fontSize=base * sc * sc * 0.92, leading=base * sc * sc * 1.12, textColor=headc,
                 spaceAfter=3 * gap),
        "body": ps("body"),
        "stat_value": ps("stat_value", fontName=head, fontSize=min(base * sc ** 3.6, 46), leading=min(base * sc ** 3.6, 46) * 1.02, textColor=acc),
        "stat_label": ps("stat_label", fontSize=base * 0.96),
        "small_head": ps("small_head", fontName=head, fontSize=base, textColor=headc, spaceAfter=3),
        "point": ps("point", leading=base * 1.36),
        "quote": ps("quote", fontName=names.get("body_italic", body), fontSize=base * sc, leading=base * sc * 1.36),
        "quote_who": ps("quote_who", fontName=bold, fontSize=base * 0.92),
        "next": ps("next", fontName=bold, textColor=acct, fontSize=base * 1.04),
        "src": ps("src", fontSize=max(base * 0.82, 8.0), leading=max(base * 0.82, 8.0) * 1.35),
        "required": ps("required", fontName=bold, fontSize=base * 0.9),
        "memo_label": ps("memo_label", fontName=head, fontSize=base * 0.92, textColor=acct),
        "memo_value": ps("memo_value", fontName=head, fontSize=base * sc * sc, leading=base * sc * sc * 1.18, textColor=headc),
        "memo_plain": ps("memo_plain"),
        "menu_name": ps("menu_name", fontName=bold),
        "menu_price": ps("menu_price", fontName=head, textColor=acct, alignment=2),
        "menu_note": ps("menu_note", fontSize=base * 0.92, leading=base * 0.92 * 1.32),
        "title_flyer": ps("title_flyer", fontName=head, fontSize=min(base * sc ** 5, 52), leading=min(base * sc ** 5, 52) * 1.04,
                          textColor=headc, alignment=1),
        "dek_center": ps("dek_center", fontSize=base * sc, leading=base * sc * 1.38, alignment=1),
        "org_center": ps("org_center", fontSize=base * 0.95, alignment=1),
        "center_bold": ps("center_bold", fontName=bold, alignment=1),
        "stat_center": ps("stat_center", fontName=head, fontSize=min(base * sc ** 3.6, 46), leading=min(base * sc ** 3.6, 46) * 1.06,
                          textColor=acc, alignment=1),
        "label_center": ps("label_center", fontSize=base * 0.96, alignment=1),
        "cta": ps("cta", fontName=head, fontSize=base * sc * sc, leading=base * sc * sc * 1.25, alignment=1,
                  textColor=hx(pal.get("band_text") or pal["paper"])),
        "sidehead": ps("sidehead", fontName=head, fontSize=base * sc, leading=base * sc * 1.2, textColor=headc),
        "pull": ps("pull", fontName=names.get("body_italic", body), fontSize=base * sc * sc, leading=base * sc * sc * 1.3),
    }


def _case(kit: dict, text: str) -> str:
    return text.upper() if ((kit.get("type") or {}).get("heading") or {}).get("case") == "upper" else text


def _sup(refs: list, idx: dict, color: str) -> str:
    nums = sorted({idx[r] for r in refs or [] if r in idx})
    if not nums:
        return ""
    return f'<super><font color="{color}" size="7">{",".join(str(i) for i in nums)}</font></super>'


class Build:
    """Flowables for one page in one kit."""

    def __init__(self, doc, kit, pal, faces, idx, rows, date, st, rl):
        self.doc, self.kit, self.pal, self.faces, self.idx, self.rows, self.date, self.st, self.rl = \
            doc, kit, pal, faces, idx, rows, date, st, rl

    def P(self, text, style):
        return self.rl["Paragraph"](re.sub(r"([\d%])(<super>)", r"\1&nbsp;\2", text), self.st[style])

    def sp(self, h):
        return self.rl["Spacer"](1, h * self.st["gap"])

    def dek(self):
        d = self.doc
        return self.P(esc(d.get("dek", "")) + _sup(d.get("dek_refs"), self.idx, self.pal["accent_text"]), "dek")

    def stat(self, filled=False, width=None):
        st = self.doc.get("stat")
        if not st:
            return []
        inner = [self.P(esc(st["value"]), "stat_value"), self.rl["Spacer"](1, 3),
                 self.P(esc(st.get("label", "")) + _sup([st.get("ref")], self.idx, self.pal["accent_text"]), "stat_label")]
        if filled and self.pal.get("fill") and width:
            t = self.rl["Table"]([[inner]], colWidths=[width])
            t.setStyle(self.rl["TableStyle"]([("BACKGROUND", (0, 0), (-1, -1), self.rl["rlc"].HexColor(self.pal["fill"])),
                                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                              ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
            return [t]
        return inner

    def points(self, head=None, ordered=False):
        pts = self.doc.get("points") or []
        if not pts:
            return []
        items = [self.rl["ListItem"](self.P(esc(p["text"]) + _sup([p.get("ref")], self.idx, self.pal["accent_text"]), "point"),
                                     leftIndent=12) for p in pts]
        lf = self.rl["ListFlowable"](items, bulletType="1" if ordered else "bullet", start=1 if ordered else None,
                                     bulletColor=self.rl["rlc"].HexColor(self.pal["accent"]),
                                     bulletFontName=self.st["body"].fontName, bulletFontSize=self.st["base"] * (0.9 if ordered else 0.75),
                                     leftIndent=12)
        out = [self.P(esc(_case(self.kit, head)), "small_head")] if head else []
        return out + [lf]

    def menu(self, items):
        """Items with prices: name and price on a line with a dotted rule under it, the note below."""
        if not items:
            return []
        rl = self.rl
        rows = []
        for it in items:
            left = [self.P(esc(it.get("name", "")), "menu_name")]
            if it.get("note"):
                left.append(self.P(esc(it["note"]), "menu_note"))
            rows.append([left, self.P(esc(it.get("price", "")), "menu_price")])
        t = rl["Table"](rows, colWidths=["*", 72])
        t.setStyle(rl["TableStyle"]([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                                     ("LINEBELOW", (0, 0), (-1, -1), 0.5, rl["rlc"].HexColor(self.pal["rule"]), None, (1, 2))]))
        return [t]

    def sections(self, runin=False):
        out = []
        for s in self.doc.get("sections") or []:
            sup = _sup(s.get("refs"), self.idx, self.pal["accent_text"])
            if s.get("items"):
                head = esc(_case(self.kit, s.get("heading", ""))) + ("" if s.get("body") else sup)
                out += [self.P(head, "h2")] + ([self.P(esc(s["body"]) + sup, "body"), self.sp(4)] if s.get("body") else [])
                out += self.menu(s["items"]) + [self.sp(10)]
                continue
            if runin:
                head = f'<font name="{self.st["h2"].fontName}" color="{self.pal["head"]}">{esc(s.get("heading", ""))}.</font> ' if s.get("heading") else ""
                out += [self.P(head + esc(s["body"]) + sup, "body"), self.sp(7)]
            else:
                out += [self.P(esc(_case(self.kit, s.get("heading", ""))), "h2"), self.P(esc(s["body"]) + sup, "body"), self.sp(10)]
        return out

    def quote(self):
        q = self.doc.get("quote")
        if not q:
            return []
        inner = [self.P(f"“{esc(q['text'])}”" + _sup([q.get("ref")], self.idx, self.pal["accent_text"]), "quote")]
        if q.get("who"):
            inner += [self.rl["Spacer"](1, 3), self.P(esc(q["who"]), "quote_who")]
        t = self.rl["Table"]([[inner]])
        t.setStyle(self.rl["TableStyle"]([("LINEBEFORE", (0, 0), (0, -1), 2.5, self.rl["rlc"].HexColor(self.pal["accent"])),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 11), ("TOPPADDING", (0, 0), (-1, -1), 2),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return [t]

    def nxt(self):
        return [self.P(esc(self.doc["next"]), "next")] if self.doc.get("next") else []

    def foot(self, with_sources=True):
        out = []
        rules = self.kit.get("rules") or {}
        if with_sources and rules.get("sources") and self.rows:
            out.append(self.P(esc(_case(self.kit, "Sources")), "small_head"))
            for r in self.rows:
                loc = (", " + ", ".join(r["locators"][:6])) if r["locators"] else ""
                out.append(self.P(f"{r['n']}. {esc(r['title'])}{esc(loc)}", "src"))
        for line in rules.get("required") or []:
            out += [self.rl["Spacer"](1, 4), self.P(esc(line), "required")]
        if out:
            out = [self.Rule(), self.rl["Spacer"](1, 6)] + out
        return out

    def Rule(self, color=None, width=0.75):
        rl = self.rl
        col = rl["rlc"].HexColor(color or self.pal["rule"])

        class _Rule(rl["Flowable"]):
            def wrap(self, aw, ah):
                self.w = aw
                return aw, width + 1

            def draw(self):
                self.canv.setStrokeColor(col)
                self.canv.setLineWidth(width)
                self.canv.line(0, 0, self.w, 0)
        return _Rule()

    def org_text(self, style="org"):
        rules = self.kit.get("rules") or {}
        bits = []
        if self.kit.get("org"):
            bits.append(f"<b>{esc(self.kit['org'])}</b>")
        if rules.get("date", True) and self.date:
            bits.append(esc(self.date))
        return [self.P("&nbsp;&nbsp;&nbsp;".join(bits), style)] if bits else []


def _two_col(b: Build, left: list, right: list, width: float, ratio: float = 1 / 3, rule=False) -> list:
    rl = b.rl
    gutter = 18
    lw = (width - gutter) * ratio
    rw = width - gutter - lw
    t = rl["Table"]([[left or [rl["Spacer"](1, 1)], right or [rl["Spacer"](1, 1)]]], colWidths=[lw, rw + gutter])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), gutter / 2),
             ("LEFTPADDING", (1, 0), (1, 0), gutter / 2), ("RIGHTPADDING", (1, 0), (1, 0), 0),
             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]
    if rule:
        style.append(("LINEAFTER", (0, 0), (0, -1), 0.75, rl["rlc"].HexColor(b.pal["rule"])))
    t.setStyle(rl["TableStyle"](style))
    return [t]


def _story(b: Build, width: float, layout: str) -> list:
    if layout == "banner":
        side = b.stat(filled=True, width=(width - 18) / 3) + [b.sp(12)] + b.points(head="At a glance")
        return [b.dek(), b.sp(14)] + _two_col(b, side, b.sections(), width) + [b.sp(8)] + b.quote() + [b.sp(10)] + b.nxt() + ["FILL", b.sp(12)] + b.foot()
    if layout == "headline":
        top = b.org_text() + [b.sp(10), b.P(esc(_case(b.kit, b.doc["title"])), "title"), b.Rule(b.pal.get("highlight") or b.pal["accent"], 3), b.sp(10)]
        head_row = _two_col(b, [b.dek()], b.stat(), width, ratio=0.62) if b.doc.get("stat") else [b.dek()]
        secs = b.doc.get("sections") or []
        tiles = []
        if secs:
            half = (len(secs) + 1) // 2
            sub_a = Build({**b.doc, "sections": secs[:half]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
            sub_b = Build({**b.doc, "sections": secs[half:]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
            tiles = _two_col(b, sub_a.sections(), sub_b.sections(), width, ratio=0.5)
        return top + head_row + [b.sp(14), b.Rule(), b.sp(10)] + tiles + b.points() + [b.sp(8)] + b.quote() + [b.sp(10)] + b.nxt() + ["FILL", b.sp(10)] + b.foot()
    if layout == "margin":
        rail = b.stat() + [b.sp(14)] + b.points(head="Key points") + [b.sp(12)] + b.quote() + [b.sp(12)] + b.foot()
        main = b.org_text() + [b.sp(8), b.P(esc(_case(b.kit, b.doc["title"])), "title"), b.sp(8), b.dek(), b.sp(14)] + b.sections() + b.nxt() + b.foot(with_sources=False)
        return _two_col(b, rail, main, width, ratio=0.3, rule=True)
    if layout == "letter":
        rl = b.rl
        rows = [[b.P("Re", "memo_label"), b.P(esc(b.doc["title"]), "memo_value")]]
        if (b.kit.get("rules") or {}).get("date", True) and b.date:
            rows.append([b.P("Date", "memo_label"), b.P(esc(b.date), "memo_plain")])
        if b.kit.get("org"):
            rows.append([b.P("From", "memo_label"), b.P(esc(b.kit["org"]), "memo_plain")])
        memo = rl["Table"](rows, colWidths=[52, width - 52])
        memo.setStyle(rl["TableStyle"]([("VALIGN", (0, 0), (-1, -1), "BASELINE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        stat = []
        if b.doc.get("stat"):
            st = b.doc["stat"]
            cell = rl["Table"]([[b.P(esc(st["value"]), "stat_value"),
                                 b.P(esc(st.get("label", "")) + _sup([st.get("ref")], b.idx, b.pal["accent_text"]), "stat_label")]],
                               colWidths=[width * 0.28, width * 0.72])
            style = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
            if b.pal.get("fill"):
                style.append(("BACKGROUND", (0, 0), (-1, -1), rl["rlc"].HexColor(b.pal["fill"])))
            cell.setStyle(rl["TableStyle"](style))
            stat = [cell, b.sp(10)]
        return [memo, b.sp(6), b.Rule(width=1.5), b.sp(12), b.dek(), b.sp(12)] + b.sections(runin=True) + stat + \
            b.points(head="Findings", ordered=True) + [b.sp(8)] + b.quote() + [b.sp(10)] + b.nxt() + ["FILL", b.sp(12)] + b.foot()
    if layout == "flyer":
        rl = b.rl
        d = b.doc
        org = [b.P("&nbsp;&nbsp;&nbsp;".join(x for x in [f"<b>{esc(b.kit['org'])}</b>" if b.kit.get("org") else "",
                                                        esc(b.date) if (b.kit.get("rules") or {}).get("date", True) and b.date else ""] if x),
                   "org_center")] if (b.kit.get("org") or b.date) else []
        top = org + [b.sp(8), b.P(esc(_case(b.kit, d["title"])), "title_flyer"), b.sp(8),
                     b.P(esc(d.get("dek", "")) + _sup(d.get("dek_refs"), b.idx, b.pal["accent_text"]), "dek_center"), b.sp(10),
                     b.Rule(b.pal["accent"], 3), b.sp(14)]
        stamp = []
        if d.get("stat"):
            st = d["stat"]
            cell = rl["Table"]([[[b.P(esc(st["value"]), "stat_center"), rl["Spacer"](1, 4),
                                  b.P(esc(st.get("label", "")) + _sup([st.get("ref")], b.idx, b.pal["accent_text"]), "label_center")]]],
                               colWidths=[width * 0.5])
            style = [("BOX", (0, 0), (-1, -1), 1.5, rl["rlc"].HexColor(b.pal["accent"])), ("TOPPADDING", (0, 0), (-1, -1), 10),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 12), ("ALIGN", (0, 0), (-1, -1), "CENTER")]
            if b.pal.get("fill"):
                style.append(("BACKGROUND", (0, 0), (-1, -1), rl["rlc"].HexColor(b.pal["fill"])))
            cell.setStyle(rl["TableStyle"](style))
            cell.hAlign = "CENTER"
            stamp = [cell, b.sp(16)]
        secs = d.get("sections") or []
        half = (len(secs) + 1) // 2
        sub_a = Build({**d, "sections": secs[:half]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
        sub_b = Build({**d, "sections": secs[half:]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
        cols = _two_col(b, sub_a.sections(), sub_b.sections(), width, ratio=0.5) if len(secs) > 1 else b.sections()
        pts = d.get("points") or []
        line = "&nbsp;&nbsp;&nbsp;&#8226;&nbsp;&nbsp;&nbsp;".join(esc(p["text"]) + _sup([p.get("ref")], b.idx, b.pal["accent_text"]) for p in pts)
        points = [b.sp(6), b.P(line, "center_bold"), b.sp(12)] if pts else []
        cta = []
        if d.get("next"):
            t = rl["Table"]([[b.P(esc(d["next"]), "cta")]], colWidths=[width])
            t.setStyle(rl["TableStyle"]([("BACKGROUND", (0, 0), (-1, -1), rl["rlc"].HexColor(b.pal.get("band") or b.pal["head"])),
                                         ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 14)]))
            cta = [b.sp(10), t]
        return top + stamp + cols + points + b.quote() + ["FILL"] + cta + [b.sp(8)] + b.foot()
    if layout == "report":
        rl = b.rl
        d = b.doc
        top = b.org_text() + [b.sp(8), b.P(esc(_case(b.kit, d["title"])), "title"), b.sp(8), b.dek(), b.sp(14)]
        figs = []
        if d.get("stat"):
            st = d["stat"]
            figs.append([b.P(esc(st["value"]), "stat_value"), rl["Spacer"](1, 3),
                         b.P(esc(st.get("label", "")) + _sup([st.get("ref")], b.idx, b.pal["accent_text"]), "stat_label")])
        for p in (d.get("points") or [])[:3]:
            figs.append([b.P(f"<b>{esc(p['text'])}</b>" + _sup([p.get("ref")], b.idx, b.pal["accent_text"]), "point")])
        fig_row = []
        if figs:
            n_f = len(figs)
            gw = 14
            cw = (width - gw * (n_f - 1)) / n_f
            cells, widths = [], []
            for i, f in enumerate(figs):
                cells.append(f)
                widths.append(cw)
                if i < n_f - 1:
                    cells.append("")
                    widths.append(gw)
            t = rl["Table"]([cells], colWidths=widths)
            style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                     ("TOPPADDING", (0, 0), (-1, -1), 7)]
            for i in range(0, 2 * n_f - 1, 2):
                style.append(("LINEABOVE", (i, 0), (i, 0), 2.5, rl["rlc"].HexColor(b.pal["accent"])))
            t.setStyle(rl["TableStyle"](style))
            fig_row = [t, b.sp(16)]
        rows = []
        for sec in d.get("sections") or []:
            right = ([b.P(esc(sec["body"]) + _sup(sec.get("refs"), b.idx, b.pal["accent_text"]), "body")] if sec.get("body") else []) + b.menu(sec.get("items") or [])
            t = rl["Table"]([[b.P(esc(_case(b.kit, sec.get("heading", ""))), "sidehead"), right or ""]], colWidths=[width * 0.27, width * 0.73])
            t.setStyle(rl["TableStyle"]([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (0, 0), 14), ("RIGHTPADDING", (1, 0), (1, 0), 0),
                                         ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                                         ("LINEABOVE", (0, 0), (-1, 0), 0.75, rl["rlc"].HexColor(b.pal["rule"]))]))
            rows.append(t)
        pull = []
        if d.get("quote"):
            q = d["quote"]
            inner = [b.P(f"“{esc(q['text'])}”" + _sup([q.get("ref")], b.idx, b.pal["accent_text"]), "pull")]
            if q.get("who"):
                inner += [rl["Spacer"](1, 4), b.P(esc(q["who"]), "quote_who")]
            t = rl["Table"]([[inner]], colWidths=[width])
            t.setStyle(rl["TableStyle"]([("LINEABOVE", (0, 0), (-1, 0), 2, rl["rlc"].HexColor(b.pal["accent"])),
                                         ("LINEBELOW", (0, -1), (-1, -1), 2, rl["rlc"].HexColor(b.pal["accent"])),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 10),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
            pull = [b.sp(8), t]
        return top + fig_row + rows + pull + [b.sp(12)] + b.nxt() + ["FILL"] + [b.sp(10)] + b.foot()
    # bulletin
    name = b.org_text() + [b.sp(6), b.P(esc(_case(b.kit, b.doc["title"])), "title"), b.sp(6), b.dek(), b.sp(8), b.Rule(b.pal["head"], 2.5), b.sp(12)]
    side = b.stat(filled=True, width=(width - 18) / 3) + [b.sp(12)] + b.points(head="This week")
    secs = b.doc.get("sections") or []
    half = (len(secs) + 1) // 2
    sub_a = Build({**b.doc, "sections": secs[:half]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
    sub_b = Build({**b.doc, "sections": secs[half:]}, b.kit, b.pal, b.faces, b.idx, b.rows, b.date, b.st, b.rl)
    main_w = (width - 18) * 2 / 3
    cols = _two_col(b, sub_a.sections(), sub_b.sections(), main_w, ratio=0.5, rule=True)
    return name + _two_col(b, side, cols, width) + [b.sp(8)] + b.quote() + [b.sp(10)] + b.nxt() + ["FILL", b.sp(10)] + b.foot()


def render(doc: dict, kit: dict, pal: dict, faces: dict, idx: dict, rows: list, colophon: str, date: str = "",
           logo=None, proof: bool = False) -> bytes:
    """One page, as PDF bytes."""
    rl = _rl()
    try:
        from . import layout as L
    except ImportError:  # loaded loose
        import layout as L  # type: ignore
    if L.uses_scene_page(kit) and doc.get("sections") is not None and "segments" not in doc:
        return _scene_page(doc, kit, pal, faces, idx, rows, date, logo, proof, rl)
    names = register_faces(faces)
    off = SLUG if proof else 0.0
    W, H = LETTER[0] + 2 * off, LETTER[1] + 2 * off
    buf = io.BytesIO()
    # the page's own body face from the start, so no unused base-14 Helvetica is listed in the file
    c = rl["rlcanvas"].Canvas(buf, pagesize=(W, H), pageCompression=1, initialFontName=names.get("body", "Helvetica"))
    c.setTitle(doc.get("title", "Brief"))
    c.setAuthor(kit.get("org") or "")
    c.setCreator("Letterpress for Hermes")
    hx = rl["rlc"].HexColor
    # paper
    c.setFillColor(hx(pal["paper"]))
    c.rect(off, off, LETTER[0], LETTER[1], stroke=0, fill=1)
    layout = kit.get("layout") or "banner"
    mx, top_m, foot_h = 46.0, 44.0, 40.0
    width = LETTER[0] - 2 * mx
    top = off + LETTER[1] - top_m
    st = styles(kit, pal, names)

    # banner: draw the band with org and title, measured
    if layout == "banner":
        org_p = rl["Paragraph"]("&nbsp;&nbsp;&nbsp;".join(x for x in [f"<b>{esc(kit['org'])}</b>" if kit.get("org") else "",
                                                                      esc(date) if (kit.get("rules") or {}).get("date", True) and date else ""] if x),
                                st["org_band"])
        title_p = rl["Paragraph"](esc(_case(kit, doc["title"])), st["title_band"])
        band_logo = raster(logo, "band")
        logo_h = 26 if band_logo is not None else 0
        _, oh = org_p.wrap(width - (logo_h * 3 if logo_h else 0), 100)
        _, th = title_p.wrap(width, 300)
        band_h = 26 + max(oh, logo_h) + 10 + th + 24
        c.setFillColor(hx(pal.get("band") or pal["head"]))
        c.rect(off, off + LETTER[1] - band_h, LETTER[0], band_h, stroke=0, fill=1)
        y = off + LETTER[1] - 26
        x = off + mx
        if logo_h:
            x += _logo(c, rl, band_logo, x, y - logo_h, logo_h) + 12
        org_p.drawOn(c, x, y - oh)
        y -= max(oh, logo_h) + 10
        title_p.drawOn(c, off + mx, y - th)
        top = off + LETTER[1] - band_h - 20
    elif raster(logo, "paper") is not None:
        _logo(c, rl, raster(logo, "paper"), off + LETTER[0] - mx - 90, off + LETTER[1] - 34, 22, right=True)

    # body: grown to fill the page when it runs short (no empty bottom third), shrunk to fit if it runs long,
    # and what space is left goes above the foot, so the sources and required lines sit at the bottom
    bottom = off + foot_h + 18
    frame_h = top - bottom
    grow = fill_scale(doc, kit, pal, faces, idx, rows, date, names, width, frame_h, layout)
    if grow != 1.0:
        st = styles(kit, pal, names, shrink=grow)
    story = _story(Build(doc, kit, pal, faces, idx, rows, date, st, rl), width, layout)
    used = _height([f for f in story if f != "FILL"], width)
    gap = max(0.0, frame_h - used - 2)
    story = [rl["Spacer"](1, gap) if f == "FILL" else f for f in story]
    kif = rl["KeepInFrame"](width, frame_h, story, mode="shrink")
    frame = rl["Frame"](off + mx, bottom, width, frame_h, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, showBoundary=0)
    frame.addFromList([kif], c)

    # foot: the kit's color bar and the colophon are proof furniture; the finished page carries neither
    bar = (pal.get("bar") or []) if proof else []
    bx, bw = off + mx, width
    seg = bw / max(1, len(bar))
    for i, col in enumerate(bar):
        c.setFillColor(hx(col))
        c.rect(bx + i * seg, off + foot_h - 6, seg, 6, stroke=0, fill=1)
    if bar:  # a hairline keeps the paper swatch visible against the paper
        c.setStrokeColor(hx(C.mix(pal["ink"], pal["paper"], 0.6)))
        c.setLineWidth(0.4)
        c.rect(bx, off + foot_h - 6, bw, 6, stroke=1, fill=0)
    c.setFillColor(hx(pal["ink"]))
    c.setFont(names.get("body", "Helvetica"), 8.5)
    if proof:
        c.drawString(bx, off + foot_h - 20, colophon[:160])
    if proof and (kit.get("rules") or {}).get("page_numbers"):
        c.drawRightString(bx + bw, off + foot_h - 20, "1")

    if proof:
        _crop_marks(c, off, W, H)
        try:
            c.setTrimBox(off, off, off + LETTER[0], off + LETTER[1])
        except Exception:
            pass
    c.showPage()
    c.save()
    return buf.getvalue()


GROW_MAX = 1.42


def _height(story: list, width: float) -> float:
    total = 0.0
    for f in story:
        try:
            _, h = f.wrap(width, 100_000)
        except Exception:
            h = 0
        total += h
    return total


def fill_scale(doc, kit, pal, faces, idx, rows, date, names, width, frame_h, layout) -> float:
    """How much to enlarge the type so a short draft fills the sheet (1.0 when it already does). Kept to
    1.42x; the space still left goes above the foot."""
    rl = _rl()

    def height(k):
        story = _story(Build(doc, kit, pal, faces, idx, rows, date, styles(kit, pal, names, shrink=k), rl), width, layout)
        return _height([f for f in story if f != "FILL"], width)

    if height(1.0) >= frame_h * 0.9:
        return 1.0
    lo, hi = 1.0, GROW_MAX
    if height(hi) <= frame_h * 0.97:
        return hi
    for _ in range(7):
        mid = (lo + hi) / 2
        if height(mid) <= frame_h * 0.97:
            lo = mid
        else:
            hi = mid
    return round(lo, 3)


def fit_ratio(doc, kit, pal, faces, idx, rows, date="") -> float:
    """How much the body would shrink to fit (1.0 = fits as set). Used to warn before type gets small."""
    rl = _rl()
    names = register_faces(faces)
    st = styles(kit, pal, names)
    width = LETTER[0] - 92
    frame_h = LETTER[1] - 44 - 58 - (150 if kit.get("layout") == "banner" else 0)
    story = [f for f in _story(Build(doc, kit, pal, faces, idx, rows, date, st, rl), width, kit.get("layout") or "banner") if f != "FILL"]
    total = 0.0
    for f in story:
        try:
            _, h = f.wrap(width, 10_000)
        except Exception:
            h = 0
        total += h
    return min(1.0, frame_h / total) if total else 1.0


def _logo(c, rl, path, x: float, y: float, h: float, right: bool = False) -> float:
    """Draw the logo ``h`` points tall; returns the width it took (0 when it could not be drawn)."""
    try:
        img = rl["ImageReader"](path if not isinstance(path, Path) else str(path))
        iw, ih = img.getSize()
        w = min(h * iw / ih if ih else h, 180.0)
        c.drawImage(img, x if not right else x + 90 - w, y, width=w, height=h, mask="auto", preserveAspectRatio=True)
        return w
    except Exception:
        return 0.0


def _crop_marks(c, off: float, W: float, H: float) -> None:
    from reportlab.lib import colors as rlc
    c.setStrokeColor(rlc.black)
    c.setLineWidth(0.5)
    L = 18
    gap = 6
    for x in (off, W - off):
        for y in (off, H - off):
            sx = -1 if x == off else 1
            sy = -1 if y == off else 1
            c.line(x + sx * gap, y, x + sx * (gap + L), y)
            c.line(x, y + sy * gap, x, y + sy * (gap + L))


def _scene_page(doc, kit, pal, faces, idx, rows, date, logo, proof, rl) -> bytes:
    """A studio or imported brand's one-pager: the page scene its design system composes, drawn as the pane shows it.
    The finished page has no marks of the proof; a proof adds the trim slug and crop marks around it."""
    try:
        from . import layout as L
        from . import render_deck as RD
        from . import scene as SC
    except ImportError:  # loaded loose
        import layout as L  # type: ignore
        import render_deck as RD  # type: ignore
        import scene as SC  # type: ignore
    sc, ty = L.page_scene(doc, kit, pal, faces, {}, date, idx=idx or {}, rows=rows or [])
    off = SLUG if proof else 0.0
    W, H = LETTER[0] + 2 * off, LETTER[1] + 2 * off
    buf = io.BytesIO()
    c = rl["rlcanvas"].Canvas(buf, pagesize=(W, H), pageCompression=1, initialFontName=ty.name("body"))
    c.setTitle(doc.get("title", "Brief"))
    c.setAuthor(kit.get("org") or "")
    c.setCreator("Letterpress for Hermes")
    if off:
        c.saveState()
        c.translate(off, off)
    SC.draw_pdf(c, sc, ty, logos=RD.logo_bytes(logo))
    if off:
        c.restoreState()
        _crop_marks(c, off, W, H)
    c.showPage()
    c.save()
    return buf.getvalue()
