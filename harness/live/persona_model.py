"""A scripted stand-in for the user's Hermes model in the live harness (never used by Hermes itself).

Two personas from the Nov 8 test have scripts (Denise's literacy nonprofit, Ana's catering kitchen): every claim
names a 'find' phrase, which becomes the ref of the passage holding it, and one deliberate derived number
(Denise's "144") tests the checker the way a real model slip would. Any other sources get a plain generic
writer that builds each output from the passages themselves, so a tester can bring their own files."""
import copy, json, re

class R:
    def __init__(self, parsed):
        self.parsed = parsed; self.text = json.dumps(parsed); self.usage = {"input_tokens": 3100, "output_tokens": 900}

LOG = []

def refs_of(body):
    # a passage runs to the next label: packed passages hold more than one paragraph
    return [(r, l, t.replace("\n", " ")) for r, l, t in
            re.findall(r"\[(P\d+)\] \(([^)]*)\) (.+?)(?=\n\[P\d+\] |\n\n=== |\n\nCONVERSATION|\Z)", body, re.S)]

def ref_for(ps, phrase):
    for r, _l, t in ps:
        if phrase.lower() in t.lower():
            return r
    LOG.append(("miss", phrase))
    return ps[0][0]

def ground(obj, ps):
    if isinstance(obj, dict):
        o = {}
        for k, v in obj.items():
            if k == "find":
                continue
            o[k] = ground(v, ps)
        if "find" in obj:
            f = obj["find"]
            if "refs" in obj or "heading" in obj and "body" in obj or "segments" not in obj and obj.get("type"):
                o["refs"] = [ref_for(ps, f)]
            else:
                o["ref"] = ref_for(ps, f)
        return o
    if isinstance(obj, list):
        return [ground(x, ps) for x in obj]
    return obj

