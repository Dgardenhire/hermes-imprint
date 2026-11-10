"""Spec slides (loop 4): the model designs each slide; Imprint brands it, traces it and checks it.

A spec slide is a list of positioned elements on the 960 x 540 slide, written by the model in brand roles, never in
hex values or font names:

    {"ground": "paper" | "primary",                     the slide's ground (primary: the brand's dark field)
     "footer": true,                                    the system's foot (source line, page number); false on a cover
     "els": [
       {"type": "text", x, y, w, h, "text", "style", "color", "align", "size"}
       {"type": "list", x, y, w, h, "items": [...], "style", "color", "size"}
       {"type": "rect", x, y, w, h, "fill"}
       {"type": "line", x, y, w, h, "color"}            a rule: one of w or h is its thickness
       {"type": "dot", x, y, w, h, "fill"}
       {"type": "figure", x, y, w, h, "value", "label", "note", "fill"}
       {"type": "bars", x, y, w, h, "orient": "horizontal" | "vertical", "items": [{"label", "value", "highlight"}]}
       {"type": "stack", x, y, w, h, "items": [{"label", "value", "highlight"}]}    one bar split into its parts
       {"type": "table", x, y, w, h, "header": [...], "rows": [[...]], "total": [...]}
       {"type": "quote", x, y, w, h, "text", "who"}
       {"type": "callout", x, y, w, h, "title", "text", "fill"}
     ]}

Styles map to the brand's faces (``title``, ``heading``, ``figure`` set in the heading face; ``body``, ``strong``,
``italic``, ``small``, ``label`` in the body faces). Colors are roles (``ink``, ``heading``, ``primary``, ``accent``,
``muted``, ``tint``, ``paper``, ``rule``); a text color that does not hold contrast on what it sits on is replaced
by the brand color that does. Every element is measured in the face it is set in: text steps down to the type floor,
never cut; what still does not fit, sits off the slide, overlaps another block or runs into the foot is a problem
the caller can hand back to the model for that one slide.
"""

from __future__ import annotations

import math

import re
from typing import Optional

try:
    from . import colors as C
    from . import scene as SC
except ImportError:  # loaded loose
    import colors as C  # type: ignore
    import scene as SC  # type: ignore

W, H = 960.0, 540.0
SAFE = (40.0, 24.0, 920.0, 484.0)  # x0, y0, x1, y1 a footed slide's content keeps inside
FOOT_TOP = 490.0

# style: (face, size, floor, lead, upper, track)
STYLES = {
    "title": ("heading", 34.0, 24.0, 1.1, False, 0.0),
    "heading": ("heading", 22.0, 16.0, 1.15, False, 0.0),
    "figure": ("heading", 48.0, 22.0, 1.0, False, 0.0),
    "body": ("body", 17.0, 11.0, 1.3, False, 0.0),
    "strong": ("body_bold", 17.0, 11.0, 1.3, False, 0.0),
    "italic": ("body_italic", 17.0, 11.0, 1.3, False, 0.0),
    "small": ("body", 13.0, 10.0, 1.3, False, 0.0),
    "label": ("label", 12.0, 10.0, 1.3, True, 0.08),
}
TEXT_TYPES = ("text", "list", "figure", "bars", "stack", "table", "quote", "callout")


def brand_accent(kit: Optional[dict], T) -> str:
    """The brand's accent as a fill: its accent color, else its second color (a marigold the import read as a rule
    color is still the brand's accent for a bar or a tile's top rule), else the measured accent."""
    cols = [c for c in (kit or {}).get("colors") or [] if isinstance(c, dict) and c.get("hex")]
    main = (T.main or "").lower()
    for want in ("accent", "highlight", "rule", "fill", None):
        for c in cols:
            h = c["hex"]
            if (want is None or c.get("role") == want) and h.lower() not in (main, T.paper.lower(), T.ink.lower()):
                try:
                    if C.contrast(h, T.paper) >= 1.4 and C.contrast(h, T.main) >= 1.4:
                        return h
                except Exception:
                    continue
    return T.accent


def roles(T, dark: bool = False, kit: Optional[dict] = None) -> dict:
    """Color roles from the system's measured tokens (``systems.Tokens``). ``accent`` is a fill color; text set in it
    is checked for contrast where it lands and replaced when it does not hold."""
    acc = brand_accent(kit, T)
    if dark:
        fa = acc if C.contrast(acc, T.field) >= 1.8 else T.field_accent  # a fill; text set in it is checked where it lands
        return {"paper": T.field, "ground": T.field, "ink": T.field_text, "heading": T.field_text, "primary": T.field_text,
                "accent": fa, "muted": T.field_muted, "rule": T.field_hair, "tint": C.mix(T.field_text, T.field, 0.86),
                "card": T.paper, "quiet": T.field_muted, "on_primary": T.field}
    return {"paper": T.paper, "ground": T.paper, "ink": T.ink, "heading": T.head, "primary": T.main, "accent": acc,
            "muted": T.muted, "rule": T.hair, "tint": C.mix(T.main, C.mix(T.paper, "#ffffff", 0.7), 0.95), "card": C.mix(T.paper, "#ffffff", 0.75),
            "quiet": T.quiet, "on_primary": T.field_text}


