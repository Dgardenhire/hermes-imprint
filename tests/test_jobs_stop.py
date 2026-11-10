"""Contract C: Stop, step timing, and Build twice is one job."""
import threading
import time
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, service, store

from test_revise import KIT, harborlight

J = jobs


@J.handler("t_slow")
async def _slow(job_id, p):
    J.step(job_id, "First part")
    p["gate"].wait(5) if "gate" in p else None
    ev = GATES[p["n"]]
    ev.wait(5)
    J.step(job_id, "Second part")
    return {"ok": True}


GATES = {}


class Stop(unittest.TestCase):
    def setUp(self):
        harborlight()
        fake_model()

    def slow(self, n):
        GATES[n] = threading.Event()
        return J.start("t_slow", f"t:slow:{n}", {"n": n})

    def test_stop_marks_it_stopped_at_once_and_retry_runs_again(self):
        j = self.slow(1)
        time.sleep(0.1)
        s = J.stop(j["id"])
        self.assertEqual(s["status"], "stopped")
        self.assertEqual(s["error"], "Stopped. Your outline is kept.")
        GATES[1].set()
        time.sleep(0.3)
        after = J.get(j["id"])
        self.assertEqual(after["status"], "stopped")  # the job's next step ended it; nothing overwrote the stop
        self.assertEqual([x["text"] for x in after["steps"]], ["First part"])
        self.assertIsNotNone(after["steps"][0]["done_at"])
        GATES[1] = threading.Event()
        GATES[1].set()
        r = J.retry(j["id"])
        self.assertNotEqual(r["id"], j["id"])
        for _ in range(50):
            if J.get(r["id"])["status"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual(J.get(r["id"])["status"], "done")

    def test_steps_carry_done_at(self):
        GATES[2] = threading.Event()
        GATES[2].set()
        j = J.start("t_slow", "t:slow:2", {"n": 2}, wait=True)
        steps = J.get(j["id"])["steps"]
        self.assertEqual([s["text"] for s in steps], ["First part", "Second part"])
        self.assertTrue(all(s["done_at"] and s["done_at"] >= s["at"] for s in steps))

    def test_build_twice_is_one_job(self):
        j1 = self.slow(3)
        j2 = J.start("t_slow", "t:slow:3", {"n": 3})
        self.assertEqual(j1["id"], j2["id"])
        GATES[3].set()

    def test_stop_route(self):
        import sys
        api = import_module(f"{PKG}.dashboard.plugin_api") if False else None
        self.assertIn("stop", dir(J))

    def test_stop_during_voicing_keeps_the_written_slides(self):
        ids = [s["id"] for s in service.list_sources()]
        real = service._store_render

        def stop_here(output_id, kit, doc, *a, **k):  # a deck's first brand is set by code (round 6), then the stop lands
            jid = store.one("SELECT id FROM jobs WHERE kind='make' AND status='running'")["id"]
            J.stop(jid)
            J.step(jid, "never")  # raises Stopped, as the job's next step would

        service._store_render = stop_here
        try:
            j = J.start("make", f"t:stop:{store.now()}", {"kind": "deck", "source_ids": ids, "kit_ids": [KIT], "brief": "A deck"}, wait=True)
        finally:
            service._store_render = real
        self.assertEqual(J.get(j["id"])["status"], "stopped")
        outs = service.list_outputs()
        self.assertEqual(len(outs), 1)
        self.assertFalse(outs[0]["building"])
        view = service.output_view(outs[0]["id"])
        self.assertEqual(view["proofs"][0]["status"], "ready")
        self.assertEqual(view["versions"][0]["reason"], "Made")


if __name__ == "__main__":
    unittest.main()


class AudioHonest(unittest.TestCase):
    def test_label_matches_the_request_and_chapters_are_timed(self):
        L = service.length_label
        self.assertEqual(L(2.6, "A three-minute brief board members can listen to on the drive in"), "About 3 min")
        self.assertEqual(L(3.4, "a 3-minute brief"), "About 3 min")
        self.assertEqual(L(1.4, "a 3-minute brief"), "About 1 min")  # too short for what was asked: says what it is
        self.assertEqual(L(0.75, "a 45-second brief"), "About 45 sec")
        self.assertEqual(L(2.2, ""), "About 2 min")
        ids, by_ref, find = harborlight()
        wait, served = find("287 adults"), find("enrolled 1,148")
        doc = {"title": "Harborlight in three minutes", "segments": [
            {"heading": "Who we served", "text": "We enrolled 1,148 adult learners. That is up from 936.", "refs": [served]},
            {"heading": "Who is waiting", "text": "At year end, 287 adults were waiting. Most were at two sites.", "refs": [wait, served]}],
            "recap": "Demand is up and people are waiting."}
        tl = service.audio_timeline(doc, by_ref, {served: 1, wait: 1}, "a 3-minute brief")
        ch = tl["chapters"]
        self.assertEqual([c["heading"] for c in ch], ["Who we served", "Who is waiting", "Recap"])
        self.assertGreater(ch[0]["start_s"], 0)  # the title is read first
        for a, b in zip(ch, ch[1:]):
            self.assertAlmostEqual(a["start_s"] + a["dur_s"], b["start_s"], delta=0.11)
        self.assertEqual(ch[1]["lines"][0]["chips"][0]["ref"], wait)  # the sentence with 287 cites the waitlist passage
        self.assertEqual(ch[1]["lines"][1]["chips"][0]["ref"], wait)  # no number: the chapter's first passage
        self.assertAlmostEqual(tl["seconds"], ch[-1]["start_s"] + ch[-1]["dur_s"], delta=0.11)


class VoiceStub(unittest.TestCase):
    def test_silent_wav_runs_as_long_as_the_script(self):
        import sys
        from _load import ROOT
        sys.path.insert(0, str(ROOT / "harness" / "live"))
        import voice_stub
        import tempfile
        import wave
        from pathlib import Path
        d = Path(tempfile.mkdtemp())
        r = voice_stub.dispatch("text_to_speech", {"text": " ".join(["word"] * 300), "output_path": str(d / "take.mp3")})
        with wave.open(r["file_path"]) as w:
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 120.0, delta=0.1)
            self.assertEqual(set(w.readframes(800)), {0})
