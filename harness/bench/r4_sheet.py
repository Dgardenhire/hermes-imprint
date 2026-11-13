"""Round 4 design sheet: the round-4 Harborlight funder deck (the real-model build, in the Harborlight brand) and a
real-model one-pager made in the same data folder, from the same two sources, in the same brand.

    /usr/bin/python3 harness/bench/r4_sheet.py RESULT.json DECK_PNG_DIR OUT.png

The one-pager is one ``make`` job (kind onepager) through ``claude -p`` (bench.ClaudeCli, run logs in
docs/runs/ai/loop2/ under the result's tag plus "-onepager"). Nothing is hand-written.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench as B  # noqa: E402
import loop2 as L2  # noqa: E402


def main():
    res_path, deck_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    r = json.loads(res_path.read_text())
    api, CK = B.load_letterpress(L2.DATA / r["tag"])
    from importlib import import_module
    kits = import_module("letterpress_plugin_package.kits")
    layout = import_module("letterpress_plugin_package.layout")
    RD = import_module("letterpress_plugin_package.render_deck")
    SC = import_module("letterpress_plugin_package.scene")
    service, jobs = api.service, api.jobs
    service.LLM = B.ClaudeCli(L2.RUNS, r["tag"] + "-onepager")
    sids = sorted({p["source_id"] for p in r["passages"].values()})
    kit = kits.get(r["kit"]["id"])
    t = time.time()
    j = jobs.start("make", f"bench:onepager:{time.time()}", {"kind": "onepager", "source_ids": sids, "kit_ids": [kit["id"]],
                                                              "brief": "A one-page summary for funders of the case for a sixth site"}, wait=True)
    j = jobs.get(j["id"])
    print("onepager", j["status"], round(time.time() - t, 1), j["error"] or "", flush=True)
    oid = (j["result"] or {})["output_id"]
    doc = service._doc_for(oid, kit)
    _s, _b, by_ref = service.passages_for(sids)
    doc = CK.grounding(doc, by_ref)["doc"]
    pal, faces = kits.palette(kit), kits.faces(kit)
    one = out.with_name(out.stem + "-onepager.png")
    sc, ty = layout.page_scene(doc, kit, pal, faces, by_ref, date="November 9, 2026")
    one.write_bytes(SC.png(sc, ty, scale=1.5, logos=RD.logo_bytes(kits.logo_variants(kit, pal))))
    (out.with_name(out.stem + "-onepager.json")).write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    # the sheet: deck slides in a 3-column grid on the left, the one-pager on the right
    from PIL import Image, ImageDraw
    slides = sorted(deck_dir.glob("slide-*.png"))
    sw = 560
    ims = [Image.open(p).convert("RGB") for p in slides]
    sh = round(sw * ims[0].height / ims[0].width)
    gap = 24
    rows = (len(ims) + 2) // 3
    op = Image.open(one).convert("RGB")
    oh = rows * sh + (rows - 1) * gap
    ow = round(oh * op.width / op.height)
    W = gap + 3 * sw + 2 * gap + gap * 2 + ow + gap
    H = gap + oh + gap
    sheet = Image.new("RGB", (W, H), (214, 214, 208))
    for i, im in enumerate(ims):
        x, y = gap + (i % 3) * (sw + gap), gap + (i // 3) * (sh + gap)
        sheet.paste(im.resize((sw, sh), Image.LANCZOS), (x, y))
    sheet.paste(op.resize((ow, oh), Image.LANCZOS), (gap + 3 * sw + 2 * gap + gap * 2, gap))
    sheet.save(out)
    print("sheet", out, sheet.size)


if __name__ == "__main__":
    main()
