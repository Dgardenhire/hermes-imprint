// A stand-in for '@hermes/plugin-sdk', for rendering desktop/plugin.js in a plain browser. Components come
// from the kit's stand-in (kit-sdk-stub.js, copied by the kit's build); atom and useValue are the real
// nanostores; host and the download bridge record calls. Harness only: the app provides the real SDK.
import { useStore } from '@nanostores/react'
import { atom as nanoAtom } from 'nanostores'

export * from './kit-sdk-stub.js'
export const atom = nanoAtom
export const useValue = useStore
const log = (...a) => (window.__hostLog = window.__hostLog || []).push(a)
export const host = { navigate(path) { log('navigate', path) } }
export function captureGatewayFileDownload() { return async (path, name) => { log('save', path, name); console.log('SAVE', path, name); return true } }
