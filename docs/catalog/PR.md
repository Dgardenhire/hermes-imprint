# DRAFT PR description (not submitted)

Title: `plugin-catalog: add imprint (a notebook for your sources that makes branded decks, one-pagers, graphics and audio briefs)`

Before opening: replace `SHA_PLACEHOLDER` in `imprint.yaml` (the `sha` and the two image URL prefixes) with the full
40-character commit that is pushed and reviewed.

---

## Imprint

Imprint is a Hermes Desktop page for working from your own documents. You add PDFs, Word files, transcripts, web
pages and notes. You ask questions and each answer carries numbered marks that open the passage it came from. Then you
make a deck, a one-pager, a graphic or an audio brief set in a brand (a saved set of colors, fonts, a logo and voice
rules). Every number and quoted phrase is matched against the passages it cites, in code, after the model has
written; a number that is not in the sources holds Export until it is fixed or kept on purpose.

Decks, one-pagers and graphics are drawn three ways (Editorial, Data board, Statement). The model lays each out as a
web page, a headless browser (Chrome, Chromium, Edge or Brave) draws it, and the model looks at a picture of the result and fixes it. The user can use one design or
mix slides across the three. A template version in the brand's own fixed layouts needs no browser. Brands can be
imported (PDF guide, color codes, CSS, design tokens, PowerPoint or Canva file, logo, Open Design package, Claude
Design system), built from a website, or proposed three at a time by the user's model.

Manual: https://linchpin.studio/hermes/imprint/manual/

### Hermes surfaces used

- `ctx.register_auxiliary_task`: one task, `imprint_write`, shown as "Imprint writing" in Settings, Models, Auxiliary.
  Every model call goes through the plugin LLM helper to the user's own Hermes model.
- A Desktop page (`desktop/plugin.js`, built from `desktop/src`), importing only `@hermes/plugin-sdk`, `react`,
  `react/jsx-runtime` and the bundled `hermes-ui-kit`. Its **Manual** button opens the manual in the user's browser
  through `api.os.openExternal`.
- A dashboard API (`dashboard/plugin_api.py`) for the page.
- The user's own tools, by fixed name through `ctx.dispatch_tool`: `text_to_speech` (the audio brief) and
  `web_extract` (a web address the user typed). A third, `image_generate`, exists in the backend; the shipped page has
  no control that asks for pictures, so it is reached only by an API request that sets a `pictures` flag on a deck.
- `tools.url_safety` (public API) for web reads when `web_extract` is not set up.
- No tools, hooks or middleware are registered. Nothing runs unless the user presses a button.

Requires Hermes 0.22.6 or newer (`requires_hermes` in the entry and in `plugin.yaml`). Python dependencies, all with
floors and upper bounds: `pypdf>=6.21.4,<7`, `python-docx>=1.1,<2`, `python-pptx>=1.0,<2`, `reportlab>=4.0,<6`,
`Pillow>=10,<14`.

### Disclosures (rule 13)

