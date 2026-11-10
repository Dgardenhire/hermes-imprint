"""Checks that run on every render, shown as pills under each proof.

- **Sources**: every number and every quoted phrase is found in a passage it cites (an exact or a
  normalized match). A number found only in some other passage gets its citation fixed and says so.
  A number or quote found nowhere is "Not found in sources" and blocks export until the person removes
  the item or keeps it on purpose (a click that is recorded).
- **Contrast**: every text and background pair the layout uses passes WCAG AA.
- **Never say**: none of the kit's never-say words appear.
- **Required lines**: every line the kit requires is on the page.
- **Fonts**: any font that had to be substituted is named, the same way the colophon names it.

Each check returns ``{id, label, tone, detail, items}``; tone is good, warn or bad.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Optional

try:
    from . import content as K
except ImportError:  # loaded loose
    import content as K  # type: ignore

QUOTE = re.compile(r"[“\"]([^”\"]{12,300})[”\"]")


def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"[‐-―]", "-", s)
    s = re.sub(r"[^\w%$.'\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_norm(s: str) -> str:
    """Words only, for comparing a quote with its source: case, curly or straight quote marks, and the
    punctuation around words never decide a match ("this spring." matches "this spring," said a learner).
    Decimal points and thousands commas inside numbers are kept."""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = re.sub(r"(?<=\d)[.,](?=\d)", "\u0000", s)
    s = re.sub(r"[‐-―]", "-", s)
    s = re.sub(r"[^\w%$'\u0000\-]+", " ", s)
    s = re.sub(r"(?<!\w)'|'(?!\w)", " ", s)
    s = s.replace("\u0000", ".")
    return re.sub(r"\s+", " ", s).strip()


_ALIAS = {"50%": "1/2", "33%": "1/3", "33.3%": "1/3", "33.33%": "1/3", "25%": "1/4", "75%": "3/4", "67%": "2/3",
          "66.7%": "2/3", "66%": "2/3"}
_DOUBLE = re.compile(r"\b(?:twice|double[sd]?|doubling)\b", re.I)


def _num_set(text: str) -> set:
    """Every number a source holds, as digits or as words: "nine weeks" holds 9, "in half" and "50%" hold 1/2,
    "doubled" holds 2x."""
    got = set(K.numbers(text)) | set(K.spelled_numbers(text)) | {v for _r, v, _a, _b in K.spelled_spans(text)}
    got |= {_ALIAS[v] for v in list(got) if v in _ALIAS}
    got |= _range_units(text)
    if _DOUBLE.search(text or ""):
        got.add("2x")
    return got


_RANGE_UNIT = re.compile(r"(?<![\d.])(\$?)(\d[\d,]*(?:\.\d+)?)\s*(?:to|-|\u2013|\u2014|and|or)\s*\$?\d[\d,]*(?:\.\d+)?\s*"
                         r"(%|percent(?:age points?)?|million|billion|thousand)", re.I)


def _range_units(text: str) -> set:
    """Loop 3 fix 3: the unit of a range, written once at its end, belongs to both ends. "fell from 5.1 to 4.4 percent"
    holds 5.1% as well as 4.4%; "$2 to 3 million" holds 2 million."""
    out = set()
    for m in _RANGE_UNIT.finditer(text or ""):
        core = m.group(2).replace(",", "")
        if "." in core:
            core = core.rstrip("0").rstrip(".") or "0"
        u = m.group(3).lower()
        unit = "%" if u.startswith("percent") or u == "%" else u
        out.add(core + unit)
    return out


def same_value(a: str, b: str) -> bool:
    """Two normalized values that name the same amount: "9" and "9", "1/2" and "50%"."""
    return a == b or _ALIAS.get(a, a) == _ALIAS.get(b, b)


def find_number(n: str, passages: dict, ids: list) -> list:
    """Passage ids among ``ids`` whose text contains the number ``n``, as digits or spelled out."""
    return [pid for pid in ids if n in _num_set((passages.get(pid) or {}).get("text", ""))]


def find_quote(q: str, passages: dict, ids: list) -> list:
    nq = quote_norm(q)
    if len(nq) < 8:
        return []
    return [pid for pid in ids if f" {nq} " in f" {quote_norm((passages.get(pid) or {}).get('text', ''))} "]


def closest(q: str, passages: dict, ids: list) -> Optional[dict]:
    """The passage that shares the most words with ``q``, for the "closest match" panel."""
    words = set(quote_norm(q).split())
    if not words:
        return None
    best, score = None, 0.0
    for pid in ids:
        pw = set(quote_norm((passages.get(pid) or {}).get("text", "")).split())
        if not pw:
            continue
        s = len(words & pw) / len(words)
        if s > score:
            best, score = pid, s
    if best is None or score < 0.25:
        return None
    return {"ref": best, "score": round(score, 2)}


SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+[\"”’']?|$)")


def best_sentence(text: str, probe: str, raw: str = "") -> str:
    """The one sentence of a passage that best matches ``probe`` (or holds ``raw``), not the whole paragraph."""
    sents = [m.group(0).strip() for m in SENTENCE.finditer(text or "") if m.group(0).strip()]
    if not sents:
        return (text or "").strip()[:LINE_MAX]
    if raw:
        for st in sents:
            if raw in st:
                return st[:LINE_MAX * 2]
    words = set(quote_norm(probe).split())
    best = max(sents, key=lambda st: len(words & set(quote_norm(st).split())))
    return best[:LINE_MAX * 2]


def _snippet(passages: dict, ref: Optional[str], probe: str, raw: str = "") -> Optional[dict]:
    p = passages.get(ref) if ref else None
    if not p:
        return None
    return {"ref": ref, "source": p.get("source_title", ""), "locator": p.get("locator", ""),
            "text": best_sentence(p.get("text", ""), probe, raw)}


def grounding(doc: dict, passages: dict, decisions: Optional[dict] = None, brief: str = "") -> dict:
    """Trace every number and quote to a source passage.

    ``passages`` maps ``"P12"`` to ``{text, locator, source_title}`` for every passage of the output's
    sources. ``decisions`` maps an item key to ``"keep"`` when the person kept it on purpose. Numbers that
    appear in the person's own request (``brief``: "a 90-second brief") are theirs, so they count as known.

    Returns ``{items, fixed, missing, kept, doc}``: ``doc`` has moved citations corrected."""
    decisions = decisions or {}
    all_ids = list(passages.keys())
    brief_nums = _num_set(brief)
    items, fixed = [], []
    doc = copy.deepcopy(doc)
    for path, text, refs in K.field_texts(doc):
        refs = [r for r in refs if r]
        bad_refs = [r for r in refs if r not in passages]
        good_refs = [r for r in refs if r in passages]
        if bad_refs:
            items.append({"key": f"{path}|ref|{','.join(bad_refs)}", "path": path, "kind": "ref", "value": ", ".join(bad_refs),
                          "status": "missing", "detail": "Cites a passage that isn't in these sources."})
        claims, dates = [], set()
        for raw, v, a, b in K.claim_spans(text):
            if not re.search(r"\d", raw or "") and not HEADLINE_PATH.search(path or ""):
                continue  # a word number in body prose ("the first two bars", "five sites") is a plain count, not a claim
            if is_date_number(text, a, b):
                dates.add(v)  # a date, year, season ("2025-26") or counter: traced when found, never flagged
            if v not in [c[1] for c in claims]:
                claims.append(("number", v, raw))
        if K.is_quote_path(path):
            claims.append(("quote", text, text))
        else:
            claims += [("quote", m.group(1), m.group(1)) for m in QUOTE.finditer(text or "")]
        for kind, value, raw in claims:
            key = f"{path}|{kind}|{value}"
            base = {"key": key, "path": path, "kind": kind, "value": value, "shown": raw, "field": text}
            finder = find_number if kind == "number" else find_quote
            hit = finder(value, passages, good_refs)
            if hit:
                items.append({**base, "status": "ok", "ref": hit[0]})
                continue
            if kind == "number" and value in dates:
                # A date, year or season is never a worked-out number ("26" in "2025-26" is not 64 minus 38), and it
                # is never flagged: it is not a fact to prove. Its card (today's pane) still says, truthfully, that
                # the sources don't hold it.
                items.append({**base, "status": "date"})
                continue
            possible = None
            if kind == "number" and good_refs:
                # A worked-out number proves itself only from the element's own cited passages, or at most from other
                # passages of the same source documents those citations come from. An element with no valid citation
                # is never marked worked out: arithmetic over the whole corpus will hit some invented number by chance.
                math = computed_match(raw, value, element_text(doc, path, text), passages, good_refs)
                if not math and ".els." in (path or ""):
                    srcs = {passages[r].get("source_id") for r in good_refs if passages.get(r, {}).get("source_id")}
                    same = [r for r in all_ids if passages.get(r, {}).get("source_id") in srcs] if srcs else []
                    if same and len(same) <= 400:
                        math = computed_match(raw, value, element_text(doc, path, text), passages, same)
                if math:
                    items.append({**base, "status": "computed", "ref": math["operands"][0]["ref"], "math": math})
                    continue
            if kind == "number" and ".els." in (path or "") and len(all_ids) <= 400:
                # A wider search is only a hint: "possible match, check the source". It stays flagged and never
                # unblocks export.
                possible = computed_match(raw, value, element_text(doc, path, text), passages, all_ids)
            elsewhere = finder(value, passages, all_ids)
            if elsewhere:
                new_ref = elsewhere[0]
                _fix_ref(doc, path, refs, new_ref)
                fixed.append({"path": path, "value": value, "shown": raw, "ref": new_ref})
                items.append({**base, "status": "moved", "ref": new_ref,
                              "detail": "Found in a different passage. The citation now points there.",
                              "line": _snippet(passages, new_ref, text, raw if kind == "number" else "")})
                continue
            if kind == "number" and value in dates:
                # Not a fact to prove: it is never flagged and never blocks export. Its card (today's pane) still
                # says, truthfully, that the sources don't hold it.
                items.append({**base, "status": "date"})
                continue
            if kind == "number" and value in brief_nums:
                items.append({**base, "status": "brief", "detail": "This number is from your own request."})
                continue
            if kind == "number" and not re.search(r"\d", raw or "") and not HEADLINE_PATH.search(path or ""):
                # A number written as a word in body prose ("Two problems need attention") is checked when the
                # sources hold it and never flagged when they don't: there it is a plain count, not a claim. In a
                # headline, title or figure ("Twelve weeks: the average wait") it is the claim, so it is flagged.
                continue
            status = "kept" if decisions.get(key) == "keep" else "missing"
            probe = text if kind == "number" else value
            near = closest(probe, passages, good_refs) if good_refs else None
            if near is None or near["score"] < 0.5:
                wide = closest(probe, passages, all_ids)
                if wide and (near is None or wide["score"] > near["score"]):
                    near = wide
            if kind == "number":
                # Round 10 (critic 9, S15): the flag names the passage Fix it for me corrects from, the one the
                # rest of the slide rests on, so the card and the fix point at the same source.
                whole = slide_closest(doc, path, text, passages, all_ids)
                if whole:
                    near = whole
            items.append({**base, "status": status, "closest": near, "context": text[:300],
                          "line": _snippet(passages, (near or {}).get("ref"), probe),
                          **({"possible": possible, "detail": "Possible match: check the source."} if possible else {})})
    order = {"missing": 0, "kept": 1, "moved": 2}
    items.sort(key=lambda i: order.get(i["status"], 3))
    missing = [i for i in items if i["status"] == "missing"]
    kept = [i for i in items if i["status"] == "kept"]
    return {"items": items, "fixed": fixed, "missing": missing, "kept": kept, "doc": doc}


# ---------------------------------------------------------------- worked-out numbers --
# "212 more adults than last year" is true when the sources say 1,148 and 936, even though no source writes 212.
# A number passes as computed when it is the result of ONE operation on TWO numbers found in passages the same
# element cites, and the element's own words name that operation ("more", "up", "total", "times"). The pair is
# never searched for across the whole corpus: a big enough pile of numbers makes almost any number by chance.

MINUS, DIVIDE = "−", "÷"
_MONTHS = (r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
           r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?")
_MONTH_BEFORE = re.compile(r"\b(?:" + _MONTHS + r")\.?\s*$", re.I)
_MONTH_AFTER = re.compile(r"^(?:st|nd|rd|th)?\s+(?:of\s+)?(?:" + _MONTHS + r")\b", re.I)
_COUNTER_BEFORE = re.compile(r"\b(?:slide|slides|page|pages|p\.|pp\.|no\.|number|chapter|step|item|line|figure|fig\.|table|"
                             r"version|v|grade|room|route|district|ward|section|part|phase|stage|day|week|month|quarter|q)\s*#?\s*$", re.I)
_YEAR = re.compile(r"(?:19|20)\d\d")

DIFF_CUES = re.compile(r"\b(?:more|fewer|less|minus|subtract(?:ed|ing)?|increase[sd]?|increasing|rise|rises|rose|risen|grew|grow|grows|growth|up|down|"
                       r"gap|difference|remaining|remainder|rest|balance|left|add|added|adds|adding|raise[sd]?|raising|gain(?:ed|s)?|drop(?:ped|s)?|fell|fall|falls|decrease[sd]?|cut|higher|"
                       r"lower|than|above|below|over|under)\b", re.I)
SUM_CUES = re.compile(r"\b(?:total|totals|totaled|totalled|combined|together|in all|altogether|sum|plus|overall|both)\b", re.I)
RATIO_CUES = re.compile(r"\b(?:times|twice|as many|as much|per|each|every|for every|average|x)\b|×|\d\s?x\b", re.I)
PCT_CUES = re.compile(r"\b(?:up|down|more|less|fewer|increase[sd]?|rise|rises|rose|grew|grow|growth|drop(?:ped)?|fell|"
                      r"decline[sd]?|change[sd]?|higher|lower|gain(?:ed)?|jump(?:ed)?|cut|over|since|than|from)\b", re.I)


def is_date_number(text: str, start: int, end: int) -> bool:
    """Whether the number at ``text[start:end]`` is a date, a year, a day of a month, a clock time or a counter like
    "slide 4". Those are never claims: nobody needs a source to know it is October 21."""
    text = text or ""
    raw = text[start:end].strip()
    before, after = text[:start], text[end:]
    digits = re.sub(r"[^\d]", "", raw)
    if not digits:
        # a number written as a word is a counter after "step", "slide", "phase" ("step two"), never a date
        return bool(re.fullmatch(r"[A-Za-z][A-Za-z -]*", raw)) and bool(_COUNTER_BEFORE.search(before))
    if _YEAR.fullmatch(raw) and not after.lstrip().startswith(("%", "percent")):
        return True
    if re.search(r"\b(?:FY|CY|AY)\s*'?$", before, re.I) or re.search(r"(?:FY|CY|AY)\s*$", before):
        return True
    if before.endswith((":", "/")) or re.match(r"^[:/]\d", after):
        return True
    if re.fullmatch(r"\d{2}", raw) and re.search(r"(?:19|20)\d\d\s?[-\u2013\u2014]\s?$", before):
        return True  # the second half of a season or fiscal year: "2025-26"
    if re.fullmatch(r"\d{1,2}", raw) and int(raw) <= 31 and (_MONTH_BEFORE.search(before) or _MONTH_AFTER.match(after)):
        return True
    if re.fullmatch(r"\d{1,3}", raw) and _COUNTER_BEFORE.search(before):
        return True
    if re.fullmatch(r"\d{1,2}", raw) and re.match(r"^\s*(?:a\.m\.|p\.m\.|am|pm)\b", after, re.I):
        return True
    return False


def _dec(value: str):
    """``(Decimal, is_percent)`` for a normalized value from ``content.numbers``, or ``None`` for phones and odd ones."""
    from decimal import Decimal, InvalidOperation
    if not value or value.startswith("tel"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(%|million|billion|thousand)?", value)
    if not m:
        return None
    try:
        d = Decimal(m.group(1))
    except InvalidOperation:
        return None
    unit = m.group(2) or ""
    d *= {"million": Decimal(10) ** 6, "billion": Decimal(10) ** 9, "thousand": Decimal(1000)}.get(unit, 1)
    return d, unit == "%"


def _places(raw: str) -> int:
    """Decimal places as shown: "22.6%" gives 1, "$1,420,000" gives 0, "$12.50" gives 2."""
    m = re.search(r"\d[\d,]*\.(\d+)", raw or "")
    return len(m.group(1)) if m else 0


def _round(d, places: int):
    from decimal import Decimal, ROUND_HALF_UP
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def fmt_number(d, places: int = 0) -> str:
    """1148 as "1,148"; 22.649 at one place as "22.6"; whole values never get a trailing ".0" unless asked."""
    q = _round(d, places)
    s = f"{q:,.{places}f}"
    return s


def _is_money(raw: str) -> bool:
    return bool(re.search(r"[$£€]", raw or "")) or bool(re.search(r"\bdollars?\b", raw or "", re.I))


def operands_in(passages: dict, refs: list, limit: int = 60) -> list:
    """The numbers in the cited passages that can be operands: ``{ref, raw, value, d, money, pos}``. Dates, years,
    phone numbers and percents are left out (a change between two percents is "points", not a percent change)."""
    out, seen = [], set()
    for ref in refs:
        text = (passages.get(ref) or {}).get("text", "") or ""
        for m in K.NUM.finditer(text):
            tok = m.group(0).rstrip(",").rstrip()
            if K._PHONE.fullmatch(tok) or is_date_number(text, m.start(), m.start() + len(tok)):
                continue
            spans = K.number_spans(tok)
            if not spans:
                continue
            raw, value = spans[0]
            got = _dec(value)
            if not got or got[1]:
                continue
            key = (ref, value)
            if key in seen:
                continue
            seen.add(key)
            out.append({"ref": ref, "raw": raw, "value": value, "d": got[0], "money": _is_money(raw), "pos": m.start()})
            if len(out) >= limit:
                return out
    return out


def _operand_view(o: dict, passages: dict) -> dict:
    p = passages.get(o["ref"]) or {}
    line = source_line(p.get("text", ""), o["raw"], o["value"])
    return {"value": o["raw"], "ref": o["ref"], "source": p.get("source_title", ""), "locator": p.get("locator", ""),
            "line": {k: v for k, v in line.items() if k != "exact"} if line else None}


def element_text(doc: dict, path: str, text: str) -> str:
    """The words of the whole element a field belongs to: a stat's "23%" is read with its label and context
    ("more learners than last year"), so the element, not the lone field, names the operation."""
    m = re.match(r"slides\.(\d+)\.", path or "")
    if not m:
        return text or ""
    try:
        sl = (doc.get("slides") or [])[int(m.group(1))]
    except (IndexError, TypeError):
        return text or ""
    if not isinstance(sl, dict):
        return text or ""
    if sl.get("type") == "spec":  # loop 4: a designed slide's words are its elements
        return " ".join([text or "", K._spec().all_text(sl)])
    parts = [str(sl.get(f) or "") for f in K.SLIDE_TEXT]
    return " ".join([text or ""] + [x for x in parts if x])


BOUND = re.compile(r"\b(more than|over|above|at least|upwards of|fewer than|less than|under|below|nearly|almost|about|around|"
                   r"roughly|approximately|close to|some|just over|just under)\s+$", re.I)


def bound_of(field_text: str, raw: str) -> Optional[str]:
    """The qualifier in front of a number ("more than 200", "nearly 1,150"), or ``None``."""
    i = (field_text or "").find(raw)
    if i < 0:
        return None
    m = BOUND.search(field_text[max(0, i - 24):i])
    return m.group(1).lower() if m else None


def bound_ok(qual: str, shown, actual) -> bool:
    """Whether ``actual`` honestly supports "``qual`` ``shown``": a bound within a quarter of the true value, an
    approximation within five percent ("nearly" and "almost" from below)."""
    from decimal import Decimal
    if not shown:
        return False
    if qual in ("more than", "over", "above", "upwards of", "just over"):
        return shown < actual <= shown * Decimal("1.25")
    if qual == "at least":
        return shown <= actual <= shown * Decimal("1.25")
    if qual in ("fewer than", "less than", "under", "below", "just under"):
        return shown * Decimal("0.75") <= actual < shown
    if qual in ("nearly", "almost"):
        return shown * Decimal("0.95") <= actual <= shown
    return abs(actual - shown) <= shown * Decimal("0.05")


def computed_match(raw: str, value: str, field_text: str, passages: dict, refs: list) -> Optional[dict]:
    """The worked-out source of a number that no cited passage writes, or ``None``.

    ``raw`` is the number as shown ("23%", "$190,000"), ``value`` its normalized form, ``field_text`` the element's
    words (they must name the operation), ``refs`` the passages the element cites. Returns
    ``{op, operands: [{value, ref, source, locator, line}] x2, result, text}``.

    Precision is the precision shown: a whole difference or sum matches exactly, money to the cent shown, a whole
    percent matches the change rounded half up, "22.6%" matches to one place, a ratio rounds the same way."""
    got = _dec(value)
    if not got:
        return None
    target, is_pct = got
    words = field_text or ""
    places = _places(raw)
    money = _is_money(raw)
    ops = operands_in(passages, [r for r in refs if r in passages])
    if not ops or (len(ops) < 2 and not bound_of(words, raw)):
        return None

    def build(op: str, a: dict, b: dict, result, text: str) -> dict:
        return {"op": op, "operands": [_operand_view(a, passages), _operand_view(b, passages)], "result": result, "text": text}

    pairs = [(a, b) for a in ops for b in ops if a is not b and a["d"] != b["d"]]
    if is_pct:
        share = _share_of(raw, target, places, pairs, words, build)
        if share:
            return share
        if not PCT_CUES.search(words):
            return None
        for a, b in pairs:
            if not b["d"] or a["money"] != b["money"]:
                continue
            change = (a["d"] - b["d"]) / b["d"] * 100
            if _round(abs(change), places) != _round(target, places):
                continue
            exact_at = max(1, places)
            shown_exact = fmt_number(abs(change), exact_at)
            fa, fb = fmt_number(a["d"], _places(a["raw"])), fmt_number(b["d"], _places(b["raw"]))
            sign = MINUS
            text = f"({fa} {sign} {fb}) {DIVIDE} {fb} = {shown_exact}%"
            if _round(abs(change), exact_at) != _round(target, exact_at):
                text += f", shown as {raw.strip()}"
            return build("pct_change", a, b, f"{shown_exact}%", text)
        return None
    qual = bound_of(words, raw)
    if qual:
        got_bound = _bounded(qual, raw, target, is_pct, money, ops, pairs, words, passages, build)
        if got_bound:
            return got_bound
    if DIFF_CUES.search(words):
        for a, b in pairs:
            if a["d"] <= b["d"] or a["money"] != b["money"] or (money and not a["money"]):
                continue
            if a["d"] - b["d"] == target:
                pa = max(_places(a["raw"]), _places(b["raw"]), places)
                res = fmt_number(target, pa)
                return build("difference", a, b, res, f"{fmt_number(a['d'], pa)} {MINUS} {fmt_number(b['d'], pa)} = {res}")
    if SUM_CUES.search(words):
        for a, b in pairs:
            if a["d"] < b["d"] or a["money"] != b["money"] or (money and not a["money"]):
                continue
            if a["d"] + b["d"] == target:
                pa = max(_places(a["raw"]), _places(b["raw"]), places)
                res = fmt_number(target, pa)
                return build("sum", a, b, res, f"{fmt_number(a['d'], pa)} + {fmt_number(b['d'], pa)} = {res}")
    if RATIO_CUES.search(words):
        for a, b in pairs:
            if not b["d"] or a["d"] <= b["d"] or a["money"] != b["money"]:
                continue
            r = a["d"] / b["d"]
            if _round(r, places) != _round(target, places):
                continue
            fa, fb = fmt_number(a["d"], _places(a["raw"])), fmt_number(b["d"], _places(b["raw"]))
            if r == target:
                return build("ratio", a, b, fmt_number(target, places), f"{fa} {DIVIDE} {fb} = {fmt_number(target, places)}")
            exact_at = places + 1
            return build("ratio", a, b, fmt_number(r, exact_at), f"{fa} {DIVIDE} {fb} = {fmt_number(r, exact_at)}, shown as {raw.strip()}")
    return None


SHARE_CUES = re.compile(r"\b(?:covers?|covering|covered|share|portion|part|of (?:the|our|this|its|all)|funds?|pays?)\b", re.I)


def _share_of(raw, target, places, pairs, words, build) -> Optional[dict]:
    """Loop 3 fix 3: "Your $85,000 would cover 57% of the project" is $85,000 over the $148,000 total, both in the
    cited passages, rounded the way it is shown: a worked-out share, never a blank."""
    if not SHARE_CUES.search(words or ""):
        return None
    for a, b in pairs:
        if not b["d"] or a["d"] >= b["d"] or a["money"] != b["money"]:
            continue
        r = a["d"] / b["d"] * 100
        if _round(r, places) != _round(target, places):
            continue
        fa, fb = fmt_number(a["d"], _places(a["raw"])), fmt_number(b["d"], _places(b["raw"]))
        exact = fmt_number(r, max(1, places))
        return build("share", a, b, f"{exact}%", f"{fa} {DIVIDE} {fb} = {exact}%, shown as {raw.strip()}")
    return None


def _bounded(qual, raw, target, is_pct, money, ops, pairs, words, passages, build) -> Optional[dict]:
    """A bounded number ("more than 200 more learners"): a source number, or one difference or sum the element's
    words name, that honestly meets the bound. The math says what the true value is and how it was shown."""
    if is_pct:
        return None
    shown = f", shown as {qual} {raw.strip()}"
    for o in ops:
        if o["money"] == money and bound_ok(qual, target, o["d"]):
            p = _places(o["raw"])
            return {"op": "bound", "operands": [_operand_view(o, passages)], "result": fmt_number(o["d"], p),
                    "text": f"{fmt_number(o['d'], p)}{shown}"}
    for a, b in pairs:
        if a["money"] != b["money"] or a["money"] != money:
            continue
        pa = max(_places(a["raw"]), _places(b["raw"]))
        if DIFF_CUES.search(words) and a["d"] > b["d"] and bound_ok(qual, target, a["d"] - b["d"]):
            res = fmt_number(a["d"] - b["d"], pa)
            return build("difference", a, b, res, f"{fmt_number(a['d'], pa)} {MINUS} {fmt_number(b['d'], pa)} = {res}{shown}")
        if SUM_CUES.search(words) and a["d"] >= b["d"] and bound_ok(qual, target, a["d"] + b["d"]):
            res = fmt_number(a["d"] + b["d"], pa)
            return build("sum", a, b, res, f"{fmt_number(a['d'], pa)} + {fmt_number(b['d'], pa)} = {res}{shown}")
    return None


def public_items(items: list) -> list:
    """Grounding items as the pane gets them: without the internal copy of each field's text."""
    return [{k: v for k, v in i.items() if k != "field"} for i in items]


