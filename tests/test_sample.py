"""Contract A and B: the Harborlight sample opens in under 3 s on a fresh data folder with no model call, shows real
pictures in the Studio tiles before and after it opens, and closing it leaves the person's own folder as it was."""
import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from _load import ROOT, fake_model, jobs, reset, runtime, service, store

from test_revise import KIT, harborlight

SHIPPED = ROOT / "samples" / "harborlight"


def record_fake(dest: Path) -> dict:
    """A recording made the way tools/record_sample.py makes it, with the stand-in model, into ``dest``."""
    reset()
    llm = fake_model()
    names = ("FY26-Program-Report.docx", "board-retreat-notes.txt", "Harborlight-Brand-Guide-2025.pdf")
    rows = [service.read_file(n, (SHIPPED / n).read_bytes()) for n in names]
    service.set_included([rows[2]["id"]], False)
    ids = [r["id"] for r in rows[:2]]
    draft = service.import_read("pdf", filename=names[2], data=(SHIPPED / names[2]).read_bytes())
    kid = service.import_save(draft["draft_id"])["kit"]["id"]
    service.KITS.update(kid, {"colors": service.SAMPLE_COLORS})
    service.KITS.set_logo(kid, "harborlight-logo.png", (SHIPPED / "harborlight-logo.png").read_bytes())
    store.set_setting("prefs", {"kit": kid})
    from test_revise import deck
    _i, _b, find = None, None, (lambda phrase: next(f"P{p['id']}" for p in store.q("SELECT id, text FROM passages") if phrase in p["text"]))
    llm.deck = lambda ps: deck(find)
    made = {}
    for kind, brief in (("deck", "A short deck for funders"), ("onepager", "A one-page summary of the FY2027 budget request"),
                        ("audio", "A three-minute brief")):
        j = jobs.start("make", f"t:sample:{kind}", {"kind": kind, "source_ids": ids, "kit_ids": [kid], "brief": brief}, wait=True)
        j = jobs.get(j["id"])
        assert j["status"] == "done", j["error"]
        made[kind] = j["result"]["output_id"]
    book = service.book_from_folder({"kit_id": kid, "outputs": made, "source_ids": [r["id"] for r in rows], "files": list(names)})
    for n in names + ("harborlight-logo.png",):
        shutil.copy(SHIPPED / n, dest / n)
    (dest / "notebook.json").write_text(json.dumps(book, ensure_ascii=False))
    return book


