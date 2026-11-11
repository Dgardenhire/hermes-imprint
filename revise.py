"""Outline first, then revise: the AI actions on a deck, each a job, each re-checked before it is shown.

Job kinds (all through ``runtime.Model.structured``, Hermes's ``complete_structured``, with the schemas here):

- ``outline``: from a brief (who, decide or do, length) and the ticked sources, 7 to 10 slides as action titles,
  then checked once more as the brief's reader would (``review_outline``), with what changed in ``review``.
- ``rewrite_title``: three options for one outline title.
- ``element_edit``: one slide made shorter, stronger (three options), into a chart, or one slide inserted after
  slide N ("Add the quote after slide 4"). A typed line that names a field and gives its new words ("Change this
  slide's title to: ...") is applied as typed, with no model call, and its numbers are checked like any option.
  Any other typed line is refused in one sentence, with no model call.
- ``fix_it``: a flagged sentence corrected against the closest passage, with a word-by-word diff.
- ``graphic_options``: three graphic specs in different forms from a pinned answer.

Rules every action keeps: the model only returns JSON in these schemas. It never picks a tool, exports, deletes or
writes a file. Every option is checked with ``checks`` before it is returned, and an option that fails is dropped.
Nothing lands on an output until the person presses Keep, which goes through lane A's version functions
(``store.add_version``, ``store.undo``); this module writes no SQL for versions.
"""

from __future__ import annotations

import copy
import difflib
import importlib.util
import re
import sys
import threading
from pathlib import Path
from typing import Optional

try:
    from . import checks as CK
    from . import content as K
    from . import jobs as J
    from . import notebook_guide as NG
    from . import runtime as R
    from . import store
except ImportError:  # loaded loose
    import checks as CK  # type: ignore
    import content as K  # type: ignore
    import jobs as J  # type: ignore
    import notebook_guide as NG  # type: ignore
    import runtime as R  # type: ignore
    import store  # type: ignore

BY = NG.BY
KINDS = ("notebook_guide", "outline", "rewrite_title", "element_edit", "fix_it", "graphic_options")
OUTLINE_TYPES = ("stat", "figures", "content", "exhibit", "quote", "comparison", "timeline", "section", "closing")
ACTIONS = ("shorter", "stronger", "chart", "insert", "typed")
MAX_TITLE_WORDS = 15
REFUSE_TYPED = ("I can change a slide's title or subtitle to your words, make a slide shorter or stronger, turn it into a "
                "chart, or add one slide. Try “Change the title to: …” or “Add the quote after slide 4”.")
INSERT = re.compile(r"^\s*add\s+(?:the|a)\s+(quote|point)\s+after\s+slide\s+(\d{1,2})\s*\.?\s*$", re.I)
# "Change this slide's title to: ...", "Set the subtitle of slide 3 to ...", "Rename slide 2 to ...", "Title: ...".
# The person's own words for one named field: read by this pattern only, never sent to a model.
_FIELD_WORDS = {"title": "head", "heading": "head", "headline": "head", "header": "head", "name": "head",
                "subtitle": "sub", "subheading": "sub", "subhead": "sub", "sub-heading": "sub", "sub-title": "sub", "dek": "sub"}
_FW = "|".join(sorted(_FIELD_WORDS, key=len, reverse=True))
_POSS = r"(?:'s|’s)?"
SET_TEXT = re.compile(
    r"^\s*(?:please\s+)?(?:change|set|make|rename|retitle|rewrite|edit|update|replace)\s+"
    r"(?:(?:the|this)\s+)?(?:(?:deck|slide\s+(?P<n1>\d{1,2})|slide)" + _POSS + r"\s+)?"
    r"(?P<field>" + _FW + r")"
    r"(?:\s+(?:of|on|for)\s+(?:(?:the|this)\s+)?(?:deck|slide\s+(?P<n2>\d{1,2})|slide))?"
    r"\s*(?:\bto(?:\s+(?:read|say|be))?\b|\bas\b|\bwith\b|:)\s*:?\s*(?P<text>\S.*?)\s*$", re.I | re.S)
RENAME = re.compile(r"^\s*(?:please\s+)?(?:rename|retitle)\s+(?:(?:the|this)\s+)?(?:deck|slide\s+(?P<n1>\d{1,2})|slide|it)"
                    r"\s*(?:\bto\b|\bas\b|:)\s*:?\s*(?P<text>\S.*?)\s*$", re.I | re.S)
BARE = re.compile(r"^\s*(?:new\s+)?(?P<field>" + _FW + r")\s*:\s*(?P<text>\S.*?)\s*$", re.I | re.S)
MAX_TYPED = 200
# "Change the title to something punchier" asks for a rewrite; it does not give the new words. Those go to the buttons.
_A_WISH = re.compile(r"(?:be\s+)?(?:something\s+|one\s+that(?:'s|’s| is)\s+)?(?:a\s+(?:bit|little)\s+)?(?:(?:much\s+)?(?:more|less)\s+)?"
                     r"(?:shorter|longer|stronger|punchier|better|clearer|simpler|bolder|plainer|snappier|catchier|"
                     r"direct|concise|catchy|formal|casual|specific|compelling|engaging|professional)\.?", re.I)
_WRAP = (("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"))


def parse_set_text(text: str) -> Optional[dict]:
    """``{"field": "head" | "sub", "slide": N or None, "text": words}`` when the line names a field and gives its new
    words; ``None`` for anything else. ``slide`` is the number as the person counts it (the title slide is 1)."""
    line = text or ""
    for pat in (SET_TEXT, RENAME, BARE):
        m = pat.match(line)
        if not m:
            continue
        d = m.groupdict()
        new = re.sub(r"\s+", " ", d.get("text") or "").lstrip(": ").strip()
        for a, b in _WRAP:  # the words were typed inside quotation marks: the marks are not part of the title
            if len(new) > 2 and new.startswith(a) and new.endswith(b) and new.count(a) + (new.count(b) if a != b else 0) == 2:
                new = new[1:-1].strip()
                break
        if not re.search(r"\w", new) or _A_WISH.fullmatch(new):
            return None
        n = d.get("n1") or d.get("n2")
        return {"field": _FIELD_WORDS.get((d.get("field") or "title").lower(), "head"), "slide": int(n) if n else None, "text": new}
    return None


SET_PATH = re.compile(r"title|subtitle|slides\.\d{1,2}\.(?:heading|label|subtitle|context)|(?:cover|slides\.\d{1,2})\.els\.\d{1,2}")
BY_YOU = "Your words, checked against your sources"
NO_TITLE_LINE = "This slide has no title line to change. Press Edit text on the line you want to change."


def _spec_mod():
    try:
        from . import spec as SP
    except ImportError:  # loaded loose
        import spec as SP  # type: ignore
    return SP


def _title_el(sl: dict) -> Optional[int]:
    """Which element of a designed slide is its title: the first text element set in the title style (the slide's
    own ``heading`` breaks a tie), else ``None``."""
    SP = _spec_mod()
    els = [SP.clean_el(e) for e in (sl.get("els") or [])]
    titles = [j for j, e in enumerate(els) if e and e.get("type") == "text" and e.get("style") == "title" and e.get("text")]
    if not titles:
        return None
    head = _s(sl.get("heading") or "", 400)
    return next((j for j in titles if head and _s(els[j]["text"], 400) == head), titles[0])


