"""Every graphic form (bars, figures, compare, timeline) in the Harborlight brand and studio systems, through the real
renderer, as PNGs, one PDF per graphic, and one contact sheet.

    /usr/bin/python3 harness/render_graphics_sheet.py OUT_DIR [--kits chart-room,stage] [--sheet NAME.png]

The graphics are the four the canvas offers for the Harborlight pinned answer, hand-written from the persona's real
sources (harness/live/personas/denise/); every number is in the FY26 Program Report or the board retreat notes.
Writes nothing outside OUT_DIR and a temporary data folder.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_harborlight as RH  # noqa: E402  (sets the temporary data folder first)

kits, layout, service, RD, RG, SC = RH.kits, RH.layout, RH.service, RH.RD, RH.RG, RH.SC

FORMS = [
    {"kicker": "Adult literacy", "headline": "Demand is outgrowing our seats",
     "dek": "Adults enrolled at Harborlight's five sites, and adults still waiting for a seat at year end",
     "dek_refs": ["P1", "P4"], "form": "bars", "unit": "Adult learners",
     "items": [{"label": "FY2025 enrolled", "value": "936", "ref": "P1"},
               {"label": "FY2026 enrolled", "value": "1,148", "ref": "P1"},
               {"label": "Waiting at year end", "value": "287", "ref": "P4", "accent": True}],
     "steps": [], "takeaway": "A sixth site at the Eastgate branch library would serve 180 more learners a year.",
     "takeaway_refs": ["P5"]},
    {"kicker": "The waitlist", "headline": "At year end, 287 adults waited an average of nine weeks",
     "dek": "Adults waiting for Harborlight classes at year end, and what staff expect from a sixth site.",
     "dek_refs": ["P4"], "form": "figures", "unit": "",
     "items": [{"label": "Adults on the waitlist", "value": "287", "ref": "P4", "accent": True},
               {"label": "More learners a year from a sixth site", "value": "180", "ref": "P5"}],
     "steps": [], "takeaway": "Staff estimate a sixth site at the Eastgate branch library would cut the waitlist in half.",
     "takeaway_refs": ["P5"]},
    {"kicker": "The cost", "headline": "The FY2027 budget request is higher than FY2026 operating expenses",
     "dek": "Harborlight's FY2026 operating expenses next to the FY2027 budget staff recommend.",
     "dek_refs": ["P3", "P5"], "form": "compare", "unit": "",
     "items": [{"label": "FY2026 expenses", "value": "$1,420,000", "ref": "P3"},
               {"label": "FY2027 request", "value": "$1,610,000", "ref": "P5", "accent": True}],
     "steps": [], "takeaway": "Reserves stand at 3.2 months of operating expenses, below the board's target of 4 months.",
     "takeaway_refs": ["P3"]},
    {"kicker": "Road to the vote", "headline": "Enrollment grew and a waitlist formed before the October 21 vote",
     "dek": "How demand at Harborlight's five sites built up ahead of the FY2027 budget vote.",
     "dek_refs": ["P1"], "form": "timeline", "unit": "", "items": [],
     "steps": [{"when": "The year before", "text": "936 adult learners enrolled", "ref": "P1"},
               {"when": "FY2026", "text": "1,148 adult learners enrolled across five sites", "ref": "P1"},
               {"when": "Year end", "text": "287 adults were on the waitlist", "ref": "P4"},
               {"when": "October 21", "text": "Board votes on the FY2027 budget", "ref": "P5"}],
     "takeaway": "Staff will bring a one-page summary of the FY2027 budget request to the October 21 meeting.",
     "takeaway_refs": ["P5"]},
]


def main():
    from PIL import Image, ImageDraw
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sheet_name = sys.argv[sys.argv.index("--sheet") + 1] if "--sheet" in sys.argv else "graphics-sheet.png"
    want = sys.argv[sys.argv.index("--kits") + 1].split(",") if "--kits" in sys.argv else ["chart-room", "stage"]
    ids = [service.read_file(n, (RH.PERSONA / n).read_bytes())["id"] for n in ("FY26-Program-Report.docx", "board-retreat-notes.txt")]
    _s, _b, by_ref = service.passages_for(ids)
    hk = RH.harborlight_kit()
    rows = []
    for kit in [hk] + [kits.get(k) for k in want]:
        pal, faces = kits.palette(kit), kits.faces(kit)
        logos = RD.logo_bytes(kits.logo_variants(kit, pal))
        name = "harborlight" if kit is hk else kit["id"]
        tiles = []
        for doc in FORMS:
            idx, _r = layout.source_index(doc, by_ref)
            sc, ty = RG.scene(doc, kit, pal, faces, idx, by_ref)
            data = SC.png(sc, ty, scale=1.0, logos=logos)
            (out / f"graphic-{name}-{doc['form']}.png").write_bytes(data)
            (out / f"graphic-{name}-{doc['form']}.pdf").write_bytes(
                RG.render_pdf(doc, kit, pal, faces, idx, by_ref, logo=kits.logo_variants(kit, pal)))
            tiles.append(Image.open(io.BytesIO(data)).convert("RGB"))
            print(name, RD.system_of(kit), doc["form"], "long:", bool(sc.get("long")))
        rows.append((f"{kit['name']}  ({RD.system_of(kit)})", tiles))
    tw = 540
    th = int(tw * 1350 / 1080)
    g = 16
    W = 40 + 4 * (tw + g) + 24
    H = 40 + len(rows) * (th + 60 + g) + 20
    sheet = Image.new("RGB", (W, H), "#e7e5e0")
    d = ImageDraw.Draw(sheet)
    y = 40
    for title, tiles in rows:
        d.text((40, y), title, font=RH.font(24, True), fill="#161616")
        for i, t in enumerate(tiles):
            sheet.paste(t.resize((tw, th), Image.LANCZOS), (40 + i * (tw + g), y + 44))
        y += th + 60 + g
    sheet.save(out / sheet_name)
    print("wrote", out / sheet_name)


if __name__ == "__main__":
    main()