# ---------------------------------------------------------------- trace cards --
# Every number in a proof carries a trace: the source line it was found in, with the number marked, the
# source's name and place, and how it matched. The pane shows it when a number is hovered or focused.

HEADLINE_PATH = re.compile(r"(?:^|\.)(?:heading|title|headline|value|amount|figure|big)$")
BOUNDARY = re.compile(r"[.!?](?=\s)|\n")
LINE_MAX = 240


def _span_of(text: str, raw: str, value: str) -> Optional[tuple]:
    """Where ``raw`` (as written in the proof) sits in ``text``: verbatim first, then by normalized value."""
    if re.search(r"\d", raw or ""):
        m = re.search(r"(?<![\d.,])" + re.escape(raw) + r"(?![\d])(?![.,]\d)", text)
    else:  # a number written as a word: "Nine" in a headline is "nine" in the report
        m = re.search(r"(?<![A-Za-z-])" + re.escape(raw) + r"(?![A-Za-z])", text, re.I) if raw else None
    if m:
        return m.start(), m.end(), True
    for m in K.NUM.finditer(text):
        tok = m.group(0).rstrip(",")
        if any(same_value(v, value) for v in K.numbers(tok)[:1]):
            return m.start(), m.start() + len(tok), False
    for raw2, v, a, b in K.spelled_spans(text):
        if same_value(v, value):
            return a, b, False
    return None


