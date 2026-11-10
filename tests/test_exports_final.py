"""Exports are safe to send (Nov 8 persona run): the finished files carry no trace marks, no production note,
proper footnotes, a phone-width layout, and a PowerPoint built on real placeholders."""
import io
import re
import unittest
from pathlib import Path

from _load import add_samples, fake_model, make, render_html, reset, service


def kit_without_sources():
    k = service.KITS.save_new({**service.KITS.get("plain-notice"), "name": "Menu kit",
                               "rules": {"sources": False, "page_numbers": False, "date": True, "required": []}})
    return k["id"]


class Finished(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.ids = [s["id"] for s in add_samples()]

    def _out(self, kits, kind="onepager"):
        j = make(self.ids, kits, kind=kind, brief=f"A {kind}")
        self.assertEqual(j["status"], "done", j)
        return j["result"]["output_id"]

    def test_a_kit_with_no_source_list_gets_no_marks_anywhere_on_exports(self):
        kid = kit_without_sources()
        oid = self._out([kid])
        page = Path(service.export(oid, kid, "html")["path"]).read_text()
        self.assertNotIn("ip-ref", page.split("</style>")[1])
        self.assertNotIn("Sources", page.split("</style>")[1])
        from pypdf import PdfReader
        text = PdfReader(service.export(oid, kid, "pdf")["path"]).pages[0].extract_text()
        self.assertNotIn("Sources", text)
        self.assertNotIn("Set in", text)
        self.assertTrue(service.proof(oid, kid)["traces"], "the proof keeps every trace")

    def test_html_reflows_at_phone_width(self):
        oid = self._out(["plain-notice"])
        page = Path(service.export(oid, "plain-notice", "html")["path"]).read_text()
        self.assertIn('name="viewport" content="width=device-width', page)
        self.assertIn("@media (max-width:700px)", page)
        self.assertIn("grid-template-columns:minmax(0,1fr)!important", page)
        self.assertNotIn("min-height:11in", page)

    def test_footnote_mark_never_touches_a_figure(self):
        node = {"t": "p", "k": [{"t": "span", "x": "Churro bites, $3"}, {"t": "sup", "c": "ip-ref", "x": "2"}]}
        self.assertEqual(render_html.node_html(node, links=True), '<p><span>Churro bites, $3</span>&nbsp;<sup class="ip-ref"><a href="#ip-src-2">2</a></sup></p>')

    def test_deck_pdf_and_script_carry_no_production_note(self):
        from pypdf import PdfReader
        oid = self._out(["plain-notice"], "deck")
        first = PdfReader(service.export(oid, "plain-notice", "pdf")["path"]).pages[0].extract_text()
        self.assertNotIn("Set in", first)
        oid = self._out(["plain-notice"], "audio")
        script = Path(service.export(oid, "plain-notice", "script")["path"]).read_text()
        self.assertNotIn("Set in", script)
        self.assertIn("Sources", script)

    def test_pptx_slides_have_titles_in_placeholders(self):
        from pptx import Presentation
        from pptx.enum.shapes import PP_PLACEHOLDER
        oid = self._out(["plain-notice"], "deck")
        prs = Presentation(service.export(oid, "plain-notice", "pptx")["path"])
        for i, s in enumerate(prs.slides):
            title = s.shapes.title
            self.assertIsNotNone(title, f"slide {i + 1} has a title placeholder")
            self.assertTrue(title.text_frame.text.strip(), f"slide {i + 1} title is filled")
        names = [s.slide_layout.name for s in prs.slides]
        self.assertEqual(names[0], "Title Slide")
        self.assertIn("Title and Content", names)
        content = next(s for s in prs.slides if s.slide_layout.name == "Title and Content")
        body = [sh for sh in content.placeholders if sh.placeholder_format.type == PP_PLACEHOLDER.OBJECT]
        self.assertTrue(body and len(body[0].text_frame.paragraphs) >= 2, "points sit in the body placeholder")
        self.assertNotIn("• ", body[0].text_frame.text, "native bullets, not typed ones")
        # the layouts were widened to 16:9 with the slides, so Reset Slide lands in the same place
        t = prs.slide_layouts[1].placeholders[0]
        self.assertGreater(t.left + t.width, prs.slide_width * 0.8)



class RequiredLinesAndLength(unittest.TestCase):
    def setUp(self):
        reset()
        self.llm = fake_model()
        self.ids = [s["id"] for s in add_samples()]

    def test_own_kits_print_their_line_unless_left_off(self):
        k = service.KITS.save_new({**service.KITS.get("plain-notice"), "name": "Harborlight",
                                   "rules": {"sources": True, "page_numbers": True, "date": True,
                                             "required": ["Harborlight Literacy Project is a 501(c)(3) nonprofit."]}})
        j = make(self.ids, [k["id"], "docket"], brief="A one-pager")
        oid = j["result"]["output_id"]
        from pypdf import PdfReader
        self.assertIn("501(c)(3)", PdfReader(service.export(oid, k["id"], "pdf")["path"]).pages[0].extract_text())
        self.assertNotIn("legal advice", PdfReader(service.export(oid, "docket", "pdf")["path"]).pages[0].extract_text())
        service.set_required(oid, k["id"], False)
        self.assertNotIn("501(c)(3)", PdfReader(service.export(oid, k["id"], "pdf")["path"]).pages[0].extract_text())

    def test_length_check_reads_the_brief(self):
        from _load import checks
        self.assertEqual(checks.target_minutes("A 90-second audio brief"), 1.5)
        self.assertEqual(checks.target_minutes("a three-minute spoken brief"), 3.0)
        self.assertEqual(checks.pill_length(1.3, "A 90-second audio brief")["tone"], "good")
        self.assertIn("90 seconds", checks.pill_length(1.3, "A 90-second audio brief")["label"])
        self.assertEqual(checks.pill_length(1.3, "")["tone"], "warn")
