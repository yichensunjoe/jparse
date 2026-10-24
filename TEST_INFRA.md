# E2E Test Infra: LiteParse PDF Local Recognition & Offline Translation (P052)

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Derived strictly from `ORIGINAL_REQUEST.md` and user-facing acceptance criteria, independent of implementation internal design.
- **Methodology**: Category-Partition + Boundary Value Analysis (BVA) + Pairwise Combinatorial Testing + Real-World Workload Testing (ORNL-TM-0733REV3).

## Feature Inventory
| # | Feature | Source (Requirement) | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Real-World) |
|---|---------|---------------------|:----------------:|:-----------------:|:-----------------:|:-------------------:|
| 1 | 打字机 OCR 微规整与启发式清洗 (R4) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |
| 2 | 代码块与打字机正文双特征分类器 (R1) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 3 | 真实代码块 100% 字节保护 (R1) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 4 | MSR 核心术语 100% 精确置换 (R2) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 5 | 表格停用词对齐短路与列对齐守恒 (R3) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 6 | 中文排版规范与格式规整 (R4) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Runner**: `python3 -m unittest discover -s tests/e2e -v` & `python3 tests/e2e/evaluate_benchmark.py`
- **Pass/Fail Semantics**: 100% of automated unit & E2E tests pass (exit code 0), 5-dimension objective composite score $\ge 90.0 / 100$.
- **Test Case Format**: Structured unittest assertions with input Markdown / text snippets, expected translated strings, coverage metrics, and regex validations.
- **Directory Layout**:
  - `tests/e2e/test_tier1_features.py`: $\ge 30$ feature tests (5 per feature).
  - `tests/e2e/test_tier2_boundaries.py`: $\ge 30$ boundary & edge case tests.
  - `tests/e2e/test_tier3_pairwise.py`: $\ge 15$ cross-feature interaction tests.
  - `tests/e2e/test_tier4_benchmark.py`: Real-world document evaluation scenarios.
  - `tests/e2e/evaluate_benchmark.py`: 5-dimension automated scoring evaluator.

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity | Target Benchmark Document |
|---|----------|--------------------|------------|---------------------------|
| 1 | 标杆 MSRE 运行安全限值规程全篇翻译 | F1, F2, F3, F4, F5, F6 | High | `processed/ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf` |
| 2 | 纯文本扫描书模式全页代码围栏解阻 | F1, F2, F5 | Medium | `outbox/ORNL-CF-58-10-37.md` |
| 3 | 混合技术代码与打字机正文共存保护 | F2, F3, F6 | Medium | Synthetic Python/Shell + MSR limits |
| 4 | 密集单字/虚词工程表格翻译与列守恒 | F4, F5, F6 | High | MSRE Fuel System & Radiation Alarm Tables |
| 5 | 极端打字机油墨粘连与字母数字混淆修复 | F1, F3, F5 | Medium | Historical OCR fragments (`4o`, `ts`, `L.k`, `ft°`) |

## Coverage Thresholds
- Tier 1: $\ge 30$ test cases ($\ge 5$ per feature).
- Tier 2: $\ge 30$ test cases ($\ge 5$ per feature).
- Tier 3: $\ge 15$ pairwise interaction test cases.
- Tier 4: $\ge 5$ realistic application-level scenarios.
- **Total E2E Test Suite**: $\ge 80$ test cases + automated 5-dimension benchmark evaluator.
- **Acceptance Threshold**: Composite score $S = 0.15 S_{\text{offline}} + 0.15 S_{\text{ocr}} + 0.25 S_{\text{struct}} + 0.25 S_{\text{term}} + 0.20 S_{\text{fluent}} \ge 90.0 / 100$.
