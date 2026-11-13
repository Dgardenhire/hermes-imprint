# hermes-ui-kit (vendored)

This folder is the source of the shared interface code inside `desktop/plugin.js`: the theme tokens, buttons, cards,
empty and error states, keyboard hooks and the page-registration helper that Letterpress and Damon Gardenhire's other
Hermes desktop plugins have in common. `desktop/plugin.js` is one built file, so this is the source a reader needs to
check what the shared parts of it say.

Copied from the hermes-ui-kit repository at commit `2c5afa3` (it builds on `e3fccf9` and adds the shorter
"couldn't reach its engine" message). Files copied unchanged: everything in `src/` and `harness/`. Files changed here:

- `scripts/build.mjs` labels each file in the bundle by its path inside the kit (`hermes-ui-kit/src/tokens.js`) instead
  of its path relative to wherever the kit was checked out, resolves symlinked folders to their real path, and names this
  folder in the header it writes. The code in the bundle is the same as before; only those comment lines differ.
- `package.json` keeps the build scripts only and pins esbuild to an exact version. `package-lock.json` is new.
- `LICENSE` is new: the same MIT license as the rest of this repository.

## Rebuild and check

From the Letterpress folder, with Node 24 (v24.14.0 was used; 26.8 and 26.9 gave the same bytes):

```
npm ci --ignore-scripts --prefix vendor/hermes-ui-kit
node vendor/hermes-ui-kit/scripts/build.mjs .
node scripts/verify-bundle.mjs
```

The first command installs esbuild 0.28.2 from `package-lock.json`. The second writes `desktop/plugin.js` from
`desktop/src/` and this folder. The third rebuilds in a temporary folder and exits 0 only if the result is
byte-identical to the committed `desktop/plugin.js`; it prints both SHA-256 values.
