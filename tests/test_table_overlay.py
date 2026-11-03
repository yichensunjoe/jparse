import unittest
from types import SimpleNamespace

from src.table_overlay import _cell_rect, _clean, _needs_translation


class TableOverlayHelpersTest(unittest.TestCase):
    def test_needs_translation_skips_chinese_and_numbers(self):
        self.assertTrue(_needs_translation("Table 1"))
        self.assertTrue(_needs_translation("Safety analysis"))
        self.assertFalse(_needs_translation("表 1"))
        self.assertFalse(_needs_translation("1234"))
        self.assertTrue(_needs_translation("SSC"))  # translated or left unchanged later

    def test_clean_collapses_pdf_line_breaks(self):
        self.assertEqual(_clean("  Safety   analysis\nprep "), "Safety analysis prep")

    def test_cell_rect_uses_inset_and_top_left_geometry(self):
        cell = SimpleNamespace(x=10.0, y=20.0, w=100.0, h=50.0)
        rect = _cell_rect(cell)
        self.assertAlmostEqual(rect.x0, 11.6)
        self.assertAlmostEqual(rect.y0, 21.6)
        self.assertAlmostEqual(rect.x1, 108.4)
        self.assertAlmostEqual(rect.y1, 68.4)

    def test_tiny_cell_is_skipped(self):
        cell = SimpleNamespace(x=10.0, y=20.0, w=5.0, h=5.0)
        self.assertIsNone(_cell_rect(cell))


if __name__ == "__main__":
    unittest.main()
