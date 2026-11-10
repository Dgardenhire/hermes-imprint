"""A hand-written draft of the warming-center brief, grounded in samples/, with passage refs filled in at
run time by matching each claim to the passage that holds it. Used by the harness fixtures and the visual
checks, so screenshots show a realistic page. Every number below appears in the sample sources."""

NEUTRAL = {
    "title": "The warming center kept 412 people out of the cold",
    "dek": "Open 87 nights this winter, the center at Maple Street Recreation Hall recorded 2,914 overnight stays and turned no one away.",
    "stat": {"value": "2,914", "label": "overnight stays from December 1 to March 15", "find": "2,914 overnight stays"},
    "sections": [
        {"heading": "Who came through the door", "find": "118 were over the age of 60",
         "body": "Of the 412 guests, 118 were over the age of 60 and 37 were veterans. Staff connected 64 guests with permanent or transitional housing before the season ended, up from 29 the season before."},
        {"heading": "What it cost and who paid", "find": "The season cost $318,400",
         "body": "The season cost $318,400, or $109 per overnight stay. The city paid $205,000 from the general fund, a county grant covered $80,000, and private donations covered the remaining $33,400."},
        {"heading": "The hardest night", "find": "The busiest night was January 21, 2026",
         "body": "The busiest night was January 21, 2026, when 61 guests stayed during a stretch of five nights below 10 degrees. On an average night, 33 guests stayed."},
        {"heading": "What staff recommend next", "find": "Staff recommend opening on November 15",
         "body": "Staff recommend opening on November 15, setting the opening trigger at 35 degrees, and adding a second site on the east side. Staff estimate the second site would add $142,000 to the season's cost."},
    ],
    "points": [
        {"text": "91 percent of guests said they felt safe at the center.", "find": "91 percent said they felt safe"},
        {"text": "Volunteers gave 3,260 hours over the season.", "find": "Volunteers gave 3,260 hours"},
        {"text": "88 percent of volunteers plan to come back next season.", "find": "88 percent said they plan to volunteer again"},
    ],
    "quote": {"text": "Having a place to go when it drops below freezing is the difference between making it through the night and not.",
              "who": "A guest, in the March survey", "find": "Having a place to go when it drops below freezing"},
    "next": "The council takes up the second site and the earlier opening date at its April 8 budget work session.",
}


def grounded(by_ref):
    """NEUTRAL with each ``find`` replaced by the ref of the passage that contains it."""
    import copy
    doc = copy.deepcopy(NEUTRAL)

    def ref_for(phrase):
        for ref, info in by_ref.items():
            if phrase.lower() in info["text"].lower():
                return ref
        raise LookupError(phrase)
    doc["stat"]["ref"] = ref_for(doc["stat"].pop("find"))
    for s in doc["sections"]:
        s["refs"] = [ref_for(s.pop("find"))]
    for p in doc["points"]:
        p["ref"] = ref_for(p.pop("find"))
    doc["quote"]["ref"] = ref_for(doc["quote"].pop("find"))
    doc["dek_refs"] = [ref_for("open 87 nights") if any("open 87 nights" in i["text"].lower() for i in by_ref.values()) else doc["stat"]["ref"]]
    return doc


# A hand-written deck and audio brief from the same sources. Each "find" becomes the ref of the passage
# that holds it, so the checks pass for real.
DECK = {
    "title": "The warming center season",
    "subtitle": "For the April 8 budget work session",
    "slides": [
        {"type": "section", "heading": "Open every freezing night", "subtitle": "87 nights, December 1 to March 15", "find": "open 87 nights"},
        {"type": "stat", "value": "2,914", "label": "overnight stays by 412 guests", "context": "The busiest night was January 21, 2026, when 61 guests stayed.", "find": "2,914 overnight stays"},
        {"type": "content", "heading": "Who came through the door",
         "bullets": [{"text": "118 guests were over the age of 60", "find": "118 were over the age of 60"},
                     {"text": "37 guests were veterans", "find": "37 were veterans"},
                     {"text": "64 guests found permanent or transitional housing", "find": "Staff connected 64 guests"}]},
        {"type": "stat", "value": "$318,400", "label": "for the season, or $109 a stay", "context": "The city paid $205,000; a county grant covered $80,000.", "find": "The season cost $318,400"},
        {"type": "quote", "quote": "Having a place to go when it drops below freezing is the difference between making it through the night and not.",
         "who": "A guest, in the March survey", "find": "Having a place to go when it drops below freezing"},
        {"type": "comparison", "heading": "This season and next",
         "left_label": "This season", "left_items": [{"text": "Opened December 1", "find": "opened on the night of December 1"},
                                                     {"text": "Opened at 32 degrees", "find": "32 degrees or colder"},
                                                     {"text": "One site, on Maple Street", "find": "Maple Street Recreation Hall"}],
         "right_label": "Staff recommend", "right_items": [{"text": "Open November 15", "find": "Staff recommend opening on November 15"},
                                                           {"text": "Open at 35 degrees", "find": "35 degrees instead of 32"},
                                                           {"text": "Add an east side site for $142,000", "find": "add $142,000"}]},
        {"type": "exhibit", "heading": "Overnight staff were more than half of what the season cost",
         "unit": "Largest costs of the $318,400 season", "find": "The largest costs were overnight staff",
         "bars": [{"label": "Overnight staff", "value": "$171,900", "find": "overnight staff at $171,900"},
                  {"label": "Cots, bedding, laundry", "value": "$48,200", "find": "laundry at $48,200"},
                  {"label": "Meals", "value": "$41,700", "find": "meals at $41,700"}]},
        {"type": "timeline", "heading": "A season that ran from December to March", "find": "opened on the night of December 1",
         "steps": [{"when": "December 1", "text": "The center opens for the season", "find": "opened on the night of December 1"},
                   {"when": "January 21", "text": "61 guests on the busiest night", "find": "The busiest night was January 21, 2026"},
                   {"when": "March 15", "text": "The center closes after 87 nights", "find": "closed for the season on March 15"},
                   {"when": "November 15", "text": "Staff recommend opening here next year", "find": "Staff recommend opening on November 15"}]},
        {"type": "image", "heading": "A second site, east of the river", "caption": "Guests would no longer have to cross the river at night.",
         "prompt": "A quiet city street at dusk in winter, a lit community hall entrance, light snow", "find": "do not have to cross the river at night"},
        {"type": "closing", "heading": "The decision", "text": "A second site and an earlier opening date for next winter.",
         "cta": "Decide at the April 8 budget work session", "find": "Staff recommend opening on November 15"},
    ],
}