# A slide spec is written by a model: every number in it is untrusted input. Nothing non-finite or out of range
# reaches a measuring or fitting loop, and every fitting loop has a fixed bound.
SIZE_MIN, SIZE_MAX = 6.0, 120.0
COORD_MIN, COORD_MAX = -200.0, 1200.0
FIT_STEPS = 200
MAX_ELS, MAX_ITEMS, MAX_ROWS, MAX_COLS = 40, 12, 30, 8


def _num(v, d=0.0) -> float:
    """A finite float from model input, else ``d`` (strings, None, NaN and infinities all fall back)."""
    if isinstance(v, bool):
        return d
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return d
    return f if math.isfinite(f) else d


def _size(v, d=0.0) -> float:
    """A model-supplied type size: finite and clamped to SIZE_MIN..SIZE_MAX; zero, negative or junk gives ``d``."""
    f = _num(v, 0.0)
    if f <= 0:
        return d
    return min(max(f, SIZE_MIN), SIZE_MAX)


def _coord(v) -> float:
    return min(max(_num(v), COORD_MIN), COORD_MAX)


def _list(v) -> list:
    """``v`` when the model gave a list, else ``[]`` (a number, string, dict or None never reaches a slice or a loop)."""
    return v if isinstance(v, list) else []


def _text(v) -> str:
    """Text the model put in a text field: a string, or a plain finite number as written; anything else is ``""``."""
    if isinstance(v, bool) or v is None:
        return ""
    if isinstance(v, str):
        return v[:4000]
    if isinstance(v, (int, float)):
        try:
            return str(v) if math.isfinite(v) else ""
        except (ValueError, OverflowError):  # an int too long to print
            return ""
    return ""


def _word(v) -> Optional[str]:
    """A short keyword field (type, style, role, align): a string of at most 40 characters, else ``None``."""
    return v if isinstance(v, str) and len(v) <= 40 else None


SCALAR_TEXT = ("text", "title", "value", "label", "note", "who")
WORDS = ("type", "style", "align", "anchor", "orient", "color", "fill")
NUMBERS = ("x", "y", "w", "h", "size", "label_size", "note_size", "title_size")


def clean_el(el) -> Optional[dict]:
    """One model-written element with every field the type it should be, or ``None`` when it is not an element.

    Unknown keys pass through untouched (nothing reads them); each known key is kept only in its right type, so a
    number where a list belongs, or a dict where text belongs, is dropped rather than reaching the composer. Idempotent.
    """
    if not isinstance(el, dict):
        return None
    out = dict(el)
    for k in WORDS:
        if k in out:
            w = _word(out[k])
            if w is None:
                out.pop(k)
            else:
                out[k] = w.lower() if k == "type" else w
    for k in NUMBERS:
        if k in out and (isinstance(out[k], bool) or not isinstance(out[k], (int, float)) or not math.isfinite(out[k])):
            out.pop(k)
    for k in SCALAR_TEXT:
        if k in out:
            out[k] = _text(out[k])
    if "ref" in out and not (isinstance(out["ref"], str) and len(out["ref"]) <= 80):
        out.pop("ref")
    for k in ("bullets",):
        if k in out and not isinstance(out[k], bool):
            out.pop(k)
    if "items" in out:
        if out.get("type") in ("bars", "stack"):
            out["items"] = [{**it, "label": _text(it.get("label")), "value": _text(it.get("value")),
                             "highlight": it.get("highlight") is True}
                            for it in _list(out["items"])[:MAX_ITEMS] if isinstance(it, dict)]
        else:
            out["items"] = [t for t in (_text(it) for it in _list(out["items"])[:MAX_ITEMS]) if t.strip()]
    for k in ("header", "total"):
        if k in out:
            out[k] = [_text(c) for c in _list(out[k])[:MAX_COLS]]
    if "rows" in out:
        out["rows"] = [[_text(c) for c in r[:MAX_COLS]] for r in _list(out["rows"])[:MAX_ROWS] if isinstance(r, list)]
    return out


def box(el: dict) -> tuple:
    return (_coord(el.get("x")), _coord(el.get("y")), min(max(0.0, _num(el.get("w"))), COORD_MAX),
            min(max(0.0, _num(el.get("h"))), COORD_MAX))


def parse_value(v: str) -> Optional[float]:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v or ""))
    if not m:
        return None
    try:
        x = float(m.group(0).replace(",", ""))
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(x) or abs(x) > 1e15:
        return None
    t = str(v).lower()
    if re.search(r"\d\s*(?:m\b|million)", t):
        x *= 1e6
    elif re.search(r"\d\s*(?:k\b|thousand)", t):
        x *= 1e3
    return x


