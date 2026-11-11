# Imprint designs API

Three model-designed options for a deck, a one-pager or a graphic, side by side in the Studio; pick one, or mix slides across
them; edit a line; revise in words; restore a version; export. Routes live in `dashboard/designs_api.py`, the work in `designs.py`
and `htmldeck.py`. Everything that calls a model or draws with Chrome starts a job and returns `{job}`.

| Route | Body | Returns |
|---|---|---|
| `POST /outputs/{id}/designs` | `{kit_id?}` | `{job}` (kind `designs`): writes three designs at once (Editorial, Data board, Statement), draws, looks, fixes (2 rounds, up to 2 more while a layout problem is left). One design failing never costs the others. |
| `GET /outputs/{id}/designs` | | the view: `options[{d, name, blurb, status, step, elapsed, error, slides, flags, problems, thumbs[]}]` (`elapsed` is seconds since a running option began; an option left `writing` with no job running is returned as `failed` with "Interrupted. Press Design three options again.")`, `browser{ok, message}` (`ok` false when no Chrome, Chromium, Edge or Brave is found; `message` says what to do), `final{label, slides[{n, from, thumb, elements[], notes}], problems}`, `flags[{slide, value, status, key, kept}]`, `open_flags`, `versions[]`, `formats`, `building` |
| `GET /outputs/{id}/designs/slide/{which}/{n}` | | `{img}` a 1100 px picture; `which` is a direction or `final` |
| `POST /outputs/{id}/designs/pick` | `{direction}` or `{picks:[{d, i}]}` | the view. A whole design, or the mix: slide `n` of the result is slide `i` of design `d`. Slides keep their own scoped CSS. |
| `POST /outputs/{id}/designs/edit` | `{slide, el, text}` | `{job}` (kind `designs_apply`): one line of text replaced, cleaned, traced, drawn again; a new version |
| `POST /outputs/{id}/designs/revise` | `{instruction, slide?}` | `{job}`: the model changes what was asked and nothing else; cleaned, drawn, traced; a new version |
| `POST /outputs/{id}/designs/restore` | `{version}` | the view |
| `POST /outputs/{id}/designs/keep` | `{key, on}` | the view. A number flagged by the trace can be kept on purpose; export waits for every flagged number to be fixed or kept |
| `POST /outputs/{id}/designs/export` | `{format}` | `{path, name}`: `pdf` (vector, brand fonts embedded), `pptx` (deck only: each slide is a picture, with its notes and the passages it cites in the notes pane), `png` (one-pager, graphic) |
| `POST /kits/{kit_id}/style-brief` | `{url}` | `{job}` (kind `kit_style_brief`): opens the site in headless Chrome (read-only, robots respected, home page plus up to three linked pages), photographs and measures it, and writes a style brief into the kit |

The three directions share one content brief, the notebook's own checked deck, one-pager or graphic doc, so the words and the
number trace are the same in all three. The kit is the brand (colors, fonts, logo, voice, required lines), its layout family and
density are a starting style the model may follow or leave, and its style brief (if it has one) is the design language.

## The number trace

Every number in a designed slide, in text, in a chart label or on a chart mark (`data-value`), must sit inside an element that
carries `data-source="P3 P7"`, and must be found in, or worked out from two numbers in, those passages. A number written as a word
is a claim too. Statuses: `exact`, `computed`, `moved` (cited to the wrong passage; it is in another), `unsourced` (no citation),
`missing`. Anything but exact or computed is a flag; export waits.

## What the model's markup can't do

Tags and attributes are an allowlist; no script, event handler, link, form, frame, address or picture (only the logo). A `<style>`
block with any escape, `<`, fetching or running construct, counter, or `content` other than none or a digit-free string is dropped
whole. `<style>` inside `svg` is dropped. A second pass must change nothing. The page has a policy that allows no network and no
script but Imprint's measuring script (by hash); its report carries a per-render nonce and is accepted only once, from a console
line. The browser's own parse is checked against the allowlist, and a slide it finds unsafe is blanked and the deck drawn again.
