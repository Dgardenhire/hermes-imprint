// Pure helpers. No imports, so node tests can load this file directly.

/**
 * Turn whatever ctx.rest threw into { status, detail }. Hermes rejects with messages like
 * `404: {"detail":"Not Found"}`; FastAPI puts the reason in `detail`, sometimes as an object.
 */
export function describeError(error) {
  const message = String((error && error.message) || error || '')
  const match = message.match(/(\d{3}):\s*([\s\S]*)$/)
  if (!match) return { status: null, detail: message.trim() }
  let detail = match[2].trim()
  try {
    const body = JSON.parse(detail)
    if (body && body.detail !== undefined) detail = body.detail
  } catch (e) { /* plain text */ }
  if (detail && typeof detail === 'object') detail = detail.message || 'Something went wrong.'
  return { status: Number(match[1]), detail: String(detail || '') }
}

/** True when the plugin's backend isn't mounted or the bridge isn't up yet. */
export function isOffline(error) {
  const { status, detail } = describeError(error)
  return status === 404 || /bridge unavailable|starting up|still starting|not found/i.test(detail)
}

const SOFTEN_BASE = [
  [/\s(?:on|at)\s[0-9a-f]{7,40}\b/g, ''], // commit codes
  [/\s?\(?\bt_[0-9a-z]{6,}\)?/g, ''], // internal card ids
]

/**
 * Engine sentences, softened for a person: commit codes and internal ids removed,
 * spacing tidied. `rules` are extra [pattern, replacement] pairs applied first.
 */
export function soften(text, rules) {
  let out = String(text || '')
  for (const [pattern, replacement] of [...(rules || []), ...SOFTEN_BASE]) out = out.replace(pattern, replacement)
  return out.replace(/\s{2,}/g, ' ').trim()
}

/** "3 tests" / "1 test". */
export function plural(count, one, many) {
  return `${count} ${count === 1 ? one : many || `${one}s`}`
}

/** Cmd+Enter on macOS, Ctrl+Enter elsewhere, never an IME commit. */
export function isModEnter(event, isSubmitEnter) {
  const submit = typeof isSubmitEnter === 'function' ? isSubmitEnter(event) : event && event.key === 'Enter'
  return Boolean(submit && (event.metaKey || event.ctrlKey))
}

/** True when a keystroke belongs to a text field and single-letter shortcuts must stay out of it. */
export function isTyping(event) {
  const el = event && event.target
  if (!el || !el.tagName) return false
  const tag = el.tagName.toLowerCase()
  return tag === 'input' || tag === 'textarea' || tag === 'select' || Boolean(el.isContentEditable)
}

/** The modifier label for hints: the command symbol on macOS, Ctrl elsewhere. */
export function modKey() {
  const p = typeof navigator !== 'undefined' ? navigator.platform || navigator.userAgent || '' : ''
  return /mac|iphone|ipad/i.test(p) ? '⌘' : 'Ctrl'
}

/** Next index for list navigation, clamped (or wrapped when loop is set). */
export function stepIndex(index, delta, count, loop) {
  if (count <= 0) return -1
  if (index < 0) return delta > 0 ? 0 : count - 1
  const next = index + delta
  if (loop) return (next + count) % count
  return Math.max(0, Math.min(count - 1, next))
}

/** Ring geometry: circumference and dash offset for a 0..1 value. */
export function ringDash(value, radius) {
  const c = 2 * Math.PI * radius
  const v = Math.max(0, Math.min(1, Number(value) || 0))
  return { circumference: c, offset: c * (1 - v) }
}

/** Sparkline path for values in a w x h box (with the area under it). */
export function sparkPath(values, w, h) {
  const list = (values || []).map(Number).filter(v => Number.isFinite(v))
  if (list.length < 2) return { line: '', area: '', last: null }
  const min = Math.min(...list)
  const max = Math.max(...list)
  const span = max - min || 1
  const pts = list.map((v, i) => [(i / (list.length - 1)) * w, h - ((v - min) / span) * h])
  const line = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)} ${y.toFixed(2)}`).join(' ')
  return { line, area: `${line} L${w} ${h} L0 ${h} Z`, last: pts[pts.length - 1] }
}
