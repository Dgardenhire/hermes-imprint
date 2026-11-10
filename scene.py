"""Scenes: one measured drawing of a slide or a graphic, and the five ways it is written out.

A design system (``systems.py``) composes each slide or graphic as a scene: a canvas size, a ground, and a flat
list of elements in canvas points. Text is measured and broken into lines here, with the same TrueType faces the
PDF embeds, so every backend draws the same lines in the same places:

- ``nodes``  the pane preview (plain nodes the page walks into React, positioned in percent, sized in container
  units, so a slide scales with its column and numbers can still be traced and hovered)
- ``svg``    a standalone SVG with the faces it uses embedded
- ``png``    a raster through Pillow, at any scale
- ``pdf``    drawn on a reportlab canvas page
- PowerPoint is written in ``render_deck`` from the same elements, so titles land in title placeholders.

Elements (all coordinates in points, origin top left):

    {"t": "rect", x, y, w, h, fill}
    {"t": "dot", x, y, w, h, fill}                               a circle in the box
    {"t": "text", x, y, w, h, lines, face, size, lead, color, align, track, marks, role}
    {"t": "image", x, y, w, h, name}                             a picture from the output folder, cropped to fill
    {"t": "logo", x, y, w, h, place}                             the kit's logo for that ground (paper or band)

``role`` on a text element says what PowerPoint should make of it: ``title`` (the title placeholder), ``body``
(the body placeholder, one paragraph per item), or nothing (a text box).
"""

from __future__ import annotations

import base64
import io
import re
from typing import Optional

try:
    from . import render_pdf as RP
except ImportError:  # loaded loose
    import render_pdf as RP  # type: ignore

ROLES = ("heading", "body", "body_bold", "body_italic", "label")


# ---------------------------------------------------------------- measuring --

class Type:
    """The kit's faces, registered with the PDF engine, measured in points."""

    def __init__(self, faces: dict):
        self.faces = faces
        self.names = RP.register_faces(faces)
        from reportlab.pdfbase import pdfmetrics
        self.pm = pdfmetrics

    def name(self, face: str) -> str:
        return self.names.get(face) or self.names.get("body") or "Helvetica"

    def width(self, text: str, face: str, size: float, track: float = 0.0) -> float:
        w = self.pm.stringWidth(text, self.name(face), size)
        return w + (len(text) - 1) * track * size if text and track else w

    def metrics(self, face: str) -> tuple:
        """``(ascent, descent)`` per point of size, descent as a positive number."""
        n = self.name(face)
        try:
            a, d = self.pm.getAscent(n) / 1000.0, -self.pm.getDescent(n) / 1000.0
        except Exception:
            a, d = 0.75, 0.25
        if a <= 0 or a > 1.4:
            a = 0.75
        if d < 0 or d > 0.8:
            d = 0.25
        return a, d

    def wrap(self, text: str, face: str, size: float, width: float, track: float = 0.0) -> list:
        """Greedy line breaks at spaces. A word wider than the line is broken by letters, so nothing runs off."""
        words = [w for w in re.split(r"\s+", (text or "").strip()) if w]
        lines, cur = [], ""
        for w in words:
            trial = f"{cur} {w}" if cur else w
            if self.width(trial, face, size, track) <= width + 0.01 or not cur:
                if not cur and self.width(w, face, size, track) > width:
                    piece = ""
                    for ch in w:
                        if self.width(piece + ch, face, size, track) > width and piece:
                            lines.append(piece)
                            piece = ch
                        else:
                            piece += ch
                    cur = piece
                else:
                    cur = trial
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines

    def css(self, face: str) -> str:
        f = self.faces.get(face) or self.faces.get("body") or {}
        return f.get("css") or "sans-serif"

    def weight(self, face: str) -> int:
        f = self.faces.get(face) or {}
        return int(f.get("weight") or (700 if face == "body_bold" else 400))

    def style(self, face: str) -> str:
        f = self.faces.get(face) or {}
        return f.get("style") or ("italic" if face == "body_italic" else "normal")


TYPE_FLOOR = 10.0  # the smallest type a slide sets, in points


