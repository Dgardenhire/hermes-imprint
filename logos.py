"""Will the logo show? Measured against the ground it sits on, on every page type.

A teal lighthouse on a teal band vanishes; a white wordmark on white paper does too. ``treatment`` reads the
logo's own colors (the opaque pixels of a PNG, the fills and strokes of an SVG) and measures what share of
the mark stands out from the ground (1.8:1 or more). When too little does, Imprint switches to the
knockout treatment: the mark's shape set in one color that reads on the ground (the band's own text color,
or the ink on paper), the way a designer prepares a reversed logo. A JPG has no transparency to knock out,
so it sits on a small paper tile instead. The proof says which treatment it used, in the Logo check.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path
from typing import Optional

try:
    from . import colors as C
except ImportError:  # loaded loose
    import colors as C  # type: ignore

STANDS_OUT = 1.8   # a part of the mark at this ratio or better against the ground is visible
ENOUGH = 0.55      # share of the mark that must stand out before it is left as it is
_cache: dict = {}


def _png_colors(data: bytes) -> list:
    """``[(hex, weight)]`` for the opaque pixels of a PNG, in up to 8 color groups."""
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.draft("RGBA", (256, 256))
    im = im.convert("RGBA")
    im.thumbnail((160, 160))
    alpha = im.getchannel("A")
    rgb = im.convert("RGB")
    px = [p for p, a in zip(rgb.getdata(), alpha.getdata()) if a >= 64]
    if not px:
        return []
    counts: dict = {}
    for r, g, b in px:  # 32 levels per channel is plenty to tell a mark from its ground
        key = (r // 8 * 8 + 4, g // 8 * 8 + 4, b // 8 * 8 + 4)
        counts[key] = counts.get(key, 0) + 1
    total = float(len(px))
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:24]
    return [("#%02x%02x%02x" % k, v / total) for k, v in top]


HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
NAMED = {"black": "#000000", "white": "#ffffff"}


def _svg_colors(data: bytes) -> list:
    text = data.decode("utf-8", "replace")
    found = [C.norm("#" + m.group(1)) for m in HEX.finditer(text)]
    for name, hx in NAMED.items():
        found += [hx] * len(re.findall(r"(?:fill|stroke)\s*[:=]\s*[\"']?" + name + r"\b", text, re.I))
    found = [f for f in found if f]
    if not found:  # an SVG with no colors draws in black
        return [("#000000", 1.0)]
    total = float(len(found))
    out: dict = {}
    for f in found:
        out[f] = out.get(f, 0) + 1 / total
    return list(out.items())


def colors_of(path: Path) -> Optional[list]:
    """The mark's colors with their share, or ``None`` for a JPG (it carries its own background)."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key in _cache:
        return _cache[key]
    kind = path.suffix.lower()
    try:
        data = path.read_bytes()
        cols = _png_colors(data) if kind == ".png" else _svg_colors(data) if kind == ".svg" else None
    except Exception:
        cols = None
    _cache[key] = cols
    return cols


def visible_share(cols: list, ground: str) -> float:
    return round(sum(w for hx, w in cols if C.contrast(hx, ground) >= STANDS_OUT), 3)


def treatment(path: Optional[Path], ground: str, text_on_ground: str) -> Optional[dict]:
    """How the logo goes on ``ground``: ``{mode, share, ratio, color}``.

    ``mode`` is ``as_is`` (enough of the mark stands out), ``knockout`` (set in ``color``, one flat color
    that reads on the ground) or ``chip`` (a JPG, set on a paper tile). ``ratio`` is the contrast of the
    mark's main color against the ground."""
    if path is None:
        return None
    cols = colors_of(path)
    if cols is None:
        if path.suffix.lower() in (".jpg", ".jpeg"):
            return {"mode": "as_is", "share": 1.0, "ratio": None, "color": None}
        return None
    if not cols:  # nothing opaque enough to judge: leave it as it is
        return {"mode": "as_is", "share": 1.0, "ratio": None, "color": None}
    main = max(cols, key=lambda c: c[1])[0]
    share = visible_share(cols, ground)
    ratio = round(C.contrast(main, ground), 2)
    if share >= ENOUGH:
        return {"mode": "as_is", "share": share, "ratio": ratio, "color": None}
    return {"mode": "knockout", "share": share, "ratio": ratio, "color": text_on_ground}