class Sample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = Path(tempfile.mkdtemp(prefix="letterpress-sample-src-"))
        cls.book = record_fake(cls.src)
        cls.real_src = service.SAMPLE_SRC
        service.SAMPLE_SRC = cls.src

    @classmethod
    def tearDownClass(cls):
        service.SAMPLE_SRC = cls.real_src
        shutil.rmtree(cls.src, ignore_errors=True)

    def setUp(self):
        reset()
        self.llm = fake_model()
        self.llm.calls.clear()

    def tearDown(self):
        if runtime.sample_open():
            service.close_sample()

    def test_open_is_fast_has_pictures_and_close_leaves_my_folder_alone(self):
        mine = service.add_text("My own notes", "The food pantry served 412 families in March.")
        st = service.state()
        self.assertEqual(st["sample"], {"available": True, "open": False, "name": "Harborlight Literacy", "label": "Sample"})
        for kind in ("deck", "onepager", "visual", "audio"):  # real pictures before the sample is opened
            self.assertTrue((st["previews"][kind] or {}).get("img", "").startswith("data:image/"), kind)
        t = time.time()
        st = service.open_sample()
        took = time.time() - t
        self.assertLess(took, 3.0)
        self.assertEqual(self.llm.calls, [])  # no model call
        self.assertTrue(st["sample"]["open"])
        self.assertEqual({s["title"] for s in st["sources"]}, {"FY26 Program Report", "Board retreat notes", "Harborlight Brand Guide 2025"})
        self.assertTrue(all(s["sample"] for s in st["sources"]))
        self.assertEqual([s["included"] for s in st["sources"] if "Brand" in s["title"]], [False])
        deck = next(o for o in st["outputs"] if o["kind"] == "deck")
        self.assertTrue(deck["sample"] and not deck["building"])
        self.assertTrue(deck["thumb"].startswith("data:image/"))
        self.assertLess(len(deck["thumb"]) * 3 / 4, 80 * 1024)
        for kind in ("deck", "onepager", "visual", "audio"):
            self.assertTrue((st["previews"][kind] or {}).get("img", "").startswith("data:image/"), kind)
            self.assertEqual(st["previews"][kind]["kit_name"], next(k["name"] for k in st["kits"] if k["id"] == self.book["kit_id"]))
        # the recorded docs draw with the current renderer, and the proof has its claims
        view = service.output_view(deck["id"])
        self.assertEqual(view["proofs"][0]["status"], "ready")
        self.assertTrue(view["proofs"][0]["claims"])
        self.assertEqual(view["versions"][0]["reason"], "Made")
        # the source reader reads the shipped file
        self.assertTrue(service.source_view(st["sources"][0]["id"])["passages"])
        # second open reuses the folder
        service.close_sample()
        t = time.time()
        service.open_sample()
        self.assertLess(time.time() - t, 1.0)
        st = service.close_sample()
        self.assertFalse(st["sample"]["open"])
        self.assertEqual([s["id"] for s in st["sources"]], [mine["id"]])
        self.assertEqual(st["outputs"], [])
        self.assertFalse(st["sources"][0]["sample"])

    def test_work_in_the_sample_stays_in_the_sample(self):
        service.open_sample()
        service.add_text("A note in the sample", "Eastgate had 140 adults waiting.")
        service.close_sample()
        self.assertEqual(service.list_sources(), [])
        service.open_sample()
        self.assertIn("A note in the sample", [s["title"] for s in service.list_sources()])


class Shipped(unittest.TestCase):
    def test_the_shipped_sample_opens_with_its_pictures_drawn_already(self):
        if not (SHIPPED / "notebook.json").exists():
            self.skipTest("not recorded yet")
        book = json.loads((SHIPPED / "notebook.json").read_text())
        if not any(service.renderer_sig() in n for n in book.get("pictures") or {}):
            self.skipTest("the shipped pictures predate this renderer: run tools/record_sample.py --pictures")
        reset()
        fake_model()
        real = service._draw_picture
        service._draw_picture = lambda *a, **k: (_ for _ in ()).throw(AssertionError("drew a picture"))
        try:
            t = time.time()
            st = service.open_sample()
            self.assertLess(time.time() - t, 3.0)
        finally:
            service._draw_picture = real
            service.close_sample()
        self.assertTrue(all((st["previews"][k] or {}).get("img", "").startswith("data:image/") for k in ("deck", "onepager", "visual", "audio")))
        self.assertTrue(all(o["thumb"] for o in st["outputs"]))

    def test_the_shipped_files_are_there_and_marked_fictional(self):
        for n in ("FY26-Program-Report.docx", "board-retreat-notes.txt", "Harborlight-Brand-Guide-2025.pdf"):
            self.assertTrue((SHIPPED / n).is_file(), n)
        for f in SHIPPED.iterdir():
            if f.suffix in (".txt", ".json"):
                low = f.read_text().lower()
                for w in ("hackathon", "linchpin", "acme"):
                    self.assertNotIn(w, low, f.name)
        book = SHIPPED / "notebook.json"
        if book.exists():
            b = json.loads(book.read_text())
            self.assertEqual(b["label"], "Sample")
            self.assertTrue(b.get("run_logs"))
            for name in b["run_logs"]:
                self.assertTrue((ROOT / "docs" / "runs" / "sample" / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