def baseline(top: float, size: float, lead: float, asc: float, desc: float) -> float:
    """Where the first line's baseline sits: the glyphs centered in the line box, the way a browser sets them,
    so the pane, the SVG, the PNG and the PDF agree."""
    return top + (lead - (asc + desc) * size) / 2 + asc * size


class Canvas:
    """A scene being composed. ``text`` measures, fits and places one block of type."""

    def __init__(self, ty: Type, w: float, h: float, ground: str):
        self.ty, self.w, self.h = ty, w, h
        self.scene = {"w": w, "h": h, "bg": ground, "els": [], "long": False}

    @property
    def els(self) -> list:
        return self.scene["els"]

    def rect(self, x, y, w, h, fill, **kw):
        if fill and w > 0 and h > 0:
            self.els.append({"t": "rect", "x": x, "y": y, "w": w, "h": h, "fill": fill, **kw})

    def dot(self, x, y, d, fill):
        self.els.append({"t": "dot", "x": x - d / 2, "y": y - d / 2, "w": d, "h": d, "fill": fill})

    def image(self, x, y, w, h, name):
        self.els.append({"t": "image", "x": x, "y": y, "w": w, "h": h, "name": name})

    def logo(self, x, y, h, place, align="left", max_w=180.0, ratio=None):
        w = min(max_w, h * (ratio or 3.0))
        self.els.append({"t": "logo", "x": x if align == "left" else x - w, "y": y, "w": w, "h": h, "place": place, "align": align})

    def text(self, text, x, y, w, h, face="body", size=30.0, min_size=None, lead=1.2, color="#000000", align="left",
             track=0.0, upper=False, marks="", anchor="top", role="", max_lines=None, field="", spill=False):
        """Set ``text`` in the box: as large as ``size`` and no smaller than ``min_size``, broken into lines that fit
        the width, and moved down for ``anchor`` bottom or middle. Returns the element (with ``bottom``, where its
        last line ends). A block that still runs past its box at the smallest size marks the scene long.

        Words are never cut. A block with more lines than ``max_lines`` at ``min_size`` steps on down to the type
        floor; if it still does not fit, ``spill`` keeps the whole sentences that fit and hands the rest back in
        ``rest`` for the caller to set elsewhere, and without ``spill`` every line is kept and the scene marked long."""
        text = (text or "").strip()
        if upper:
            text = text.upper()
        min_size = min_size or size
        floor = min(min_size, max(TYPE_FLOOR, min_size * 0.8)) if max_lines else min_size
        s = size
        while True:
            lines = self._lines(text, face, s, w, track, marks)
            lh = s * lead
            over = bool(max_lines) and len(lines) > max_lines
            fits = len(lines) * lh <= h + 0.5 and not over
            if fits or s <= floor or (s <= min_size and not over):
                break
            s = max(floor if over else min_size, s - max(1.0, s * 0.06))
        lh = s * lead
        if 2 <= len(lines) <= 4:
            lines = self._balance(text, face, s, w, track, marks, lines)
        elif len(lines) > 4 and len(lines[-1].split()) == 1:
            for k in (0.97, 0.94, 0.91):
                trial = self._lines(text, face, s, w * k, track, marks)
                if len(trial) == len(lines) and len(trial[-1].split()) > 1:
                    lines = trial
                    break
        rest = ""
        if max_lines and len(lines) > max_lines:
            keep = self._whole_sentences(text, face, s, w, track, marks, max_lines) if spill else ""
            if keep:
                rest = text[len(keep):].strip()
                lines = self._lines(keep, face, s, w, track, marks)
            else:
                self.scene["long"] = True  # every word kept: running long is better than a cut sentence
        total = len(lines) * lh
        if total > h + 0.5:
            self.scene["long"] = True
        top = y + (h - total if anchor == "bottom" else (h - total) / 2 if anchor == "middle" else 0)
        el = {"t": "text", "x": x, "y": top, "w": w, "h": total, "lines": lines or [""], "face": face, "size": round(s, 2),
              "lead": round(lh, 2), "color": color, "align": align, "track": track, "marks": marks, "role": role, "field": field}
        if marks:
            el["mcolor"] = _quiet(color, self.scene["bg"])
        el["bottom"] = top + total
        if rest:
            el["rest"] = rest
        self.els.append(el)
        return el

    def _whole_sentences(self, text, face, size, w, track, marks, max_lines) -> str:
        """The longest run of whole sentences from the start of ``text`` that sets in ``max_lines`` lines, or ""."""
        ends = [m.end() for m in re.finditer(r"[.!?;:](?=\s|$)", text)]
        best = ""
        for e in ends:
            part = text[:e].strip()
            if part and len(self._lines(part, face, size, w, track, marks)) <= max_lines:
                best = part
            else:
                break
        return best if best and best != text else ""

    def _balance(self, text, face, size, w, track, marks, lines):
        """A short block (two to four lines) broken so its lines run about even: no word left alone on the last
        line, the way a typesetter rags a headline."""
        n = len(lines)
        longest = max((self.ty.width(wd, face, size, track) for wd in (text or "").split()), default=0.0)
        if longest > w:
            return lines
        lo, hi = max(w * 0.5, longest + 0.5), w
        for _ in range(12):
            mid = (lo + hi) / 2
            if len(self._lines(text, face, size, mid, track, marks)) <= n:
                hi = mid
            else:
                lo = mid
        out = self._lines(text, face, size, hi + 0.5, track, marks)
        return out if len(out) == n else lines

    def _lines(self, text, face, size, w, track, marks):
        """Lines for the box, leaving room on the last one for the source mark that follows it."""
        lines = self.ty.wrap(text, face, size, w, track)
        if marks and lines:
            room = self.ty.width("\u2009" + marks, face, size * 0.5)
            last = lines[-1]
            if self.ty.width(last, face, size, track) + room > w:
                words = last.split(" ")
                if len(words) > 1:
                    lines[-1:] = [" ".join(words[:-1]), words[-1]]
        return lines

    def measure(self, text, face, size, w, lead=1.2, track=0.0, upper=False) -> float:
        t = (text or "").upper() if upper else (text or "")
        return len(self.ty.wrap(t, face, size, w, track)) * size * lead

    def done(self, **extra) -> dict:
        self.scene.update(extra)
        return self.scene


