// Error words and the job-check clock (desktop/src/errors.js): run with `node --test tests/js/`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { GIVE_UP_MS, MAX_MS, MISS_MAX_MS, OFFLINE, POLL_GAVE_UP, isUnreachable, plainError, pollClock } from '../../desktop/src/errors.js'

test('a request that never reached the backend reads as one plain sentence, not the browser’s words', () => {
  for (const e of [new TypeError('Failed to fetch'), new TypeError('Load failed'), new Error('NetworkError when attempting to fetch resource.'),
    new Error('Request timed out'), Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' }),
    new Error('502: Bad Gateway'), new Error('503: {"detail": "Service Unavailable"}'), new Error('504: '), new Error('404: Not Found'),
    new Error('Plugin bridge unavailable'), new Error('Imprint is not connected.'), new Error('')]) {
    assert.equal(plainError(e), OFFLINE, String(e && e.message))
    assert.ok(isUnreachable(e))
  }
  assert.equal(`${plainError(new TypeError('Failed to fetch'))} Try again.`, 'Imprint’s backend isn’t answering. Try again.')
})

test('the backend’s own sentences pass through, always ending with a full stop', () => {
  assert.equal(plainError(new Error('400: {"detail": "Paste some text first."}')), 'Paste some text first.')
  assert.equal(plainError(new Error('404: {"detail": "That source is gone"}')), 'That source is gone.')
  assert.equal(plainError(new Error('409: {"detail": "Choose a brand first."}')), 'Choose a brand first.')
  assert.equal(plainError(new Error('500: {"detail": {"message": "Something broke"}}')), 'Something broke.')
  assert.equal(plainError(new Error('That did not start')), 'That did not start.')
  assert.ok(!isUnreachable(new Error('404: {"detail": "That source is gone."}')))
  assert.ok(!isUnreachable(new Error('400: {"detail": "That web address is too long."}')))
})

test('job checks back off while answered and stop after a long run of misses', () => {
  let t = 0
  const clock = pollClock({ now: () => t })
  let last = 0
  for (let i = 0; i < 20; i++) { const n = clock.ok(); assert.ok(n.delay >= last && n.delay <= MAX_MS); assert.equal(n.giveUp, false); last = n.delay }
  assert.equal(last, MAX_MS)
  // the backend goes away: misses back off harder, up to MISS_MAX_MS, and give up after GIVE_UP_MS of nothing but misses
  let n
  let waited = 0
  let checks = 0
  do { n = clock.miss(); checks++; if (!n.giveUp) { assert.ok(n.delay <= MISS_MAX_MS); waited += n.delay; t += n.delay } } while (!n.giveUp && checks < 1000)
  assert.equal(n.giveUp, true)
  assert.ok(waited >= GIVE_UP_MS && waited < GIVE_UP_MS + MISS_MAX_MS, String(waited))
  assert.ok(checks < 25, `bounded: ${checks} checks`)
})

test('one answer in the middle of the misses starts the count again', () => {
  let t = 0
  const clock = pollClock({ now: () => t })
  for (let i = 0; i < 5; i++) { clock.miss(); t += 20000 }
  clock.ok()
  const n = clock.miss()
  assert.equal(n.giveUp, false)
  assert.ok(n.delay < MISS_MAX_MS)
})

test('the give-up message says what happened and what to do, in plain words', () => {
  assert.match(POLL_GAVE_UP, /stopped answering/)
  assert.match(POLL_GAVE_UP, /restart Hermes/)
  assert.ok(!/fetch|poll|HTTP|error code/i.test(POLL_GAVE_UP))
})
