# Imprint

Imprint turns your documents into a finished deck, one-pager, graphic or audio brief in your own brand, inside Hermes
Desktop. Drop in PDFs, Word files or text. Ask questions of your sources and get answers that cite the paragraph.
Pick from three deck designs, mix slides between them, and revise any slide in plain words. Before export, numbers and
quotes are checked against the sources, and the Source notes PDF shows each one beside the sentence it came from.

The writing and the checking use the model you already set up in Hermes. Imprint has no keys of its own.

![The Imprint notebook on first open: Sources, Ask and Studio, with the Harborlight sample open: a cited answer, suggested pieces and finished designs](docs/shots/live/notebook.jpg)

The screenshots use the sample that ships with Imprint: Harborlight Literacy, a made-up adult literacy group.

## What it does

- **Sources.** Add a PDF, a Word file, a text or Markdown file, a transcript (.vtt, .srt, .txt), a web page or pasted
  text. Each becomes a card with a short summary. Tick the ones that count; everything else in Imprint uses only the
  ticked sources. Click a card to read every passage with its page, heading or timestamp. Imprint does not listen to
  audio or video; add the transcript.
- **Ask.** A chat that answers only from the ticked sources. Each claim carries a numbered mark that opens the passage
  it came from, and a mark appears only when it points to a real passage the model was shown. Pin an answer as a note,
  copy it, or use **Make from this** to start a deck, one-pager or graphic from it.
- **Studio.** Four things to make: **Deck**, **One-pager**, **Graphic** and **Audio brief**. Fill in who it is for,
  what they should decide or do, and a length. A deck stops at an outline you can edit (retitle, reorder, delete, add,
  ask for three new titles) before anything is drawn.
- **Three designs.** When a deck, one-pager or graphic is finished, Imprint draws it three ways: Editorial, Data board
  and Statement. Your model lays each one out as a web page, Chrome draws it, and the model looks at a picture of the
  result and fixes what is wrong. For a deck you can use one design whole, or click slides from any of the three to mix
  them into one deck, then revise in words, edit a line, or restore an earlier version. A **Template version** of
  every piece, set in the brand's own fixed layouts, is one click away and needs no Chrome.
- **Numbers are checked.** After the model has written, code matches every number and quoted phrase against the
  passages it cites. A number that is not in your sources is flagged, and Export waits until you fix it, have your
  model fix it, or keep it on purpose. Hover a number to see the source sentence with the number marked. The check
  shows that a number appears in your sources. It cannot tell you whether the source is right. It checks numbers and
  quotes, not claims or framing: a deck headlined "adds a site" passed 19 of 19 when the sources said "proposes", so
  read the headlines yourself.
- **Brands.** A brand is a saved set of colors with roles (checked for contrast), fonts, a logo, voice rules, a page
  layout and rules for every page. Five studio brands ship with Imprint (Counsel, Chart Room, Stage, Folio and
  Meridian), plus 16 earlier starters. Make your own by importing one (brand guide PDF, pasted color codes, CSS,
  an Open Design package, a Claude Design system, a PowerPoint or Canva file, a design tokens file, a logo or brand
  sheet, a Keynote theme on a Mac), by **Build from a website**, by **Help me build a brand** (your model proposes
  three that differ), or by hand. Every draft is shown as a proof before you save it.
- **Exports.** Deck: PDF, and PowerPoint. From the standard version the PowerPoint carries the brand on its slide
  master with real title placeholders and bullets. A deck made from the three designs exports to PowerPoint as one
  picture per slide, with the slide's notes: you can present it, but not edit its text in PowerPoint. For editable
  slides, export the Template version.
  One-pager: PDF and PNG from the designs; PDF, a proof PDF with crop marks and a self-contained HTML page from the
  standard version. Graphic: PDF and PNG from the designs; PNG, SVG and PDF from the standard version. Audio brief:
  an MP3 recording, the script as text and a script PDF. An export is saved where you pick in the save dialog.
  Decks and one-pagers also export **Source notes**: a PDF that sets every number and quote beside the sentence in
  your sources it came from, grouped by slide, in your brand.

