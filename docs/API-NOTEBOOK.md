# Letterpress notebook API: the contract

Owner: the AI lane (`loop1-ai`). Written Sun Nov 8, 2026, about 10 PM CT, before any AI-lane code.
Readers: the canvas lane, lane A (the notebook agent), the product owner.

Every route below is mounted under `/api/plugins/letterpress/` and reached from the pane through `ctx.rest`.
The pane's request limit is 25 seconds (`desktop/src/plugin.js:26`). So **every route that calls a model
returns `{job: <job>}` at once**, and the result arrives through `GET /jobs/{id}` as `job.result` when
`job.status` is `done`. Nothing waits on a model inside a request.

Rule for this file: once published, no shape changes without (1) editing this file, (2) adding a dated line
under **Changes**, and (3) telling the canvas lane and the product owner.

Field names in `code` are exact. "Lane A" marks a route or shape lane A builds; the AI lane only lists it.

---

## 1. Shared shapes

### Job

```
GET /jobs/{id} ->
{ id: "j_0123456789ab", kind: "outline", status: "running" | "done" | "failed",
  step: "Reading 3 sources",                       // current step, plain words
  steps: [{text, at}],                             // every step with its start time (epoch seconds)
  result: <kind-specific, below> | null,
  error: "plain sentence" | null, error_code: "cut_off" | "model" | "refused" | "gone" | ... | null,
  params: {...}, created_at, updated_at }
POST /jobs/{id}/retry -> <job>                     // same kind, same params
```

A failed job always has one plain sentence in `error` with one next step ("Press Retry.").

### Chip (a citation the pane draws)

```
{ ref: "P4", n: 1, source_n: 1, source: "FY26 Program Report", locator: "The waitlist", source_id: "s_..." }
```

`n` is the chip's number inside its own answer or card. `source_n` is the source's number in the Sources
pane (1-based, in the order the sources were ticked). `locator` is the place inside the source, as the
reader shows it (a heading, `para. 3`, `page 2`, `00:04:12`).

### Line (one source sentence, with the matched words marked)

```
{ before: "At year end, ", match: "287", after: " adults were on the waitlist, most of them at the Eastgate and Riverside sites." }
```

`match` is empty when no single span matched (a "missing" claim shows its closest sentence as `before`).

### Written-by label

Every AI result carries `by: "Written by your Hermes model"`. The pane shows it in 12px under the result,
with no sparkle icon.

---

## 2. Routes that exist today (`dashboard/plugin_api.py` at `0faa05e`)

Unchanged by this lane. Listed so the canvas lane has one map. `<source>`, `<chat>`, `<note>`, `<proof>`
are the rows `service.source_row`, `service.chat_row`, `service.note_row` and `service.proof` build.

