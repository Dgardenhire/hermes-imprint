// One shared <style> per key, reference-counted in the DOM itself.
//
// Each plugin bundles its own copy of the kit, so a module-level counter would give every
// plugin its own sheet. The count lives on the element instead: the first plugin to mount
// writes the kit sheet, every later one bumps data-hk-refs, and the last ctx.onDispose
// removes it. A plugin's own CSS gets a sheet under its own key the same way.

import { KIT_CSS, KIT_VERSION } from './tokens.js'

const ATTR = 'data-hermes-ui-kit'

function acquire(key, css) {
  const head = document.head
  let el = null
  for (const node of head.getElementsByTagName('style')) {
    if (node.getAttribute(ATTR) === key) { el = node; break }
  }
  if (!el) {
    el = document.createElement('style')
    el.setAttribute(ATTR, key)
    el.textContent = css
    head.append(el)
  }
  el.setAttribute('data-hk-refs', String(Number(el.getAttribute('data-hk-refs') || 0) + 1))
  let released = false
  return () => {
    if (released) return
    released = true
    const left = Number(el.getAttribute('data-hk-refs') || 1) - 1
    if (left <= 0) el.remove()
    else el.setAttribute('data-hk-refs', String(left))
  }
}

/**
 * Install the kit's sheet and, optionally, a plugin's own sheet. Returns a release
 * function, and hands the same function to ctx.onDispose when the host provides one.
 */
export function installStyles(ctx, pluginId, pluginCss) {
  if (typeof document === 'undefined' || !document.head) return () => {}
  const releases = [acquire(`kit@${KIT_VERSION}`, KIT_CSS)]
  if (pluginCss) releases.push(acquire(`plugin:${pluginId}`, pluginCss))
  const release = () => releases.splice(0).reverse().forEach(fn => fn())
  try { if (ctx && typeof ctx.onDispose === 'function') ctx.onDispose(release) } catch (e) { /* host without dispose */ }
  return release
}
