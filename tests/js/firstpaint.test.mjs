// The first-paint copy (desktop/src/firstpaint.js): run with `node --test tests/js/`.
// A real state answer can be passed in LETTERPRESS_STATE_JSON (tests/test_first_paint.py does, from the sample notebook).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CACHE_KEY, CACHE_MAX, CACHE_VERSION, STATE_KEYS, createFirstPaint, pack, scrub, unpack } from '../../desktop/src/firstpaint.js'

const png = n => `data:image/png;base64,${'A'.repeat(n)}`
function makeState(over = {}) {
  return {
    sources: [{ id: 's_1', title: 'Annual report', included: true, summary: 'What the year did.' }],
    kits: [{ id: 'counsel', name: 'Counsel', font_keys: ['b-inter-400-normal'], bar: ['#123456'] }],
    outputs: [{ id: 'o_1', kind: 'deck', title: 'Funder deck', status: 'ready', tokens_in: 1200, tokens_out: 5000, thumb: png(1000) }],
    jobs: [{ id: 'j_1', kind: 'make', status: 'running' }],
    sample: { available: true, open: false, name: 'Harborlight Literacy', label: 'Sample' },
    previews: { deck: { img: png(2000), w: 640, h: 360, kit_name: 'Counsel' } },
    prefs: { kit: 'counsel' }, usage: { today: 0, cap: null }, deps: { pypdf: { ok: true, label: 'PDF reading' } },
    storage: { bytes: 10, sources: 1, outputs: 1, kits: 0 }, layouts: {}, kinds: {}, ready_kinds: ['deck'], fonts: [],
    today: 'Tuesday, November 10', proof_css: '.ip{}', notes: [{ id: 1, text: 'A note' }], deck_systems: {},
    ...over,
  }
}
function fakeStorage(initial) {
  const m = new Map(initial ? [[CACHE_KEY, initial]] : [])
  return { m, writes: 0, get: (k, f) => (m.has(k) ? m.get(k) : f), set(k, v) { this.writes++; m.set(k, v) }, remove(k) { m.delete(k) } }
}
function fakeTimers() {
  let next = 1
  const due = new Map()
  return { setTimeout(fn) { const id = next++; due.set(id, fn); return id }, clearTimeout(id) { due.delete(id) }, run() { const fns = [...due.values()]; due.clear(); for (const f of fns) f() }, get pending() { return due.size } }
}
function page(storage) {
  // A stand-in for the page: three atoms and the wiring plugin.js does.
  const live = { state: null, chats: null, guide: undefined }
  const staleSeen = []
  const timers = fakeTimers()
  const fp = createFirstPaint({ storage, read: () => live, onStale: v => staleSeen.push(v), timers })
  return { live, fp, timers, staleSeen }
}

test('the first open ever has nothing stored and paints the usual wait', () => {
  const s = fakeStorage()
  const p = page(s)
  assert.equal(p.fp.hydrate(), null)
  assert.equal(p.fp.isStale(), false)
})

test('the next open paints the stored notebook at once, then the real answers replace it', () => {
  const s = fakeStorage()
  // open 1: real answers land and are stored
  const one = page(s)
  one.live.state = makeState(); one.fp.fresh('state')
  one.live.chats = [{ id: 1, role: 'user', text: 'What changed?' }]; one.fp.fresh('chats')
  one.live.guide = { guide: [{ text: 'The year in short.' }], source_ids: ['s_1'] }; one.fp.fresh('guide')
  one.timers.run()
  assert.equal(s.writes, 1)

  // open 2: the copy is there before any request is answered
  const two = page(s)
  const rec = two.fp.hydrate()
  assert.ok(rec, 'a stored copy')
  assert.equal(rec.state.sources[0].title, 'Annual report')
  assert.equal(rec.chats[0].text, 'What changed?')
  assert.equal(rec.guide.guide[0].text, 'The year in short.')
  assert.deepEqual(rec.state.jobs, [], 'jobs are never drawn from the copy')
  assert.equal(two.fp.isStale(), true)
  assert.deepEqual(two.staleSeen, [true])

  // while it is the copy, nothing is stored back
  two.live.state = rec.state; two.live.chats = rec.chats; two.live.guide = rec.guide
  two.fp.schedule(); two.fp.flush()
  assert.equal(s.writes, 1)

  // the real state lands: still not interactive until chats and the guide are real too
  two.live.state = makeState({ sources: [{ id: 's_1', title: 'Annual report', included: true }, { id: 's_2', title: 'Board notes', included: false }] })
  two.fp.fresh('state')
  assert.equal(two.fp.isStale(), true)
  assert.equal(two.fp.isStale('state'), false)
  two.live.chats = []; two.fp.fresh('chats')
  two.live.guide = null; two.fp.fresh('guide')
  assert.equal(two.fp.isStale(), false)
  assert.deepEqual(two.staleSeen, [true, false], 'the page hears once that it may take input')

  // and the new answers replace the old copy
  two.timers.run()
  const after = unpack(s.m.get(CACHE_KEY))
  assert.equal(after.state.sources.length, 2)
  assert.deepEqual(after.chats, [])
  assert.equal(after.guide, null)
})

