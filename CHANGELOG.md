# Changelog

## 0.1.1, November 12, 2026

Letterpress was called Imprint before Nov 12, 2026.

- **New name.** The plugin is now Letterpress. Install it with `hermes plugins install letterpress`; it appears as
  **Letterpress** in the sidebar, and its writing task is **Letterpress writing** under Settings, Models, Auxiliary.
- **Your work carries over.** The first time Letterpress opens its data folder, it copies in everything from the
  folder kept under the earlier name: sources, brands, made pieces, notes, chats and settings. The earlier folder stays
  exactly as it was; delete it yourself once you no longer need it. If the Letterpress folder already holds data,
  nothing is copied and nothing in it is replaced. Only this plugin's own data is copied.
- **The Brands page fits its window.** Studio brands and earlier starters no longer run past the right edge; the
  columns step down as the window narrows.
- **Outside programs no longer receive your Hermes keys.** The browser that draws designs and reads websites, and the
  macOS `sips` program that draws one-pager previews, start with only what a program needs to run: `PATH`, `HOME`, the
  temporary folder, the language settings, and on Linux and Windows the few system settings a browser reads at start.
- **Turn it on again.** Hermes keeps "on for this profile" and the model picked for a writing task by plugin name, so
  switch Letterpress on under Capabilities, Plugins, and pick its writing model again if you had picked one.
- `LETTERPRESS_BROWSER` and `LETTERPRESS_DATA_DIR` replace the earlier environment variable names, which are still read.
- **The page file can be rebuilt from this repository.** The shared interface code behind `desktop/plugin.js` is now in `vendor/hermes-ui-kit` with a pinned esbuild, and `node scripts/verify-bundle.mjs` rebuilds the file and checks it matches byte for byte.

## Unreleased

### Statement fix (Nov 11, 2026)

- **No more bare grey slides.** A Statement deck could come back with every slide after the title unstyled: the model drew
  the slide number with CSS `content: attr(...)`, which Letterpress refuses for safety, and refusing it threw away that
  slide's whole stylesheet. Now only the refused rule goes; the rest of the slide keeps its styling. The brief tells the
  model never to draw text with CSS, and the Statement brief is simpler (one large figure or statement on a plain
  ground, no slide number).
- **A broken design is never offered.** A design with an unstyled or empty slide, or more than two layout problems a
  slide, is made once more. If it is still broken, a deck shows Letterpress's own layout in that design's direction,
  named "(template version)" on its card; other pieces say to try again. At most two tries per design.

### Ambition pass (Nov 11, 2026, branch `ambition-nov11`)

- **Type the new title.** In Revise, "Change this slide's title to: ..." now does it. Also "Change the subtitle to
  ...", "Set the heading of slide 3 to ..." and "Rename slide 2 to ...". Your words are set exactly as typed, with no
  model call. They are checked against your sources like any other change, shown beside the old title, and nothing
  changes until you press Keep. A number no source holds is named and the slide stays as it was. Works on the title
  slide and on slides the model laid out. A quote slide can't be typed over, since it shows a source's exact words.
- **Source notes (PDF).** A new export for decks and one-pagers: every number and quote on the piece beside the
  sentence in your sources it came from, with the source's name and section, grouped by slide, in your brand's faces
  and colors. A figure worked out from two others shows the sum; a figure you kept on purpose says so. No model call.
  Needs Chrome, Chromium, Edge or Brave, like the three designs. A brand with a dark ground prints dark type on white.

### Live check (Nov 11, 2026)

- **Manual** at the right end of the top bar opens the manual on linchpin.studio in your browser.
- Works with Pillow 13, the version Hermes now ships; Hermes no longer warns that a dependency is missing.

### Rubric fixes (Nov 11, 2026, branch `rubric-fixes`)

- **Plain words when the backend is down.** A request that never reaches Letterpress's backend now reads "Letterpress's backend
  isn't answering." instead of the browser's "Failed to fetch"; the start-up screen adds "Wait a moment and try again. If
  it keeps happening, restart Hermes." Every error sentence ends with a full stop.
- **Job checks stop when nobody answers.** A running job is checked quickly at first and then less often; when the
  backend stops answering, checks back off further, and after 90 seconds of no answers the page stops waiting and says
  so (the job may still finish). The Designs room does the same for its own view and offers Check again.