class Composer:
    """One spec slide set on a ``scene.Canvas`` in the system's grid, faces and colors."""

    def __init__(self, sysm, spec: dict):
        self.sys, self.T, self.spec = sysm, sysm.T, spec
        self.dark = (spec.get("ground") in ("primary", "dark", "field"))
        self.R = roles(self.T, self.dark, getattr(sysm, "kit", None))
        self.c = sysm.canvas(self.T.field if self.dark else self.T.paper)
        self.fills = []  # (x, y, w, h, color): what a text block may sit on
        self.blocks = []  # (j, x, y, w, h): each element's text area, for the overlap check
        self.problems = []

    # -------------------------------------------------------------- colors --

    def col(self, role: str, default: str = "ink") -> str:
        r = (role or default).strip().lower()
        if r.startswith("#"):
            r = default  # the model never picks a hex: a hex is read as the role it should have named
        return self.R.get(r) or self.R[default]

    def under(self, x, y, w, h) -> str:
        cx, cy = x + w / 2, y + min(h, 30) / 2
        for fx, fy, fw, fh, f in reversed(self.fills):
            if fx <= cx <= fx + fw and fy <= cy <= fy + fh:
                return f
        return self.c.scene["bg"]

    def legible(self, color: str, ground: str, size: float) -> str:
        need = 3.0 if size >= 24 else 4.5
        try:
            if C.contrast(color, ground) >= need:
                return color
            # the brand's own colors first, in the order a designer would reach for them; the most contrast last
            for cand in (self.R["heading"], self.R["primary"], self.R["ink"], self.R["paper"], self.T.field_text):
                if C.contrast(cand, ground) >= need:
                    return cand
            cands = [self.R["ink"], self.R["paper"], self.R["heading"], self.T.field_text, self.T.ink, self.T.paper, "#ffffff", "#111111"]
            return C.best_text_on(ground, cands)[0]
        except Exception:
            return color

    def fill(self, x, y, w, h, role, default="tint"):
        f = self.col(role, default)
        self.c.rect(x, y, w, h, f)
        self.fills.append((x, y, w, h, f))
        return f

    # -------------------------------------------------------------- text --

    def setp(self, text, x, y, w, h, style="body", size=None, color=None, align="left", anchor="top", role="", floor=None):
        """One block, stepped down from ``size`` to the style's floor; returns the element."""
        face, s0, fl, lead, upper, track = STYLES.get(style, STYLES["body"])
        size = _size(size, s0) or s0
        fl = min(size, _size(floor, 0) or fl)
        ground = self.under(x, y, w, h)
        default = "heading" if style in ("title", "heading") else "muted" if style in ("label", "small") else "ink"
        colr = self.legible(self.col(color, default), ground, size)
        long_before = self.c.scene["long"]
        el = self.c.text(text, x, y, w, h, face=face, size=size, min_size=fl, lead=lead, color=colr, align=align if align in ("left", "right", "center") else "left",
                         upper=upper, track=track, anchor=anchor, role=role)
        self.c.scene["long"] = long_before
        return el

    def stack(self, texts, x, y, w, h, style, size, color, gap=0.45, bullet=False):
        """Paragraphs one under another at one shared size, the largest that fits ``h``; ``True`` when they fit."""
        face, s0, fl, lead, upper, track = STYLES.get(style, STYLES["body"])
        s = _size(size, s0) or s0
        indent = s * 0.9 if bullet else 0.0
        for _ in range(FIT_STEPS):
            tot = sum(self.c.measure(t, face, s, w - indent, lead, track, upper) for t in texts) + gap * s * max(0, len(texts) - 1)
            if tot <= h + 0.5 or s <= fl:
                break
            s = max(fl, s - max(0.5, s * 0.05))
        yy = y
        ground = self.under(x, y, w, h)
        colr = self.legible(self.col(color, "ink"), ground, s)
        for t in texts:
            if bullet:
                d = max(4.0, s * 0.3)
                self.c.rect(x, yy + s * lead / 2 - d / 2, d, d, self.legible(self.R["accent"], ground, 30))
            el = self.c.text(t, x + indent, yy, w - indent, 10000, face=face, size=s, lead=lead, color=colr, upper=upper, track=track)
            yy = el["bottom"] + gap * s
        return yy - gap * s <= y + h + 0.5, yy - gap * s

    # -------------------------------------------------------------- elements --

    def draw(self, j: int, el: dict):
        t = (el.get("type") or "").lower()
        x, y, w, h = box(el)
        if t in ("rect", "line", "dot"):
            if t == "line":
                if w < 1 and h < 1:
                    return
                w, h = (w, max(h, 1.0)) if w >= h else (max(w, 1.0), h)
                self.c.rect(x, y, w, h, self.col(el.get("color") or el.get("fill"), "rule"))
            elif t == "dot":
                self.c.els.append({"t": "dot", "x": x, "y": y, "w": w, "h": h, "fill": self.col(el.get("fill") or el.get("color"), "accent")})
            else:
                self.fill(x, y, w, h, el.get("fill") or el.get("color"), "tint")
            return
        fits = True
        if t == "text":
            role = "title" if el.get("style") == "title" else ""
            e = self.setp(el.get("text", ""), x, y, w, h, el.get("style") or "body", el.get("size"), el.get("color"),
                          el.get("align") or "left", el.get("anchor") or "top", role=role)
            fits = e["h"] <= h + 0.5
        elif t == "list":
            fits, _b = self.stack([str(i) for i in el.get("items") or [] if str(i).strip()], x, y, w, h, el.get("style") or "body",
                                  el.get("size"), el.get("color"), bullet=el.get("bullets", True) is not False)
        elif t == "figure":
            fits = self.figure(el, x, y, w, h)
        elif t == "bars":
            fits = self.bars(el, x, y, w, h)
        elif t == "stack":
            fits = self.split_bar(el, x, y, w, h)
        elif t == "table":
            fits = self.table(el, x, y, w, h)
        elif t == "quote":
            fits = self.quote(el, x, y, w, h)
        elif t == "callout":
            fits = self.callout(el, x, y, w, h)
        else:
            return
        self.blocks.append((j, x, y, w, h))
        if not fits:
            n = getattr(self, "need", 0)
            more = f"; it needs about {int(n) + 4} tall at the smallest size" if n else "; give it more room or less to hold"
            self.need = 0
            self.problems.append({"el": j, "kind": "overflow",
                                  "detail": f"element {j} ({t}) does not fit its {int(w)} x {int(h)} box even at the smallest type size{more}"})

    def figure(self, el, x, y, w, h) -> bool:
        pad = 14.0 if el.get("fill") else 0.0
        if el.get("fill"):
            self.fill(x, y, w, h, el.get("fill"), "tint")
            self.c.rect(x, y, w, 4, self.R["accent"])  # a rule, not text: the brand's accent as it is
        ix, iw = x + pad, w - 2 * pad
        val = str(el.get("value") or "")
        rest = [str(t) for t in (el.get("label"), el.get("note")) if t]
        vs = _size(el.get("size"), 0) or min(56.0, max(26.0, h * 0.42))
        for _ in range(FIT_STEPS):
            if not (vs > 20 and self.c.ty.width(val, "heading", vs) > iw):
                break
            vs -= 1
        ls, ns = _size(el.get("label_size"), 0) or 15.0, _size(el.get("note_size"), 0) or 12.5

        def need(vs, ls, ns):
            t = pad + 4 + vs * 1.05 + 6
            if rest:
                t += self.c.measure(rest[0], "body_bold", ls, iw, 1.3) + 4
            if len(rest) > 1:
                t += self.c.measure(rest[1], "body", ns, iw, 1.3)
            return t + pad
        # the number, its words and its note step down together until the tile holds them (never below the floors)
        for _ in range(FIT_STEPS):
            if not (need(vs, ls, ns) > h + 0.5 and (vs > 26 or ls > 11 or ns > 10)):
                break
            vs, ls, ns = max(26.0, vs - 2), max(11.0, ls - 0.5), max(10.0, ns - 0.5)
        e = self.setp(val, ix, y + pad + 4, iw, vs * 1.05, "figure", vs, el.get("color") or "accent", floor=vs)
        yy = e["bottom"] + 6
        if rest:
            lab = self.setp(rest[0], ix, yy, iw, 10000, "strong", ls, "ink", floor=ls)
            yy = lab["bottom"] + 4
            if len(rest) > 1:
                self.setp(rest[1], ix, yy, iw, 10000, "small", ns, "muted", floor=ns)
        n = need(vs, ls, ns)
        if n > h + 0.5:
            self.need = n
            return False
        return True

    def bars(self, el, x, y, w, h) -> bool:
        items = [it for it in (el.get("items") or [])[:MAX_ITEMS] if isinstance(it, dict)]
        if not items:
            return True
        vals = [parse_value(it.get("value")) or 0.0 for it in items]
        top = max(vals) or 1.0
        hi_any = any(it.get("highlight") for it in items)
        ground = self.under(x, y, w, h)
        # the finding in the accent, the rest a soft primary that still reads on the ground; no finding: all primary
        hi_c = self.R["accent"]
        lo_c = C.mix(self.R["primary"], ground, 0.55) if hi_any else self.R["primary"]
        if C.contrast(lo_c, ground) < 1.4:
            lo_c = self.R["quiet"]
        ok = True
        if (el.get("orient") or "horizontal").startswith("v"):
            n = len(items)
            gap = min(28.0, w / n * 0.3)
            bw = (w - gap * (n - 1)) / n
            lab_h, val_h = 40.0, 26.0
            area = h - lab_h - val_h
            for i, (it, v) in enumerate(zip(items, vals)):
                bx = x + i * (bw + gap)
                bh = max(2.0, area * v / top)
                by = y + val_h + area - bh
                self.c.rect(bx, by, bw, bh, hi_c if it.get("highlight") else lo_c)
                ve = self.setp(str(it.get("value", "")), bx - 6, by - val_h, bw + 12, val_h, "strong", 17, "ink", "center", "bottom", floor=11)
                le = self.setp(str(it.get("label", "")), bx - 4, y + h - lab_h + 6, bw + 8, lab_h - 6, "small", 13, "muted", "center", floor=10)
                ok = ok and le["h"] <= lab_h - 5.5 and ve["h"] <= val_h + 0.5
            return ok
        n = len(items)
        lw = min(w * 0.34, max(self.c.ty.width(str(it.get("label", "")), "body", 15) for it in items) + 10)
        vw = max(self.c.ty.width(str(it.get("value", "")), "body_bold", 17) for it in items) + 14
        row = h / n
        bh = min(34.0, row * 0.62)
        for i, (it, v) in enumerate(zip(items, vals)):
            ry = y + i * row
            le = self.setp(str(it.get("label", "")), x, ry, lw - 8, row - 2, "body", 15, "ink", "left", "middle", floor=10)
            ok = ok and le["h"] <= row
            bmax = w - lw - vw
            bl = max(2.0, bmax * v / top)
            self.c.rect(x + lw, ry + (row - bh) / 2, bl, bh, hi_c if it.get("highlight") else lo_c)
            self.setp(str(it.get("value", "")), x + lw + bl + 8, ry, vw, row, "strong", 17, "ink", "left", "middle", floor=11)
        return ok

    def split_bar(self, el, x, y, w, h) -> bool:
        items = [it for it in (el.get("items") or [])[:MAX_ITEMS] if isinstance(it, dict)]
        vals = [parse_value(it.get("value")) or 0.0 for it in items]
        tot = sum(vals) or 1.0
        widths = [w * v / tot for v in vals]
        below = [self.c.ty.width(f"{it.get('label', '')} {it.get('value', '')}".strip(), "body_bold", 14) > sw - 16
                 for it, sw in zip(items, widths)]
        stagger = any(a and b for a, b in zip(below, below[1:]))
        room = (6 + 34 + (36 if stagger else 0)) if any(below) else 0
        bh = max(24.0, min(64.0, h - room)) if room else min(h, 64.0)
        xx, ok = x, True
        last_end, last_row = -1e9, 1
        palette = [self.R["primary"], self.R["accent"], self.R["tint"], self.R["quiet"]]
        if self.dark:  # on the dark field the parts are the accent and soft steps of the light text, never a white slab
            palette = [self.R["accent"], C.mix(self.R["ink"], self.c.scene["bg"], 0.55), C.mix(self.R["ink"], self.c.scene["bg"], 0.75)]
        for i, (it, v) in enumerate(zip(items, vals)):
            sw = w * v / tot
            f = self.R["accent"] if it.get("highlight") else palette[i % len(palette)] if not any(t.get("highlight") for t in items) \
                else (palette[1 + i % (len(palette) - 1)] if self.dark else self.R["primary"] if i % 2 == 0 else self.R["tint"])
            self.c.rect(xx, y, sw, bh, f)
            self.fills.append((xx, y, sw, bh, f))
            inside = f"{it.get('label', '')} {it.get('value', '')}".strip()
            if self.c.ty.width(inside, "body_bold", 14) <= sw - 16:
                self.setp(inside, xx + 8, y, sw - 16, bh, "strong", 14, "ink" if self.dark else "on_primary", "center", "middle", floor=14)
            else:
                lw = max(sw, 110.0)
                lx = min(xx, x + w - lw)
                row = 0 if lx >= last_end + 6 else 1 - last_row
                ly = y + bh + 6 + row * 36
                self.c.rect(xx, y + bh, 1, 6 + row * 36, self.R["rule"])
                lab = self.setp(f"{it.get('value', '')}  {it.get('label', '')}".strip(), lx + 4, ly, lw - 4, 34, "small", 12.5, "ink", floor=10)
                ok = ok and lab["h"] <= 34.5 and ly + 34 <= y + h + 12
                last_end, last_row = (lx + 4 + max(self.c.ty.width(ln, "body", lab["size"]) for ln in lab["lines"])), row
            xx += sw
        if not ok:
            self.need = 30 + room
        return ok

    def table(self, el, x, y, w, h) -> bool:
        header = [str(c) for c in (el.get("header") or [])[:MAX_COLS]]
        rows = [[str(c) for c in r[:MAX_COLS]] for r in (el.get("rows") or [])[:MAX_ROWS] if isinstance(r, list)]
        total = [str(c) for c in (el.get("total") or [])[:MAX_COLS]]
        ncol = max([len(header), len(total)] + [len(r) for r in rows] or [1])
        if not ncol:
            return True
        numeric = [all(re.fullmatch(r"[\s$£€+\-–~≈]*\d[\d,.]*\s*(?:%|[kKmM]|million)?\s*", r[c]) or not r[c].strip()
                       for r in rows if c < len(r)) and any(c < len(r) and r[c].strip() for r in rows) for c in range(ncol)]
        wts = []
        for c in range(ncol):
            longest = max([len(r[c]) for r in rows + [header, total] if c < len(r)] or [4])
            wts.append(max(6, min(longest, 46)))
        cw = [w * k / sum(wts) for k in wts]
        need = [max([self.c.ty.width(r[c], "body_bold", 17) for r in rows + [header, total] if c < len(r)] or [0]) + 22
                if numeric[c] else 0 for c in range(ncol)]
        short = sum(max(0.0, need[c] - cw[c]) for c in range(ncol))
        if short:
            spare = [c for c in range(ncol) if not numeric[c]] or [0]
            for c in range(ncol):
                cw[c] = max(cw[c], need[c])
            for c in spare:
                cw[c] -= short / len(spare)
        all_rows = ([("h", header)] if header else []) + [("r", r) for r in rows] + ([("t", total)] if total else [])
        n = len(all_rows)
        size = _size(el.get("size"), 0) or min(16.0, max(11.0, h / max(n, 1) / 2.0))
        ok = True
        for _ in range(12):
            heights = []
            for kind, r in all_rows:
                face = "body_bold" if kind in ("h", "t") else "body"
                hh = max([self.c.measure(r[c], face, size, cw[c] - 16, 1.25) for c in range(min(len(r), ncol))] or [size * 1.25])
                heights.append(hh + 12)
            if sum(heights) <= h + 0.5 or size <= 10:
                break
            size -= 0.5
        ok = sum(heights) <= h + 0.5
        yy = y
        for i, ((kind, r), rh) in enumerate(zip(all_rows, heights)):
            if kind == "h":
                self.fill(x, yy, w, rh, "primary")
            elif kind == "t":
                self.c.rect(x, yy, w, 2, self.R["heading"])
            elif i % 2 == 0:
                self.fill(x, yy, w, rh, "tint")
            xx = x
            for c in range(ncol):
                txt = r[c] if c < len(r) else ""
                style = "strong" if kind in ("h", "t") else "body"
                colr = "on_primary" if kind == "h" else "heading" if kind == "t" else "ink"
                al = "right" if numeric[c] and c > 0 else "left"
                if txt:
                    self.setp(txt, xx + 8, yy + 6, cw[c] - 16, rh - 12, style, size, colr, al, floor=size)
                xx += cw[c]
            yy += rh
            if kind == "r":
                self.c.rect(x, yy - 0.5, w, 0.5, self.R["rule"])
        return ok

    def quote(self, el, x, y, w, h) -> bool:
        ground = self.under(x, y, w, h)
        self.c.text("“", x - 4, y - 8, 60, 70, face="heading", size=72, lead=1.0, color=self.legible(self.R["accent"], ground, 72))
        who = str(el.get("who") or "")
        who_h = 44.0 if who else 0.0
        e = self.setp(str(el.get("text", "")), x + 48, y + 6, w - 48, h - who_h - 6, "italic", _size(el.get("size"), 26), el.get("color") or "heading", floor=14)
        ok = e["h"] <= h - who_h - 5.5
        if who:
            wh = self.setp(who, x + 48, e["bottom"] + 14, w - 48, 30, "small", 14, "muted", floor=10)
            ok = ok and wh["bottom"] <= y + h + 0.5
        return ok

    def callout(self, el, x, y, w, h) -> bool:
        f = self.fill(x, y, w, h, el.get("fill") or "tint", "tint")
        self.c.rect(x, y, 4, h, self.R["accent"])
        pad = 16.0
        yy, ok = y + pad, True
        if el.get("title"):
            e = self.setp(str(el["title"]), x + pad + 4, yy, w - 2 * pad - 4, h - 2 * pad, "heading", _size(el.get("title_size"), 18), "heading", floor=13)
            yy = e["bottom"] + 8
        texts = el.get("items") or ([el["text"]] if el.get("text") else [])
        if texts:
            ok, _b = self.stack([str(t) for t in texts], x + pad + 4, yy, w - 2 * pad - 4, y + h - pad - yy, "body", _size(el.get("size"), 15),
                                "ink", bullet=bool(el.get("items")))
        return ok

    # -------------------------------------------------------------- the slide --

    def compose(self) -> dict:
        s = self.spec
        footed = s.get("footer", True) is not False
        for j, raw in enumerate(_list(s.get("els"))[:MAX_ELS]):  # j stays the stored index, the one ``fields`` traces
            el = clean_el(raw)
            if el is None:
                continue
            x, y, w, h = box(el)
            nx, ny = min(max(x, 0.0), W - 4), min(max(y, 0.0), H - 4)
            nw, nh = min(w, W - nx), min(h, H - ny)
            if (nx, ny, nw, nh) != (x, y, w, h) and (el.get("type") or "") in TEXT_TYPES:
                self.problems.append({"el": j, "kind": "off", "detail": f"element {j} runs off the slide (x {x:.0f}, y {y:.0f}, w {w:.0f}, h {h:.0f})"})
            el = {**el, "x": nx, "y": ny, "w": nw, "h": nh}
            if footed and (el.get("type") or "") in TEXT_TYPES and ny + nh > FOOT_TOP + 2:
                self.problems.append({"el": j, "kind": "foot", "detail": f"element {j} runs into the footer band (it ends at y {ny + nh:.0f}; keep content above y {SAFE[3]:.0f})"})
                el["h"] = max(10.0, FOOT_TOP - ny)
            n_els, n_fills, n_blocks = len(self.c.scene["els"]), len(self.fills), len(self.blocks)
            try:
                self.draw(j, el)
            except Exception as ex:  # one bad element is left out and recorded; it never takes the deck down
                del self.c.scene["els"][n_els:], self.fills[n_fills:], self.blocks[n_blocks:]
                self.problems.append({"el": j, "kind": "bad",
                                      "detail": f"element {j} ({el.get('type') or 'no type'}) could not be drawn ({type(ex).__name__}) and was left out"})
        for a in range(len(self.blocks)):
            for b in range(a + 1, len(self.blocks)):
                ja, ax, ay, aw, ah = self.blocks[a]
                jb, bx, by, bw, bh = self.blocks[b]
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)
                if ox > 4 and oy > 4:
                    self.problems.append({"el": jb, "kind": "overlap", "detail": f"elements {ja} and {jb} overlap"})
        if footed:
            try:
                self.sys.foot(self.c, s, color=self.R["muted"], hair=self.R["rule"])
            except TypeError:
                self.sys.foot(self.c, s)
        if s.get("cover"):
            self.c.logo(W - 40, 22, 30, "band" if self.dark else "paper", align="right")
        sc = self.c.done(dark=self.dark, band=self.dark)
        sc["long"] = any(p["kind"] in ("overflow", "foot") for p in self.problems)
        sc["problems"] = self.problems
        return sc