def _quiet(color: str, ground: str) -> str:
    """The source mark's color: the text's own color stepped toward the ground, so the marks sit back from the words
    and never read as part of a number, still 3:1 on the ground."""
    try:
        from . import colors as C
    except ImportError:  # loaded loose
        import colors as C  # type: ignore
    try:
        t = 0.42
        q = C.mix(color, ground, t)
        while C.contrast(q, ground) < 3.0 and t > 0.05:
            t -= 0.06
            q = C.mix(color, ground, t)
        return q
    except Exception:
        return color


# ---------------------------------------------------------------- the pane --

def _pct(v: float, of: float) -> str:
    return f"{100.0 * v / of:.3f}"


def nodes(scene: dict, ty: Type, cls: str = "ip-scene", images: Optional[dict] = None, logos: Optional[dict] = None,
          extra_class: str = "") -> dict:
    """The scene as positioned nodes for the pane. Sizes are container units of the slide's own width, so the
    preview is the export at any column width. Text stays text (numbers can be traced); nothing is HTML."""
    W, H = scene["w"], scene["h"]
    kids = []
    for el in scene["els"]:
        t = el["t"]
        box = {"--x": _pct(el["x"], W), "--y": _pct(el["y"], H), "--w": _pct(el["w"], W), "--h": _pct(el["h"], H)}
        if t in ("rect", "dot"):
            st = {**box, "--c": el["fill"]}
            if el.get("op") is not None:
                st["--op"] = str(el["op"])
            kids.append({"t": "div", "c": "ip-sc-r" + (" is-dot" if t == "dot" else ""), "a": {"style": st}})
        elif t == "image":
            src = (images or {}).get(el.get("name"))
            if src:
                kids.append({"t": "img", "c": "ip-sc-i", "a": {"src": src, "style": box}})
        elif t == "logo":
            src = (logos or {}).get(el.get("place")) or (logos or {}).get("paper")
            if src:
                # the box is a div holding the picture: every renderer that walks these nodes keeps a div's place
                # (some drop an img's style, which left the logo at the top left over the kicker)
                kids.append({"t": "div", "c": "ip-sc-l" + (" is-right" if el.get("align") == "right" else ""), "a": {"style": box},
                             "k": [{"t": "img", "c": "ip-sc-lg", "a": {"src": src}}]})
        elif t == "text":
            face = el["face"]
            style = {**box, "--fs": f"{100.0 * el['size'] / W:.3f}", "--lh": f"{100.0 * el['lead'] / W:.3f}",
                     "--c": el["color"], "--ff": ty.css(face), "--fw": str(ty.weight(face)), "--fst": ty.style(face),
                     "--ls": f"{el.get('track') or 0}em", "--ta": el.get("align") or "left"}
            lines = []
            n = len(el["lines"])
            for i, ln in enumerate(el["lines"]):
                node = {"t": "span", "c": "ip-ln", "x": ln}
                if i == n - 1 and el.get("marks"):
                    node["k"] = [{"t": "sup", "c": "ip-ref", "x": el["marks"]}]
                lines.append(node)
            if el.get("marks") and el.get("mcolor"):
                style["--mc"] = el["mcolor"]
            tag = "h2" if el.get("role") == "title" else "p"
            kids.append({"t": tag, "c": "ip-sc-t", "a": {"style": style}, "k": lines})
    return {"t": "div", "c": f"{cls} {extra_class}".strip(), "a": {"style": {"--bg": scene["bg"], "--ar": f"{W} / {H}"}}, "k": kids}