def _set_text_target(doc: dict, on_title: bool, slide: int, want: dict) -> tuple:
    """``(path, message)``: the doc field a typed change lands on, or why it can't."""
    slides = doc.get("slides") or []
    n = want.get("slide")
    if n is not None:
        if not 1 <= n <= len(slides) + 1:
            return None, f"This deck has {len(slides) + 1} slides. Pick a slide number from 1 to {len(slides) + 1}."
        on_title, slide = n == 1, n - 2
    head = want["field"] == "head"
    if on_title:
        cover = doc.get("cover") if isinstance(doc.get("cover"), dict) and doc["cover"].get("els") else None
        if cover is None:
            return ("title" if head else "subtitle"), None
        j = _title_el(cover) if head else None  # a designed cover: its title is one of its elements
        return (f"cover.els.{j}", None) if j is not None else (None, NO_TITLE_LINE)
    if not 0 <= slide < len(slides):
        return None, "That slide is gone. Pick a slide and try again."
    sl = slides[slide]
    t = sl.get("type")
    if t == "spec":
        j = _title_el(sl) if head else None
        return (f"slides.{slide}.els.{j}", None) if j is not None else (None, NO_TITLE_LINE)
    if head:
        if t == "quote":
            return None, ("A quote slide shows a source's exact words, so they can't be typed over. "
                          "Try “Add the quote after slide 4” for a different quote.")
        return f"slides.{slide}.{'label' if t == 'stat' else 'heading'}", None
    f = "context" if t == "stat" else "subtitle" if t in ("section", "closing") or sl.get("subtitle") else None
    if not f:
        return None, "This slide has no subtitle. Try “Change the title to: …”."
    return f"slides.{slide}.{f}", None


def _get_path(doc: dict, path: str) -> str:
    cur = doc
    try:
        for part in path.split("."):
            cur = cur[int(part)] if part.isdigit() else cur[part]
    except (KeyError, IndexError, TypeError, ValueError):
        return ""
    if isinstance(cur, dict):  # a designed slide's element: its words
        cur = cur.get("text")
    return cur if isinstance(cur, str) else ""


def _put_text(doc: dict, path: str, new: str) -> bool:
    """Set the words at ``path``. A designed slide's title element also names the slide (``heading``), and the
    cover's names the deck (``title``), so the outline, the file name and the slide stay one title."""
    parts = path.split(".")
    try:
        if ".els." in path:
            if not _spec_mod().set_field(doc, path, lambda _old: new):
                return False
            holder = doc["cover"] if parts[0] == "cover" else doc["slides"][int(parts[1])]
            holder["heading"] = new
            if parts[0] == "cover":
                doc["title"] = new
        else:
            K.set_path(doc, path, new)
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return True


def check_field(doc: dict, path: str, by_ref: dict) -> dict:
    """``{status, label, items}`` for one field of a deck, by the same checker every proof uses."""
    g = CK.grounding(doc, by_ref)
    mine = [i for i in g["items"] if i.get("path") == path and i["kind"] in ("number", "quote")]
    bad = [i for i in mine if i["status"] == "missing"]
    if bad:
        n = len(bad)
        return {"status": "missing", "label": f"{n} number{'s' if n != 1 else ''} not found in your sources", "items": CK.public_items(bad)}
    return {"status": "ok", "label": CK.match_label(len(mine)) if mine else "No numbers to check", "items": []}


def set_text_option(doc: dict, neutral: dict, by_ref: dict, on_title: bool, slide: int, want: dict) -> dict:
    """The typed change as one checked option, or a refusal: ``{status, message, path, before_text, base_text, option}``."""
    path, why = _set_text_target(doc, on_title, slide, want)
    if not path:
        return {"status": "refused", "message": why}
    new = want["text"]
    if len(new) > MAX_TYPED:
        return {"status": "refused", "message": f"That is {len(new)} characters, too long to set on a slide. Keep it under {MAX_TYPED}."}
    before = _get_path(doc, path)
    if new == before:
        return {"status": "refused", "message": "The slide already says that."}
    after = copy.deepcopy(doc)
    if not _put_text(after, path, new):
        return {"status": "refused", "message": "That slide is gone. Pick a slide and try again."}
    chk = check_field(after, path, by_ref)
    if chk["status"] != "ok":
        vals = ", ".join(dict.fromkeys(str(i.get("shown") or i.get("value")) for i in chk["items"]))
        return {"status": "refused", "message": (f"{vals} isn’t in your sources, so the slide stays as it is. Take the number out, or "
                                                 "use Edit text and then “Keep mine, I checked”.")}
    is_slide = path.startswith("slides.")
    return {"status": "ok", "message": None, "path": path, "before_text": before, "base_text": _get_path(neutral, path),
            "after": after, "option": {"slide": after["slides"][int(path.split(".")[1])] if is_slide else None, "text": new, "check": chk},
            "frame": int(path.split(".")[1]) + 1 if is_slide else 0}


def frame_trees(output_id: str, kit_id: str, docs: list, frame: int) -> list:
    """Frame ``frame`` (0 is the title slide) of each doc as the scene node the canvas draws, ``None`` where it can't be drawn."""
    parts = _kit_parts(output_id, kit_id)
    if not parts:
        return [None] * len(docs)
    kit, pal, faces, logo = parts
    S = _service()
    _KITS, _L, RD, _RG = _drawing()
    out = S._output(output_id)
    _srcs, _b, by_ref = S.passages_for(out["source_ids"])
    date = S.nice_date(out.get("created_at"))
    trees = []
    for d in docs:
        try:
            trees.append(RD.deck_tree(d, kit, pal, faces, by_ref, date, logo_urls=logo)[0]["k"][frame])
        except Exception:  # noqa: BLE001
            trees.append(None)
    return trees


def _service():
    try:
        from . import service as S
    except ImportError:  # loaded loose
        import service as S  # type: ignore
    return S


_ROUTES_LOCK = threading.Lock()


def routes():
    """``dashboard/revise_api.py``, loaded by path (the dashboard folder is not part of the package)."""
    name = "imprint_revise_api"
    # Load under a lock and register only a finished module (see designs.routes): a half-loaded one has no ``mount``.
    with _ROUTES_LOCK:
        mod = sys.modules.get(name)
        if mod is None or not hasattr(mod, "mount"):
            spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / "dashboard" / "revise_api.py")
            if spec is None or spec.loader is None:
                raise RuntimeError("Could not load Imprint's revise routes")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sys.modules[name] = mod
        return mod


_s = NG._s


def words(text: str) -> int:
    return len(re.findall(r"[\w$%][\w$%,.'’-]*", text or ""))


def _claim_numbers(text: str) -> list:
    out = []
    for m in K.NUM.finditer(text or ""):
        tok = m.group(0).rstrip(",").rstrip()
        if not CK.is_date_number(text, m.start(), m.start() + len(tok)):
            out.append(tok)
    return out


SPLIT = re.compile(r";|\s(?:and|while|but|whereas|plus)\s|,\s(?:and\s)?(?=[a-z]+\s+\d)", re.I)


def needs_split(title: str, kind: str = "") -> bool:
    """A title that carries two claims: two numbers joined by "and", "while", a semicolon. Only a hint: the
    person decides, the title is never changed on its own."""
    nums = _claim_numbers(title)
    if kind == "stat" and len(nums) > 1:
        return True
    if ";" in (title or ""):
        return True
    return len(nums) >= 2 and bool(SPLIT.search(title or ""))


# ---------------------------------------------------------------- outline --

OUTLINE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["slides"],
    "properties": {"slides": {
        "type": "array", "minItems": 5, "maxItems": 10,
        "items": {"type": "object", "required": ["title", "type", "refs"],
                  "properties": {"title": {"type": "string", "description": "A full sentence under 15 words that states one claim. No period."},
                                 "type": {"type": "string", "enum": list(OUTLINE_TYPES)},
                                 "refs": NG.REFS}}}},
}