def compose(sysm, spec: dict) -> dict:
    return Composer(sysm, spec).compose()


# ------------------------------------------------------------------ the doc --

def el_fields(el: dict) -> list:
    """``[(suffix, text)]``: every piece of text an element shows, for the checks (suffix "" is the element's own)."""
    el = clean_el(el)
    if el is None:
        return []
    t = (el.get("type") or "").lower()
    if t in ("text", "callout"):
        out = [("", str(el.get("text") or ""))] if el.get("text") else []
        if t == "callout" and el.get("title"):
            out.append((".title", str(el["title"])))
        out += [(f".items.{k}", str(it)) for k, it in enumerate(el.get("items") or [])]
        return out
    if t == "list":
        return [(f".items.{k}", str(it)) for k, it in enumerate(el.get("items") or [])]
    if t == "figure":
        return [("", " ".join(str(v) for v in (el.get("value"), el.get("label"), el.get("note")) if v))]
    if t in ("bars", "stack"):
        return [(f".items.{k}", f"{it.get('label', '')} {it.get('value', '')}".strip()) for k, it in enumerate(el.get("items") or [])
                if isinstance(it, dict)]
    if t == "table":
        out = []
        if el.get("header"):
            out.append((".header", " ".join(str(c) for c in el["header"])))
        out += [(f".rows.{k}", " ".join(str(c) for c in r)) for k, r in enumerate(el.get("rows") or []) if isinstance(r, list)]
        if el.get("total"):
            out.append((".total", " ".join(str(c) for c in el["total"])))
        return out
    if t == "quote":
        return [(".quote", str(el.get("text") or ""))]
    return []


