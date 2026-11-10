"""Scripted stand-in answers for the AI lane's purposes in the live harness (never used by Hermes itself).

``persona_model.py`` imports this module once (its last line); this module then wraps
``PersonaModel.acomplete_structured`` so the six new purposes (notebook_guide, outline, rewrite_title,
element_edit, fix_it, graphic_options) get answers built from the passages in the call, and every other purpose
goes to the persona script as before. Harborlight (Denise) has a script tied to the acceptance checks; any other
sources get plain answers built from their own sentences. These are stand-ins: no judged screen uses them (P7).
"""
import json
import re

import persona_model as PM

MINE = ("notebook_guide", "outline", "rewrite_title", "element_edit", "fix_it", "graphic_options")
NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def _purpose(kw):
    p = kw.get("purpose", "")
    return p.split(".", 1)[1] if p.startswith("imprint.") else p


def _body(kw):
    return "".join(b.get("text", "") for b in kw.get("input", []) if isinstance(b, dict))


def _first(text, n=14):
    s = re.split(r"(?<=[.!?])\s+", text.strip())[0].rstrip(".")
    w = s.split()
    return " ".join(w[:n])


def _find(ps, phrase):
    for r, _l, t in ps:
        if phrase.lower() in t.lower():
            return r
    return None


def _is_harborlight(body):
    return "Harborlight" in body or "1,148" in body


def guide(ps, body):
    if _is_harborlight(body):
        f = lambda s: _find(ps, s)
        served, wait, money, rec, board = f("enrolled 1,148"), f("287 adults"), f("Operating expenses for FY2026"), f("approve an FY2027"), f("reserves stand")
        return {"guide": [{"text": "Harborlight enrolled 1,148 adult learners in FY2026, up from 936 the year before.", "refs": [served]},
                          {"text": "Another 287 adults ended the year on the waitlist, most near Eastgate and Riverside.", "refs": [wait]},
                          {"text": "Staff propose a $1,610,000 budget for FY2027 that adds a sixth site.", "refs": [rec]}],
                "asks": [{"who": "The board", "what": "A one-page summary of the FY2027 budget request", "by": "October 21", "kind": "onepager",
                          "refs": [board], "brief": {"who": "Board members", "goal": "Vote on the FY2027 budget on October 21", "length": "One page"}},
                         {"who": "Board members", "what": "A short deck for funders about the sixth site", "by": "", "kind": "deck",
                          "refs": [board], "brief": {"who": "Funders", "goal": "Fund the sixth site", "length": "About 8 slides"}}],
                "questions": [{"text": "Reserves stand at 3.2 months against a 4-month target. Can Harborlight add a site while the budget rises $190,000?",
                               "refs": [board, rec, money]},
                              {"text": "Would 180 more seats a year be enough for a waitlist of 287?", "refs": [rec, wait]}]}
    lines = [{"text": _first(t, 20) + ".", "refs": [r]} for r, _l, t in ps[:3]]
    asks = []
    for r, _l, t in ps:
        m = re.search(r"asked (?:staff )?(?:to bring |for )(an? [^.]{5,80})", t, re.I)
        if m:
            asks.append({"who": "The sources", "what": m.group(1)[:1].upper() + m.group(1)[1:], "by": "", "kind": "deck" if "deck" in m.group(1) else "onepager",
                         "refs": [r], "brief": {"who": "The readers named in the sources", "goal": "Decide on the request", "length": "One page"}})
    with_num = [(r, t) for r, _l, t in ps if NUMBER.search(t)]
    qs = []
    if len(with_num) >= 2:
        (r1, t1), (r2, t2) = with_num[0], with_num[1]
        qs.append({"text": f"How does {NUMBER.search(t1).group(0)} square with {NUMBER.search(t2).group(0)}?", "refs": [r1, r2]})
        qs.append({"text": "What would change if the next year looked like this one?", "refs": [r1, r2]})
    return {"guide": lines, "asks": asks[:2], "questions": qs}


def outline(ps, body):
    if _is_harborlight(body):
        f = lambda s: _find(ps, s)
        return {"slides": [
            {"title": "Demand for adult literacy is outgrowing our five sites", "type": "section", "refs": [f("enrolled 1,148")]},
            {"title": "Enrollment grew by 212 adults in one year", "type": "exhibit", "refs": [f("enrolled 1,148")]},
            {"title": "287 adults ended the year waiting for a seat", "type": "stat", "refs": [f("287 adults")]},
            {"title": "The average adult waits nine weeks for a seat", "type": "stat", "refs": [f("287 adults")]},
            {"title": "Seventy-one learners earned a high school equivalency credential", "type": "stat", "refs": [f("enrolled 1,148")]},
            {"title": "Volunteers gave 9,870 hours of tutoring last year", "type": "stat", "refs": [f("214 volunteer")]},
            {"title": "A sixth site would serve 180 more learners a year", "type": "content", "refs": [f("approve an FY2027")]},
            {"title": "The FY2027 budget rises $190,000 to open it", "type": "stat", "refs": [f("approve an FY2027"), f("Operating expenses for FY2026")]},
            {"title": "Fund the sixth site and halve the waitlist", "type": "closing", "refs": [f("approve an FY2027")]},
        ]}
    return {"slides": [{"title": _first(t, 12), "type": "stat" if NUMBER.search(t) else "content", "refs": [r]} for r, _l, t in ps[:9]]}