def source_line(text: str, raw: str, value: str) -> Optional[dict]:
    """The sentence of ``text`` that holds the number, cut to about two lines, as ``{before, match, after, exact}``."""
    text = text or ""
    hit = _span_of(text, raw, value)
    if not hit:
        return None
    a, b, exact = hit
    stops = [m.end() for m in BOUNDARY.finditer(text)]
    start = max([s for s in stops if s <= a], default=0)
    end = min([s for s in stops if s >= b], default=len(text))
    before, after = text[start:a].lstrip(), text[b:end].rstrip()
    room = max(40, (LINE_MAX - (b - a)) // 2)
    if len(before) > room:
        before = "…" + before[-room:].lstrip()
    if len(after) > room:
        after = after[:room].rstrip() + "…"
    return {"before": before, "match": text[a:b], "after": after, "exact": exact}


def trace_table(items: list, passages: dict, idx: dict, computed: bool = False) -> tuple:
    """``(traces, resolve)`` for one proof.

    ``traces`` is the list the pane shows as cards: ``{status, value, n, source, locator, line}``, status
    ``exact`` (the number as written is in the passage), ``close`` (the same value written another way),
    ``computed`` (worked out from two numbers in the passages it cites; ``math`` shows how; only when the caller
    passes ``computed=True``, since today's pane knows five statuses: without it the card says ``close`` and still
    carries ``math`` and ``worked: True``),
    ``missing`` (not in any source; ``line`` is the closest passage, if any) or ``kept`` (kept on purpose).
    ``resolve(node_text, raw)`` answers which trace a number in a piece of proof text belongs to, as
    ``(index, source_number)``, or ``None`` when the text is not one of the checked fields."""
    by_value = {}
    for it in items:
        if it.get("kind") == "number":
            by_value.setdefault(it["value"], []).append(it)
    sid_n = {}
    for ref, num in sorted(idx.items(), key=lambda kv: kv[1]):
        p = passages.get(ref)
        if p:
            sid_n.setdefault(p.get("source_id"), num)
    traces, seen = [], {}

    def card(it: dict, raw: str) -> tuple:
        status = it.get("status")
        if status == "brief":
            key = ("brief", None, raw)
            if key not in seen:
                seen[key] = len(traces)
                traces.append({"status": "brief", "value": raw, "n": None, "source": "Your request", "locator": "",
                               "line": None})
            return seen[key], None
        if status == "computed":
            math = it.get("math") or {}
            first = (math.get("operands") or [{}])[0]
            p = passages.get(first.get("ref")) if first.get("ref") else None
            num = sid_n.get(p.get("source_id")) if p else None
            key = ("computed", it.get("ref"), raw)
            if key not in seen:
                seen[key] = len(traces)
                traces.append({"status": "computed" if computed else "close", "worked": True, "value": raw, "n": num,
                               "source": (p or {}).get("source_title", ""), "locator": (p or {}).get("locator", ""),
                               "line": first.get("line"), "math": math})
            return seen[key], num
        ref = it.get("ref") if status in ("ok", "moved") else ((it.get("closest") or {}).get("ref"))
        p = passages.get(ref) if ref else None
        line = source_line(p.get("text", ""), raw, it["value"]) if p else None
        if status in ("ok", "moved"):
            shown = "exact" if line and line["exact"] else "close"
        else:
            shown = "kept" if status == "kept" else "missing"
            if p and not line:
                text = (p.get("text") or "").strip()
                line = {"before": text[:LINE_MAX] + ("…" if len(text) > LINE_MAX else ""), "match": "", "after": "", "exact": False}
        num = sid_n.get(p.get("source_id")) if p else None
        key = (shown, ref, raw)
        if key not in seen:
            seen[key] = len(traces)
            traces.append({"status": shown, "value": raw, "n": num if shown in ("exact", "close") or line else None,
                           "source": (p or {}).get("source_title", ""), "locator": (p or {}).get("locator", ""),
                           "line": {k: v for k, v in line.items() if k != "exact"} if line else None})
        return seen[key], (num if shown in ("exact", "close") else None)

    def resolve(node_text: str, raw: str) -> Optional[tuple]:
        v0 = K.value_of(raw)
        vals = [v0] if v0 else []
        if not vals:
            return None
        core = re.sub(r"\s+", " ", (node_text or "").strip().strip("“”\""))
        if not core:
            return None
        cands = [it for it in by_value.get(vals[0], []) if core in re.sub(r"\s+", " ", it.get("field") or "")]
        if not cands:
            return None
        it = min(cands, key=lambda c: len(c.get("field") or ""))
        return card(it, raw)

    return traces, resolve


def _fix_ref(doc: dict, path: str, refs: list, new_ref: str) -> None:
    """Point the field at ``path`` to ``new_ref``: on the nearest object that owns a ``ref`` or ``refs``."""
    if path == "dek":
        if new_ref not in doc.setdefault("dek_refs", []):
            doc["dek_refs"].append(new_ref)
        return
    parts = path.split(".")
    for cut in range(len(parts), 0, -1):
        try:
            owner = K.get_path(doc, ".".join(parts[:cut]))
        except (IndexError, KeyError, TypeError, ValueError):
            continue
        if not isinstance(owner, dict):
            continue
        if "ref" in owner:
            owner["ref"] = new_ref
            return
        if isinstance(owner.get("refs"), list):
            if new_ref not in owner["refs"]:
                owner["refs"].append(new_ref)
            return


def match_label(n: int) -> str:
    """The check stamp for ``n`` numbers that all match: "No numbers to check.", "The 1 number matches your
    sources.", "All 14 numbers match your sources." (contract F)."""
    n = int(n or 0)
    if n <= 0:
        return "No numbers to check."
    if n == 1:
        return "The 1 number matches your sources."
    return f"All {n} numbers match your sources."


def _all_found(checked: int) -> str:
    return "The 1 number or quote found in your sources" if checked == 1 else f"All {checked} numbers and quotes found in your sources"


def pill_sources(g: dict) -> dict:
    n_missing, n_kept = len(g["missing"]), len(g["kept"])
    checked = len([i for i in g["items"] if i["kind"] in ("number", "quote") and i["status"] != "date"])
    from_brief = sum(1 for i in g["items"] if i["status"] == "brief")
    if n_missing:
        nums = sum(1 for i in g["missing"] if i["kind"] == "number")
        quotes = sum(1 for i in g["missing"] if i["kind"] == "quote")
        refs = sum(1 for i in g["missing"] if i["kind"] == "ref")
        parts = []
        if nums:
            parts.append(f"{nums} number{'s' if nums != 1 else ''}")
        if quotes:
            parts.append(f"{quotes} quote{'s' if quotes != 1 else ''}")
        if refs:
            parts.append(f"{refs} citation{'s' if refs != 1 else ''}")
        return {"id": "sources", "tone": "bad", "label": f"{' and '.join(parts)} not found in sources",
                "items": public_items(g["missing"]), "blocking": True}
    if n_kept:
        return {"id": "sources", "tone": "warn", "label": f"{n_kept} kept on purpose, not in sources", "items": public_items(g["kept"])}
    worked = sum(1 for i in g["items"] if i["status"] == "computed")
    if g["fixed"]:
        tail = f"; {worked} worked out from them" if worked else ""
        return {"id": "sources", "tone": "good", "label": f"{_all_found(checked)}{tail}; {len(g['fixed'])} citation{'s' if len(g['fixed']) != 1 else ''} corrected",
                "items": g["fixed"]}
    if not checked:
        return {"id": "sources", "tone": "good", "label": "No numbers or quotes to check", "items": []}
    tail = f"; {worked} worked out from them" if worked else ""
    tail += f"; {from_brief} from your request" if from_brief else ""
    return {"id": "sources", "tone": "good", "label": f"{_all_found(checked)}{tail}", "items": []}


def pill_contrast(palette: dict) -> dict:
    fails = [p for p in palette.get("pairs", []) if not p.get("passes")]
    if fails:
        return {"id": "contrast", "tone": "bad", "label": f"{len(fails)} color pair{'s' if len(fails) != 1 else ''} below AA",
                "items": fails}
    down = palette.get("downgraded") or []
    if down:
        return {"id": "contrast", "tone": "warn",
                "label": f"Contrast passes; {len(down)} brand color{'s' if len(down) != 1 else ''} kept to rules and fills",
                "items": down}
    low = min((p["ratio"] for p in palette.get("pairs", [])), default=21)
    return {"id": "contrast", "tone": "good", "label": f"Contrast passes, lowest {low:.1f}:1", "items": palette.get("pairs", [])}


def pill_never(doc: dict, never: list, changes: list) -> dict:
    hits = K.never_hits(doc, never)
    if hits:
        words = sorted({h["word"] for h in hits})
        return {"id": "never", "tone": "warn", "label": f"Never-say word used: {', '.join(words)}", "items": hits}
    if changes:
        return {"id": "never", "tone": "good", "label": f"Voice rules applied ({len(changes)} swap{'s' if len(changes) != 1 else ''})", "items": changes}
    return {"id": "never", "tone": "good", "label": "No never-say words", "items": []}


def pill_required(required: list, page_text: str) -> Optional[dict]:
    if not required:
        return None
    flat = norm_text(page_text)
    missing = [r for r in required if norm_text(r) not in flat]
    if missing:
        return {"id": "required", "tone": "bad", "label": f"{len(missing)} required line{'s' if len(missing) != 1 else ''} missing", "items": missing}
    return {"id": "required", "tone": "good", "label": "Required lines present", "items": required}


def pill_fonts(subs: list, stands_in: Optional[list] = None) -> dict:
    swaps = [s for s in subs if not s.get("note")]
    if swaps:
        text = "; ".join(f"{s['used']} in place of {s['wanted']}" for s in swaps)
        return {"id": "fonts", "tone": "warn", "label": f"Font substituted: {text}", "items": subs}
    if subs:
        return {"id": "fonts", "tone": "warn", "label": subs[0]["note"], "items": subs}
    if stands_in:
        fams = ", ".join(dict.fromkeys(stands_in))
        return {"id": "fonts", "tone": "good", "label": f"Kit fonts used; {fams} stands in for a licensed typeface",
                "items": [f"{f} is an open (OFL) font standing in for the licensed typeface the original look used." for f in dict.fromkeys(stands_in)]}
    return {"id": "fonts", "tone": "good", "label": "Kit fonts used", "items": []}


def pill_voice(reverted: list) -> Optional[dict]:
    if not reverted:
        return None
    if reverted == ["all"]:
        return {"id": "voice", "tone": "warn", "label": "Kept the plain wording: the voice pass didn't come back usable", "items": reverted}
    return {"id": "voice", "tone": "warn",
            "label": f"Kept the plain wording in {len(reverted)} place{'s' if len(reverted) != 1 else ''}: the voice pass changed a fact",
            "items": reverted}


_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "a": 1, "ninety": 90, "thirty": 30, "forty-five": 45, "sixty": 60, "half": 0.5}
_TARGET = re.compile(r"\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|ninety|thirty|forty-five|sixty|half)"
                     r"[\s-]*(?:an?\s+)?(second|sec|minute|min)s?\b", re.I)


