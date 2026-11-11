# Imprint security audit

Independent audit, Nov 8, 2026, against the hackathon security bar (SECURITY-BAR.md, items 1 to 10) and the
must-fix in the Imprint spec. The auditor did not build Imprint. Code audited: `main` at `408cc05` (Fonts offline,
stage 5). Fixes landed as `audit:` commits on `main`, `37f1d40` through `81e0b2c`, not pushed.

Ground rules kept: no `hermes` command was run, nothing was installed into `~/.hermes`, and `~/.hermes/.env`,
`auth.json` and the Keychain were never read. Hermes source files were read (never config or secrets). Two probes
ran the Hermes venv's Python against Hermes's `tools/url_safety.py` with `HOME` and `HERMES_HOME` pointed at an
empty scratch folder and `HERMES_ALLOW_PRIVATE_URLS=false`, so no profile was read.

## Verdict

Pass, with two residual items for Damon (R1, R2). The must-fix is closed: every web fetch now counts decoded
bytes and never holds more than its cap whatever the server sends, and every upload is capped while it streams,
before anything parses or spools it. Eight findings were fixed, each with tests that fail on the original code.
No secrets, no high static-analysis findings, no shell, no subprocess, no telemetry. Tests: 218 before, 244 after,
all passing.

## Tools run

| Tool | Command | Result |
|---|---|---|
| gitleaks 8 | `gitleaks git .` (26 commits, about 3 MB) and `gitleaks dir .` | No leaks, before and after the fixes. The repo's `.gitleaks.toml` allowlist is one regex for font face ids (`b-inter-700-normal`). Run without it: 338 hits, all `generic-api-key` on those ids in `harness/fixtures.json`. The allowlist is narrow and right. |
| pip-audit | `uvx pip-audit -r` the four declared ranges (resolves the newest in range) | 0 known vulnerabilities: pypdf 6.21.4, python-docx 1.2.0, python-pptx 1.0.2, reportlab 5.1.0, lxml 6.1.3, pillow 13.0.0, typing-extensions 4.16.0, xlsxwriter 3.3.1, charset-normalizer 3.5.2. |
| pip-audit | the range floors, `--no-deps --disable-pip` | pypdf 6.0.0: 101 advisories (infinite loops, long runtimes, memory exhaustion from crafted PDFs), fixed by 6.21.4. Finding F8. python-docx 1.1.0, python-pptx 1.0.0, reportlab 4.0.0: none. |
| pip-audit | Hermes's own pins | pillow 12.3.0 (what this Mac's Hermes venv has): 39 advisories, fixed in 13.0.0. Residual R1. pypdf 6.21.4, lxml 6.1.3, reportlab 5.1.0, python-docx 1.2.0, python-pptx 1.0.2: none. |
| npm audit | n/a | No `package.json` or lockfile in the repo. `desktop/plugin.js` is a prebuilt bundle whose only imports are `@hermes/plugin-sdk`, `react` and `react/jsx-runtime`. |
| bandit 1.8 | `uvx bandit -r . -x ./tests,./harness` (7,696 lines) | 0 high, 4 medium, 11 low. Medium: B314 x2 (`ElementTree.fromstring`, imports.py:723 and :1021) and B608 x2 (service.py:167, :170). Low: B405 x2 (same XML imports), B110 x9 (`try/except/pass` around best-effort cleanup and optional font/logo drawing). All justified below. |
| semgrep | `uvx semgrep scan --metrics=off --config p/python --config p/security-audit --config p/secrets --config p/javascript --config p/owasp-top-ten` (52 files, tests included) | 2 results, both `use-defused-xml` at imports.py:713 and :1020. Justified below; F7 tightened the first. |
| Hermes SSRF probe | `is_safe_url` on 25 addresses (isolated home) | 24 blocked: 127.0.0.1, localhost, 0.0.0.0, [::1], 2130706433, 0x7f000001, 127.1, 017700000001, 169.254.169.254, [::ffff:127.0.0.1], 10/8, 192.168/16, 172.16/12, 100.64/10 (CGNAT), [fe80::1], userinfo and backslash tricks (`example.com@127.0.0.1`, `127.0.0.1#@example.com`, `127.0.0.1\@example.com`), file:, ftp:, gopher:, metadata.google.internal, localtest.me and 127.0.0.1.nip.io (DNS to loopback). Only https://example.com passed. |
| Live fetch | Imprint's `fetch` through the real Hermes client | example.com read; httpbin gzip and deflate read whole; httpbin brotli refused ("couldn't unpack"); a 100 KB body stopped at a 64 KB cap; http://127.0.0.1:8770 refused. |
| Real Starlette check | `_upload` with Starlette 1.3.1 from the Hermes venv | A small multipart file comes through; a 60 MB multipart body with no Content-Length is refused after 405 of 960 chunks. |