def rewrite(ps, body):
    m = re.search(r"REWRITE SLIDE \d+: (.+)", body)
    old = (m.group(1) if m else "This slide").strip()
    refs = [r for r, _l, _t in ps]
    core = old[0].lower() + old[1:]
    return {"options": [{"title": f"This year, {core}", "refs": refs}, {"title": f"Our numbers show {core}", "refs": refs},
                        {"title": f"The record is clear: {core}", "refs": refs}]}


def edit(ps, body, instr):
    m = re.search(r"THE SLIDE \(JSON\)\n(.+?)\n\nITS PASSAGES", body, re.S)
    sl = json.loads(m.group(1)) if m else {"type": "content", "heading": "A slide", "refs": []}
    refs = sl.get("refs") or [r for r, _l, _t in ps[:1]]
    if instr.startswith("Write three stronger"):
        opts = []
        for lead in ("Right now,", "This year,", "Without a seat,"):
            o = dict(sl)
            if o.get("type") == "stat":
                o["label"] = f"{(o.get('label') or 'people')}, {lead.lower().rstrip(',')}"[:110]
            else:
                o["heading"] = f"{lead} {(o.get('heading') or 'the sources agree')}"[:110]
            opts.append(o)
        return {"options": opts}
    if instr.startswith("Make this slide shorter"):
        o = dict(sl)
        for k in ("label", "context", "heading", "subtitle", "text"):
            if o.get(k):
                o[k] = " ".join(str(o[k]).split()[:6])
        return {"slide": o}
    if instr.startswith("Turn this slide"):
        items = sl.get("bullets") or sl.get("left_items") or []
        bars = []
        for it in items:
            n = NUMBER.search(it.get("text", ""))
            if n:
                bars.append({"label": " ".join(re.sub(NUMBER, "", it["text"]).split()[:4]) or "Count", "value": n.group(0), "ref": it.get("ref") or refs[0]})
        return {"slide": {"type": "exhibit", "heading": (sl.get("heading") or "What the numbers show"), "unit": "As the sources count them",
                          "bars": bars, "refs": refs}}
    if "quote" in instr:
        for r, _l, t in ps:
            q = re.search(r"[“\"]([^”\"]{12,300})[”\"]", t)
            if q:
                return {"slide": {"type": "quote", "quote": q.group(1).rstrip(",. "), "who": "", "refs": [r]}}
    r, _l, t = ps[0] if ps else ("P1", "", "A point from the sources.")
    return {"slide": {"type": "content", "heading": _first(t, 7), "bullets": [{"text": _first(t, 10), "ref": r}], "refs": [r]}}


def fix(body):
    sent = re.search(r"THE SENTENCE\n(.+?)\n\nTHE WRONG PART\n(.+?)\n\nTHE CLOSEST PASSAGE\n\[(P\d+)\] \([^)]*\) (.+)", body, re.S)
    if not sent:
        return {"text": ""}
    text, wrong, _ref, passage = sent.group(1), sent.group(2).strip(), sent.group(3), sent.group(4)
    if "1,200" in wrong and "1,148 adult learners" in passage:
        return {"text": text.replace("1,200 learners", "1,148 adult learners").replace("1,200", "1,148")}
    want = re.sub(r"[^\d.]", "", wrong) or "0"
    best = min(NUMBER.findall(passage) or [wrong], key=lambda n: abs(float(re.sub(r"[^\d.]", "", n) or 0) - float(want or 0)))
    return {"text": text.replace(wrong, best)}


def graphics(ps):
    found = []
    for r, _l, t in ps:
        for m in NUMBER.finditer(t):
            v = m.group(0).rstrip(",.")
            if re.fullmatch(r"(19|20)\d\d", v) or "%" in v:
                continue
            words = t[max(0, m.start() - 40):m.start()].split()[-3:]
            found.append({"label": " ".join(words)[:30] or "Count", "value": v, "ref": r})
    if len(found) < 2:
        return {"options": []}
    head = "What the sources count"
    return {"options": [
        {"headline": head, "form": "bars", "items": found[:4], "takeaway": "Read each bar against the others.", "unit": "As written"},
        {"headline": head + " in two numbers", "form": "figures", "items": found[:2], "takeaway": "Two numbers carry the story."},
        {"headline": "One number set against another", "form": "compare", "items": found[:2], "takeaway": "The gap is the point."},
    ]}


_orig = PM.PersonaModel.acomplete_structured


async def acomplete_structured(self, **kw):
    purpose = _purpose(kw)
    if purpose not in MINE:
        return await _orig(self, **kw)
    body = _body(kw)
    ps = PM.refs_of(body)
    PM.LOG.append(("call", kw.get("purpose", "")))
    if purpose == "notebook_guide":
        return PM.R(guide(ps, body))
    if purpose == "outline":
        return PM.R(outline(ps, body))
    if purpose == "rewrite_title":
        return PM.R(rewrite(ps, body))
    if purpose == "element_edit":
        return PM.R(edit(ps, body, kw.get("instructions", "")))
    if purpose == "fix_it":
        return PM.R(fix(body))
    return PM.R(graphics(ps))


PM.PersonaModel.acomplete_structured = acomplete_structured
