// Imprint canvas: one output open as an editor. The slide large in the middle with the filmstrip under it, the
// source sentences behind the slide on the left ("Evidence for this slide"), and Revise on the right.
//
// What it shows, it reads from the output (docs/API-NOTEBOOK.md section 3, and the Loop 2 additions):
//   proof.claims          {c12: {kind, value, status, ref, source_n, source, locator, line, math, slides, key, fixable}}
//   proof.slides          [{i, type, title, refs, claims}]        i and claims[].slides are 0-based frames (0 = title)
//   proof.passages_used   {P7: {source_id, source_n, source, locator, text, slides}}
//   proof.stamp           the one-sentence check ("All 14 numbers match your sources.")
//   output.versions       [{v, created_at, reason, active}]
//   a "tr" key on a scene node names its claim ({"t": "span", "a": {"tr": "c12"}})
// It never decides whether a number passes, never finds a match and never does the math: it draws what the
// output says. Everything else it needs (routes, the reader, toasts) comes through the `api` prop, so this file
// never reaches into plugin.js. Imports: react, @hermes/plugin-sdk and hermes-ui-kit only.
//
// Rendering: our own node walker with a fixed tag list (div, span, img, svg, g, rect, line, path, circle, text,
// tspan), text only as text, no innerHTML, no model-written markup. Each slide is laid out at the scene's own
// width (960 px) and scaled to fit, so a slide here is drawn the way the exports draw it. The plugin's chrome uses
// host tokens only; a brand's colors and fonts appear only on the slide, the thumbnails and the brand chip.
//
// Indexes: frames are 0-based everywhere in this file (frame 0 = the title slide). The AI routes take `slide` as a
// 0-based index into doc.slides, which is frame - 1. Labels on screen are 1-based ("Slide 4" = frame 3).

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { Button, Codicon, captureGatewayFileDownload } from '@hermes/plugin-sdk'
import { useReducedMotion } from 'hermes-ui-kit'