OUTLINE_RULES = """Write the outline of a deck from the sources, for the brief below. Seven to ten slides, in the
order the reader needs them.

Each title is an action title: one full sentence under 15 words that states one claim, the way a reader would
retell the slide. Never a topic label ("Enrollment"), always the finding ("Enrollment grew by 212 adults in one
year"). A chart slide's title states what the chart shows. A stat slide carries one number. One claim per title:
if you need "and" to join two findings, make two slides.

Pick each slide's type: figures for three or four related numbers (results, people, money), exhibit for a chart
of two to six numbers of one kind (two periods, or the parts of a budget or funding mix), content for three to five
points, comparison for today against the plan with matched rows, quote for a source's exact words, timeline for
dated steps, stat for one number that stands alone, closing for the ask. No section slides when the brief names a
length: every slide carries evidence.

Build an argument, not a list of facts. A deck that asks for support goes: the need, the proof that the work works,
the people who do it, the plan, what it costs and who pays for it, the ask. Cover each of these the sources hold:
when the sources count volunteers or staff, one slide carries them; when they give a budget, a cost per person or
where the money comes from, one slide carries those numbers. At most one stat slide; three or four related numbers
share one figures slide. Never a slide with only one or two weak lines. Each slide cites every passage it needs for
its evidence, not only the passage of its title. The last slide is the ask: what the reader should give or do, with
the amount when the sources give one, written to the brief's reader: a deck for funders or the public never
carries an internal deadline (a board vote, a council session) or an internal worry (reserves below target). When
the brief names a length, keep to it: the title slide is added to your
slides and counts as one, so "7 to 9 slides" means at most 8 slides here.

The deck's main chart: when the sources count the same thing for two periods and also give a number that shows the
pressure on it (people waiting, a gap, a shortfall), give one exhibit slide that charts all three, cite the
passages of both periods and of the pressure number, and title it with the finding ("Need is outgrowing our
capacity", never "Need is outgrowing our capacity as 287 adults wait"). Do not give that pressure number a stat
slide of its own.

One number, one slide: a number appears in at most one title, and the main chart's highlighted number (which the
cover repeats) stays out of that chart's title. When a passage gives a budget, a cost breakdown or a funding mix, one
slide carries all its money figures, and cites that passage.

Keep the source's relation words in a title: an average stays an average, people "waiting at" a site are waiting
there, an estimate or a plan is said as one ("Staff estimate a sixth site would serve 180 more learners").

Plain words: never coin a shorthand noun for a group of people ("stayers", "leavers", "completers"); say "learners
who stayed". Use a word like busiest, coldest, largest, first or record only when the cited passage uses it.

Every slide cites the passages it rests on. Every number in a title is copied from a passage or worked out from
two numbers in the passages that slide cites: when a title works out a number (a difference, a total, a change),
that slide cites the passage of each of the two numbers it comes from. Never invent a number, a name or a date."""

REVIEW_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["slides", "changes"],
    "properties": {
        "slides": OUTLINE_SCHEMA["properties"]["slides"],
        "changes": {"type": "array", "maxItems": 5, "description": "What you changed and why, in the order it matters. Empty when the outline already makes the case.",
                    "items": {"type": "object", "required": ["text", "refs"],
                              "properties": {"text": {"type": "string", "description": "One short sentence a person reads, under 18 words, saying what changed: \"Added the survey finding on hours\", \"The closing now asks for the increase, $46,500\". Name what a passage says, never its label (P2): the chips show the source. No period."},
                                             "refs": NG.REFS}}}},
}

REVIEW_RULES = """Check this outline as the reader the brief names, before anyone writes the slides. Read the sources
first, then the outline draft. Ask, as that reader would:

1. The ask. Does the last slide state what the reader is asked to give or do, with the amount and what it pays for,
   when the sources give them? When the sources ask for an increase over a current budget or cost, the ask is the
   increase (work it out from the two numbers and cite both passages), never the new total. When the sources give
   the amount asked, use that amount. Never invent an amount.
2. The strongest evidence. Which finding in the sources argues hardest for the ask: what the people served said or
   did, a share of them, a comparison, the cause of the problem the ask fixes? It must be on a slide, in a title,
   early. A deck that leaves it out loses the case, however true its other slides are.
3. The reader's questions. What will this reader ask that no slide answers: how big the need is, whether the work
   works, what it costs and who else pays, what changes with the money? Answer each one the sources can answer.
4. Each title rests on its passages. A slide's cited passages must hold the evidence for its title; a slide whose
   passages are about something else is retitled or re-cited.
5. Cut what does not argue: a slide on a lone figure, a quote that repeats a number, a slide that only lists facts.

Then return the whole revised outline under the same rules as the draft (action titles, one claim, types, a number
in one title only, the length) and a short list of what you changed. When the draft already makes the case, return
it as it is with an empty list. Every number in a title is copied from a passage that slide cites or worked out from
two numbers in them. Never invent a number, a name or a date. Keep the outline rules below.

""" + OUTLINE_RULES


REWRITE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["options"],
    "properties": {"options": {"type": "array", "minItems": 3, "maxItems": 3,
                               "items": {"type": "object", "required": ["title", "refs"],
                                         "properties": {"title": {"type": "string", "description": "A full sentence under 15 words, one claim. No period."},
                                                        "refs": NG.REFS}}}},
}

REWRITE_RULES = """Rewrite one slide title three ways. Each option is an action title: one full sentence under 15
words with one claim, stronger and plainer than the old one, and different from the other two (lead with the
number, lead with the people, lead with the consequence). Keep to what the cited passages say. Every number is
copied from them or worked out from two numbers in them. Never coin a shorthand noun for a group of people
("stayers", "leavers", "completers")."""


def _brief_text(brief: dict) -> str:
    b = brief if isinstance(brief, dict) else {}
    return (f"Who it is for: {_s(b.get('who'), 120) or 'not given'}\n"
            f"What they should decide or do: {_s(b.get('goal'), 200) or 'not given'}\n"
            f"Length: {_s(b.get('length'), 60) or 'about 8 slides'}")


def max_slides(brief) -> Optional[int]:
    """The most slides the brief allows, title slide included: "7 to 9 slides" gives 9, "About 8 slides" gives 8."""
    length = (brief or {}).get("length") if isinstance(brief, dict) else ""
    nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", length or "") if 3 <= int(n) <= 30]
    return max(nums) if nums and re.search(r"slide", length or "", re.I) else None


def clean_outline_slide(sl: dict, by_ref: dict, allowed: set, source_order: list) -> Optional[dict]:
    if not isinstance(sl, dict):
        return None
    title = K.strip_period(_s(sl.get("title"), 160))
    refs = [r for r in NG._valid(sl.get("refs"), by_ref, allowed)]
    if not title or not refs:
        return None
    typ = sl.get("type") if sl.get("type") in OUTLINE_TYPES else "content"
    got = CK.check_line(title, refs, {r: by_ref[r] for r in allowed if r in by_ref})
    n = words(title)
    hint = "split" if needs_split(title, typ) else ("shorten" if n >= MAX_TITLE_WORDS else None)
    return {"title": title, "type": typ, "refs": got["refs"], "chips": NG.chips_for(got["refs"], by_ref, source_order),
            "hint": hint, "words": n,
            "check": {"status": "ok" if got["ok"] else "missing",
                      "label": "Every number matches your sources" if got["ok"] else "A number here isn't in your sources",
                      "items": got["items"]}}


def _outline_ctx(source_ids: list) -> tuple:
    S = _service()
    corpus, srcs, by_ref, shown = S._corpus(source_ids, with_ids=True)
    return corpus, srcs, by_ref, shown


def get_outline(outline_id: str) -> dict:
    if not re.fullmatch(r"ol_[a-f0-9]{12}", outline_id or ""):
        raise ValueError("That outline is gone. Write it again.")
    o = store.get_setting(f"outline:{outline_id}", None)
    if not o:
        raise ValueError("That outline is gone. Write it again.")
    return o