SCENE_CSS = """
.ip-deck{display:grid;grid-template-columns:minmax(0,1fr);gap:22px}
.ip-visual{display:grid;justify-items:center}
.ip-visual>.ip-scene{max-width:100%}
.ip-scene{position:relative;width:100%;aspect-ratio:var(--ar);background:var(--bg);overflow:hidden;container-type:inline-size;
  box-shadow:0 0 0 1px rgba(0,0,0,.14),0 1px 2px rgba(0,0,0,.12)}
.ip-scene>*{position:absolute;left:calc(var(--x)*1%);top:calc(var(--y)*1%);width:calc(var(--w)*1%);margin:0}
.ip-sc-r,.ip-sc-i,.ip-sc-l{height:calc(var(--h)*1%)}
.ip-sc-r{background:var(--c);opacity:var(--op,1)}
.ip-sc-r.is-dot{border-radius:50%}
.ip-sc-i{object-fit:cover}
.ip-sc-l>img{--h:100;display:block;position:static;width:100%;height:100%;max-width:none;object-fit:contain;object-position:left center}
.ip-sc-l.is-right>img{object-position:right center}
.ip-sc-t{font-size:calc(var(--fs)*1cqw);line-height:calc(var(--lh)*1cqw);color:var(--c);font-family:var(--ff);font-weight:var(--fw);
  font-style:var(--fst);letter-spacing:var(--ls);text-align:var(--ta);padding:0;font-kerning:normal;font-feature-settings:"kern"}
.ip-sc-t .ip-ln{display:block;white-space:nowrap;min-height:calc(var(--lh)*1cqw)}
.ip-sc-t .ip-ref{font-size:.5em;vertical-align:.7em;line-height:0;margin-left:.12em;letter-spacing:0;color:var(--mc,inherit)}
"""


# ---------------------------------------------------------------- SVG --

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _line_x(el: dict, width: float) -> float:
    a = el.get("align") or "left"
    if a == "center":
        return el["x"] + (el["w"] - width) / 2
    if a == "right":
        return el["x"] + el["w"] - width
    return el["x"]


