# Imprint status

A dated build log. Current facts (Hermes floor `>=0.22.6`, tests, fixes) are in `CHANGELOG.md` and `README.md`.

Updated Nov 8, 2026, stage 7 (the notebook). Branch `notebook` in the worktree `hermes-imprint-wt-notebook`, not
pushed, not merged. Next stage starts here.

**Tests: 336**, all passing (`cd tests && /usr/bin/python3 -m unittest discover -s .`, about 18 s; was 304).
`test_imports.Css.test_css_pathological_input_is_fast` is timing-bound and fails only under heavy load (load
average 26 to 43 during this stage), passing on rerun. Desktop bundle rebuilt with `node
~/products/hermes-ui-kit/scripts/build.mjs .` (the unchanged rebuild matched main before any edit; `--check` up to
date after). gitleaks clean before each commit.

## Stage 7: what changed (Damon, Nov 8: "the most mediocre and disappointing ... templates ... elementary ... no
three-tiered notebook")

1. **Three-pane notebook** replaces the Proofs tab (desktop/src/plugin.js, `NotebookTab`). Sources pane: add file,
   drop files, link (through `web_extract`, safe reader fallback), paste; each source shows kind, size, a model-written
   two-sentence summary and three questions (`summarize` job, started after every read); tick to include; title opens
   the source reader at a passage. Chat pane: answers only from ticked sources, numbered citations that open the
   cited passage in the reader, suggested questions before the first ask, pin as note, copy, follow-ups on the last
   answer, clear. Studio pane: kit chooser (studio kits, yours, earlier starters, Import, Build your own, All kits),
   four outputs with a brief, "build around N notes", the opt-in picture slide; progress shows each real step with
   its time (`jobs.steps`); "Made in this notebook"; Notes. Viewer: an output large over chat and Studio, checks,
   kit swap, export, delete.
2. **Five studio kits** (`starter_kits.STUDIO`): Counsel (exhibit), Chart Room (broadsheet), Stage (stage), Folio
   (folio), Meridian (grid). Each: a type pairing plus a label face, contrast-checked palette, its deck system.
   Earlier starters keep working, shown under "Earlier starters".
3. **Scene engine** (`scene.py`) and **design systems** (`systems.py`): measured, positioned scenes drawn the same in
   the pane (nodes in percent and container units), PDF, PowerPoint (titles in title placeholders, bullets native),
   PNG (Pillow) and SVG (fonts embedded). Slide types: title, section, content, stat, quote, comparison, exhibit,
   timeline, image, closing, sources. Text shrinks to a floor (30 pt reading, 20 pt chart labels, 14 pt source lines)
   and a "runs long" check names any slide that still overflows. The old deck renderer and its CSS are gone.
4. **Graphic output** (`render_graphic.py`, `content.VISUAL_SCHEMA`): one 4:5 graphic, PNG/SVG/PDF, traced and checked.
5. **Picture slides**: opt-in `image_generate`, words-only prompt, read back only from `<HERMES_HOME>/cache/`, re-encoded.
6. **Notes** (`notes` table): pinned answers or typed lines; they go into the make's brief.
7. **Fix**: `ingest.corpus` underestimated each passage's label and dropped a source's last passage (the warming
   center report lost its recommendations). Tested.
8. Fonts added: Source Serif 4 400/600, Source Sans 3 400/600, DM Serif Display (local OFL copies, hashes pinned).

Screens (looked at, light and dark): `docs/shots/notebook-*`, `viewer-*`, `kits-studio-*`, `kit-bench-*`,
`storage-light`, from live mode (`sh harness/shoot.sh`). Old Proofs-tab shots removed. Gallery, before/after and the
three direction thumbnails: `~/Desktop/claude-test/.planning/hackathon-2026-11/imprint/notebook-v2/`.

## Left, ranked (stage 7)

1. **Damon looks at it in Hermes** (Tuesday live test list in `docs/LIVE-TEST.md` still applies), plus: `web_extract`
   and `image_generate` from a job thread (the digest marks `dispatch_tool` from a worker thread as unverified),
   whether his image provider's paths land under `<HERMES_HOME>/cache/`, and the deck opened in PowerPoint and
   Keynote (only Quick Look's first slide was looked at; without the kit's fonts installed it falls back to Times).
2. **One-pagers still use the stage 6 page families**, now in the studio kits' type and color. They are good but not
   at the decks' level; a scene-based one-pager per system is the next design job.
3. **Two-voice audio** is not built: Hermes's `text_to_speech` gives plugins one voice (ElevenLabs `voice_id`
   aside). The audio brief stays one narrator.
4. The fixture harness (`harness/index.html` without `live=1`) still serves Kits screens only; the notebook is shot
   in live mode. `harness/make_fixtures.py` was not regenerated.