### Justifications for what the scanners report

- **XML (B314, B405, use-defused-xml).** `_xml` (PowerPoint theme and slide parts) refuses any part with a NUL
  byte (UTF-16 and UTF-32), any `<!DOCTYPE` or `<!ENTITY` in any letter case, and, since F7, any declared
  encoding other than UTF-8, before parsing; parse errors are a plain refusal. Without a DOCTYPE there are no
  entities to expand and no external entities to fetch. `svg_problem` refuses DOCTYPE and ENTITY in the decoded
  text and parses a `str`, so Python ignores any encoding declaration. python-docx and python-pptx parse with
  lxml and `resolve_entities=False`. `defusedxml` is in the Hermes venv but not a declared dependency, so it is not
  relied on.
- **B608.** `service.passages_for` builds `IN (?,?,...)` from the count of ids; the ids themselves are bound
  parameters, and the route only accepts ids matching `s_[a-f0-9]{12}`.
- **B110.** Each `except: pass` guards cleanup (closing a stale connection, removing a temp file) or an optional
  drawing step (a logo the PDF can't place). None hides a security decision.

## The must-fix

> ingest.py downloads the whole response and only then trims it... Stream it, refuse early on a Content-Length
> over the cap, count DECODED bytes while reading, stop at the cap, and say so plainly. Tests: an oversized
> response, a gzip bomb, and a missing Content-Length all stop at the cap. Apply the same rule to every fetch and
> upload in Imprint.

**Closed.** Before this audit the builder had moved to `client.stream` and counted `aiter_bytes()`, with tests
that fed already-decoded chunks to a stand-in client. Two gaps were left, both closed here:

- **Fetch (F1).** httpx inflates each network chunk whole before Imprint's count sees it, so a 64 KB gzip chunk
  could become 64 MB at once, and a brotli or zstd stream (decoded when those packages are installed) far more.
  Measured with the real httpx client: a 200 MB gzip bomb now peaks under 24 MB for a 2 MB cap.
- **Uploads (F2).** The multipart branch of `_upload` called Starlette's `request.form()`, which spools file parts
  to a temporary file with no size limit, so the 25 MB check ran only after the whole body was on disk.

Every fetch goes through `ingest.fetch` (web sources, site kits, up to 10 stylesheets, Help me build a kit
references). Every upload goes through `_upload` or `_read_capped` (sources, kit imports, logo, fonts, the 40 MB
folder-import JSON).

## Findings

| ID | Severity | Where | Status |
|---|---|---|---|
| F1 | Medium | ingest.py:410 `_Inflate`, :452 `fetch` | Fixed, `37f1d40` |
| F2 | Medium | dashboard/plugin_api.py:160 `_upload` | Fixed, `0177c08` |
| F3 | Medium | sitekit.py:56-196 | Fixed, `6d33127` |
| F4 | Low | store.py:197 `inside_root`, :207 `write_bytes`; service.py:450 | Fixed, `6002908` |
| F5 | Low | ingest.py:162 `read_pdf` | Fixed, `79d2bc7` |
| F6 | Low | imports.py:1030 `svg_problem`, :1045 `jpg_problem`; kits.py:458 `set_logo` | Fixed, `65b159b` |
| F7 | Low | imports.py:712 `_xml` | Fixed, `48495f9` |
| F8 | Medium | plugin.yaml:15 | Fixed, `871142e` |
| R1 | Low | Pillow version (Hermes's choice) | Open, for Damon |
| R2 | Low | plugin.yaml:10 `requires_hermes` | Open, for Damon |

**F1. Web reads could inflate far past the cap before it was checked.** *Scenario:* a person adds a web page, or
reads a kit from a site, whose server answers with a small gzip body that inflates to gigabytes, or with brotli,
or with compressed padding that inflates to nothing so the read never ends, or trickles bytes under the
20-second per-read timeout. *Fix:* `fetch` reads `aiter_raw()` and inflates with zlib asking for no more than the
room left under the cap; only identity, gzip and deflate are accepted, and Imprint asks for only those
(`Accept-Encoding: gzip, deflate`); compressed bytes are capped at twice the cap; the whole read has a 60-second
deadline. *Tests:* `F1_FetchInflatesWithinTheCap` (8): real-httpx gzip bomb peak memory, unasked-for encodings
refused, empty deflate blocks stop, trickle stops at the deadline, only gzip and deflate are asked for, small
gzip, zlib, raw-deflate and plain pages read whole, every redirect hop re-checked (loopback, metadata, file:,
localhost, gopher:), only web schemes accepted. Six of them fail on the original code.

**F2. Multipart uploads were spooled whole before the 25 MB check.** *Scenario:* any multipart POST to
`/sources/file`, `/kits/import/file`, `/kits/<id>/logo` or `/kits/<id>/fonts` with a body of any size is written
to the system temp folder (outside plugin-data) by Starlette before Imprint looks at it. *Fix:* the body is read
with `_read_capped` (refused on a declared length over the cap before any read, and as soon as the streamed bytes
pass it), then only those bytes go to `request.form(max_files=1, max_fields=8)`. *Tests:*
`F2_MultipartUploadsAreCappedFirst` (3); all three fail on the original code.

**F3. The site reader's regexes backtracked quadratically.** *Scenario:* a site a person reads a kit from (or
names as a reference) serves a 2 MB stylesheet with no braces, or a page with thousands of unclosed `<style`,
`<meta`, `<link` or `<title` tags. Measured on the original code: 40 KB of brace-free CSS took 10 s and 60 KB of
`<style>` tags took 2 s, growing with the square of the size; 2 MB is hours. Python's regex engine holds the GIL,
so the whole Hermes backend stalls, not just the job (the original-code test run hung past its 400-second
timeout). *Fix:* rules are found in one pass over the braces, comments are stripped with `str.find` (also in
`imports.css_blocks`), and tags with `str.find`. *Tests:* `F3_SiteReaderIsLinear` (3): four hostile stylesheets
and five hostile pages each finish in under 10 s, and the readers still find the same colors, fonts, theme color,
same-site links and title.

**F4. The one write path did not check where it wrote.** *Scenario:* defense in depth. Every caller built safe
names (route ids are checked against fixed patterns, file names are Imprint's own), but `store.write_bytes`
would write anywhere it was pointed, and the audio copy in `_gather_audio` bypassed it. *Fix:* `write_bytes`
(and `write_json` through it) resolves the target and refuses a climbing path, an absolute path elsewhere, or a
link that points out; the audio copy goes through it. *Tests:* `F4_EveryWriteStaysInTheDataFolder` (2).

**F5. Long PDFs were read in full before the keep limit applied.** *Scenario:* a 25 MB PDF (a file, or a web
address that serves one) with thousands of text-heavy pages is extracted page by page, then all but 400,000
characters are dropped. *Fix:* extraction stops past the keep limit and at 2,000 pages; the page count still
reports the file. pypdf's own per-stream limit (75 MB) and F8's floor cover a single hostile stream. *Test:*
`F5_PdfReadingStopsAtTheKeepLimit`.

**F6. Logo checks missed SVG `<style>` elements, `url()` paints and JPEG size.** *Scenario:* an SVG logo carries
`<style>@import url(https://...)</style>` or `fill="url(https://...)"`; inert today because Imprint shows SVGs
only as `<img>` data URLs and never rasterizes them, but a future loader would follow them. A 2 MB JPEG declares
a 60,000-pixel frame that reportlab and python-pptx would unpack in full. Kit PNG uploads were checked for the
signature only. *Fix:* both SVG forms are refused (local `url(#id)` still passes); JPEGs are read for their frame
size and held to 4096 px a side; kit PNG uploads use `png_problem`. *Tests:* `F6_LogoChecks` (3); the existing
kit test now uses a real 1 x 1 PNG.

**F7. PowerPoint XML in another declared encoding.** *Scenario:* a theme part declares EBCDIC, where the byte
search for DOCTYPE can't see one. Expat rejects such encodings today ("unknown encoding", tested on expat 2.2.8
and 2.6.3), but as an unhandled `ParseError` that surfaced as a 500. *Fix:* any declared encoding but UTF-8 is
refused before parsing, and a part that doesn't parse gets the damaged-file message. *Tests:*
`F7_OfficeXmlIsUtf8Only` (3).

**F8. The pypdf floor allowed versions with published DoS advisories.** *Scenario:* pip keeps an installed pypdf
that satisfies `>=6.0,<7`; 6.0.0 has 101 advisories reachable from a crafted PDF. *Fix:* `pypdf>=6.21.4,<7`,
which is Hermes's own documents pin, so it never conflicts. *Test:* `F8_DependencyFloors`.

**R1. Pillow (open, Low).** reportlab and python-pptx open logo images with Pillow, whose version Hermes
controls. This Mac's Hermes venv has Pillow 12.3.0 (39 advisories, fixed in 13.0.0); Hermes's current
`pyproject.toml` overrides Pillow to 13.0.0 for itself and plugin workspaces. What reaches Pillow from Imprint is
narrow: PNG or JPEG only, signature-checked, at most 5 MB and 4096 px a side. *Recommendation:* update Hermes
before the live test. Don't declare `pillow>=13` in Imprint yet: on an older Hermes it could collide with
browser-harness's exact `pillow==12.3.0` pin and block the install.

**R2. `requires_hermes ">=0.22.0"` (open, Low).** Both routes Imprint uses (`create_ssrf_safe_async_client` with
its connect-time guard, and `register_auxiliary_task`) exist at the v0.22.0 tag. But `is_safe_url` gained its
authority-ambiguity refusal (`01fbd26`) and IDNA metadata comparison (`c5d9f20`) between 0.22.0 and 0.23.0. On
0.22 the connect-time guard still validates the address actually dialed, so this is depth, not a hole.
*Recommendation:* raise to `">=0.23.0"`, as the spec proposed, unless supporting 0.22 users matters more. Damon's
call.

## Tried and held

- **SSRF.** Private, loopback, link-local, CGNAT, metadata, IPv4-mapped IPv6, decimal, hex and octal forms,
  userinfo and backslash confusion, DNS names that resolve to loopback: all refused by Hermes (probe above).
  Imprint re-checks every redirect hop itself (`follow_redirects=False`, five hops), and `normalize_url` refuses
  any scheme but http and https before a request is built. **DNS rebinding:** Hermes's client re-resolves and
  validates at TCP connect and dials the validated IP (source read at `tools/url_safety.py:444-604`, present at
  v0.22.0). With a proxy set in the environment, Hermes hands DNS to the proxy by design.
- **Zips** (Claude Design `.zip`, `.pptx`, `.docx`). Checked before any read: entry count (5,000; 2,000 for
  PowerPoint), declared total (200 MB; 100 MB; 150 MB), per-entry ratio over 100 above 1 MB, paths that are
  absolute or climb (Windows and POSIX), symlink entries. Nothing is ever extracted to disk, so zip slip has no
  target. A zip that lies about sizes is held to the declared size by Python and fails its CRC (tested).
- **Folder imports.** The pane reads only the named files (`readFolder`, desktop/src/plugin.js:980) and
  releases the grant; the backend takes at most 60 entries in a 40 MB body and re-checks every relative path.
- **Injection into the page, HTML, PDF and PowerPoint.** The pane renders proof nodes from a fixed tag list, text
  as text, images only as `data:image/` URLs, style keys only as `--custom-properties`; no `innerHTML`, `eval` or
  `fetch`. The HTML export escapes text and attributes and strips `;{}<>` from style values. Every reportlab
  `Paragraph` input is escaped; model markup (an `<img>` pointing at a system file, `<a href=file:>`, `<font name=...>`)
  lands only as inert `/Title` text, with no image, link or launch objects (`RedTeam` tests). Kit colors are hex
  only.
- **Prompt injection.** Sources reach the model as delimited, redacted data; replies are schema-checked JSON;
  extra fields (`delete_kits`, `export_path`, a logo path) are dropped. The model has no tools: the one tool
  Imprint calls is `text_to_speech`, by fixed name, with text, an output path inside plugin-data and the kit's
  delivery notes (`RedTeam` test with a source ordering image generation, sends and a write to `~/.ssh`). Kits
  change only when a person presses Save on a draft; required lines are never imported from any route. Export of
  anything not found in the sources needs a person's Keep or Remove click. Exfiltration through TTS is bounded to
  the script the person asked for, sent to the voice provider the README names.
- **Fonts.** 18 bundled TTFs, each with an OFL license string in its name table, plus `fonts/OFL.txt` and
  `fonts/SOURCES.txt` (the SHA-256 of every file, checked by the tests). No code
  fetches a font (`test_fonts_offline`); fonts whose `fsType` forbids embedding are refused; fonts inside a
  PowerPoint are never reused.
- **What leaves the computer.** Matches the README: source text to the person's model, audio scripts to their
  Hermes voice, an image to their model only on request, and only the web addresses they enter. No telemetry.
  README and catalog text were updated for the new limits, for the recording Imprint copies back from the Hermes
  voice (its one read outside plugin-data that a person didn't pick), and for capped uploads.
- **Catalog rules.** Desktop bundle imports only the SDK and React. No compiled binaries: 13 TTF, 40 PNG, the rest
  text. `provides_tools`, `provides_hooks` and `provides_middleware` are empty, matching `register(ctx)` (one
  auxiliary task). No shell, subprocess, stored credential, self-update or background process beyond job threads.

## Smaller notes (no fix needed for release)

- FastAPI parses `body: dict` routes (paste, ask, kit edits) whole before Imprint's field caps; the pane is the
  only client and Hermes guards the dashboard.
- A Claude Design zip entry that fails its CRC raises `BadZipFile`, shown as the generic error, not the
  damaged-zip message.
- Ask sends the last six chat turns with a question, whatever sources they used: the person's own text to the
  person's own model.
- The size message rounds caps under 1 MB up to "1 MB" (stylesheet reads use 2 MB, pages 5 MB, so people won't
  see it).
- `test_imports.Css.test_css_pathological_input_is_fast` has a 2.5-second budget that fails on both the original
  and the fixed code when the machine is loaded (load average near 39 during this audit) and passes when it is
  quiet.
- Tracked docs and code no longer carry the builder's home-folder paths (README, `desktop/src/plugin.js`,
  `docs/LIVE-TEST.md` now use relative or placeholder paths). Older commits still contain them; rewrite history
  only if that matters before the repo goes public.

## What remains on the bar

- Item 9, fresh-machine install: a clean Hermes on macOS, plus Windows and Linux VMs. Not run in this audit
  (no `hermes` commands). `docs/LIVE-TEST.md` covers macOS.
- The AI persona testers from the bar's tester note.
- R1 and R2 above.

## Test counts

Before the audit: 218 tests, all passing. After: 244 (26 in `tests/test_security_audit.py`), all passing with
`cd tests && /usr/bin/python3 -m unittest discover -s .`. Every fix's tests were run against the original code
from `git archive 408cc05`: F1 (6 of 8), F2 (3 of 3), F4, F5, F6, F7 and F8 fail there, and F3 hangs past its
400-second timeout. The two red-team tests pass on both and guard what already held.

## Second review

Independent review, Nov 8, 2026, of everything after the first audit's last commit (`0e14f76`) up to `d22a5d0`:
the brand guide PDF route, logo recoloring and the reversed-logo upload, pasted-label parsing, PowerPoint color
ranking, the Flyer and Report layouts and auto type sizing, HTML export changes, required-lines opt-in, the five
added bundled fonts, and `harness/live`. Fixes landed as `audit:` commits `6329151` through `af3eadf` on `main`, not
pushed. Same ground rules: no `hermes` command, nothing installed into the Hermes home, and its env file, auth file
and the Keychain never read. Hermes source was read; its plugin scanner was run as a library from the Hermes venv
with `HOME` and `HERMES_HOME` pointed at an empty scratch folder.

### Verdict

Pass after fixes. Two medium denial-of-service findings in the new brand guide reader (F9, F10) were real and
cheap to trigger from a file under 20 KB; F9 also reached source PDFs, which the first audit's F5 had not covered.
Five findings fixed, each with tests that fail on `d22a5d0`. No secrets, no new scanner findings in shipped code.
Tests: 291 before, 304 after, all passing on system Python 3.9 (pypdf 6.13.3) and on Python 3.11 with the
declared floors (pypdf 6.21.4, Pillow 13.0.0, reportlab 5.1.0, python-pptx 1.0.2).

### Tools run

| Tool | Command | Result |
|---|---|---|
| gitleaks 8 | `gitleaks git .` and `gitleaks dir .`, before and after | No leaks. |
| pip-audit | `uvx pip-audit -r` the four declared ranges | No known vulnerabilities. |
| bandit | `uvx bandit -r . -x ./tests,./harness` | 0 high, 4 medium, 11 low: the same B314/B405/B608/B110 set the first audit justified, at new line numbers (`imports.py` 897/907 and 1304/1305). |
| bandit | `uvx bandit -r ./harness` | `harness/live/drive.py`: subprocess (fixed argv, `sys.executable`, `qlmanage`, `pdftoppm`) and `urlopen` on its own `http://127.0.0.1` base. Test tooling; never loaded by Hermes. |
| semgrep | `uvx semgrep scan --metrics=off` with `p/python`, `p/security-audit`, `p/secrets`, `p/javascript`, `p/owasp-top-ten` | 5 results: the two known `use-defused-xml`, and three in `harness/live/drive.py` (the same subprocess and urllib calls). |
| Hermes plugin scanner | `tools.plugin_guard.scan_plugin` on a `git archive` of the tree | Verdict `caution` at both `0e14f76` and `d22a5d0`. The one high finding in the whole tree was this report's own sentence quoting a system-file path; reworded, the tree scans `safe` (0 high, 90 medium, 6 low). Everything else is medium or low (test fixtures, the bundle's base64 upload code). |
| Hostile-file probes | hand-built PDFs and PowerPoints, timed with the real pypdf and python-pptx | Below. |