- **The browser starts without fork.** The website reader's browser is started with `posix_spawn`, gets only its own
  pipe, and the design browser and `sips` are started the same way through subprocess. On macOS, a forked child could
  crash in the system network framework's fork handler once proxies had been looked up; that made three security tests
  fail only in the full suite, and could have stopped the browser inside Hermes.
- **Windows website look** says plainly that the browser step isn't available there yet; colors and fonts are still read.
- **Copy.** The first screen's headline names what Letterpress does, with no "every number is checked" line and no caption
  under the sample slide; the Designs room drops its subtitle and the one-line taglines under each design. "Open the
  sample" says "Opening the sample" while it works. Messages say brand, not kit. A private or local web address says it
  isn't a public page; a cut-off answer suggests Retry or a shorter piece.
- **Docs.** The catalog entry and PR describe the browser lookup as the code does it (Chrome, Chromium, Edge or Brave;
  `LETTERPRESS_BROWSER`, install folders, `PATH`) and disclose `LETTERPRESS_DATA_DIR`; the PR's Hermes floor is 0.22.6; the README
  and the manual have an Uninstall section.

### Design fixes (Nov 10, 2026, evening)

- **Designs work on Claude models.** When Claude's strict output mode, or Hermes itself, declines the JSON format request,
  Letterpress asks for the JSON in plain words and reads it from the reply; three designs running at once each recover on
  their own. A plain-text `debug.log` in the data folder records error kinds and reply shapes only.
- **A shape drawn over text is caught.** The layout check compared only text with text, so a dot grid spilling onto its
  caption passed. A small painted shape over text is now an overlap (text wholly inside a shape still passes), and the
  fix round sees it.
- **The title slide is kept.** A deck's title slide is always its own first slide in every design.
- **Routes load once under concurrent requests.** The revise and designs routes are loaded behind a lock, so requests
  that arrive together on a cold start no longer race.
- **Hermes floor.** `requires_hermes` is `>=0.22.6`.

### Fast open (Nov 10, 2026, branch `fast-open`)

- **The notebook opens at once after the first time.** The last good notebook (sources, brands, made pieces, notes, the chat
  and the guide) is kept in Hermes's plugin storage and drawn straight away while Hermes starts the plugin helper; the real
  answers replace it as they land, and the page takes no clicks or keys until they have. Pictures are kept only while the
  copy stays under 400,000 characters; jobs and anything secret are never kept. The first open ever still shows "Opening
  Letterpress".
- **The first three requests go out together.** The chat and the notebook guide no longer wait for the state answer.

### Fixes (Nov 10, 2026)

- **Slide-number badges no longer cover the slide.** The numbers (and "used" ticks) on the design thumbnails and the deck strip sit
  in a caption row under each picture, not over its top-left corner.
- **Build from a website picks the brand, not the error red.** Colors are weighted by where they are used (page and header
  backgrounds, headings, logo) instead of by how many rules mention them; `var(--x)` uses count; error, alert, small-button and
  hover colors are demoted; the paper is found in backgrounds, so white text on dark no longer beats a cream page.
- **The audio brief's "not recorded yet" bar** stays in the page flow above the script; the recorded bar sticks below the
  header's real height.
- **Interrupted design runs recover.** Options left "writing" by a restart or Stop come back as "Interrupted. Press Design three
  options again." (on open and at startup) and the button works again.
- **Shorter design runs.** Pages are drawn four at a time and only changed slides are drawn again; later fix rounds send only the
  slides that still have problems; a fix that changes nothing, or extra rounds that stop clearing hard problems, end the loop;
  each design shows its step and elapsed time.
- **Any browser.** Chrome, Chromium, Edge or Brave on Mac, Windows and Linux, or `LETTERPRESS_BROWSER`; the Designs screen says so
  when none is found.

### Designs and the site style brief (Nov 9, 2026, branch `loop4`)

- **Three designs for every deck, one-pager and graphic.** Make now also asks the model to lay the piece out itself, three different ways
  (Editorial, Data board, Statement), as HTML and CSS drawn by Chrome; the model looks at its own render and fixes it. The three
  appear side by side in the Studio with a progress line. Pick one, or pick slide by slide across the three; edit a line; revise in
  words; restore a version; export PDF (PowerPoint as slide pictures with notes, for decks). The template path (proof, canvas, outline,
  versions, exports) is unchanged and one click away ("Template version").
