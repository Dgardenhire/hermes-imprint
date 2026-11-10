# DRAFT PR description (not submitted)

Title: `plugin-catalog: add imprint (brand kits for briefs, decks and audio)`

Re-pin before opening: the `sha` and every image URL in `imprint.yaml` must point at the pushed commit, and the
screenshots should be swapped for real Hermes captures from the Tuesday live test (the current ones are harness
renders: the real page and real backend answers inside a mock Hermes window).

---

## Imprint

Imprint turns your sources (PDFs, Word files, web pages, transcripts, notes) into a one-page brief, a slide deck
or a spoken audio brief that looks and sounds like your organization, and checks every number and quote against
the sources before you export.

What a prompt or a skill can't do here:

- **A brand kit is a real object.** Colors with roles set by measured WCAG contrast, font files, a logo, voice
  rules, a layout family and rules for every page. Imprint's own renderers own the look; the model only writes
  into a fixed structure.
- **The same kit drives every format.** The PowerPoint carries the kit on its slide master, the PDF embeds the
  kit's fonts, the audio brief's delivery follows the kit's voice notes. One source set, one look, three formats.
- **Two kits side by side.** The same facts as two press proofs, each with crop marks, the kit's color bar and a
  colophon that admits any font substitution.
- **Checked before export.** Each number and quote is matched to a source passage; a wrong citation is corrected,
  and a number that isn't in the sources blocks export until it is fixed, removed or kept on purpose.
- **Many kits.** Ten starter kits (nine original kits worked out for different readers, plus the public-domain US
  Web Design System), unlimited kits of your own, and Help me build a kit, which proposes three kits that really
  differ and keeps a record of recent looks so they don't repeat. Kits import from pasted colors, CSS, design
  tokens, Open Design packages, a Claude Design zip or folder, PowerPoint and Canva files, a website, or a logo
  read by your own model, each shown as a proof before it is saved.

Overlap: Podcast Studio (merged) makes two-host audio from any text. Imprint's audio is one narrator through the
user's own Hermes voice and is one of three formats tied to a brand kit; it does not use edge-tts directly.
folio (open) indexes and cites a library; Imprint makes branded outputs from a chosen source set.

### Screenshots

| | |
|---|---|
| Two proofs, two kits | `docs/shots/proofs-light.png` |
| A number not in the sources, blocked | `docs/shots/proofs-flagged-light.png` |
| Deck filmstrip | `docs/shots/deck-dark.png` |
| Audio brief | `docs/shots/audio-light.png` |
| Kits | `docs/shots/kits-light.png` |
| An import as a proof before save | `docs/shots/kits-draft-light.png` |

Demo video (under 90 s; sped-up parts marked 2x): link to be added.

### Disclosures (rule 13)

- **Model calls** go to the user's own Hermes model through the plugin LLM helper, under the auxiliary task
  "Imprint writing" (Settings, Models, Auxiliary). Source text is redacted with Hermes's redactor first. A logo or
  brand sheet goes to the model as an image only when the user asks Imprint to read one.
- **Speech** goes through the user's own Hermes `text_to_speech` tool with the kit's delivery notes. If the provider
  is the default (Edge), script text goes to Microsoft's online voice service. That is the user's Hermes setting.
- **Network calls of its own:** only web addresses the user enters (page sources, a site to build a kit from,
  reference sites in Help me build a kit), through `tools.url_safety`'s SSRF-safe client: public addresses only,
  every redirect checked, 20 seconds to answer and 60 in all, streamed and capped (gzip or deflate only, unpacked within the cap), the page plus up to 10 same-site stylesheets.
  No other hosts. No telemetry.
- **Reads** only files the user picks, and in a folder import only the named token, font and logo files; the
  folder grant is released after. Zip, Word and PowerPoint files are checked for size, unpack ratio, climbing
  paths, links and XML entities before reading.
- **Writes** only `$HERMES_HOME/plugin-data/imprint/` and paths the user picks in the save dialog.
- **Background work:** model calls, web reads and recordings run on threads inside Hermes; each ends with its job.
  No child processes, no shell commands.
- **Credentials:** none stored or read. No self-updates.
- **Registers** no tools, hooks or middleware: one auxiliary model task, a Desktop page and a dashboard API. So
  nothing runs unattended, under cron or from the messaging gateway.
- **Bundled data:** 18 OFL font files with `fonts/OFL.txt` and `fonts/SOURCES.txt` (each file's SHA-256). No binaries.
- **Python dependencies:** `pypdf>=6.0,<7`, `python-docx>=1.1,<2`, `python-pptx>=1.0,<2`, `reportlab>=4.0,<6`.
- **Desktop page:** imports only `@hermes/plugin-sdk`, `react` and `react/jsx-runtime`; built with esbuild from
  `desktop/src/plugin.js`.

### Checks run

- `hermes plugins validate` equivalent in a scratch HOME: 16 checks pass, 0 warnings.
- `scripts/validate_plugin_catalog.py docs/catalog/imprint.yaml`: valid.
- Unit tests: 181, all passing (`cd tests && python3 -m unittest discover -s .`).
- gitleaks on every commit: no leaks. bandit: no high-severity findings.
- Live run in Hermes Desktop 0.23.0: see `docs/LIVE-TEST.md` (to be filled in).

`requires_hermes ">=0.22.0"`, the same floor in `plugin.yaml`. Folder imports are feature-detected, so older
Hermes versions get the file and zip routes instead.

Imprint is an independent community plugin. It is not made or endorsed by Nous Research.
