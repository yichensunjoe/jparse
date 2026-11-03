import unittest

from src.figure_overlay import (
    _TERM_FIXES,
    _container_kind,
    _fit_size,
    _has_orphan_line,
    _needs_translation,
    _text_width,
    _wrap_text,
)


class FigureOverlayHelpersTest(unittest.TestCase):
    def test_container_kinds(self):
        self.assertEqual(_container_kind((0.05, 0.16, 0.25)), "dark")
        self.assertEqual(_container_kind((0.31, 0.65, 0.18)), "green")
        self.assertEqual(_container_kind((0.80, 0.80, 0.81)), "gray")
        self.assertEqual(_container_kind((0.95, 0.95, 0.95)), "other")

    def test_explicit_header_newline_is_preserved(self):
        lines = _wrap_text("协议\n- 对齐", 110, 20)
        self.assertEqual(lines, ["协议", "- 对齐"])

    def test_dash_header_is_kept_on_one_line(self):
        text = "协议—对齐"
        self.assertEqual(_wrap_text(text, 110, 20), [text])

    def test_single_character_cjk_line_is_rejected(self):
        self.assertTrue(_has_orphan_line(["B. 核安全设计", "协", "议（NSDA）"]))
        self.assertFalse(_has_orphan_line(["B. 核安全设计", "协议（NSDA）"]))

    def test_nontext_punctuation_line_is_rejected(self):
        self.assertTrue(_has_orphan_line(["交与批准（见表 1", "）"]))

    def test_fit_size_avoids_orphan_line(self):
        import fitz

        rect = fitz.Rect(0, 0, 87.3, 104)
        size = _fit_size("B. 核安全设计协议（NSDA）的提交与批准（见表 1）", rect, 10)
        lines = _wrap_text("B. 核安全设计协议（NSDA）的提交与批准（见表 1）", rect.width - 6.0, size)
        self.assertFalse(_has_orphan_line(lines))

    def test_only_latin_text_needs_translation(self):
        self.assertTrue(_needs_translation("Phases"))
        self.assertFalse(_needs_translation("阶段"))
        self.assertFalse(_needs_translation("1234"))

    def test_term_fix_keeps_header_compact(self):
        self.assertEqual(_TERM_FIXES["协议 - 对齐"], "协议—对齐")
        self.assertGreater(_text_width("阶段", 22), 20)


if __name__ == "__main__":
    unittest.main()
