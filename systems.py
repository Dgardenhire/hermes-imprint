"""Design systems for decks, graphics and one-page briefs: how a kit composes each kind of slide, its graphic and
its page.

Five systems, each worked out from how a kind of studio builds its pages, never copying anyone's look:

- **exhibit**: the consulting exhibit. A tracker and a hairline across the top, the title is the conclusion in one
  sentence set large, a subhead says what the chart measures, one chart labeled directly with the finding in the
  accent and the rest in a tint of the brand color, a hairline baseline, and a source line at the foot.
- **broadsheet**: the data desk. A short colored tab and a heavy rule over the headline, a standfirst in the text
  italic, charts on hairline gridlines with their scale printed, the finding in the accent, the source set small.
- **stage**: the keynote. A dark ground, one idea a slide in very large type, numbers given the whole slide,
  columns drawn tall with their values set as display figures.
- **folio**: the book. Generous margins, a running head between hairlines, centered display serif, figures set
  in the text face, quotes set as epigraphs, the folio centered at the foot.
- **grid**: the modernist poster. A twelve-column grid, a heavy rule at the head, condensed figures as structure,
  and one color that owns whole fields of the page.

Every system works with any kit: the colors come from the kit's measured palette (paper, ink, head, accent, band,
fill, rule), the faces from its type, so an imported brand gets real compositions too.

Slides are 960 x 540 points (13.33 x 7.5 in, PowerPoint's 16:9) on a twelve-column grid (56 pt margins, 24 pt
gutters). Graphics are 1080 x 1350 (4:5). Pages are 612 x 792 (US Letter). The type scale is set per system with
real contrast: action titles 44 pt and up on slides, chart labels 18 to 22 pt, source lines and trackers 12 to 14
pt. A slide whose text still doesn't fit at its smallest size is marked long, and the deck's checks say which.
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
GW, GH = 1080.0, 1350.0
PW, PH = 612.0, 792.0
NUMBERS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}


def nice_step(top: float) -> float:
    """A round gridline step that gives three to five lines up to ``top``."""
    if top <= 0:
        return 1.0
    raw = top / 4
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def fmt_tick(v: float, like: str) -> str:
    """A gridline value written the way the data is: "$100,000" beside "$205,000", "40%" beside "38%"."""
    cur = next((ch for ch in like if ch in "$£€"), "")
    pct = "%" if "%" in like else ""
    if v >= 1e9 and "billion" in like.lower():
        return f"{cur}{v / 1e9:g} billion"
    if v >= 1e6 and "million" in like.lower():
        return f"{cur}{v / 1e6:g} million"
    return f"{cur}{v:,.0f}{pct}" if v == int(v) else f"{cur}{v:,.1f}{pct}"


def parse_value(v: str) -> Optional[float]:
    """The number a value string shows, for the length of its bar: "1,148" 1148, "38%" 38, "$2.4 million" 2.4e6."""
    s = (v or "").lower().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    x = float(m.group(0))
    for word, k in (("billion", 1e9), ("million", 1e6), ("thousand", 1e3)):
        if word in s:
            x *= k
    if re.search(r"\d\s*k\b", s):
        x *= 1e3
    return x


def _lighten_to(base: str, ground: str, target: float, start: float = 0.78, low: float = 0.2) -> str:
    """``base`` mixed toward ``ground`` as far as it can go while it still stands ``target`` against the ground."""
    t = start
    col = C.mix(base, ground, t)
    while C.contrast(col, ground) < target and t > low:
        t -= 0.04
        col = C.mix(base, ground, t)
    return col


class Tokens:
    """The palette as the systems use it: every color already measured against the ground it sits on."""

    def __init__(self, pal: dict, kit: dict):
        self.paper, self.ink, self.head = pal["paper"], pal["ink"], pal["head"]
        self.accent, self.accent_text, self.rule = pal["accent"], pal["accent_text"], pal["rule"]
        self.band = pal.get("band")
        self.band_text = pal.get("band_text")
        self.fill = pal.get("fill")
        self.accent2 = pal.get("accent2")
        self.dark = bool(pal.get("dark"))
        # A quiet tone for the bars that are not the point, held to 2:1 on the paper so a bar never vanishes.
        self.quiet = _lighten_to(self.ink, self.paper, 2.0, start=0.58)
        self.hair = self.rule if C.contrast(self.rule, self.paper) >= 1.25 else C.mix(self.ink, self.paper, 0.8)
        # Secondary text: a step back from the ink, still a comfortable 4.5:1 for reading.
        self.muted = _lighten_to(self.ink, self.paper, 5.6, start=0.3, low=0.0)
        # The tint the bars that are not the finding take: the brand's main color, light but never lost (1.5:1).
        main = self.band or (self.head if C.contrast(self.head, self.paper) >= 3 else self.ink)
        self.main = main
        need = 4.2 if self.dark else 1.55
        self.tint = _lighten_to(main, self.paper, need, start=0.74)
        if main.lower() == self.accent.lower() or C.contrast(self.tint, self.accent) < 1.6:
            # the brand's main color is its accent too: the rest go to a gray so the finding still owns the color
            self.tint = _lighten_to(self.ink, self.paper, need, start=0.76)
        # the growth a subhead names (FY2026 past FY2025), a step darker than the tint
        self.grow = _lighten_to(main if main.lower() != self.accent.lower() else self.ink, self.paper, 2.4 if not self.dark else 5.0,
                                start=0.55)
        # the field a strong slide sits on: the band when the kit has one, else the heading color when it holds
        # paper-colored text, else the ink
        field = self.band or (self.head if C.contrast(self.paper, self.head) >= 4.5 else self.ink)
        self.field = field
        self.field_text = self.band_text if (self.band and self.band_text) else C.best_text_on(field, [self.paper, self.ink, "#ffffff", "#111111"])[0]
        self.field_accent = self.accent if C.contrast(self.accent, field) >= 3.0 else self.field_text
        self.field_muted = C.mix(self.field_text, field, 0.22)
        self.field_hair = C.mix(self.field_text, field, 0.72)
        self.on_accent = C.best_text_on(self.accent, [self.paper, self.ink, "#ffffff", "#111111"])[0]


class System:
    """The exhibit method, and the shared craft every system draws with (grid, furniture, charts)."""
    name = "exhibit"
    M = 56.0          # side margin
    GUT = 24.0        # gutter
    TOP = 30.0        # tracker baseline row
    T_SIZE, T_MIN, T_LEAD = 46.0, 36.0, 1.06   # action title
    SUB = 22.0        # subhead
    SRC = 13.0        # source line, page number, tracker
    LABEL = 20.0      # chart category labels
    VALUE = 22.0      # chart values
    chart = "hbars"   # how an exhibit draws its bars: hbars or columns
    SUB_FACE = "body"
    grid_lines = False

    def __init__(self, ty: SC.Type, T: Tokens, kit: dict):
        self.ty, self.T, self.kit = ty, T, kit
        t = kit.get("type") or {}
        self.upper_head = (t.get("heading") or {}).get("case") == "upper"
        self.show_numbers = (kit.get("rules") or {}).get("page_numbers", True)
        self.cw = (W - 2 * self.M - 11 * self.GUT) / 12

    # ------------------------------------------------------------ grid --

    def col(self, i: float) -> float:
        return self.M + i * (self.cw + self.GUT)

    def span(self, a: int, b: int) -> float:
        """Width from the start of column ``a`` to the end of column ``b - 1``."""
        return (b - a) * self.cw + (b - a - 1) * self.GUT

    # ------------------------------------------------------------ helpers --

    def canvas(self, ground: Optional[str] = None) -> SC.Canvas:
        return SC.Canvas(self.ty, W, H, ground or self.T.paper)

    def src(self, c, spec, prefix, width, size, face="body") -> str:
        """The slide's source line, or its titles only when the passages' places don't fit on one line."""
        for key in ("src", "src_short"):
            t = spec.get(key)
            if t and c.ty.width(prefix + t, face, size) <= width:
                return prefix + t
        t = spec.get("src_short") or spec.get("src") or ""
        while t and c.ty.width(prefix + t + "…", face, size) > width:
            t = t[:-1]
        return (prefix + t.rstrip(" ,;") + "…") if t else ""

    def head(self, c, text, x, y, w, h, size=None, min_size=None, color=None, align="left", anchor="top", lead=None, face="heading"):
        size = size or self.T_SIZE
        eb = getattr(self, "_eyebrow", "")
        if eb and face == "heading":
            # loop 3: the draft's topic title, small, above the headline that states the slide's point
            self._eyebrow = ""
            T = self.T
            ec = T.field_accent if color is not None and color == getattr(T, "field_text", None) else T.accent_text
            c.text(eb, x, y, w, 20, face="label", size=14, lead=1.3, color=ec, align=align, upper=True, track=0.12, max_lines=1,
                   role="eyebrow")
            y, h = y + 28, max(h - 28, size * 1.1)
        return c.text(text, x, y, w, h, face=face, size=size, min_size=min_size or min(size, self.T_MIN), lead=lead or self.T_LEAD,
                      color=color or self.T.head, align=align, anchor=anchor, upper=self.upper_head and face == "heading",
                      track=0.02 if self.upper_head and face == "heading" else 0, role="title")

    def label(self, c, text, x, y, w, color=None, size=None, align="left", track=0.1, upper=True, face="label"):
        if text:
            return c.text(text, x, y, w, (size or self.SRC) * 1.4, face=face, size=size or self.SRC, lead=1.3,
                          color=color or self.T.ink, align=align, upper=upper, track=track if upper else 0, max_lines=1)
        return None

    # ------------------------------------------------------------ furniture --

    def top(self, c, s, color=None, hair=None):
        """Tracker on the left, the deck's short title on the right, a hairline across: quiet, the same on every slide."""
        T = self.T
        if s.get("deck"):
            self.label(c, s["deck"], self.col(8), self.TOP - 4, self.span(8, 12), color=color or T.muted, align="right", upper=False,
                       face="body")
        c.rect(self.M, self.TOP + 18, W - 2 * self.M, 1, hair or T.hair)
        return self.TOP + 18

    def foot(self, c, spec, color=None, rule=True, hair=None):
        T = self.T
        col = color or T.muted
        y = H - 34
        if rule:
            c.rect(self.M, y - 10, W - 2 * self.M, 1, hair or T.hair)
        src = self.src(c, spec, "Source: ", W - 2 * self.M - 90, self.SRC)
        if src:
            c.text(src, self.M, y, W - 2 * self.M - 90, self.SRC * 1.4, face="body", size=self.SRC, lead=1.3, color=col, max_lines=1)
        if self.show_numbers and spec.get("num", 1) > 1:
            c.text(str(spec["num"]), W - self.M - 60, y, 60, self.SRC * 1.4, face="label", size=self.SRC, lead=1.3, color=col, align="right")

    def title_area(self, c, s, y, w=None, x=None, size=None, color=None, sub_color=None):
        """The action title and the subhead under it. Returns where the block ends."""
        x = self.M if x is None else x
        w = w or self.span(0, 11)
        el = self.head(c, s.get("head", ""), x, y, w, (size or self.T_SIZE) * self.T_LEAD * 2 + 2, size=size, color=color)
        y = el["bottom"]
        sub = s.get("subhead") or ""
        if sub:
            y = c.text(sub, x, y + 10, w, self.SUB * 1.3 * 2, face="body", size=self.SUB, min_size=18, lead=1.3,
                       color=sub_color or self.T.muted, marks=s.get("sub_marks", ""))["bottom"]
        return y

    def exhibit_head(self, c, s, y, x=None, w=None, size=46.0, min_size=40.0, color=None, sub_color=None, sub_face=None):
        """The exhibit's headline: never under ``min_size`` (the canvas shows the slide at about 0.95 scale, and the
        finding must read at 36 px or more there). Two lines when it fits at that size, else three."""
        x = self.M if x is None else x
        w = w or self.span(0, 12)
        text = s.get("head", "")
        lines = lambda sz: c.measure(text, "heading", sz, w, self.T_LEAD, upper=self.upper_head) / (sz * self.T_LEAD)
        n = 2 if lines(min_size) <= 2 else 3
        el = self.head(c, text, x, y, w, size * self.T_LEAD * n + 2, size=size, min_size=min_size, color=color)
        y = el["bottom"]
        if s.get("subhead"):
            y = c.text(s["subhead"], x, y + 10, w, self.SUB * 1.3 * 2, face=sub_face or self.SUB_FACE, size=self.SUB, min_size=18, lead=1.3,
                       color=sub_color or self.T.muted, marks=s.get("sub_marks", ""))["bottom"]
        return y

    @staticmethod
    def growth_text(bars, i) -> str:
        """"+212": the rise a growth segment draws, written the way its bar's value is."""
        d = (bars[i][2] or 0) - (bars[i - 1][2] or 0)
        like = bars[i][1]
        cur = next((ch for ch in like if ch in "$£€"), "")
        pct = "%" if "%" in like else ""
        return f"+{cur}{d:,.0f}{pct}" if d == int(d) else f"+{cur}{d:,.1f}{pct}"

    def bullets(self, c, items, x, y, w, h, size=26, min_size=20, color=None, marker="square", mcolor=None, gap=0.55, lead=1.25):
        """Points set as a list: the marker hangs in the margin, the items share one size and fill the space."""
        color, mcolor = color or self.T.ink, mcolor or self.T.accent
        indent = 30.0 if marker else 0.0
        s = size
        while True:
            hs = [c.measure(t + (" " + m if m else ""), "body", s, w - indent, lead) for t, m in items]
            total = sum(hs) + gap * s * (len(items) - 1)
            if total <= h or s <= min_size:
                break
            s -= 1
        if total > h:
            c.scene["long"] = True
        g = gap * s
        yy = y
        out = []
        for i, (t, m) in enumerate(items):
            el = c.text(t, x + indent, yy, w - indent, hs[i], face="body", size=s, lead=lead, color=color, marks=m, role="body")
            out.append(el)
            mid = yy + s * lead / 2 + s * 0.04
            if marker == "square":
                c.rect(x, mid - 4, 8, 8, mcolor, mk=True)
            elif marker == "dash":
                c.rect(x, mid - 1, 16, 2, mcolor, mk=True)
            yy += hs[i] + g
        return out

    def rows(self, c, items, x, y, w, h, size=26, min_size=19, color=None, ncolor=None, numbered=True, hair=None, lead=1.22):
        """Points as ruled rows: a hairline over each, a small number hung in its own column, the text at one size,
        the rows spread over the space. The consulting list, not a bullet wall."""
        T = self.T
        color, ncolor, hair = color or T.ink, ncolor or T.accent_text, hair or T.hair
        indent = 52.0 if numbered else 0.0
        n = max(1, len(items))
        s = size
        while True:
            hs = [c.measure(t + (" " + m if m else ""), "body", s, w - indent, lead) for t, m in items]
            pad = s * 0.7
            total = sum(hs) + 2 * pad * n
            if total <= h or s <= min_size:
                break
            s -= 1
        if total > h:
            c.scene["long"] = True
        rowh = [max(hh + 2 * pad, (h / n) if total < h * 0.7 else 0) for hh in hs]
        rowh = [min(r, hh + 2 * pad + 40) for r, hh in zip(rowh, hs)]
        yy = y
        for i, (t, m) in enumerate(items):
            c.rect(x, yy, w, 1, hair)
            ty = yy + pad
            if numbered:
                c.text(f"{i + 1:02d}", x, ty + (s - 15) * 0.55, indent - 8, 20, face="label", size=15, lead=1.2, color=ncolor, max_lines=1)["mk"] = True
            c.text(t, x + indent, ty, w - indent, hs[i], face="body", size=s, lead=lead, color=color, marks=m, role="body")
            yy += rowh[i]
        c.rect(x, yy, w, 1, hair)
        return yy

    def paired(self, c, cols, xs, ws, y, h, size=22, min_size=16, colors=None, hair=None, lead=1.25, heads=None):
        """Two columns as one table: row i of the left list beside row i of the right, both on the same rule, the row as
        tall as its taller cell. A comparison read across, not two lists side by side."""
        T = self.T
        hairs = hair if isinstance(hair, tuple) else (hair or T.hair, hair or T.hair)
        colors = colors or (T.ink, T.ink)
        lists = [items for _label, items in cols][:2]
        n = max(len(l) for l in lists) if lists else 0
        if not n:
            return y
        s = size
        while True:
            pad = s * 0.55
            hts = [max(c.measure(l[i][0] + (" " + l[i][1] if l[i][1] else ""), "body", s, ws[k], lead) if i < len(l) else 0
                       for k, l in enumerate(lists)) + 2 * pad for i in range(n)]
            if sum(hts) <= h or s <= min_size:
                break
            s -= 1
        if sum(hts) > h:
            c.scene["long"] = True
        yy = y
        for i in range(n):
            for k, l in enumerate(lists):
                if i <= len(l):
                    c.rect(xs[k], yy, ws[k], 1, hairs[k])
                if i < len(l):
                    t, m = l[i]
                    c.text(t, xs[k], yy + pad, ws[k], hts[i] - pad, face="body", size=s, lead=lead, color=colors[k], marks=m, role="body")
            yy += hts[i]
        for k, l in enumerate(lists):
            if len(l) == n:
                c.rect(xs[k], yy, ws[k], 1, hairs[k])
        return yy

    # ------------------------------------------------------------ charts --

    def _hi(self, bars, hi):
        if hi is not None and 0 <= hi < len(bars):
            return hi
        return max(range(len(bars)), key=lambda i: bars[i][2] or 0)

    def hbars(self, c, bars, x, y, w, h, hi=None, size=None, vsize=None, accent=None, tint=None, ink=None, axis=None,
              grid=False, value_face="label", max_bar=46.0, label_w=None, finding_bold=False, apart=False, label_face="body", growth=None):
        """Horizontal bars labeled directly: names right-aligned to a hairline axis, each value just past its bar, the
        finding in the accent and the rest in a tint. No legend, nothing to decode."""
        T = self.T
        size, vsize = size or self.LABEL, vsize or self.VALUE
        accent, tint, ink, axis = accent or T.accent, tint or T.tint, ink or T.ink, axis or T.ink
        n = len(bars)
        hi = self._hi(bars, hi)
        top = max([b[2] for b in bars if b[2] is not None] or [1]) or 1
        if grid:
            st = nice_step(top)
            while math.ceil(top / st - 1e-9) * st > top * 1.2 and st > 1:
                st /= 2
            top = math.ceil(top / st - 1e-9) * st
        lw = label_w or min(w * 0.34, max(c.ty.width(b[0], "body_bold", size) for b in bars) + 22)
        vw = max(c.ty.width(b[1], value_face, vsize) for b in bars) + 30
        x0 = x + lw
        span = w - lw - vw
        tick_room = 30 if grid else 0
        sep = apart and hi == n - 1 and n >= 3
        rows_n = n + (0.5 if sep else 0)
        row = min((h - tick_room) / rows_n, max_bar / 0.58)
        bh = min(row * 0.58, max_bar)
        yy = y + tick_room + max(0.0, (h - tick_room - row * rows_n) / 2)
        if grid:
            step = st
            while top / step > 6:
                step *= 2
            k = 0
            while step * k <= top * 1.0001 and k < 12:
                gx = x0 + span * step * k / top
                c.rect(gx, yy - 6, 1, row * rows_n + 6, T.hair)
                c.text(fmt_tick(step * k, bars[0][1]), gx - 60, yy - 30, 120, 18, face="label", size=14, lead=1.2, color=T.muted,
                       align="center", max_lines=1)
                k += 1
        for i, (label, value, num, marks) in enumerate(bars):
            ry = yy + (i + (0.5 if sep and i == n - 1 else 0)) * row + (row - bh) / 2
            if sep and i == n - 1:
                c.rect(x, yy + (n - 1) * row + row * 0.25, w, 1, T.hair)
            ln = max(2.0, span * ((num or 0) / top)) if num else 2.0
            is_hi = i == hi
            c.rect(x0, ry, ln, bh, accent if is_hi else tint, bar=i)
            if growth == i and i > 0 and not is_hi and bars[i - 1][2] and num and num > bars[i - 1][2]:
                # the subhead's difference, drawn: the part of this bar past the one before it, a step darker
                gx = x0 + span * (bars[i - 1][2] / top)
                c.rect(gx, ry, x0 + ln - gx, bh, T.grow)
                c.rect(gx - 0.5, ry - row + bh + (row - bh) / 2 - 2, 1, row - bh + 4 + 2, T.muted)
                # the finding labelled on the chart: the rise, set in the segment that draws it
                gt = self.growth_text(bars, i)
                gs = min(18.0, bh * 0.55)
                on = C.best_text_on(T.grow, [T.paper, T.ink, "#ffffff", "#111111"])[0]
                if c.ty.width(gt, "body_bold", gs) + 14 <= x0 + ln - gx:
                    c.text(gt, gx, ry + (bh - gs * 1.2) / 2, x0 + ln - gx - 8, gs * 1.2, face="body_bold", size=gs, lead=1.2,
                           color=on, align="right", max_lines=1)
            c.text(label, x, ry + (bh - size * 1.2) / 2, lw - 14, size * 1.2, face="body_bold" if (is_hi and finding_bold) else label_face,
                   size=size, min_size=15, lead=1.2, color=ink, align="right", max_lines=1)
            c.text(value, x0 + ln + 10, ry + (bh - vsize * 1.2) / 2, vw + 20, vsize * 1.2, face=value_face, size=vsize, lead=1.2,
                   color=T.accent_text if (is_hi and accent == T.accent) else ink, marks=marks, max_lines=1)
        ax = axis if axis != T.ink else T.quiet
        if sep:
            c.rect(x0 - 0.5, yy - 4, 1, (n - 1) * row + row * 0.25 - 4 + 4, ax)
            c.rect(x0 - 0.5, yy + (n - 1) * row + row * 0.25 + 6, 1, row * rows_n - ((n - 1) * row + row * 0.25 + 6) + 4, ax)
        else:
            c.rect(x0 - 0.5, yy - 4, 1, row * rows_n + 8, ax)
        return hi

    def columns(self, c, bars, x, y, w, h, hi=None, vsize=None, lsize=None, accent=None, tint=None, ink=None, base=None,
                value_face="heading", colw_max=170.0, gap_ratio=0.42, value_color=None, base_w=2.0, center=False, apart=False, growth=None, **_):
        """Columns on a baseline: the value set over each column as a display figure, the label under it, the finding
        in the accent, the rest in a tint."""
        T = self.T
        vsize, lsize = vsize or 40.0, lsize or self.LABEL
        accent, tint, ink, base = accent or T.accent, tint or T.tint, ink or T.ink, base or T.ink
        n = len(bars)
        hi = self._hi(bars, hi)
        top = max([b[2] for b in bars if b[2] is not None] or [1]) or 1
        sep = apart and hi == n - 1 and n >= 3
        cw = min(colw_max, w / (n + (n - 1) * gap_ratio + (0.5 if sep else 0)))
        gap = cw * gap_ratio if n > 1 else 0
        total = n * cw + (n - 1) * gap
        x1 = x + ((w - total) / 2 if center else 0)
        lab_h = lsize * 1.2 * 2 + 12
        # every value at one size, small enough that each stays inside its own column and the gap after it: a value
        # never runs into the next value or over the next bar ("$1,420,000" beside "$1,610,000")
        room = cw + gap * 0.8 if n > 1 else w
        while vsize > 18 and max(c.ty.width(b[1], value_face, vsize) + (0.32 * vsize * (len(b[3]) + 1) if b[3] else 0) for b in bars) > room:
            vsize -= 1
        y1 = y + h - lab_h
        y0 = y + vsize * 1.25
        for i, (label, value, num, marks) in enumerate(bars):
            cx = x1 + i * (cw + gap) + (cw * 0.5 if sep and i == n - 1 else 0)
            if sep and i == n - 1:
                c.rect(cx - gap / 2 - cw * 0.25, y0, 1, y1 - y0, T.hair)
            bh = max(3.0, (y1 - y0) * ((num or 0) / top)) if num else 3.0
            is_hi = i == hi
            c.rect(cx, y1 - bh, cw, bh, accent if is_hi else tint, bar=i)
            if growth == i and i > 0 and not is_hi and bars[i - 1][2] and num and num > bars[i - 1][2]:
                ph = (y1 - y0) * (bars[i - 1][2] / top)
                c.rect(cx, y1 - bh, cw, bh - ph, T.grow)
                gt = self.growth_text(bars, i)
                gs = min(20.0, (bh - ph) * 0.6, cw / max(1, len(gt)) * 1.6)
                if gs >= 11:
                    on = C.best_text_on(T.grow, [T.paper, T.ink, "#ffffff", "#111111"])[0]
                    c.text(gt, cx, y1 - bh + (bh - ph - gs * 1.2) / 2, cw, gs * 1.2, face="body_bold", size=gs, lead=1.2, color=on,
                           align="center", max_lines=1)
            vw = room + 2 if n > 1 else w - (cx - x)
            c.text(value, cx, y1 - bh - vsize * 1.18, vw, vsize * 1.12, face=value_face, size=vsize, min_size=vsize, lead=1.0,
                   color=value_color or (T.accent_text if (is_hi and accent == T.accent) else ink), marks=marks, max_lines=1)
            c.text(label, cx, y1 + 10, min(cw + gap * 0.9, x + w - cx), lab_h - 10, face="body", size=lsize, min_size=min(14, lsize),
                   lead=1.2, color=ink, max_lines=2)
        c.rect(x, y1, w, base_w, base)
        return hi

    @staticmethod
    def growth_of(spec: dict) -> Optional[int]:
        """The bar whose rise over the bar before it is the number the subhead states ("212 more adults than last year"
        over 936 and 1,148), or None."""
        nums = [parse_value(m) for m in re.findall(r"[$£€]?\d[\d,]*(?:\.\d+)?", spec.get("subhead") or "")]
        bars = spec.get("bars") or []
        for n in nums:
            for i in range(1, len(bars)):
                a, b = bars[i - 1][2], bars[i][2]
                if a is not None and b is not None and n and abs((b - a) - n) < 0.5:
                    return i
        return None

    def bars(self, c, bars, x, y, w, h, highlight=None, form=None, **kw):
        """The exhibit's chart, drawn the system's way (``form``: hbars or columns); ``highlight`` is the finding."""
        apart = highlight is not None and highlight == len(bars) - 1 and len(bars) >= 3
        if (form or self.chart) == "columns" and len(bars) <= 6:
            return self.columns(c, bars, x, y, w, h, hi=highlight, apart=apart, **kw)
        return self.hbars(c, bars, x, y, w, h, hi=highlight, apart=apart, **{k: v for k, v in kw.items() if k in (
            "size", "vsize", "accent", "tint", "ink", "axis", "grid", "value_face", "max_bar", "label_w", "finding_bold", "label_face",
            "growth")})

    def picture(self, c, spec, x, y, w, h) -> bool:
        if spec.get("picture"):
            c.image(x, y, w, h, spec["picture"])
            return True
        return False

    # ------------------------------------------------------------ slides --

    draws_fig = True  # this system sets the cover's figure and the closing's amount

    def compose(self, spec: dict) -> dict:
        self._eyebrow = spec.get("eyebrow") or ""
        if not self.draws_fig and (spec.get("fig") or spec.get("amount")):
            spec = {k: v for k, v in spec.items() if k != "fig"}
            if spec.get("amount"):
                spec["cta"] = " ".join(x for x in (spec.get("cta"), f"{spec.get('amount_label') or 'The ask'}: {spec['amount']}") if x)
                spec.pop("amount")
        k = spec["kind"]
        fn = getattr(self, f"s_{k}", None) or self.s_content
        sc = fn(spec)
        sc["kind"], sc["num"] = k, spec.get("num", 1)
        marked = [el for el in sc["els"] if el["t"] == "text" and el.get("marks")]
        if spec.get("src") and marked and len({el["marks"] for el in marked}) == 1 and "," not in marked[0]["marks"]:
            # every line cites the one source the slide's foot names: the foot says it once, quietly
            for el in marked:
                el["marks"] = ""
                el.pop("mcolor", None)
        return sc

    def s_spec(self, s):
        """Loop 4: a slide the model designed as positioned elements in brand roles (``spec.py``), set in this system's
        faces, colors and foot, measured and checked."""
        try:
            from . import spec as SP
        except ImportError:  # loaded loose
            import spec as SP  # type: ignore
        return SP.compose(self, s)

    def s_title(self, s):
        """A cover: the field color full bleed, furniture top and bottom, the title large in the lower left."""
        T = self.T
        c = self.canvas(T.field)
        self.label(c, s.get("org") or "", self.M, 30, self.span(0, 6), color=T.field_text)
        c.rect(self.M, 62, W - 2 * self.M, 1, T.field_hair)
        self.label(c, s.get("date") or "", self.M, H - 40, self.span(0, 6), color=T.field_muted)
        fig = bool(s.get("fig"))
        tw = self.span(0, 7) if fig else self.span(0, 12)
        tsize = 64 if fig else 88
        sub_h = c.measure(s.get("sub", ""), "body", 24, self.span(0, 7 if fig else 9), 1.3) + 22 if s.get("sub") else 0
        th = c.measure(s["title"], "heading", tsize, tw, 0.98)
        top = max(96.0, H - 92 - th - sub_h)
        if T.field_accent != T.field_text:
            c.rect(self.M, top - 30, 64, 5, T.field_accent)
        el = self.head(c, s["title"], self.M - 4, top, tw, th + 4, size=tsize, min_size=44, color=T.field_text, lead=0.98)
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 20, self.span(0, 7 if fig else 9), 80, size=24, min_size=20, lead=1.3, color=T.field_muted)
        if fig:
            c.rect(self.col(7) + self.GUT / 2, 96, 1, H - 96 - 72, T.field_hair)
            self.cover_fig(c, s, self.col(8) - 8, 96, self.span(8, 12) + 8, H - 92 - 96, T.field_accent, T.field_muted, T.field_hair)
        c.rect(self.M, H - 52, W - 2 * self.M, 1, T.field_hair)
        c.logo(W - self.M, 20, 32, "band", align="right")
        return c.done(dark=True, band=True)

    def s_section(self, s):
        """A divider: a panel of the field color holding the part number, the heading beside it on the paper."""
        T = self.T
        c = self.canvas()
        pw = self.col(4) - self.GUT / 2
        c.rect(0, 0, pw, H, T.field)
        n = s.get("n") or 1
        self.label(c, "Part", self.M, 64, pw - self.M, color=T.field_muted)
        c.text(f"{n:02d}", self.M - 4, 84, pw - self.M, 150, face="heading", size=128, lead=1.0, color=T.field_accent, max_lines=1)
        hh = c.measure(s["head"], "heading", 48, self.span(5, 12), 1.06)
        sh = c.measure(s.get("sub", ""), "body", 24, self.span(5, 12), 1.3) + 20 if s.get("sub") else 0
        top = max(80.0, (H - hh - sh) / 2)
        el = self.head(c, s["head"], self.col(5), top, self.span(5, 12), hh + 4, size=48, min_size=34)
        if s.get("sub"):
            c.text(s["sub"], self.col(5), el["bottom"] + 20, self.span(5, 12), 110, size=24, min_size=19, lead=1.3, color=T.muted,
                   marks=s.get("marks", ""))
        return c.done()

    def s_content(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, w=self.span(0, 11), size=40)
        self.rows(c, s.get("items") or [], self.M, y + 30, self.span(0, 11), H - 60 - (y + 30), size=26)
        self.foot(c, s, rule=False)
        return c.done()

    def s_sources(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, {**s, "section": ""})
        el = self.head(c, s.get("head", "Sources"), self.M, 66, self.span(0, 8), 60, size=34, min_size=28)
        yy = el["bottom"] + 26
        for i, it in enumerate(s.get("items") or []):
            c.rect(self.M, yy, W - 2 * self.M, 1, T.hair)
            c.text(f"{i + 1}", self.M, yy + 12, 40, 24, face="label", size=15, color=T.accent_text, max_lines=1)
            el = c.text(it[0], self.M + 52, yy + 10, W - 2 * self.M - 52, 70, size=18, min_size=14, lead=1.35, color=T.ink)
            yy = el["bottom"] + 14
        return c.done()

    def s_stat(self, s):
        """One huge number on the left, what it counts and what it means in a column on the right."""
        T = self.T
        c = self.canvas()
        v = c.text(s["value"], self.M - 10, 80, self.span(0, 7) + 10, 380, face="heading", size=300, min_size=96, lead=1.0,
                   color=T.accent, max_lines=1, anchor="middle")
        # the words start where the number ends, so a short number ("71") leaves no empty middle third (round 3)
        vw = c.ty.width(s["value"], "heading", self.fit_size(c, [s["value"]], self.span(0, 7) + 10, 300, 96))
        x = min(self.col(7) + 8, max(self.col(4), self.M - 10 + vw + 36))
        tw = W - self.M - x
        big = tw > self.span(7, 12) + 60
        lsz, csz = (34, 23) if big else (28, 20)
        lh = c.measure(s.get("label", "") + " 1", "body_bold", lsz, tw, 1.2)
        ch = c.measure(s.get("context", ""), "body", csz, tw, 1.4) + 20 if s.get("context") else 0
        y = max(150.0, 276 - (lh + ch) / 2)
        c.rect(x, y - 22, 40, 4, T.accent)
        el = c.text(s.get("label", ""), x, y, tw, 170, face="body_bold", size=lsz, min_size=21, lead=1.2, color=T.head,
                    marks=s.get("marks", ""))
        if s.get("context"):
            c.text(s["context"], x, el["bottom"] + 18, tw, 400 - el["bottom"] + 40, size=csz, min_size=16, lead=1.4,
                   color=T.muted)
        self.foot(c, s)
        return c.done()

    def s_quote(self, s):
        """Round 10 (critics 7, 9): the quote fills its page. It is set as large as half the page takes, the quote mark
        sits on its first line, and the speaker and where they said it close it, so no half-empty page is left."""
        T = self.T
        c = self.canvas()
        q = f"{s['quote'].rstrip(',;: ')}”"
        w = self.span(1, 11)
        size = 34.0
        for sz in (66.0, 60.0, 54.0, 48.0, 44.0, 40.0, 36.0):
            if c.measure(q, "heading", sz, w, 1.12) <= H * 0.52:
                size = sz
                break
        qh = c.measure(q, "heading", size, w, 1.12)
        who_h = 74 if s.get("who") else 0
        top = max(118.0, (H - 40 - qh - who_h) / 2)
        c.text("“", self.col(1) - size * 0.82, top - size * 0.2, size * 0.8, size * 1.7, face="heading", size=size * 1.6, lead=1.0,
               color=T.accent, max_lines=1)
        el = c.text(q, self.col(1), top, w, qh + size, face="heading", size=size, min_size=26, lead=1.12, color=T.head,
                    marks=s.get("marks", ""))
        if s.get("who"):
            y = el["bottom"] + 30
            c.rect(self.col(1), y + 9, 40, 3, T.accent)
            c.text(s["who"], self.col(1) + 54, y, w - 54, 28, face="body", size=21, min_size=16, lead=1.25, color=T.ink, max_lines=1)
            if s.get("src_short"):
                c.text(s["src_short"].replace("Source: ", "From the "), self.col(1) + 54, y + 30, w - 54, 22, face="body", size=15,
                       min_size=12, lead=1.25, color=T.ink, max_lines=1)
        self.foot(c, s)
        return c.done()

    def s_comparison(self, s):
        """Today against the plan: two ruled columns, the second one set on a panel and headed in the accent."""
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40) + 30
        cols = s.get("cols") or []
        xs, ws = [self.col(0), self.col(6)], [self.span(0, 6), self.span(6, 12)]
        for i, (label, items) in enumerate(cols[:2]):
            c.rect(xs[i], y, ws[i], 4, T.accent if i == 1 else T.main)
            self.label(c, label, xs[i], y + 14, ws[i], color=T.accent_text if i == 1 else T.head, size=15)
        self.paired(c, cols, xs, ws, y + 46, H - 64 - (y + 46), size=22, colors=(T.ink, T.ink))
        self.foot(c, s, rule=False)
        return c.done()

    def exhibit_chart(self, c, s, x, y, w, h):
        unit = s.get("unit") or ""
        if unit:
            self.label(c, unit, x, y, w, color=self.T.muted, size=14, upper=False, face="body")
            y += 30
            h -= 30
        return self.bars(c, s["bars"], x, y, w, h, highlight=s.get("hi"), growth=self.growth_of(s), grid=self.grid_lines,
                         max_bar=min(72.0, max(46.0, h / max(1, len(s["bars"])) * 0.5)), size=22, vsize=26)

    def note(self, c, s, x, bottom, w, color=None, face="body") -> float:
        """The exhibit's note under the chart, set small; returns how much room the chart gives up for it."""
        if not s.get("note"):
            return 0.0
        h = c.measure(s["note"], face, 14, w, 1.3)
        c.text(s["note"], x, bottom - h, w, h, face=face, size=14, min_size=12, lead=1.3, color=color or self.T.muted, max_lines=2)
        return h + 14

    def s_exhibit(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.exhibit_head(c, s, 66)
        nh = self.note(c, s, self.M, H - 52, W - 2 * self.M)
        self.exhibit_chart(c, s, self.M, y + 30, W - 2 * self.M, H - 60 - nh - (y + 30))
        self.foot(c, s)
        return c.done()

    def s_timeline(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40)
        steps = s.get("steps") or []
        n = max(1, len(steps))
        cw = (W - 2 * self.M) / n
        ly = y + 120
        c.rect(self.M, ly, W - 2 * self.M, 2, T.hair)
        for i, (when, text, marks) in enumerate(steps):
            x = self.M + i * cw
            last = i == n - 1
            c.rect(x, ly - 7, 16, 16, T.accent if last else T.main)
            c.text(when, x, ly - 50, cw - 16, 30, face="label", size=20, min_size=13, color=T.accent_text if last else T.head, max_lines=1,
                   upper=False)
            c.text(text, x, ly + 28, cw - 22, H - 60 - (ly + 28), size=22, min_size=15, lead=1.3, color=T.ink, marks=marks)
        self.foot(c, s)
        return c.done()

    def s_image(self, s):
        T = self.T
        c = self.canvas()
        if self.picture(c, s, self.col(6), 0, W - self.col(6), H):
            self.label(c, s.get("section", ""), self.M, 40, self.span(0, 5), color=T.accent_text)
            el = self.head(c, s.get("head", ""), self.M, 90, self.span(0, 5), 200, size=40, min_size=28)
            if s.get("caption"):
                c.text(s["caption"], self.M, el["bottom"] + 22, self.span(0, 5), 180, size=20, min_size=16, lead=1.4, color=T.muted,
                       marks=s.get("marks", ""))
            return c.done()
        return self.s_statement(s)

    def s_statement(self, s):
        """An image slide with no picture: the line set as a statement on a field of the kit's color."""
        T = self.T
        c = self.canvas(T.field)
        hh = c.measure(s.get("head", ""), "heading", 52, self.span(0, 10), 1.06)
        ch = c.measure(s.get("caption", ""), "body", 24, self.span(0, 8), 1.35) + 26 if s.get("caption") else 0
        top = max(90.0, (H - hh - ch) / 2)
        c.rect(self.M, top - 30, 48, 4, T.field_accent)
        el = self.head(c, s.get("head", ""), self.M, top, self.span(0, 10), hh + 4, size=52, min_size=34, color=T.field_text)
        if s.get("caption"):
            c.text(s["caption"], self.M, el["bottom"] + 24, self.span(0, 8), 150, size=24, min_size=18, lead=1.35, color=T.field_muted,
                   marks=s.get("marks", ""))
        return c.done(dark=True, band=True)

    def s_closing(self, s):
        T = self.T
        c = self.canvas(T.field)
        if T.field_accent != T.field_text:
            c.rect(0, 0, W, 6, T.field_accent)
        amt = bool(s.get("amount"))
        hw, tw = (self.span(0, 7), self.span(0, 7)) if amt else (self.span(0, 10), self.span(0, 8))
        hs, ts = (40, 21) if amt else (48, 24)
        hh = c.measure(s.get("head", ""), "heading", hs, hw, 1.06) if s.get("head") else 0
        th = c.measure(s.get("text", ""), "body", ts, tw, 1.35) + 22 if s.get("text") else 0
        y = max(64.0, (H - hh - th - (70 if s.get("cta") else 0)) / 2 - 10)
        if s.get("head"):
            y = self.head(c, s["head"], self.M, y, hw, hh + 4, size=hs, min_size=30, color=T.field_text)["bottom"] + 22
        if s.get("text"):
            y = c.text(s["text"], self.M, y, tw, min(160.0, H - 130 - y), size=ts, min_size=17, lead=1.35, color=T.field_muted,
                       marks="" if amt else s.get("marks", ""))["bottom"] + 30
        if s.get("cta"):
            c.rect(self.M, y, tw, 1, T.field_hair)
            c.text(s["cta"], self.M, y + 16, tw, 64, face="body_bold", size=22, min_size=17, lead=1.3, color=T.field_text,
                   max_lines=2)
        if amt:
            c.rect(self.col(7) + self.GUT / 2, 80, 1, H - 160, T.field_hair)
            self.ask_amount(c, s, self.col(8), 80, self.span(8, 12), H - 160, T.field_accent, T.field_muted, hair=T.field_accent)
        req = s.get("required") or []
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 58 - 18 * (len(req[:2]) - 1 - i), self.span(0, 9), 18, face="body", size=12, color=T.field_muted, max_lines=1)
        c.logo(W - self.M, H - 62, 28, "band", align="right")
        return c.done(dark=True, band=True)


    # ------------------------------------------------------------ evidence slides --
    # A funder reads a slide for its numbers. These three put the evidence on the page with the same craft as the
    # rest of the system: figures side by side, points that lead with their number, and a before/after read across.

    def fit_size(self, c, values, w, size, min_size=28.0, face="heading") -> float:
        s = size
        while s > min_size and max([c.ty.width(v or "", face, s) for v in values] or [0]) > w:
            s -= 2
        return s

    @staticmethod
    def split_unit(v: str) -> tuple:
        m = re.match(r"^([$£€]?\d[\d,.]*%?)\s+([A-Za-z][A-Za-z ]{1,16})$", v or "")
        return (m.group(1), m.group(2)) if m else (v, "")

    def figures_row(self, c, figs, x, y, w, h, vface="heading", vcolor=None, lcolor=None, ccolor=None, rule=None, first=None):
        """Three or four figures side by side, each on its own rule: the number large, what it counts in bold, one
        line of context. The block sits in the middle of the room it is given; the first rule is the accent."""
        T = self.T
        figs = list(figs or [])[:4]
        n = max(1, len(figs))
        gut = self.GUT * 1.6
        cw = (w - gut * (n - 1)) / n
        parts = [self.split_unit(f[0]) for f in figs]  # "14 months": the number large, its unit set small beside it
        room = [cw * 0.9 - (c.ty.width(p[1], "body_bold", 22) + 10 if p[1] else 0) for p in parts]
        vs = min(104.0 if n <= 3 else 92.0, h * 0.4)
        while vs > 30 and any(c.ty.width(p[0], vface, vs) > r for p, r in zip(parts, room)):
            vs -= 2
        ls, cs = (22.0, 17.0) if n <= 3 else (20.0, 16.0)
        lh = max([c.measure(f[1], "body_bold", ls, cw, 1.22) for f in figs] or [0])
        chh = max([c.measure(f[2], "body", cs, cw, 1.35) for f in figs if f[2]] or [0])
        block = 22 + vs * 1.08 + 14 + lh + (12 + chh if chh else 0)
        yy = y + max(0.0, (h - block) / 2)
        for i, (v, l, ctx, m) in enumerate(figs):
            xx = x + i * (cw + gut)
            c.rect(xx, yy, cw, 4 if i == 0 else 2, (first or T.accent) if i == 0 else (rule or T.main))
            num, unit = parts[i]
            vcol = vcolor or (T.accent_text if i == 0 else T.head)
            ve = c.text(num, xx - 2, yy + 22, cw + 4, vs * 1.08, face=vface, size=vs, min_size=vs * 0.7, lead=1.0,
                        color=vcol, marks="" if unit else m, max_lines=1)
            if unit:
                us = max(16.0, vs * 0.3)
                ux = xx - 2 + c.ty.width(num, vface, ve["size"]) + 8
                c.text(unit, ux, yy + 22 + ve["size"] * 0.72 - us, max(40.0, xx + cw - ux), us * 1.2, face="body_bold", size=us, min_size=12,
                       lead=1.2, color=vcol, marks=m, max_lines=1)
            le = c.text(l, xx, ve["bottom"] + 14, cw, lh + 4, face="body_bold", size=ls, min_size=15, lead=1.22,
                        color=lcolor or T.ink, role="body")
            if ctx:
                c.text(ctx, xx, le["bottom"] + 12, cw, chh + 4, face="body", size=cs, min_size=13, lead=1.35, color=ccolor or T.muted)
        return yy + block

    def s_figures(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40)
        nh = 0.0
        if s.get("note"):  # round 16: the slide's lines with no number, one caption band under the row
            w = W - 2 * self.M
            sz = 20.0
            while sz > 15 and c.measure(s["note"], "body", sz, w, 1.3) > 110:
                sz -= 1
            nh = c.measure(s["note"], "body", sz, w, 1.3)
            ny = H - 62 - nh
            c.rect(self.M, ny - 16, w, 1, self.T.hair)
            c.text(s["note"], self.M, ny, w, nh + 4, face="body", size=sz, min_size=15, lead=1.3, color=self.T.ink, role="body")
            nh += 30
        self.figures_row(c, s.get("figs") or [], self.M, y + 30, W - 2 * self.M, H - 62 - nh - (y + 30))
        self.foot(c, s)
        return c.done()

    def s_table(self, s):
        """Round 16: a money or figures list as one table: the line's words on the left, its amount right-aligned in
        its own column, the whole (a budget, a total, the gap) bold on a heavier rule, the lines with no amount set
        under the table as one note. Type steps down to its floor to fit; nothing is cut."""
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40) + 26
        x, w = self.M, W - 2 * self.M
        rows = s.get("rows") or []
        note = s.get("note") or ""
        bottom = H - 62
        size = 24.0
        while True:
            nh = c.measure(note, "body", max(15.0, size - 4), w, 1.3) + 18 if note else 0.0
            aw = max([c.ty.width(a, "heading", size + 4) for _l, a, _m, _b in rows] or [0]) + 24
            lw = w - aw
            hs = [c.measure(l + (" " + m if m else ""), "body_bold" if b else "body", size, lw - 16, 1.22) for l, _a, m, b in rows]
            pad = size * 0.42
            if sum(hs) + 2 * pad * len(rows) + nh <= bottom - y or size <= 15:
                break
            size -= 1
        if sum(hs) + 2 * pad * len(rows) + nh > bottom - y:
            c.scene["long"] = True
        yy = y
        for (l, a, m, b), hh in zip(rows, hs):
            rh = hh + 2 * pad
            c.rect(x, yy, w, 3 if b else 1, T.main if b else T.hair)
            c.text(l, x, yy, lw - 16, rh, face="body_bold" if b else "body", size=size, lead=1.22, color=T.head if b else T.ink,
                   marks=m, anchor="middle", role="body")
            c.text(a, x + lw, yy, aw, rh, face="heading", size=size + 4, min_size=size, lead=1.0,
                   color=T.accent_text if b else T.ink, anchor="middle", align="right", max_lines=1)
            yy += rh
        c.rect(x, yy, w, 1, T.hair)
        if note:
            c.text(note, x, yy + 16, w, bottom - yy - 16, face="body", size=max(15.0, size - 4), min_size=14, lead=1.3,
                   color=T.ink, role="body")
        self.foot(c, s, rule=False)
        return c.done()

    def ledger(self, c, items, figs, x, y, w, h, size=24, fsize=40.0, hair=None, fcolor=None, color=None, fface="heading"):
        """Points that lead with their numbers: a ruled row each, the figure set large in its own column, the line
        beside it. A point with no number leaves its figure cell empty. Rows share the room evenly."""
        T = self.T
        hair, fcolor, color = hair or T.hair, fcolor or T.accent_text, color or T.ink
        n = max(1, len(items))
        fsize = self.fit_size(c, [f for f in figs if f], w * 0.3, fsize, 24, fface)
        fw = max([c.ty.width(f, fface, fsize) for f in figs if f] or [0]) + 26
        tw = w - fw
        s = size
        while True:
            hs = [max(c.measure(t + (" " + m if m else ""), "body", s, tw, 1.25), fsize * 1.05 if figs[i] else 0)
                  for i, (t, m) in enumerate(items)]
            pad = s * 0.55
            if sum(hs) + 2 * pad * n <= h or s <= 17:
                break
            s -= 1
        if sum(hs) + 2 * pad * n > h:
            c.scene["long"] = True
        spare = max(0.0, h - sum(hs) - 2 * pad * n)
        extra = min(spare / n, 46.0)
        yy = y
        for i, (t, m) in enumerate(items):
            rh = hs[i] + 2 * pad + extra
            c.rect(x, yy, w, 1, hair)
            if figs[i]:
                c.text(figs[i], x, yy, fw - 14, rh, face=fface, size=fsize, min_size=fsize * 0.75, lead=1.0, color=fcolor,
                       anchor="middle", max_lines=1)
            c.text(t, x + fw, yy, tw, rh, face="body", size=s, lead=1.25, color=color, marks=m, anchor="middle", role="body")
            yy += rh
        c.rect(x, yy, w, 1, hair)
        return yy

    def s_ledger(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40)
        self.ledger(c, s.get("items") or [], s.get("figs") or [], self.M, y + 26, self.span(0, 12), H - 62 - (y + 26))
        self.foot(c, s, rule=False)
        return c.done()

    def matched(self, c, s, x, y, w, h, head_color=None, panel=None, hair=None, lface="label"):
        """Before and after, read across: one row per thing (sites, staff, the wait), its label in the margin, today's
        value, then the plan's value on a tinted panel headed in the accent."""
        T = self.T
        hair = hair or T.hair
        panel = panel or C.mix(T.accent, T.paper, 0.9 if not T.dark else 0.8)
        rows = s.get("rows") or []
        left, right = s.get("labels") or ("Today", "With the plan")
        lw = w * 0.24
        cw = (w - lw) / 2
        xl, xr = x + lw, x + lw + cw
        hh = 52.0
        c.rect(xr, y, cw, h, panel)
        c.rect(xl, y, cw - 16, 4, T.main)
        c.rect(xr, y, cw, 4, T.accent)
        c.text(left, xl, y + 14, cw - 28, 30, face="body_bold", size=20, min_size=15, color=head_color or T.head, max_lines=1)
        c.text(right, xr + 18, y + 14, cw - 32, 30, face="body_bold", size=20, min_size=15, color=T.accent_text, max_lines=1)
        n = max(1, len(rows))
        s_ = 22.0
        body_h = h - hh
        while True:
            hs = [max(c.measure(a + (" " + m if m else ""), "body", s_, cw - 30, 1.25), c.measure(b, "body_bold", s_, cw - 36, 1.25))
                  for (_l, a, b, m) in rows]
            pad = s_ * 0.6
            if sum(hs) + 2 * pad * n <= body_h or s_ <= 15:
                break
            s_ -= 1
        if sum(hs) + 2 * pad * n > body_h:
            c.scene["long"] = True
        extra = min(max(0.0, body_h - sum(hs) - 2 * pad * n) / n, 40.0)
        yy = y + hh
        for i, (lab, a, b, m) in enumerate(rows):
            rh = hs[i] + 2 * pad + extra
            c.rect(x, yy, w, 1, hair)
            c.text(lab, x, yy, lw - 16, rh, face=lface, size=14, min_size=12, lead=1.25, color=T.muted, upper=True, track=0.08,
                   anchor="middle", max_lines=2)
            c.text(a, xl, yy, cw - 30, rh, face="body", size=s_, lead=1.25, color=T.ink, anchor="middle", role="body")
            c.text(b, xr + 18, yy, cw - 36, rh, face="body_bold", size=s_, lead=1.25, color=T.head, marks=m, anchor="middle",
                   role="body")
            yy += rh
        c.rect(x, yy, w, 1, hair)
        return yy

    def s_matched(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 66, size=40) + 28
        self.matched(c, s, self.M, y, W - 2 * self.M, H - 62 - y)
        self.foot(c, s, rule=False)
        return c.done()

    def cover_fig(self, c, s, x, y, w, h, color, label_color, hair, face="heading", align="right", size=210.0):
        """The cover's figure: the number the deck argues from, set as large as the column takes, what it counts under
        it on a hairline. It carries its source mark, like any number."""
        fig = s.get("fig")
        if not fig:
            return None
        v, lab, m = fig
        vs = self.fit_size(c, [v], w - 6, size, 36, face)
        lh = c.measure(lab, "label", 15, w, 1.3, track=0.08, upper=True) if lab else 0
        # the figure is measured in the face it is set in: as wide as the column and no taller than the room left over
        # its label, so the label always stays on the slide
        room = h - (22 + lh if lab else 0)
        vs = max(36.0, min(vs, room / 0.96))
        top = y + max(0.0, (h - vs * 0.96 - (22 + lh if lab else 0)))
        el = c.text(v, x, top, w, vs * 0.96, face=face, size=vs, min_size=vs, lead=0.96, color=color, align=align, max_lines=1)
        if lab:
            c.rect(x if align == "left" else x + w * 0.4, el["bottom"] + 10, w * 0.6, 1, hair)
            c.text(lab, x, el["bottom"] + 20, w, lh + 2, face="label", size=15, min_size=12, lead=1.3, color=label_color, align=align,
                   upper=True, track=0.08)
        return el

    def ask_amount(self, c, s, x, y, w, h, color, label_color, hair=None, face="heading", size=104.0, align="left"):
        """The closing's amount: the ask in figures, large, with what it pays for under it."""
        if not s.get("amount"):
            return None
        vs = self.fit_size(c, [s["amount"]], w - 24, size, 44, face)
        lh = c.measure(s.get("amount_label", ""), "body", 21, w, 1.3) if s.get("amount_label") else 0
        top = y + max(0.0, (h - vs - 16 - lh) / 2)
        if hair:
            c.rect(x, top - 22, 48, 4, hair)
        el = c.text(s["amount"], x, top, w, vs * 1.02, face=face, size=vs, min_size=vs, lead=1.0, color=color, marks=s.get("marks", ""),
                    max_lines=1, align=align)
        if s.get("amount_label"):
            c.text(s["amount_label"], x, el["bottom"] + 16, w, lh + 4, face="body", size=21, min_size=16, lead=1.3, color=label_color,
                   align=align)
        return el

    # ------------------------------------------------------------ graphic --

    def graphic(self, g: dict) -> dict:
        """One information graphic, 1080 x 1350: one message, labeled directly, sourced."""
        T = self.T
        c = SC.Canvas(self.ty, GW, GH, T.paper)
        M = 84.0
        y = self.g_head(c, g, M)
        self.g_body(c, g, M, y + 56, GH - 270)
        self.g_foot(c, g, M)
        marked = [el for el in c.els if el["t"] == "text" and el.get("marks")]
        if g.get("src") and marked and len({el["marks"] for el in marked}) == 1 and "," not in marked[0]["marks"]:
            for el in marked:
                el["marks"] = ""
                el.pop("mcolor", None)
        return c.done(kind="graphic")

    def g_head(self, c, g, M):
        T = self.T
        c.rect(M, 84, GW - 2 * M, 2, T.ink)
        if g.get("kicker"):
            c.text(g["kicker"], M, 108, 800, 30, face="label", size=20, color=T.accent_text, upper=True, track=0.1, max_lines=1)
        el = c.text(g["headline"], M, 150, GW - 2 * M, 250, face="heading", size=76, min_size=50, lead=1.04, color=T.head,
                    upper=self.upper_head, role="title")
        y = el["bottom"] + 24
        if g.get("dek"):
            y = c.text(g["dek"], M, y, GW - 2 * M - 80, 130, size=30, min_size=24, lead=1.32, color=T.muted, marks=g.get("dek_marks", ""))["bottom"]
        return y

    def g_bars(self, c, g, M, y, h):
        T = self.T
        if g.get("unit"):
            c.text(g["unit"], M, y, 800, 30, face="body", size=22, color=T.muted, max_lines=1)
            y += 46
            h -= 46
        if len(g["bars"]) <= 4:
            self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="columns", vsize=64, lsize=26, colw_max=230)
        else:
            self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="hbars", size=26, vsize=30, max_bar=70)

    def g_body(self, c, g, M, y, bottom):
        T = self.T
        form = g["form"]
        h = bottom - y
        if form == "bars":
            self.g_bars(c, g, M, y, h)
        elif form == "figures":
            self.g_figures(c, g, M, y, h)
        elif form == "compare":
            pair = g["bars"][:2]
            self.columns(c, pair, M + 60, y, GW - 2 * M - 120, h, hi=g.get("hi") if g.get("hi") is not None else 1, vsize=96, lsize=28,
                         colw_max=320, gap_ratio=0.3)
        else:
            steps = g["steps"]
            n = len(steps)
            rh = h / max(1, n)
            c.rect(M + 11, y + 10, 2, h - rh * 0.4, T.hair)
            for i, (when, text, marks) in enumerate(steps):
                cy = y + i * rh
                c.rect(M, cy + 4, 24, 24, T.accent if i == n - 1 else T.main)
                c.text(when, M + 60, cy, 400, 40, face="label", size=26, color=T.accent_text if i == n - 1 else T.head, max_lines=1)
                c.text(text, M + 60, cy + 44, GW - 2 * M - 60, rh - 54, size=32, min_size=24, lead=1.3, color=T.ink, marks=marks)
        return bottom

    def g_figures(self, c, g, M, y, h):
        """Big numbers that hold the page: up to three stacked, each on its own rule and set as large as its share of
        the room allows (all at one size, so none looks more certain than another), four as a two-by-two grid. The
        finding takes the accent and the heavy rule."""
        T = self.T
        figs = g["bars"][:4]
        n = len(figs)
        if not n:
            return
        cols = 2 if n == 4 else 1
        rows = (n + cols - 1) // cols
        gx = 48.0
        cw = (GW - 2 * M - (cols - 1) * gx) / cols
        rh = h / rows
        hi = self._hi(figs, g.get("hi"))
        ls = 30.0 if cols == 1 else 26.0
        lh = max(c.measure(f[0] + (" " + f[3] if f[3] else ""), "body", ls, cw, 1.28) for f in figs)
        lh = min(lh, ls * 1.28 * 2)
        vs = min(240.0 if cols == 1 else 150.0, (rh - 30 - 18 - lh - 24) / 1.0)
        vs = self.fit_size(c, [f[1] for f in figs], cw - 8, vs, 56, "heading")
        block = 30 + vs * 0.9 + 14 + lh
        for i, (label, value, _num, marks) in enumerate(figs):
            cx = M + (i % cols) * (cw + gx)
            cy = y + (i // cols) * rh + max(0.0, (rh - block) / 2 - 8)
            is_hi = i == hi
            c.rect(cx, cy, cw, 6 if is_hi else 2, T.accent if is_hi else T.ink)
            v = c.text(value, cx, cy + 30, cw, vs * 1.0, face="heading", size=vs, min_size=vs, lead=1.0,
                       color=T.accent_text if is_hi else T.head, max_lines=1)
            c.text(label, cx, v["bottom"] - vs * 0.1 + 14, cw, lh + 2, size=ls, min_size=22, lead=1.28, color=T.ink, marks=marks, max_lines=2)

    def g_foot(self, c, g, M):
        T = self.T
        y = GH - 230
        if g.get("takeaway"):
            c.rect(M, y, 64, 6, T.accent)
            c.text(g["takeaway"], M, y + 26, GW - 2 * M - 40, 100, face="body_bold", size=32, min_size=24, lead=1.28, color=T.head,
                   marks=g.get("take_marks", ""))
        c.rect(M, GH - 104, GW - 2 * M, 1, T.hair)
        if g.get("src"):
            c.text("Source: " + g["src"], M, GH - 88, GW - 2 * M - 220, 50, size=18, min_size=15, lead=1.35, color=T.muted, max_lines=2)
        c.logo(GW - M, GH - 92, 40, "paper", align="right")

    # ------------------------------------------------------------ page --

    def page(self, p: dict) -> dict:
        """A one-page brief, 612 x 792: masthead, the lead finding, the figures, the argument in two columns, what
        we ask, the sources."""
        T = self.T
        c = SC.Canvas(self.ty, PW, PH, T.paper)
        M = 48.0
        y = self.p_mast(c, p, M)
        y = self.p_lead(c, p, M, y + 16)
        y = self.p_figures(c, p, M, y + 22)
        y = self.p_columns(c, p, M, y + 22, PH - (150 if self.next_is_ask(p.get("next")) else 112))
        self.p_ask(c, p, M)
        self.p_foot(c, p, M)
        return c.done(kind="page")

    def p_mast(self, c, p, M):
        T = self.T
        c.rect(0, 0, PW, 6, T.accent)
        self.label(c, p.get("org") or p.get("date") or "", M, 26, 300, color=T.head, size=9.5)
        if p.get("org"):
            self.label(c, p.get("date") or "", PW - M - 220, 26, 220, color=T.muted, size=9.5, align="right")
        c.rect(M, 44, PW - 2 * M, 1, T.hair)
        el = c.text(p["title"], M, 58, PW - 2 * M, 80, face="heading", size=30, min_size=22, lead=1.08, color=T.head,
                    upper=self.upper_head, role="title")
        return el["bottom"]

    def p_lead(self, c, p, M, y):
        T = self.T
        if p.get("dek"):
            y = c.text(p["dek"], M, y, PW - 2 * M - 40, 70, size=13.5, min_size=11.5, lead=1.38, color=T.ink, marks=p.get("dek_marks", ""))["bottom"]
        return y

    def p_figures(self, c, p, M, y):
        """The stat and the figures from the points, set as a row of numbers over hairlines."""
        T = self.T
        figs = []
        if p.get("stat"):
            figs.append((p["stat"]["value"], p["stat"]["label"], p["stat"].get("marks", ""), True))
        for it in p.get("figures") or []:
            figs.append((it[0], it[1], it[2], False))
        figs = figs[:4]
        if not figs:
            return y
        n = len(figs)
        gap = 18.0
        fw = (PW - 2 * M - gap * (n - 1)) / n
        bottom = y
        for i, (v, lab, marks, lead) in enumerate(figs):
            x = M + i * (fw + gap)
            c.rect(x, y, fw, 3 if lead else 1, T.accent if lead else T.ink)
            vv = c.text(v, x, y + 10, fw, 46, face="heading", size=40 if lead else 32, min_size=20, lead=1.0,
                        color=T.accent if lead else T.head, max_lines=1)
            el = c.text(lab, x, vv["bottom"] + 6, fw, 60, size=10, min_size=8.5, lead=1.32, color=T.ink, marks=marks)
            bottom = max(bottom, el["bottom"])
        return bottom

    def p_columns(self, c, p, M, y, bottom):
        """The argument in two columns. With a chart, the sections run down the left and the chart and the quote hold
        the right; without one, the sections flow across both. The text is set as large as the space allows."""
        T = self.T
        secs = p.get("sections") or []
        chart = p.get("chart") if (p.get("chart") or {}).get("bars") else None
        gap = 24.0
        cw = (PW - 2 * M - gap) / 2
        c.rect(M, y, PW - 2 * M, 1, T.hair)
        y += 14
        avail = bottom - 14 - y

        def col_h(items, size):
            return sum(c.measure(sc.get("heading", ""), "body_bold", size + 1, cw, 1.25) + 3 +
                       c.measure(sc.get("body", "") + " 1", "body", size, cw, 1.42) + 14 for sc in items)

        if chart:
            left, right = secs, []
        else:
            half = (len(secs) + 1) // 2
            left, right = secs[:half], secs[half:]
        q = p.get("quote")
        size = 12.5
        while size > 9:
            rh = col_h(right, size) + ((c.measure(q["text"], "body_italic", size + 1.5, cw - 12, 1.35) + 30) if q else 0)
            if col_h(left, size) <= avail and (chart or rh <= avail):
                break
            size -= 0.25
        # the right column ends where the left one does: the chart takes the room the quote leaves it
        left_end = min(bottom, y + col_h(left, size)) if chart else bottom
        cy = [y, y]
        for ci, items in ((0, left), (1, right)):
            x = M + ci * (cw + gap)
            for sec in items:
                el = c.text(sec.get("heading", ""), x, cy[ci], cw, 30, face="body_bold", size=size + 1, lead=1.25, color=T.head, max_lines=2)
                el = c.text(sec.get("body", ""), x, el["bottom"] + 3, cw, max(30.0, bottom - el["bottom"] - 3), size=size, min_size=9,
                            lead=1.42, color=T.ink, marks=sec.get("marks", ""))
                cy[ci] = el["bottom"] + 14
        x = M + cw + gap
        if chart:
            if chart.get("title"):
                el = c.text(chart["title"], x, cy[1], cw, 30, face="body_bold", size=size + 1, lead=1.25, color=T.head, max_lines=2)
                cy[1] = el["bottom"] + 2
            if chart.get("unit"):
                el = c.text(chart["unit"], x, cy[1], cw, 14, size=8.5, color=T.muted, max_lines=1)
                cy[1] = el["bottom"] + 4
            qh = (c.measure(f"“{q['text']}”", "body_italic", size + 1.5, cw - 12, 1.35) + (16 if q.get("who") else 0) + 22) if q else 0
            ch = max(110.0, min(bottom - cy[1] - qh - 18, max(170.0, left_end - cy[1] - qh - 18)))
            self.page_chart(c, chart, x, cy[1], cw, ch)
            cy[1] += ch + 18
        if q:
            qy = cy[1]
            c.rect(x, qy + 3, 2, size, T.accent)
            el = c.text(f"“{q['text']}”", x + 12, qy, cw - 12, 90, face="body_italic", size=size + 1.5, min_size=10, lead=1.35, color=T.head,
                        marks=q.get("marks", ""))
            if q.get("who"):
                el = c.text(q["who"], x + 12, el["bottom"] + 4, cw - 12, 16, face="label", size=8, color=T.muted, upper=True, track=0.08,
                            max_lines=1)
            cy[1] = el["bottom"]
        return max(cy)

    def page_chart(self, c, chart, x, y, w, h):
        """The page's chart: columns that stand the height of the column when there is room for them (a few bars),
        else thin labeled bars."""
        bars = chart["bars"]
        if h >= 140 and len(bars) <= 4:
            return self.columns(c, bars, x, y + 4, w, h - 4, hi=chart.get("hi"), vsize=22.0, lsize=9.5, value_face="heading",
                                colw_max=w * 0.34, gap_ratio=0.32, base_w=1.0)
        return self.hbars(c, bars, x, y, w, h, hi=chart.get("hi"), size=9.5, vsize=11, max_bar=16, label_w=w * 0.4)

    ASK_WORDS = re.compile(r"\b(approv|fund|give|gift|support|invest|join|donat|sponsor|commit|pledg|grant|contribut|ask|request|"
                           r"consider|adopt|renew|match|underwrit)\w*|[$£€]\s?\d", re.I)

    @classmethod
    def next_is_ask(cls, text) -> bool:
        """True when the line asks the reader for something; False for a line that only names when something happens
        ("The board will vote on the FY2027 budget at its October 21 meeting"), which is set as a date line."""
        return bool(text) and bool(cls.ASK_WORDS.search(text))

    def p_ask(self, c, p, M):
        T = self.T
        if not p.get("next"):
            return
        if not self.next_is_ask(p["next"]):
            # a date, not an ask: one quiet line over the sources, no ask band
            y = PH - 100
            c.rect(M, y + 4, 24, 3, T.accent)
            c.text(p["next"], M + 34, y, PW - 2 * M - 34, 16, face="body_bold", size=11, min_size=9.5, lead=1.25, color=T.head,
                   max_lines=1)
            return
        y = PH - 142
        c.rect(M, y, PW - 2 * M, 54, T.field)
        c.text("What we ask", M + 14, y + 10, 120, 16, face="label", size=8.5, color=T.field_accent, upper=True, track=0.1, max_lines=1)
        c.text(p["next"], M + 14, y + 25, PW - 2 * M - 28, 26, face="body_bold", size=12, min_size=10, lead=1.25, color=T.field_text, max_lines=2)

    def p_foot(self, c, p, M):
        T = self.T
        y = PH - 74
        c.rect(M, y, PW - 2 * M, 1, T.hair)
        rows = p.get("sources") or []
        yy = y + 8
        for i, r in enumerate(rows[:3]):
            el = c.text(f"{i + 1}. {r}", M, yy, PW - 2 * M - 90, 12, size=7.5, lead=1.3, color=T.muted, max_lines=1)
            yy = el["bottom"] + 1
        c.logo(PW - M, y + 8, 22, "paper", align="right", max_w=90)


# ---------------------------------------------------------------- broadsheet --

class Broadsheet(System):
    """The data desk: tab and heavy rule over a bold short headline, an italic standfirst, gridded bars."""
    name = "broadsheet"
    T_LEAD = 1.04
    SUB_FACE = "body_italic"
    T_SIZE, T_MIN = 44.0, 34.0
    grid_lines = True

    def top(self, c, s, color=None, hair=None):
        T = self.T
        c.rect(self.M, 34, W - 2 * self.M, 2.5, T.ink)
        c.rect(self.M, 34, 56, 8, T.accent)
        return 44

    def title_area(self, c, s, y, w=None, x=None, size=None, color=None, sub_color=None):
        x = self.M if x is None else x
        w = w or self.span(0, 11)
        el = self.head(c, s.get("head", ""), x, y, w, (size or self.T_SIZE) * self.T_LEAD * 2 + 2, size=size, color=color)
        y = el["bottom"]
        if s.get("subhead"):
            y = c.text(s["subhead"], x, y + 8, w, self.SUB * 1.3 * 2, face="body_italic", size=24, min_size=18, lead=1.28,
                       color=sub_color or self.T.muted, marks=s.get("sub_marks", ""))["bottom"]
        return y

    def foot(self, c, spec, color=None, rule=True, hair=None):
        T = self.T
        y = H - 34
        src = self.src(c, spec, "Source: ", W - 2 * self.M - 90, self.SRC)
        if src:
            c.text(src, self.M, y, W - 2 * self.M - 90, self.SRC * 1.4, face="body", size=self.SRC, lead=1.3, color=T.muted, max_lines=1)
        if self.show_numbers and spec.get("num", 1) > 1:
            c.text(str(spec["num"]), W - self.M - 60, y, 60, self.SRC * 1.4, face="label", size=self.SRC, lead=1.3, color=T.ink, align="right")

    def exhibit_chart(self, c, s, x, y, w, h):
        T = self.T
        if s.get("unit"):
            self.label(c, s["unit"], x, y, w, color=T.ink, size=14, upper=False, face="label")
            y += 26
            h -= 26
        return self.bars(c, s["bars"], x, y, w, h, highlight=s.get("hi"), growth=self.growth_of(s), grid=True, value_face="label",
                         max_bar=min(64.0, max(40.0, h / max(1, len(s["bars"])) * 0.45)), label_face="label", size=21, vsize=24)

    def s_title(self, s):
        T = self.T
        c = self.canvas()
        c.rect(self.M, 56, W - 2 * self.M, 3, T.ink)
        c.rect(self.M, 56, 56, 8, T.accent)
        self.label(c, s.get("org") or "", self.M, 82, self.span(0, 6), color=T.ink, size=13)
        self.label(c, s.get("date") or "", self.col(6), 82, self.span(6, 12), color=T.muted, size=13, align="right")
        fig = bool(s.get("fig"))
        el = self.head(c, s["title"], self.M, 140, self.span(0, 7 if fig else 11), 230, size=64 if fig else 72, min_size=42, lead=1.0,
                       anchor="bottom")
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 20, self.span(0, 7 if fig else 9), 90, face="body_italic", size=28, min_size=21,
                   lead=1.28, color=T.muted)
        if fig:
            c.rect(self.col(8) - 4, 140, self.span(8, 12) + 4, 2.5, T.ink)
            c.rect(self.col(8) - 4, 140, 40, 8, T.accent)
            self.cover_fig(c, s, self.col(8) - 4, 160, self.span(8, 12) + 4, H - 80 - 160, T.head, T.ink, T.hair, align="left", size=170)
        c.rect(self.M, H - 60, W - 2 * self.M, 1, T.hair)
        c.logo(W - self.M, H - 50, 28, "paper", align="right")
        return c.done()

    def s_section(self, s):
        T = self.T
        c = self.canvas(T.accent)
        on = T.on_accent
        c.rect(self.M, 56, W - 2 * self.M, 2.5, on)
        self.label(c, f"Part {NUMBERS.get(s.get('n') or 1, s.get('n') or 1)}", self.M, 74, 400, color=on, size=15)
        el = self.head(c, s["head"], self.M, 150, self.span(0, 10), 190, size=60, min_size=40, color=on, lead=1.02, anchor="bottom")
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 18, self.span(0, 9), 90, face="body_italic", size=26, min_size=20, lead=1.3, color=on,
                   marks=s.get("marks", ""))
        return c.done(dark=True)

    def s_content(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 62, size=40)
        self.rows(c, s.get("items") or [], self.M, y + 30, self.span(0, 11), H - 64 - (y + 30), size=28, min_size=19, ncolor=T.accent_text)
        self.foot(c, s)
        return c.done()

    def s_stat(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        v = c.text(s["value"], self.M - 6, 64, self.span(0, 12), 230, face="heading", size=230, min_size=100, lead=1.0, color=T.head,
                   max_lines=1)
        c.rect(self.M, v["bottom"] + 8, 120, 8, T.accent)
        el = c.text(s.get("label", ""), self.M, v["bottom"] + 30, self.span(0, 6), 110, face="label", size=26, min_size=20, lead=1.2,
                    color=T.ink, marks=s.get("marks", ""))
        if s.get("context"):
            c.text(s["context"], self.col(6), v["bottom"] + 32, self.span(6, 12), 120, face="body_italic", size=20, min_size=16, lead=1.4,
                   color=T.muted)
        self.foot(c, s)
        return c.done()

    def s_quote(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        qh = c.measure(s["quote"], "body_italic", 40, self.span(1, 11), 1.2)
        top = max(110.0, (H - qh) / 2 - 20)
        c.text("“", self.M - 4, top - 34, 90, 120, face="heading", size=120, lead=1.0, color=T.accent, max_lines=1)
        el = c.text(s["quote"].rstrip(",;: ") + "”", self.col(1), top, self.span(1, 11), 270, face="body_italic", size=40, min_size=26, lead=1.2, color=T.head,
                    marks=s.get("marks", ""))
        if s.get("who"):
            c.text(s["who"], self.col(1), el["bottom"] + 20, self.span(1, 11), 30, face="label", size=17, color=T.ink, max_lines=1)
        self.foot(c, s)
        return c.done()

    def s_comparison(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 62, size=40) + 30
        cols = s.get("cols") or []
        xs, ws = [self.col(0), self.col(6)], [self.span(0, 6), self.span(6, 12)]
        for i, (label, items) in enumerate(cols[:2]):
            c.rect(xs[i], y, ws[i], 2, T.ink)
            c.rect(xs[i], y, 40, 6, T.accent if i == 1 else T.ink)
            self.label(c, label, xs[i], y + 14, ws[i], color=T.accent_text if i == 1 else T.head, size=15, upper=False)
        self.paired(c, cols, xs, ws, y + 46, H - 64 - (y + 46), size=22)
        self.foot(c, s)
        return c.done()

    def s_timeline(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 62, size=40) + 26
        steps = s.get("steps") or []
        rh = (H - 64 - y) / max(1, len(steps))
        for i, (when, text, marks) in enumerate(steps):
            yy = y + i * rh
            last = i == len(steps) - 1
            c.rect(self.M, yy, W - 2 * self.M, 1, T.hair)
            c.text(when, self.M, yy + 10, self.span(0, 3), rh - 10, face="label", size=18, min_size=14, color=T.accent_text if last else T.ink,
                   max_lines=2)
            c.text(text, self.col(3), yy + 8, self.span(3, 12), rh - 10, size=20, min_size=15, color=T.ink, marks=marks, lead=1.3)
        self.foot(c, s)
        return c.done()

    def s_closing(self, s):
        T = self.T
        c = self.canvas()
        c.rect(self.M, 56, W - 2 * self.M, 3, T.ink)
        c.rect(self.M, 56, 56, 8, T.accent)
        y = 130
        amt = bool(s.get("amount"))
        cw = self.span(0, 7) if amt else self.span(0, 9)
        if s.get("head"):
            y = self.head(c, s["head"], self.M, y, self.span(0, 7) if amt else self.span(0, 10), 150, size=52, min_size=34)["bottom"] + 20
        if s.get("text"):
            y = c.text(s["text"], self.M, y, cw, 140, face="body_italic", size=26, min_size=20, lead=1.3, color=T.muted,
                       marks="" if amt else s.get("marks", ""))["bottom"] + 26
        if s.get("cta"):
            c.text(s["cta"], self.M, y, cw, 70, face="label", size=22, min_size=17, lead=1.25, color=T.accent_text, max_lines=2)
        if amt:
            c.rect(self.col(8) - 4, 130, self.span(8, 12) + 4, 2.5, T.ink)
            self.ask_amount(c, s, self.col(8) - 4, 150, self.span(8, 12) + 4, H - 110 - 150, T.head, T.ink, hair=T.accent)
        req = s.get("required") or []
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 58 - 18 * (len(req[:2]) - 1 - i), self.span(0, 9), 18, size=12, color=T.muted, max_lines=1)
        c.logo(W - self.M, H - 62, 28, "paper", align="right")
        return c.done()

    def g_head(self, c, g, M):
        T = self.T
        c.rect(M, 84, GW - 2 * M, 4, T.ink)
        c.rect(M, 84, 64, 10, T.accent)
        if g.get("kicker"):
            c.text(g["kicker"], M, 116, 800, 30, face="label", size=22, color=T.ink, max_lines=1)
        el = c.text(g["headline"], M, 158, GW - 2 * M, 250, face="heading", size=74, min_size=48, lead=1.02, color=T.head, role="title")
        y = el["bottom"] + 22
        if g.get("dek"):
            y = c.text(g["dek"], M, y, GW - 2 * M - 60, 130, face="body_italic", size=32, min_size=24, lead=1.3, color=T.muted,
                       marks=g.get("dek_marks", ""))["bottom"]
        return y

    def g_bars(self, c, g, M, y, h):
        T = self.T
        if g.get("unit"):
            c.text(g["unit"], M, y, 800, 30, face="label", size=22, color=T.ink, max_lines=1)
            y += 44
            h -= 44
        self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="hbars", size=26, vsize=30, grid=True, max_bar=76,
                  label_face="label")

    def p_mast(self, c, p, M):
        T = self.T
        c.rect(M, 30, PW - 2 * M, 2, T.ink)
        c.rect(M, 30, 60, 7, T.accent)
        self.label(c, p.get("org") or "", M, 42, 300, color=T.ink, size=9.5, upper=False)
        self.label(c, p.get("date") or "", PW - M - 220, 42, 220, color=T.muted, size=9.5, align="right", upper=False, face="body")
        el = c.text(p["title"], M, 66, PW - 2 * M, 80, face="heading", size=30, min_size=22, lead=1.04, color=T.head, role="title")
        return el["bottom"]

    def p_lead(self, c, p, M, y):
        T = self.T
        if p.get("dek"):
            y = c.text(p["dek"], M, y, PW - 2 * M - 30, 70, face="body_italic", size=14, min_size=11.5, lead=1.36, color=T.muted,
                       marks=p.get("dek_marks", ""))["bottom"]
        return y