# ---------------- Denise ----------------
D_ONE = {
    "title": "A sixth site to cut the literacy waitlist",
    "dek": "Harborlight enrolled 1,148 adult learners in FY2026, and 287 more are waiting for a seat.",
    "dek_refs_find": "287 adults were on the waitlist",
    "stat": {"value": "1,148", "label": "adult learners enrolled in FY2026", "find": "enrolled 1,148 adult learners"},
    "sections": [
        {"heading": "What learners gained", "find": "gained one or more reading levels", "refs": [],
         "body": "Sixty-eight percent of learners who stayed at least 12 weeks gained one or more reading levels. Seventy-one learners earned a high school equivalency credential, the most in Harborlight's history."},
        {"heading": "Who made it happen", "find": "214 volunteer tutors", "refs": [],
         "body": "A corps of 214 volunteer tutors gave 9,870 tutoring hours. The average tutor stayed 14 months."},
        {"heading": "What it cost", "find": "Operating expenses for FY2026 were $1,420,000", "refs": [],
         "body": "Operating expenses were $1,420,000, and 81 percent went to programs. The cost per learner was $1,237."},
        {"heading": "What we ask the board", "find": "approve an FY2027 budget of $1,610,000", "refs": [],
         "body": "Staff recommend an FY2027 budget of $1,610,000. It adds a sixth site at the Eastgate branch library and serves 180 more learners a year, about 144 fewer people waiting."},
    ],
    "points": [
        {"text": "The average wait for a seat was nine weeks.", "find": "The average wait was nine weeks"},
        {"text": "Reserves stand at 3.2 months of operating expenses.", "find": "3.2 months of operating expenses"},
        {"text": "The board votes on October 21.", "find": "vote on the FY2027 budget on October 21"},
    ],
    "quote": {"text": "I read my granddaughter a bedtime story for the first time this spring.", "who": "A learner at the Riverside site", "find": "bedtime story"},
    "next": "The board votes on the FY2027 budget and the sixth site on October 21.",
}
D_DECK = {"title": "A sixth site for Harborlight", "subtitle": "For funders and the October 21 board vote", "slides": [
    {"type": "section", "heading": "Demand is outgrowing our seats", "subtitle": "FY2026 in brief", "find": "enrolled 1,148 adult learners"},
    {"type": "stat", "value": "1,148", "label": "adult learners enrolled", "context": "Up from 936 the year before.", "find": "enrolled 1,148 adult learners"},
    {"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "The average wait was nine weeks.", "find": "287 adults were on the waitlist"},
    {"type": "content", "heading": "What learners gained", "find": "gained one or more reading levels", "bullets": [
        {"text": "68 percent gained a reading level or more", "find": "gained one or more reading levels"},
        {"text": "71 earned a high school equivalency credential", "find": "Seventy-one learners earned"},
        {"text": "389 were English language learners", "find": "389 were English language learners"}]},
    {"type": "quote", "quote": "I read my granddaughter a bedtime story for the first time this spring,", "who": "A learner at the Riverside site", "find": "bedtime story"},
    {"type": "stat", "value": "9,870", "label": "volunteer tutoring hours", "context": "From 214 volunteer tutors.", "find": "9,870 tutoring hours"},
    {"type": "comparison", "heading": "This year and next", "find": "approve an FY2027 budget",
     "left_label": "FY2026", "left_items": [{"text": "Five sites", "find": "five neighborhood sites"}, {"text": "$1,420,000 budget", "find": "$1,420,000"}],
     "right_label": "FY2027 proposed", "right_items": [{"text": "Sixth site at Eastgate library", "find": "sixth site at the Eastgate"}, {"text": "$1,610,000 budget", "find": "$1,610,000"}, {"text": "180 more learners a year", "find": "180 more learners"}]},
    {"type": "closing", "heading": "The ask", "text": "A sixth site cuts the waitlist in half.", "cta": "Vote yes on October 21", "find": "cut the waitlist in half"},
]}
D_AUDIO = {"title": "Harborlight in three minutes", "segments": [
    {"heading": "The short version", "find": "enrolled 1,148", "text": "Harborlight enrolled 1,148 adult learners this year, up from 936. They learned at five neighborhood sites."},
    {"heading": "The waitlist", "find": "287 adults", "text": "At year end, 287 adults were on the waitlist. The average wait was nine weeks."},
    {"heading": "Results", "find": "gained one or more reading levels", "text": "Sixty-eight percent of learners who stayed 12 weeks gained a reading level or more."},
    {"heading": "The ask", "find": "$1,610,000", "text": "Staff recommend a budget of $1,610,000 that adds a sixth site."}],
    "recap": "Three things to remember: 1,148 learners, 287 waiting, and a vote on October 21."}

# ---------------- Ana ----------------
A_ONE = {
    "title": "Fall office catering from Salvia Kitchen",
    "dek": "Boxed lunches and family-style trays, made from produce grown within 40 miles.",
    "dek_refs_find": "three farms within 40 miles",
    "stat": {"value": "$16", "label": "per boxed lunch, minimum 10 boxes", "find": "Boxed lunches, $16 per person"},
    "sections": [
        {"heading": "Boxed lunches", "find": "Roasted squash and farro salad", "refs": [],
         "body": "$16 per person, minimum 10 boxes. Each box comes with a seasonal side and piloncillo shortbread.",
         "items": [{"name": "Roasted squash and farro salad", "price": "", "note": "Sage brown butter, toasted pepitas"},
                   {"name": "Chicken mole torta", "price": "", "note": "On a bolillo roll, with pickled red onion"},
                   {"name": "Grilled vegetable torta", "price": "", "note": "Black bean spread. Vegan"}]},
        {"heading": "Family-style trays", "find": "Braised short rib with ancho", "refs": [],
         "body": "$24 per person, minimum 15 guests. Trays serve 15, 25 or 40 guests.",
         "items": [{"name": "Braised short rib", "price": "", "note": "Ancho and orange, cilantro rice, charro beans"},
                   {"name": "Lemon-herb roast chicken", "price": "", "note": "Roasted root vegetables, green salad"}]},
        {"heading": "Add-ons", "find": "agua fresca by the gallon", "refs": [], "body": "",
         "items": [{"name": "Agua fresca by the gallon", "price": "$28", "note": ""},
                   {"name": "Churro bites", "price": "$3", "note": "Per person"}]},
        {"heading": "How to order", "find": "72 hours notice", "refs": [],
         "body": "We need 72 hours notice. Delivery is free within 10 miles of downtown, $35 beyond that. Every menu can be made gluten-free, and we label all eight major allergens."},
    ],
    "points": [
        {"text": "214 events catered last year", "find": "catered 214 events"},
        {"text": "Produce from three farms within 40 miles", "find": "three farms within 40 miles"},
    ],
    "quote": None,
    "next": "Order by phone at 555-0142 or at salviakitchen.example.",
}
A_AUDIO = {"title": "Salvia Kitchen fall catering in 90 seconds", "segments": [
    {"heading": "Who we are", "find": "Ana and her brother Tomas", "text": "Salvia Kitchen is Ana and her brother Tomas. We started cooking for neighbors' parties in 2019. Last year we catered 214 events and served about 9,600 guests. Most of that was office lunches and baby showers."},
    {"heading": "Boxed lunches", "find": "Boxed lunches, $16 per person", "text": "Our boxed lunches are $16 a person, with a minimum of 10 boxes. Pick the squash and farro salad, the chicken mole torta, or the vegan grilled vegetable torta. Every box has a seasonal side and a piece of piloncillo shortbread."},
    {"heading": "Trays for a crowd", "find": "Family-style trays, $24 per person", "text": "For a bigger group, our family-style trays are $24 a person, for 15 guests or more. Choose braised short rib with ancho and orange, or lemon-herb roast chicken. Trays come for 15, 25 or 40 guests."},
    {"heading": "How to order", "find": "72 hours notice", "text": "We need 72 hours notice. Delivery is free within 10 miles of downtown, and $35 beyond that. Every menu can be made gluten-free, and we label all eight major allergens. Call 555-0142."}],
    "recap": "Three things to remember. Boxed lunches start at $16. Trays start at $24. And give us 72 hours notice."}

def which(body):
    if "Harborlight" in body: return "denise"
    if "Salvia" in body: return "ana"
    if "warming center" in body.lower() or "Cedar Hollow" in body: return "warm"
    return "other"


# The warming-center samples (samples/): hand-written, grounded outputs from harness/demo_content.py, and answers that
# bring the three sources together the way a good model would, each claim tied to its passage.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
import demo_content as DEMO  # noqa: E402

WARM_SUMMARY = {
    "warming": ("The city's season report on the Maple Street warming center: open 87 nights, 2,914 overnight stays by 412 guests, "
                "a $318,400 season, and staff recommendations for next winter.",
                ["What did the season cost, and who paid?", "Who did the center serve?", "What do staff recommend for next season?"]),
    "council": ("The council's work session on the season report. Members press on the east side walk and the second site, and the "
                "mayor puts both on the April 8 budget agenda.",
                ["Why do council members want a second site?", "Is the county grant renewing?", "When does the council decide?"]),
    "survey": ("A March survey of 188 guests and 146 volunteers: most guests felt safe, the trip there was the hardest part, and "
               "most volunteers plan to come back.",
               ["How safe did guests feel?", "What was hardest for guests?", "What do volunteers ask for?"]),
}

WARM_ANSWERS = [
    (("cost", "paid", "pay", "fund", "money"),
     "The season cost $318,400 [{a}], or $109 for each overnight stay [{a}]. The city paid $205,000 from the general fund, a county "
     "grant covered $80,000 and private donations the remaining $33,400 [{b}]. At the work session, Council Member Pham asked whether "
     "the county grant renews; the director said the county expects to renew at the same level but won't confirm it in writing until "
     "April [{c}]. A second site would add $142,000 to the season [{d}].",
     ["The season cost $318,400", "The city paid $205,000", "expect to renew at the same level", "add $142,000"]),
    (("second site", "east", "river", "bridge"),
     "Staff recommend a second site on the east side so guests don't have to cross the river at night [{a}]. Council Member Reyes "
     "described people walking across the Fifth Street bridge at two in the morning [{b}], and in the survey 74 percent of guests said the "
     "walk or ride was the hardest part of getting there [{c}]. A church on Ridge Avenue has offered its fellowship hall [{d}].",
     ["do not have to cross the river at night", "Fifth Street bridge", "74 percent said the walk", "fellowship hall"]),
]


def warm_answer(question, ps):
    q = question.lower()
    for keys, text, finds in WARM_ANSWERS:
        if any(k in q for k in keys):
            refs = [ref_for(ps, f) for f in finds]
            return {"answer": text.format(a=refs[0], b=refs[1], c=refs[2], d=refs[3]), "refs": refs,
                    "followups": ["Is the county grant renewing?", "Who did the center serve?", "When does the council decide?"]}
    r = ref_for(ps, "open 87 nights")
    r2 = ref_for(ps, "2,914 overnight stays")
    return {"answer": f"The center was open 87 nights, every night the forecast low was 32 degrees or colder [{r}]. It recorded 2,914 "
                      f"overnight stays by 412 different guests [{r2}].", "refs": [r, r2],
            "followups": ["What did the season cost, and who paid?", "Why do council members want a second site?", "How safe did guests feel?"]}


def _by_ref(ps):
    return {r: {"text": t} for r, _l, t in ps}


SENT = re.compile(r"[^.!?]+[.!?]")


def _sentences(t):
    return [x.strip() for x in SENT.findall(t) if len(x.strip()) > 20]


def generic(kind, ps):
    """A plain draft built only from the passages: each claim is a passage's own sentence, cited to it."""
    ps = ps or [("P1", "", "Your sources are empty.")]
    sents = [(r, s) for r, _l, t in ps for s in _sentences(t)] or [(ps[0][0], ps[0][2])]
    words = lambda s, n: " ".join(s.rstrip(".!?").split()[:n])
    num = [(r, s) for r, s in sents if re.search(r"\d", s)]
    title = words(sents[0][1], 8)
    if kind == "deck":
        slides = [{"type": "section", "heading": words(sents[0][1], 5), "subtitle": sents[0][1], "refs": [sents[0][0]]}]
        for r, s in num[:2]:
            m = re.search(r"[$]?\d[\d,.]*%?", s)
            slides.append({"type": "stat", "value": m.group(0).rstrip(".,"), "label": words(s, 8), "context": s, "refs": [r]})
        chunk = sents[1:13]
        for i in range(0, len(chunk), 3):
            grp = chunk[i:i + 3]
            if grp:
                slides.append({"type": "content", "heading": words(grp[0][1], 5), "refs": [grp[0][0]],
                               "bullets": [{"text": words(s, 13), "ref": r} for r, s in grp]})
        slides.append({"type": "closing", "heading": "What happens next", "text": sents[-1][1], "cta": "", "refs": [sents[-1][0]]})
        return {"title": title, "subtitle": "From your sources", "slides": slides[:11]}
    if kind == "visual":
        items = []
        for r, s in num:
            for m in re.finditer(r"[$]?\d[\d,]*\d|[$]?\d", s):
                items.append({"label": words(s, 3), "value": m.group(0), "ref": r})
                break
        return {"kicker": "From your sources", "headline": title, "dek": sents[0][1], "dek_refs": [sents[0][0]],
                "form": "bars" if len(items) >= 2 else "figures", "unit": "", "items": items[:5] or [{"label": "Sources", "value": "1", "ref": sents[0][0]}],
                "takeaway": sents[-1][1][:180], "takeaway_refs": [sents[-1][0]]}
    if kind == "audio":
        segs = [{"heading": words(s, 4), "text": " ".join(x for _r, x in sents[i:i + 3]), "refs": [r]}
                for i, (r, s) in enumerate(sents[:12]) if i % 3 == 0]
        return {"title": title, "segments": segs[:6] or [{"heading": "Summary", "text": sents[0][1], "refs": [sents[0][0]]}] * 2,
                "recap": " ".join(s for _r, s in sents[:2])}
    secs = []
    for i in range(0, min(len(sents), 12), 3):
        grp = sents[i:i + 3]
        secs.append({"heading": words(grp[0][1], 5), "body": " ".join(s for _r, s in grp), "refs": sorted({r for r, _s in grp})})
    stat = None
    if num:
        r, s = num[0]
        m = re.search(r"[$]?\d[\d,.]*%?", s)
        stat = {"value": m.group(0).rstrip(".,"), "label": words(s, 9), "ref": r}
    return {"title": title, "dek": sents[0][1], "dek_refs": [sents[0][0]], "stat": stat, "sections": secs[:4] or
            [{"heading": "Summary", "body": sents[0][1], "refs": [sents[0][0]]}],
            "points": [{"text": words(s, 14), "ref": r} for r, s in num[1:4]], "quote": None, "next": sents[-1][1]}

def guide_props(body):
    base = lambda name, why, layout, paper, ink, colors, hf, hw, bf: {"name": name, "why": why, "signature": why, "layout": layout,
        "paper": paper, "ink": ink, "colors": colors, "heading": {"family": hf, "weight": hw}, "body": {"family": bf}, "density": "medium",
        "voice": {"notes": "Warm, hopeful, plain. Talk about adult learners.", "delivery": "Warm and unhurried."}, "borrowed": "Your teal and gold.", "new": "A layout built for a board packet."}
    return {"proposals": [
        base("Harbor Board", "A teal banner and a big number up top, for board members who skim.", "banner", "#faf7f2", "#2b2b2b",
             [{"hex": "#0e5e6f", "role": "band"}, {"hex": "#f2a900", "role": "accent"}, {"hex": "#5b5651", "role": "rule"}], "Montserrat", 800, "Lora"),
        base("Lighthouse Letter", "A letter from the director, with a gold rule and a serif head.", "letter", "#ffffff", "#2b2b2b",
             [{"hex": "#0e5e6f", "role": "head"}, {"hex": "#f2a900", "role": "rule"}], "Lora", 700, "Lora"),
        base("Tide Table", "A margin rail of numbers beside the story, for funders who want the data.", "rail", "#f3f6f6", "#1d2b2e",
             [{"hex": "#0e5e6f", "role": "head"}, {"hex": "#c0392b", "role": "accent"}], "Montserrat", 700, "Lora"),
    ]}

class PersonaModel:
    async def acomplete_structured(self, **kw):
        purpose = kw.get("purpose", "")
        body = "".join(b.get("text", "") for b in kw.get("input", []) if isinstance(b, dict))
        schema = kw.get("json_schema")
        LOG.append(("call", purpose))
        ps = refs_of(body)
        from letterpress_plugin_package import content as C
        if purpose.endswith("summarize"):
            low = body[:300].lower()
            key = "council" if "work session" in low else "survey" if "survey" in low else "warming" if "warming" in low else None
            if key:
                summ, qs = WARM_SUMMARY[key]
                return R({"summary": summ, "questions": qs})
            sents = [x for x in _sentences(body) if "===" not in x][:2]
            return R({"summary": " ".join(sents)[:300] or "A short source.", "questions": ["What does it say first?", "What numbers does it give?", "What happens next?"]})
        if purpose.endswith("write") and which(body) == "warm":
            br = _by_ref(ps)
            if schema is C.DECK_SCHEMA:
                return R(DEMO.grounded_deck(br))
            if schema is C.AUDIO_SCHEMA:
                return R(DEMO.grounded_audio(br))
            if schema is C.VISUAL_SCHEMA:
                return R(DEMO.grounded_visual(br))
            return R(DEMO.grounded(br))
        if purpose.endswith("ask") and which(body) == "warm":
            q = body.split("QUESTION:", 1)[-1].strip()
            return R(warm_answer(q, ps))
        if purpose.endswith("write"):
            who = which(body)
            if who == "other":
                kind = "deck" if schema is C.DECK_SCHEMA else "audio" if schema is C.AUDIO_SCHEMA else "visual" if schema is C.VISUAL_SCHEMA else "onepager"
                return R(generic(kind, ps))
            if schema is C.DECK_SCHEMA:
                src = D_DECK if who == "denise" else D_DECK
                d = copy.deepcopy(src)
                for sl in d["slides"]:
                    sl["refs"] = [ref_for(ps, sl.pop("find"))] if "find" in sl else []
                    for k in ("bullets", "left_items", "right_items"):
                        for it in sl.get(k) or []:
                            it["ref"] = ref_for(ps, it.pop("find"))
                return R(d)
            if schema is C.AUDIO_SCHEMA:
                d = copy.deepcopy(A_AUDIO if who == "ana" else D_AUDIO)
                for s in d["segments"]:
                    s["refs"] = [ref_for(ps, s.pop("find"))]
                return R(d)
            d = copy.deepcopy(A_ONE if who == "ana" else D_ONE)
            d["dek_refs"] = [ref_for(ps, d.pop("dek_refs_find"))]
            if d.get("stat"):
                d["stat"]["ref"] = ref_for(ps, d["stat"].pop("find"))
            for s in d["sections"]:
                s["refs"] = [ref_for(ps, s.pop("find"))]
            for p in d["points"]:
                p["ref"] = ref_for(ps, p.pop("find"))
            if d.get("quote"):
                d["quote"]["ref"] = ref_for(ps, d["quote"].pop("find"))
            return R(d)
        if purpose.endswith("voice"):
            return R(json.loads(kw["input"][0]["text"]))
        if purpose.endswith("ask"):
            r = ps[0][0] if ps else "P1"
            return R({"answer": f"The sources answer this in passage [{r}].", "refs": [r], "followups": ["What did it cost?", "Who paid for it?", "What happens next?"]})
        if purpose.endswith("image_kit"):
            return R({"colors": [{"hex": "#0e5e6f", "role": "head"}, {"hex": "#f2a900", "role": "accent"}], "heading_font": "Montserrat",
                      "body_font": "Lora", "serif_headings": False, "layout": "banner", "is_logo": True, "name": "Harborlight"})
        if purpose.endswith("guide"):
            return R(guide_props(body))
        if purpose.endswith("site_voice"):
            return R({"notes": "Plain.", "delivery": "Steady.", "never": []})
        return R({})

import model_ai  # noqa: E402,F401  the AI lane's purposes (notebook_guide, outline, rewrite_title, element_edit, fix_it, graphic_options)
