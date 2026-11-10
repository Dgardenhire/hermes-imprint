# Imprint

Your sources, in your look. Imprint turns PDFs, Word files, web pages, transcripts and notes into a one-page
brief, a slide deck or a spoken audio brief that looks and sounds like your organization. It sets the same facts
in two brand kits side by side and checks every number and quote against your sources before you export.

Runs on your own Hermes model and your own Hermes voice. No keys.

![Two proofs of the same brief, one per kit, each with crop marks, the kit's color bar, a colophon and its checks](docs/shots/proofs-light.png)

## What it does

- **A notebook in three panes.** Sources on the left (files, links, pasted notes; a short summary of each; tick what
  counts; open any source at the passage a citation points to). A chat in the middle that answers only from the
  ticked sources and numbers every claim back to its passage; pin an answer as a note. The Studio on the right:
  pick a kit and make a slide deck, a graphic, an audio brief or a one-pager from the ticked sources and your
  notes, watch each step, open it large, export it.
- **Studio kits.** Five kits built the way studios build: Counsel (consulting exhibits), Chart Room (the data desk),
  Stage (the keynote), Folio (the book) and Meridian (the modernist poster). Each has its own type pairing and
  label face, a measured scale, a grid, a color system checked for contrast, and its own composition for every
  slide type (title, section, content, big number, quote, exhibit chart, comparison, timeline, picture, closing) and
  for its graphic. Any kit, including one you import, gets one of these five deck systems.
- **Kits you can hold.** A kit is a real object: colors with roles checked for contrast, fonts, a logo, voice
  rules, a page layout, a deck system and rules for every page. Besides the studio kits, 16 earlier starters stay
  available (nine originals, four looks adapted from Open Design packages under plain names, two layout starters
  and the public-domain US Web Design System). Make as many kits of your own as you like.
- **Help me build a kit.** Say what can't change (name, exact colors, required fonts), who reads it and what they
  need to do, and pick up to three references. Your model proposes three kits that really differ. Imprint keeps a
  record of your recent looks, so new kits don't repeat the last ones.
- **Kits from what you already have.** Paste color codes, drop a CSS or design-token file, pick an Open Design
  package, drop a Claude Design `.zip` (or pick its folder), drop a PowerPoint (a Canva design downloads as one),
  read a website, or let your own model read a logo or brand sheet. On a Mac, a Keynote theme comes in through
  Keynote's PowerPoint export. Every import is shown as a proof before you save it. Every route reads the same on
  Mac, Windows and Linux (Windows paths, zips written on Windows, files with a byte order mark, folder names in
  any case).
- **Written once, voiced per kit.** The content is written from your sources once. Each kit rewords it in its own
  voice, and Imprint puts back any sentence where a number, quote or citation changed.
- **Checked before it goes out.** Every number and quote is matched to a source passage. Anything not found in
  your sources blocks export until you fix it, remove it, or keep it on purpose. The check proves a number is in
  your sources; it can't tell whether a source is right.
- **Hover a number, see its source.** Every checked number in a proof carries its source number. Hover it, or tab
  to it, and a card quotes the source line with the number marked, names the source and its page or timestamp,
  and says whether it is an exact or a close match. A number that isn't in your sources says so.
- **Honest about fonts.** If a kit's font can't be used, the colophon names what was set in its place. Imprint
  never downloads a font: it uses the OFL fonts it ships and the fonts you add to a kit.
- **Exports.** One-pager: PDF, a proof PDF with crop marks, and a self-contained HTML page. Deck: PowerPoint with
  the kit on the slide master (theme colors, theme fonts, background, logo), titles in title placeholders and points
  as native bullets, and a PDF of the slides with the fonts embedded. Graphic: PNG, SVG (fonts embedded) and PDF.
  Audio brief: the recording, the script as text, and a script PDF. The PowerPoint names the kit's fonts; on a
  computer without them, PowerPoint substitutes (the fonts are in Imprint's `fonts/` folder, all OFL).

The same kit drives every format. A deck, a one-pager and an audio brief made from one source set share the same
facts, colors, type and voice rules.

## Install

From the Hermes plugin catalog, once listed:

```
hermes plugins install imprint
```

Or from this repository:

```
hermes plugins install https://github.com/Dgardenhire/hermes-imprint
```

Hermes asks before it installs the four Python libraries Imprint lists (`pypdf`, `python-docx`, `python-pptx`,
`reportlab`). Then open **Imprint** in the Hermes desktop sidebar. Needs Hermes 0.22.0 or newer. Folder imports
(Open Design, a Claude Design folder) use the desktop's folder access when your Hermes has it; on an older
Hermes, Imprint offers the file or `.zip` route instead.

To choose which model writes for Imprint, open Settings, Models, Auxiliary, and set **Imprint writing**.

The manual is in [docs/MANUAL.md](docs/MANUAL.md).

## What leaves your computer

- Source text (with secrets redacted by Hermes) goes to the model you set in Hermes, under the auxiliary task
  "Imprint writing" (Settings, Models, Auxiliary). If that model is a cloud service, the text goes to it.
- Audio scripts go to your own Hermes text-to-speech provider, with the kit's delivery notes. If that provider is
  an online service (the Hermes default, Edge, is Microsoft's online voice), the script goes to it.
- A logo or brand sheet you ask Imprint to read goes to your model as an image.
- Web addresses you add as sources go first to your own Hermes web tool (`web_extract`), which fetches them with the
  web backend you set in Hermes (it may be a cloud service). Imprint refuses private, local and odd addresses before
  anything is sent.
- When you tick "Ask my Hermes image tool for a picture slide", a short description of a photograph, written by
  your model from your sources and stripped to plain words (no addresses, codes or digits), goes to your own Hermes
  image tool (`image_generate`) and its provider. Imprint reads the picture back only from Hermes's own image cache.
- When the web tool isn't set up, web addresses you add, sites you build a kit from, and sites you name as references in Help me build a kit are
  fetched with Hermes's SSRF-safe client (public addresses only, every redirect checked, 20 seconds to answer and
  60 seconds in all): the page and up to 10 stylesheets on the same site, each read in a stream and stopped at its
  size limit. Imprint asks only for gzip or deflate compression and unpacks it itself, never past that limit.

Nothing else. No telemetry, no usage reporting, no other hosts.

## What Imprint touches on your computer

- It writes only to `<HERMES_HOME>/plugin-data/imprint/`. An export is saved only where you pick in the save
  dialog.
- It reads outside that folder only the files you pick, the recording your Hermes voice hands back (copied into
  the data folder), a picture your Hermes image tool made (read only from `<HERMES_HOME>/cache/`, re-encoded, copied
  into the data folder), and the folders you grant in a folder import, where it
  reads only the files it names (for an Open Design package: `manifest.json`, `tokens.css`, `DESIGN.md`,
  `design-tokens.json`; for a Claude Design folder or `.zip`: `design-system.json`, `tokens.json`, `tokens.css`,
  up to 8 font files in `fonts/` and up to 4 logo files in each `assets/` folder named for a logo) and gives the
  folder back when it is done. A `.zip` is checked for size, file count, unpack ratio, paths that climb out and
  links before anything is read. Every upload is read in a stream and stopped at 25 MB; nothing past that is held
  or written anywhere. Every file Imprint writes is checked to land inside its data folder.
- It registers no tools, hooks or middleware, only the "Imprint writing" model task, a desktop page and its API.
  Nothing runs unless you press a button on the page.
- Slow work (model calls, web reads, recordings) runs on background threads inside Hermes. No separate processes,
  no shell commands, no stored credentials, no self-updates, no telemetry.
- "Forget everything" on the Storage tab deletes the whole data folder and database after you type the words.

## Disclosures

- Use kits only for brands you own or have permission to use. You're responsible for documents made with a kit.
- Imprint ships no third-party logos. Four starter kits adapt color and type values from Open Design packages
  (Apache-2.0, with MIT upstreams; see `NOTICE`). Some of those packages imitate a real company's public look; the
  adapted kits carry neutral names, never a company's name, logo or mark, and where a package named a licensed
  typeface the kit uses a bundled OFL font and its colophon says so. The US Web Design System kit follows a public
  domain design system (GSA's work is CC0, its fonts are OFL); it carries no logo, seal or government banner, and
  documents made with it don't claim to come from any agency.
- Fonts embedded in a PowerPoint file are never reused. Fonts whose license forbids embedding are refused.
- Bundled fonts are under the SIL Open Font License 1.1 (`fonts/OFL.txt`). Credits: Anton, Barlow and Barlow
  Condensed, Courier Prime, Crimson Pro, DM Serif Display, Instrument Serif, Inter, Libre Caslon Display, Lora (The Lora
  Project Authors), Merriweather, Montserrat (The Montserrat Project Authors, Julieta Ulanovsky), Public Sans, Source
  Sans 3 and Source Serif 4. Montserrat and Lora come from the Google Fonts repository; their own licence files are
  `fonts/OFL-montserrat.txt` and `fonts/OFL-lora.txt`, and `fonts/SOURCES.txt` records where each file came from.
- Sample sources in `samples/` describe a fictional city.
- Imprint is an independent community plugin. It is not made or endorsed by Nous Research.

## Development

```
cd tests && /usr/bin/python3 -m unittest discover -s .
node ../hermes-ui-kit/scripts/build.mjs .   # hermes-ui-kit checked out beside this repo
/usr/bin/python3 harness/make_fixtures.py
/usr/bin/python3 -m http.server 8794 --bind 127.0.0.1 --directory .   # then sh harness/shoot.sh
```

The screenshots in `docs/shots/` are rendered by the harness: the real page and real backend answers, made with a
scripted stand-in model, inside a mock of the Hermes window.

Status and what is left: `docs/STATUS.md`. Live test: `docs/LIVE-TEST.md`. Changes: `CHANGELOG.md`.

MIT license.
