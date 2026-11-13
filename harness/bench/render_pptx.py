"""Render a .pptx to one PNG per slide without PowerPoint or Keynote: macOS Quick Look, then headless Chrome.

    /usr/bin/python3 harness/bench/render_pptx.py DECK.pptx OUT_DIR

How, and its limits (state these wherever the PNGs are judged):
1. A copy of the deck with its speaker notes removed: Quick Look's Office generator refuses any deck that has notes
   ("did not produce any preview"), and notes never show on a slide, so nothing visible changes.
2. ``qlmanage -p -o`` writes Apple's own HTML conversion of every slide (the OfficeImport framework, the same one
   Quick Look and the Finder preview use): shapes, fills, text with fonts and sizes, pictures, and each chart as a
   PDF image it draws itself, which ``qlmanage -t`` turns into a PNG at 1600 px.
3. Headless Chrome (muted, no autoplay) screenshots each slide alone at 2x.
4. Charts: Quick Look draws charts in its own default style (blue bars, axes and gridlines shown, point colors and
   data label formats dropped), which would misrepresent the deck. So each clustered bar or column chart is drawn
   from the chart's own XML instead (``chart_png``: categories, values, series and point colors, data labels with
   their number format, label sizes and colors, axis visibility, gridlines), in Arial or Georgia.
Limits: Apple's converter, not PowerPoint. A font the Mac lacks (Calibri, for one) falls back to a system face, as
it would on any Mac without Office. Gradients, shadows and some chart styling can come out simpler than in
PowerPoint. This is how the deck looks to a person on a Mac opening it with the space bar.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from childenv import child_env  # noqa: E402  only the allowlisted names reach the programs started here

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def strip_notes(src: Path, dst: Path) -> None:
    from pptx import Presentation
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    p = Presentation(str(src))
    for slide in p.slides:
        for rid, rel in list(slide.part.rels.items()):
            if rel.reltype == RT.NOTES_SLIDE:
                slide.part.drop_rel(rid)
    p.save(str(dst))


FONTS = {"serif": "/System/Library/Fonts/Supplemental/Georgia.ttf", "serif-bold": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
         "sans": "/System/Library/Fonts/Supplemental/Arial.ttf", "sans-bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"}
NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart", "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
OFFICE_ACCENT1 = "#4472C4"
OFFICE_ACCENTS = (OFFICE_ACCENT1, "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47")


def _font(name: str, bold: bool, px: float):
    from PIL import ImageFont
    serif = any(k in (name or "").lower() for k in ("georgia", "times", "garamond", "serif", "cambria", "palatino"))
    return ImageFont.truetype(FONTS[("serif" if serif else "sans") + ("-bold" if bold else "")], max(6, int(round(px))))


def _fmt(v: float, fmt: str) -> str:
    """An Excel number format, the common cases: "#,##0", "$#,##0", "0%", "0.0", "#,##0.00", General."""
    if fmt is None or fmt == "General" or not re.search(r"[0#]", fmt or ""):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:g}"
    f0 = fmt.split(";")[0]
    pct = "%" in re.sub(r'"[^"]*"', "", f0).replace("\\%", "")  # a quoted or escaped "%" is a literal sign, not x100
    f = f0.replace('"', "").replace("\\", "")
    m = re.search(r"[#0][#0,]*(?:\.0+)?", f)
    pre, core, post = f[:m.start()], m.group(0), f[m.end():]
    scale = len(core) - len(core.rstrip(","))  # commas after the last digit scale by thousands: '#,##0,"K"' is 640K
    if scale:
        core = core.rstrip(",")
        v = v / (1000 ** scale)
    dec = len(core.split(".")[1]) if "." in core else 0
    if pct and "%" in post:
        v = v * 100
    body = f"{v:,.{dec}f}" if "," in core else f"{v:.{dec}f}"
    return pre + body + post


def _srgb(el) -> str:
    if el is None:
        return ""
    c = el.find(".//a:solidFill/a:srgbClr", NS)
    return f"#{c.get('val')}" if c is not None else ""


def _txt(el, default_px: float, scale: float) -> tuple:
    """(size px, bold, color, face) from a chart text property block."""
    size, bold, color, face = default_px, False, "#595959", ""
    if el is not None:
        rp = el.find(".//a:defRPr", NS)
        if rp is not None:
            if rp.get("sz"):
                size = int(rp.get("sz")) / 100 * scale
            bold = rp.get("b") == "1"
            col = rp.find("a:solidFill/a:srgbClr", NS)
            if col is not None:
                color = "#" + col.get("val")
            lat = rp.find("a:latin", NS)
            if lat is not None:
                face = lat.get("typeface", "")
    return size, bold, color, face


def chart_png(gf, scale: float) -> bytes:
    """A clustered bar or column chart drawn from its own XML: categories, values, the series and per-point fill
    colors, data labels with their number format, label font sizes and colors, axis visibility, gridlines and the
    category axis line. 1 pt = ``scale`` px. Quick Look draws charts in its default style and drops these."""
    from PIL import Image, ImageDraw
    import io
    ch = gf.chart
    cs = ch._chartSpace
    W, H = int(gf.width / 12700 * scale), int(gf.height / 12700 * scale)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = _txt(cs.find("c:txPr", NS), 10 * scale, scale)
    plot = ch.plots[0]
    horizontal = cs.find(".//c:barDir", NS) is not None and cs.find(".//c:barDir", NS).get("val") == "bar"
    cats = [str(c) for c in plot.categories]
    # Every series of a clustered chart (round 6: a two-series chart was drawn with its first series only).
    SERIES = []
    for si, ser in enumerate(plot.series):
        ser_el = ser._element
        sf = _srgb(ser_el.find("c:spPr", NS)) or OFFICE_ACCENTS[si % len(OFFICE_ACCENTS)]
        pf = {}
        for dpt in ser_el.findall("c:dPt", NS):
            pf[int(dpt.find("c:idx", NS).get("val"))] = _srgb(dpt.find("c:spPr", NS)) or sf
        SERIES.append((str(ser.name or ""), [float(v or 0) for v in ser.values], sf, pf))
    vals = [v for _n, vs, _f, _p in SERIES for v in vs]
    K_ = len(SERIES)
    dls = cs.find(".//c:dLbls", NS)
    on = lambda el: el is not None and el.get("val") in (None, "1", "true")  # a bare <c:delete/> means true
    show_val = dls is not None and on(dls.find("c:showVal", NS))
    nf = dls.find("c:numFmt", NS) if dls is not None else None
    fmt = nf.get("formatCode") if nf is not None else "General"
    lab = _txt(dls.find("c:txPr", NS) if dls is not None else None, base[0], scale)
    lab = (lab[0], lab[1], lab[2] if lab[2] != "#595959" else base[2], lab[3] or base[3])
    cat_ax, val_ax = cs.find(".//c:catAx", NS), cs.find(".//c:valAx", NS)
    deleted = lambda ax: ax is not None and on(ax.find("c:delete", NS))
    val_visible = val_ax is not None and not deleted(val_ax)
    grid = val_ax is not None and val_ax.find("c:majorGridlines", NS) is not None
    cat_t = _txt(cat_ax.find("c:txPr", NS) if cat_ax is not None else None, base[0], scale)
    cat_t = (cat_t[0], cat_t[1], cat_t[2] if cat_t[2] != "#595959" else base[2], cat_t[3] or base[3])
    cat_line = _srgb(cat_ax.find("c:spPr", NS) if cat_ax is not None else None)
    gap = 150
    g = cs.find(".//c:gapWidth", NS)
    if g is not None:
        gap = int(g.get("val"))
    top = max(vals + [0]) or 1
    legend = cs.find(".//c:legend", NS) is not None and K_ > 1
    mn = val_ax.find(".//c:max", NS) if val_ax is not None else None
    if mn is not None:
        top = float(mn.get("val"))
    else:  # PowerPoint's automatic maximum: a round major unit, about five of them, a little above the top value
        import math
        raw = top * 1.05 / 5
        mag = 10 ** math.floor(math.log10(raw))
        step = next(k * mag for k in (1, 2, 2.5, 5, 10) if k * mag >= raw)
        top = math.ceil(top * 1.05 / step) * step
    fl = _font(lab[3], lab[1], lab[0])
    fc = _font(cat_t[3], cat_t[1], cat_t[0])
    fv = _font(base[3], False, base[0] * 0.9)
    pad = 6 * scale
    n = len(cats)
    if not horizontal:
        left = pad + (max(d.textlength(_fmt(top, "#,##0"), font=fv) for _ in [0]) + 6 * scale if val_visible else 0)
        right, tp = W - pad, pad + lab[0] * 1.6
        bottom = H - pad - cat_t[0] * 1.5
        if grid or val_visible:
            for k in range(6):
                v = top * k / 5
                y = bottom - (bottom - tp) * k / 5
                if grid:
                    d.line([(left, y), (right, y)], fill="#D9D9D9", width=max(1, int(scale * 0.75)))
                if val_visible:
                    t = _fmt(v, "#,##0")
                    d.text((left - 6 * scale - d.textlength(t, font=fv), y - base[0] * 0.5), t, font=fv, fill=base[2])
        if legend:
            tp += cat_t[0] * 1.6
        slot = (right - left) / n
        gw = slot / (1 + gap / 100)
        bw = gw / K_
        for i, c in enumerate(cats):
            g0 = left + slot * i + (slot - gw) / 2
            for k, (_nm, vs, sf, pf) in enumerate(SERIES):
                v = vs[i] if i < len(vs) else 0
                x0 = g0 + bw * k
                y0 = bottom - (bottom - tp) * (v / top)
                d.rectangle([x0, y0, x0 + bw * (0.92 if K_ > 1 else 1), bottom], fill=pf.get(i, sf))
                if show_val:
                    t = _fmt(v, fmt)
                    d.text((x0 + bw / 2 - d.textlength(t, font=fl) / 2, y0 - lab[0] * 1.3), t, font=fl, fill=lab[2])
            tw = d.textlength(c, font=fc)
            d.text((g0 + gw / 2 - tw / 2, bottom + cat_t[0] * 0.3), c, font=fc, fill=cat_t[2])
        if legend:
            x = left
            for nm, _vs, sf, _pf in SERIES:
                sw = cat_t[0] * 0.9
                d.rectangle([x, pad, x + sw, pad + sw], fill=sf)
                d.text((x + sw * 1.4, pad - cat_t[0] * 0.1), nm, font=fc, fill=cat_t[2])
                x += sw * 1.4 + d.textlength(nm, font=fc) + 16 * scale
        d.line([(left, bottom), (right, bottom)], fill=cat_line or "#D9D9D9", width=max(1, int(scale)))
    else:
        lw = max(d.textlength(c, font=fc) for c in cats) + 10 * scale
        left, right = pad + lw, W - pad - max(d.textlength(_fmt(v, fmt), font=fl) for v in vals) - 8 * scale
        tp, bottom = pad, H - pad - (base[0] * 1.5 if val_visible else 0)
        slot = (bottom - tp) / n
        bw = slot / (1 + gap / 100)
        order = list(range(n))
        rev = cat_ax is not None and cat_ax.find(".//c:orientation", NS) is not None and cat_ax.find(".//c:orientation", NS).get("val") == "maxMin"
        gw = bw
        bw = gw / K_
        for row, i in enumerate(order if rev else order[::-1]):
            g0 = tp + slot * row + (slot - gw) / 2
            for k, (_nm, vs, sf, pf) in enumerate(SERIES if rev else SERIES[::-1]):
                v = vs[i] if i < len(vs) else 0
                y0 = g0 + bw * k
                x1 = left + (right - left) * (v / top)
                d.rectangle([left, y0, x1, y0 + bw * (0.92 if K_ > 1 else 1)], fill=pf.get(i, sf))
                if show_val:
                    d.text((x1 + 6 * scale, y0 + bw / 2 - lab[0] * 0.6), _fmt(v, fmt), font=fl, fill=lab[2])
            c = cats[i]
            d.text((left - 8 * scale - d.textlength(c, font=fc), g0 + gw / 2 - cat_t[0] * 0.6), c, font=fc, fill=cat_t[2])
        d.line([(left, tp), (left, bottom)], fill=cat_line or "#D9D9D9", width=max(1, int(scale)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _chart_boxes(deck: Path) -> dict:
    """``{slide number: [(left, top, width, height in pt, graphic frame)]}`` for every chart in the deck."""
    from pptx import Presentation
    p = Presentation(str(deck))
    out = {}
    for n, slide in enumerate(p.slides, start=1):
        for sh in slide.shapes:
            if getattr(sh, "has_chart", False) and sh.has_chart:
                out.setdefault(n, []).append((sh.left / 12700, sh.top / 12700, sh.width / 12700, sh.height / 12700, sh))
    return out


def render(deck: Path, out: Path) -> list:
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="p6-pptx-"))
    copy = work / "deck.pptx"
    strip_notes(deck, copy)
    (work / "ql").mkdir()
    r = subprocess.run(["qlmanage", "-p", "-o", str(work / "ql"), str(copy)], capture_output=True, text=True, timeout=180, env=child_env())
    prev = work / "ql" / "deck.pptx.qlpreview"
    html = (prev / "Preview.html").read_text(encoding="utf-8") if (prev / "Preview.html").exists() else ""
    if not html:
        raise SystemExit(f"Quick Look made no preview: {r.stdout[-400:]} {r.stderr[-400:]}")
    # Charts and some shapes come as PDF attachments, which Chrome won't draw in an <img>: each one is drawn to a PNG
    # by Quick Look itself (vector, at 1600 px on its long side) and the page points at that instead.
    # Round 2 fix: ``qlmanage -t`` paints a white page behind each shape (an oval came out as a circle on a white
    # square), so each PDF is drawn with ``sips`` instead, which keeps the page transparent.
    for pdf in sorted(prev.glob("*.pdf")):
        png = prev / (pdf.name + ".png")
        subprocess.run(["sips", "-s", "format", "png", "-Z", "1600", str(pdf), "--out", str(png)], capture_output=True, timeout=120, env=child_env())
        if not png.exists():
            subprocess.run(["qlmanage", "-t", "-s", "1600", "-o", str(prev), str(pdf)], capture_output=True, timeout=120, env=child_env())
        if png.exists():
            html = html.replace(f'"{pdf.name}"', f'"{png.name}"')
    m = re.search(r"div\.slide, div\.loading-slide \{ width: (\d+); height: (\d+);\}", html)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (959, 540)
    n = html.count('<div class="slide"')
    charts = _chart_boxes(deck)
    boxes = _shape_boxes(deck)
    shapes = _shape_list(deck)
    hide = ("<style>body{margin:0!important;background:#fff!important}div.slide{display:none!important}"
            "div.slide.show{display:block!important;margin:0!important;-webkit-box-shadow:none!important}"
            "div.loading-slide{display:none!important}</style>")
    files = []
    for i in range(n):
        k = -1
        for _ in range(i + 1):
            k = html.index('<div class="slide"', k + 1)
        page = html[:k] + '<div class="slide show"' + html[k + len('<div class="slide"'):]
        page = page.replace("</head>", hide + "</head>", 1)
        k = page.index('<div class="slide show"')  # round 3: the style above shifts the slide's place in the page
        page = _swap_charts(page, k, i + 1, charts, prev, w)
        page = _own_shapes(page, k, shapes.get(i + 1, []), w)
        f = prev / f"slide-{i + 1:02d}.html"
        f.write_text(page, encoding="utf-8")
        png = out / f"slide-{i + 1:02d}.png"
        prof = work / f"chrome-profile-{i + 1:02d}"  # its own scratch profile, deleted with ``work``: no temp-profile leak
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio", f"--user-data-dir={prof}",
                        "--autoplay-policy=user-gesture-required", "--force-device-scale-factor=2",
                        f"--window-size={w},{h}", "--virtual-time-budget=3000", f"--screenshot={png}", f.as_uri()],
                       capture_output=True, timeout=120, env=child_env())
        shutil.rmtree(prof, ignore_errors=True)
        files.append(png)
    shutil.rmtree(work, ignore_errors=True)
    return files


def _shape_boxes(deck: Path) -> dict:
    """``{slide number: [(left, top, width, height in pt)]}`` for every shape on the slide, groups opened."""
    from pptx import Presentation
    p = Presentation(str(deck))
    out = {}

    def walk(shapes, n):
        for sh in shapes:
            if getattr(sh, "shape_type", None) == 6:  # a group
                walk(sh.shapes, n)
            elif sh.width is not None and sh.left is not None:
                out.setdefault(n, []).append((sh.left / 12700, sh.top / 12700, sh.width / 12700, sh.height / 12700))
    for n, slide in enumerate(p.slides, start=1):
        walk(slide.shapes, n)
    return out


def _drop_phantoms(page: str, start: int, boxes: list, slide_w: int) -> str:
    """Quick Look sometimes repeats a shape image from another slide (a teal oval showed on a slide that has none).
    Each <img> on this slide must sit where one of the slide's own shapes is, or it is taken out."""
    end = page.find('<div class="slide"', start + 10)
    end = len(page) if end < 0 else end
    seg = page[start:end]
    sx = slide_w / 960.0
    def own(t, l, w, h, bl, bt, bw, bh):
        # Quick Look pads a shape's image by the same margin on every side (its outline and effects, up to about
        # 25 pt). Round 3: a phantom card of another size sat within the old loose margin and covered a card's text.
        pads = (bl * sx - l, bt * sx - t, (w - bw * sx) / 2, (h - bh * sx) / 2)
        return all(-3 <= p <= 30 for p in pads) and max(pads) - min(pads) <= 8
    keep = []
    imgs = list(re.finditer(r'<img src="[^"]+" style="position:absolute;[^>]*>', seg))
    at = imgs[0].start() if imgs else -1  # the first image sits after the slide's background, so the rest go there too
    for m in list(re.finditer(r'<img src="[^"]+" style="position:absolute; top:(-?[\d.]+); left:(-?[\d.]+); width:([\d.]+); height:([\d.]+);[^>]*>', seg)):
        t, l, w, h = (float(m.group(j)) for j in (1, 2, 3, 4))
        seg = seg.replace(m.group(0), "", 1)
        if ('src="chart-' in m.group(0) or any(own(t, l, w, h, *b) for b in boxes)) and m.group(0) not in keep:
            keep.append(m.group(0))
    # Round 3: Quick Look writes some shape images after the text that sits on them, so a card painted over its own
    # words. Every shape image goes first, in the order Quick Look gave, and the text paints over it, as in PowerPoint.
    if at >= 0:
        seg = seg[:at] + "".join(keep) + seg[at:]
    return page[:start] + seg + page[end:]


