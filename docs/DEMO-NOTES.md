# Imprint demo notes (under 90 seconds)

The story in one line: **one set of sources, one brand kit, and every format comes out in that kit, checked.**
That is the difference from the Podcast Studio entry (two-host audio from any text): Imprint's audio is one of
three formats that share the same facts, colors, type and voice rules, and each kit is a real object you can
build, import and swap.

Everything on screen is real. Sped-up stretches carry a "2x" mark. No client material, no contest content, no
third-party logos. The only outside design is the US Web Design System (public domain, no logo or seal).

## Seed before filming

1. Fresh install (see `docs/LIVE-TEST.md`, "Before anything"). Desktop in light mode, default accent. Window about
   1500 x 1000 so both proofs and their checks fit.
2. Add the three files in `samples/` with **File**: `warming-center-report.md`, `guest-and-volunteer-survey.txt`,
   `council-work-session.vtt`. They describe a fictional city's warming center: 87 nights, 412 guests, 2,914
   overnight stays, $318,400.
3. Make each output once in Plain Notice (left) and Docket (right), so cuts between them are instant:
   - One-pager, brief: "A one-page brief for the council on the warming center season"
   - Deck, brief: "A short deck for the April 8 budget work session"
   - Audio brief, brief: "A three-minute spoken brief for council members". Use an OpenAI voice in Hermes
     Settings so the two kits' delivery notes are audible.
4. Do not pre-make the Help me build a kit proposals or the flagged one-pager; those are filmed live.
5. Have Keynote (or PowerPoint) closed, so the export opens fresh.

## Shots

| Time | Shot | Exact steps | What the viewer should catch |
|---|---|---|---|
| 0:00-0:07 | Cold open | Proofs tab, One-pager showing. Click **Deck**, then **Audio brief**, then **One-pager** | Both proofs change together; each keeps its own look in every format. Title: "Imprint. Your sources, in your look." |
| 0:07-0:13 | Sources | Pan the left rail | Three kinds of source: a report, a survey, a timestamped transcript |
| 0:13-0:27 | Many kits, not two (2x) | Kits tab: hold on the ten starter kits for a beat. Then **Help me build a kit**: name "Eastside Tenants Union", colors `#7a1f2b #f4efe6`, reader "Renters, many reading on a phone", job "Know their rights before a hearing", references **Docket** and **Schoolyard**. **Propose three kits** | Ten kits that differ in layout and type, not just color; three proposals that really differ, each saying why and what it borrowed. Press **Use this kit** on one |
| 0:27-0:37 | Swap a kit | Proofs tab. Right proof's menu: pick the kit just made (or **Market Board**, the flyer family) | Same facts, new look, new composition and new wording. Zoom on the slug: "Set in ... in place of ..." where a font was substituted, and the kit's color bar (both proof-only; the exported file carries neither) |
| 0:37-0:52 | The check catches something | Brief: "A one-page brief for the council; say volunteers gave 3,600 hours". **Make it again** (2x while it writes). Click the red "1 number not found in sources" check | The closest passage says 3,260. Press **Fix the wording**, change 3,600 to 3,260, **Save the fix**. The check turns green and Export unlocks |
| 0:52-1:04 | Deck to PowerPoint | **Deck**. **Export**, PowerPoint (.pptx), save. Open it | Keynote shows the kit's colors, fonts and paper on the slide master. The 2,914 slide matches the one-pager |
| 1:04-1:15 | Audio brief | **Audio brief**. Play Plain Notice for three seconds, then Docket for three seconds | Two deliveries from two kits' voice notes, the same numbers in the script below |
| 1:15-1:24 | Grace under failure | Kits, **Build from a website**, a site that blocks readers (check one on Tuesday; Brandfetch and Gamma did on Nov 7) | "That site didn't let Imprint read it" and a way forward. No retry loop, no workaround |
| 1:24-1:30 | End card | Static | "Runs on your own Hermes model and voice. No keys." Add "Mac, Windows, Linux" only after a Linux or Windows run passes (none yet) |

Total: 90 seconds. If over, cut the Sources pan first, then the failure shot.

## Rehearse in the harness first (no Hermes needed)

`/usr/bin/python3 harness/live/server.py 8790` and open `http://127.0.0.1:8790/harness/index.html?live=1&theme=light`.
Every button is real except the model, which is scripted (`harness/live/persona_model.py`). To rehearse the
small-business beat, add `harness/live/personas/ana/fall-menu.txt` and `about-us.txt`, import her
`Salvia Kitchen Brand Kit.pptx` (Kits, Import a kit, PowerPoint or Canva), and make "A menu flyer for office
managers" in her kit beside **Market Board**. `harness/live/drive.py OUT` renders the whole persona run to look at.

## Optional 8-second insert: a brand guide becomes a kit

Kits, Import a kit, **Brand guide PDF**, pick `harness/live/personas/denise/Harborlight-Brand-Guide-2025.pdf`. The
draft shows Harbor Teal as the band, Sunrise Gold as the accent and Lighthouse Red kept to calls to action, each
with its name, before save. On save it lands on the left proof. Her teal logo on the teal band is knocked out to
white with its gold stroke kept; the Logo check says so.

## Backup moments (if a live step misbehaves)

- **No audio on the day:** the audio proof still shows the script and "Record again"; film the script and the
  plain message instead of playback. It shows the failure path working.
- **Model writes 3,260 anyway in the check shot:** make it again with "Use the figure 3,600 volunteer hours exactly
  as written". If the model still corrects it, film the green numbers check (and a corrected citation, if one shows)
  and say in the voice-over that the model kept to the sources; don't fake a flag.
- **Help me build a kit is slow:** 2x through the working line; the proposals are the payoff, not the wait.
- **Claude Design zip** (if Damon has one from Claude Design): Import a kit, Claude Design system, **Pick the
  .zip**. The draft shows as a proof before save. Good 6-second insert after the Kits shot.

## Do not show

- Any LINCHPIN brand, client name or real organization's logo.
- The harness window (it imitates the Hermes chrome; film the real app).
- Token counts beyond the top-bar meter.