### Findings

| ID | Severity | Where | Status |
|---|---|---|---|
| F9 | Medium | imports.py `read_pdf_guide`; ingest.py `read_pdf`; dashboard/plugin_api.py `post_kit_import_file` | Fixed, `6329151` |
| F10 | Medium | imports.py `guide_fonts`, `_family_from`, `guide_name` | Fixed, `ba0a828` |
| F11 | Low | imports.py `_slide_size`, `read_pptx` | Fixed, `33cab14` |
| F12 | Low | harness/live/server.py | Fixed, `b3d5a82` |
| F13 | Low (depth) | render_html.py `_css_value` | Fixed, `af3eadf` |
| R3 | Low | `harness/` ships in every install | Open, for Damon |

**F9. One small PDF page could extract for hours and hold all its text.** *Scenario:* a brand guide PDF (or a
source PDF, or a web address serving one) whose page paints the same form XObject many times. pypdf walks the
form's operators on every paint (it allows 5,000 paints per page) and keeps all the text. Measured: a 22 KB file
painting a 7 MB form 10 times took 73 s and returned 8 MB of text; at 300 paints the original-code test was still
running after 10 minutes. The first audit's F5 limits apply between pages, not inside one. The guide reader ran in
the request handler, so the dashboard's event loop (this pane and every other plugin) waited with it. *Fix:*
`ingest.pdf_page_text` walks each page with pypdf's visitors and stops on a character budget and a deadline checked
on every operator, inside forms too; the stop is a `BaseException` so pypdf's per-form `except Exception` can't
swallow it. The guide gets 20 s and its 200,000-character budget, a source 90 s and its 400,000. The longest
uninterruptible step left is pypdf parsing one stream, which its own 2,000,000-token limit bounds (a few seconds).
File imports (.pdf, .pptx, Claude Design .zip) now run in `asyncio.to_thread`. *Tests:*
`F9_PdfReadsAreBoundedInsideForms` (5): text-heavy form bomb for the guide and for sources, a text-free form bomb
stopped by the clock, the stop surviving pypdf's handler, and the route reading off the event loop. All five fail
on the original code.