def svg(scene: dict, ty: Type, images: Optional[dict] = None, logos: Optional[dict] = None, title: str = "") -> str:
    """A standalone SVG: the faces it uses are embedded, pictures and logos are data URLs, text stays text."""
    W, H = scene["w"], scene["h"]
    used = sorted({el["face"] for el in scene["els"] if el["t"] == "text"})
    css = []
    for face in used:
        f = ty.faces.get(face) or {}
        if f.get("file"):
            data = base64.b64encode(open(f["file"], "rb").read()).decode("ascii")
            css.append(f"@font-face{{font-family:'imp-{f['key']}';src:url(data:font/ttf;base64,{data}) format('truetype');"
                       f"font-weight:{f.get('weight') or 400};font-style:{f.get('style') or 'normal'}}}")
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}" width="{W:g}" height="{H:g}" role="img"'
           + (f' aria-label="{_esc(title)}"' if title else "") + ">"]
    if title:
        out.append(f"<title>{_esc(title)}</title>")
    if css:
        out.append("<style>" + "".join(css) + "</style>")
    out.append(f'<rect width="{W:g}" height="{H:g}" fill="{scene["bg"]}"/>')
    for el in scene["els"]:
        t = el["t"]
        if t == "rect":
            op = f' fill-opacity="{el["op"]}"' if el.get("op") is not None else ""
            out.append(f'<rect x="{el["x"]:.2f}" y="{el["y"]:.2f}" width="{el["w"]:.2f}" height="{el["h"]:.2f}" fill="{el["fill"]}"{op}/>')
        elif t == "dot":
            r = el["w"] / 2
            out.append(f'<circle cx="{el["x"] + r:.2f}" cy="{el["y"] + r:.2f}" r="{r:.2f}" fill="{el["fill"]}"/>')
        elif t in ("image", "logo"):
            src = (images or {}).get(el.get("name")) if t == "image" else ((logos or {}).get(el.get("place")) or (logos or {}).get("paper"))
            if src:
                fit = "xMidYMid slice" if t == "image" else ("xMaxYMid meet" if el.get("align") == "right" else "xMinYMid meet")
                out.append(f'<image x="{el["x"]:.2f}" y="{el["y"]:.2f}" width="{el["w"]:.2f}" height="{el["h"]:.2f}" '
                           f'preserveAspectRatio="{fit}" href="{src}"/>')
        elif t == "text":
            f = ty.faces.get(el["face"]) or {}
            fam = f"'imp-{f['key']}', " if f.get("key") else ""
            fam += (f.get("css") or "sans-serif").split(",", 1)[-1].strip() if f.get("key") else (f.get("css") or "sans-serif")
            asc, desc = ty.metrics(el["face"])
            y0 = baseline(el["y"], el["size"], el["lead"], asc, desc)
            sp = f' letter-spacing="{el["track"] * el["size"]:.2f}"' if el.get("track") else ""
            for i, ln in enumerate(el["lines"]):
                wd = ty.width(ln, el["face"], el["size"], el.get("track") or 0)
                x = _line_x(el, wd + (_mark_w(el, ty) if i == len(el["lines"]) - 1 else 0))
                mark = ""
                if i == len(el["lines"]) - 1 and el.get("marks"):
                    mc = el.get("mcolor") or el["color"]
                    mark = f'<tspan baseline-shift="super" font-size="{el["size"] * 0.5:.2f}" fill="{mc}"> {_esc(el["marks"])}</tspan>'
                out.append(f'<text x="{x:.2f}" y="{y0 + i * el["lead"]:.2f}" font-family="{_esc(fam)}" font-size="{el["size"]:.2f}" '
                           f'font-weight="{ty.weight(el["face"])}" font-style="{ty.style(el["face"])}" fill="{el["color"]}"{sp}>'
                           f"{_esc(ln)}{mark}</text>")
    out.append("</svg>")
    return "\n".join(out)


def _mark_w(el: dict, ty: Type) -> float:
    return ty.width(" " + el["marks"], el["face"], el["size"] * 0.5) if el.get("marks") else 0.0


# ---------------------------------------------------------------- PNG --

PNG_FALLBACK = {"serif": "crimson-pro-400.ttf", "sans": "inter-400.ttf", "mono": "courier-prime-400.ttf"}


def _png_font(ty: Type, face: str, px: float):
    from PIL import ImageFont
    f = ty.faces.get(face) or {}
    path = f.get("file")
    if not path:
        from pathlib import Path
        here = Path(__file__).resolve().parent / "fonts"
        pdf = (f.get("pdf") or "").lower()
        cls = "serif" if "times" in pdf else "mono" if "courier" in pdf else "sans"
        name = PNG_FALLBACK[cls]
        if "bold" in pdf and cls == "sans":
            name = "inter-700.ttf"
        path = str(here / name)
    return ImageFont.truetype(path, max(1, int(round(px))))