def fields(sl: dict, prefix: str) -> list:
    """``[(path, text, refs)]`` for one spec slide."""
    refs = [r for r in _list(sl.get("refs")) if isinstance(r, str)]
    out = []
    for j, el in enumerate(_list(sl.get("els"))):
        el = clean_el(el)
        if el is None:
            continue
        for suf, text in el_fields(el):
            if text:
                out.append((f"{prefix}.els.{j}{suf}", text, [el["ref"]] if el.get("ref") else refs))
    return out


def set_field(doc: dict, path: str, fn) -> bool:
    """Apply ``fn`` to the text at a spec path (``slides.2.els.3.items.1``, ``cover.els.0``); ``False`` if it is not there."""
    try:
        return _set_field(doc, path, fn)
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        return False


def _set_field(doc: dict, path: str, fn) -> bool:
    parts = path.split(".")
    try:
        if parts[0] == "cover":
            sl, rest = doc["cover"], parts[1:]
        else:
            sl, rest = doc["slides"][int(parts[1])], parts[2:]
        if rest[0] != "els":
            return False
        el = sl["els"][int(rest[1])]
        rest = rest[2:]
    except (KeyError, IndexError, ValueError, TypeError):
        return False
    t = (el.get("type") or "").lower()
    if not rest:
        if t == "figure":
            for k in ("value", "label", "note"):
                if el.get(k):
                    new = fn(str(el[k]))
                    if new != str(el[k]):
                        el[k] = new
                        return True
            return False
        el["text"] = fn(str(el.get("text") or ""))
        return True
    if rest[0] == "quote":
        el["text"] = fn(str(el.get("text") or ""))
        return True
    if rest[0] == "title":
        el["title"] = fn(str(el.get("title") or ""))
        return True
    if rest[0] == "items" and len(rest) > 1:
        it = el["items"][int(rest[1])]
        if isinstance(it, dict):
            for k in ("value", "label"):
                new = fn(str(it.get(k) or ""))
                if new != str(it.get(k) or ""):
                    it[k] = new
                    return True
            return False
        el["items"][int(rest[1])] = fn(str(it))
        return True
    cells = el.get("header") if rest[0] == "header" else el.get("total") if rest[0] == "total" else el["rows"][int(rest[1])] if rest[0] == "rows" else None
    if cells is None:
        return False
    for i, c in enumerate(cells):
        new = fn(str(c))
        if new != str(c):
            cells[i] = new
            return True
    return False