**F10. The guide's font patterns were quadratic.** *Scenario:* guide text (up to 200,000 characters) with a long
run of "if a" or of weight words. `FALLBACK`'s lazy name groups rescan to the end from every "if"; the weight strip
backtracks over every run. Measured: 42 s and 86 s, each a single regex call holding the GIL, so the whole Hermes
backend stalls. *Fix:* type specs are read only from lines of 400 characters or fewer, the spec is cut to 200
characters before the strip, and fallbacks are read only around the first 20 short lines that mention installing
(the lines either side, for wrapped sentences). The persona guide reads identically. *Tests:*
`F10_GuideFontPatternsAreLinear` (2); the hostile cases fail on the original code.

**F11. A huge PowerPoint size crashed the ranking.** *Scenario:* a 400-digit `cx` on a shape or the slide is a
valid int that overflows the float division (`OverflowError`, a 500 rather than a plain refusal). *Fix:* sizes are
clamped to the format's ranges and a shape's share of the slide to 1. *Tests:* `F11_PowerPointSizesAreHeldToTheFormat`.

**F12. The live harness could be imported, and answered any site.** *Scenario:* Hermes installs the whole repo,
and its loader makes the plugin folder a package, so `harness/live/server.py` is importable; importing it replaced
`fastapi` in `sys.modules` and set `IMPRINT_DATA_DIR`. While it runs, any page open in the same browser could post
a `text/plain` body to it (tested: a cross-site POST planted a source), and a DNS-rebound name could read its
answers. *Fix:* the module raises `ImportError` unless run as a script; a foreign `Host` or an `Origin` other than
its own page gets a 403. *Tests:* `F12_LiveHarnessStaysOutOfHermes` (2) and
`test_live_harness.LiveMode.test_refuses_other_sites_and_rebound_names`.