const h = (t, p, ...k) => {
  const kids = k.flat().filter(x => x !== null && x !== undefined && x !== false)
  return kids.length > 1 ? jsxs(t, { ...(p || {}), children: kids }) : jsx(t, { ...(p || {}), children: kids[0] })
}
const cls = (...xs) => xs.filter(Boolean).join(' ')
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`

// The scene's own width, in CSS pixels, before it is scaled to fit.
const ART_W = 960
// A slide drawn inside Revise: the panel's 260px less its padding, the card's and the option's.
const MINI_W = 196

// Every route the canvas calls, in one place (docs/API-NOTEBOOK.md 2 and 4, 01-CONTRACT-L2 C, E, G).
export const ROUTES = {
  elementEdit: id => `outputs/${id}/element-edit`, // {kit_id, slide: 0-based doc slide, action, text?} -> {job}
  fix: id => `outputs/${id}/fix`, //                  {kit_id, key} -> {job}
  keep: id => `outputs/${id}/keep`, //                {job_id, choice} -> output view
  discard: id => `outputs/${id}/discard`, //          {job_id} -> {ok}
  undo: id => `outputs/${id}/undo`, //                {} -> output view, 400 "Nothing to undo." at v1
  decide: id => `outputs/${id}/decide`, //            {key, action: "keep"} -> output view (lane A, existing)
  text: id => `outputs/${id}/edit`, //                {path, text} -> output view (lane A, existing)
  kit: id => `outputs/${id}/kit`, //                  {kit_id, slot} -> {job} (lane A, existing)
  export: id => `outputs/${id}/export`, //            {kit_id, format} -> {path, name} (lane A, existing)
  del: id => `outputs/${id}`, //                      DELETE (lane A, existing)
  graphics: () => 'graphics/options', //              {source_ids, note_id?, text?, kit_id?} -> {job}
  graphicKeep: () => 'graphics/keep', //              {job_id, choice, kit_id} -> {output_id} (a new graphic)
  addGraphic: id => `outputs/${id}/add-graphic`, //   {job_id, choice} -> deck output view, a new version
  stop: id => `jobs/${id}/stop`, //                   {} -> job, status "stopped"
  retry: id => `jobs/${id}/retry`, //                 {} -> job
}

export function usesCanvas(out, viewing) {
  if (!out || out.id !== viewing || !out.proofs || !out.proofs[0]) return false
  const p = out.proofs[0]
  return p.status === 'ready' && (p.kind === 'deck' || p.kind === 'visual' || p.kind === 'onepager')
}

/* ------------------------------------------------------------------ reading the output -- */

const OK = new Set(['exact', 'close', 'computed', 'brief'])
const COUNTED = new Set(['exact', 'close', 'computed'])
const STATUS = {
  exact: () => 'Matches your source',
  close: () => 'Same number, written another way',
  computed: () => 'Worked out from your sources',
  missing: () => 'Not found in your sources',
  kept: () => 'Kept on purpose. You checked it.',
  brief: () => 'From your own request',
}
const statusWords = c => (STATUS[c.status] || STATUS.missing)(c)
const toneOf = c => (OK.has(c.status) ? 'good' : c.status === 'kept' ? 'warn' : 'bad')

function trOf(n) {
  const a = n.a || {}
  const t = typeof n.tr === 'string' ? n.tr : typeof a.tr === 'string' ? a.tr : null
  return t && /^c\d{1,4}$/.test(t) ? t : null
}

function scenesOf(proof) {
  const t = proof.tree
  if (!t) return []
  const isScene = n => n && typeof n.c === 'string' && /(^|\s)ip-scene(\s|$)/.test(n.c)
  if (isScene(t)) return [t]
  const kids = (t.k || []).filter(isScene)
  if (kids.length) return kids
  return [t] // a one-pager: the page is the one "slide"
}

function aspectOf(scene) {
  const ar = scene && scene.a && scene.a.style && scene.a.style['--ar']
  const m = typeof ar === 'string' && ar.match(/^\s*([\d.]+)\s*\/\s*([\d.]+)\s*$/)
  if (m && +m[1] > 0 && +m[2] > 0) return +m[2] / +m[1]
  return /ip-scene/.test(scene && scene.c || '') ? 540 / 960 : 11 / 8.5
}

// A frame's type: the row's own word, else the scene's class (ip-sk-stat -> stat).
function typeOf(row, scene) {
  if (row && typeof row.type === 'string' && /^[a-z]+$/.test(row.type)) return row.type
  const m = String((scene && scene.c) || '').match(/ip-sk-([a-z]+)/)
  return m ? m[1] : ''
}

const textOfNode = n => (!n || typeof n !== 'object' || n.t === 'sup') ? '' : (n.x || '') + (n.k || []).map(textOfNode).join('')

// The headline element of a scene: the text block set largest.
function headlineIndex(scene) {
  let best = -1, size = 0
  ;(scene && scene.k || []).forEach((n, i) => {
    const fs = parseFloat((n.a && n.a.style && n.a.style['--fs']) || '0')
    if (/ip-sc-t/.test(n.c || '') && textOfNode(n).trim().length > 2 && fs > size) { size = fs; best = i }
  })
  return best
}

const SENT = /(?<=[.!?”])\s+/
function firstSentence(text) {
  return String(text || '').split(SENT)[0] || ''
}

// The strip marks a claim lights: its own sentence, or each operand's for a worked-out number.
const markKeys = (cid, c) => (c && c.math && c.math.operands ? c.math.operands.map((o, k) => `${cid}:${k}`) : [cid])
const markSel = (cid, c) => markKeys(cid, c).map(k => `[data-marks~="${k}"]`).join(', ')
const CUE_KEY = 'imprint.canvas.cue.v1'
const unquote = s => String(s || '').replace(/^[“"‘']+|[”"’']+$/g, '')

const claimRefs = c => (c && c.math && c.math.operands ? c.math.operands.map(o => o.ref) : [c && c.ref]).filter(Boolean)

// The strip for one slide: per passage the slide cites, the sentences its numbers came from, with each number's
// place in its sentence (from the claim's own line), so each can be lit alone.
function evidenceFor(row, claims, used) {
  if (!row) return []
  const items = []
  const byRef = new Map()
  const add = (ref, line, mark) => {
    if (!ref || !used[ref]) return
    let it = byRef.get(ref)
    if (!it) { it = { ref, p: used[ref], sentences: [] }; byRef.set(ref, it); items.push(it) }
    if (!line) return
    const text = `${line.before || ''}${line.match || ''}${line.after || ''}`
    let s = it.sentences.find(x => x.text === text)
    if (!s) { s = { text, marks: [] }; it.sentences.push(s) }
    const start = (line.before || '').length
    if (!mark || !line.match) return
    const same = s.marks.find(m => m.start === start)
    if (same) { if (!same.keys.includes(mark.key)) same.keys.push(mark.key) } else s.marks.push({ keys: [mark.key], start, len: line.match.length })
  }
  for (const cid of row.claims || []) {
    const c = claims[cid]
    if (!c || !OK.has(c.status) && c.status !== 'kept') continue
    if (c.math && c.math.operands) c.math.operands.forEach((o, k) => add(o.ref, o.line, { cid, key: `${cid}:${k}` }))
    else add(c.ref, c.line, { cid, key: cid })
  }
  for (const ref of row.refs || []) add(ref, null)
  for (const it of items) {
    if (!it.sentences.length) it.sentences.push({ text: firstSentence(it.p.text), marks: [] })
    for (const s of it.sentences) s.marks.sort((a, b) => a.start - b.start)
  }
  return items
}

/* ------------------------------------------------------------------ the node walker -- */

const OUT_TAGS = new Set(['div', 'span', 'img', 'svg', 'g', 'rect', 'line', 'path', 'circle', 'text', 'tspan'])
const AS_DIV = new Set(['h1', 'h2', 'h3', 'p', 'section', 'header', 'footer', 'figure', 'figcaption', 'blockquote', 'ul', 'ol', 'li', 'hr'])
const AS_SPAN = new Set(['strong', 'em', 'small', 'b', 'i'])
const SVG_ATTRS = new Set(['x', 'y', 'width', 'height', 'fill', 'stroke', 'stroke-width', 'd', 'cx', 'cy', 'r', 'x1', 'y1', 'x2', 'y2',
  'viewBox', 'text-anchor', 'font-size', 'font-weight', 'opacity', 'fill-opacity', 'rx'])
const SVG_REACT = { 'stroke-width': 'strokeWidth', 'text-anchor': 'textAnchor', 'font-size': 'fontSize', 'font-weight': 'fontWeight', 'fill-opacity': 'fillOpacity' }

function walk(n, key, ctx, depth) {
  if (!n || typeof n !== 'object' || depth > 40) return null
  const t = n.t
  if (t === 'sup') return null // no superscript source marks on the canvas: the underline and the hover prove a number
  const asTag = OUT_TAGS.has(t) ? t : AS_DIV.has(t) ? 'div' : AS_SPAN.has(t) ? 'span' : null
  if (!asTag) return null
  const a = n.a || {}
  // A hairline (a rule under 1% of the slide's height) is never a number's mark, even when the scene tags it.
  const hair = a.style && typeof a.style === 'object' && (parseFloat(a.style['--h']) < 1 || parseFloat(a.style['--w']) < 0.5)
  const cid = hair ? null : trOf(n)
  const claim = cid && ctx.claims[cid]
  let className = typeof n.c === 'string' ? n.c.replace(/(^|\s)ip-num(?=\s|$)/g, ' ').trim() : ''
  if (t !== asTag) className = cls(className, `ip-cv-as-${t}`)
  const props = { key }
  if (asTag === 'img') {
    if (typeof a.src !== 'string' || !a.src.startsWith('data:image/')) return null
    return jsx('img', { key, className: className || undefined, src: a.src, alt: '' })
  }
  if (a.style && typeof a.style === 'object') {
    const style = {}
    for (const [k, v] of Object.entries(a.style)) if (/^--[a-z0-9-]+$/.test(k)) style[k] = String(v)
    props.style = style
  }
  if (['svg', 'g', 'rect', 'line', 'path', 'circle', 'text', 'tspan'].includes(asTag)) {
    for (const [k, v] of Object.entries(a)) {
      if (!SVG_ATTRS.has(k)) continue
      const s = String(v)
      if (/url\(|javascript:|expression\(/i.test(s)) continue
      props[SVG_REACT[k] || k] = s
    }
  }
  if (claim && ctx.live) {
    const lit = ctx.active === cid
    className = cls(className, asTag === 'span' ? 'ip-cv-claim' : 'ip-cv-hot', `is-${claim.status}`, lit && 'is-lit', ctx.pinned === cid && 'is-pinned',
      !lit && ctx.rev && ctx.rev.has(cid) && 'is-rev')
    props['data-cid'] = cid
    props.onMouseEnter = e => ctx.enter(cid, e.currentTarget)
    props.onMouseLeave = () => ctx.leave(cid)
    props.onClick = e => { e.stopPropagation(); ctx.pin(cid, e.currentTarget) }
    if (asTag === 'span') {
      props.tabIndex = 0
      props.role = 'button'
      props['aria-label'] = `${claim.value}: ${statusWords(claim)}`
      props.onFocus = e => ctx.focus(cid, e.currentTarget)
      props.onBlur = () => ctx.blur(cid)
      props.onKeyDown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); ctx.pin(cid, e.currentTarget) } }
    }
  } else if (claim && ctx.flags && claim.status === 'missing') {
    className = cls(className, 'ip-cv-flag-thumb')
  }
  if (depth === 1 && ctx.live && ctx.onElement) {
    props['data-el'] = String(key)
    const prev = props.onClick
    props.onClick = e => { if (prev) prev(e); else { e.stopPropagation(); ctx.onElement(key, e.currentTarget) } }
    if (ctx.selectedEl === key) className = cls(className, 'ip-cv-sel-el')
  }
  props.className = className || undefined
  const kids = []
  if (typeof n.x === 'string' && n.x) kids.push(n.x)
  ;(Array.isArray(n.k) ? n.k : []).forEach((c, i) => { const el = walk(c, i, ctx, depth + 1); if (el) kids.push(el) })
  return kids.length > 1 ? jsxs(asTag, { ...props, children: kids }) : jsx(asTag, { ...props, children: kids[0] })
}

// One slide, laid out at the scene's width and scaled to `width`.
function Art({ scene, width, ctx, label }) {
  const ar = aspectOf(scene)
  const s = width / ART_W
  return h('div', { className: 'ip-cv-fit', style: { width: `${width}px`, height: `${Math.round(width * ar)}px` } },
    h('div', { className: 'ip-cv-art', style: { width: `${ART_W}px`, transform: `scale(${s})` }, 'aria-label': label },
      walk(scene, 'scene', ctx || { live: false, claims: {} }, 0)))
}

/* ------------------------------------------------------------------ hooks -- */

function useSize(ref) {
  const [size, setSize] = useState({ w: 0, h: 0 })
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const read = () => setSize(s => (s.w === el.clientWidth && s.h === el.clientHeight ? s : { w: el.clientWidth, h: el.clientHeight }))
    read()
    if (typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(read)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return size
}

function useOutside(open, box, close) {
  useEffect(() => {
    if (!open) return undefined
    const off = e => { if (box.current && !box.current.contains(e.target)) close() }
    const esc = e => { if (e.key === 'Escape') { e.stopPropagation(); close() } }
    document.addEventListener('mousedown', off)
    window.addEventListener('keydown', esc, true)
    return () => { document.removeEventListener('mousedown', off); window.removeEventListener('keydown', esc, true) }
  }, [open])
}

function useTick(on) {
  const [, set] = useState(0)
  useEffect(() => {
    if (!on) return undefined
    const t = setInterval(() => set(x => x + 1), 1000)
    return () => clearInterval(t)
  }, [on])
}

// One AI job, from start to its result: polls, keeps the steps with their times, Stop and Retry.
function useJob(api) {
  const [job, setJob] = useState(null)
  const stopper = useRef(null)
  useEffect(() => () => stopper.current && stopper.current(), [])
  const track = (meta, j) => {
    setJob({ ...meta, id: j.id, status: 'running', steps: j.steps || [], step: j.step, started: Date.now() / 1000 })
    stopper.current = api.pollJob(j,
      d => setJob(x => (x && x.id === j.id ? { ...x, status: 'done', steps: d.steps || x.steps, result: d.result } : x)),
      f => setJob(x => (x && x.id === j.id ? { ...x, status: f.status === 'stopped' ? 'stopped' : 'failed', steps: f.steps || x.steps, error: f.error || 'That did not finish. Press Retry.' } : x)),
      s => {
        if (s.status === 'stopped') { if (stopper.current) stopper.current(); setJob(x => (x && x.id === j.id ? { ...x, status: 'stopped', steps: s.steps || x.steps, error: s.error || 'Stopped.' } : x)); return }
        setJob(x => (x && x.id === j.id ? { ...x, steps: s.steps || x.steps, step: s.step || x.step } : x))
      })
  }
  const start = async (meta, path, body) => {
    if (stopper.current) stopper.current()
    setJob({ ...meta, status: 'running', steps: [], started: Date.now() / 1000 })
    try {
      const r = await api.post(path, body)
      if (!r || !r.job) throw new Error('That did not start. Try again.')
      track(meta, r.job)
    } catch (e) { setJob({ ...meta, status: 'failed', error: api.errText(e) }) }
  }
  const stop = async () => {
    if (!job || !job.id) return
    if (stopper.current) stopper.current()
    try { await api.post(ROUTES.stop(job.id), {}) } catch (e) { /* stopped on our side either way */ }
    setJob(x => (x ? { ...x, status: 'stopped', error: 'Stopped.' } : x))
  }
  const retry = async () => {
    if (!job || !job.id) return
    const meta = { kind: job.kind, label: job.label, frame: job.frame, cid: job.cid, action: job.action }
    try { const r = await api.post(ROUTES.retry(job.id), {}); track(meta, r.job || r) } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  return { job, setJob, start, stop, retry }
}

/* ------------------------------------------------------------------ canvas -- */

// The head's stamp, short enough never to be cut: "29 of 29 numbers match." The count is the server's check when it
// gave one (so the pane and the canvas say the same number), else the count on the page.
function shortStamp(stamp, counted) {
  const m = /^All (\d+) numbers match/.exec(stamp || '')
  const n = m ? +m[1] : counted
  if (!m && stamp && !counted) return stamp
  return n === 0 ? 'No numbers to check.' : n === 1 ? 'The 1 number matches your sources.' : `${n} of ${n} numbers match.`
}

export function Canvas({ st, out, api }) {
  const proof = out.proofs[0]
  const scenes = useMemo(() => scenesOf(proof), [proof.tree])
  const claims = proof.claims || {}
  const used = proof.passages_used || {}
  const rows = Array.isArray(proof.slides) ? proof.slides : []
  const versions = Array.isArray(out.versions) ? out.versions : Array.isArray(proof.versions) ? proof.versions : []
  const startAt = useMemo(() => {
    const i = rows.findIndex(r => (r.claims || []).some(c => claims[c] && claims[c].kind !== 'quote'))
    return i >= 0 ? i : 0
  }, [out.id])
  const [cur, setCur] = useState(startAt)
  const [hot, setHot] = useState(null) // {cid, el, via}
  const [pinned, setPinned] = useState(null) // cid
  const [reverse, setReverse] = useState(null) // passage ref picked in the strip
  const [sel, setSel] = useState(null) // {frame, el: index|null}
  const [reviseOpen, setReviseOpen] = useState(false)
  const [mode, setMode] = useState(null) // null | {kind: 'text', path, text}
  const [chosen, setChosen] = useState(0) // the option the person is looking at
  const [peek, setPeek] = useState(false) // the folded strip, opened over the stage
  const [brandJob, setBrandJob] = useState(null)
  const [cue, setCue] = useState(() => { try { return window.localStorage.getItem(CUE_KEY) !== '1' } catch (e) { return true } })
  const seen = () => { if (!cue) return; setCue(false); try { window.localStorage.setItem(CUE_KEY, '1') } catch (e) { /* the cue just shows again next time */ } }
  const edit = useJob(api)
  const fix = useJob(api)
  const reduced = useReducedMotion()
  const root = useRef(null)
  const stage = useRef(null)
  const strip = useRef(null)
  const film = useRef(null)
  const leaveT = useRef(null)
  const stageSize = useSize(stage)
  const rootSize = useSize(root)
  const row = rows[cur] || { i: cur, refs: [], claims: [] }
  const scene = scenes[cur]
  const ftype = typeOf(row, scene)
  const evidence = useMemo(() => evidenceFor(row, claims, used), [row, claims, used])
  const kit = (st.kits || []).find(k => k.id === proof.kit_id) || (proof.kit ? { ...proof.kit, id: proof.kit_id } : { id: proof.kit_id, name: 'Brand' })
  const flags = Object.entries(claims).filter(([, c]) => c.status === 'missing')
  const counted = Object.values(claims).filter(c => COUNTED.has(c.status)).length
  const job = edit.job
  const revising = reviseOpen || !!sel || !!job || !!fix.job || !!mode
  // Below 900px of canvas (a 1024 window) the strip folds to a rail so the slide keeps its size; the evidence is a click away.
  const folded = revising || (rootSize.w > 0 && rootSize.w < 900)
  const active = (hot && hot.cid) || pinned

  useEffect(() => { setCur(startAt); setPinned(null); setReverse(null); setSel(null); setHot(null); setMode(null) }, [out.id])
  useEffect(() => { if (cur >= scenes.length) setCur(Math.max(0, scenes.length - 1)) }, [scenes.length])
  useEffect(() => () => clearTimeout(leaveT.current), [])
  useEffect(() => { setChosen(0) }, [job && job.id, job && job.status])
  useEffect(() => { if (!folded) setPeek(false) }, [folded])

  const close = () => api.close()
  const go = i => { if (i < 0 || i >= scenes.length) return; setCur(i); setHot(null); setPinned(null); if (sel) setSel({ frame: i, el: null }) }

  useEffect(() => {
    const onKey = e => {
      const tag = (e.target && e.target.tagName) || ''
      if (e.key === 'Escape') {
        if (pinned || reverse || peek) { setPinned(null); setReverse(null); setPeek(false); setHot(null); e.stopPropagation(); return }
        if (sel && !job && !mode) { setSel(null); e.stopPropagation(); return }
        if (revising) return
        close()
        return
      }
      if (/INPUT|TEXTAREA/.test(tag)) return
      if (e.key === 'ArrowRight' || e.key === 'PageDown') { e.preventDefault(); go(cur + 1) }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); go(cur - 1) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const revHere = reverse ? new Set((row.claims || []).filter(c => claimRefs(claims[c]).includes(reverse))) : null
  const ctx = {
    live: true, claims, active, pinned, rev: revHere, selectedEl: sel && sel.frame === cur ? sel.el : null,
    enter: (cid, el) => { clearTimeout(leaveT.current); setHot({ cid, el }); seen() },
    leave: () => { clearTimeout(leaveT.current); leaveT.current = setTimeout(() => setHot(x => (x && x.via === 'focus' ? x : null)), 60) },
    focus: (cid, el) => { clearTimeout(leaveT.current); setHot({ cid, el, via: 'focus' }) },
    blur: () => setHot(x => (x && x.via === 'focus' ? null : x)),
    pin: cid => {
      setPinned(p => (p === cid ? null : cid))
      const node = strip.current && strip.current.querySelector(markSel(cid, claims[cid]))
      if (node) node.scrollIntoView({ block: 'nearest' })
    },
    onElement: el => { setSel({ frame: cur, el }); setMode(null) },
  }

  const lit = new Set()
  if (active && claims[active]) {
    const c = claims[active]
    if (c.math && c.math.operands) c.math.operands.forEach((o, k) => lit.add(`${active}:${k}`))
    else lit.add(active)
  }

  // A preview of a chosen option, drawn on the stage in place of the slide until it is kept or discarded.
  const r = job && job.status === 'done' ? job.result || {} : null
  const opts = r && Array.isArray(r.options) ? r.options : []
  const previewTree = r && job.frame === cur && opts[chosen] && opts[chosen].tree && r.action !== 'insert' ? opts[chosen].tree : null
  const shown = previewTree || scene

  // the slide: as large as the stage allows, top-aligned
  const padX = revising ? 12 : 20
  const ar = shown ? aspectOf(shown) : 9 / 16
  const filmH = scenes.length > 1 ? 70 : 0
  const availW = Math.max(200, stageSize.w - padX * 2)
  const availH = Math.max(160, stageSize.h - filmH - 32 - 16)
  const artW = Math.floor(Math.min(availW, availH / ar))

  const stamp = !Object.keys(claims).length ? (proof.stamp ? { tone: 'good', text: proof.stamp } : null) : flags.length
    ? { tone: 'bad', text: flags.length === 1 ? '1 number isn’t in your sources.' : `${flags.length} numbers aren’t in your sources.` }
    : { tone: 'good', text: shortStamp(proof.stamp, counted) }
  const exportOff = flags.length ? 'Fix or keep the numbers that aren’t in your sources first.' : proof.blocked ? 'Something on it needs a look before it can go out.' : ''
  const activeV = versions.find(v => v.active) || versions[versions.length - 1]
  const canUndo = !!activeV && activeV.v > 1

  const refresh = async () => { await api.openOutput(out.id) }
  const docSlide = ftype === 'title' || ftype === 'sources' ? null : cur - 1
  const passed = (row.claims || []).filter(c => claims[c] && COUNTED.has(claims[c].status) && claims[c].kind !== 'quote')
  const nPassed = new Set(passed.map(c => claims[c].value)).size

  const actions = docSlide === null ? [] : [
    { id: 'text', label: 'Edit text' },
    { id: 'shorter', label: 'Shorter' },
    { id: 'stronger', label: 'Stronger headline' },
    // Shown only when it can work: a chart needs two checked numbers on the slide, and an exhibit is a chart already.
    ftype !== 'exhibit' && nPassed >= 2 ? { id: 'chart', label: 'Turn into a chart' } : null,
  ].filter(Boolean)
  const editText = () => {
    const el = sel && sel.el !== null ? sel.el : headlineIndex(scene)
    const node = scene && scene.k && scene.k[el]
    // A claim's key names the field where that number first appears, which can be another slide: use it only when
    // it points into this slide.
    const here = docSlide === null ? /^(title|subtitle)\|/ : new RegExp(`^slides\\.${docSlide}\\.`)
    const inEl = node ? claimsInElement(scene, el).map(c => claims[c]).find(c => c && c.key && here.test(c.key)) : null
    const field = { stat: 'label', quote: 'quote', closing: 'heading' }[ftype] || 'heading'
    const kp = inEl ? inEl.key.split('|')[0] : ''
    const path = kp ? (/\.(bullets|left_items|right_items)\.\d+$/.test(kp) ? `${kp}.text` : kp) : docSlide === null ? 'title' : `slides.${docSlide}.${field}`
    setMode({ kind: 'text', path, text: node ? textOfNode(node).replace(/\s+/g, ' ').trim() : '' })
    setReviseOpen(true)
  }
  const act = a => {
    if (a.off || docSlide === null) return
    if (a.id === 'text') { editText(); return }
    setMode(null); setReviseOpen(true)
    edit.start({ kind: 'edit', action: a.id, label: a.label, frame: cur }, ROUTES.elementEdit(out.id), { kit_id: proof.kit_id, slide: docSlide, action: a.id })
  }
  const ask = text => {
    const slide = docSlide === null ? 0 : docSlide
    edit.start({ kind: 'edit', action: 'typed', label: 'Your change', frame: cur }, ROUTES.elementEdit(out.id), { kit_id: proof.kit_id, slide, action: 'typed', text, on: ftype === 'title' ? 'title' : '' })
  }
  const keep = async choice => {
    try {
      await api.post(ROUTES.keep(out.id), { job_id: job.id, choice })
      edit.setJob(null); setSel(null); setReviseOpen(false)
      await refresh()
      api.toast('Kept.')
    } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  const discard = async () => {
    const id = job && job.id
    edit.setJob(null)
    if (id && job.status === 'done') { try { await api.post(ROUTES.discard(out.id), { job_id: id }) } catch (e) { /* nothing to keep either way */ } }
  }
  const undo = async () => {
    try { await api.post(ROUTES.undo(out.id), {}); await refresh(); api.toast('Undone.') } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  const saveText = async () => {
    const t = (mode.text || '').trim()
    if (!t) return
    try { await api.post(ROUTES.text(out.id), { path: mode.path, text: t }); setMode(null); await refresh() } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  const startFix = cid => {
    const c = claims[cid]
    const f = (c.slides || [])[0]
    if (typeof f === 'number' && f !== cur) go(f)
    setReviseOpen(true)
    fix.start({ kind: 'fix', label: 'Fix it for me', cid, frame: typeof f === 'number' ? f : cur }, ROUTES.fix(out.id), { kit_id: proof.kit_id, key: c.key })
  }
  const acceptFix = async () => {
    try { await api.post(ROUTES.keep(out.id), { job_id: fix.job.id, choice: 0 }); fix.setJob(null); await refresh(); api.toast('Fixed. The number matches your source.') } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  const keepMine = async cid => {
    try {
      await api.post(ROUTES.decide(out.id), { key: claims[cid].key, action: 'keep' })
      if (fix.job && fix.job.cid === cid) fix.setJob(null)
      await refresh()
      api.toast('Kept on purpose. Noted on the trace card.')
    } catch (e) { api.toast(api.errText(e), 'bad') }
  }
  const swapBrand = async id => {
    if (id === proof.kit_id) return
    const name = ((st.kits || []).find(k => k.id === id) || {}).name || 'that brand'
    setBrandJob({ step: `Setting it in ${name}` })
    try {
      const rr = await api.post(ROUTES.kit(out.id), { kit_id: id, slot: 0 })
      api.pollJob(rr.job, async () => { setBrandJob(null); await refresh() }, j => { setBrandJob(null); api.toast(j.error || 'That brand could not be set.', 'bad') }, j => setBrandJob({ step: j.step || `Setting it in ${name}` }))
    } catch (e) { setBrandJob(null); api.toast(api.errText(e), 'bad') }
  }
  const remove = async () => { try { await api.del(ROUTES.del(out.id)); close(); api.toast('Deleted.') } catch (e) { api.toast(api.errText(e), 'bad') } }

  const hits = useMemo(() => {
    if (!reverse) return null
    const s = new Set()
    rows.forEach((rw, f) => { if ((rw.claims || []).some(c => claimRefs(claims[c]).includes(reverse))) s.add(typeof rw.i === 'number' ? rw.i : f) })
    return s
  }, [reverse, rows, claims])

  // Each checked number drawn on this slide, once, in reading order: the proof without hovering.
  const numbers = useMemo(() => {
    const seenIds = new Set()
    const drawn = []
    const visit = n => { if (!n || typeof n !== 'object') return; const c = trOf(n); if (c && claims[c] && !seenIds.has(c)) { seenIds.add(c); drawn.push(c) }; (n.k || []).forEach(visit) }
    visit(scene)
    return drawn.filter(c => claims[c].kind !== 'quote')
  }, [scene, claims])
  const selOnFrame = sel && sel.frame === cur
  return h('div', { ref: root, className: cls('ip-cv', revising && 'is-revising', folded && 'is-folded', reduced && 'is-still'), role: 'region', 'aria-label': out.title || 'Deck' },
    h('style', null, CSS),
    h(Head, { out, proof, st, kit, stamp, exportOff, close, swapBrand, brandJob, api, scenes, canUndo, undo, activeV, remove,
      revising, nFlags: flags.length, toggleRevise: () => { if (revising) { setSel(null); setMode(null); setReviseOpen(false); if (job && job.status !== 'running') discard() } else setReviseOpen(true) } }),
    h(Strip, { strip, folded, peek, setPeek, evidence, lit, reverse, setReverse, count: evidence.length }),
    h('main', { ref: stage, className: 'ip-cv-stage', onClick: () => { if (!job && !mode) setSel(null) } },
      shown ? h('div', { key: 'slot', className: 'ip-cv-slot', style: { width: `${artW}px` } },
        previewTree ? h('p', { key: 'tag', className: 'ip-cv-preview-tag' }, `Option ${chosen + 1}, not kept yet`) : null,
        h('div', { key: 'slide', className: cls('ip-cv-slide', selOnFrame && sel.el === null && 'is-selected', previewTree && 'is-preview'), style: { width: `${artW}px` },
          onClick: e => { e.stopPropagation(); if (!previewTree) { setSel({ frame: cur, el: null }); setMode(null) } } },
        h(Art, { scene: shown, width: artW, ctx: previewTree ? { live: false, claims } : ctx, label: `Slide ${cur + 1} of ${scenes.length}` }),
        selOnFrame && !previewTree && actions.length ? h(ActionBar, { actions, act, sel, artW }) : null)) : null,
      scenes.length > 1 ? h(Filmstrip, { key: 'film', film, scenes, rows, cur, go, hits, width: availW, flagged: new Set(flags.flatMap(([, c]) => c.slides || [])) }) : null,
      numbers.length && !previewTree ? h(Numbers, { key: 'nums', numbers, claims, active, width: artW,
        enter: cid => { clearTimeout(leaveT.current); const el = stage.current && stage.current.querySelector(`.ip-cv-slide [data-cid="${cid}"]`); setHot({ cid, el, via: 'row' }); seen() },
        leave: ctx.leave, pin: ctx.pin }) : null),
    h(Revise, {
      open: revising, fold: () => { setSel(null); setMode(null); setReviseOpen(false); if (job && job.status !== 'running') discard() },
      openIt: () => setReviseOpen(true), cur, scenes, ftype, docSlide, job, edit, chosen, setChosen, keep, discard, mode, setMode, saveText,
      flags, fix, startFix, acceptFix, keepMine, ask, claims, scene,
    }),
    active && claims[active] && !previewTree ? h(Trace, { root, stage, strip, film, cid: active, claim: claims[active], el: hot && hot.cid === active ? hot.el : null, reduced, used, folded: folded && !peek }) : null)
}

function claimsInElement(scene, idx) {
  const out = []
  const n = scene && scene.k && scene.k[idx]
  const visit = x => { if (!x) return; const c = trOf(x); if (c && !out.includes(c)) out.push(c); (x.k || []).forEach(visit) }
  visit(n)
  return out
}

/* ---- head: Back, the title, the brand, the one-sentence check, Undo, Export, and More (Delete) ---- */

function Head({ out, proof, st, kit, stamp, exportOff, close, swapBrand, brandJob, api, scenes, canUndo, undo, activeV, remove, revising, nFlags, toggleRevise }) {
  const kind = proof.kind === 'deck' ? `Slide deck, ${plural(scenes.length, 'slide')}` : proof.kind === 'visual' ? 'Graphic, 4:5' : 'One-pager, letter page'
  return h('div', { className: 'ip-cv-headbox' }, h('header', { className: 'ip-cv-head' },
    h(Button, { variant: 'secondary', className: 'ip-cv-back', onClick: close }, h(Codicon, { name: 'arrow-left', size: '14px' }), 'Back'),
    h('div', { className: 'ip-cv-title' }, h('strong', { title: out.title || '' }, out.title || 'Untitled'), h('span', null, kind)),
    h(BrandChip, { st, kit, onPick: swapBrand, busy: brandJob }),
    stamp ? h('p', { className: 'ip-cv-stamp', 'data-tone': stamp.tone, role: 'status' },
      h(Codicon, { name: stamp.tone === 'good' ? 'pass' : 'warning', size: '14px' }), h('span', null, stamp.text)) : null,
    h('div', { className: 'ip-cv-grow' }),
    api && api.openDesigns && ['deck', 'onepager', 'visual'].includes(proof.kind) ? h(Button, { variant: 'secondary', onClick: api.openDesigns }, 'Designs') : null,
    canUndo ? h(Button, { variant: 'secondary', onClick: undo, title: activeV && activeV.reason ? `Undo: ${activeV.reason}` : 'Undo the last change' },
      h(Codicon, { name: 'discard', size: '14px' }), 'Undo') : null,
    h(Button, { variant: 'secondary', className: cls('ip-cv-rev-btn', revising && 'is-on'), 'aria-pressed': revising, onClick: toggleRevise },
      h(Codicon, { name: 'edit', size: '14px' }), 'Revise',
      nFlags ? h('span', { className: 'ip-cv-rail-n is-bad', 'aria-label': `${plural(nFlags, 'number')} to look at` }, String(nFlags)) : null),
    h(ExportButton, { out, proof, off: exportOff, api }),
    h(MoreMenu, { onDelete: remove, what: proof.kind === 'deck' ? 'deck' : proof.kind === 'visual' ? 'graphic' : 'one-pager' })))
}

function swatchOf(k) {
  return (k && (k.accent || k.head || (k.bar && k.bar[2]))) || 'currentColor'
}

function BrandChip({ st, kit, onPick, busy }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  useOutside(open, box, () => setOpen(false))
  const kits = st.kits || []
  const groups = [['Your brands', kits.filter(x => !x.starter)], ['Studio brands', kits.filter(x => x.starter && x.tier === 'studio')],
    ['Earlier starters', kits.filter(x => x.starter && x.tier !== 'studio')]].filter(g => g[1].length)
  const keyNav = e => {
    if (!['ArrowDown', 'ArrowUp'].includes(e.key)) return
    e.preventDefault()
    const items = [...box.current.querySelectorAll('[role=menuitemradio]')]
    const i = items.indexOf(document.activeElement)
    const n = items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]
    if (n) n.focus()
  }
  return h('div', { ref: box, className: 'ip-cv-pop' },
    h('button', { type: 'button', className: 'ip-cv-chip', 'aria-haspopup': 'menu', 'aria-expanded': open, onClick: () => setOpen(!open), title: 'Set it in another brand' },
      h('span', { className: 'ip-cv-sw', style: { background: swatchOf(kit) }, 'aria-hidden': 'true' }),
      h('span', { className: 'ip-cv-chip-name' }, busy ? busy.step : kit.name),
      h(Codicon, { name: busy ? 'loading' : 'chevron-down', size: '14px', className: busy ? 'codicon-modifier-spin' : '' })),
    open ? h('div', { className: 'ip-cv-menu', role: 'menu', 'aria-label': 'Brand', onKeyDown: keyNav },
      groups.map(([label, list]) => h('div', { key: label, role: 'group', 'aria-label': label },
        h('p', { className: 'ip-cv-menu-h' }, label),
        list.map(k => h('button', { key: k.id, type: 'button', role: 'menuitemradio', 'aria-checked': k.id === kit.id, className: 'ip-cv-menu-item',
          onClick: () => { setOpen(false); onPick(k.id) } },
        h('span', { className: 'ip-cv-sw', style: { background: swatchOf(k) }, 'aria-hidden': 'true' }), k.name,
        k.id === kit.id ? h(Codicon, { name: 'check', size: '14px' }) : null))))) : null)
}

function ExportButton({ out, proof, off, api }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const box = useRef(null)
  useOutside(open, box, () => setOpen(false))
  const go = async format => {
    setOpen(false); setBusy(true)
    const save = captureGatewayFileDownload()
    try { const r = await api.post(ROUTES.export(out.id), { kit_id: proof.kit_id, format }); await save(r.path, r.name) } catch (e) { api.toast(api.errText(e), 'bad') }
    setBusy(false)
  }
  const formats = Object.entries(out.formats || { pdf: 'PDF' }).filter(([f]) => f !== 'audio')
  return h('div', { ref: box, className: 'ip-cv-pop ip-cv-export' },
    h(Button, { loading: busy, 'aria-disabled': off ? 'true' : undefined, className: off ? 'ip-cv-off' : '', 'aria-describedby': off ? 'ip-cv-export-why' : undefined,
      onClick: () => { if (!off) setOpen(!open) }, 'aria-haspopup': 'menu', 'aria-expanded': open }, 'Export'),
    off ? h('span', { id: 'ip-cv-export-why', role: 'tooltip', className: 'ip-cv-why' }, off) : null,
    open ? h('div', { className: 'ip-cv-menu is-right', role: 'menu' },
      formats.map(([f, l]) => h('button', { key: f, type: 'button', role: 'menuitem', className: 'ip-cv-menu-item', onClick: () => go(f) }, l))) : null)
}

function MoreMenu({ onDelete, what }) {
  const [open, setOpen] = useState(false)
  const [armed, setArmed] = useState(false)
  const box = useRef(null)
  useOutside(open, box, () => { setOpen(false); setArmed(false) })
  return h('div', { ref: box, className: 'ip-cv-pop ip-cv-more' },
    h('button', { type: 'button', className: 'ip-cv-icon is-boxed', 'aria-label': 'More', 'aria-haspopup': 'menu', 'aria-expanded': open, title: 'More', onClick: () => setOpen(!open) },
      h(Codicon, { name: 'ellipsis', size: '14px' })),
    open ? h('div', { className: 'ip-cv-menu is-right', role: 'menu' },
      armed
        ? h('div', { className: 'ip-cv-confirm' }, h('p', null, `Delete this ${what}? This can’t be undone.`),
          h('div', { className: 'ip-cv-row' },
            h('button', { type: 'button', role: 'menuitem', className: 'ip-cv-menu-item is-danger', onClick: () => { setOpen(false); setArmed(false); onDelete() } }, 'Delete'),
            h('button', { type: 'button', role: 'menuitem', className: 'ip-cv-menu-item', onClick: () => setArmed(false) }, 'Cancel')))
        : h('button', { type: 'button', role: 'menuitem', className: 'ip-cv-menu-item is-danger', onClick: () => setArmed(true) },
          h(Codicon, { name: 'trash', size: '14px' }), `Delete this ${what}`)) : null)
}

/* ---- the strip ---- */

function Strip({ strip, folded, peek, setPeek, evidence, lit, reverse, setReverse, count }) {
  const list = h('div', { ref: strip, className: 'ip-cv-strip-list' },
    evidence.length ? evidence.map(it => h(EvidenceItem, { key: it.ref, it, lit, reverse, onPick: ref => setReverse(r => (r === ref ? null : ref)) }))
      : h('p', { className: 'ip-cv-strip-none' }, 'Nothing on this slide comes from your sources. It has no numbers or quotes to check.'))
  if (folded) {
    return h('aside', { className: 'ip-cv-strip is-rail', 'aria-label': 'Evidence for this slide' },
      h('button', { type: 'button', className: 'ip-cv-rail-btn', 'aria-expanded': peek, onClick: () => setPeek(!peek), title: peek ? 'Hide the evidence' : 'Show the evidence' },
        h(Codicon, { name: 'book', size: '16px' }), h('span', { className: 'ip-cv-rail-label' }, 'Evidence'),
        count ? h('span', { className: 'ip-cv-rail-n' }, String(count)) : null),
      peek ? h('div', { className: 'ip-cv-peek' }, h('h2', { className: 'ip-cv-strip-h' }, 'Evidence for this slide'), list) : null)
  }
  return h('aside', { className: 'ip-cv-strip', 'aria-label': 'Evidence for this slide' }, h('h2', { className: 'ip-cv-strip-h' }, 'Evidence for this slide'), list)
}

function EvidenceItem({ it, lit, reverse, onPick }) {
  const p = it.p
  const where = [p.source, unquote(p.locator)].filter(Boolean).join(', ')
  return h('div', { className: cls('ip-cv-ev', reverse === it.ref && 'is-picked') },
    h('p', { className: 'ip-cv-ev-src' }, h('span', { className: 'ip-cv-ev-n', 'aria-hidden': 'true' }, String(p.source_n || '')), where),
    it.sentences.map((s, i) => h('button', { key: i, type: 'button', className: 'ip-cv-ev-s', 'aria-pressed': reverse === it.ref,
      title: 'Show the slides that use this sentence', onClick: () => onPick(it.ref) }, marked(s, lit))))
}

function marked(s, lit) {
  const out = []
  let at = 0
  for (const m of s.marks) {
    if (m.start < at) continue
    if (m.start > at) out.push(s.text.slice(at, m.start))
    out.push(h('span', { key: m.start, className: cls('ip-cv-n', m.keys.some(k => lit.has(k)) && 'is-lit'), 'data-marks': m.keys.join(' ') }, s.text.slice(m.start, m.start + m.len)))
    at = m.start + m.len
  }
  if (at < s.text.length) out.push(s.text.slice(at))
  return out
}

/* ---- numbers on this slide: each with its check and its source; hovering a row draws its trace ---- */

function Numbers({ numbers, claims, active, width, enter, leave, pin }) {
  return h('section', { className: 'ip-cv-nums', style: { maxWidth: `${width}px` }, 'aria-label': 'Numbers on this slide', onClick: e => e.stopPropagation() },
    h('h2', { className: 'ip-cv-nums-h' }, 'Numbers on this slide'),
    h('div', { className: 'ip-cv-nums-list' }, numbers.map(cid => {
      const c = claims[cid]
      const tone = toneOf(c)
      const src = c.status === 'missing' ? 'Not in your sources' : c.status === 'brief' ? 'From your request'
        : [c.status === 'computed' ? 'Worked out' : '', c.source].filter(Boolean).join(', ')
      return h('button', { key: cid, type: 'button', className: cls('ip-cv-num', active === cid && 'is-lit'), 'data-tone': tone, 'data-row': cid,
        'aria-label': `${c.value}: ${statusWords(c)}`, onMouseEnter: () => enter(cid), onMouseLeave: () => leave(cid), onFocus: () => enter(cid), onBlur: () => leave(cid),
        onClick: () => pin(cid) },
      h('span', { className: 'ip-cv-num-v' }, c.value),
      h(Codicon, { name: tone === 'good' ? 'check' : tone === 'warn' ? 'info' : 'warning', size: '14px' }),
      h('span', { className: 'ip-cv-num-s' }, src))
    })))
}

/* ---- the filmstrip: numbers under the thumbnails, an edge fade and arrows when it clips ---- */

function Filmstrip({ film, scenes, rows, cur, go, hits, width, flagged }) {
  const n = scenes.length
  const gap = 8
  const tw = Math.max(72, Math.min(120, Math.floor((width - 56 - gap * (n - 1)) / n)))
  const [clip, setClip] = useState({ left: false, right: false })
  const read = () => {
    const el = film.current
    if (!el) return
    const left = el.scrollLeft > 2, right = el.scrollLeft + el.clientWidth < el.scrollWidth - 2
    setClip(c => (c.left === left && c.right === right ? c : { left, right }))
  }
  useLayoutEffect(read)
  useEffect(() => {
    const el = film.current && film.current.querySelector('[aria-current=true]')
    if (el) el.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  }, [cur])
  const step = d => { const el = film.current; if (el) el.scrollBy({ left: d * (el.clientWidth - tw), behavior: 'smooth' }) }
  return h('div', { className: cls('ip-cv-filmwrap', clip.left && 'clip-l', clip.right && 'clip-r'), style: { maxWidth: `${width}px` }, onClick: e => e.stopPropagation() },
    // keyed: h() drops empty children, so without keys the strip would remount (and lose its scroll) when an arrow shows
    clip.left ? h('button', { key: 'l', type: 'button', className: 'ip-cv-arrow is-l', 'aria-label': 'Earlier slides', onClick: () => step(-1) }, h(Codicon, { name: 'chevron-left', size: '16px' })) : null,
    h('nav', { key: 'film', ref: film, className: cls('ip-cv-film', hits && 'is-reverse'), 'aria-label': 'Slides', onScroll: read },
      scenes.map((sc, i) => {
        const r = rows[i] || {}
        const on = hits && hits.has(i)
        return h('button', { key: i, type: 'button', className: cls('ip-cv-thumb', i === cur && 'is-current', on && 'is-hit', hits && !on && 'is-dim'),
          'aria-current': i === cur ? 'true' : undefined, 'aria-label': `Slide ${i + 1}${r.title ? `: ${r.title}` : ''}`, 'data-frame': i, onClick: () => go(i) },
        h('span', { role: 'img', 'aria-hidden': 'true', className: 'ip-cv-thumb-img' }, h(Art, { scene: sc, width: tw })),
        h('span', { className: 'ip-cv-thumb-n', 'aria-hidden': 'true' }, String(i + 1), flagged.has(i) ? h('span', { className: 'ip-cv-thumb-flag' }) : null))
      })),
    clip.right ? h('button', { key: 'r', type: 'button', className: 'ip-cv-arrow is-r', 'aria-label': 'Later slides', onClick: () => step(1) }, h(Codicon, { name: 'chevron-right', size: '16px' })) : null)
}

/* ---- the floating action bar, above the selection ---- */

function ActionBar({ actions, act, sel, artW }) {
  const [box, setBox] = useState(null)
  const bar = useRef(null)
  useLayoutEffect(() => {
    const slide = bar.current && bar.current.parentElement
    if (!slide) return
    const target = sel.el === null ? null : slide.querySelector(`[data-el="${sel.el}"]`)
    const sr = slide.getBoundingClientRect()
    const r = target ? target.getBoundingClientRect() : sr
    const bw = bar.current.offsetWidth
    setBox({ left: Math.max(0, Math.min(r.left - sr.left, sr.width - bw)), top: Math.max(-48, r.top - sr.top - 48) })
  }, [sel.el, artW])
  return h('div', { ref: bar, className: 'ip-cv-bar', role: 'toolbar', 'aria-label': 'Change this slide', onClick: e => e.stopPropagation(),
    style: box ? { left: `${box.left}px`, top: `${box.top}px` } : { visibility: 'hidden' } },
  actions.map((a, i) => [i === 1 ? h('span', { key: 'sep', className: 'ip-cv-bar-sep', 'aria-hidden': 'true' }) : null,
    h('button', { key: a.id, type: 'button', className: cls('ip-cv-bar-btn', a.off && 'is-off'), 'aria-disabled': a.off ? 'true' : undefined,
      'aria-describedby': a.off ? `ip-cv-why-${a.id}` : undefined, onClick: () => act(a) }, a.label,
    a.off ? h('span', { id: `ip-cv-why-${a.id}`, role: 'tooltip', className: 'ip-cv-why' }, a.off) : null)]))
}

/* ---- Revise ---- */

function Revise(p) {
  const { open, fold, openIt, cur, scenes, job, edit, chosen, setChosen, keep, discard, mode, setMode, saveText, flags, fix, startFix, acceptFix, keepMine, ask, claims, scene, docSlide } = p
  const [text, setText] = useState('')
  if (!open) return null // Revise opens from its button beside Export
  const send = () => { const t = text.trim(); if (!t) return; ask(t); setText('') }
  const showJob = job && job.frame === cur
  return h('aside', { className: 'ip-cv-revise', 'aria-label': 'Revise' },
    h('div', { className: 'ip-cv-rev-head' }, h('h2', null, 'Revise'), h('span', { className: 'ip-cv-rev-where' }, `Slide ${cur + 1}`),
      h('button', { type: 'button', className: 'ip-cv-icon', onClick: fold, 'aria-label': 'Close Revise', title: 'Close Revise' }, h(Codicon, { name: 'close', size: '14px' }))),
    flags.length ? h('section', { className: 'ip-cv-flags', 'aria-label': 'Numbers to look at' },
      flags.map(([cid, c]) => h(Flag, { key: cid, cid, c, fix, startFix, acceptFix, keepMine }))) : null,
    mode && mode.kind === 'text' ? h('section', { className: 'ip-cv-card-s' },
      h('label', { className: 'ip-cv-lab', htmlFor: 'ip-cv-edit' }, 'Edit text'),
      h('textarea', { id: 'ip-cv-edit', rows: 3, value: mode.text, onChange: e => setMode({ ...mode, text: e.target.value }), autoFocus: true,
        onKeyDown: e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); saveText() } } }),
      h('div', { className: 'ip-cv-row' }, h(Button, { onClick: saveText, disabled: !mode.text.trim() }, 'Save'), h(Button, { variant: 'secondary', onClick: () => setMode(null) }, 'Cancel'))) : null,
    showJob ? h(JobView, { job, edit, chosen, setChosen, keep, discard, scene }) : null,
    h('section', { className: 'ip-cv-compose' },
      h('label', { className: 'ip-cv-lab', htmlFor: 'ip-cv-compose' }, 'Ask for a change'),
      h('textarea', { id: 'ip-cv-compose', rows: 2, value: text, placeholder: 'Change the title to: …', onChange: e => setText(e.target.value),
        onKeyDown: e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } } }),
      h(Button, { variant: 'secondary', disabled: !text.trim() || (job && job.status === 'running'), onClick: send }, 'Send')))
}

function Steps({ job, onStop }) {
  useTick(job.status === 'running')
  const now = Date.now() / 1000
  const steps = job.steps && job.steps.length ? job.steps : [{ text: job.step || 'Starting', at: job.started, done_at: null }]
  return h('div', { className: 'ip-cv-steps', role: 'status' },
    steps.map((s, i) => {
      const last = i === steps.length - 1
      const done = s.done_at || !last || job.status !== 'running'
      const secs = Math.max(0, Math.round(((s.done_at || (last && job.status === 'running' ? now : (steps[i + 1] && steps[i + 1].at) || now)) - (s.at || job.started))))
      return h('p', { key: i, className: cls('ip-cv-step', done && 'is-done') },
        done ? h(Codicon, { name: 'check', size: '14px' }) : h('span', { className: 'ip-cv-spin', 'aria-hidden': 'true' }), h('span', null, s.text), h('span', { className: 'ip-cv-secs' }, `${secs} s`))
    }),
    job.status === 'running' && onStop ? h('div', { className: 'ip-cv-row' }, h(Button, { variant: 'secondary', onClick: onStop }, 'Stop')) : null)
}

const headOf = sl => (!sl ? '' : typeof sl === 'string' ? sl : sl.heading || sl.label || sl.quote || sl.text || sl.title || '')

function JobView({ job, edit, chosen, setChosen, keep, discard, scene }) {
  const head = h('p', { className: 'ip-cv-lab' }, job.label)
  if (job.status === 'running') return h('section', { className: 'ip-cv-card-s' }, head, h(Steps, { job, onStop: edit.stop }))
  if (job.status === 'failed' || job.status === 'stopped') {
    return h('section', { className: 'ip-cv-card-s', 'data-tone': job.status === 'failed' ? 'bad' : undefined, role: 'alert' }, head,
      h('p', null, job.status === 'stopped' ? 'Stopped. The slide is as it was.' : job.error),
      h('div', { className: 'ip-cv-row' }, h(Button, { onClick: edit.retry }, 'Retry'), h(Button, { variant: 'secondary', onClick: () => edit.setJob(null) }, 'Close')))
  }
  const r = job.result || {}
  const opts = Array.isArray(r.options) ? r.options : []
  if (r.status && r.status !== 'ok' || !opts.length) {
    return h('section', { className: 'ip-cv-card-s' }, head, h('p', null, r.message || 'Nothing new passed the check against your sources, so the slide stays as it is.'),
      h('div', { className: 'ip-cv-row' }, r.status === 'unchanged' ? h(Button, { onClick: edit.retry }, 'Retry') : null, h(Button, { variant: 'secondary', onClick: () => edit.setJob(null) }, 'Close')))
  }
  // A typed line becomes what the backend read it as: a new slide ("insert") or the person's own words for a title ("retitle").
  const act = r.action && r.action !== 'typed' ? r.action : job.action
  const adds = act === 'insert' || act === 'typed'
  const retitle = act === 'retitle'
  const visual = act === 'chart' || adds || (retitle && opts.some(o => o.tree))
  const before = r.before_tree || (visual && !retitle ? scene : null)
  return h('section', { className: 'ip-cv-card-s', 'aria-label': job.label }, head,
    h('div', { className: 'ip-cv-now' }, h('p', { className: 'ip-cv-lab-s' }, adds ? `New slide after slide ${r.insert_after || ''}` : 'Now'),
      adds ? null
        : visual && before ? h('div', { className: 'ip-cv-mini' }, h(Art, { scene: before, width: MINI_W })) : h('p', { className: 'ip-cv-now-t' }, retitle ? r.before_text || headOf(r.before) : headOf(r.before))),
    opts.map((o, i) => {
      const on = i === chosen
      const ok = !o.check || o.check.status === 'ok'
      return h('div', { key: i, className: cls('ip-cv-opt', on && 'is-on'), onClick: () => setChosen(i) },
        h('p', { className: 'ip-cv-lab-s' }, opts.length > 1 ? `Option ${i + 1}` : 'New'),
        visual ? (o.tree ? h('div', { className: 'ip-cv-mini' }, h(Art, { scene: o.tree, width: MINI_W })) : retitle ? h('p', { className: 'ip-cv-opt-t' }, o.text) : h(Sketch, { sl: o.slide })) : h('p', { className: 'ip-cv-opt-t' }, retitle ? o.text || headOf(o.slide) : headOf(o.slide)),
        o.check && o.check.label ? h('p', { className: cls('ip-cv-chk', ok ? 'is-good' : 'is-bad') }, h(Codicon, { name: ok ? 'pass' : 'warning', size: '14px' }), o.check.label) : null,
        on ? h(Button, { disabled: !ok, onClick: e => { e.stopPropagation(); keep(i) } }, 'Keep')
          : h(Button, { variant: 'secondary', onClick: e => { e.stopPropagation(); setChosen(i) } }, 'Use this'))
    }),
    h('div', { className: 'ip-cv-foot' }, h('p', { className: 'ip-cv-by' }, r.by || 'Written by your Hermes model'),
      h('button', { type: 'button', className: 'ip-cv-link', onClick: discard }, 'Discard')))
}

// A plain drawing of a slide that has no picture yet: its headline, and its bars to scale when it has bars.
function Sketch({ sl }) {
  if (!sl) return null
  const bars = Array.isArray(sl.bars) ? sl.bars : []
  const val = b => parseFloat(String(b.value || '').replace(/[^\d.]/g, '')) || 0
  const max = Math.max(1, ...bars.map(val))
  return h('div', { className: 'ip-cv-sketch' }, h('p', { className: 'ip-cv-opt-t' }, headOf(sl)),
    bars.map((b, i) => h('div', { key: i, className: 'ip-cv-sk-row' }, h('span', { className: 'ip-cv-sk-l' }, b.label),
      h('span', { className: 'ip-cv-sk-bar', style: { width: `${Math.round(100 * val(b) / max)}%` } }), h('span', { className: 'ip-cv-sk-v' }, b.value))))
}

function flagSentence(c) {
  const closest = c.line && c.line.before ? ` The closest is in the ${c.source || 'source'}${c.locator ? `, ${unquote(c.locator)}` : ''}.` : ''
  return `${c.value} isn’t in your sources.${closest}`
}

// One flag: the plain sentence and Fix it for me first. The word-by-word change shows only after the click.
function Flag({ cid, c, fix, startFix, acceptFix, keepMine }) {
  const j = fix.job && fix.job.cid === cid ? fix.job : null
  const where = (c.slides || []).length ? `Slide ${c.slides[0] + 1}` : ''
  if (!j) {
    return h('div', { className: 'ip-cv-flag' },
      h('p', { className: 'ip-cv-flag-h' }, h(Codicon, { name: 'warning', size: '14px' }), where ? `${where}: a number to look at` : 'A number to look at'),
      h('p', null, flagSentence(c)),
      h('div', { className: 'ip-cv-row' },
        c.fixable === false ? null : h(Button, { onClick: () => startFix(cid) }, 'Fix it for me'),
        h(Button, { variant: 'secondary', onClick: () => keepMine(cid), title: 'Kept on purpose. Noted on the trace card.' }, 'Keep mine, I checked')))
  }
  if (j.status === 'running') return h('div', { className: 'ip-cv-flag' }, h('p', { className: 'ip-cv-flag-h' }, 'Fixing the number'), h(Steps, { job: j, onStop: fix.stop }))
  const r = j.result || {}
  if (j.status !== 'done' || r.status !== 'ok') {
    return h('div', { className: 'ip-cv-flag', role: 'alert' }, h('p', null, j.error || (r.check && r.check.label) || 'The correction didn’t match your sources, so nothing changed.'),
      h('div', { className: 'ip-cv-row' }, h(Button, { onClick: fix.retry }, 'Retry'), h(Button, { variant: 'secondary', onClick: () => keepMine(cid) }, 'Keep mine, I checked')))
  }
  // Diff parts join with "" once each part keeps its own spaces; older results dropped them, so a space goes back
  // between two parts that would otherwise run together.
  const raw = Array.isArray(r.diff) ? r.diff : [{ op: 'same', text: r.after }]
  const parts = raw.map((d, k) => (k && !/\s$/.test(raw[k - 1].text || '') && !/^\s/.test(d.text || '') ? { ...d, pad: true } : d))
  return h('div', { className: 'ip-cv-flag is-fixed' },
    h('p', { className: 'ip-cv-lab-s' }, 'Suggested change'),
    h('p', { className: 'ip-cv-diff' }, parts.map((d, k) => [d.pad ? ' ' : null, h('span', { key: k, className: `is-${d.op}` }, d.text)])),
    r.check && r.check.label ? h('p', { className: 'ip-cv-chk is-good' }, h(Codicon, { name: 'pass', size: '14px' }), r.check.label) : null,
    h('div', { className: 'ip-cv-row' }, h(Button, { onClick: acceptFix }, 'Accept'), h(Button, { variant: 'secondary', onClick: () => keepMine(cid) }, 'Keep mine, I checked')),
    h('p', { className: 'ip-cv-by' }, r.by || 'Written by your Hermes model'))
}

/* ---- the trace: the tint, one routed line per lit word, and the card in free space beside the element ---- */

// What a line or the card must keep clear of on the slide: the words (tight, per text line) and every drawn leaf
// (bars, rules, dots), as viewport rects. `skip` is left out (the number the line lands on).
function obstaclesIn(slide, skip) {
  const out = []
  if (!slide) return out
  const so = slide.getBoundingClientRect()
  const area = so.width * so.height
  const walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT)
  const range = document.createRange()
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (!t.textContent.trim() || (skip && skip.contains(t))) continue
    range.selectNodeContents(t)
    for (const r of range.getClientRects()) if (r.width > 0 && r.height > 0) out.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom, word: true })
  }
  for (const e of slide.querySelectorAll('.ip-cv-art *')) {
    // a box that holds words counts as its words (above), not as its full-width line box
    if (e === skip || (skip && skip.contains(e)) || e.firstElementChild || e.textContent.trim()) continue
    const r = e.getBoundingClientRect()
    if (r.width < 1 || r.height < 1 || r.width * r.height > area * 0.25) continue
    out.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom })
  }
  return out
}

// A line from (x0, y) to (x1, y) or (x, y0) to (x, y1), with `pad` px of room, crosses none of `obs`.
const clearH = (obs, y, xa, xb, pad) => !obs.some(o => o.top - pad < y && o.bottom + pad > y && o.left - pad < Math.max(xa, xb) && o.right + pad > Math.min(xa, xb))
const clearV = (obs, x, ya, yb, pad) => !obs.some(o => o.left - pad < x && o.right + pad > x && o.top - pad < Math.max(ya, yb) && o.bottom + pad > Math.min(ya, yb))

// The way into the slide: from the gutter `gx` to the number `T`, never across the slide's words. Straight in at
// the number's middle when that row is clear; else along the clearest free row above or below, then down (or up)
// onto the number. Returns the points from the gutter on, ending on the number's edge.
function routeIn(obs, so, T, gx) {
  const cy = T.top + T.height / 2, cx = T.left + T.width / 2
  if (clearH(obs, cy, so.left - 1, T.left - 2, 5)) return [[gx, cy], [T.left - 4, cy]]
  const ok = y => clearH(obs, y, so.left - 1, cx, 5) && clearV(obs, cx, y, y < T.top ? T.top : T.bottom, 4)
  const band = (from, dir, stop) => {
    let y = from
    while ((dir < 0 ? y > stop : y < stop) && !ok(y)) y += dir * 2
    if (dir < 0 ? y <= stop : y >= stop) return null
    let z = y
    while ((dir < 0 ? z - 2 > stop : z + 2 < stop) && Math.abs(z - y) < 28 && ok(z + dir * 2)) z += dir * 2
    return { y: (y + z) / 2, d: Math.abs((y + z) / 2 - (dir < 0 ? T.top : T.bottom)) }
  }
  const up = band(T.top - 6, -1, so.top + 4)
  const down = band(T.bottom + 6, 1, so.bottom - 4)
  const best = [up, down].filter(Boolean).sort((a, b) => a.d - b.d)[0]
  if (!best) return [[gx, cy], [T.left - 4, cy]]
  return [[gx, best.y], [cx, best.y], [cx, best.y < T.top ? T.top - 2 : T.bottom + 2]]
}

// Points to an SVG path with small rounded elbows.
function roundPath(pts, r) {
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
  for (let i = 1; i < pts.length; i++) {
    const [x, y] = pts[i]
    if (i === pts.length - 1) { d += ` L${x.toFixed(1)} ${y.toFixed(1)}`; break }
    const [px, py] = pts[i - 1], [nx, ny] = pts[i + 1]
    const a = Math.min(r, Math.hypot(x - px, y - py) / 2), b = Math.min(r, Math.hypot(nx - x, ny - y) / 2)
    const l1 = Math.hypot(x - px, y - py) || 1, l2 = Math.hypot(nx - x, ny - y) || 1
    const ux = (x - px) / l1, uy = (y - py) / l1, vx = (nx - x) / l2, vy = (ny - y) / l2
    d += ` L${(x - ux * a).toFixed(1)} ${(y - uy * a).toFixed(1)} Q${x.toFixed(1)} ${y.toFixed(1)} ${(x + vx * b).toFixed(1)} ${(y + vy * b).toFixed(1)}`
  }
  return d
}

// For a bar: one straight line, or one elbow, from `a` (the gutter) to `P` (the bar's left end, at its middle),
// crossing no word and no other bar (hairline rules and the axis may be crossed). The shortest such path; null when
// there is none. Returns the points after `a`.
function elbowTo(obs, a, P, so) {
  const pad = 4
  const near = o => P[0] >= o.left - 8 && P[0] <= o.right + 8 && P[1] >= o.top - 8 && P[1] <= o.bottom + 8
  const solid = obs.filter(o => (o.word || Math.min(o.right - o.left, o.bottom - o.top) >= 3) && !near(o))
  const clear = (p, q) => {
    const n = Math.max(1, Math.ceil(Math.hypot(q[0] - p[0], q[1] - p[1]) / 3))
    for (let i = 0; i <= n; i++) {
      const x = p[0] + (q[0] - p[0]) * i / n, y = p[1] + (q[1] - p[1]) * i / n
      if (solid.some(o => x > o.left - pad && x < o.right + pad && y > o.top - pad && y < o.bottom + pad)) return false
    }
    return true
  }
  if (clear(a, P)) return [P]
  const cands = []
  for (let x = a[0]; x < P[0] - 2; x += 4) {
    for (let y = so.top + 4; y < so.bottom - 4; y += 4) cands.push([x, y, Math.hypot(x - a[0], y - a[1]) + Math.hypot(P[0] - x, P[1] - y)])
  }
  cands.sort((m, n) => m[2] - n[2])
  for (const [x, y] of cands) if (clear([x, y], P) && clear(a, [x, y])) return [[x, y], P]
  return null
}

function Trace({ root, stage, strip, film, cid, claim, el, reduced, used, folded }) {
  const [geo, setGeo] = useState(null)
  const card = useRef(null)
  useLayoutEffect(() => {
    const R = root.current, S = stage.current, L = strip.current
    if (!R || !S) return
    const rr = R.getBoundingClientRect()
    const from = el && el.isConnected && el.closest('.ip-cv-slide') ? el : S.querySelector(`.ip-cv-slide [data-cid="${cid}"]`)
    if (!from) { setGeo(null); return }
    const slide = S.querySelector('.ip-cv-slide')
    const so = slide.getBoundingClientRect()
    const fr = from.getBoundingClientRect()
    // The line lands on the claim itself: a number on its text; a bar at its left end, at its middle (the bar is the
    // claim; its value label beside it is tinted with it).
    const labels = [...S.querySelectorAll(`.ip-cv-slide span[data-cid="${cid}"]`)]
    const near = r => labels.map(n => [n, n.getBoundingClientRect()]).sort((a, b) => Math.abs(a[1].top + a[1].height / 2 - (r.top + r.height / 2)) - Math.abs(b[1].top + b[1].height / 2 - (r.top + r.height / 2)))[0]
    const isBar = from.tagName !== 'SPAN'
    const land = [from, fr]
    const T = land[1]
    const st = S.getBoundingClientRect()
    const fm = film.current ? film.current.getBoundingClientRect() : null
    const obsLine = obstaclesIn(slide, land[0])
    const lines = []
    if (L && !folded) {
      const lr = L.getBoundingClientRect()
      const gx = Math.max(lr.right + 6, so.left - 10)
      const lab = isBar ? near(fr) : null
      const inner = isBar ? null : routeIn(obsLine, so, T, gx)
      for (const m of L.querySelectorAll(markSel(cid, claim))) {
        const mr = m.getBoundingClientRect()
        // The source end sits on the lit number's underline and runs out along it to the strip's edge.
        let y0 = mr.bottom + 1, x0 = mr.left + Math.min(mr.width / 2, 10), edge = false
        if (mr.bottom < lr.top + 30) { y0 = lr.top + 30; x0 = lr.right - 8; edge = true } else if (mr.top > lr.bottom - 8) { y0 = lr.bottom - 8; x0 = lr.right - 8; edge = true }
        const tail = !isBar ? inner : elbowTo(obsLine, [gx, y0], [T.left + 1, T.top + T.height / 2], so) || elbowTo(obsLine, [gx, y0], [T.left + 8, T.top - 1], so) || elbowTo(obsLine, [gx, y0], [T.left + 8, T.bottom + 1], so) || routeIn(obstaclesIn(slide, lab ? lab[0] : from), so, lab ? lab[1] : T, gx)
        const pts = [[x0, y0], [gx, y0], ...tail].filter((q, i, a) => !i || Math.abs(q[0] - a[i - 1][0]) > 0.5 || Math.abs(q[1] - a[i - 1][1]) > 0.5)
        const loc = pts.map(([x, y]) => [x - rr.left, y - rr.top])
        lines.push({ key: `${m.dataset.marks}@${lines.length}`, d: roundPath(loc, 7), a: loc[0], b: loc[loc.length - 1], edge, pts })
      }
    }
    // The card: in free space beside the element, then above or below it, covering no word, bar or line on the
    // slide; never over the filmstrip. Failing that, a free place on the stage close by. When the only free place
    // for the full card is far from the number (a dense slide), the card turns into one short line (the check and
    // the source) that fits the narrow gaps beside the number. Failing that, the least covered of the first places.
    const compact = !!(geo && geo.compact === cid)
    const canCompact = !folded && claim.status !== 'missing'
    const cw = card.current ? card.current.offsetWidth : 272
    const ch = card.current ? card.current.offsetHeight : 96
    const gap = 14
    const floor = (fm ? fm.top : st.bottom) - 10
    const own = [fr, T, ...labels.map(n => n.getBoundingClientRect()).filter(o => o.top < fr.bottom + 4 && o.bottom > fr.top - 4)]
    const u = { left: Math.min(...own.map(o => o.left)), right: Math.max(...own.map(o => o.right)), top: Math.min(...own.map(o => o.top)), bottom: Math.max(...own.map(o => o.bottom)) }
    const block = from.tagName === 'SPAN' ? from.closest('[data-el]') : null
    let bx = u
    if (block) {
      const rg = document.createRange(); rg.selectNodeContents(block)
      const rs = [...rg.getClientRects()].filter(r => r.width > 0)
      if (rs.length) bx = { left: Math.min(...rs.map(r => r.left)), right: Math.max(...rs.map(r => r.right)), top: Math.min(...rs.map(r => r.top)), bottom: Math.max(...rs.map(r => r.bottom)) }
    }
    const mid = (u.top + u.bottom) / 2 - ch / 2
    const tries = [
      [u.right + gap, mid], [bx.right + gap, (bx.top + bx.bottom) / 2 - ch / 2], [u.right + gap, u.top - 4],
      [u.left, bx.bottom + gap], [u.left, bx.top - gap - ch], [bx.right - cw, bx.bottom + gap], [bx.right - cw, bx.top - gap - ch],
      [u.left - gap - cw, mid],
    ]
    const obsCard = obstaclesIn(slide, null).concat(lines.flatMap(l => l.pts.slice(1).map((q, i) => {
      const p0 = l.pts[i]
      return { left: Math.min(p0[0], q[0]) - 3, right: Math.max(p0[0], q[0]) + 3, top: Math.min(p0[1], q[1]) - 3, bottom: Math.max(p0[1], q[1]) + 3 }
    })))
    const cover = (x, y) => obsCard.reduce((n, o) => n + Math.max(0, Math.min(o.right, x + cw) - Math.max(o.left, x)) * Math.max(0, Math.min(o.bottom, y + ch) - Math.max(o.top, y)), 0)
    const fits = (x, y) => x >= st.left + 8 && x + cw <= st.right - 8 && y >= st.top + 8 && y + ch <= floor
    let spot = tries.find(([x, y]) => fits(x, y) && !cover(x, y)), far = false
    if (!spot) {
      const cx = (u.left + u.right) / 2, cy = (u.top + u.bottom) / 2
      let best = null
      for (let y = st.top + 8; y + ch <= floor; y += 12) {
        for (let x = st.left + 8; x + cw <= st.right - 8; x += 12) {
          if (x < u.right + 6 && x + cw > u.left - 6 && y < u.bottom + 6 && y + ch > u.top - 6) continue
          if (cover(x, y)) continue
          const d = Math.hypot(Math.max(u.left - (x + cw), x - u.right, 0), Math.max(u.top - (y + ch), y - u.bottom, 0)) + 0.02 * Math.hypot(x + cw / 2 - cx, y + ch / 2 - cy)
          if (!best || d < best[2]) best = [x, y, d]
        }
      }
      far = !best || best[2] > 48
      if (far && canCompact && !compact && card.current) {
        setGeo({ lines, left: -9999, top: 0, w: rr.width, h: rr.height, measured: true, compact: cid })
        return
      }
      spot = best || tries.filter(([x, y]) => fits(x, y)).sort((a, b) => cover(...a) - cover(...b))[0] || tries[0]
    }
    const left = Math.max(st.left + 8, Math.min(spot[0], st.right - 8 - cw))
    const top = Math.max(st.top + 8, Math.min(spot[1], floor - ch))
    setGeo({ lines, left: left - rr.left, top: top - rr.top, w: rr.width, h: rr.height, measured: !!card.current, compact: compact ? cid : null })
  }, [cid, el, folded, geo && geo.measured, geo && geo.compact])
  const math = claim.math && claim.math.text
  const where = [claim.source, unquote(claim.locator)].filter(Boolean).join(', ')
  // With the strip folded, the card carries the sentence (each operand's, for a worked-out number).
  const folds = folded && claim.status !== 'missing'
    ? (claim.math && claim.math.operands ? claim.math.operands.map(o => o.line).filter(Boolean) : claim.line ? [claim.line] : []) : []
  return h('div', { className: 'ip-cv-trace-layer' },
    !reduced && geo && geo.lines.length ? h('svg', { className: 'ip-cv-paths', width: geo.w, height: geo.h, viewBox: `0 0 ${geo.w} ${geo.h}`, 'aria-hidden': 'true' },
      geo.lines.map(l => h('g', { key: l.key, 'data-pts': JSON.stringify(l.pts.map(q => q.map(v => Math.round(v)))) },
        h('path', { className: 'ip-cv-path', d: l.d, pathLength: '1' }),
        h('circle', { className: 'ip-cv-dot', cx: l.a[0].toFixed(1), cy: l.a[1].toFixed(1), r: '3.5' }),
        h('circle', { className: 'ip-cv-dot is-end', cx: l.b[0].toFixed(1), cy: l.b[1].toFixed(1), r: '3.5' })))) : null,
    geo && geo.compact === cid ? h('div', { ref: card, className: 'ip-cv-card is-compact', role: 'tooltip', 'data-tone': toneOf(claim),
      style: geo.left > -9000 ? { left: `${geo.left}px`, top: `${geo.top}px` } : { left: 0, top: 0, visibility: 'hidden' } },
    h('p', { className: 'ip-cv-card-head' }, h(Codicon, { name: toneOf(claim) === 'good' ? 'pass' : toneOf(claim) === 'warn' ? 'info' : 'error', size: '14px' }),
      math ? h('span', { className: 'ip-cv-card-math', 'aria-label': `${statusWords(claim)}: ${math}` }, math) : statusWords(claim)),
    where ? h('p', { className: 'ip-cv-card-src' }, h('span', { className: 'ip-cv-ev-n', 'aria-hidden': 'true' }, String(claim.source_n || (used[claim.ref] && used[claim.ref].source_n) || '')), where) : null) :
    h('div', { ref: card, className: 'ip-cv-card', role: 'tooltip', 'data-tone': toneOf(claim),
      style: geo && geo.left > -9000 ? { left: `${geo.left}px`, top: `${geo.top}px` } : { left: 0, top: 0, visibility: 'hidden' } },
    h('p', { className: 'ip-cv-card-head' }, h(Codicon, { name: toneOf(claim) === 'good' ? 'pass' : toneOf(claim) === 'warn' ? 'info' : 'error', size: '14px' }), statusWords(claim)),
    math ? h('p', { className: 'ip-cv-card-math' }, math) : null,
    claim.status === 'missing'
      ? h('p', { className: 'ip-cv-card-line' }, claim.line && claim.line.before ? `Closest: ${claim.line.before}${claim.line.match || ''}${claim.line.after || ''}` : 'No sentence in your sources is close to it.')
      : null,
    folds.map((ln, i) => h('p', { key: `l${i}`, className: 'ip-cv-card-line' }, ln.before, ln.match ? h('mark', null, ln.match) : null, ln.after)),
    where && claim.status !== 'missing' ? h('p', { className: 'ip-cv-card-src' }, h('span', { className: 'ip-cv-ev-n', 'aria-hidden': 'true' }, String(claim.source_n || (used[claim.ref] && used[claim.ref].source_n) || '')), where) : null))
}

/* ------------------------------------------------------------------ graphic options (S17) -- */

// Three graphics from one pinned answer, set in the brand side by side. Each value traces to its sentence. The pane
// mounts this beside the canvas (docs/CANVAS-SEAM.md); it calls graphics/options itself. The values were checked on
// the server; this only finds each value's sentence to show it.
function lineFor(text, value) {
  const t = String(text || '').replace(/\s+/g, ' ')
  const i = t.indexOf(value)
  if (i < 0) return { before: firstSentence(t), match: '', after: '' }
  const starts = [0, ...[...t.matchAll(/(?<=[.!?”])\s+/g)].map(m => m.index + m[0].length)]
  const a = Math.max(...starts.filter(x => x <= i))
  const nxt = starts.filter(x => x > i)
  const b = nxt.length ? nxt[0] : t.length
  return { before: t.slice(a, i), match: value, after: t.slice(i + value.length, b).trimEnd() }
}

function traceable(o, oi, passages) {
  const claims = {}
  if (!o.tree) return { tree: null, claims }
  const tree = JSON.parse(JSON.stringify(o.tree))
  const items = ((o.spec && o.spec.items) || []).filter(it => it && it.value && it.ref)
  items.forEach((it, k) => {
    const cid = `c${oi * 50 + k + 1}`
    const p = passages[it.ref]
    let hit = false
    const visit = n => {
      if (!n || typeof n !== 'object' || hit) return
      if (n.t === 'span' && typeof n.x === 'string' && n.x.trim() === String(it.value).trim()) { n.tr = cid; hit = true; return }
      ;(n.k || []).forEach(visit)
    }
    visit(tree)
    if (hit) claims[cid] = { kind: 'count', value: it.value, status: 'exact', ref: it.ref, source_n: null, label: it.label,
      source: p ? p.source_title : '', locator: p ? unquote(p.locator) : '', line: p ? lineFor(p.text, it.value) : null }
  })
  return { tree, claims }
}

// Each option's values, grouped by the source sentence they came from (a sentence once, with all its values marked).
function sentencesOf(claims, also) {
  const out = []
  for (const c of Object.values(claims || {})) {
    if (!c.line || !c.line.match) continue
    const text = `${c.line.before}${c.line.match}${c.line.after}`.replace(/\s+/g, ' ').trim()
    let row = out.find(r => r.text === text)
    if (!row) out.push(row = { text, where: [c.source, c.locator].filter(Boolean).join(', '), values: [] })
    if (!row.values.includes(c.value)) row.values.push(c.value)
  }
  // the option's other values that sit in the same sentence are marked too
  for (const row of out) for (const v of also || []) if (v && row.text.includes(String(v)) && !row.values.includes(v)) row.values.push(v)
  return out
}

function markValues(text, values) {
  const esc = values.filter(Boolean).map(v => String(v).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).sort((a, b) => b.length - a.length)
  if (!esc.length) return text
  return text.split(new RegExp(`(${esc.join('|')})`)).map((part, i) => (i % 2 ? h('mark', { key: i }, part) : part))
}

export function GraphicOptions({ st, note, kitId, api }) {
  const [pick, setPick] = useState(0)
  const [hot, setHot] = useState(null) // {oi, cid}
  const [passages, setPassages] = useState({})
  const [saved, setSaved] = useState({}) // option index -> its graphic's output id
  const [busy, setBusy] = useState(null)
  const g = useJob(api)
  const kit = (st.kits || []).find(k => k.id === kitId) || (st.kits || [])[0] || {}
  const sources = (note && note.source_ids) || (st.sources || []).filter(s => s.included !== false).map(s => s.id)
  useEffect(() => {
    if (!note) return
    g.start({ kind: 'graphics', label: 'Three graphics from your answer' }, ROUTES.graphics(), { source_ids: sources, note_id: note.id, kit_id: kit.id })
  }, [note && note.id, kit.id])
  const j = g.job
  const r = j && j.status === 'done' ? j.result || {} : null
  const opts = r && Array.isArray(r.options) ? r.options : []
  useEffect(() => {
    const refs = [...new Set(opts.flatMap(o => o.refs || ((o.spec && o.spec.items) || []).map(it => it.ref)).filter(x => typeof x === 'string' && /^P\d+$/.test(x)))]
    refs.filter(ref => !passages[ref]).forEach(ref => api.rest(`passages/${ref}`).then(p => setPassages(x => ({ ...x, [ref]: p })), () => {}))
  }, [r])
  const drawn = useMemo(() => opts.map((o, oi) => traceable(o, oi, passages)), [r, passages])
  const FORM = { bars: 'Bars', figures: 'Big numbers', compare: 'Side by side', timeline: 'Timeline' }
  const deck = ((st.outputs || []).filter(o => o.kind === 'deck' && o.status !== 'failed')[0]) || null
  const save = async (oi, format) => {
    setBusy(`${oi}:${format}`)
    const download = captureGatewayFileDownload()
    try {
      let id = saved[oi]
      if (!id) { id = (await api.post(ROUTES.graphicKeep(), { job_id: j.id, choice: oi, kit_id: kit.id })).output_id; setSaved(x => ({ ...x, [oi]: id })) }
      const rr = await api.post(ROUTES.export(id), { kit_id: kit.id, format })
      await download(rr.path, rr.name)
    } catch (e) { api.toast(api.errText(e), 'bad') }
    setBusy(null)
  }
  const addToDeck = async oi => {
    setBusy(`${oi}:deck`)
    try {
      const v = await api.post(ROUTES.addGraphic(deck.id), { job_id: j.id, choice: oi })
      const last = (v && v.versions || []).find(x => x.active)
      api.toast(last && last.reason ? `${last.reason}, in ${deck.title}.` : `Added to ${deck.title}.`)
    } catch (e) { api.toast(api.errText(e), 'bad') }
    setBusy(null)
  }
  const noteAll = String((note && note.text) || '').replace(/\s*\[\d+\]/g, '').replace(/\s+/g, ' ').trim()
  const noteText = noteAll.length <= 280 ? noteAll : noteAll.split(SENT).reduce((acc, x) => (acc.length + x.length < 280 ? `${acc} ${x}`.trim() : acc), '') || `${noteAll.slice(0, 277)}...`
  return h('div', { className: 'ip-cv ip-go', role: 'region', 'aria-label': 'Make a graphic' },
    h('style', null, CSS),
    h('div', { className: 'ip-cv-headbox' }, h('header', { className: 'ip-cv-head' },
      h(Button, { variant: 'secondary', className: 'ip-cv-back', onClick: () => api.close() }, h(Codicon, { name: 'arrow-left', size: '14px' }), 'Back to the notebook'),
      h('div', { className: 'ip-cv-title' }, h('strong', null, 'Make a graphic'), h('span', null, `From your pinned answer, in ${kit.name || 'your brand'}`)),
      h('div', { className: 'ip-cv-grow' }))),
    h('main', { className: 'ip-go-body' },
      noteText ? h('p', { key: 'note', className: 'ip-go-note' }, noteText) : null,
      !j || j.status === 'running' ? h('div', { key: 'wait', className: 'ip-go-wait' }, j ? h(Steps, { job: j, onStop: g.stop }) : null)
        : j.status !== 'done' ? h('div', { key: 'err', className: 'ip-cv-card-s', role: 'alert' }, h('p', null, j.status === 'stopped' ? 'Stopped.' : j.error), h('div', { className: 'ip-cv-row' }, h(Button, { onClick: g.retry }, 'Retry')))
          : h('div', { key: 'grid', className: 'ip-go-grid' }, opts.map((o, oi) => {
            const d = drawn[oi] || {}
            const lit = hot && hot.oi === oi ? d.claims[hot.cid] : null
            const ctx = { live: true, claims: d.claims || {}, active: lit ? hot.cid : null, enter: c => setHot({ oi, cid: c }), leave: () => setHot(null),
              focus: c => setHot({ oi, cid: c }), blur: () => setHot(null), pin: c => setHot({ oi, cid: c }) }
            return h('figure', { key: oi, className: cls('ip-go-opt', pick === oi && 'is-on'), onClick: () => setPick(oi) },
              d.tree ? h('div', { className: 'ip-go-art' }, h(Art, { scene: d.tree, width: 300, ctx }))
                : h(Sketch, { sl: { heading: o.spec && o.spec.headline, bars: ((o.spec && o.spec.items) || []).map(it => ({ label: it.label, value: it.value })) } }),
              !lit && !Object.keys(d.claims || {}).length ? null : h('div', { className: 'ip-go-trace', 'aria-live': 'polite' }, lit
                ? [h('p', { key: 's', className: 'ip-cv-card-src' }, h(Codicon, { name: 'pass', size: '14px' }), [lit.source, lit.locator].filter(Boolean).join(', ')),
                  lit.line ? h('p', { key: 'l', className: 'ip-cv-card-line' }, lit.line.before, lit.line.match ? h('mark', null, lit.line.match) : null, lit.line.after) : null]
                : sentencesOf(d.claims).length ? sentencesOf(d.claims, ((o.spec && o.spec.items) || []).map(it => it && it.value)).slice(0, 3).map((row, i) => h('div', { key: `s${i}`, className: 'ip-go-src' },
                  h('p', { className: 'ip-cv-card-src' }, h(Codicon, { name: 'pass', size: '14px' }), row.where),
                  h('p', { className: 'ip-cv-card-line' }, markValues(row.text, row.values))))
                : h('p', { className: 'ip-go-hint' }, [...new Set(Object.values(d.claims || {}).map(c => [c.source, c.locator].filter(Boolean).join(', ')).filter(Boolean))].join('; '))),
              h('figcaption', null, h('strong', null, FORM[o.form] || o.form),
                o.check && o.check.label ? h('span', { className: 'ip-cv-chk is-good' }, h(Codicon, { name: 'pass', size: '14px' }), o.check.label) : null,
                pick === oi ? h('span', { className: 'ip-go-picked' }, 'Picked') : h(Button, { variant: 'secondary', onClick: e => { e.stopPropagation(); setPick(oi) } }, 'Use this')),
              pick === oi ? h('div', { className: 'ip-cv-row ip-go-acts', onClick: e => e.stopPropagation() },
                h(Button, { loading: busy === `${oi}:png`, onClick: () => save(oi, 'png') }, 'Save as PNG'),
                h(Button, { variant: 'secondary', loading: busy === `${oi}:svg`, onClick: () => save(oi, 'svg') }, 'Save as SVG'),
                deck && o.form !== 'timeline' ? h(Button, { variant: 'secondary', loading: busy === `${oi}:deck`, onClick: () => addToDeck(oi) }, 'Add to the deck') : null) : null)
          })),
      r ? h('p', { key: 'by', className: 'ip-cv-by' }, r.by || 'Written by your Hermes model') : null))
}

/* ------------------------------------------------------------------ styles -- */
// Host tokens (the kit's --hk-* over the app's theme), 2px corners, no text under 12px, no dimmed body text.

const CSS = `
.ip-cv{position:relative;min-height:0;height:100%;display:grid;grid-template-columns:200px minmax(0,1fr) 0px;grid-template-rows:auto minmax(0,1fr);
  transition:grid-template-columns 180ms cubic-bezier(.2,.7,.2,1);background:var(--hk-bg);color:var(--hk-ink);font-size:13px;--cv-r:var(--radius-md,2px);
  --cv-tint:color-mix(in srgb,var(--hk-accent) 18%,transparent);--cv-line:color-mix(in srgb,currentColor 42%,transparent);overflow:hidden}