def all_text(sl: dict) -> str:
    return " ".join(t for _p, t, _r in fields(sl, "x"))


# ------------------------------------------------------------------ the model --

SPEC_SYSTEM = ("You are a presentation designer who lays out funder decks slide by slide, the way a strong designer "
               "writing python-pptx code would: each slide's layout chosen for what it says.")

ELEMENTS_HELP = """Each slide is positioned elements on a 960 x 540 canvas (points, origin top left). Element types:
- text: {"type":"text","x","y","w","h","text","style","color","align"}  style: title | heading | figure | body | strong | italic | small | label
- list: {"type":"list","x","y","w","h","items":["..."],"style":"body"}  bulleted points
- rect: {"type":"rect","x","y","w","h","fill"}  a panel or band (draw it BEFORE the text that sits on it)
- line: {"type":"line","x","y","w","h","color"}  a rule (h 2 for horizontal, w 2 for vertical)
- dot: {"type":"dot","x","y","w","h","fill"}  a circle (timeline markers)
- figure: {"type":"figure","x","y","w","h","value":"$31,900","label":"vehicle costs in FY2026","note":"up from $19,700","fill":"tint"}  a big-number tile (omit fill for no panel)
- bars: {"type":"bars","x","y","w","h","orient":"horizontal"|"vertical","items":[{"label","value","highlight":true}]}  a bar or column chart; value is the number as shown ("$85,000", "41%")
- stack: {"type":"stack","x","y","w","h","items":[{"label","value","highlight"}]}  one bar split into its parts (funding sources)
- table: {"type":"table","x","y","w","h","header":["Line","Amount"],"rows":[["Van","$74,000"]],"total":["Total","$148,000"]}
- quote: {"type":"quote","x","y","w","h","text","who"}
- callout: {"type":"callout","x","y","w","h","title","text" or "items":[...],"fill":"tint"}  a boxed note ("what this does not show")
Colors and fills are brand ROLES only: ink, heading, primary, accent, muted, tint (a light panel), card (a near-white panel), paper, rule. Never a hex value, never a font name.
Slide fields: {"ground":"paper"|"primary","footer":true|false,"title":"the slide's title as shown","els":[...]}
ground "primary" sets the slide on the brand's dark field (use it for the cover and the closing ask, or not at all); text on it reads light automatically.
Default type sizes: title 34, heading 22, figure 48, body 17, strong 17, small 13, label 12. Imprint measures every block in the brand's real fonts and shrinks type only down to a floor, so give each block room: a body line of 90 characters at 17pt needs about 600 wide by 23 high per line.
Footer: on footer slides Imprint draws the source line and page number below y 490; keep every element above y 484 and inside x 40 to 920. Cover: footer false (Imprint adds the logo at the top right; leave x 780 to 920, y 10 to 60 empty)."""