AUDIO = {
    "title": "The warming center season in three minutes",
    "segments": [
        {"heading": "The short version", "find": "open 87 nights",
         "text": "The warming center at the Maple Street Recreation Hall was open 87 nights this winter. It opened on December 1 and closed on March 15. It never turned anyone away."},
        {"heading": "Who came", "find": "2,914 overnight stays",
         "text": "Over the season the center recorded 2,914 overnight stays by 412 different guests. The busiest night was January 21, 2026, when 61 guests stayed. On an average night, 33 guests stayed."},
        {"heading": "Who it served", "find": "118 were over the age of 60",
         "text": "Of the 412 guests, 118 were over the age of 60, and 37 were veterans. Before the season ended, staff connected 64 guests with permanent or transitional housing. The season before, that number was 29."},
        {"heading": "What it cost", "find": "The season cost $318,400",
         "text": "The season cost $318,400. That is $109 for each overnight stay. The largest cost was overnight staff, at $171,900. The city paid $205,000 from the general fund. A county grant covered $80,000, and private donations covered the remaining $33,400."},
        {"heading": "Who helped", "find": "Volunteers gave 3,260 hours",
         "text": "Volunteers gave 3,260 hours over the season, mostly in the evening meal and morning shifts. The Cedar Hollow Faith Alliance and two neighborhood associations organized most of the schedule."},
        {"heading": "What staff recommend", "find": "Staff recommend opening on November 15",
         "text": "Staff recommend opening on November 15 instead of December 1. They recommend opening when the forecast low is 35 degrees, not 32. And they recommend a second site on the east side of the city, so guests do not have to cross the river at night. Staff estimate the second site would add $142,000 to the season's cost."},
    ],
    "recap": "Three things to remember. The center was open 87 nights. It recorded 2,914 overnight stays. And the council decides on a second site and an earlier opening on April 8.",
}


def grounded_deck(by_ref):
    import copy
    doc = copy.deepcopy(DECK)

    def ref_for(phrase):
        for ref, info in by_ref.items():
            if phrase.lower() in info["text"].lower():
                return ref
        raise LookupError(phrase)
    for sl in doc["slides"]:
        sl["refs"] = [ref_for(sl.pop("find"))] if "find" in sl else []
        for lst in ("bullets", "left_items", "right_items", "bars", "steps"):
            for it in sl.get(lst) or []:
                it["ref"] = ref_for(it.pop("find"))
    return doc


# One graphic from the same sources: who paid for the season.
VISUAL = {
    "kicker": "Winter shelter",
    "headline": "The city's general fund carried most of the $318,400 season",
    "dek": "Who paid for the Cedar Hollow warming center, December 1, 2025 to March 15, 2026.",
    "dek_find": "The season cost $318,400",
    "form": "bars",
    "unit": "Funding by source",
    "items": [{"label": "City general fund", "value": "$205,000", "find": "The city paid $205,000"},
              {"label": "County grant", "value": "$80,000", "find": "A county grant covered $80,000"},
              {"label": "Private donations", "value": "$33,400", "find": "private donations covered the remaining $33,400"}],
    "steps": [],
    "takeaway": "A second site would add $142,000 to the cost, so the funding mix is the decision.",
    "take_find": "add $142,000",
}


def grounded_visual(by_ref):
    import copy
    doc = copy.deepcopy(VISUAL)

    def ref_for(phrase):
        for ref, info in by_ref.items():
            if phrase.lower() in info["text"].lower():
                return ref
        raise LookupError(phrase)
    doc["dek_refs"] = [ref_for(doc.pop("dek_find"))]
    doc["takeaway_refs"] = [ref_for(doc.pop("take_find"))]
    for it in doc["items"]:
        it["ref"] = ref_for(it.pop("find"))
    return doc


def grounded_audio(by_ref):
    import copy
    doc = copy.deepcopy(AUDIO)

    def ref_for(phrase):
        for ref, info in by_ref.items():
            if phrase.lower() in info["text"].lower():
                return ref
        raise LookupError(phrase)
    for seg in doc["segments"]:
        seg["refs"] = [ref_for(seg.pop("find"))]
    return doc
