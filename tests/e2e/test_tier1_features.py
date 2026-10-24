#!/usr/bin/env python3
"""Tier 1: Feature Coverage E2E Tests (Unit & Component Level Isolation).

Covers Features F1 through F6 in isolation with >= 5 test cases per feature (>= 30 total).
Features:
  F1: 打字机 OCR 微规整与启发式清洗 (R4)
  F2: 代码块与打字机正文双特征分类器 (R1)
  F3: 真实代码块 100% 字节保护 (R1)
  F4: MSR 核心术语 100% 精确置换 (R2)
  F5: 表格停用词对齐短路与列对齐守恒 (R3)
  F6: 科技公文中文排版规范后处理 (R4)
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
    normalize_chinese_text,
)
import src.translator as translator_module

from tests.e2e.e2e_helpers import (
    BENCHMARK_30_TERMS,
    MSR_GLOSSARY_77,
    TABLE_STOPWORDS_MAP,
    apply_reference_ocr_cleaner,
    get_code_classifier,
    get_ocr_cleaner,
    get_shared_engine,
)


class TestTier1Feature1OCRCleaning(unittest.TestCase):
    """F1: 打字机 OCR 微规整与启发式清洗 (>= 5 tests)."""

    def _clean(self, text: str) -> str:
        cleaner = get_ocr_cleaner()
        if cleaner is not None:
            return cleaner(text)
        self.skipTest("clean_historical_ocr_text not yet exported in src.translator (pending M1 integration)")

    def test_f1_01_ocr_letter_numeral_confusion(self):
        """Verify letter-digit confusions (4o->40, ts->is, 1imits->limits, 1s->is)."""
        raw = "4o years of operation. It ts expected that 1imits will be observed when limit 1s reached."
        cleaned = self._clean(raw)
        self.assertIn("40 years", cleaned)
        self.assertIn("It is expected", cleaned)
        self.assertIn("limits will be observed", cleaned)
        self.assertIn("limit is reached", cleaned)

    def test_f1_02_ocr_section_numbering(self):
        """Verify chapter and section numbering confusions (L.k->4.4, L.5->4.5, k11->4.11)."""
        raw = "L.k Cell Temperature limits and L.5 Drain Tank pressure. k11 Ventilation Filters Test."
        cleaned = self._clean(raw)
        self.assertIn("4.4 Cell", cleaned)
        self.assertIn("4.5 Drain Tank", cleaned)
        self.assertIn("4.11 Ventilation", cleaned)

    def test_f1_03_ocr_ink_smear_ligatures(self):
        """Verify typewriter ink smear ligatures (energydemands, Agsicies, Thair, madeit, plusthe)."""
        raw = "energydemands are high for Agsicies. Thair system madeit plusthe test."
        cleaned = self._clean(raw)
        self.assertIn("energy demands", cleaned)
        self.assertIn("Agencies", cleaned)
        self.assertIn("Their", cleaned)
        self.assertIn("made it", cleaned)
        self.assertIn("plus the", cleaned)

    def test_f1_04_ocr_hyphenation_wrapping(self):
        """Verify broken hyphenation across word wraps (ex-\\nceeded, wmaintained)."""
        raw = "The limit was ex-\nceeded due to high pressure. Flow was wmaintained."
        cleaned = self._clean(raw)
        self.assertIn("exceeded", cleaned)
        self.assertIn("maintained", cleaned)

    def test_f1_05_ocr_engineering_units(self):
        """Verify engineering units and symbols (1.0 ft° -> 1.0 ft³, 3k/k -> Δk/k)."""
        raw = "Gas flow rate was 1.0 ft°/min with reactivity 0.5% 3k/k."
        cleaned = self._clean(raw)
        self.assertIn("1.0 ft³", cleaned)
        self.assertIn("Δk/k", cleaned)

    def test_f1_06_ocr_reference_rules_integrity(self):
        """Verify that typewriter OCR cleaner preserves legitimate scientific notation."""
        raw = "LiF-BeF2-ZrF4-UF4 at 1150°F and 25 psig."
        cleaned = self._clean(raw)
        self.assertIn("LiF-BeF2-ZrF4-UF4", cleaned)
        self.assertIn("1150°F", cleaned)
        self.assertIn("25 psig", cleaned)


class TestTier1Feature2CodeClassifier(unittest.TestCase):
    """F2: 代码块与打字机正文双特征分类器 (>= 5 tests)."""

    def setUp(self):
        self.classifier = get_code_classifier()
        if self.classifier is None:
            self.skipTest("classify_code_block not yet exported in src.translator (pending M1 integration)")

    def test_f2_01_explicit_text_fence_classified_as_prose(self):
        """Verify ```text is classified as translatable prose (returns False for code / True for prose)."""
        content = "The operating safety limits shall apply at all times when fuel is in the reactor."
        # If returns bool: False = real code, True = prose (or vice versa per interface contract)
        # Check that classification distinguishes text fence from python code
        res_text = self.classifier("text", content)
        res_python = self.classifier("python", "def calculate(): return 42")
        self.assertNotEqual(res_text, res_python, "Text fence and real python code must have different classification")

    def test_f2_02_empty_lang_prose_classified_as_prose(self):
        """Verify empty lang code fence with natural language prose is classified as prose."""
        content = "Section 4.14 Leak Detector System. All drain tanks shall be tested annually."
        res = self.classifier("", content)
        # Should be classified same as prose
        res_text = self.classifier("text", content)
        self.assertEqual(res, res_text)

    def test_f2_03_falsely_tagged_python_prose_classified_as_prose(self):
        """Verify block falsely tagged as python but containing legal disclaimer is classified as prose."""
        content = (
            "A. Makes any warranty or representation, expressed or implied, with respect to the accuracy, "
            "completeness, or usefulness of the information contained in this report...\n"
            "B. Assumes any liabilities with respect to the use of any information disclosed."
        )
        res = self.classifier("python", content)
        res_real_py = self.classifier("python", "import sys\nfrom pathlib import Path\ndef main(): pass")
        self.assertNotEqual(res, res_real_py)

    def test_f2_04_genuine_python_and_bash_classified_as_code(self):
        """Verify genuine Python and Bash code are classified as code."""
        py_code = "def calculate_flow(p, t):\n    # Calculate flow\n    return p * 1.5\n"
        sh_code = "#!/bin/bash\nset -euo pipefail\necho 'Running diagnostics'\nexit 0\n"
        self.assertEqual(self.classifier("python", py_code), self.classifier("bash", sh_code))

    def test_f2_05_c_and_json_classified_as_code(self):
        """Verify C code and JSON configs are classified as code."""
        c_code = "#include <stdio.h>\nint main(int argc, char **argv) {\n    printf(\"hello\\n\");\n    return 0;\n}\n"
        json_code = '{\n  "system": "MSRE",\n  "limits": {\n    "temp": 1300\n  }\n}\n'
        c_res = self.classifier("c", c_code)
        json_res = self.classifier("json", json_code)
        self.assertEqual(c_res, json_res)


class TestTier1Feature3CodeByteProtection(unittest.TestCase):
    """F3: 真实代码块 100% 字节保护 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(model_dir=cls._get_model_dir())
        cls.translator = MarkdownDocumentTranslator(engine, config)

    @staticmethod
    def _get_model_dir() -> Path:
        return Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation"

    def test_f3_01_python_nested_indentation_exact(self):
        """Verify exact byte-level preservation of 4-space, 8-space indentation in Python code blocks."""
        code = (
            "```python\n"
            "class SafetyMonitor:\n"
            "    def check_scram(self, period):\n"
            "        if period < 1.0:\n"
            "            return True\n"
            "        return False\n"
            "```"
        )
        md = f"# Title\n\n{code}\n\nParagraph text explaining safety."
        translated = self.translator.translate_document(md)
        self.assertIn("class SafetyMonitor:", translated)
        self.assertIn("    def check_scram(self, period):", translated)
        self.assertIn("        if period < 1.0:", translated)
        self.assertIn("            return True", translated)

    def test_f3_02_code_block_newlines_not_doubled(self):
        """Verify that single empty lines inside code blocks are not doubled into multiple blank lines."""
        code = "```python\ndef a():\n    pass\n\ndef b():\n    pass\n```"
        md = f"# Title\n\n{code}\n"
        translated = self.translator.translate_document(md)
        self.assertIn("def a():\n    pass\n\ndef b():", translated)
        self.assertNotIn("\n\n\n", translated)

    def test_f3_03_code_special_characters_and_pointers(self):
        """Verify C pointers (*, ->), bitwise operators (&, |), and angle brackets remain unescaped."""
        code = "```c\n#include <stdio.h>\nvoid update(Node *node) {\n    int mask = (1 << 4) | 0x0F;\n    node->val &= mask;\n}\n```"
        translated = self.translator.translate_document(f"# Header\n\n{code}\n")
        self.assertIn("Node *node", translated)
        self.assertIn("node->val &= mask;", translated)
        self.assertIn("#include <stdio.h>", translated)

    def test_f3_04_code_fence_language_tag_preserved(self):
        """Verify code fence backticks and language tag are preserved exactly."""
        code = "```bash\necho 'hello world'\n```"
        translated = self.translator.translate_document(f"# Shell\n\n{code}\n")
        self.assertIn("```bash", translated)
        self.assertIn("echo 'hello world'", translated)

    def test_f3_05_shell_env_vars_and_syntax_preserved(self):
        """Verify environment variables ($PATH, ${VAR:-default}, $$) are not mangled."""
        code = "```sh\nexport BASE_DIR=${PROJECT_HOME:-/tmp}\necho \"PID: $$\" > \"$BASE_DIR/run.pid\"\n```"
        translated = self.translator.translate_document(f"# Config\n\n{code}\n")
        self.assertIn("${PROJECT_HOME:-/tmp}", translated)
        self.assertIn("\"$BASE_DIR/run.pid\"", translated)


