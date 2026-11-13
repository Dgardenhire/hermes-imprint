#!/usr/bin/env node
// Rebuild desktop/plugin.js from vendor/hermes-ui-kit and desktop/src into a temporary folder and compare it, byte
// for byte, with the committed desktop/plugin.js. Prints both SHA-256 values. Exits 0 only when they match.
//
//   npm ci --ignore-scripts --prefix vendor/hermes-ui-kit     (once: installs the pinned esbuild)
//   node scripts/verify-bundle.mjs
//
// The build runs on a copy of the sources in a fresh temporary folder, so it cannot lean on anything else in the
// checkout. Exit codes: 0 identical, 1 different or the bundle breaks the desktop rules, 2 cannot run (no esbuild).

import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const KIT = join(ROOT, 'vendor', 'hermes-ui-kit')
const COMMITTED = join(ROOT, 'desktop', 'plugin.js')
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex')

if (!existsSync(join(KIT, 'node_modules', 'esbuild'))) {
  console.error('esbuild is not installed. Run: npm ci --ignore-scripts --prefix vendor/hermes-ui-kit')
  process.exit(2)
}
if (!existsSync(COMMITTED)) {
  console.error(`missing ${COMMITTED}`)
  process.exit(2)
}

const work = mkdtempSync(join(tmpdir(), 'verify-bundle-'))
let code = 1
try {
  mkdirSync(join(work, 'desktop'), { recursive: true })
  cpSync(join(ROOT, 'desktop', 'src'), join(work, 'desktop', 'src'), { recursive: true })
  cpSync(KIT, join(work, 'vendor', 'hermes-ui-kit'), { recursive: true, filter: from => !from.includes('node_modules') })
  symlinkSync(join(KIT, 'node_modules'), join(work, 'vendor', 'hermes-ui-kit', 'node_modules'), 'dir')

  const { bundle, ruleProblems } = await import(pathToFileURL(join(work, 'vendor', 'hermes-ui-kit', 'scripts', 'build.mjs')).href)
  const rebuilt = await bundle(work)
  writeFileSync(join(work, 'desktop', 'plugin.js'), rebuilt)
  const problems = ruleProblems(rebuilt)

  const rebuiltBytes = readFileSync(join(work, 'desktop', 'plugin.js'))
  const committedBytes = readFileSync(COMMITTED)
  console.log(`committed desktop/plugin.js  sha256 ${sha256(committedBytes)}  ${committedBytes.length} bytes`)
  console.log(`rebuilt from vendor + src    sha256 ${sha256(rebuiltBytes)}  ${rebuiltBytes.length} bytes`)
  if (problems.length) console.error(`the rebuilt bundle breaks the desktop rules: ${problems.join(', ')}`)
  if (!problems.length && Buffer.compare(rebuiltBytes, committedBytes) === 0) {
    console.log('MATCH: desktop/plugin.js is exactly what vendor/hermes-ui-kit and desktop/src build.')
    code = 0
  } else {
    console.error('DIFFERENT: rebuild with `node vendor/hermes-ui-kit/scripts/build.mjs .` and commit desktop/plugin.js.')
  }
} finally {
  rmSync(work, { recursive: true, force: true })
}
process.exit(code)
