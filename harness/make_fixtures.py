"""Write harness/fixtures.json: real answers from Imprint's backend, made with a scripted stand-in model
(harness/demo_content.py) so the pane can be rendered and screenshotted without Hermes.

    /usr/bin/python3 harness/make_fixtures.py
"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["IMPRINT_DATA_DIR"] = tempfile.mkdtemp(prefix="imprint-fixtures-")
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "harness"))
from _load import service, jobs, kits, store, Result, run, api, content, runtime, imports  # noqa: E402
import demo_content  # noqa: E402

# How each kit's voice pass rewords the draft. Numbers and refs never change; keep_facts enforces it.
VOICE = {
    "Plain Notice": {"title": "The warming center kept 412 people out of the cold",
                     "dek": "Open 87 nights this winter, the center at Maple Street Recreation Hall recorded 2,914 overnight stays and turned no one away.",
                     "headings": ["Who came", "What it cost", "The coldest night", "What changes next winter"],
                     "next": "The council decides on a second site and an earlier start on April 8."},
    "Docket": {"title": "Season results: 412 guests kept out of the cold",
               "dek": "The center was open 87 nights and recorded 2,914 overnight stays; staff ask the council to decide on a second site and an earlier opening.",
               "headings": ["Guests served", "Cost and funding", "Peak demand", "Staff recommendations"],
               "next": "Decision requested at the April 8 budget work session on the east side site and the earlier opening date."},
}


DECK_VOICE = {
    "Plain Notice": {"title": "One winter at the warming center", "subtitle": "What happened and what comes next, for April 8"},
    "Docket": {"title": "Warming center: season results and decisions", "subtitle": "Staff report to the April 8 budget work session"},
}
AUDIO_VOICE = {
    "Plain Notice": "The warming center, in three minutes",
    "Docket": "Season results: the warming center",
}


class Scripted:
    def __init__(self, doc, deck=None, audio=None):
        self.doc, self.deck, self.audio = doc, deck, audio

    async def acomplete_structured(self, **kw):
        p = kw.get("purpose", "")
        body = kw["input"][0]["text"]
        schema = kw.get("json_schema")
        if p.endswith("write"):
            if schema is content.DECK_SCHEMA:
                return Result(parsed=self.deck)
            if schema is content.AUDIO_SCHEMA:
                return Result(parsed=self.audio)
            return Result(parsed=self.doc)
        if p.endswith("voice") and schema is not content.ONEPAGER_SCHEMA:
            d = json.loads(body)
            name = re.search(r"Voice for (.+?):", kw["instructions"]).group(1)
            if "slides" in d and name in DECK_VOICE:
                d.update(DECK_VOICE[name])
            if "segments" in d and name in AUDIO_VOICE:
                d["title"] = AUDIO_VOICE[name]
            return Result(parsed=d)
        if p.endswith("voice"):
            d = json.loads(body)
            name = re.search(r"Voice for (.+?):", kw["instructions"]).group(1)
            v = VOICE.get(name)
            if v:
                d["title"], d["dek"], d["next"] = v["title"], v["dek"], v["next"]
                for s, hd in zip(d["sections"], v["headings"]):
                    s["heading"] = hd
            return Result(parsed=d)
        if p.endswith("ask"):
            refs = re.findall(r"\[(P\d+)\] \([^)]*\) ([^\n]+)", body)
            cost = next(r for r, t in refs if "318,400" in t)
            fund = next(r for r, t in refs if "205,000" in t)
            return Result(parsed={"answer": f"The season cost $318,400, or $109 per overnight stay. [{cost}] The city paid $205,000 from the general fund, the county grant covered $80,000, and donations covered $33,400. [{fund}]",
                                  "refs": [cost, fund], "followups": ["Is the county grant renewing next year?", "What would the east side site cost?", "How many guests found housing?"]})
        return Result(parsed={})


def tone_wav(seconds=2.0, rate=16000):
    """A short, quiet two-note chime as WAV, so the harness player has something real to load."""
    import io
    import math
    import struct
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(int(seconds * rate)):
            t = i / rate
            f = 523.25 if t < seconds / 2 else 659.25
            amp = 0.12 * math.exp(-3 * (t % (seconds / 2)))
            frames += struct.pack("<h", int(32767 * amp * math.sin(2 * math.pi * f * t)))
        w.writeframes(bytes(frames))
    return buf.getvalue()


def main():
    srcs = [service.read_file(n, (ROOT / "samples" / n).read_bytes())
            for n in ("warming-center-report.md", "council-work-session.vtt", "guest-and-volunteer-survey.txt")]
    ids = [s["id"] for s in srcs]
    _s, _b, by_ref = service.passages_for(ids)
    service.LLM = Scripted(demo_content.grounded(by_ref), demo_content.grounded_deck(by_ref), demo_content.grounded_audio(by_ref))
    j = jobs.start("make", "fx", {"kind": "onepager", "source_ids": ids, "kit_ids": ["plain-notice", "docket"],
                                  "brief": "A one-page brief for the council on the warming center season"}, wait=True)
    oid = jobs.get(j["id"])["result"]["output_id"]
    clean = service.output_view(oid)
    # A flagged version: one number the sources don't have, for the "check catches something" shot.
    service.edit(oid, "points.1.text", "Volunteers gave 3,600 hours over the season.")
    flagged = service.output_view(oid)
    service.edit(oid, "points.1.text", "Volunteers gave 3,260 hours over the season.")
    a = jobs.start("ask", "fxa", {"question": "What did the season cost, and who paid?", "source_ids": ids}, wait=True)
    fonts = {}
    for p in clean["proofs"]:
        for k in p["fonts"]:
            f = service.font_file(k); f.pop("data"); fonts[k] = f
    for k in ("night-desk", "studio-italic", "almanac", "payments-violet", "midnight-indigo", "poster-block", "parchment-ink"):
        jobs.start("voice", f"fx{k}", {"output_id": oid, "kit_id": k, "slot": 1}, wait=True)
    extra = {k: service.proof(oid, k) for k in ("night-desk", "studio-italic", "almanac", "payments-violet", "midnight-indigo", "poster-block", "parchment-ink")}
    for p in extra.values():
        for k in p["fonts"]:
            f = service.font_file(k); f.pop("data"); fonts[k] = f
    passages = {r: service.passage(r) for r in by_ref}
    page = (ROOT / "tests" / "test_site_guide_layout.py").read_text().split('PAGE = """', 1)[1].split('"""', 1)[0]
    site = service._draft_view(__import__("_load").sitekit.draft_from(page, [], "https://riverbend.example", service.nice_date()))
    site["draft"]["voice"]["notes"] = "Warm and neighborly. Lead with what an artist or a visitor can do this month. Use we for the council and you for the reader. Short paragraphs."
    # The deck and the audio brief, from the same sources and kits.
    dj = jobs.start("make", "fxd", {"kind": "deck", "source_ids": ids, "kit_ids": ["plain-notice", "docket"],
                                    "brief": "A short deck for the April 8 budget work session"}, wait=True)
    deck = service.output_view(jobs.get(dj["id"])["result"]["output_id"])
    wav = tone_wav()

    def voice(tool, args, timeout=180.0):
        p = Path(args["output_path"]).with_suffix(".wav")
        p.write_bytes(wav)
        return {"success": True, "file_path": str(p)}
    runtime.dispatch = voice
    aj = jobs.start("make", "fxa2", {"kind": "audio", "source_ids": ids, "kit_ids": ["plain-notice", "docket"],
                                     "brief": "A three-minute spoken brief for council members"}, wait=True)
    audio = service.output_view(jobs.get(aj["id"])["result"]["output_id"])
    import base64
    audio_file = {"mime": "audio/wav", "data": base64.b64encode(wav).decode("ascii")}
    for o in (deck, audio):
        for p in o["proofs"]:
            for k in p["fonts"]:
                f = service.font_file(k); f.pop("data"); fonts[k] = f
    # Import drafts: an invented Open Design style package, and a logo read by the model.
    od = {"manifest.json": json.dumps({"schemaVersion": "od-design-system-project/v1", "id": "harbor-press", "name": "Harbor Press",
                                       "category": "Editorial & Print"}),
          "tokens.css": ":root{--bg:#f7f3ea;--fg:#1d1b18;--muted:#6b6259;--border:#d9cfc0;--surface-warm:#ede3d1;--accent:#8a3b12;"
                        "--accent-on:#ffffff;--success:#3f7d4a;--warn:#b7791f;--accent-hover:color-mix(in oklab, var(--accent), black 8%);"
                        "--font-display:'Libre Caslon Display', Georgia, serif;--font-body:'Crimson Pro', Georgia, serif;"
                        "--text-base:17px;--text-2xl:40px;--space-4:16px;--radius-md:6px}"}
    draft = service.import_read("open-design", files=od)
    imports.update(draft["draft_id"], {"name": "Harbor Press Notes"})
    draft = service.import_view(draft["draft_id"])
    # Two kits of the person's own, so the library leads with them.
    kits.save_new({"name": "Eastside Tenants Union", "org": "Eastside Tenants Union", "paper": "#fbf8f2", "ink": "#1c1a17", "layout": "bulletin",
                   "colors": [{"hex": "#7a1f2b", "role": "head", "name": "Oxblood"}, {"hex": "#7a1f2b", "role": "accent", "name": "Oxblood"},
                              {"hex": "#f2c14e", "role": "fill", "name": "Marigold"}, {"hex": "#d8cfc2", "role": "rule", "name": "Card"}],
                   "type": {"heading": {"family": "Barlow Condensed", "stack": "Barlow Condensed, Arial Narrow, sans-serif", "weight": 700, "case": "upper"},
                            "body": {"family": "Barlow", "stack": "Barlow, Helvetica, Arial, sans-serif", "weight": 400}},
                   "subject": "Notices and updates for renters in our buildings, read on a phone before a hearing.",
                   "voice": {"notes": "Plain and direct. Speak to renters as you.", "delivery": "Steady and warm."}})
    kits.save_new({"name": "Riverbend Arts Council", "paper": "#ffffff", "ink": "#15212b", "layout": "headline",
                   "colors": [{"hex": "#0f5c6e", "role": "head", "name": "River"}, {"hex": "#d94f2b", "role": "accent", "name": "Kiln"},
                              {"hex": "#e8f1f2", "role": "fill", "name": "Mist"}, {"hex": "#b9cdd1", "role": "rule", "name": "Reed"}],
                   "type": {"heading": {"family": "Instrument Serif", "stack": "Instrument Serif, Georgia, serif", "weight": 400, "style": "italic"},
                            "body": {"family": "Inter", "stack": "Inter, Helvetica, Arial, sans-serif", "weight": 400}},
                   "subject": "What artists and visitors can do this month, from the city's arts council.",
                   "voice": {"notes": "Warm and neighborly.", "delivery": "Warm."}})
    data = {"state": service.state(), "deck": deck, "audio": audio, "audio_file": audio_file, "draft": draft, "output": clean, "flagged": flagged, "extra": extra, "chats": service.chats(),
            "fonts": fonts, "passages": passages, "kit_uswds": service.kit_view("uswds"), "kit_docket": service.kit_view("docket"),
            "site": site}
    data["state"]["outputs"] = service.list_outputs()
    out = ROOT / "harness" / "fixtures.json"
    out.write_text(json.dumps(data))
    print(out, round(out.stat().st_size / 1024), "KB")


if __name__ == "__main__":
    main()