- **Model calls.** Source text (secrets redacted with Hermes's redactor), questions, briefs and notes go to the user's
  own Hermes model. That includes pictures of draft slides, which the model is shown so it can fix layout. A logo or
  brand sheet goes to the model as an image only when the user asks Imprint to read one.
- **Speech.** Audio scripts and the brand's delivery notes go to the user's Hermes `text_to_speech` provider. With the
  default (Edge) that is Microsoft's online voice service. It is the user's Hermes setting.
- **Network calls of its own.** Only web addresses the user enters (page sources, a site to build a brand from,
  reference sites in Help me build a brand). Page sources go first to the user's `web_extract`; otherwise, and for
  brand sites, through Hermes's SSRF-safe client: public addresses only, every redirect checked, 20 seconds to answer
  and 60 in all, streamed and size-capped, gzip or deflate only, the page plus up to 10 same-site stylesheets. No other
  hosts. No telemetry or usage reporting.
- **A headless browser, a child process.** Started only by a button press, with a scratch profile that is deleted
  after, and started with `posix_spawn` (never `fork`). Which browser (`browser.py`): the `IMPRINT_BROWSER` environment
  variable (a full path, or a program name) when it is set; otherwise the usual install folders for Google Chrome,
  Chromium, Microsoft Edge and Brave on macOS (`/Applications`, `~/Applications`) and Windows (`Program Files`,
  `Program Files (x86)`, `AppData\Local`); otherwise those programs by name on `PATH` (macOS, Windows and Linux). Chrome
  is preferred when several are installed. The lookup has been run on a Mac; the Windows and Linux paths are covered by
  tests that stand in for those systems. If none is found the Designs screen says so and the template version still
  works. Two uses:
  (1) Drawing the three designs and their PDF and image exports (`htmldeck.py`). Each page it draws carries
  `default-src 'none'`, so it can request nothing.
  (2) Looking at a website the user builds a brand from (`sitestyle.py`), on macOS and Linux (on Windows the site's
  colors and fonts are still read, and Imprint says the browser look is not available there yet). It opens the home
  page and up to three linked pages, read only, never types, clicks or signs in, after reading robots.txt. It is
  driven over a pipe (no debugging port) and receives no other descriptor of Hermes's. All its traffic must pass
  through a forward proxy Imprint runs on `127.0.0.1` on a random port, which resolves each host once, refuses unless
  every address is public, and connects to that checked address; QUIC, WebRTC and WebTransport are disabled.
- **Other shell command.** On macOS, `sips` converts the first page of a one-pager PDF to a small preview image;
  without it a brand card is drawn instead.
- **Background work.** Model calls, web reads, recordings and drawing run on threads inside Hermes. The checking proxy
  is a thread that exists only while a website is read. Each ends with its job. A job interrupted by a Hermes restart
  is marked stopped.
- **Reads.** Only files the user picks; in a folder import, only the named token, font and logo files, with the folder
  grant released after; and, for a generated image, only from `<HERMES_HOME>/cache/`. Zip, Word and PowerPoint files
  are checked for size, unpack ratio, climbing paths, links and XML entities before reading. Uploads stop at 25 MB.
- **Writes.** `<HERMES_HOME>/plugin-data/imprint/` (including a `debug.log` of error kinds, last 200 lines, never the
  user's words), scratch folders it deletes, and paths the user picks in the save dialog. If the `IMPRINT_DATA_DIR`
  environment variable is set, everything Imprint stores goes to that folder instead (the test harness uses it; Hermes
  never sets it). "Forget everything" deletes the data folder.
- **Credentials.** None stored or read. No self-updates. No telemetry.
- **Bundled data.** 29 OFL font files (.ttf) with `fonts/OFL.txt` and `fonts/SOURCES.txt`. No compiled code. The tests
  and the local test harness carry sample Word, PowerPoint, PDF and .zip files (a fictional brand kit).
- **Time.** A three-designs run takes several minutes on a small model; each model call is cut off after 8 minutes.

### Fixed since the first draft (Nov 10-11)

- **Designs on Claude models.** When Claude's strict output mode (or Hermes itself) declines the JSON format request,
  Imprint asks for the JSON in plain words and reads it from the reply, so the design and fix calls work on Claude.
- **Shapes over text are caught.** The layout check now flags a chart mark or shape drawn over text, and the fix round
  is shown it.
- **The title slide is kept** in all three designs.
- **Route loading under concurrent requests.** The revise and designs routes load once, behind a lock (8-thread test).
- **Fast open.** The last good notebook is drawn at once from plugin storage while the backend starts; it takes no
  input until the real answers land.
- **Slide-number badges** sit in a caption row under each thumbnail, not over the slide.
- **Website colors.** Build from a website weighs colors by where they are used (backgrounds, headings, logo), not by
  how many rules mention them, so an error red no longer becomes the brand color.
- **Speed.** Slides are drawn four at a time, only changed slides are redrawn, later fix rounds send only slides that
  still have problems, and each design shows its step and elapsed time.
- **Plain errors.** With the backend down the page says "Imprint's backend isn't answering." (not "Failed to fetch"),
  and a job check stops after 90 seconds of no answers and says so, instead of spinning forever.
- **Browser start-up.** The browser is started with `posix_spawn`, never `fork`: on macOS a forked child can crash in a
  system network framework's fork handler once proxies have been looked up. This was the cause of three security
  tests failing only in the full suite.
- **Manual link.** A **Manual** button in the top bar opens the manual on linchpin.studio in the user's browser.

### Tests

689 Python tests pass in one full run (`cd tests && python3 -m unittest discover -s .`, about 2.5 minutes), with one
skip: a migration check that needs an older checkout beside the repo. The desktop page's own tests pass with
`node --test tests/js/*.test.mjs` (18 tests, 17 pass and one is driven from the Python suite with a real state answer).
The three Chrome-over-a-pipe security tests, which used to fail only in the full run, pass in it.

Overlap: Podcast Studio (merged) makes two-host audio from any text. Imprint's audio is one narrator through the
user's own Hermes voice and is one of four formats tied to a brand. `folio` (open) indexes and cites a library;
Imprint makes branded outputs from a chosen set of sources.

### Screenshots

Captured in Hermes Desktop with the made-up Harborlight sample: the notebook on first open, a deck with the number
check, a one-pager with its evidence, the three designs, and a mixed deck.

### Validator warnings, one line each

- **Security scan, `docs/SECURITY-AUDIT.md:386`.** A prose line in an audit document that named example system and
  settings file paths as paths the plugin refuses to read; it was documentation, not code, and is reworded so it no
  longer names them.
- **App markup selector, `desktop/plugin.js` 2727, 7196-7197, 7427-7429 and 7528 (from `desktop/src/plugin.js` 2647-2648,
  2878-2880, 2979 and `desktop/src/designs.js:200`).** Every one is a rule inside the plugin's own CSS text, not a query run on the page
  with JavaScript. Each is anchored to a class the plugin renders itself (`.imp`, `.imp-top`, `.imp-askcard`,
  `.ip-ds-export`), and selects the SDK `Button` component, which the plugin renders inside that element, by its
  `[data-slot=button]` attribute to set its corner radius, font size, quiet style or a held-back look. None reaches
  Hermes's own markup outside the plugin's page: there is no `document.querySelector` or `MutationObserver` on app
  elements, no `window.hermesDesktop` call, and the only document-level query in the plugin (`.ip-cv-nums`) is for one
  of its own classes. If the reviewers would rather the plugin style its buttons only through SDK props, that is a
  change to make before merge.

Imprint is an independent community plugin. It is not made or endorsed by Nous Research.
