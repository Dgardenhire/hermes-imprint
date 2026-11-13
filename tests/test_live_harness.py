"""Live mode (harness/live/server.py): the real routes behind a local server, so a tester presses real buttons.
Started in a subprocess on a free port with its own temp data folder."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class LiveMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.mkdtemp(prefix="letterpress-live-test-")
        cls.port = free_port()
        env = {k: v for k, v in os.environ.items() if k != "LETTERPRESS_DATA_DIR"}
        cls.proc = subprocess.Popen([sys.executable, str(REPO / "harness" / "live" / "server.py"), str(cls.port), "--data", cls.data],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(80):
            try:
                urllib.request.urlopen(cls.base + "/api/state", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        raise RuntimeError("live server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + "/api/" + path, data=data, method=method,
                                     headers={"content-type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def wait(self, job):
        for _ in range(300):
            j = self.call("GET", f"jobs/{job['id']}")
            if j["status"] != "running":
                return j
            time.sleep(0.05)
        raise TimeoutError(job)

    def test_real_buttons_end_to_end(self):
        src = self.call("POST", "sources/text", {"title": "Season report", "text": (
            "The center recorded 2,914 overnight stays this winter. It was open 87 nights. "
            "Volunteers gave 3,260 hours over the season. The council meets on April 8 to decide on a second site.")})
        sid = src["source"]["id"] if "source" in src else src["id"]
        j = self.wait(self.call("POST", "outputs", {"kind": "onepager", "source_ids": [sid], "kit_ids": ["plain-notice", "board-report"],
                                                   "brief": "A one-page brief for the council"})["job"])
        self.assertEqual(j["status"], "done", j)
        out = self.call("GET", f"outputs/{j['result']['output_id']}")
        self.assertEqual([p["status"] for p in out["proofs"]], ["ready", "ready"])
        self.assertFalse(any(p["blocked"] for p in out["proofs"]), [p["checks"] for p in out["proofs"]])
        r = self.call("POST", f"outputs/{out['id']}/export", {"kit_id": "board-report", "format": "html"})
        self.assertTrue(Path(r["path"]).resolve().is_relative_to(Path(self.data).resolve()), "writes only in its own data folder")
        self.assertIn("ip-report", Path(r["path"]).read_text())

    def test_serves_the_pane_and_nothing_outside_the_repo(self):
        page = urllib.request.urlopen(self.base + "/harness/index.html?live=1").read().decode()
        self.assertIn("./live/harness.js", page)
        import http.client
        for path in ("/../../../etc/passwd", "/harness/../../../../etc/hosts", "/.git/config"):
            c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            c.request("GET", path)
            body = c.getresponse().read().decode("utf-8", "replace")
            c.close()
            self.assertIn("Letterpress harness", body, path)  # anything outside the repo, or hidden, gets the harness page
            self.assertNotIn("[core]", body)
            self.assertNotIn("localhost", body.split("<style>")[0].replace("http://localhost:8794", ""))

    def test_refuses_other_sites_and_rebound_names(self):
        """Second review F12: a page on another site, open in the same browser, can post to localhost; a
        DNS-rebound name reaches it with a foreign Host. Both get a 403 and change nothing."""
        import http.client
        before = len(self.call("GET", "state")["sources"])
        body = json.dumps({"title": "Planted", "text": "Planted by another site."})
        for headers in ({"Host": f"127.0.0.1:{self.port}", "Origin": "https://evil.example", "Content-Type": "text/plain"},
                        {"Host": f"rebound.evil.example:{self.port}", "Content-Type": "application/json"},
                        {"Host": f"127.0.0.1:{self.port}", "Origin": "null", "Content-Type": "text/plain"}):
            with self.subTest(headers=headers):
                c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
                c.request("POST", "/api/sources/text", body=body, headers=headers)
                r = c.getresponse()
                r.read()
                c.close()
                self.assertEqual(r.status, 403)
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", "/api/state", headers={"Host": f"rebound.evil.example:{self.port}"})
        self.assertEqual(c.getresponse().status, 403)
        c.close()
        after = self.call("GET", "state")["sources"]
        self.assertEqual(len(after), before)
        self.assertNotIn("Planted", json.dumps(after))
        same = self.call("POST", "sources/text", {"title": "Mine", "text": "Typed on the live page itself."})
        self.assertTrue(same)

    def test_refuses_a_data_folder_inside_hermes(self):
        r = subprocess.run([sys.executable, str(REPO / "harness" / "live" / "server.py"), "1", "--data",
                            str(Path(self.data) / ".hermes" / "x")], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("never writes inside ~/.hermes", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