test('a piece still shown from the copy is not stored back as if it were real', () => {
  const s = fakeStorage(pack({ state: makeState(), chats: [{ id: 9, role: 'user', text: 'old' }] }))
  const p = page(s)
  const rec = p.fp.hydrate()
  p.live.state = makeState({ today: 'Wednesday' }); p.live.chats = rec.chats
  p.fp.fresh('state'); p.timers.run()
  const now = unpack(s.m.get(CACHE_KEY))
  assert.equal(now.state.today, 'Wednesday')
  assert.equal('chats' in now, false, 'the old chats are left out until the real ones land')
})

test('the copy is capped: pictures go in only while they fit, the notebook itself always or not at all', () => {
  const st = makeState({ outputs: [1, 2, 3, 4, 5].map(i => ({ id: `o_${i}`, kind: 'deck', title: `Deck ${i}`, thumb: png(30000) })) })
  const s = pack({ state: st }, { max: 100000 })
  assert.ok(s.length <= 100000)
  const rec = unpack(s, { max: 100000 })
  const withPic = rec.state.outputs.filter(o => o.thumb)
  assert.equal(withPic.length, 3, 'three 30 KB covers fit under 100 KB')
  assert.deepEqual(withPic.map(o => o.id), ['o_1', 'o_2', 'o_3'], 'the first cards on screen first')
  assert.equal(rec.state.outputs.length, 5, 'every card is kept, with or without its cover')
  assert.equal(rec.state.previews.deck.img, undefined, 'tiles are not on screen once something is made')
  assert.ok(JSON.stringify(rec).length <= CACHE_MAX)

  // a notebook too big for the cap is not stored, and an older copy is removed rather than left to mislead
  const huge = makeState({ notes: [{ id: 1, text: 'x'.repeat(CACHE_MAX) }] })
  assert.equal(pack({ state: huge }), null)
  const storage = fakeStorage(pack({ state: makeState() }))
  const p = page(storage)
  p.live.state = huge; p.fp.fresh('state'); p.timers.run()
  assert.equal(storage.m.has(CACHE_KEY), false)

  // an oversized string in storage is not even parsed
  assert.equal(unpack('x'.repeat(CACHE_MAX + 1)), null)
})

test('preview tiles keep their pictures while nothing has been made', () => {
  const rec = unpack(pack({ state: makeState({ outputs: [] }) }))
  assert.match(rec.state.previews.deck.img, /^data:image\/png/)
  assert.equal(rec.state.previews.deck.w, 640)
})

test('no secrets or credentials are stored', () => {
  const st = makeState({
    prefs: { kit: 'counsel', api_key: 'abc', token: 't', Authorization: 'Bearer abcdefghijklmnop' },
    deps: { tts: { ok: true, label: 'Voice', credentials: { user: 'u', password: 'p' } } },
    sources: [{ id: 's_1', title: 'Report', included: true, origin: ('sk-' + 'ant-api03-' + 'A'.repeat(24)), note: 'Bearer abcdefghijklmnopqrstuvwxyz' }],
    usage: { today: 3, cap: null, refresh_token: 'r', client_secret: 's', cookie: 'c' },
    extra_secret_section: { password: 'nope' }, // not a key the first screen reads, so not stored at all
  })
  const s = pack({ state: st, chats: [{ id: 1, role: 'ai', text: 'ok', access_token: 'zzz' }], guide: { guide: [], apiKey: 'k' } })
  for (const bad of ['api_key', '"token"', 'Authorization', 'Bearer', 'password', 'sk-ant', 'refresh_token', 'client_secret', 'cookie', 'credentials', 'access_token', 'apiKey', 'extra_secret_section'])
    assert.equal(s.includes(bad), false, `stored ${bad}`)
  const rec = unpack(s)
  assert.deepEqual(rec.state.kits[0].font_keys, ['b-inter-400-normal'], 'ordinary keys with "key" in the name stay')
  assert.equal(rec.state.outputs[0].tokens_in, 1200, 'token counts stay')
  assert.equal(rec.state.sources[0].title, 'Report')
  assert.equal(rec.state.sources[0].origin, undefined)
  assert.deepEqual(Object.keys(rec.state).sort(), [...STATE_KEYS, 'jobs'].sort())
})

