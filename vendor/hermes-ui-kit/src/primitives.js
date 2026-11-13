// Layout and data primitives. Plain ESM with jsx() calls, like the plugins themselves.

import { useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'
import { Codicon, DisclosureCaret, KbdGroup, RowButton } from '@hermes/plugin-sdk'
import { ringDash, sparkPath } from './helpers.js'

const cx = (...parts) => parts.filter(Boolean).join(' ')

/* ------------------------------------------------------------------ layout -- */

/**
 * The page root: theme tokens, scroll container, keyboard target. `width` is
 * wide (1040px), narrow (760px) or full. `onKeyDown` receives keys from anywhere
 * inside the page. `motion` false turns every animation off.
 */
export function Page({ width = 'wide', className, onKeyDown, motion = true, top, children, rootRef, label }) {
  return jsxs('div', {
    ref: rootRef, className: cx('hk', 'hk-page', className), 'data-width': width, 'data-motion': motion ? undefined : 'off',
    tabIndex: -1, onKeyDown, role: 'region', 'aria-label': label,
    children: [top || null, jsx('div', { className: 'hk-page-inner', children })],
  })
}

/** Title block: eyebrow, one h1, a lead sentence, actions on the right. */
export function PageHeader({ eyebrow, title, lead, actions, back }) {
  return jsxs('header', { className: 'hk-head hk-enter', children: [
    back || null,
    eyebrow ? jsx('div', { className: 'hk-eyebrow', children: eyebrow }) : null,
    jsxs('div', { className: 'hk-head-row', children: [
      jsx('h1', { className: 'hk-h1 hk-grow', children: title }),
      actions ? jsx('div', { className: 'hk-actions', children: actions }) : null,
    ] }),
    lead ? jsx('p', { className: 'hk-lead', children: lead }) : null,
  ] })
}

export function Section({ title, count, actions, hint, children, className, id }) {
  return jsxs('section', { className: cx('hk-section', className), 'aria-labelledby': id, children: [
    title ? jsxs('div', { className: 'hk-section-head', children: [
      jsx('h2', { className: 'hk-h2', id, children: title }),
      count === undefined || count === null ? null : jsx('span', { className: 'hk-count', children: String(count) }),
      jsx('span', { className: 'hk-grow' }),
      actions || null,
    ] }) : null,
    hint ? jsx('p', { className: 'hk-small', children: hint }) : null,
    children,
  ] })
}

/** A flat card. `tone` adds a left rule, `tint` washes the background in that tone. */
export function Card({ tone, tint, flush, active, className, children, onClick, as = 'div', ...rest }) {
  return jsx(as, {
    className: cx('hk-card', onClick && 'hk-card-click', className),
    'data-tone': tone || undefined, 'data-tint': tint ? '' : undefined, 'data-flush': flush ? '' : undefined,
    'data-active': active ? '' : undefined, onClick, ...rest, children,
  })
}

/** A card that is one big click target (a real button), for cards with no buttons inside. */
export function CardButton({ tone, active, className, children, onClick, ...rest }) {
  return jsx(RowButton, {
    className: cx('hk-card', 'hk-card-click', className), 'data-tone': tone || undefined,
    'data-active': active ? '' : undefined, onClick, ...rest, children,
  })
}

export function Stat({ label, value, sub, tone }) {
  return jsxs('div', { className: 'hk-stat', 'data-tone': tone || undefined, children: [
    jsx('span', { className: 'hk-stat-label', children: label }),
    jsx('span', { className: 'hk-stat-value', children: value }),
    sub ? jsx('span', { className: 'hk-stat-sub', children: sub }) : null,
  ] })
}

/** A small status label. Tones: good, warn, bad, info, idle. */
export function Pill({ tone = 'idle', icon, dot, children, className }) {
  return jsxs('span', { className: cx('hk-pill', className), 'data-tone': tone, children: [
    icon ? jsx(Codicon, { name: icon, size: 12 }) : dot ? jsx('span', { className: 'hk-pill-dot' }) : null,
    children,
  ] })
}

/** A thin progress bar with an optional label row. */
export function Meter({ value = 0, max = 1, tone = 'info', label, detail }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0
  return jsxs('div', { className: 'hk-meter', 'data-tone': tone, children: [
    label || detail ? jsxs('div', { className: 'hk-meter-row', children: [jsx('span', { children: label }), jsx('span', { children: detail })] }) : null,
    jsx('div', { className: 'hk-meter-track', role: 'progressbar', 'aria-valuemin': 0, 'aria-valuemax': max, 'aria-valuenow': value,
      'aria-label': typeof label === 'string' ? label : undefined,
      children: jsx('div', { className: 'hk-meter-fill', style: { width: `${pct}%` } }) }),
  ] })
}

/**
 * Steps in a row, joined by an SVG rail. `at` is the current step's index (-1 for
 * none); `done` marks every step past. `working` draws the spinning arc on the
 * current step, for while something is happening there. `select` turns it into a
 * scale with one stop lit and nothing marked as done (where an answer landed).
 */
export function Stepper({ steps, at = -1, done = false, tone = 'info', working = false, compact = false, label, select = false }) {
  const n = steps.length
  const state = i => (select ? (i === at ? 'now' : 'later') : done || i < at ? 'past' : i === at ? 'now' : 'later')
  return jsxs('ol', { className: 'hk-stepper', 'data-compact': compact ? '' : undefined, style: { '--hk-n': n },
    'aria-label': label, children: [
      jsx('svg', { className: 'hk-step-rail', viewBox: '0 0 100 2', preserveAspectRatio: 'none', 'aria-hidden': 'true', children:
        steps.slice(0, -1).map((s, i) => jsx('line', {
          // A segment is walked once the step it leads to is reached.
          className: !select && (done || i + 1 <= at) ? 'hk-rail-past' : 'hk-rail-later',
          x1: ((i + 0.5) / n) * 100, x2: ((i + 1.5) / n) * 100, y1: 1, y2: 1,
        }, s.id || i)) }),
      ...steps.map((s, i) => {
        const st = state(i)
        return jsxs('li', { className: 'hk-step', 'data-state': st, 'data-tone': st === 'now' ? tone : undefined,
          'aria-current': st === 'now' ? 'step' : undefined, children: [
            jsxs('span', { className: 'hk-step-node', children: [
              st === 'now' && working ? jsx('span', { className: 'hk-arc', 'aria-hidden': 'true' }) : null,
              jsx(Codicon, { name: st === 'past' ? 'check' : s.icon || 'circle-small', size: compact ? 12 : 15 }),
            ] }),
            jsx('span', { className: 'hk-step-title', children: s.title }),
            !compact && s.line ? jsx('span', { className: 'hk-step-line', children: s.line }) : null,
            jsx('span', { className: 'hk-sr', children: st === 'past' ? ' (done)' : st === 'now' ? (select ? ' (this one)' : ' (current)') : '' }),
          ] }, s.id || i)
      }),
    ] })
}

/** A progress ring (SVG, currentColor). `label` is drawn in the middle. */
export function Ring({ value = 0, size = 40, stroke = 4, tone = 'info', label, title }) {
  const r = (size - stroke) / 2
  const { circumference, offset } = ringDash(value, r)
  return jsxs('span', { className: 'hk-ring', 'data-tone': tone, style: { width: size, height: size },
    role: 'img', 'aria-label': title || (typeof label === 'string' ? label : undefined), children: [
      jsxs('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}`, 'aria-hidden': 'true', children: [
        jsx('circle', { className: 'hk-ring-track', cx: size / 2, cy: size / 2, r, strokeWidth: stroke }),
        jsx('circle', { className: 'hk-ring-arc', cx: size / 2, cy: size / 2, r, strokeWidth: stroke,
          strokeDasharray: circumference.toFixed(2), strokeDashoffset: offset.toFixed(2) }),
      ] }),
      label !== undefined ? jsx('span', { className: 'hk-ring-label', 'aria-hidden': 'true', children: label }) : null,
    ] })
}

