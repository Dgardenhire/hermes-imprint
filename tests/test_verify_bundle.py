"""The committed desktop/plugin.js is exactly what vendor/hermes-ui-kit and desktop/src build.

Runs scripts/verify-bundle.mjs, which rebuilds the file in a temporary folder and compares the bytes. Skipped, with
the reason, when Node is not installed or the pinned esbuild has not been installed yet."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
ESBUILD = ROOT / "vendor" / "hermes-ui-kit" / "node_modules" / "esbuild"


class VerifyBundle(unittest.TestCase):
    @unittest.skipUnless(NODE, "node is not installed; install Node 24 to check that desktop/plugin.js matches its source")
    @unittest.skipUnless(
        ESBUILD.exists(), "esbuild is not installed; run: npm ci --ignore-scripts --prefix vendor/hermes-ui-kit"
    )
    def test_committed_bundle_matches_a_rebuild(self):
        # close_fds=False makes Python start the program with posix_spawn instead of fork. On macOS, once other tests in
        # this run have touched the system networking libraries, a forked child can crash (SIGSEGV) before it starts.
        run = subprocess.run(
            [NODE, str(ROOT / "scripts" / "verify-bundle.mjs")],
            capture_output=True, text=True, timeout=180, close_fds=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("MATCH", run.stdout)
        shas = [line.split("sha256")[1].split()[0] for line in run.stdout.splitlines() if "sha256" in line]
        self.assertEqual(len(shas), 2)
        self.assertEqual(shas[0], shas[1])
        self.assertEqual(len(shas[0]), 64)


if __name__ == "__main__":
    unittest.main()
