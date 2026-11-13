// Letterpress, desktop half. SOURCE: desktop/plugin.js is built from this file and the shared interface code in
// vendor/hermes-ui-kit by `node vendor/hermes-ui-kit/scripts/build.mjs .` (esbuild, pinned in that folder). Edit here, then build.
//
// The built file is one ES module that imports only '@hermes/plugin-sdk', 'react' and 'react/jsx-runtime'.
// No JSX, no innerHTML: proofs arrive as plain nodes ({t, c, x, k}) from the backend and are walked into
// React elements from a fixed list of tags, with text only as text.
//
// Three tabs on one page:
//  - Notebook: three panes. Sources (tick what counts, a short summary of each, open one at a cited passage),
//    Chat (answers only from the ticked sources, every claim numbered back to its passage, pin an answer as a
//    note), and Studio (choose a kit, make a deck, a graphic, an audio brief or a one-pager, watch each step,
//    open it large with its checks, export it).
//  - Kits: every kit, the kit bench (roles by measured contrast, type, deck style, voice, rules, logo, fonts),
//    Import a kit, Build from a website, and Help me build a kit.
//  - Storage: everything stored, sizes, delete, Forget everything, the token meter and daily limit.
// Plugin chrome uses only the app's theme variables. A kit's colors and fonts appear only inside proofs,
// swatches and specimens; they never restyle the plugin.

import { Component, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { Button, Codicon, Input, SegmentedControl, Textarea, atom, captureGatewayFileDownload, host, useValue } from '@hermes/plugin-sdk'
import { registerPage } from 'hermes-ui-kit'
import { Canvas, usesCanvas } from './canvas.js'
import { DesignsRoom } from './designs.js'
import * as canvasLane from './canvas.js' // GraphicOptions, when the canvas lane ships it
import { createFirstPaint } from './firstpaint.js'
import { OFFLINE_HELP, POLL_GAVE_UP, isUnreachable, plainError, pollClock } from './errors.js'

const PLUGIN_ID = 'letterpress'
const ROUTE = '/letterpress'
const REST_TIMEOUT = 25000

let api = null
const $state = atom(null)
const $loadError = atom(null)
const $tab = atom('notebook')
const $output = atom(null) // the output open in the viewer {id, proofs, ...}
const $job = atom(null) // the latest make job, for the status bar
const $designJob = atom(null) // the running designs job {…job, oid}
const $designsOn = atom(false) // the Designs room is open over the viewed output
const DESIGN_KINDS = ['deck', 'onepager', 'visual']
const $toast = atom(null)
const $stale = atom(false) // true while any part of the first screen is the stored copy (firstpaint.js): no input until it is real
let fp = null // the first-paint store, made in register()

/* ------------------------------------------------------------------ helpers -- */

const h = (t, p, ...k) => {
  const kids = k.flat().filter(x => x !== null && x !== undefined && x !== false)
  return kids.length > 1 ? jsxs(t, { ...(p || {}), children: kids }) : jsx(t, { ...(p || {}), children: kids[0] })
}
const cls = (...xs) => xs.filter(Boolean).join(' ')
// What a person reads for an error: the backend's own sentence, or one plain line when the backend isn't answering
// (never the browser's "Failed to fetch"). Always ends with a full stop, so callers can add " Try again.".
const errText = e => plainError(e)
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
function bytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
// A toast reports the last action only: it goes after 4 seconds, or as soon as the person starts the next step
// (a click or a key), so a "Kept." or "Undone." is never left over on the next screen.
function toast(text, tone) {
  const at = Date.now()
  $toast.set({ text, tone: tone || 'info', at })
  setTimeout(() => { const t = $toast.get(); if (t && t.at === at) $toast.set(null) }, tone === 'bad' ? 6000 : 4000)
}
if (typeof window !== 'undefined') {
  const stale = () => { const t = $toast.get(); if (t && Date.now() - t.at > 600) $toast.set(null) }
  window.addEventListener('pointerdown', stale, true)
  window.addEventListener('keydown', stale, true)
}

// The toast sits bottom right, but never over the canvas's numbers row: when the two would meet it rises above it.
function Toast({ t }) {
  const el = useRef(null)
  const [bottom, setBottom] = useState(18)
  useLayoutEffect(() => {
    const me = el.current
    const nums = typeof document !== 'undefined' && document.querySelector('.ip-cv-nums')
    if (!me || !nums) { setBottom(18); return }
    const a = me.getBoundingClientRect(), b = nums.getBoundingClientRect()
    const meets = b.width && b.left < a.right && b.right > a.left && b.top < innerHeight - 18 && b.bottom > innerHeight - 18 - a.height
    setBottom(meets ? Math.max(18, innerHeight - b.top + 12) : 18)
  }, [t.at])
  return h('div', { ref: el, className: 'imp-toast', 'data-tone': t.tone, role: 'status', style: { bottom: `${bottom}px` } }, t.text)
}

function rest(path, options) {
  if (!api) return Promise.reject(new Error('Letterpress is not connected.'))
  return api.rest(path, { timeoutMs: REST_TIMEOUT, ...(options || {}) })
}
const post = (path, body) => rest(path, { method: 'POST', body: body || {} })
const del = path => rest(path, { method: 'DELETE' })

function applyKit(st) {
  const prefs = st.prefs || {}
  if (prefs.kit && st.kits.some(k => k.id === prefs.kit)) $kit.set(prefs.kit)
  else if (!st.kits.some(k => k.id === $kit.get()) && st.kits.length) $kit.set(st.kits[0].id)
}
// Before the first draw: the last good notebook from plugin storage, if there is one (firstpaint.js). Shown as it was;
// load() replaces each part as the real answer lands, and the page takes no input until then.
let hydrated = false
function hydrate() {
  if (hydrated) return
  hydrated = true
  if ($state.get() || !fp) return
  const rec = fp.hydrate()
  if (!rec) return
  $state.set(rec.state)
  applyKit(rec.state)
  if ('chats' in rec && $chats.get() === null) $chats.set(rec.chats)
  if ('guide' in rec && $guide.get() === undefined) $guide.set(rec.guide)
}
// The three first answers go out together: chats and the guide do not wait on state.
let loading = null
let loaded = false
function load() {
  if (!loading) loading = loadNow().finally(() => { loading = null })
  return loading
}
async function loadNow() {
  if ($chats.get() === null || (fp && fp.isStale('chats'))) ensureChats()
  if ($guide.get() === undefined || (fp && fp.isStale('guide'))) ensureGuide()
  try {
    const st = await rest('state')
    $state.set(st)
    $loadError.set(null)
    loaded = true
    applyKit(st)
    if (fp) fp.fresh('state')
    for (const j of st.jobs || []) { if (j.kind === 'make') trackMake(j); if (j.kind === 'designs' && j.status === 'running' && !$designJob.get()) trackDesigns(j, (j.params || {}).output_id) }
    watchSummaries(st)
  } catch (e) {
    $loadError.set(e)
  }
}
async function refresh() {
  try { $state.set(await rest('state')); if (fp) fp.schedule() } catch (e) { /* keep what is on screen */ }
}

/* Jobs: start returns at once; poll until done. A pushed event only makes the next poll sooner. */
const pollers = new Map()
let poke = () => {}
function pollJob(job, onDone, onFail, onStep) {
  let stopped = false
  let last = job
  const clock = pollClock()
  const tick = async () => {
    if (stopped) return
    let next
    try {
      const j = await rest(`jobs/${job.id}`)
      last = j
      if (j.status === 'done') { stopped = true; pollers.delete(job.id); onDone && onDone(j); return }
      if (j.status === 'failed' || j.status === 'stopped') { stopped = true; pollers.delete(job.id); onFail && onFail(j); return }
      onStep && onStep(j)
      next = clock.ok()
    } catch (e) {
      // A missed check is retried, backing off; after about a minute and a half of misses the screen stops waiting
      // and says why, instead of spinning forever. The job itself may still finish in the backend.
      next = clock.miss()
      if (next.giveUp) {
        stopped = true
        pollers.delete(job.id)
        onFail && onFail({ ...(last || job), status: 'failed', lost: true, error: POLL_GAVE_UP })
        return
      }
    }
    pollers.set(job.id, setTimeout(tick, next.delay))
  }
  pollers.set(job.id, setTimeout(tick, clock.first))
  poke = () => { for (const [id, t] of pollers) { clearTimeout(t); pollers.set(id, setTimeout(tick, 50)) } }
  return () => { stopped = true; clearTimeout(pollers.get(job.id)); pollers.delete(job.id) }
}

async function openOutput(id) {
  try {
    const out = await rest(`outputs/${id}`)
    $output.set(out)
    loadFonts(out.proofs)
  } catch (e) {
    $output.set(null)
  }
}

/* Kit fonts in the preview: the backend's own TrueType bytes, loaded as FontFace, so the preview uses the
   same faces the PDF embeds. A font that fails to load falls back to its stack and the proof still renders. */
const loadedFonts = new Set()
async function loadFonts(proofs) {
  if (typeof FontFace === 'undefined' || typeof document === 'undefined' || !document.fonts) return
  const keys = new Set()
  for (const p of proofs || []) for (const k of p.fonts || []) keys.add(k)
  for (const key of keys) {
    if (loadedFonts.has(key)) continue
    loadedFonts.add(key)
    try {
      const f = await rest(`fonts/${key}`)
      const bin = atob(f.data)
      const buf = new Uint8Array(bin.length)
      for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
      const face = new FontFace(`imp-${key}`, buf.buffer, { weight: String(f.weight || 400), style: f.style || 'normal' })
      await face.load()
      document.fonts.add(face)
    } catch (e) {
      loadedFonts.delete(key)
    }
  }
}

/* ------------------------------------------------------------------ files -- */

function pickFile(accept, onFile) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = accept
  input.onchange = () => { const f = input.files && input.files[0]; if (f) onFile(f) }
  input.click()
}
async function upload(path, file) {
  const buf = await file.arrayBuffer()
  try {
    return await rest(path, { method: 'POST', upload: { filename: file.name, contentType: file.type || 'application/octet-stream', bytes: buf }, timeoutMs: 120000 })
  } catch (e) {
    // Remote backends behind OAuth take no multipart uploads yet: send the bytes as base64 JSON instead.
    if (!/upload/i.test(errText(e))) throw e
    let bin = ''
    const view = new Uint8Array(buf)
    for (let i = 0; i < view.length; i += 0x8000) bin += String.fromCharCode.apply(null, view.subarray(i, i + 0x8000))
    return rest(path, { method: 'POST', body: { filename: file.name, data: btoa(bin) }, timeoutMs: 120000 })
  }
}

/* ------------------------------------------------------------------ page -- */

function LetterpressPage() {
  hydrate()
  const st = useValue($state)
  const loadError = useValue($loadError)
  const tab = useValue($tab)
  const t = useValue($toast)
  const stale = useValue($stale)
  const root = useRef(null)
  useEffect(() => { if (!loaded) load() }, [])
  // The stored copy is for looking only: no clicks, keys or focus reach it until the real answers have landed.
  useLayoutEffect(() => { if (root.current) root.current.inert = !!stale }, [stale, !!st])
  if (loadError && (!st || (fp && fp.isStale('state')))) {
    return h('div', { className: 'hk imp' }, h('div', { className: 'imp-center' },
      h('div', { className: 'imp-notice', 'data-tone': 'bad' },
        h('h2', { className: 'imp-h2' }, 'Letterpress could not start'),
        h('p', null, errText(loadError)),
        isUnreachable(loadError) ? h('p', null, OFFLINE_HELP) : null,
        h(Button, { onClick: () => { $loadError.set(null); load() } }, 'Try again'))))
  }
  if (!st) return h('div', { className: 'hk imp' }, h('div', { className: 'imp-center' }, h('p', { className: 'imp-wait' }, h('span', { className: 'imp-spin' }), 'Opening Letterpress')))
  return h('div', { className: 'hk imp', ref: root, 'aria-busy': stale ? 'true' : undefined },
    h('style', null, st.proof_css),
    h(CopyGuard, { stale },
      h(TopBar, { st, tab }),
      tab === 'kits' ? h(KitsTab, { st }) : tab === 'storage' ? h(StorageTab, { st }) : h(NotebookTab, { st })),
    t ? h(Toast, { t }) : null)
}

// A stored copy that fails to draw (an older shape, say) is dropped and the page waits as on a first open. Any other
// error is passed on as before.
class CopyGuard extends Component {
  constructor(props) { super(props); this.state = { error: null } }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch() {
    if (!this.props.stale || !fp) return
    fp.discard()
    $chats.set(null); $guide.set(undefined); $state.set(null)
    this.setState({ error: null })
  }
  render() {
    if (this.state.error && !this.props.stale) throw this.state.error
    return this.state.error ? null : this.props.children
  }
}

function TopBar({ st, tab }) {
  return h('header', { className: 'imp-top' },
    h(SegmentedControl, { options: [{ id: 'notebook', label: 'Notebook' }, { id: 'kits', label: 'Brands' }, { id: 'storage', label: 'Settings' }],
      value: tab, onChange: v => $tab.set(v) }),
    h('div', { className: 'imp-grow' }),
    tab === 'notebook' && isSample(st) ? h('span', { className: 'imp-top-sample' },
      h('span', { className: 'imp-tag' }, (st.sample && st.sample.label) || 'Sample'), (st.sample && st.sample.name) || 'Sample notebook',
      h(Button, { size: 'sm', variant: 'secondary', className: 'imp-quiet', onClick: closeSample }, 'Close the sample')) : null,
    // The manual on linchpin.studio, in the user's own browser (Nov 11: no plugin linked its manual).
    h(Button, { size: 'sm', variant: 'ghost', title: 'Open the manual in your browser', onClick: openManual }, 'Manual'))
}

const MANUAL_URL = 'https://linchpin.studio/hermes/letterpress/manual/'
function openManual() {
  try { if (api && api.os && typeof api.os.openExternal === 'function') api.os.openExternal(MANUAL_URL) } catch (e) { /* nothing to open with */ }
}

function Working({ step }) {
  return h('div', { className: 'imp-working', role: 'status' }, h('span', { className: 'imp-spin' }), step)
}

/* The audio brief: the recording from the person's own Hermes voice, or why there isn't one and a way to retry. */
function AudioPlayer({ out, proof, onChapter }) {
  const [src, setSrc] = useState(null)
  const [job, setJob] = useState(null)
  const [err, setErr] = useState('')
  const a = proof.audio || {}
  useEffect(() => {
    setSrc(null)
    if (a.status !== 'ready') return
    let live = true
    rest(`outputs/${out.id}/audio/${proof.kit_id}`, { timeoutMs: 60000 })
      .then(r => { if (live) setSrc(`data:${r.mime};base64,${r.data}`) }, e => { if (live) setErr(errText(e)) })
    return () => { live = false }
  }, [out.id, proof.kit_id, a.status, a.bytes])
  const record = async () => {
    setErr('')
    try {
      const r = await post(`outputs/${out.id}/speak`, { kit_id: proof.kit_id })
      setJob(r.job)
      pollJob(r.job, async () => { setJob(null); await openOutput(out.id) }, async j => { setJob(null); setErr(j.error); await openOutput(out.id) }, setJob)
    } catch (e) { setErr(errText(e)) }
  }
  if (job) return h(Working, { step: job.step || 'Recording' })
  if (a.status === 'ready') return h(PlayerBar, { proof, src, err, record, onChapter, label: `Audio brief in ${proof.kit.name}` })
  return h('div', { className: 'imp-player is-off', role: 'status' },
    h('span', { className: 'imp-play is-off', 'aria-hidden': 'true' }, h(Icon, { name: 'audio', size: 18 })),
    h('p', { className: 'imp-player-note' }, err || a.error || 'Not recorded yet. The script is ready to read or export.'),
    h(Button, { size: 'sm', variant: 'secondary', onClick: record }, a.status === 'failed' ? 'Record again' : 'Record it'))
}

// Chapter titles and start times: the backend's chapters when sent, else the script's own section heads.
function chaptersOf(proof) {
  const ch = proof.chapters || (proof.audio && proof.audio.chapters)
  if (ch && ch.length) return ch.map(c => ({ title: c.heading || c.title || '', start: c.start_s, dur: c.dur_s }))
  const out = []
  const text = n => (n && n.t !== 'sup' ? (n.x || '') + (n.k || []).map(text).join('') : '')
  const walk = n => {
    if (!n || typeof n !== 'object') return
    if (/(^|\s)ip-seg(\s|$)/.test(n.c || '')) {
      const head = (n.k || []).find(k => /^h[1-4]$/.test(k.t))
      out.push({ title: head ? text(head).replace(/^\s*\d+\s*/, '').trim() : `Part ${out.length + 1}` })
      return
    }
    for (const k of n.k || []) walk(k)
  }
  walk(proof.tree)
  return out
}
const clock = t => `${Math.floor((t || 0) / 60)}:${String(Math.floor((t || 0) % 60)).padStart(2, '0')}`

function PlayerBar({ proof, src, err, record, onChapter, label }) {
  const el = useRef(null)
  const [t, setT] = useState(0)
  const [dur, setDur] = useState(0)
  const [on, setOn] = useState(false)
  const chs = chaptersOf(proof)
  const at = dur ? chapterAt(proof, { currentTime: t, duration: dur }) : -1
  const toggle = () => { const a = el.current; if (!a) return; if (a.paused) a.play().catch(() => {}); else a.pause() }
  const seek = e => { const a = el.current; if (!a || !dur) return; const r = e.currentTarget.getBoundingClientRect(); a.currentTime = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur }
  const starts = chs.map((c, i) => c.start !== undefined ? c.start : (dur * i) / Math.max(1, chs.length))
  return h('div', { className: 'imp-player' },
    src ? h('audio', { ref: el, src, preload: 'metadata', 'aria-label': label,
      onLoadedMetadata: e => setDur(e.currentTarget.duration || 0), onPlay: () => setOn(true), onPause: () => setOn(false),
      onTimeUpdate: e => { setT(e.currentTarget.currentTime); onChapter && onChapter(chapterAt(proof, e.currentTarget)) }, onEnded: () => { setOn(false); onChapter && onChapter(-1) } }) : null,
    h('button', { type: 'button', className: 'imp-play', onClick: toggle, disabled: !src, 'aria-label': on ? 'Pause' : 'Play' },
      on ? h('span', { className: 'imp-pause', 'aria-hidden': 'true' }, h('span', null), h('span', null)) : h(Icon, { name: 'play', size: 16 })),
    h('div', { className: 'imp-player-mid' },
      h('p', { className: 'imp-player-title' }, !src ? 'Loading the recording' : at >= 0 && chs[at] ? `Chapter ${at + 1} of ${chs.length}: ${chs[at].title}` : `${plural(chs.length, 'chapter')}`),
      h('div', { className: 'imp-progress', onClick: seek, role: 'slider', 'aria-label': 'Position', 'aria-valuemin': 0, 'aria-valuemax': Math.round(dur), 'aria-valuenow': Math.round(t), tabIndex: 0,
        onKeyDown: e => { const a = el.current; if (!a) return; if (e.key === 'ArrowRight') a.currentTime = Math.min(dur, a.currentTime + 5); if (e.key === 'ArrowLeft') a.currentTime = Math.max(0, a.currentTime - 5) } },
        h('span', { className: 'imp-progress-fill', style: { width: `${dur ? (t / dur) * 100 : 0}%` } }),
        dur ? starts.slice(1).map((s, i) => h('span', { key: i, className: 'imp-progress-tick', style: { left: `${(s / dur) * 100}%` } })) : null)),
    h('span', { className: 'imp-secs' }, `${clock(t)} / ${clock(dur)}`),
    h(Button, { size: 'sm', variant: 'secondary', className: 'imp-quiet', onClick: record }, 'Record again'),
    err ? h('p', { className: 'imp-error' }, err) : null)
}

// Which chapter is playing: from the chapters' own start times when the backend sends them, else by share of time.
function chapterAt(proof, el) {
  const t = el.currentTime || 0
  const ch = proof.chapters || (proof.audio && proof.audio.chapters) || []
  if (ch.length && ch[0].start_s !== undefined) { let at = 0; ch.forEach((c, i) => { if (t >= c.start_s) at = i }); return at }
  const n = ch.length || 5
  return el.duration ? Math.min(n - 1, Math.floor((t / el.duration) * n)) : 0
}

/* Deleting is for good, so it takes two clicks: the first arms the button for a few seconds. */
function DeleteButton({ onDelete, label = 'Delete', size, className }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => { if (!armed) return; const t = setTimeout(() => setArmed(false), 4000); return () => clearTimeout(t) }, [armed])
  return h(Button, { size, variant: 'secondary', className, onClick: () => { if (armed) { setArmed(false); onDelete() } else setArmed(true) } },
    armed ? 'Click again to delete' : label)
}

function Failed({ job, onRetry }) {
  return h('div', { className: 'imp-failed', role: 'alert' },
    h('p', null, job.error || 'That did not work.'),
    job.error_code === 'coming' || job.error_code === 'no_sources' ? null : h(Button, { variant: 'secondary', size: 'sm', onClick: onRetry }, 'Retry'))
}

/* The proof: crop marks, the page, the kit's color bar, the colophon. Every number the checks traced is
   focusable; hovering or focusing it opens a trace card with the source line it came from. */
// A short draft fills its sheet the way the PDF does: the page's base size grows (to 1.4x at most) until the
// content reaches the foot of the letter-shaped sheet, and what space is left sits above the sources.
function useFillSheet(sheet, key, off) {
  useLayoutEffect(() => {
    const el = sheet.current
    if (off || !el) return
    const fit = () => {
      const page = el.querySelector(':scope > .ip-page')
      if (!page || !el.clientHeight) return
      const base = 13
      const fits = k => {
        page.style.setProperty('--ip-base', `${(base * k).toFixed(2)}px`)
        page.style.minHeight = '0px'
        const ok = page.scrollHeight <= el.clientHeight * 0.97
        page.style.minHeight = ''
        return ok
      }
      if (!fits(1)) { page.style.setProperty('--ip-base', `${base}px`); return }
      let lo = 1, hi = 1.4
      if (fits(hi)) lo = hi
      else for (let i = 0; i < 6; i++) { const mid = (lo + hi) / 2; if (fits(mid)) lo = mid; else hi = mid }
      page.style.setProperty('--ip-base', `${(base * lo).toFixed(2)}px`)
    }
    fit()
    if (typeof ResizeObserver === 'undefined') return
    let w = el.clientWidth
    const ro = new ResizeObserver(() => { if (el.clientWidth !== w) { w = el.clientWidth; fit() } })
    ro.observe(el)
    return () => ro.disconnect()
  }, [key, off])
}

function Proof({ proof, plain, playing }) {
  const fig = useRef(null)
  const sheet = useRef(null)
  const scene = proof.kind === 'deck' || proof.kind === 'visual'
  useFillSheet(sheet, proof.tree, scene)
  const plainTree = useMemo(() => plain && proof.kind === 'audio' ? chipPerSentence(proof.tree) : proof.tree, [proof.tree, plain, proof.kind])
  const timer = useRef(null)
  const openEl = useRef(null)
  const [trace, setTrace] = useState(null) // {i, top, left, caret, above}
  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(() => { setTrace(null) }, [proof.tree])
  const traces = proof.traces || []
  const place = (i, el) => {
    const f = fig.current
    if (!f || !el || !traces[i]) return
    openEl.current = el
    const fr = f.getBoundingClientRect()
    const r = el.getBoundingClientRect()
    const width = Math.min(262, fr.width - 16)
    const mid = r.left + r.width / 2 - fr.left
    const left = Math.max(8, Math.min(mid - width / 2, fr.width - width - 8))
    const above = r.bottom - fr.top + 170 > fr.height && r.top - fr.top > 170
    setTrace({ i, left, width, caret: Math.max(12, Math.min(mid - left, width - 12)),
      top: above ? null : r.bottom - fr.top + 8, bottom: above ? fr.bottom - r.top + 8 : null })
  }
  const ctx = {
    traces, plain: !!plain, playing: playing === undefined ? -1 : playing, segs: { i: 0 },
    open: trace ? trace.i : null,
    id: i => `imp-trace-${proof.kit_id || 'draft'}-${i}`,
    hover: (i, el) => { clearTimeout(timer.current); timer.current = setTimeout(() => place(i, el), 150) },
    focus: (i, el) => { clearTimeout(timer.current); place(i, el) },
    leave: () => { clearTimeout(timer.current); openEl.current = null; setTrace(null) },
  }
  // Focusing a number below the fold scrolls the page inside the sheet: keep the card on a focused number,
  // close it for a hovered one.
  const onScroll = () => {
    const el = openEl.current
    if (el && typeof document !== 'undefined' && document.activeElement === el) place(trace.i, el)
    else ctx.leave()
  }
  if (plain) {
    return h('figure', { className: 'imp-proof is-plain', ref: fig },
      h('div', { ref: sheet, className: cls('imp-sheet', scene && 'is-deck', proof.kind === 'visual' && 'is-visual', proof.kind === 'audio' && 'is-script'), onScroll: trace ? onScroll : undefined }, renderNode(plainTree, 'root', ctx)),
      trace && traces[trace.i] ? h(TraceCard, { t: traces[trace.i], id: ctx.id(trace.i), pos: trace }) : null)
  }
  return h('figure', { className: 'imp-proof', ref: fig },
    h('div', { className: 'imp-crop' },
      ['tl', 'tr', 'bl', 'br'].map(c => h('span', { key: c, className: `imp-mark imp-mark-${c}`, 'aria-hidden': 'true' })),
      h('div', { ref: sheet, className: cls('imp-sheet', scene && 'is-deck', proof.kind === 'visual' && 'is-visual'), onScroll: trace ? onScroll : undefined }, renderNode(proof.tree, 'root', ctx))),
    h(ColorBar, { bar: proof.bar }),
    h('figcaption', { className: 'imp-colophon' }, proof.colophon, proof.stale_voice ? ' The brand changed since the wording was set. Set it in the same brand again to redo the voice.' : ''),
    trace && traces[trace.i] ? h(TraceCard, { t: traces[trace.i], id: ctx.id(trace.i), pos: trace }) : null)
}