def _swap_charts(page: str, start: int, n: int, charts: dict, prev: Path, slide_w: int) -> str:
    """On slide ``n`` (whose div starts at ``start``), put the chart drawn from its XML in place of Quick Look's
    chart image: the <img> whose box (in Quick Look's points) is closest to the chart frame's box."""
    if n not in charts:
        return page
    end = page.find('<div class="slide"', start + 10)
    end = len(page) if end < 0 else end
    seg = page[start:end]
    sx = slide_w / 960.0  # Quick Look's slide is 959 wide for a 960 pt (13.333 in) slide
    imgs = list(re.finditer(r'<img src="([^"]+)" style="position:absolute; top:(-?[\d.]+); left:(-?[\d.]+); width:([\d.]+); height:([\d.]+);', seg))
    for ci, (l, t, w, h, gf) in enumerate(charts[n]):
        best, bd = None, 1e9
        for m in imgs:
            tt, ll, ww, hh = (float(m.group(j)) for j in (2, 3, 4, 5))
            dist = abs(tt - t * sx) + abs(ll - l * sx) + abs(ww - w * sx) + abs(hh - h * sx)
            if dist < bd:
                best, bd = m, dist
        if best is None or bd > 60:
            continue
        name = f"chart-{n:02d}-{ci}.png"
        (prev / name).write_bytes(chart_png(gf, 4.0))
        seg = seg.replace(f'src="{best.group(1)}"', f'src="{name}"', 1)
    return page[:start] + seg + page[end:]


