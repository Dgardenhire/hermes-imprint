"""Fast open: the notebook is drawn from the last good answers in plugin storage while the real ones load
(desktop/src/firstpaint.js). The cache itself is tested in tests/js/firstpaint.test.mjs; this runs those tests with a
real state answer from the sample notebook, and checks the page wiring in the source and the built bundle."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _load import ROOT, service

SRC = ROOT / "desktop" / "src" / "plugin.js"
FP = ROOT / "desktop" / "src" / "firstpaint.js"
BUNDLE = ROOT / "desktop" / "plugin.js"


def _node():
    found = shutil.which("node")
    if found:
        return found
    nvm = Path.home() / ".nvm" / "versions" / "node"
    if nvm.is_dir():
        for d in sorted(nvm.iterdir(), reverse=True):
            if (d / "bin" / "node").exists():
                return str(d / "bin" / "node")
    return None


class TestCacheWithRealState(unittest.TestCase):
    def test_the_js_cache_tests_pass_on_the_sample_notebook(self):
        node = _node()
        if not node:
            self.skipTest("node is not installed")
        service.open_sample()
        try:
            st = service.state()
        finally:
            service.close_sample()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state.json"
            p.write_text(json.dumps(st))
            env = dict(os.environ, IMPRINT_STATE_JSON=str(p))
            r = subprocess.run([node, "--test", str(ROOT / "tests" / "js" / "firstpaint.test.mjs")],
                               capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr[-2000:])
        self.assertRegex(r.stdout, r"(#|ℹ) skipped 0\b", "the real-state test ran")

    def test_state_keeps_the_keys_the_copy_stores(self):
        """firstpaint.js stores a fixed list of state keys; a key renamed in service.state() must be renamed there too."""
        keys = json.loads("[" + FP.read_text().split("export const STATE_KEYS = [", 1)[1].split("]", 1)[0].replace("'", '"') + "]")
        st = service.state()
        self.assertEqual([k for k in keys if k not in st], [])


class TestPageWiring(unittest.TestCase):
    def setUp(self):
        self.src = SRC.read_text()

    def test_first_answers_go_out_together(self):
        body = self.src.split("async function loadNow() {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(body.index("ensureChats()"), body.index("await rest('state')"))
        self.assertLess(body.index("ensureGuide()"), body.index("await rest('state')"))

    def test_the_copy_takes_no_input_and_starts_no_model_work(self):
        self.assertIn("root.current.inert = !!stale", self.src)
        guide = self.src.split("function GuideBlock(", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("!copy) writeGuide(ids)", guide)
        load = self.src.split("async function loadNow() {", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(load.index("fp.fresh('state')"), load.index("trackMake(j)"), "jobs are tracked only from a real answer")

    def test_the_bundle_carries_it(self):
        bundle = BUNDLE.read_text()
        for needle in ("firstPaint", "createFirstPaint", ".inert = !!stale", "function ensureChats"):
            self.assertIn(needle, bundle)


if __name__ == "__main__":
    unittest.main()
