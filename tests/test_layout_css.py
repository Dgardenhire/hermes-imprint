"""The Brands and Storage pages are one-column grids that hold wider grids of cards. A grid column left at its default
(auto) is as wide as its widest child, so four 300 px Studio cards held it at 1,266 px and pushed the fourth column off the
right edge on windows narrower than about 1,500 px. Each of these grids must name its column minmax(0,1fr).
harness/check_layout.py does the same check in a browser, at widths and zoom levels."""
import re
import unittest
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "desktop" / "src" / "plugin.js").read_text()


def rule(selector):
    m = re.search(r"(?m)^" + re.escape(selector) + r"\{([^}]*)\}", CSS)
    assert m, f"rule {selector} not found"
    return m.group(1)


class OneColumnPages(unittest.TestCase):
    def test_page_grids_cap_their_column(self):
        for sel in (".imp-kits,.imp-store", ".imp-kitgrid-wrap", ".imp-lib", ".imp-field"):
            with self.subTest(sel):
                body = rule(sel)
                self.assertIn("display:grid", body)
                self.assertIn("grid-template-columns:minmax(0,1fr)", body)

    def test_built_bundle_matches(self):
        bundle = (Path(__file__).resolve().parents[1] / "desktop" / "plugin.js").read_text()
        self.assertIn(".imp-kitgrid-wrap{display:grid;grid-template-columns:minmax(0,1fr)", bundle)


if __name__ == "__main__":
    unittest.main()
