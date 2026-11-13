// Letterpress's error words and the job-check clock. No React, no SDK: tests drive it (tests/js/errors.test.mjs).
//
// A request that never reaches the backend (Hermes's plugin helper stopped, restarting or not up yet) comes back from
// the browser as "Failed to fetch", "Load failed", a timeout or a bare 502/503/504. None of that means anything to a
// person, so plainError() turns it into one plain sentence and leaves every sentence the backend wrote alone.
//
// pollClock() paces the checks on a running job: quick at first, then backing off; a missed check backs off harder,
// and after GIVE_UP_MS of nothing but misses it says to stop, so a dead backend ends in a message, not a spinner.

export const OFFLINE = 'Letterpress’s backend isn’t answering.'
export const OFFLINE_HELP = 'Wait a moment and try again. If it keeps happening, restart Hermes.'
export const POLL_GAVE_UP = 'Letterpress’s backend stopped answering, so Letterpress stopped checking on this. ' +
  'It may still finish: open Letterpress again in a minute, or restart Hermes if it stays stuck.'

const UNREACHABLE = /failed to fetch|load failed|networkerror|network error|network request failed|fetch failed|timed? ?out|timeout|aborted|aborterror|econnrefused|econnreset|bridge unavailable|starting up|still starting|not connected|socket hang up/i

// The same reading of an error as hermes-ui-kit's describeError ("<status>: <body>"), so this file runs on its own.
export function describe(error) {
  const message = error && typeof error === 'object' ? String(error.message || '') : String(error || '')
  const m = message.match(/(\d{3}):\s*([\s\S]*)$/)
  if (!m) return { status: null, detail: message.trim() }
  let detail = m[2].trim()
  try { const body = JSON.parse(detail); if (body && body.detail !== undefined) detail = body.detail } catch (e) { /* plain text */ }
  if (detail && typeof detail === 'object') detail = detail.message || ''
  return { status: Number(m[1]), detail: String(detail || '').trim() }
}

/** True when the request never got an answer from Letterpress's own backend. */
export function isUnreachable(error, read = describe) {
  const { status, detail } = read(error)
  if (status === 502 || status === 503 || status === 504) return true
  if (status === 404 && /^not found\.?$/i.test(detail)) return true // the backend isn't mounted; a route's own 404 says more
  if (status) return false
  return !detail || UNREACHABLE.test(detail) || (error && error.name === 'AbortError')
}

/** One plain sentence (or a few) for a person, always ending in a full stop or other closing mark. */
export function plainError(error, read = describe) {
  if (isUnreachable(error, read)) return OFFLINE
  const { detail } = read(error)
  const text = (detail || 'Something went wrong.').replace(/\s+/g, ' ').trim()
  return /[.!?…:)”"']$/.test(text) ? text : `${text}.`
}

export const FIRST_MS = 400
export const START_MS = 700
export const MAX_MS = 2500
export const MISS_MAX_MS = 8000
export const GIVE_UP_MS = 90000

/** The pace of checks on one job. ok() after an answer, miss() after a failed check; each returns the next wait. */
export function pollClock({ now = () => Date.now(), start = START_MS, max = MAX_MS, missMax = MISS_MAX_MS, giveUp = GIVE_UP_MS } = {}) {
  let delay = start
  let missDelay = start
  let missingSince = null
  return {
    first: FIRST_MS,
    ok() {
      missingSince = null
      missDelay = start
      delay = Math.min(delay * 1.3, max)
      return { delay, giveUp: false }
    },
    miss() {
      const t = now()
      if (missingSince === null) missingSince = t
      missDelay = Math.min(missDelay * 2, missMax)
      return { delay: missDelay, giveUp: t - missingSince >= giveUp }
    },
  }
}
