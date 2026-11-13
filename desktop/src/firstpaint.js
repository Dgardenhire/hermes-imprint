// Letterpress's first paint: the last good notebook, shown at once on the next open while the real one loads.
//
// Opening Letterpress waits on its backend: Hermes starts the plugin helper and shakes hands with it before the first
// request is answered, which takes two or three seconds. The page's first screen is built from three answers:
// GET state, GET chats and GET notebook/guide. This file keeps a small copy of the last good answers in the Desktop
// SDK's own plugin storage (ctx.storage, the same place other plugins keep their per-window choices), so the next open
// draws the notebook straight away. The real answers replace the copy as they land; until all of them have, the page
// takes no input (the page sets `inert`), so nothing can be sent, deleted or exported from the copy.
//
// What is kept: only the keys the first screen reads (STATE_KEYS), no running jobs, no outputs still being built, and
// nothing whose name says it is a secret (SECRET_KEY) or whose value looks like a key or a bearer token. Pictures go
// in only while the copy stays under CACHE_MAX characters, the ones on screen first. The very first open has no copy
// and shows the usual "Opening Letterpress".
//
// No React, no SDK: tests drive it with a fake storage (tests/js/firstpaint.test.mjs).

export const CACHE_KEY = 'firstPaint'
export const CACHE_VERSION = 1 // bump when the shape of state changes, so an older copy is never drawn
export const CACHE_MAX = 400000 // characters of JSON, pictures included
export const PIECES = ['state', 'chats', 'guide']

// The parts of GET state the page reads. `jobs` is kept empty: a job is only ever tracked from a real answer.
export const STATE_KEYS = ['sources', 'kits', 'outputs', 'sample', 'previews', 'prefs', 'usage', 'deps', 'storage', 'layouts',
  'kinds', 'ready_kinds', 'fonts', 'today', 'proof_css', 'notes', 'deck_systems']
const REQUIRED = { sources: 'array', kits: 'array', outputs: 'array', notes: 'array', proof_css: 'string', sample: 'object', previews: 'object', prefs: 'object' }

// A property is dropped, at any depth, when its name is one of these. Names like `font_keys` or `tokens_in` stay.
export const SECRET_KEY = /^(api[_-]?keys?|apikey|secrets?|client[_-]?secret|password|passwd|pass|token|tokens|access[_-]?token|refresh[_-]?token|id[_-]?token|auth|authorization|cookies?|credentials?|bearer|session[_-]?token|private[_-]?key)$/i
// A string is dropped when it looks like a key or a token, whatever it is called.
export const SECRET_VALUE = /^(?:bearer\s+\S{8,}|(?:sk|pk|rk|xox[abpr]|ghp|gho|github_pat|glpat|hf|AKIA)[-_][A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,})$/i

const isImage = v => typeof v === 'string' && v.startsWith('data:image/')
const kindOf = v => (Array.isArray(v) ? 'array' : v === null ? 'null' : typeof v)

export function scrub(v, depth = 0) {
  if (depth > 40) return undefined
  if (typeof v === 'string') return SECRET_VALUE.test(v.trim()) ? undefined : v
  if (Array.isArray(v)) return v.map(x => scrub(x, depth + 1)).filter(x => x !== undefined)
  if (v && typeof v === 'object') {
    const out = {}
    for (const [k, x] of Object.entries(v)) {
      if (SECRET_KEY.test(k)) continue
      const y = scrub(x, depth + 1)
      if (y !== undefined) out[k] = y
    }
    return out
  }
  return typeof v === 'function' ? undefined : v
}

// The first screen's part of a state answer, pictures taken out (they go back in by budget, below).
function coreOf(st) {
  const core = {}
  for (const k of STATE_KEYS) if (k in st) core[k] = st[k]
  core.jobs = []
  core.outputs = (st.outputs || []).filter(o => o && !o.building).map(o => { const { thumb, ...rest } = o; return rest })
  const pv = {}
  for (const [k, p] of Object.entries(st.previews || {})) { if (p && typeof p === 'object') { const { img, ...rest } = p; pv[k] = rest } }
  core.previews = pv
  return core
}

// Pictures in the order the first screen shows them: the four preview tiles (and the first-open slide) only matter
// while nothing has been made; after that, the Made cards' covers, newest first.
function picturesOf(st) {
  const list = []
  const made = (st.outputs || []).filter(o => o && !o.building)
  if (!made.length) for (const [k, p] of Object.entries(st.previews || {})) if (p && isImage(p.img)) list.push({ at: ['previews', k, 'img'], img: p.img })
  for (const o of made) if (isImage(o.thumb)) list.push({ at: ['outputs', o.id, 'thumb'], img: o.thumb })
  return list
}

function put(state, at, img) {
  if (at[0] === 'previews') { if (state.previews[at[1]]) state.previews[at[1]].img = img; return }
  const o = state.outputs.find(x => x.id === at[1])
  if (o) o.thumb = img
}

