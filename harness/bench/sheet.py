"""A blind contact sheet: every slide image in a folder, in order, on one neutral sheet with no names or labels.

    /usr/bin/python3 harness/bench/sheet.py SLIDE_DIR OUT.png [--cols 3] [--width 640]

Slides are scaled to the same width (16:9 kept, letterboxed on the sheet's gray if a slide is another shape), so
neither side's resolution shows. Nothing on the sheet says which tool made it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def sheet(slide_dir: Path, out: Path, cols: int = 3, width: int = 640) -> Path:
    files = sorted(p for p in slide_dir.glob("*.png"))
    if not files:
        raise SystemExit(f"no slides in {slide_dir}")
    h = round(width * 9 / 16)
    gap, pad = 24, 40
    rows = (len(files) + cols - 1) // cols
    W = pad * 2 + cols * width + (cols - 1) * gap
    H = pad * 2 + rows * h + (rows - 1) * gap
    page = Image.new("RGB", (W, H), "#d6d6d3")
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((width, h), Image.LANCZOS)
        tile = Image.new("RGB", (width, h), "#d6d6d3")
        tile.paste(im, ((width - im.width) // 2, (h - im.height) // 2))
        x = pad + (i % cols) * (width + gap)
        y = pad + (i // cols) * (h + gap)
        page.paste(tile, (x, y))
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(out)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    cols = int(a[a.index("--cols") + 1]) if "--cols" in a else 3
    width = int(a[a.index("--width") + 1]) if "--width" in a else 640
    print(sheet(Path(a[0]), Path(a[1]), cols, width))
