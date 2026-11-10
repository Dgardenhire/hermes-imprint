"""The notebook guide: what the ticked sources say, what they ask for, and what a reader will likely ask.

One structured call over the ticked sources (job kind ``notebook_guide``) returns:

- ``guide``: one paragraph, sentence by sentence, each with its passage chips;
- ``asks``: the explicit requests in the sources ("the board asked for a one-page summary by October 21"), each
  with who asked, what, by when, the kind of output and a ready brief, so the pane can show a Make button;
- ``questions``: two or three likely questions built from a tension between passages, labeled as suggestions.

Nothing is shown unless it cites a passage the model was actually shown. Every number in a sentence is checked
(``checks.check_line``); a sentence with a number the sources don't hold is dropped, never shown.

This is not ``guide.py`` (the "Help me build a kit" method, job kind ``guide``).
"""

from __future__ import annotations

import re
from typing import Optional

try:
    from . import checks as CK
    from . import content as K
    from . import jobs as J
    from . import runtime as R
    from . import store
except ImportError:  # loaded loose
    import checks as CK  # type: ignore
    import content as K  # type: ignore
    import jobs as J  # type: ignore
    import runtime as R  # type: ignore
    import store  # type: ignore

BY = "Written by your Hermes model"
KINDS = ("onepager", "deck", "graphic", "audio")
SETTING = "notebook_guide"

REFS = {"type": "array", "items": K.REF, "description": "The labels of the passages this rests on, like P12"}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["guide", "asks", "questions"],
    "properties": {
        "guide": {
            "type": "array", "minItems": 2, "maxItems": 5,
            "description": "One paragraph, as its sentences in order: what these sources are and what they say that matters most.",
            "items": {"type": "object", "required": ["text", "refs"],
                      "properties": {"text": {"type": "string", "description": "One plain sentence under 25 words"}, "refs": REFS}},
        },
        "asks": {
            "type": "array", "maxItems": 4,
            "description": "Only requests the sources state outright: someone asked for a document, deck, graphic or recording. Never your own ideas. An empty list when there are none.",
            "items": {"type": "object", "required": ["who", "what", "by", "kind", "refs", "brief"],
                      "properties": {
                          "who": {"type": "string", "description": "Who asked, as the source names them, under 6 words"},
                          "what": {"type": "string", "description": "What they asked for, under 14 words"},
                          "by": {"type": "string", "description": "The deadline exactly as the source writes it, or empty"},
                          "kind": {"type": "string", "enum": list(KINDS)},
                          "refs": REFS,
                          "brief": {"type": "object", "required": ["who", "goal", "length"],
                                    "properties": {"who": {"type": "string", "description": "Who will read or hear it, under 8 words"},
                                                   "goal": {"type": "string", "description": "What they should decide or do, under 14 words"},
                                                   "length": {"type": "string", "description": "How long, like 'One page' or 'About 8 slides'"}}}}},
        },
        "questions": {
            "type": "array", "minItems": 2, "maxItems": 3,
            "description": "Questions a reader of these sources will likely ask, each built from a tension between two passages.",
            "items": {"type": "object", "required": ["text", "refs"],
                      "properties": {"text": {"type": "string", "description": "One or two short sentences ending in a question mark, under 35 words"},
                                     "refs": REFS}},
        },
    },
}

RULES = """Read the sources and write the notebook guide.

guide: one short paragraph, as two to five sentences. Say what these sources are and the few facts that matter
most. Plain words, short sentences. Each sentence carries the labels of the passages it rests on.

asks: the requests the sources state outright. A request is someone asking for something to be made: a summary,
a one-pager, a deck, a graphic, a recording, a report. Copy who asked and the deadline as the source writes them.
Pick the kind: onepager for a summary or one page, deck for slides or a presentation, graphic for one chart or
picture, audio for a recording or a spoken brief. Write the brief: who will read it, what they should decide or
do, how long. Cite the passage that holds the request. If the sources ask for nothing, return an empty list. Never
add an ask of your own.

questions: always two or three (never one) questions a careful reader will ask, each built from two passages that pull against each
other (a goal and a shortfall, a cost and a reserve, a demand and a capacity). Lead with the hardest one: a
shortfall set against a new cost, with the numbers of both sides in the one question (the shortfall and its target,
and how much the cost rises, worked out when the sources give only the two totals). Every question names its numbers. When you work out a number (a difference, a total,
a change), cite the passage of every number you used.

Every number you write is copied from a passage, or worked out from two numbers in the passages you cite. Never
invent a number, a name or a date."""

REQUEST = re.compile(r"\b(ask(?:ed|s)?|request(?:ed|s)?|wants?|wanted|needs?|needed|bring|send|prepare|deliver|due|"
                     r"would like|calls? for|called for|expects?|expected)\b", re.I)


