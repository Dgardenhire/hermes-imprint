// Renders desktop/plugin.js inside a Hermes-like window. ctx.rest answers from fixtures.json (real backend
// answers made by make_fixtures.py). URL parameters:
//   tab    kits | storage | notebook           (default kits; the notebook is shot in live mode: harness/live/)
//   theme  dark | light                         (default dark)
//   scene  clean | flagged | empty | working | failed | ask | single   (proofs)
//   kits   grid | bench | site | guide         (kits)
//   pair   two kit ids, comma separated (proofs)
//   kind   onepager | deck | audio            (proofs)
//   kits   ... | import | draft               (kits: the import panel, or a draft on the bench)
//   accent hex without #                       (red or green Hermes accent check)
//   trace  a number as written, or "missing"   (focus it so its trace card opens; slot 0 or 1)
import { createRoot } from 'react-dom/client'
import { jsx, jsxs } from 'react/jsx-runtime'

const params = new URLSearchParams(location.search)
const dark = params.get('theme') !== 'light'
document.documentElement.dataset.theme = dark ? 'dark' : 'light'
document.documentElement.classList.toggle('dark', dark)
// accent  a hex without # (e.g. e5484d for red, 30a46c for green), to check the page with a red or green Hermes accent
if (/^[0-9a-f]{6}$/i.test(params.get('accent') || '')) { for (const v of ['--ui-accent', '--dt-primary']) document.documentElement.style.setProperty(v, '#' + params.get('accent')) }
const FX = await (await fetch('./fixtures.json')).json()
const pause = ms => new Promise(r => setTimeout(r, ms))
const clone = x => JSON.parse(JSON.stringify(x))
const scene = params.get('scene') || 'clean'

const kind = params.get('kind') || 'onepager'
function outputFor() {
  const o = clone(kind === 'deck' ? FX.deck : kind === 'audio' ? FX.audio : scene === 'flagged' ? FX.flagged : FX.output)
  if (scene === 'novoice' && kind === 'audio') for (const p of o.proofs) p.audio = { status: 'failed', code: 'no_voice', error: "Imprint couldn't record this: your Hermes voice isn't set up here. Turn on text to speech in Hermes Settings, then press Record again. The script is ready to read or export now." }
  const pair = (params.get('pair') || '').split(',').filter(Boolean)
  if (pair.length) {
    const all = [...o.proofs, ...Object.values(FX.extra)]
    o.proofs = pair.map(k => all.find(p => p.kit_id === k)).filter(Boolean)
    o.kit_ids = pair
  }
  return o
}
function fontFile(key) {
  const m = key.match(/^b-(.+)-(\d{3})-(normal|italic)$/)
  return `../fonts/${m[1]}-${m[2]}${m[3] === 'italic' ? '-italic' : ''}.ttf`
}
async function fontData(key) {
  const buf = await (await fetch(fontFile(key))).arrayBuffer()
  let bin = ''
  const v = new Uint8Array(buf)
  for (let i = 0; i < v.length; i += 0x8000) bin += String.fromCharCode.apply(null, v.subarray(i, i + 0x8000))
  return btoa(bin)
}

