#!/usr/bin/env python3
"""Empirical Adversarial Stress Test Suite for Milestone 1 Iteration 2.

Exhaustively challenges:
1. classify_code_block on heavy nuclear safety domain comments (Python, Bash, C, SQL, YAML, JSON).
2. classify_code_block on complex typewriter scanned prose (bullet lists, footnotes, capitalized headings, numbers).
3. clean_historical_ocr_text on currency pairs vs genuine inline and display math.
4. normalize_chinese_text on grammatical collocations, reduplication, and period typography.
"""

import unittest

from src.translator import (
    classify_code_block,
    clean_historical_ocr_text,
    normalize_chinese_text,
)


class TestAdversarialCodeClassification(unittest.TestCase):
    """Stress test classify_code_block with heavy nuclear domain prose in comments & docstrings."""

    def test_python_with_nuclear_safety_comments_and_docstrings(self):
        snippets = [
            # 1. Extensive docstring with nuclear regulatory text
            (
                "python",
                '''def verify_containment_pressure(p_psig: float) -> bool:
    """The reactor containment pressure shall be maintained within safety limits.
    
    In accordance with ORNL-TM-0733 safety specifications, whenever the
    reactor cell temperature exceeds 1200 F, pressure must not exceed 15 psig.
    Operation beyond this limit warrants immediate emergency scram.
    """
    return p_psig <= 15.0''',
            ),
            # 2. Multi-line comment block before function
            (
                "python",
                '''# SECTION 4. OPERATING LIMITS AND SAFETY REQUIREMENTS
# The maximum fuel temperature shall not exceed 1300 F.
# Under no circumstances shall the operator disable scram channels.
# All safety provisions must be strictly followed in accordance with procedures.
import sys

def scram():
    sys.exit(1)''',
            ),
            # 3. Class with inline comments on every line
            (
                "python",
                '''class ReactorSafetyController:
    # Operating safety limit for fuel drain tank
    TEMP_LIMIT = 1300  # Maximum reactor temperature in degrees F
    PRESSURE_LIMIT = 15  # Containment cell pressure limit in psig
    
    def is_safe(self, temp, pressure):
        # Verify both parameters are within safety requirements
        return temp <= self.TEMP_LIMIT and pressure <= self.PRESSURE_LIMIT''',
            ),
            # 4. Short lambda / one-liner with heavy comment
            (
                "python",
                '''# The reactor emergency scram limit shall be enforced by system monitoring
check_limit = lambda t: t < 1200''',
            ),
            # 5. Untagged Python with domain comments
            (
                "",
                '''def monitor_fuel_salt():
    """Safety check for MSRE reactor cell."""
    return True''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"Python snippet {idx} misclassified as prose (got {res})")

    def test_bash_with_nuclear_safety_comments(self):
        snippets = [
            # 1. Shebang with regulatory text
            (
                "bash",
                '''#!/bin/bash
# MSRE Reactor Emergency Shutdown Script
# In accordance with ORNL safety requirements, initiate scram if temperature exceeds limit
if [ "$REACTOR_TEMP" -gt 1300 ]; then
    echo "EMERGENCY SCRAM: Temperature limit exceeded"
    /opt/msre/bin/scram --force
fi''',
            ),
            # 2. Shell commands with heavy comments and no shebang
            (
                "sh",
                '''# The containment ventilation stack radiation monitor shall be checked.
# If activity exceeds 0.62 yc/sec, isolation valve must close immediately.
export SAFETY_STATUS="ACTIVE"
chmod 600 /etc/msre/containment.conf
pip install msre-safety-daemon''',
            ),
            # 3. Untagged shell script with shebang and domain prose
            (
                "",
                '''#!/usr/bin/env bash
# Reactor cell safety monitoring daemon
# Shall operate continuously in accordance with technical specifications
echo "Monitoring MSRE..."''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"Bash snippet {idx} misclassified as prose (got {res})")

    def test_c_with_nuclear_safety_comments(self):
        snippets = [
            # 1. C code with block comment containing full nuclear paragraph
            (
                "c",
                '''/*
 * ORNL-TM-0733 Section 4.1: Reactor Core and Fuel Salt System
 * The reactor shall not be operated unless all safety limits are verified.
 * Pressure in the reactor cell shall be maintained below 15 psig.
 * Scram channels must remain energized in accordance with provisions.
 */
#include <stdio.h>
#include <stdbool.h>

bool check_safety_limit(double temp) {
    if (temp > 1300.0) {
        return false;
    }
    return true;
}''',
            ),
            # 2. C snippet with struct and inline comments
            (
                "c",
                '''// Reactor cell containment parameters
// Safety limit requires pressure and temperature limits
int main(void) {
    printf("Reactor status OK\\n");
    return 0;
}''',
            ),
            # 3. C snippet with semicolon lines and void func
            (
                "cpp",
                '''// The emergency drain tank cooling system operation
void initiate_scram() {
    trigger_solenoid_valve();
    log_event("SCRAM INITIATED");
}''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"C snippet {idx} misclassified as prose (got {res})")

    def test_sql_with_nuclear_safety_comments(self):
        snippets = [
            # 1. SQL with uppercase keywords and domain comments
            (
                "sql",
                '''-- In accordance with ORNL safety requirements, query the scram log
-- The reactor temperature limit shall be verified against calibration data
SELECT event_id, reactor_cell, max_temp, scram_status
FROM msre_safety_log
WHERE max_temp > 1200.0 AND scram_status = 'PENDING';''',
            ),
            # 2. Lowercase SQL with domain comments
            (
                "sql",
                '''-- Safety limit database update
-- Reactor containment cell parameters shall be logged every hour
select timestamp, core_temp from reactor_monitoring where limit_exceeded = 1;''',
            ),
            # 3. INSERT / CREATE TABLE
            (
                "sql",
                '''CREATE TABLE reactor_limits (
    limit_id INT PRIMARY KEY,
    system_name VARCHAR(100),
    max_safety_value DOUBLE,
    accordance_doc VARCHAR(50)
);''',
            ),
            # 4. Untagged SQL
            (
                "",
                '''SELECT safety_limit, reactor_status FROM system_table WHERE limit > 10;''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"SQL snippet {idx} misclassified as prose (got {res})")

    def test_yaml_with_nuclear_safety_comments(self):
        snippets = [
            # 1. YAML with extensive header comments
            (
                "yaml",
                '''# ORNL MSRE Operational Safety Specifications
# In accordance with Section 4, the reactor containment cell pressure
# shall not exceed 15 psig and fuel temperature shall not exceed 1300 F.
# The emergency drain tank heater system must be operational.
reactor_system: MSRE
safety_limits:
  max_fuel_temp_f: 1300
  max_cell_pressure_psig: 15
  scram_delay_ms: 100
  containment_monitored: true''',
            ),
            # 2. YAML list of parameters
            (
                "yml",
                '''# Safety requirements list
core_monitoring:
  sample_interval_sec: 1
  alert_threshold_temp: 1250
  shutdown_threshold_temp: 1300''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"YAML snippet {idx} misclassified as prose (got {res})")

    def test_json_with_nuclear_safety_comments_and_text(self):
        snippets = [
            # 1. JSON containing domain prose inside values
            (
                "json",
                '''{
  "system": "MSRE",
  "document": "ORNL-TM-0733",
  "safety_clause": "The reactor safety limit shall be maintained in accordance with regulations.",
  "parameters": {
    "temperature_limit": 1300,
    "pressure_limit": 15
  }
}''',
            ),
            # 2. Untagged JSON with regulatory prose values
            (
                "",
                '''{
  "scram_condition": "Reactor core temperature shall not exceed 1300 F under any operating condition",
  "status": "ARMED"
}''',
            ),
        ]
        for idx, (lang, code) in enumerate(snippets):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, code)
                self.assertTrue(res, f"JSON snippet {idx} misclassified as prose (got {res})")


class TestAdversarialTypewriterProseClassification(unittest.TestCase):
    """Stress test classify_code_block on complex typewriter scanned prose blocks."""

    def test_typewriter_scanned_prose_with_headings_and_lists(self):
        prose_blocks = [
            # 1. Tagged 'text': Section heading, capitalized titles, bullet lists, numbers
            (
                "text",
                '''SECTION 4. OPERATING LIMITS AND SAFETY REQUIREMENTS

4.1 REACTOR CORE AND FUEL SALT SYSTEM

In accordance with safety requirements, the following conditions shall be maintained:
(a) The fuel salt concentration shall not exceed 0.62 yc/sec under any circumstance.
(b) The reactor cell pressure shall be maintained below 15 psig during normal operation.
(c) The emergency drain tank temperature shall remain above 1200 F to prevent freezing.
(d) All safety instrumentation channels shall be operational and calibrated.''',
            ),
            # 2. Empty tag: Regulatory paragraph with footnote and numbers
            (
                "",
                '''The maximum steady-state power level of the MSRE shall be 10 MW. During
operation with U-233 fuel, the maximum temperature shall not exceed 1300 F at
any point in the core. This limit ensures that the graphite moderator and
Hastelloy-N containment vessel maintain structural integrity throughout operation.

* Research sponsored by the U.S. Atomic Energy Commission under contract with Union Carbide Corporation.
[1] See ORNL-4396 for additional experimental data regarding fuel salt stability.''',
            ),
            # 3. Tagged 'plaintext': Typewriter report with numbered items and legal disclaimer
            (
                "plaintext",
                '''1. The primary coolant flow rate shall be maintained in accordance with specifications.
2. In the event of an abnormal temperature increase, the reactor shall be shut down.
3. Neither the United States Government nor the Commission makes any warranty, expressed or implied.
4. The operator shall assume liabilities with respect to the use of information disclosed in this report.''',
            ),
            # 4. Empty tag: Historical document header block
            (
                "",
                '''OAK RIDGE NATIONAL LABORATORY
Operated by
UNION CARBIDE CORPORATION
NUCLEAR DIVISION
Post Office Box Y
Oak Ridge, Tennessee 37830

DATE: October 24, 1969
SUBJECT: MSRE Technical Specifications and Safety Limits
TO: Distribution
FROM: Reactor Operations Staff''',
            ),
            # 5. Tagged 'raw': Typewriter bulleted instructions
            (
                "raw",
                '''OPERATING PROCEDURE:
- Verify that cooling water is flowing to the reactor cell shield.
- Check that the offgas system pressure is within specified limits.
- Confirm that the fuel drain tank vent valves are closed.
- Ensure that the operator on duty has reviewed all safety limits.''',
            ),
        ]
        for idx, (lang, text) in enumerate(prose_blocks):
            with self.subTest(idx=idx, lang=lang):
                res = classify_code_block(lang, text)
                self.assertFalse(res, f"Typewriter prose block {idx} misclassified as code (got {res})")


class TestAdversarialHistoricalOcrMathCurrency(unittest.TestCase):
    """Stress test clean_historical_ocr_text on currency pairs vs genuine math formulas."""

    def test_currency_pairs_and_variations(self):
        samples = [
            # Currency pair with 'and'
            ("The project budget was $4o and $5o per unit.", "The project budget was $40 and $50 per unit."),
            # Currency pair with 'to'
            ("Cost estimates range from $10o to $20oo.", "Cost estimates range from $100 to $2000."),
            # Currency pair with comma
            ("Spent $4o, $5o, and $6o respectively.", "Spent $40, $50, and $60 respectively."),
            # Single currency with digit-o confusion
            ("Total expenditure was $4o.", "Total expenditure was $40."),
            ("A fee of $20oo was paid.", "A fee of $2000 was paid."),
            # Currency in parenthesis
            ("Estimated costs ($4o or $5o) were acceptable.", "Estimated costs ($40 or $50) were acceptable."),
            # Mixed currency and OCR text typos
            ("The Administ  strator approved $4o for apparotus testing.", "The Administrator approved $40 for apparatus testing."),
        ]
        for inp, expected in samples:
            with self.subTest(inp=inp):
                self.assertEqual(clean_historical_ocr_text(inp), expected)

    def test_genuine_math_formulas_preserved(self):
        math_samples = [
            # Inline math with reactivity
            ("The reactivity formula is $3k/k$ under perturbation.", "The reactivity formula is $3k/k$ under perturbation."),
            # Inline LaTeX math
            ("Let $x = 4o$ in the formula $f(x) = x^2$.", "Let $x = 4o$ in the formula $f(x) = x^2$."),  # math protected
            ("Where $\\Delta k/k \\le 0.05$ holds.", "Where $\\Delta k/k \\le 0.05$ holds."),
            ("Equation $E = mc^2$ governs energy release.", "Equation $E = mc^2$ governs energy release."),
            # Display math block
            ("$$\n\\int_0^1 f(x) dx = 4o\n$$", "$$\n\\int_0^1 f(x) dx = 4o\n$$"),
            # Inline code block
            ("Run `calc_cost($4o, $5o)` now.", "Run `calc_cost($4o, $5o)` now."),
        ]
        for inp, expected in math_samples:
            with self.subTest(inp=inp):
                self.assertEqual(clean_historical_ocr_text(inp), expected)

    def test_plain_text_reactivity_without_math_delimiters(self):
        """In plain text without $ delimiters, 3k/k should be converted to Δk/k."""
        raw = "The reactivity addition of 3k/k was recorded."
        cleaned = clean_historical_ocr_text(raw)
        self.assertIn("Δk/k", cleaned)
        self.assertNotIn("3k/k", cleaned)


class TestAdversarialChineseNormalization(unittest.TestCase):
    """Stress test normalize_chinese_text on grammatical collocations and period typography."""

    def test_legitimate_grammatical_collocations_and_reduplications(self):
        samples = [
            # 2-character verb/noun reduplication (colloquial and formal)
            ("我们需要研究研究这个方案。", "我们需要研究研究这个方案。"),
            ("大家讨论讨论下一步的工作计划。", "大家讨论讨论下一步的工作计划。"),
            ("向专家请教请教核安全问题。", "向专家请教请教核安全问题。"),
            ("仔细检查检查反应堆阀门。", "仔细检查检查反应堆阀门。"),
            ("对数据进行分析分析。", "对数据进行分析分析。"),
            ("认真考虑考虑技术路线。", "认真考虑考虑技术路线。"),
            ("去现场看看仪表读数。", "去现场看看仪表读数。"),
            ("听听专家的意见。", "听听专家的意见。"),
            # Two adjacent identical words serving different grammatical roles
            ("通过该系统系统地开展实验。", "通过该系统系统地开展实验。"),
            ("设计设计图纸需要严格把关。", "设计设计图纸需要严格把关。"),
            ("发展发展中国家的清洁能源。", "发展发展中国家的清洁能源。"),
            # Idioms with AABB / AA structure
            ("工程师们战战兢兢地监测压力。", "工程师们战战兢兢地监测压力。"),
            ("工作人员兢兢业业地坚守岗位。", "工作人员兢兢业业地坚守岗位。"),
            ("各个部件清清楚楚，明明白白。", "各个部件清清楚楚，明明白白。"),
            ("世世代代的科学工作者。", "世世代代的科学工作者。"),
            ("天天向上，人人有责。", "天天向上，人人有责。"),
        ]
        for inp, expected in samples:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

    def test_nmt_stutter_loops_elimination(self):
        stutter_cases = [
            # 3+ identical single character repetition
            ("安全安全安全", "安全"),
            ("的 的 的 的", "的"),
            ("等等等等等", "等"),
            # 3+ identical 2-character phrase repetition
            ("系统系统系统", "系统"),
            ("反应堆反应堆反应堆", "反应堆"),
            ("限值限值限值限值", "限值"),
            # Repetition with punctuation
            ("系统，系统，系统，", "系统，"),
            ("安全、安全、安全、", "安全、"),
        ]
        for inp, expected in stutter_cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

    def test_period_punctuation_adversarial_matrix(self):
        cases = [
            # Sentence ending period followed by Western acronym
            ("这是核工程标准. MSRE 是熔盐堆标杆.", "这是核工程标准。MSRE 是熔盐堆标杆。"),
            ("该标准已经实施. ORNL 负责具体运行.", "该标准已经实施。ORNL 负责具体运行。"),
            # Sentence ending period followed by Western lowercase word
            ("系统已初始化. python 进程正在运行.", "系统已初始化。python 进程正在运行。"),
            # Sentence ending period followed by numbers
            ("反应堆处于安全状态. 1200 MW 是热功率上限.", "反应堆处于安全状态。1200 MW 是热功率上限。"),
            # Sentence ending period followed by quotes / brackets
            ("他说：“核安全至关重要.”", "他说：“核安全至关重要。”"),
            ("操作规程明确规定（参见第 4 条.）", "操作规程明确规定（参见第 4 条。）"),
            ("【操作手册.】", "【操作手册。】"),
            ("「这是安全规程.」", "「这是安全规程。」"),
            ("『必须严格执行.』", "『必须严格执行。』"),
            # Sentence ending period at end of line
            ("操作规程必须严格遵守.", "操作规程必须严格遵守。"),
        ]
        for inp, expected in cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)

    def test_negative_period_cases_protected(self):
        negative_cases = [
            # Filenames with extensions
            ("请查看附件文档.pdf 和数据表.xlsx 以及代码.py 文件。", "请查看附件文档.pdf 和数据表.xlsx 以及代码.py 文件。"),
            # Domains / URLs
            ("访问网站清华.edu.cn 获取更多信息。", "访问网站清华.edu.cn 获取更多信息。"),
            # Chapter numbers / Decimals
            ("在第 4.4 节中详细说明了 1210.5 °F 的温度上限。", "在第 4.4 节中详细说明了 1210.5 °F 的温度上限。"),
            # Ellipsis
            ("反应堆正在启动中... 请稍候。", "反应堆正在启动中... 请稍候。"),
        ]
        for inp, expected in negative_cases:
            with self.subTest(inp=inp):
                self.assertEqual(normalize_chinese_text(inp), expected)


class TestInSituRosterAndLegalNoticeIsolation(unittest.TestCase):
    """验证 Page 11 名单离散隔离与 Page 2 法律通知段落合并兼得（互不干扰）。"""

    def test_is_roster_entry_distinguishes_recipients_from_clauses(self):
        from src.in_situ_renderer import is_roster_entry

        # Page 11: 真实分发名单项（必须判定为 True，保持独立行）
        valid_recipients = [
            "1. R. G. Affel",
            "35. P. R. Kasten",
            "49-50. M. W. Rosenthal",
            "Lo, R. E. MacPherson",
            "63. Gale Young",
            "Central Research Library (CRL)",
            "Document Reference Section (DRS)",
            "J. L. Anderson",
            "F. Baes",
            "L. Crowley",
            "Blumberg",
            "Houtgzeel",
        ]
        for r in valid_recipients:
            self.assertTrue(is_roster_entry(r), f"Expected '{r}' to be recognized as roster entry")

        # Page 2: 法律声明前言与条款（必须判定为 False，绝不能误判为人员名单阻止合并）
        legal_clauses = [
            "A. Makes any warranty or representation, expressed or implied, with respect to the accuracy, completeness, or usefulness of the information contained in this report, or that the use of any information, apparatus, method, or process disclosed in this report may not infringe privately owned rights; or",
            "B. Assumes any liabilities with respect to the use of, or for damages resulting from the use of any information, apparatus, method, or process disclosed in this report.",
            "This report was prepared as an account of Government sponsored work. Neither the United States, nor the Commission, nor any person acting on behalf of the Commission:",
        ]
        for c in legal_clauses:
            self.assertFalse(is_roster_entry(c), f"Expected '{c[:40]}' NOT to be recognized as roster entry")

    def test_should_merge_blocks_merges_legal_notice_but_isolates_roster(self):
        from src.in_situ_renderer import should_merge_blocks

        # 1. Page 2 法律前言冒号结尾 -> 与条款 A. 必须成功合并
        intro_b = {
            "text": "This report was prepared as an account of Government sponsored work. Neither the United States, nor the Commission, nor any person acting on behalf of the Commission:",
            "x": 130.0, "y": 263.0, "w": 300.0, "h": 16.0,
        }
        clause_a_b = {
            "text": "A. Makes any warranty or representation, expressed or implied, with respect to the accuracy...",
            "x": 130.0, "y": 282.0, "w": 306.0, "h": 40.0,
        }
        self.assertTrue(
            should_merge_blocks(intro_b, clause_a_b, page_w=612.0),
            "Page 2 intro sentence ending in colon MUST merge with Clause A."
        )

        # 2. Page 11 人员名单两行 -> 必须严格隔离不合并
        roster_1 = {"text": "35. P. R. Kasten", "x": 176.0, "y": 420.0, "w": 90.0, "h": 9.0}
        roster_2 = {"text": "36. R. B. Lindauer", "x": 176.0, "y": 431.0, "w": 95.0, "h": 9.0}
        self.assertFalse(
            should_merge_blocks(roster_1, roster_2, page_w=612.0),
            "Page 11 roster entries MUST remain discrete and unmerged."
        )

    def test_clean_ocr_item_filters_scanner_dust_specks(self):
        from src.in_situ_renderer import is_clean_ocr_item

        # 孤立单字母灰尘污渍（Page 2 的 L，Page 3 的 J、s、g）应当过滤
        dust_speck_l = {"text": "L", "x": 433.0, "y": 241.0, "width": 9.3, "height": 6.1}
        dust_speck_j = {"text": "J", "x": 540.0, "y": 320.0, "width": 1.8, "height": 3.0}
        self.assertFalse(is_clean_ocr_item(dust_speck_l, page_w=612.0, page_h=792.0))
        self.assertFalse(is_clean_ocr_item(dust_speck_j, page_w=612.0, page_h=792.0))

        # 真实单字母单词或章节序号绝不能过滤
        valid_word_a = {"text": "a", "x": 150.0, "y": 200.0, "width": 6.0, "height": 9.0}
        valid_marker_a = {"text": "A.", "x": 130.0, "y": 280.0, "width": 10.0, "height": 9.0}
        self.assertTrue(is_clean_ocr_item(valid_word_a, page_w=612.0, page_h=792.0))
        self.assertTrue(is_clean_ocr_item(valid_marker_a, page_w=612.0, page_h=792.0))


class TestInSituLayoutCascadeAndFitting(unittest.TestCase):
    """验证原位排版仿 pdf2zh 动态字号行距缩放、纵向层叠防重叠与页底脚注保护。"""

    def test_estimate_rendered_lines_cjk_and_latin(self):
        from src.in_situ_renderer import estimate_rendered_lines

        # 30 个汉字在 150pt 宽度、10pt 字号下应该排 ~2-3 行
        cjk_text = "液体燃料反应堆的主要好处之一是有可能不断加工燃料和一揽子材料"
        lines = estimate_rendered_lines(cjk_text, font_size_pt=10.0, width_pt=150.0)
        self.assertTrue(2 <= lines <= 3)

        # 短英文字符串在足够宽的容器里排 1 行
        short_en = "Chapter 6 Chemical Processing"
        lines_en = estimate_rendered_lines(short_en, font_size_pt=10.0, width_pt=300.0)
        self.assertEqual(lines_en, 1)

    def test_dynamic_typography_fitting_scales_down(self):
        from src.in_situ_renderer import compute_block_typography

        # 长文本在有限高度容器中必须自适应缩小行距与字号，防止溢出膨胀
        blk = {
            "text": "Long paragraph text with lots of details about chemical extraction and reactor fuels.",
            "zh_text": "在295°C时，0.02米的U02S04溶液中，硫酸钡的溶解度为7毫克/千克H2O，硫酸锶的溶解度为21毫克/千克H2O。在酸性溶液中由于氢气的存在会发生还原反应。",
            "font_size": 8.5,
            "w": 320.0,
            "h": 35.0,  # 目标高度较紧凑
            "lines_count": 3,
        }
        fs, fw, lh, sp = compute_block_typography(blk, page_w=419.0, page_h=594.0, target_h=35.0)
        self.assertLessEqual(lh, 1.40)
        self.assertLessEqual(fs, 10.0)

    def test_cascade_prevents_consecutive_block_overlap(self):
        from src.in_situ_renderer import layout_page_blocks

        # 连续两个块处于同一栏，前一个块由于译文较长向下扩展，后一个块必须被级联下推
        blocks = [
            {
                "orig_text": "Block 1 line 1. Block 1 line 2.",
                "zh_text": "第 18 项参考文献详细阐述了均相反应堆项目的季度技术进展报告，涵盖各项工程与化学处理流程指标。",
                "x": 55.0, "y": 60.0, "w": 320.0, "h": 20.0, "font_size": 8.0,
            },
            {
                "orig_text": "Block 2 line 1.",
                "zh_text": "第 19 项参考文献阐述了锕系元素化学分离过程。",
                "x": 55.0, "y": 82.0, "w": 320.0, "h": 20.0, "font_size": 8.0,
            },
        ]
        placed = layout_page_blocks(blocks, page_w=419.0, page_h=594.0, min_gap=2.5)
        self.assertEqual(len(placed), 2)
        b0, b1 = placed[0], placed[1]
        self.assertGreaterEqual(b1["y"], b0["y"] + b0["est_h"] + 2.5)

    def test_reference_typography_scale(self):
        from src.in_situ_renderer import quantize_typography

        # 参考文献条目（如 18. R. E. LEUZE et al.）字号收敛于 8.5~9.5pt，避免强制 11pt 导致炸裂
        ref_blk = {
            "orig_text": "18. R. E. LEUZE et al., in Homogeneous Reactor Project Quarterly Progress Report",
            "font_size": 7.8, "x": 55.0, "y": 62.0, "w": 320.0, "h": 30.0,
        }
        font_size, weight = quantize_typography(ref_blk, page_w=419.0, page_h=594.0)
        self.assertLessEqual(font_size, 9.5)
        self.assertGreaterEqual(font_size, 8.5)

    def test_footnote_ceiling_prevents_encroachment(self):
        from src.in_situ_renderer import layout_page_blocks

        # 正文块很长，但下方有页底脚注，正文块不得侵入脚注保护区
        blocks = [
            {
                "orig_text": "Body paragraph filling the page.",
                "zh_text": "液体燃料反应堆的主要优势之一是可以连续处理燃料和包层材料以消除裂变产物和其他毒物。" * 8,
                "x": 55.0, "y": 140.0, "w": 320.0, "h": 380.0, "font_size": 9.0,
            },
            {
                "orig_text": "*By R. A. McNees, with contributions from...",
                "zh_text": "* 由 R. A. McNees 提供，经橡树岭国家实验室授权。",
                "x": 55.0, "y": 550.0, "w": 320.0, "h": 22.0, "font_size": 8.5,
            },
        ]
        placed = layout_page_blocks(blocks, page_w=419.0, page_h=594.0, min_gap=2.5)
        body = [b for b in placed if not b["is_footnote"]][0]
        fn = [b for b in placed if b["is_footnote"]][0]
        self.assertLessEqual(body["y"] + body["est_h"], fn["y"])

    def test_chapter_and_section_heading_quantization(self):
        from src.in_situ_renderer import quantize_typography

        # CHAPTER 6 必须识别为一级标题字号 (>= 12.0pt, weight 700)
        ch_blk = {"orig_text": "CHAPTER 6", "font_size": 10.5, "align": "center", "y": 75.0, "w": 60.0}
        fs, fw = quantize_typography(ch_blk, page_w=419.0, page_h=594.0)
        self.assertGreaterEqual(fs, 12.0)
        self.assertEqual(fw, "700")

        # 居中全大写章节副标题 (CHEMICAL PROCESSING*) 识别为章节标题
        sub_blk = {"orig_text": "CHEMICAL PROCESSING*", "font_size": 10.5, "align": "center", "y": 98.0, "w": 128.0}
        fs_sub, fw_sub = quantize_typography(sub_blk, page_w=419.0, page_h=594.0)
        self.assertGreaterEqual(fs_sub, 12.0)
        self.assertEqual(fw_sub, "700")

        # 连字符格式章节小节号 (6-1. INTRODUCTION 或 6-l. INTRODUCTION) 识别为二级标题 (11.0pt, weight 600)
        sec_blk = {"orig_text": "6-1. INTRODUCTION", "font_size": 10.5, "align": "center", "y": 120.0, "w": 83.0}
        fs_sec, fw_sec = quantize_typography(sec_blk, page_w=419.0, page_h=594.0)
        self.assertEqual(fs_sec, 11.0)
        self.assertEqual(fw_sec, "600")

    def test_alphanumeric_word_wrap_line_estimation(self):
        from src.in_situ_renderer import estimate_rendered_lines

        # 包含长英文单词/编号/化学式的致密参考文献条目，换行估算必须考虑单词整体换行 slack
        ref_text = (
            "13. D. E. FERGUSON 等人。Oak Ridge 国家实验室，载于同质反应堆项目季度进展报告，"
            "USEC Reports ORNL-2272,1957 年(第 5 页)。133-135;ORNL-2331,1957 年(第 13 页)。"
            "142-143,148-149;ORNL-2379,1957 年(第 2 页)。138-139。"
        )
        lines = estimate_rendered_lines(ref_text, font_size_pt=8.5, width_pt=322.8)
        self.assertGreaterEqual(lines, 4)


if __name__ == "__main__":
    unittest.main()