def save_outline(outline_id: str, slides: list) -> dict:
    """The person's own edit of an outline (move, edit, delete, add): no model, every slide re-checked."""
    o = get_outline(outline_id)
    if not isinstance(slides, list) or not slides:
        raise ValueError("An outline needs at least one slide.")
    if len(slides) > 14:
        raise ValueError("Keep the outline to 14 slides or fewer.")
    _srcs, _b, by_ref = _service().passages_for(o["source_ids"])
    allowed = set(by_ref)
    out = []
    for i, sl in enumerate(slides, start=1):
        c = clean_outline_slide(sl, by_ref, allowed, o["source_ids"])
        if c is None:
            raise ValueError(f"Slide {i} needs a title and at least one source.")
        out.append(c)
    o = {**o, "slides": out, "updated_at": store.now(), "warnings": []}
    store.set_setting(f"outline:{outline_id}", o)
    return o


@J.handler("outline")
async def job_outline(job_id: str, p: dict) -> dict:
    S = _service()
    source_ids = p.get("source_ids") or []
    brief = p.get("brief") if isinstance(p.get("brief"), dict) else {}
    corpus, srcs, by_ref, shown = _outline_ctx(source_ids)
    J.step(job_id, f"Reading {len(srcs)} source{'s' if len(srcs) != 1 else ''}")
    ask = p.get("ask") if isinstance(p.get("ask"), dict) else {}
    extra = f"\nThe sources asked for: {_s(ask.get('what'), 160)}" if ask.get("what") else ""
    body = f"{corpus}\n\nBRIEF\n{_brief_text(brief)}{extra}"
    raw = await S.model().structured(system=K.SYSTEM, instructions=OUTLINE_RULES, body=body, schema=OUTLINE_SCHEMA,
                                     purpose="outline", max_tokens=1800, timeout=150)
    J.step(job_id, "Checking every title against your sources")
    slides, warnings = [], []
    for i, sl in enumerate((raw.get("slides") if isinstance(raw, dict) else None) or [], start=1):
        c = clean_outline_slide(sl, by_ref, shown, [s["id"] for s in srcs])
        if c is None:
            warnings.append(f"Slide {i} had no source, so it was left out.")
            continue
        slides.append(c)
    slides = _cap(slides, brief)
    if len(slides) < 3:
        raise R.ModelError(R.CUT_OFF, "cut_off")
    slides, review = await review_outline(job_id, S, body, slides, brief, by_ref, shown, [s["id"] for s in srcs])
    if len(slides) < min(7, (max_slides(brief) or 8) - 1):
        warnings.append(f"Only {len(slides)} slides came back with sources. Add slides, or write the outline again.")
    oid = store.new_id("ol")
    o = {"by": BY, "outline_id": oid, "kind": "deck", "brief": {k: _s(brief.get(k), 200) for k in ("who", "goal", "length")},
         "source_ids": source_ids, "slides": slides, "review": review, "warnings": warnings, "created_at": store.now()}
    store.set_setting(f"outline:{oid}", o)
    return o


def _cap(slides: list, brief: dict) -> list:
    slides = slides[:10]
    cap = max_slides(brief)
    if cap and len(slides) > cap - 1:  # the title slide counts toward the person's length
        slides = slides[:cap - 2] + [slides[-1]]
    return slides


def min_kept(slides: list, brief: dict) -> int:
    """The fewest slides a revised outline may keep: the brief's shortest length less the title slide ("7 to 9
    slides" gives 6), else the draft less one. A review may cut a slide that does not argue, never the length."""
    length = (brief or {}).get("length") if isinstance(brief, dict) else ""
    nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", length or "") if 3 <= int(n) <= 30]
    floor = min(nums) - 1 if nums and re.search(r"slide", length or "", re.I) else len(slides) - 1
    return max(3, min(floor, len(slides)))


def _missing(slides: list) -> int:
    return sum(1 for sl in slides if (sl.get("check") or {}).get("status") == "missing")


def outline_rows(slides: list) -> str:
    return "\n".join(f"{i}. [{sl.get('type', 'content')}] {sl.get('title', '')} (passages: {', '.join(sl.get('refs') or [])})"
                     for i, sl in enumerate(slides, start=1))


async def review_outline(job_id: str, S, body: str, slides: list, brief: dict, by_ref: dict, shown: set,
                         source_order: list) -> tuple:
    """The outline checked as its reader would (round 5): one more model call reads the draft against the sources
    and returns a revised outline and what it changed. The revision is kept only when every slide still has a
    source, it keeps the brief's length (or the draft less one when the brief names none), and no more of its titles
    fail the number check.
    ``review`` is ``[{text, chips, refs}]``: what the pane shows under "Checked the outline"."""
    J.step(job_id, "Checking the outline as your reader would")
    try:
        raw = await S.model().structured(system=K.SYSTEM, instructions=REVIEW_RULES,
                                         body=f"{body}\n\nTHE OUTLINE DRAFT\n{outline_rows(slides)}", schema=REVIEW_SCHEMA,
                                         purpose="outline_review", max_tokens=2400, timeout=150)
    except (R.ModelError, ValueError):
        return slides, []
    raw = raw if isinstance(raw, dict) else {}
    got = [c for c in (clean_outline_slide(sl, by_ref, shown, source_order) for sl in raw.get("slides") or []) if c]
    got = _cap(got, brief)
    if len(got) < min_kept(slides, brief) or _missing(got) > _missing(slides):
        return slides, []
    if [(a["title"], a["type"], a["refs"]) for a in got] == [(b["title"], b["type"], b["refs"]) for b in slides]:
        return slides, []  # a re-cited slide is a change too: the write call fills each slide from its passages
    review = []
    for ch in raw.get("changes") or []:
        if not isinstance(ch, dict):
            continue
        text = K.strip_period(_s(ch.get("text"), 200))
        refs = NG._valid(ch.get("refs"), by_ref, shown)
        if not text:
            continue
        pool = {r: by_ref[r] for r in shown if r in by_ref}
        if K.numbers(text) and not CK.check_line(text, refs or list(pool), pool)["ok"]:
            continue  # a change note with a number the sources don't hold is not shown
        review.append({"text": text, "refs": refs, "chips": NG.chips_for(refs, by_ref, source_order)})
    return got, review[:5]


@J.handler("rewrite_title")
async def job_rewrite_title(job_id: str, p: dict) -> dict:
    S = _service()
    o = get_outline(p.get("outline_id") or "")
    i = p.get("index")
    if not isinstance(i, int) or not 0 <= i < len(o["slides"]):
        raise J.JobError("That slide is gone from the outline.", "gone")
    sl = o["slides"][i]
    _srcs, _b, by_ref = S.passages_for(o["source_ids"])
    cited = [r for r in sl["refs"] if r in by_ref]
    body = (f"BRIEF\n{_brief_text(o.get('brief'))}\n\nTHE OUTLINE\n" +
            "\n".join(f"{n}. {s['title']}" for n, s in enumerate(o["slides"], start=1)) +
            f"\n\nREWRITE SLIDE {i + 1}: {sl['title']}\n\nITS PASSAGES\n" +
            "\n".join(f"[{r}] ({by_ref[r]['locator']}) {by_ref[r]['text']}" for r in cited))
    J.step(job_id, "Writing three titles")
    raw = await S.model().structured(system=K.SYSTEM, instructions=REWRITE_RULES, body=R.redact(body), schema=REWRITE_SCHEMA,
                                     purpose="rewrite_title", max_tokens=600, timeout=90)
    allowed = set(cited)
    opts, seen = [], {sl["title"].lower()}
    for op in (raw.get("options") if isinstance(raw, dict) else None) or []:
        if not isinstance(op, dict):
            continue
        op = {"title": op.get("title"), "type": sl["type"], "refs": op.get("refs") or cited}
        c = clean_outline_slide(op, by_ref, allowed, o["source_ids"])
        if c is None or c["check"]["status"] != "ok" or c["title"].lower() in seen or K.SHORTHAND.search(c["title"]):
            continue
        seen.add(c["title"].lower())
        opts.append({k: c[k] for k in ("title", "chips", "refs", "hint", "words")})
    if not opts:
        raise J.JobError("None of the new titles matched your sources. Press Retry, or edit the title yourself.", "unchecked")
    return {"by": BY, "outline_id": o["outline_id"], "index": i, "before": sl["title"], "options": opts[:3]}


