// Harness stand-in for the '@hermes/plugin-sdk' components the kit uses, so a plugin's
// desktop/plugin.js renders in a plain browser without Hermes. Copied into each plugin's
// harness/ by scripts/build.mjs; the plugin's own harness/sdk.js re-exports it and adds
// its own `host`.
//
// Names and props follow apps/desktop/src/sdk/index.ts and the components behind it.
// The look is approximated in kit-sdk-stub.css. The data layer is the real
// @tanstack/react-query at the app's version, through the harness import map.

import { QueryClient, useMutation as useTanstackMutation, useQuery as useTanstackQuery } from '@tanstack/react-query'
import { jsx, jsxs } from 'react/jsx-runtime'

export const ROUTES_AREA = 'routes'
export const SIDEBAR_NAV_AREA = 'sidebar.nav'
export const PALETTE_AREA = 'palette'
export const KEYBINDS_AREA = 'keybinds'
export const STATUSBAR_AREAS = { left: 'statusBar.left', right: 'statusBar.right' }
export const TRANSCRIPT_DIRECTIVE_AREA = 'transcript.directive'

export const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false } } })
export const useQuery = options => useTanstackQuery({ ...options, retry: false }, queryClient)
export const useMutation = options => useTanstackMutation(options, queryClient)
export const useQueryClient = () => queryClient

export function isSubmitEnter(event) {
  const native = event.nativeEvent || event
  return event.key === 'Enter' && !(native.isComposing || native.keyCode === 229)
}

export function Button({ variant = 'default', size = 'default', loading = false, className = '', children, disabled, ...rest }) {
  return jsx('button', {
    'data-slot': 'button', 'data-variant': variant, 'data-size': size, 'aria-busy': loading || undefined,
    className: `hb-btn ${className}`.trim(), disabled: disabled || loading, type: 'button', ...rest,
    children: loading
      ? jsxs('span', { className: 'hb-loading', children: [jsx('span', { className: 'hb-ghost', children }), jsx('span', { className: 'hb-spin' })] })
      : children,
  })
}

export function Codicon({ name, className = '', size, style, ...rest }) {
  return jsx('i', {
    'aria-hidden': 'true', className: `codicon codicon-${name} ${className}`.trim(),
    style: { ...(size != null && size !== '' ? { fontSize: size } : {}), ...style }, ...rest,
  })
}

export function RowButton({ type = 'button', ...props }) {
  return jsx('button', { 'data-slot': 'row-button', type, ...props })
}

export function Skeleton({ className = '', ...props }) {
  return jsx('div', { 'data-slot': 'skeleton', className: `hb-skeleton ${className}`.trim(), ...props })
}

export function Kbd({ children, className = '', size, ...props }) {
  return jsx('kbd', { 'data-slot': 'kbd', 'data-size': size || 'md', className: `hb-kbd ${className}`.trim(), ...props, children })
}

// Mirrors the real KbdGroup (components/ui/kbd.tsx): it needs `keys: string[]` and renders the keys itself.
// The old stand-in accepted children, which hid a crash that only showed up in real Hermes.
export function KbdGroup({ keys, size, className = '' }) {
  const label = keys.join(' ')
  return jsx('span', { 'data-slot': 'kbd-group', 'aria-label': label, className: `hb-kbd-group ${className}`.trim(),
    children: keys.map((k, i) => jsx('kbd', { key: `${k}-${i}`, 'data-slot': 'kbd', className: 'hb-kbd', children: k })) })
}

export function DisclosureCaret({ open, size = '0.75rem', className = '' }) {
  return jsx(Codicon, { name: 'chevron-right', size, className: `hb-caret ${open ? 'hb-caret-open' : ''} ${className}`.trim() })
}

export function Tip({ label, children }) {
  if (!label) return children
  return jsx('span', { className: 'hb-tip', title: typeof label === 'string' ? label : undefined, children })
}

export function Input({ className = '', ...props }) {
  return jsx('input', { 'data-slot': 'input', className: `hb-input ${className}`.trim(), ...props })
}

export function Textarea({ className = '', ...props }) {
  return jsx('textarea', { 'data-slot': 'textarea', className: `hb-input hb-textarea ${className}`.trim(), ...props })
}

export function Checkbox({ checked, onCheckedChange, className = '', id, disabled, ...rest }) {
  return jsx('button', {
    type: 'button', role: 'checkbox', 'aria-checked': Boolean(checked), 'data-state': checked ? 'checked' : 'unchecked', id, disabled,
    className: `hb-checkbox ${className}`.trim(), onClick: () => onCheckedChange && onCheckedChange(!checked), ...rest,
    children: checked ? jsx(Codicon, { name: 'check', size: '0.75rem' }) : null,
  })
}

export function Switch({ checked, onCheckedChange, className = '', ...rest }) {
  return jsx('button', {
    type: 'button', role: 'switch', 'aria-checked': Boolean(checked), 'data-state': checked ? 'checked' : 'unchecked',
    className: `hb-switch ${className}`.trim(), onClick: () => onCheckedChange && onCheckedChange(!checked), ...rest,
    children: jsx('span', { className: 'hb-switch-thumb' }),
  })
}

export function SegmentedControl({ options, value, onChange, className = '', disabled }) {
  return jsx('div', { className: `hb-seg ${className}`.trim(), children: options.map(o => jsx('button', {
    type: 'button', 'aria-pressed': value === o.id, disabled, className: 'hb-seg-btn', onClick: () => onChange(o.id), children: o.label,
  }, o.id)) })
}

export function Loader() {
  return jsx('span', { className: 'hb-spin' })
}

export function ErrorState({ title, description, icon, children }) {
  return jsxs('div', { className: 'hb-error', children: [
    icon || jsx(Codicon, { name: 'error', size: '1.75rem', className: 'hb-error-icon' }),
    typeof title === 'string' ? jsx('h2', { className: 'hb-error-title', children: title }) : title,
    typeof description === 'string' ? jsx('p', { className: 'hb-muted', children: description }) : description,
    children ? jsx('div', { className: 'hb-error-actions', children }) : null,
  ] })
}

export function PanelEmpty({ action, description, icon = 'inbox', title }) {
  return jsx('div', { className: 'hb-empty', children: jsxs('div', { className: 'hb-empty-inner', children: [
    jsx(Codicon, { name: icon, size: '1.25rem', className: 'hb-empty-icon' }),
    title ? jsx('p', { className: 'hb-empty-title', children: title }) : null,
    description ? jsx('p', { className: 'hb-empty-desc', children: description }) : null,
    action ? jsx('div', { style: { marginTop: 8 }, children: action }) : null,
  ] }) })
}

export function Badge({ children, className = '' }) {
  return jsx('span', { className: `hb-badge ${className}`.trim(), children })
}