![A Harborlight sample deck slide with the number check: 19 of 19 numbers match, the evidence on the left, each number's source below](docs/shots/live/deck-numbers.jpg)

![Three designs of one deck, from the same sources and checked numbers (what each design puts forward can differ), with a count of numbers to check and layout problems under each](docs/shots/live/three-designs.jpg)

The full guide, with every screen, is the manual: https://linchpin.studio/hermes/imprint/manual/

## Requirements

- Hermes Desktop 0.22.6 or newer (`requires_hermes` in `plugin.yaml`).
- A model set up in Hermes. If you've chatted with Hermes, you already have one; if not, open Hermes Settings, Model.
  Imprint uses your main model unless you set **Imprint writing** under Settings, Models,
  Auxiliary. Reading a logo or brand sheet needs a model that can see images.
- Python libraries `pypdf`, `python-docx`, `python-pptx`, `reportlab` and `Pillow`. They are listed in `plugin.yaml`
  and installed with the plugin; Hermes asks before it installs them.
- Google Chrome, Chromium, Microsoft Edge or Brave, for the three designs, for exporting a designed piece to PDF or PNG,
  and for reading how a website looks. Everything else works without it. See "Where the three designs are drawn" below.
- A voice set up in Hermes (text-to-speech), only if you want the audio brief recorded. The script is made either way.

### Where the three designs are drawn

The designs, and the PDF and image export of a designed piece, are drawn by `htmldeck.py`, and a website's look is read
by `sitestyle.py`. Both start a headless browser, found the same way (`browser.py`): the `IMPRINT_BROWSER` environment
variable (a full path to a browser program) first; then the usual install places for your system (on a Mac,
`/Applications` and `~/Applications`; on Windows, the `Program Files`, `Program Files (x86)` and `AppData\Local`
folders); then program names on your `PATH` (`google-chrome`, `google-chrome-stable`, `chromium`, `chromium-browser`,
`chrome`, `microsoft-edge`, `brave-browser`; on Windows `chrome.exe`, `msedge.exe`, `brave.exe`). Google Chrome comes
first when several are installed, then Chromium, Microsoft Edge and Brave. The lookup runs each time, so installing a
browser needs no restart. If none is found, the Designs screen says so, with what to do, and **Design three options**
stays off; the Template version still works. Only the Mac lookup has been run on a real machine; the Windows and Linux
paths are covered by tests that stand in for those systems. Looking at a website in the browser (for a brand's style
brief) runs on a Mac and on Linux; on Windows, Imprint still reads the site's colors and fonts and says the browser look
is not available there yet. The browser is started with `posix_spawn`, never by forking Hermes's process; the website
reader's browser gets no open file of Hermes's except the pipe it is driven over.

## Install

From the Hermes plugin catalog:

```
hermes plugins install imprint
```

Hermes may ask to install a few helper libraries (the Python libraries listed under Requirements); say yes.

Or, in Hermes Desktop, open Capabilities, then Plugins, then Install from Git, and paste
`https://github.com/Dgardenhire/hermes-imprint`. Switch Imprint on under Capabilities, Plugins, then click **Imprint**
in the sidebar. It has three tabs: Notebook, Brands and Settings.

## Uninstall

1. If you want your Imprint data gone too, first open Imprint's **Settings** tab and use **Forget everything** (type the
   words it asks for). That deletes `<HERMES_HOME>/plugin-data/imprint/`: sources, brands, made pieces, recordings and
   settings. Files you exported through the save dialog are yours and stay where you saved them.
2. Remove the plugin. In Hermes Desktop: Capabilities, then Plugins, then the trash button beside Imprint, and confirm.
   From a terminal: `hermes plugins remove imprint`. Restart the gateway to unload its code.
