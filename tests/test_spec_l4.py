"""Loop 4: the model designs each slide as a positioned spec in brand roles; Letterpress draws it in the brand's faces and
colors, traces every number in every element, turns a number no source holds into a flagged blank, and measures each
slide (overflow, off the slide, overlap, the foot), sending a broken slide back to the model once, alone."""
import copy
import unittest
from importlib import import_module

from _load import PKG, fake_model, jobs, store, service, kits
from test_revise import KIT, harborlight
from test_plain_r13 import DRAFT

K = import_module(f"{PKG}.content")
CK = import_module(f"{PKG}.checks")
RD = import_module(f"{PKG}.render_deck")
SP = import_module(f"{PKG}.spec")
SC = import_module(f"{PKG}.scene")
L = import_module(f"{PKG}.layout")

SPECS = {"slides": [
    {"ground": "primary", "footer": False, "title": "Harborlight Literacy", "els": [
        {"type": "text", "x": 60, "y": 150, "w": 700, "h": 60, "text": "Harborlight Literacy", "style": "title", "size": 48},
        {"type": "text", "x": 60, "y": 230, "w": 700, "h": 60, "text": "Opening a sixth site at Eastgate. A proposal to our funders.",
         "style": "body", "size": 22}]},
    {"title": "Demand keeps growing: 287 adults are waiting", "els": [
        {"type": "text", "x": 40, "y": 40, "w": 860, "h": 50, "text": "Demand keeps growing: 287 adults are waiting", "style": "title"},
        {"type": "bars", "x": 40, "y": 120, "w": 520, "h": 300, "orient": "vertical", "items": [
            {"label": "FY2025", "value": "936"}, {"label": "FY2026", "value": "1,148", "highlight": True}]},
        {"type": "figure", "x": 600, "y": 120, "w": 300, "h": 140, "value": "212", "label": "more adults than the year before",
         "note": "up 31%", "fill": "tint"},
        {"type": "figure", "x": 600, "y": 280, "w": 300, "h": 140, "value": "287", "label": "adults on the waitlist", "fill": "tint"}]},
    {"title": "What we ask", "els": [
        {"type": "text", "x": 40, "y": 40, "w": 860, "h": 50, "text": "What we ask", "style": "title"},
        {"type": "callout", "x": 40, "y": 120, "w": 520, "h": 160, "title": "The ask",
         "text": "Help fund the $190,000 increase in our FY2027 budget."},
        {"type": "quote", "x": 600, "y": 120, "w": 300, "h": 240, "text": "This program changed my whole family.", "who": "A learner"}]},
]}


def kit():
    return kits.get(KIT)