async function rest(path, options = {}) {
  await pause(20)
  if (path === 'state') {
    const s = clone(FX.state)
    if (scene === 'empty') { s.sources = []; s.outputs = [] }
    if (scene === 'working') s.jobs = [{ id: 'j_000000000001', kind: 'make', status: 'running', step: 'Writing from your sources' }]
    if (scene === 'failed') s.jobs = [{ id: 'j_000000000002', kind: 'make', status: 'running', step: 'Writing from your sources' }]
    if (params.get('pair')) s.prefs = { pair: params.get('pair').split(',') }
    const first = kind === 'deck' ? FX.deck : kind === 'audio' ? FX.audio : FX.output
    s.outputs = [{ id: first.id, kind: first.kind, title: first.title, source_ids: first.source_ids, kit_ids: first.kit_ids, tokens_in: 9000, tokens_out: 3000 }, ...(s.outputs || []).filter(o => o.id !== first.id)]
    return s
  }
  if (/^outputs\/o_[a-f0-9]+\/audio\//.test(path)) return clone(FX.audio_file)
  if (path.startsWith('kits/import/')) return clone(FX.draft)
  if (path.startsWith('outputs/') && !path.includes('/', 8)) {
    if (scene === 'empty' || scene === 'working' || scene === 'failed') throw new Error('404: {"detail":"none"}')
    return outputFor()
  }
  if (path === 'jobs/j_000000000001') { await pause(100000); return { status: 'running' } }
  if (path === 'jobs/j_000000000002') return { id: 'j_000000000002', kind: 'make', status: 'failed', error: "Imprint couldn't reach your Hermes model. Check Settings, then press Retry.", error_code: 'no_model' }
  if (path.startsWith('fonts/')) { const key = path.slice(6); const m = key.match(/-(\d{3})-(normal|italic)$/); return { key, weight: Number(m[1]), style: m[2], data: await fontData(key) } }
  if (path.startsWith('passages/')) return FX.passages[path.slice(9)]
  if (path === 'chats') return { chats: FX.chats }
  if (path === 'kits/uswds') return clone(FX.kit_uswds)
  if (path === 'kits/docket') return clone(FX.kit_docket)
  if (path === 'kits/preview') return { palette: FX.kit_uswds.palette }
  throw new Error('400: {"detail":"The harness does not answer this request."}')
}

const contributions = []
const ctx = {
  rest, registerMany(list) { contributions.push(...list) }, register(i) { contributions.push(i) },
  onEvent() { return () => {} }, onDispose() {}, setTimeout, setInterval,
  storage: { get: (k, f) => f, set() {}, remove() {} },
  os: { async revealPath() { return true } },
}
const mod = await import('../desktop/plugin.js')
mod.default.register(ctx)
const tab = params.get('tab') || 'kits'
mod.openTab(tab)
const kitsView = params.get('kits')
if (kitsView === 'bench') mod.openKit(params.get('kit') || 'uswds')
if (kitsView === 'site' || kitsView === 'guide' || kitsView === 'import') mod.setKitMode(kitsView)
if (kitsView === 'draft') mod.openDraft(clone(FX.draft))
if (kitsView === 'all') mod.showAllStarters()
const page = contributions.find(c => c.area === 'routes')
const nav = contributions.filter(c => c.area === 'sidebar.nav')
const CORE = [['New session', 'robot'], ['Capabilities', 'extensions'], ['Messaging', 'comment'], ['Kanban', 'layout'], ['Scheduled jobs', 'watch']]
function Shell() {
  return jsxs('div', { className: 'hb-window', children: [
    jsx('div', { className: 'hb-titlebar', children: jsxs('div', { className: 'hb-lights', children: [jsx('span', {}), jsx('span', {}), jsx('span', {})] }) }),
    jsxs('div', { className: 'hb-body', children: [
      jsxs('nav', { className: 'hb-sidebar', children: [
        ...CORE.map(([l, i]) => jsxs('div', { className: 'hb-nav', children: [jsx('i', { className: `codicon codicon-${i}` }), l] }, l)),
        ...nav.map(n => jsxs('div', { className: 'hb-nav hb-nav-active', children: [jsx('i', { className: `codicon codicon-${n.data.codicon}` }), n.data.label] }, n.id)),
      ] }),
      jsx('main', { className: 'hb-main', style: { overflow: 'hidden', height: '100%' }, children: page.render() }),
    ] }),
  ] })
}
createRoot(document.getElementById('root')).render(jsx(Shell, {}))
try { await document.fonts.load('16px codicon') } catch (e) { /* icons may be missing */ }
await pause(1500)
const click = t => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim().startsWith(t)); if (b) b.click(); return b }
if (scene === 'flagged') { click('1 number not found'); await pause(600) }
if (scene === 'ask') { click('Ask about these sources'); await pause(500) }
if (params.get('open') === 'export') { click('Export'); await pause(200) }
// route  an import route's label start (e.g. keynote): open it on the import panel
if (params.get('route')) { const want = params.get('route').toLowerCase(); const b = [...document.querySelectorAll('.imp-route')].find(x => x.textContent.toLowerCase().startsWith(want)); if (b) b.click(); await pause(200) }
// trace  a number as written (412, 3,600) or "missing": focus that traced number in the given proof slot, opening its card
if (params.get('trace')) {
  const want = params.get('trace')
  const slot = Number(params.get('slot') || 0)
  const sheets = [...document.querySelectorAll('.imp-proof')]
  const nums = [...(sheets[slot] || document).querySelectorAll('.ip-num')]
  const el = want === 'missing' ? nums.find(n => n.classList.contains('is-missing')) : nums.find(n => n.firstChild && n.firstChild.textContent === want)
  if (el) { el.scrollIntoView({ block: 'center' }); await pause(100); el.focus({ preventScroll: true }) }
  await pause(400)
}
if (kitsView === 'site') {
  // show the draft the site reader made
}
await pause(900)
// audit=1: measure the rendered page for the design floors (no text under 12px, no emoji) and write the result
// to <html data-audit>, which `--dump-dom` prints.
if (params.get('audit')) {
  const small = []
  let min = 99
  for (const el of document.querySelectorAll('.imp *')) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
    // hb-* are the harness's stand-ins for the host's own SDK controls (Button, SegmentedControl): the host sizes those.
    if (!own || !el.getClientRects().length || el.closest('.hb-btn,.hb-seg,.hb-seg-btn,.hb-input,.hb-textarea')) continue
    const px = parseFloat(getComputedStyle(el).fontSize)
    min = Math.min(min, px)
    if (px < 11.95) small.push(`${el.className || el.tagName}: ${px}px "${el.textContent.trim().slice(0, 30)}"`)
  }
  const emoji = (document.querySelector('.imp').innerText.match(/\p{Extended_Pictographic}/gu) || []).length
  document.documentElement.dataset.audit = JSON.stringify({ min, small: small.slice(0, 12), emoji })
}
document.documentElement.dataset.ready = '1'