def knockout_png(data: bytes, color: str, ground: Optional[str] = None) -> bytes:
    """A reversed logo made from the person's own file: every part of the mark that would vanish on ``ground``
    is set in ``color``, and the parts that already stand out (a gold stroke on a teal band) keep their own
    color. With no ground, the whole shape (its alpha) is filled with ``color``."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    alpha = im.getchannel("A")
    if ground is None:
        flat = Image.new("RGBA", im.size, C.rgb(color) + (255,))
        flat.putalpha(alpha)
        out = io.BytesIO()
        flat.save(out, "PNG", optimize=True)
        return out.getvalue()
    q = im.convert("RGB").quantize(colors=64)
    pal = q.getpalette()[: 64 * 3]
    new = []
    for i in range(0, len(pal), 3):
        hx = "#%02x%02x%02x" % tuple(pal[i:i + 3])
        new += list(C.rgb(color)) if C.contrast(hx, ground) < STANDS_OUT else pal[i:i + 3]
    q.putpalette(new)
    rgb = q.convert("RGB")
    rgb.putalpha(alpha)
    out = io.BytesIO()
    rgb.save(out, "PNG", optimize=True)
    return out.getvalue()


def knockout_svg(data: bytes, color: str) -> bytes:
    """Every color in the SVG set to ``color``, and ``color`` as the root fill for shapes that name none."""
    text = data.decode("utf-8", "replace")
    text = HEX.sub(color, text)
    for name in NAMED:
        text = re.sub(r"((?:fill|stroke)\s*[:=]\s*[\"']?)" + name + r"\b", r"\g<1>" + color, text, flags=re.I)
    text = re.sub(r"<svg\b", f'<svg fill="{color}"', text, count=1)
    return text.encode("utf-8")


MIME = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def variant(path: Optional[Path], ground: str, text_on_ground: str) -> Optional[dict]:
    """The logo as it should go on ``ground``: ``{mode, data (bytes), kind, data_url, share, ratio, color}``."""
    t = treatment(path, ground, text_on_ground)
    if t is None:
        return None
    data = path.read_bytes()
    kind = path.suffix.lower()
    if t["mode"] == "knockout":
        data = knockout_png(data, t["color"], ground) if kind == ".png" else knockout_svg(data, t["color"])
    url = f"data:{MIME.get(kind, 'image/png')};base64," + base64.b64encode(data).decode("ascii")
    return {**t, "data": data, "kind": kind, "data_url": url}


def grounds(kit: dict, pal: dict) -> dict:
    """Where the logo sits for this kit, as ``{place: (ground, text color on it)}``. The banner and bulletin
    families put it on the band (their masthead and their dark slides); every family puts it on paper too."""
    band = pal.get("band") or pal["head"]
    band_text = pal.get("band_text") or C.best_text_on(band, [pal["paper"], pal["ink"], "#ffffff", "#111111"])[0]
    return {"paper": (pal["paper"], pal["ink"]), "band": (band, band_text)}


def for_kit(path: Optional[Path], kit: dict, pal: dict, alt: Optional[Path] = None) -> dict:
    """``{"paper": variant, "band": variant}`` for one kit (either may be ``None`` with no logo).

    Where the main logo would vanish, the kit's own reversed logo (``alt``) is used when it reads on that
    ground; failing that, Imprint knocks the main logo out in one color."""
    out = {}
    for place, (g, t) in grounds(kit, pal).items():
        v = variant(path, g, t)
        if v and v["mode"] != "as_is" and alt is not None:
            a = variant(alt, g, t)
            if a and a["mode"] == "as_is":
                v = {**a, "mode": "alternate"}
        out[place] = v
    return out


def uses_band(kit: dict, kind: str) -> bool:
    layout = kit.get("layout") or "banner"
    if kind == "deck":
        return layout in ("banner", "bulletin")
    return layout == "banner"


def pill(kit: dict, kind: str, variants: dict) -> Optional[dict]:
    """The Logo check: says when the mark had to be knocked out, and where."""
    places = ["paper"] + (["band"] if uses_band(kit, kind) else [])
    notes = []
    for place in places:
        v = variants.get(place)
        if v and v["mode"] == "alternate":
            notes.append(f"Your reversed logo is used on {'the band' if place == 'band' else 'the paper'}")
        elif v and v["mode"] == "knockout":
            where = "the band" if place == "band" else "the paper"
            color = "white" if C.luminance(v["color"]) > 0.8 else "black" if C.luminance(v["color"]) < 0.02 else v["color"]
            notes.append(f"Logo set in {color} on {where}: its own colors were too close to it ({v['ratio']}:1)")
    if not notes:
        return None
    return {"id": "logo", "tone": "good", "label": notes[0] if len(notes) == 1 else "Logo knocked out where it would vanish",
            "items": notes + ([] if all("reversed logo is used" in x for x in notes) else
                              ["If you have a reversed (knockout) version of your logo, add it to the brand on the Brands tab and Imprint will use it here."])}
