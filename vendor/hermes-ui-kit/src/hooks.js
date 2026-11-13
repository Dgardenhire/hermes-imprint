// Data and behavior hooks shared by the plugins.

import { useCallback, useEffect, useRef, useState } from 'react'
import { isSubmitEnter, useMutation, useQuery, useQueryClient } from '@hermes/plugin-sdk'
import { isModEnter, isTyping, stepIndex } from './helpers.js'

/**
 * A query that polls and never blanks the screen: the previous answer stays while a
 * new one loads, and a failed refresh keeps the last good data (`stale` is true).
 * `loading` is true only before the first answer.
 */
export function usePolled({ key, fn, interval = 0, enabled = true, staleTime, options }) {
  const q = useQuery({
    queryKey: key, queryFn: fn, enabled,
    refetchInterval: interval || false, staleTime,
    placeholderData: previous => previous,
    retry: 1,
    ...(options || {}),
  })
  const data = q.data
  return {
    data,
    error: q.error || null,
    loading: Boolean(q.isLoading && data === undefined),
    stale: Boolean(q.error && data !== undefined),
    refreshing: Boolean(q.isFetching),
    updatedAt: q.dataUpdatedAt || 0,
    refetch: () => q.refetch(),
  }
}

/**
 * A mutation that updates the cached query first and rolls back if the server says no.
 * `apply(old, vars)` returns the optimistic value; the query refetches when it settles.
 */
export function useOptimistic({ key, run, apply, onDone, onFail }) {
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: run,
    onMutate: async vars => {
      if (!apply || !key) return {}
      try { await qc.cancelQueries({ queryKey: key }) } catch (e) { /* nothing in flight */ }
      const previous = qc.getQueryData(key)
      if (previous !== undefined) qc.setQueryData(key, old => apply(old, vars))
      return { previous }
    },
    onError: (error, vars, context) => {
      if (key && context && context.previous !== undefined) qc.setQueryData(key, context.previous)
      if (onFail) onFail(error, vars)
    },
    onSuccess: (out, vars) => { if (onDone) onDone(out, vars) },
    onSettled: () => { if (key) qc.invalidateQueries({ queryKey: key }) },
  })
  return { run: m.mutateAsync, busy: m.isPending, error: m.error || null, vars: m.variables }
}

/**
 * Keyboard navigation over a list: j/k or the arrows move, Home/End jump, Enter opens,
 * Escape calls onEscape. Spread `keyProps` on the list's container (or the page) and
 * `itemProps(i)` on each row. Letter keys are ignored while typing in a field.
 */
export function useListKeys({ count, onOpen, onEscape, loop = false, initial = -1 }) {
  const [index, setIndex] = useState(initial)
  useEffect(() => { if (index >= count) setIndex(count - 1) }, [count])
  const onKeyDown = useCallback(e => {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return
    const typing = isTyping(e)
    let next = null
    if (e.key === 'ArrowDown' || (!typing && e.key === 'j')) next = stepIndex(index, 1, count, loop)
    else if (e.key === 'ArrowUp' || (!typing && e.key === 'k')) next = stepIndex(index, -1, count, loop)
    else if (!typing && e.key === 'Home') next = count ? 0 : -1
    else if (!typing && e.key === 'End') next = count - 1
    else if (e.key === 'Enter' && !typing && index >= 0 && onOpen) { e.preventDefault(); onOpen(index); return }
    else if (e.key === 'Escape' && onEscape) { e.preventDefault(); onEscape(); return }
    if (next !== null && !(typing && (e.key === 'ArrowDown' || e.key === 'ArrowUp'))) { e.preventDefault(); setIndex(next) }
  }, [index, count, loop, onOpen, onEscape])
  const itemProps = i => ({
    'data-active': i === index ? '' : undefined,
    'aria-selected': i === index,
    ref: el => { if (el && i === index && typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'nearest' }) },
    onMouseMove: () => { if (i !== index) setIndex(i) },
  })
  return { index, setIndex, keyProps: { onKeyDown }, itemProps }
}

/**
 * Page-level keys. `bindings` maps a key to a handler: a single key ('n', '/', 'Escape')
 * or 'mod+Enter'. Letters never fire while typing; Escape and mod+Enter do.
 * Returns an onKeyDown for the page root.
 */
export function useKeys(bindings) {
  const ref = useRef(bindings)
  ref.current = bindings
  return useCallback(e => {
    const b = ref.current || {}
    if (e.defaultPrevented) return
    if (b['mod+Enter'] && isModEnter(e, isSubmitEnter)) { e.preventDefault(); b['mod+Enter'](e); return }
    if (e.metaKey || e.ctrlKey || e.altKey) return
    if (e.key === 'Escape' && b.Escape) { b.Escape(e); return }
    if (isTyping(e)) return
    const fn = b[e.key]
    if (fn) { e.preventDefault(); fn(e) }
  }, [])
}

/** Cmd+Enter (Ctrl+Enter) inside one field submits it. Spread onto a Textarea or Input. */
export function submitOnModEnter(submit) {
  return { onKeyDown: e => { if (isModEnter(e, isSubmitEnter)) { e.preventDefault(); submit() } } }
}

/** [ref, width] for an element, kept current with a ResizeObserver. */
export function useContainerWidth() {
  const [width, setWidth] = useState(0)
  const observer = useRef(null)
  const ref = useCallback(el => {
    if (observer.current) { observer.current.disconnect(); observer.current = null }
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(entries => {
      const w = entries[0] && entries[0].contentRect ? Math.round(entries[0].contentRect.width) : 0
      setWidth(prev => (prev === w ? prev : w))
    })
    ro.observe(el)
    observer.current = ro
  }, [])
  return [ref, width]
}

/** True when the person asked the system for less motion. */
export function useReducedMotion() {
  const query = '(prefers-reduced-motion: reduce)'
  const get = () => (typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : false)
  const [reduced, setReduced] = useState(get)
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined
    const mq = window.matchMedia(query)
    const on = () => setReduced(mq.matches)
    mq.addEventListener ? mq.addEventListener('change', on) : mq.addListener(on)
    return () => (mq.removeEventListener ? mq.removeEventListener('change', on) : mq.removeListener(on))
  }, [])
  return reduced
}

/**
 * Remember that something just finished, for a one-shot completion pulse: returns true
 * for `ms` after `value` changes to something truthy it wasn't before.
 */
export function useJustChanged(value, ms = 1400) {
  const [on, setOn] = useState(false)
  const last = useRef(value)
  useEffect(() => {
    if (value && value !== last.current) {
      setOn(true)
      const t = setTimeout(() => setOn(false), ms)
      last.current = value
      return () => clearTimeout(t)
    }
    last.current = value
    return undefined
  }, [value])
  return on
}

/** Focus the page root on mount when nothing else has focus, so its keys work at once. */
export function useFocusOnMount(ref) {
  useEffect(() => {
    const el = ref && ref.current
    if (!el || typeof document === 'undefined') return
    const active = document.activeElement
    if (!active || active === document.body) {
      try { el.focus({ preventScroll: true }) } catch (e) { /* not focusable */ }
    }
  }, [])
}