def _shape_list(deck: Path) -> dict:
    """``{slide number: [shape dicts in z-order]}``: each shape's box in pt, its kind (pic, chart, auto, text), and for
    a plain autoshape (rectangle, rounded rectangle, oval) with no text, the CSS that draws it."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE, MSO_SHAPE
    from pptx.enum.dml import MSO_FILL
    p = Presentation(str(deck))
    out = {}

    def color(fmt):
        try:
            if fmt.type == MSO_FILL.SOLID:
                return "#" + str(fmt.fore_color.rgb)
            if fmt.type == MSO_FILL.BACKGROUND:
                return "transparent"
        except Exception:
            return None
        return None

    def walk(shapes, n):
        for sh in shapes:
            st = getattr(sh, "shape_type", None)
            if st == MSO_SHAPE_TYPE.GROUP:
                walk(sh.shapes, n)
                continue
            if sh.width is None or sh.left is None:
                continue
            d = {"box": (sh.left / 12700, sh.top / 12700, sh.width / 12700, sh.height / 12700), "kind": "text", "css": None}
            if st == MSO_SHAPE_TYPE.PICTURE:
                d["kind"] = "pic"
            elif getattr(sh, "has_chart", False) and sh.has_chart:
                d["kind"] = "chart"
            elif st == MSO_SHAPE_TYPE.AUTO_SHAPE:
                d["kind"] = "auto"
                try:
                    ast = sh.auto_shape_type
                except Exception:
                    ast = None
                fill = color(sh.fill)
                has_text = bool(getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip())
                # a shape with words in it stays Quick Look's: it draws the words inside the shape's own image
                if ast in (MSO_SHAPE.RECTANGLE, MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.OVAL) and fill and not has_text:
                    l, t, w, h = d["box"]
                    css = f"position:absolute; left:{{l}}px; top:{{t}}px; width:{{w}}px; height:{{h}}px; background:{fill};"
                    try:
                        line = color(sh.line.fill)
                        lw = sh.line.width.pt if sh.line.width else 0.75
                    except Exception:
                        line, lw = None, 0
                    if line and line != "transparent":
                        css += f" box-shadow: inset 0 0 0 {lw:.2f}px {line};"
                    if ast == MSO_SHAPE.OVAL:
                        css += " border-radius:50%;"
                    elif ast == MSO_SHAPE.ROUNDED_RECTANGLE:
                        try:
                            adj = sh.adjustments[0] if len(sh.adjustments) else 0.16667
                        except Exception:
                            adj = 0.16667
                        css += f" border-radius:{{r}}px;"
                        d["radius"] = adj * min(w, h)
                    d["css"] = css
            out.setdefault(n, []).append(d)
    for n, slide in enumerate(p.slides, start=1):
        walk(slide.shapes, n)
    return out


_EL = re.compile(r'<img src="[^"]+" style="position:absolute; top:(-?[\d.]+); left:(-?[\d.]+); width:([\d.]+); height:([\d.]+);[^>]*>'
                 r'|<div style="position:absolute; top:(-?[\d.]+); left:(-?[\d.]+); width:([\d.]+); height:([\d.]+);')


def _own_shapes(page: str, start: int, shapes: list, slide_w: int) -> str:
    """Round 3: Quick Look's shape images are not to be trusted. It writes some after the text that sits on them (a
    white card painted over its own words), repeats cards from other slides, and leaves some out, and which ones
    change from run to run. So every plain rectangle, rounded rectangle and oval is drawn here from the deck's own
    XML (its box, fill, outline and corner radius) as a div, placed in the deck's own z-order: just before the first
    element Quick Look wrote for any later shape. Quick Look images are kept only for pictures, charts and any other
    shape we don't draw, and only when their box matches that shape's (Quick Look pads every side alike)."""
    end = page.find('<div class="slide"', start + 10)
    end = len(page) if end < 0 else end
    seg = page[start:end]
    sx = slide_w / 960.0

    def padded(t, l, w, h, b):
        bl, bt, bw, bh = b
        pads = (bl * sx - l, bt * sx - t, (w - bw * sx) / 2, (h - bh * sx) / 2)
        return all(-3 <= q <= 30 for q in pads) and max(pads) - min(pads) <= 8

    def exact(t, l, w, h, b):
        bl, bt, bw, bh = b
        return abs(bl * sx - l) <= 3 and abs(bt * sx - t) <= 3 and abs(bw * sx - w) <= 3 and abs(bh * sx - h) <= 3

    drawn = [i for i, d in enumerate(shapes) if d.get("css")]
    els = []  # (match start, html, is_img, shape index or None)
    taken = set()
    for m in _EL.finditer(seg):
        if m.group(1) is not None:
            t, l, w, h = (float(m.group(j)) for j in (1, 2, 3, 4))
            idx = next((i for i, d in enumerate(shapes) if i not in taken and not d.get("css") and d["kind"] in ("pic", "chart", "auto")
                        and (padded(t, l, w, h, d["box"]) or exact(t, l, w, h, d["box"]))), None)
            if 'src="chart-' in m.group(0):
                idx = next((i for i, d in enumerate(shapes) if d["kind"] == "chart" and i not in taken), idx)
            if idx is not None:
                taken.add(idx)
            els.append((m.start(), m.group(0), True, idx))
        else:
            t, l, w, h = (float(m.group(j)) for j in (5, 6, 7, 8))
            idx = next((i for i, d in enumerate(shapes) if exact(t, l, w, h, d["box"])), None)
            els.append((m.start(), None, False, idx))
    # a plain shape Quick Look drew as a div of its own (a flat rectangle) stays as it is
    as_div = {idx for _s, _h, img, idx in els if not img and idx is not None and shapes[idx].get("css")}
    inserts = {}
    for i in drawn:
        if i in as_div:
            continue
        l, t, w, h = (v * sx for v in shapes[i]["box"])
        css = shapes[i]["css"].replace("{l}", f"{l:.1f}").replace("{t}", f"{t:.1f}").replace("{w}", f"{w:.1f}").replace("{h}", f"{h:.1f}")
        css = css.replace("{r}", f"{shapes[i].get('radius', 0) * sx:.1f}")
        html = f'<div style="{css}"></div>'
        at = next((pos for pos, _h, img, idx in els if idx is not None and idx >= i and not (img and idx == i)), None)
        inserts.setdefault(at, []).append(html)
    # rebuild: drop every image that is not a matched picture, chart or undrawn shape; put the drawn shapes in place
    out, last = [], 0
    for pos, html, img, idx in els:
        out.append(seg[last:pos])
        out.extend(inserts.pop(pos, []))
        if img:
            if idx is not None:
                out.append(html)
            last = pos + len(html)
        else:
            last = pos
    out.append(seg[last:])
    tail = "".join(inserts.pop(None, []))
    seg = "".join(out)
    if tail:
        cut = seg.rfind("</div>")
        seg = seg[:cut] + tail + seg[cut:] if cut > 0 else seg + tail
    return page[:start] + seg + page[end:]


if __name__ == "__main__":
    got = render(Path(sys.argv[1]), Path(sys.argv[2]))
    print(len(got), "slides ->", sys.argv[2])