SPEC_SCHEMA = {
    "type": "object", "required": ["slides"],
    "properties": {"slides": {"type": "array", "items": {
        "type": "object", "required": ["els"],
        "properties": {"ground": {"type": "string"}, "footer": {"type": "boolean"}, "title": {"type": "string"},
                       "els": {"type": "array", "items": {"type": "object", "required": ["type"],
                                                          "properties": {"type": {"type": "string"}}}}}}}}}

RULES = """Rules:
- One spec slide per draft slide, in the same order; the first is the cover. Keep the draft's words: you may move a line into a figure tile, a chart, a table row, a callout or the title, and you may split a figure's number from its words, but do not add claims, change any number or drop a point.
- Every number you show must be one the draft or the documents state. Never invent a number, a percent or a total.
- Titles state the slide's point (a finding), not a topic label, and each title is a text element with style "title".
- Choose each slide's layout for what it says: figure tiles for three or four headline numbers, a table with a total for a budget, a stack for who funds what, bars for a comparison or growth, a quote slide for a voice, a callout for limits or caveats, a timeline (dots, a line and text) for a plan. Vary the layouts across the deck; never a slide that is only a bulleted list when its content has numbers.
- Size every box to what it holds: a panel, tile or callout no taller than its text needs plus its padding; no large empty panels. Use the slide's height: spread the content, do not leave the bottom third empty.
- Leave white space: 40 points of margin, at least 16 between blocks, no two text blocks overlapping (a text on a rect is fine)."""