- **Number trace on designed slides**: every number, in text, chart labels and chart marks, must cite a passage that holds it; numbers
  written as words are checked too; a flagged number holds Export until fixed or kept on purpose.
- **Style brief from a site**: the website reader now also opens the site in a browser (read-only, robots respected, home page plus
  up to three pages), photographs and measures it, and writes a short brief (layout, type, images, shapes, color use, components,
  tone, what to avoid). It lives with the kit, is editable on the Brands bench, and the designs follow it.
- **Changed**: nothing removed. The kit's layout family and density now also feed the designs as a starting style. Pictures in a
  designed slide are never allowed except the logo (a picture could carry a number nobody traces). `docs/API-DESIGNS.md`.

### Notebook (Nov 8, 2026, branch `notebook`)

- **Three-pane notebook as the main screen.** Sources (files, dropped files, links read through your Hermes web
  tool, pasted text; a two-sentence summary and three questions per source; tick to include; open any source at a
  cited passage), Chat (answers synthesized only from ticked sources, every claim numbered to a real passage the
  model was shown, pin as note, copy, follow-ups, clear) and Studio (kit chooser, four outputs, step-by-step
  progress with real times, everything made, notes). Outputs open large in a viewer with checks, kit swap and
  exports. The Proofs tab and the two-kit spread are gone; Sources is now Storage.
- **Five studio kits** lead the library: Counsel, Chart Room, Stage, Folio, Meridian. The 16 earlier starters stay,
  listed below them.