def target_minutes(brief: str) -> Optional[float]:
    """The length the person asked for ("a 90-second brief", "three-minute"), in minutes, or ``None``."""
    m = _TARGET.search(brief or "")
    if not m:
        return None
    raw = m.group(1).lower()
    n = float(raw) if re.fullmatch(r"\d+(?:\.\d+)?", raw) else float(_WORDNUM.get(raw, 0))
    if not n:
        return None
    return round(n / 60.0 if m.group(2).lower().startswith("sec") else n, 2)


def pill_length(minutes: float, brief: str = "") -> dict:
    """How long the audio brief runs, read at a steady 150 words a minute, against the length the person asked
    for in the brief (within a quarter either way), or two to four minutes when they named none."""
    want = target_minutes(brief)
    if want:
        lo, hi = want * 0.75, want * 1.25 + 0.15
        tone = "good" if lo <= minutes <= hi else "warn"
        shown = f"{int(round(want * 60))} seconds" if want <= 1.5 else f"{want:g} minutes"
        label = f"About {minutes:g} min" + (f", as asked ({shown})" if tone == "good" else (f", short of the {shown} asked" if minutes < lo else f", over the {shown} asked"))
        return {"id": "length", "tone": tone, "label": label, "items": [f"{minutes} minutes at 150 words a minute; you asked for {shown}"]}
    tone = "good" if 1.8 <= minutes <= 4.4 else "warn"
    label = f"About {max(1, round(minutes))} min" + ("" if tone == "good" else (", short" if minutes < 1.8 else ", long"))
    return {"id": "length", "tone": tone, "label": label, "items": [f"{minutes} minutes at 150 words a minute"]}


