"""P6: Imprint's own number checker over a deck's text, for either side.

    /usr/bin/python3 harness/bench/p6_check.py RESULT.json [PLAIN.pptx] > report.json

RESULT.json is Imprint's build for the same source set (it holds the passages both sides were given). With a .pptx,
every text box (its paragraphs joined, as one element), table row and chart value in it is read, and each number is looked for the way
``checks.check_line`` looks: in the sources as written (exact), or worked out from two numbers in the sources
(computed, one operation: a difference, sum, ratio or percent change). The plain deck cites no passages, so it is
checked against all of them, which is the lenient reading: a number counts as found if ANY passage holds it, or two
numbers anywhere work it out. Dates, years and slide counters are skipped, as on Imprint's side. Without a .pptx,
the Imprint deck's own grounding is reported. Spelled-out source numbers ("Seventy-one") count as found.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bench as B  # noqa: E402


def pptx_lines(path: Path) -> list:
    from pptx import Presentation
    p = Presentation(str(path))
    out = []
    for n, slide in enumerate(p.slides, start=1):
        for sh in slide.shapes:
            if sh.has_text_frame:
                # One text box is one element, as on Imprint's side: a big number and its label are often two
                # paragraphs of one box, and the label's words are what name a worked-out number ("per event").
                t = " ".join("".join(r.text for r in para.runs).strip() for para in sh.text_frame.paragraphs).strip()
                if t and not re.fullmatch(r"\d{1,2}\s*/\s*\d{1,2}|\d{1,2}", t):  # page counters ("3 / 8") and card numbers
                    out.append((n, t))
            if getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    t = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                    if t:
                        out.append((n, t))
            if getattr(sh, "has_chart", False) and sh.has_chart:
                pl = sh.chart.plots[0]
                for cat, v in zip(pl.categories, pl.series[0].values):
                    out.append((n, f"{cat} {v:,.0f}" if float(v).is_integer() else f"{cat} {v}"))
    return out


def main():
    res = json.loads(Path(sys.argv[1]).read_text())
    import tempfile
    api, CK = B.load_imprint(Path(tempfile.mkdtemp(prefix="p6-check-")))
    by_ref = {k: {**v, "ref": k} for k, v in res["passages"].items()}
    ids = list(by_ref)
    if len(sys.argv) > 2:
        lines = pptx_lines(Path(sys.argv[2]))
        found, missing, computed = 0, [], []
        for n, t in lines:
            got = CK.check_line(t, ids, by_ref, all_ids=ids)
            for it in got["items"]:
                if it["status"] == "missing":
                    missing.append({"slide": n, "value": it["value"], "line": t})
                elif it["status"] == "computed":
                    computed.append({"slide": n, "value": it["value"], "line": t, "math": (it.get("math") or {}).get("text")})
                else:
                    found += 1
        print(json.dumps({"side": "plain", "deck": sys.argv[2], "checked": found + len(missing) + len(computed), "exact": found,
                          "computed": computed, "missing": missing}, indent=1, ensure_ascii=False))
    else:
        g = res["grounding"]
        nums = [i for i in g if i.get("kind") in ("number", "quote") and i["status"] not in ("date",)]
        print(json.dumps({"side": "imprint", "checked": len(nums), "missing": [i for i in nums if i["status"] == "missing"],
                          "computed": [i for i in nums if i["status"] == "computed"]}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
