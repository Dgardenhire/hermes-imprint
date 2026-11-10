"""A picked graphic: kept as its own graphic output (exports as PNG and SVG), or added to a deck as an exhibit slide
(a new version Undo takes back). Values are re-checked first."""
import unittest

from _load import fake_model, jobs, service, store

from test_revise import KIT, finish, harborlight, made


class GraphicKeep(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, find = harborlight()
        self.llm = fake_model()
        self.deck = made(find, self.llm)
        served, wait = find("enrolled 1,148"), find("287 adults")
        bars = {"headline": "Demand is outgrowing our seats", "form": "bars", "takeaway": "A sixth site would help.",
                "items": [{"label": "FY2025", "value": "936", "ref": served}, {"label": "FY2026", "value": "1,148", "ref": served},
                          {"label": "Waiting", "value": "287", "ref": wait}]}
        steps = {"headline": "The year in order", "form": "timeline", "takeaway": "It moved fast.",
                 "steps": [{"when": "FY2025", "text": "936 enrolled", "ref": served}, {"when": "FY2026", "text": "1,148 enrolled", "ref": served},
                           {"when": "Year end", "text": "287 waiting", "ref": wait}]}
        self.llm.queue.append({"options": [bars, steps]})
        self.job = finish("graphic_options", {"source_ids": self.ids, "text": "Demand is outgrowing our seats.", "note_id": None})
        self.assertEqual(self.job["status"], "done", self.job["error"])
        self.bars = next(i for i, o in enumerate(self.job["result"]["options"]) if o["form"] == "bars")

    def test_keep_as_a_graphic_that_exports(self):
        oid = service.keep_graphic(self.job["id"], self.bars, KIT)["output_id"]
        view = service.output_view(oid)
        self.assertEqual(view["kind"], "visual")
        self.assertEqual(view["title"], "Demand is outgrowing our seats")
        self.assertEqual(view["proofs"][0]["status"], "ready")
        self.assertFalse(view["proofs"][0]["blocked"])
        for fmt in ("png", "svg"):
            self.assertGreater(service.export(oid, KIT, fmt)["bytes"], 500)
        with self.assertRaisesRegex(ValueError, "Pick one"):
            service.keep_graphic(self.job["id"], 9, KIT)

    def test_add_to_deck_is_a_version(self):
        before = service._output(self.deck)["neutral"]["slides"]
        view = service.add_graphic(self.deck, self.job["id"], self.bars)
        after = service._output(self.deck)["neutral"]["slides"]
        self.assertEqual(len(after), len(before) + 1)
        self.assertEqual(after[-1]["type"], "closing")
        new = after[-2]
        self.assertEqual((new["type"], new["heading"]), ("exhibit", "Demand is outgrowing our seats"))
        self.assertEqual([b["value"] for b in new["bars"]], ["936", "1,148", "287"])
        self.assertEqual(view["versions"][-1]["reason"], f"Added a graphic, slide {len(after)}")
        store.undo(self.deck)
        self.assertEqual(service._output(self.deck)["neutral"]["slides"], before)

    def test_a_tampered_value_is_refused(self):
        j = jobs.get(self.job["id"])
        res = j["result"]
        res["options"][self.bars]["spec"]["items"][1]["value"] = "1,300"
        store.run("UPDATE jobs SET result=? WHERE id=?", (store.dumps(res), j["id"]))
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            service.keep_graphic(j["id"], self.bars, KIT)
        with self.assertRaises(ValueError):
            service.add_graphic(self.deck, j["id"], self.bars)


if __name__ == "__main__":
    unittest.main()
