"""Versions: Keep applies a finished suggestion on the server and saves a version, Undo goes one step back, Undo at
version 1 says "Nothing to undo.", and a database made by the main-era Imprint (no versions table) opens with every
output intact and a version 1."""
import sqlite3
import subprocess
import sys
import unittest
from importlib import import_module

from _load import PKG, ROOT, fake_model, jobs, kits, reset, service, store, HTTPException, run

from test_revise import KIT, deck, finish, harborlight, made

RV = import_module(f"{PKG}.revise")


def routes():
    router = sys.modules["fastapi"].APIRouter()
    RV.routes().mount(router, PKG)
    if not (hasattr(router, "routes") and router.routes and isinstance(router.routes[0], tuple)):
        return None
    return {(m, p): f for m, p, f in router.routes}


class Versions(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.llm = fake_model()
        self.oid = made(self.find, self.llm)

    def stronger(self):
        wait = self.find("287 adults")
        self.llm.queue.append({"options": [
            {"type": "stat", "value": "287", "label": "adults are waiting for a seat", "context": "", "refs": [wait]},
            {"type": "stat", "value": "287", "label": "adults ended the year on our waitlist", "context": "", "refs": [wait]},
            {"type": "stat", "value": "287", "label": "adults have no seat yet", "context": "", "refs": [wait]}]})
        j = finish("element_edit", {"output_id": self.oid, "kit_id": KIT, "slide": 1, "action": "stronger", "text": ""})
        self.assertEqual(j["status"], "done", j["error"])
        return j

    def test_made_is_version_one(self):
        v = service.output_view(self.oid)["versions"]
        self.assertEqual([(x["v"], x["reason"], x["active"]) for x in v], [(1, "Made", True)])

    def test_keep_changes_only_that_slide_and_undo_restores_it(self):
        fn = routes()
        before = service._output(self.oid)["neutral"]
        voiced_before = store.loads(store.one("SELECT content FROM renders WHERE output_id=?", (self.oid,))["content"])["doc"]
        j = self.stronger()
        body = {"job_id": j["id"], "choice": 0}
        view = run(fn[("POST", "/outputs/{output_id}/keep")](self.oid, body)) if fn else (RV.keep(self.oid, j["id"], 0), service.output_view(self.oid))[1]
        self.assertEqual([(x["v"], x["active"]) for x in view["versions"]], [(1, False), (2, True)])
        self.assertEqual(view["versions"][1]["reason"], "Stronger headline, slide 3")
        after = service._output(self.oid)["neutral"]
        self.assertEqual(after["slides"][1]["label"], "adults are waiting for a seat")
        self.assertEqual([s for i, s in enumerate(after["slides"]) if i != 1], [s for i, s in enumerate(before["slides"]) if i != 1])
        # the brand's voiced doc follows: slide 2 is the new wording, every other slide keeps its voicing
        voiced = store.loads(store.one("SELECT content FROM renders WHERE output_id=?", (self.oid,))["content"])["doc"]
        self.assertEqual(voiced["slides"][1]["label"], "adults are waiting for a seat")
        self.assertEqual([s for i, s in enumerate(voiced["slides"]) if i != 1], [s for i, s in enumerate(voiced_before["slides"]) if i != 1])
        # the proof reads the active version
        pr = view["proofs"][0]
        self.assertIn("adults are waiting for a seat", store.dumps(pr["tree"]))

        view = run(fn[("POST", "/outputs/{output_id}/undo")](self.oid, {})) if fn else (RV.undo(self.oid), service.output_view(self.oid))[1]
        self.assertEqual([(x["v"], x["active"]) for x in view["versions"]], [(1, True), (2, False)])
        self.assertEqual(service._output(self.oid)["neutral"], before)
        voiced = store.loads(store.one("SELECT content FROM renders WHERE output_id=?", (self.oid,))["content"])["doc"]
        self.assertEqual(voiced, voiced_before)

        if fn:
            with self.assertRaises(HTTPException) as e:
                run(fn[("POST", "/outputs/{output_id}/undo")](self.oid, {}))
            self.assertEqual(e.exception.status_code, 400)
            self.assertEqual(e.exception.detail, "Nothing to undo.")
        with self.assertRaisesRegex(ValueError, "^Nothing to undo.$"):
            store.undo(self.oid)

    def test_keep_after_undo_drops_the_version_ahead(self):
        j = self.stronger()
        RV.keep(self.oid, j["id"], 0)
        store.undo(self.oid)
        j2 = self.stronger()
        self.assertEqual(RV.keep(self.oid, j2["id"], 2), 2)
        v = store.versions(self.oid)
        self.assertEqual([(x["v"], x["active"]) for x in v], [(1, False), (2, True)])
        self.assertEqual(service._output(self.oid)["neutral"]["slides"][1]["label"], "adults have no seat yet")

    def test_delete_output_drops_versions(self):
        service.delete_output(self.oid)
        self.assertEqual(store.q("SELECT * FROM output_versions WHERE output_id=?", (self.oid,)), [])


class MainEraDatabase(unittest.TestCase):
    def test_opens_with_nothing_lost(self):
        reset()
        old = subprocess.run(["git", "show", "0faa05e:store.py"], cwd=str(ROOT), capture_output=True, text=True)
        if old.returncode != 0:
            self.skipTest("main-era store.py not in this checkout")
        ns: dict = {}
        schema = old.stdout.split('SCHEMA = """', 1)[1].split('"""', 1)[0]
        self.assertNotIn("output_versions", schema)
        store.forget_everything()
        path = store.root() / store.DB_NAME
        c = sqlite3.connect(str(path))
        c.executescript(schema)
        doc = {"title": "A warming center that stays open", "dek": "Sample", "sections": [], "points": []}
        c.execute("INSERT INTO outputs(id, kind, title, source_ids, brief, neutral, kit_ids, status, created_at, updated_at) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)", ("o_0123456789ab", "onepager", doc["title"], "[]", "b", store.dumps(doc),
                                                 store.dumps([KIT]), "ready", 1762650000.0, 1762650000.0))
        c.execute("INSERT INTO renders(output_id, kit_id, kit_version, content, voice_note, decisions, created_at) VALUES(?,?,?,?,?,?,?)",
                  ("o_0123456789ab", KIT, 1, store.dumps({"doc": doc, "reverted": []}), "", "{}", 1762650000.0))
        c.execute("INSERT INTO settings(key, value) VALUES('prefs', '{\"kit\": \"x\"}')")
        c.commit()
        c.close()
        rows = store.q("SELECT id, title, neutral FROM outputs")
        self.assertEqual(len(rows), 1)
        self.assertEqual(store.loads(rows[0]["neutral"]), doc)
        self.assertEqual(store.get_setting("prefs"), {"kit": "x"})
        v = store.versions("o_0123456789ab")
        self.assertEqual([(x["v"], x["reason"], x["active"], x["created_at"]) for x in v], [(1, "Made", True, 1762650000.0)])
        n = store.add_version("o_0123456789ab", {**doc, "title": "A warming center open every night"}, "Edited")
        self.assertEqual(n, 2)
        self.assertEqual(store.undo("o_0123456789ab"), 1)
        self.assertEqual(store.loads(store.one("SELECT neutral FROM outputs")["neutral"]), doc)


class Claims(unittest.TestCase):
    """Contract F: the proof carries claims, slides and passages used from checks.claims_map."""

    def test_harborlight_deck_proof_has_claims(self):
        ids, by_ref, find = harborlight()
        llm = fake_model()
        oid = made(find, llm)
        pr = service.output_view(oid)["proofs"][0]
        claims = pr["claims"]
        by_value = {c["value"]: (cid, c) for cid, c in claims.items()}
        cid, c212 = by_value["212"]
        self.assertEqual(c212["status"], "computed")
        self.assertEqual(c212["math"]["op"], "difference")
        self.assertEqual([o["value"] for o in c212["math"]["operands"]], ["1,148", "936"])
        self.assertTrue(all(o["source_n"] == 1 for o in c212["math"]["operands"]))
        self.assertEqual(c212["slides"], [1])
        for v in ("2026", "21", "October 21", "2027", "FY2027"):
            self.assertNotIn(v, by_value)
        self.assertEqual(by_value["287"][1]["status"], "exact")
        self.assertEqual(by_value["287"][1]["slides"], [1, 2])  # the cover only repeats an opening exhibit's finding (round 3)
        self.assertEqual(by_value["1,200"][1]["status"], "missing")
        # slides: 0-based frames, frame 0 the title slide; every claim id it lists is in claims
        self.assertEqual([s["i"] for s in pr["slides"]], list(range(8)))
        self.assertEqual(pr["slides"][0]["type"], "title")
        self.assertTrue(pr["slides"][1]["title"].startswith("Demand is outgrowing our seats"))
        self.assertIn(cid, pr["slides"][1]["claims"])
        self.assertTrue(all(c in claims for s in pr["slides"] for c in s["claims"]))
        # passages used: every cited passage, with the frames it shows on
        ref = find("enrolled 1,148")
        self.assertIn(ref, pr["passages_used"])
        self.assertIn(1, pr["passages_used"][ref]["slides"])
        self.assertIsInstance(pr["slide_count"], int)
        self.assertIn("not found in your sources", pr["stamp"])

    def test_scene_spans_carry_claim_ids(self):
        ids, by_ref, find = harborlight()
        oid = made(find, fake_model())
        pr = service.output_view(oid)["proofs"][0]
        got = []

        def walk(n, f):
            if isinstance(n, dict):
                if "tr" in n:
                    got.append((f, "ip-sc-r" in str(n.get("c")), pr["claims"][n["tr"]]["value"]))
                for k in n.get("k") or []:
                    walk(k, f)
        for f, sc in enumerate(pr["tree"]["k"]):
            walk(sc, f)
        self.assertIn((1, False, "212"), got)
        self.assertIn((1, True, "936"), got)  # the exhibit bar traces its value
        self.assertFalse([g for g in got if g[1] and g[0] != 1])  # bars only on the exhibit
        self.assertFalse([g for g in got if g[2] in ("21", "2026", "2")])  # no date or page number
        for f, _bar, v in got:
            self.assertIn(f, next(c for c in pr["claims"].values() if c["value"] == v)["slides"])

    def test_stamp_wording(self):
        S = service.stamp
        self.assertEqual(S({}), "No numbers to check.")
        self.assertEqual(S({"c1": {"kind": "count", "status": "exact"}}), "The 1 number matches your sources.")
        many = {f"c{i}": {"kind": "count", "status": st} for i, st in enumerate(["exact"] * 12 + ["close", "computed"])}
        self.assertEqual(S(many), "All 14 numbers match your sources.")


if __name__ == "__main__":
    unittest.main()


class EditTextUndo(unittest.TestCase):
    def test_edit_text_is_one_undo_away(self):
        ids, by_ref, find = harborlight()
        oid = made(find, fake_model())
        neutral = service._output(oid)["neutral"]
        path, old = next((f"slides.{i}.heading", s.get("heading")) for i, s in enumerate(neutral["slides"]) if s.get("heading"))
        service.edit(oid, path, "A plain new heading")
        self.assertEqual(service._output(oid)["neutral"]["slides"][int(path.split(".")[1])]["heading"], "A plain new heading")
        store.undo(oid)
        self.assertEqual(service._output(oid)["neutral"]["slides"][int(path.split(".")[1])]["heading"], old)