test('scrub keeps ordinary values and drops key-shaped strings anywhere', () => {
  assert.deepEqual(scrub({ a: [1, 'two', { b: true, token: 'x' }], c: 'ghp_abcdefghijklmnopqrstuv' }), { a: [1, 'two', { b: true }] })
  assert.equal(scrub(['eyJhbGciOiJIUzI1NiJ9', 'eyJzdWIiOiIxMjM0NTY3ODkwIn0', 'dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'].join('.')), undefined)
  assert.equal(scrub('A plain sentence about tokens and keys.'), 'A plain sentence about tokens and keys.')
})

test('outputs still being built and running jobs are left out of the copy', () => {
  const rec = unpack(pack({ state: makeState({ outputs: [{ id: 'o_1', kind: 'deck', title: 'Done' }, { id: 'o_2', kind: 'deck', building: true }] }) }))
  assert.deepEqual(rec.state.outputs.map(o => o.id), ['o_1'])
  assert.deepEqual(rec.state.jobs, [])
})

test('a copy of another version, a broken one, or one missing a key is never drawn', () => {
  const good = JSON.parse(pack({ state: makeState() }))
  assert.equal(unpack(JSON.stringify({ ...good, v: CACHE_VERSION + 1 })), null)
  assert.equal(unpack('{"v":1,'), null)
  const missing = structuredClone(good); delete missing.state.deck_systems
  assert.equal(unpack(JSON.stringify(missing)), null)
  const noKits = structuredClone(good); noKits.state.kits = []
  assert.equal(unpack(JSON.stringify(noKits)), null)
  assert.ok(unpack(good), 'an object a storage parsed already is accepted')
})

test('a copy that fails to draw is discarded and the page waits as on a first open', () => {
  const s = fakeStorage(pack({ state: makeState() }))
  const p = page(s)
  assert.ok(p.fp.hydrate())
  p.fp.discard()
  assert.equal(p.fp.isStale(), false)
  assert.equal(s.m.has(CACHE_KEY), false)
})

test('a storage that is missing, throws, or answers late costs only the fast open', () => {
  assert.equal(createFirstPaint({ storage: undefined }).hydrate(), null)
  const throwing = { get() { throw new Error('no') }, set() { throw new Error('full') } }
  const fp = createFirstPaint({ storage: throwing, read: () => ({ state: makeState() }), timers: fakeTimers() })
  assert.equal(fp.hydrate(), null)
  assert.doesNotThrow(() => { fp.fresh('state'); fp.flush() })
  assert.equal(createFirstPaint({ storage: { get: () => Promise.resolve('x') } }).hydrate(), null)
})

test('writes are batched and an unchanged notebook is not written again', () => {
  const s = fakeStorage()
  const p = page(s)
  p.live.state = makeState()
  p.fp.fresh('state'); p.fp.schedule(); p.fp.schedule()
  assert.equal(p.timers.pending, 1)
  p.timers.run(); p.fp.schedule(); p.timers.run()
  assert.equal(s.writes, 1)
})

const real = process.env.LETTERPRESS_STATE_JSON
test('a real state answer from the sample notebook packs under the cap and draws back the same notebook', { skip: !real }, () => {
  const st = JSON.parse(readFileSync(real, 'utf8'))
  const s = pack({ state: st })
  assert.ok(s, 'it fits')
  assert.ok(s.length <= CACHE_MAX)
  const rec = unpack(s)
  assert.deepEqual(rec.state.sources.map(x => x.id), st.sources.map(x => x.id))
  assert.deepEqual(rec.state.kits.map(x => x.id), st.kits.map(x => x.id))
  assert.deepEqual(rec.state.outputs.map(x => x.id), st.outputs.filter(o => !o.building).map(x => x.id))
  assert.equal(rec.state.proof_css, st.proof_css)
  assert.deepEqual(rec.state.notes, st.notes)
  assert.deepEqual(rec.state.prefs, st.prefs)
})