def png(scene: dict, ty: Type, scale: float = 2.0, pictures: Optional[dict] = None, logos: Optional[dict] = None) -> bytes:
    """The scene as a PNG, ``scale`` pixels per point. ``pictures`` and ``logos`` hold image bytes."""
    from PIL import Image, ImageDraw
    W, H = int(round(scene["w"] * scale)), int(round(scene["h"] * scale))
    im = Image.new("RGB", (W, H), scene["bg"])
    dr = ImageDraw.Draw(im)
    S = lambda v: v * scale
    for el in scene["els"]:
        t = el["t"]
        if t == "rect" and el.get("op") is not None:
            box = [int(S(el["x"])), int(S(el["y"])), int(S(el["x"] + el["w"])), int(S(el["y"] + el["h"]))]
            layer = Image.new("RGBA", (max(1, box[2] - box[0]), max(1, box[3] - box[1])), el["fill"])
            layer.putalpha(int(255 * float(el["op"])))
            base = im.crop(box).convert("RGBA")
            im.paste(Image.alpha_composite(base, layer).convert("RGB"), box[:2])
            dr = ImageDraw.Draw(im)
        elif t == "rect":
            x0, y0 = S(el["x"]), S(el["y"])
            dr.rectangle([x0, y0, max(x0, S(el["x"] + el["w"]) - 1), max(y0, S(el["y"] + el["h"]) - 1)], fill=el["fill"])
        elif t == "dot":
            dr.ellipse([S(el["x"]), S(el["y"]), S(el["x"] + el["w"]), S(el["y"] + el["h"])], fill=el["fill"])
        elif t in ("image", "logo"):
            data = (pictures or {}).get(el.get("name")) if t == "image" else ((logos or {}).get(el.get("place")) or (logos or {}).get("paper"))
            if not data:
                continue
            try:
                src = Image.open(io.BytesIO(data)).convert("RGBA")
            except Exception:
                continue
            bw, bh = int(S(el["w"])), int(S(el["h"]))
            if t == "image":
                k = max(bw / src.width, bh / src.height)
                src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
                l, tp = (src.width - bw) // 2, (src.height - bh) // 2
                src = src.crop((l, tp, l + bw, tp + bh))
                im.paste(src.convert("RGB"), (int(S(el["x"])), int(S(el["y"]))))
            else:
                k = min(bw / src.width, bh / src.height)
                src = src.resize((max(1, int(src.width * k)), max(1, int(src.height * k))), Image.LANCZOS)
                x = int(S(el["x"])) if el.get("align") != "right" else int(S(el["x"] + el["w"])) - src.width
                im.paste(src, (x, int(S(el["y"])) + (bh - src.height) // 2), src)
        elif t == "text":
            font = _png_font(ty, el["face"], S(el["size"]))
            asc, desc = ty.metrics(el["face"])
            y0 = baseline(el["y"], el["size"], el["lead"], asc, desc)
            track = (el.get("track") or 0) * S(el["size"])
            for i, ln in enumerate(el["lines"]):
                wd = ty.width(ln, el["face"], el["size"], el.get("track") or 0)
                last = i == len(el["lines"]) - 1
                x = S(_line_x(el, wd + (_mark_w(el, ty) if last else 0)))
                y = S(y0 + i * el["lead"])
                if track:
                    for ch in ln:
                        dr.text((x, y), ch, font=font, fill=el["color"], anchor="ls")
                        x += font.getlength(ch) + track
                else:
                    dr.text((x, y), ln, font=font, fill=el["color"], anchor="ls")
                    x += font.getlength(ln)
                if last and el.get("marks"):
                    small = _png_font(ty, el["face"], S(el["size"]) * 0.5)
                    dr.text((x + S(el["size"]) * 0.12, y - S(el["size"]) * 0.36), el["marks"], font=small, fill=el.get("mcolor") or el["color"], anchor="ls")
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- PDF --

def draw_pdf(c, scene: dict, ty: Type, pictures: Optional[dict] = None, logos: Optional[dict] = None) -> None:
    """Draw the scene on the current reportlab page (the page is the scene's size)."""
    from reportlab.lib import colors as rlc
    from reportlab.lib.utils import ImageReader
    H = scene["h"]
    hx = rlc.HexColor
    c.setFillColor(hx(scene["bg"]))
    c.rect(0, 0, scene["w"], H, stroke=0, fill=1)
    for el in scene["els"]:
        t = el["t"]
        if t == "rect":
            c.setFillColor(hx(el["fill"]))
            if el.get("op") is not None:
                c.saveState()
                c.setFillAlpha(float(el["op"]))
            c.rect(el["x"], H - el["y"] - el["h"], el["w"], el["h"], stroke=0, fill=1)
            if el.get("op") is not None:
                c.restoreState()
        elif t == "dot":
            c.setFillColor(hx(el["fill"]))
            r = el["w"] / 2
            c.circle(el["x"] + r, H - el["y"] - r, r, stroke=0, fill=1)
        elif t in ("image", "logo"):
            data = (pictures or {}).get(el.get("name")) if t == "image" else ((logos or {}).get(el.get("place")) or (logos or {}).get("paper"))
            if not data:
                continue
            try:
                if t == "image":
                    from PIL import Image
                    src = Image.open(io.BytesIO(data)).convert("RGB")
                    k = max(el["w"] / src.width, el["h"] / src.height)
                    cw, ch = el["w"] / k, el["h"] / k
                    l, tp = (src.width - cw) / 2, (src.height - ch) / 2
                    src = src.crop((int(l), int(tp), int(l + cw), int(tp + ch)))
                    buf = io.BytesIO()
                    src.save(buf, "JPEG", quality=88)
                    buf.seek(0)
                    c.drawImage(ImageReader(buf), el["x"], H - el["y"] - el["h"], width=el["w"], height=el["h"])
                else:
                    img = ImageReader(io.BytesIO(data))
                    iw, ih = img.getSize()
                    k = min(el["w"] / iw, el["h"] / ih)
                    w, h = iw * k, ih * k
                    x = el["x"] if el.get("align") != "right" else el["x"] + el["w"] - w
                    c.drawImage(img, x, H - el["y"] - el["h"] + (el["h"] - h) / 2, width=w, height=h, mask="auto")
            except Exception:
                continue
        elif t == "text":
            name = ty.name(el["face"])
            # A brand face that isn't on this machine falls back to a built-in PDF face, which can only draw the
            # Windows Latin set: anything else would print as a black box, so it is dropped (thin spaces, joiners).
            try:
                from reportlab.pdfbase.ttfonts import TTFont
                base14 = not isinstance(ty.pm.getFont(name), TTFont)
            except Exception:
                base14 = True
            el = {**el, "lines": [_latin(x) for x in el["lines"]], "marks": _latin(el.get("marks") or "")} if base14 else el
            asc, desc = ty.metrics(el["face"])
            y0 = baseline(el["y"], el["size"], el["lead"], asc, desc)
            track = (el.get("track") or 0) * el["size"]
            c.setFillColor(hx(el["color"]))
            for i, ln in enumerate(el["lines"]):
                wd = ty.width(ln, el["face"], el["size"], el.get("track") or 0)
                last = i == len(el["lines"]) - 1
                x = _line_x(el, wd + (_mark_w(el, ty) if last else 0))
                y = H - (y0 + i * el["lead"])
                tx = c.beginText(x, y)
                tx.setFont(name, el["size"])
                tx.setCharSpace(track)  # always set: the PDF's character spacing carries over from one text block to the next
                tx.textOut(ln)
                if last and el.get("marks"):
                    tx.setCharSpace(0)
                    tx.setFont(name, el["size"] * 0.5)
                    tx.setRise(el["size"] * 0.36)
                    tx.setFillColor(rlc.HexColor(el.get("mcolor") or el["color"]))
                    tx.textOut(" " + _latin(el["marks"]).strip())  # a thin space prints as a box in some faces
                    tx.setRise(0)
                c.drawText(tx)


def _latin(s: str) -> str:
    s = (s or "").replace("\u2009", " ").replace("\u202f", " ").replace("\u00a0", " ")
    return s.encode("cp1252", "ignore").decode("cp1252")


def text_of(scene: dict) -> str:
    return "\n".join(" ".join(el["lines"]) for el in scene["els"] if el["t"] == "text")