// The copy to store, as a string no longer than `max`, or null when even the plain notebook will not fit.
export function pack({ state, chats, guide }, { max = CACHE_MAX, now = Date.now() } = {}) {
  if (!validState(state)) return null
  const rec = { v: CACHE_VERSION, at: now, state: scrub(coreOf(state)) }
  let size = JSON.stringify(rec).length
  if (size > max) return null
  for (const [k, v] of [['guide', guide], ['chats', chats]]) {
    if (v === undefined || (k === 'chats' && !Array.isArray(v))) continue
    const clean = scrub(v)
    const n = JSON.stringify(clean === undefined ? null : clean).length + k.length + 4
    if (size + n <= max) { rec[k] = clean === undefined ? null : clean; size += n }
  }
  for (const p of picturesOf(state)) {
    if (SECRET_VALUE.test(p.img)) continue
    const n = p.img.length + 16
    if (size + n > max) continue
    put(rec.state, p.at, p.img)
    size += n
  }
  const s = JSON.stringify(rec)
  return s.length <= max ? s : null
}

function validState(st) {
  if (!st || typeof st !== 'object' || Array.isArray(st)) return false
  for (const [k, t] of Object.entries(REQUIRED)) if (kindOf(st[k]) !== t) return false
  return st.kits.length > 0
}

// A stored copy, checked, or null. Accepts the string pack() made, or an object if the storage parsed it already.
export function unpack(raw, { max = CACHE_MAX } = {}) {
  let rec = raw
  try {
    if (typeof raw === 'string') { if (raw.length > max) return null; rec = JSON.parse(raw) }
  } catch (e) { return null }
  if (!rec || typeof rec !== 'object' || rec.v !== CACHE_VERSION || !validState(rec.state)) return null
  for (const k of STATE_KEYS) if (!(k in rec.state)) return null
  const out = { at: rec.at, state: rec.state }
  if (Array.isArray(rec.chats)) out.chats = rec.chats
  if ('guide' in rec && (rec.guide === null || (typeof rec.guide === 'object' && !Array.isArray(rec.guide)))) out.guide = rec.guide
  return out
}

function readRaw(storage) {
  try {
    if (!storage || typeof storage.get !== 'function') return null
    const v = storage.get(CACHE_KEY, null)
    return v && typeof v.then === 'function' ? null : v // an async storage cannot help the first paint
  } catch (e) { return null }
}
function writeRaw(storage, v) {
  try {
    if (!storage) return
    if (v === null) { if (typeof storage.remove === 'function') storage.remove(CACHE_KEY); else if (typeof storage.set === 'function') storage.set(CACHE_KEY, null) }
    else if (typeof storage.set === 'function') storage.set(CACHE_KEY, v)
  } catch (e) { /* a full or missing storage only costs the fast open */ }
}

// The page's side: hydrate() once before the first draw, fresh(piece) as each real answer lands, schedule() after any
// change. `read` returns the live {state, chats, guide}; `onStale` hears whether any piece on screen is still the copy.
export function createFirstPaint({ storage, read, onStale, delay = 800, timers = globalThis } = {}) {
  const stale = new Set()
  let timer = null
  let last // the string last written; undefined until the first write, so an old copy that no longer fits is removed
  let told = false
  const tell = () => {
    const now = stale.size > 0
    if (now === told) return
    told = now
    try { onStale && onStale(now) } catch (e) { /* ignore */ }
  }
  const fp = {
    hydrate() {
      const rec = unpack(readRaw(storage))
      if (!rec) return null
      stale.add('state')
      if ('chats' in rec) stale.add('chats')
      if ('guide' in rec) stale.add('guide')
      tell()
      return rec
    },
    isStale: piece => (piece ? stale.has(piece) : stale.size > 0),
    fresh(piece) {
      if (!stale.delete(piece)) { fp.schedule(); return }
      tell()
      fp.schedule()
    },
    // A copy that failed to draw is dropped, and the page waits for the real answers as on a first open.
    discard() {
      stale.clear(); tell()
      if (timer) { timers.clearTimeout(timer); timer = null }
      last = null
      writeRaw(storage, null)
      return true
    },
    schedule() {
      if (stale.has('state')) return // never store the copy back, only real answers
      if (timer) timers.clearTimeout(timer)
      timer = timers.setTimeout(() => { timer = null; fp.flush() }, delay)
    },
    flush() {
      if (timer) { timers.clearTimeout(timer); timer = null }
      if (stale.has('state') || typeof read !== 'function') return
      const now = read() || {}
      if (!now.state) return
      const live = { state: now.state, chats: stale.has('chats') ? undefined : now.chats === null ? undefined : now.chats, guide: stale.has('guide') ? undefined : now.guide }
      const s = pack(live)
      if (s === last) return
      last = s
      writeRaw(storage, s)
    },
    dispose() { fp.flush(); if (timer) timers.clearTimeout(timer); timer = null },
  }
  return fp
}
