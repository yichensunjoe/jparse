#!/usr/bin/env python3
"""Tier 2: Boundary & Corner Cases E2E Tests.

Covers boundary, edge, and corner cases across features B1 through B6 with >= 5 test cases per feature (>= 30 total).
Features:
  B1: 极端 OCR 边界与科学公式保护
  B2: 代码块分类器边界条件（极短代码、伪标签、空白代码块）
  B3: 代码字节保护极端边界（三引号、制表符缩进、连续空行）
  B4: 专业术语边界碰撞（行内反引号、LaTeX 公式、中英无缝混排、复数大小写）
  B5: 表格单元格极端边界（空单元格、纯符号、长文本单元格、无数据行）
  B6: 中文排版极端长度与特殊字符边界（超长段落分词上限、嵌套括号链接、纯符号）
"""

from pathlib import Path
import re
import sys
import unittest

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent.parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.translator import (
    MarkdownDocumentTranslator,
    TranslationConfig,
    chunk_long_text,
    normalize_chinese_text,
)
import src.translator as translator_module

from tests.e2e.e2e_helpers import (
    MSR_GLOSSARY_77,
    get_code_classifier,
    get_ocr_cleaner,
    get_shared_engine,
)


class TestTier2Boundary1OCRCleaning(unittest.TestCase):
    """B1: 极端 OCR 边界与科学公式保护 (>= 5 tests)."""

    def _clean(self, text: str) -> str:
        cleaner = get_ocr_cleaner()
        if cleaner is not None:
            return cleaner(text)
        self.skipTest("clean_historical_ocr_text not yet exported in src.translator")

    def test_b1_01_complex_chemical_formulas(self):
        """Verify complex molten salt chemical formula is NOT altered by number-letter cleaning."""
        raw = "Fuel salt composition: LiF-BeF2-ZrF4-UF4 (65-30-5-0.1 mole %) carrier matrix."
        cleaned = self._clean(raw)
        self.assertIn("LiF-BeF2-ZrF4-UF4", cleaned)
        self.assertIn("65-30-5-0.1 mole %", cleaned)

    def test_b1_02_temperature_and_pressure_formats(self):
        """Verify temperatures and pressures in scientific ranges are preserved."""
        raw = "Operating range: 1150°F to 1300°F at 25 psig to 100 psig."
        cleaned = self._clean(raw)
        self.assertIn("1150°F", cleaned)
        self.assertIn("1300°F", cleaned)
        self.assertIn("25 psig", cleaned)
        self.assertIn("100 psig", cleaned)

    def test_b1_03_single_character_tokens(self):
        """Verify isolated single characters A, I, x, y are not mangled."""
        raw = "Let variable x = 1 and y = 2. Option A is chosen."
        cleaned = self._clean(raw)
        self.assertIn("variable x = 1", cleaned)
        self.assertIn("Option A", cleaned)

    def test_b1_04_mixed_alphanumeric_isotopes(self):
        """Verify nuclear isotopes U-235, U-238, Th-232, Xe-135 are preserved."""
        raw = "Fissile inventory includes U-235 and U-233, fertile Th-232, and poison Xe-135."
        cleaned = self._clean(raw)
        self.assertIn("U-235", cleaned)
        self.assertIn("U-233", cleaned)
        self.assertIn("Th-232", cleaned)
        self.assertIn("Xe-135", cleaned)

    def test_b1_05_empty_and_whitespace_only_ocr_input(self):
        """Verify empty string and whitespace-only input return without exception."""
        self.assertEqual(self._clean(""), "")
        self.assertEqual(self._clean("   \t  \n  "), "   \t  \n  ")


class TestTier2Boundary2CodeClassifier(unittest.TestCase):
    """B2: 代码块分类器边界条件 (>= 5 tests)."""

    def setUp(self):
        self.classifier = get_code_classifier()
        if self.classifier is None:
            self.skipTest("classify_code_block not yet exported in src.translator")

    def test_b2_01_single_character_block(self):
        """Verify 2-character OCR blot like ';\\ne' is handled safely without index errors."""
        res = self.classifier("", ";\ne")
        self.assertIsInstance(res, bool)

    def test_b2_02_whitespace_only_code_block(self):
        """Verify whitespace-only code block returns False (prose / empty bypass)."""
        res = self.classifier("", "   \n\t  \n   ")
        self.assertFalse(res)

    def test_b2_03_shebang_only_script(self):
        """Verify 1-line script #!/usr/bin/env python3 is classified as code (True)."""
        res = self.classifier("bash", "#!/usr/bin/env python3\n")
        self.assertTrue(res)

    def test_b2_04_prose_containing_isolated_programming_word(self):
        """Verify prose containing programming word 'class' or 'import' is NOT classified as code."""
        prose = "The class of materials used in the reactor vessel shall withstand extreme heat and corrosion."
        res = self.classifier("", prose)
        self.assertFalse(res)

    def test_b2_05_code_with_heavy_comments_and_docstrings(self):
        """Verify Python code with extensive comments is still classified as code (True)."""
        code = (
            '"""\n'
            'Safety trip logic calculator.\n'
            'Complies with standard rules.\n'
            '"""\n'
            '# Calculate trip threshold\n'
            'def trip_level(flow: float) -> bool:\n'
            '    return flow < 10.0\n'
        )
        res = self.classifier("python", code)
        self.assertTrue(res)


