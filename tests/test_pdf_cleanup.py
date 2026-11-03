import unittest

import fitz

from src.pdf_cleanup import _candidate_rules, _is_neutral_dark, _touches_source_text


class PdfCleanupHelpersTest(unittest.TestCase):
    def test_only_neutral_dark_rules_are_candidates(self):
        self.assertTrue(_is_neutral_dark((0.0, 0.0, 0.0)))
        self.assertFalse(_is_neutral_dark((0.27, 0.47, 0.53)))
        self.assertFalse(_is_neutral_dark((0.75, 0.75, 0.75)))
        self.assertFalse(_is_neutral_dark(None))

    def test_inline_underline_touches_source_text(self):
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((20, 70), "Departmental Elements", fontsize=10)
        rect = fitz.Rect(20, 70, 120, 70.6)
        self.assertTrue(_touches_source_text(page, rect))
        self.assertFalse(_touches_source_text(page, fitz.Rect(20, 120, 120, 120.6)))
        doc.close()

    def test_standalone_and_coloured_rules_are_not_candidates(self):
        doc = fitz.open()
        page = doc.new_page(width=200, height=200)
        page.insert_text((45, 70), "Heading", fontsize=10)
        page.draw_rect(fitz.Rect(45, 70, 145, 70.6), color=None, fill=(0, 0, 0))
        page.draw_rect(fitz.Rect(45, 120, 145, 120.6), color=None, fill=(0, 0, 0))
        page.draw_rect(fitz.Rect(45, 160, 145, 160.6), color=None, fill=(0.27, 0.47, 0.53))
        rules = _candidate_rules(page, [])
        self.assertEqual(len(rules), 1)
        self.assertAlmostEqual(rules[0].y0, 70.0, places=1)
        doc.close()


if __name__ == "__main__":
    unittest.main()