**F13. Export tokens could carry `url()` (depth).** The export stripped `;{}<>` from custom-property values but not
`url(`, `image-set(` or CSS escapes, and its rules paint tokens into url-taking properties
(`background:var(--k-band)`). Every token is a checked hex color, number or font stack, so nothing reaches this
today; such a value is now dropped. *Test:* `F13_HtmlExportTokensCannotLoad`.

**R3. `harness/` ships in every install (open, Low).** Hermes has no exclude list: it clones the repo (or a
subdirectory). The harness, its persona files (a PDF, a PowerPoint, a Word file, a zip) and `drive.py` land in the
plugin folder. After F12 nothing there can run inside Hermes, and no shipped module or the desktop bundle refers to
it (tested). *Recommendation:* before catalog submission, move the plugin into a subfolder (`imprint/`) and point
the catalog at it, so the subdirectory install leaves `harness/`, `tests/` and `docs/shots/` behind.

### Tried and held

- **Brand guide PDF.** Encrypted files refused. A 200,000-entry page tree stops at pypdf's array limit. 40 pages
  sharing one 70 MB content stream finish at the 20 s deadline. The fill-color scan reads at most 2 MB of each
  page's content. 12,000 distinct color codes read in under 2 s and keep 24.
- **Fonts named in a PDF are never fetched.** Names only match uploaded or bundled faces; CSS stacks are quoted
  inside custom properties used only by `font-family`.