// A spoken script reads like a document: its source marks gather into one chip at the end of each sentence,
// never one after every number. Works line by line (a paragraph, a heading, a list item): a line's own marks never
// climb to the section around it (that drew a stray full-width "2" box between chapters). Returns a copy; the
// numbers keep their trace index (a.tr).
const SENT_END = /[.!?](?=["”’)]*(?:\s|$))/g
const INLINE = new Set(['span', 'sup', 'strong', 'em', 'small'])
function chipPerSentence(tree) {
  const isSup = n => n && n.t === 'sup'
  const refsOf = n => String(n.x || (n.k || []).map(k => (k && k.x) || '').join('')).split(/[^\d]+/).filter(Boolean)
  const chip = refs => ({ t: 'sup', c: 'ip-ref ip-ref-num', x: [...refs].join(', ') })
  const hasSup = n => !!n && (isSup(n) || (n.k || []).some(hasSup))
  const isLine = n => Array.isArray(n.k) && n.k.length && n.k.every(c => c && INLINE.has(c.t))
  // A class-less wrapper span only groups the line's pieces: walk into it with the same pending marks, so one
  // pass sees the whole line, and keep the wrapper (a heading lays its pieces out by them).
  const wrapper = c => c && c.t === 'span' && !c.c && !c.a && !c.x && Array.isArray(c.k) && c.k.length
  // Takes the last word off the end of a line built so far (a number, or the tail of a text run), so a chip can
  // keep it company; nothing when the line ends in a space or in anything else.
  const lastWord = out => {
    const l = out[out.length - 1]
    if (!l || l.t !== 'span' || typeof l.x !== 'string' || /\s$/.test(l.x) || (l.k || []).length) return []
    const at = l.x.search(/\S+$/)
    if (at <= 0) return [out.pop()]
    out[out.length - 1] = { ...l, x: l.x.slice(0, at) }
    return [{ ...l, x: l.x.slice(at) }]
  }
  const line = n => {
    let pending = new Set()
    const run = list => {
    const out = []
    for (const c of list) {
      if (wrapper(c)) { out.push({ ...c, k: run(c.k) }); continue }
      if (isSup(c)) { refsOf(c).forEach(r => pending.add(r)); continue }
      if (c.t === 'span' && (c.k || []).some(isSup)) {
        c.k.filter(isSup).forEach(s => refsOf(s).forEach(r => pending.add(r)))
        out.push({ ...c, k: c.k.filter(k => !isSup(k)) })
        continue
      }
      const text = c.t === 'span' && !c.c && !(c.k || []).length && typeof c.x === 'string' ? c.x : null
      if (text === null || !pending.size) { out.push(c); continue }
      let rest = text
      SENT_END.lastIndex = 0
      const m = SENT_END.exec(rest)
      if (!m) { out.push(c); continue }
      // The chip never starts a line: it stays on one line with the word before it and the stop after it.
      const head = rest.slice(0, m.index)
      const cutAt = head.search(/\S+$/)
      const word = cutAt >= 0 ? [{ ...c, x: head.slice(cutAt) }] : lastWord(out)
      if (cutAt > 0) out.push({ ...c, x: head.slice(0, cutAt) })
      out.push({ t: 'span', c: 'imp-nowrap', k: [...word, chip(pending), { ...c, x: m[0] }] }); pending = new Set()
      if (rest.slice(m.index + m[0].length)) out.push({ ...c, x: rest.slice(m.index + m[0].length) })
    }
    return out
    }
    const out = run(n.k)
    if (pending.size) out.push({ t: 'span', c: 'imp-nowrap', k: [...lastWord(out), chip(pending)] })
    return { ...n, k: out }
  }
  // A chapter heading never carries a source mark: its numbers are cited in the sentences below it.
  const noSup = n => !n || !Array.isArray(n.k) ? n : { ...n, k: n.k.filter(c => !isSup(c)).map(noSup) }
  const walk = n => {
    if (n && /^h[1-6]$/.test(n.t)) return saidQuote(noSup(n))
    if (!n || !Array.isArray(n.k) || !hasSup(n)) return saidQuote(n)
    if (isLine(n) && n.t !== 'span') return saidQuote(line(n))
    return { ...n, k: n.k.map(walk) }
  }
  return walk(tree)
}
// The script says "Quote. ... End quote." so the voice can mark it; the reading view sets it as a quotation instead.
// The spoken words stay in the audio. A whole quote inside one run of text becomes its own set line; a quote
// split over several runs only loses the spoken markers.
const QUOTE_WHOLE = /\bQuote[.,:]\s*["“]([^"”]+)["”]\s*End quote\.?\s*/
function saidQuote(n) {
  if (!n || !Array.isArray(n.k)) return n
  const k = []
  for (const c of n.k) {
    if (!c || c.t !== 'span' || c.c || (c.k || []).length || typeof c.x !== 'string' || !/quote/i.test(c.x)) { k.push(c && Array.isArray(c.k) ? saidQuote(c) : c); continue }
    let x = c.x
    const m = QUOTE_WHOLE.exec(x)
    if (m) {
      const before = x.slice(0, m.index), after = x.slice(m.index + m[0].length)
      if (before) k.push({ ...c, x: before })
      k.push({ t: 'span', c: 'imp-said', x: `\u201c${m[1].trim()}\u201d` })
      if (after) k.push({ ...c, x: after })
      continue
    }
    x = x.replace(/\bQuote[.,:]\s*(?=["“])/g, '').replace(/(["”])\s*End quote\.?/g, '$1')
    k.push({ ...c, x })
  }
  return { ...n, k }
}

const TRACE_HEADS = {
  exact: n => n ? `Exact match in source ${n}` : 'Exact match in your sources',
  computed: n => n ? `Worked out from source ${n}` : 'Worked out from your sources',
  close: n => n ? `Close match in source ${n}` : 'Close match in your sources',
  missing: () => 'Not found in your sources',
  kept: () => 'Kept on purpose, not in your sources',
  brief: () => 'From your own request',
}
// Any status the backend adds later still gets a plain head, never a thrown error.
const TRACE_HEAD = new Proxy(TRACE_HEADS, { get: (o, k) => o[k] || (() => 'Checked against your sources') })
const TRACE_TONE = { exact: 'good', close: 'good', computed: 'good', missing: 'bad', kept: 'warn', brief: 'good' }
// "1,148 - 936 = 212" with a real minus sign and times sign.
const mathText = m => String((m && (m.text || m.expr)) || m || '').replace(/(\d|\s)-(\s|\d)/g, '$1\u2212$2').replace(/(\d|\s)\*(\s|\d)/g, '$1\u00d7$2')

function TraceNum({ node, i, ctx, children }) {
  const t = ctx.traces[i]
  const on = ctx.open === i
  return h('span', {
    className: cls(node.c, `is-${t.status}`, on && 'is-open'), tabIndex: 0, role: 'button',
    'aria-label': `${t.value}: ${TRACE_HEAD[t.status](t.n)}`, 'aria-describedby': on ? ctx.id(i) : undefined,
    onMouseEnter: e => ctx.hover(i, e.currentTarget), onMouseLeave: ctx.leave,
    onFocus: e => ctx.focus(i, e.currentTarget), onBlur: ctx.leave,
    onKeyDown: e => { if (e.key === 'Escape' && on) { e.stopPropagation(); ctx.leave() } else if ((e.key === 'Enter' || e.key === ' ') && !on) { e.preventDefault(); ctx.focus(i, e.currentTarget) } },
  }, children)
}

function TraceCard({ t, id, pos }) {
  const line = t.line
  const where = [t.source, t.locator].filter(Boolean).join(', ')
  return h('div', { id, role: 'tooltip', className: cls('imp-trace', pos.top === null && 'is-above'), 'data-tone': TRACE_TONE[t.status],
    style: { left: `${pos.left}px`, width: `${pos.width}px`, top: pos.top === null ? 'auto' : `${pos.top}px`, bottom: pos.bottom === null ? 'auto' : `${pos.bottom}px`, '--caret': `${pos.caret}px` } },
    h('p', { className: 'imp-trace-head' }, h(Codicon, { name: t.status === 'missing' ? 'error' : t.status === 'kept' ? 'warning' : 'pass', size: '14px' }), TRACE_HEAD[t.status](t.n)),
    t.math ? h('p', { className: 'imp-trace-math' }, mathText(t.math)) : null,
    line ? h('p', { className: 'imp-trace-line' }, t.status === 'missing' || t.status === 'kept' ? h('span', { className: 'imp-trace-closest' }, 'Closest line: ') : null,
      line.before, line.match ? h('mark', null, line.match) : null, line.after) : null,
    where ? h('p', { className: 'imp-trace-src' }, t.n ? h('span', { className: 'imp-trace-n', 'aria-hidden': 'true' }, String(t.n)) : null, where) : null)
}

function ColorBar({ bar }) {
  return h('div', { className: 'imp-bar', 'aria-hidden': 'true' }, (bar || []).map((c, i) => h('span', { key: i, style: { background: c } })))
}

const TAGS = new Set(['div', 'section', 'header', 'footer', 'h1', 'h2', 'h3', 'p', 'span', 'sup', 'ul', 'ol', 'li', 'img', 'blockquote', 'strong', 'em', 'figure', 'figcaption', 'hr', 'small'])
// A date, year or day number is never a claim (contract F): in the plain viewer it is never underlined.
const MONTHS = /(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s*$/
const dateish = t => !t || /^(?:1[89]|20)\d\d$/.test(String(t.value).trim()) || (/^\d{1,2}$/.test(String(t.value).trim()) && MONTHS.test(String((t.line && t.line.before) || '')))
function renderNode(n, key, ctx) {
  if (!n || !TAGS.has(n.t)) return null
  // In the plain viewer a source mark is a small chip on the line, never a superscript.
  if (ctx && ctx.plain && n.t === 'sup') {
    const t = String(n.x || (n.k || []).map(k => k && k.x || '').join('')).replace(/[^\d,\s]/g, '').trim()
    return t ? jsx('span', { key, className: 'imp-cite is-static imp-linechip', children: t.replace(/\s*,\s*/g, ' ') }) : null
  }
  const props = { key, className: n.c || undefined }
  if (ctx && ctx.segs && /(^|\s)ip-seg(\s|$)/.test(n.c || '')) { const at = ctx.segs.i++; if (at === ctx.playing) props.className = `${n.c} imp-playing`; props['data-seg'] = at }
  const a = n.a || {}
  if (n.t === 'img') {
    if (typeof a.src !== 'string' || !a.src.startsWith('data:image/')) return null
    return jsx('img', { ...props, src: a.src, alt: '' })
  }
  if (a.style && typeof a.style === 'object') {
    const style = {}
    for (const [k, v] of Object.entries(a.style)) if (/^--[a-z0-9-]+$/.test(k)) style[k] = String(v)
    props.style = style
  }
  if (n.t === 'hr') return jsx('hr', props)
  const kids = []
  if (n.x) kids.push(n.x)
  ;(n.k || []).forEach((c, i) => { const el = renderNode(c, i, ctx); if (el) kids.push(el) })
  if (n.t === 'span' && ctx && ctx.plain && Number.isInteger(a.tr) && ctx.traces[a.tr] && dateish(ctx.traces[a.tr])) return kids.length > 1 ? jsxs('span', { key, children: kids }) : jsx('span', { key, children: kids[0] })
  if (n.t === 'span' && ctx && Number.isInteger(a.tr) && ctx.traces[a.tr]) return jsx(TraceNum, { key, node: n, i: a.tr, ctx, children: kids })
  return kids.length > 1 ? jsxs(n.t, { ...props, children: kids }) : jsx(n.t, { ...props, children: kids[0] })
}

function Checks({ proof, out, openCheck, setOpenCheck }) {
  return h('div', { className: 'imp-checks' },
    h('ul', { className: 'imp-pills' }, proof.checks.map(c => h('li', { key: c.id },
      h('button', { type: 'button', className: 'imp-pill', 'data-tone': c.tone, 'aria-expanded': openCheck === c.id,
        onClick: () => setOpenCheck(openCheck === c.id ? null : c.id) },
        h(Codicon, { name: c.tone === 'good' ? 'pass' : c.tone === 'bad' ? 'error' : 'warning', size: '14px' }), c.label)))),
    openCheck === 'sources' && proof.grounding.length ? h(Grounding, { proof, out }) : null,
    openCheck && openCheck !== 'sources' ? h(CheckDetail, { check: proof.checks.find(c => c.id === openCheck), proof, out }) : null)
}

function CheckDetail({ check, proof, out }) {
  const [busy, setBusy] = useState(false)
  if (!check || !check.items || !check.items.length) return null
  const act = check.action && out ? async () => {
    setBusy(true)
    try { $output.set(await post(`outputs/${out.id}/required`, { kit_id: proof.kit_id, on: check.action.do === 'require' })) } catch (e) { toast(errText(e), 'bad') }
    setBusy(false)
  } : null
  return h('div', { className: 'imp-detail-wrap' }, h('ul', { className: 'imp-detail' }, check.items.slice(0, 8).map((it, i) => h('li', { key: i },
    typeof it === 'string' ? it
      : it.what ? `${it.what}: ${it.ratio}:1 ${it.passes ? '(passes)' : '(below AA)'}`
        : it.word ? `"${it.word}" in ${it.path}`
          : it.say ? `"${it.not}" became "${it.say}"`
            : it.wanted ? (it.note || `${it.used} in place of ${it.wanted}`)
              : it.hex ? `${it.hex} at ${it.ratio}:1 is kept to ${it.label === 'fill' ? 'fills' : 'rules'}` : JSON.stringify(it)))),
    act ? h(Button, { size: 'sm', variant: 'secondary', loading: busy, onClick: act }, check.action.label) : null)
}

function Grounding({ proof, out }) {
  const [showFixed, setShowFixed] = useState(false)
  const act = proof.grounding.filter(i => i.status !== 'moved')
  const fixed = proof.grounding.filter(i => i.status === 'moved')
  return h('div', { className: 'imp-ground' },
    act.map(item => h(GroundItem, { key: item.key, item, out })),
    fixed.length ? h('div', { className: 'imp-gfixed' },
      h('button', { type: 'button', className: 'imp-gfixed-toggle', 'aria-expanded': showFixed, onClick: () => setShowFixed(!showFixed) },
        h(Codicon, { name: showFixed ? 'chevron-down' : 'chevron-right', size: '14px' }),
        `${fixed.length} citation${fixed.length === 1 ? '' : 's'} pointed to the right source`),
      showFixed ? h('ul', { className: 'imp-gfixed-list' }, fixed.map(item => h('li', { key: item.key },
        h('strong', null, item.kind === 'quote' ? `"${item.shown || item.value}"` : (item.shown || item.value)),
        item.line ? ` found in ${[item.line.source, item.line.locator].filter(Boolean).join(', ')}` : ' found in another passage'))) : null) : null)
}

// The backend sends a cut-off stretch of the text around a number; show it to the last whole word, with an ellipsis.
const wholeWords = t => { const x = String(t || ''); return /[.!?”"]$/.test(x.trim()) || x.length < 160 ? x : `${x.replace(/\s+\S*$/, '')}…` }
function GroundItem({ item, out }) {
  const [passage, setPassage] = useState(null)
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(item.context || '')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    const ref = (item.closest && item.closest.ref) || item.ref
    if (!item.line && ref) rest(`passages/${ref}`).then(setPassage, () => setPassage(null))
  }, [item.key])
  const act = async (path, body) => {
    setBusy(true)
    try {
      const v = await post(`outputs/${out.id}/${path}`, body)
      $output.set(v)
    } catch (e) { toast(errText(e), 'bad') }
    setBusy(false)
  }
  const editable = /^(title|dek|next|stat|quote|sections\.\d\.(heading|body)|points\.\d)$/.test(item.path)
  const editPath = item.path === 'stat' ? 'stat.label' : item.path === 'quote' ? 'quote.text' : /^points\.\d$/.test(item.path) ? `${item.path}.text` : item.path
  const shown = item.shown || item.value
  const line = item.line || (passage ? { source: passage.source_title, locator: passage.locator, text: passage.text } : null)
  return h('div', { className: 'imp-gitem', 'data-status': item.status },
    h('p', { className: 'imp-gwhat' }, item.status === 'kept' ? 'Kept on purpose' : 'Not found in sources',
      ': ', h('strong', null, item.kind === 'quote' ? `"${shown}"` : shown)),
    item.context && item.kind !== 'quote' ? h('p', { className: 'imp-gctx' }, wholeWords(item.context)) : null,
    line ? h('blockquote', { className: 'imp-passage' },
      h('p', { className: 'imp-passage-src' }, 'Closest line, ', [line.source, line.locator].filter(Boolean).join(', ')),
      h('p', null, line.text)) : h('p', { className: 'imp-gctx' }, 'No passage in your sources comes close.'),
    item.status === 'missing' ? (editing
      ? h('div', { className: 'imp-gedit' },
        h(Textarea, { value: text, rows: 3, onChange: e => setText(e.target.value), 'aria-label': 'New wording' }),
        h('div', { className: 'imp-row' },
          h(Button, { size: 'sm', loading: busy, onClick: () => act('edit', { path: editPath, text }) }, 'Save the fix'),
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => setEditing(false) }, 'Cancel')))
      : h('div', { className: 'imp-row' },
        editable ? h(Button, { size: 'sm', onClick: () => setEditing(true) }, 'Fix the wording') : null,
        h(Button, { size: 'sm', variant: 'secondary', loading: busy, onClick: () => act('decide', { key: item.key, action: 'remove' }) }, 'Remove it'),
        h(Button, { size: 'sm', variant: 'secondary', loading: busy, onClick: () => act('decide', { key: item.key, action: 'keep' }) }, 'Keep it, I checked'))) : null)
}

// Export waits while a number is flagged, the same as the canvas: the button stays in place, says why on hover or
// focus, and does nothing until the number is fixed, removed or kept on purpose.
// A year or a day of the month is never a claim (contract F), so it never holds Export.
const flaggedOf = proof => (proof && proof.traces || []).filter(t => t.status === 'missing' && !dateish(t))
const exportHeld = proof => flaggedOf(proof).length ? 'Fix or keep the numbers that aren’t in your sources first.'
  : proof && proof.blocked ? 'Something in it needs a look before it can go out.' : ''
function ExportMenu({ out, proof }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const off = exportHeld(proof)
  const go = async format => {
    setOpen(false)
    if (off) return
    setBusy(true)
    const save = captureGatewayFileDownload()
    try {
      const r = await post(`outputs/${out.id}/export`, { kit_id: proof.kit_id, format })
      await save(r.path, r.name)
    } catch (e) { toast(errText(e), 'bad') }
    setBusy(false)
  }
  return h('div', { className: cls('imp-export', off && 'is-held') },
    h(Button, { size: 'sm', loading: busy, 'aria-disabled': off ? 'true' : undefined, className: off ? 'imp-off' : '', 'aria-describedby': off ? 'imp-export-why' : undefined,
      onClick: () => { if (!off) setOpen(!open) }, 'aria-haspopup': 'menu', 'aria-expanded': open }, 'Export'),
    off ? h('span', { id: 'imp-export-why', role: 'tooltip', className: 'imp-why' }, off) : null,
    open && !off ? h('div', { className: 'imp-menu', role: 'menu' },
      Object.entries((out && out.formats) || { pdf: 'PDF', proof: 'Proof PDF with crop marks', html: 'HTML page' })
        .filter(([f]) => f !== 'audio' || (proof.audio && proof.audio.status === 'ready')).map(([f, l]) =>
        h('button', { key: f, type: 'button', role: 'menuitem', className: 'imp-menu-item', onClick: () => go(f) }, l))) : null)
}

/* ------------------------------------------------------------------ notebook -- */
// The main screen, in NotebookLM's shape: Sources on the left (tick what counts, a short summary of each, open one
// at a cited passage), Ask in the middle (the notebook guide written by the model: what the files say, what they
// ask for, the questions people may raise; then answers drawn only from the ticked sources, every claim numbered
// back to its passage), and the Studio on the right (real previews in the active brand, what the files asked for,
// what was made, as thumbnails that open the canvas). Making something runs in the middle column: a brief filled
// in from the ask, an outline to edit, then the build with its real steps and a Stop button.

const KINDS = [
  { id: 'deck', label: 'Deck', noun: 'deck', icon: 'deck', outline: true, length: 'About 8 slides' },
  { id: 'onepager', label: 'One-pager', noun: 'one-pager', icon: 'page', length: 'One page' },
  { id: 'visual', label: 'Graphic', noun: 'graphic', icon: 'chart', length: 'One graphic' },
  { id: 'audio', label: 'Audio brief', noun: 'audio brief', icon: 'audio', length: 'About 3 minutes' },
]
const KIND_OF = Object.fromEntries(KINDS.map(k => [k.id, k]))
KIND_OF.graphic = KIND_OF.visual

const $reader = atom(null) // {id, ref}: a source open in the left pane, at a passage
const $viewing = atom(null) // output id open in the viewer
const $kit = atom('counsel') // the Studio's brand
const $chats = atom(null)
const $makes = atom({}) // job id -> job, for makes running, stopped or failed
const $form = atom(null) // kept for the harness: openForm(kind) opens the brief for that kind
const $guide = atom(undefined) // undefined: not loaded; null: none yet; else the notebook guide
const $guideJob = atom(null)
const $flow = atom(null) // {kind, ask, seed, step: 'brief' | 'outline', job, outline, build}
const $asking = atom(null) // {question, job, source_ns}
const $rail = atom(false) // the narrow layout's sources overlay (and the canvas room's)
const $askDock = atom(false) // the canvas room's Ask overlay
const $reading = atom([]) // labels of files being read
const $graphicFor = atom(null) // a pinned note the canvas lane's GraphicOptions draws three graphics from

const included = st => ((st && st.sources) || []).filter(s => s.included)
const unitText = s => s.units ? plural(s.units, (s.unit_label || 'part').replace(/s$/, '')) : ''
const kitOf = (st, id) => (st.kits || []).find(k => k.id === id) || (st.kits || [])[0]
const isSample = st => !!(st && st.sample && st.sample.open)
const ago = t => {
  if (!t) return ''
  const s = Math.max(0, Date.now() / 1000 - t)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return new Date(t * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten']
const say = n => WORDS[n] || String(n)

/* Lucide-style glyphs, drawn from plain path data (no innerHTML): stroke only, 1.5. */
const ICONS = {
  doc: [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }], ['path', { d: 'M16 13H8' }], ['path', { d: 'M16 17H8' }], ['path', { d: 'M10 9H8' }]],
  note: [['path', { d: 'M16 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V8Z' }], ['path', { d: 'M15 3v4a2 2 0 0 0 2 2h4' }]],
  pdf: [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }], ['path', { d: 'M8 13h2a1.5 1.5 0 0 1 0 3H8v-5' }]],
  web: [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20' }], ['path', { d: 'M2 12h20' }]],
  talk: [['path', { d: 'M2 10v3' }], ['path', { d: 'M6 6v11' }], ['path', { d: 'M10 3v18' }], ['path', { d: 'M14 8v7' }], ['path', { d: 'M18 5v13' }], ['path', { d: 'M22 10v3' }]],
  deck: [['path', { d: 'M2 3h20' }], ['path', { d: 'M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3' }], ['path', { d: 'm7 21 5-5 5 5' }]],
  page: [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }]],
  chart: [['path', { d: 'M3 3v16a2 2 0 0 0 2 2h16' }], ['path', { d: 'M18 17V9' }], ['path', { d: 'M13 17V5' }], ['path', { d: 'M8 17v-3' }]],
  audio: [['path', { d: 'M2 10v3' }], ['path', { d: 'M6 6v11' }], ['path', { d: 'M10 3v18' }], ['path', { d: 'M14 8v7' }], ['path', { d: 'M18 5v13' }], ['path', { d: 'M22 10v3' }]],
  check: [['path', { d: 'M20 6 9 17l-5-5' }]],
  plus: [['path', { d: 'M5 12h14' }], ['path', { d: 'M12 5v14' }]],
  link: [['path', { d: 'M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71' }], ['path', { d: 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71' }]],
  paste: [['rect', { width: 8, height: 4, x: 8, y: 2, rx: 1 }], ['path', { d: 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2' }]],
  up: [['path', { d: 'm5 12 7-7 7 7' }], ['path', { d: 'M12 19V5' }]],
  down: [['path', { d: 'M12 5v14' }], ['path', { d: 'm19 12-7 7-7-7' }]],
  edit: [['path', { d: 'M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5z' }]],
  trash: [['path', { d: 'M3 6h18' }], ['path', { d: 'M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6' }], ['path', { d: 'M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2' }]],
  pin: [['path', { d: 'M12 17v5' }], ['path', { d: 'M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z' }]],
  copy: [['rect', { width: 14, height: 14, x: 8, y: 8, rx: 2 }], ['path', { d: 'M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2' }]],
  more: [['circle', { cx: 12, cy: 12, r: 1 }], ['circle', { cx: 19, cy: 12, r: 1 }], ['circle', { cx: 5, cy: 12, r: 1 }]],
  chevd: [['path', { d: 'm6 9 6 6 6-6' }]],
  chevr: [['path', { d: 'm9 18 6-6-6-6' }]],
  back: [['path', { d: 'm12 19-7-7 7-7' }], ['path', { d: 'M19 12H5' }]],
  x: [['path', { d: 'M18 6 6 18' }], ['path', { d: 'm6 6 12 12' }]],
  stop: [['rect', { width: 12, height: 12, x: 6, y: 6, rx: 1 }]],
  redo: [['path', { d: 'M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8' }], ['path', { d: 'M21 3v5h-5' }], ['path', { d: 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16' }], ['path', { d: 'M8 16H3v5' }]],
  send: [['path', { d: 'm5 12 7-7 7 7' }], ['path', { d: 'M12 19V5' }]],
  ask: [['path', { d: 'M7.9 20A9 9 0 1 0 4 16.1L2 22Z' }]],
  rail: [['rect', { width: 18, height: 18, x: 3, y: 3, rx: 2 }], ['path', { d: 'M9 3v18' }]],
  split: [['path', { d: 'M16 3h5v5' }], ['path', { d: 'M8 3H3v5' }], ['path', { d: 'M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3' }], ['path', { d: 'm15 9 6-6' }]],
  play: [['polygon', { points: '6 3 20 12 6 21 6 3' }]],
  // slide types
  stat: [['path', { d: 'M4 9h16' }], ['path', { d: 'M4 15h16' }], ['path', { d: 'M10 3 8 21' }], ['path', { d: 'M16 3l-2 18' }]],
  content: [['path', { d: 'M15 18H3' }], ['path', { d: 'M17 6H3' }], ['path', { d: 'M21 12H3' }]],
  exhibit: [['path', { d: 'M3 3v16a2 2 0 0 0 2 2h16' }], ['path', { d: 'M18 17V9' }], ['path', { d: 'M13 17V5' }], ['path', { d: 'M8 17v-3' }]],
  quote: [['path', { d: 'M16 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z' }], ['path', { d: 'M5 3a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2 1 1 0 0 1 1 1v1a2 2 0 0 1-2 2 1 1 0 0 0-1 1v2a1 1 0 0 0 1 1 6 6 0 0 0 6-6V5a2 2 0 0 0-2-2z' }]],
  comparison: [['rect', { width: 18, height: 18, x: 3, y: 3, rx: 2 }], ['path', { d: 'M12 3v18' }]],
  timeline: [['path', { d: 'M3 12h18' }], ['circle', { cx: 7, cy: 12, r: 2 }], ['circle', { cx: 17, cy: 12, r: 2 }]],
  section: [['path', { d: 'M4 7V4h16v3' }], ['path', { d: 'M9 20h6' }], ['path', { d: 'M12 4v16' }]],
  closing: [['path', { d: 'M4 22V4a1 1 0 0 1 .4-.8A6 6 0 0 1 8 2c3 0 5 2 7.33 2q2 0 3.67-.67a1 1 0 0 1 1 .8V15a1 1 0 0 1-.4.8A6 6 0 0 1 16 16c-3 0-5-2-8-2a6 6 0 0 0-4 1.528' }]],
}
ICONS.title = ICONS.section
function Icon({ name, size = 16, className }) {
  const parts = ICONS[name] || ICONS.page
  return jsx('svg', { viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round',
    'aria-hidden': 'true', focusable: 'false', className: cls('imp-ic', className), children: parts.map(([t, a], i) => jsx(t, { key: i, ...a })) })
}
const SLIDE_TYPE = { stat: 'One number', content: 'Points', exhibit: 'Chart', quote: 'Quote', comparison: 'Side by side', timeline: 'Timeline', section: 'Section', closing: 'Close', title: 'Title' }
function sourceGlyph(s) {
  const k = String((s && (s.kind || s.origin)) || '').toLowerCase()
  if (/pdf/.test(k)) return 'pdf'
  if (/web|url|http/.test(k)) return 'web'
  if (/transcript|vtt|srt|audio/.test(k)) return 'talk'
  if (/word|docx|doc\b/.test(k)) return 'doc'
  return 'note'
}

function adoptKit(kit, saidSaved) {
  $kit.set(kit.id)
  post('prefs', { kit: kit.id }).catch(() => {})
  toast(`${saidSaved || `Saved ${kit.name}`}. The Studio now uses it.`)
}
async function chooseKit(id) {
  $kit.set(id)
  try { await post('prefs', { kit: id }); await refresh() } catch (e) { /* the choice still holds in this window */ }
}

function openReader(chip) {
  if (chip && chip.source_id) { $reader.set({ id: chip.source_id, ref: chip.ref }); $rail.set(true) }
}
function openViewer(id) {
  $designsOn.set(false)
  $viewing.set(id)
  if (!$output.get() || $output.get().id !== id) openOutput(id)
}
function openFlow(kind, opts) {
  const o = opts || {}
  $viewing.set(null)
  $flow.set({ kind: KIND_OF[kind] ? KIND_OF[kind].id : 'deck', ask: o.ask || null, seed: o.seed || null, step: 'brief' })
}

async function loadChats() { try { $chats.set((await rest('chats')).chats) } catch (e) { $chats.set([]) } if (fp) fp.fresh('chats') }
async function loadGuide() {
  try { const r = await rest('notebook/guide'); $guide.set(r.guide || null) } catch (e) { $guide.set(null) }
  if (fp) fp.fresh('guide')
}
// The first load and the notebook's mount both ask; one request answers both.
let chatsReq = null
let guideReq = null
function ensureChats() { if (!chatsReq) chatsReq = loadChats().finally(() => { chatsReq = null }); return chatsReq }
function ensureGuide() { if (!guideReq) guideReq = loadGuide().finally(() => { guideReq = null }); return guideReq }
function writeGuide(ids) {
  $guideJob.set({ status: 'running', step: `Reading ${plural(ids.length, 'source')}`, steps: [{ text: `Reading ${plural(ids.length, 'source')}`, at: Date.now() / 1000 }], created_at: Date.now() / 1000 })
  post('notebook/guide', { source_ids: ids }).then(r => {
    $guideJob.set(r.job)
    pollJob(r.job, j => { $guideJob.set(null); $guide.set(j.result || null) }, j => $guideJob.set(j), j => $guideJob.set(j))
  }, e => $guideJob.set({ status: 'failed', error: errText(e) }))
}

async function openSample() {
  const st = await post('sample/open')
  $state.set(st)
  $flow.set(null); $viewing.set(null); $reader.set(null); $asking.set(null)
  $chats.set(null); $guide.set(undefined)
  if (st.prefs && st.prefs.kit) $kit.set(st.prefs.kit)
  await Promise.all([loadChats(), loadGuide()])
}
async function closeSample() {
  try {
    const st = await post('sample/close')
    $state.set(st)
    $flow.set(null); $viewing.set(null); $reader.set(null); $asking.set(null)
    $chats.set(null); $guide.set(undefined)
    await Promise.all([loadChats(), loadGuide()])
  } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
}

/* Summaries are written in the background after a source is read; watch any that are running. */
const watched = new Set()
function watchSummaries(st) {
  for (const j of (st && st.jobs) || []) {
    if (j.kind !== 'summarize' || watched.has(j.id)) continue
    watched.add(j.id)
    pollJob(j, () => refresh(), () => refresh())
  }
}

async function readFile(f) {
  const label = `Reading ${f.name}`
  $reading.set([...$reading.get(), label])
  const done = () => $reading.set($reading.get().filter(x => x !== label))
  try {
    const r = await upload('sources/file', f)
    pollJob(r.job, async j => {
      done()
      if (j.result && j.result.source && j.result.source.duplicate) toast('That file is already in your sources.')
      await refresh()
      watchSummaries($state.get())
    }, j => { done(); toast(j.error, 'bad') })
  } catch (e) { done(); toast(errText(e), 'bad') }
}
const addFiles = () => pickFile('.pdf,.docx,.txt,.md,.markdown,.vtt,.srt', readFile)

function trackMake(job) {
  $makes.set({ ...$makes.get(), [job.id]: job })
  $job.set(job)
  pollJob(job, async j => {
    const m = { ...$makes.get() }
    delete m[job.id]
    $makes.set(m)
    $job.set(null)
    const f = $flow.get()
    if (f && f.build && f.build.id === job.id) $flow.set(null)
    await refresh()
    const oid = j.result && j.result.output_id
    if (oid) {
      await openOutput(oid)
      const made = (($state.get() || {}).outputs || []).find(o => o.id === oid)
      // Make now also designs the piece three ways, and shows them side by side while they draw.
      if (made && DESIGN_KINDS.includes(made.kind)) { $designsOn.set(true); startDesigns(oid) } else $designsOn.set(false)
      $viewing.set(oid)
    }
  }, j => { $makes.set({ ...$makes.get(), [job.id]: j }); $job.set(null); syncFlowBuild(j) },
  j => { $makes.set({ ...$makes.get(), [job.id]: j }); $job.set(j); syncFlowBuild(j) })
}
async function startDesigns(oid) {
  try {
    const r = await post(`outputs/${oid}/designs`, {})
    trackDesigns(r.job, oid)
  } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
}
function trackDesigns(job, oid) {
  $designJob.set({ ...job, oid })
  pollJob(job, async () => { $designJob.set(null); await refresh() },
    j => { $designJob.set(null); toast(j.error || 'The designs did not finish. Press Design again.', 'bad') },
    j => $designJob.set({ ...j, oid }))
}
function openDesigns(id) {
  if (!$output.get() || $output.get().id !== id) openOutput(id)
  $designsOn.set(true)
  $viewing.set(id)
}
function syncFlowBuild(j) {
  const f = $flow.get()
  if (f && f.build && f.build.id === j.id) $flow.set({ ...f, build: j })
}
async function stopJob(job) {
  try {
    const j = await post(`jobs/${job.id}/stop`)
    if ($makes.get()[job.id]) $makes.set({ ...$makes.get(), [job.id]: { ...j, params: job.params } })
    syncFlowBuild({ ...j, params: job.params })
    for (const [id, t] of pollers) if (id === job.id) { clearTimeout(t); pollers.delete(id) }
    return j
  } catch (e) { toast(`${errText(e)} Try again.`, 'bad'); return null }
}
async function retryMake(job) {
  try {
    const r = await post(`jobs/${job.id}/retry`)
    const m = { ...$makes.get() }; delete m[job.id]; $makes.set(m)
    const next = { ...r, params: job.params || r.params }
    const f = $flow.get()
    if (f && f.build && f.build.id === job.id) $flow.set({ ...f, build: next })
    trackMake(next)
  } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
}

function NotebookTab({ st }) {
  const flow = useValue($flow)
  const rail = useValue($rail)
  const gf = useValue($graphicFor)
  useEffect(() => { if ($chats.get() === null) ensureChats(); if ($guide.get() === undefined) ensureGuide() }, [])
  const viewing = useValue($viewing)
  const out = useValue($output)
  const GraphicOptionsC = canvasLane.GraphicOptions
  if (gf && GraphicOptionsC) return h(GraphicOptionsC, { st, note: gf, kitId: $kit.get(), api: { rest, post, del, pollJob, openReader, openOutput, toast, errText, close: () => $graphicFor.set(null) } })
  const designsOn = useValue($designsOn)
  const dj = useValue($designJob)
  if (viewing && designsOn && out && out.id === viewing && DESIGN_KINDS.includes(out.kind)) {
    return h('div', { className: 'imp-nb is-viewing is-designs' },
      h(DesignsRoom, { key: out.id, out, st, job: dj && dj.oid === out.id ? dj : null, onDesign: () => startDesigns(out.id), onTemplate: () => $designsOn.set(false),
        api: { rest, post, pollJob, toast, errText, close: () => { $designsOn.set(false); $viewing.set(null) },
          save: async (path, name) => { const save = captureGatewayFileDownload(); await save(path, name) } } }))
  }
  if (viewing && usesCanvas(out, viewing)) return h(CanvasRoom, { st, out })
  const fresh = !(st.sources || []).length && !isSample(st)
  return h('div', { className: cls('imp-nb', viewing && 'is-viewing', rail && 'is-rail-open') },
    h(SourcesPane, { st }),
    flow ? h(FlowPane, { key: `${flow.kind}-${flow.ask ? flow.ask.id : 'own'}`, st, flow }) : fresh ? h(FirstOpen, { st }) : h(ChatPane, { st }),
    h(StudioPane, { st, fresh }),
    rail ? h('button', { type: 'button', className: 'imp-scrim', 'aria-label': 'Close sources', onClick: () => { $rail.set(false); $reader.set(null) } }) : null,
    viewing ? h(Viewer, { st, id: viewing }) : null)
}

/* The deck canvas keeps the notebook beside it: Sources and Ask fold to one 56px rail (the rail used at 1024),
   and each opens over the canvas as an overlay. Nothing about the canvas changes; it gets 56px less width. */
function CanvasRoom({ st, out }) {
  const rail = useValue($rail)
  const dock = useValue($askDock)
  const reader = useValue($reader)
  const shut = () => { $rail.set(false); $reader.set(null); $askDock.set(false) }
  useEffect(() => {
    if (!rail && !dock) return
    const onKey = e => { if (e.key === 'Escape') shut() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rail, dock])
  useLayoutEffect(() => { $rail.set(false); $reader.set(null); $askDock.set(false); return () => { $rail.set(false); $askDock.set(false) } }, [])
  const srcs = st.sources || []
  const openSources = id => { $askDock.set(false); $reader.set(id ? { id, ref: null } : null); $rail.set(id ? true : !rail || !!reader) }
  const openAsk = () => { $rail.set(false); $reader.set(null); $askDock.set(!dock) }
  return h('div', { className: cls('imp-room', (rail || dock) && 'is-open') },
    h('nav', { className: 'imp-room-rail', 'aria-label': 'Notebook' },
      h('button', { type: 'button', className: cls('imp-room-tab', rail && 'is-on'), 'aria-pressed': !!rail, onClick: () => openSources(null) },
        h(Icon, { name: 'rail', size: 18 }), h('span', null, 'Sources')),
      srcs.map((s, i) => h('button', { key: s.id, type: 'button', className: cls('imp-room-btn', s.included && 'is-in', rail && reader && reader.id === s.id && 'is-on'),
        title: `${i + 1}. ${s.title}${s.included ? '' : ' (not in use)'}`, 'aria-label': `Read ${s.title}`, onClick: () => openSources(s.id) },
      h(Icon, { name: sourceGlyph(s), size: 17 }), h('span', { className: 'imp-rail-n', 'aria-hidden': 'true' }, String(i + 1)))),
      h('span', { className: 'imp-room-sep', 'aria-hidden': 'true' }),
      h('button', { type: 'button', className: cls('imp-room-tab', dock && 'is-on'), 'aria-pressed': !!dock, onClick: openAsk },
        h(Icon, { name: 'ask', size: 18 }), h('span', null, 'Ask'))),
    h('div', { className: 'imp-room-stage' },
      h(Canvas, { st, out, api: { rest, post, del, pollJob, openReader, openOutput, openDesigns: () => openDesigns(out.id), toast, errText, close: () => { shut(); $viewing.set(null) } } })),
    rail || dock ? h('button', { type: 'button', className: 'imp-room-scrim', 'aria-label': rail ? 'Close sources' : 'Close Ask', onClick: shut }) : null,
    rail ? h('div', { className: 'imp-dock is-sources' }, h(SourcesPane, { st })) : null,
    dock && !rail ? h('div', { className: 'imp-dock is-ask' }, h(ChatPane, { st })) : null)
}

/* ---- First open: what Letterpress does, in one sentence, and the sample one click away ---- */

function FirstOpen({ st }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const sample = st.sample || {}
  const deck = (st.previews || {}).deck
  const pic = deck && typeof deck.img === 'string' && deck.img.startsWith('data:image/') ? deck : null
  const go = async () => {
    setBusy(true); setErr('')
    try { await openSample() } catch (e) { setErr(`The sample didn’t open: ${errText(e)} Try again.`) }
    setBusy(false)
  }
  return h('section', { className: 'imp-pane imp-ask imp-first', 'aria-label': 'Start' },
    h('div', { className: 'imp-first-inner' },
      h('h1', { className: 'imp-first-lead' }, 'Ask questions of your documents, then make a deck, one-pager, graphic or audio brief in your brand.'),
      pic ? h('figure', { className: 'imp-first-pic' },
        h('img', { src: pic.img, width: pic.w, height: pic.h, alt: `A slide from the sample deck in the ${pic.kit_name || 'sample'} brand`, draggable: false })) : null,
      h('div', { className: 'imp-first-acts' },
        h(Button, { onClick: go, loading: busy, disabled: busy || sample.available === false }, busy ? 'Opening the sample' : 'Open the sample'),
        h(Button, { variant: 'secondary', onClick: addFiles }, 'Start with your own files')),
      err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
      sample.name ? h('p', { className: 'imp-first-sample' }, h('span', { className: 'imp-tag' }, sample.label || 'Sample'), `${sample.name}, a made-up adult literacy group: a program report, board notes and a brand guide.`) : null))
}

/* ---- Sources ---- */

function SourcesPane({ st }) {
  const reader = useValue($reader)
  const reading = useValue($reading)
  const [adding, setAdding] = useState(null) // 'menu' | 'link' | 'paste'
  const [drag, setDrag] = useState(false)
  const srcs = st.sources || []
  const on = included(st)
  const sample = isSample(st)
  const setAll = async v => {
    try { const r = await post('sources/include', { ids: srcs.map(s => s.id), on: v }); $state.set({ ...$state.get(), sources: r.sources }) } catch (e) { toast(errText(e), 'bad') }
  }
  const body = reader ? h(SourceReader, { st, reader }) : h('div', { className: 'imp-src-body' },
    h('div', { className: 'imp-pane-head' },
      h('h2', { className: 'imp-h2' }, 'Sources'),
      srcs.length ? h('span', { className: 'imp-count' }, on.length === srcs.length ? String(srcs.length) : `${on.length} of ${srcs.length}`) : null,
      h('span', { className: 'imp-grow' }),
      sample ? null : h('div', { className: 'imp-addwrap' },
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => setAdding(adding ? null : 'menu'), 'aria-haspopup': 'menu', 'aria-expanded': adding === 'menu' }, h(Icon, { name: 'plus', size: 14 }), 'Add'),
        adding === 'menu' ? h('div', { className: 'imp-menu imp-addmenu', role: 'menu' },
          h('button', { type: 'button', role: 'menuitem', className: 'imp-menu-item', onClick: () => { setAdding(null); addFiles() } }, h(Icon, { name: 'doc', size: 15 }), 'A file'),
          h('button', { type: 'button', role: 'menuitem', className: 'imp-menu-item', onClick: () => setAdding('link') }, h(Icon, { name: 'web', size: 15 }), 'A web page'),
          h('button', { type: 'button', role: 'menuitem', className: 'imp-menu-item', onClick: () => setAdding('paste') }, h(Icon, { name: 'paste', size: 15 }), 'Pasted text')) : null)),
    adding === 'link' ? h(AddLink, { done: () => setAdding(null) }) : null,
    adding === 'paste' ? h(AddPaste, { done: () => setAdding(null) }) : null,
    reading.map(b => h(Working, { key: b, step: b })),
    srcs.length ? h('ol', { className: 'imp-srcs' }, srcs.map((s, i) => h(SourceCard, { key: s.id, s, n: i + 1, sample })))
      : h('div', { className: 'imp-src-empty' },
        h('p', null, 'No sources yet.'),
        h('p', { className: 'imp-src-empty-kinds' }, 'Reports, Word files, PDFs, transcripts, web pages or pasted notes.'),
        h(Button, { size: 'sm', variant: 'secondary', onClick: addFiles }, h(Icon, { name: 'plus', size: 14 }), 'Add a file')),
    srcs.length > 1 && on.length < srcs.length ? h('button', { type: 'button', className: 'imp-linkish imp-useall', onClick: () => setAll(true) }, 'Use every source') : null)
  return h('aside', {
    className: cls('imp-pane imp-srcpane', drag && 'is-drop', reader && 'is-reading'), 'aria-label': 'Sources',
    onDragOver: e => { e.preventDefault(); setDrag(true) }, onDragLeave: () => setDrag(false),
    onDrop: e => { e.preventDefault(); setDrag(false); for (const f of (e.dataTransfer && e.dataTransfer.files) || []) readFile(f) },
  },
  h(SourceRail, { st }),
  body)
}

/* At 1000 to 1179 wide the Sources column folds to a 56px rail: one glyph per source, open as an overlay. */
function SourceRail({ st }) {
  const srcs = st.sources || []
  return h('div', { className: 'imp-rail', role: 'toolbar', 'aria-label': 'Sources' },
    h('button', { type: 'button', className: 'imp-rail-btn', title: 'Show sources', 'aria-label': 'Show sources', onClick: () => $rail.set(!$rail.get()) }, h(Icon, { name: 'rail', size: 18 })),
    srcs.map((s, i) => h('button', { key: s.id, type: 'button', className: cls('imp-rail-btn', s.included && 'is-on'), title: `${i + 1}. ${s.title}${s.included ? '' : ' (not in use)'}`, 'aria-label': `${s.title}${s.included ? '' : ', not in use'}`,
      onClick: () => { $reader.set(null); $rail.set(true) } },
    h(Icon, { name: sourceGlyph(s), size: 18 }), h('span', { className: 'imp-rail-n', 'aria-hidden': 'true' }, String(i + 1)))),
    isSample(st) ? null : h('button', { type: 'button', className: 'imp-rail-btn', title: 'Add a file', 'aria-label': 'Add a file', onClick: addFiles }, h(Icon, { name: 'plus', size: 18 })))
}

function SourceCard({ s, n, sample }) {
  const [open, setOpen] = useState(false)
  const toggle = async () => {
    try { const r = await post('sources/include', { ids: [s.id], on: !s.included }); $state.set({ ...$state.get(), sources: r.sources }) } catch (e) { toast(errText(e), 'bad') }
  }
  const summarize = async () => {
    try { const r = await post(`sources/${s.id}/summarize`); pollJob(r.job, () => refresh(), j => { refresh(); toast(j.error, 'bad') }); refresh() } catch (e) { toast(errText(e), 'bad') }
  }
  const meta = [s.origin && s.origin !== 'pasted' && !/^https?:/.test(s.origin) ? s.origin : s.kind, unitText(s)].filter(Boolean).join(' · ')
  return h('li', { className: cls('imp-scard', !s.included && 'is-off') },
    h('div', { className: 'imp-scard-top' },
      h('span', { className: 'imp-scard-glyph', 'aria-hidden': 'true' }, h(Icon, { name: sourceGlyph(s), size: 16 })),
      h('button', { type: 'button', className: 'imp-scard-title', onClick: () => $reader.set({ id: s.id, ref: null }) }, s.title),
      h('label', { className: 'imp-tick', title: s.included ? 'In use' : 'Not in use' },
        h('input', { type: 'checkbox', checked: s.included, onChange: toggle, 'aria-label': `Use ${s.title}` }),
        h('span', { className: 'imp-tick-box', 'aria-hidden': 'true' }, s.included ? h(Icon, { name: 'check', size: 12 }) : null))),
    h('p', { className: 'imp-scard-meta' }, meta),
    s.summary ? h('p', { className: cls('imp-scard-sum', open && 'is-open'), onClick: () => setOpen(!open) }, s.summary)
      : s.summary_state === 'running' ? h('p', { className: 'imp-scard-wait' }, h('span', { className: 'imp-spin' }), 'Writing a short summary')
        : s.summary_state === 'failed' ? h('p', { className: 'imp-scard-wait' }, 'The summary didn’t finish. ', h('button', { type: 'button', className: 'imp-linkish', onClick: summarize }, 'Try again'))
          : h('button', { type: 'button', className: 'imp-linkish', onClick: summarize }, 'Write a summary'))
}

// When a scroll can't go as far as asked (the end of the list is near), the top edge can land mid-line. Back up so
// the first thing showing at the top starts whole: a paragraph, a list row, an answer's footer or a question.
function unclip(box, pad) {
  if (!box || !box.getBoundingClientRect) return
  const edge = box.getBoundingClientRect().top
  const cut = [...box.querySelectorAll('p, li, h2, h3, .imp-a-foot, .imp-q')].filter(e => { const r = e.getBoundingClientRect(); return r.height && r.top < edge - 1 && r.bottom > edge + 1 })
    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0]
  if (cut) box.scrollTop -= edge + pad - cut.getBoundingClientRect().top
}

// The cited passage lands just under the reader's sticky header. When the list can't scroll that far (the passage
// is near the end), the scroll backs up to the passage boundary above, so no line is ever cut under the header.
function scrollUnderHead(el) {
  let box = el.parentElement
  while (box && !(/(auto|scroll)/.test(getComputedStyle(box).overflowY) && box.scrollHeight > box.clientHeight)) box = box.parentElement
  if (!box) return
  const head = box.querySelector('.imp-reader-back')
  const top = () => box.getBoundingClientRect().top + (head ? head.getBoundingClientRect().height : 0)
  box.scrollTop += el.getBoundingClientRect().top - top() - 4
  const body = el.closest('.imp-reader-body')
  const rows = body ? [...body.children].flatMap(c => c.tagName === 'OL' ? [...c.children] : [c]) : [...el.parentElement.children]
  const cut = rows.find(p => { const r = p.getBoundingClientRect(); return r.top < top() - 1 && r.bottom > top() + 1 })
  if (cut) box.scrollTop -= top() - cut.getBoundingClientRect().top + 4
}

function SourceReader({ st, reader }) {
  const [v, setV] = useState(null)
  const [err, setErr] = useState('')
  const list = useRef(null)
  useEffect(() => { setV(null); setErr(''); rest(`sources/${reader.id}`).then(setV, e => setErr(errText(e))) }, [reader.id])
  useLayoutEffect(() => {
    if (!v || !reader.ref || !list.current) return
    const el = list.current.querySelector(`[data-ref="${reader.ref}"]`)
    if (el) scrollUnderHead(el)
  }, [v, reader.ref])
  const s = v && v.source
  return h('div', { className: 'imp-reader' },
    h('div', { className: 'imp-reader-back' }, h('button', { type: 'button', className: 'imp-linkish', onClick: () => $reader.set(null) }, h(Icon, { name: 'back', size: 14 }), 'All sources'), s ? h('span', { className: 'imp-reader-name' }, s.title) : null),
    err ? h('p', { className: 'imp-error' }, `${err} Go back and open it again.`) : !v ? h(Working, { step: 'Opening the source' }) : h('div', { className: 'imp-reader-body' },
      h('h2', { className: 'imp-h2' }, s.title),
      h('p', { className: 'imp-scard-meta' }, [s.origin && s.origin !== 'pasted' ? s.origin : s.kind, unitText(s)].filter(Boolean).join(' · ')),
      s.summary ? h('p', { className: 'imp-reader-sum' }, s.summary) : null,
      h('ol', { className: 'imp-passages', ref: list }, v.passages.map(p => h('li', { key: p.ref, 'data-ref': p.ref, className: cls('imp-pass', p.ref === reader.ref && 'is-cited') },
        h('span', { className: 'imp-pass-loc' }, p.locator), h('p', null, p.text)))),
      v.more ? h('p', { className: 'imp-scard-meta' }, 'This source is long. The first 800 passages show here.') : null))
}

function AddLink({ done }) {
  const [url, setUrl] = useState('')
  const [err, setErr] = useState('')
  const go = async () => {
    setErr('')
    try {
      const r = await post('sources/url', { url })
      done()
      const label = 'Reading the page'
      $reading.set([...$reading.get(), label])
      const off = () => $reading.set($reading.get().filter(x => x !== label))
      pollJob(r.job, async () => { off(); await refresh(); watchSummaries($state.get()) }, j => { off(); toast(j.error, 'bad') })
    } catch (e) { setErr(`${errText(e)} Check the address and try again.`) }
  }
  return h('div', { className: 'imp-mini-form' },
    h(Input, { value: url, placeholder: 'https://', autoFocus: true, onChange: e => setUrl(e.target.value), onKeyDown: e => { if (e.key === 'Enter') go() }, 'aria-label': 'Web address' }),
    err ? h('p', { className: 'imp-error' }, err) : null,
    h('div', { className: 'imp-row' }, h(Button, { size: 'sm', onClick: go, disabled: !url.trim() }, 'Add the page'), h(Button, { size: 'sm', variant: 'secondary', onClick: done }, 'Cancel')))
}

function AddPaste({ done }) {
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [err, setErr] = useState('')
  const go = async () => {
    try { await post('sources/text', { title, text }); done(); await refresh(); watchSummaries($state.get()) } catch (e) { setErr(`${errText(e)} Try again.`) }
  }
  return h('div', { className: 'imp-mini-form' },
    h(Input, { value: title, placeholder: 'Title', onChange: e => setTitle(e.target.value), 'aria-label': 'Title' }),
    h(Textarea, { value: text, rows: 6, placeholder: 'Paste notes, an email or a passage', onChange: e => setText(e.target.value), 'aria-label': 'Text' }),
    err ? h('p', { className: 'imp-error' }, err) : null,
    h('div', { className: 'imp-row' }, h(Button, { size: 'sm', onClick: go, disabled: !text.trim() }, 'Add the text'), h(Button, { size: 'sm', variant: 'secondary', onClick: done }, 'Cancel')))
}

/* ---- Citation chips ---- */

function Cite({ chip, n, lit }) {
  if (!chip) return null
  const where = [chip.source || chip.title, chip.locator].filter(Boolean).join(', ')
  return h('button', { type: 'button', className: cls('imp-cite', lit && 'is-lit'), onClick: () => openReader(chip), title: where, 'aria-label': `Source ${n}: ${where}` }, String(n))
}
// A source pill: the file a claim came from, by name, with its place inside it.
function SourcePill({ chip, st }) {
  const s = ((st && st.sources) || []).find(x => x.id === chip.source_id)
  const name = (s && s.origin && s.origin !== 'pasted' && !/^https?:/.test(s.origin)) ? s.origin : (chip.source || chip.title || (s && s.title) || 'Source')
  return h('button', { type: 'button', className: 'imp-spill', onClick: () => openReader(chip), title: [chip.source || chip.title, chip.locator].filter(Boolean).join(', ') },
    h(Icon, { name: sourceGlyph(s || { origin: name }), size: 13 }), h('span', { className: 'imp-spill-name' }, name), chip.locator ? h('span', { className: 'imp-spill-loc' }, chip.locator) : null)
}

/* ---- Ask ---- */

function ChatPane({ st }) {
  const chats = useValue($chats)
  const asking = useValue($asking)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const scroller = useRef(null)
  const target = useRef(null) // the chat id to bring to the top once it lands
  const on = included(st)
  const list = chats || []
  const lastAi = list.map(c => c.role !== 'user').lastIndexOf(true) // the model's credit shows once, on its newest answer
  // Opening the notebook starts at the guide; a new question or answer lands with its top at the top.
  useLayoutEffect(() => {
    const el = scroller.current
    if (!el || !target.current) return
    const node = el.querySelector(`[data-turn="${target.current}"]`)
    if (node) { el.scrollTop = Math.max(0, node.offsetTop - 14); unclip(el, 6); if (target.current !== 'pending') target.current = null }
  }, [list.length, !!asking])
  const ask = async question => {
    setErr('')
    if (!on.length) { setErr((st.sources || []).length ? 'No source is ticked. Tick one on the left, then ask again.' : 'Add a source first, then ask.'); return }
    const ns = (st.sources || []).map((s, i) => s.included ? i + 1 : 0).filter(Boolean)
    $asking.set({ question, job: null, source_ns: ns })
    target.current = 'pending'
    setQ('')
    try {
      const r = await post('ask', { question, source_ids: on.map(s => s.id) })
      $asking.set({ question, job: r.job, source_ns: ns })
      pollJob(r.job, async () => {
        const c = await rest('chats')
        const before = new Set(list.map(x => x.id))
        const fresh = c.chats.find(x => x.role === 'user' && !before.has(x.id))
        target.current = fresh ? String(fresh.id) : null
        $asking.set(null)
        $chats.set(c.chats)
      }, j => { $asking.set(null); setQ(question); setErr(`${j.error || 'The answer didn’t finish.'}`) })
    } catch (e) { $asking.set(null); setQ(question); setErr(`${errText(e)} Try again.`) }
  }
  const send = () => { if (q.trim() && !asking) ask(q.trim()) }
  return h('section', { className: 'imp-pane imp-ask', 'aria-label': 'Ask' },
    h('div', { className: 'imp-pane-head imp-ask-head' },
      h('h2', { className: 'imp-h2' }, 'Ask'),
      h('span', { className: 'imp-grow' }),
      list.length ? h(DeleteButton, { size: 'sm', className: 'imp-quiet', label: 'Clear the chat', onDelete: async () => { try { await del('chats'); $chats.set([]) } catch (e) { toast(errText(e), 'bad') } } }) : null),
    h('div', { className: 'imp-chat-scroll', ref: scroller },
      h(GuideBlock, { st, ask, credit: lastAi < 0 }),
      list.map((c, i) => c.role === 'user'
        ? h('p', { key: c.id, className: 'imp-q', 'data-turn': String(c.id) }, c.text)
        : h(Answer, { key: c.id, c, ask, st, last: i === list.length - 1 && !asking, credit: i === lastAi })),
      asking ? h('p', { className: 'imp-q', 'data-turn': 'pending' }, asking.question) : null,
      asking ? h(ReadingCard, { st, ns: asking.source_ns }) : null),
    h('div', { className: 'imp-composer' },
      err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
      h('div', { className: 'imp-composer-box' },
        h(Textarea, { value: q, rows: 2, placeholder: on.length ? 'Ask about your sources' : 'Tick a source to ask about it',
          onChange: e => setQ(e.target.value), 'aria-label': 'Question', 'aria-keyshortcuts': 'Meta+Enter Control+Enter',
          onKeyDown: e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey || !e.shiftKey)) { e.preventDefault(); send() } } }),
        h('button', { type: 'button', className: 'imp-send', disabled: !q.trim() || !!asking, onClick: send, 'aria-label': 'Ask', title: 'Ask' }, h(Icon, { name: 'send', size: 16 }))),
      h('p', { className: 'imp-scope' }, on.length ? plural(on.length, 'source') : 'No source ticked')))
}

/* While a question is answered: which sources are being read, lit. No fake typing. */
function ReadingCard({ st, ns }) {
  const [, tick] = useState(0)
  const t0 = useRef(Date.now())
  useEffect(() => { const t = setInterval(() => tick(x => x + 1), 1000); return () => clearInterval(t) }, [])
  const secs = Math.round((Date.now() - t0.current) / 1000)
  const srcs = st.sources || []
  return h('div', { className: 'imp-reading', role: 'status' },
    h('span', { className: 'imp-spin' }),
    h('span', null, `Reading ${ns.length === 1 ? 'source' : 'sources'} `),
    ns.map((n, i) => h('span', { key: n, className: 'imp-cite is-lit is-static', title: (srcs[n - 1] || {}).title, style: { animationDelay: `${i * 160}ms` } }, String(n))),
    h('span', { className: 'imp-grow' }),
    secs >= 1 ? h('span', { className: 'imp-secs' }, `${secs} s`) : null)
}

/* The notebook guide: the model's read of the ticked sources, what they ask for, and questions people may raise. */
function GuideBlock({ st, ask, credit = true }) {
  const guide = useValue($guide)
  const gjob = useValue($guideJob)
  const copy = useValue($stale)
  const on = included(st)
  const ids = on.map(s => s.id)
  useEffect(() => { // never from the stored copy: the ticked sources may have changed since
    if (guide === null && !gjob && ids.length && !isSample(st) && !copy) writeGuide(ids)
  }, [guide === null, ids.join(','), copy])
  if (!ids.length) return h('div', { className: 'imp-gd-empty' }, (st.sources || []).length ? 'No source is ticked. Tick one on the left to read it here.' : 'Add a source on the left.')
  if (gjob && gjob.status !== 'done') {
    if (gjob.status === 'failed') return h('div', { className: 'imp-failed', role: 'alert' }, h('p', null, gjob.error || 'The guide didn’t finish.'), h('div', { className: 'imp-row' }, h(Button, { size: 'sm', variant: 'secondary', onClick: () => writeGuide(ids) }, 'Retry')))
    return h('div', { className: 'imp-gd is-wait', role: 'status' }, h(JobSteps, { job: gjob }), h('div', { className: 'imp-skel' }, h('span', null), h('span', null), h('span', { style: { width: '62%' } })))
  }
  if (guide === undefined) return h('div', { className: 'imp-gd is-wait' }, h('div', { className: 'imp-skel' }, h('span', null), h('span', null), h('span', { style: { width: '62%' } })))
  if (!guide) return null
  // One running number per passage across the paragraph, the way an answer numbers its sources.
  const nums = new Map()
  const numOf = c => { if (!nums.has(c.ref)) nums.set(c.ref, nums.size + 1); return nums.get(c.ref) }
  const stale = (guide.source_ids || []).slice().sort().join(',') !== ids.slice().sort().join(',')
  const asks = guide.asks || []
  const qs = guide.questions || []
  const askSrc = (() => {
    const t = new Set(asks.flatMap(a => (a.chips || []).map(c => c.source || c.title)))
    return t.size === 1 ? `Your ${[...t][0].toLowerCase()}` : 'Your sources'
  })()
  const boardy = asks.some(a => /board/i.test(`${a.who} ${(a.brief || {}).who || ''}`))
  return h('div', { className: 'imp-gd' },
    h('p', { className: 'imp-gd-text' }, (guide.guide || []).map((g, i) => h('span', { key: i }, g.text, ' ', (g.chips || []).map(c => h(Cite, { key: c.ref, chip: c, n: numOf(c) })), ' '))),
    credit || stale ? h('p', { className: 'imp-by' }, credit ? (guide.by || 'Written by your Hermes model') : null, credit && stale ? ' · ' : null, stale ? h('button', { key: 'r', type: 'button', className: 'imp-linkish', onClick: () => writeGuide(ids) }, `Read the ${plural(ids.length, 'ticked source')} again`) : null) : null,
    asks.length ? h('section', { className: 'imp-gd-sec' },
      h('h3', { className: 'imp-h3' }, `${askSrc} ask${asks.length === 1 && askSrc === 'Your sources' ? 's' : ''} for ${say(asks.length)} thing${asks.length === 1 ? '' : 's'}`),
      h('ul', { className: 'imp-asks' }, asks.map(a => h(AskCard, { key: a.id, a, st })))) : null,
    qs.length ? h('section', { className: 'imp-gd-sec' },
      h('h3', { className: 'imp-h3' }, boardy ? 'Questions the board may ask' : 'Questions people may ask', h('span', { className: 'imp-tag is-quiet' }, 'Suggested')),
      h('ul', { className: 'imp-qrows' }, qs.map((x, i) => h('li', { key: i }, h('button', { type: 'button', className: 'imp-qrow', onClick: () => ask(x.text) },
        h('span', null, x.text), h(Icon, { name: 'chevr', size: 14 })))))) : null)
}

function AskCard({ a, st }) {
  const k = KIND_OF[a.kind] || KIND_OF.deck
  const by = a.by ? `by ${a.by.replace(/^by\s+/i, '').replace(/^the\s+/i, '')}` : ''
  return h('li', { className: 'imp-askcard' },
    h('span', { className: 'imp-askcard-glyph', 'aria-hidden': 'true' }, h(Icon, { name: k.icon, size: 18 })),
    h('div', { className: 'imp-askcard-body' },
      h('strong', null, a.what),
      h('p', { className: 'imp-askcard-meta' }, [`${k.label} for ${(a.brief && a.brief.who) || a.who}`, by].filter(Boolean).join(', ')),
      (a.chips || []).slice(0, 1).map(c => h(SourcePill, { key: c.ref, chip: c, st }))),
    h(Button, { size: 'sm', variant: 'secondary', className: 'imp-quiet is-go', onClick: () => openFlow(k.id, { ask: a }) }, 'Make'))
}

// An answer: the first sentence leads in bold, then the rest in spaced paragraphs; its sources fold to one line.
function splitLead(text) {
  const paras = String(text || '').split(/\n+/).map(x => x.trim()).filter(Boolean)
  if (!paras.length) return { lead: '', paras: [] }
  const first = paras[0]
  const m = first.match(/^(.+?[.!?](?:\s*\[\d+\])*)(\s+[A-Z“"(].*)?$/s)
  if (m && m[2]) return { lead: m[1], paras: [m[2].trim(), ...paras.slice(1)] }
  return { lead: first, paras: paras.slice(1) }
}
function withChips(text, chipOf, keyBase) {
  // A chip keeps the punctuation after it on its own line ("nine weeks [2]." never breaks before the period).
  const parts = String(text).split(/(\[\d+\])/)
  const out = []
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i]
    const m = p.match(/^\[(\d+)\]$/)
    const ch = m && chipOf(Number(m[1]))
    if (m && !ch) continue
    if (!ch) { out.push(h('span', { key: `${keyBase}-${i}` }, p)); continue }
    const next = parts[i + 1] || ''
    const punct = (next.match(/^[.,;:!?)”"]+/) || [''])[0]
    if (punct) parts[i + 1] = next.slice(punct.length)
    out.push(h('span', { key: `${keyBase}-${i}`, className: 'imp-nowrap' }, h(Cite, { chip: ch, n: ch.n }), punct || null))
  }
  return out
}

function Answer({ c, ask, st, last, credit = true }) {
  const [pinned, setPinned] = useState(c.pinned)
  const [srcOpen, setSrcOpen] = useState(false)
  const [menu, setMenu] = useState(false)
  useEffect(() => setPinned(c.pinned), [c.pinned])
  const chips = c.chips || []
  const chipOf = n => chips.find(x => x.n === n)
  // The fold counts the sources the answer used, not its numbered marks (three marks from two files is 2 sources),
  // and says so when one of them has been switched off since.
  const used = [...new Set(chips.map(x => x.source_id || x.title || x.source))]
  const srcs = (st && st.sources) || []
  const offNow = used.filter(id => { const s = srcs.find(x => x.id === id); return s && s.included === false }).length
  const usedLabel = plural(used.length, 'source') + (offNow ? `, ${offNow === used.length ? (offNow === 1 ? 'now off' : 'all now off') : `${offNow} now off`}` : '')
  // The backend may split the answer itself (lead, detail, more); else the first sentence leads.
  const split = c.lead ? { lead: c.lead, paras: String(c.detail || '').split(/\n+/).map(x => x.trim()).filter(Boolean) } : splitLead(c.text)
  const { lead, paras } = split
  const more = c.lead ? String(c.more || '').split(/\n+/).map(x => x.trim()).filter(Boolean) : []
  const [moreOpen, setMoreOpen] = useState(false)
  const plain = s => String(s).replace(/\s*\[\d+\]/g, '').trim()
  const pin = async () => {
    try { const r = await post('notes', { chat_id: c.id }); setPinned(true); $state.set({ ...$state.get(), notes: r.notes }); toast('Pinned to Notes.') } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
  }
  const copy = () => { try { navigator.clipboard.writeText(plain(c.text)); toast('Copied') } catch (e) { toast('Copy didn’t work here. Select the text instead.', 'bad') } }
  const makeFrom = kind => {
    setMenu(false)
    if (kind === 'visual') {
      const seed = { text: plain(c.text), lead: plain(lead), chat_id: c.id }
      const have = ($state.get().notes || []).find(n => n.chat_id === c.id)
      if (have || !canvasLane.GraphicOptions) { makeGraphicFrom(have || { text: c.text, chat_id: c.id }, seed); return }
      post('notes', { chat_id: c.id }).then(r => { setPinned(true); $state.set({ ...$state.get(), notes: r.notes }); makeGraphicFrom((r.notes || []).find(n => n.chat_id === c.id), seed) }, e => toast(`${errText(e)} Try again.`, 'bad'))
      return
    }
    openFlow(kind, { seed: { goal: plain(lead), text: plain(c.text), chat_id: c.id } })
  }
  return h('article', { className: 'imp-a' },
    h('p', { className: 'imp-a-lead' }, withChips(lead, chipOf, 'l')),
    paras.map((p, i) => h('p', { key: i, className: 'imp-a-p' }, withChips(p, chipOf, `p${i}`))),
    more.length ? (moreOpen ? more.map((p, i) => h('p', { key: `m${i}`, className: 'imp-a-p' }, withChips(p, chipOf, `m${i}`)))
      : h('button', { type: 'button', className: 'imp-a-fold', onClick: () => setMoreOpen(true) }, h(Icon, { name: 'chevr', size: 14 }), 'More')) : null,
    h('div', { className: 'imp-a-foot' },
      chips.length ? h('button', { type: 'button', className: 'imp-a-fold', 'aria-expanded': srcOpen, onClick: () => setSrcOpen(!srcOpen) },
        h(Icon, { name: srcOpen ? 'chevd' : 'chevr', size: 14 }), usedLabel) : null,
      h('span', { className: 'imp-grow' }),
      h(Button, { size: 'sm', variant: 'secondary', className: 'imp-quiet', disabled: pinned, onClick: pin }, h(Icon, { name: 'pin', size: 14 }), pinned ? 'Pinned' : 'Pin'),
      h('div', { className: 'imp-addwrap' },
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => setMenu(!menu), 'aria-haspopup': 'menu', 'aria-expanded': menu }, 'Make from this', h(Icon, { name: 'chevd', size: 14 })),
        menu ? h('div', { className: 'imp-menu imp-makemenu', role: 'menu' }, ['deck', 'onepager', 'visual'].map(id => h('button', { key: id, type: 'button', role: 'menuitem', className: 'imp-menu-item', onClick: () => makeFrom(id) },
          h(Icon, { name: KIND_OF[id].icon, size: 15 }), KIND_OF[id].label))) : null),
      h('button', { type: 'button', className: 'imp-iconbtn', onClick: copy, 'aria-label': 'Copy the answer', title: 'Copy' }, h(Icon, { name: 'copy', size: 15 }))),
    srcOpen ? h('ol', { className: 'imp-a-src' }, chips.map(ch => h('li', { key: ch.n },
      h('button', { type: 'button', className: 'imp-a-srcbtn', onClick: () => openReader(ch) }, h('span', { className: 'imp-cite is-static', 'aria-hidden': 'true' }, String(ch.n)),
        h('span', null, [ch.title || ch.source, ch.locator].filter(Boolean).join(', ')))))) : null,
    credit ? h('p', { className: 'imp-by' }, c.by || 'Written by your Hermes model') : null,
    last && c.followups && c.followups.length ? h('ul', { className: 'imp-qrows is-follow' }, c.followups.slice(0, 3).map(f => h('li', { key: f },
      h('button', { type: 'button', className: 'imp-qrow', onClick: () => ask(f) }, h('span', null, f), h(Icon, { name: 'chevr', size: 14 }))))) : null)
}

/* ---- Job steps: real step names, seconds per step, and Stop ---- */

function JobSteps({ job, onStop, compact }) {
  const [, tick] = useState(0)
  const running = !job.status || job.status === 'running' || job.status === 'queued'
  useEffect(() => { if (!running) return; const t = setInterval(() => tick(x => x + 1), 1000); return () => clearInterval(t) }, [running])
  const steps = (job.steps && job.steps.length) ? job.steps : [{ text: job.step || 'Starting', at: job.created_at || Date.now() / 1000 }]
  const now = Date.now() / 1000
  const secs = (a, b) => `${Math.max(0, Math.round((b || now) - (a || now)))} s`
  return h('div', { className: cls('imp-jsteps', compact && 'is-compact') },
    h('ol', { className: 'imp-steps' }, steps.map((s, i) => {
      const last = i === steps.length - 1
      const end = s.done_at || (!last ? steps[i + 1].at : (job.status === 'done' ? job.updated_at : null))
      const halted = last && (job.status === 'failed' || job.status === 'stopped')
      const state = halted ? (job.status === 'failed' ? 'is-bad' : 'is-stopped') : end ? 'is-done' : 'is-now'
      return h('li', { key: i, className: state },
        state === 'is-done' ? h('span', { className: 'imp-step-ic' }, h(Icon, { name: 'check', size: 13 })) : state === 'is-now' ? h('span', { className: 'imp-spin' }) : h('span', { className: 'imp-step-ic is-x' }, h(Icon, { name: state === 'is-bad' ? 'x' : 'stop', size: 12 })),
        h('span', { className: 'imp-step-text' }, s.text),
        h('span', { className: 'imp-secs' }, end ? secs(s.at, end) : state === 'is-now' ? secs(s.at, now) : ''))
    })),
    running && onStop ? h('div', { className: 'imp-row' }, h(Button, { size: 'sm', variant: 'secondary', onClick: onStop }, h(Icon, { name: 'stop', size: 13 }), 'Stop')) : null)
}

/* ---- Make: the brief, the outline, the build (middle column) ---- */

function briefText(b) {
  return [b.who && `For ${b.who}.`, b.goal && `${b.goal.replace(/[.\s]+$/, '')}.`, b.length && `${b.length.replace(/[.\s]+$/, '')}.`].filter(Boolean).join(' ')
}

function FlowPane({ st, flow }) {
  const k = KIND_OF[flow.kind] || KIND_OF.deck
  const kit = kitOf(st, useValue($kit))
  const close = () => $flow.set(null)
  const title = flow.ask ? flow.ask.what : flow.seed && flow.seed.goal ? `A ${k.noun} from this answer` : `A new ${k.noun}`
  return h('section', { className: 'imp-pane imp-ask imp-flow', 'aria-label': `Make the ${k.noun}` },
    h('div', { className: 'imp-pane-head imp-ask-head' },
      h('button', { type: 'button', className: 'imp-linkish', onClick: close }, h(Icon, { name: 'back', size: 14 }), 'Back to Ask'),
      h('span', { className: 'imp-grow' }),
      h('span', { className: 'imp-flow-steps', 'aria-label': 'Steps' },
        ['Brief', k.outline ? 'Outline' : null, 'Build'].filter(Boolean).map(s => h('span', { key: s, className: cls('imp-flow-step', (flow.build ? 'Build' : flow.step === 'outline' ? 'Outline' : 'Brief') === s && 'is-on') }, s)))),
    h('div', { className: 'imp-flow-scroll' },
      h('header', { className: 'imp-flow-head' },
        h('span', { className: 'imp-flow-glyph', 'aria-hidden': 'true' }, h(Icon, { name: k.icon, size: 20 })),
        h('div', null, h('p', { className: 'imp-flow-kind' }, k.label), h('h2', { className: 'imp-flow-title' }, title))),
      flow.build ? h(BuildCard, { st, flow, k, kit })
        : flow.kind === 'visual' && flow.seed && flow.seed.text ? h(GraphicOptions, { st, flow, kit })
          : flow.step === 'outline' ? h(OutlineEditor, { st, flow, k, kit })
            : h(BriefForm, { st, flow, k, kit })))
}

function BriefForm({ st, flow, k, kit }) {
  const a = flow.ask
  const seed = flow.seed || {}
  const pre = (a && a.brief) || {}
  const [who, setWho] = useState(pre.who || '')
  const [goal, setGoal] = useState(pre.goal || seed.goal || '')
  const [length, setLength] = useState(pre.length && !/^a short/i.test(pre.length) ? pre.length : k.length)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [job, setJob] = useState(flow.job || null)
  const on = included(st)
  const brief = { who: who.trim(), goal: goal.trim(), length: length.trim() }
  const reason = !on.length ? ((st.sources || []).length ? 'Tick at least one source on the left first.' : 'Add a source on the left first.') : !brief.goal ? 'Say what they should decide or do.' : ''
  const writeOutline = async () => {
    setErr(''); setBusy(true)
    try {
      const r = await post('outlines', { source_ids: on.map(s => s.id), brief, kind: 'deck', ...(a ? { ask: a } : {}) })
      setJob(r.job)
      $flow.set({ ...$flow.get(), job: r.job, brief })
      pollJob(r.job, j => { setJob(null); $flow.set({ ...$flow.get(), job: null, step: 'outline', outline: j.result, brief }) },
        j => { setJob(j); setBusy(false) }, j => setJob(j))
    } catch (e) { setErr(`${errText(e)} Try again.`); setBusy(false) }
  }
  const makeNow = async () => {
    setErr(''); setBusy(true)
    try {
      const notes = (st.notes || []).filter(n => seed.chat_id && n.chat_id === seed.chat_id).map(n => n.id)
      const r = await post('outputs', { kind: k.id, source_ids: on.map(s => s.id), kit_ids: [kit.id], brief: briefText(brief), note_ids: notes })
      const j = { ...r.job, params: { ...(r.job.params || {}), kind: k.id, kit_ids: [kit.id] } }
      $flow.set({ ...$flow.get(), build: j, brief })
      trackMake(j)
    } catch (e) { setErr(`${errText(e)} Try again.`); setBusy(false) }
  }
  if (job && job.status !== 'failed') {
    return h('div', { className: 'imp-flow-card', role: 'status' },
      h('p', { className: 'imp-flow-card-head' }, 'Writing the outline'),
      h(JobSteps, { job, onStop: async () => { const j = await stopJob(job); if (j) { setJob(null); setBusy(false) } } }))
  }
  return h('div', { className: 'imp-flow-card' },
    a ? h('div', { className: 'imp-flow-ask' }, h('p', null, `${a.who} asked for this${a.by ? `, by ${a.by.replace(/^by\s+/i, '').replace(/^the\s+/i, '')}` : ''}.`), (a.chips || []).slice(0, 1).map(c => h(SourcePill, { key: c.ref, chip: c, st }))) : null,
    h('div', { className: 'imp-brief' },
      h('label', { className: 'imp-field' }, h('span', null, 'Who it is for'), h(Input, { value: who, onChange: e => setWho(e.target.value), placeholder: 'Funders, the board, the city council' })),
      h('label', { className: 'imp-field' }, h('span', null, 'What they should decide or do'), h(Textarea, { value: goal, rows: 2, onChange: e => setGoal(e.target.value), placeholder: 'Fund the sixth site' })),
      h('label', { className: 'imp-field' }, h('span', null, 'Length'), h(Input, { value: length, onChange: e => setLength(e.target.value) })),
      h('div', { className: 'imp-field' }, h('span', null, 'Brand'), h(BrandChip, { st, kit }))),
    job && job.status === 'failed' ? h('div', { className: 'imp-failed', role: 'alert' }, h('p', null, job.error || 'The outline didn’t finish. Press Retry.')) : null,
    err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
    h('div', { className: 'imp-flow-acts' },
      k.outline ? h(Button, { onClick: writeOutline, loading: busy, disabled: busy || !!reason }, job && job.status === 'failed' ? 'Retry' : 'Write the outline')
        : h(Button, { onClick: makeNow, loading: busy, disabled: busy || !!reason }, `Make the ${k.noun}`),
      h('span', { className: 'imp-flow-from' }, reason || `From ${plural(on.length, 'source')}, in ${kit.name}`)))
}

function OutlineEditor({ st, flow, k, kit }) {
  const ol = flow.outline || {}
  const [slides, setSlides] = useState(() => (ol.slides || []).map((s, i) => ({ ...s, key: `s${i}` })))
  const [focus, setFocus] = useState(0)
  const [editing, setEditing] = useState(null)
  const [draft, setDraft] = useState('')
  const [rewrite, setRewrite] = useState(null) // {index, job, options}
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')
  const [shown, setShown] = useState(() => (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) ? 999 : 0)
  const list = useRef(null)
  useEffect(() => { // titles land in order, 40ms apart
    if (shown >= slides.length) return
    const t = setTimeout(() => setShown(n => n + 1), 40)
    return () => clearTimeout(t)
  }, [shown, slides.length])
  const save = async next => {
    setSlides(next); setErr('')
    if (!ol.outline_id) return
    setSaving(true)
    try {
      const r = await post(`outlines/${ol.outline_id}`, { slides: next.map(s => ({ title: s.title, type: s.type, refs: s.refs || (s.chips || []).map(c => c.ref) })) })
      const keyed = (r.slides || []).map((s, i) => ({ ...s, key: (next[i] || {}).key || `n${Date.now()}${i}` }))
      setSlides(keyed)
      $flow.set({ ...$flow.get(), outline: { ...ol, ...r, slides: r.slides } })
    } catch (e) { setErr(`${errText(e)} Your last change wasn’t saved. Try again.`) }
    setSaving(false)
  }
  const move = (i, d) => {
    const j = i + d
    if (j < 0 || j >= slides.length) return
    const next = slides.slice(); const [x] = next.splice(i, 1); next.splice(j, 0, x)
    setFocus(j); save(next)
    setTimeout(() => { const el = list.current && list.current.querySelector(`[data-row="${j}"]`); if (el) el.focus() }, 0)
  }
  const remove = i => { const next = slides.filter((_, x) => x !== i); setFocus(Math.max(0, Math.min(i, next.length - 1))); save(next) }
  const add = () => {
    const last = slides[slides.length - 1] || {}
    const next = [...slides, { title: 'New slide: say the one point it makes', type: 'content', refs: last.refs || [], chips: last.chips || [], key: `n${Date.now()}` }]
    setFocus(next.length - 1); setEditing(next.length - 1); setDraft(next[next.length - 1].title); setSlides(next)
  }
  const commit = i => {
    const t = draft.trim()
    setEditing(null)
    if (!t || t === slides[i].title) return
    save(slides.map((s, x) => x === i ? { ...s, title: t } : s))
  }
  const askRewrite = async i => {
    setRewrite({ index: i, job: { status: 'running', step: 'Writing three new titles', created_at: Date.now() / 1000 } })
    try {
      const r = await post(`outlines/${ol.outline_id}/rewrite`, { index: i })
      setRewrite({ index: i, job: r.job })
      pollJob(r.job, j => setRewrite({ index: i, options: (j.result && j.result.options) || [] }), j => setRewrite({ index: i, job: j }), j => setRewrite(x => x && x.index === i && !x.options ? { index: i, job: j } : x))
    } catch (e) { setRewrite({ index: i, job: { status: 'failed', error: `${errText(e)} Try again.` } }) }
  }
  const pick = (i, o) => { setRewrite(null); save(slides.map((s, x) => x === i ? { ...s, title: o.title, chips: o.chips || s.chips, hint: o.hint, words: o.words } : s)) }
  const build = async () => {
    setErr('')
    const on = included(st)
    try {
      const r = await post('outputs', { kind: 'deck', source_ids: on.map(s => s.id), kit_ids: [kit.id], brief: briefText(flow.brief || {}), outline_id: ol.outline_id })
      const j = { ...r.job, params: { ...(r.job.params || {}), kind: 'deck', kit_ids: [kit.id], outline_id: ol.outline_id } }
      $flow.set({ ...$flow.get(), build: j })
      trackMake(j)
    } catch (e) { setErr(`${errText(e)} Try again.`) }
  }
  const onKey = (e, i) => {
    if (editing !== null) return
    if (e.altKey && e.key === 'ArrowUp') { e.preventDefault(); move(i, -1) } else if (e.altKey && e.key === 'ArrowDown') { e.preventDefault(); move(i, 1) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); const j = Math.max(0, i - 1); setFocus(j); const el = list.current.querySelector(`[data-row="${j}"]`); if (el) el.focus() }
    else if (e.key === 'ArrowDown') { e.preventDefault(); const j = Math.min(slides.length - 1, i + 1); setFocus(j); const el = list.current.querySelector(`[data-row="${j}"]`); if (el) el.focus() }
    else if (e.key === 'Enter') { e.preventDefault(); setEditing(i); setDraft(slides[i].title) }
  }
  return h('div', { className: 'imp-flow-card imp-outline' },
    h('div', { className: 'imp-outline-head' },
      h('p', null, h('strong', null, plural(slides.length + 1, 'slide')), ` for ${(flow.brief || {}).who || 'your readers'}`),
      h('span', { className: 'imp-grow' }),
      saving ? h('span', { className: 'imp-secs' }, 'Saving') : null),
    (ol.warnings || []).length ? h('p', { className: 'imp-outline-warn' }, ol.warnings.join(' ')) : null,
    h('ol', { className: 'imp-ol', ref: list }, h('li', { className: 'imp-ol-row is-fixed', 'aria-label': 'Slide 1: the title slide' },
      h('span', { className: 'imp-ol-n' }, '1'),
      h('span', { className: 'imp-ol-type' }, h(Icon, { name: 'deck', size: 16 })),
      h('div', { className: 'imp-ol-body' }, h('p', { className: 'imp-ol-title' }, 'Title slide'))), slides.map((s, i) => {
      const on = focus === i
      const rw = rewrite && rewrite.index === i ? rewrite : null
      return h('li', { key: s.key, 'data-row': i, tabIndex: 0, className: cls('imp-ol-row', on && 'is-focus', i >= shown && 'is-hidden'),
        onFocus: () => setFocus(i), onClick: () => setFocus(i), onKeyDown: e => onKey(e, i), 'aria-label': `Slide ${i + 2}: ${s.title}` },
      h('span', { className: 'imp-ol-n' }, String(i + 2)),
      h('span', { className: 'imp-ol-type', title: SLIDE_TYPE[s.type] || s.type }, h(Icon, { name: ICONS[s.type] ? s.type : 'content', size: 16 })),
      h('div', { className: 'imp-ol-body' },
        editing === i
          ? h('input', { className: 'imp-ol-input', value: draft, autoFocus: true, 'aria-label': `Title of slide ${i + 2}`, onChange: e => setDraft(e.target.value),
            onKeyDown: e => { e.stopPropagation(); if (e.key === 'Enter') commit(i); else if (e.key === 'Escape') setEditing(null) }, onBlur: () => commit(i) })
          : h('p', { className: 'imp-ol-title' }, s.title),
        h('div', { className: 'imp-ol-meta' },
          h('span', { className: 'imp-ol-kind' }, SLIDE_TYPE[s.type] || 'Slide'),
          (s.chips || []).filter((c, x, all) => all.findIndex(y => y.ref === c.ref) === x).slice(0, 3).map(c => h('button', { key: c.ref, type: 'button', className: 'imp-locchip', title: [c.source || c.title, c.locator].filter(Boolean).join(', '),
            onClick: e => { e.stopPropagation(); openReader(c) } }, String(c.locator || c.source || c.ref).replace(/[“”"]/g, ''))),
          s.hint === 'split' ? h('button', { type: 'button', className: 'imp-ol-split', onClick: e => { e.stopPropagation(); setFocus(i); setEditing(i); setDraft(s.title) } }, h(Icon, { name: 'split', size: 13 }), 'Two points here. Split this?') : null),
        rw ? h('div', { className: 'imp-rw' },
          rw.options ? [
            h('p', { key: 'h', className: 'imp-rw-head' }, 'Pick a new title'),
            ...rw.options.map((o, x) => h('button', { key: x, type: 'button', className: 'imp-rw-opt', onClick: e => { e.stopPropagation(); pick(i, o) } }, o.title)),
            h('button', { key: 'k', type: 'button', className: 'imp-linkish', onClick: e => { e.stopPropagation(); setRewrite(null) } }, 'Keep the one I have'),
          ] : rw.job && rw.job.status === 'failed' ? h('div', { className: 'imp-row' }, h('p', { className: 'imp-error' }, rw.job.error || 'That didn’t work.'), h(Button, { size: 'sm', variant: 'secondary', onClick: () => askRewrite(i) }, 'Retry'))
            : h(JobSteps, { job: rw.job || {}, compact: true })) : null),
      on && editing !== i ? h('div', { className: 'imp-ol-acts', onClick: e => e.stopPropagation() },
        h('button', { type: 'button', className: 'imp-iconbtn', disabled: i === 0, onClick: () => move(i, -1), title: 'Move up (Alt+Up)', 'aria-label': 'Move up' }, h(Icon, { name: 'up', size: 15 })),
        h('button', { type: 'button', className: 'imp-iconbtn', disabled: i === slides.length - 1, onClick: () => move(i, 1), title: 'Move down (Alt+Down)', 'aria-label': 'Move down' }, h(Icon, { name: 'down', size: 15 })),
        h('button', { type: 'button', className: 'imp-iconbtn', onClick: () => { setEditing(i); setDraft(s.title) }, title: 'Edit', 'aria-label': 'Edit the title' }, h(Icon, { name: 'edit', size: 15 })),
        h('button', { type: 'button', className: 'imp-textbtn', onClick: () => askRewrite(i), disabled: !!rw && !rw.options }, h(Icon, { name: 'redo', size: 14 }), 'Rewrite this title'),
        h('button', { type: 'button', className: 'imp-iconbtn', onClick: () => remove(i), title: 'Delete', 'aria-label': 'Delete this slide', disabled: slides.length <= 1 }, h(Icon, { name: 'trash', size: 15 }))) : null)
    })),
    h('button', { type: 'button', className: 'imp-ol-add', onClick: add }, h(Icon, { name: 'plus', size: 14 }), 'Add a slide'),
    err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
    h('div', { className: 'imp-flow-acts' },
      h(Button, { onClick: build, disabled: !slides.length || saving || editing !== null }, 'Build'),
      h(Button, { variant: 'secondary', onClick: () => $flow.set({ ...$flow.get(), step: 'brief', outline: null }) }, 'Change the brief'),
      h('span', { className: 'imp-flow-from' }, `${plural(slides.length + 1, 'slide')} in ${kit.name}`)))
}

function BuildCard({ st, flow, k, kit }) {
  const job = flow.build
  const stopped = job.status === 'stopped'
  const failed = job.status === 'failed'
  return h('div', { className: 'imp-flow-card', role: 'status' },
    h('p', { className: 'imp-flow-card-head' }, stopped ? 'Stopped. Your outline is kept.' : failed ? `The ${k.noun} didn’t finish.` : `Building the ${k.noun} in ${kit.name}`),
    h(JobSteps, { job, onStop: () => stopJob(job) }),
    failed && job.error ? h('p', null, job.error) : null,
    flow.outline && (flow.outline.slides || []).length ? h(BuildPlan, { slides: flow.outline.slides, job }) : null,
    stopped || failed ? h('div', { className: 'imp-flow-acts' },
      h(Button, { onClick: () => retryMake(job) }, 'Retry'),
      flow.outline ? h(Button, { variant: 'secondary', onClick: () => $flow.set({ ...$flow.get(), build: null, step: 'outline' }) }, 'Back to the outline') : null) : null)
}

// The outline being built, slide by slide: done, the one being written, still to come.
function BuildPlan({ slides, job }) {
  const step = String(job.step || ((job.steps || []).slice(-1)[0] || {}).text || '')
  const m = step.match(/slide (\d+) of (\d+)/i)
  const at = job.status === 'done' ? slides.length : m ? Number(m[1]) - 1 : /check|set|brand|render/i.test(step) ? slides.length : -1
  return h('ol', { className: 'imp-plan' }, h('li', { className: at > 0 || job.status === 'done' ? 'is-done' : '' },
    h('span', { className: 'imp-plan-n' }, at > 0 || job.status === 'done' ? h(Icon, { name: 'check', size: 12 }) : '1'),
    h('span', { className: 'imp-plan-t' }, 'Title slide'),
    h('span', { className: 'imp-plan-k' }, h(Icon, { name: 'deck', size: 14 }))), slides.map((s, i) => h('li', { key: i, className: i < at ? 'is-done' : i === at && job.status === 'running' ? 'is-now' : '' },
    h('span', { className: 'imp-plan-n' }, i < at ? h(Icon, { name: 'check', size: 12 }) : String(i + 2)),
    h('span', { className: 'imp-plan-t' }, s.title),
    h('span', { className: 'imp-plan-k', title: SLIDE_TYPE[s.type] || '' }, h(Icon, { name: ICONS[s.type] ? s.type : 'content', size: 14 })))))
}

/* A graphic from an answer: three forms from the checked numbers, then make the one picked. */
function GraphicOptions({ st, flow, kit }) {
  const [job, setJob] = useState(null)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')
  const on = included(st)
  const start = async () => {
    setErr(''); setRes(null)
    try {
      const note = (st.notes || []).find(n => flow.seed.chat_id && n.chat_id === flow.seed.chat_id)
      const r = await post('graphics/options', { source_ids: on.map(s => s.id), ...(note ? { note_id: note.id } : {}), text: flow.seed.text })
      setJob(r.job)
      pollJob(r.job, j => { setJob(null); setRes(j.result || { options: [] }) }, j => setJob(j), j => setJob(j))
    } catch (e) { setErr(`${errText(e)} Try again.`) }
  }
  useEffect(() => { start() }, [])
  const FORM = { bars: 'Bars', figures: 'Big numbers', compare: 'Side by side', timeline: 'Timeline' }
  const make = async o => {
    try {
      const r = await post('outputs', { kind: 'visual', source_ids: on.map(s => s.id), kit_ids: [kit.id], brief: `${flow.seed.lead || ''} Draw it as ${(FORM[o.form] || o.form).toLowerCase()}.`.trim() })
      const j = { ...r.job, params: { ...(r.job.params || {}), kind: 'visual', kit_ids: [kit.id] } }
      $flow.set({ ...$flow.get(), build: j })
      trackMake(j)
    } catch (e) { setErr(`${errText(e)} Try again.`) }
  }
  if (err) return h('div', { className: 'imp-failed', role: 'alert' }, h('p', null, err), h('div', { className: 'imp-row' }, h(Button, { size: 'sm', variant: 'secondary', onClick: start }, 'Retry')))
  if (job) return h('div', { className: 'imp-flow-card', role: 'status' }, h('p', { className: 'imp-flow-card-head' }, 'Finding three ways to draw it'),
    job.status === 'failed' ? h('div', { className: 'imp-row' }, h('p', null, job.error), h(Button, { size: 'sm', variant: 'secondary', onClick: start }, 'Retry')) : h(JobSteps, { job }))
  if (!res) return null
  const opts = res.options || []
  return h('div', { className: 'imp-flow-card' },
    opts.length ? h('ul', { className: 'imp-gopts' }, opts.map((o, i) => h('li', { key: i, className: 'imp-gopt' },
      h('span', { className: 'imp-gopt-glyph', 'aria-hidden': 'true' }, h(Icon, { name: o.form === 'timeline' ? 'timeline' : o.form === 'compare' ? 'comparison' : o.form === 'figures' ? 'stat' : 'exhibit', size: 22 })),
      h('strong', null, FORM[o.form] || o.form),
      h('p', null, (o.spec && (o.spec.title || o.spec.headline)) || ''),
      o.check && o.check.label ? h('p', { className: 'imp-gopt-check' }, h(Icon, { name: 'check', size: 13 }), o.check.label) : null,
      h(Button, { size: 'sm', variant: 'secondary', onClick: () => make(o) }, 'Make this one'))))
      : h('p', null, 'None of the numbers in that answer could be drawn and checked. Try a different answer.'),
    h('p', { className: 'imp-by' }, res.by || 'Written by your Hermes model'))
}

/* ---- Studio ---- */

function StudioPane({ st, fresh }) {
  const makes = useValue($makes)
  const flow = useValue($flow)
  const guide = useValue($guide)
  const kit = kitOf(st, useValue($kit))
  const sampleOpen = isSample(st)
  const KIND_RANK = { deck: 0, onepager: 1, visual: 2, audio: 3 }
  // In the sample the funder deck leads (it opens the canvas); your own notebook keeps newest first.
  const outs = (st.outputs || []).filter(o => !o.building)
    .map((o, i) => [o, i]).sort((a, b) => sampleOpen ? ((KIND_RANK[a[0].kind] ?? 9) - (KIND_RANK[b[0].kind] ?? 9)) || a[1] - b[1] : a[1] - b[1]).map(x => x[0])
  const running = Object.values(makes).filter(j => !(flow && flow.build && flow.build.id === j.id))
  const building = (st.outputs || []).filter(o => o.building && !Object.values(makes).some(j => j.result && j.result.output_id === o.id))
  const asks = (guide && guide.asks) || []
  const sample = isSample(st)
  return h('aside', { className: 'imp-pane imp-studio', 'aria-label': 'Studio' },
    h('div', { className: 'imp-pane-head' }, h('h2', { className: 'imp-h2' }, 'Studio'), h('span', { className: 'imp-grow' }), fresh ? null : h(BrandChip, { st, kit, compact: true })),
    !fresh && outs.length ? h(MakeRow, { st, kit }) : h(PreviewTiles, { st, kit, fresh }),
    !fresh && flow && asks.length ? h('section', { className: 'imp-st-sec' },
      h('h3', { className: 'imp-h3' }, 'Suggested'),
      h('ul', { className: 'imp-sugg' }, asks.map(a => {
        const k = KIND_OF[a.kind] || KIND_OF.deck
        return h('li', { key: a.id }, h('button', { type: 'button', className: 'imp-sugg-row', onClick: () => openFlow(k.id, { ask: a }) },
          h(Icon, { name: k.icon, size: 16 }), h('span', null, a.what), h('span', { className: 'imp-sugg-go' }, 'Make')))
      }))) : null,
    h(DesignJobCard, { st }),
    running.length || building.length ? h('section', { className: 'imp-st-sec' },
      h('h3', { className: 'imp-h3' }, 'Making'),
      running.map(j => h(StudioJob, { key: j.id, job: j, st })),
      building.map(o => h('div', { key: o.id, className: 'imp-sjob' }, h('span', { className: 'imp-spin' }), h('span', null, `Building ${o.title || (KIND_OF[o.kind] || KIND_OF.deck).noun}`)))) : null,
    !fresh ? h('section', { className: 'imp-st-sec' },
      h('h3', { className: 'imp-h3' }, 'Made'),
      outs.length ? h('ul', { className: 'imp-made' }, outs.map(o => h(MadeCard, { key: o.id, o, st, sample })))
        : h('p', { className: 'imp-st-empty' }, 'Nothing made yet.')) : null,
    !fresh ? h(NotesBox, { st }) : null)
}

/* Once anything is made, the four makes fold to one row of small buttons with the brand's colors on top, so the
   finished work below is the one gallery in the column. */
function MakeRow({ st, kit }) {
  const on = included(st)
  const reason = !on.length ? ((st.sources || []).length ? 'Tick a source first' : 'Add a source first') : ''
  const bar = (kit && kit.bar) || []
  const swatch = bar.length ? `linear-gradient(90deg,${bar.slice(0, 3).map((c, i, a) => `${c} ${Math.round(i / a.length * 100)}% ${Math.round((i + 1) / a.length * 100)}%`).join(',')})` : 'var(--hk-stroke)'
  return h('div', { className: 'imp-makerow', role: 'group', 'aria-label': 'Make' }, KINDS.map(k =>
    h('button', { key: k.id, type: 'button', className: 'imp-make', disabled: !!reason, title: reason || `Make a ${k.noun} in ${kit.name}`,
      style: { '--sw': swatch }, onClick: () => openFlow(k.id) },
    h(Icon, { name: k.icon, size: 16 }), h('span', null, k.id === 'audio' ? 'Audio' : k.label))))
}

/* The four things Letterpress makes, each a real picture in the active brand (state.previews). */
function PreviewTiles({ st, kit, fresh }) {
  const pv = st.previews || {}
  const on = included(st)
  const reason = !on.length ? ((st.sources || []).length ? 'Tick a source first' : (fresh ? '' : 'Add a source first')) : ''
  return h('div', { className: 'imp-tiles', role: 'group', 'aria-label': 'Make' }, KINDS.map(k => {
    const p = pv[k.id]
    const img = p && typeof p.img === 'string' && p.img.startsWith('data:image/') ? p.img : null
    return h('button', { key: k.id, type: 'button', className: cls('imp-tile', `is-${k.id}`), disabled: fresh && !isSample(st) ? false : !!reason,
      title: reason || `Make a ${k.noun} in ${kit.name}`,
      onClick: () => { if (fresh && !(st.sources || []).length) { addFiles(); return } openFlow(k.id) } },
    h('span', { className: 'imp-tile-pic' }, img ? h('img', { src: img, alt: `${k.label} in ${(p && p.kit_name) || kit.name}`, draggable: false }) : h(TileStandIn, { k, kit })),
    h('span', { className: 'imp-tile-label' }, h(Icon, { name: k.icon, size: 14 }), k.label))
  }))
}
// Until the backend sends previews: the brand's own colors as a quiet picture, never a blank.
function TileStandIn({ k, kit }) {
  const bar = (kit && kit.bar) || []
  return h('span', { className: 'imp-tile-stand', style: { '--a': bar[0] || 'var(--hk-sunken)', '--b': bar[1] || 'var(--hk-stroke)', '--c': bar[2] || 'var(--hk-stroke-strong)' } },
    h('span', { className: 'imp-ts-band' }), h('span', { className: 'imp-ts-line' }), h('span', { className: 'imp-ts-line is-short' }),
    k.id === 'deck' || k.id === 'visual' ? h('span', { className: 'imp-ts-bars' }, h('span', { style: { height: '45%' } }), h('span', { style: { height: '70%' } }), h('span', { style: { height: '100%' } })) : null)
}

// "Nov 9, 6:12 AM": a date and time, so two decks with the same cover read apart.
function madeWhen(at) {
  const d = at ? new Date(typeof at === 'number' && at < 1e12 ? at * 1000 : String(at).replace(' ', 'T')) : null
  if (!d || isNaN(d)) return ago(at)
  const date = d.toDateString() === new Date().toDateString() ? 'Today' : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  return `${date}, ${time}`
}

function MadeCard({ o, st, sample }) {
  const k = KIND_OF[o.kind] || KIND_OF.onepager
  const kit = kitOf(st, (o.kit_ids || [])[0])
  return h('li', null, h('button', { type: 'button', className: 'imp-mcard', onClick: () => openViewer(o.id) },
    h('span', { className: cls('imp-mcard-pic', `is-${o.kind}`) }, o.thumb && String(o.thumb).startsWith('data:image/') ? h('img', { src: o.thumb, alt: '', draggable: false }) : h(TileStandIn, { k, kit })),
    h('span', { className: 'imp-mcard-text' },
      h('strong', null, o.title || k.label),
      h('span', { className: 'imp-mcard-meta' }, h(Icon, { name: k.icon, size: 13 }), k.label),
      o.created_at ? h('span', { className: 'imp-mcard-meta is-when' }, madeWhen(o.created_at)) : null,
      o.status && o.status !== 'ready' && o.status !== 'done' ? h('span', { className: 'imp-mcard-meta' }, o.status === 'failed' ? 'Didn’t finish. Open it to retry.' : o.status) : null)))
}

function DesignJobCard({ st }) {
  const dj = useValue($designJob)
  if (!dj) return null
  const o = (st.outputs || []).find(x => x.id === dj.oid)
  return h('section', { className: 'imp-st-sec' },
    h('h3', { className: 'imp-h3' }, 'Designing'),
    h('div', { className: 'imp-sjob-card' },
      h('p', { className: 'imp-sjob-head' }, h('span', { className: 'imp-spin' }), h('strong', null, `Three designs of ${o && o.title ? o.title : 'your piece'}`)),
      h('p', { className: 'imp-sjob-step' }, dj.step || 'Starting'),
      h('div', { className: 'imp-row' }, h(Button, { size: 'sm', variant: 'secondary', onClick: () => openDesigns(dj.oid) }, 'Open'))))
}

function StudioJob({ job, st }) {
  const p = job.params || {}
  const k = KIND_OF[p.kind] || KIND_OF.deck
  const kit = kitOf(st, (p.kit_ids || [])[0])
  const ended = job.status === 'failed' || job.status === 'stopped'
  const dismiss = () => { const m = { ...$makes.get() }; delete m[job.id]; $makes.set(m) }
  return h('div', { className: cls('imp-sjob-card', ended && 'is-ended') },
    h('p', { className: 'imp-sjob-head' }, h(Icon, { name: k.icon, size: 15 }), h('strong', null, job.status === 'stopped' ? 'Stopped. Your outline is kept.' : job.status === 'failed' ? `The ${k.noun} didn’t finish` : `${k.label} in ${kit ? kit.name : 'your brand'}`)),
    h(JobSteps, { job, compact: true, onStop: () => stopJob(job) }),
    job.status === 'failed' && job.error ? h('p', { className: 'imp-sjob-err' }, job.error) : null,
    ended ? h('div', { className: 'imp-row' }, h(Button, { size: 'sm', onClick: () => retryMake(job) }, 'Retry'), h(Button, { size: 'sm', variant: 'secondary', onClick: dismiss }, 'Dismiss')) : null)
}

/* The brand: a chip with its colors, and a menu of brands with their bars. No native select. */
function BrandChip({ st, kit, compact, onPick }) {
  const [open, setOpen] = useState(false)
  const [more, setMore] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const off = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const esc = e => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', off); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc) }
  }, [open])
  if (!kit) return null
  const studio = st.kits.filter(k => k.tier === 'studio')
  const mine = st.kits.filter(k => !k.starter)
  const classic = st.kits.filter(k => k.tier === 'classic')
  const pick = id => { setOpen(false); if (onPick) onPick(id); else chooseKit(id) }
  const row = k => h('li', { key: k.id }, h('button', { type: 'button', className: cls('imp-kc-row', k.id === kit.id && 'is-on'), role: 'menuitemradio', 'aria-checked': k.id === kit.id, onClick: () => pick(k.id) },
    h('span', { className: 'imp-kitrow-bar', 'aria-hidden': 'true' }, (k.bar || []).slice(0, 6).map((c, i) => h('span', { key: i, style: { background: c } }))),
    h('span', { className: 'imp-kitrow-text' }, h('strong', null, k.name)),
    k.id === kit.id ? h(Icon, { name: 'check', size: 14 }) : null))
  const go = mode => { setOpen(false); $tab.set('kits'); $kitOpen.set(null); $kitMode.set(mode) }
  return h('div', { className: cls('imp-kc', compact && 'is-compact'), ref },
    h('button', { type: 'button', className: 'imp-kc-btn', 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': `Brand: ${kit.name}`, onClick: () => setOpen(!open) },
      h('span', { className: 'imp-kc-bar', 'aria-hidden': 'true' }, (kit.bar || []).slice(0, 4).map((c, i) => h('span', { key: i, style: { background: c } }))),
      h('span', { className: 'imp-kc-name' }, kit.name),
      h(Icon, { name: 'chevd', size: 14 })),
    open ? h('div', { className: 'imp-kc-menu', role: 'menu' },
      mine.length ? [h('p', { key: 'm', className: 'imp-kc-group' }, 'Your brands'), h('ul', { key: 'ml' }, mine.map(row))] : null,
      h('p', { className: 'imp-kc-group' }, 'Studio brands'), h('ul', null, studio.map(row)),
      classic.length ? h('button', { type: 'button', className: 'imp-linkish imp-kc-more', 'aria-expanded': more, onClick: () => setMore(!more) },
        h(Icon, { name: more ? 'chevd' : 'chevr', size: 14 }), `More brands (${classic.length})`) : null,
      more ? h('ul', null, classic.map(row)) : null,
      onPick ? null : h('div', { className: 'imp-kc-foot' },
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => go('import') }, 'Import a brand'),
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => go('library') }, 'All brands'))) : null)
}

// A graphic from a pinned answer: the canvas lane's three options when it has them, else the options here.
async function makeGraphicFrom(note, seed) {
  if (canvasLane.GraphicOptions && note) { $viewing.set(null); $flow.set(null); $graphicFor.set(note); return }
  openFlow('visual', { seed: seed || { text: String(note.text || '').replace(/\s*\[\d+\]/g, ''), chat_id: note.chat_id } })
}

function NotesBox({ st }) {
  const [text, setText] = useState('')
  const [adding, setAdding] = useState(false)
  const notes = st.notes || []
  const add = async () => {
    try { const r = await post('notes', { text }); $state.set({ ...$state.get(), notes: r.notes }); setText(''); setAdding(false) } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
  }
  const remove = async id => {
    try { const r = await del(`notes/${id}`); $state.set({ ...$state.get(), notes: r.notes }); if ($chats.get()) loadChats() } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
  }
  return h('section', { className: 'imp-st-sec imp-notes' },
    h('div', { className: 'imp-pane-head' }, h('h3', { className: 'imp-h3' }, 'Notes'), h('span', { className: 'imp-grow' }),
      h('button', { type: 'button', className: 'imp-linkish', onClick: () => setAdding(!adding) }, h(Icon, { name: 'plus', size: 14 }), 'Add a note')),
    adding ? h('div', { className: 'imp-mini-form' },
      h(Textarea, { value: text, rows: 3, placeholder: 'A point to build around', onChange: e => setText(e.target.value), 'aria-label': 'Note' }),
      h('div', { className: 'imp-row' }, h(Button, { size: 'sm', onClick: add, disabled: !text.trim() }, 'Keep the note'), h(Button, { size: 'sm', variant: 'secondary', onClick: () => setAdding(false) }, 'Cancel'))) : null,
    notes.length ? h('ul', { className: 'imp-note-list' }, notes.map(n => h('li', { key: n.id, className: 'imp-note' },
      h('p', null, String(n.text).replace(/\s*\[\d+\]/g, '')),
      h('div', { className: 'imp-note-foot' },
        n.chips && n.chips.length ? h('span', { className: 'imp-chips-inline' }, n.chips.slice(0, 4).map(ch => h(Cite, { key: ch.n, chip: ch, n: ch.n }))) : h('span', null, 'Your note'),
        h('span', { className: 'imp-grow' }),
        h('button', { type: 'button', className: 'imp-textbtn', onClick: () => makeGraphicFrom(n) }, h(Icon, { name: 'chart', size: 14 }), 'Make a graphic'),
        h('button', { type: 'button', className: 'imp-iconbtn', 'aria-label': 'Remove note', title: 'Remove', onClick: () => remove(n.id) }, h(Icon, { name: 'x', size: 14 }))))))
      : null)
}

/* ---- Viewer: the audio brief (decks, graphics and one-pagers open in the canvas) ---- */

function Viewer({ st, id }) {
  const out = useValue($output)
  const [swapJob, setSwapJob] = useState(null)
  const [details, setDetails] = useState(false)
  const [openCheck, setOpenCheck] = useState(null)
  const [playing, setPlaying] = useState(-1)
  useEffect(() => { if (!out || out.id !== id) openOutput(id) }, [id])
  const close = () => $viewing.set(null)
  useEffect(() => {
    const onKey = e => { if (e.key === 'Escape') close() }
    if (typeof window !== 'undefined') window.addEventListener('keydown', onKey)
    return () => { if (typeof window !== 'undefined') window.removeEventListener('keydown', onKey) }
  }, [])
  // The audio bar sticks just under the header, whatever height the header has (a long title or the brand chip wrap it).
  useEffect(() => {
    if (typeof document === 'undefined') return
    const head = document.querySelector('.imp-viewer-head')
    const box = head && head.closest('.imp-viewer')
    if (!head || !box) return
    const set = () => box.style.setProperty('--imp-head-h', `${Math.ceil(head.getBoundingClientRect().height)}px`)
    set()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(set)
    ro.observe(head)
    return () => ro.disconnect()
  })
  if (!out || out.id !== id) return h('div', { className: 'imp-viewer' }, h(Working, { step: 'Opening' }))
  const proof = out.proofs[0]
  const k = KIND_OF[out.kind] || KIND_OF.onepager
  const kit = kitOf(st, proof ? proof.kit_id : out.kit_ids[0])
  const swap = async kid => {
    try {
      const r = await post(`outputs/${out.id}/kit`, { kit_id: kid, slot: 0 })
      setSwapJob(r.job)
      pollJob(r.job, async () => { setSwapJob(null); await openOutput(out.id) }, j => setSwapJob(j), j => setSwapJob(j))
    } catch (e) { toast(`${errText(e)} Try again.`, 'bad') }
  }
  const working = swapJob && swapJob.status === 'running'
  const minutes = proof && proof.kind === 'audio' ? Math.max(1, Math.round(proof.minutes || 3)) : 0
  const meta = proof && proof.kind === 'deck' ? `${plural(proof.slide_count || (Array.isArray(proof.slides) ? proof.slides.length : proof.slides) || 0, 'slide')}` : proof && proof.kind === 'audio' ? `${proof.length_label || `About ${minutes} min`}, one narrator`
    : proof && proof.kind === 'visual' ? '4:5' : 'Letter page'
  const ready = proof && proof.status === 'ready'
  return h('div', { className: 'imp-viewer', role: 'dialog', 'aria-label': out.title || k.label },
    h('div', { className: 'imp-viewer-head' },
      h('button', { type: 'button', className: 'imp-linkish', onClick: close }, h(Icon, { name: 'back', size: 14 }), 'Back'),
      h('div', { className: 'imp-viewer-title' }, h('strong', null, out.title || k.label), h('span', null, `${k.label} · ${meta}`)),
      h(BrandChip, { st, kit, compact: true, onPick: kid => { if (kid !== kit.id) swap(kid) } }),
      DESIGN_KINDS.includes(out.kind) ? h(Button, { size: 'sm', variant: 'secondary', onClick: () => openDesigns(out.id) }, 'Designs') : null,
      ready ? h(ExportMenu, { out, proof }) : null,
      h(MoreMenu, { onDelete: async () => { try { await del(`outputs/${out.id}`); $output.set(null); close(); refresh() } catch (e) { toast(`${errText(e)} Try again.`, 'bad') } } })),
    ready ? h(Stamp, { proof, details, setDetails, fix: () => { setDetails(true); setOpenCheck('sources') } }) : null,
    ready && details ? h('div', { className: 'imp-details' }, h(Checks, { proof, out, openCheck, setOpenCheck })) : null,
    h('div', { className: cls('imp-viewer-body', proof && `is-${proof.kind}`) },
      working ? h(Working, { step: swapJob.step || 'Setting it in the new brand' }) : null,
      swapJob && swapJob.status === 'failed' ? h(Failed, { job: swapJob, onRetry: () => swap(kit.id) }) : null,
      ready && proof.kind === 'audio' ? h(AudioPlayer, { out, proof, onChapter: setPlaying }) : null,
      ready ? h(Proof, { proof, plain: true, playing }) : h(Working, { step: 'Setting it in the brand' })))
}

// One sentence for the checks; everything else folds into Details.
function Stamp({ proof, details, setDetails, fix }) {
  const tr = proof.traces || []
  const good = tr.filter(t => t.status === 'exact' || t.status === 'close' || t.status === 'computed').length
  const flagged = flaggedOf(proof)
  const bad = flagged.length
  // A flagged number is named, so the person knows which one to fix before Export opens.
  const text = !bad && proof.stamp ? proof.stamp : bad === 1 ? `“${flagged[0].value}” isn’t in your sources, so Export waits.` : bad ? `${plural(bad, 'number')} aren’t in your sources, so Export waits.`
    : good === 0 ? 'No numbers to check.' : good === 1 ? 'The 1 number matches your sources.' : `All ${good} numbers match your sources.`
  return h('div', { className: 'imp-stamp-row' },
    h('p', { className: 'imp-stamp', 'data-tone': bad ? 'bad' : 'good' }, h(Icon, { name: bad ? 'x' : 'check', size: 14 }), text),
    bad && fix ? h(Button, { size: 'sm', onClick: fix }, bad === 1 ? 'Fix it' : 'Fix them') : null,
    h('button', { type: 'button', className: 'imp-linkish', 'aria-expanded': details, onClick: () => setDetails(!details) }, h(Icon, { name: details ? 'chevd' : 'chevr', size: 14 }), 'Details'))
}

function MoreMenu({ onDelete }) {
  const [open, setOpen] = useState(false)
  return h('div', { className: 'imp-addwrap' },
    h('button', { type: 'button', className: 'imp-iconbtn', 'aria-haspopup': 'menu', 'aria-expanded': open, 'aria-label': 'More', title: 'More', onClick: () => setOpen(!open) }, h(Icon, { name: 'more', size: 16 })),
    open ? h('div', { className: 'imp-menu', role: 'menu' }, h(DeleteButton, { size: 'sm', label: 'Delete', onDelete: () => { setOpen(false); onDelete() } })) : null)
}

/* ------------------------------------------------------------------ kits tab -- */

const $kitOpen = atom(null) // {id} | {draft, palette, source} | {importDraft}
const $kitMode = atom('library') // library | site | guide | import

function KitsTab({ st }) {
  const mode = useValue($kitMode)
  const open = useValue($kitOpen)
  return h('div', { className: 'imp-kits' },
    h('div', { className: 'imp-kits-head' },
      h('h2', { className: 'imp-h2' }, 'Brands'),
      h('div', { className: 'imp-row' },
        h(Button, { size: 'sm', variant: mode === 'import' ? 'default' : 'secondary', onClick: () => { $kitOpen.set(null); $kitMode.set('import') } }, 'Import a brand'),
        h(Button, { size: 'sm', variant: mode === 'site' ? 'default' : 'secondary', onClick: () => { $kitOpen.set(null); $kitMode.set('site') } }, 'Build from a website'),
        h(Button, { size: 'sm', variant: mode === 'guide' ? 'default' : 'secondary', onClick: () => { $kitOpen.set(null); $kitMode.set('guide') } }, 'Help me build a brand'),
        h(Button, { size: 'sm', variant: 'secondary', onClick: () => { $kitMode.set('library'); $kitOpen.set({ draft: blankKit(), palette: null }) } }, 'New brand by hand'))),
    open && open.importDraft ? h(DraftBench, { st, open }) : open ? h(KitBench, { st, open })
      : mode === 'site' ? h(SiteReader, null) : mode === 'guide' ? h(Guide, { st }) : mode === 'import' ? h(ImportPanel, { st }) : h(KitGrid, { st }))
}

/* A kit judged by what it makes: its own title slide and exhibit (or every slide type and its graphic), composed by
   the backend on a built-in sample. Saved kits are cached; the bench asks again as the draft changes. */
const specimens = new Map()
function KitSpecimen({ kitId, kit, all, compact }) {
  const key = kitId ? `${kitId}:${all ? 1 : 0}` : null
  const [sp, setSp] = useState(key ? specimens.get(key) || null : null)
  const [err, setErr] = useState('')
  const draft = kit ? JSON.stringify(kit) : ''
  useEffect(() => {
    let live = true
    const run = () => post('kits/specimen', kitId ? { kit_id: kitId, all: !!all } : { kit, all: !!all })
      .then(v => { if (!live) return; if (key) specimens.set(key, v); setSp(v); setErr(''); loadFonts([{ fonts: v.fonts }]) }, e => { if (live) setErr(errText(e)) })
    if (key && specimens.has(key)) { loadFonts([{ fonts: specimens.get(key).fonts }]); return }
    const t = setTimeout(run, kitId ? 0 : 450)
    return () => { live = false; clearTimeout(t) }
  }, [key, draft])
  if (err) return h('p', { className: 'imp-hint' }, err)
  if (!sp) return h('div', { className: cls('imp-spec', compact && 'is-compact') }, h('div', { className: 'imp-spec-wait', 'aria-hidden': 'true' }))
  return h('div', { className: cls('imp-spec', compact && 'is-compact', all && 'is-all'), 'aria-hidden': compact ? 'true' : undefined },
    sp.slides.map((n, i) => h('div', { key: i, className: 'imp-spec-slide' }, renderNode(n, i, null))),
    sp.graphic ? h('div', { className: 'imp-spec-graphic' }, renderNode(sp.graphic, 'g', null)) : null)
}

function blankKit() {
  return { name: 'New brand', org: '', paper: '#ffffff', ink: '#1b1b1b', colors: [{ hex: '#0d5566', role: 'head', name: '' }],
    type: { heading: { family: 'Inter', stack: 'Inter, Helvetica, Arial, sans-serif', weight: 700 }, body: { family: 'Inter', stack: 'Inter, Helvetica, Arial, sans-serif', weight: 400 }, scale: 1.25 },
    layout: 'banner', deck: 'exhibit', density: 'medium', voice: { notes: '', delivery: '', never: [], pairs: [] }, rules: { sources: true, page_numbers: true, date: true, required: [] } }
}

/* The library leads with the person's own kits. Starters are a short shelf of proofs (crop marks, the kit's
   own fonts on the person's own headline, the color bar), with the full list one click away. */
const $allStarters = atom(false)

function KitProof({ k, sample }) {
  return h('button', { type: 'button', className: 'imp-kp', onClick: () => $kitOpen.set({ id: k.id }), 'aria-label': `${k.name}, ${k.layout_label}` },
    h('div', { className: 'imp-kp-crop', 'aria-hidden': 'true' },
      ['tl', 'tr', 'bl', 'br'].map(c => h('span', { key: c, className: `imp-mark imp-mark-${c}` })),
      h('div', { className: 'imp-kp-page', style: { background: k.paper, color: k.ink } },
        k.band ? h('div', { className: 'imp-kp-band', style: { background: k.band } }) : null,
        h('p', { className: 'imp-kp-head', style: { color: k.head, fontFamily: k.head_css, fontStyle: k.head_style, fontWeight: k.head_weight,
          textTransform: k.head_case === 'upper' ? 'uppercase' : 'none' } }, sample),
        h('span', { className: 'imp-kp-rule', style: { background: k.accent } }),
        h('p', { className: 'imp-kp-body', style: { fontFamily: k.body_css } }, k.subject || 'Your sources, set in this brand.'))),
    h(ColorBar, { bar: k.bar }),
    h('span', { className: 'imp-kp-name' }, h('strong', null, k.name),
      h('span', null, k.heading_family === k.body_family ? k.heading_family : `${k.heading_family} and ${k.body_family}`)))
}

function KitGrid({ st }) {
  const mine = st.kits.filter(k => !k.starter)
  const studio = st.kits.filter(k => k.tier === 'studio')
  const classic = st.kits.filter(k => k.tier === 'classic')
  const all = useValue($allStarters)
  const current = useValue($kit)
  const out = useValue($output)
  useEffect(() => { loadFonts([{ fonts: st.kits.flatMap(k => k.font_keys || []) }]) }, [st.kits.length])
  const sample = (out && out.title) || 'The warming center kept 412 people out of the cold'
  const use = k => { chooseKit(k.id); toast(`The Studio now uses ${k.name}.`) }
  return h('div', { className: 'imp-kitgrid-wrap' },
    h('section', { className: 'imp-lib' },
      h('h3', { className: 'imp-h3' }, 'Your brands'),
      mine.length ? h('div', { className: 'imp-kitgrid is-mine' }, mine.map(k => h(KitProof, { key: k.id, k, sample })))
        : h('p', { className: 'imp-lib-empty' }, 'No brands of your own yet. Import your brand guide, a Canva file or a design file, read a website, or build one with help.')),
    h('section', { className: 'imp-lib' },
      h('h3', { className: 'imp-h3' }, 'Studio brands'),
      h('div', { className: 'imp-studio-kits' }, studio.map(k => h('article', { key: k.id, className: 'imp-sk' },
        h('button', { type: 'button', className: 'imp-sk-spec', onClick: () => $kitOpen.set({ id: k.id }), 'aria-label': `Open ${k.name}` },
          h(KitSpecimen, { kitId: k.id, compact: true })),
        h('div', { className: 'imp-sk-text' },
          h('div', { className: 'imp-row' }, h('strong', null, k.name), h('span', { className: 'imp-grow' }),
            k.id === current ? h('span', { className: 'imp-sk-on' }, h(Codicon, { name: 'check', size: '14px' }), 'In the Studio')
              : h(Button, { size: 'sm', variant: 'secondary', onClick: () => use(k) }, 'Use in the Studio')),
          h('p', null, k.method),
          h('p', { className: 'imp-sk-type' }, k.heading_family === k.body_family ? k.heading_family : `${k.heading_family} and ${k.body_family}`)))))),
    h('section', { className: 'imp-lib' },
      h('button', { type: 'button', className: 'imp-linkish', 'aria-expanded': all, onClick: () => $allStarters.set(!all) },
        h(Codicon, { name: all ? 'chevron-down' : 'chevron-right', size: '14px' }), `Earlier starters (${classic.length})`),
      all ? h('ul', { className: 'imp-kitlist' }, classic.map(k => h('li', { key: k.id },
        h('button', { type: 'button', className: 'imp-kitrow', onClick: () => $kitOpen.set({ id: k.id }) },
          h('span', { className: 'imp-kitrow-bar', 'aria-hidden': 'true' }, k.bar.slice(0, 6).map((c, i) => h('span', { key: i, style: { background: c } }))),
          h('span', { className: 'imp-kitrow-text' },
            h('strong', null, k.name),
            h('span', null, `${k.layout_label}. ${k.heading_family === k.body_family ? k.heading_family : `${k.heading_family} and ${k.body_family}`}`)))))) : null))
}

function SiteReader() {
  const [url, setUrl] = useState('')
  const [job, setJob] = useState(null)
  const [err, setErr] = useState('')
  const go = async () => {
    setErr('')
    try {
      const r = await post('kits/from-site', { url })
      setJob(r.job)
      pollJob(r.job, j => { setJob(null); $kitOpen.set({ importDraft: j.result.draft, request: null }) },
        j => { setJob(null); setErr(j.error) }, setJob)
    } catch (e) { setErr(errText(e)) }
  }
  return h('div', { className: 'imp-panel' },
    h('h3', { className: 'imp-h3' }, 'Build from a website'),
    h('p', null, 'Colors and fonts come from the site’s own stylesheets. Nothing is saved until you press Save the brand.'),
    h('div', { className: 'imp-row' },
      h(Input, { value: url, placeholder: 'https://', onChange: e => setUrl(e.target.value), onKeyDown: e => { if (e.key === 'Enter') go() }, 'aria-label': 'Website' }),
      h(Button, { onClick: go, loading: !!job }, 'Read the site')),
    job ? h(Working, { step: job.step || 'Reading the site' }) : null,
    err ? h('div', { className: 'imp-failed', role: 'alert' }, h('p', null, err),
      h(Button, { size: 'sm', variant: 'secondary', onClick: () => { $kitMode.set('library'); $kitOpen.set({ draft: blankKit() }) } }, 'Make a brand by hand')) : null)
}

function Guide({ st }) {
  const [fixed, setFixed] = useState({ name: '', org: '', colors: '', fonts: '', notes: '' })
  const [subject, setSubject] = useState({ reader: '', job: '', work: '', only: '', sample: '' })
  const [refs, setRefs] = useState([])
  const [refUrl, setRefUrl] = useState('')
  const [job, setJob] = useState(null)
  const [result, setResult] = useState(null)
  const [err, setErr] = useState('')
  const field = (obj, set, key, label, ph, area) => h('label', { className: 'imp-field' }, h('span', null, label),
    area ? h(Textarea, { rows: 3, value: obj[key], placeholder: ph, onChange: e => set({ ...obj, [key]: e.target.value }) })
      : h(Input, { value: obj[key], placeholder: ph, onChange: e => set({ ...obj, [key]: e.target.value }) }))
  const go = async () => {
    setErr('')
    setResult(null)
    const body = {
      fixed: { ...fixed, colors: fixed.colors.split(/[\s,]+/).filter(Boolean), fonts: fixed.fonts.split(',').map(s => s.trim()).filter(Boolean) },
      subject, refs,
    }
    try {
      const r = await post('kits/guide', body)
      setJob(r.job)
      pollJob(r.job, j => { setJob(null); setResult(j.result) }, j => { setJob(null); setErr(j.error) }, setJob)
    } catch (e) { setErr(errText(e)) }
  }
  const use = async d => {
    try { const v = await post('kits', { kit: d.kit }); await refresh(); adoptKit(v.kit); $kitOpen.set({ id: v.kit.id }) } catch (e) { toast(errText(e), 'bad') }
  }
  const [logoJob, setLogoJob] = useState(null)
  const addLogoRef = () => pickFile('.png,.jpg,.jpeg,.webp', async f => {
    setErr('')
    try {
      const r = await upload('kits/import/file', f)
      if (!r.job) return
      setLogoJob(r.job)
      pollJob(r.job, j => { setLogoJob(null); setRefs(cur => [...cur, { draft_id: j.result.draft.draft_id }].slice(0, 3)); toast('Your model read the image. It joins the references.') },
        j => { setLogoJob(null); setErr(j.error) }, setLogoJob)
    } catch (e) { setErr(errText(e)) }
  })
  return h('div', { className: 'imp-guide' },
    h('div', { className: 'imp-guide-steps' },
      h('section', { className: 'imp-step' }, h('h3', { className: 'imp-h3' }, '1. What can’t change'),
        field(fixed, setFixed, 'name', 'Name', 'Eastside Tenants Union'),
        field(fixed, setFixed, 'colors', 'Exact colors', '#7a1f2b #f4efe6'),
        field(fixed, setFixed, 'fonts', 'Fonts you must use', 'Leave empty if none'),
        field(fixed, setFixed, 'notes', 'Anything else fixed', '', true)),
      h('section', { className: 'imp-step' }, h('h3', { className: 'imp-h3' }, '2. The subject'),
        field(subject, setSubject, 'reader', 'Who reads it', 'Renters in our buildings, many reading on a phone'),
        field(subject, setSubject, 'job', 'What they need to do', 'Know their rights before a hearing'),
        field(subject, setSubject, 'work', 'What the organization does', '', true),
        field(subject, setSubject, 'only', 'One thing only it has', '')),
      h('section', { className: 'imp-step' }, h('h3', { className: 'imp-h3' }, '3. References'),
        h('p', null, 'Pick up to three.'),
        h('div', { className: 'imp-refpick' }, st.kits.filter(k => k.starter).map(k => h('button', { key: k.id, type: 'button',
          className: cls('imp-refchip', refs.some(r => r.kit_id === k.id) && 'is-on'),
          onClick: () => setRefs(refs.some(r => r.kit_id === k.id) ? refs.filter(r => r.kit_id !== k.id) : refs.length < 3 ? [...refs, { kit_id: k.id }] : refs) }, k.name))),
        h('div', { className: 'imp-row' }, h(Input, { value: refUrl, placeholder: 'A website you admire', onChange: e => setRefUrl(e.target.value) }),
          h(Button, { size: 'sm', variant: 'secondary', disabled: !refUrl || refs.length >= 3, onClick: () => { setRefs([...refs, { url: refUrl }]); setRefUrl('') } }, 'Add')),
        h(Button, { size: 'sm', variant: 'secondary', disabled: refs.length >= 3 || !!logoJob, loading: !!logoJob, onClick: addLogoRef }, 'Add your logo or brand sheet'),
        refs.filter(r => r.url || r.draft_id).map(r => h('p', { key: r.url || r.draft_id, className: 'imp-src-meta' }, r.url || 'Your logo or brand sheet, read by your model'))),
      h('div', { className: 'imp-row' }, h(Button, { onClick: go, loading: !!job }, '4. Propose three brands'))),
    job ? h(Working, { step: job.step || 'Drafting three brands' }) : null,
    err ? h('div', { className: 'imp-failed', role: 'alert' }, h('p', null, err), h(Button, { size: 'sm', variant: 'secondary', onClick: go }, 'Retry')) : null,
    result ? h('div', { className: 'imp-proposals' }, result.proposals.map((d, i) => h('article', { key: i, className: 'imp-proposal' },
      h('div', { className: 'imp-kitcard-sheet', style: { background: d.kit.paper, color: d.kit.ink } },
        d.palette.band ? h('div', { className: 'imp-spec-band', style: { background: d.palette.band } }) : null,
        h('p', { className: 'imp-kitcard-name', style: { color: d.palette.head } }, d.kit.name),
        h('p', { className: 'imp-kitcard-type' }, `${d.kit.type.heading.family} and ${d.kit.type.body.family}, ${d.look.layout}`)),
      h(ColorBar, { bar: d.palette.bar }),
      h('p', null, d.why),
      d.borrowed ? h('p', { className: 'imp-src-meta' }, `Borrowed: ${d.borrowed}`) : null,
      d.fresh ? h('p', { className: 'imp-src-meta' }, d.fresh) : null,
      h(Button, { size: 'sm', onClick: () => use(d) }, 'Use this brand')))) : null)
}

const BRIEF_FIELDS = [['layout', 'Layout and density'], ['type', 'Type scale and hierarchy'], ['imagery', 'Image treatment'], ['shapes', 'Shapes, rules and borders'],
  ['color', 'How colour is used'], ['components', 'Recurring components'], ['tone', 'Tone of the copy'], ['avoid', 'What to avoid']]

/* The look of a site, written down: the Studio's designs follow it. Editable like everything else on the bench. */
function StyleBriefSection({ kit, set, view, setView, setKit }) {
  const [url, setUrl] = useState('')
  const [job, setJob] = useState(null)
  const sb = kit.style_brief
  const saved = view && view.kit && !view.kit.starter
  const capture = async () => {
    try {
      const r = await post(`kits/${view.kit.id}/style-brief`, { url })
      setJob(r.job)
      pollJob(r.job, j => { setJob(null); const v = j.result && j.result.kit; if (v) { setView(v); setKit(v.kit) } toast('Style brief captured from the site.') },
        j => { setJob(null); toast(j.error || 'The style brief did not finish.', 'bad') }, j => setJob(j))
    } catch (e) { toast(errText(e), 'bad') }
  }
  return h('section', { className: 'imp-bench-sec', 'aria-label': 'Style brief' },
    h('h3', { className: 'imp-h3' }, 'Style brief'),
    sb ? h('p', { className: 'imp-origin' }, `Written from what ${sb.source || 'the site'} looks like${sb.at ? `, ${sb.at}` : ''}. The designs in the Studio follow it. Edit anything.`)
      : h('p', { className: 'imp-origin' }, 'How this brand looks beyond its colors and fonts: layout, shapes, imagery, tone. Capture it from a site, or write it.'),
    BRIEF_FIELDS.map(([k, l]) => h('label', { key: k, className: 'imp-field' }, h('span', null, l),
      h(Textarea, { rows: 3, value: (sb && sb[k]) || '', onChange: e => set({ style_brief: { ...(sb || {}), [k]: e.target.value } }) }))),
    saved ? h('div', { className: 'imp-row' },
      h(Input, { value: url, placeholder: 'https://yourbrand.com', 'aria-label': 'Site to capture the look from', onChange: e => setUrl(e.target.value) }),
      h(Button, { size: 'sm', variant: 'secondary', disabled: !url.trim() || !!job, onClick: capture }, sb ? 'Capture again' : 'Capture from a site')) : null,
    job ? h('p', { className: 'imp-hint', role: 'status' }, job.step || 'Working') : null)
}

function KitBench({ st, open }) {
  const [view, setView] = useState(null)
  const [kit, setKit] = useState(open.draft || null)
  const [pal, setPal] = useState(open.palette || null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    if (open.id) rest(`kits/${open.id}`).then(v => { setView(v); setKit(v.kit); setPal(v.palette) }, e => setErr(errText(e)))
  }, [open.id])
  useEffect(() => {
    if (!kit) return
    const t = setTimeout(() => { post('kits/preview', { kit }).then(v => { setPal(v.palette); setErr('') }, e => setErr(errText(e))) }, 350)
    return () => clearTimeout(t)
  }, [JSON.stringify(kit && [kit.paper, kit.ink, kit.colors, kit.type, kit.layout])])
  if (!kit) return err ? h('p', { className: 'imp-error' }, err) : h(Working, { step: 'Opening the brand' })
  const starter = view && view.kit.starter
  const set = patch => setKit({ ...kit, ...patch })
  const save = async () => {
    setSaving(true)
    try {
      const v = open.id ? await post(`kits/${open.id}`, { kit }) : await post('kits', { kit })
      await refresh()
      if (!open.id || starter) adoptKit(v.kit, starter ? `Saved your copy: ${v.kit.name}` : null)
      else toast(`Saved ${v.kit.name}`)
      $kitOpen.set({ id: v.kit.id })
    } catch (e) { setErr(errText(e)) }
    setSaving(false)
  }
  const roles = ['head', 'accent', 'accent2', 'band', 'fill', 'highlight', 'rule']
  const sw = (pal && pal.swatches) || []
  const fontsList = (st.fonts || []).map(f => f.family).concat(['Times New Roman', 'Helvetica', 'Courier'])
  const face = role => h('div', { className: 'imp-face' },
    h('span', { className: 'imp-label' }, role === 'heading' ? 'Headings' : 'Body'),
    h('select', { className: 'imp-select', value: fontsList.includes(kit.type[role].family) ? kit.type[role].family : '__other', 'aria-label': `${role} font`,
      onChange: e => e.target.value !== '__other' && set({ type: { ...kit.type, [role]: { ...kit.type[role], family: e.target.value, stack: `${e.target.value}, ${kit.type[role].stack.split(',').slice(1).join(',').trim() || 'sans-serif'}` } } }) },
      fontsList.map(f => h('option', { key: f, value: f }, f)), h('option', { value: '__other' }, kit.type[role].family + (view && view.faces && view.faces[role] && view.faces[role].source === 'upload' ? ' (added font)' : view && view.faces && view.faces[role] && view.faces[role].substituted ? ' (not on this computer)' : ''))),
    h(Input, { value: kit.type[role].stack, 'aria-label': `${role} font stack`, onChange: e => set({ type: { ...kit.type, [role]: { ...kit.type[role], stack: e.target.value, family: e.target.value.split(',')[0].replace(/["']/g, '').trim() } } }) }))
  return h('div', { className: 'imp-bench' },
    h('div', { className: 'imp-bench-head' },
      h('button', { type: 'button', className: 'imp-linkish', onClick: () => $kitOpen.set(null) }, h(Codicon, { name: 'arrow-left', size: '14px' }), 'All brands'),
      h(Input, { className: 'imp-kitname', value: kit.name, 'aria-label': 'Brand name', onChange: e => set({ name: e.target.value }) }),
      h('div', { className: 'imp-row' },
        h(Button, { onClick: save, loading: saving }, starter ? 'Save as my copy' : 'Save the brand'),
        view && !starter ? h(DeleteButton, { onDelete: async () => { try { await del(`kits/${view.kit.id}`); await refresh(); $kitOpen.set(null) } catch (e) { toast(errText(e), 'bad') } } }) : null)),
    open.note || (kit.origin_note) ? h('p', { className: 'imp-origin' }, open.note || kit.origin_note) : null,
    err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
    h('section', { className: 'imp-bench-preview', 'aria-label': 'What this brand makes' },
      h('div', { className: 'imp-row' }, h('h3', { className: 'imp-h3' }, 'What it makes'), h('span', { className: 'imp-hint' }, 'Its slides and graphic on a sample, updated as you edit'),
        h('span', { className: 'imp-grow' }),
        view ? h(Button, { size: 'sm', variant: 'secondary', onClick: () => { chooseKit(view.kit.id); toast(`The Studio now uses ${view.kit.name}.`) } }, 'Use in the Studio') : null),
      h(KitSpecimen, { kit, all: true })),
    h('div', { className: 'imp-bench-grid' },
      h('section', { className: 'imp-bench-sec' },
        h('h3', { className: 'imp-h3' }, 'Colors'),
        h('div', { className: 'imp-swatch-row' },
          ['paper', 'ink'].map(k => h('label', { key: k, className: 'imp-swatch' },
            h('span', { className: 'imp-chip', style: { background: kit[k] } }),
            h('span', { className: 'imp-sw-text' }, h('span', null, k === 'paper' ? 'Paper' : 'Ink'), h(Input, { className: 'imp-hex', value: kit[k], onChange: e => set({ [k]: e.target.value }), 'aria-label': k }))))),
        kit.colors.map((c, i) => {
          const s = sw[i]
          return h('div', { key: i, className: 'imp-swatch' },
            h('span', { className: 'imp-chip', style: { background: c.hex } }),
            h('span', { className: 'imp-sw-text' },
              h(Input, { className: 'imp-hex', value: c.hex, 'aria-label': 'Color', onChange: e => { const cs = [...kit.colors]; cs[i] = { ...c, hex: e.target.value }; set({ colors: cs }) } }),
              h('select', { className: 'imp-select', value: c.role, 'aria-label': 'Role', onChange: e => { const cs = [...kit.colors]; cs[i] = { ...c, role: e.target.value }; set({ colors: cs }) } }, roles.map(r => h('option', { key: r, value: r }, r))),
              s ? h('span', { className: 'imp-ratio', 'data-use': s.usage }, `${s.ratio.toFixed(1)}:1 ${s.label}`) : null),
            h('button', { type: 'button', className: 'imp-x', 'aria-label': 'Remove color', onClick: () => set({ colors: kit.colors.filter((_, j) => j !== i) }) }, h(Codicon, { name: 'close', size: '14px' })))
        }),
        kit.colors.length < 8 ? h(Button, { size: 'sm', variant: 'secondary', onClick: () => set({ colors: [...kit.colors, { hex: '#888888', role: 'rule', name: '' }] }) }, 'Add a color') : null,
        h(ColorBar, { bar: pal ? pal.bar : [] })),
      h('section', { className: 'imp-bench-sec' },
        h('h3', { className: 'imp-h3' }, 'Type and page'),
        face('heading'), face('body'),
        h('div', { className: 'imp-row' },
          h('label', { className: 'imp-field' }, h('span', null, 'Layout'), h('select', { className: 'imp-select', value: kit.layout, onChange: e => set({ layout: e.target.value }) },
            Object.entries(st.layouts).map(([id, l]) => h('option', { key: id, value: id }, l)))),
          h('label', { className: 'imp-field' }, h('span', null, 'Density'), h('select', { className: 'imp-select', value: kit.density, onChange: e => set({ density: e.target.value }) },
            ['airy', 'medium', 'dense'].map(d => h('option', { key: d, value: d }, d))))),
        h('label', { className: 'imp-field' }, h('span', null, 'Slides and graphics'), h('select', { className: 'imp-select', value: kit.deck || (view && view.deck) || '', onChange: e => set({ deck: e.target.value }) },
          h('option', { value: '' }, 'Chosen from the page layout'),
          Object.entries(st.deck_systems || {}).map(([id, l]) => h('option', { key: id, value: id }, l)))),
        h('label', { className: 'imp-field' }, h('span', null, 'Organization name on the page'), h(Input, { value: kit.org || '', onChange: e => set({ org: e.target.value }) })),
        view && !starter ? h('div', { className: 'imp-row' },
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => pickFile('.svg,.png,.jpg,.jpeg', async f => { try { const v = await upload(`kits/${view.kit.id}/logo`, f); setView(v); toast('Logo added') } catch (e) { toast(errText(e), 'bad') } }) }, view.kit.logo ? 'Replace logo' : 'Add your logo'),
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => pickFile('.ttf,.otf', async f => { try { const v = await upload(`kits/${view.kit.id}/fonts`, f); setView(v); setKit(v.kit); toast(`Added ${v.kit.fonts.slice(-1)[0].family}`) } catch (e) { toast(errText(e), 'bad') } }) }, 'Add a font file')) : null,
        view && view.logo ? h('img', { className: 'imp-logo-preview', src: view.logo, alt: 'Logo' }) : null,
        view && view.logo && !starter ? h('div', { className: 'imp-row' },
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => pickFile('.svg,.png,.jpg,.jpeg', async f => { try { const v = await upload(`kits/${view.kit.id}/logo-reversed`, f); setView(v); toast('Reversed logo added') } catch (e) { toast(errText(e), 'bad') } }) },
            view.logo_alt ? 'Replace reversed logo' : 'Add a reversed logo (for dark bands)'),
          view.logo_alt ? h('img', { className: 'imp-logo-preview is-dark', src: view.logo_alt, alt: 'Reversed logo' }) : null) : null,
        view && view.logo_check ? h('p', { className: 'imp-origin', role: 'status' }, view.logo_check) : null,
        view ? h('p', { className: 'imp-origin' }, view.colophon) : null),
      h('section', { className: 'imp-bench-sec' },
        h('h3', { className: 'imp-h3' }, 'Voice'),
        kit.voice.draft ? h('p', { className: 'imp-origin' }, 'Drafted from the site. Read it and make it yours.') : null,
        h('label', { className: 'imp-field' }, h('span', null, 'How it writes'), h(Textarea, { rows: 4, value: kit.voice.notes, onChange: e => set({ voice: { ...kit.voice, notes: e.target.value, draft: false } }) })),
        h('label', { className: 'imp-field' }, h('span', null, 'How the narrator sounds'), h(Input, { value: kit.voice.delivery, onChange: e => set({ voice: { ...kit.voice, delivery: e.target.value } }) })),
        h('label', { className: 'imp-field' }, h('span', null, 'Never say'), h(Input, { value: (kit.voice.never || []).join(', '), onChange: e => set({ voice: { ...kit.voice, never: e.target.value.split(',').map(s => s.trim()).filter(Boolean) } }) })),
        h('div', { className: 'imp-field' }, h('span', null, 'Say this, not that'),
          (kit.voice.pairs || []).length ? h('div', { className: 'imp-pair imp-pair-head' }, h('span', null, 'Say'), h('span', null, 'Not')) : null,
          (kit.voice.pairs || []).map((p, i) => h('div', { key: i, className: 'imp-pair' },
            h(Input, { value: p.say, 'aria-label': 'Say', onChange: e => { const ps = [...kit.voice.pairs]; ps[i] = { ...p, say: e.target.value }; set({ voice: { ...kit.voice, pairs: ps } }) } }),
            h(Input, { value: p.not, 'aria-label': 'Not', onChange: e => { const ps = [...kit.voice.pairs]; ps[i] = { ...p, not: e.target.value }; set({ voice: { ...kit.voice, pairs: ps } }) } }))),
          h(Button, { size: 'sm', variant: 'secondary', onClick: () => set({ voice: { ...kit.voice, pairs: [...(kit.voice.pairs || []), { say: '', not: '' }] } }) }, 'Add a pair'))),
      h(StyleBriefSection, { kit, set, view, setView, setKit }),
      h('section', { className: 'imp-bench-sec' },
        h('h3', { className: 'imp-h3' }, 'Every page'),
        [['sources', 'Source list'], ['page_numbers', 'Page numbers'], ['date', 'Date']].map(([k, l]) => h('label', { key: k, className: 'imp-check' },
          h('input', { type: 'checkbox', checked: !!kit.rules[k], onChange: e => set({ rules: { ...kit.rules, [k]: e.target.checked } }) }), l)),
        h('label', { className: 'imp-field' }, h('span', null, 'Required lines, one per line'),
          h(Textarea, { rows: 3, value: (kit.rules.required || []).join('\n'), onChange: e => set({ rules: { ...kit.rules, required: e.target.value.split('\n').filter(s => s.trim()) } }) })),
        pal ? h('ul', { className: 'imp-pairs' }, pal.pairs.map((p, i) => h('li', { key: i, 'data-tone': p.passes ? 'good' : 'bad' },
          h('span', { className: 'imp-chip imp-chip-pair', style: { background: p.bg, color: p.fg } }, 'Aa'), `${p.what}: ${p.ratio.toFixed(1)}:1`))) : null)))
}

/* ------------------------------------------------------------------ import -- */

const ROUTES = [
  { id: 'pdf', label: 'Brand guide PDF', note: 'Your guide’s color codes, the words beside them, and its fonts' },
  { id: 'paste', label: 'Paste color codes', note: 'Copy your guide’s color page, names and notes included' },
  { id: 'css', label: 'CSS file or paste', note: ':root variables, Tailwind @theme, any tokens.css' },
  { id: 'open-design', label: 'Open Design package', note: 'A package folder with manifest.json and tokens.css' },
  { id: 'claude-design', label: 'Claude Design system', note: 'The .zip Claude Design exports, or its saved folder' },
  { id: 'pptx', label: 'PowerPoint or Canva', note: 'In Canva: Share, Download, PowerPoint. Any .pptx works' },
  { id: 'dtcg', label: 'Design tokens file', note: 'The DTCG JSON that Figma, Tokens Studio and Penpot export' },
  { id: 'image', label: 'Logo or brand sheet', note: 'A PNG or JPG read by your own model, or a PDF guide' },
  { id: 'keynote', label: 'Keynote theme (Mac only)', note: 'In Keynote: File, Export To, PowerPoint' },
]

async function readFolder(kind) {
  const files = api && api.files
  if (!files || !files.requestFolder) return { error: kind === 'claude-design' ? 'Folder access needs a newer Hermes. Pick the .zip instead.' : 'Folder access needs a newer Hermes. Pick the package’s tokens.css file instead.', fallback: true }
  const picked = await files.requestFolder()
  if (!picked.ok) return { error: picked.message || 'Letterpress could not open that folder.' }
  if (!picked.folder) return { cancelled: true }
  const id = picked.folder.id
  const out = {}
  const text = async path => { const r = await files.readText(id, path); if (r.ok) out[path] = r.text }
  const data = async path => { const r = await files.readDataUrl(id, path); if (r.ok) out[path] = r.url }
  // Names match without case (a Linux folder may hold Tokens.css or Fonts/), and every file is read by the
  // path the host listed, so Mac, Windows and Linux folders read the same way.
  const list = async path => { const r = await files.list(id, path); return r.ok ? r.entries : [] }
  const find = (entries, name, dir) => entries.find(e => !!e.isDirectory === !!dir && e.name.toLowerCase() === name)
  try {
    let root = await list('')
    if (kind === 'open-design') {
      for (const n of ['manifest.json', 'tokens.css', 'design.md', 'design-tokens.json']) { const e = find(root, n); if (e) await text(e.path) }
    } else {
      const proj = find(root, 'project', true)
      if (proj) root = await list(proj.path)
      for (const n of ['design-system.json', 'tokens.json', 'tokens.css']) { const e = find(root, n); if (e) await text(e.path) }
      const fonts = find(root, 'fonts', true)
      if (fonts) for (const e of (await list(fonts.path)).filter(e => !e.isDirectory && /\.(ttf|otf|woff2?)$/i.test(e.name)).slice(0, 8)) await data(e.path)
      const assets = find(root, 'assets', true)
      if (assets) for (const d of (await list(assets.path)).filter(e => e.isDirectory && /logo/i.test(e.name)).slice(0, 3)) {
        for (const e of (await list(d.path)).filter(e => !e.isDirectory && /\.(svg|png)$/i.test(e.name)).slice(0, 4)) await data(e.path)
      }
    }
  } finally {
    try { await files.release(id) } catch (e) { /* the grant can be revoked in Settings too */ }
  }
  return { files: out }
}

function ImportPanel({ st }) {
  const [route, setRoute] = useState('pdf')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(null)
  const [err, setErr] = useState('')
  const r = ROUTES.find(x => x.id === route)
  const open = (draft, request) => { $kitOpen.set({ importDraft: draft, request }) }
  const send = async request => {
    setErr('')
    setBusy('Reading it')
    try { const v = await post('kits/import', request); open(v.draft, request) } catch (e) { setErr(errText(e)) }
    setBusy(null)
  }
  const pickText = (accept, kind) => pickFile(accept, async f => {
    if (f.size > 5 * 1024 * 1024) { setErr('That file is over 5 MB. Pick the file that holds your colors and type.'); return }
    send({ kind, text: await f.text(), filename: f.name })
  })
  const pickUpload = accept => pickFile(accept, async f => {
    setErr('')
    setBusy(route === 'image' ? 'Your model is reading the image' : `Reading ${f.name}`)
    try {
      const res = await upload('kits/import/file', f)
      if (res.draft) { setBusy(null); open(res.draft, null); return }
      pollJob(res.job, j => { setBusy(null); open(j.result.draft, null) }, j => { setBusy(null); setErr(j.error) }, j => setBusy(j.step || 'Reading it'))
    } catch (e) { setBusy(null); setErr(errText(e)) }
  })
  const folder = async () => {
    setErr('')
    const got = await readFolder(route)
    if (got.cancelled) return
    if (got.error) { setErr(got.error); return }
    send({ kind: route, files: got.files })
  }
  return h('div', { className: 'imp-import' },
    h('div', { className: 'imp-routes', role: 'tablist', 'aria-label': 'Import from' },
      ROUTES.map(x => h('button', { key: x.id, type: 'button', role: 'tab', 'aria-selected': route === x.id, className: cls('imp-route', route === x.id && 'is-on'),
        onClick: () => { setRoute(x.id); setErr('') } }, h('strong', null, x.label), h('span', null, x.note)))),
    h('section', { className: 'imp-step imp-import-body' },
      h('h3', { className: 'imp-h3' }, r.label),
      route === 'paste' || route === 'css' ? h('div', { className: 'imp-mini-form' },
        h(Textarea, { rows: route === 'css' ? 8 : 4, value: text, maxLength: route === 'paste' ? 10000 : undefined, 'aria-label': r.label,
          placeholder: route === 'paste' ? 'Harbor Teal  #0E5E6F  Primary. Headlines, the logo, bands.\nLighthouse Red  #C0392B  Calls to action only.\nPaper  #FAF7F2  Backgrounds.' : ':root {\n  --bg: #fbf7f0;\n  --fg: #1f1a16;\n  --accent: #9a5a2f;\n}',
          onChange: e => setText(e.target.value) }),
        h('div', { className: 'imp-row' },
          h(Button, { onClick: () => send({ kind: route, text }), disabled: !text.trim() || !!busy, loading: !!busy }, 'Read it'),
          route === 'css' ? h(Button, { variant: 'secondary', onClick: () => pickText('.css', 'css') }, 'Pick a .css file') : null)) : null,
      route === 'claude-design' ? h('div', { className: 'imp-row' },
        h(Button, { onClick: () => pickUpload('.zip'), loading: !!busy }, 'Pick the .zip'),
        h(Button, { variant: 'secondary', onClick: folder }, 'Pick the folder')) : null,
      route === 'open-design' ? h('div', { className: 'imp-row' },
        h(Button, { onClick: folder, loading: !!busy }, 'Pick the folder'),
        h(Button, { variant: 'secondary', onClick: () => pickText('.css', 'css') }, 'Pick its tokens.css instead')) : null,
      route === 'pdf' ? h('div', { className: 'imp-mini-form' },
        h(Button, { onClick: () => pickUpload('.pdf'), loading: !!busy }, 'Pick your brand guide PDF'),
        h('p', { className: 'imp-src-meta' }, 'Letterpress reads the color codes and the words beside them (“Primary”, “Calls to action only”) and the fonts it names. A scanned guide has no text to read: copy its color page into Paste color codes instead.')) : null,
      route === 'pptx' ? h(Button, { onClick: () => pickUpload('.pptx'), loading: !!busy }, 'Pick a .pptx file') : null,
      route === 'keynote' ? h('div', { className: 'imp-mini-form' },
        h('p', null, 'Keynote runs only on a Mac. Open a slide in your theme, choose File, Export To, PowerPoint, then pick the file it saves. On Windows or Linux, use PowerPoint or Canva, or a token file.'),
        h('div', { className: 'imp-row' }, h(Button, { onClick: () => pickUpload('.pptx'), loading: !!busy }, 'Pick the exported .pptx'))) : null,
      route === 'dtcg' ? h(Button, { onClick: () => pickText('.json,.tokens', 'dtcg'), loading: !!busy }, 'Pick a token file') : null,
      route === 'image' ? h('div', { className: 'imp-mini-form' },
        h(Button, { onClick: () => pickUpload('.png,.jpg,.jpeg,.webp,.pdf'), loading: !!busy }, 'Pick an image or PDF'),
        h('p', { className: 'imp-src-meta' }, 'The image goes to your own Hermes model, which needs to see images.')) : null,
      busy ? h(Working, { step: busy }) : null,
      err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null))
}

function DraftBench({ st, open }) {
  const [v, setV] = useState(open.importDraft)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [showSkipped, setShowSkipped] = useState(false)
  const [name, setName] = useState(open.importDraft.kit.name || '')
  useEffect(() => { if (v && v.proof) loadFonts([v.proof]) }, [v && v.proof && v.proof.fonts.join()])
  const patch = async p => {
    setErr('')
    try { setV(await post(`kits/import/${v.draft_id}`, { patch: p })) } catch (e) { setErr(errText(e)) }
  }
  useEffect(() => { const t = setTimeout(() => { if (name !== v.kit.name) patch({ name }) }, 350); return () => clearTimeout(t) }, [name])
  const mode = async m => {
    if (!open.request) return
    try { const n = await post('kits/import', { ...open.request, mode: m }); del(`kits/import/${v.draft_id}`).catch(() => {}); setV(n.draft); setName(n.draft.kit.name || name) } catch (e) { setErr(errText(e)) }
  }
  const save = async () => {
    setSaving(true)
    try { const k = await post(`kits/import/${v.draft_id}/save`); await refresh(); adoptKit(k.kit); $kitOpen.set({ id: k.kit.id }) } catch (e) { setErr(errText(e)) }
    setSaving(false)
  }
  const discard = async () => { try { await del(`kits/import/${v.draft_id}`) } catch (e) { /* already gone */ } $kitOpen.set(null) }
  const roles = ['head', 'accent', 'accent2', 'band', 'fill', 'highlight', 'rule']
  const sw = v.palette.swatches || []
  return h('div', { className: 'imp-bench imp-draft' },
    h('div', { className: 'imp-bench-head' },
      h('button', { type: 'button', className: 'imp-linkish', onClick: discard }, h(Codicon, { name: 'arrow-left', size: '14px' }), 'Discard draft'),
      h(Input, { className: 'imp-kitname', value: name, placeholder: 'Name this brand', 'aria-label': 'Brand name', onChange: e => setName(e.target.value) }),
      h('span', { className: 'imp-origin' }, v.origin_note)),
    v.brand_line ? h('div', { className: 'imp-notice', 'data-tone': 'warn' }, h('p', null, v.brand_line)) : null,
    err ? h('p', { className: 'imp-error', role: 'alert' }, err) : null,
    h('div', { className: 'imp-draft-grid' },
      h('div', { className: 'imp-draft-side' },
        v.modes.length ? h('label', { className: 'imp-field' }, h('span', null, 'Which mode'),
          h('select', { className: 'imp-select', value: v.mode, disabled: !open.request, onChange: e => mode(e.target.value) }, v.modes.map(m => h('option', { key: m, value: m }, m)))) : null,
        h('section', { className: 'imp-bench-sec' },
          h('h3', { className: 'imp-h3' }, 'Colors'),
          h('div', { className: 'imp-swatch-row' },
            ['paper', 'ink'].map(k => h('label', { key: k, className: 'imp-swatch' },
              h('span', { className: 'imp-chip', style: { background: v.kit[k] } }),
              h('span', { className: 'imp-sw-text' }, h('span', null, k === 'paper' ? 'Paper' : 'Ink'),
                h(Input, { className: 'imp-hex', defaultValue: v.kit[k], 'aria-label': k, onBlur: e => e.target.value !== v.kit[k] && patch({ [k]: e.target.value }) }))))),
          v.kit.colors.map((c, i) => {
            const s = sw[i]
            return h('div', { key: `${i}-${c.hex}`, className: 'imp-swatch' },
              h('span', { className: 'imp-chip', style: { background: c.hex } }),
              h('span', { className: 'imp-sw-text' },
                h('span', { className: 'imp-hex' }, c.hex),
                h('select', { className: 'imp-select', value: c.role, 'aria-label': 'Role', onChange: e => { const cs = [...v.kit.colors]; cs[i] = { ...c, role: e.target.value }; patch({ colors: cs }) } },
                  roles.map(r => h('option', { key: r, value: r }, r))),
                s ? h('span', { className: 'imp-ratio', 'data-use': s.usage }, `${s.ratio.toFixed(1)}:1 ${s.label}`) : null),
              h('button', { type: 'button', className: 'imp-x', 'aria-label': 'Remove color', onClick: () => v.kit.colors.length > 1 && patch({ colors: v.kit.colors.filter((_, j) => j !== i) }) }, h(Codicon, { name: 'close', size: '14px' })))
          })),
        h('section', { className: 'imp-bench-sec' },
          h('h3', { className: 'imp-h3' }, 'Type and page'),
          ['heading', 'body'].map(role => h('p', { key: role, className: 'imp-face-line' },
            h('strong', null, role === 'heading' ? 'Headings ' : 'Body '),
            v.faces[role] && v.faces[role].substituted ? `${v.faces[role].used} in place of ${v.faces[role].wanted}` : (v.faces[role] ? v.faces[role].used : v.kit.type[role].family))),
          h('label', { className: 'imp-field' }, h('span', null, 'Layout'),
            h('select', { className: 'imp-select', value: v.kit.layout, onChange: e => patch({ layout: e.target.value }) },
              Object.entries(st.layouts).map(([id, l]) => h('option', { key: id, value: id }, l)))),
          v.fonts.length ? h('p', { className: 'imp-src-meta' }, `Font files: ${v.fonts.map(f => f.family).join(', ')}`) : null),
        v.logos.length ? h('section', { className: 'imp-bench-sec' },
          h('h3', { className: 'imp-h3' }, 'Logo'),
          h('div', { className: 'imp-logos' }, v.logos.map(lg => h('button', { key: lg.i, type: 'button', className: cls('imp-logo-pick', lg.chosen && 'is-on'), 'aria-pressed': lg.chosen,
            onClick: () => patch({ logo: lg.chosen ? null : lg.i }) }, h('img', { src: lg.url, alt: lg.name }), h('span', null, lg.chosen ? 'Using this logo' : 'Use this logo'))))) : null,
        v.warnings.length ? h('ul', { className: 'imp-detail' }, v.warnings.map((w, i) => h('li', { key: i }, w))) : null,
        v.skipped.length ? h('div', null,
          h('button', { type: 'button', className: 'imp-linkish', 'aria-expanded': showSkipped, onClick: () => setShowSkipped(!showSkipped) }, `Skipped ${v.skipped.length}`),
          showSkipped ? h('ul', { className: 'imp-detail' }, v.skipped.map((x, i) => h('li', { key: i, className: 'imp-skip-row' }, `${x.what}: ${x.why}`,
            /^#[0-9a-f]{6}$/i.test(x.what) && !v.kit.colors.some(c => c.hex === x.what.toLowerCase()) && v.kit.colors.length < 8
              ? h(Button, { size: 'sm', variant: 'secondary', onClick: () => patch({ colors: [...v.kit.colors, { hex: x.what, role: 'accent2', name: '' }] }) }, 'Add it back') : null))) : null) : null),
      h('div', { className: 'imp-draft-main' },
        v.proof ? h(Proof, { proof: { ...v.proof, kind: 'onepager' } }) : null,
        h('ul', { className: 'imp-pills' }, v.checks.map(c => h('li', { key: c.id },
          h('span', { className: 'imp-pill', 'data-tone': c.tone },
            h(Codicon, { name: c.tone === 'good' ? 'pass' : c.tone === 'bad' ? 'error' : 'warning', size: '14px' }), c.label)))),
        h('div', { className: 'imp-save' },
          h('p', null, v.responsibility),
          h('div', { className: 'imp-row' },
            h(Button, { onClick: save, loading: saving, disabled: !v.can_save }, 'Save the brand'),
            h(Button, { variant: 'secondary', onClick: discard }, 'Discard'))))))
}

/* ------------------------------------------------------------------ sources tab -- */

function StorageTab({ st }) {
  const [confirm, setConfirm] = useState('')
  const [cap, setCap] = useState(st.usage.cap ? String(st.usage.cap) : '')
  const removeSource = async id => { try { await del(`sources/${id}`); refresh() } catch (e) { toast(errText(e), 'bad') } }
  const removeOutput = async id => { try { await del(`outputs/${id}`); if ($output.get() && $output.get().id === id) $output.set(null); refresh() } catch (e) { toast(errText(e), 'bad') } }
  const missing = Object.values(st.deps || {}).filter(d => !d.ok)
  return h('div', { className: 'imp-store' },
    missing.length ? h('div', { className: 'imp-notice', 'data-tone': 'warn' }, h('p', null, `Not installed: ${missing.map(d => d.label).join(', ')}. Reinstall Letterpress to add the libraries it lists.`)) : null,
    h('section', null, h('h2', { className: 'imp-h2' }, 'Sources'),
      st.sources.length ? h('table', { className: 'imp-tbl' }, h('tbody', null, st.sources.map(s => h('tr', { key: s.id },
        h('td', null, s.title), h('td', null, s.kind), h('td', null, plural(s.units, s.unit_label.replace(/s$/, ''))), h('td', null, bytes(s.bytes || s.chars)),
        h('td', null, h(DeleteButton, { size: 'sm', onDelete: () => removeSource(s.id) })))))) : h('p', null, 'No sources yet.')),
    h('section', null, h('h2', { className: 'imp-h2' }, 'Outputs'),
      st.outputs.length ? h('table', { className: 'imp-tbl' }, h('tbody', null, st.outputs.map(o => h('tr', { key: o.id },
        h('td', null, h('button', { type: 'button', className: 'imp-linkish', onClick: () => { $tab.set('notebook'); openViewer(o.id) } }, o.title || 'Untitled')),
        h('td', null, h(DeleteButton, { size: 'sm', onDelete: () => removeOutput(o.id) })))))) : h('p', null, 'Nothing made yet.')),
    h('details', { className: 'imp-fold' }, h('summary', null, h('span', { className: 'imp-h2' }, 'Model use'), h('span', { className: 'imp-fold-hint' }, 'Details')),
      h('p', null, `${(st.usage.today || 0).toLocaleString()} tokens today on your own Hermes model.`),
      h('div', { className: 'imp-row' }, h(Input, { className: 'imp-short', value: cap, placeholder: 'Daily token limit (off)', onChange: e => setCap(e.target.value.replace(/[^0-9]/g, '')), 'aria-label': 'Daily token limit' }),
        h(Button, { size: 'sm', variant: 'secondary', onClick: async () => { try { await post('settings', { daily_token_cap: cap || null }); toast(cap ? 'Daily limit set' : 'Daily limit off'); refresh() } catch (e) { toast(errText(e), 'bad') } } }, 'Save'))),
    h('section', null, h('h2', { className: 'imp-h2' }, 'Storage'),
      h('p', null, `${bytes(st.storage.bytes)} in Letterpress's folder: ${plural(st.storage.sources, 'source')}, ${plural(st.storage.kits, 'brand')}, ${plural(st.storage.outputs, 'output')}.`),
      h('div', { className: 'imp-row' }, h(Input, { className: 'imp-short', value: confirm, placeholder: 'Type: forget everything', onChange: e => setConfirm(e.target.value), 'aria-label': 'Confirm' }),
        h(Button, { size: 'sm', variant: 'secondary', disabled: confirm !== 'forget everything', onClick: async () => { try { $state.set(await post('forget', { confirm })); $output.set(null); setConfirm(''); toast('Everything is forgotten') } catch (e) { toast(errText(e), 'bad') } } }, 'Forget everything'))))
}

/* ------------------------------------------------------------------ styles -- */

// Plugin chrome only. Host theme variables (through the kit's --hk-* tokens), corners at the host's
// --radius-md (2px in the app), no text under 12px, and no dimmed body text: secondary lines are smaller,
// never grayer. Kit colors appear only in proofs, swatches and specimens.
const CSS = `
.imp{--imp-solid:linear-gradient(var(--hk-surface),var(--hk-surface)),linear-gradient(var(--hk-bg),var(--hk-bg)),Canvas;height:100%;display:grid;grid-template-rows:auto 1fr;min-height:0;container-type:size;background:var(--hk-bg);font-size:13px;--imp-r:var(--radius-md,2px);--imp-ink2:color-mix(in srgb,var(--hk-ink) 76%,var(--hk-bg))}
.imp *{box-sizing:border-box}
.imp [data-slot=button]{border-radius:var(--imp-r)}
.imp [data-slot=button][data-size=sm],.imp-top [aria-pressed]{font-size:12px}
.imp-center{display:grid;place-items:center;height:100%;padding:24px}
.imp[aria-busy="true"]{cursor:progress}
.imp-h2{font-size:15px;font-weight:600;margin:0}
.imp-h3{font-size:13px;font-weight:600;margin:0}
.imp p{margin:0}
.imp-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.imp-grow{flex:1}
.imp-label,.imp-field>span{font-size:12px;font-weight:600}
.imp-field{display:grid;grid-template-columns:minmax(0,1fr);gap:4px;min-width:0}
.imp-check{display:inline-flex;gap:6px;align-items:center;font-size:12px}
.imp-error{color:var(--hk-bad);font-size:12px}
.imp-top{display:flex;align-items:center;gap:14px;padding:10px 16px;border-bottom:1px solid var(--hk-stroke);flex-wrap:wrap}
.imp-srcs{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.imp-src{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:start;padding:6px;border-radius:var(--imp-r);cursor:pointer}
.imp-src:hover{background:var(--hk-hover)}
.imp-src input{margin-top:2px}
.imp-src-text{display:grid;min-width:0}
.imp-src-title{font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.imp-src-meta{font-size:12px}
.imp-add{display:flex;gap:6px;flex-wrap:wrap}
.imp-mini-form{display:grid;gap:6px}
.imp-follow{display:grid;gap:4px}
.imp-follow-btn,.imp-refchip{all:unset;cursor:pointer;font-size:12px;padding:4px 8px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);line-height:1.4}
.imp-follow-btn:hover,.imp-refchip:hover{background:var(--hk-hover)}
.imp-refchip.is-on{border-color:var(--hk-accent);background:var(--hk-active)}
.imp-linkish{all:unset;cursor:pointer;font-size:12px;font-weight:600;color:var(--hk-info);display:inline-flex;gap:4px;align-items:center}
.imp-linkish:hover{text-decoration:underline}
.imp-linkish:focus-visible{outline:2px solid var(--hk-accent)}
.imp-select{font:inherit;font-size:12px;color:var(--hk-ink);background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r);padding:4px 6px;max-width:100%}
.imp-select:focus-visible{outline:2px solid var(--hk-accent)}
.imp-sheet-wrap{display:grid;gap:8px}
.imp-proof{margin:0;display:grid;gap:6px;animation:imp-in 160ms ease-out;position:relative}
.imp .ip-num{cursor:help;text-decoration-line:underline;text-decoration-style:dotted;text-decoration-thickness:1px;text-underline-offset:.22em;
  text-decoration-color:color-mix(in srgb,currentColor 55%,transparent);border-radius:1px;transition:text-decoration-color 100ms}
.imp .ip-num:hover,.imp .ip-num.is-open{text-decoration-style:solid;text-decoration-thickness:2px;text-decoration-color:var(--hk-accent)}
.imp .ip-num:focus{outline:none}
.imp .ip-num:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp .ip-num.is-missing{text-decoration-style:wavy;text-decoration-thickness:1.5px;text-decoration-color:var(--hk-bad-fill)}
.imp .ip-num.is-kept{text-decoration-color:var(--hk-warn-fill)}
.imp .ip-title .ip-ref-num,.imp .ip-s-title .ip-ref-num,.imp .ip-s-value .ip-ref-num,.imp .ip-stat-value .ip-ref-num{font-size:max(12px,.36em);margin-left:.08em}
.imp-trace{position:absolute;z-index:6;display:grid;gap:8px;padding:10px 12px;background:var(--imp-solid);color:var(--hk-ink);border:1px solid var(--hk-stroke-strong,var(--hk-stroke));
  border-radius:var(--imp-r);box-shadow:0 12px 32px -8px rgba(0,0,0,.32),0 2px 6px rgba(0,0,0,.12);font-size:13px;line-height:1.45;pointer-events:none;animation:imp-rise 100ms ease-out;text-align:left}
.imp-trace::before{content:"";position:absolute;top:-6px;left:calc(var(--caret) - 5px);width:10px;height:10px;background:var(--hk-surface);
  border-left:1px solid var(--hk-stroke-strong,var(--hk-stroke));border-top:1px solid var(--hk-stroke-strong,var(--hk-stroke));transform:rotate(45deg)}
.imp-trace.is-above::before{top:auto;bottom:-6px;transform:rotate(225deg)}
.imp-trace-head{display:flex;gap:6px;align-items:center;font-size:12px;font-weight:600;color:var(--hk-tone)}
.imp-trace-head .codicon{color:var(--hk-tone)}
.imp-trace-line{padding-left:10px;border-left:2px solid var(--hk-accent);overflow-wrap:anywhere}
.imp-trace[data-tone=bad] .imp-trace-line{border-left-color:var(--hk-stroke-strong,var(--hk-stroke))}
.imp-trace-line mark{background:color-mix(in srgb,var(--hk-accent) 18%,transparent);color:inherit;padding:0 2px;border-radius:1px;font-weight:600}
.imp-trace-closest{font-weight:600}
.imp-trace-src{display:flex;gap:7px;align-items:center;font-size:12px}
.imp-trace-n{display:inline-grid;place-items:center;flex:none;min-width:18px;height:18px;padding:0 3px;border:1px solid var(--hk-stroke-strong,var(--hk-stroke));font-size:12px;font-weight:600;font-variant-numeric:tabular-nums}
.imp-crop{position:relative;padding:14px}
.imp-mark{position:absolute;width:10px;height:10px;border-color:var(--hk-ink);border-style:solid;border-width:0}
.imp-mark-tl{top:0;left:0;border-right-width:1px;border-bottom-width:1px}
.imp-mark-tr{top:0;right:0;border-left-width:1px;border-bottom-width:1px}
.imp-mark-bl{bottom:0;left:0;border-right-width:1px;border-top-width:1px}
.imp-mark-br{bottom:0;right:0;border-left-width:1px;border-top-width:1px}
.imp-sheet{box-shadow:0 1px 2px rgba(0,0,0,.18),0 0 0 1px var(--hk-stroke);min-height:200px}
.imp-sheet .ip-page{--ip-base:13px;min-height:calc(1.294 * 100cqw)}
.imp-proof .imp-sheet:not(.is-deck){aspect-ratio:8.5/11;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin}
.imp-sheet{container-type:inline-size}
.imp-bar{display:flex;height:8px;box-shadow:0 0 0 1px var(--hk-stroke)}
.imp-bar span{flex:1}
.imp-colophon{font-size:12.5px;line-height:1.45}
.imp-checks{display:grid;gap:8px}
.imp-pills{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.imp-pill{all:unset;cursor:pointer;display:inline-flex;gap:6px;align-items:center;font-size:12.5px;line-height:1.35;padding:4px 9px;border-radius:var(--imp-r);
  border:1px solid color-mix(in srgb,var(--hk-tone-fill) 55%,var(--hk-stroke));background:color-mix(in srgb,var(--hk-tone-fill) 12%,transparent)}
.imp-pill .codicon{color:var(--hk-tone)}
.imp-pill[data-tone=bad]{font-weight:600}
.imp-pill:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-detail{margin:0;padding-left:18px;font-size:12.5px;display:grid;gap:2px}
.imp-ground{display:grid;gap:10px}
.imp-gitem{display:grid;gap:6px;padding:10px 12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-gitem[data-status=missing]{border-color:var(--hk-bad-fill)}
.imp-gwhat{font-size:13px}
.imp-gctx{font-size:12.5px}
.imp-passage{margin:0;padding:6px 10px;border-left:2px solid var(--hk-stroke-strong);display:grid;gap:3px;font-size:12.5px}
.imp-passage-src{font-weight:600}
.imp-gfixed{display:grid;gap:6px;font-size:12.5px}
.imp-gfixed-toggle{all:unset;cursor:pointer;display:inline-flex;gap:4px;align-items:center;font-size:12.5px;color:var(--hk-ink)}
.imp-gfixed-toggle:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp-gfixed-list{margin:0;padding-left:18px;display:grid;gap:4px}
.imp-gedit{display:grid;gap:6px}
.imp-export{position:relative}
.imp-export .imp-off{background:color-mix(in srgb,var(--hk-accent) 50%,var(--hk-bg));border-color:transparent;cursor:default}
.imp-why{position:absolute;top:calc(100% + 6px);right:0;z-index:31;width:240px;padding:8px 10px;font-size:12px;line-height:1.4;font-weight:400;white-space:normal;background:var(--hk-surface);color:var(--hk-ink);border:1px solid var(--hk-stroke);border-radius:var(--imp-r);box-shadow:0 8px 20px rgba(0,0,0,.22);opacity:0;pointer-events:none;transition:opacity 120ms ease-out}
.imp-export:hover .imp-why,.imp-export:focus-within .imp-why{opacity:1}
.imp-menu{position:absolute;right:0;top:calc(100% + 4px);z-index:12;display:grid;min-width:200px;padding:4px;background:var(--imp-solid);border:1px solid var(--hk-stroke);border-radius:var(--imp-r);box-shadow:0 8px 24px rgba(0,0,0,.18)}
.imp-menu-item{all:unset;cursor:pointer;padding:7px 10px;font-size:13px;border-radius:var(--imp-r)}
.imp-menu-item:hover,.imp-menu-item:focus-visible{background:var(--hk-hover)}
.imp-working{display:flex;gap:8px;align-items:center;font-size:13px;padding:10px 12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-wait{display:flex;gap:8px;align-items:center}
.imp-spin{width:13px;height:13px;border-radius:50%;border:2px solid color-mix(in srgb,currentColor 30%,transparent);border-top-color:var(--hk-accent);animation:imp-spin .7s linear infinite;flex:none}
.imp-failed{display:grid;gap:8px;padding:12px;border:1px solid var(--hk-bad-fill);background:color-mix(in srgb,var(--hk-bad-fill) 8%,var(--hk-surface));border-radius:var(--imp-r)}
.imp-notice{display:grid;gap:8px;padding:12px;border:1px solid var(--hk-tone-fill);border-radius:var(--imp-r);background:var(--hk-surface);max-width:560px}
.imp-toast{position:fixed;right:18px;bottom:18px;max-width:380px;padding:10px 12px;background:var(--imp-solid);border:1px solid var(--hk-stroke);border-radius:var(--imp-r);box-shadow:0 8px 24px rgba(0,0,0,.25);font-size:13px;z-index:20}
.imp-toast[data-tone=bad]{border-color:var(--hk-bad-fill)}
.imp-kits,.imp-store{overflow:auto;min-height:0;padding:16px 20px 40px;display:grid;grid-template-columns:minmax(0,1fr);gap:18px;align-content:start}
.imp-kits-head{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.imp-kitgrid-wrap{display:grid;grid-template-columns:minmax(0,1fr);gap:26px}
.imp-lib{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;justify-items:start}
.imp-lib>*{justify-self:stretch}
.imp-lib>.imp-linkish{justify-self:start}
.imp-lib-empty{font-size:13px;max-width:62ch}
.imp-kitgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(176px,1fr));gap:22px 20px;max-width:1180px}
.imp-kp{all:unset;cursor:pointer;display:grid;grid-template-rows:1fr auto auto;gap:7px;min-width:0}
.imp-kp:focus-visible{outline:2px solid var(--hk-accent);outline-offset:4px}
.imp-kp-crop{position:relative;padding:10px;display:grid}
.imp-kp-crop .imp-mark{width:8px;height:8px}
.imp-kp-page{min-height:232px;display:grid;align-content:start;gap:10px;padding:0 0 14px;
  box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke)),0 1px 2px rgba(16,24,40,.08),0 10px 22px -12px rgba(16,24,40,.35);transition:box-shadow 120ms,transform 120ms}
.imp-kp:hover .imp-kp-page{box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke)),0 2px 4px rgba(16,24,40,.1),0 16px 30px -12px rgba(16,24,40,.45);transform:translateY(-1px)}
.imp-kp-band{height:30px;margin-bottom:-2px}
.imp-kp-head{font-size:17px;line-height:1.12;padding:12px 13px 0;letter-spacing:-.01em;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;overflow:hidden}
.imp-kp-rule{display:block;width:28px;height:3px;margin:0 13px}
.imp-kp-body{font-size:12px;line-height:1.45;padding:0 13px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;overflow:hidden}
.imp-kp .imp-bar{height:7px;margin:0 10px}
.imp-kp-name{display:grid;gap:1px;padding:0 10px;font-size:12px;line-height:1.35}
.imp-kp-name strong{font-size:13px;font-weight:600}
.imp-kp-name>*{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.imp-kitlist{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:2px 16px;max-width:1180px}
.imp-kitrow{all:unset;cursor:pointer;display:grid;grid-template-columns:auto 1fr;gap:12px;align-items:center;padding:7px 8px;border-radius:var(--imp-r);width:100%;box-sizing:border-box}
.imp-kitrow:hover{background:var(--hk-hover)}
.imp-kitrow:focus-visible{outline:2px solid var(--hk-accent)}
.imp-kitrow-bar{display:flex;width:56px;height:16px;box-shadow:0 0 0 1px var(--hk-stroke)}
.imp-kitrow-bar span{flex:1}
.imp-kitrow-text{display:grid;min-width:0;font-size:12px;line-height:1.35}
.imp-kitrow-text strong{font-size:13px;font-weight:600}
@media (prefers-reduced-motion:reduce){.imp-kp-page{transition:none}.imp-kp:hover .imp-kp-page{transform:none}}
.imp-kitcard-sheet{min-height:150px;box-shadow:0 0 0 1px var(--hk-stroke);display:grid;align-content:start;overflow:hidden}
.imp-kitcard-sheet .imp-spec-band{height:40px}
.imp-kitcard-name{font-size:18px;font-weight:600;padding:12px 14px 2px;line-height:1.2}
.imp-kitcard-type{font-size:12px;padding:0 14px}
.imp-panel,.imp-guide{display:grid;gap:12px;max-width:820px}
.imp-guide-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;align-items:start}
.imp-step{display:grid;gap:8px;padding:12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-refpick{display:flex;flex-wrap:wrap;gap:6px}
.imp-proposals{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px}
.imp-proposal{display:grid;gap:8px;align-content:start}
.imp-bench{display:grid;gap:12px}
.imp-bench-head{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.imp-kitname{max-width:320px;font-weight:600}
.imp-origin{font-size:12.5px}
.imp-bench-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;align-items:start}
.imp-bench-sec{display:grid;gap:10px;padding:14px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-swatch-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.imp-swatch{display:grid;grid-template-columns:44px 1fr auto;gap:10px;align-items:center}
.imp-swatch-row .imp-swatch{grid-template-columns:44px 1fr}
.imp-chip{width:44px;height:44px;box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke));display:inline-grid;place-items:center;font-weight:600}
.imp-chip-pair{width:32px;height:24px;font-size:13px}
.imp-sw-text{display:grid;gap:4px;min-width:0}
.imp-hex{font-family:var(--hk-mono);font-size:12px;max-width:120px}
.imp-ratio{font-size:12px;font-variant-numeric:tabular-nums}
.imp-ratio[data-use=text]{color:var(--hk-good)}
.imp-x{all:unset;cursor:pointer;padding:4px;border-radius:var(--imp-r)}
.imp-x:hover{background:var(--hk-hover)}
.imp-face{display:grid;gap:4px}
.imp-pair{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.imp-pair-head span{font-size:12px;font-weight:600}
.imp-pairs{list-style:none;margin:0;padding:0;display:grid;gap:6px;font-size:12.5px}
.imp-pairs li{display:flex;gap:8px;align-items:center}
.imp-logo-preview{max-width:160px;max-height:60px;object-fit:contain;background:#fff;padding:4px;box-shadow:0 0 0 1px var(--hk-stroke)}
.imp-logo-preview.is-dark{background:#1f2328}
.imp-tbl{border-collapse:collapse;width:100%;max-width:900px}
.imp-tbl td{padding:7px 8px;border-bottom:1px solid var(--hk-stroke);font-size:13px}
.imp-store section,.imp-fold{display:grid;gap:8px}
.imp-fold>summary{cursor:pointer;display:flex;gap:10px;align-items:baseline}
.imp-fold-hint{font-size:12px}
.imp-short{width:280px;max-width:100%}
.imp-sheet.is-deck{box-shadow:none;background:transparent}
.imp-audio{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-audio audio{flex:1;min-width:220px;height:36px}
.imp-import{display:grid;gap:14px;grid-template-columns:minmax(220px,300px) minmax(0,1fr);align-items:start;max-width:1040px}
.imp-routes{display:grid;gap:4px}
.imp-route{all:unset;cursor:pointer;display:grid;gap:2px;padding:8px 10px;border-radius:var(--imp-r);border:1px solid transparent}
.imp-route strong{font-size:13px;font-weight:600}
.imp-route span{font-size:12px;line-height:1.4}
.imp-route:hover{background:var(--hk-hover)}
.imp-route.is-on{background:var(--hk-active);border-color:var(--hk-stroke);box-shadow:inset 2px 0 0 var(--hk-accent)}
.imp-route:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-import-body{align-content:start}
.imp-draft-grid{display:grid;grid-template-columns:minmax(260px,340px) minmax(0,1fr);gap:20px;align-items:start}
.imp-draft-side{display:grid;gap:12px;align-content:start}
.imp-draft-main{display:grid;gap:10px;max-width:640px}
.imp-face-line{font-size:13px}
.imp-logos{display:flex;gap:8px;flex-wrap:wrap}
.imp-logo-pick{all:unset;cursor:pointer;display:grid;gap:4px;justify-items:center;padding:6px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);font-size:12px}
.imp-logo-pick img{max-width:120px;max-height:48px;object-fit:contain;background:#fff}
.imp-logo-pick.is-on{border-color:var(--hk-accent);box-shadow:inset 0 0 0 1px var(--hk-accent)}
.imp-logo-pick:focus-visible{outline:2px solid var(--hk-accent)}
.imp-save{display:grid;gap:8px;padding:12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
.imp-save p{font-size:13px}
@media (max-width:900px){.imp-import,.imp-draft-grid{grid-template-columns:1fr}}
@keyframes imp-spin{to{transform:rotate(360deg)}}
@keyframes imp-in{from{opacity:.4}to{opacity:1}}
@keyframes imp-rise{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){.imp-proof,.imp-trace{animation:none}.imp-spin{animation-duration:2s}.imp .ip-num{transition:none}}

.imp-studio-kits{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:22px;max-width:1320px}
.imp-sk{display:grid;gap:10px;align-content:start}
.imp-sk-spec{all:unset;cursor:pointer;display:block}
.imp-sk-spec:focus-visible{outline:2px solid var(--hk-accent);outline-offset:3px}
.imp-sk-text{display:grid;gap:4px;font-size:12.5px;line-height:1.45}
.imp-sk-text strong{font-size:14px}
.imp-sk-type{font-size:12px}
.imp-sk-on{display:inline-flex;gap:4px;align-items:center;font-size:12px;font-weight:600}
.imp-spec{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
.imp-spec.is-all{grid-template-columns:repeat(3,minmax(0,1fr));align-items:start}
.imp-spec.is-all .imp-spec-graphic{grid-row:span 2}
.imp-spec-wait{aspect-ratio:16/9;background:var(--hk-hover)}
.imp-spec .ip-scene{box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke)),0 6px 16px -8px rgba(0,0,0,.35)}
.imp-bench-preview{display:grid;gap:10px;padding:14px;background:var(--hk-sunken);border:1px solid var(--hk-stroke);border-radius:var(--imp-r)}
/* Notebook: three panes. Sources and Studio sit on the raised surface, Ask on the page ground. */
.imp-nb{display:grid;grid-template-columns:280px minmax(420px,1fr) 360px;grid-template-rows:minmax(0,1fr);min-height:0;position:relative}
.imp-nb>.imp-srcpane{grid-area:1/1}
.imp-nb>.imp-ask{grid-area:1/2}
.imp-nb>.imp-studio{grid-area:1/3}
.imp-ic{flex:none;display:block}
.imp-pane{min-height:0;overflow:auto;padding:0 16px 20px;display:flex;flex-direction:column;gap:12px;scrollbar-width:thin}
.imp-pane-head{display:flex;align-items:center;gap:8px;min-height:48px;flex-wrap:wrap}
.imp-count{font-size:12px;font-variant-numeric:tabular-nums;padding:0 6px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);line-height:18px}
.imp-hint{font-size:12px;line-height:1.45}
.imp-tag{display:inline-flex;align-items:center;font-size:12px;font-weight:600;line-height:16px;padding:0 5px;border-radius:var(--imp-r);
  border:1px solid color-mix(in srgb,var(--hk-accent) 45%,var(--hk-stroke));background:color-mix(in srgb,var(--hk-accent) 9%,transparent);white-space:nowrap}
.imp-tag-inline{margin-left:6px;vertical-align:1px}
.imp-tag-pic{position:absolute;left:6px;bottom:6px;background:linear-gradient(var(--hk-surface),var(--hk-surface)),Canvas;box-shadow:0 1px 3px rgba(0,0,0,.2)}
.imp .imp-quiet[data-slot=button]{background:transparent;box-shadow:none;border-color:transparent;color:var(--imp-ink2);font-weight:500}
.imp .imp-quiet[data-slot=button]:hover:not(:disabled){background:var(--hk-hover);color:var(--hk-ink)}
.imp .imp-quiet.is-go[data-slot=button]{color:var(--hk-info,var(--hk-accent));font-weight:600}
.imp-tag.is-quiet{border-color:var(--hk-stroke);background:transparent;font-weight:500}
.imp-addwrap{position:relative}
.imp-addwrap>.imp-menu{right:0;left:auto}
.imp-menu-item{display:flex;gap:9px;align-items:center}
.imp-makemenu{min-width:170px}
.imp-iconbtn{all:unset;cursor:pointer;display:inline-grid;place-items:center;width:28px;height:28px;border-radius:var(--imp-r);box-sizing:border-box}
.imp-iconbtn:hover:not(:disabled){background:var(--hk-hover)}
.imp-iconbtn:disabled{color:var(--hk-stroke-strong,var(--hk-stroke));cursor:default}
.imp-iconbtn:focus-visible,.imp-textbtn:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-textbtn{all:unset;cursor:pointer;display:inline-flex;gap:6px;align-items:center;height:28px;padding:0 8px;font-size:12.5px;font-weight:600;border-radius:var(--imp-r)}
.imp-textbtn:hover:not(:disabled){background:var(--hk-hover)}
.imp-secs{font-size:12px;font-variant-numeric:tabular-nums;white-space:nowrap}
.imp-by{font-size:12px;line-height:1.4}
.imp-scrim{display:none}
.imp-room{display:grid;grid-template-columns:56px minmax(0,1fr);grid-template-rows:minmax(0,1fr);min-height:0;height:100%;position:relative}
.imp-room-rail{grid-area:1/1;z-index:10;display:flex;flex-direction:column;align-items:center;gap:2px;padding:10px 0;overflow:auto;background:var(--hk-surface);border-right:1px solid var(--hk-stroke);scrollbar-width:none}
.imp-room-stage{grid-area:1/2;min-width:0;min-height:0;position:relative}
.imp-room-tab{all:unset;cursor:pointer;display:grid;justify-items:center;gap:3px;width:50px;padding:7px 0 6px;border-radius:var(--imp-r);font-size:12px;font-weight:600;line-height:1}
.imp-room-btn{all:unset;cursor:pointer;position:relative;display:grid;place-items:center;width:38px;height:36px;border-radius:var(--imp-r)}
.imp-room-tab:hover,.imp-room-btn:hover{background:var(--hk-hover)}
.imp-room-tab:focus-visible,.imp-room-btn:focus-visible{outline:2px solid var(--hk-accent);outline-offset:-2px}
.imp-room-tab.is-on,.imp-room-btn.is-on{background:var(--hk-active);color:var(--hk-accent);box-shadow:inset 2px 0 0 var(--hk-accent)}
.imp-room-btn.is-in{color:var(--hk-accent)}
.imp-room-btn .imp-rail-n{position:absolute;right:1px;bottom:1px;font-size:12px;font-weight:600;line-height:1;color:var(--hk-ink)}
.imp-room-sep{width:28px;height:1px;background:var(--hk-stroke);margin:8px 0}
.imp-room-scrim{all:unset;grid-area:1/2;z-index:8;background:color-mix(in srgb,var(--hk-ink) 10%,transparent)}
.imp-dock{position:absolute;left:56px;top:0;bottom:0;z-index:9;display:flex;background:var(--imp-solid);border-right:1px solid var(--hk-stroke);box-shadow:16px 0 36px -18px rgba(0,0,0,.4);animation:imp-in 120ms ease-out}
.imp-dock.is-sources{width:min(320px,calc(100% - 96px))}
.imp-dock.is-ask{width:min(500px,calc(100% - 96px))}
.imp-dock>.imp-pane{flex:1;min-width:0;height:100%;overflow:auto;position:static;border:0}
.imp-dock>.imp-ask{overflow:hidden;display:flex;flex-direction:column}
.imp-dock .imp-rail{display:none!important}
.imp-dock .imp-src-body,.imp-dock .imp-reader{display:flex!important;position:static!important;width:auto!important;box-shadow:none!important;border:0!important;animation:none!important;background:transparent!important;overflow:visible!important}
.imp-dock .imp-chat-scroll{padding-left:22px;padding-right:22px}.imp-dock .imp-composer{padding-left:22px;padding-right:22px}
.imp-rail{display:none}

/* Sources */
.imp-srcpane{background:var(--hk-surface);border-right:1px solid var(--hk-stroke);padding:0;gap:0}
.imp-srcpane.is-drop{box-shadow:inset 0 0 0 2px var(--hk-accent)}
.imp-src-body{display:flex;flex-direction:column;gap:10px;padding:0 14px 20px;min-height:0}
.imp-srcs{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.imp-scard{display:grid;gap:5px;padding:10px 11px 11px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg);transition:border-color 120ms}
.imp-scard:hover{border-color:var(--hk-stroke-strong,var(--hk-stroke))}
.imp-scard.is-off{background:transparent}
.imp-scard.is-off .imp-scard-title,.imp-scard.is-off .imp-scard-sum{text-decoration:none}
.imp-scard-top{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:8px;align-items:start}
.imp-scard-glyph{display:grid;place-items:center;width:16px;height:19px;color:var(--hk-accent)}
.imp-scard-title{all:unset;cursor:pointer;font-weight:600;font-size:13px;line-height:1.45;overflow-wrap:anywhere}
.imp-scard-title:hover{text-decoration:underline}
.imp-scard-title:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp-tick{position:relative;display:grid;place-items:center;width:20px;height:20px;cursor:pointer}
.imp-tick input{position:absolute;inset:0;opacity:0;margin:0;cursor:pointer}
.imp-tick-box{display:grid;place-items:center;width:16px;height:16px;border:1.5px solid var(--hk-stroke-strong,var(--hk-stroke));border-radius:var(--imp-r);color:#fff}
.imp-tick input:checked+.imp-tick-box{background:var(--hk-accent);border-color:var(--hk-accent)}
.imp-tick input:focus-visible+.imp-tick-box{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp-scard-meta{display:block;font-size:12px;line-height:1.4;padding-left:24px;min-width:0}
.imp-scard-n{display:inline-grid;place-items:center;min-width:16px;height:16px;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;border:1px solid var(--hk-stroke-strong,var(--hk-stroke));border-radius:var(--imp-r);padding:0 2px}
.imp-scard-sum{font-size:12.5px;line-height:1.5;padding-left:24px;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;cursor:pointer}
.imp-scard-sum.is-open{display:block}
.imp-scard-wait{display:flex;gap:6px;align-items:center;font-size:12px;flex-wrap:wrap;padding-left:24px}
.imp-scard>.imp-linkish{margin-left:24px}
.imp-useall{align-self:flex-start}
.imp-src-empty{display:grid;gap:8px;justify-items:start;padding:14px 2px;font-size:13px;line-height:1.5}
.imp-src-empty-kinds{font-size:12.5px}
.imp-reader{display:flex;flex-direction:column;gap:10px;padding:0 14px 20px}
.imp-reader-back{position:sticky;top:0;z-index:2;background:var(--imp-solid);padding:15px 0 9px;display:flex;gap:10px;align-items:baseline;border-bottom:1px solid var(--hk-stroke)}
.imp-reader-back>.imp-linkish{white-space:nowrap;flex:none}
.imp-reader-name{font-size:12px;font-weight:600;min-width:0;overflow-wrap:anywhere}
.imp-reader-body{display:grid;gap:8px}
.imp-reader-sum{font-size:13px;line-height:1.5;padding:8px 10px;background:var(--hk-bg);border-radius:var(--imp-r)}
.imp-passages{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.imp-pass{display:grid;gap:3px;padding:8px 10px;border-left:2px solid transparent;font-size:13px;line-height:1.55}
.imp-pass p{font-family:"Source Serif 4",Georgia,serif;font-size:15px;line-height:1.55}
.imp-pass.is-cited{border-left-color:var(--hk-accent);background:var(--hk-active)}
.imp-pass-loc{font-size:12px;font-weight:600}

/* Ask */
.imp-ask{background:var(--hk-bg);padding:0;gap:0;min-width:0}
.imp-ask-head{padding:0 24px;border-bottom:1px solid var(--hk-stroke);flex:none}
.imp-chat-scroll{position:relative;flex:1;overflow:auto;padding:22px 28px 28px;display:flex;flex-direction:column;gap:18px;min-height:0;scrollbar-width:thin}
.imp-chat-scroll{-webkit-mask-image:linear-gradient(to bottom,#000 calc(100% - 28px),transparent);mask-image:linear-gradient(to bottom,#000 calc(100% - 28px),transparent)}
.imp-chat-scroll>*{width:100%;max-width:680px;align-self:center}
.imp-gd{display:grid;gap:14px}
.imp-gd-text{font-size:15px;line-height:1.62;color:var(--hk-ink)}
.imp-gd-empty{font-size:13px;line-height:1.5;padding:14px 0}
.imp-gd.is-wait{padding:14px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-surface)}
.imp-skel{display:grid;gap:9px}
.imp-skel span{display:block;height:11px;border-radius:var(--imp-r);background:linear-gradient(90deg,var(--hk-hover),color-mix(in srgb,var(--hk-ink) 10%,transparent),var(--hk-hover));background-size:200% 100%;animation:imp-shimmer 1.4s linear infinite}
.imp-gd-sec{display:grid;gap:6px;padding-top:4px}
.imp-gd-sec>.imp-h3{display:flex;gap:8px;align-items:center;font-size:12.5px;font-weight:600;color:var(--imp-ink2)}
.imp-gd>.imp-gd-sec:first-of-type{margin-top:6px;padding-top:16px;border-top:1px solid var(--hk-stroke)}
.imp-asks{list-style:none;margin:0;padding:0;display:grid;gap:0}
.imp-askcard{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:start;padding:9px 4px 9px 2px}
.imp-asks>li+li{border-top:1px solid var(--hk-stroke)}
.imp-askcard-glyph{display:grid;place-items:center;width:26px;height:26px;color:var(--imp-ink2)}
.imp-askcard-body{display:grid;gap:4px;justify-items:start;min-width:0}
.imp-askcard-body strong{font-size:13px;line-height:1.4;font-weight:600}
.imp-askcard-meta{font-size:12px;line-height:1.4}
.imp-askcard>[data-slot=button]{align-self:center}
.imp-spill{all:unset;cursor:pointer;box-sizing:border-box;display:inline-flex;gap:6px;align-items:center;max-width:100%;font-size:12px;line-height:20px;padding:0 7px;
  border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg)}
.imp-spill:hover{border-color:var(--hk-accent)}
.imp-spill:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-spill .imp-ic{color:var(--hk-accent)}
.imp-spill-name{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.imp-spill-loc{white-space:nowrap;padding-left:6px;border-left:1px solid var(--hk-stroke)}
.imp-qrows{list-style:none;margin:0;padding:0;display:grid}
.imp-qrows li+li .imp-qrow{border-top:1px solid var(--hk-stroke)}
.imp-qrow{all:unset;cursor:pointer;box-sizing:border-box;width:100%;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;align-items:center;padding:8px 8px;font-size:12.5px;line-height:1.5;border-radius:var(--imp-r);color:var(--imp-ink2)}
.imp-qrow:hover{background:var(--hk-hover)}
.imp-qrow:focus-visible{outline:2px solid var(--hk-accent);outline-offset:-2px}
.imp-qrows.is-follow{margin-top:2px;border-top:1px solid var(--hk-stroke)}
.imp-q{align-self:flex-end !important;width:auto !important;max-width:min(80%,560px) !important;margin-top:10px;font-size:14px;line-height:1.5;font-weight:500;padding:9px 13px;border-radius:var(--imp-r);
  background:color-mix(in srgb,var(--hk-accent) 10%,var(--imp-q-bg,transparent));border:1px solid color-mix(in srgb,var(--hk-accent) 22%,var(--hk-stroke))}
.imp-chat-scroll>.imp-q{margin-right:max(0px,calc((100% - 680px) / 2))}
.imp-a{display:grid;gap:10px}
.imp-a-lead{font-size:14px;line-height:1.6;font-weight:600}
.imp-a-p{font-size:14px;line-height:1.65;overflow-wrap:anywhere}
.imp-a-foot{display:flex;gap:6px;align-items:center;flex-wrap:wrap;padding:8px 0;position:sticky;bottom:-28px;z-index:2;background:linear-gradient(var(--hk-bg),var(--hk-bg)),Canvas;border-top:1px solid var(--hk-stroke)}
.imp-a-fold{all:unset;cursor:pointer;display:inline-flex;gap:4px;align-items:center;font-size:12.5px;font-weight:600;padding:4px 6px 4px 2px;border-radius:var(--imp-r)}
.imp-a-fold:hover{background:var(--hk-hover)}
.imp-a-fold:focus-visible{outline:2px solid var(--hk-accent)}
.imp-a-src{list-style:none;margin:0;padding:8px 0 0;display:grid;gap:2px;border-top:1px solid var(--hk-stroke)}
.imp-a-srcbtn{all:unset;cursor:pointer;display:flex;gap:8px;align-items:center;font-size:12.5px;padding:3px 4px;border-radius:var(--imp-r)}
.imp-a-srcbtn:hover{background:var(--hk-hover)}
.imp-a-srcbtn:focus-visible{outline:2px solid var(--hk-accent)}
.imp-cite{all:unset;cursor:pointer;display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 3px;margin:0 1px;box-sizing:border-box;
  font-size:12px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums;color:var(--hk-ink);border:1px solid color-mix(in srgb,var(--hk-accent) 70%,var(--hk-stroke));border-radius:var(--imp-r);
  vertical-align:.1em;background:color-mix(in srgb,var(--hk-accent) 9%,transparent)}
.imp-cite:hover{background:color-mix(in srgb,var(--hk-accent) 22%,transparent)}
.imp-cite:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-cite.is-static{cursor:inherit}
.imp-nowrap{white-space:nowrap}
.imp-cite.is-lit{background:var(--hk-accent);border-color:var(--hk-accent);color:#fff;animation:imp-lit 1.2s ease-in-out infinite alternate}
.imp-reading{display:flex;gap:6px;align-items:center;font-size:13px;padding:12px 14px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-surface)}
.imp-reading .imp-spin{margin-right:4px}
.imp-composer{flex:none;padding:12px 28px 14px;border-top:1px solid var(--hk-stroke);display:grid;gap:6px;background:var(--hk-bg)}
.imp-composer>*{width:100%;max-width:680px;justify-self:center}
.imp-composer-box{position:relative;display:block}
.imp-composer-box textarea{width:100%;resize:none;padding-right:48px;font-size:14px;line-height:1.5}
.imp-send{all:unset;cursor:pointer;position:absolute;right:8px;bottom:8px;display:grid;place-items:center;width:30px;height:30px;border-radius:var(--imp-r);background:var(--hk-accent);color:#fff}
.imp-send:disabled{cursor:default;background:var(--hk-sunken);color:var(--hk-ink)}
.imp-send:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp-scope{font-size:12px}

/* First open */
.imp-first .imp-first-inner{margin:auto;max-width:580px;padding:36px 32px;display:grid;gap:20px;justify-items:start}
.imp-first-pic{margin:0;display:grid;gap:8px;width:100%}
.imp-first-pic img{display:block;width:100%;height:auto;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);box-shadow:0 1px 2px rgba(0,0,0,.06),0 12px 32px -14px rgba(0,0,0,.28);animation:imp-in 240ms ease-out}
.imp-first-pic figcaption{font-size:12.5px;line-height:1.4}
.imp-first-lead{font-size:22px;line-height:1.38;font-weight:600;letter-spacing:-.012em;margin:0}
.imp-first-acts{display:flex;gap:10px;flex-wrap:wrap}
.imp-first-sample{display:flex;gap:8px;align-items:baseline;font-size:12.5px;line-height:1.5}
.imp-top-sample{display:inline-flex;gap:8px;align-items:center;font-size:13px;font-weight:600}

/* Make: brief, outline, build */
.imp-flow-steps{display:inline-flex;gap:2px;font-size:12px}
.imp-flow-step{padding:2px 8px;border-radius:var(--imp-r)}
.imp-flow-step.is-on{background:var(--hk-active);font-weight:600;box-shadow:inset 0 -2px 0 var(--hk-accent)}
.imp-flow-scroll{flex:1;overflow:auto;padding:24px 28px 32px;display:flex;flex-direction:column;gap:18px;min-height:0}
.imp-flow-scroll>*{width:100%;max-width:680px;align-self:center}
.imp-flow-head{display:grid;grid-template-columns:auto minmax(0,1fr);gap:14px;align-items:center}
.imp-flow-glyph{display:grid;place-items:center;width:44px;height:44px;border-radius:var(--imp-r);background:color-mix(in srgb,var(--hk-accent) 11%,transparent);color:var(--hk-accent)}
.imp-flow-kind{font-size:12px;font-weight:600}
.imp-flow-title{font-size:19px;line-height:1.3;font-weight:600;margin:0;letter-spacing:-.01em}
.imp-flow-card{display:grid;gap:16px;padding:18px 20px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-surface)}
.imp-flow-card-head{font-size:14px;font-weight:600}
.imp-flow-ask{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13px;padding-bottom:14px;border-bottom:1px solid var(--hk-stroke)}
.imp-brief{display:grid;gap:14px}
.imp-brief .imp-field>span{font-size:12px;font-weight:600}
.imp-brief input,.imp-brief textarea{font-size:13.5px}
.imp-flow-acts{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.imp-flow-from{font-size:12px}
.imp-outline{gap:12px}
.imp-outline>.imp-flow-acts{position:sticky;bottom:-33px;z-index:2;margin:0 -20px -18px;padding:12px 20px 14px;background:var(--imp-solid);border-top:1px solid var(--hk-stroke)}
.imp-outline-head{display:flex;align-items:center;gap:8px;font-size:13px}
.imp-outline-warn{font-size:12.5px;padding:8px 10px;border-left:2px solid var(--hk-warn-fill);background:color-mix(in srgb,var(--hk-warn-fill) 8%,transparent)}
.imp-ol{list-style:none;margin:0 -8px;padding:0;display:grid;gap:2px}
.imp-ol-row{position:relative;display:grid;grid-template-columns:20px 20px minmax(0,1fr);gap:10px;align-items:start;padding:10px 8px;border-radius:var(--imp-r);outline:none;
  transition:opacity 220ms ease-out,transform 220ms ease-out,background 120ms}
.imp-ol-row.is-hidden{opacity:0;transform:translateY(8px)}
.imp-ol-row:hover{background:var(--hk-hover)}
.imp-ol-row.is-focus{background:var(--hk-active);box-shadow:inset 2px 0 0 var(--hk-accent)}
.imp-ol-row.is-fixed{cursor:default}.imp-ol-row.is-fixed:hover{background:none}
.imp-ol-row:focus-visible{box-shadow:inset 2px 0 0 var(--hk-accent),0 0 0 2px var(--hk-accent)}
.imp-ol-n{font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;text-align:right;line-height:21px}
.imp-ol-type{display:grid;place-items:center;height:21px;color:var(--hk-accent)}
.imp-ol-body{display:grid;gap:5px;min-width:0}
.imp-ol-title{font-size:14px;line-height:1.5;font-weight:600}
.imp-ol-input{font:inherit;font-size:14px;font-weight:600;line-height:1.5;color:var(--hk-ink);background:var(--hk-bg);border:1px solid var(--hk-accent);border-radius:var(--imp-r);padding:2px 6px;width:100%;box-sizing:border-box}
.imp-ol-meta{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:12px}
.imp-ol-kind{margin-right:2px}
.imp-locchip{all:unset;cursor:pointer;font-size:12px;line-height:18px;padding:0 6px;border:1px solid color-mix(in srgb,var(--hk-accent) 50%,var(--hk-stroke));border-radius:var(--imp-r);background:color-mix(in srgb,var(--hk-accent) 7%,transparent);max-width:220px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.imp-locchip:hover{background:color-mix(in srgb,var(--hk-accent) 18%,transparent)}
.imp-locchip:focus-visible{outline:2px solid var(--hk-accent)}
.imp-ol-split{all:unset;cursor:pointer;display:inline-flex;gap:4px;align-items:center;font-size:12px;padding:0 6px;line-height:20px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg)}
.imp-ol-split:hover{border-style:solid}
.imp-ol-acts{grid-column:3;display:flex;gap:2px;align-items:center;flex-wrap:wrap;margin-left:-6px}
.imp-ol-add{all:unset;cursor:pointer;display:inline-flex;gap:6px;align-items:center;font-size:12.5px;font-weight:600;padding:6px 8px;border-radius:var(--imp-r);justify-self:start}
.imp-ol-add:hover{background:var(--hk-hover)}
.imp-rw{display:grid;gap:6px;padding:10px;margin-top:4px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg)}
.imp-rw-head{font-size:12px;font-weight:600}
.imp-rw-opt{all:unset;cursor:pointer;font-size:13.5px;line-height:1.45;padding:7px 9px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-surface)}
.imp-rw-opt:hover,.imp-rw-opt:focus-visible{border-color:var(--hk-accent);background:var(--hk-active)}
.imp-plan{list-style:none;margin:0;padding:12px 0 0;display:grid;gap:2px;border-top:1px solid var(--hk-stroke)}
.imp-plan li{display:grid;grid-template-columns:20px minmax(0,1fr) auto;gap:10px;align-items:center;padding:5px 0;font-size:13px;line-height:1.4}
.imp-plan-n{display:grid;place-items:center;width:20px;height:20px;font-size:12px;font-weight:600;border:1px solid var(--hk-stroke);border-radius:50%;font-variant-numeric:tabular-nums}
.imp-plan li.is-done .imp-plan-n{background:var(--hk-good-fill);border-color:var(--hk-good-fill);color:#fff}
.imp-plan li.is-now{font-weight:600}
.imp-plan li.is-now .imp-plan-n{border-color:var(--hk-accent);box-shadow:0 0 0 3px color-mix(in srgb,var(--hk-accent) 20%,transparent)}
.imp-plan-k{color:var(--hk-accent)}
.imp-gopts{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.imp-gopt{display:grid;gap:6px;align-content:start;justify-items:start;padding:12px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg);font-size:12.5px}
.imp-gopt-glyph{color:var(--hk-accent)}
.imp-gopt-check{display:inline-flex;gap:4px;align-items:center}

/* Job steps */
.imp-jsteps{display:grid;gap:12px}
.imp-steps{list-style:none;margin:0;padding:0;display:grid;gap:7px}
.imp-steps li{display:grid;grid-template-columns:16px minmax(0,1fr) auto;gap:9px;align-items:center;font-size:13px;line-height:1.4}
.imp-jsteps.is-compact .imp-steps li{font-size:12.5px}
.imp-steps li.is-now{font-weight:600}
.imp-step-ic{display:grid;place-items:center;width:16px;height:16px;border-radius:50%;background:var(--hk-good-fill);color:#fff}
.imp-step-ic.is-x{background:var(--hk-sunken);color:var(--hk-ink)}
.imp-steps li.is-bad .imp-step-ic{background:var(--hk-bad-fill);color:#fff}
.imp-steps .imp-spin{width:14px;height:14px}

/* Studio */
.imp-studio{background:var(--hk-surface);border-left:1px solid var(--hk-stroke);gap:14px}
.imp-studio>.imp-pane-head{flex-wrap:nowrap}
.imp-st-sec{display:grid;gap:8px;padding-top:12px;border-top:1px solid var(--hk-stroke)}
.imp-st-sec>.imp-h3{font-size:13px}
.imp-st-empty{font-size:12.5px}
.imp-tiles{display:grid;grid-template-columns:1fr 1fr;gap:12px 10px}
.imp-makerow{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.imp-make{all:unset;cursor:pointer;box-sizing:border-box;position:relative;display:grid;justify-items:center;align-content:center;gap:4px;min-width:0;height:54px;padding:6px 2px 4px;
  border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg);font-size:12px;font-weight:600;line-height:1.2;text-align:center;overflow:hidden;transition:border-color 120ms,background 120ms}
.imp-make::before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:var(--sw)}
.imp-make>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.imp-make .imp-ic{color:var(--imp-ink2)}
.imp-make:hover:not(:disabled){border-color:var(--hk-stroke-strong,var(--hk-stroke));background:var(--hk-hover)}
.imp-make:focus-visible{outline:2px solid var(--hk-accent);outline-offset:1px}
.imp-make:disabled{cursor:not-allowed;color:color-mix(in srgb,var(--hk-ink) 50%,var(--hk-bg))}
.imp-tile{all:unset;cursor:pointer;box-sizing:border-box;display:grid;gap:7px;min-width:0}
.imp-tile:disabled{cursor:not-allowed}
.imp-tile-pic{display:block;position:relative;aspect-ratio:16/10;overflow:hidden;border-radius:var(--imp-r);background:var(--hk-sunken);
  box-shadow:0 0 0 1px var(--hk-stroke),0 1px 2px rgba(16,24,40,.06),0 8px 18px -12px rgba(16,24,40,.4);transition:transform 160ms var(--hk-ease,ease),box-shadow 160ms}
.imp-tile-pic img{display:block;width:100%;height:100%;object-fit:cover;object-position:top center}
.imp-tile.is-onepager .imp-tile-pic img,.imp-tile.is-visual .imp-tile-pic img{object-position:top center}
.imp-tile:hover:not(:disabled) .imp-tile-pic{transform:translateY(-2px);box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke)),0 2px 4px rgba(16,24,40,.08),0 14px 26px -12px rgba(16,24,40,.5)}
.imp-tile:focus-visible .imp-tile-pic{outline:2px solid var(--hk-accent);outline-offset:2px}
.imp-tile:disabled .imp-tile-pic{filter:grayscale(1) contrast(.85)}
.imp-tile-label{display:flex;gap:6px;align-items:center;font-size:12.5px;font-weight:600}
.imp-tile-label .imp-ic{color:var(--hk-accent)}
.imp-tile-stand{position:absolute;inset:0;display:grid;align-content:start;gap:7px;padding:0 0 10px;background:color-mix(in srgb,var(--a) 6%,var(--hk-bg))}
.imp-ts-band{height:22%;background:var(--a)}
.imp-ts-line{height:6px;margin:0 12%;width:66%;background:color-mix(in srgb,var(--a) 55%,transparent);border-radius:1px}
.imp-ts-line.is-short{width:40%;background:color-mix(in srgb,var(--b) 70%,transparent)}
.imp-ts-bars{position:absolute;left:12%;right:44%;bottom:10%;height:36%;display:flex;gap:10%;align-items:flex-end}
.imp-ts-bars span{flex:1;background:color-mix(in srgb,var(--a) 70%,transparent)}
.imp-ts-bars span:last-child{background:var(--c)}
.imp-sugg{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.imp-sugg-row{all:unset;cursor:pointer;box-sizing:border-box;width:100%;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:9px;align-items:center;padding:8px 10px;font-size:12.5px;line-height:1.4;
  border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg)}
.imp-sugg-row .imp-ic{color:var(--hk-accent)}
.imp-sugg-row:hover{border-color:var(--hk-accent)}
.imp-sugg-row:focus-visible{outline:2px solid var(--hk-accent)}
.imp-sugg-go{font-size:12px;font-weight:600;color:var(--hk-info)}
.imp-made{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:1fr 1fr;gap:14px 10px}
.imp-mcard{all:unset;cursor:pointer;box-sizing:border-box;width:100%;display:grid;gap:8px;align-content:start;border-radius:var(--imp-r)}
.imp-mcard:hover .imp-mcard-pic{transform:translateY(-2px);box-shadow:0 0 0 1px var(--hk-stroke-strong,var(--hk-stroke)),0 14px 26px -12px rgba(16,24,40,.5)}
.imp-mcard:focus-visible{outline:2px solid var(--hk-accent)}
.imp-mcard-pic{position:relative;display:block;aspect-ratio:16/10;overflow:hidden;border-radius:var(--imp-r);background:var(--hk-sunken);box-shadow:0 0 0 1px var(--hk-stroke),0 8px 18px -12px rgba(16,24,40,.45);transition:transform 160ms,box-shadow 160ms}
.imp-mcard-pic img{display:block;width:100%;height:100%;object-fit:cover;object-position:top center}
.imp-mcard-text{display:grid;gap:3px;min-width:0}
.imp-mcard-text strong{font-size:12.5px;line-height:1.35;overflow-wrap:break-word}
.imp-mcard-meta{display:block;font-size:12px;line-height:1.45}
.imp-mcard-meta .imp-ic{display:inline-block;vertical-align:-2px;margin-right:5px}
.imp-mcard-meta .imp-tag{margin-left:6px}
.imp-mcard-meta.is-when{font-variant-numeric:tabular-nums;color:var(--imp-ink2)}
.imp-sjob,.imp-sjob-card{display:grid;gap:8px;padding:10px 12px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg);font-size:12.5px}
.imp-sjob{grid-template-columns:auto 1fr;align-items:center}
.imp-sjob-card.is-ended{border-color:var(--hk-stroke-strong,var(--hk-stroke))}
.imp-sjob-head{display:flex;gap:7px;align-items:center;font-size:13px}
.imp-sjob-head .imp-ic{color:var(--hk-accent)}
.imp-sjob-err{font-size:12.5px}
.imp-kc{position:relative;min-width:0}
.imp-kc-btn{all:unset;cursor:pointer;box-sizing:border-box;display:inline-flex;gap:8px;align-items:center;max-width:100%;height:28px;padding:0 8px 0 6px;border:1px solid var(--hk-stroke);border-radius:var(--imp-r);background:var(--hk-bg);font-size:12.5px;font-weight:600}
.imp-kc-btn:hover{border-color:var(--hk-stroke-strong,var(--hk-stroke))}
.imp-kc-btn:focus-visible{outline:2px solid var(--hk-accent)}
.imp-kc-bar{display:flex;width:28px;height:14px;flex:none;box-shadow:0 0 0 1px var(--hk-stroke)}
.imp-kc-bar span{flex:1}
.imp-kc-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.imp-kc-menu{position:absolute;right:0;top:calc(100% + 4px);z-index:12;width:260px;max-height:420px;overflow:auto;padding:6px;display:grid;gap:2px;
  background:var(--imp-solid);border:1px solid var(--hk-stroke-strong,var(--hk-stroke));border-radius:var(--imp-r);box-shadow:0 12px 32px -8px rgba(0,0,0,.35)}
.imp-brief .imp-kc-menu{left:0;right:auto}
.imp-kc-menu ul{list-style:none;margin:0;padding:0;display:grid;gap:1px}
.imp-kc-group{font-size:12px;font-weight:600;padding:6px 6px 2px}
.imp-kc-row{all:unset;cursor:pointer;box-sizing:border-box;width:100%;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;padding:6px;border-radius:var(--imp-r)}
.imp-kc-row:hover,.imp-kc-row:focus-visible{background:var(--hk-hover)}
.imp-kc-row.is-on{background:var(--hk-active)}
.imp-kc-more{padding:6px}
.imp-kc-foot{display:flex;flex-wrap:wrap;gap:6px;padding:8px 6px 4px;border-top:1px solid var(--hk-stroke);margin-top:4px}
.imp-note-list{list-style:none;margin:0;padding:0;display:grid;gap:6px}
.imp-note{display:grid;gap:6px;padding:9px 10px;border-left:2px solid var(--hk-accent);background:var(--hk-bg);font-size:12.5px;line-height:1.5}
.imp-note p{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}
.imp-note-foot{display:flex;align-items:center;justify-content:space-between;font-size:12px}
.imp-chips-inline{display:flex;gap:2px}
.imp-notes>.imp-pane-head{min-height:0}

/* The viewer (audio brief) */
.imp-viewer{grid-area:1/2/2/4;z-index:6;background:var(--hk-sunken);overflow:auto;display:flex;flex-direction:column;min-height:0;border-left:1px solid var(--hk-stroke);animation:imp-in 140ms ease-out}
.imp-viewer-head{position:sticky;top:0;z-index:3;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 18px;background:var(--hk-surface);border-bottom:1px solid var(--hk-stroke)}
.imp-viewer-title{display:grid;flex:1;min-width:180px}
.imp-viewer-title strong{font-size:14px}
.imp-viewer-title span{font-size:12px}
.imp-player{display:grid;grid-template-columns:auto minmax(0,1fr) auto auto;gap:14px;align-items:center;padding:12px 16px;background:var(--imp-solid);border:1px solid var(--hk-stroke);border-radius:var(--imp-r);box-shadow:0 8px 24px -16px rgba(0,0,0,.35);position:sticky;top:calc(var(--imp-head-h,64px) + 8px);z-index:2}
.imp-player.is-off{grid-template-columns:auto minmax(0,1fr) auto;box-shadow:none;position:relative;top:auto;z-index:auto;margin:0 0 4px}
.imp-player+.imp-proof{position:relative;z-index:0;margin-top:0}
.imp-player audio{display:none}
.imp-play{all:unset;cursor:pointer;display:grid;place-items:center;width:40px;height:40px;border-radius:50%;background:var(--hk-accent);color:#fff}
.imp-play:disabled{background:var(--hk-sunken);color:var(--hk-ink);cursor:default}
.imp-play:focus-visible{outline:2px solid var(--hk-accent);outline-offset:3px}
.imp-play.is-off{background:var(--hk-sunken);color:var(--hk-ink)}
.imp-play .imp-ic{margin-left:2px;fill:currentColor}
.imp-pause{display:flex;gap:4px}.imp-pause span{width:4px;height:14px;background:currentColor;border-radius:1px}
.imp-player-mid{display:grid;gap:7px;min-width:0}
.imp-player-title{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.imp-player-note{font-size:13px;line-height:1.45}
.imp-progress{position:relative;height:6px;border-radius:3px;background:var(--hk-sunken);cursor:pointer}
.imp-progress:focus-visible{outline:2px solid var(--hk-accent);outline-offset:3px}
.imp-progress-fill{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--hk-accent)}
.imp-progress-tick{position:absolute;top:-2px;bottom:-2px;width:2px;margin-left:-1px;background:var(--hk-bg)}
.imp-stamp-row{display:flex;gap:12px;align-items:center;padding:12px 18px 0;max-width:796px;width:100%;align-self:center;box-sizing:border-box}
.imp-stamp{display:inline-flex;gap:7px;align-items:center;font-size:13px;font-weight:600}
.imp-stamp .imp-ic{color:var(--hk-tone)}
.imp-details{padding:10px 18px 0;max-width:796px;width:100%;align-self:center;box-sizing:border-box}
.imp-viewer-body{padding:14px 18px 40px;display:grid;gap:12px;justify-items:center}
.imp-viewer-body>*{width:100%;max-width:760px}
.imp-proof.is-plain .imp-sheet{box-shadow:0 1px 2px rgba(0,0,0,.12),0 0 0 1px var(--hk-stroke),0 18px 40px -24px rgba(0,0,0,.4)}
.imp-sheet.is-script{aspect-ratio:auto;overflow:visible}
.imp .imp-sheet.is-script .ip-num,.imp .imp-sheet.is-script .ip-num.is-kept{text-decoration:none}
.imp .imp-sheet.is-script .ip-num:hover,.imp .imp-sheet.is-script .ip-num.is-open{text-decoration:none;background:color-mix(in srgb,var(--hk-accent) 14%,transparent);border-radius:2px}
.imp .imp-sheet.is-script .ip-num.is-missing{text-decoration:underline wavy var(--hk-bad-fill) 1.5px}
.imp .imp-said{display:block;margin:.7em 0 .7em .2em;padding:.1em 0 .1em 1em;border-left:2px solid var(--k-accent,var(--hk-accent));font-style:italic;font-size:1.12em;line-height:1.45;color:var(--k-ink,inherit)}
.imp .imp-playing{background:color-mix(in srgb,var(--hk-accent) 9%,transparent);box-shadow:inset 3px 0 0 var(--hk-accent);border-radius:1px;padding:8px 12px 8px 16px;margin:-8px -12px -8px -16px}
.imp .imp-linechip{margin-left:3px;vertical-align:.12em;font-family:system-ui,sans-serif;background:transparent;border-color:color-mix(in srgb,var(--hk-accent) 40%,var(--hk-stroke));min-width:16px;height:16px}
.imp .ip-page .imp-linechip{color:var(--k-ink,#2b2b2b);border-color:color-mix(in srgb,var(--k-ink,#2b2b2b) 38%,transparent)}
.imp-sheet.is-visual{background:transparent;box-shadow:none}
.imp-trace-math{font-size:13px;font-weight:600;font-variant-numeric:tabular-nums}

/* 1280: 248 / 400+ / 320 */
@container (max-width:1120px){.imp-nb{grid-template-columns:248px minmax(400px,1fr) 320px}
  .imp-makerow{grid-template-columns:1fr 1fr}.imp-make{grid-auto-flow:column;justify-content:start;gap:7px;height:34px;padding:3px 10px 0}
  .imp-chat-scroll,.imp-flow-scroll{padding-left:22px;padding-right:22px}.imp-composer{padding-left:22px;padding-right:22px}}
/* 1000 to 1179 wide: Sources folds to a 56px rail; Studio stays the third column. */
@container (max-width:960px){.imp-nb{grid-template-columns:56px minmax(0,1fr) 300px}
  .imp-srcpane{overflow:visible;position:relative;z-index:9}
  .imp-rail{display:flex;flex-direction:column;align-items:center;gap:4px;padding:10px 0}
  .imp-rail-btn{all:unset;cursor:pointer;position:relative;display:grid;place-items:center;width:38px;height:38px;border-radius:var(--imp-r)}
  .imp-rail-btn:hover{background:var(--hk-hover)}
  .imp-rail-btn:focus-visible{outline:2px solid var(--hk-accent)}
  .imp-rail-btn.is-on{color:var(--hk-accent)}
  .imp-rail-n{position:absolute;right:1px;bottom:1px;font-size:12px;font-weight:600;line-height:1;color:var(--hk-ink)}
  .imp-src-body,.imp-reader{display:none}
  .is-rail-open .imp-src-body,.is-rail-open .imp-reader{display:flex;position:absolute;left:56px;top:0;bottom:0;width:300px;overflow:auto;background:var(--imp-solid);
    border-right:1px solid var(--hk-stroke);box-shadow:16px 0 36px -18px rgba(0,0,0,.4);animation:imp-in 120ms ease-out}
  .is-rail-open .imp-scrim{all:unset;display:block;grid-area:1/2/2/4;z-index:8;background:color-mix(in srgb,var(--hk-ink) 8%,transparent)}
  .imp-studio{padding-left:12px;padding-right:12px}
  .imp-chat-scroll,.imp-flow-scroll{padding-left:18px;padding-right:18px}.imp-composer{padding-left:18px;padding-right:18px}
}
@keyframes imp-shimmer{to{background-position:-200% 0}}
@keyframes imp-lit{from{box-shadow:0 0 0 0 color-mix(in srgb,var(--hk-accent) 0%,transparent)}to{box-shadow:0 0 0 3px color-mix(in srgb,var(--hk-accent) 28%,transparent)}}
@media (prefers-reduced-motion:reduce){.imp-viewer,.imp-tile-pic,.imp-ol-row,.imp-dock,.imp-first-pic img{animation:none;transition:none}.imp-skel span,.imp-cite.is-lit{animation:none}.imp-ol-row.is-hidden{opacity:1;transform:none}}
`

/* ------------------------------------------------------------------ register -- */

function Status() {
  const job = useValue($job)
  if (!job || job.status !== 'running') return null
  return h('span', { className: 'imp-status' }, `Letterpress: ${job.step || 'working'}`)
}

export default {
  id: PLUGIN_ID,
  name: 'Letterpress',
  register(ctx) {
    api = ctx
    fp = createFirstPaint({ storage: ctx.storage, read: () => ({ state: $state.get(), chats: $chats.get(), guide: $guide.get() }), onStale: v => $stale.set(v) })
    const offs = [$state, $chats, $guide].map(a => (typeof a.listen === 'function' ? a.listen(() => fp && fp.schedule()) : null))
    registerPage(ctx, {
      id: PLUGIN_ID, route: ROUTE, label: 'Letterpress', codicon: 'symbol-color', css: CSS,
      render: () => jsx(LetterpressPage, {}),
      palette: [
        { id: 'letterpress.open', label: 'Letterpress: open the notebook', keywords: ['brand', 'notebook', 'sources', 'deck', 'graphic', 'one-pager', 'kit'] },
        { id: 'letterpress.kits', contributionId: 'kits', label: 'Letterpress: open the brands', keywords: ['brand kit', 'colors', 'fonts'], run: () => { $tab.set('kits'); host.navigate(ROUTE) } },
      ],
      status: { render: () => jsx(Status, {}), side: 'right', order: 50 },
    })
    try { ctx.onEvent && ctx.onEvent('plugin.letterpress.job', () => poke()) } catch (e) { /* polling covers it */ }
    ctx.onDispose(() => { if (fp) fp.dispose(); for (const off of offs) if (typeof off === 'function') off(); api = null; for (const t of pollers.values()) clearTimeout(t); pollers.clear() })
  },
}

// For the harness: open a tab, a kit, an output or a source directly.
export function openTab(tab) { $tab.set(tab === 'proofs' ? 'notebook' : tab === 'sources' ? 'storage' : tab) }
export function openKit(id) { $tab.set('kits'); $kitOpen.set(id ? { id } : null) }
export function setKitMode(mode) { $tab.set('kits'); $kitMode.set(mode) }
export function setKit(id) { $kit.set(id) }
export function showAllStarters() { $tab.set('kits'); $allStarters.set(true) }
export function openDraft(draft) { $tab.set('kits'); $kitOpen.set({ importDraft: draft, request: null }) }
export function makeGraphic(noteId) { const n = (($state.get() || {}).notes || []).find(x => x.id === noteId); if (n) { $tab.set('notebook'); $graphicFor.set(n) } }
export async function openOutline(id, askId) {
  const r = await rest(`outlines/${id}`)
  const ol = r.outline || r
  const g = $guide.get()
  const ask = g && askId ? (g.asks || []).find(a => a.id === askId) : null
  $tab.set('notebook'); $viewing.set(null)
  $flow.set({ kind: ol.kind || 'deck', ask, step: 'outline', outline: ol, brief: ol.brief || (ask && ask.brief) || {} })
}
export async function showBuild(jobId, outlineId, askId) {
  if (outlineId) await openOutline(outlineId, askId)
  const j = await rest(`jobs/${jobId}`)
  const job = { ...j, params: { kind: 'deck', ...(j.params || {}) } }
  $flow.set({ ...($flow.get() || { kind: 'deck', step: 'outline' }), build: job })
  if (job.status === 'running') trackMake(job)
}
export function flowNow() { return $flow.get() }
export function stateNow() { return $state.get() }
export function view(id) { $tab.set('notebook'); openViewer(id) }
export function read(id, ref) { $tab.set('notebook'); $reader.set({ id, ref: ref || null }) }
export function designsFor(id) { $tab.set('notebook'); openDesigns(id) }
export function openForm(kind) { $tab.set('notebook'); openFlow(kind) }