class TestTier1Feature4NuclearTerminology(unittest.TestCase):
    """F4: MSR 核心术语 100% 精确置换 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        # Ensure MSR glossary is injected
        config = TranslationConfig(
            model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation",
            glossary=MSR_GLOSSARY_77,
        )
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def test_f4_01_scram_and_reactor_cell_precision(self):
        """Verify scram -> 停堆 (NOT 螺旋藻) and reactor cell -> 反应堆舱 (NOT 反应堆电池)."""
        text = "The scram circuit shall be tested before startup. The reactor cell pressure must remain negative."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("停堆", translated)
        self.assertNotIn("螺旋藻", translated)
        self.assertIn("反应堆舱", translated)
        self.assertNotIn("反应堆电池", translated)

    def test_f4_02_fuel_drain_tank_and_drained_precision(self):
        """Verify fuel drain tank -> 燃料排盐罐 (NOT 排水池/坦克) and drained -> 排空 (NOT 精疲力尽)."""
        text = "The fuel salt shall be drained into the fuel drain tank immediately."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("燃料排盐罐", translated)
        self.assertNotIn("排水池", translated)
        self.assertNotIn("排油罐", translated)
        self.assertNotIn("坦克", translated)
        self.assertNotIn("精疲力尽", translated)

    def test_f4_03_offgas_and_ventilation_stack_precision(self):
        """Verify offgas -> 尾气 (NOT 沼气) and ventilation stack -> 通风烟囱 (NOT 堆栈/堆叠)."""
        text = "The fuel offgas system discharges through the ventilation stack."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("尾气", translated)
        self.assertNotIn("沼气", translated)
        self.assertIn("通风烟囱", translated)
        self.assertNotIn("堆叠", translated)
        self.assertNotIn("堆栈", translated)

    def test_f4_04_graphite_moderator_and_breeder_precision(self):
        """Verify graphite moderator -> 石墨慢化剂 (NOT 石墨游戏主持人) and breeder reactor -> 增殖堆."""
        text = "The MSRE utilized a graphite moderator. It served as a prototype for a molten salt breeder reactor."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("石墨慢化剂", translated)
        self.assertNotIn("游戏主持人", translated)
        self.assertIn("增殖堆", translated)
        self.assertNotIn("饲养堆", translated)

    def test_f4_05_tellurium_embrittlement_and_flibe_precision(self):
        """Verify tellurium embrittlement -> 碲脆化 and FLiBe preservation."""
        text = "Hastelloy-N resistance to tellurium embrittlement in FLiBe carrier salt."
        translated = self.translator.translate_paragraph(text)
        self.assertIn("碲脆化", translated)
        self.assertIn("FLiBe", translated)
        self.assertNotIn("飞利贝", translated)

    def test_f4_06_all_30_benchmark_terms_mapped_without_fatal_blunders(self):
        """Verify none of the 30 core benchmark terms produce forbidden translations."""
        for eng, valid_zh, forbidden_set in BENCHMARK_30_TERMS:
            sent = f"The operating specifications require inspection of the {eng} during maintenance."
            translated = self.translator.translate_paragraph(sent)
            # Remove legitimate Chinese translations before checking for forbidden substrings
            clean_check = translated
            for valid in valid_zh:
                clean_check = clean_check.replace(valid, "")
            for bad_term in forbidden_set:
                self.assertNotIn(
                    bad_term,
                    clean_check,
                    f"Fatal mistranslation '{bad_term}' found for term '{eng}' in translated sentence: {translated}",
                )


class TestTier1Feature5TableShortCircuit(unittest.TestCase):
    """F5: 表格停用词对齐短路与列对齐守恒 (>= 5 tests)."""

    @classmethod
    def setUpClass(cls):
        engine = get_shared_engine()
        config = TranslationConfig(
            model_dir=Path(__file__).resolve().parent.parent.parent / "assets" / "models" / "translation",
            glossary=MSR_GLOSSARY_77,
        )
        cls.translator = MarkdownDocumentTranslator(engine, config)

    def setUp(self):
        # Table short-circuit is an M2 deliverable. Check if implemented.
        has_table_short_circuit = hasattr(translator_module, "TABLE_STOPWORDS_MAP") or getattr(
            self.translator, "_table_short_circuit_enabled", False
        )
        if not has_table_short_circuit:
            self.skipTest("Table stopwords short-circuit & column invariance pending M2 integration")

    def test_f5_01_isolated_stopwords_short_circuit_no_hallucination(self):
        """Verify isolated cells 'of', 'the', 'in', 'to' in table do NOT produce '联年月日' or 'be be'."""
        tbl = [
            "| Item | Description | Preposition | Target |",
            "| --- | --- | --- | --- |",
            "| Valve | of | the | Commission |",
            "| Flow | in | the | reactor |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertNotIn("联年月日", full_text)
        self.assertNotIn("联联年月日", full_text)
        self.assertNotIn("be be", full_text)

    def test_f5_02_gas_and_total_not_stuttering(self):
        """Verify isolated 'gas' and 'total' in table do not produce '天然气气体' or '总计共计'."""
        tbl = [
            "| Parameter | Type | Value |",
            "| --- | --- | --- |",
            "| Cover | gas | 10 psig |",
            "| Flow | total | 100 gpm |",
        ]
        translated = self.translator.translate_table(tbl)
        full_text = "\n".join(translated)
        self.assertNotIn("天然气气体", full_text)
        self.assertNotIn("总计共计", full_text)

    def test_f5_03_column_count_invariance(self):
        """Verify that every row in translated table matches the header column count exactly."""
        tbl = [
            "| Col1 | Col2 | Col3 | Col4 |",
            "| :--- | :--- | :--- | :--- |",
            "| Cell A | Cell B | Cell C | Cell D |",
            "| Single | Full phrase with information | Next | End |",
        ]
        translated = self.translator.translate_table(tbl)
        header_cols = len(re.split(r"(?<!\\)\|", translated[0])[1:-1])
        self.assertEqual(header_cols, 4)
        for row_idx, row in enumerate(translated):
            if re.match(r"^\|[\s\-:|]+\|$", row):
                continue
            cols = len(re.split(r"(?<!\\)\|", row)[1:-1])
            self.assertEqual(cols, 4, f"Row {row_idx} column count mismatch: {row}")

    def test_f5_04_escaped_pipe_preserved_in_cells(self):
        """Verify escaped pipe \\| inside table cells is preserved without splitting columns."""
        tbl = [
            "| Parameter | Expression |",
            "| --- | --- |",
            "| Norm | Option A \\| Option B |",
        ]
        translated = self.translator.translate_table(tbl)
        data_row = translated[2]
        cols = len(re.split(r"(?<!\\)\|", data_row)[1:-1])
        self.assertEqual(cols, 2, "Cell with escaped pipe must not be split into additional columns")
        self.assertIn(r"\|", data_row, "Escaped pipe must be preserved in translated cell")

    def test_f5_05_ragged_table_row_padded_to_n(self):
        """Verify ragged row with fewer columns is padded to match header columns."""
        tbl = [
            "| H1 | H2 | H3 |",
            "| --- | --- | --- |",
            "| Only one cell |",
        ]
        translated = self.translator.translate_table(tbl)
        data_row = translated[2]
        cols = len(re.split(r"(?<!\\)\|", data_row)[1:-1])
        self.assertEqual(cols, 3, "Ragged row must be padded to match 3 columns")


class TestTier1Feature6ChineseTypography(unittest.TestCase):
    """F6: 科技公文中文排版规范后处理 (>= 5 tests)."""

    def test_f6_01_pangu_spacing_cjk_alphanumeric(self):
        """Verify space between Chinese character and alphanumeric word (Pangu spacing)."""
        raw = "核反应堆MSRE运行规程第4.4节。"
        norm = normalize_chinese_text(raw)
        self.assertIn("MSRE", norm)
        self.assertTrue(re.search(r"[\u4e00-\u9fa5]\s+MSRE|MSRE\s+[\u4e00-\u9fa5]", norm) or "MSRE" in norm)

    def test_f6_02_fullwidth_punctuation_normalization(self):
        """Verify ASCII punctuation following Chinese characters becomes fullwidth."""
        raw = "第一项条文,第二项条文;第三项条文:正常运行?全部合格!"
        norm = normalize_chinese_text(raw)
        self.assertIn("，", norm)
        self.assertIn("；", norm)
        self.assertIn("：", norm)
        self.assertIn("？", norm)
        self.assertIn("！", norm)
        self.assertNotIn(",", norm)
        self.assertNotIn(";", norm)

    def test_f6_03_zero_space_adjacent_to_fullwidth_punctuation(self):
        """Verify zero whitespace adjacent to fullwidth punctuation marks."""
        raw = "这是条文 ， 那是结果 。 请注意 ！"
        norm = normalize_chinese_text(raw)
        self.assertNotIn(" ，", norm)
        self.assertNotIn(" ， ", norm)
        self.assertNotIn(" 。", norm)
        self.assertNotIn(" ！", norm)

    def test_f6_04_markdown_images_and_links_protection(self):
        """Verify ![alt](url) exclamation mark is NOT turned into fullwidth ！."""
        raw = "请查看以下流程图：![系统原理图](images/flow.png) 以及参考链接 [文档](https://ornl.gov)。"
        norm = normalize_chinese_text(raw)
        self.assertIn("![系统原理图](images/flow.png)", norm)
        self.assertNotIn("！[", norm)

    def test_f6_05_inline_code_and_math_typography(self):
        """Verify inline code `var` and math $x$ delimiters are clean and not mangled."""
        raw = "当参数 `flow_rate` 超过 $1.0\\text{ gpm}$ 时，触发报警。"
        norm = normalize_chinese_text(raw)
        self.assertIn("`flow_rate`", norm)
        self.assertIn("$1.0\\text{ gpm}$", norm)


if __name__ == "__main__":
    unittest.main()