class Spec(unittest.TestCase):
    def setUp(self):
        self.ids, self.by_ref, self.find = harborlight()
        self.slides = K.parse_plain(DRAFT)
        self.doc = service.spec_doc(copy.deepcopy(SPECS["slides"]), self.slides, self.by_ref)

    def scenes(self, doc):
        k = kit()
        idx, rows = L.source_index(doc, self.by_ref)
        return RD.scenes(doc, k, kits.palette(k), kits.faces(k), idx, rows, "", self.by_ref)

    def test_every_element_is_a_checked_field(self):
        paths = [p for p, _t, _r in K.field_texts(self.doc)]
        self.assertIn("cover.els.0", paths)
        self.assertIn("slides.0.els.1.items.1", paths)  # the 1,148 bar
        self.assertIn("slides.1.els.2.quote", paths)
        g = CK.grounding(self.doc, self.by_ref)
        st = {(i["path"], i["value"]): i["status"] for i in g["items"]}
        self.assertEqual(st[("slides.0.els.1.items.1", "1148")], "ok")
        self.assertIn(st[("slides.0.els.2", "212")], ("computed", "ok"))

    def test_an_invented_number_is_a_flagged_blank_in_its_element(self):
        g = CK.grounding(self.doc, self.by_ref)
        doc, flags = K.flag_unsupported(g["doc"], g["items"], self.by_ref)
        self.assertIn("up " + K.NUMBER_FLAG, doc["slides"][0]["els"][2]["note"])
        self.assertEqual(doc["slides"][0]["els"][2]["value"], "212")
        self.assertTrue(any(f["path"] == "slides.0.els.2" for f in flags))

    def test_drawn_in_the_brand_and_clean(self):
        scs, ty = self.scenes(self.doc)
        self.assertEqual([sc["kind"] for sc in scs], ["spec", "spec", "spec"])
        self.assertEqual([sc.get("problems") for sc in scs], [[], [], []])
        k = kit()
        faces = {el["face"] for sc in scs for el in sc["els"] if el["t"] == "text"}
        self.assertTrue(faces <= set(SC.ROLES))
        pal = kits.palette(k)
        self.assertEqual(scs[0]["bg"].lower(), SP.roles(__import__(f"{PKG}.systems", fromlist=["x"]).Tokens(pal, k), True)["paper"].lower())
        self.assertTrue(SC.png(scs[1], ty, scale=1.0).startswith(b"\x89PNG"))

    def test_problems_are_measured(self):
        bad = copy.deepcopy(SPECS["slides"])
        bad[1]["els"].append({"type": "text", "x": 600, "y": 130, "w": 300, "h": 40, "text": "word " * 80, "style": "body"})
        bad[1]["els"].append({"type": "text", "x": 900, "y": 470, "w": 200, "h": 60, "text": "Off the edge", "style": "body"})
        scs, _ty = self.scenes(service.spec_doc(bad, self.slides, self.by_ref))
        kinds = {p["kind"] for p in scs[1]["problems"]}
        self.assertTrue({"overflow", "overlap", "off", "foot"} <= kinds, kinds)
        self.assertTrue(scs[1]["long"])

    def test_the_length_holds_and_the_closing_ask_stays(self):
        many = copy.deepcopy(SPECS["slides"]) + [copy.deepcopy(SPECS["slides"][1]) for _ in range(3)] + [copy.deepcopy(SPECS["slides"][2])]
        self.assertEqual(service.spec_cap("A 7 to 9 slide funder deck", self.slides), 3)  # the draft has 3 slides
        d = service.spec_doc(many, self.slides, self.by_ref, "A 7 to 9 slide funder deck")
        self.assertEqual(1 + len(d["slides"]), 3)
        self.assertEqual(d["slides"][-1]["heading"], "What we ask")

    def test_pptx_and_pdf_draw_the_same_slides(self):
        k = kit()
        pal, faces = kits.palette(k), kits.faces(k)
        idx, rows = L.source_index(self.doc, self.by_ref)
        px = RD.render_pptx(self.doc, k, pal, idx, rows, self.by_ref, faces=faces)
        self.assertTrue(px.startswith(b"PK"))
        from pptx import Presentation
        import io
        prs = Presentation(io.BytesIO(px))
        self.assertEqual(len(prs.slides), 3)
        words = " ".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
        self.assertIn("1,148", words)
        self.assertIn("Help fund the $190,000", words)
        pdf = RD.render_pdf(self.doc, k, pal, faces, idx, rows, "", passages=self.by_ref)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_the_trace_reaches_bars(self):
        k = kit()
        tree, scs = RD.deck_tree(self.doc, k, kits.palette(k), kits.faces(k), self.by_ref)
        self.assertIn("ip-sk-spec", tree["k"][1]["c"])

    def test_the_make_job_designs_fixes_once_and_keeps_the_draft(self):
        llm = fake_model()
        broken = copy.deepcopy(SPECS)
        broken["slides"][2]["els"].append({"type": "text", "x": 40, "y": 300, "w": 300, "h": 30, "text": "word " * 60, "style": "body"})
        fixed = copy.deepcopy(SPECS["slides"][2])
        llm.queue = [{"draft": DRAFT}, broken, fixed]
        service.PLAIN, service.SPEC = True, True
        try:
            j = jobs.start("make", "t:spec", {"kind": "deck", "source_ids": self.ids, "kit_ids": [KIT],
                                              "brief": "A 7 to 9 slide funder deck"}, wait=True)
            j = jobs.get(j["id"])
        finally:
            service.PLAIN = False
        self.assertEqual(j["status"], "done", j.get("error"))
        self.assertEqual([c["purpose"] for c in llm.calls], ["letterpress.plain_draft", "letterpress.spec_design", "letterpress.spec_fix"])
        oid = j["result"]["output_id"]
        out = service._output(oid)
        self.assertEqual([s["type"] for s in out["neutral"]["slides"]], ["spec", "spec"])
        rec = store.loads(store.get_setting(f"spec_record_of:{oid}"))
        self.assertEqual(rec["fixed"][0]["frame"], 2)
        self.assertFalse(rec.get("left"))
        view = service.output_view(oid)
        tree = view["proofs"][0]["tree"]
        frame = [k for k in tree["k"] if "ip-sk-spec" in k.get("c", "")][1]  # the exhibit slide

        def spans(n, out):
            if isinstance(n, dict):
                if "ip-num" in str(n.get("c") or ""):
                    out.append(n)
                for k in n.get("k") or []:
                    spans(k, out)
            return out
        nums = spans(frame, [])
        self.assertIn("1,148", [n.get("x") for n in nums])
        self.assertTrue(all(n.get("tr") for n in nums if n.get("x") == "1,148"))  # a claim id on the number
        bars = [k for k in frame["k"] if "ip-sc-r" in str(k.get("c")) and k.get("tr")]
        self.assertTrue(bars)  # hovering a bar traces its value
        o = store.get_setting("outline:" + store.get_setting(f"outline_of:{oid}"))
        self.assertEqual([s["title"] for s in o["slides"]], ["Demand keeps growing", "What we ask"])


if __name__ == "__main__":
    unittest.main()
