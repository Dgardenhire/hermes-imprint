# Canvas seam

The canvas (`desktop/src/canvas.js`) is bundled into `desktop/plugin.js` by the same build as everything else
(`node ~/products/hermes-ui-kit/scripts/build.mjs .`). It imports only `react`, `react/jsx-runtime`,
`@hermes/plugin-sdk` and `hermes-ui-kit`; everything else comes through the `api` prop.

## The lines in the pane's file (`desktop/src/plugin.js`, owned by the pane lane)

```js
import { Canvas, usesCanvas } from './canvas.js'
import * as canvasLane from './canvas.js' // GraphicOptions (Loop 2)
...
  const out = useValue($output)
  if (viewing && usesCanvas(out, viewing)) return h(Canvas, { st, out, api: { rest, post, del, pollJob, openReader, openOutput, toast, errText, close: () => $viewing.set(null) } })
  const gf = useValue($graphicFor)
  if (gf && canvasLane.GraphicOptions) return h(canvasLane.GraphicOptions, { st, note: gf, kitId: $kit.get(), api: { ...same api, close: () => $graphicFor.set(null) } })
export function makeGraphic(noteId) { ... $graphicFor.set(note) }   // for the shoot script
```

`usesCanvas(out, viewing)` is true when the open output's first proof is ready and is a deck, a graphic or a
one-pager. Audio stays in the pane's Viewer. `pollJob` ends on `done`, `failed` and (Loop 2) `stopped`.

## What the canvas reads

Per proof (docs/API-NOTEBOOK.md section 3, live on `loop2-backend` since 6f2ecf6 and 2593a1e): `claims`, `slides`
(frames, 0-based, frame 0 the title slide), `passages_used`, `stamp`, and a string `tr` claim id on each claim's
node in the tree (`node.tr`, or `a.tr` when it is a string; the pane's integer `a.tr` is ignored), including the bar
of an exhibit value. Per output: `versions` (top level). The canvas never decides whether a number passes; it draws
what the proof says.

From the AI lane's job results (`loop2-ai` 8cbf4a8): `element_edit` `before`, `before_tree`, `options[i].slide`,
`options[i].tree`, `options[i].check`; `fix_it` `before`, `after`, `diff` (parts keep their own spaces; older
results without them get a space put back between parts), `check`; `graphic_options` `options[i].tree`, `refs`,
`spec`. Option trees carry no `tr`, so the canvas treats them as pictures; in the graphic options it finds each
spec item's value in the tree and shows that value's sentence from `GET passages/{ref}`.

## Routes it calls (one table, `ROUTES` at the top of canvas.js)

| What | Route | Body |
|---|---|---|
| Shorter, Stronger headline, Turn into a chart | `POST outputs/{id}/element-edit` | `{kit_id, slide: frame - 1, action}` |
| Ask for a change | `POST outputs/{id}/element-edit` | `{kit_id, slide, action: "typed", text}` |
| Fix it for me | `POST outputs/{id}/fix` | `{kit_id, key: claim.key}` |
| Keep, Accept | `POST outputs/{id}/keep` | `{job_id, choice}` |
| Discard | `POST outputs/{id}/discard` | `{job_id}` |
| Undo | `POST outputs/{id}/undo` | `{}` |
| Keep mine, I checked | `POST outputs/{id}/decide` | `{key, action: "keep"}` |
| Edit text | `POST outputs/{id}/edit` | `{path, text}` |
| Stop, Retry | `POST jobs/{id}/stop`, `POST jobs/{id}/retry` | `{}` |
| Make a graphic | `POST graphics/options` | `{source_ids, note_id, kit_id}` |
| Brand, Export, Delete | `outputs/{id}/kit`, `outputs/{id}/export`, `DELETE outputs/{id}` | unchanged |

Slides are 0-based in code; `element-edit` takes the 0-based index into `doc.slides`, which is the frame index
minus one (the title frame and the Sources frame are not editable). Labels on screen are 1-based.

## Requests (open)

To lane A / design (the scene engine): the exhibit headline sets at 32 pt in the scene, which is 30.7 px on
screen at 1440 (the slide is 920 px wide there: 1208 px of pane less the 200 px evidence strip and the 48 px
Revise rail). The brief asks 36 px. The canvas cannot get there by layout; the exhibit head needs about 38 pt.

To the backend: `POST outputs/{id}/edit` (Edit text) changes the deck without a version, so Undo can't undo it; add a
version ("Edited text") there. (Done on loop2-backend 9b6ec6d and used: `POST graphics/keep` for Save as PNG/SVG and
`POST outputs/{deck}/add-graphic` for Add to the deck.)

To the AI lane: a claim can sit in a frame's `claims` but not be drawn (the hero deck's "212" on the exhibit frame
has no span), so it has nothing to hover; either draw it (the subhead "212 more adults than last year") or leave
it out of the frame's claims.