| Method and path | In | Out |
|---|---|---|
| `GET /state` | | `{sources:[<source>], kits, outputs, jobs:[<job running>], prefs, usage, deps, storage, layouts, kinds, ready_kinds, fonts, today, proof_css, notes:[<note>], deck_systems}` |
| `POST /prefs` | `{pair?, output?, tab?, rail?, kit?}` | the saved prefs |
| `POST /settings` | `{daily_token_cap: int \| null}` | `usage` |
| `GET /jobs/{id}` | | `<job>` |
| `POST /jobs/{id}/retry` | | `<job>` |
| `POST /sources/file` | multipart or `{filename, data: base64}` | `{job}` (kind `read_file`) |
| `POST /sources/text` | `{title, text}` | `{source}` |
| `POST /sources/url` | `{url}` | `{job}` (kind `read_url`) |
| `POST /sources/include` | `{ids:[s_...], on: bool}` | `{sources}` |
| `GET /sources/{id}` | | `{source, passages:[{ref, locator, text}]}` (the reader) |
| `POST /sources/{id}/summarize` | | `{job}` (kind `summarize`) |
| `DELETE /sources/{id}` | | `{sources, storage}` |
| `GET /passages/{ref}` | | `{ref, text, locator, source_title, source_id}` |
| `POST /forget` | `{confirm: "forget everything"}` | `state` |
| `GET /kits/{id}`, `POST /kits`, `POST /kits/{id}`, `POST /kits/{id}/duplicate`, `DELETE /kits/{id}` | kit JSON | `kit_view` |
| `POST /kits/preview`, `POST /kits/specimen` | `{kit}` or `{kit_id, all?}` | draft view, specimen |
| `POST /kits/from-site`, `POST /kits/import`, `POST /kits/import/file`, `GET/POST/DELETE /kits/import/{draft}`, `POST /kits/import/{draft}/save` | | drafts and `{job}` (kinds `site_kit`, `image_kit`) |
| `POST /kits/guide` | `{fixed, subject, refs}` | `{job}` (kind `guide`, "Help me build a kit". Not the notebook guide.) |
| `POST/DELETE /kits/{id}/logo`, `/logo-reversed`, `POST /kits/{id}/fonts`, `GET /fonts/{key}` | | kit view, font bytes |
| `POST /outputs` | `{kind, source_ids, kit_ids, brief, note_ids?, pictures?}` (lane A adds `outline_id?`) | `{job}` (kind `make`) |
| `GET /outputs/{id}` | | output view, section 3 |
| `POST /outputs/{id}/kit` | `{kit_id, slot}` | `{job}` (kind `voice`) |
| `POST /outputs/{id}/decide` | `{key, action: "keep" \| "remove"}` | output view |
| `POST /outputs/{id}/required` | `{kit_id, on}` | output view |
| `POST /outputs/{id}/edit` | `{path, text}` | output view (a person's own typed edit; no model) |
| `POST /outputs/{id}/export` | `{kit_id, format}` | `{path, ...}` |
| `GET /outputs/{id}/audio/{kit}`, `POST /outputs/{id}/speak` | | audio, `{job}` (kind `speak`) |
| `DELETE /outputs/{id}` | | `{outputs, storage}` |
| `GET /chats`, `DELETE /chats` | | `{chats:[<chat>]}` |
| `GET /notes`, `POST /notes` `{chat_id \| text}`, `DELETE /notes/{id}` | | `{note?, notes}` |
| `POST /ask` | `{question, source_ids}` | `{job}` (kind `ask`; result `{chat}`; sends the last six turns) |

**Lane A:** the sample switch.

| Method and path | In | Out |
|---|---|---|
| `POST /sample/open` | `{}` | `state`, with the three Harborlight sources marked `sample: true` (lane A defines the rest) |
| `POST /sample/close` | `{}` | `state`; the person's own sources, kits and outputs untouched |

---

## 3. The output view gains claims, slides, passages used and versions

`GET /outputs/{id}` keeps every field it has today. Each proof (`proofs[i]`) gains four fields. **Lane A**
wires them into `service.proof` and `scene.py`, using the helper `checks.claims_map` this lane ships
(section 6). Until then the canvas lane works from the fixture in section 8.

```
proof.claims = {
  "c12": {
    kind: "count" | "money" | "percent" | "quote",
    value: "287",                       // as shown on the slide
    status: "exact" | "close" | "computed" | "missing" | "kept" | "brief",
    ref: "P4" | null,                   // the passage that holds it (computed: the first operand's passage)
    source_n: 1 | null, source: "FY26 Program Report", locator: "The waitlist",
    line: <line> | null,                // missing: the closest sentence, match ""
    math: null | {
      op: "difference" | "sum" | "ratio" | "pct_change" | "bound",   // bound: one operand, "1,148, shown as about 1,150"
      operands: [{value: "1,148", ref: "P1", source_n: 1, source: "FY26 Program Report", locator: "Who we served", line: <line>},
                 {value: "936",   ref: "P1", ...}],
      result: "212",                    // the exact result at the precision shown, before "shown as"
      text: "1,148 − 936 = 212"         // ready to show; a percent reads "(1,148 − 936) ÷ 936 = 22.6%, shown as 23%"
    },
    slides: [2, 5],                     // frame indexes (0-based, frame 0 = the title slide) where this claim appears
    key: "slides.2.context|number|212", // the grounding key, for Keep on purpose and Fix it for me
    fixable: true                       // status missing: Fix it for me is offered
  }, ...
}
proof.slides = [ {i: 0, type: "title", title: "Demand is outgrowing our seats", refs: ["P1", "P4"], claims: ["c1", "c2"]}, ... ]
                // a graphic or a one-pager is one "slide" with i: 0
proof.passages_used = { "P4": {source_n: 1, source: "FY26 Program Report", locator: "The waitlist",
                               text: "At year end, 287 adults ...", slides: [2, 5]}, ... }
output.versions = [ {v: 1, created_at: 1762650000.0, reason: "Made", active: false},
                    {v: 2, created_at: 1762650300.0, reason: "Stronger headline, slide 3", active: true} ]
```

Rules that hold for every proof:

- **Dates, years, day numbers and slide numbers are never claims.** "October 21", "FY2027", "2026",
  "Slide 4" carry no underline and no card. `checks.is_date_number(text, start, end)` decides it.
- Status words, for the card: `exact` "Matches your source", `close` "Same number, written another way",
  `computed` "Worked out from your sources", `missing` "Not found in your sources", `kept` "Kept on purpose,
  not in your sources", `brief` "From your own request".
- Export is blocked while any claim is `missing` (today's gate, unchanged).
- **Scene tree.** Every claim's text span in `proof.tree` carries the data key `"tr": "c12"` on the node
  object (not a DOM attribute). The canvas underlines it (1px dotted) and finds its card by that key.
  Today's `ip-num` spans keep working beside it until lane A removes the superscript marks.

---

## 4. New AI routes (this lane, `dashboard/revise_api.py`)

All new routes start a job and return `{job}` at once, except the three version routes and the outline
save, which call no model.

| Method and path | In | Job kind | Model call |
|---|---|---|---|
| `POST /notebook/guide` | `{source_ids: [s_...]}` | `notebook_guide` | yes |
| `GET /notebook/guide` | | | no: the last guide, or `{guide: null}` |
| `POST /outlines` | `{source_ids, brief: {who, goal, length}, kind: "deck", ask?: <ask>}` | `outline` | yes |
| `GET /outlines/{outline_id}` | | | no |
| `POST /outlines/{outline_id}` | `{slides: [{title, type, refs}]}` (move, edit, delete, add) | | no: saved and re-checked |
| `POST /outlines/{outline_id}/rewrite` | `{index: 0-based slide}` | `rewrite_title` | yes |
| `POST /outputs/{id}/element-edit` | `{kit_id, slide: 0-based index into doc.slides, action: "shorter" \| "stronger" \| "chart" \| "insert" \| "typed", text?: "Add the quote after slide 4"}` | `element_edit` | yes, except a refused typed line |
| `POST /outputs/{id}/fix` | `{kit_id, key: <claim.key>}` | `fix_it` | yes |
| `POST /graphics/options` | `{source_ids, note_id?: n_..., text?: "the pinned answer"}` | `graphic_options` | yes |
| `POST /outputs/{id}/keep` | `{job_id, choice: 0}` | | no: applies one returned option as a new version |
| `POST /outputs/{id}/discard` | `{job_id}` | | no: marks the job's options discarded |
| `POST /outputs/{id}/undo` | `{}` | | no: one step back |

Job kinds already taken (unchanged): `summarize`, `make`, `speak`, `voice`, `read_file`, `read_url`,
`site_kit`, `image_kit`, `guide`, `ask`. This lane's: `notebook_guide`, `outline`, `rewrite_title`,
`element_edit`, `fix_it`, `graphic_options`.

Errors: a bad input is a 400 with one plain sentence (`{detail}`); a model failure ends the job as
`failed` with one plain sentence and Retry.

### 4.1 `notebook_guide` result

```
{ by: "Written by your Hermes model", source_ids: [...], created_at: 1762650000.0,
  guide: [ {text: "Harborlight enrolled 1,148 adult learners in FY2026, up from 936.", chips: [<chip>]} , ...],  // one paragraph, sentence by sentence
  asks: [ {id: "a1", who: "The board", what: "A one-page summary of the FY2027 budget request", by: "October 21",
           kind: "onepager" | "deck" | "graphic" | "audio", chips: [<chip>],
           brief: {who: "Board members", goal: "Vote on the FY2027 budget", length: "One page"}} ],
  questions: [ {text: "Reserves are 3.2 months against a 4-month target. Can we add a site while the budget rises $190,000?",
                chips: [<chip>, <chip>], suggestion: true} ] }
```

- A sentence, ask or question with no valid passage ref is dropped. Only refs the model was shown count.
- `asks` are the explicit requests in the sources, not ideas. `questions` are two or three likely
  questions built from tensions between passages, labeled as suggestions.
- The pane draws each ask with its chip and a **Make** button. Make sends `ask` into `POST /outlines`.

### 4.2 `outline` result, and the saved outline

```
{ by, outline_id: "ol_0123456789ab", kind: "deck", brief: {who, goal, length}, source_ids: [...],
  slides: [ {title: "Demand for adult literacy is outgrowing our five sites",
             type: "stat" | "content" | "exhibit" | "quote" | "comparison" | "timeline" | "section" | "closing",
             chips: [<chip>], refs: ["P1", "P4"], hint: null | "split", words: 9} ],   // 7 to 10 slides
  review: [ {text: "The closing now asks for the $190,000 increase", refs: ["P9", "P11"], chips: [<chip>]} ],  // 0 to 5
  warnings: ["Slide 4 has no source, so it was left out."] }
```

- `review` (round 5): after the draft, a second model call (`purpose: outline_review`, job step "Checking the
  outline as your reader would") reads the draft against the sources as the brief's reader and returns the revised
  outline. `slides` is the revised outline; `review` is what it changed, one short sentence each with its chips.
  Empty when the draft already made the case, or when the revision was not kept (a slide lost its source, it dropped
  more than one slide, or more titles failed the number check). A change note with a number the sources do not
  hold is never shown. The pane shows it under the outline as "Checked the outline:" and the notes.

- Titles are full sentences under 15 words with one claim. A chart title states the finding. A stat slide
  has one number. A title with two claims gets `hint: "split"` ("Split this?" in the pane); it is never
  changed on its own.
- `POST /outlines/{id}` takes the person's edited list and returns the same shape, re-checked (`hint`,
  `words`, chips). A slide whose refs are all unknown is refused with a sentence.
- **Lane A:** `POST /outputs` gains `outline_id`; the `make` job reads it with `revise.get_outline(outline_id)`
  and builds those slides in that order.

### 4.3 `rewrite_title` result

```
{ by, outline_id, index: 3, before: "<old title>",
  options: [ {title, chips, hint: null | "split", words}, {...}, {...} ] }   // three, all different
```

The person picks one; the pane saves the list with `POST /outlines/{id}`.

### 4.4 `element_edit` result

```
{ by, output_id, kit_id, slide: 2, action: "stronger",
  status: "ok" | "refused" | "unchanged",
  message: null | "I can shorten, strengthen, chart or add a quote. Try 'Add the quote after slide 4'.",
  before: <slide as in doc.slides>,
  options: [ {slide: <slide, same schema>, check: {status: "ok" | "missing", label: "All 3 numbers match your sources", items: [...]}} ],
            // shorter, chart, insert: one option; stronger: three
  insert_after: null | 4 }    // insert only: the new slide goes after this 1-based slide number
```

- `chart` needs two or more numbers on the slide that already pass the check; otherwise `status: "refused"`
  with a sentence.
- Every option is re-checked by `checks.grounding` before it is returned. An option that fails the check is
  dropped; if all fail, `status: "unchanged"` with a sentence.
- A typed line that names a field and gives its new words ("Change this slide's title to: ...", "Change the subtitle
  to ...", "Set the heading of slide 3 to ...", "Rename slide 2 to ...", "Title: ...") comes back as
  `action: "retitle"` with one option, and no model call is made. The result adds `path` (the doc field: `title`,
  `subtitle`, `slides.N.heading|label|subtitle|context`, or a designed slide's title element `cover.els.J` /
  `slides.N.els.J`), `frame` (0 is the title slide), `before_text`, `base_text`, and `options[0].text`. The body may
  carry `on: "title"` when the title slide is the one open. The new words are checked by `checks.grounding`; a number
  no source holds returns `status: "refused"` with a sentence naming it. Keep goes through `store.add_version`.
- Any other typed line that is not exactly "Add the quote after slide N" or "Add the point after slide N" returns
  `status: "refused"` and one plain sentence. No model call is made for it.
- The model never picks a tool, exports, deletes, or writes anything outside `plugin-data/letterpress`. It only
  returns slide JSON that this code checks.

### 4.5 `fix_it` result

```
{ by, output_id, kit_id, key, path: "slides.2.heading",
  status: "ok" | "unchanged",
  before: "1,200 learners in one year", after: "1,148 adult learners in one year",
  diff: [ {op: "del", text: "1,200"}, {op: "add", text: "1,148 adult"}, {op: "same", text: "learners in one year"} ],
  chips: [<chip>], check: {status: "ok", label: "Matches your source"} }
```

Returned only when `after` passes the check. Otherwise `status: "unchanged"` and the flag stays.

### 4.6 `graphic_options` result

```
{ by, source_ids, options: [ {form: "bars" | "figures" | "compare" | "timeline", spec: <content.VISUAL_SCHEMA doc>,
                              check: {status: "ok", label}} ],     // up to three, all different forms
  dropped: 0 }
```

Values come only from checked numbers. An option with a value that does not match its passage is dropped
and counted in `dropped`. Drawing a spec is lane A's renderer (`render_graphic.tree`).

### 4.7 Keep, Discard, Undo

```
POST /outputs/{id}/keep    {job_id, choice}  -> output view, with versions; the kept option is the new active version
POST /outputs/{id}/discard {job_id}          -> {ok: true}
POST /outputs/{id}/undo    {}                -> output view, one version back
```

Keep reads the option from the finished job on the server; the pane never sends slide JSON back. The doc
is re-checked once more before it is saved. These routes call lane A's version functions only (section 7).

---

## 5. Every new model call (for the README and catalog disclosure)

| Call (purpose) | Sends to the person's own Hermes model | When |
|---|---|---|
| `letterpress.notebook_guide` | the ticked sources' passages (redacted the same way as Ask) | Opening a notebook, or Refresh guide |
| `letterpress.outline` | the brief and the ticked sources' passages | Write the outline |
| `letterpress.rewrite_title` | one title, the brief, and that slide's cited passages | Rewrite this title |
| `letterpress.element_edit` | one slide's JSON and its cited passages | Shorter, Stronger headline, Turn into a chart, Add the quote |
| `letterpress.fix_it` | the flagged sentence and the closest passage across the output's sources | Fix it for me |
| `letterpress.graphic_options` | the pinned answer or text, and the passages it cites | Make a graphic from a note |
| `letterpress.argument`, `letterpress.argument_repair` | the brief and the ticked sources' passages (the repair adds the drafted case and its faults) | Make a deck with no outline (round 11), before the deck write |

All go through `runtime.Model.structured` (Hermes's `complete_structured`), with this lane's schemas.
Nothing calls the web, a tool or another service.

---

## 6. Helpers this lane ships in `checks.py` (for lane A)

- `checks.grounding(doc, passages, decisions, brief)`: unchanged signature. Items gain status
  `"computed"` with `math` (shape in section 3, without the `source_n` fields).
- `checks.trace_table(items, passages, idx, computed=False)`: cards for worked-out numbers carry `math` and
  `worked: true`. Their status is `"close"` by default, because today's pane has trace heads for five statuses
  only and throws on any other (`TRACE_HEAD[t.status] is not a function`, `desktop/src/plugin.js:338`). Pass
  `computed=True` once the pane has a head for it (request 7). The `claims` map always says `"computed"`.
- `checks.check_line(text, refs, passages, all_ids)` -> `{ok, refs, items}`: the same check for one free sentence.
- `checks.computed_match(raw, value, field_text, passages, refs)` -> `math` or `None`.
- `checks.is_date_number(text, start, end)` -> bool.
- `checks.claims_map(items, passages, idx, frame_of)` -> `(claims, passages_used, claim_of)`, where
  `frame_of(path) -> int` maps a field path to its frame index and `claim_of(path, raw) -> "c12" | None`
  tells `scene.py` which `tr` key a span gets.

---

## 7. Requests to lane A

1. **The mount line** in `dashboard/plugin_api.py`, after `router = APIRouter()` and the two `try` blocks:

   ```python
   importlib.import_module("letterpress_plugin_package.revise").routes().mount(router, "letterpress_plugin_package")
   ```

2. **Version functions** in `store.py`, the only way this lane touches `output_versions`:
   - `store.add_version(output_id: str, doc: dict, reason: str) -> int`: saves `doc` as the output's new
     neutral doc, re-renders its proofs, makes it active, returns `v`.
   - `store.undo(output_id: str) -> int`: makes the previous version active, returns its `v`; raises
     `ValueError("Nothing to undo.")` at version 1.
   - `store.versions(output_id: str) -> list` of `{v, created_at, reason, active}`.
   Until these exist, Keep and Undo answer 400 "Keep isn't wired yet." Discard works.
3. **Claims and `tr`**: in `service.proof`, call `checks.claims_map` with the grounding items and add
   `claims`, `slides`, `passages_used` to the proof; in `scene.py`, put `"tr"` on each claim span.
4. **Dates are not claims**: drop underlines and `ip-num` on spans where `checks.is_date_number` is true.
5. **Make from an outline**: `POST /outputs` accepts `outline_id`; the `make` job reads `revise.get_outline`.
6. **Stamp count**: "All N numbers match your sources." counts `exact`, `close` and `computed` claims.
7. **A trace head for worked-out numbers** in `desktop/src/plugin.js` (`TRACE_HEAD` and `TRACE_TONE`, line 324),
   for example `computed: n => n ? \`Worked out from source ${n}\` : 'Worked out from your sources'`, with
   `t.math.text` drawn above the line; then call `trace_table(..., computed=True)` in `service.proof`. Until then the
   card says "Close match in source 1" over the first operand's sentence, which is true of 1,148 but not of 212.

---

## 8. Fixture (Harborlight, for the canvas lane)

Passage refs are the ones `service.read_file` gives the two Harborlight files on a fresh data folder:
FY26 Program Report P1 to P5, board retreat notes P6 to P8. Note: for a source with headings, `ingest` writes the
locator wrapped in curly quotes (`“Who we served”`), and every route returns it that way today. The fixture shows
it without them; strip them when drawing "FY26 Program Report, Who we served".

```json
{
  "output": {
    "id": "o_8f2c1a9b0d3e",
    "kind": "deck",
    "title": "A sixth site for Harborlight",
    "versions": [
      {"v": 1, "created_at": 1762650000.0, "reason": "Made", "active": false},
      {"v": 2, "created_at": 1762650300.0, "reason": "Stronger headline, slide 3", "active": true}
    ],
    "proofs": [{
      "kit_id": "s_counsel",
      "status": "ready",
      "blocked": true,
      "slides": [
        {"i": 0, "type": "title", "title": "A sixth site for Harborlight", "refs": [], "claims": []},
        {"i": 1, "type": "exhibit", "title": "Demand is outgrowing our seats", "refs": ["P1", "P4"], "claims": ["c1", "c2", "c3", "c4"]},
        {"i": 2, "type": "stat", "title": "Up 23% in one year", "refs": ["P1"], "claims": ["c5"]},
        {"i": 3, "type": "stat", "title": "1,200 learners in one year", "refs": ["P1"], "claims": ["c6"]},
        {"i": 4, "type": "content", "title": "A $190,000 increase pays for the sixth site", "refs": ["P3", "P5"], "claims": ["c7"]},
        {"i": 5, "type": "stat", "title": "287 adults are still waiting", "refs": ["P4"], "claims": ["c3"]}
      ],
      "claims": {
        "c1": {"kind": "count", "value": "936", "status": "exact", "ref": "P1", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Who we served", "line": {"before": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five neighborhood sites, up from ", "match": "936", "after": " the year before."},
               "math": null, "slides": [1], "key": "slides.0.bars.0|number|936", "fixable": false},
        "c2": {"kind": "count", "value": "1,148", "status": "exact", "ref": "P1", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Who we served", "line": {"before": "In fiscal year 2026, Harborlight enrolled ", "match": "1,148", "after": " adult learners across five neighborhood sites, up from 936 the year before."},
               "math": null, "slides": [1], "key": "slides.0.bars.1|number|1148", "fixable": false},
        "c3": {"kind": "count", "value": "287", "status": "exact", "ref": "P4", "source_n": 1, "source": "FY26 Program Report",
               "locator": "The waitlist", "line": {"before": "At year end, ", "match": "287", "after": " adults were on the waitlist, most of them at the Eastgate and Riverside sites."},
               "math": null, "slides": [1, 5], "key": "slides.0.bars.2|number|287", "fixable": false},
        "c4": {"kind": "count", "value": "212", "status": "computed", "ref": "P1", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Who we served", "line": {"before": "In fiscal year 2026, Harborlight enrolled ", "match": "1,148", "after": " adult learners across five neighborhood sites, up from 936 the year before."},
               "math": {"op": "difference",
                        "operands": [
                          {"value": "1,148", "ref": "P1", "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served",
                           "line": {"before": "In fiscal year 2026, Harborlight enrolled ", "match": "1,148", "after": " adult learners across five neighborhood sites, up from 936 the year before."}},
                          {"value": "936", "ref": "P1", "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served",
                           "line": {"before": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five neighborhood sites, up from ", "match": "936", "after": " the year before."}}],
                        "result": "212", "text": "1,148 − 936 = 212"},
               "slides": [1], "key": "slides.0.note|number|212", "fixable": false},
        "c5": {"kind": "percent", "value": "23%", "status": "computed", "ref": "P1", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Who we served", "line": {"before": "In fiscal year 2026, Harborlight enrolled ", "match": "1,148", "after": " adult learners across five neighborhood sites, up from 936 the year before."},
               "math": {"op": "pct_change",
                        "operands": [
                          {"value": "1,148", "ref": "P1", "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served", "line": null},
                          {"value": "936", "ref": "P1", "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served", "line": null}],
                        "result": "22.6%", "text": "(1,148 − 936) ÷ 936 = 22.6%, shown as 23%"},
               "slides": [2], "key": "slides.1.value|number|23%", "fixable": false},
        "c6": {"kind": "count", "value": "1,200", "status": "missing", "ref": "P1", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Who we served", "line": {"before": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five neighborhood sites, up from 936 the year before.", "match": "", "after": ""},
               "math": null, "slides": [3], "key": "slides.2.value|number|1200", "fixable": true},
        "c7": {"kind": "money", "value": "$190,000", "status": "computed", "ref": "P5", "source_n": 1, "source": "FY26 Program Report",
               "locator": "Recommendation to the board", "line": {"before": "Staff recommend that the board approve an FY2027 budget of ", "match": "$1,610,000", "after": ", which adds a sixth site at the Eastgate branch library and two site coordinators."},
               "math": {"op": "difference",
                        "operands": [
                          {"value": "$1,610,000", "ref": "P5", "source_n": 1, "source": "FY26 Program Report", "locator": "Recommendation to the board", "line": null},
                          {"value": "$1,420,000", "ref": "P3", "source_n": 1, "source": "FY26 Program Report", "locator": "Money", "line": null}],
                        "result": "190,000", "text": "1,610,000 − 1,420,000 = 190,000"},
               "slides": [4], "key": "slides.3.heading|number|190000", "fixable": false}
      },
      "passages_used": {
        "P1": {"source_n": 1, "source": "FY26 Program Report", "locator": "Who we served",
               "text": "In fiscal year 2026, Harborlight enrolled 1,148 adult learners across five neighborhood sites, up from 936 the year before.", "slides": [1, 2, 3]},
        "P3": {"source_n": 1, "source": "FY26 Program Report", "locator": "Money", "text": "Operating expenses for FY2026 were $1,420,000.", "slides": [4]},
        "P4": {"source_n": 1, "source": "FY26 Program Report", "locator": "The waitlist",
               "text": "At year end, 287 adults were on the waitlist, most of them at the Eastgate and Riverside sites. The average wait was nine weeks.", "slides": [1, 5]},
        "P5": {"source_n": 1, "source": "FY26 Program Report", "locator": "Recommendation to the board",
               "text": "Staff recommend that the board approve an FY2027 budget of $1,610,000, which adds a sixth site at the Eastgate branch library and two site coordinators.", "slides": [4]}
      },
      "tree_sample": {"t": "div", "c": "sc-node sc-note", "k": [
        {"t": "span", "x": "212", "tr": "c4"},
        {"t": "span", "x": " more adults than last year"}
      ]}
    }]
  },
  "jobs": {
    "notebook_guide": {
      "by": "Written by your Hermes model",
      "source_ids": ["s_290d5ff51a37", "s_51976a6db455"],
      "guide": [
        {"text": "Harborlight enrolled 1,148 adult learners in FY2026, up from 936 the year before.",
         "chips": [{"ref": "P1", "n": 1, "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served", "source_id": "s_290d5ff51a37"}]},
        {"text": "Another 287 adults ended the year on the waitlist.",
         "chips": [{"ref": "P4", "n": 2, "source_n": 1, "source": "FY26 Program Report", "locator": "The waitlist", "source_id": "s_290d5ff51a37"}]},
        {"text": "Staff propose a $1,610,000 budget for FY2027 that adds a sixth site.",
         "chips": [{"ref": "P5", "n": 3, "source_n": 1, "source": "FY26 Program Report", "locator": "Recommendation to the board", "source_id": "s_290d5ff51a37"}]}
      ],
      "asks": [
        {"id": "a1", "who": "The board", "what": "A one-page summary of the FY2027 budget request", "by": "October 21", "kind": "onepager",
         "chips": [{"ref": "P8", "n": 1, "source_n": 2, "source": "Board retreat notes", "locator": "para. 3", "source_id": "s_51976a6db455"}],
         "brief": {"who": "Board members", "goal": "Vote on the FY2027 budget on October 21", "length": "One page"}},
        {"id": "a2", "who": "Board members", "what": "A short deck for funders about the sixth site", "by": "", "kind": "deck",
         "chips": [{"ref": "P8", "n": 1, "source_n": 2, "source": "Board retreat notes", "locator": "para. 3", "source_id": "s_51976a6db455"}],
         "brief": {"who": "Funders", "goal": "Fund the sixth site", "length": "About 8 slides"}}
      ],
      "questions": [
        {"text": "Reserves stand at 3.2 months against a 4-month target. Can Harborlight add a site while the budget rises $190,000?",
         "chips": [{"ref": "P8", "n": 1, "source_n": 2, "source": "Board retreat notes", "locator": "para. 3", "source_id": "s_51976a6db455"},
                   {"ref": "P5", "n": 2, "source_n": 1, "source": "FY26 Program Report", "locator": "Recommendation to the board", "source_id": "s_290d5ff51a37"}],
         "suggestion": true},
        {"text": "Would 180 more seats a year be enough for a waitlist of 287?",
         "chips": [{"ref": "P5", "n": 1, "source_n": 1, "source": "FY26 Program Report", "locator": "Recommendation to the board", "source_id": "s_290d5ff51a37"},
                   {"ref": "P4", "n": 2, "source_n": 1, "source": "FY26 Program Report", "locator": "The waitlist", "source_id": "s_290d5ff51a37"}],
         "suggestion": true}
      ]
    },
    "element_edit_stronger": {
      "by": "Written by your Hermes model", "output_id": "o_8f2c1a9b0d3e", "kit_id": "s_counsel", "slide": 2, "action": "stronger",
      "status": "ok", "message": null, "insert_after": null,
      "before": {"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "The average wait was nine weeks.", "refs": ["P4"]},
      "options": [
        {"slide": {"type": "stat", "value": "287", "label": "adults are waiting for a seat", "context": "They wait nine weeks on average.", "refs": ["P4"]},
         "check": {"status": "ok", "label": "All 1 numbers match your sources", "items": []}},
        {"slide": {"type": "stat", "value": "287", "label": "adults ended the year on our waitlist", "context": "Most of them live near Eastgate and Riverside.", "refs": ["P4"]},
         "check": {"status": "ok", "label": "All 1 numbers match your sources", "items": []}},
        {"slide": {"type": "stat", "value": "287", "label": "adults are ready to learn and have no seat", "context": "The average wait was nine weeks.", "refs": ["P4"]},
         "check": {"status": "ok", "label": "All 1 numbers match your sources", "items": []}}
      ]
    },
    "fix_it": {
      "by": "Written by your Hermes model", "output_id": "o_8f2c1a9b0d3e", "kit_id": "s_counsel",
      "key": "slides.2.value|number|1200", "path": "slides.2.value", "status": "ok",
      "before": "1,200 learners in one year", "after": "1,148 adult learners in one year",
      "diff": [{"op": "del", "text": "1,200"}, {"op": "add", "text": "1,148 adult"}, {"op": "same", "text": "learners in one year"}],
      "chips": [{"ref": "P1", "n": 1, "source_n": 1, "source": "FY26 Program Report", "locator": "Who we served", "source_id": "s_290d5ff51a37"}],
      "check": {"status": "ok", "label": "Matches your source"}
    }
  }
}
```

---

## Changes

- 2026-11-08 22:05 CT: first published.
- 2026-11-08 23:00 CT: `trace_table` keeps today's five statuses unless called with `computed=True` (today's pane
  throws on an unknown status); `check_line` added to section 6; request 7 (a trace head for worked-out numbers);
  the note on curly-quoted locators. No route or claim shape changed.
- 2026-11-08 23:40 CT: from the real-model bench. (1) `math.op` gains `"bound"` for a number shown with a
  qualifier ("about 1,150" from 1,148); a bounded difference or sum keeps its op and ends "shown as more than 200".
  Bounds hold within a quarter of the true value, approximations within five percent. (2) Grounding items gain
  status `"date"` for an unfound date, year or season ("2025-26"): never missing, never blocking, not counted, and
  never a claim. Both came from false flags on the bench decks.
- 2026-11-09 00:40 CT (backend lane, Loop 2): **Versions (sections 4.7, 7) and claims (section 3) are live.**
  `store.add_version / undo / versions` exist (table `output_versions(output_id, v, doc, reason, created_at, active,
  renders)`; `renders` holds every brand's voiced doc so Undo restores exactly what was on screen; a main-era database
  gets version 1 "Made" on first read). Keep and Undo now answer with the output view; Undo at version 1 is 400
  "Nothing to undo."; keeping after an Undo drops the versions ahead (no Redo). The output view gains top-level
  `versions` (not per proof). Each proof gains `claims`, `slides` (the frame list, 0-based, frame 0 the title slide,
  ids `c1`, `c2`... from `checks.claims_map`), `passages_used`, and `stamp` ("All 14 numbers match your sources." /
  "The 1 number matches your sources." / "No numbers to check." / "2 numbers not found in your sources.").
  **Shape change:** the deck slide count that was `proof.slides` (an int) is now `proof.slide_count`; `proof.slides`
  is the frame list. `trace_table` still runs with `computed=False` (`service.TRACE_COMPUTED`) until the pane has a
  "computed" head.
- 2026-11-09 01:05 CT (backend lane): **Make from an outline (contract D) is live.** `POST /outputs` takes
  `outline_id` (`ol_` + 12 hex; a deck only); the make job builds exactly the outline's slides, in its order, each
  slide's heading set to the outline title word for word (the written slide of the same type is matched to each
  outline row), and fails as `cut_off` if fewer slides come back. Output rows (`state.outputs[i]`) gain
  `building: true` while their make job runs. Make steps now read "Reading 3 sources", "Writing 8 slides from your
  outline" (or "Writing from your sources"), "Checking 14 numbers against your sources", "Setting it in <brand>".
- 2026-11-09 01:30 CT (backend lane): **Stop, step timing, `tr` claim ids.** `POST /jobs/{id}/stop` -> the job, status
  `"stopped"` at once, error "Stopped. Your outline is kept.", `error_code: "stopped"`; the work ends at its next step and
  nothing overwrites the stop; Retry starts it again. A make stopped after its slides are written keeps the output
  (plain wording for a brand not set yet, version 1 "Made"). Every `steps[i]` gains `done_at` (null while running).
  Scene trees: each traced number span's node object carries `tr: "c12"` (the claim id, contract F) beside the pane's
  integer `a.tr`; on an exhibit, the bar `div.ip-sc-r` just before a traced value carries the same `tr`. Dates and page
  numbers get none. Trace cards now come with `computed=True` (status `"computed"`, `math`).
- 2026-11-09 01:45 CT (backend lane): make-from-outline now writes with the AI lane's `K.instructions_for(kind, brief,
  outline=...)`; a stat slide takes the outline title as its `label`, every other slide but a quote as its `heading`.
  Chat rows (`<chat>`) gain `lead`, `detail`, `more` from `K.split_answer(text)` (assistant rows; empty strings on
  the person's own rows).
- 2026-11-09 02:30 CT (backend lane): **Sample and pictures (contract A, B).** `POST /sample/open` and `POST /sample/close`
  (`{}` in, `<state>` out). Open switches Letterpress to `<data>/sample/` (built from `samples/harborlight/notebook.json` the
  first time, no model call, reused after; the shipped folder is only read); close goes back to the person's folder,
  untouched. `state.sample = {available, open, name: "Harborlight Literacy", label: "Sample"}`; while it is open every
  source row and output row carries `sample: true`. `state.previews = {deck, onepager, visual, audio}`, each
  `{img: "data:image/...", w: 640, h, kit_id, kit_name}` or null, drawn in the active brand (prefs.kit, else the first
  studio kit) from the recorded sample docs, cached under `previews/`. deck = the exhibit slide, onepager = the top of
  the page, visual = the deck's exhibit as a bar graphic, audio = the first three chapter titles on a brand card.
  `outputs[i].thumb`: a data URI of the first slide or the page top, 480px wide, under 80 KB, null while building.
  The sample brand is Harborlight's guide with Harbor Teal for headlines and the band and Lighthouse Red as the only
  accent. The brand guide PDF is the third source, unticked.
- 2026-11-09 02:50 CT (backend lane): **Audio, honest.** An audio proof gains `length_label` ("About 3 min": the length
  asked for when the script runs within a quarter of it, else the script's own length), `seconds`, and `chapters:
  [{i, heading, start_s, dur_s, lines: [{text, start_s, chips: [<chip>]}]}]`, timed at 150 words a minute (the title is
  read first, the recap is the last chapter "Recap"). A line's chips are the passages holding its numbers, else the
  chapter's first passage. Harness only: `harness/live/server.py --voice-stub` records silent WAVs (never played).
- 2026-11-09 00:40 CT Mon (backend lane, asked by the canvas lane for S17): **a picked graphic.**
  `POST /graphics/keep {job_id, choice, kit_id}` -> `{output_id}`: the `graphic_options` job's option saved as a new
  `visual` output (title = its headline, the job's sources), re-checked first, version 1 "Made"; it exports through
  `POST /outputs/{id}/export` (png, svg, pdf). `POST /outputs/{deck_id}/add-graphic {job_id, choice}` -> output view:
  the option added to the deck as an exhibit slide before the closing slide, as a new version ("Added a graphic, slide
  N"; Undo takes it back). 400 with one sentence when a value no longer matches, the graphic is a timeline, or it cites
  sources the deck doesn't use.
- 2026-11-09 00:35 CT Mon (backend lane): the sample ships its Studio previews and output thumbs in `notebook.json`
  (`pictures`, by cache name), so `POST /sample/open` on a fresh folder draws nothing (0.35 s). Each cached picture
  names the renderer fingerprint (`service.renderer_sig()`, a hash of the render files), so after a design change the
  pictures are drawn fresh instead of showing old ones. Redraw the shipped ones with no model call:
  `/usr/bin/python3 tools/record_sample.py --pictures`.
- 2026-11-09 00:15 CT (loop2-ai): (1) **Hero exhibit fields for the design lane.** An exhibit slide's bar may
  carry `accent: true`. That is the one bar that holds the finding, and the renderer sets it in the brand's
  accent. `clean_deck` keeps at most one. When none is set, the renderer falls back to the largest bar. An exhibit
  may also carry `subhead`: one line under the heading with the worked-out change ("212 more adults than last
  year"). It is checked like any field, so 212 passes as `computed`. `clean_deck` strips an "Exhibit N" eyebrow
  from the heading. Shape: `{type: "exhibit", heading, subhead?, unit, note, refs, bars: [{label, value, ref, accent?}]}`.
  (2) `element_edit` result: `before` is the slide as it reads on screen in `kit_id`, the brand-voiced live text
  from `service._doc_for`. A new `base` is the neutral slide, and Keep checks against it. There is also
  `before_tree`, plus `options[i].tree`: scene nodes for the canvas, or null. (3) `fix_it`: `before` and `key` refer
  to the live text, and diff parts keep their own spaces. Join them with "": same+add gives `after`, and same+del
  gives `before`. (4) `graphic_options` takes an optional `kit_id`. Each option gains `tree` and `refs`. (5) The
  check label is `checks.match_label(n)`: "No numbers to check." / "The 1 number matches your sources." /
  "All N numbers match your sources." (6) Chat: `content.split_answer(text) -> {lead, detail, more}`, and
  `chat_row` spreads it (backend glue). (7) Make from an outline: `content.instructions_for("deck", brief,
  outline)` plus `content.apply_outline(doc, outline)` after `clean_for`, for the write call only (backend glue).
  (8) Grounding: a date or season number ("26" in "2025-26") is status `date`, never `computed`.
- 2026-11-09 03:20 CT (round-5 deck lane, `loop2r5-deck`): (1) **The outline is checked as its reader would.** The
  `outline` job makes one more model call (`purpose: outline_review`, step "Checking the outline as your reader
  would"): is the ask on the closing (the amount and its use; an increase, not the new total), is the strongest
  finding for the ask on a slide, what the reader will ask that no slide answers, does each title rest on its
  passages. The result's `slides` is the revised outline and a new `review: [{text, refs, chips}]` says what changed
  (section 4.2). The make job builds from that saved outline as before, so it is the default path. (2) **Points back
  the title.** In the make job's one repair call, a slide built from an outline whose points cite none of its title's
  passages is a fault (`checks.off_title`), rewritten from those passages; the repair is kept only with fewer faults.
  (3) The deck schema's closing `amount` is the increase when the ask is an increase over a current budget.
- 2026-11-09 03:30 CT (round-6 deck lane, `loop2r6-deck`): (1) **A deck is written in one pass.** The `make` job for
  a deck makes one `letterpress.write` call with every source in view (`content.onepass_instructions`,
  `content.onepass_schema`): the model first writes `case` (three to five sentences: the reader, what they must
  believe, the strongest evidence, their open question, the ask), then every slide, in the first brand's voice. When
  an approved outline is given (`outline_id`) it is the pass's spine (same slides, order, types and titles, held in
  code by `follow_outline`); with none, the pass plans and writes together. A length the request names ("7 to 9
  slides") caps the slides in the schema, the title slide counted, and sets `max_slides`. Image slides are offered only
  when pictures were asked for. The case is saved as the setting `case_of:<output_id>` (not shown on a slide).
  (2) **No voice call for a deck's first brand.** The pass wrote in that brand's voice, so the render is stored by
  code (`service._store_render`); a second brand still gets its `letterpress.voice` call, and a brand swap still
  re-voices. The job's steps are unchanged. (3) **The one repair call gains two faults**: numbers, quotes and
  citations no source holds (`checks.unsourced`, from the trace), and numbers the pass's own case names as evidence
  that no slide shows (`checks.case_left_out`). As before, the repair is kept only when it has fewer faults and the
  same slides. The `outline` job (with its round-5 review) is unchanged, for people who want an outline first.
- 2026-11-09 07:10 CT (round 11, argue lane): **A deck made with no outline is argued before it is laid out.** The
  make job's first deck step is "Drafting the case": one `letterpress.argument` call with every source in view drafts the
  case as a development director would; code checks it (`checks.argument_problems`: every number in a cited passage
  or worked out with its operation said, every quote found, every ref a real passage, the ask has an amount or says
  the sources give none, no placeholder, and every instruction the notes give for the deck, found by
  `checks.notes_instructions`, is listed with its own words and met by a step); on a fault, one
  `letterpress.argument_repair` call ("Fixing N things in the case"), kept only with fewer faults. The deck write then
  takes the case as a fixed spine (`content.argument_outline` + `service.follow_outline`): one slide per step, in
  order, each heading word for word, the counter-case on its own slide, the ask on the closing; the general coverage
  and money rules are off for it, and the repair call does not add budget figures the case left out. With no usable
  case the job falls back to the round-6 one pass. An approved outline (`outline_id`) still wins and skips the case.
  **The `argument` result shape** (stored as JSON in setting `argument_of:<output_id>` with a `faults` list, and
  returned in the make job's `result.argument` without `faults`, so the pane can show it later):
  ```
  {"reader": str,
   "instructions": [{"said": str (the notes' words), "refs": [ref], "met_by": "lead" | "point N" | "counter" | "ask" | "left out"}],
   "lead":    {"heading": str, "type": slide type, "evidence": [{"text": str, "refs": [ref]}]},
   "points":  [{"heading", "type", "evidence"}, ...],            # in order, 2 to (length - 3)
   "counter": {"objection": str, "heading": str, "type", "evidence"},
   "ask":     {"heading": str, "amount": str ("" when none), "buys": [str], "by_when": str, "rest": str,
               "report": str, "refs": [ref], "none_in_sources": bool},
   "faults":  [{"where": str, "what": str}]}                     # stored copy only: what still failed after the repair
  ```
  Slide order is lead, points, counter, closing; `content.argument_steps(argument)` gives it as
  `[{role, heading, type, evidence, refs}]`. No route changed.