# ---------------------------------------------------------------- stage --

class Stage(System):
    """The keynote: dark ground, one idea a slide, very large type, columns drawn tall."""
    name = "stage"
    draws_fig = False
    M = 64.0
    T_SIZE, T_MIN = 48.0, 38.0
    LABEL, VALUE = 22.0, 30.0
    chart = "hbars"

    def top(self, c, s, color=None, hair=None):
        return 40

    def foot(self, c, spec, color=None, rule=False, hair=None):
        col = color or self.T.muted
        src = self.src(c, spec, "", W - 2 * self.M - 80, self.SRC)
        if src:
            c.text(src, self.M, H - 38, W - 2 * self.M - 80, 20, size=self.SRC, color=col, max_lines=1)
        if self.show_numbers and spec.get("num", 1) > 1:
            c.text(str(spec["num"]), W - self.M - 60, H - 38, 60, 20, face="label", size=self.SRC, color=col, align="right")

    def s_title(self, s):
        T = self.T
        c = self.canvas()
        c.rect(self.M, 48, W - 2 * self.M, 1, T.hair)
        c.rect(self.M, 48, 64, 5, T.accent)
        el = self.head(c, s["title"], self.M - 4, 80, self.span(0, 12), 300, size=92, min_size=52, lead=0.96, anchor="bottom")
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 24, self.span(0, 9), 70, size=26, min_size=20, lead=1.3, color=T.muted)
        meta = "   ".join(x for x in (s.get("org"), s.get("date")) if x)
        if meta:
            self.label(c, meta, self.M, H - 58, self.span(0, 8), color=T.accent_text, size=13, track=0.14)
        c.logo(W - self.M, H - 64, 28, "paper", align="right")
        return c.done(dark=True)

    def s_section(self, s):
        T = self.T
        c = self.canvas()
        n = s.get("n") or 1
        c.text(f"{n:02d}", self.M - 6, 70, 400, 220, face="heading", size=200, lead=1.0, color=T.accent, max_lines=1)
        el = self.head(c, s["head"], self.M, 290, self.span(0, 11), 140, size=56, min_size=38, lead=1.02)
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 16, self.span(0, 9), 70, size=24, min_size=19, lead=1.3, color=T.muted, marks=s.get("marks", ""))
        return c.done(dark=True)

    def s_content(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 68, size=46)
        self.bullets(c, s.get("items") or [], self.M, y + 40, self.span(0, 10), H - 70 - (y + 40), size=30, min_size=21, marker="dash",
                     gap=0.8, mcolor=T.accent)
        self.foot(c, s)
        return c.done(dark=True)

    def s_stat(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        v = c.text(s["value"], self.M - 10, 60, W - 2 * self.M + 10, 300, face="heading", size=300, min_size=120, lead=1.0, color=T.accent,
                   max_lines=1, anchor="middle")
        el = c.text(s.get("label", ""), self.M, v["bottom"] + 6, self.span(0, 7), 100, face="body_bold", size=30, min_size=22, lead=1.2,
                    color=T.head, marks=s.get("marks", ""))
        if s.get("context"):
            c.text(s["context"], self.col(7), v["bottom"] + 10, self.span(7, 12), 120, size=19, min_size=15, lead=1.4, color=T.muted)
        self.foot(c, s)
        return c.done(dark=True)

    def s_quote(self, s):
        T = self.T
        c = self.canvas()
        qh = c.measure(f"“{s['quote'].rstrip(',;: ')}”", "heading", 48, self.span(0, 11), 1.12)
        top = max(70.0, (H - qh - 60) / 2)
        el = c.text(f"“{s['quote'].rstrip(',;: ')}”", self.M, top, self.span(0, 11), 330, face="heading", size=48, min_size=30, lead=1.12, color=T.head,
                    marks=s.get("marks", ""))
        if s.get("who"):
            self.label(c, s["who"], self.M, el["bottom"] + 26, self.span(0, 10), color=T.accent_text, size=15, track=0.12)
        self.foot(c, s)
        return c.done(dark=True)

    def s_comparison(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 68, size=42) + 34
        cols = s.get("cols") or []
        xs, ws = [self.col(0), self.col(6)], [self.span(0, 6), self.span(6, 12)]
        for i, (label, items) in enumerate(cols[:2]):
            self.label(c, label, xs[i], y, ws[i], color=T.accent_text if i == 1 else T.muted, size=15)
            c.rect(xs[i], y + 28, ws[i], 2, T.accent if i == 1 else T.muted)
        self.paired(c, cols, xs, ws, y + 30, H - 70 - (y + 30), size=24, colors=(T.ink, T.ink))
        self.foot(c, s)
        return c.done(dark=True)

    def exhibit_chart(self, c, s, x, y, w, h):
        T = self.T
        if s.get("unit"):
            self.label(c, s["unit"], x, y, w, color=T.muted, size=13)
            y += 26
            h -= 26
        return self.bars(c, s["bars"], x, y, w, h, highlight=s.get("hi"), growth=self.growth_of(s), form="hbars", max_bar=54, value_face="label", vsize=26, axis=T.hair)

    def s_exhibit(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.exhibit_head(c, s, 66, w=W - 2 * self.M)
        nh = self.note(c, s, self.M, H - 50, W - 2 * self.M)
        self.exhibit_chart(c, s, self.M, y + 26, W - 2 * self.M, H - 54 - nh - (y + 26))
        self.foot(c, s)
        return c.done(dark=True)

    def s_timeline(self, s):
        sc = super().s_timeline(s)
        sc["dark"] = True
        return sc

    def s_statement(self, s):
        T = self.T
        c = self.canvas()
        hh = c.measure(s.get("head", ""), "heading", 60, self.span(0, 11), 1.04)
        top = max(90.0, (H - hh) / 2 - 30)
        el = self.head(c, s.get("head", ""), self.M, top, self.span(0, 11), hh + 4, size=60, min_size=38, lead=1.04)
        if s.get("caption"):
            c.text(s["caption"], self.M, el["bottom"] + 22, self.span(0, 9), 120, size=24, min_size=18, lead=1.35, color=T.muted,
                   marks=s.get("marks", ""))
        return c.done(dark=True)

    def s_closing(self, s):
        T = self.T
        c = self.canvas()
        hh = c.measure(s.get("head", ""), "heading", 60, self.span(0, 11), 1.04) if s.get("head") else 0
        y = max(80.0, (H - hh - 160) / 2)
        if s.get("head"):
            y = self.head(c, s["head"], self.M, y, self.span(0, 11), hh + 4, size=60, min_size=38, lead=1.04)["bottom"] + 22
        if s.get("text"):
            y = c.text(s["text"], self.M, y, self.span(0, 9), 120, size=24, min_size=18, lead=1.35, color=T.muted, marks=s.get("marks", ""))["bottom"] + 24
        if s.get("cta"):
            c.text(s["cta"], self.M, y, self.span(0, 10), 70, face="label", size=20, min_size=15, lead=1.3, color=T.accent_text, upper=True,
                   track=0.08, max_lines=2)
        req = s.get("required") or []
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 58 - 18 * (len(req[:2]) - 1 - i), self.span(0, 9), 18, size=12, color=T.muted, max_lines=1)
        c.logo(W - self.M, H - 62, 28, "paper", align="right")
        return c.done(dark=True)

    def s_sources(self, s):
        sc = super().s_sources(s)
        sc["dark"] = True
        return sc

    def g_head(self, c, g, M):
        T = self.T
        if g.get("kicker"):
            c.text(g["kicker"], M, 96, 800, 30, face="label", size=22, color=T.accent_text, upper=True, track=0.12, max_lines=1)
        el = c.text(g["headline"], M, 140, GW - 2 * M, 300, face="heading", size=84, min_size=54, lead=1.0, color=T.head, role="title")
        y = el["bottom"] + 24
        if g.get("dek"):
            y = c.text(g["dek"], M, y, GW - 2 * M - 60, 130, size=30, min_size=24, lead=1.32, color=T.muted, marks=g.get("dek_marks", ""))["bottom"]
        return y

    def g_bars(self, c, g, M, y, h):
        T = self.T
        if len(g["bars"]) <= 4:
            self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="columns", vsize=80, lsize=26, colw_max=240, base=T.hair,
                      gap_ratio=0.4)
        else:
            self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="hbars", size=26, vsize=30, max_bar=70)

    def p_mast(self, c, p, M):
        T = self.T
        c.rect(M, 34, 40, 4, T.accent)
        self.label(c, p.get("org") or "", M, 46, 300, color=T.accent_text, size=9.5)
        self.label(c, p.get("date") or "", PW - M - 220, 46, 220, color=T.muted, size=9.5, align="right")
        el = c.text(p["title"], M, 70, PW - 2 * M, 90, face="heading", size=34, min_size=24, lead=1.02, color=T.head, role="title")
        return el["bottom"]