/** A tiny line chart (SVG, currentColor). */
export function Sparkline({ values, width = 80, height = 20, tone = 'info', title }) {
  const { line, area, last } = sparkPath(values, width, height)
  if (!line) return null
  return jsxs('svg', { className: 'hk-spark', 'data-tone': tone, width, height, viewBox: `0 0 ${width} ${height}`,
    role: 'img', 'aria-label': title, children: [
      jsx('path', { className: 'hk-spark-area', d: area }),
      jsx('path', { d: line }),
      last ? jsx('circle', { cx: last[0], cy: last[1], r: 2, fill: 'currentColor' }) : null,
    ] })
}

/**
 * One row of cells (SVG). Each cell is { state: pass|fail|unsure|wait, label, key }.
 * With `onPick`, cells are focusable buttons (Enter or Space picks); `selected` is the
 * picked key.
 */
export function HeatStrip({ cells, cell = 12, gap = 3, selected, onPick, label, wrap = 0 }) {
  const perRow = wrap > 0 ? wrap : cells.length
  const rows = Math.max(1, Math.ceil(cells.length / Math.max(1, perRow)))
  const width = Math.max(0, Math.min(cells.length, perRow) * (cell + gap) - gap)
  const height = rows * (cell + gap) - gap
  // One unit of padding on every side so the selection outline isn't clipped; the box matches
  // the viewBox exactly, so cells keep their size and sit flush with the text beside them.
  return jsx('svg', { className: 'hk-heat', width: width + 2, height: height + 2, viewBox: `-1 -1 ${width + 2} ${height + 2}`,
    role: onPick ? 'group' : 'img', 'aria-label': label, children: cells.map((c, i) => {
      const key = c.key !== undefined ? c.key : i
      const pickable = Boolean(onPick && c.state !== 'wait')
      return jsx('rect', {
        className: cx(`hk-cell-${c.state || 'wait'}`, pickable && 'hk-cell-pick', selected !== undefined && selected === key && 'hk-cell-sel'),
        x: (i % perRow) * (cell + gap), y: Math.floor(i / perRow) * (cell + gap), width: cell, height: cell, rx: 2.5,
        role: pickable ? 'button' : undefined, tabIndex: pickable ? 0 : undefined, 'aria-label': c.label,
        'aria-pressed': pickable ? selected === key : undefined,
        onClick: pickable ? () => onPick(key) : undefined,
        onKeyDown: pickable ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPick(key) } } : undefined,
        children: c.label ? jsx('title', { children: c.label }) : null,
      }, key)
    }) })
}