def chips_for(refs: list, by_ref: dict, source_order: list) -> list:
    """Chips the pane draws: ``{ref, n, source_n, source, locator, source_id}``, numbered in order of use."""
    out = []
    order = {sid: i for i, sid in enumerate(source_order, start=1)}
    for r in refs:
        p = by_ref.get(r)
        if not p or any(c["ref"] == r for c in out):
            continue
        out.append({"ref": r, "n": len(out) + 1, "source_n": order.get(p.get("source_id")), "source": p.get("source_title", ""),
                    "locator": p.get("locator", ""), "source_id": p.get("source_id")})
    return out


LABEL = re.compile(r"\s*[\[(]\s*P\d+(?:\s*,\s*P\d+)*\s*[\])]")


def _s(v, n: int) -> str:
    """Plain text for the pane: passage labels the model wrote inline ("[P4]", "(P1, P3)") come out, since the
    chips carry them."""
    return re.sub(r"\s+", " ", LABEL.sub("", str(v or ""))).strip()[:n]


def _valid(refs, by_ref: dict, shown: set) -> list:
    out = []
    for x in refs if isinstance(refs, list) else []:
        r = K._ref(x)
        if r and r in by_ref and r in shown and r not in out:
            out.append(r)
    return out


def _line(text: str, refs: list, by_ref: dict, shown: set) -> Optional[list]:
    """The sentence's refs after the check, or ``None`` when it must be dropped."""
    if not refs or not text:
        return None
    allowed = {r: by_ref[r] for r in shown if r in by_ref}
    got = CK.check_line(text, refs, allowed)
    return got["refs"] if got["ok"] else None


def clean(raw: dict, by_ref: dict, shown: set, source_order: list) -> dict:
    """The guide as the pane gets it. Drops every sentence, ask and question without a valid ref, and any whose
    numbers fail the check. An ask must cite a passage that holds a request."""
    if not isinstance(raw, dict):
        raise ValueError("not an object")
    guide, asks, questions = [], [], []
    for g in (raw.get("guide") or [])[:5]:
        if not isinstance(g, dict):
            continue
        text = _s(g.get("text"), 260)
        refs = _line(text, _valid(g.get("refs"), by_ref, shown), by_ref, shown)
        if refs:
            guide.append({"text": text, "chips": chips_for(refs, by_ref, source_order)})
    for a in (raw.get("asks") or [])[:4]:
        if not isinstance(a, dict):
            continue
        refs = _valid(a.get("refs"), by_ref, shown)
        refs = [r for r in refs if REQUEST.search(by_ref[r].get("text", ""))]
        what = _s(a.get("what"), 140)
        if not refs or not what:
            continue
        kind = a.get("kind") if a.get("kind") in KINDS else ("deck" if re.search(r"\b(deck|slides|presentation)\b", what, re.I) else "onepager")
        b = a.get("brief") if isinstance(a.get("brief"), dict) else {}
        asks.append({"id": f"a{len(asks) + 1}", "who": _s(a.get("who"), 60), "what": what, "by": _s(a.get("by"), 40), "kind": kind,
                     "chips": chips_for(refs, by_ref, source_order),
                     "brief": {"who": _s(b.get("who"), 80), "goal": _s(b.get("goal"), 140), "length": _s(b.get("length"), 40)}})
    for q in (raw.get("questions") or [])[:3]:
        if not isinstance(q, dict):
            continue
        text = _s(q.get("text"), 300)
        refs = _line(text, _valid(q.get("refs"), by_ref, shown), by_ref, shown)
        if refs and text.endswith("?"):
            questions.append({"text": text, "chips": chips_for(refs, by_ref, source_order), "suggestion": True})
    if not guide:
        raise ValueError("no usable guide")
    return {"by": BY, "guide": guide, "asks": asks, "questions": questions}


def last() -> Optional[dict]:
    return store.get_setting(SETTING, None) or None


@J.handler("notebook_guide")
async def job_notebook_guide(job_id: str, p: dict) -> dict:
    try:
        from . import service as S
    except ImportError:  # loaded loose
        import service as S  # type: ignore
    source_ids = p.get("source_ids") or []
    corpus, srcs, by_ref, shown = S._corpus(source_ids, with_ids=True)
    J.step(job_id, f"Reading {len(srcs)} source{'s' if len(srcs) != 1 else ''}")
    raw = await S.model().structured(system=K.SYSTEM, instructions=RULES, body=corpus, schema=SCHEMA,
                                     purpose="notebook_guide", max_tokens=1600, timeout=120)
    J.step(job_id, "Checking every number against your sources")
    try:
        got = clean(raw, by_ref, shown, [s["id"] for s in srcs])
    except ValueError:
        raise R.ModelError(R.CUT_OFF, "cut_off")
    got.update(source_ids=source_ids, created_at=store.now())
    store.set_setting(SETTING, got)
    return got
