"""Contract D: a make job with an outline builds exactly the outline's slides, in its order, with its titles, after the
person moved a slide and changed a title. Output rows say ``building`` while the make job runs."""
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, service, store

from test_revise import KIT, finish, harborlight

RV = import_module(f"{PKG}.revise")


class MakeFromOutline(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, f = harborlight()
        self.llm = fake_model()
        self.f = f
        served, wait, rec, tutors = f("enrolled 1,148"), f("287 adults"), f("approve an FY2027"), f("214 volunteer")
        self.slides = {
            "exhibit": {"type": "exhibit", "heading": "Enrollment by year", "unit": "Adults", "refs": [served, wait],
                        "bars": [{"label": "FY2025", "value": "936", "ref": served}, {"label": "FY2026", "value": "1,148", "ref": served}]},
            "stat": {"type": "stat", "value": "287", "label": "adults on the waitlist", "context": "Most at two sites.", "refs": [wait]},
            "content": {"type": "content", "heading": "Volunteers", "refs": [tutors], "bullets": [{"text": "9,870 hours of tutoring", "ref": tutors}]},
            "section": {"type": "section", "heading": "The ask", "subtitle": "What the budget adds", "refs": [rec]},
            "closing": {"type": "closing", "heading": "Fund it", "text": "Every new seat shortens the wait.", "cta": "Talk with us", "refs": [rec]},
        }
        oid = "ol_" + "a1b2c3d4e5f6"
        store.set_setting(f"outline:{oid}", {"outline_id": oid, "kind": "deck", "brief": {}, "source_ids": self.ids, "slides": [], "warnings": []})
        rows = [{"title": "Demand is outgrowing our seats", "type": "exhibit", "refs": [served, wait]},
                {"title": "287 adults ended the year waiting", "type": "stat", "refs": [wait]},
                {"title": "Volunteers gave 9,870 hours", "type": "content", "refs": [tutors]},
                {"title": "A sixth site for the waitlist", "type": "section", "refs": [rec]},
                {"title": "Fund the sixth site", "type": "closing", "refs": [rec]}]
        RV.save_outline(oid, rows)
        # the person moves slide 4 up one place and changes a title
        rows[2], rows[3] = rows[3], rows[2]
        rows[0]["title"] = "Demand for adult literacy is outgrowing our five sites"
        self.outline = RV.save_outline(oid, rows)
        self.oid = oid

    def make(self, order):
        self.llm.queue.append({"title": "A sixth site", "subtitle": "For funders", "slides": [self.slides[t] for t in order]})
        j = jobs.start("make", f"t:outline:{store.now()}", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                                            "brief": "A deck for funders", "outline_id": self.oid}, wait=True)
        j = jobs.get(j["id"])
        self.assertEqual(j["status"], "done", j["error"])
        return j, service._output(j["result"]["output_id"])["neutral"]

    def test_follows_the_edited_order_and_titles(self):
        want = [(s["type"], s["title"]) for s in self.outline["slides"]]
        self.assertEqual([t for t, _ in want], ["exhibit", "stat", "section", "content", "closing"])
        for order in (["exhibit", "stat", "section", "content", "closing"], ["stat", "closing", "content", "exhibit", "section"]):
            j, doc = self.make(order)
            self.assertEqual([(s["type"], s["label"] if s["type"] == "stat" else s["heading"]) for s in doc["slides"]], want)
            self.assertTrue(any("Fund the sixth site" in str(c.get("instructions")) for c in self.llm.calls))
            self.assertIn("Writing 6 slides from your outline", [s["text"] for s in j["steps"]])

    def test_too_few_slides_back_is_a_cut_off(self):
        self.llm.queue.append({"title": "A sixth site", "subtitle": "x", "slides": [self.slides["stat"]]})
        j = jobs.start("make", f"t:outline-short:{store.now()}", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                                                  "brief": "b", "outline_id": self.oid}, wait=True)
        self.assertEqual(jobs.get(j["id"])["status"], "failed")
        self.assertEqual(service.list_outputs(), [])

    def test_building_flag(self):
        o = store.new_id("o")
        store.run("INSERT INTO outputs(id, kind, title, source_ids, kit_ids, status, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
                  (o, "deck", "", "[]", store.dumps([KIT]), "writing", store.now(), store.now()))
        self.assertTrue(next(r for r in service.list_outputs() if r["id"] == o)["building"])
        store.run("UPDATE outputs SET status='ready' WHERE id=?", (o,))
        self.assertFalse(next(r for r in service.list_outputs() if r["id"] == o)["building"])


if __name__ == "__main__":
    unittest.main()