# ---------------------------------------------------------------- element edits --

SLIDE_ITEM = K.DECK_SCHEMA["properties"]["slides"]["items"]
ONE_SLIDE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["slide"], "properties": {"slide": SLIDE_ITEM}}
THREE_SLIDES_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["options"],
                       "properties": {"options": {"type": "array", "minItems": 3, "maxItems": 3, "items": SLIDE_ITEM}}}

EDIT_RULES = {
    "shorter": "Make this slide shorter: fewer words on every line, the same facts, the same type, the same numbers. "
               "Return the slide in the same JSON shape.",
    "stronger": "Write three stronger versions of this slide. The headline is what changes: the heading, or on a stat "
                "slide the label beside the number. Each of the three headlines is different from the old one and "
                "from the other two: one leads with the number, one with the people, one with the consequence. "
                "Plainer and more direct, never longer. Same type, same facts, same numbers. Return three slides in "
                "the same JSON shape.",
    "chart": "Turn this slide into an exhibit slide: a chart of the numbers it already has (two to six, of one kind), "
             "each bar labeled in under five words, with a heading that states what the chart shows as a full "
             "sentence under 14 words. Use only these numbers, written exactly as they are.",
    "insert": "Write one new slide to add to the deck: {what}. Take it from the passages below, with its passage "
              "labels. A quote slide copies a source's exact words from one passage.",
}
EDIT_SYSTEM_TAIL = ("\n\nYou return JSON for one slide only. You never choose a tool, export, delete or save anything; "
                    "the person decides what to keep.")


def _clean_slide(raw, fallback_refs: list, allowed: set) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    try:
        got = K.clean_deck({"title": "Deck", "subtitle": "", "slides": [raw, {"type": "section", "heading": "x"},
                                                                          {"type": "section", "heading": "y"}]})["slides"]
    except ValueError:
        return None
    if len(got) < 3:
        return None
    sl = got[0]
    sl["refs"] = [r for r in sl.get("refs") or [] if r in allowed] or list(fallback_refs)
    for k in ("bullets", "left_items", "right_items", "bars", "steps"):
        for it in sl.get(k) or []:
            if it.get("ref") not in allowed:
                it["ref"] = sl["refs"][0] if sl["refs"] else ""
    return sl


def _drawing():
    try:
        from . import kits as KITS, layout as L, render_deck as RD, render_graphic as RG
    except ImportError:  # loaded loose
        import kits as KITS, layout as L, render_deck as RD, render_graphic as RG  # type: ignore
    return KITS, L, RD, RG


def _kit_parts(output_id: Optional[str], kit_id: str) -> Optional[tuple]:
    S = _service()
    KITS, _L, _RD, _RG = _drawing()
    try:
        kit = KITS.get(kit_id)
        if output_id:
            kit = S.kit_for_output(output_id, kit)
        pal, faces = KITS.palette(kit), KITS.faces(kit)
        logo, _variants = S.logo_srcs(kit, pal)
    except Exception:  # noqa: BLE001 - no kit, no picture; the canvas draws its fallback
        return None
    return kit, pal, faces, logo


def slide_trees(output_id: str, kit_id: str, doc: dict, i: int, news: list, insert_at: Optional[int] = None) -> tuple:
    """``(before_tree, [tree per new slide])``: each slide as the scene node the canvas draws, set in ``kit_id``
    inside the whole deck (so source numbers match the proof). ``None`` wherever it can't be drawn."""
    parts = _kit_parts(output_id, kit_id)
    if not parts:
        return None, [None] * len(news)
    kit, pal, faces, logo = parts
    S = _service()
    _KITS, L, RD, _RG = _drawing()
    out = S._output(output_id)
    _srcs, _b, by_ref = S.passages_for(out["source_ids"])
    date = S.nice_date(out.get("created_at"))

    def node(d: dict, at: int):
        try:
            tree, _scs = RD.deck_tree(d, kit, pal, faces, by_ref, date, logo_urls=logo)
            return tree["k"][at + 1]  # frame 0 is the title slide
        except Exception:  # noqa: BLE001
            return None
    before = node(doc, i) if insert_at is None else None
    trees = []
    for sl in news:
        d = copy.deepcopy(doc)
        if insert_at is None:
            d["slides"][i] = sl
            trees.append(node(d, i))
        else:
            d["slides"].insert(insert_at, sl)
            trees.append(node(d, insert_at))
    return before, trees


def graphic_tree(kit_id: str, spec: dict, by_ref: dict):
    parts = _kit_parts(None, kit_id) if kit_id else None
    if not parts:
        return None
    kit, pal, faces, logo = parts
    _KITS, L, _RD, RG = _drawing()
    try:
        idx, _rows = L.source_index(spec, by_ref)
        return RG.tree(spec, kit, pal, faces, idx, by_ref, logo_urls=logo)[0]
    except Exception:  # noqa: BLE001
        return None


def check_slide(sl: dict, by_ref: dict) -> dict:
    """``{status, label, items}`` for one slide, by the same checker every proof uses."""
    g = CK.grounding({"title": "", "subtitle": "", "slides": [sl]}, by_ref)
    nums = [i for i in g["items"] if i["kind"] in ("number", "quote")]
    if g["missing"]:
        n = len(g["missing"])
        return {"status": "missing", "label": f"{n} number{'s' if n != 1 else ''} not found in your sources",
                "items": CK.public_items(g["missing"])}
    return {"status": "ok", "label": CK.match_label(len(nums)), "items": []}


def headline(sl: dict) -> str:
    """The words a reader takes as the slide's headline: the heading, or a stat's label, or a quote."""
    return _s(sl.get("heading") or sl.get("label") or sl.get("quote") or "", 200)


def _passed_numbers(sl: dict, by_ref: dict) -> list:
    g = CK.grounding({"title": "", "subtitle": "", "slides": [sl]}, by_ref)
    return [i for i in g["items"] if i["kind"] == "number" and i["status"] in ("ok", "moved", "computed")]


def _output_doc(output_id: str) -> tuple:
    S = _service()
    out = S._output(output_id)
    doc = copy.deepcopy(out.get("neutral") or {})
    _srcs, _b, by_ref = S.passages_for(out["source_ids"])
    return out, doc, by_ref


def live_doc(output_id: str, kit_id: str, neutral: dict) -> dict:
    """The doc as the canvas shows it in ``kit_id``: that kit's voiced words, its say-this-not-that pairs, and the
    checker's citation fixes (``service._doc_for``, the same path every proof and export takes). When the kit has no
    render yet, or its render no longer has the neutral draft's shape, the neutral draft is what shows."""
    S = _service()
    try:
        kit = S.KITS.get(kit_id) if kit_id else None
        doc = S._doc_for(output_id, kit) if kit else None
    except Exception:  # noqa: BLE001 - a missing kit or render falls back to the neutral words
        doc = None
    if not isinstance(doc, dict) or K.kind_of(doc) != K.kind_of(neutral):
        return copy.deepcopy(neutral)
    if K.kind_of(doc) == "deck" and len(doc.get("slides") or []) != len(neutral.get("slides") or []):
        return copy.deepcopy(neutral)
    return copy.deepcopy(doc)