def blocking(pills: list) -> bool:
    return any(p and p.get("blocking") for p in pills)


# ---------------------------------------------------------------- claims for the canvas --
# The canvas proves a number with an underline and a card. ``claims_map`` turns the grounding items into the
# claims the contract (docs/API-NOTEBOOK.md, section 3) names: one claim per number or quote, shared when the
# same number from the same passage shows on several slides. Dates, years and counters are never claims.

STATUS_SHOWN = {"ok": None, "moved": None, "computed": "computed", "missing": "missing", "kept": "kept", "brief": "brief"}


def _claim_kind(item: dict) -> str:
    if item.get("kind") == "quote":
        return "quote"
    if str(item.get("value", "")).endswith("%"):
        return "percent"
    return "money" if _is_money(item.get("shown") or "") else "count"


def _is_date_item(item: dict) -> bool:
    if item.get("kind") != "number":
        return False
    field, shown = item.get("field") or "", item.get("shown") or ""
    hit = _span_of(field, shown, item.get("value", "")) if shown else None
    return bool(hit) and is_date_number(field, hit[0], hit[1])


def claims_map(items: list, passages: dict, idx: dict, frame_of=None) -> tuple:
    """``(claims, passages_used, claim_of)`` for one proof.

    ``items`` come from ``grounding``; ``idx`` is ``layout.source_index``'s ref-to-number map; ``frame_of(path)``
    gives the frame a field path lands on (0 when left out: a one-pager or a graphic is one frame).
    ``claim_of(path, raw)`` says which claim id a number (or, with ``raw=None``, a quote) in that field carries,
    for the ``tr`` key in the scene tree."""
    frame_of = frame_of or (lambda _path: 0)
    sid_n = {}
    for ref, num in sorted((idx or {}).items(), key=lambda kv: kv[1]):
        p = passages.get(ref)
        if p:
            sid_n.setdefault(p.get("source_id"), num)

    def src(ref):
        p = passages.get(ref) if ref else None
        return (p or {}), (sid_n.get(p.get("source_id")) if p else None)

    claims, by_group, by_field = {}, {}, {}
    usable = [i for i in items if i.get("kind") in ("number", "quote") and i.get("status") != "date" and not _is_date_item(i)]
    usable.sort(key=lambda i: (frame_of(i.get("path", "")), i.get("path", "")))
    for it in usable:
        status = it.get("status")
        ref = it.get("ref") if status in ("ok", "moved", "computed") else (it.get("closest") or {}).get("ref")
        p, n = src(ref)
        line = None
        shown = STATUS_SHOWN.get(status, "missing")
        if status in ("ok", "moved"):
            if it.get("kind") == "number":
                ln = source_line(p.get("text", ""), it.get("shown") or "", it["value"]) if p else None
                shown = "exact" if ln and ln["exact"] else "close"
                line = {k: v for k, v in ln.items() if k != "exact"} if ln else None
            else:
                shown = "exact"
                sent = best_sentence(p.get("text", ""), it["value"]) if p else ""
                line = {"before": "", "match": sent, "after": ""} if sent else None
        elif status == "computed":
            first = ((it.get("math") or {}).get("operands") or [{}])[0]
            line = first.get("line")
        elif p:
            sent = best_sentence(p.get("text", ""), it.get("field") or it.get("value", ""))
            line = {"before": sent, "match": "", "after": ""}
        math = None
        if status == "computed" and it.get("math"):
            math = copy.deepcopy(it["math"])
            for o in math.get("operands") or []:
                o["source_n"] = src(o.get("ref"))[1]
        group = (it.get("kind"), it.get("value"), shown, ref)
        frame = frame_of(it.get("path", ""))
        cid = by_group.get(group)
        if cid is None:
            cid = f"c{len(claims) + 1}"
            by_group[group] = cid
            claims[cid] = {"kind": _claim_kind(it), "value": it.get("shown") or it.get("value"), "status": shown, "ref": ref,
                           "source_n": n, "source": p.get("source_title", ""), "locator": p.get("locator", ""), "line": line,
                           "math": math, "slides": [], "key": it.get("key"), "fixable": shown == "missing"}
        if frame not in claims[cid]["slides"]:
            claims[cid]["slides"].append(frame)
            claims[cid]["slides"].sort()
        by_field[(it.get("path"), it.get("value") if it.get("kind") == "number" else None)] = cid

    used = {}
    for cid, c in claims.items():
        refs = [c["ref"]] if c["ref"] and c["status"] not in ("missing", "kept", "brief") else []
        refs += [o.get("ref") for o in ((c.get("math") or {}).get("operands") or []) if o.get("ref")]
        for r in refs:
            p, n = src(r)
            if not p:
                continue
            u = used.setdefault(r, {"source_n": n, "source": p.get("source_title", ""), "locator": p.get("locator", ""),
                                    "text": (p.get("text") or "").strip()[:LINE_MAX * 3], "slides": []})
            for f in c["slides"]:
                if f not in u["slides"]:
                    u["slides"].append(f)
            u["slides"].sort()

    def claim_of(path: str, raw: Optional[str]) -> Optional[str]:
        if raw is None:
            return by_field.get((path, None))
        v0 = K.value_of(raw)
        return by_field.get((path, v0)) if v0 else None

    return claims, used, claim_of


def check_line(text: str, refs: list, passages: dict, all_ids: Optional[list] = None) -> dict:
    """Check one free sentence (a guide line, a likely question, a fixed headline) the way ``grounding`` checks a
    field: every number and quote must be in a cited passage, worked out from two numbers in them, or (for a number
    written as is) in another passage, whose ref is then added. Dates and counters are skipped.

    Returns ``{ok, refs, items}``; ``ok`` is False when anything is missing."""
    refs = [r for r in dict.fromkeys(refs or []) if r in passages]
    all_ids = list(all_ids if all_ids is not None else passages.keys())
    items, ok = [], True
    for raw, value, a, b in K.claim_spans(text or ""):
        if is_date_number(text, a, b):
            continue
        if value.startswith("tel"):
            continue
        hit = find_number(value, passages, refs)
        if hit:
            items.append({"value": raw, "status": "exact", "ref": hit[0]})
            continue
        math = computed_match(raw, value, text, passages, refs) if refs else None
        if math:
            items.append({"value": raw, "status": "computed", "ref": math["operands"][0]["ref"], "math": math})
            continue
        elsewhere = find_number(value, passages, all_ids)
        if elsewhere:
            refs.append(elsewhere[0])
            items.append({"value": raw, "status": "moved", "ref": elsewhere[0]})
            continue
        if not re.search(r"\d", raw or ""):
            continue  # a number written as a word is never flagged (see grounding)
        ok = False
        items.append({"value": raw, "status": "missing", "ref": None})
    for m in QUOTE.finditer(text or ""):
        q = m.group(1)
        hit = find_quote(q, passages, refs) or find_quote(q, passages, all_ids)
        if hit:
            if hit[0] not in refs:
                refs.append(hit[0])
            items.append({"value": q, "status": "exact", "ref": hit[0]})
        else:
            ok = False
            items.append({"value": q, "status": "missing", "ref": None})
    return {"ok": ok, "refs": refs, "items": items}


# ---------------------------------------------------------------- wording and coverage (P6 round 2) --
# The number checker passes "1,148" and cannot see the words around it. Two plain checks catch what the bench found:
# a superlative the cited passage never uses ("coldest night" where the report says "busiest"), and a deck that leaves
# out a passage of money figures (a budget, a funding mix) that a funder needs.

_SUPER = re.compile(r"\b([A-Za-z]{3,}est|record|first|only|largest|biggest|highest|lowest|worst|best)\b", re.I)
_NOT_SUPER = {"interest", "request", "honest", "forest", "harvest", "guest", "rest", "test", "west", "suggest", "invest", "contest",
              "protest", "arrest", "digest", "chest", "nest", "quest", "manifest", "modest", "earnest", "priest", "behest",
              "conquest", "inquest", "midwest", "southwest", "northwest", "attest", "detest", "infest", "unrest", "pest",
              "zest", "vest", "crest", "jest", "lest", "bequest", "interests", "requested"}
