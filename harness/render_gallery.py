"""The kit gallery: every studio kit's deck (all slide types), its graphic and its one-pager, from the same demo
sources, as one contact sheet per kit plus an index sheet.

    /usr/bin/python3 harness/render_gallery.py OUT_DIR [--picture PATH] [--kits counsel,stage]

Runs outside Hermes on a temporary data folder with the hand-written demo content (harness/demo_content.py), every
claim tied to a passage of samples/. Slides and graphics are drawn by scene.png, the same scene the PDF and the
PowerPoint use. The one-pager is the finished HTML export, screenshotted with headless Chrome when Chrome is present.
``--picture`` sets a stand-in for the picture slide (Imprint asks the person's own image tool for the real one).
Writes nothing outside OUT_DIR and the temporary folder.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["IMPRINT_DATA_DIR"] = tempfile.mkdtemp(prefix="imprint-gallery-")
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "harness"))
from importlib import import_module  # noqa: E402

from _load import add_samples, kits, layout, render_html, reset, service  # noqa: E402

import demo_content as D  # noqa: E402

PKG = "imprint_plugin_package"
RD = import_module(f"{PKG}.render_deck")
RG = import_module(f"{PKG}.render_graphic")
SC = import_module(f"{PKG}.scene")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def font(size, bold=False):
    from PIL import ImageFont
    return ImageFont.truetype(str(ROOT / "fonts" / ("inter-700.ttf" if bold else "inter-400.ttf")), size)


def onepager_png(doc, kit, by_ref, out: Path) -> Path | None:
    pal, faces = kits.palette(kit), kits.faces(kit)
    sc, ty = layout.page_scene(doc, kit, pal, faces, by_ref, "November 8, 2026")
    if sc is not None:  # studio kits and imported brands set the page as a scene: draw it directly
        png = out / f"onepager-{kit['id']}.png"
        png.write_bytes(SC.png(sc, ty, scale=1.5))
        return png
    tree = layout.tree(doc, kit, pal, faces, by_ref, date="November 8, 2026")
    html_path = out / f"onepager-{kit['id']}.html"
    html_path.write_text(render_html.export_page(tree, faces, doc["title"], marks=True))
    png = out / f"onepager-{kit['id']}.png"
    if not Path(CHROME).exists():
        return None
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                    "--autoplay-policy=user-gesture-required", "--window-size=816,1056",
                    "--virtual-time-budget=4000", f"--screenshot={png}", html_path.as_uri()], capture_output=True, timeout=90)
    return png if png.exists() else None


def main():
    from PIL import Image, ImageDraw
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    pic = Path(sys.argv[sys.argv.index("--picture") + 1]).read_bytes() if "--picture" in sys.argv else None
    want = sys.argv[sys.argv.index("--kits") + 1].split(",") if "--kits" in sys.argv else [k["id"] for k in kits.list_all() if k.get("tier") == "studio"]
    reset()
    srcs = add_samples()
    _s, _b, by_ref = service.passages_for([s["id"] for s in srcs])
    deck, vis, one = D.grounded_deck(by_ref), D.grounded_visual(by_ref), D.grounded(by_ref)
    if pic:
        for sl in deck["slides"]:
            if sl["type"] == "image":
                sl["picture"] = "picture.jpg"
    sheets = []
    for kid in want:
        kit = kits.get(kid)
        pal, faces = kits.palette(kit), kits.faces(kit)
        idx, rows = layout.source_index(deck, by_ref)
        scs, ty = RD.scenes(deck, kit, pal, faces, idx, rows, "November 8, 2026", by_ref)
        pics = {"picture.jpg": pic} if pic else None
        tiles = [Image.open(io.BytesIO(SC.png(sc, ty, scale=0.5, pictures=pics))) for sc in scs]
        gidx, _r = layout.source_index(vis, by_ref)
        gsc, gty = RG.scene(vis, kit, pal, faces, gidx, by_ref)
        graphic = Image.open(io.BytesIO(SC.png(gsc, gty, scale=0.5)))
        (out / f"graphic-{kid}.png").write_bytes(SC.png(gsc, gty, scale=1.0))
        one_png = onepager_png(one, kit, by_ref, out)
        page = Image.open(one_png).convert("RGB") if one_png else None
        tw, th, g = tiles[0].width, tiles[0].height, 16
        cols = 3
        rows_n = (len(tiles) + cols - 1) // cols
        left_w = cols * tw + (cols - 1) * g
        gw = 432
        graphic = graphic.resize((gw, int(graphic.height * gw / graphic.width)))
        if page:
            page = page.resize((gw, int(page.height * gw / page.width)))
        head = 96
        H = head + max(rows_n * th + (rows_n - 1) * g, graphic.height + g + (page.height if page else 0)) + 40
        W = 40 + left_w + 32 + gw + 40
        sheet = Image.new("RGB", (W, H), "#e9e7e2")
        d = ImageDraw.Draw(sheet)
        d.text((40, 30), kit["name"], font=font(30, True), fill="#161616")
        d.text((40, 66), kit.get("method", ""), font=font(16), fill="#2a2a2a")
        for i, t in enumerate(tiles):
            sheet.paste(t, (40 + (i % cols) * (tw + g), head + (i // cols) * (th + g)))
        x2 = 40 + left_w + 32
        sheet.paste(graphic, (x2, head))
        if page:
            sheet.paste(page, (x2, head + graphic.height + g))
        path = out / f"kit-{kid}.png"
        sheet.save(path)
        sheets.append(path)
        print(kid, len(scs), "slides", "long:", [sc["num"] for sc in scs if sc.get("long")], "graphic long:", bool(gsc.get("long")))
    # an index: each kit's title slide, exhibit and graphic in one row
    rows_img = []
    for kid in want:
        kit = kits.get(kid)
        pal, faces = kits.palette(kit), kits.faces(kit)
        idx, rows = layout.source_index(deck, by_ref)
        scs, ty = RD.scenes(deck, kit, pal, faces, idx, rows, "November 8, 2026", by_ref)
        pick = [scs[0], next(s for s in scs if s["kind"] == "exhibit"), next(s for s in scs if s["kind"] == "stat")]
        ims = [Image.open(io.BytesIO(SC.png(s, ty, scale=0.42, pictures={"picture.jpg": pic} if pic else None))) for s in pick]
        rows_img.append((kit, ims, Image.open(out / f"graphic-{kid}.png")))
    tw, th = rows_img[0][1][0].size
    gh = th
    gw = int(1080 * gh / 1350)
    W = 40 + 220 + 3 * (tw + 14) + gw + 40
    H = 40 + len(rows_img) * (th + 28) + 20
    idx_img = Image.new("RGB", (W, H), "#e9e7e2")
    d = ImageDraw.Draw(idx_img)
    for r, (kit, ims, gimg) in enumerate(rows_img):
        y = 40 + r * (th + 28)
        d.text((40, y + 6), kit["name"], font=font(22, True), fill="#161616")
        d.text((40, y + 38), RD.system_of(kit), font=font(14), fill="#2a2a2a")
        for i, im in enumerate(ims):
            idx_img.paste(im, (260 + i * (tw + 14), y))
        idx_img.paste(gimg.resize((gw, gh)), (260 + 3 * (tw + 14), y))
    idx_img.save(out / "kits-index.png")
    print("wrote", len(sheets), "kit sheets and kits-index.png to", out)


if __name__ == "__main__":
    main()