- **Logos.** Reversed logos pass the same `svg_problem`, `png_problem` and `jpg_problem` checks and write only
  `logo-reversed.<kind>` in the kit folder; `safe_logo` accepts no other name. Knockout SVGs only change colors and
  add a root `fill` to a checked SVG; SVGs are never rasterized. A 4096 px PNG knocks out in 0.5 s.
- **Pasted labels and PowerPoint ranking.** Linear on hostile input; names cut to 40 characters, usage to 200, shown
  as text. PowerPoint parts still go through `_xml` and `zip_ok`.
- **Flyer and Report layouts, auto sizing.** New reportlab `Paragraph` inputs are all escaped; the fill search runs
  at most 7 builds.
- **HTML export.** Text escaped, tags from the fixed list, images only `data:image/`, footnote links only
  `#ip-src-<digits>`, no script, no external URL in its CSS.
- **Required-lines opt-in.** Only the person's own click changes it; the route validates both ids; the model has no
  route to it.
- **Bundled fonts.** Five added files match `fonts/SOURCES.txt` hashes (tested); all 18 have `fsType` 0.

### Smaller notes

- Keep on a removed menu item: a `sections.<n>.items.<m>` path past the end gives a 500, not a refusal.
- `_family_from` keeps trailing weights when the line has more words after them ("Montserrat bold bold x").