_MONEY = re.compile(r"[$£€]\s?\d")


def wording(doc: dict, passages: dict) -> list:
    """Fields that state a sourced number with a superlative ("coldest", "record", "first") their cited passages
    never use. Quotes are the source's own words and are skipped. Each hit: path, word, field."""
    hits = []
    for path, text, refs in K.field_texts(doc):
        if K.is_quote_path(path) or not text or not K.numbers(element_text(doc, path, text)):
            continue
        src = " ".join((passages.get(r) or {}).get("text", "") for r in refs if r in passages).lower()
        if not src:
            continue
        for m in _SUPER.finditer(text):
            w = m.group(1).lower()
            if w in _NOT_SUPER or re.search(r"\b" + re.escape(w) + r"\b", src):
                continue
            if w == "first" and re.match(r"\s+(two|three|four|five|\d)", text[m.end():], re.I):
                continue  # "the first two bars" counts, it claims nothing
            hits.append({"path": path, "word": w, "field": text})
    return hits


def pill_wording(hits: list) -> Optional[dict]:
    if not hits:
        return None
    words = sorted({h["word"] for h in hits})
    return {"id": "wording", "tone": "warn", "items": hits,
            "label": f"Check the wording: {', '.join(chr(8220) + w + chr(8221) for w in words[:3])} isn't in the source it cites"}


def money_left_out(doc: dict, passages: dict) -> list:
    """Passages that give two or more money figures (a budget, a funding mix, a cost breakdown) that no slide cites."""
    if K.kind_of(doc) != "deck":
        return []
    cited = set()
    for sl in doc.get("slides") or []:
        cited.update(sl.get("refs") or [])
        for lst in K.SLIDE_LISTS:
            cited.update(it.get("ref") for it in sl.get(lst) or [] if isinstance(it, dict) and it.get("ref"))
    out = []
    for ref, p in passages.items():
        if ref not in cited and len(_MONEY.findall(p.get("text") or "")) >= 2:
            out.append({"ref": ref, "where": f"{p.get('source_title', 'Source')}, {p.get('locator', '')}".strip(", ")})
    return out


def pill_money(left: list) -> Optional[dict]:
    if not left:
        return None
    return {"id": "money", "tone": "warn", "items": left,
            "label": "The deck leaves out money figures from " + "; ".join(x["where"] for x in left[:2])}


# ---------------------------------------------------------------- round 3: money shown, repeats, relation words --
# Round 3 of the bench found three faults the checks above could not see: a deck that cites the money passage once
# (for one number) and still leaves its funding mix out; one figure set big on four slides; and sourced facts whose
# relation words drifted ("over a year" for an average of 14 months, "live near" for "waiting at").

_MONEY_FIG = re.compile(r"[$£€]\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(million|thousand|[MK])\b)?")


