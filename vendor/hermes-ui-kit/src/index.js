// hermes-ui-kit: one look for Damon's Hermes desktop plugins.
//
// A desktop plugin may import only '@hermes/plugin-sdk', 'react' and 'react/jsx-runtime'
// (plugin-catalog/README.md rule 8), and plugins cannot import each other. So this kit is
// never installed on its own: scripts/build.mjs bundles it into each plugin's
// desktop/plugin.js with esbuild, and only the pieces a plugin uses ship.

export { KIT_CSS, KIT_VERSION } from './tokens.js'
export { installStyles } from './styles.js'
export {
  describeError, isModEnter, isOffline, isTyping, modKey, plural, ringDash, soften, sparkPath, stepIndex,
} from './helpers.js'
export {
  Back, BadgeIcon, Card, CardButton, Details, Facts, Field, HeatStrip, KeyHint, Meter, Notice, Page, PageHeader,
  Pill, Ring, Section, Sparkline, Spinner, Stat, Stepper,
} from './primitives.js'
export { Empty, Failure, NotConnected, SkeletonCard, SkeletonList, SkeletonPage, StaleNotice } from './states.js'
export {
  submitOnModEnter, useContainerWidth, useFocusOnMount, useJustChanged, useKeys, useListKeys, useOptimistic, usePolled,
  useReducedMotion,
} from './hooks.js'
export { registerPage } from './register.js'