@J.handler("element_edit")
async def job_element_edit(job_id: str, p: dict) -> dict:
    S = _service()
    output_id, kit_id, action = p.get("output_id") or "", p.get("kit_id") or "", p.get("action")
    out, neutral, by_ref = _output_doc(output_id)
    if K.kind_of(neutral) != "deck":
        raise J.JobError("Slide edits work on decks. Make a deck first.", "not_deck")
    doc = live_doc(output_id, kit_id, neutral)  # "Now" is the slide as it reads on screen, in this brand
    slides = doc.get("slides") or []
    i = p.get("slide")
    on_title = p.get("on") == "title"  # the title slide has no entry in ``slides``; the pane says when it is the one open
    if not isinstance(i, int) or not 0 <= i < len(slides):
        raise J.JobError("That slide is gone. Pick a slide and try again.", "gone")
    before = slides[i]
    res = {"by": BY, "output_id": output_id, "kit_id": kit_id, "slide": i, "action": action, "status": "ok",
           "message": None, "before": before, "base": (neutral.get("slides") or [])[i], "options": [], "insert_after": None}
    what = None
    if action == "typed":
        m = INSERT.match(p.get("text") or "")
        want = None if m else parse_set_text(p.get("text") or "")
        if want:  # the person's own words for one field: set as typed, checked, shown, kept only on Keep
            got = set_text_option(doc, neutral, by_ref, on_title, i, want)
            if got["status"] != "ok":
                return {**res, "action": "retitle", "status": "refused", "message": got["message"]}
            J.step(job_id, "Checking every number against your sources")
            path, f = got["path"], got["frame"]
            opt = got["option"]
            res.update(action="retitle", path=path, frame=f, before_text=got["before_text"], base_text=got["base_text"], by=BY_YOU)
            if opt["slide"] is not None:
                k = f - 1
                res.update(slide=k, before=slides[k], base=(neutral.get("slides") or [])[k])
            else:
                res.update(before={"heading": got["before_text"]}, base=None)
                opt["slide"] = {"type": "title", "heading": opt["text"]}
            res["before_tree"], opt["tree"] = frame_trees(output_id, kit_id, [doc, got["after"]], f)
            res["options"] = [opt]
            return res
        if not m:
            return {**res, "status": "refused", "message": REFUSE_TYPED}
        what, n = m.group(1).lower(), int(m.group(2))
        if not 1 <= n <= len(slides) + 1:
            return {**res, "status": "refused", "message": f"This deck has {len(slides) + 1} slides. Pick a slide number from 1 to {len(slides) + 1}."}
        action, res["action"], res["insert_after"] = "insert", "insert", n
    if action not in ("shorter", "stronger", "chart", "insert"):
        return {**res, "status": "refused", "message": REFUSE_TYPED}
    cited = [r for r in before.get("refs") or [] if r in by_ref]
    if action == "insert":
        cited = list(dict.fromkeys(r for sl in slides for r in (sl.get("refs") or []) if r in by_ref)) or list(by_ref)
    if action == "chart":
        nums = _passed_numbers(before, by_ref)
        if len({n["value"] for n in nums}) < 2:
            return {**res, "status": "refused",
                    "message": "A chart needs two or more numbers that match your sources, and this slide has fewer."}
    allowed = set(cited)
    instr = EDIT_RULES[action].format(what="a quote" if what == "quote" else "one more point")
    body = (f"THE SLIDE (JSON)\n{store.dumps(before)}\n\nITS PASSAGES\n" +
            "\n".join(f"[{r}] ({by_ref[r]['locator']}) {by_ref[r]['text']}" for r in cited[:24]))
    J.step(job_id, {"shorter": "Shortening the slide", "stronger": "Writing three headlines", "chart": "Turning it into a chart",
                    "insert": "Writing the new slide"}[action])
    schema = THREE_SLIDES_SCHEMA if action == "stronger" else ONE_SLIDE_SCHEMA
    raw = await S.model().structured(system=K.SYSTEM + EDIT_SYSTEM_TAIL, instructions=instr, body=R.redact(body), schema=schema,
                                     purpose="element_edit", max_tokens=1400, timeout=120)
    cands = (raw.get("options") if action == "stronger" else [raw.get("slide")]) if isinstance(raw, dict) else []
    J.step(job_id, "Checking every number against your sources")
    seen = {store.dumps(before)}
    heads = {headline(before).lower()} if action == "stronger" else set()
    for c in cands or []:
        sl = _clean_slide(c, cited if action != "insert" else cited[:1], allowed)
        if sl is None:
            continue
        if action == "chart":
            if sl["type"] != "exhibit":
                continue
            have = {n["value"] for n in _passed_numbers(before, by_ref)}
            if any((K.numbers(b.get("value", ""))[:1] or [""])[0] not in have for b in sl.get("bars") or []):
                continue
        if action == "insert" and what == "quote" and sl["type"] != "quote":
            continue
        chk = check_slide(sl, by_ref)
        key = store.dumps(sl)
        if chk["status"] != "ok" or key in seen:
            continue
        if action == "stronger":
            hl = headline(sl).lower()
            if not hl or hl in heads or K.SHORTHAND.search(hl):  # a different headline, in plain words
                continue
            heads.add(hl)
        seen.add(key)
        res["options"].append({"slide": sl, "check": chk})
    if not res["options"]:
        res.update(status="unchanged", message="Nothing new passed the check against your sources, so the slide stays as it is. Press Retry.")
        res["before_tree"] = slide_trees(output_id, kit_id, doc, i, [])[0] if action != "insert" else None
        return res
    at = None
    if action == "insert":
        at = min(max(int(res["insert_after"] or 1) - 1, 0), len(slides))
    before_tree, trees = slide_trees(output_id, kit_id, doc, i, [o["slide"] for o in res["options"]], insert_at=at)
    res["before_tree"] = before_tree
    for o, t in zip(res["options"], trees):
        o["tree"] = t
    return res


# ---------------------------------------------------------------- fix it for me --

FIX_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"],
              "properties": {"text": {"type": "string", "description": "The corrected sentence"}}}
FIX_RULES = """A sentence in a document has a number or quote that its sources don't hold. Correct the sentence so
it says what the passage says: change only the words that are wrong, keep the rest as written, and keep it about as
long. Use the passage's number exactly as the passage writes it, and name what is counted the way the passage
names it (its own noun, with the words that qualify it). The sentence sits on a slide with other lines (THE REST OF
THE SLIDE): the corrected sentence must still fit them and say what they are about. When the passage closest to the
sentence counts something else, use the passage the slide's lines rest on, so a headline over waitlist points still
speaks of the waitlist. Keep every word that says what kind of claim the number is: when the sentence or the passage
says "staff estimate", "expect", "plan", "proposed", "about" or "average", the corrected sentence says it too
("Staff estimate 180 more learners a year", never "180 more learners in one year")."""


_TOK = re.compile(r"\S+|\s+")


def word_diff(before: str, after: str) -> list:
    """``[{op: same|del|add, text}]``, word by word, with runs joined. Every part keeps its own spaces, so the
    ``same`` and ``add`` parts joined with "" give ``after`` exactly, and ``same`` and ``del`` give ``before``."""
    a, b = _TOK.findall(before or ""), _TOK.findall(after or "")
    out = []

    def push(op, ws):
        t = "".join(ws)
        if not t:
            return
        if out and out[-1]["op"] == op:
            out[-1]["text"] += t
        else:
            out.append({"op": op, "text": t})
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            push("same", a[i1:i2])
        else:
            push("del", a[i1:i2])
            push("add", b[j1:j2])
    return out


def _slide_rest(doc: dict, path: str) -> list:
    """The other lines on the slide that holds ``path`` (its heading, points, figures), for a fix that must fit them."""
    parts = (path or "").split(".")
    if len(parts) < 2 or parts[0] != "slides" or not parts[1].isdigit():
        return []
    pre = f"slides.{parts[1]}."
    return [t for fp, t, _r in K.field_texts(doc) if (fp + ".").startswith(pre) and fp != path and t and t.strip()]