def _money_key(num: str, unit: str = "") -> str:
    v = (num or "").replace(",", "")
    try:
        f = float(v)
    except ValueError:
        return v
    mult = {"million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}.get((unit or "").lower(), 1)
    return str(int(round(f * mult)))


def money_figures(text: str) -> list:
    """The money figures a text states, as ``(shown, key)``: "$1.42 million" and "$1,420,000" share a key."""
    return [(m.group(0).rstrip(",."), _money_key(m.group(1).rstrip(",."), m.group(2) or "")) for m in _MONEY_FIG.finditer(text or "")]


_BUDGET = re.compile(r"\b(budget|cost|costs|fund|funds|funded|funding|grant|grants|donat\w*|donors?|paid|spending|spent|"
                     r"expenses?|revenue|contract|reserve|salar\w*)\b", re.I)


def money_not_shown(doc: dict, passages: dict) -> list:
    """Each money passage (two or more money figures: a budget, a funding mix, a cost breakdown) whose figures are not
    all on some slide. Citing the passage is not enough: its figures must be shown. Each: ref, where, missing."""
    if K.kind_of(doc) != "deck":
        return []
    shown = set()
    for _p, text, _r in K.field_texts(doc):
        shown.update(k for _s, k in money_figures(text))
        shown.update(re.sub(r"[^\d]", "", n) for n in K.numbers(text) if re.search(r"\d{3}", n))
    out = []
    for ref, p in passages.items():
        figs = money_figures(p.get("text") or "")
        if len(figs) < 2 or not _BUDGET.search(p.get("text") or ""):
            continue  # a price list is not a budget: only money that funds or costs the work must be shown
        missing = list(dict.fromkeys(s for s, k in figs if k not in shown))
        if missing:
            out.append({"ref": ref, "where": f"{p.get('source_title', 'Source')}, {p.get('locator', '')}".strip(", "),
                        "missing": missing})
    return out


def pill_money_shown(left: list) -> Optional[dict]:
    if not left:
        return None
    figs = [f for x in left for f in x["missing"]]
    return {"id": "money", "tone": "warn", "items": left,
            "label": "The deck leaves out " + ", ".join(figs[:4]) + (" and more" if len(figs) > 4 else "") + " from "
                     + "; ".join(x["where"] for x in left[:2])}


def _core(n: str) -> str:
    """A number's identity for the repeat check: "214", "214 events" and "214" are one; "$1,237" and "1,237" are one."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", n or "")
    return m.group(0).replace(",", "") if m else ""


def big_figures(doc: dict) -> list:
    """Where the deck sets a number big: each slide's heading (or a stat's label), its stat value, its figures, its
    figure-led points and its closing amount, plus the cover (the opening exhibit's finding bar, which the cover
    repeats). A slide counts each number once. Each: (slide index or -1 for the cover, core number, as shown, path)."""
    out = []
    sls = doc.get("slides") or []
    lead = next((i for i, sl in enumerate(sls) if sl.get("type") not in ("section", "quote")), None)
    if lead is not None and sls[lead].get("type") == "exhibit":
        b = next((b for b in sls[lead].get("bars") or [] if b.get("accent") is True), None)
        if b and not re.search(r"[$£€]", b.get("value", "")) and _core(b.get("value")):
            out.append((-1, _core(b["value"]), b["value"], "cover"))
    for i, sl in enumerate(sls):
        seen = set()
        places = [(f"slides.{i}.heading", sl.get("heading") or "")]
        if sl.get("type") == "stat":
            places += [(f"slides.{i}.value", sl.get("value") or ""), (f"slides.{i}.label", sl.get("label") or "")]
        places += [(f"slides.{i}.figures.{j}", f.get("value") or "") for j, f in enumerate(sl.get("figures") or [])]
        places += [(f"slides.{i}.bullets.{j}.figure", b.get("figure") or "") for j, b in enumerate(sl.get("bullets") or [])]
        places.append((f"slides.{i}.amount", sl.get("amount") or ""))
        for path, text in places:
            for n in K.numbers(text) if not path.endswith(("value", "figure", "amount")) and ".figures." not in path else [text]:
                c = _core(n)
                if not c or c in seen or (len(c) == 4 and c.startswith(("19", "20"))):
                    continue  # a year names a time, not a finding
                seen.add(c)
                out.append((i, c, n, path))
    return out


def repeats(doc: dict) -> list:
    """Numbers set big on more than one slide (the cover counts). Each: number, where (paths after the first)."""
    by: dict = {}
    for i, c, shown, path in big_figures(doc):
        by.setdefault(c, []).append((i, shown, path))
    return [{"number": v[0][1], "first": v[0][2], "again": [p for _i, _s, p in v[1:]]} for c, v in by.items() if len(v) > 1]


def pill_repeats(hits: list) -> Optional[dict]:
    if not hits:
        return None
    return {"id": "repeats", "tone": "warn", "items": hits,
            "label": "Set big more than once: " + ", ".join(h["number"] for h in hits[:4])}


# Relation words a sourced fact must keep. Each family: the words that mean the same relation. When the cited
# sentence holds the number with a word of a family, the deck's field must use a word of that family too
# ("average": the average tutor stayed 14 months); and a field may not add a relation the cited passages never use
# ("live near" where the source says "waiting at"; "over a year" where it gives an average).
RELATION = {
    "average": ("average", "averages", "averaged", "on average", "typical", "mean"),
    "median": ("median",),
    "about": ("about", "approximately", "roughly", "around", "nearly", "almost", "some"),
    "estimate": ("estimate", "estimates", "estimated", "expect", "expects", "expected", "projected", "projects"),
    "at most": ("up to", "at most", "within", "no more than"),
    "at least": ("at least", "more than", "over", "upward of"),
}
_ADDED = re.compile(r"\b(over a year|more than a year|over (?:a|one|two|three) (?:year|month|decade)s?|"
                    r"lives? (?:near|in|around|close to)|living (?:near|in)|reside[sd]? (?:near|in)|"
                    r"farthest|furthest|every|always|never|all of|guaranteed?)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")


def _has(text: str, words) -> bool:
    t = " " + re.sub(r"\s+", " ", (text or "").lower()) + " "
    return any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words)


def _item_text(doc: dict, path: str, text: str) -> str:
    """The words a reader sees with a field: a figure with its label and context, a point with its figure."""
    parts = path.split(".")
    try:
        if len(parts) >= 4 and parts[0] == "slides":
            sl = doc["slides"][int(parts[1])]
            it = (sl.get(parts[2]) or [])[int(parts[3])]
            if isinstance(it, dict):
                return " ".join(str(v) for k, v in it.items() if k != "ref" and isinstance(v, str))
    except (IndexError, KeyError, ValueError, TypeError):
        pass
    return text


def drift(doc: dict, passages: dict) -> list:
    """Sourced facts whose relation words drifted from the cited sentence. Each: path, field, word, source."""
    hits = []
    for path, text, refs in K.field_texts(doc):
        if K.is_quote_path(path) or not text or path.endswith(".figure") or not refs:
            continue
        src = " ".join((passages.get(r) or {}).get("text", "") for r in refs if r in passages)
        if not src:
            continue
        seen = _item_text(doc, path, text)
        for m in _ADDED.finditer(text):
            w = m.group(1).lower()
            if not _has(src, [w]) and not (w.startswith(("live", "living", "reside")) and _has(src, ["live", "lives", "living", "reside"])):
                hits.append({"path": path, "field": text, "word": w, "source": "", "kind": "added"})
        for n in K.numbers(text):
            core = n.replace(",", "")
            digits = re.sub(r"[^\d.]", "", core)
            if not digits or len(digits) < 1:
                continue
            for sent in _SENT.split(src):
                if not re.search(r"(?<![\d,.])" + re.escape(n.lstrip("$£€")) + r"(?![\d])", sent):
                    continue
                pos = sent.find(n.lstrip("$£€"))
                before = " ".join(sent[:pos].split()[-4:])  # the words that qualify a number sit just before it
                after = " ".join(sent[pos + len(n):].split()[:3])
                window = before + " " + ("on average" if _has(after, ["on average"]) else "")
                for fam, words in RELATION.items():
                    if fam == "estimate":
                        if _has(sent[:pos], ("estimate", "estimates", "estimated", "projected")) and not _has(seen, words):
                            hits.append({"path": path, "field": text, "word": fam, "source": sent.strip()[:200], "kind": "dropped"})
                    elif _has(window, words) and not _has(seen, words):
                        hits.append({"path": path, "field": text, "word": fam, "source": sent.strip()[:200], "kind": "dropped"})
                break
    out, keys = [], set()
    for h in hits:
        k = (h["path"], h["word"])
        if k not in keys:
            keys.add(k)
            out.append(h)
    return out


def pill_drift(hits: list) -> Optional[dict]:
    if not hits:
        return None
    words = sorted({h["word"] for h in hits})
    return {"id": "relation", "tone": "warn", "items": hits,
            "label": "Check the wording against the source: " + ", ".join(chr(8220) + w + chr(8221) for w in words[:3])}


def deck_problems(doc: dict, passages: dict) -> dict:
    """Everything the make job repairs before the voice pass: money not shown, repeats, wording drift, superlatives."""
    return {"money": money_not_shown(doc, passages), "repeats": repeats(doc), "drift": drift(doc, passages),
            "wording": wording(doc, passages)}


def unsourced(doc: dict, passages: dict) -> list:
    """Numbers and quotes the trace finds in no passage and cannot work out (round 6: the one pass is checked by code
    and only what fails goes to the one repair call). ``[{path, kind, value, field}]``; a citation of a passage that is
    not in the sources is one too."""
    out = []
    for i in grounding(doc, passages)["missing"]:
        out.append({"path": i["path"], "kind": i["kind"], "value": i["value"], "field": (i.get("field") or i.get("value") or "")[:200]})
    return out


def case_left_out(case: str, doc: dict, passages: dict) -> list:
    """Numbers the one pass's own case names as its evidence that no slide shows (round 6: a pass planned to use the
    74% finding and then left it off every slide). Only numbers a passage holds, never years. ``[{number, sentence}]``."""
    if not case:
        return []
    shown = set()
    for _path, text, _refs in K.field_texts(doc):
        shown |= _num_set(text)
    shown |= _num_set(doc.get("title") or "") | _num_set(doc.get("subtitle") or "")
    held = set()
    for p in passages.values():
        held |= set(K.numbers(p.get("text") or ""))
    out, seen = [], set()
    for sent in SENTENCE.findall(case):
        for raw, v in K.number_spans(sent):
            if v in seen or v in shown or v not in held or _YEAR.fullmatch(v):
                continue
            seen.add(v)
            out.append({"number": raw, "sentence": sent.strip()[:220]})
    return out


def problem_count(p: dict) -> int:
    return (sum(len(x["missing"]) for x in p.get("money") or []) + sum(len(x["again"]) for x in p.get("repeats") or [])
            + len(p.get("drift") or []) + len(p.get("wording") or []) + len(p.get("off_title") or [])
            + len(p.get("unsourced") or []) + len(p.get("case") or []) + len(p.get("filler") or []))


# ---------------------------------------------------------------- filler (round 8) --
# Three critics named the same slides: a list whose points say the headline again ("Most adults on the waitlist are at
# Eastgate and Riverside" over "Most adults on the waitlist wait at Eastgate or Riverside"). A point restates its
# slide's title when most of its content words are the title's words. A content slide is filler when a point restates
# the title and its points show at most one number: the one repair call rebuilds it as figures from its passages.

_FILLER_STOP = set("""a an the and or of to in on at for by with from as is are was were be been being that this these those
it its their our we they he she his her them us who which what when where how than then so but not no if into over under
about more most some any each all also just still had has have do did does will would can could may might per year end""".split())


def _content_words(text: str) -> set:
    out = set()
    for w in re.findall(r"[a-z]+", (text or "").lower()):
        if w in _FILLER_STOP or len(w) < 3:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def restates(point: str, title: str) -> bool:
    """Whether a point says its slide's title again: at least 60% of its content words are the title's, and it adds
    no number the title lacks."""
    pw, tw = _content_words(point), _content_words(title)
    if len(pw) < 2 or not tw:
        return False
    new_nums = {v for _r, v, _a, _b in K.claim_spans(point)} - {v for _r, v, _a, _b in K.claim_spans(title)}
    return not new_nums and len(pw & tw) / len(pw) >= 0.6


def filler(doc: dict, passages: Optional[dict] = None) -> list:
    """Content slides whose points add nothing new: ``{path, i, heading, restating, numbers, rebuild}``. ``rebuild`` is
    True (rebuild it as a figures slide) when a point restates the title and the points show at most one number and
    the slide's passages hold at least two numbers to show; otherwise only the restating points are named."""
    passages = passages or {}
    out = []
    for i, sl in enumerate(doc.get("slides") or []):
        if sl.get("type") != "content":
            continue
        head = sl.get("heading") or ""
        pts = [b.get("text", "") for b in sl.get("bullets") or [] if isinstance(b, dict)]
        same = [t for t in pts if restates(t, head)]
        if not same:
            continue
        nums = {v for t in pts for _r, v, _a, _b in K.claim_spans(t)}
        refs = [r for r in dict.fromkeys((sl.get("refs") or []) + [b.get("ref") for b in sl.get("bullets") or []
                                                                    if isinstance(b, dict) and b.get("ref")]) if r in passages]
        held = {v for r in refs for raw, v, a, b in K.claim_spans(passages[r].get("text", ""))
                if not is_date_number(passages[r].get("text", ""), a, b)}
        big = {c for j, c, _n, _p in big_figures(doc) if j != i}
        fresh = {v for v in held if _core(v) not in big}
        out.append({"path": f"slides.{i}", "i": i, "heading": head, "restating": same, "numbers": len(nums),
                    "rebuild": len(nums) <= 1 and len(held) >= 2, "refs": refs,
                    # three numbers no other slide sets big make a figures slide; fewer make one big number
                    "as": "figures" if len(fresh) >= 3 else "stat"})
    return out


POINT_FIELDS = ("bullets", "figures", "rows", "left_items", "right_items", "steps", "bars")


def point_refs(slide: dict) -> list:
    """The refs a slide's own points cite (points, figures, rows, steps, bars), in order."""
    out = []
    for f in POINT_FIELDS:
        for it in slide.get(f) or []:
            r = it.get("ref") if isinstance(it, dict) else None
            if r and r not in out:
                out.append(r)
    return out


def off_title(doc: dict, outline: Optional[dict]) -> list:
    """Slides built from an outline whose points cite none of the passages their title rests on (round 5): the
    title says one thing and the points another (a slide titled on the farms whose points are menu items).
    ``[{path, heading, want, got}]``. A slide with no points (a quote, a stat, the closing) is never off."""
    want = (outline or {}).get("slides") or []
    out = []
    for i, (sl, ol) in enumerate(zip(doc.get("slides") or [], want)):
        if sl.get("type") in ("stat", "quote", "closing", "section", "title", "image"):
            continue
        got, refs = point_refs(sl), [r for r in ol.get("refs") or [] if r]
        if got and refs and not set(got) & set(refs):
            out.append({"path": f"slides.{i}", "heading": sl.get("heading") or sl.get("label") or "", "want": refs, "got": got})
    return out


def trim_repeats(doc: dict) -> dict:
    """What is left after the repair: a later figures-slide figure or point figure that repeats a number set big
    earlier is taken off when the slide keeps enough without it (three figures; a point keeps its words)."""
    out = copy.deepcopy(doc)
    for h in repeats(out):
        for path in h["again"]:
            parts = path.split(".")
            if len(parts) < 4 or parts[0] != "slides":
                continue
            sl = out["slides"][int(parts[1])]
            if parts[2] == "figures" and len(sl.get("figures") or []) > 3:
                sl["figures"] = [f for j, f in enumerate(sl["figures"]) if j != int(parts[3])]
            elif parts[2] == "bullets" and path.endswith(".figure"):
                b = sl["bullets"][int(parts[3])]
                f = b.pop("figure", "")
                if f and f not in b.get("text", ""):
                    t = b.get("text", "")
                    b["text"] = f"{f} {t[:1].lower() + t[1:] if t[:1].isupper() and not t[1:2].isupper() else t}".strip()
                sl["bullets"] = K.even_points(sl["bullets"])
    return out


_QUAL_BEFORE = re.compile(r"\b(at least|about|approximately|roughly|nearly|almost|more than|up to|within|an average of|on average)\s+$", re.I)


