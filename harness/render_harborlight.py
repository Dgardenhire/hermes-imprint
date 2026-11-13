"""The Harborlight funder deck, one-pager and graphic in every studio system plus the Harborlight brand, through the
real renderer, as PNGs and one contact sheet.

    /usr/bin/python3 harness/render_harborlight.py OUT_DIR [--kits counsel,stage] [--sheet NAME.png] [--deck RUN.json]

Runs on a temporary data folder. The sources are the persona's real files (harness/live/personas/denise/), read
with the real readers, so passage ids match the real-model run logs. The deck doc is a real-model write
(``--deck``, a run log JSON whose ``response`` is the deck; default: Loop 1's last funder deck). Its funding exhibit
is replaced by the hero exhibit the brief names (three bars, 287 flagged as the finding, the subhead), the slide the
AI lane makes the model write; every number on it is in the FY26 Program Report. The one-pager and the graphic are
hand-written from the same passages (no real-model one exists yet) and say so in the report.
Writes nothing outside OUT_DIR and the temporary folder.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["LETTERPRESS_DATA_DIR"] = tempfile.mkdtemp(prefix="letterpress-harborlight-")
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from childenv import child_env  # noqa: E402  only the allowlisted names reach the programs started here
from importlib import import_module  # noqa: E402

from _load import kits, layout, render_html, service  # noqa: E402

PKG = "letterpress_plugin_package"
RD = import_module(f"{PKG}.render_deck")
RG = import_module(f"{PKG}.render_graphic")
SC = import_module(f"{PKG}.scene")
K = import_module(f"{PKG}.content")
IM = import_module(f"{PKG}.imports")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PERSONA = ROOT / "harness" / "live" / "personas" / "denise"
PLAN = Path.home() / "Desktop/claude-test/.planning/hackathon-2026-11/premium-plan/imprint"
DEFAULT_DECK = PLAN / "loop1/runs/loop1-213923-03-write.json"
DATE = "November 8, 2026"

HERO = {"type": "exhibit", "heading": "Demand is outgrowing our seats", "subhead": "212 more adults than last year",
        "unit": "Adult learners", "refs": ["P1", "P4"],
        "bars": [{"label": "FY2025", "value": "936", "ref": "P1"},
                 {"label": "FY2026", "value": "1,148", "ref": "P1"},
                 {"label": "Waiting at year end", "value": "287", "ref": "P4", "accent": True}],
        "note": ""}

VISUAL = {"kicker": "Adult literacy", "headline": "Demand is outgrowing our seats",
          "dek": "Adults enrolled at Harborlight's five sites, and adults still waiting for a seat at year end",
          "dek_refs": ["P1", "P4"], "form": "bars", "unit": "Adult learners",
          "items": [{"label": "FY2025 enrolled", "value": "936", "ref": "P1"},
                    {"label": "FY2026 enrolled", "value": "1,148", "ref": "P1"},
                    {"label": "Waiting at year end", "value": "287", "ref": "P4", "accent": True}],
          "steps": [], "takeaway": "A sixth site at the Eastgate branch library would serve 180 more learners a year.",
          "takeaway_refs": ["P5"]}

ONEPAGER = {"title": "The FY2027 budget request, on one page",
            "dek": "Staff ask the board to approve a budget of $1,610,000 that opens a sixth site at the Eastgate branch "
                   "library and adds two site coordinators.",
            "dek_refs": ["P5"],
            "stat": {"value": "287", "label": "adults were on the waitlist at year end, most at Eastgate and Riverside", "ref": "P4"},
            "sections": [
                {"heading": "Who we served", "body": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five "
                 "neighborhood sites, up from 936 the year before. Sixty-eight percent of learners who stayed at least 12 weeks "
                 "gained one or more reading levels.", "refs": ["P1"]},
                {"heading": "The money", "body": "Operating expenses for FY2026 were $1,420,000, and program costs were 81 percent "
                 "of spending. Reserves stand at 3.2 months of operating expenses, below the board's target of 4 months.",
                 "refs": ["P3", "P8"]},
                {"heading": "What the sixth site does", "body": "Staff estimate the sixth site would serve 180 more learners a "
                 "year and cut the waitlist in half.", "refs": ["P5"]}],
            "points": [{"text": "1,148 adults enrolled in FY2026", "ref": "P1"},
                       {"text": "71 learners earned a high school equivalency credential", "ref": "P1"},
                       {"text": "214 volunteer tutors gave 9,870 hours", "ref": "P2"}],
            "quote": {"text": "I read my granddaughter a bedtime story for the first time this spring.", "who": "A learner at the Riverside site", "ref": "P5"},
            "chart": {"title": "Demand is outgrowing our seats", "unit": "Adult learners",
                      "bars": [{"label": "FY2025 enrolled", "value": "936", "ref": "P1"},
                               {"label": "FY2026 enrolled", "value": "1,148", "ref": "P1"},
                               {"label": "Waiting at year end", "value": "287", "ref": "P4", "accent": True}]},
            "next": "The board votes on the FY2027 budget on October 21."}


def harborlight_kit() -> dict:
    fd = IM.read("pdf", data=(PERSONA / "Harborlight-Brand-Guide-2025.pdf").read_bytes(), filename="Harborlight-Brand-Guide-2025.pdf")
    kit = IM.save(IM.create(fd))
    kits.set_logo(kit["id"], "harborlight-logo.png", (PERSONA / "harborlight-logo.png").read_bytes())
    return kits.get(kit["id"])


def chrome_png(html_path: Path, png: Path, w=816, h=1056) -> Path | None:
    if not Path(CHROME).exists():
        return None
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                    "--autoplay-policy=user-gesture-required", f"--window-size={w},{h}", "--virtual-time-budget=4000",
                    f"--screenshot={png}", html_path.as_uri()], capture_output=True, timeout=90, env=child_env())
    return png if png.exists() else None


def onepager_png(doc, kit, by_ref, out: Path):
    """The one-pager as the person sees it: a scene when the system draws one, else the finished HTML page."""
    pal, faces = kits.palette(kit), kits.faces(kit)
    png = out / f"onepager-{kit['id']}.png"
    page = getattr(layout, "page_scene", None)
    if page:
        sc, ty = page(doc, kit, pal, faces, by_ref, date=DATE)
        if sc is not None:
            png.write_bytes(SC.png(sc, ty, scale=1.5, logos=RD.logo_bytes(kits.logo_variants(kit, pal))))
            return png
    tree = layout.tree(doc, kit, pal, faces, by_ref, date=DATE)
    html_path = out / f"onepager-{kit['id']}.html"
    html_path.write_text(render_html.export_page(tree, faces, doc["title"], marks=True))
    return chrome_png(html_path, png)


def font(size, bold=False):
    from PIL import ImageFont
    return ImageFont.truetype(str(ROOT / "fonts" / ("inter-700.ttf" if bold else "inter-400.ttf")), size)


def main():
    from PIL import Image, ImageDraw
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    deck_log = Path(sys.argv[sys.argv.index("--deck") + 1]) if "--deck" in sys.argv else DEFAULT_DECK
    sheet_name = sys.argv[sys.argv.index("--sheet") + 1] if "--sheet" in sys.argv else "sheet.png"
    ids = []
    for n in ("FY26-Program-Report.docx", "board-retreat-notes.txt"):
        ids.append(service.read_file(n, (PERSONA / n).read_bytes())["id"])
    _s, _b, by_ref = service.passages_for(ids)
    raw = json.loads(deck_log.read_text())["response"]
    deck = K.clean_deck(raw)
    ex = [i for i, s in enumerate(deck["slides"]) if s["type"] == "exhibit"]
    if ex:
        deck["slides"][ex[0]] = dict(HERO)
    else:
        deck["slides"].insert(1, dict(HERO))
    hk = harborlight_kit()
    want = sys.argv[sys.argv.index("--kits") + 1].split(",") if "--kits" in sys.argv else \
        [k["id"] for k in kits.list_all() if k.get("studio")][:5]
    kit_list = [kits.get(k) for k in want] + [hk]
    (out / "deck-doc.json").write_text(json.dumps(deck, indent=2))
    rows_img = []
    for kit in kit_list:
        pal, faces = kits.palette(kit), kits.faces(kit)
        idx, rows = layout.source_index(deck, by_ref)
        scs, ty = RD.scenes(deck, kit, pal, faces, idx, rows, DATE, by_ref)
        logos = RD.logo_bytes(kits.logo_variants(kit, pal))
        kd = out / ("harborlight" if kit is hk else kit["id"])
        kd.mkdir(exist_ok=True)
        tiles = []
        for sc in scs:
            data = SC.png(sc, ty, scale=1.0, logos=logos)
            (kd / f"slide-{sc['num']:02d}-{sc['kind']}.png").write_bytes(data)
            tiles.append(Image.open(io.BytesIO(data)).convert("RGB"))
        gidx, _r = layout.source_index(VISUAL, by_ref)
        gsc, gty = RG.scene(VISUAL, kit, pal, faces, gidx, by_ref)
        gdata = SC.png(gsc, gty, scale=1.0, logos=logos)
        (kd / "graphic.png").write_bytes(gdata)
        one = onepager_png(ONEPAGER, kit, by_ref, kd)
        rows_img.append((kit, tiles, Image.open(io.BytesIO(gdata)).convert("RGB"), Image.open(one).convert("RGB") if one else None))
        print(kit["id"], RD.system_of(kit), len(scs), "slides; long:", [sc["num"] for sc in scs if sc.get("long")], "graphic long:", bool(gsc.get("long")))
    # contact sheet: per kit a row of every slide (small), then the graphic and the page
    tw, th = 384, 216
    cols = 6
    gw = 216
    pw = 216
    g = 10
    blocks = []
    for kit, tiles, graphic, page in rows_img:
        n = len(tiles)
        r = (n + cols - 1) // cols
        bh = max(r * (th + g), int(graphic.height * gw / graphic.width), int(page.height * pw / page.width) if page else 0) + 60
        blocks.append(bh)
    W = 40 + cols * (tw + g) + gw + g + pw + 40
    H = 40 + sum(blocks) + 20
    sheet = Image.new("RGB", (W, H), "#e7e5e0")
    d = ImageDraw.Draw(sheet)
    y = 40
    for (kit, tiles, graphic, page), bh in zip(rows_img, blocks):
        d.text((40, y), f"{kit['name']}  ({RD.system_of(kit)})", font=font(24, True), fill="#161616")
        yy = y + 40
        for i, t in enumerate(tiles):
            sheet.paste(t.resize((tw, th), Image.LANCZOS), (40 + (i % cols) * (tw + g), yy + (i // cols) * (th + g)))
        gx = 40 + cols * (tw + g)
        sheet.paste(graphic.resize((gw, int(graphic.height * gw / graphic.width)), Image.LANCZOS), (gx, yy))
        if page:
            sheet.paste(page.resize((pw, int(page.height * pw / page.width)), Image.LANCZOS), (gx + gw + g, yy))
        y += bh
    sheet.save(out / sheet_name)
    print("wrote", out / sheet_name)


if __name__ == "__main__":
    main()