def _field(doc: dict, path: str) -> Optional[tuple]:
    for fp, text, refs in K.field_texts(doc):
        if fp == path:
            return text, [r for r in refs if r]
    return None


@J.handler("fix_it")
async def job_fix_it(job_id: str, p: dict) -> dict:
    S = _service()
    output_id, kit_id, key = p.get("output_id") or "", p.get("kit_id") or "", p.get("key") or ""
    out, neutral, by_ref = _output_doc(output_id)
    doc = live_doc(output_id, kit_id, neutral)  # the claim key and "Now" come from the text on screen
    path, _, rest = key.partition("|")
    kind, _, value = rest.partition("|")
    found = _field(doc, path)
    if not found or kind not in ("number", "quote"):
        raise J.JobError("That flag is gone. The text may have changed.", "gone")
    text, refs = found
    g = CK.grounding(doc, by_ref)
    item = next((i for i in g["items"] if i["key"] == key), None)
    if not item or item["status"] != "missing":
        raise J.JobError("That number already matches your sources.", "gone")
    rest = _slide_rest(doc, path)
    # Round 10 (critic 9, S15): the fix corrects from the passage the flag names. checks.grounding already picks the
    # passage the rest of the slide rests on (round 8: a headline over waitlist points takes the waitlist's number).
    ref = (item.get("closest") or {}).get("ref") or (CK.closest(text, by_ref, list(by_ref)) or {}).get("ref")
    if not ref:
        return {"by": BY, "output_id": output_id, "kit_id": kit_id, "key": key, "path": path, "status": "unchanged",
                "before": text, "after": text, "diff": [{"op": "same", "text": text}], "chips": [],
                "check": {"status": "missing", "label": "No passage in your sources is close to this sentence. Edit it, or remove it."}}
    passage = by_ref[ref]
    body = f"THE SENTENCE\n{text}\n\nTHE WRONG PART\n{item.get('shown') or value}\n\nTHE CLOSEST PASSAGE\n[{ref}] ({passage['locator']}) {passage['text']}"
    if rest:
        body += "\n\nTHE REST OF THE SLIDE\n" + "\n".join(f"- {t}" for t in rest[:8])
    J.step(job_id, "Writing the correction")
    # Round 10 (critics 7, 8, 9, S15/S16): a fix keeps the words that say what kind of claim the number is ("staff
    # estimate", "expect", "plan", "about", "average"). A correction that drops one is sent back once with the words
    # named; if the second try drops one too, nothing changes.
    after, chk, still, lost = "", {"ok": False, "refs": []}, False, []
    for attempt in range(2):
        ask = body
        if lost:
            ask += ("\n\nKEEP THESE WORDS\nYour last correction dropped " + ", ".join(f'"{w}"' for w in lost)
                    + ". The sentence or the passage says it, so the corrected sentence must say it too.")
        raw = await S.model().structured(system=K.SYSTEM, instructions=FIX_RULES, body=R.redact(ask), schema=FIX_SCHEMA,
                                         purpose="fix_it", max_tokens=300, timeout=60)
        after = _s(raw.get("text") if isinstance(raw, dict) else "", 600)
        if text.rstrip()[-1:] not in ".!?":  # a headline without a period keeps none
            after = K.strip_period(after)
        if attempt == 0:
            J.step(job_id, "Checking the correction")
        chk = CK.check_line(after, [ref] + [r for r in refs if r in by_ref], by_ref, all_ids=[ref])
        still = value in [v for _r, v, _a, _b in K.claim_spans(after)] if kind == "number" else False
        lost = CK.hedges_dropped(text, after, passage["text"]) if after else []
        if not lost:
            break
    base = {"by": BY, "output_id": output_id, "kit_id": kit_id, "key": key, "path": path, "before": text,
            "source_ref": ref, "source_title": passage.get("source_title") or "", "source_locator": passage.get("locator") or ""}
    if lost and after and after != text:
        return {**base, "status": "unchanged", "after": text, "diff": [{"op": "same", "text": text}], "chips": [],
                "check": {"status": "missing", "label": "The correction dropped \u201c" + lost[0] + "\u201d, so nothing changed. Press Retry, or edit it yourself."}}
    if not after or after == text or not chk["ok"] or still:
        return {**base, "status": "unchanged", "after": text, "diff": [{"op": "same", "text": text}], "chips": [],
                "check": {"status": "missing", "label": "The correction didn't match your sources, so nothing changed. Press Retry, or edit it yourself."}}
    return {**base, "status": "ok", "after": after, "diff": word_diff(text, after), "refs": chk["refs"],
            "chips": NG.chips_for(chk["refs"], by_ref, out["source_ids"]), "check": {"status": "ok", "label": "Matches your source"}}


# ---------------------------------------------------------------- graphic options --

GRAPHIC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["options"],
                  "properties": {"options": {"type": "array", "minItems": 3, "maxItems": 3, "items": K.VISUAL_SCHEMA}}}
GRAPHIC_RULES = """Make three different information graphics from the note below and its passages, one per form, each
a different form (bars, figures, compare, timeline): pick the three forms the numbers suit best. Each graphic
carries one message, stated as its headline in a full sentence under 14 words. Every value is copied exactly as a
passage writes it, with that passage's label. Never invent a number. The first graphic answers THE QUESTION (or, with
none, the note's own point) with the numbers the note uses: a note about reserves against a budget rise gets a graphic
of reserves against the budget rise first. A timeline only puts steps in an order the passages state; never write
"before", "after", "then" or "led to" unless the passage says it."""

# Round 10 (critic 8, S17): words that put two things in an order. A timeline step may use one only when its passage
# does ("a waitlist formed before the October 21 vote" overstated the sources).
ORDER_WORDS = ("before", "after", "then", "led to", "leads to", "followed", "following", "until", "since", "afterward",
               "prior to", "ahead of", "later", "earlier")


def _order_ok(text: str, passage: str) -> bool:
    return all(CK._has(passage, (w,)) for w in ORDER_WORDS if CK._has(text, (w,)))


def _answers(spec: dict, ask: str) -> float:
    """How directly a graphic answers the question it was made from: the numbers it shares with the note and question,
    then the words its headline shares with them. The first option shown is the one that answers best."""
    nums = set(K.numbers(ask or ""))
    vals = [v for it in spec.get("items") or [] for v in K.numbers(it.get("value", ""))]
    hits = sum(1 for v in vals if v in nums)
    words = lambda t: {w for w in re.findall(r"[a-z]{4,}", (t or "").lower())}
    aw = words(ask)
    head = words(" ".join([spec.get("headline", "")] + [it.get("label", "") for it in spec.get("items") or []]))
    return hits * 2 + (len(aw & head) / len(aw) if aw else 0)


def _visual_ok(spec: dict, by_ref: dict) -> bool:
    for it in spec.get("items") or []:
        v = (K.numbers(it.get("value", "")) or [None])[0]
        if not v or it.get("ref") not in by_ref or not CK.find_number(v, by_ref, [it["ref"]]):
            return False
    for st in spec.get("steps") or []:
        if st.get("ref") not in by_ref or not CK.check_line(st.get("text", ""), [st["ref"]], by_ref, all_ids=[st["ref"]])["ok"]:
            return False
        if not _order_ok(f"{st.get('when', '')} {st.get('text', '')}", by_ref[st["ref"]].get("text", "")):
            return False
    for f, rk in (("headline", None), ("takeaway", "takeaway_refs"), ("dek", "dek_refs")):
        refs = [i.get("ref") for i in spec.get("items") or []] + (spec.get(rk) or [] if rk else [])
        if not CK.check_line(spec.get(f, ""), [r for r in refs if r], by_ref, all_ids=[r for r in refs if r])["ok"]:
            return False
    return True