class TestTier2Boundary3CodeByteProtection(unittest.TestCase):
    """B3: 代码字节保护极端边界 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation")
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def test_b3_01_triple_quoted_multiline_strings(self):
        """Verify triple-quoted strings inside Python code blocks are preserved intact."""
        code = (
            '```python\n'
            'def get_doc():\n'
            '    return """\n'
            '    Line 1\n'
            '    Line 2\n'
            '    """\n'
            '```'
        )
        translated = self.translator.translate_document(f"# Header\n\n{code}\n")
        self.assertIn('"""\n    Line 1\n    Line 2\n    """', translated)

    def test_b3_02_c_pointers_and_bitwise_expressions(self):
        """Verify C pointers, bitwise shifts, and angle brackets remain unescaped."""
        code = (
            "```c\n"
            "#include <stdio.h>\n"
            "int main() {\n"
            "    int *p = &val;\n"
            "    int flag = (*p >> 3) & 0x01;\n"
            "    return flag;\n"
            "}\n"
            "```"
        )
        translated = self.translator.translate_document(f"# C Code\n\n{code}\n")
        self.assertIn("int *p = &val;", translated)
        self.assertIn("(*p >> 3) & 0x01", translated)
        self.assertIn("#include <stdio.h>", translated)

    def test_b3_03_consecutive_blank_lines_in_code(self):
        """Verify code blocks with multiple consecutive blank lines retain exact lines."""
        code = "```python\ndef first():\n    pass\n\n\ndef second():\n    pass\n```"
        translated = self.translator.translate_document(f"# Header\n\n{code}\n")
        self.assertIn("def first():\n    pass\n\n\ndef second():", translated)

    def test_b3_04_mixed_tabs_and_spaces_indentation(self):
        """Verify code block with tab indentation preserves exact tab character."""
        code = "```python\ndef run():\n\tval = 10\n\treturn val\n```"
        translated = self.translator.translate_document(f"# Code\n\n{code}\n")
        self.assertIn("\tval = 10", translated)
        self.assertIn("\treturn val", translated)

    def test_b3_05_code_block_no_trailing_newline(self):
        """Verify code block ending immediately before closing fence without trailing newline."""
        code = "```bash\nexport ENV=production```"
        translated = self.translator.translate_document(f"# Shell\n\n{code}\n")
        self.assertIn("export ENV=production", translated)