3. Removing the plugin does not delete its data folder. If you skipped step 1, delete
   `<HERMES_HOME>/plugin-data/imprint/` yourself. The Python libraries installed with it (`pypdf`, `python-docx`,
   `python-pptx`, `reportlab`, `Pillow`) stay, since other plugins may use them.

## How long things take

Imprint sets no clock of its own for most steps; the time is your model's. The three designs take several minutes.
Each design is one model call that writes the whole piece, followed by a first round of drawing, looking and fixing, and
a second only if a problem is left. Up to two more rounds are allowed for hard layout problems (text over text, cut off,
outside the page, too small), and only while each round is clearing some of them; a fix that changes nothing ends the
loop. After the first look, a fix round shows the model only the slides that still have a problem, and only changed
slides are drawn again. The three designs run at the same time, and each shows its step and how long it has been going.
Each model call is cut off after 8 minutes. If a run is cut off (Hermes or the plugin helper restarted, or you pressed
Stop), the designs come back as "Interrupted. Press Design three options again." and the button works again. On a small or slow model, expect the long end. A recording stops being waited for after five minutes. Reading
a website's look stops after 150 seconds. You can leave the screen while the designs draw; the Studio shows a card
with the current step, and a job interrupted by a Hermes restart comes back as stopped with a Retry button.

## What leaves your computer

- Your ticked sources (with secrets redacted by Hermes), your questions, your brief and your notes go to the model you
  set in Hermes, under the auxiliary task "Imprint writing". If that model is a cloud service, the text goes to it.
  That covers summaries, answers, outlines, scripts, the three designs and their fixes.
- While drawing the three designs, Imprint shows your model a picture of each draft so it can fix it. Those pictures
  carry your content to the model.