5. Merge `notebook` into `main` and re-pin the catalog entry after Damon's go-ahead; no push without it.
6. Earlier stages' items below are unchanged unless listed here.

## Stage 6 record

Updated Nov 8, stage 6 (the persona fixes). 291 tests then.

### Stage 6: what changed (from `.planning/hackathon-2026-11/personas/imprint.md`)

1. **Exports are safe to send.** The HTML export is the finished page, not the proof: no per-number trace marks
   (no more "$16 ²" or "555²-0142²"), field-level footnotes that link to the numbered source list, a no-break
   space before any mark that follows a figure, one column on a phone (`render_html.EXPORT_CSS`). The colophon
   and the color bar are proof furniture: they print on the proof PDF and in the pane only, never on the finished
   PDF, deck PDF, script or HTML. A kit that lists no sources (a menu, a customer flyer) gets no marks on any
   export; the proof keeps every trace. Phone numbers are one figure (`content.PHONE`). Phone width measured
   at 390px with mobile emulation on all four persona HTML exports: 0px overflow. Note: the persona's clipped
   phone shot did not reproduce in Chromium at a true 390px mobile viewport (likely a headless window minimum);
   the layout was hardened anyway (grids to one column, `overflow-wrap:anywhere`, images capped).
2. **The invisible logo.** `logos.py` measures the share of the mark that stands out (1.8:1) from the ground it
   sits on, band and paper, for every page type. Too little, and it uses the kit's **reversed logo** (new
   upload on the bench, `logo-reversed.<png|svg|jpg>`, held to that one name) or knocks the mark out: the parts
   that vanish go to the band's text color, the parts that already read (Denise's gold stroke) keep theirs. One-
   pager masthead, HTML, PDF, deck PDF and PowerPoint (band slides hide the master's logo and carry the knocked-
   out one). A Logo check says what it did. The PDF masthead gap after the logo is gone.
3. **The checker stops crying wolf.** Quotes compare words only (trailing punctuation, curly quotes and case
   never decide), so Denise's "this spring." matches "this spring," and its citation is corrected (the PDF now
   cites the right source). Spelled-out numbers in sources match digits ("Sixty-eight percent" = 68%). Numbers
   in the person's own brief count as known ("90-second"). The closest passage is searched across every source
   and shown as its one sentence. "Not found" items come first; corrected citations fold into one line; numbers
   show as written ("1,148").
4. **Kit import quality.** Brand guide PDFs are a route (first in the list): codes, the words beside them, the
   fonts the guide names with its own fallbacks, the guide's name; drawn swatches when there are no codes; a
   refusal that says "paste the color page". Pasted codes keep their names and labels: "Primary. Headlines, the
   logo, bands." becomes the heading and band color; "Calls to action only" becomes an accent, never the band;
   no color appears twice. PowerPoint/Canva ranks by use on the slides: paper from the slide background, ink from
   the most text, heading color and font from the biggest type, fills by area; Office's default theme colors that
   no slide uses are skipped and listed ("Add it back" puts any skipped color back in one click). Missing fonts
   fall to the nearest bundled open face by kind (Playfair to Libre Caslon Display, Poppins to Inter, Lora to
   Crimson Pro). Persona results: Ana's cream, sage, terracotta and saffron with Playfair and Poppins; Denise's
   teal band with gold accent and red as an accent only.
5. **Outputs that don't look templated.** Two new layout families with their own compositions: **Flyer or
   menu** (centered head, a stamped price, items with dotted leaders and prices, the call to action on the band
   at the foot) and **Report** (key figures in a row on rules, side-heads beside each section, a pulled quote).
   Starters **Market Board** and **Board Report**; the shelf shows one starter per family (Banner, Headline,
   Letter, Flyer, Report). The one-pager can carry items with prices; a menu or flyer brief asks the model for
   them, and prices are checked like any number. No empty bottom third: the PDF grows a short draft's type up to
   1.42x and pins the foot to the bottom; the pane does the same on the letter-shaped sheet.
6. **The smaller list.** A starter kit's required lines are opt-in per output (Docket no longer adds "Not legal
   advice." to a board memo); your own kit's lines print unless you leave them off; the Required lines check holds
   the switch. Deck stat number no longer collides with its label. PowerPoint slides sit on real layouts with
   titles in title placeholders, native bullets and layouts widened to 16:9. A kit just saved or imported goes onto
   the left proof with a toast. Also: one brief per format, the length check reads the length asked for, a typed
   family that isn't installed reads "(not on this computer)", a Claude Design zip says ".zip".
