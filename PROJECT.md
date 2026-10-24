# Project: LiteParse PDF 本地识别与离线翻译深度优化 (P052)

## Architecture
LiteParse 是面向学术与历史文献的轻量化本地离线 PDF 识别与神经机器翻译流水线。
本优化项目针对 1950-1960 年代历史打字机扫描文献（以 ORNL-TM-0733REV3 MSRE 运行安全规程为标杆），全面消除结构阻断、术语翻车与表格对齐幻觉，将端到端综合评分从 38.8 分提升至 90 分以上。

### Pipeline Flow
1. **Input**: PDF 文档投递至 `inbox/`（或已处理在 `processed/`）。
2. **OCR & Layout**: PaddleOCR / `lit` 解析排版，输出中间 Markdown。
3. **Pre-translation OCR Cleaning (R4)**: `clean_historical_ocr_text` 修正打字机连词、字母数字混淆（`4o`->`40`, `ts`->`is`, `L.k`->`4.4`）与工程单位。
4. **Structure & Code Classification (R1)**: `classify_code_block` 区分真实编程语言代码与打字机等宽正文，对真实代码提供 100% 字节保护，对正文解除围栏送入翻译流。
5. **Terminology & Placeholder Isolation (R2)**: 77 项 MSR 核工程专业术语匹配（`[-\s]+` 连字符容错），通过 `XPH{i}X` 占位符隔离。
6. **Table Triage & Invariants (R3)**: `translate_table` 四阶分流，孤立停用词（$\le 3$ 字符）直接查表短路映射，基准列数 $N$ 守恒与 `\|` 转义保护。
7. **Inference**: CTranslate2 INT8 轻量本地模型批量并行推理（纯离线，<200MB，零外部守护）。
8. **Post-translation Typography (R4)**: `normalize_chinese_text` 执行 GB/T 15834-2011 规范（盘古之白 CJK/西文空格、全角标点规整）。
9. **Atomic Output**: 成果物原子写入 `outbox/`（`.zh.md` 与单文件 `.zh.html`）。

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | 打字机 OCR 微规整与启发式清洗 (R4) | 30+ 规则预清洗字母数字混淆、打字机连词、章节序号错误与工程单位 | M1 | Survey (Explorer 1 & 3) |
| F2 | 代码块与打字机正文双特征分类器 (R1) | 语法模式+停用词密度精准判别真实代码与打字机正文，解除围栏提升覆盖率至 $\ge 98\%$ | M1 | Survey (Explorer 1) |
| F3 | 熔盐堆与核工程 77 核心术语字典与占位保护 (R2) | 5大领域 77 个专业术语、连字符容错正则、`XPH{i}X` 占位符隔离与还原 | M2 | Survey (Spec Miner 2) |
| F4 | 表格停用词对齐幻觉短路与列守恒 (R3) | 孤立虚词/停用词确定性映射，0 处 `联年月日`，基准列数 $N$ 守恒与转义管道符隔离 | M2 | Survey (Spec Miner 2 & 3) |
| F5 | 科技公文中文排版规范后处理 (R4) | GB/T 15834-2011 标准：盘古之白（中西文空一格）、标点全角规整、零冗余空格 | M1 | Survey (Explorer 1) |
| F6 | 4阶 E2E 测试套件与五维自动化评分架构 | Tier 1~4 需求驱动黑盒测试套件、5维量化评分脚本（目标 $\ge 90/100$） | E2E-Track & M-Final | Survey (Explorer 3) |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | 结构解阻与打字机 OCR 预清洗 (R1+R4) | `classify_code_block`, `clean_historical_ocr_text`, `normalize_chinese_text` Pangu spacing, 真实代码 100% 保护, 覆盖率 $\ge 98\%$ | None | DONE |
| M2 | MSR 核工程术语注入与表格对齐幻觉消除 (R2+R3) | 77 术语字典, `XPH{i}X` 占位符引擎, `TABLE_STOPWORDS_MAP` 短路, 列数 $N$ 守恒 | M1 Interface Contracts | IN_PROGRESS |
| E2E | 端到端黑盒测试套件构建 (E2E Testing Track) | 4-Tier 测试架构（Tier 1~4，11*N+5 用例），五维评分脚本，发布 `TEST_READY.md` | Survey | DONE (`TEST_READY.md`) |
| M-Final | 最终端到端验收与对抗硬化 (Final Milestone) | Phase 1: 100% 通过 E2E 测试且综合分 $\ge 90$; Phase 2: Tier 5 对抗性测试与覆盖硬化 | M1, M2, E2E | PLANNED |

---

## Interface Contracts

### M1 ↔ M2 (Pipeline Execution Order)
1. **Pre-translation Order**:
   - Step A: `clean_historical_ocr_text(line)` executes first on raw input lines.
   - Step B: `classify_code_block(lang, content)` checks whether fenced blocks are real code or typewriter prose. If prose, unwrap and pass through OCR cleaner.
   - Step C: `inject_glossary_placeholders(text, glossary)` applies MSR terminology replacements via `XPH{i}X` markers on cleaned prose text.
   - Step D: Text/table cells enter CTranslate2 batch translation.
2. **Post-translation Order**:
   - Step E: `normalize_chinese_text(translated)` applies typography (fullwidth punctuation, CJK-alphanumeric spacing).
   - Step F: `restore_placeholders(translated, placeholder_map)` restores Chinese terms and preserved technical tags using safe callable lambda.

### M2 Table Processing Contract
- `translate_table(table_block, ...)` must maintain the header column count $N$.
- Cells matching `TABLE_STOPWORDS_MAP` (e.g. `of` -> `的`, `the` -> `该`, `in` -> `内`) short-circuit immediately without invoking NMT.
- Preserved pipe characters inside cells must be isolated as `XPH_PIPE_X` before column splitting and restored after cell reassembly.

---

## Code Layout
- `src/translator.py`: 核心离线翻译引擎、代码块分类器、OCR微清洗、MSR术语表、表格短路分流器、中文排版后处理器。
- `src/config.py`: 配置管理（支持术语与排版选项）。
- `tests/test_translator.py`: 翻译器核心单元测试套件（现有 25 项 + 新增项）。
- `tests/test_watcher.py`: 监控与管道集成测试（现有 24 项）。
- `tests/test_paddle_ocr.py`: OCR 流与进程复用测试（现有 16 项）。
- `tests/e2e/`: E2E 黑盒测试套件（Tier 1~4 测试用例、端到端评估脚本、5维综合评分量规）。
- `outbox/`: 翻译成果物输出目录（`.zh.md`, `.zh.html`）。
- `processed/`: 归档原始输入文献（含标杆 `ORNL-TM-0733REV3_MSRE_Design_Operations_Part_VI_Rev3.pdf`）。
