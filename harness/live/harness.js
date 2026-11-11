// Live mode: renders desktop/plugin.js inside a Hermes-like window with ctx.rest going to the real backend
// (harness/live/server.py), so every button works. Open /harness/index.html?live=1. URL parameters:
//   tab    notebook | kits | storage            (default notebook)
//   theme  dark | light                         (default dark)
//   kit    the Studio's kit id                  (notebook) or the kit on the bench (kits=bench)
//   view   deck | visual | onepager | audio      (open the latest output of that kind in the viewer)
//   reader 1                                    (open the first answer's first citation in the source reader)
//   form   deck | visual | onepager | audio      (open that Studio form)
//   kits   grid | bench | site | guide | import | all
//   accent hex without #                       (red or green Hermes accent check)
//   trace  a number as written                  (focus it in the viewer so its trace card opens)
//   slow   milliseconds                         (hold every answer this long, like a cold Hermes backend)
import { createRoot } from 'react-dom/client'
import { jsx, jsxs } from 'react/jsx-runtime'

const params = new URLSearchParams(location.search)
const dark = params.get('theme') !== 'light'
document.documentElement.dataset.theme = dark ? 'dark' : 'light'
document.documentElement.classList.toggle('dark', dark)
// accent  a hex without # (e.g. e5484d for red, 30a46c for green), to check the page with a red or green Hermes accent
if (/^[0-9a-f]{6}$/i.test(params.get('accent') || '')) { for (const v of ['--ui-accent', '--dt-primary']) document.documentElement.style.setProperty(v, '#' + params.get('accent')) }

const SLOW = Math.max(0, Number(params.get('slow')) || 0)
async function rest(path, options = {}) {
  if (SLOW) await new Promise(r => setTimeout(r, SLOW))
  const init = { method: options.method || 'GET', headers: {} }
  if (options.upload) {
    const v = new Uint8Array(options.upload.bytes); let bin = ''
    for (let i = 0; i < v.length; i += 0x8000) bin += String.fromCharCode.apply(null, v.subarray(i, i + 0x8000))
    init.body = JSON.stringify({ filename: options.upload.filename, data: btoa(bin) }); init.headers['content-type'] = 'application/json'
  } else if (options.body !== undefined) { init.body = JSON.stringify(options.body); init.headers['content-type'] = 'application/json' }
  const r = await fetch('/api/' + path, init)
  const t = await r.text()
  if (!r.ok) throw new Error(r.status + ': ' + t)
  return JSON.parse(t)
}
const pause = ms => new Promise(r => setTimeout(r, ms))
const contributions = []
const ctx = {
  rest, registerMany(list) { contributions.push(...list) }, register(i) { contributions.push(i) },
  onEvent() { return () => {} }, onDispose() {}, setTimeout, setInterval,
  storage: { get: (k, f) => { try { const v = localStorage.getItem('imp:'+k); return v == null ? f : JSON.parse(v) } catch { return f } }, set(k, v) { localStorage.setItem('imp:'+k, JSON.stringify(v)) }, remove(k) { localStorage.removeItem('imp:'+k) } },
  os: { async revealPath() { return true } },
}
const mod = await import('../../desktop/plugin.js')
mod.default.register(ctx)
const tab = params.get('tab') || 'notebook'
mod.openTab(tab)
const kitsView = params.get('kits')
if (kitsView === 'bench') mod.openKit(params.get('kit') || 'counsel')
else if (params.get('kit')) mod.setKit(params.get('kit'))
if (kitsView === 'site' || kitsView === 'guide' || kitsView === 'import') mod.setKitMode(kitsView)
if (kitsView === 'all') mod.showAllStarters()
if (params.get('form')) mod.openForm(params.get('form'))
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
await pause(800)
if (params.get('view')) {
  const st = await rest('state')
  const o = (st.outputs || []).find(x => x.kind === params.get('view'))
  if (o) { mod.view(o.id); await pause(2500) }
}
if (params.get('reader')) {
  const c = (await rest('chats')).chats.find(x => x.role === 'assistant' && x.chips && x.chips.length)
  if (c) { mod.read(c.chips[0].source_id, c.chips[0].ref); await pause(900) }
}
if (params.get('trace')) {
  const want = params.get('trace')
  const el = [...document.querySelectorAll('.imp-viewer .ip-num')].find(n => n.firstChild && n.firstChild.textContent === want)
  if (el) { el.scrollIntoView({ block: 'center' }); await pause(100); el.focus({ preventScroll: true }); await pause(400) }
}
if (params.get('open') === 'kit') { const b = document.querySelector('.imp-kc-btn'); if (b) b.click(); await pause(300) }
if (params.get('open') === 'export') { const b = [...document.querySelectorAll('.imp-viewer button')].find(x => x.textContent.trim() === 'Export'); if (b) b.click(); await pause(300) }
document.documentElement.dataset.ready = '1'