7. **Live mode for the harness.** `harness/live/server.py` serves the real routes on 127.0.0.1 with a temp data
   folder; open `/harness/index.html?live=1`. `persona_model.py` scripts the three personas and writes a plain
   cited draft from any other sources. `harness/live/drive.py OUT` replays the persona run and writes every
   export, PDF pages as PNG, the PowerPoint's first slide (Quick Look), HTML at 390px and the pane in light and
   dark. Persona input files: `harness/live/personas/`.

Screens added to `docs/shots/` (looked at, each): `live-onepager-{light,dark}`, `live-menu-{light,dark}`,
`live-deck-dark`, `live-kits-light`, `export-harborlight-pdf`, `export-board-report-pdf`,
`export-salvia-menu-pdf`, `export-market-board-pdf`, `export-salvia-menu-html-phone`,
`export-harborlight-html-phone`, `export-harborlight-deck-pdf` (all ten slides), `export-harborlight-deck-pptx`.
`harness/fixtures.json` regenerated; the fixture harness renders with no page errors.

## Left, ranked (stage 6)

1. **Tuesday live test** (`docs/LIVE-TEST.md`), now also: open an exported PPTX in PowerPoint and check outline
   view, Designer and the accessibility checker see titles (python-pptx structure is tested; only Quick Look's
   first-slide render was looked at, Keynote export via AppleScript did not run here); open an HTML export on a
   real phone; a real model on a menu brief (does it fill `items`?).
2. Not done from the persona list: Studio Italic's descender on the rule and its bullets outside the grid (S3);
   Help me build a kit thumbnails and your own kits as references (S3); a brand guide added as a *source* does
   not yet offer "make a kit from its colors" (the Kits route reads it); kit names from CSS and DTCG still use the
   file stem.
3. Deck content slides still leave room below three bullets at 28pt; the comparison slide's 20pt items are small.
4. Stage 5 items 3 to 6 below are unchanged (catalog re-pin, outside security sign-off, platforms).

## Stage 5: what changed

1. **Hover a number, see its source (the trace card).** `checks.trace_table` turns the grounding pass into one
   trace per number: `exact` (the number as written is in the passage), `close` (same value written another way,
   "91%" against "91 percent"), `missing` (with the closest line) or `kept`. `layout.mark_traces` wraps each
   checked number in the proof tree as a focusable span with its own source number after it; a field's own
   citation drops sources its numbers already show, so marks don't double. Days and years in written dates are
   traced but get no mark (it would read as part of the date). Dates, slide numbers, source lists and the org
   line are never touched. The pane shows a 262px card on hover (150 ms) or focus: "Exact match in source 1",
   the source sentence with the number marked, the numbered square and "Warming center report, page 2". Escape
   closes, Enter or Space reopens, the card follows a focused number when the sheet scrolls, `aria-describedby`
   points at it. Works on one-pagers, decks and audio scripts. The HTML export is the proof, so it carries the
   per-number marks (no controls); the PDF and PowerPoint keep field-level citations. Tests:
   `tests/test_traces.py` (12). Screens: `docs/shots/trace-*.png` (light, dark, deck, missing, green accent).
