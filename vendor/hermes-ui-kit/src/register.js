// registerPage: the route, sidebar entry, palette commands, keybinds and status chip
// every plugin page repeats, in one call. Styles are installed on the way in and
// removed through ctx.onDispose.

import { KEYBINDS_AREA, PALETTE_AREA, ROUTES_AREA, SIDEBAR_NAV_AREA, STATUSBAR_AREAS, host } from '@hermes/plugin-sdk'
import { installStyles } from './styles.js'

/**
 * registerPage(ctx, {
 *   id: 'holdout-factory', route: '/factory', label: 'Factory', codicon: 'tools',
 *   render: () => jsx(Page, {}), css: PLUGIN_CSS,
 *   palette: [{ id, label, detail, keywords, run }],    // run defaults to opening the route
 *   keybinds: [{ id, label, defaults, run, category }],  // shown in the app's Keyboard settings
 *   status: { render, order, side: 'right' },
 *   extra: [contributions...],
 * })
 * Contribution ids are 'page', 'nav', palette ids as given ('open' for the first one
 * when none is given), 'kb:<id>' and 'status', so existing ids stay stable.
 */
export function registerPage(ctx, opts) {
  const { id, route, label, codicon, render, css, palette = [], keybinds = [], status, extra = [] } = opts
  installStyles(ctx, id, css)
  const open = () => host.navigate(route)
  const list = [
    { id: 'page', area: ROUTES_AREA, data: { path: route }, render },
    { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: route, label, codicon } },
    ...palette.map((p, i) => ({
      id: p.contributionId || (i === 0 ? 'open' : `palette-${i}`), area: PALETTE_AREA,
      data: { id: p.id, label: p.label, detail: p.detail, keywords: p.keywords, run: p.run || open },
    })),
    ...keybinds.map(k => ({
      id: `kb:${k.id}`, area: KEYBINDS_AREA,
      data: { id: k.id, label: k.label, category: k.category, defaults: k.defaults || [], run: k.run || open },
    })),
    ...(status ? [{ id: 'status', area: STATUSBAR_AREAS[status.side || 'right'], order: status.order, render: status.render }] : []),
    ...extra,
  ]
  return ctx.registerMany(list)
}