- The audio script and the brand's delivery notes go to your own Hermes text-to-speech provider. If that provider is
  an online service (the Hermes default, Edge, is Microsoft's online voice), the script goes to it.
- A logo or brand sheet you ask Imprint to read goes to your model as an image.
- A web address you add as a source goes first to your own Hermes web tool (`web_extract`), which fetches it with the
  web backend you set in Hermes (it may be a cloud service). If that tool is not set up, Imprint fetches the page
  itself through Hermes's SSRF-safe client (`tools.url_safety`): public addresses only, every redirect checked, 20
  seconds to answer and 60 in all, read in a stream and stopped at a size limit, gzip or deflate only. Private, local
  and odd addresses are refused before anything is sent.
- **Build from a website**, and a website named as a reference in **Help me build a brand**, fetch the page and up to
  10 style sheets on the same site the same way. Building from a website also opens the site in Chrome: the home page
  and up to three pages it links to, read only. Imprint reads and respects robots.txt first, never types, clicks or
  signs in, and uses a throwaway Chrome profile. Everything Chrome requests goes through a small checking proxy that
  Imprint runs on 127.0.0.1 and that refuses non-public addresses. Pictures of those pages and measurements of their
  styles go to your model, which writes the style brief.
- Each web request carries your internet address, as any web request does. Nothing else leaves: no telemetry, no
  usage reporting, no other hosts.

## What Imprint touches on your computer

- It writes only to `<HERMES_HOME>/plugin-data/imprint/` (sources, passages, brands, outputs, recordings, settings,
  and a `debug.log` of the last 200 lines of error kinds and reply shapes, never what you wrote), to short-lived
  scratch folders it deletes afterward, and to a path you pick in the save dialog. One exception: if the
  `IMPRINT_DATA_DIR` environment variable is set, everything Imprint stores goes to that folder instead. The local test
  harness uses it; Hermes never sets it.
- **Environment variables it reads.** `IMPRINT_BROWSER` (which browser to draw with) and `IMPRINT_DATA_DIR` (where to
  keep its data). Neither holds a secret, and neither is needed.
- It reads outside that folder only the files you pick, the recording your Hermes voice hands back (copied into the
  data folder), and the folders you grant in a folder import, where it reads only the files it names (for an Open
  Design package: `manifest.json`, `tokens.css`, `DESIGN.md`, `design-tokens.json`; for a Claude Design folder or
  `.zip`: `design-system.json`, `tokens.json`, `tokens.css`, up to 8 font files in `fonts/` and up to 4 logo files in
  each `assets/` folder named for a logo) and releases the folder when it is done. A `.zip` is checked for size,
  file count, unpack ratio, paths that climb out and links before anything is read. Every upload is read in a stream
  and stopped at 25 MB.
- **Shell commands and other processes.** Chrome is started as a child process, with a scratch profile that is
  deleted afterward, to draw the designs and their PDF and image exports (headless; each page it draws carries a content
  security policy that blocks every network request) and to look at a website when you build a brand from one. On a Mac, Imprint also runs the system
  command `sips` to draw the first page of a one-pager as a small preview; without it, the preview is a brand card.
  Both are started only by a button you press and end with their job.
- **Background work.** Model calls, web reads, recordings and drawing run on background threads inside Hermes. The
  checking proxy is a thread that exists only while a website is being read. Nothing runs unless you press a button.
- **Credentials.** Imprint stores and reads none. No self-updates.
- **What it registers.** No tools, hooks or middleware: the "Imprint writing" model task, a desktop page and the
  page's own API. It calls three of your own Hermes tools by fixed name: `text_to_speech` (the audio brief),
  `web_extract` (a web address you typed), and `image_generate`. The shipped page has no control that asks for
  pictures, so `image_generate` is reached only by a request to the plugin's own API that sets a `pictures` flag on a
  deck; see `docs/SECURITY-AUDIT.md`. Nothing a model writes can choose a tool.
- "Forget everything" on the Settings tab deletes the whole data folder and database after you type the words.

## Disclosures

- Use brands only for organizations you own or have permission to use. You are responsible for what you make with
  them.
- Imprint ships no third-party logos. Four of the earlier starter brands adapt color and type values from Open Design
  packages (Apache-2.0, with MIT upstreams; see `NOTICE`). Some of those packages imitate a real company's public look;
  the adapted brands carry neutral names, never a company's name, logo or mark, and where a package named a licensed
  typeface the brand uses a bundled OFL font. The US Web Design System starter follows a public domain design system
  (GSA's work is CC0, its fonts are OFL); it carries no logo, seal or government banner, and documents made with it do
  not claim to come from any agency.
- Fonts embedded in a PowerPoint file are never reused. Fonts whose license forbids embedding are refused. Imprint
  never downloads a font; it uses the OFL fonts it ships and the fonts you add to a brand.
- Bundled fonts are under the SIL Open Font License 1.1 (`fonts/OFL.txt`). Credits: Anton, Barlow and Barlow
  Condensed, Courier Prime, Crimson Pro, DM Serif Display, Instrument Serif, Inter, Libre Caslon Display, Lora (The Lora
  Project Authors), Merriweather, Montserrat (The Montserrat Project Authors, Julieta Ulanovsky), Public Sans, Source
  Sans 3 and Source Serif 4. `fonts/OFL-montserrat.txt` and `fonts/OFL-lora.txt` are their own license files;
  `fonts/SOURCES.txt` records where each file came from.
- The sample sources in `samples/` describe a made-up literacy group.
- Imprint is an independent community plugin. It is not made or endorsed by Nous Research.

## Development

```
cd tests && /usr/bin/python3 -m unittest discover -s .
node --test tests/js/*.test.mjs             # the fast-open copy (desktop/src/firstpaint.js)
node ../hermes-ui-kit/scripts/build.mjs .   # hermes-ui-kit checked out beside this repo
```

Status and what is left: `docs/STATUS.md`. Live test: `docs/LIVE-TEST.md`. Changes: `CHANGELOG.md`.

MIT license.