2. **Open Design starters, renamed (Damon's correction 1).** Four looks join the starters because each adds range
   the originals lack: Payments Violet (light violet-on-white headline page), Midnight Indigo (dark margin-rail
   page), Poster Block (black-on-unbleached bulletin with highlighter yellow), Parchment Ink (ink-blue serif on
   parchment). Neutral names, no logo or mark, no company name anywhere (a test greps the starters and NOTICE).
   Licensed typefaces are never asked for: a kit face marked `stands_in` uses a bundled OFL font, the colophon
   says "Inter (an open font standing in for a licensed one)" and the Fonts check says so in good tone. The
   licensed face is not named, because some carry the company's name. `NOTICE` holds the Open Design Apache-2.0
   attribution and license text (copied from a local Apache-2.0 file) and the MIT text for the three upstreams
   the Open Design catalog credits. Unverified: each upstream's exact copyright line (NOTICE points to the repos).
3. **Kits tab tamed (UPGRADE-REVIEW Imprint item 1).** Your kits lead at full width. Starters are a shelf of five
   proofs (crop marks, the kit's own fonts on your headline, its subject line, the color bar); "All 14 starter
   kits" opens the rest as a compact list with swatch strips. Filter chips and cover cards are gone. Proof pages
   have a strong 1px frame so dark kits hold on the dark table (item 4). Not done from the review: dropping the
   top Sources tab (item 2), because that tab also holds outputs, the token meter and Forget everything.
4. **Imports on Mac, Windows and Linux.** Every MUST route (manual build with logo and font uploads, paste, CSS,
   website reader, Open Design folder, Claude Design zip and folder, PowerPoint/Canva, DTCG) is tested with its
   Windows and Linux shapes in `tests/test_platforms.py` (16 tests). Fixed: upload names now keep only the file
   name whatever separators arrive (`C:\...`, `\\server\...`, `/home/...`); a zip written on Windows with
   backslash names was refused on a Mac or Linux backend but opened on Windows (Python converts only on a Windows
   host) and now opens the same everywhere, with climbing and absolute paths still refused; Open Design and Claude
   Design folders match names without case (a Linux package with `Tokens.css` or `Fonts/` read nothing before),
   and the pane lists the folder and reads each file by the host's own path; a byte order mark no longer breaks a
   Windows-saved token file. Keynote is a route labeled "Keynote theme (Mac only)" through Keynote's PowerPoint
   export; `.pages` and `.numbers` say what to do instead.
5. **Fonts, no runtime downloads.** Only the 18 OFL files in `fonts/` ship; `tests/test_fonts_offline.py` checks
   every bundled file is present, licensed, a TrueType file and matches its SHA-256 in `fonts/SOURCES.txt`, nothing
   stray is in `fonts/`, no code names a font host or a font URL, and every starter resolves to bundled or built-in
   faces with no substitution. Merriweather (Regular, Bold) and Public Sans (Regular, Bold, Italic) were added
   Nov 8 with Damon's approval, unmodified static files from google/fonts pinned to a commit; the US Web Design
   System kit now reads "Set in Merriweather and Public Sans".
6. **Design floors, measured on the rendered page.** The harness takes `audit=1` and writes the smallest text size
   and an emoji count to `<html data-audit>` (`--dump-dom`). Ten views in light and dark: smallest Imprint text
   12px, no emoji. It caught one: a stat label in a narrow margin rail at 11.6px; stat labels and rails now floor
   at 12px. (The harness's stand-ins for the host's own SDK buttons render at 11.5px; the host sizes those.) The
   margin-rail layout now puts the main column first when a proof is too narrow for the rail.

Screens: 39 in `docs/shots/`, re-shot from fresh fixtures (the fixtures now carry two kits of your own and the
four adapted starters). Looked at: trace light, dark, deck, missing, green accent; kits library light, dark and
all; adapted starters light and dark; Keynote import.

## Left, ranked (stage 5)

1. **Tuesday live test**, `docs/LIVE-TEST.md`, now also: the trace card in Electron (hover, Tab, Escape, card
   position inside a scrolled sheet), `ctx.files.list(id, '')` returning the folder root, and one real Windows or
   Linux run of an import (the code paths are tested; no machine run yet). The end card must not claim Windows or
   Linux until one run passes.
2. Done Nov 8: Merriweather and Public Sans bundled (approved download); the USWDS kit no longer substitutes.
3. Re-pin `docs/catalog/imprint.yaml` to the pushed commit; make `trace-light.png` the catalog image
   (UPGRADE-REVIEW item 7). Push needs Damon's go-ahead.
4. `docs/SECURITY-AUDIT.md` per `../SECURITY-BAR.md` (pip-audit, semgrep, npm audit; an outside sign-off).
5. Body text with many numbers reads footnoted (every number carries its mark, as asked). If Damon finds it busy,
   the cheapest change is marks on stat and slide figures only, with body numbers keeping the dotted underline.
6. Stage 4 items 6 to 8 below are unchanged.

## Stage 4: what changed

**Design review (step 7) on real renders**: light, dark, red accent (`e5484d`), green accent (`30a46c`), a
900px pane and a 2200px pane. Fixed after looking:

1. **The signature was below the fold.** Pages grew to fit their text (about 1,000px tall at a 1500px pane), so
   the color bar, colophon and checks only showed after scrolling, and the bottom crop marks never showed.
   Pages now keep the letter shape (8.5:11) and scroll inside, as DESIGN.md planned; the whole proof (crop
   marks, page, color bar, slug, checks) fits in one screen. Decks are unchanged (a filmstrip).
2. **Wide panes ran Docket's lines to about 95 characters.** Proof columns now cap at 640px and the table centers.
3. **"Visual Coming" and "Report Coming"** in the output switcher advertised unbuilt work and wrapped the bar to
   two lines at 900px. The switcher now shows only One-pager, Deck and Audio brief, at 13px. (The SPEC asked for
   "Coming" tabs; I cut them for the premium bar. Put them back in `TopBar` if Damon wants them.)
4. **Kit covers cut a line in half** (US Web Design System at 900px: "The warming center kept 412 / [half line]").
   Covers now grow to fit, rows stay even, the sample is held to three whole lines.
5. **Dark swatches**: a `#1b1b1b` ink chip vanished on the dark ground; chips now use the strong stroke.
6. **Sources tab**: the token-limit and forget-everything fields ran 1,230px wide; now 280px.

**Recurring elements, each with its reason** (all kept): crop marks, color bar and colophon slug (the signature;
Imprint makes print-ready pages); check pills with a glyph plus words (results, readable without color, so red and
green accents don't collide with pass and fail); superscript source numbers (they match the source list on every
page); numbered steps 1 to 4 in Help me build a kit (a real sequence); 01 to 06 on audio segments (spoken order);
the navy band on the USWDS kit and the green band on Plain Notice (each kit's own device, not Imprint's); mono
only for hex codes (data). Nothing found by reflex. Recorded in `~/.design-ledger.jsonl` ("Imprint (Hermes
plugin, built)", verdict pending Damon).

**Copy audit** (every pane string and every backend message, 300+ lines read): cut "Hermes reports no cost, so
none is shown"; cut "Imprint borrows a method from each, never the whole look" to "Pick up to three"; tightened
the website reader line; replaced robotic "No such kit/draft/job/source" and "Unknown font" with plain sentences
and a next step; the grounding pass now says "All 30 numbers and quotes found in your sources" instead of "Every
fact traced" (it proves presence, not truth; this was stage 3's item 3). No emoji, no periods on headings, no
"this tool helps you".

**New: Claude Design `.zip` import** (Damon's correction 2 in SPEC). `imports.read_claude_design_zip`: 25 MB cap,
5,000 entries, 200 MB unpacked, 100:1 ratio on big parts, no climbing paths, backslashes or drive letters, no
symlinks, `__MACOSX` ignored, finds the token files at any depth, reads only the files the folder route names, then
the same reader. Pane: "Pick the .zip" first, "Pick the folder" second. 3 new tests.

**Package**: README rewritten (what it does, install, what leaves the computer, what it touches, disclosures),
`docs/MANUAL.md`, `CHANGELOG.md`, LICENSE (MIT, unchanged), `docs/catalog/card.png` (1200x600, from
`card.html`), `docs/catalog/imprint.yaml` (draft, validator-clean), `docs/catalog/PR.md` (draft),
`docs/LIVE-TEST.md`, `docs/DEMO-NOTES.md`. Screens re-shot: 29 in `docs/shots/`, adding narrow, wide and
accent views.

## Left after stage 4, ranked (item 4, the trace card, and the font part of item 8 are handled in stage 5)

1. **Tuesday live test**, `docs/LIVE-TEST.md`, riskiest first: register in the dashboard process (aux task
   listed), kit fonts in Electron, export save dialog, `text_to_speech` from a background thread, second-profile
   jobs, image input, folder grants, a real Claude Design zip and Canva PPTX. Then swap the PR screenshots for
   real Hermes captures (the current ones are harness renders in a mock window).
2. **Re-pin** `docs/catalog/imprint.yaml` (sha and image URLs) to the pushed commit; push needs Damon's go-ahead.
3. **`docs/SECURITY-AUDIT.md`** per `../SECURITY-BAR.md`: pip-audit, semgrep, npm audit not yet run; an auditor
   who did not build it signs off.
4. **The trace card** from the upgrade review (hover a number, see "Exact match in source 3" and the line) is not
   built. Today the source shows only when a check is opened. It is the strongest single demo beat if it lands.
5. **Platforms**: not yet run on Linux or Windows; the end card must not claim them until one run passes.
6. Stage 3 items still open: sweep orphaned `uploads/`; a timed-out voice call can leave a `-take` file; deleting
   a source blocks export of older outputs that cite it (say so on the second click); one DB connection per data
   folder for two open profiles.
7. SHOULD items not started: Visual, Report (.docx), two voices with ElevenLabs, YouTube captions, Open Design
   export, scanned PDFs, `imprint_make` agent tool, History. Import gaps: website logo candidates, "Draft voice
   notes from README", update a kit from a file side by side.
8. USWDS fonts are bundled as of Nov 8. The Ledger kit names Times New Roman, which is not bundled (it resolves
   to the PDF's built-in Times, which is the same face, so no substitution is reported).


## Stage 3 review: what was broken and is now fixed (each with a test)

1. **Arbitrary file read through a kit (critical).** `POST /kits` kept any `logo.file` and `fonts[].file` the
   page sent, so `{"logo": {"file": "../../../../.env"}}` made `GET /kits/<id>` return `~/.hermes/.env` as a data
   URL, put it in exports, and `duplicate` copied a named path. Now `kits.safe_logo` / `safe_fonts` accept only
   the names Imprint writes (`logo.<png|svg|jpg>`, `<family>-<weight>-<style>.ttf`), a new kit always starts with
   none, and every read checks the path stays in the kit folder (`kits.inside`). `tests/test_kits.py`
   `KitFilesStayInside` (fails on the old code).
2. **Jobs ran in the wrong profile.** Hermes keeps the active profile's home in a context variable; job threads
   were bare threads, so a job started from a non-default profile wrote to the default profile's data folder and
   used its model. Jobs and tool calls now run in a copy of the request's context. `JobsKeepTheProfile`.
3. **A voice that never answered held the job forever** (`dispatch` ignored its timeout, and `asyncio.run` waits
   for worker threads). `runtime.dispatch_bounded` runs the tool on a daemon thread with a hard 300 s limit; the
   proof says "took too long" with Record again. `test_a_voice_that_never_answers_does_not_hold_the_job`.
4. **A failed make left a half-made output** that the page then opened as the latest. Failed makes now delete
   it (Retry makes a fresh one).
5. **Word files had no zip-bomb check.** `ingest.zip_unpacks_safely` refuses a .docx that unpacks past 150 MB
   or packs more than 200:1 in a large part, before python-docx inflates it.
6. **Office XML check could be skipped** with a UTF-16 part or a lowercase `<!doctype`. Now any NUL byte or any
   DOCTYPE/ENTITY in any case is refused.
7. **Request bodies were read whole before the size check** (`/kits/import` and base64 uploads). Bodies now
   stream and stop at the cap; a declared Content-Length over the cap is refused first.
8. **Guide route trusted its input shape** (`subject` as a list crashed with a 500; `fixed.notes` and
   `fixed.colors` were unbounded into the prompt). Now trimmed to known keys and sizes. Draft patches skip
   non-dict colors and `True` as a logo index.
9. **Install scanner caution** (an invisible U+FEFF and a no-break space as literals in `ingest.py`): written as
   escapes. Full `validate_plugin_dir` run in a scratch HOME: 16 checks pass, 0 warnings (manifest, requires
   hermes, loadable, python dependencies, capabilities match registrations, security scan, no core override,
   private imports, desktop surface).
10. **Text under 12px in proofs** (citation marks at 8.8px, slide refs, segment numbers, foot, memo labels, big
    dek in narrow panes): floored at 12px.
11. **One-click permanent deletes** of kits, sources and outputs: now two clicks ("Click again to delete",
    disarms after 4 s). "Show in folder" after export was removed: it opened Imprint's internal copy, not the
    file the person saved (the save bridge does not return the saved path).
12. **README disclosures were incomplete**: now say that text and scripts go to cloud providers when those are
    what Hermes uses, that reference sites in Help me build a kit are fetched, which Claude Design files are read,
    that exports go only where the person picks, the background threads, and no tools/hooks/credentials/shell.
13. **Red-team test** (`HostileSourceRedTeam`): a source that tells the model to delete kits, export to
    a system file and send deposit details changes only draft words; extra action-like fields are dropped, kits
    are untouched, nothing is written outside the data folder, and an invented number blocks export.
14. **Accent check**: harness takes `accent=<hex>`; flagged proofs shot with a red accent (light) and a green
    accent (dark): `docs/shots/proofs-flagged-accent-*.png`. Meanings hold by icon and words.

Checked and found sound: SSRF (Hermes's safe client, every hop re-checked), streamed web caps, HTML never
rendered raw (fixed tag list, `data:image/` only, CSS custom properties only), SQL parameterized (bandit's two
B608 hits are `IN (?,?,...)` placeholder lists), route ids regex-checked, upload names reduced to a base name,
no tools/hooks so nothing runs unattended, forget-everything needs typed words, `requires_hermes ">=0.22.0"` is
right (`ctx.files` is feature-detected), dependencies have upper bounds, no compiled binaries, gitleaks clean.
bandit: 0 high; 4 medium (2 XML parses after the DOCTYPE/ENTITY/NUL refusal, 2 SQL false positives).

**Tests: 178**, all passing (about 4 s).

## Left after stage 3, ranked

1. Live checks in Hermes (Tuesday), unchanged list below, plus: confirm a job started from a second profile
   writes to that profile (fix 2), and that `text_to_speech` from a daemon thread with a copied context reaches
   the user's provider.
2. `docs/SECURITY-AUDIT.md` per `../SECURITY-BAR.md`: run pip-audit, semgrep and npm audit (not run here), and
   attach the bandit and validator output above. An auditor who did not build it signs off.
3. Grounding proves a number or quote is *in* a source, not that the source is honest: a number planted in a
   pasted source passes. Say this in the checks panel copy ("Found in your sources") rather than implying truth.
4. `uploads/` files orphaned by a restart mid-read are never swept (`imports.expire` clears only `tmp/`). Sweep
   uploads older than a day in the same pass.
5. A timed-out voice call keeps running on its daemon thread; if it finishes later it leaves a `-take` file in the
   output folder until the next recording clears it.
6. Deleting a source blocks export of older outputs that cite it (their passages are gone); the second click
   could say so.
7. Two profiles open at once make the shared SQLite connection reopen on every switch (correct under the lock,
   only slower). A connection per data folder would fix it.
8. Web reads use `tools.url_safety` directly (no private-import warning from the validator). The digest prefers
   `dispatch_tool("web_extract")` for pages; site kits still need raw CSS, so keep the client for stylesheets.
9. Everything in "What is left" below that stage 3 did not touch (SHOULD items, import gaps, polish, catalog YAML,
   demo video).


## Stage 2 record

### What works (tested)

Stage 1 (still true): skeleton (`plugin.yaml`, manifest v2, `requires_hermes ">=0.22.0"`, no tools, hooks or
capabilities), sources with locators, 10 starter kits plus unlimited custom kits, Build from a website, Help me
build a kit with the recent-looks record, one-pager written once and voiced per kit, grounding and the other
checks, PDF / proof PDF / HTML exports, jobs that survive restarts, usage meter, Ask. Details in git history.

Stage 2 added:

- **Deck (MUST 8).** `content.DECK_SCHEMA` (Forge's slide types: section, content, stat, quote, comparison,
  closing; 7 to 11 slides after a title slide), the same write-once, voice-per-kit flow. `keep_facts` now works on
  any kind: refs, quotes, stat values, slide types and structure always come from the neutral draft; a field whose
  numbers or quoted words changed is reverted. Preview is a filmstrip of 16:9 slides in the kit (one column in a
  two-kit spread, two columns when there is room; text never under 12px; slides grow instead of cutting text).
  `render_deck.py`: **PowerPoint** with the kit on the slide master (theme `clrScheme` and `fontScheme` rewritten,
  paper as the master background, a PNG logo placed on the master through its part), speaker notes listing the
  sources behind each slide; and a **deck PDF** (16:9, kit TTFs embedded). Exports checked by eye
  (Quick Look on the .pptx; PDF pages contact-sheeted for Plain Notice, Docket and Night Desk).
- **Audio brief (MUST 9).** `content.AUDIO_SCHEMA` (4 to 7 spoken segments with signposts, a recap), written as a
  briefing for one narrator. After the voice pass, each kit's script goes to the person's own Hermes
  `text_to_speech` through `runtime.dispatch` with `instructions` from the kit's delivery notes (OpenAI voices follow
  them). Parts are joined frame to frame for MP3. No voice: the job still finishes, the proof says exactly what to
  turn on, and "Record again" starts a `speak` job. Player is a plain `<audio>` with a data URL from
  `GET /outputs/<id>/audio/<kit>`. Exports: the recording, the script as text with sources, a script PDF.
  A "Length" pill reads the script at 150 words a minute (2 to 4 minutes is the target).
- **Kit import (IMPORT-SPEC I-1 to I-8), `imports.py`.** One pipeline: a reader returns colors with role hints,
  font stacks, a type ratio, logo and font candidates and a Skipped list; `build` sets paper, ink (auto-replaced
  and noted when under 4.5:1) and roles by measured contrast; the draft lives in `kit_drafts` with files under
  `tmp/import-<id>/` (cleared after 24 hours and by Forget everything); the Kits tab shows it on a draft bench with
  **a full proof of the person's latest one-pager** (or a built-in sample) before **Save kit**. Readers: paste
  (I-2), CSS with `:root`/`@theme`/dark blocks, `var()` aliases with loop detection, Tailwind defaults dropped, a
  linear block scanner (I-3), website ending in a draft (I-4), Open Design package reading only the four named files
  with the 86-id brand-name gate and its warning line (I-5), Claude Design folder with themes, aliases, TTF fonts
  (WOFF and restricted fonts skipped with the reason, `fsType` read) and logo candidates never auto-picked (I-6),
  PowerPoint/Canva with zip-bomb, path and DOCTYPE checks, theme colors and fonts, logos used on 2+ slides,
  embedded fonts never reused (I-7), DTCG tokens with aliases, `$ref`, type inheritance, modes, oklch/oklab/p3
  conversion and caps (I-8). Required lines are never imported. The save line: "Use kits only for brands you own or
  have permission to use. You're responsible for documents made with this kit."
- **Kit from a logo or brand sheet (Damon's addition).** PNG/JPG/WebP goes to the person's model through
  `complete_structured` with an image block (not `vision_analyze`, per spike S1), returns colors with roles, font
  guesses and a layout, and lands as a draft marked "read by your model". A non-vision model gets "Pick a model
  that can see images, or paste your color codes." The same image can be added as a reference in Help me build a
  kit.
- **Folder imports in the pane** use `ctx.files.requestFolder`, read only the named files, then `release` the
  folder. Feature-detected: on an older Hermes the pane says so and offers "Pick its tokens.css instead", so the
  floor stayed `>=0.22.0` at this stage. (Now `>=0.22.6`: see `plugin.yaml` and the CHANGELOG.)
- **Security fix from the Nov 7 review (must fix before release): done.** `ingest.fetch` now streams: a
  Content-Length over the cap is refused before reading; decoded bytes are counted as they arrive and the read
  stops at the cap (pages refuse and say so; stylesheets keep what fits). URL sources use the 25 MB file cap;
  stylesheets are capped at 10 per site, same site only, 2 MB each. Tests: declared-too-big, missing length,
  decoded bomb, keep-what-fits, small page. Uploaded SVG logos now pass the same SVG checks as imports (no
  DOCTYPE/ENTITY, script, foreignObject, `on*`, external `href`).
- **Tests: 164 at the end of stage 2 (178 now)**, `cd tests && /usr/bin/python3 -m unittest discover -s .` (about 3 s). New files:
  `tests/test_outputs.py` (deck, audio, streamed fetch), `tests/test_imports.py` (every reader, the pipeline,
  the gate, safety, routes; runs over all installed Open Design packages when the app is present).
- **Screens: 22** in `docs/shots/`, rendered from real backend fixtures (`harness/make_fixtures.py`), light and
  dark: `deck-light/dark`, `audio-light/dark`, `audio-novoice-light`, `kits-import-light/dark`,
  `kits-draft-light/dark`, plus the stage 1 set re-shot. Looked at each; fixed a slide class collision that hid
  the title slide's subtitle and date, and slide text that overflowed when the filmstrip was two columns.

### What is left, in priority order (stage 2 list)

1. **Live test in Hermes (Tuesday)**: `register` in the dashboard process, aux task routing, FontFace in Electron,
   25 MB upload through Electron, the export save dialog, events, **`text_to_speech` from a route** (S2: confirm
   `output_path` under plugin-data is accepted, and what Damon's provider returns), **image input** on his model
   (S1), `ctx.files.requestFolder` with a real Open Design folder and a Claude Design folder (spike D1), one real
   Canva PPTX (spike C1), one Figma variables export (spike F1).
2. SHOULD, in SPEC order, none started: **Visual** (one-panel infographic, SVG and PNG), **Report** (.docx with
   kit styles, logo in header, source list), two voices with ElevenLabs, YouTube captions, Open Design **export**,
   PDF page vision and scanned PDFs, `imprint_make` agent tool, History.
3. Import gaps against IMPORT-SPEC: website logo candidates (apple-touch-icon, og:image, inline SVG) are not
   fetched or offered; Claude Design "Draft voice notes from README" button is not built; Open Design
   `design-tokens.json` "default" tags and `DESIGN.md` front matter are not read; "update an existing kit from a
   file" side by side (SHOULD) is not built.
4. Polish: deck proofs could use the upgrade mock's hero-plus-grid at video size; draft bench shows head and accent
   as two swatches when they are the same color; PDF one-pager still never grows to fill a short page; grounding
   panel beside the proof; specimen line from the person's own sources on the Kits grid.
5. Catalog YAML, README disclosures (updated in this stage), demo video, SECURITY-AUDIT (bandit, semgrep,
   pip-audit, npm audit, gitleaks history) per `../SECURITY-BAR.md`.

### Known risks

- `register(ctx)` may not run in the dashboard's process. Then routes use `PluginLlm` directly and the public tool
  registry; `text_to_speech` must be registered there or the audio says "your Hermes voice isn't set up here" even
  when it is. Verify Tuesday; if so, consider calling the TTS function module directly.
- `text_to_speech` may refuse `output_path` under plugin-data on some setups; Imprint retries without it and copies
  the file in. Only audio extensions are accepted from the tool's result.
- The deck preview reflows; PowerPoint uses fixed text boxes. A very long bullet can overflow its box in .pptx.
  The deck PDF draws from the same specs.
- Image reading depends on the main or `imprint_write` model accepting images; a text-only model fails with the
  plain message above.
- Mozilla Protocol stays dropped (MPL-2.0 code, but it is a system for Mozilla and Firefox sites and Mozilla's
  trademark policy forbids designs confusingly similar to its marks). Demo kits: US Web Design System (no logo,
  seal or banner) and the original starters.
- Bundled fonts differ from the SPEC's list (Source Serif 4, Zilla Slab, IBM Plex Sans are not bundled); the set
  is 13 OFL files that were already on the machine plus Merriweather and Public Sans, downloaded Nov 8.