/* ------------------------------------------------------------------ small pieces -- */

/** A disclosure: the app's caret, a real button with aria-expanded, content below. */
export function Details({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return jsxs('div', { className: 'hk-disclosure', children: [
    jsxs('button', { type: 'button', className: 'hk-disclose', 'aria-expanded': open, onClick: () => setOpen(!open), children: [
      jsx(DisclosureCaret, { open }), label] }),
    open ? jsx('div', { className: 'hk-disclose-body hk-enter', children }) : null,
  ] })
}

/** Label, control, optional hint. */
export function Field({ label, hint, children }) {
  return jsxs('label', { className: 'hk-field', children: [
    label ? jsx('span', { className: 'hk-field-label', children: label }) : null,
    children,
    hint ? jsx('span', { className: 'hk-field-hint', children: hint }) : null,
  ] })
}

export function Facts({ rows }) {
  return jsx('dl', { className: 'hk-facts', children: rows.filter(Boolean).flatMap((r, i) => [
    jsx('dt', { children: r.label }, `t${i}`),
    jsx('dd', { className: r.mono ? 'hk-mono' : undefined, children: r.value }, `d${i}`),
  ]) })
}

/** A keyboard hint: <KeyHint keys={['⌘', '↵']} label="to send" />. */
export function KeyHint({ keys, label }) {
  return jsxs('span', { className: 'hk-keys', children: [
    jsx(KbdGroup, { keys, size: 'sm' }),     // the real KbdGroup renders its own keys and needs `keys: string[]`
    label ? jsx('span', { children: label }) : null,
  ] })
}

/** The way back, with its Esc hint. */
export function Back({ label = 'Back', onClick, hint = true }) {
  return jsxs('div', { className: 'hk-row', children: [
    jsxs('button', { type: 'button', className: 'hk-back', onClick, children: [jsx(Codicon, { name: 'arrow-left', size: 13 }), label] }),
    hint ? jsx(KeyHint, { keys: ['Esc'] }) : null,
  ] })
}

/** An inline message in a tone, with an icon. */
export function Notice({ tone = 'info', icon, title, children, action, live }) {
  const fallback = { good: 'pass-filled', warn: 'warning', bad: 'error', info: 'info', idle: 'info' }[tone]
  return jsxs('div', { className: 'hk-notice', 'data-tone': tone, role: live ? 'status' : undefined, 'aria-live': live ? 'polite' : undefined, children: [
    jsx(Codicon, { name: icon || fallback, size: 14 }),
    jsxs('div', { className: 'hk-grow hk-stack', style: { gap: 2 }, children: [
      title ? jsx('strong', { children: title }) : null,
      children ? jsx('div', { children }) : null,
    ] }),
    action || null,
  ] })
}

/** A tinted round icon, for banners. */
export function BadgeIcon({ name, tone = 'info', size = 16, pulse }) {
  return jsx('span', { className: cx('hk-badge-icon', pulse && 'hk-pulse'), 'data-tone': tone, children: jsx(Codicon, { name, size }) })
}

/** A small spinner in the current text color, for inline "working" labels. */
export function Spinner() {
  return jsx('span', { className: 'hk-spinner', 'aria-hidden': 'true' })
}
