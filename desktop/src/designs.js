// Letterpress designs: for a deck, a one-pager or a graphic, three designs of the same checked content side by side in the Studio.
// The person uses one whole, or picks slide by slide across the three (the deck's slide 3 from one design, slide 4 from
// another), then edits a line, revises in words, restores an earlier version and exports.
//
// Everything on screen comes from GET outputs/{id}/designs (docs/API-DESIGNS.md). The pictures are drawn by the backend in
// Chrome from markup the model wrote and Letterpress cleaned: this file shows pictures and plain text, never model markup.
// It never decides whether a number passes; it shows what the trace said. Imports: react, @hermes/plugin-sdk, hermes-ui-kit.

import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { Button, Codicon, Textarea } from '@hermes/plugin-sdk'
import { POLL_GAVE_UP, pollClock } from './errors.js'

const h = (t, p, ...k) => {
  const kids = k.flat().filter(x => x !== null && x !== undefined && x !== false)
  return kids.length > 1 ? jsxs(t, { ...(p || {}), children: kids }) : jsx(t, { ...(p || {}), children: kids[0] })
}
const cls = (...xs) => xs.filter(Boolean).join(' ')
const fmtElapsed = sec => (sec < 60 ? `${sec}s` : `${Math.floor(sec / 60)}m ${String(sec % 60).padStart(2, '0')}s`)
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`

const STATUS_WORDS = {
  missing: 'isn’t in your sources',
  unsourced: 'doesn’t name its source',
  moved: 'is cited to the wrong source',
}
const KIND_WORD = { deck: 'deck', onepager: 'one-pager', visual: 'graphic' }

export function DesignsRoom({ out, st, api, job, onDesign, onTemplate }) {
  const [view, setView] = useState(null)
  const [sel, setSel] = useState(1)
  const [big, setBig] = useState('')
  const [busy, setBusy] = useState('')
  const [apply, setApply] = useState(null) // a running edit or revise job
  const [ask, setAsk] = useState('')
  const [scope, setScope] = useState('slide')
  const [exportOpen, setExportOpen] = useState(false)
  const timer = useRef(null)
  const clock = useRef(null)
  const [lost, setLost] = useState(false) // the backend stopped answering while the designs drew: checks stopped
  const id = out.id
  const kind = (view && view.kind) || out.kind

  // While the designs draw, the view is checked every 2.2 s. A failed check is retried, backing off, and after about
  // a minute and a half of failures the room stops checking and says so (one message, not a toast every few seconds).
  const load = async ({ quiet } = {}) => {
    try {
      setView(await api.rest(`outputs/${id}/designs`))
      clock.current = null
      setLost(false)
    } catch (e) {
      if (!quiet) { api.toast(`${api.errText(e)} Try again.`, 'bad'); return }
      if (!clock.current) clock.current = pollClock()
      const next = clock.current.miss()
      if (next.giveUp) { clock.current = null; setLost(true); return }
      timer.current = setTimeout(() => load({ quiet: true }), next.delay)
    }
  }
  useEffect(() => { load(); return () => clearTimeout(timer.current) }, [id])
  const working = !!job || !!apply || (view && view.building)
  const noBrowser = !!(view && view.browser && !view.browser.ok)
  useEffect(() => {
    clearTimeout(timer.current)
    if (working && !lost) timer.current = setTimeout(() => load({ quiet: true }), 2200)
    return () => clearTimeout(timer.current)
  }, [working, view, lost])
  useEffect(() => { if (!job) load() }, [job ? job.id : null])

  const final = view && view.final
  const n = final ? Math.min(sel, final.slides.length) : 1
  useEffect(() => {
    let live = true
    setBig('')
    if (!final) return
    api.rest(`outputs/${id}/designs/slide/final/${n}`).then(r => { if (live) setBig(r.img) }).catch(() => {})
    return () => { live = false }
  }, [id, n, final ? final.slides.map(s => s.from).join() + final.label : '', view ? view.versions.length : 0, apply ? apply.id : ''])

  const pick = async body => {
    setBusy('pick')
    try { setView(await api.post(`outputs/${id}/designs/pick`, body)) } catch (e) { api.toast(`${api.errText(e)} Try again.`, 'bad') }
    setBusy('')
  }
  const useWhole = d => pick({ direction: d })
  const useSlide = (d, i) => {
    if (!final) return pick({ direction: d })
    const picks = final.slides.map(s => { const [fd, fi] = (s.from || '').split(':'); return { d: fd, i: Number(fi) } })
    picks[i - 1] = { d, i }
    return pick({ picks })
  }
  const run = async (path, body, said) => {
    try {
      const r = await api.post(`outputs/${id}/designs/${path}`, body)
      setApply(r.job)
      api.pollJob(r.job, async () => { setApply(null); await load(); if (said) api.toast(said, 'good') }, j => { setApply(null); api.toast(j.error || 'That did not finish. Try again.', 'bad') },
        j => setApply(j))
    } catch (e) { api.toast(`${api.errText(e)} Try again.`, 'bad') }
  }
  const doExport = async format => {
    setExportOpen(false)
    setBusy('export')
    try { const r = await api.post(`outputs/${id}/designs/export`, { format }); await api.save(r.path, r.name) } catch (e) { api.toast(api.errText(e), 'bad') }
    setBusy('')
  }

  const exportWhy = view && view.open_flags ? 'Fix or keep the numbers that aren’t in your sources first.' : !final ? 'Pick a design first.' : ''
  const opts = (view && view.options) || []
  const slide = final && final.slides[n - 1]
  const mine = new Set(final ? final.slides.map(s => s.from) : [])
  const whole = final && opts.find(o => final.slides.length === o.slides && final.slides.every((s, i) => s.from === `${o.d}:${i + 1}`))

  return h('div', { className: 'ip-ds', role: 'dialog', 'aria-label': 'Designs' },
    h('style', null, CSS),
    h('header', { className: 'ip-ds-head' },
      h(Button, { variant: 'secondary', onClick: api.close }, h(Codicon, { name: 'arrow-left', size: '14px' }), 'Back'),
      h('div', { className: 'ip-ds-title' }, h('strong', null, out.title || 'Untitled')),
      h('div', { className: 'ip-ds-grow' }),
      onTemplate ? h(Button, { variant: 'secondary', onClick: onTemplate }, 'Template version') : null,
      h(Button, { variant: 'secondary', disabled: !!working || noBrowser, onClick: onDesign }, h(Codicon, { name: 'refresh', size: '14px' }), view && view.made ? 'Design again' : 'Design three options'),
      h('div', { className: cls('ip-ds-export', exportWhy && 'is-held') },
        h(Button, { loading: busy === 'export', 'aria-disabled': exportWhy ? 'true' : undefined, 'aria-haspopup': 'menu', 'aria-expanded': exportOpen,
          onClick: () => { if (!exportWhy) setExportOpen(!exportOpen) } }, 'Export'),
        exportWhy ? h('span', { role: 'tooltip', className: 'ip-ds-why' }, exportWhy) : null,
        exportOpen && !exportWhy ? h('div', { className: 'ip-ds-menu', role: 'menu' },
          Object.entries((view && view.formats) || {}).map(([f, l]) => h('button', { key: f, type: 'button', role: 'menuitem', onClick: () => doExport(f) }, l))) : null)),
    job ? h('p', { className: 'ip-ds-step', role: 'status' }, h('span', { className: 'ip-ds-spin' }), job.step || 'Starting the designs') : null,
    !view ? h('p', { className: 'ip-ds-empty' }, 'Opening the designs') : null,
    noBrowser ? h('p', { className: 'ip-ds-bad ip-ds-nobrowser', role: 'alert' }, view.browser.message) : null,
    lost ? h('p', { className: 'ip-ds-bad', role: 'alert' }, POLL_GAVE_UP, ' ',
      h('button', { type: 'button', className: 'imp-linkish', onClick: () => { setLost(false); load() } }, 'Check again')) : null,
    view && !view.made && !working ? h('div', { className: 'ip-ds-empty' },
      h('p', null, 'Letterpress asks the model to lay this out three different ways, draws each one, looks at it, and fixes what is wrong. It takes a few minutes.'),
      h(Button, { disabled: noBrowser, onClick: onDesign }, 'Design three options')) : null,
    h('section', { className: 'ip-ds-options', 'aria-label': 'The three designs' }, opts.map(o => h('article', { key: o.d, className: cls('ip-ds-opt', whole && whole.d === o.d && 'is-used') },
      h('div', { className: 'ip-ds-opt-head' },
        h('strong', null, o.name),
        o.status === 'ready' ? h('span', { className: 'ip-ds-meta' }, plural(o.slides, kind === 'deck' ? 'slide' : 'page'),
          o.flags ? ` · ${plural(o.flags, 'number')} to check` : '', o.problems.length ? ` · ${plural(o.problems.length, 'layout problem')}` : '') : null),
      o.status === 'writing' ? h('p', { className: 'ip-ds-work' }, h('span', { className: 'ip-ds-spin' }), (o.step ? `${o.step}` : 'Waiting') + (o.elapsed ? ` · ${fmtElapsed(o.elapsed)}` : '')) : null,
      o.status === 'failed' ? h('p', { className: 'ip-ds-bad' }, o.error || 'This design did not come back.') : null,
      o.status === 'ready' ? h('div', { className: cls('ip-ds-thumbs', kind !== 'deck' && 'is-single') }, o.thumbs.map((t, i) =>
        t ? h('button', { key: i, type: 'button', className: cls('ip-ds-thumb', mine.has(`${o.d}:${i + 1}`) && 'is-in'), disabled: !!busy,
          'aria-label': kind === 'deck' ? `Use ${o.name} slide ${i + 1} in my deck` : `Use ${o.name}`, 'aria-pressed': mine.has(`${o.d}:${i + 1}`),
          title: kind === 'deck' ? `Use slide ${i + 1} from ${o.name}` : `Use ${o.name}`, onClick: () => (kind === 'deck' ? useSlide(o.d, i + 1) : useWhole(o.d)) },
        h('img', { src: t, alt: '', draggable: false }), kind === 'deck' ? h('span', { className: 'ip-ds-n' }, String(i + 1)) : null,
        mine.has(`${o.d}:${i + 1}`) ? h('span', { className: 'ip-ds-tick' }, h(Codicon, { name: 'check', size: '12px' })) : null) : null)) : null,
      o.status === 'ready' ? h(Button, { variant: whole && whole.d === o.d ? 'secondary' : 'primary', disabled: !!busy, onClick: () => useWhole(o.d) },
        whole && whole.d === o.d ? 'In use' : kind === 'deck' ? 'Use this whole design' : 'Use this design') : null))),
    final ? h('section', { className: 'ip-ds-mine', 'aria-label': 'Your result' },
      h('div', { className: 'ip-ds-mine-head' }, h('strong', null, kind === 'deck' ? `Your deck: ${final.label}` : `Your ${KIND_WORD[kind]}: ${final.label}`),
        kind === 'deck' ? h('span', { className: 'ip-ds-meta' }, 'Click any slide in a design above to put it in your deck at that number.') : null),
      kind === 'deck' ? h('div', { className: 'ip-ds-strip', role: 'tablist', 'aria-label': 'Slides in your deck' }, final.slides.map(s => h('button', { key: s.n, type: 'button', role: 'tab',
        'aria-selected': s.n === n, className: cls('ip-ds-mini', s.n === n && 'is-on'), onClick: () => setSel(s.n), 'aria-label': `Slide ${s.n}` },
      s.thumb ? h('img', { src: s.thumb, alt: '', draggable: false }) : null, h('span', { className: 'ip-ds-n' }, String(s.n)), h('span', { className: 'ip-ds-from' }, (s.from || '').replace(':', ' ').replace(/^./, c => c.toUpperCase()))))) : null,
      h('div', { className: 'ip-ds-work-area' },
        h('figure', { className: 'ip-ds-big' }, big ? h('img', { src: big, alt: `Slide ${n}`, draggable: false }) : h('span', { className: 'ip-ds-empty' }, 'Drawing'),
          working && apply ? h('figcaption', { className: 'ip-ds-step', role: 'status' }, h('span', { className: 'ip-ds-spin' }), (apply && apply.step) || 'Working') : null),
        h('div', { className: 'ip-ds-side' },
          h('div', { className: 'ip-ds-card' },
            h('h3', null, 'Revise'),
            h(Textarea, { value: ask, rows: 3, placeholder: 'Say what to change: “make the chart larger”, “warmer headline”', onChange: e => setAsk(e.target.value), 'aria-label': 'What to change' }),
            h('div', { className: 'ip-ds-row' },
              kind === 'deck' ? h('span', { className: 'ip-ds-seg', role: 'group', 'aria-label': 'Where to apply it' },
                h('button', { type: 'button', 'aria-pressed': scope === 'slide', className: cls(scope === 'slide' && 'is-on'), onClick: () => setScope('slide') }, `Slide ${n}`),
                h('button', { type: 'button', 'aria-pressed': scope === 'deck', className: cls(scope === 'deck' && 'is-on'), onClick: () => setScope('deck') }, 'Whole deck')) : null,
              h(Button, { disabled: !ask.trim() || !!apply, onClick: () => { run('revise', { instruction: ask.trim(), slide: kind === 'deck' && scope === 'slide' ? n : null }, 'Revised.'); setAsk('') } }, 'Revise'))),
          h('div', { className: 'ip-ds-card' },
            h('h3', null, 'Edit a line'),
            slide && slide.elements.length ? slide.elements.slice(0, 14).map(el => h(EditLine, { key: `${id}-${n}-${el.index}-${el.text}`, el, disabled: !!apply,
              onSave: text => run('edit', { slide: n, el: el.index, text }, 'Saved.') })) : h('p', { className: 'ip-ds-meta' }, 'No text on this slide to edit.')),
          h('div', { className: 'ip-ds-card' },
            h('h3', null, 'Numbers'),
            view.flags.length ? h('ul', { className: 'ip-ds-flags' }, view.flags.map(f => h('li', { key: `${f.key}-${f.slide}`, className: cls(f.kept && 'is-kept') },
              h('span', null, `Slide ${f.slide}: “${f.value}” ${STATUS_WORDS[f.status] || 'needs a look'}${f.status === 'moved' && f.found_in ? ` (it is in ${f.found_in})` : ''}.`),
              h('span', { className: 'ip-ds-row' },
                h(Button, { size: 'sm', variant: 'secondary', onClick: async () => { try { setView(await api.post(`outputs/${id}/designs/keep`, { key: f.key, on: !f.kept })) } catch (e) { api.toast(api.errText(e), 'bad') } } }, f.kept ? 'Kept on purpose' : 'Keep'),
                f.kept ? null : h(Button, { size: 'sm', disabled: !!apply, onClick: () => run('revise', { instruction: `The number “${f.value}” on slide ${f.slide} (${f.text.slice(0, 60)}) is ${STATUS_WORDS[f.status] || 'not supported'}. Fix it: use the figure the sources really give, cite the passage it is in, or remove it.`, slide: f.slide }, 'Fixed.') }, 'Fix it')))))
              : h('p', { className: 'ip-ds-meta ip-ds-good' }, final.counts && Object.keys(final.counts).length ? `All ${Object.values(final.counts).reduce((a, b) => a + b, 0)} numbers trace to your sources.` : 'No numbers to check.')),
          h('div', { className: 'ip-ds-card' },
            h('h3', null, 'Versions'),
            h('ul', { className: 'ip-ds-versions' }, view.versions.slice(0, 6).map((v, i) => h('li', { key: v.id }, h('span', null, v.label), i === 0 ? h('span', { className: 'ip-ds-meta' }, 'Now') :
              h(Button, { size: 'sm', variant: 'secondary', disabled: !!apply, onClick: () => run('restore', { version: v.id }) }, 'Restore')))))))) : null)
}

function EditLine({ el, onSave, disabled }) {
  const [v, setV] = useState(el.text)
  const dirty = v.trim() !== el.text && v.trim()
  return h('div', { className: 'ip-ds-edit' },
    h('input', { className: 'ip-ds-input', value: v, disabled, onChange: e => setV(e.target.value), 'aria-label': `Edit ${el.tag} text`,
      onKeyDown: e => { if (e.key === 'Enter' && dirty) onSave(v.trim()) } }),
    dirty ? h(Button, { size: 'sm', onClick: () => onSave(v.trim()) }, 'Save') : null)
}

const CSS = `
.ip-ds{grid-area:1/1/-1/-1;z-index:6;background:var(--hk-sunken);overflow:auto;display:flex;flex-direction:column;gap:16px;min-height:0;padding:0 0 32px;color:var(--hk-ink)}
.ip-ds *{box-sizing:border-box}
.ip-ds-head{position:sticky;top:0;z-index:4;display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:10px 18px;background:var(--hk-surface);border-bottom:1px solid var(--hk-stroke)}
.ip-ds-title{display:grid;min-width:200px}.ip-ds-title strong{font-size:14px}.ip-ds-title span{font-size:12px;opacity:.72}
.ip-ds-grow{flex:1}
.ip-ds-export{position:relative}.ip-ds-export.is-held [data-slot=button]{opacity:.55;cursor:not-allowed}
.ip-ds-why{position:absolute;right:0;top:100%;margin-top:6px;width:240px;padding:8px 10px;background:var(--hk-surface);border:1px solid var(--hk-stroke);font-size:12px;display:none;z-index:5}
.ip-ds-export.is-held:hover .ip-ds-why,.ip-ds-export.is-held:focus-within .ip-ds-why{display:block}
.ip-ds-menu{position:absolute;right:0;top:100%;margin-top:6px;min-width:220px;background:var(--hk-surface);border:1px solid var(--hk-stroke);display:grid;z-index:5}
.ip-ds-menu button{all:unset;cursor:pointer;padding:9px 12px;font-size:13px}.ip-ds-menu button:hover,.ip-ds-menu button:focus-visible{background:var(--hk-sunken)}
.ip-ds-step{display:flex;gap:8px;align-items:center;margin:0 18px;font-size:12.5px}
.ip-ds-spin{width:12px;height:12px;border-radius:50%;border:2px solid var(--hk-stroke-strong,var(--hk-stroke));border-top-color:var(--hk-accent);animation:ip-ds-spin 900ms linear infinite;flex:none}
@keyframes ip-ds-spin{to{transform:rotate(360deg)}}
.ip-ds-empty{margin:0 18px;display:grid;gap:10px;justify-items:start;font-size:13px}
.ip-ds-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;padding:0 18px;align-items:start}
.ip-ds-opt{display:grid;gap:8px;align-content:start;padding:12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r,2px);min-width:0}
.ip-ds-opt.is-used{border-color:var(--hk-accent)}
.ip-ds-opt-head{display:flex;justify-content:space-between;gap:8px;align-items:baseline;flex-wrap:wrap}.ip-ds-opt-head strong{font-size:14px}
.ip-ds-meta{font-size:12px;opacity:.78}
.ip-ds-work{display:flex;gap:8px;align-items:center;font-size:12.5px}.ip-ds-bad{font-size:12.5px;color:var(--hk-danger,#b3261e)}.ip-ds-good{color:var(--hk-success,#1e7a46);opacity:1}
.ip-ds-thumbs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;max-height:46vh;overflow:auto;padding:2px}
.ip-ds-thumbs.is-single{grid-template-columns:1fr;max-height:none}
.ip-ds-thumb{all:unset;cursor:pointer;position:relative;display:flex;flex-direction:column;border:1px solid var(--hk-stroke);background:#fff;line-height:0}
.ip-ds-thumb img{width:100%;height:auto;display:block}
.ip-ds-thumb:hover{border-color:var(--hk-stroke-strong,var(--hk-ink))}.ip-ds-thumb:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.ip-ds-thumb.is-in{outline:2px solid var(--hk-accent);outline-offset:-2px}
.ip-ds-n{position:static;display:block;align-self:stretch;min-height:22px;line-height:22px;font-size:12px;font-weight:600;padding:0 8px;background:var(--hk-surface);color:var(--hk-ink);border-top:1px solid var(--hk-stroke)}
.ip-ds-tick{position:absolute;right:4px;bottom:3px;line-height:1;padding:3px;background:var(--hk-accent);color:#fff;display:grid;place-items:center}
.ip-ds-mine{display:grid;gap:10px;padding:0 18px}
.ip-ds-mine-head{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.ip-ds-strip{display:flex;gap:8px;overflow:auto;padding:4px 2px}
.ip-ds-mini{all:unset;cursor:pointer;position:relative;flex:none;width:150px;border:1px solid var(--hk-stroke);background:#fff;line-height:0;display:flex;flex-wrap:wrap;align-items:center}
.ip-ds-mini img{flex:0 0 100%;width:100%;display:block}.ip-ds-mini .ip-ds-n{flex:0 0 auto;align-self:auto;border-top:1px solid var(--hk-stroke)}.ip-ds-mini.is-on{outline:2px solid var(--hk-accent);outline-offset:1px}.ip-ds-mini:focus-visible{outline:2px solid var(--hk-accent);outline-offset:2px}
.ip-ds-from{position:static;flex:1 1 0;min-width:0;min-height:22px;line-height:22px;font-size:12px;padding:0 6px;text-align:right;background:var(--hk-surface);color:var(--hk-ink);border-top:1px solid var(--hk-stroke);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.ip-ds-work-area{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(260px,1fr);gap:16px;align-items:start}
.ip-ds-big{margin:0;border:1px solid var(--hk-stroke);background:#fff;min-height:160px;display:grid;line-height:0;position:relative}
.ip-ds-big img{width:100%;height:auto;display:block}.ip-ds-big .ip-ds-empty{line-height:1.4;padding:24px;margin:0}
.ip-ds-big figcaption{position:absolute;left:8px;bottom:8px;background:var(--hk-surface);padding:6px 10px;line-height:1.3;margin:0}
.ip-ds-side{display:grid;gap:10px}
.ip-ds-card{display:grid;gap:8px;padding:12px;background:var(--hk-surface);border:1px solid var(--hk-stroke);border-radius:var(--imp-r,2px)}
.ip-ds-card h3{margin:0;font-size:13px;font-weight:600}
.ip-ds-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.ip-ds-seg{display:inline-flex;border:1px solid var(--hk-stroke)}.ip-ds-seg button{all:unset;cursor:pointer;padding:5px 10px;font-size:12px}.ip-ds-seg button.is-on{background:var(--hk-accent);color:#fff}.ip-ds-seg button:focus-visible{outline:2px solid var(--hk-accent);outline-offset:-2px}
.ip-ds-input{font:inherit;font-size:12.5px;padding:6px 8px;background:var(--hk-bg);color:var(--hk-ink);border:1px solid var(--hk-stroke);border-radius:var(--imp-r,2px);min-width:0}
.ip-ds-edit{display:flex;gap:6px;align-items:center}.ip-ds-edit .ip-ds-input{flex:1}
.ip-ds-flags,.ip-ds-versions{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.ip-ds-flags li,.ip-ds-versions li{display:grid;gap:6px;font-size:12.5px;line-height:1.4}.ip-ds-versions li{grid-template-columns:1fr auto;align-items:center}
.ip-ds-flags li.is-kept{opacity:.7}
@container (max-width: 1100px){.ip-ds-work-area{grid-template-columns:1fr}.ip-ds-options{grid-template-columns:1fr}}
@media (max-width: 1100px){.ip-ds-work-area{grid-template-columns:1fr}.ip-ds-options{grid-template-columns:1fr}}
`