def spec_prompt(sources: list, draft: str, brand: str) -> str:
    src = "\n\n".join(f"=== {n} ===\n{t}" for n, t in sources)
    return (f"Here are our documents.\n\n{src}\n\nHere is the deck's draft, slide by slide:\n\n{draft}\n\n"
            f"The brand: {brand}\n\nDesign every slide of this deck.\n\n{ELEMENTS_HELP}\n\n{RULES}\n\n"
            "Reply with one JSON object: {\"slides\": [ ...one spec per draft slide... ]}.")


def fix_prompt(slide: dict, problems: list) -> str:
    import json
    lines = "\n".join(f"- {p['detail']}" for p in problems)
    return (f"This slide was measured in the brand's real fonts and has problems:\n{lines}\n\n{ELEMENTS_HELP}\n\n"
            "Fix the layout: move, resize or re-arrange elements, or use a smaller style. Keep every word and number exactly as "
            "it is; never shorten or drop text. Reply with the corrected slide as one JSON object with the same fields.\n\n"
            f"The slide:\n{json.dumps(slide, ensure_ascii=False)}")


FIX_SCHEMA = SPEC_SCHEMA["properties"]["slides"]["items"]


def brand_line(kit: dict) -> str:
    """The brand in words for the model: its name and the roles it may use (no hex, no font names needed)."""
    name = kit.get("name") or "the organization's brand"
    dark = "a dark primary color" if kit.get("colors") else "a primary color"
    return f"{name}: a heading face and a body face, {dark}, an accent color for the one thing to notice, a light tint for panels."


def words_kept(draft_slides: list, spec_slides: list) -> list:
    """Draft lines whose numbers no spec slide shows (a dropped claim), for the record."""
    try:
        from . import content as K
    except ImportError:
        import content as K  # type: ignore
    shown = set()
    for sl in spec_slides:
        shown |= set(K.numbers(all_text(sl)))
    out = []
    for s in draft_slides:
        for t in [s["title"]] + s["lines"]:
            if any(n not in shown for n in K.numbers(t)):
                out.append(t)
    return out