### Test counts

291 before, 304 after (12 in `tests/test_second_review.py`, 1 in `tests/test_live_harness.py`), all passing with
`cd tests && /usr/bin/python3 -m unittest discover -s .`. Every new test was run against `git archive d22a5d0`:
all fail there (F9's text-bomb tests by running past a 10-minute timeout).

## Notebook build (Nov 8, 2026)

Self-review of the `notebook` branch (three-pane notebook, studio kits, scene engine, graphic and picture slides).
Not an independent audit: an outside reviewer should still sign off. Same ground rules as above.

### Links: SSRF, rebinding and redirects

A link source now goes first to the person's own Hermes `web_extract` tool (`ctx.dispatch_tool`), then, only when
that tool is not set up, to Imprint's own reader (`ingest.fetch`). Flagged by an automated review as a possible
time-of-check/time-of-use and redirect differential. Checked against the Hermes source, and it holds:

- **Before anything is sent**, `service._safe_public_url` refuses any scheme but http and https, any user name or
  password in the address, and any host Hermes's `is_safe_url` calls private (`tools/url_safety.py`). An unsafe
  address never reaches the tool (`test_notebook.Links.test_private_local_and_odd_addresses_never_reach_the_tool`).
- **Inside the tool**, Hermes re-runs `async_is_safe_url` on every URL before any extract backend is called
  (`tools/web_tools.py`, `web_extract_tool`, the "SSRF protection" loop), so the tool is guarded on its own.
  Damon's configured extract backend is the remote Nous gateway, so the fetch itself happens off this machine.
- **Imprint's own reader** (the fallback) builds its client only from `tools.url_safety.create_ssrf_safe_async_client`,
  which resolves, validates and dials the checked IP at TCP connect (closing DNS rebinding) and keeps Host and SNI.
  It runs with `follow_redirects=False` and checks `is_safe_url` again on every hop itself, five hops at most
  (`ingest.fetch`). No module builds a plain httpx client, `urllib` or `requests` call
  (`test_notebook.FallbackClient`, both tests: a source scan, and a run of the fallback with `httpx.AsyncClient`
  and `httpx.Client` replaced by a trap that fails the test if either is built).
- **The check on the URL the tool reports back** (`_extract` refuses a final address that is not public, and a
  result the tool marks "Blocked") is belt and braces, not the guard. The guards are the pre-dispatch check, the
  tool's own check and the connect-time pinning above.

No redesign needed.

### The rest of the notebook build

- **Tools Imprint calls now: three, each by fixed name.** `text_to_speech` (unchanged), `web_extract` (only with an
  address the person typed, after the checks above) and `image_generate` (only when the person ticks "Ask my Hermes
  image tool for a picture slide", at most two per deck). The red-team test that a hostile source can't reach any
  other tool still holds; `test_no_picture_asked_for_means_no_image_tool_call` adds that no tick means no image call.
- **Image prompts carry words only.** The model writes the picture's description from the sources, so a hostile
  source could try to smuggle data out through it. `service.picture_prompt` strips web addresses, email addresses,
  long codes and every character but letters and basic punctuation, and caps it at 400 characters before it goes to
  the person's image provider (test: an address, an email, a 22-character key and digits all removed).
- **The picture comes back only from Hermes's image cache.** A local path is read only if it resolves inside
  `<HERMES_HOME>/cache/`, is a PNG, JPEG or WebP, and is under 20 MB; an https URL goes through the SSRF-safe
  reader. Every picture is decoded and re-encoded by Pillow as a plain JPEG (no metadata), so an SVG or anything
  else never reaches a page or a file. A path outside the cache folder (the data folder, a system file, or a path that climbs out of the cache) is never read
  (tests).
- **Chat citations.** A citation survives only if it names a passage from a ticked source that was inside the
  corpus the model saw; others are dropped with their brackets (tests: a foreign source's passage, an invented label,
  a passage past the part of a long source that fit).
- **Notes** are capped (60 notes, 4,000 characters), ids are pattern-checked, a pinned answer is copied from the
  stored chat (the page can't supply its citations), and notes go into the brief as the person's points; the
  grounding check still looks every number up in the passages.
- **New routes** (`/sources/include`, `/sources/{id}`, `/sources/{id}/summarize`, `/notes`, `/chats` delete,
  `/kits/specimen`) validate ids by pattern and bodies by shape; the specimen route renders a built-in sample only.
- **The pane** renders scene nodes through the same fixed tag list (positions, sizes and colors only as CSS custom
  properties; pictures only as `data:image/` URLs). The bundle check (no eval, no dynamic import, no innerHTML) passes.
- **Fonts**: five files added (`fonts/SOURCES.txt`), all OFL with `fsType` 0, copied from local copies, not
  downloaded; their hashes are pinned and tested. Not yet matched against the upstream release files.

Not done here: semgrep, pip-audit and an outside reviewer on this branch.

336 tests on the notebook branch, all passing (`test_imports.Css.test_css_pathological_input_is_fast` again failed
once under a load average near 26 and passed when rerun).