@J.handler("graphic_options")
async def job_graphic_options(job_id: str, p: dict) -> dict:
    S = _service()
    source_ids = p.get("source_ids") or []
    _srcs, _b, by_ref = S.passages_for(source_ids)
    if not by_ref:
        raise J.JobError("Choose at least one source first.", "no_sources")
    text, refs, question = _s(p.get("text"), 3000), [], _s(p.get("question"), 600)
    if p.get("note_id"):
        row = store.one("SELECT * FROM notes WHERE id=?", (p["note_id"],))
        if not row:
            raise J.JobError("That note is gone.", "gone")
        text = _s(row.get("text"), 3000)
        refs = [r for r in (store.loads(row.get("refs"), []) or []) if r in by_ref]
        if row.get("chat_id") and not question:
            asked = store.one("SELECT content FROM chats WHERE id<=? AND role='user' ORDER BY id DESC LIMIT 1", (row["chat_id"],))
            question = _s((asked or {}).get("content"), 600)
    if not text:
        raise J.JobError("Pin an answer first, then make a graphic from it.", "empty")
    if refs:
        cited = refs
        corpus = "\n".join(f"[{r}] ({by_ref[r]['locator']}) {by_ref[r]['text']}" for r in cited)
    else:
        corpus, _srcs2, _by, shown = S._corpus(source_ids, with_ids=True)
        cited = [r for r in shown if r in by_ref]
    allowed = {r: by_ref[r] for r in cited}
    J.step(job_id, "Drawing up three graphics")
    raw = await S.model().structured(system=K.SYSTEM, instructions=GRAPHIC_RULES, body=R.redact((f"THE QUESTION\n{question}\n\n" if question else "") + f"THE NOTE\n{text}\n\nPASSAGES\n{corpus}"),
                                     schema=GRAPHIC_SCHEMA, purpose="graphic_options", max_tokens=2200, timeout=150)
    J.step(job_id, "Checking every value against your sources")
    opts, forms, dropped = [], set(), 0
    for spec in (raw.get("options") if isinstance(raw, dict) else None) or []:
        try:
            v = K.clean_visual(spec)
        except ValueError:
            dropped += 1
            continue
        if v["form"] in forms:
            dropped += 1
            continue
        if not _visual_ok(v, allowed):
            dropped += 1
            continue
        forms.add(v["form"])
        opts.append({"form": v["form"], "spec": v, "check": {"status": "ok", "label": "Every value matches your sources"},
                     "refs": [it.get("ref") for it in v.get("items") or [] if it.get("ref")] + [st.get("ref") for st in v.get("steps") or [] if st.get("ref")],
                     "tree": graphic_tree(p.get("kit_id") or "", v, by_ref)})
    if not opts:
        raise J.JobError("None of the graphics matched your sources. Press Retry.", "unchecked")
    ask = f"{question} {text}"
    opts.sort(key=lambda o: -_answers(o["spec"], ask))  # stable: the model's order breaks ties
    return {"by": BY, "source_ids": source_ids, "options": opts, "dropped": dropped}


# ---------------------------------------------------------------- keep, discard, undo --

def _version_fn(name: str):
    fn = getattr(store, name, None)
    if not callable(fn):
        raise ValueError("Keep isn't wired yet.")
    return fn


def kept_doc(output_id: str, job: dict, choice: int) -> tuple:
    """``(doc, reason)``: the output's doc with one option of a finished job applied, re-checked. Pure: saves nothing."""
    if not job or job.get("status") != "done" or job.get("kind") not in ("element_edit", "fix_it"):
        raise ValueError("That suggestion is gone. Ask for it again.")
    res = job.get("result") or {}
    if res.get("output_id") != output_id:
        raise ValueError("That suggestion is for another output.")
    if store.get_setting(f"revise_discarded:{job['id']}", False):
        raise ValueError("That suggestion was discarded. Ask for it again.")
    _out, doc, by_ref = _output_doc(output_id)
    slides = doc.get("slides") or []
    if job["kind"] == "element_edit":
        opts = res.get("options") or []
        if res.get("status") != "ok" or not isinstance(choice, int) or not 0 <= choice < len(opts):
            raise ValueError("Pick one of the options first.")
        if res.get("action") == "retitle":
            path, text = res.get("path") or "", opts[choice].get("text") or ""
            if not SET_PATH.fullmatch(path) or not text:
                raise ValueError("That suggestion is gone. Ask for it again.")
            if _get_path(doc, path) != (res.get("base_text") or ""):
                raise ValueError("That slide changed since. Ask for the change again.")
            if not _put_text(doc, path, text):
                raise ValueError("That slide changed since. Ask for the change again.")
            if check_field(doc, path, by_ref)["status"] != "ok":
                raise ValueError("That option no longer matches your sources.")
            what = "subtitle" if path.rsplit(".", 1)[-1] in ("subtitle", "context") else "title"
            return doc, f"Changed the {what}, slide {int(res.get('frame') or 0) + 1}"
        new = copy.deepcopy(opts[choice]["slide"])
        if check_slide(new, by_ref)["status"] != "ok":
            raise ValueError("That option no longer matches your sources.")
        i = res.get("slide")
        if res.get("action") == "insert":
            at = min(max(int(res.get("insert_after") or 1) - 1, 0), len(slides))  # slide N on screen counts the title slide
            slides.insert(at, new)
            reason = f"Added a slide after slide {res.get('insert_after')}"
        else:
            base = res.get("base") if res.get("base") is not None else res.get("before")
            if not isinstance(i, int) or not 0 <= i < len(slides) or store.dumps(slides[i]) != store.dumps(base):
                raise ValueError("That slide changed since. Ask for the suggestion again.")
            slides[i] = new
            reason = {"shorter": "Shorter", "stronger": "Stronger headline", "chart": "Turned into a chart"}.get(res.get("action"), "Edited") + f", slide {i + 2}"
        doc["slides"] = slides
        return doc, reason
    if res.get("status") != "ok":
        raise ValueError("That fix didn't pass the check, so there is nothing to keep.")
    found = _field(live_doc(output_id, res.get("kit_id") or "", doc), res.get("path") or "")
    if not found or found[0] != res.get("before"):
        raise ValueError("That sentence changed since. Ask for the fix again.")
    parts = res["path"].split(".")
    if len(parts) >= 2 and parts[-2] in ("bars", "steps", "items"):
        raise ValueError("Chart labels are fixed by hand: edit the bar, or remove it.")
    target = doc
    for part in parts[:-1]:
        target = target[int(part)] if part.isdigit() else target[part]
    last = parts[-1]
    if isinstance(target, list):
        holder = target[int(last)]
        holder["text"] = res["after"]
        if res.get("refs"):
            holder["ref"] = res["refs"][0]
    else:
        target[last] = res["after"]
        if res.get("refs") and isinstance(target.get("refs"), list):
            target["refs"] = list(dict.fromkeys(target["refs"] + res["refs"]))
    return doc, "Fixed a number"


def keep(output_id: str, job_id: str, choice: int = 0) -> int:
    doc, reason = kept_doc(output_id, J.get(job_id), choice)
    v = _version_fn("add_version")(output_id, doc, reason)
    store.set_setting(f"revise_discarded:{job_id}", True)  # one Keep per suggestion
    return v


def discard(job_id: str) -> dict:
    job = J.get(job_id)
    if not job or job.get("kind") not in KINDS:
        raise ValueError("That suggestion is gone already.")
    store.set_setting(f"revise_discarded:{job_id}", True)
    return {"ok": True}


def undo(output_id: str) -> int:
    return _version_fn("undo")(output_id)