class TestTier2Boundary4NuclearTerminology(unittest.TestCase):
    """B4: 专业术语边界碰撞 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(
            model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation",
            glossary=MSR_GLOSSARY_77,
        )
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def test_b4_01_term_inside_inline_backticks(self):
        """Verify inline backtick delimiters `...` are preserved and not stripped."""
        text = "The command `scram` is used to shut down the reactor."
        translated = self.translator.translate_paragraph(text)
        self.assertTrue(re.search(r"`[^`]+`", translated), f"Inline code delimiters must be preserved: {translated}")

    def test_b4_02_term_inside_latex_math(self):
        """Verify term inside inline math $scram = 0$ is NOT replaced with Chinese."""
        text = "When $scram_{trip} = 1$, the rods drop."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("$scram_{trip} = 1$", translated)
        self.assertNotIn("停堆", text)

    def test_b4_03_term_adjacent_to_cjk_boundary(self):
        """Verify term adjacent to Chinese character (no ASCII word boundary) is replaced."""
        text = "此时scram保护动作应立即响应。"
        applied = self.translator._apply_glossary(text)
        self.assertIn("停堆", applied)
        self.assertNotIn("scram", applied)

    def test_b4_04_plural_and_hyphenated_term_variants(self):
        """Verify plural and hyphenated variants like fuel-pump bowls and fuel drain-tanks."""
        text = "Inspection of fuel-pump bowls and fuel drain-tanks shall be performed."
        applied = self.translator._apply_glossary(text)
        self.assertTrue("燃料泵" in applied or "排盐罐" in applied)

    def test_b4_05_case_insensitive_term_variations(self):
        """Verify uppercase SCRAM and lowercase scram both translate to standardized term."""
        text = "SCRAM initiated. Manual scram complete."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("停堆", translated)
        self.assertNotIn("螺旋藻", translated)


class TestTier2Boundary5TableCells(unittest.TestCase):
    """B5: 表格单元格极端边界 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(
            model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation",
            glossary=MSR_GLOSSARY_77,
        )
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def setUp(self):
        has_table_short_circuit = hasattr(translator_module, "TABLE_STOPWORDS_MAP") or getattr(
            self.translator, "_table_short_circuit_enabled", False
        )
        if not has_table_short_circuit:
            self.skipTest("Table stopwords short-circuit & column invariance pending M2 integration")

    def test_b5_01_empty_and_whitespace_cells(self):
        """Verify table with empty cells is preserved without index error."""
        tbl = [
            "| H1 | H2 | H3 |",
            "| --- | --- | --- |",
            "|   | Non-empty |   |",
        ]
        translated = self.translator.translate_table(tbl)
        cols = len(re.split(r"(?<!\\)\|", translated[2])[1:-1])
        self.assertEqual(cols, 3)

    def test_b5_02_single_symbol_cells(self):
        """Verify cells with single symbols '-', '+', '/', 'N/A' are passed through untouched."""
        tbl = [
            "| Col A | Symbol | Col B |",
            "| --- | --- | --- |",
            "| Limit | - | None |",
            "| Status | N/A | Active |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertIn("-", full_text)
        self.assertIn("N/A", full_text)

    def test_b5_03_cell_with_escaped_pipe_and_math(self):
        """Verify cell containing math equation with escaped pipe $\\|x\\| \\le 1$."""
        tbl = [
            "| Var | Equation |",
            "| --- | --- |",
            "| X | $\\|x\\| \\le 1$ |",
        ]
        translated = self.translator.translate_table(tbl)
        cols = len(re.split(r"(?<!\\)\|", translated[2])[1:-1])
        self.assertEqual(cols, 2)
        self.assertIn(r"\|", translated[2])

    def test_b5_04_table_with_only_header_and_separator(self):
        """Verify table with 0 data rows translates without crashing."""
        tbl = [
            "| Col 1 | Col 2 |",
            "| --- | --- |",
        ]
        translated = self.translator.translate_table(tbl)
        self.assertEqual(len(translated), 2)

    def test_b5_05_extreme_cell_length_table(self):
        """Verify cell containing 500 characters handles cleanly."""
        long_text = "The reactor cell pressure safety limit requires strict continuous monitoring at all times. " * 6
        tbl = [
            "| Key | Details |",
            "| --- | --- |",
            f"| Item 1 | {long_text} |",
        ]
        translated = self.translator.translate_table(tbl)
        cols = len(re.split(r"(?<!\\)\|", translated[2])[1:-1])
        self.assertEqual(cols, 2)


class TestTier2Boundary6ChineseTypography(unittest.TestCase):
    """B6: 中文排版极端长度与特殊字符边界 (>= 5 tests)."""

    def test_b6_01_already_normalized_fullwidth_text(self):
        """Verify text already containing fullwidth punctuation is not doubled or altered."""
        text = "这是标准科技公文，包含完整的全角标点；没有任何西文逗号。"
        norm = normalize_chinese_text(text)
        self.assertEqual(norm, text)

    def test_b6_02_text_with_only_punctuation_and_symbols(self):
        """Verify string with only symbols and punctuation handles without error."""
        text = "--- ... !? () [] @ # $ %"
        norm = normalize_chinese_text(text)
        self.assertIsInstance(norm, str)

    def test_b6_03_url_with_nested_parentheses_and_hash(self):
        """Verify markdown link with parentheses and URL fragment is preserved."""
        text = "请参考文档 [规范](https://example.org/wiki/Flow_(mathematics)#Limits)。"
        norm = normalize_chinese_text(text)
        self.assertIn("https://example.org/wiki/Flow_(mathematics)#Limits", norm)
        self.assertNotIn("（mathematics）", norm)

    def test_b6_04_extreme_length_unpunctuated_text(self):
        """Verify 600-word paragraph without punctuation is chunked to avoid NMT 512 token error."""
        words = ["reactor", "safety", "limit", "temperature", "flow", "containment"] * 100
        long_para = " ".join(words)
        chunks = chunk_long_text(long_para, max_words=50)
        self.assertTrue(len(chunks) >= 10)
        for chunk in chunks:
            self.assertTrue(len(chunk.split()) <= 60)

    def test_b6_05_legitimate_chinese_character_repetition(self):
        """Verify NMT repetition stuttering (e.g. 公式公式公式) is suppressed while normal text is intact."""
        stutter_text = "这是重要的设计规程，包含公式公式公式和名称名称名称。"
        norm = normalize_chinese_text(stutter_text)
        self.assertIn("这是重要的设计规程", norm)
        self.assertNotIn("公式公式公式", norm)
        self.assertNotIn("名称名称名称", norm)


if __name__ == "__main__":
    unittest.main()
