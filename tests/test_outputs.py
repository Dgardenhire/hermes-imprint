"""Deck and audio brief, end to end with the stand-in model, plus the streamed, capped web fetch."""
import asyncio
import base64
import io
import json
import unittest
import zipfile
import zlib
from pathlib import Path

from _load import (HTTPException, add_samples, api, content, fake_model, ingest, jobs, layout, make, reset, run,
                   runtime, service, store)


def _deck_out(kit_ids=("plain-notice", "docket")):
    srcs = add_samples()
    j = make([s["id"] for s in srcs], list(kit_ids), brief="A deck for the council", kind="deck")
    assert j["status"] == "done", j
    return service.output_view(j["result"]["output_id"])


class Deck(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()

    def test_deck_is_written_once_voiced_per_kit_and_traced(self):
        out = _deck_out()
        self.assertEqual(out["kind"], "deck")
        self.assertEqual(set(out["formats"]), {"pptx", "pdf", "notes"})
        for pr in out["proofs"]:
            self.assertEqual(pr["status"], "ready")
            self.assertEqual(pr["kind"], "deck")
            self.assertTrue(pr["tree"]["c"].startswith("ip-deck"))
            self.assertGreaterEqual(pr["slide_count"], 6)
            self.assertFalse(pr["blocked"], pr["grounding"])
        doc = service._doc_for(out["id"], service.KITS.get("docket"))
        stat = next(s for s in doc["slides"] if s["type"] == "stat")
        neutral = service._output(out["id"])["neutral"]
        self.assertEqual(stat["value"], next(s for s in neutral["slides"] if s["type"] == "stat")["value"])
        self.assertTrue(any(s.get("heading", "").endswith(" now") for s in doc["slides"]))
        self.assertTrue(doc["title"].startswith("Here is"))

    def test_voice_pass_that_changes_a_number_is_reverted(self):
        neutral = content.clean_deck({"title": "Season", "subtitle": "x", "slides": [
            {"type": "stat", "value": "2,914", "label": "stays in 87 nights", "refs": ["P1"]},
            {"type": "content", "heading": "Costs", "bullets": [{"text": "It cost $318,400.", "ref": "P2"}]},
            {"type": "closing", "heading": "Next", "text": "Decide in April."}]})
        voiced = json.loads(json.dumps(neutral))
        voiced["slides"][0]["label"] = "stays in 90 nights"
        voiced["slides"][0]["value"] = "3,000"
        voiced["slides"][1]["bullets"][0]["text"] = "It cost about $300,000."
        voiced["slides"][2]["heading"] = "What comes next"
        merged, reverted = content.keep_facts(neutral, voiced)
        self.assertEqual(merged["slides"][0]["value"], "2,914")
        self.assertEqual(merged["slides"][0]["label"], "stays in 87 nights")
        self.assertEqual(merged["slides"][1]["bullets"][0]["text"], "It cost $318,400.")
        self.assertEqual(merged["slides"][2]["heading"], "What comes next")
        self.assertIn("slides.0.label", reverted)
        self.assertIn("slides.1.bullets.0.text", reverted)

    def test_voice_pass_that_changes_slide_types_is_reverted(self):
        neutral = content.clean_deck({"title": "Season", "slides": [
            {"type": "section", "heading": "One"}, {"type": "section", "heading": "Two"}, {"type": "closing", "heading": "End"}]})
        voiced = json.loads(json.dumps(neutral))
        voiced["slides"][1] = {"type": "closing", "heading": "Changed"}
        merged, reverted = content.keep_facts(neutral, voiced)
        self.assertEqual(merged["slides"][1], neutral["slides"][1])
        self.assertIn("slides.1.heading", reverted)

    def test_pptx_carries_the_kit_on_the_master(self):
        from pptx import Presentation
        out = _deck_out()
        kit = service.KITS.get("docket")
        r = service.export(out["id"], "docket", "pptx")
        self.assertTrue(r["name"].endswith(".pptx"))
        data = Path(r["path"]).read_bytes()
        prs = Presentation(io.BytesIO(data))
        pr = next(p for p in out["proofs"] if p["kit_id"] == "docket")
        self.assertEqual(len(prs.slides), pr["slide_count"])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            theme = z.read("ppt/theme/theme1.xml").decode("utf-8")
        self.assertIn(kit["ink"].lstrip("#").upper(), theme)
        self.assertIn(f'typeface="{kit["type"]["heading"]["family"]}"', theme)
        notes = [s.notes_slide.notes_text_frame.text for s in prs.slides if s.has_notes_slide]
        self.assertTrue(any(n.startswith("Sources: ") for n in notes))
        texts = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
        self.assertIn("$318,400", texts)

    def test_deck_pdf_has_one_page_per_slide(self):
        from pypdf import PdfReader
        out = _deck_out()
        r = service.export(out["id"], "plain-notice", "pdf")
        reader = PdfReader(r["path"])
        pr = next(p for p in out["proofs"] if p["kit_id"] == "plain-notice")
        self.assertEqual(len(reader.pages), pr["slide_count"])
        box = reader.pages[0].mediabox
        self.assertAlmostEqual(float(box.width) / float(box.height), 16 / 9, places=2)

    def test_deck_refuses_one_pager_formats(self):
        out = _deck_out()
        with self.assertRaises(ValueError):
            service.export(out["id"], "docket", "html")

    def test_deck_with_a_png_logo_places_it(self):
        from pptx import Presentation
        k = service.KITS.save_new({**service.KITS.get("docket"), "name": "Logo deck kit"})
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
        service.KITS.set_logo(k["id"], "logo.png", png)
        out = _deck_out(kit_ids=(k["id"],))
        r = service.export(out["id"], k["id"], "pptx")
        prs = Presentation(r["path"])
        self.assertTrue(any(sh.shape_type == 13 for sh in prs.slide_master.shapes))  # 13 is a picture

    def test_remove_a_flagged_deck_bullet(self):
        doc = content.clean_deck({"title": "T", "slides": [
            {"type": "content", "heading": "H", "bullets": [{"text": "We served 999 people.", "ref": "P1"}, {"text": "Fine", "ref": "P1"}]},
            {"type": "stat", "value": "77", "label": "nights", "refs": ["P1"]}, {"type": "closing", "heading": "End"}]})
        service._remove(doc, "slides.0.bullets.0", "slides.0.bullets.0|number|999")
        self.assertEqual([b["text"] for b in doc["slides"][0]["bullets"]], ["Fine"])
        service._remove(doc, "slides.1.value", "slides.1.value|number|77")
        self.assertEqual([s["type"] for s in doc["slides"]], ["content", "closing"])

    def test_deck_slide_text_is_editable(self):
        out = _deck_out()
        v = service.edit(out["id"], "slides.0.heading", "A new heading")
        self.assertEqual(service._output(out["id"])["neutral"]["slides"][0]["heading"], "A new heading")
        self.assertEqual(v["kind"], "deck")
        with self.assertRaises(ValueError):
            service.edit(out["id"], "slides.0.refs", "P1")


class Audio(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.calls = []
        self._orig = runtime.dispatch

    def tearDown(self):
        runtime.dispatch = self._orig

    def _voice(self, parts=1, fail=None):
        def fake(tool, args, timeout=180.0):
            self.calls.append((tool, args))
            if fail:
                raise runtime.ToolUnavailable(fail)
            base = Path(args.get("output_path") or (store.root() / "elsewhere" / "tts.mp3"))
            base.parent.mkdir(parents=True, exist_ok=True)
            paths = []
            for i in range(parts):
                p = base.with_name(f"{base.stem}-{i}.mp3") if parts > 1 else base
                p.write_bytes(b"ID3" + bytes([i]) * 400)
                paths.append(str(p))
            return {"success": True, "file_path": paths[0], "file_paths": paths}
        runtime.dispatch = fake

    def _make(self, kit_ids=("plain-notice", "docket")):
        srcs = add_samples()
        j = make([s["id"] for s in srcs], list(kit_ids), brief="A spoken brief", kind="audio")
        self.assertEqual(j["status"], "done", j)
        return service.output_view(j["result"]["output_id"])

    def test_audio_brief_is_scripted_voiced_and_recorded_per_kit(self):
        self._voice()
        out = self._make()
        self.assertEqual(out["kind"], "audio")
        self.assertEqual(len(self.calls), 2)
        tool, args = self.calls[0]
        self.assertEqual(tool, "text_to_speech")
        self.assertIn("briefing", args["instructions"])
        self.assertIn("Three things to remember", args["text"])
        for pr in out["proofs"]:
            self.assertEqual(pr["audio"]["status"], "ready", pr["audio"])
            self.assertTrue(pr["tree"]["c"].startswith("ip-page ip-script"))
            self.assertTrue(any(c["id"] == "length" for c in pr["checks"]))
        got = service.audio_file(out["id"], "docket")
        self.assertEqual(got["mime"], "audio/mpeg")
        self.assertTrue(base64.b64decode(got["data"]).startswith(b"ID3"))
        exp = service.export(out["id"], "docket", "audio")
        self.assertTrue(exp["name"].endswith(".mp3"))
        script = Path(service.export(out["id"], "docket", "script")["path"]).read_text()
        self.assertIn("Sources", script)
        self.assertTrue(service.export(out["id"], "docket", "pdf")["name"].endswith("-script.pdf"))

    def test_kit_delivery_notes_reach_the_voice(self):
        self._voice()
        kit = service.KITS.save_new({**service.KITS.get("docket"), "name": "Calm voice kit",
                                     "voice": {**service.KITS.get("docket")["voice"], "delivery": "Warm and slow. Stress the dates."}})
        self._make(kit_ids=(kit["id"],))
        self.assertTrue(self.calls[0][1]["instructions"].startswith("Warm and slow. Stress the dates."))

    def test_long_scripts_in_parts_are_joined(self):
        self._voice(parts=3)
        out = self._make(kit_ids=("docket",))
        p = Path(service.export(out["id"], "docket", "audio")["path"])
        self.assertEqual(p.stat().st_size, 3 * 403)

    def test_no_voice_keeps_the_script_and_says_what_to_do(self):
        self._voice(fail="Unknown tool: text_to_speech")
        out = self._make(kit_ids=("docket",))
        pr = out["proofs"][0]
        self.assertEqual(pr["audio"]["status"], "failed")
        self.assertIn("Turn on text to speech", pr["audio"]["error"])
        self.assertTrue(service.export(out["id"], "docket", "script")["name"].endswith(".txt"))
        with self.assertRaises(ValueError):
            service.export(out["id"], "docket", "audio")
        with self.assertRaises(ValueError):
            service.audio_file(out["id"], "docket")
        j = jobs.start("speak", "again", {"output_id": out["id"], "kit_id": "docket"}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "failed")
        self.assertEqual(j["error_code"], "no_voice")

    def test_record_again_after_turning_the_voice_on(self):
        self._voice(fail="Unknown tool: text_to_speech")
        out = self._make(kit_ids=("docket",))
        self._voice()
        r = run(api.post_speak(out["id"], {"kit_id": "docket"}))
        t = jobs._threads.get(r["job"]["id"])
        if t:
            t.join(10)
        self.assertEqual(jobs.get(r["job"]["id"])["status"], "done")
        self.assertEqual(service.proof(out["id"], "docket")["audio"]["status"], "ready")

    def test_voice_file_outside_audio_types_is_refused(self):
        def fake(tool, args, timeout=180.0):
            p = store.root() / "x.txt"
            p.write_text("not audio")
            return {"success": True, "file_path": str(p)}
        runtime.dispatch = fake
        out = self._make(kit_ids=("docket",))
        self.assertEqual(out["proofs"][0]["audio"]["status"], "failed")

    def test_a_voice_that_never_answers_does_not_hold_the_job(self):
        import time
        def hang(tool, args, timeout=180.0):
            time.sleep(1.5)
            return {"success": True, "file_path": ""}
        runtime.dispatch = hang
        old = service.TTS_TIMEOUT
        service.TTS_TIMEOUT = 0.2
        try:
            t0 = time.time()
            out = self._make(kit_ids=("docket",))
            self.assertLess(time.time() - t0, 1.4)
        finally:
            service.TTS_TIMEOUT = old
        a = out["proofs"][0]["audio"]
        self.assertEqual(a["status"], "failed")
        self.assertIn("took too long", a["error"])
        self.assertTrue(service.export(out["id"], "docket", "script")["name"].endswith(".txt"))

    def test_audio_routes_validate(self):
        for coro in (api.get_output_audio("../x", "docket"), api.post_speak("o_../x", {"kit_id": "docket"}),
                     api.post_speak("o_aaaaaaaaaaaa", {"kit_id": "../evil"})):
            with self.subTest(coro=coro):
                with self.assertRaises(HTTPException):
                    run(coro)

    def test_script_minutes_and_length_pill(self):
        doc = {"title": "T", "segments": [{"heading": "A", "text": " ".join(["word"] * 450), "refs": []}], "recap": "r"}
        self.assertAlmostEqual(layout.script_minutes(doc), 3.0, places=1)
        from _load import checks
        self.assertEqual(checks.pill_length(3.0)["tone"], "good")
        self.assertEqual(checks.pill_length(0.6)["tone"], "warn")


class FakeResp:
    def __init__(self, chunks, headers=None, status=200, url="https://example.org/"):
        self.chunks, self.headers, self.status_code, self.url = chunks, headers or {}, status, url
        self.is_redirect = False
        self.read = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def aiter_raw(self):
        for c in self.chunks:
            self.read += 1
            yield c


class FakeClient:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url):
        return self.resp


class StreamedFetch(unittest.TestCase):
    def setUp(self):
        self._orig = ingest._client_factory

    def tearDown(self):
        ingest._client_factory = self._orig

    def _with(self, resp):
        ingest._client_factory = lambda: ((lambda **kw: FakeClient(resp)), (lambda url: True))

    def test_declared_length_over_cap_is_refused_before_reading(self):
        resp = FakeResp([b"x" * 10], headers={"content-length": str(50 * 1024 * 1024)})
        self._with(resp)
        with self.assertRaises(ingest.Refused) as cm:
            asyncio.run(ingest.fetch("https://example.org", max_bytes=1024))
        self.assertIn("limit", str(cm.exception))
        self.assertEqual(resp.read, 0)

    def test_missing_length_stops_at_the_cap(self):
        resp = FakeResp([b"a" * 600] * 1000)  # 600 KB with no Content-Length
        self._with(resp)
        with self.assertRaises(ingest.Refused):
            asyncio.run(ingest.fetch("https://example.org", max_bytes=4096))
        self.assertLess(resp.read, 10)

    def test_decoded_bomb_stops_at_the_cap(self):
        # A small gzip body that inflates hugely: Letterpress inflates it itself, never more than the room left, so
        # the read stops in the first chunk past the cap.
        z = zlib.compressobj(9, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
        bomb = b"".join(z.compress(b"\0" * (1024 * 1024)) for _ in range(200)) + z.flush()
        resp = FakeResp([bomb[i:i + 4096] for i in range(0, len(bomb), 4096)],
                        headers={"content-length": str(len(bomb)), "content-encoding": "gzip"})
        self._with(resp)
        with self.assertRaises(ingest.Refused):
            asyncio.run(ingest.fetch("https://example.org", max_bytes=2 * 1024 * 1024))
        self.assertLessEqual(resp.read, 3)

    def test_stylesheets_keep_what_fits(self):
        resp = FakeResp([b":root{--a:#123456}" + b" " * 5000], headers={"content-type": "text/css"})
        self._with(resp)
        got = asyncio.run(ingest.fetch("https://example.org/a.css", max_bytes=1000, stop_at_cap=True))
        self.assertTrue(got["cut"])
        self.assertEqual(len(got["raw"]), 1000)
        self.assertIn("--a:#123456", got["body"])

    def test_small_page_reads_whole(self):
        resp = FakeResp([b"<html><body><p>Hi</p></body></html>"], headers={"content-type": "text/html; charset=utf-8"})
        self._with(resp)
        got = asyncio.run(ingest.fetch("https://example.org"))
        self.assertFalse(got["cut"])
        self.assertIn("Hi", got["body"])


if __name__ == "__main__":
    unittest.main()
