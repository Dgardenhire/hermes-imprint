// Loading, empty, error and not-connected states. Designed, never a bare line of text.

import { jsx, jsxs } from 'react/jsx-runtime'
import { Button, Codicon, ErrorState, PanelEmpty, Skeleton } from '@hermes/plugin-sdk'
import { describeError, isOffline } from './helpers.js'
import { Card, Details, Notice } from './primitives.js'

/* ------------------------------------------------------------------ skeletons -- */

function Bone({ className, style }) {
  return jsx(Skeleton, { className: `hk-skel ${className || 'hk-skel-line'}`, style })
}

/**
 * A card-shaped placeholder. `shape` describes the real card it stands in for:
 *   { title: true, lines: 2, steps: 4, cells: 0, button: true, dot: false }
 */
export function SkeletonCard({ shape = {} }) {
  const { title = true, lines = 2, steps = 0, cells = 0, button = false, dot = false, tone } = shape
  const widths = ['92%', '78%', '64%', '84%']
  return jsxs(Card, { tone, 'aria-hidden': 'true', children: [
    title ? jsxs('div', { className: 'hk-row', children: [dot ? jsx(Bone, { className: 'hk-skel-dot' }) : null, jsx(Bone, { className: 'hk-skel-title' })] }) : null,
    steps ? jsx('div', { style: { display: 'grid', gridTemplateColumns: `repeat(${steps}, 1fr)`, gap: 6, justifyItems: 'center', padding: '4px 0' },
      children: Array.from({ length: steps }, (_, i) => jsx(Bone, { className: 'hk-skel-dot' }, i)) }) : null,
    ...Array.from({ length: lines }, (_, i) => jsx(Bone, { style: { width: widths[i % widths.length] } }, `l${i}`)),
    cells ? jsx('div', { className: 'hk-row', style: { gap: 3 }, children: Array.from({ length: cells }, (_, i) =>
      jsx(Bone, { style: { width: 12, height: 12, minHeight: 12 } }, i)) }) : null,
    button ? jsx('div', { className: 'hk-actions', children: jsx(Bone, { className: 'hk-skel-btn' }) }) : null,
  ] })
}

/** Rows of a list: a dot, a title line and a detail line each. */
export function SkeletonList({ rows = 4 }) {
  return jsx('div', { className: 'hk-stack', 'aria-hidden': 'true', children: Array.from({ length: rows }, (_, i) =>
    jsxs('div', { className: 'hk-row', style: { padding: '6px 8px', flexWrap: 'nowrap' }, children: [
      jsx(Bone, { className: 'hk-skel-dot' }),
      jsxs('div', { className: 'hk-grow hk-stack', style: { gap: 5 }, children: [
        jsx(Bone, { style: { width: `${60 - (i % 3) * 10}%` } }),
        jsx(Bone, { style: { width: `${40 + (i % 2) * 15}%`, height: 8, minHeight: 8 } }),
      ] }),
    ] }, i)) })
}

/**
 * A whole page while its first answer loads: a header block and the card shapes
 * given. The live region says what is loading for screen readers.
 */
export function SkeletonPage({ label = 'Loading', cards = [{}, {}], header = true }) {
  return jsxs('div', { className: 'hk-stack', style: { gap: 14 }, children: [
    jsx('span', { className: 'hk-sr', role: 'status', 'aria-live': 'polite', children: label }),
    header ? jsxs('div', { className: 'hk-stack', 'aria-hidden': 'true', style: { gap: 6 }, children: [
      jsx(Bone, { style: { width: 180, height: 18, minHeight: 18 } }),
      jsx(Bone, { style: { width: '62%' } }),
    ] }) : null,
    ...cards.map((shape, i) => jsx(SkeletonCard, { shape }, i)),
  ] })
}

/* ------------------------------------------------------------------ empty -- */

/** An empty list or screen: the app's PanelEmpty, with full-contrast words. */
export function Empty({ icon = 'inbox', title, body, action }) {
  return jsx(Card, { children: jsx(PanelEmpty, {
    icon,
    title: title ? jsx('span', { className: 'hk-ink', children: title }) : undefined,
    description: body ? jsx('span', { className: 'hk-ink', style: { fontSize: 12 }, children: body }) : undefined,
    action,
  }) })
}

/* ------------------------------------------------------------------ errors -- */

function TechDetails({ error }) {
  if (!error) return null
  const { status, detail } = describeError(error)
  if (!detail && !status) return null
  return jsx(Details, { label: 'Technical details', children: jsx('p', { className: 'hk-mono', children: status ? `${status}: ${detail}` : detail }) })
}

/**
 * Something failed. The app's ErrorState, with the reason in plain words, a retry,
 * and the raw error folded under Technical details.
 */
export function Failure({ title, body, error, onRetry, retryLabel = 'Try again', children }) {
  return jsx('div', { className: 'hk-state hk-enter', role: 'alert', children: jsx(ErrorState, {
    title,
    description: body ? jsx('p', { className: 'hk-state-body', children: body }) : undefined,
    children: jsxs('div', { className: 'hk-stack', style: { justifyItems: 'center' }, children: [
      children || null,
      onRetry ? jsx(Button, { variant: 'secondary', onClick: onRetry, children: retryLabel }) : null,
      jsx(TechDetails, { error }),
    ] }),
  }) })
}

/**
 * The plugin's backend isn't answering. `steps` say how to turn it on; when the error
 * is something else, `otherwise` explains instead.
 */
export function NotConnected({ name, error, onRetry, steps, otherwise }) {
  const off = !error || isOffline(error)
  return jsx(Card, { tone: 'bad', tint: true, className: 'hk-enter', role: 'alert', children: jsxs('div', { className: 'hk-banner', children: [
    jsx('span', { className: 'hk-badge-icon', 'data-tone': 'bad', children: jsx(Codicon, { name: 'plug', size: 16 }) }),
    jsxs('div', { className: 'hk-grow hk-stack', children: [
      jsx('h2', { className: 'hk-h2', children: `${name} isn’t connected` }),
      off ? (steps || null) : jsx('p', { children: otherwise || `${name} couldn’t reach its engine. Try again.` }),
      onRetry ? jsx('div', { className: 'hk-actions', children: jsx(Button, { variant: 'secondary', onClick: onRetry, children: 'Try again' }) }) : null,
      jsx(TechDetails, { error }),
    ] }),
  ] }) })
}

/** Data is on screen but the last refresh failed: say so without blanking the page. */
export function StaleNotice({ error, updatedAt, onRetry }) {
  if (!error) return null
  const when = updatedAt ? new Date(updatedAt).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' }) : ''
  return jsx(Notice, { tone: 'warn', icon: 'debug-disconnect', live: true,
    title: when ? `Showing what was true at ${when}` : 'Showing the last answer',
    action: onRetry ? jsx(Button, { variant: 'secondary', size: 'sm', onClick: onRetry, children: 'Refresh' }) : null,
    children: `The latest refresh didn’t come back. ${describeError(error).detail || ''}`.trim() })
}