# ---------------------------------------------------------------- folio --

class Folio(System):
    """The book: a running head over a hairline, flush-left text pages in a display serif, figures in the text face,
    centered openers and epigraphs, the folio at the outer corner."""
    name = "folio"
    draws_fig = False
    M = 72.0
    T_SIZE, T_MIN, T_LEAD = 46.0, 34.0, 1.08
    LABEL, VALUE = 20.0, 24.0

    def top(self, c, s, color=None, hair=None):
        T = self.T
        if s.get("section"):
            self.label(c, s["section"], self.M, 30, self.span(0, 9), color=T.muted, size=13, track=0.14)
        c.rect(self.M, 50, W - 2 * self.M, 1, T.hair)
        return 50

    def foot(self, c, spec, color=None, rule=False, hair=None):
        T = self.T
        src = self.src(c, spec, "", W - 2 * self.M - 120, self.SRC + 1, face="body_italic")
        if src:
            c.text(src, self.M, H - 38, W - 2 * self.M - 100, 20, face="body_italic", size=self.SRC + 1, color=T.muted, max_lines=1)
        if self.show_numbers and spec.get("num", 1) > 1:
            c.text(str(spec["num"]), W - self.M - 60, H - 38, 60, 20, face="body", size=15, color=T.ink, align="right")

    def title_area(self, c, s, y, w=None, x=None, size=None, color=None, sub_color=None):
        T = self.T
        w = w or self.span(0, 10)
        x = self.M if x is None else x
        el = self.head(c, s.get("head", ""), x, y, w, (size or self.T_SIZE) * self.T_LEAD * 2 + 2, size=size, color=color)
        y = el["bottom"]
        if s.get("subhead"):
            y = c.text(s["subhead"], x, y + 8, w, 64, face="body_italic", size=26, min_size=19, lead=1.28, color=sub_color or T.muted,
                       marks=s.get("sub_marks", ""))["bottom"]
        return y

    def s_title(self, s):
        T = self.T
        c = self.canvas()
        self.label(c, s.get("org") or "", self.M, 30, self.span(0, 8), color=T.muted, size=13, track=0.16)
        self.label(c, s.get("date") or "", self.col(8), 30, self.span(8, 12), color=T.muted, size=11.5, track=0.2, align="right")
        c.rect(self.M, 50, W - 2 * self.M, 1, T.hair)
        sub_h = c.measure(s.get("sub", ""), "body_italic", 28, self.span(0, 9), 1.3) + 26 if s.get("sub") else 0
        th = c.measure(s["title"], "heading", 84, self.span(0, 11), 1.0)
        top = max(90.0, H - 70 - th - sub_h - 20)
        el = self.head(c, s["title"], self.M - 4, top, self.span(0, 11), th + 4, size=84, min_size=52, lead=1.0)
        if s.get("sub"):
            c.text(s["sub"], self.M, el["bottom"] + 22, self.span(0, 9), 80, face="body_italic", size=28, min_size=21, lead=1.3, color=T.ink)
        c.rect(self.M, H - 50, W - 2 * self.M, 1, T.hair)
        c.logo(W - self.M, H - 42, 24, "paper", align="right", max_w=90)
        return c.done()

    def s_section(self, s):
        T = self.T
        c = self.canvas()
        n = s.get("n") or 1
        self.label(c, f"Part {NUMBERS.get(n, n)}", self.M, 150, W - 2 * self.M, color=T.accent_text, size=14, align="center", track=0.24)
        el = self.head(c, s["head"], self.col(1), 190, self.span(1, 11), 160, size=52, min_size=36, lead=1.08, align="center")
        c.rect(W / 2 - 20, el["bottom"] + 20, 40, 1, T.accent)
        if s.get("sub"):
            c.text(s["sub"], self.col(2), el["bottom"] + 38, self.span(2, 10), 80, face="body_italic", size=24, min_size=19, lead=1.3,
                   color=T.muted, align="center", marks=s.get("marks", ""))
        return c.done()

    def s_content(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        el = self.head(c, s.get("head", ""), self.M, 80, self.span(0, 5), 300, size=40, min_size=28, lead=1.1)
        c.rect(self.M, el["bottom"] + 18, 40, 1, T.accent)
        self.rows(c, s.get("items") or [], self.col(5) + 10, 82, self.span(5, 12) - 10, H - 70 - 82, size=24, min_size=16, numbered=True,
                  ncolor=T.accent_text)
        self.foot(c, s)
        return c.done()

    def s_stat_centered(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        v = c.text(s["value"], self.M, 70, W - 2 * self.M, 230, face="heading", size=200, min_size=96, lead=1.0, color=T.accent,
                   max_lines=1, align="center")
        c.rect(W / 2 - 20, v["bottom"] + 10, 40, 1, T.hair)
        el = c.text(s.get("label", ""), self.col(2), v["bottom"] + 26, self.span(2, 10), 80, face="body", size=28, min_size=21, lead=1.25,
                    color=T.head, align="center", marks=s.get("marks", ""))
        if s.get("context"):
            c.text(s["context"], self.col(2), el["bottom"] + 10, self.span(2, 10), 70, face="body_italic", size=19, min_size=15, lead=1.4,
                   color=T.muted, align="center")
        self.foot(c, s)
        return c.done()

    def s_quote(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        qh = c.measure(f"“{s['quote'].rstrip(',;: ')}”", "body_italic", 38, self.span(1, 11), 1.3)
        top = max(90.0, (H - qh - 60) / 2)
        el = c.text(f"“{s['quote'].rstrip(',;: ')}”", self.col(1), top, self.span(1, 11), 280, face="body_italic", size=38, min_size=26, lead=1.3,
                    color=T.head, align="center", marks=s.get("marks", ""))
        if s.get("who"):
            self.label(c, s["who"], self.M, el["bottom"] + 24, W - 2 * self.M, color=T.accent_text, size=13, align="center", track=0.18)
        self.foot(c, s)
        return c.done()

    def s_comparison(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 70, size=40) + 30
        cols = s.get("cols") or []
        xs, ws = [self.col(0), self.col(6)], [self.span(0, 6), self.span(6, 12)]
        for i, (label, items) in enumerate(cols[:2]):
            self.label(c, label, xs[i], y, ws[i], color=T.accent_text if i == 1 else T.muted, size=13, track=0.16)
        self.paired(c, cols, xs, ws, y + 30, H - 64 - (y + 30), size=22, colors=(T.ink, T.ink))
        self.foot(c, s)
        return c.done()

    def s_comparison_old(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        y = self.title_area(c, s, 74, size=38) + 30
        for i, (label, items) in enumerate(s.get("cols") or []):
            a, b = (0, 6) if i == 0 else (6, 12)
            x, w = self.col(a) + (0 if i == 0 else 10), self.span(a, b) - 10
            self.label(c, label, x, y, w, color=T.accent_text if i == 1 else T.muted, size=13, track=0.16)
            self.rows(c, items, x, y + 30, w, H - 80 - (y + 30), size=20, min_size=15, numbered=False)
        c.rect(W / 2, y, 1, H - 90 - y, T.hair)
        self.foot(c, s)
        return c.done()

    def exhibit_chart(self, c, s, x, y, w, h):
        T = self.T
        if s.get("unit"):
            self.label(c, s["unit"], x, y, w, color=T.muted, size=12, track=0.16)
            y += 28
            h -= 28
        return self.bars(c, s["bars"], x, y, w, h, highlight=s.get("hi"), growth=self.growth_of(s), value_face="body", max_bar=40, size=24, vsize=28)

    def s_exhibit(self, s):
        c = self.canvas()
        self.top(c, s)
        y = self.exhibit_head(c, s, 70)
        nh = self.note(c, s, self.M, H - 50, W - 2 * self.M, face="body_italic")
        self.exhibit_chart(c, s, self.M, y + 28, W - 2 * self.M, H - 60 - nh - (y + 28))
        self.foot(c, s)
        return c.done()

    def s_closing(self, s):
        T = self.T
        c = self.canvas()
        c.rect(self.M, 54, W - 2 * self.M, 1, T.hair)
        c.rect(self.M, H - 54, W - 2 * self.M, 1, T.hair)
        hh = c.measure(s.get("head", ""), "heading", 50, self.span(1, 11), 1.08) if s.get("head") else 0
        y = max(90.0, (H - hh - 150) / 2)
        if s.get("head"):
            y = self.head(c, s["head"], self.col(1), y, self.span(1, 11), hh + 4, size=50, min_size=34, align="center")["bottom"] + 20
        if s.get("text"):
            y = c.text(s["text"], self.col(2), y, self.span(2, 10), 120, face="body_italic", size=24, min_size=18, lead=1.35, color=T.muted,
                       align="center", marks=s.get("marks", ""))["bottom"] + 22
        if s.get("cta"):
            self.label(c, s["cta"], self.col(1), y, self.span(1, 11), color=T.accent_text, size=14, align="center", track=0.14)
        req = s.get("required") or []
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 92 - 18 * (len(req[:2]) - 1 - i), W - 2 * self.M, 18, size=12, color=T.muted, max_lines=1, align="center")
        return c.done()

    def g_head(self, c, g, M):
        T = self.T
        c.rect(M, 84, GW - 2 * M, 1, T.hair)
        if g.get("kicker"):
            c.text(g["kicker"], M, 104, GW - 2 * M, 30, face="label", size=18, color=T.accent_text, upper=True, track=0.22, align="center",
                   max_lines=1)
        el = c.text(g["headline"], M + 30, 156, GW - 2 * M - 60, 250, face="heading", size=74, min_size=48, lead=1.08, color=T.head,
                    align="center", role="title")
        y = el["bottom"] + 22
        if g.get("dek"):
            y = c.text(g["dek"], M + 60, y, GW - 2 * M - 120, 130, face="body_italic", size=30, min_size=24, lead=1.35, color=T.muted,
                       align="center", marks=g.get("dek_marks", ""))["bottom"]
        return y

    def g_bars(self, c, g, M, y, h):
        if g.get("unit"):
            c.text(g["unit"], M, y, GW - 2 * M, 30, face="label", size=18, color=self.T.muted, upper=True, track=0.18, align="center", max_lines=1)
            y += 46
            h -= 46
        self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), form="hbars", size=28, vsize=34, max_bar=64, value_face="body")

    def p_mast(self, c, p, M):
        T = self.T
        self.label(c, p.get("org") or "", M, 30, PW - 2 * M, color=T.muted, size=8.5, align="center", track=0.22)
        c.rect(M, 48, PW - 2 * M, 1, T.hair)
        el = c.text(p["title"], M + 20, 64, PW - 2 * M - 40, 80, face="heading", size=30, min_size=22, lead=1.1, color=T.head,
                    align="center", role="title")
        return el["bottom"]

    def p_lead(self, c, p, M, y):
        T = self.T
        if p.get("dek"):
            y = c.text(p["dek"], M + 30, y, PW - 2 * M - 60, 70, face="body_italic", size=13.5, min_size=11.5, lead=1.38, color=T.ink,
                       align="center", marks=p.get("dek_marks", ""))["bottom"]
        return y


# ---------------------------------------------------------------- grid --

class Grid(System):
    """The modernist poster: a heavy rule at the head, condensed figures as structure, one color in whole fields."""
    name = "grid"
    M = 48.0
    GUT = 20.0
    T_SIZE, T_MIN, T_LEAD = 46.0, 34.0, 1.02
    chart = "columns"

    def top(self, c, s, color=None, hair=None):
        T = self.T
        c.rect(self.M, 36, W - 2 * self.M, 4, color or T.ink)
        return 40

    def foot(self, c, spec, color=None, rule=True, hair=None):
        T = self.T
        col = color or T.ink
        y = H - 32
        c.rect(self.M, y - 10, W - 2 * self.M, 1.5, col)
        if self.show_numbers and spec.get("num", 1) > 1:
            c.text(f"{spec['num']:02d}", self.M, y, 60, 20, face="label", size=14, color=col, max_lines=1)
        src = self.src(c, spec, "", self.span(3, 12), self.SRC)
        if src:
            c.text(src, self.col(3), y, self.span(3, 12), 20, size=self.SRC, color=T.muted if color is None else col, max_lines=1)

    def exhibit_chart(self, c, s, x, y, w, h):
        T = self.T
        if s.get("unit"):
            self.label(c, s["unit"], x, y, w, color=T.accent_text, size=15, track=0.06)
            y += 28
            h -= 28
        return self.bars(c, s["bars"], x, y, w, h, highlight=s.get("hi"), growth=self.growth_of(s), vsize=46, lsize=18, colw_max=W, gap_ratio=0.12,
                         value_face="label", base_w=3.0)

    def s_exhibit(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        if c.measure(s.get("head", ""), "heading", 40, self.span(0, 6), self.T_LEAD) > 250:
            # a headline too long for the side column at a size that reads: across the top, the chart under it
            y = self.exhibit_head(c, s, 60, sub_color=T.ink)
            nh = self.note(c, s, self.M, H - 52, W - 2 * self.M)
            self.exhibit_chart(c, s, self.M, y + 24, W - 2 * self.M, H - 52 - nh - (y + 24))
            self.foot(c, s)
            return c.done()
        el = self.head(c, s.get("head", ""), self.M, 60, self.span(0, 6), 250, size=48, min_size=40)
        if s.get("subhead"):
            c.text(s["subhead"], self.M, el["bottom"] + 14, self.span(0, 5), 120, size=22, min_size=16, lead=1.3, color=T.ink,
                   marks=s.get("sub_marks", ""))
        nh = self.note(c, s, self.M, H - 52, self.span(0, 5))
        self.exhibit_chart(c, s, self.col(6), 64, self.span(6, 12), H - 52 - 64)
        self.foot(c, s)
        return c.done()

    def s_title(self, s):
        T = self.T
        c = self.canvas()
        c.rect(self.M, 36, W - 2 * self.M, 4, T.ink)
        self.head(c, s["title"], self.M - 4, 56, self.span(0, 11), 260, size=88, min_size=48, lead=0.96)
        by = H - 150
        c.rect(0, by, W, H - by, T.field)
        ink = T.field_text
        fig = bool(s.get("fig"))
        if s.get("sub"):
            c.text(s["sub"], self.M, by + 26, self.span(0, 7 if not fig else 6), 80, face="heading", size=26, min_size=18, lead=1.15, color=ink)
        if fig:
            if s.get("date"):
                c.text(s["date"], self.col(8), 48, self.span(8, 12), 20, face="label", size=14, lead=1.1, color=T.ink, upper=True,
                       align="right", max_lines=1)
            self.cover_fig(c, s, self.col(6), by + 14, self.span(6, 12), H - by - 30, ink, ink, ink, face="label", size=90)
        elif s.get("date"):
            c.text(s["date"], self.col(8), by + 26, self.span(8, 12), 60, face="label", size=22, lead=1.1, color=ink, upper=True, max_lines=2)
        self.label(c, s.get("org") or "", self.M, H - 34, self.span(0, 8), color=ink, size=13, track=0.06)
        c.logo(W - self.M, H - 46, 26, "band", align="right")
        return c.done(band=True)

    def s_section(self, s):
        T = self.T
        c = self.canvas(T.field)
        n = s.get("n") or 1
        c.rect(self.M, 36, W - 2 * self.M, 4, T.field_text)
        c.text(f"{n:02d}", self.M - 6, 50, self.span(0, 6), 270, face="label", size=260, lead=1.0, color=T.field_text, max_lines=1)
        el = self.head(c, s["head"], self.col(6), 220, self.span(6, 12), 200, size=44, min_size=30, color=T.field_text, anchor="bottom")
        if s.get("sub"):
            c.text(s["sub"], self.col(6), el["bottom"] + 16, self.span(6, 12), 90, size=20, min_size=16, lead=1.3, color=T.field_text,
                   marks=s.get("marks", ""))
        return c.done(dark=True, band=True)

    def s_content(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        self.head(c, s.get("head", ""), self.M, 60, self.span(0, 5), 300, size=40, min_size=28)
        self.rows(c, s.get("items") or [], self.col(5), 64, self.span(5, 12), H - 56 - 64, size=24, min_size=17, ncolor=T.accent_text,
                  hair=T.ink)
        self.foot(c, s)
        return c.done()

    def s_stat(self, s):
        T = self.T
        c = self.canvas()
        fx = self.col(7) - self.GUT / 2
        c.rect(0, 0, fx, H, T.field)
        c.rect(self.M, 36, fx - self.M - 10, 4, T.field_text)
        c.text(s["value"], self.M - 6, 90, fx - self.M - 10, 400, face="label", size=380, min_size=110, lead=0.92, color=T.field_text,
               max_lines=1, anchor="bottom")
        x = fx + 24
        c.rect(x, 36, W - self.M - x, 4, T.ink)
        lh = c.measure(s.get("label", ""), "heading", 34, W - self.M - x, 1.06)
        el = c.text(s.get("label", ""), x, max(64.0, 250 - lh), W - self.M - x, 200, face="heading", size=34, min_size=24, lead=1.06,
                    color=T.head, marks=s.get("marks", ""))
        if s.get("context"):
            c.text(s["context"], x, el["bottom"] + 20, W - self.M - x, 200, size=19, min_size=15, lead=1.4, color=T.ink)
        src = self.src(c, s, "", W - self.M - x, self.SRC)
        if src:
            c.text(src, x, H - 32, W - self.M - x, 20, size=self.SRC, color=T.muted, max_lines=1)
        return c.done(band=True)

    def s_quote(self, s):
        T = self.T
        c = self.canvas()
        c.rect(0, 0, self.col(2) - self.GUT / 2, H, T.field)
        c.text("“", self.M - 4, 50, 120, 202, face="label", size=200, lead=1.0, color=T.field_text, max_lines=1)
        qh = c.measure(f"{s['quote'].rstrip(',;: ')}”", "heading", 40, self.span(3, 12), 1.08)
        top = max(70.0, (H - qh - 60) / 2)
        el = c.text(f"{s['quote'].rstrip(',;: ')}”", self.col(3), top, self.span(3, 12), 330, face="heading", size=40, min_size=26, lead=1.08, color=T.head,
                    marks=s.get("marks", ""))
        if s.get("who"):
            self.label(c, s["who"], self.col(3), el["bottom"] + 22, self.span(3, 12), color=T.accent_text, size=15, track=0.06)
        return c.done(band=True)

    def s_comparison(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        el = self.head(c, s.get("head", ""), self.M, 60, self.span(0, 10), 110, size=40, min_size=28)
        y = el["bottom"] + 26
        cols = s.get("cols") or []
        xs, ws = [self.col(0), self.col(6)], [self.span(0, 6), self.span(6, 12)]
        for i, (label, items) in enumerate(cols[:2]):
            c.rect(xs[i], y - 8, ws[i], 6 if i == 1 else 2, T.accent if i == 1 else T.ink)
            self.label(c, label, xs[i], y + 6, ws[i], color=T.accent_text if i == 1 else T.ink, size=15, track=0.06)
        self.paired(c, cols, xs, ws, y + 40, H - 64 - (y + 40), size=22, min_size=15, colors=(T.ink, T.ink), hair=(T.hair, T.hair))
        self.foot(c, s)
        return c.done()

    def s_timeline(self, s):
        T = self.T
        c = self.canvas()
        self.top(c, s)
        el = self.head(c, s.get("head", ""), self.M, 60, self.span(0, 10), 110, size=40, min_size=28)
        steps = s.get("steps") or []
        n = max(1, len(steps))
        y = el["bottom"] + 34
        cw = (W - 2 * self.M) / n
        for i, (when, text, marks) in enumerate(steps):
            x = self.M + i * cw
            last = i == n - 1
            if last:
                c.rect(x, y - 10, W - self.M - x, H - 52 - (y - 10), T.field)
            ink = T.field_text if last else T.ink
            xx = x + (12 if last else 0)
            c.rect(xx, y, cw - 24, 3, ink)
            c.text(when, xx, y + 12, cw - 28, 60, face="label", size=24, min_size=16, lead=1.05, color=ink, max_lines=2)
            c.text(text, xx, y + 80, cw - 28, H - 70 - (y + 80), size=17, min_size=14, lead=1.32, color=ink, marks=marks)
        self.foot(c, s)
        return c.done()

    def s_image(self, s):
        T = self.T
        c = self.canvas()
        if s.get("picture"):
            c.image(self.col(5), 0, W - self.col(5), H - 52, s["picture"])
            c.rect(self.M, 36, self.span(0, 5), 4, T.ink)
            el = self.head(c, s.get("head", ""), self.M, 60, self.span(0, 5), 200, size=36, min_size=26)
            if s.get("caption"):
                c.text(s["caption"], self.M, el["bottom"] + 18, self.span(0, 5), 200, size=19, min_size=15, lead=1.35, color=T.ink, marks=s.get("marks", ""))
            self.foot(c, {**s, "src": ""})
            return c.done()
        return self.s_statement(s)

    def s_statement(self, s):
        T = self.T
        c = self.canvas(T.field)
        c.rect(self.M, 36, W - 2 * self.M, 4, T.field_text)
        el = self.head(c, s.get("head", ""), self.M, 70, self.span(0, 10), 230, size=56, min_size=36, color=T.field_text)
        if s.get("caption"):
            c.text(s["caption"], self.col(6), el["bottom"] + 24, self.span(6, 12), 140, size=22, min_size=17, lead=1.35, color=T.field_text,
                   marks=s.get("marks", ""))
        return c.done(dark=True, band=True)

    def s_closing(self, s):
        T = self.T
        c = self.canvas(T.field)
        ink = T.field_text
        c.rect(self.M, 36, W - 2 * self.M, 4, ink)
        y = 64
        if s.get("head"):
            y = self.head(c, s["head"], self.M, y, self.span(0, 10), 200, size=56, min_size=36, color=ink)["bottom"] + 24
        if s.get("amount"):
            self.ask_amount(c, s, self.M, y, self.span(0, 6), H - 96 - y, ink, ink, face="label", size=120)
        if s.get("text"):
            y = c.text(s["text"], self.col(6), y, self.span(6, 12), 140, size=21, min_size=16, lead=1.35, color=ink,
                       marks="" if s.get("amount") else s.get("marks", ""))["bottom"] + 20
        if s.get("cta"):
            c.text(s["cta"], self.col(6), y, self.span(6, 12), 70, face="label", size=22, min_size=16, lead=1.1, color=ink, upper=True,
                   track=0.04, max_lines=2)
        req = s.get("required") or []
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 56 - 18 * (len(req[:2]) - 1 - i), W - 2 * self.M, 18, size=12, color=ink, max_lines=1)
        c.logo(self.M, H - 70, 28, "band", align="left")
        return c.done(dark=True, band=True)

    def g_head(self, c, g, M):
        T = self.T
        c.rect(0, 0, GW, 360, T.field)
        c.rect(M, 70, GW - 2 * M, 5, T.field_text)
        if g.get("kicker"):
            c.text(g["kicker"], M, 88, 700, 34, face="label", size=26, color=T.field_text, upper=True, track=0.06, max_lines=1)
        c.text(g["headline"], M, 130, GW - 2 * M, 200, face="heading", size=70, min_size=44, lead=1.0, color=T.field_text,
               anchor="bottom", role="title")
        y = 396
        if g.get("dek"):
            y = c.text(g["dek"], M, y, GW - 2 * M - 80, 120, size=28, min_size=22, lead=1.32, color=T.ink, marks=g.get("dek_marks", ""))["bottom"]
        return y

    def g_bars(self, c, g, M, y, h):
        T = self.T
        if g.get("unit"):
            c.text(g["unit"], M, y, GW - 2 * M, 30, face="label", size=24, color=T.accent_text, upper=True, track=0.06, max_lines=1)
            y += 46
            h -= 46
        self.bars(c, g["bars"], M, y, GW - 2 * M, h, highlight=g.get("hi"), vsize=64, lsize=24, colw_max=GW, gap_ratio=0.1,
                  value_face="label", base_w=4.0, size=26, max_bar=70)

    def p_mast(self, c, p, M):
        T = self.T
        c.rect(0, 0, PW, 150, T.field)
        c.rect(M, 30, PW - 2 * M, 3, T.field_text)
        self.label(c, p.get("org") or "", M, 40, 300, color=T.field_text, size=10, track=0.06)
        self.label(c, p.get("date") or "", PW - M - 200, 40, 200, color=T.field_text, size=10, align="right", track=0.06)
        c.text(p["title"], M, 58, PW - 2 * M, 80, face="heading", size=30, min_size=22, lead=1.02, color=T.field_text, anchor="bottom",
               role="title")
        return 150


SYSTEMS = {"exhibit": System, "broadsheet": Broadsheet, "stage": Stage, "folio": Folio, "grid": Grid}


# ---------------------------------------------------------------- the second family --
#
# Round 11 (five blind critic panels: "one layout family in three palettes"). Every system above shares one set of
# slide compositions: a hairline tracker, the title across the top, the evidence under it on the paper. The editorial
# family is a second set, worked out from how a magazine art desk and an annual-report studio build spreads (the
# Pitch cover's type scale, the foundation report's color tabs, the consulting exhibit's one highlighted bar):
#
# - **full**: the slide is one color field, full bleed (the cover, a stat set huge, the close).
# - **split-L / split-R**: a field of color owns one side; the headline sits on it, the evidence on the paper beside
#   it, and the chart bleeds off the paper's edge.
# - **rail-R / rail-L**: a large column of type on the paper and a narrow tinted rail holding the evidence.
# - **open**: the headline set very large, the points under it in two columns, no rules boxing them in.
#
# The deck alternates: each slide kind lists the compositions it can take, and a slide never takes the one the slide
# before it took. The colors, faces and furniture still come from the kit and its system, so a kit in this family
# keeps its own palette and type; what changes is how the page is built.

class Editorial:
    """The editorial family, mixed over a system: its slides composed as spreads, not as exhibits."""
    family = "editorial"
    draws_fig = True  # the family sets the cover's figure and the closing's amount itself, on every system
    PREFS = {
        "title": ["full"], "exhibit": ["split-L", "split-R"], "figures": ["full", "rail-R"], "stat": ["full", "rail-R"],
        "quote": ["full", "split-R"], "ledger": ["rail-R", "rail-L"], "content": ["open", "rail-L"],
        "closing": ["full", "split-L"], "statement": ["full"], "section": ["split-L"],
    }
    BASE_COMP = {"section": "split-L", "statement": "full", "image": "split-R"}

    def compose(self, spec: dict) -> dict:
        k = spec["kind"]
        last = getattr(self, "_last_comp", None)
        prefs = self.PREFS.get(k)
        if k == "quote" and (spec.get("photo") or {}).get("name"):
            prefs = ["split-R", "full"]  # a source photo of the speaker sits beside the quote
        if prefs:
            comp = next((p for p in prefs if p != last), prefs[0])
        else:
            comp = self.BASE_COMP.get(k, "open")
        if spec.get("comp") in (prefs or []):  # round 13: split to fit moved this slide to the composition that holds more text
            comp = spec["comp"]
        self._comp = comp
        sc = super().compose(spec)
        sc["comp"], sc["family"] = comp, self.family
        self._last_comp = comp
        return sc

    # ------------------------------------------------------------ craft --

    def _t(self, c, text, x, y, w, h, ground, **kw):
        """Text whose source marks are measured against the ground it actually sits on (a panel, not the slide)."""
        el = c.text(text, x, y, w, h, **kw)
        if el.get("marks"):
            el["mcolor"] = SC._quiet(el["color"], ground)
        return el

    def _rail(self):
        T = self.T
        return C.mix(T.main, T.paper, 0.86 if not T.dark else 0.8)

    def _photo(self, c, s, x, y, w, h, credit_color, ground):
        """A photo from the sources, credited to its file: only when a source holds one (never generated or stock)."""
        ph = s.get("photo") or {}
        if not ph.get("name"):
            return False
        c.image(x, y, w, h, ph["name"])
        if ph.get("credit"):
            cr = "Photo: " + ph["credit"]
            c.rect(x, y + h - 30, w, 30, C.mix("#000000", ground, 0.35))
            c.text(cr, x + 12, y + h - 24, w - 24, 18, face="body", size=12, min_size=10, color="#ffffff", max_lines=1)
        return True

    def _src(self, c, s, x, y, w, color):
        src = self.src(c, s, "Source: ", w, self.SRC)
        if src:
            c.text(src, x, y, w, self.SRC * 1.4, face="body", size=self.SRC, lead=1.3, color=color, max_lines=1)

    def _num(self, c, s, x, y, color, align="right", w=60):
        if self.show_numbers and s.get("num", 1) > 1:
            c.text(f"{s['num']:02d}", x, y, w, self.SRC * 1.4, face="label", size=self.SRC, lead=1.3, color=color, align=align)

    def _deck(self, c, s, x, y, w, color, align="left"):
        if s.get("deck"):
            c.text(s["deck"], x, y, w, 18, face="label", size=12, lead=1.3, color=color, align=align, upper=True, track=0.12, max_lines=1)

    def bleed_bars(self, c, s, x0, y, h, side="right"):
        """The exhibit's bars bleeding off the slide's edge: the longest runs off the paper, each value set inside its
        own bar, the name over it, the finding in the accent and set apart, the rest in a tint."""
        T = self.T
        bars = s.get("bars") or []
        n = max(1, len(bars))
        hi = self._hi(bars, s.get("hi"))
        growth = self.growth_of(s)
        top = max([b[2] for b in bars if b[2] is not None] or [1]) or 1
        sep = hi == n - 1 and n >= 3
        rows_n = n + (0.4 if sep else 0)
        row = min(h / rows_n, 118.0)
        lab = 17.0
        bh = min(row - lab * 1.3 - 14, 64.0)
        yy = y + max(0.0, (h - row * rows_n) / 2)
        span = (W - x0) if side == "right" else x0
        for i, (label, value, num, marks) in enumerate(bars):
            ry = yy + (i + (0.4 if sep and i == n - 1 else 0)) * row
            ln = max(4.0, span * ((num or 0) / top)) if num else 4.0
            is_hi = i == hi
            col = T.accent if is_hi else T.tint
            bx = x0 if side == "right" else x0 - ln
            lx = x0 if side == "right" else self.M
            # round 14: a long name takes a second line (never cut) and its bar gives up the height
            el = c.text(label, lx, ry, (W - x0 - 24) if side == "right" else (x0 - self.M), lab * 1.3 * 2, face="body_bold" if is_hi else "body",
                        size=lab, min_size=13, lead=1.3, color=T.accent_text if is_hi else T.ink, max_lines=2)
            by = el["bottom"] + 6
            bh = max(24.0, min(min(row - lab * 1.3 - 14, 64.0), ry + row - by - 8))
            c.rect(bx, by, ln, bh, col, bar=i)
            if growth == i and i > 0 and not is_hi and bars[i - 1][2] and num and num > bars[i - 1][2]:
                pl = span * (bars[i - 1][2] / top)
                gx = x0 + pl if side == "right" else x0 - ln
                gw = ln - pl
                c.rect(gx, by, gw, bh, T.grow)
                gt = self.growth_text(bars, i)
                gs = min(18.0, bh * 0.4)
                on = C.best_text_on(T.grow, [T.paper, T.ink, "#ffffff", "#111111"])[0]
                if c.ty.width(gt, "body_bold", gs) + 16 <= gw:
                    c.text(gt, gx + 8, by + (bh - gs * 1.2) / 2, gw - 16, gs * 1.2, face="body_bold", size=gs, lead=1.2, color=on,
                           align="left" if side == "right" else "right", max_lines=1)
            vs = min(46.0, bh * 0.78)
            vw = c.ty.width(value, "heading", vs) + 0.32 * vs * (len(marks) + 1 if marks else 0)
            on_bar = C.best_text_on(col, [T.paper, T.ink, "#ffffff", "#111111"])[0]
            inside = ln - (span * (bars[i - 1][2] / top) if (growth == i and i > 0 and bars[i - 1][2]) else 0) >= vw + 36 or ln >= vw + 36
            if is_hi and ln + vw + 40 < span:
                # the finding's value stands just past its bar, so the bar's own end stays clear for the trace line
                inside = False
            if inside and growth != i:
                vx = bx + 16 if side == "right" else bx + ln - vw - 16
                vc = on_bar
            elif inside:
                vx = bx + 16 if side == "right" else bx + ln - vw - 16
                vc = on_bar
            else:
                vx = bx + ln + 14 if side == "right" else bx - vw - 14
                vc = T.accent_text if is_hi else T.ink
            el = c.text(value, vx, by + (bh - vs * 1.1) / 2, vw + 30, vs * 1.1, face="heading", size=vs, lead=1.1, color=vc, marks=marks,
                        max_lines=1)
            if marks and inside:
                el["mcolor"] = SC._quiet(vc, col)
        return hi

    # ------------------------------------------------------------ slides --

    def s_title(self, s):
        """The cover as a magazine cover: the title set huge from the top, a heavy rule under it, the standfirst and
        the deck's figure in a row below. A source photo, when there is one, takes the right third."""
        T = self.T
        c = self.canvas(T.field)
        photo = bool((s.get("photo") or {}).get("name"))
        right = self.col(8) - self.GUT / 2 if photo else W
        tw = right - 2 * self.M
        self.label(c, s.get("org") or "", self.M, 34, tw * 0.7, color=T.field_text, size=13)
        if not photo:
            c.logo(W - self.M, 26, 30, "band", align="right")
        tsize = 88.0
        while tsize > 52 and c.measure(s["title"], "heading", tsize, tw, 0.95) > 250:
            tsize -= 4
        fig = bool(s.get("fig")) and self.draws_fig
        if fig and not getattr(self, "cover_low", False):
            # the title steps down until the figure row under it has room for the figure at its full width-fit size
            # (measured in the face actually used, up to 120 pt) and its label; the figure never pushes its label off the slide
            fx = self.M + tw * 0.6
            fw = right - self.M - fx
            fv, flab, _m = s["fig"]
            need = min(120.0, self.fit_size(c, [fv], fw - 6, 150.0, 36, "heading")) * 0.96 + 18
            if flab:
                need += 22 + c.measure(flab, "label", 15, fw, 1.3, track=0.08, upper=True)
            while tsize > 52 and max(84 + c.measure(s["title"], "heading", tsize, tw, 0.95) + 30, 300.0) > H - 56 - need:
                tsize -= 4
        if getattr(self, "cover_low", False) and fig:
            # the poster cover: the figure set across the top as structure, the title low under a heavy rule
            v, lab, m = s["fig"]
            vs = self.fit_size(c, [v], tw * 0.6, 230.0, 80.0)
            self._t(c, v, self.M - 6, 60, tw * 0.62, vs * 0.95, T.field, face="heading", size=vs, min_size=vs, lead=0.95,
                    color=T.field_accent, marks=m, max_lines=1)
            if lab:
                c.text(lab, self.M + tw * 0.64, 60 + vs * 0.95 - 40, tw * 0.36, 40, face="label", size=14, lead=1.3, color=T.field_text,
                       upper=True, track=0.1, anchor="bottom")
            th = c.measure(s["title"], "heading", min(tsize, 64.0), tw * 0.8, 0.98)
            ty = H - 64 - th - (40 if s.get("sub") else 0)
            c.rect(self.M, ty - 26, tw, 8, T.field_text)
            el = self.head(c, s["title"], self.M - 3, ty, tw * 0.8, th + 4, size=min(tsize, 64.0), min_size=40, color=T.field_text, lead=0.98)
            if s.get("sub"):
                c.text(s["sub"], self.M, el["bottom"] + 12, tw * 0.8, 34, size=20, min_size=15, lead=1.3, color=T.field_muted, max_lines=1)
            self.label(c, s.get("date") or "", W - self.M - 240, H - 38, 240, color=T.field_muted, size=12, align="right")
            return c.done(dark=True, band=True)
        el = self.head(c, s["title"], self.M - 3, 84, tw, 270, size=tsize, min_size=48, color=T.field_text, lead=0.95)
        ry = max(el["bottom"] + 30, 300.0)
        c.rect(self.M, ry, tw, 6, T.field_accent)
        sw = tw * (0.56 if fig else 0.8)
        if s.get("sub"):
            c.text(s["sub"], self.M, ry + 26, sw, H - 70 - (ry + 26), size=24, min_size=17, lead=1.3, color=T.field_text)
        if fig:
            fx = self.M + tw * 0.6
            self.cover_fig(c, s, fx, ry + 18, right - self.M - fx, H - 56 - (ry + 18), T.field_accent, T.field_muted, T.field_hair,
                           size=150.0)
        self.label(c, s.get("date") or "", self.M, H - 38, tw * 0.5, color=T.field_muted, size=12)
        if photo:
            self._photo(c, s, right, 0, W - right, H, T.field_muted, T.field)
        return c.done(dark=True, band=True)

    def s_exhibit(self, s):
        """Split screen: the finding stated on a field of color, the chart on the paper bleeding off the slide's edge."""
        T = self.T
        c = self.canvas()
        comp = getattr(self, "_comp", "split-L")
        head = s.get("head", "")
        pw = self.col(5) + 24
        for cand in (self.col(5) + 24, self.col(6) - self.GUT / 2, self.col(6) + 24):
            pw = cand
            if c.measure(head, "heading", 56, cand - 36 - self.M, 1.04) <= 56 * 1.04 * 4 + 1:
                break  # the headline sets in four lines or fewer at a size that reads on a small screen
        if comp == "split-L":
            px, tx, cx0, side = 0.0, self.M, pw + 44, "right"
        else:
            px, tx, cx0, side = W - pw, W - pw + 36, W - pw - 44, "left"
        c.rect(px, 0, pw, H, T.field)
        tw = pw - 36 - (self.M if comp == "split-L" else self.M)
        self._deck(c, s, tx, 40, tw, T.field_muted)
        hs = 56.0  # the finding reads at 36 px or more on a 1024 screen (the canvas shows the slide at about 0.68)
        while hs > 34 and (c.measure(s.get("head", ""), "heading", hs, tw, 1.04) > 300 or
                           max(c.ty.width(wd, "heading", hs) for wd in (s.get("head") or "x").split()) > tw):
            hs -= 2
        el = self.head(c, s.get("head", ""), tx, 80, tw, 310, size=hs, min_size=30, color=T.field_text, lead=1.04)
        y = el["bottom"] + 20
        c.rect(tx, y, 48, 5, T.field_accent)
        if s.get("subhead"):
            self._t(c, s["subhead"], tx, y + 22, tw, H - 100 - (y + 22), T.field, face="body", size=22, min_size=16, lead=1.3,
                    color=T.field_text, marks=s.get("sub_marks", ""))
        self._src(c, s, tx, H - 40, tw, T.field_muted)
        cy = 70.0
        if s.get("unit"):
            ux = cx0 if side == "right" else self.M
            self.label(c, s["unit"], ux, 48, (W - cx0 - 24) if side == "right" else (cx0 - self.M), color=T.muted, size=13)
        nh = 0.0
        if s.get("note"):
            nx, nw = (cx0, W - cx0 - self.M) if side == "right" else (self.M, cx0 - self.M)
            nh = self.note(c, s, nx, H - 30, nw)
        self.bleed_bars(c, s, cx0, cy + 10, H - 60 - nh - cy, side=side)
        self._num(c, s, (W - self.M - 60) if side == "right" else self.M, H - 34, T.muted, align="right" if side == "right" else "left")
        return c.done()

    def _figs_block(self, c, s, ground, ink, head, accent, muted, hair, x, w, rail_x, rail_w, rail_ground=None):
        figs = list(s.get("figs") or [])[:4]
        hs = 40.0
        while hs > 28 and c.measure(s.get("head", ""), "heading", hs, w, 1.06) > 140:
            hs -= 2
        el = self.head(c, s.get("head", ""), x, 66, w, 150, size=hs, min_size=26, color=head, lead=1.06)
        if not figs:
            return el["bottom"]
        v, l, ctx, m = figs[0]
        num, unit = self.split_unit(v)
        top = el["bottom"] + 26
        room = H - 60 - top
        vs = self.fit_size(c, [num], w - (c.ty.width(unit, "body_bold", 30) + 14 if unit else 0), 190.0, 60.0)
        vs = min(vs, room * 0.62)
        ve = self._t(c, num, x - 4, top, w, vs * 1.0, ground, face="heading", size=vs, min_size=vs, lead=1.0, color=accent,
                     marks="" if unit else m, max_lines=1)
        if unit:
            us = max(20.0, vs * 0.24)
            ux = x - 4 + c.ty.width(num, "heading", vs) + 12
            self._t(c, unit, ux, top + vs * 0.72 - us, w - (ux - x), us * 1.2, ground, face="body_bold", size=us, lead=1.2, color=accent,
                    marks=m, max_lines=1)
        le = c.text(l, x, ve["bottom"] + 12, w * 0.85, 60, face="body_bold", size=24, min_size=17, lead=1.22, color=ink, role="body")
        if ctx:
            c.text(ctx, x, le["bottom"] + 8, w * 0.85, max(20.0, H - 56 - (le["bottom"] + 8)), face="body", size=18, min_size=13,
                   lead=1.35, color=muted)
        rest = figs[1:]
        if rest:
            rg = rail_ground or ground
            n = len(rest)
            ry0 = 70.0
            rh = (H - 60 - ry0) / n
            fs = self.fit_size(c, [self.split_unit(f[0])[0] for f in rest], rail_w - 8, 64.0, 30.0)
            fs = min(fs, rh * 0.5)
            for i, (v2, l2, ctx2, m2) in enumerate(rest):
                yy = ry0 + i * rh
                c.rect(rail_x, yy, rail_w, 1, hair)
                n2, u2 = self.split_unit(v2)
                e2 = self._t(c, n2 + ((" " + u2) if u2 else ""), rail_x, yy + 12, rail_w, fs * 1.05, rg, face="heading", size=fs,
                             min_size=fs * 0.6, lead=1.0, color=head, marks=m2, max_lines=1)
                c.text(l2, rail_x, e2["bottom"] + 6, rail_w, rh - fs * 1.05 - 24, face="body", size=16, min_size=12, lead=1.25,
                       color=ink, role="body")
        return top

    def s_figures(self, s):
        """A stat slide: the lead figure set as large as the page takes, the others in a rail beside it. On a full field
        of color, or on the paper with a tinted rail when the slide before was a field."""
        T = self.T
        if s.get("note"):  # round 16: a figures row with its caption band, set by the system under this family
            return super().s_figures(s)
        comp = getattr(self, "_comp", "full")
        rx = self.col(8) + 4
        rw = W - self.M - rx
        if comp == "full":
            c = self.canvas(T.field)
            c.rect(self.col(8) - self.GUT / 2, 66, 1, H - 66 - 56, T.field_hair)
            self._deck(c, s, self.M, 30, self.span(0, 8), T.field_muted)
            self._figs_block(c, s, T.field, T.field_text, T.field_text, T.field_accent, T.field_muted, T.field_hair,
                             self.M, self.span(0, 8) - 16, rx, rw)
            self._src(c, s, self.M, H - 38, self.span(0, 8), T.field_muted)
            self._num(c, s, W - self.M - 60, H - 38, T.field_muted)
            return c.done(dark=True, band=True)
        c = self.canvas()
        rail = self._rail()
        c.rect(self.col(8) - self.GUT / 2 - 12, 0, W - (self.col(8) - self.GUT / 2 - 12), H, rail)
        self._deck(c, s, self.M, 30, self.span(0, 8), T.muted)
        self._figs_block(c, s, T.paper, T.ink, T.head, T.accent_text, T.muted, T.hair, self.M, self.span(0, 8) - 16, rx, rw,
                         rail_ground=rail)
        self._src(c, s, self.M, H - 38, self.span(0, 8), T.muted)
        self._num(c, s, W - self.M - 60, H - 38, T.muted)
        return c.done()

    def s_stat(self, s):
        """One number given the page: set as large as seven columns hold, on a full field of color (or on the paper
        with the words in a tinted rail), what it counts and what it means in the column beside it."""
        T = self.T
        comp = getattr(self, "_comp", "full")
        full = comp == "full"
        rx = self.col(8) - self.GUT / 2
        c = self.canvas(T.field if full else None)
        rail = self._rail()
        if not full:
            c.rect(rx, 0, W - rx, H, rail)
        ground, ink, muted = (T.field, T.field_text, T.field_muted) if full else (T.paper, T.head, T.muted)
        accent = T.field_accent if full else T.accent_text
        num, unit = self.split_unit(s.get("value", ""))
        lw = rx - self.M - 24
        vs = self.fit_size(c, [num], lw - (c.ty.width(unit, "body_bold", 40) + 16 if unit else 0), 300.0, 80.0)
        top = (H - vs * 0.9) / 2 - (30 if unit else 10)
        ve = self._t(c, num, self.M - 8, top, lw, vs * 0.95, ground, face="heading", size=vs, min_size=vs, lead=0.95, color=accent,
                     marks="" if unit else s.get("marks", ""), max_lines=1)
        if unit:
            us = max(28.0, vs * 0.2)
            ux = self.M - 8 + c.ty.width(num, "heading", vs) + 16
            if ux + c.ty.width(unit, "body_bold", us) > rx - 12:
                ux, uy = self.M, ve["bottom"] + 6  # a long unit goes under the number
            else:
                uy = top + vs * 0.72 - us
            self._t(c, unit, ux, uy, rx - 12 - ux, us * 1.2, ground, face="body_bold", size=us, lead=1.2, color=accent,
                    marks=s.get("marks", ""), max_lines=1)
        tx, tw = rx + 32, W - self.M - rx - 32 + (8 if full else 0)
        lh = c.measure(s.get("label", ""), "body_bold", 28, tw, 1.2)
        ch = c.measure(s.get("context", ""), "body", 19, tw, 1.4) + 18 if s.get("context") else 0
        y = max(90.0, (H - lh - ch) / 2)
        c.rect(tx, y - 26, 40, 5, T.field_accent if full else T.accent)
        if full:
            c.rect(rx, 66, 1, H - 66 - 56, T.field_hair)
        el = self._t(c, s.get("label", ""), tx, y, tw, 200, ground if full else rail, face="body_bold", size=28, min_size=18, lead=1.2,
                     color=ink, role="body")
        if s.get("context"):
            c.text(s["context"], tx, el["bottom"] + 18, tw, H - 60 - (el["bottom"] + 18), face="body", size=19, min_size=14, lead=1.4,
                   color=muted if full else T.muted)
        self._src(c, s, self.M, H - 38, lw, muted)
        self._num(c, s, W - self.M - 60, H - 38, muted)
        return c.done(dark=True, band=True) if full else c.done()

    def s_quote(self, s):
        """The quote set huge over a field of color. On a split, the speaker sits on the paper beside it (or a source
        photo of them, when the sources hold one)."""
        T = self.T
        comp = getattr(self, "_comp", "full")
        q = f"{s['quote'].rstrip(',;: ')}”"
        c = self.canvas(T.field if comp == "full" else None)
        if comp == "full":
            x, w = self.M + 70, W - 2 * self.M - 70
        else:
            pw = W - (self.col(4) - self.GUT / 2)
            c.rect(W - pw, 0, pw, H, T.field)
            x, w = W - pw + 104, pw - 104 - self.M
        size = 34.0
        longest = max(q.split(), key=lambda wd: c.ty.width(wd, "heading", 10)) if q.split() else ""
        for sz in (78.0, 72.0, 66.0, 60.0, 54.0, 48.0, 44.0, 40.0, 36.0):
            if c.measure(q, "heading", sz, w, 1.08) <= H * (0.6 if comp == "full" else 0.7) and c.ty.width(longest, "heading", sz) <= w:
                size = sz
                break
        qh = c.measure(q, "heading", size, w, 1.08)
        who_h = 70 if (s.get("who") and (comp == "full" or (s.get("photo") or {}).get("name"))) else 0
        top = max(70.0, (H - qh - who_h) / 2 - 10)
        c.text("“", x - 84, top - 22, 76, 160, face="heading", size=150, lead=1.0, color=T.field_accent, max_lines=1)
        el = self._t(c, q, x, top, w, qh + size, T.field, face="heading", size=size, min_size=26, lead=1.08, color=T.field_text,
                     marks=s.get("marks", ""))
        src = (s.get("src_short") or "").replace("Source: ", "From the ")
        photo = comp != "full" and self._photo(c, s, 0, 0, self.col(4) - self.GUT / 2, H, T.muted, T.paper)
        if comp == "full" or photo:
            if s.get("who"):
                y = el["bottom"] + 28
                c.rect(x, y + 10, 40, 3, T.field_accent)
                c.text(s["who"], x + 54, y, w - 54, 28, face="body_bold", size=20, min_size=15, lead=1.25, color=T.field_text, max_lines=1)
                if src:
                    c.text(src, x + 54, y + 30, w - 54, 22, face="body", size=15, min_size=12, lead=1.25, color=T.field_muted, max_lines=1)
                if s.get("note"):  # loop 3: the takeaway after the attribution, as a line of text, never a list item
                    ny = y + (58 if src else 36)
                    c.text(s["note"], x + 54, ny, w - 54, max(24.0, H - 50 - ny), face="body", size=19, min_size=14, lead=1.3,
                           color=T.field_text, role="body")
            self._num(c, s, W - self.M - 60, H - 38, T.field_muted)
            return c.done(dark=True, band=True) if comp == "full" else c.done()
        lw = self.span(0, 4) - 12
        self._deck(c, s, self.M, 40, lw, T.muted)
        if s.get("who"):
            c.rect(self.M, H - 168, 40, 4, T.accent)
            c.text(s["who"], self.M, H - 148, lw, 64, face="body_bold", size=22, min_size=15, lead=1.25, color=T.head)
            if src:
                c.text(src, self.M, H - 84, lw, 40, face="body", size=15, min_size=12, lead=1.3, color=T.muted)
        if s.get("note"):
            c.text(s["note"], self.M, 90, lw, H - 190 - 90, face="body", size=20, min_size=14, lead=1.3, color=T.ink, role="body")
        self._num(c, s, self.M, H - 38, T.muted, align="left")
        return c.done()

    def s_ledger(self, s):
        """A large column of type and a narrow evidence rail: the headline set big on the paper, the numbers in a
        tinted rail beside it, each figure over its line."""
        T = self.T
        comp = getattr(self, "_comp", "rail-R")
        c = self.canvas()
        rail = self._rail()
        rw = self.span(0, 5) + self.GUT + 20
        if comp == "rail-R":
            rx0, tx = W - rw, self.M
        else:
            rx0, tx = 0.0, rw + 40
        tw = W - rw - 40 - self.M
        c.rect(rx0, 0, rw, H, rail)
        self._deck(c, s, tx, 34, tw, T.muted)
        hs = 54.0
        while hs > 32 and c.measure(s.get("head", ""), "heading", hs, tw, 1.02) > 280:
            hs -= 2
        el = self.head(c, s.get("head", ""), tx, 72, tw, 300, size=hs, min_size=30, color=T.head, lead=1.02)
        y = el["bottom"] + 22
        c.rect(tx, y, 56, 5, T.accent)
        if s.get("subhead"):
            self._t(c, s["subhead"], tx, y + 22, tw, H - 70 - (y + 22), T.paper, face="body", size=21, min_size=15, lead=1.35,
                    color=T.muted, marks=s.get("sub_marks", ""))
        self._src(c, s, tx, H - 38, tw, T.muted)
        items, figs = s.get("items") or [], s.get("figs") or []
        ix, iw = rx0 + 32, rw - 32 - (self.M - 16 if comp == "rail-R" else 32)
        n = max(1, len(items))
        y0, y1 = 44.0, H - 44
        rh = (y1 - y0) / n
        fs = self.fit_size(c, [f for f in figs if f], iw, 44.0, 24.0)
        for i, (t, m) in enumerate(items):
            yy = y0 + i * rh
            c.rect(ix, yy, iw, 1, T.hair)
            ty = yy + 12
            if i < len(figs) and figs[i]:
                fe = self._t(c, figs[i], ix, ty, iw, fs * 1.05, rail, face="heading", size=fs, min_size=fs * 0.7, lead=1.0,
                             color=T.accent_text, max_lines=1)
                ty = fe["bottom"] + 6
            self._t(c, t, ix, ty, iw, yy + rh - 8 - ty, rail, face="body", size=17, min_size=12, lead=1.28, color=T.ink, marks=m,
                    role="body")
        c.rect(ix, y1, iw, 1, T.hair)
        self._num(c, s, (W - self.M - 60) if comp == "rail-L" else tx + tw - 60, H - 38, T.muted)
        return c.done()

    def s_content(self, s):
        """Open: the headline set very large, the points under it in two columns, each led by its number."""
        T = self.T
        comp = getattr(self, "_comp", "open")
        items = s.get("items") or []
        if comp == "rail-L":
            return self.s_ledger({**s, "figs": [f"{i + 1:02d}" for i in range(len(items))]})
        c = self.canvas()
        self._deck(c, s, self.M, 30, self.span(0, 8), T.muted)
        tw = self.span(0, 10)
        hs = 58.0
        while hs > 34 and c.measure(s.get("head", ""), "heading", hs, tw, 1.0) > 135:
            hs -= 2
        n = len(items)
        cols = 2 if n > 1 else 1
        per = math.ceil(n / cols) if n else 1
        if cols == 2 and s.get("split") and 1 <= s["split"] < n:
            per = s["split"]  # loop 3: the second column starts where the lines change kind
        groups = [items[:per], items[per:]] if cols == 2 else [items]
        numbered = n <= 6  # loop 3 (critics 11): a list over six items is two columns of plain rows, not 01 to 10
        ind = 50 if numbered else 0
        cw = (W - 2 * self.M - self.GUT * 2 * (cols - 1)) / cols

        def need(sz):
            return max([sum(c.measure(t + (" " + m if m else ""), "body", sz, cw - ind, 1.3) for t, m in g) + 22 * (len(g) - 1)
                        for g in groups] or [0])
        # round 16: when the points do not fit at the type floor, the headline steps down before anything runs into
        # the foot (no point is cut, no slide is added)
        while hs > 30 and need(15.0) > H - 70 - (60 + c.measure(s.get("head", ""), "heading", hs, tw, 1.0) + 34):
            hs -= 2
        el = self.head(c, s.get("head", ""), self.M - 2, 60, tw, 150, size=hs, min_size=30, color=T.head, lead=1.0)
        y = el["bottom"] + 34
        size = 28.0
        avail = H - 70 - y
        while size > 15:
            if need(size) <= avail:
                break
            size -= 1
        for i, (t, m) in enumerate(items):
            k, r = (0, i) if i < per else (1, i - per)
            x = self.M + k * (cw + self.GUT * 2)
            yy = y + sum(c.measure(tt + (" " + mm if mm else ""), "body", size, cw - ind, 1.3) + 22 for tt, mm in groups[k][:r])
            if numbered:
                c.text(f"{i + 1:02d}", x, yy - 2, 44, 30, face="heading", size=24, lead=1.1, color=T.accent_text, max_lines=1)["mk"] = True
            elif r:
                c.rect(x, yy - 12, cw, 1, T.hair)
            c.text(t, x + ind, yy, cw - ind, avail, face="body", size=size, min_size=size, lead=1.3, color=T.ink, marks=m, role="body")
        c.rect(self.M, y - 18, 56, 5, T.accent)
        self._src(c, s, self.M, H - 38, W - 2 * self.M - 80, T.muted)
        self._num(c, s, W - self.M - 60, H - 38, T.muted)
        return c.done()

    def s_closing(self, s):
        """The close on a full field: the ask in figures as large as the page holds, then what it buys and the call."""
        T = self.T
        comp = getattr(self, "_comp", "full")
        amt = bool(s.get("amount"))
        if comp != "full" or not amt:
            return super().s_closing(s)
        c = self.canvas(T.field)
        c.logo(W - self.M, 30, 28, "band", align="right")
        self._deck(c, s, self.M, 36, self.span(0, 8), T.field_muted)
        vs = self.fit_size(c, [s["amount"]], self.span(0, 9), 168.0, 60.0)
        ae = self._t(c, s["amount"], self.M - 6, 76, self.span(0, 10), vs * 1.0, T.field, face="heading", size=vs, min_size=vs, lead=1.0,
                     color=T.field_accent, marks=s.get("marks", ""), max_lines=1)
        y = ae["bottom"] + 8
        if s.get("amount_label"):
            y = c.text(s["amount_label"], self.M, y, self.span(0, 10), 40, face="body_bold", size=24, min_size=17, lead=1.25,
                       color=T.field_text, max_lines=1)["bottom"]
        y = max(y + 26, 290.0)
        c.rect(self.M, y, W - 2 * self.M, 2, T.field_hair)
        lw, rx, rw = self.span(0, 6), self.col(7), self.span(7, 12)
        req = s.get("required") or []
        bottom = H - 48 - 16 * len(req[:2])
        hb = y + 22
        if s.get("head"):
            hb = self.head(c, s["head"], self.M, y + 22, lw, bottom - (y + 22), size=34, min_size=22, color=T.field_text, lead=1.08)["bottom"]
        # the right column: the text, then the call under it, each fit by its measured height in the room the column
        # has (stepping down to the floor). Nothing is cut: a call that still does not fit keeps its whole sentences
        # and the rest is set under the heading on the left
        top = y + 24
        cta_h = c.measure(s.get("cta", ""), "body_bold", 20, rw, 1.3) if s.get("cta") else 0
        if s.get("text"):
            top = c.text(s["text"], rx, top, rw, max(40.0, bottom - top - (cta_h + 18 if cta_h else 0)), size=19, min_size=14, lead=1.4,
                         color=T.field_muted)["bottom"] + 18
        if s.get("cta"):
            room = bottom - top
            n = max(1, int(room // (15 * 1.3)))
            el = c.text(s["cta"], rx, top, rw, max(room, 20.0), face="body_bold", size=20, min_size=15, lead=1.3,
                        color=T.field_text, max_lines=n, spill=True, anchor="bottom")
            if el.get("rest"):
                c.text(el["rest"], self.M, hb + 18, lw, max(20.0, bottom - hb - 18), face="body_bold", size=el["size"], min_size=12,
                       lead=1.3, color=T.field_text)
        for i, line in enumerate(req[:2]):
            c.text(line, self.M, H - 40 - 16 * (len(req[:2]) - 1 - i), self.span(0, 9), 16, face="body", size=11, color=T.field_muted,
                   max_lines=1)
        return c.done(dark=True, band=True)


_FAMILIES: dict = {}


def editorial(base: type) -> type:
    """``base`` composed in the editorial family (its colors, faces and furniture, the family's compositions)."""
    if base not in _FAMILIES:
        extra = {"family": "editorial"}
        if base.name == "grid":
            # the poster builds its spreads the other way round: the field on the right, the rail on the left, the
            # figure over the title on the cover, so two kits in this family never read as one layout recolored
            extra["PREFS"] = {**Editorial.PREFS, "exhibit": ["split-R", "split-L"], "ledger": ["rail-L", "rail-R"],
                              "quote": ["split-R", "full"], "figures": ["full", "rail-R"], "content": ["rail-L", "open"]}
            extra["cover_low"] = True
        _FAMILIES[base] = type(f"Editorial{base.__name__}", (Editorial, base), extra)
    return _FAMILIES[base]


# The family each studio system takes when the kit doesn't say: the poster and the keynote are built as spreads; the
# exhibit, the data desk and the book keep the first family. An imported brand (not a starter) takes the editorial
# family too, so a brand's deck never looks like a recolored studio deck (render_deck.family_of decides that).
EDITORIAL_SYSTEMS = {"stage", "grid"}
FAMILIES = ("classic", "editorial")


def for_kit(kit: dict, pal: dict, ty: SC.Type, name: str, family: Optional[str] = None) -> System:
    """The kit's system; ``family`` "editorial" composes its slides in the second family (graphics and pages are
    the system's own either way)."""
    base = SYSTEMS.get(name, System)
    fam = family or kit.get("family") or ("editorial" if name in EDITORIAL_SYSTEMS else "classic")
    return (editorial(base) if fam == "editorial" else base)(ty, Tokens(pal, kit), kit)