:root[data-theme=dark] .ip-cv,.dark .ip-cv{--cv-tint:color-mix(in srgb,var(--hk-accent) 24%,transparent)}
.ip-cv.is-folded{grid-template-columns:40px minmax(0,1fr) 0px}
.ip-cv.is-revising{grid-template-columns:40px minmax(0,1fr) 260px}
.ip-cv *{box-sizing:border-box}
.ip-cv p,.ip-cv h2,.ip-cv h3{margin:0}
.ip-cv-head{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--hk-stroke);min-width:0}
.ip-cv-title{display:flex;flex-direction:column;min-width:120px;flex:0 1 auto;max-width:300px}
.ip-cv-title strong{font-size:14px;font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.ip-cv-title span{font-size:12px;line-height:1.35}
.ip-cv-grow{flex:1;min-width:8px}
.ip-cv-headbox{grid-column:1/-1;container-type:inline-size;min-width:0}
@container (max-width:820px){.ip-cv-head{gap:8px;padding:10px 12px}.ip-cv-back .codicon,.ip-cv-rev-btn>.codicon{display:none}.ip-cv-more{margin-left:0;padding-left:8px}}
.ip-cv-stamp{display:inline-flex;align-items:center;gap:6px;flex:none;white-space:nowrap;font-size:12px;font-weight:600;line-height:1.3;padding:4px 9px;border-radius:var(--cv-r)}
.ip-cv-stamp span{overflow-wrap:anywhere}
.ip-cv-stamp .codicon{flex:none}
.ip-cv-stamp[data-tone=good]{color:var(--hk-good);background:color-mix(in srgb,var(--hk-good-fill) 12%,transparent)}
.ip-cv-stamp[data-tone=bad]{color:var(--hk-bad);background:color-mix(in srgb,var(--hk-bad-fill) 12%,transparent)}
.ip-cv-pop{position:relative;flex:none}
.ip-cv-more{margin-left:6px;padding-left:10px;border-left:1px solid var(--hk-stroke)}
.ip-cv-chip{display:inline-flex;flex:none;align-items:center;gap:8px;height:28px;padding:0 10px;border:1px solid var(--hk-stroke);border-radius:var(--cv-r);
  background:var(--hk-surface);color:var(--hk-ink);font:inherit;font-size:12px;cursor:pointer;max-width:200px}
.ip-cv-chip:hover{background:var(--hk-hover)}
.ip-cv :focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.ip-cv-chip-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ip-cv-sw{width:12px;height:12px;border-radius:1px;flex:none;box-shadow:0 0 0 1px color-mix(in srgb,var(--hk-ink) 22%,transparent)}
.ip-cv-menu{position:absolute;top:calc(100% + 4px);left:0;z-index:30;min-width:220px;max-height:360px;overflow:auto;padding:4px;background:var(--hk-surface);
  border:1px solid var(--hk-stroke);border-radius:var(--cv-r);box-shadow:0 12px 32px -8px rgba(0,0,0,.32)}
.ip-cv-menu.is-right{left:auto;right:0}
.ip-cv-menu-h{font-size:12px;font-weight:600;padding:8px 8px 4px}
.ip-cv-menu-item{display:flex;align-items:center;gap:8px;width:100%;padding:6px 8px;border:0;border-radius:var(--cv-r);background:transparent;color:var(--hk-ink);
  font:inherit;font-size:13px;text-align:left;cursor:pointer;white-space:nowrap}
.ip-cv-menu-item:hover{background:var(--hk-hover)}
.ip-cv-menu-item .codicon:last-child:not(:first-child){margin-left:auto}
.ip-cv-menu-item.is-danger{color:var(--hk-bad)}
.ip-cv-confirm{display:grid;gap:8px;padding:8px;width:240px}
.ip-cv-confirm p{font-size:13px;line-height:1.45}
.ip-cv-off{opacity:.55;cursor:default}
.ip-cv-why{position:absolute;top:calc(100% + 6px);right:0;z-index:31;width:240px;padding:8px 10px;font-size:12px;line-height:1.4;background:var(--hk-surface);color:var(--hk-ink);
  border:1px solid var(--hk-stroke);border-radius:var(--cv-r);box-shadow:0 8px 20px rgba(0,0,0,.22);opacity:0;pointer-events:none;transition:opacity 120ms ease-out;white-space:normal;font-weight:400}
.ip-cv-export:hover .ip-cv-why,.ip-cv-export:focus-within .ip-cv-why{opacity:1}
.ip-cv-icon{display:grid;place-items:center;width:28px;height:28px;border:0;border-radius:var(--cv-r);background:transparent;color:var(--hk-ink);cursor:pointer}
.ip-cv-icon:hover{background:var(--hk-hover)}
.ip-cv-icon.is-boxed{border:1px solid var(--hk-stroke);background:var(--hk-surface)}

.ip-cv-strip{grid-row:2;grid-column:1;position:relative;display:grid;grid-template-rows:auto minmax(0,1fr);border-right:1px solid var(--hk-stroke);min-height:0;width:200px}
.ip-cv-strip.is-rail{width:40px;display:block;z-index:20}
.ip-cv-strip-h{font-size:13px;font-weight:600;padding:14px 14px 8px}
.ip-cv-strip-list{overflow:auto;overscroll-behavior:contain;padding:0 8px 16px;scrollbar-width:thin;display:grid;align-content:start;gap:12px}
.ip-cv-strip-none{font-size:13px;line-height:1.45;padding:0 6px}
.ip-cv-peek{position:absolute;left:40px;top:0;bottom:0;width:240px;display:grid;grid-template-rows:auto minmax(0,1fr);background:var(--hk-bg);
  border-right:1px solid var(--hk-stroke);box-shadow:12px 0 28px -16px rgba(0,0,0,.35)}
.ip-cv-rail-btn{display:flex;flex-direction:column;align-items:center;gap:10px;width:100%;padding:14px 0;border:0;background:transparent;color:var(--hk-ink);font:inherit;cursor:pointer}
.ip-cv-rail-btn:hover{background:var(--hk-hover)}
.ip-cv-rail-label{writing-mode:vertical-rl;font-size:12px;font-weight:600;letter-spacing:.02em}
.ip-cv-rail-n{display:grid;place-items:center;min-width:20px;height:20px;padding:0 5px;border-radius:10px;font-size:12px;font-weight:600;background:var(--hk-sunken)}
.ip-cv-rail-n.is-bad{color:var(--hk-bad);background:color-mix(in srgb,var(--hk-bad-fill) 14%,transparent)}
.ip-cv-ev{display:grid;gap:4px;padding:6px;border-radius:var(--cv-r)}
.ip-cv-ev.is-picked{background:var(--hk-active)}
.ip-cv-ev-src{display:flex;gap:6px;align-items:flex-start;font-size:12px;font-weight:600;line-height:1.35}
.ip-cv-ev-n{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 4px;border-radius:var(--cv-r);font-size:12px;font-weight:600;
  font-variant-numeric:tabular-nums;background:var(--hk-sunken);color:var(--hk-ink);flex:none}
.ip-cv-ev-s{display:block;width:100%;padding:4px 6px;margin:0;border:0;border-radius:var(--cv-r);background:transparent;color:var(--hk-ink);font:inherit;
  font-size:13px;line-height:1.5;text-align:left;cursor:pointer}
.ip-cv-ev-s:hover{background:var(--hk-hover)}
.ip-cv-n{padding:0 1px;border-bottom:1px solid transparent;transition:background-color 120ms ease-out,border-color 120ms ease-out}
.ip-cv-n.is-lit{background:var(--cv-tint);border-bottom-color:var(--hk-accent)}

.ip-cv-stage{grid-row:2;grid-column:2;position:relative;min-width:0;min-height:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;
  gap:14px;padding:32px 20px 12px;overflow:hidden}
.ip-cv.is-revising .ip-cv-stage{padding-left:12px;padding-right:12px}
.ip-cv-slot{position:relative;flex:none}
.ip-cv-preview-tag{position:absolute;bottom:calc(100% + 8px);left:0;font-size:12px;font-weight:600}
.ip-cv-slide{position:relative;flex:none;outline:1px solid color-mix(in srgb,var(--hk-ink) 12%,transparent);box-shadow:0 1px 2px rgba(0,0,0,.08),0 18px 40px -22px rgba(0,0,0,.5)}
.ip-cv-slide.is-selected{outline:2px solid var(--hk-accent);outline-offset:2px}
.ip-cv-slide.is-preview{outline:2px dashed var(--hk-accent);outline-offset:2px}
.ip-cv-fit{position:relative;overflow:hidden}
.ip-cv-art{transform-origin:0 0}
.ip-cv-art .ip-scene{box-shadow:none}
.ip-cv-as-hr{height:1px;background:currentColor;opacity:.3}
.ip-cv-claim{width:fit-content;text-decoration-line:underline;text-decoration-style:dotted;text-decoration-thickness:1px;text-decoration-color:var(--cv-line);
  text-underline-offset:.14em;cursor:pointer;outline:none;transition:background-color 120ms ease-out}
.ip-cv-claim.is-missing{text-decoration-style:wavy;text-decoration-color:var(--hk-bad-fill)}
.ip-cv-claim.is-kept{text-decoration-style:dashed}
.ip-cv-claim.is-lit,.ip-cv-claim:focus-visible{text-decoration-style:solid;text-decoration-color:var(--hk-accent);
  background:linear-gradient(transparent 48%,var(--cv-tint) 48%,var(--cv-tint) 80%,transparent 80%)}
.ip-cv-claim.is-missing.is-lit{text-decoration-color:var(--hk-bad-fill)}
.ip-cv-hot{cursor:pointer;transition:box-shadow 120ms ease-out}
.ip-cv-hot.is-lit{box-shadow:0 0 0 1px var(--hk-accent),0 0 0 4px var(--cv-tint)}
.ip-cv-claim.is-rev{text-decoration-style:solid;text-decoration-color:var(--hk-accent);background:linear-gradient(transparent 48%,var(--cv-tint) 48%,var(--cv-tint) 80%,transparent 80%)}
.ip-cv-hot.is-rev{box-shadow:0 0 0 1px var(--hk-accent),0 0 0 4px var(--cv-tint)}
.ip-cv-cue{position:absolute;top:6px;left:50%;transform:translateX(-50%);display:inline-flex;align-items:center;gap:8px;padding:3px 10px;font-size:12px;font-weight:500;
  line-height:18px;white-space:nowrap;border-radius:var(--cv-r);background:var(--hk-sunken);color:var(--hk-ink);animation:ip-cv-fade 240ms linear}
.ip-cv-cue-dot{width:7px;height:7px;border-radius:4px;background:var(--hk-accent);box-shadow:0 0 0 3px var(--cv-tint)}
.ip-cv-nums{flex:1 1 auto;min-height:0;width:100%;display:grid;grid-template-rows:auto minmax(0,1fr);gap:6px;padding-top:6px}
.ip-cv-nums-h{font-size:12px;font-weight:600}
.ip-cv-nums-list{min-height:0;overflow:auto;scrollbar-width:thin;display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:2px 10px;align-content:start}
.ip-cv-num{display:grid;grid-template-columns:auto auto minmax(0,1fr);align-items:center;gap:8px;min-height:28px;padding:4px 8px;border:0;border-radius:var(--cv-r);
  background:transparent;color:var(--hk-ink);font:inherit;font-size:13px;text-align:left;cursor:pointer;transition:background-color 120ms ease-out}
.ip-cv-num:hover,.ip-cv-num.is-lit{background:var(--cv-tint)}
.ip-cv-num-v{font-weight:600;font-variant-numeric:tabular-nums;white-space:nowrap}
.ip-cv-num-s{font-size:12px;line-height:1.35;overflow-wrap:anywhere}
.ip-cv-num[data-tone=good] .codicon{color:var(--hk-good)}
.ip-cv-num[data-tone=bad] .codicon,.ip-cv-num[data-tone=bad] .ip-cv-num-s{color:var(--hk-bad)}
.ip-cv-rev-btn .ip-cv-rail-n{margin-left:2px;height:18px;min-width:18px}
.ip-cv-rev-btn.is-on{background:var(--hk-active)}
.ip-cv-sel-el{outline:2px solid var(--hk-accent);outline-offset:4px}
[data-el]{cursor:default}

.ip-cv-filmwrap{position:relative;flex:none;display:flex;align-items:center;width:100%;justify-content:center}
.ip-cv-film{display:flex;gap:8px;max-width:100%;overflow-x:auto;overflow-y:hidden;padding:3px 3px 2px;scrollbar-width:none}
.ip-cv-film::-webkit-scrollbar{display:none}
.ip-cv-filmwrap.clip-r .ip-cv-film{-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 56px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 56px),transparent)}
.ip-cv-filmwrap.clip-l .ip-cv-film{-webkit-mask-image:linear-gradient(90deg,transparent,#000 56px);mask-image:linear-gradient(90deg,transparent,#000 56px)}
.ip-cv-filmwrap.clip-l.clip-r .ip-cv-film{-webkit-mask-image:linear-gradient(90deg,transparent,#000 56px,#000 calc(100% - 56px),transparent);mask-image:linear-gradient(90deg,transparent,#000 56px,#000 calc(100% - 56px),transparent)}
.ip-cv-arrow{position:absolute;top:calc(50% - 10px);z-index:3;display:grid;place-items:center;width:28px;height:28px;border:1px solid var(--hk-stroke);border-radius:14px;
  background:var(--hk-surface);color:var(--hk-ink);cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.18)}
.ip-cv-arrow.is-l{left:0}.ip-cv-arrow.is-r{right:0}
.ip-cv-arrow:hover{background:var(--hk-hover)}
.ip-cv-thumb{position:relative;flex:none;display:grid;justify-items:center;gap:3px;padding:0;border:0;background:none;color:var(--hk-ink);cursor:pointer;transition:opacity 180ms ease-out}
.ip-cv-thumb-img{display:block;pointer-events:none;outline:1px solid color-mix(in srgb,var(--hk-ink) 16%,transparent);border-radius:1px}
.ip-cv-thumb:hover .ip-cv-thumb-img{outline-color:color-mix(in srgb,var(--hk-ink) 40%,transparent)}
.ip-cv-thumb.is-current .ip-cv-thumb-img{outline:2px solid var(--hk-ink);outline-offset:1px}
.ip-cv-thumb.is-hit .ip-cv-thumb-img{outline:2px solid var(--hk-accent);outline-offset:1px}
.ip-cv-thumb.is-dim{opacity:.4}
.ip-cv-thumb-n{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;line-height:16px;font-variant-numeric:tabular-nums}
.ip-cv-thumb.is-current .ip-cv-thumb-n{color:var(--hk-accent)}
.ip-cv-thumb-flag{width:6px;height:6px;border-radius:3px;background:var(--hk-bad-fill)}

.ip-cv-bar{position:absolute;z-index:12;display:flex;align-items:center;gap:2px;padding:3px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--cv-r);
  box-shadow:0 10px 26px -8px rgba(0,0,0,.35);white-space:nowrap;animation:ip-cv-rise 140ms cubic-bezier(.2,.7,.2,1)}
@keyframes ip-cv-rise{from{opacity:0;transform:translateY(4px)}}
.ip-cv-bar-sep{width:1px;height:18px;margin:0 3px;background:var(--hk-stroke)}
.ip-cv-bar-btn{position:relative;height:30px;padding:0 10px;border:0;border-radius:var(--cv-r);background:transparent;color:var(--hk-ink);font:inherit;font-size:13px;
  font-weight:500;cursor:pointer}
.ip-cv-bar-btn:hover{background:var(--hk-hover)}
.ip-cv-bar-btn.is-off{opacity:.5;cursor:default}
.ip-cv-bar-btn .ip-cv-why{right:auto;left:0}
.ip-cv-bar-btn:hover .ip-cv-why,.ip-cv-bar-btn:focus .ip-cv-why{opacity:1}

.ip-cv-revise{grid-row:2;grid-column:3;min-height:0;min-width:0;border-left:1px solid var(--hk-stroke);overflow-y:auto;overflow-x:hidden;display:grid;align-content:start;gap:14px;padding:12px 14px 20px;width:260px;
  scrollbar-width:thin}
.ip-cv-revise.is-rail{width:48px;padding:0;overflow:hidden}
.ip-cv-rev-head{display:flex;align-items:center;gap:8px}
.ip-cv-rev-head h2{font-size:15px;font-weight:600}
.ip-cv-rev-where{font-size:12px;font-weight:600;margin-right:auto;padding:2px 6px;border-radius:var(--cv-r);background:var(--hk-sunken)}
.ip-cv-hint{font-size:13px;line-height:1.45}
.ip-cv-lab{font-size:13px;font-weight:600}
.ip-cv-lab-s{font-size:12px;font-weight:600}
.ip-cv-card-s{display:grid;gap:10px;padding:12px;border:1px solid var(--hk-stroke);border-radius:var(--cv-r);background:var(--hk-surface)}
.ip-cv-card-s[data-tone=bad]{border-color:color-mix(in srgb,var(--hk-bad-fill) 50%,var(--hk-stroke))}
.ip-cv-card-s textarea,.ip-cv-compose textarea{width:100%;resize:vertical;padding:8px;font:inherit;font-size:13px;line-height:1.45;color:var(--hk-ink);background:var(--hk-bg);
  border:1px solid var(--hk-stroke);border-radius:var(--cv-r)}
.ip-cv-card-s textarea:focus,.ip-cv-compose textarea:focus{outline:2px solid var(--hk-accent);outline-offset:-1px}
.ip-cv-steps{display:grid;gap:6px}
.ip-cv-step{display:flex;align-items:center;gap:8px;font-size:13px;line-height:1.35}
.ip-cv-step.is-done .codicon{color:var(--hk-good)}
.ip-cv-secs{margin-left:auto;font-size:12px;font-variant-numeric:tabular-nums}
.ip-cv-spin{flex:none;width:12px;height:12px;border-radius:50%;border:2px solid color-mix(in srgb,currentColor 30%,transparent);border-top-color:currentColor;animation:ip-cv-spin .8s linear infinite}
@keyframes ip-cv-spin{to{transform:rotate(360deg)}}
.ip-cv-now{display:grid;gap:4px;padding-bottom:10px;border-bottom:1px solid var(--hk-stroke)}
.ip-cv-now-t{font-size:13px;line-height:1.45}
.ip-cv-opt{display:grid;gap:8px;justify-items:start;padding:10px;margin:0 -4px;border:1px solid transparent;border-radius:var(--cv-r);cursor:pointer}
.ip-cv-opt:hover{background:var(--hk-hover)}
.ip-cv-opt.is-on{border-color:var(--hk-accent);background:color-mix(in srgb,var(--hk-accent) 6%,transparent)}
.ip-cv-opt-t{font-size:14px;font-weight:600;line-height:1.35}
.ip-cv-mini{outline:1px solid color-mix(in srgb,var(--hk-ink) 14%,transparent)}
.ip-cv-chk{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600}
.ip-cv-chk.is-good{color:var(--hk-good)}
.ip-cv-chk.is-bad{color:var(--hk-bad)}
.ip-cv-foot{display:flex;align-items:center;justify-content:space-between;gap:8px}
.ip-cv-by{font-size:12px}
.ip-cv-link{border:0;background:none;padding:2px 0;color:var(--hk-ink);font:inherit;font-size:13px;text-decoration:underline;text-underline-offset:.2em;cursor:pointer}
.ip-cv-diff{font-size:14px;line-height:1.5;white-space:pre-wrap}
.ip-cv-diff .is-del{text-decoration:line-through;text-decoration-color:var(--hk-bad-fill);background:color-mix(in srgb,var(--hk-bad-fill) 12%,transparent)}
.ip-cv-diff .is-add{font-weight:600;background:color-mix(in srgb,var(--hk-good-fill) 16%,transparent)}
.ip-cv-row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.ip-cv-flags{display:grid;gap:10px}
.ip-cv-flag{display:grid;gap:8px;padding:12px;border:1px solid color-mix(in srgb,var(--hk-bad-fill) 35%,var(--hk-stroke));border-left:3px solid var(--hk-bad-fill);border-radius:var(--cv-r);
  background:color-mix(in srgb,var(--hk-bad-fill) 5%,var(--hk-surface))}
.ip-cv-flag.is-fixed{border-left-color:var(--hk-good-fill);border-color:color-mix(in srgb,var(--hk-good-fill) 35%,var(--hk-stroke));background:var(--hk-surface)}
.ip-cv-flag p{font-size:13px;line-height:1.45}
.ip-cv-flag .ip-cv-flag-h{display:flex;align-items:center;gap:6px;font-weight:600;color:var(--hk-bad)}
.ip-cv-compose{display:grid;gap:6px;justify-items:start;padding-top:12px;border-top:1px solid var(--hk-stroke)}
.ip-cv-sketch{display:grid;gap:6px;width:100%}
.ip-cv-sk-row{display:grid;grid-template-columns:80px 1fr auto;gap:6px;align-items:center;font-size:12px}
.ip-cv-sk-l{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ip-cv-sk-bar{height:10px;background:var(--hk-accent);border-radius:1px}
.ip-cv-sk-v{font-weight:600;font-variant-numeric:tabular-nums}

.ip-cv-trace-layer{position:absolute;inset:0;pointer-events:none;z-index:15}
.ip-cv-paths{position:absolute;left:0;top:0;overflow:visible}
.ip-cv-path{fill:none;stroke:var(--hk-accent);stroke-width:2px;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:1;
  animation:ip-cv-draw 160ms cubic-bezier(.2,.7,.2,1) forwards}
.ip-cv-dot{fill:var(--hk-accent);stroke:var(--hk-bg);stroke-width:2px}
.ip-cv-dot.is-end{opacity:0;animation:ip-cv-fade 50ms linear 130ms forwards}
@keyframes ip-cv-draw{to{stroke-dashoffset:0}}
@keyframes ip-cv-fade{to{opacity:1}}
.ip-cv-card{position:absolute;width:272px;display:grid;gap:6px;padding:10px 12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--cv-r);
  box-shadow:0 14px 34px -12px rgba(0,0,0,.42);font-size:13px;line-height:1.45;animation:ip-cv-fade 100ms linear;opacity:1}
.ip-cv-card-head{display:flex;align-items:center;gap:6px;font-weight:600}
.ip-cv-card[data-tone=good] .ip-cv-card-head .codicon{color:var(--hk-good)}
.ip-cv-card[data-tone=bad] .ip-cv-card-head{color:var(--hk-bad)}
.ip-cv-card[data-tone=warn] .ip-cv-card-head .codicon{color:var(--hk-warn,var(--hk-ink))}
.ip-cv-card-line mark{background:var(--cv-tint);color:inherit;padding:0 1px;border-bottom:1px solid var(--hk-accent)}
.ip-cv-card-math{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.ip-cv-card-src{display:flex;gap:6px;align-items:center;font-size:12px;font-weight:600}
.ip-cv-card.is-compact{width:max-content;max-width:440px;display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;padding:6px 10px}
.ip-cv-card.is-compact .ip-cv-card-math{font-size:14px}
.ip-cv.is-still .ip-cv-paths{display:none}

.ip-go{grid-template-columns:minmax(0,1fr)}
.ip-go-body{grid-row:2;overflow:auto;padding:24px;display:grid;align-content:start;gap:18px}
.ip-go-note{font-size:13px;line-height:1.5;max-width:70ch;padding-left:10px;border-left:2px solid var(--hk-stroke)}
.ip-go-wait{max-width:360px}
.ip-go-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:20px;align-items:start}
.ip-go-opt{margin:0;display:grid;gap:10px;padding:10px;border:1px solid var(--hk-stroke);border-radius:var(--cv-r);background:var(--hk-surface);cursor:pointer}
.ip-go-opt.is-on{border-color:var(--hk-accent);box-shadow:0 0 0 1px var(--hk-accent)}
.ip-go-opt figcaption{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ip-go-picked{margin-left:auto;font-size:12px;font-weight:600;color:var(--hk-accent)}
.ip-go-art{justify-self:center}
.ip-go-trace{min-height:64px;display:grid;align-content:start;gap:4px;padding:8px 10px;border-radius:var(--cv-r);background:var(--hk-sunken)}
.ip-go-trace .codicon{color:var(--hk-good)}
.ip-go-hint{font-size:12px;line-height:1.45}
.ip-go-src{display:grid;gap:4px}
.ip-go-src+.ip-go-src{padding-top:8px;border-top:1px solid var(--hk-stroke)}
.ip-go-trace .ip-cv-card-line{font-size:13px;line-height:1.45}
.ip-go-acts{padding-top:10px;border-top:1px solid var(--hk-stroke)}
@media (prefers-reduced-motion:reduce){.ip-cv,.ip-cv-thumb,.ip-cv-n,.ip-cv-bar,.ip-cv-card,.ip-cv-cue,.ip-cv-num{transition:none;animation:none}.ip-cv-paths{display:none}.ip-cv-spin{animation-duration:2s}}
`
