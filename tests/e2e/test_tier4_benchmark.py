#!/usr/bin/env python3
"""Tier 4: Real-World Document Benchmark Scenarios & Evaluator Verification.

Uses the real-world benchmark document:
  Source: processed/ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf
  Baseline Markdown: outbox/ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.md
  Translated Markdown: outbox/ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.zh.md
  Translated HTML: outbox/ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.zh.html

Evaluates:
  1. Real-world benchmark file integrity and defect census.
  2. Structure blockage and effective translation coverage.
  3. Nuclear terminology accuracy and fatal error detection.
  4. Table hallucination census and alignment invariance.
  5. 5-dimension objective scoring calibration against historical baseline (38.8 ± 3.0).
  6. Golden scenario scoring verification (composite score >= 90.0 / 100.0).
  7. Offline compliance, self-contained HTML, and XSS sanitization.
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

from tests.e2e.e2e_helpers import (
    OUTBOX_DIR,
    PROCESSED_DIR,
    PROJECT_ROOT,
)
from tests.e2e.evaluate_benchmark import (
    BenchmarkEvaluator,
    FATAL_MISTRANSLATIONS,
    OCR_BENCHMARK_ARTIFACTS,
    TABLE_HALLUCINATIONS,
)


class TestTier4RealWorldBenchmark(unittest.TestCase):
    """Tier 4 real-world document benchmark scenarios."""

    @classmethod
    def setUpClass(cls):
        cls.pdf_path = PROCESSED_DIR / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf"
        cls.raw_md_path = OUTBOX_DIR / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.md"
        cls.zh_md_path = OUTBOX_DIR / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.zh.md"
        cls.zh_html_path = OUTBOX_DIR / "ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.zh.html"

        if cls.zh_md_path.exists():
            cls.zh_md_text = cls.zh_md_path.read_text(encoding="utf-8")
        else:
            cls.zh_md_text = ""

        if cls.zh_html_path.exists():
            cls.zh_html_text = cls.zh_html_path.read_text(encoding="utf-8")
        else:
            cls.zh_html_text = ""

    def test_scenario1_benchmark_source_and_target_artifacts_presence(self):
        """Scenario 1: Verify source PDF and generated benchmark artifacts exist and are non-empty."""
        self.assertTrue(self.pdf_path.exists(), f"Benchmark PDF missing at {self.pdf_path}")
        self.assertGreater(self.pdf_path.stat().st_size, 100000)

        self.assertTrue(self.raw_md_path.exists(), f"Raw markdown missing at {self.raw_md_path}")
        self.assertGreater(self.raw_md_path.stat().st_size, 10000)

        self.assertTrue(self.zh_md_path.exists(), f"Translated zh.md missing at {self.zh_md_path}")
        self.assertGreater(self.zh_md_path.stat().st_size, 10000)

        self.assertTrue(self.zh_html_path.exists(), f"Translated zh.html missing at {self.zh_html_path}")
        self.assertGreater(self.zh_html_path.stat().st_size, 10000)

    def test_scenario2_code_fence_blockage_and_coverage_census(self):
        """Scenario 2: Verify code fence unwrapping and high translation coverage in benchmark document."""
        lines = self.zh_md_text.splitlines()
        # In optimized output, false code fences enclosing typewriter text are unwrapped
        # Total lines are compacted (358 lines vs 647 lines in unreflowed baseline)
        self.assertLess(len(lines), 400, "Optimized document reflows and unwraps typewriter code blocks")

        in_code = False
        code_lines = 0
        table_lines = 0

        for line in lines:
            s = line.strip()
            if s.startswith("```"):
                in_code = not in_code
                code_lines += 1
            elif in_code:
                code_lines += 1
            elif s.startswith("|"):
                table_lines += 1

        # In optimized benchmark: code lines reduced from 386 down to <= 10 (genuine code only)
        self.assertLessEqual(code_lines, 10, f"Expected code lines <= 10 after unwrapping, got {code_lines}")
        # Table lines remain intact
        self.assertEqual(table_lines, 148, f"Expected 148 table lines preserved, got {table_lines}")

    def test_scenario3_nuclear_engineering_terminology_census(self):
        """Scenario 3: Verify zero fatal nuclear engineering mistranslations in optimized benchmark."""
        fatal_found = {}
        for term in FATAL_MISTRANSLATIONS:
            count = len(re.findall(re.escape(term), self.zh_md_text))
            if count > 0:
                fatal_found[term] = count

        # In optimized benchmark, all fatal mistranslations must be completely eliminated
        self.assertEqual(fatal_found, {}, f"Expected 0 fatal mistranslations, but found: {fatal_found}")

        # Also verify evaluator defect sensitivity: detects fatal terms when present in defective text
        defective_sample = "螺旋藻 反应堆电池 精疲力尽 天然气气体"
        evaluator = BenchmarkEvaluator(defective_sample, None)
        rep = evaluator.evaluate_all("defective_sample.zh.md", None)
        self.assertLess(rep.dimensions[3].raw_score, 10.0, "Evaluator must penalize fatal mistranslations")

    def test_scenario4_table_hallucinations_and_alignment_census(self):
        """Scenario 4: Verify zero table alignment hallucinations and preserved table structure."""
        hallucinations_found = {}
        for h in TABLE_HALLUCINATIONS:
            count = len(re.findall(re.escape(h), self.zh_md_text))
            if count > 0:
                hallucinations_found[h] = count

        # In optimized benchmark, table hallucinations like 联年月日 and 'be be' must be eliminated
        self.assertEqual(hallucinations_found, {}, f"Expected 0 table hallucinations, but found: {hallucinations_found}")

        # Also verify evaluator defect sensitivity: detects table hallucinations when present
        bad_table = "| 列1 | 列2 |\n| --- | --- |\n| 联年月日 | be be |\n"
        evaluator = BenchmarkEvaluator(bad_table, None)
        rep = evaluator.evaluate_all("bad_table.zh.md", None)
        self.assertLess(rep.dimensions[4].raw_score, 100.0, "Evaluator must penalize table hallucinations")
        self.assertEqual(rep.dimensions[4].details["n_hallucinations"], 2)

    def test_scenario5_evaluator_baseline_calibration(self):
        """Scenario 5: Run 5-dimension evaluator against baseline mock and verify live benchmark score >= 90.0."""
        # 1. Baseline calibration check on synthetic unoptimized baseline snippet
        baseline_mock = (
            "```text\n"
            "This is historical typewriter prose blocked in code fence.\n"
            "```\n"
            "螺旋藻 反应堆电池 精疲力尽\n"
            "| A | B |\n| --- | --- |\n| 联年月日 | be be |\n"
        )
        baseline_evaluator = BenchmarkEvaluator(baseline_mock, None)
        baseline_rep = baseline_evaluator.evaluate_all("baseline_mock.zh.md", None, threshold=90.0)
        self.assertFalse(baseline_rep.passed, "Baseline defect pattern must fail the >= 90.0 gate")
        self.assertLess(baseline_rep.composite_score, 80.0)

        # 2. Live benchmark document check: must pass >= 90.0 gate
        evaluator = BenchmarkEvaluator(self.zh_md_text, self.zh_html_text)
        report = evaluator.evaluate_all(str(self.zh_md_path), str(self.zh_html_path), threshold=90.0)
        self.assertTrue(report.passed, f"Optimized benchmark must pass >= 90.0 gate, got {report.composite_score}")
        self.assertGreaterEqual(report.composite_score, 90.0)
        self.assertEqual(report.threshold, 90.0)

    def test_scenario6_evaluator_target_passing_golden(self):
        """Scenario 6: Verify evaluator awards >= 90.0 on an optimized golden translation document."""
        # Golden document with:
        # - Offline compliance = 100.0
        # - OCR errors cleaned
        # - Unwrapped code blocks into natural translated paragraphs (coverage >= 98%)
        # - Nuclear engineering terms accurately translated (>= 27/30 benchmark terms, 0 fatal errors)
        # - Table alignment intact, 0 hallucinations
        golden_doc = (
            "# MSRE 运行安全限值规程\n\n"
            "## 1. 适用范围\n\n"
            "本规程适用于橡树岭国家实验室 (ORNL) 熔盐堆实验装置 (MSRE) 的全部核运行工况。\n"
            "当燃料盐与冷却盐装入反应堆容器后，清洗盐与载体盐完成清洗循环。\n"
            "所有停堆电路必须经过严格的停堆试验，确保停堆跳闸及周期停堆保护动作正常。\n\n"
            "## 2. 核心安全系统要求\n\n"
            "1. 燃料排盐罐系统处于持续待命状态，排盐罐舱保持充氮惰化，在次临界及临界状态下燃料盐事故工况必须及时排空。\n"
            "2. 反应堆舱及舱室屏蔽块密封完好，覆盖气体压力正常，监测反应性及反应性异常指标。\n"
            "3. 燃料泵泵池配备防过充保护，燃料尾气经过活性炭吸附床后由通风烟囱排向高空。\n"
            "4. 石墨慢化剂构件结构完整，控制棒与安全棒落棒顺畅，热屏蔽与哈氏合金 N 对碲脆化具备高度耐受力。\n"
            "5. 作为增殖堆关键原型验证堆，一回路安全壳及蒸汽冷凝系统运行正常，FLiBe 盐循环稳定。\n\n"
            "| 部件名称 | 所在舱室 | 设定阈值 | 运行状态 |\n"
            "| --- | --- | --- | --- |\n"
            "| 燃料排盐罐 | 排盐罐舱 | 45 psig | 待命 |\n"
            "| 反应堆容器 | 反应堆舱 | 1300°F | 正常 |\n"
            "| 控制棒驱动机构 | 堆顶 | 1.0 s | 正常 |\n\n"
            "```python\n"
            "def verify_scram_system():\n"
            "    # Code block preserved byte-for-byte\n"
            "    return True\n"
            "```\n\n"
            "## 3. 规程结论\n\n"
            "各项运行安全指标完全符合科技公文规范标准。\n"
        )
        evaluator = BenchmarkEvaluator(golden_doc, None)
        report = evaluator.evaluate_all("golden_sample.zh.md", None, threshold=90.0)

        self.assertTrue(report.passed, f"Golden document must pass >= 90.0 gate, got {report.composite_score}")
        self.assertGreaterEqual(report.composite_score, 90.0)

    def test_scenario7_evaluator_dimension_weights_and_bounds(self):
        """Scenario 7: Mathematical validation of dimension weights summing to 1.0."""
        evaluator = BenchmarkEvaluator("Sample text", None)
        report = evaluator.evaluate_all("test.zh.md", None)
        weights_sum = sum(d.weight for d in report.dimensions)
        self.assertAlmostEqual(weights_sum, 1.0, places=4, msg="Dimension weights must sum to exactly 1.0")

        for d in report.dimensions:
            self.assertGreaterEqual(d.raw_score, 0.0)
            self.assertLessEqual(d.raw_score, 100.0)
            self.assertAlmostEqual(d.weighted_score, round(d.raw_score * d.weight, 2), places=2)

    def test_scenario8_benchmark_html_single_file_self_contained_and_security(self):
        """Scenario 8: Verify benchmark HTML is strictly self-contained and free of script injection."""
        self.assertTrue(self.zh_html_path.exists())
        # Check no external remote stylesheets or external scripts
        self.assertNotIn("http://", self.zh_html_text[:500])
        self.assertNotIn("https://", self.zh_html_text[:500])
        # Check no script injection
        self.assertEqual(len(re.findall(r"<script[\s>]", self.zh_html_text, re.I)), 0)
        # Check data URI or self-contained style
        self.assertIn("<style>", self.zh_html_text)


if __name__ == "__main__":
    unittest.main()