- **Scene engine and five deck systems** (`scene.py`, `systems.py`): every slide and graphic is composed once, with
  measured type, and drawn the same in the pane, PDF, PowerPoint, PNG and SVG. New slide types: exhibit (labeled bar
  or column chart with its source line), timeline, picture (opt-in, from your Hermes image tool; type-only when it
  doesn't answer). Reading text 30 pt or more; slides that still run long are named in a check.
- **Graphic output**: one 4:5 information graphic per make (bars, figures, compare or timeline), PNG, SVG, PDF.
- **Kits tab**: studio kits shown by their own slides; the bench previews what a kit makes as you edit and picks
  its deck system.
- **Fonts**: Source Serif 4 (400, 600), Source Sans 3 (400, 600) and DM Serif Display, unmodified OFL files copied
  from LINCHPIN's own projects, hashes in `fonts/SOURCES.txt`.
- **Fixes**: the corpus no longer drops a source's last passage when its locators run long; PowerPoint slides state
  their background so other apps read the paper right.
- **Harness**: `harness/live/seed_notebook.py` fills live mode with the warming-center notebook;
  `harness/shoot.sh` now shoots live mode; `harness/render_gallery.py` renders every studio kit's deck, graphic and
  one-pager.

### Before the notebook

- **Exports safe to send.** The HTML export is the finished page: no trace marks on numbers, footnotes that link
  to the source list, one column on a phone. The colophon and color bar print on the proof only. A kit that lists
  no sources (a menu, a flyer) puts no source marks on any export. Phone numbers are one figure.
- **Logos that show.** Letterpress measures the logo against the band and the paper it sits on and, where it would
  vanish, uses your reversed logo (new upload on the kit bench) or knocks the mark out. One-pagers, HTML, PDF,
  deck PDF and PowerPoint. A Logo check says what it did.
- **Fewer false alarms in the check.** Quotes match regardless of the punctuation around them; spelled-out numbers
  in sources match digits; numbers from your own request count as known; the closest passage comes from every
  source, shown as one sentence; items not found come first.
- **Better kit imports.** Brand guide PDFs (codes, names, usage notes, fonts). Pasted codes honor the labels beside
  them ("Primary", "Calls to action only") and keep their names. PowerPoint and Canva files rank colors and fonts by
  what the slides use and skip Office's unused default theme colors. Skipped colors can be added back. Missing fonts
  fall to the nearest bundled open font.
- **New layouts.** Flyer or menu (items with prices, a call to action on the band) and Report (key figures,
  side-heads). Starters Market Board and Board Report. Short drafts fill the page.
- **Smaller fixes.** A starter kit's required lines are opt-in per output. Deck stat slides no longer overlap; the
  PowerPoint uses real title and body placeholders. A saved kit goes onto the left proof. One brief per format. The
  length check reads the length you asked for.
- **Harness live mode** (`harness/live/`): the real backend with a scripted stand-in model, so a tester presses real
  buttons; `drive.py` replays the persona run and renders every export.
- **US Web Design System fonts.** Merriweather (Regular, Bold) and Public Sans (Regular, Bold, Italic) now ship
  in `fonts/`, unmodified OFL files from the Google Fonts repository, so the USWDS kit sets in its own fonts and
  its colophon no longer reports a substitution. `fonts/SOURCES.txt` records each file's source and SHA-256, and
  the tests check every bundled file against it. Nothing is downloaded at runtime.
- **Security audit** (`docs/SECURITY-AUDIT.md`). Web reads unpack gzip or deflate themselves and never hold more
  than the size limit, with a 60-second limit on the whole read; uploads are capped while they stream, before
  anything is parsed or spooled; the site reader runs in linear time on hostile pages and stylesheets; every write
  is checked to stay in the data folder; long PDFs stop at the text a source keeps; SVG and JPEG logo checks are
  tighter; PowerPoint XML must be UTF-8; `pypdf` 6.21.4 or newer.
- **Trace cards.** Every checked number in a proof carries its source number; hover or focus it to see the
  source line with the number marked, the source's name and place, and an exact or close match. Keyboard
  accessible (Tab, Escape, Enter). Numbers not in the sources say so.
- **Starter library.** Four kits adapted from Open Design packages under neutral names (Payments Violet, Midnight
  Indigo, Poster Block, Parchment Ink), with attributions in `NOTICE`. The Kits tab leads with your kits, shows five
  starters as proofs, and lists all 14 on request.
- **Imports on every system.** Windows paths and zips, byte order marks, CRLF line endings and folder names in
  any case read the same on Mac, Windows and Linux. Keynote (Mac only) comes in through its PowerPoint export.
- **Fonts.** Starters that stand in an open font for a licensed one say so in the colophon. Margin-rail pages put
  the main column first when the proof is narrow. Stat labels and rails never set text under 12px.

## 0.1.0, November 2026

First release.

- **Sources:** PDF, Word (.docx), text, Markdown, web pages, pasted text and transcripts (.vtt, .srt, .txt), each
  passage kept with its page, heading or timestamp. Up to 25 MB a file, deduplicated.
- **Ask:** a short grounded chat over the sources, with numbered citations, three follow-ups, and "Make a
  one-pager from this answer".
- **Outputs:** one-pager, deck and audio brief, written once from the sources and voiced per kit, shown as two
  proofs side by side with crop marks, the kit's color bar and a colophon.
- **Checks on every proof:** numbers and quotes matched to source passages (missing ones block export until fixed,
  removed or kept on purpose), WCAG contrast, never-say words, required lines, font substitutions, audio length.
- **Exports:** one-pager PDF, proof PDF with crop marks and HTML; deck as PowerPoint with the kit on the slide
  master, plus a PDF; audio recording through the person's own Hermes voice, the script as text and a script PDF.
- **Kits:** ten starter kits (nine original kits plus the public-domain US Web Design System), unlimited kits of
  your own, a bench for colors with roles by measured contrast, fonts, logo, voice rules, layout and rules for
  every page.
- **Help me build a kit:** fixed things, the subject, up to three references, then three proposals that really
  differ, with a record of recent looks so new kits don't repeat.
- **Kit import:** paste, CSS, design tokens (DTCG), Open Design package folder, Claude Design `.zip` or folder,
  PowerPoint and Canva, a website, and a logo or brand sheet read by the person's own model. Every import is a
  draft shown as a proof before it is saved.
- **Reliability:** every slow step is a background job the page polls; jobs survive a page reload, keep the Hermes
  profile they were started in, and come back as "Stopped when Hermes restarted" with Retry after a restart; a
  voice that never answers stops after five minutes.
- **Safety:** web reads through Hermes's SSRF-safe client, streamed and capped; uploads capped while they stream;
  zip, Word and PowerPoint files checked for bombs, climbing paths, links and XML entities; SVGs checked for script;
  kit files can't point outside the kit's folder; two clicks to delete; typed words to forget everything.