def keep_qualifiers(doc: dict, passages: dict) -> tuple:
    """A dropped relation word put back where it belongs: when the cited sentence sets a word like "at least" or "about"
    right before the number ("stayed at least 12 weeks"), and the deck's field has the same number without it, the
    word goes back in front of the number. Returns ``(doc, fixed paths)``. Only plain text fields are touched."""
    out = copy.deepcopy(doc)
    fixed = []
    for h in drift(out, passages):
        if h.get("kind") != "dropped" or not h.get("source"):
            continue
        path = h["path"]
        try:
            text = K.get_path(out, path)
        except (IndexError, KeyError, TypeError):
            continue
        if not isinstance(text, str):
            continue
        for n in K.numbers(text):
            pos = h["source"].find(n.lstrip("$£€"))
            m = _QUAL_BEFORE.search(h["source"][:pos]) if pos > 0 else None
            at = text.find(n)
            if not m or at < 0 or _QUAL_BEFORE.search(text[:at]):
                continue
            word = m.group(1).lower()
            new = text[:at] + word + " " + text[at:]
            if at == 0:
                new = word[:1].upper() + word[1:] + " " + text
            K.set_path(out, path, new)
            fixed.append(path)
            break
    return out, fixed


# ---------------------------------------------------------------- a fix keeps the meaning --
# Round 10 (critics 7, 8, 9, S15/S16): "Staff estimate 180 more learners" fixed to "180 more learners in one year"
# matched every digit and turned a projection into a fact. A correction may change a number; it may not drop the word
# that says what kind of claim the number is. These are the words a fix must carry over from the sentence it fixes
# and from the source sentence that holds the new number.
HEDGES = {
    "estimate": ("estimate", "estimates", "estimated", "estimating", "projected", "projects", "projection", "forecast",
                 "forecasts"),
    "expect": ("expect", "expects", "expected", "expecting", "anticipate", "anticipates", "anticipated"),
    "plan": ("plan", "plans", "planned", "planning", "proposed", "propose", "proposes", "proposal", "would", "could",
             "might", "aim", "aims", "target", "goal"),
    "about": RELATION["about"],
    "average": RELATION["average"],
    "at most": RELATION["at most"],
    "at least": RELATION["at least"],
}


def hedges_in(text: str) -> set:
    """The hedge families a sentence uses ("staff estimate", "expect", "plan", "about", "average")."""
    return {fam for fam, words in HEDGES.items() if _has(text, words)}


def _sentence_with(text: str, nums: list) -> str:
    """The sentence of ``text`` that holds one of ``nums`` (the source sentence a fix takes its number from)."""
    for s in _SENT.split(text or ""):
        if any(n in _num_set(s) for n in nums):
            return s
    return ""


def hedges_dropped(before: str, after: str, passage: str = "") -> list:
    """The hedge words a correction lost: every family the old sentence used must still be in the new sentence, and
    when the source sentence that holds the new number hedges it, the new sentence keeps at least one of its hedges.
    Returns the missing families' words, plainest first."""
    have = hedges_in(after)
    lost = [f for f in HEDGES if f in hedges_in(before) and f not in have]
    src = hedges_in(_sentence_with(passage, list(_num_set(after)))) if passage else set()
    if src and not (src & have):  # the source hedges its number ("Staff estimate ... would serve"): keep one of them
        lost += [f for f in HEDGES if f in src and f not in lost]
    return [HEDGES[f][0] for f in HEDGES if f in lost]


def slide_closest(doc: dict, path: str, text: str, passages: dict, ids: Optional[list] = None) -> Optional[dict]:
    """The passage a flagged slide line should be fixed from: the one the line and the rest of its slide rest on, so
    "1,200 learners" over three waitlist points is matched to the waitlist passage, not enrollment's. The flag shows
    this passage and Fix it for me corrects from it, so both name the same source."""
    parts = (path or "").split(".")
    if len(parts) < 2 or parts[0] != "slides" or not parts[1].isdigit():
        return None
    pre = f"slides.{parts[1]}."
    rest = [t for fp, t, _r in K.field_texts(doc) if (fp + ".").startswith(pre) and fp != path and t and t.strip()]
    if not rest:
        return None
    return closest((text or "") + " " + " ".join(rest), passages, ids if ids is not None else list(passages))


# ---------------------------------------------------------------- the argument (round 11) --
# The case is checked in code before any slide is written: every number in it is in a cited passage or worked out from
# two, every quote is found, every ref is a real passage, the ask has an amount or says the sources give none, and
# every instruction the notes give for the deck is listed by the case with its own words and met by a step.

_INSTRUCTION = re.compile(r"^\s*(?:[-*•]\s*)?(?:[A-Z][A-Za-z.\- ]{1,30}:\s*)?(?:please\s+)?"
                          r"(start|lead|open|begin|end|put|say|show|tell|do not|don't|never|keep|leave|make|be plain|be clear|"
                          r"include|mention|use|give|label|note|avoid|stick|no more than)\b", re.I)
_DECKISH = re.compile(r"\b(deck|slides?|presentation|proposal)\b", re.I)
_PLACEHOLDER = re.compile(r"\[[^\]]{0,40}\]|\bTBD\b|\bX{2,}\b")


def notes_instructions(passages: dict) -> list:
    """Sentences in a passage about a deck (it says deck, slides, presentation or proposal) that tell the writer
    what to do: "Marguerite: start with the children who are waiting", "Do not claim all of the drop".
    ``[{ref, text}]``, in passage order."""
    out = []
    for ref, p in passages.items():
        text = (p or {}).get("text") or ""
        if not _DECKISH.search(text):
            continue
        for line in re.split(r"\n+", text):
            for sent in SENTENCE.findall(line):
                s = sent.strip()
                if len(s) > 12 and _INSTRUCTION.match(s):
                    out.append({"ref": ref, "text": s})
    return out


def _covers(said: str, sentence: str) -> bool:
    sw, tw = _content_words(said), _content_words(sentence)
    if not tw:
        return True
    return len(sw & tw) / len(tw) >= 0.5


def argument_problems(arg: dict, passages: dict) -> list:
    """Faults in a drafted case, ``[{where, what}]``; empty when it holds."""
    try:
        steps = K.argument_steps(arg or {})
    except Exception:  # noqa: BLE001 - a malformed case is one fault
        return [{"where": "case", "what": "the case is not in the shape asked for"}]
    out = []
    all_ids = list(passages)
    for s in steps:
        if s["role"] != "ask" and not (s["heading"] or "").strip():
            out.append({"where": s["role"], "what": "has no heading"})
        if s["role"] != "ask" and not s["evidence"]:
            out.append({"where": s["role"], "what": "has no evidence"})
        for line in [s["heading"]] + [e.get("text", "") for e in s["evidence"]]:
            refs = s["refs"]
            for e in s["evidence"]:
                if e.get("text") == line:
                    refs = e.get("refs") or []
                    for r in refs:
                        if r not in passages:
                            out.append({"where": s["role"], "what": f"cites {r}, which is not a passage"})
            res = check_line(line, refs, passages, all_ids)
            for it in res["items"]:
                if it["status"] == "missing":
                    out.append({"where": s["role"], "what": f"\"{it['value']}\" is in no source and cannot be worked out from them (in: {line[:120]})"})
    a = (arg or {}).get("ask") or {}
    ask_text = " ".join([a.get("heading") or "", a.get("amount") or ""] + list(a.get("buys") or []) + [a.get("rest") or "", a.get("report") or "", a.get("by_when") or ""])
    if _PLACEHOLDER.search(ask_text):
        out.append({"where": "ask", "what": "has a placeholder; say what the sources give, or that they give none"})
    if not (a.get("amount") or "").strip() and not a.get("none_in_sources"):
        out.append({"where": "ask", "what": "has no amount and does not say the sources give none"})
    res = check_line(ask_text, [r for r in a.get("refs") or [] if r], passages, all_ids)
    for it in res["items"]:
        if it["status"] == "missing":
            out.append({"where": "ask", "what": f"\"{it['value']}\" is in no source and cannot be worked out from them; if you worked it out, say how in the same line (\"more than\", \"an increase of\", \"in all\")"})
    roles = {s["role"] for s in steps} | {"left out"}
    listed = [x for x in (arg or {}).get("instructions") or [] if isinstance(x, dict)]
    for x in listed:
        said = x.get("said") or ""
        if said and not (find_quote(said, passages, all_ids) or any(_covers(said, n["text"]) for n in notes_instructions(passages))):
            if not closest(said, passages, all_ids):
                out.append({"where": "instructions", "what": f"\"{said[:100]}\" is not in the notes"})
        mb = (x.get("met_by") or "").strip().lower()
        if mb not in roles:
            out.append({"where": "instructions", "what": f"\"{said[:80]}\" is met by \"{mb}\", which is not a step of the case"})
    for n in notes_instructions(passages):
        if not any(_covers(x.get("said") or "", n["text"]) for x in listed):
            out.append({"where": "instructions", "what": f"the notes say \"{n['text'][:160]}\" ({n['ref']}); the case does not list it or meet it"})
    return out


_WORDNUM = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_LEN = re.compile(r"\b(\d{1,2}|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?:\s+(?:or|to)\s+(\d{1,2}|three|four|five|six|seven|eight|nine|ten|eleven|twelve))?\s+slides?\b", re.I)
_LEN_CAP = re.compile(r"\b(at most|no more than|maximum|max|or fewer|or less|under|up to)\b", re.I)


def notes_length(passages: dict) -> Optional[int]:
    """The most slides a note about the deck allows, title slide included ("No more than eight slides", "Seven or
    eight slides at most" give 8), or None. Round 11b: two decks ran to nine slides past a note's "eight"."""
    best = None
    for p in passages.values():
        text = (p or {}).get("text") or ""
        if not _DECKISH.search(text):
            continue
        for sent in SENTENCE.findall(text):
            m = _LEN.search(sent)
            if not m or not _LEN_CAP.search(sent):
                continue
            n = max(int(x) if x.isdigit() else _WORDNUM[x.lower()] for x in m.groups() if x)
            if 3 <= n <= 30:
                best = n if best is None else min(best, n)
    return best
