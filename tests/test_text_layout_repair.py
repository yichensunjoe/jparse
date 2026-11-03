import unittest

import fitz

from src.text_layout_repair import (
    _extract_targets,
    _find_marker,
    _heading_label,
    _marker_label,
    _normalize_target,
    _page_indexes,
    _source_groups,
    _wrap_text,
)


class TextLayoutRepairHelpersTest(unittest.TestCase):
    def test_list_markers_do_not_match_section_references(self):
        self.assertEqual(_marker_label("a. Departmental Elements"), "a.")
        self.assertEqual(_marker_label("b. Office of Nuclear Energy"), "b.")
        self.assertEqual(_marker_label("1) Exemption"), "1)")
        self.assertEqual(_marker_label("• The Office"), "•")
        self.assertIsNone(_marker_label("2.1.d., this Standard applies"))
        self.assertIsNone(_marker_label("2.1.b 段所述设施"))

    def test_heading_labels(self):
        self.assertEqual(_heading_label("2.1 Applicability"), ("2.1", "Applicability"))
        self.assertEqual(_heading_label("3.0 ROLES AND AUTHORITIES"), ("3.0", "ROLES AND AUTHORITIES"))
        self.assertIsNone(_heading_label("2.1.d., this Standard"))

    def test_marker_search_skips_reference_inside_paragraph(self):
        text = "第2.1.b段所述设施和活动。 b. 核能办公室设施和活动。"
        found = _find_marker(text, "b.", 0)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(text[found[0] : found[1]], "b.")
        self.assertGreater(found[0], text.index("第2.1.b"))

    def test_source_groups_keep_list_indentation_and_underline(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 83), "2.1 Applicability", fontname="tibo", fontsize=12)
        page.insert_text((126, 102), "a.", fontname="tiro", fontsize=12)
        page.insert_text((144, 102), "Departmental Elements and more text", fontname="tiro", fontsize=12)
        page.insert_text((144, 116), "continuation of the first item", fontname="tiro", fontsize=12)
        page.insert_text((126, 130), "b.", fontname="tiro", fontsize=12)
        page.insert_text((144, 130), "Office of Nuclear Energy", fontname="tiro", fontsize=12)
        page.insert_text((144, 144), "continuation of the second item", fontname="tiro", fontsize=12)
        page.draw_rect(fitz.Rect(144, 103, 256, 103.6), color=None, fill=(0, 0, 0))

        groups = _source_groups(page)
        doc.close()

        self.assertEqual([group.label for group in groups], ["2.1", "a.", "b."])
        self.assertEqual(groups[1].body_x, 144.0)
        self.assertEqual(groups[1].cont_x, 144.0)
        self.assertTrue(groups[1].underline)
        self.assertFalse(groups[2].underline)

    def test_target_extraction_handles_merged_paragraph_markers(self):
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 83), "2.1 适用性", fontname="china-s", fontsize=12)
        page.insert_text(
            (126, 102),
            "a. 部门组成部分。本标准适用于所有部门组成部分。 \x00 b. 核能办公室设施和活动。",
            fontname="china-s",
            fontsize=12,
        )
        page.insert_text((126, 130), "c. 承包商。 \x00 1) 豁免。本标准适用于设施。", fontname="china-s", fontsize=12)
        page.insert_text((126, 160), "2) 豁免。设施免于遵守本标准。", fontname="china-s", fontsize=12)
        page.insert_text((72, 200), "3.0 角色与权限", fontname="china-s", fontsize=14)
        page.insert_text((90, 225), "• 核能办公室负责授权。", fontname="china-s", fontsize=12)
        page.insert_text((72, 260), "3) 其他等效性。", fontname="china-s", fontsize=12)

        # The synthetic page is only used to prove the target splitter is
        # driven by source labels; it intentionally has no real NUL glyphs.
        groups = [
            type("G", (), {"kind": "heading", "label": "2.1", "bold": True})(),
            type("G", (), {"kind": "item", "label": "a.", "bold": False})(),
            type("G", (), {"kind": "item", "label": "b.", "bold": False})(),
            type("G", (), {"kind": "item", "label": "c.", "bold": False})(),
            type("G", (), {"kind": "item", "label": "1)", "bold": False})(),
            type("G", (), {"kind": "item", "label": "2)", "bold": False})(),
            type("G", (), {"kind": "item", "label": "3)", "bold": False})(),
            type("G", (), {"kind": "heading", "label": "3.0", "bold": True})(),
            type("G", (), {"kind": "item", "label": "•", "bold": False})(),
        ]
        stream = (
            "2.1 适用性 a. 部门组成部分。本标准适用于所有部门组成部分。 "
            "b. 核能办公室设施和活动。 c. 承包商。 1) 豁免。本标准适用于设施。 "
            "2) 豁免。设施免于遵守本标准。 3) 其他等效性。 3.0 角色与权限 "
            "• 核能办公室负责授权。"
        )
        targets = _extract_targets(stream, groups)
        doc.close()

        self.assertIsNotNone(targets)
        assert targets is not None
        self.assertEqual(targets[0], "适用性")
        self.assertEqual(targets[7], "角色与权限")
        self.assertEqual(targets[1], "部门组成部分。本标准适用于所有部门组成部分。")
        self.assertEqual(targets[5], "豁免。设施免于遵守本标准。")

    def test_normalize_target_fixes_halfwidth_punctuation(self):
        text = _normalize_target("部门组成部分,[1] ,在 第2.1.b 段。\uf9e4")
        self.assertIn("，[1]，", text)
        self.assertIn("理", text)
        self.assertNotIn(" ,", text)

    def test_wrap_text_keeps_closing_punctuation_with_previous_line(self):
        font = fitz.Font("china-s")
        lines = _wrap_text("标准。", font, 12, 24.1, 24.1)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].text, "标准。")

    def test_page_indexes_parse_ranges(self):
        self.assertEqual(_page_indexes("2,4-5", 6), {1, 3, 4})
        self.assertEqual(_page_indexes(None, 3), {0, 1, 2})


if __name__ == "__main__":
    unittest.main()
