"""Color math: WCAG 2.x contrast and the roles a color can safely play on a kit's paper.

A kit's exact brand colors are fixed. Letterpress never invents a new brand color; it measures each one
against the paper and decides what job it can do:

- ``text``   4.5:1 or more on the paper: body text, headings, numbers
- ``large``  3:1 to 4.5:1: headings 18pt and up, big numbers, rules
- ``fill``   under 3:1 and light: a background, with the kit's ink set on top (checked too)
- ``rule``   under 3:1 and not light enough to sit under ink: lines and the color bar only
"""

from __future__ import annotations

import re
from typing import Optional

HEX = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

AA_TEXT = 4.5
AA_LARGE = 3.0

ROLE_LABEL = {
    "text": "Text",
    "large": "Headings only",
    "fill": "Fills only",
    "rule": "Rules only",
}


def norm(value: str) -> Optional[str]:
    """``#abc`` / ``abc`` / ``#AABBCC`` to ``#aabbcc``; None when it is not a hex color."""
    if not isinstance(value, str):
        return None
    m = HEX.match(value.strip())
    if not m:
        return None
    h = m.group(1).lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def rgb(hexcolor: str) -> tuple:
    h = norm(hexcolor)
    if not h:
        raise ValueError(f"not a color: {hexcolor!r}")
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def to_hex(r: float, g: float, b: float) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in (r, g, b))


def _channel(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hexcolor: str) -> float:
    r, g, b = rgb(hexcolor)
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def ratio_text(a: str, b: str) -> str:
    return f"{contrast(a, b):.1f}:1"


def usage(color: str, paper: str, ink: str) -> str:
    """The safest job for ``color`` on ``paper``, given the kit's ``ink``."""
    c = contrast(color, paper)
    if c >= AA_TEXT:
        return "text"
    if c >= AA_LARGE:
        return "large"
    if contrast(ink, color) >= AA_TEXT and luminance(color) > luminance(ink):
        return "fill"
    return "rule"


def best_text_on(fill: str, candidates: list) -> tuple:
    """The candidate with the highest contrast on ``fill``, with that ratio."""
    best, ratio = None, 0.0
    for c in candidates:
        if not norm(c):
            continue
        r = contrast(c, fill)
        if r > ratio:
            best, ratio = c, r
    return best, ratio


def mix(a: str, b: str, t: float) -> str:
    """``a`` moved toward ``b`` by ``t`` (0..1), in sRGB. Used for tints of a kit's own colors only."""
    ra, rb = rgb(a), rgb(b)
    return to_hex(*(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def is_light(color: str) -> bool:
    return luminance(color) > 0.45


def describe(color: str) -> str:
    """A plain name for a color family, for looks and labels (not a brand name)."""
    r, g, b = rgb(color)
    mx, mn = max(r, g, b), min(r, g, b)
    lum = luminance(color)
    if mx - mn < 18:
        if lum > 0.85:
            return "white"
        if lum < 0.03:
            return "black"
        return "gray"
    # hue
    rf, gf, bf = r / 255, g / 255, b / 255
    mxf, mnf = max(rf, gf, bf), min(rf, gf, bf)
    d = mxf - mnf
    if mxf == rf:
        h = ((gf - bf) / d) % 6
    elif mxf == gf:
        h = (bf - rf) / d + 2
    else:
        h = (rf - gf) / d + 4
    h *= 60
    light = lum > 0.7
    if lum > 0.8 and (r > b) and (g > b) and mx - mn < 60:
        return "cream"
    names = [(15, "red"), (45, "orange"), (65, "yellow"), (160, "green"), (195, "teal"), (255, "blue"),
             (290, "purple"), (335, "magenta"), (360, "red")]
    for limit, name in names:
        if h < limit:
            return ("pale " + name) if light else name
    return "red"
