#!/usr/bin/env python3
"""LiteParse 本地离线文献翻译引擎 (Product-Grade Self-Contained Translation Engine).

摆脱对 Ollama 或外部后台守护服务的依赖，将轻量化 CTranslate2 引擎与 NMT 模型内置于 assets/models/，
实现极速（>100 句/秒）、低内存（<200MB）、完全本地离线的高质量科技文献中英互译。

特性：
1. 结构化 Markdown 保护：代码块、公式块、HTML 注释、表格结构、行内代码、行内公式、图片链接原生免疫破坏。
2. 术语表与规范化：集成 ASME 等专业术语表与规范中文排版（标点规范、去中文间空格、防结巴复读）。
3. 全文批处理翻译：一次性调度全篇段落与表格，充分利用多核 CPU 并行能力，避免 O(N^2) 重复计算与逐句 I/O 阻塞。
4. 双模输出：纯中文精译版 (.zh.md, .zh.html) 与对齐双语版 (.bilingual.md, .bilingual.html)。
5. 确定性单文件 HTML 生成：继承项目安全规范，转义原始不可信输入，图片 Base64 Data URI 内嵌。
6. 原子发布：中间文件经 .partial 暂存，成功后原子更名，失败完整回滚。
"""

import argparse
from dataclasses import dataclass, field
import importlib.util
import os
from pathlib import Path
import re
import sys
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

try:
    from .html_renderer import render_markdown_document
except ImportError:
    from html_renderer import render_markdown_document

# 常用英文缩写词库（句尾点号不作为断句依据）
_ABBREVIATIONS = {
    "e.g.", "i.e.", "fig.", "tab.", "sec.", "para.", "no.", "dr.", "vs.",
    "al.", "vol.", "pp.", "ref.", "approx.", "dept.", "assn.", "inc.",
    "ltd.", "co.", "corp.", "rev.", "ed.", "ch.", "app.", "art.",
}

# 表格孤立停用词/虚词短路映射字典 (R3: 彻底消除联合国决议日期循环、排、天然气气体等对齐幻觉)
TABLE_STOPWORDS_MAP: Dict[str, str] = {
    # 常用孤立冠词、介词、连词与代词（全覆盖 <= 3 字符与常见单字）
    "the": "该",
    "The": "该",
    "THE": "该",
    "of": "的",
    "Of": "的",
    "OF": "的",
    "a": "",
    "an": "",
    "A": "",
    "An": "",
    "in": "内",
    "In": "内",
    "IN": "内",
    "to": "至",
    "To": "至",
    "TO": "至",
    "for": "用于",
    "For": "用于",
    "FOR": "用于",
    "as": "作为",
    "As": "作为",
    "AS": "作为",
    "by": "由",
    "By": "由",
    "BY": "由",
    "at": "在",
    "At": "在",
    "AT": "在",
    "on": "在",
    "On": "在",
    "ON": "在",
    "from": "自",
    "From": "自",
    "FROM": "自",
    "with": "含",
    "With": "含",
    "WITH": "含",
    "into": "进入",
    "Into": "进入",
    "its": "其",
    "Its": "其",
    "it": "它",
    "It": "它",
    "is": "为",
    "Is": "为",
    "are": "为",
    "Are": "为",
    "was": "为",
    "Was": "为",
    "were": "为",
    "Were": "为",
    "be": "为",
    "Be": "为",
    "BE": "为",
    "gas": "气体",
    "Gas": "气体",
    "GAS": "气体",
    "total": "总计",
    "Total": "总计",
    "TOTAL": "总计",
    "or": "或",
    "Or": "或",
    "OR": "或",
    "and": "和",
    "And": "和",
    "AND": "和",
    "not": "非",
    "Not": "非",
    "NOT": "非",
    "no": "无",
    "No": "无",
    "NO": "无",
    "all": "全部",
    "All": "全部",
    "ALL": "全部",
    "any": "任一",
    "Any": "任一",
    "per": "每",
    "Per": "每",
    "via": "经由",
    "Via": "经由",
    "min": "分",
    "Min": "分",
    "sec": "秒",
    "Sec": "秒",
    "ref": "参考",
    "Ref": "参考",
    "each": "每个",
    "Each": "每个",
    "than": "比",
    "Than": "比",
    "this": "该",
    "This": "该",
    "that": "该",
    "That": "该",
    "of the": "该",
    "in the": "在",
    "to the": "至",
    "for the": "用于",
    "by the": "由",
    "at the": "于",
    "on the": "在",
    "from the": "自",
    "with the": "含",
    "and the": "及",
    "whenever": "当",
    "shield": "屏蔽",
    "blocks": "块",
    "shall": "应",
    "be": "为",
    "place": "就位",
    "secured": "固定",
    "devices": "装置",
    "manipulation": "操纵",
    "directly": "直接",
    "certified": "持证",
    "qualified": "合格",
    "supervised": "监督",
    "director": "主任",
    "division": "处",
    "division,": "处，",
    "vessel,": "容器，",
    "n/a": "N/A",
    "N/A": "N/A",
    "na": "N/A",
    "NA": "N/A",
    "-": "-",
    "--": "--",
    "---": "---",
    "/": "/",
}

# 熔盐堆与核工程 77+ 项核心专业术语表 (R2: 按长度严格降序排列，贪婪长词优先匹配)
MSR_GLOSSARY_77: List[Tuple[str, str]] = [
    ("operating safety limits for the molten-salt reactor experiment", "熔盐堆实验装置运行安全限值规程"),
    ("operating safety limits", "运行安全限值规程"),
    ("molten-salt reactor experiment", "熔盐堆实验装置 (MSRE)"),
    ("msre design and operations report", "MSRE 设计与运行报告"),
    ("design and operations report", "设计与运行报告"),
    ("u.s. atomic energy commission", "美国原子能委员会"),
    ("atomic energy commission", "原子能委员会"),
    ("oak ridge national laboratory", "橡树岭国家实验室"),
    ("union carbide corporation", "联合碳化物公司"),
    ("nuclear division", "核能事业部"),
    ("surge volume", "缓冲容积"),
    ("overflow tank", "溢流排盐罐"),
    ("effective delayed neutron fraction", "有效缓发中子份额"),
    ("aqueous homogeneous reactor", "水均匀反应堆"),
    ("delayed neutron precursor", "缓发中子先驱体"),
    ("vapor-condensing system", "蒸汽冷凝系统"),
    ("neutron count-rate channel", "中子计数率通道"),
    ("vapor-condensing tank", "蒸汽冷凝罐"),
    ("nuclear instrumentation", "核测控仪表"),
    ("flux safety channels", "中子通量安全通道"),
    ("flux safety channel", "中子通量安全通道"),
    ("period trip point", "周期停堆跳闸设定值"),
    ("secondary containment", "二道安全壳"),
    ("tellurium embrittlement", "碲脆化"),
    ("thorium fuel cycle", "钍-铀燃料循环"),
    ("flux trip point", "通量跳闸设定值"),
    ("primary containment", "一道安全壳"),
    ("cell shield blocks", "舱室屏蔽块"),
    ("reactivity anomaly", "反应性异常"),
    ("particulate emitters", "颗粒放射源"),
    ("neutron count rate", "中子计数率"),
    ("absolute filters", "高效空气过滤器"),
    ("fuel offgas system", "燃料尾气系统"),
    ("graphite moderator", "石墨慢化剂"),
    ("sampler-enricher", "取样浓缩添加器"),
    ("reactivity worth", "反应性价值"),
    ("hold-down device", "压紧装置"),
    ("excess reactivity", "剩余反应性"),
    ("fuel-pump bowl", "燃料泵泵池"),
    ("fuel drain tank", "燃料排盐罐"),
    ("drain-tank cell", "排盐罐舱"),
    ("breeder reactor", "增殖堆"),
    ("prompt critical", "瞬发临界"),
    ("fissile material", "可裂变材料"),
    ("fertile material", "可转换材料"),
    ("reactor vessel", "反应堆容器"),
    ("ventilation stack", "通风烟囱"),
    ("delayed neutron", "缓发中子"),
    ("prompt neutron", "瞬发中子"),
    ("reactor period", "反应堆周期"),
    ("charcoal bed", "活性炭吸附床"),
    ("xenon poisoning", "氙中毒"),
    ("instrument well", "仪表井"),
    ("conversion ratio", "转换比"),
    ("grain boundary", "晶界"),
    ("high-bay area", "高跨区"),
    ("chief operator", "主操"),
    ("specific power", "比功率"),
    ("breeding ratio", "增殖比"),
    ("breeding gain", "增殖增益"),
    ("doubling time", "倍增时间"),
    ("fission product", "裂变产物"),
    ("thermal shield", "热屏蔽"),
    ("overflow tank", "溢流罐"),
    ("freeze valve", "冷冻阀"),
    ("freeze flange", "冷冻法兰"),
    ("salt sampler", "熔盐取样器"),
    ("coolant salt", "冷却盐"),
    ("carrier salt", "载体盐"),
    ("leak detector", "泄漏探测器"),
    ("scram circuit", "停堆跳闸电路"),
    ("scram trip", "停堆跳闸"),
    ("scram test", "停堆试验"),
    ("scram time", "停堆时间"),
    ("period trip", "周期停堆跳闸"),
    ("reactor cell", "反应堆舱"),
    ("control rod", "控制棒"),
    ("regulating rod", "调节棒"),
    ("safety rod", "安全棒"),
    ("shim rod", "补偿棒"),
    ("drain tank", "排盐罐"),
    ("flush salt", "冲洗盐"),
    ("fuel salt", "燃料盐"),
    ("decay heat", "衰变热"),
    ("containment", "安全壳"),
    ("subcritical", "次临界"),
    ("block valve", "隔离阀"),
    ("check valve", "止回阀"),
    ("fuel burnup", "燃料燃耗"),
    ("pump bowl", "泵池"),
    ("cover gas", "覆盖气体"),
    ("Hastelloy-N", "哈氏合金N"),
    ("INOR-8", "INOR-8合金"),
    ("radiator", "空冷散热器"),
    ("offgas", "尾气"),
    ("burnup", "燃耗"),
    ("corrosion", "腐蚀"),
    ("drained", "排空"),
    ("annulus", "环形空间"),
    ("header", "联箱"),
    ("FLiNaK", "FLiNaK"),
    ("FLiBe", "FLiBe"),
    ("scram", "停堆"),
    ("critical", "临界"),
    ("reactivity", "反应性"),
]

# 默认内置核心专业术语表与规范化映射 (MSR 核心术语 + ASME 机械规范)
_DEFAULT_GLOSSARY: List[Tuple[str, str]] = list(MSR_GLOSSARY_77) + [
    # 常用机械与核能规范术语（中文标准化映射）
    ("动力驱动", "动力操作"),
    ("抗震报告", "抗震鉴定报告"),
    ("压力泄放阀", "泄压阀"),
    ("起动力", "起动载荷"),
    ("分叉区", "交会区"),
    ("构筑物", "结构"),
    ("原动力", "动力源"),
    ("抗震规范", "抗震鉴定规范"),
    ("主动机械设备", "能动机械设备"),
    ("有效机械设备", "能动机械设备"),
    ("主动设备", "能动设备"),
    ("液压脉冲", "液压缓冲器"),
    ("液压减震器", "液压缓冲器"),
    ("水力阻尼器", "液压缓冲器"),
    ("母体约束", "母型约束件"),
    ("软化盐", "熔盐"),
    ("熔融盐", "熔盐"),
    ("熔盐反应堆和能", "熔盐堆与钍能"),
    # 表格常用表头规范化（消除单字/短语歧义）
    ("函数职能", "功能"),
    ("函数职能功能", "功能"),
    ("状态状况现状", "状态"),
    ("状况状况", "状态"),
    ("股股", "单位"),
    ("构成部分", "部件"),
    # 情态动词规范（强制 ASME 准则：shall=应，should=宜，may=可）
    ("必须", "应"),
    ("应当", "应"),
    ("应予", "应"),
    ("应该", "宜"),
    ("可以", "可"),
]


def _safe_link_url(raw_url: str) -> Optional[str]:
    """验证链接安全性，拒绝危险 URL scheme（与 html_renderer 规范保持一致）。"""
    value = raw_url.strip().strip("<>")
    parsed = urlsplit(value)
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return value
    if not parsed.scheme and not parsed.netloc and (value.startswith("#") or not value.startswith("javascript:")):
        return value
    return None


# 英语常见停用词集合（用于代码块启发式判定与虚假标签过滤）
_PROSE_STOPWORDS = {
    "the", "of", "and", "to", "in", "is", "that", "for", "it", "as", "was",
    "with", "be", "by", "on", "not", "he", "at", "this", "are", "from", "or",
    "an", "they", "which", "one", "you", "were", "her", "all", "she", "there",
    "would", "their", "we", "him", "been", "has", "when", "who", "will", "more",
    "no", "if", "out", "so", "said", "what", "up", "its", "about", "into", "than",
    "them", "can", "only", "other", "new", "some", "could", "time", "these",
    "two", "may", "then", "do", "first", "any", "my", "now", "such", "like",
    "our", "over", "me", "even", "most", "made", "after", "also", "did", "many",
    "before", "must", "through", "back", "where", "much", "your", "way", "well",
    "down", "should", "because", "each", "just", "those", "how", "too", "little",
    "good", "very", "make", "still", "own", "see", "work", "long", "here",
    "between", "both", "under", "never", "same", "another", "while", "last",
    "might", "since", "against", "shall"
}

# 真实计算机编程语法强特征模式（支持大小写不敏感 SQL 关键字）
_CODE_KEYWORDS_RE = re.compile(
    r"(?m)(?:^\s*(?:def\s+\w+\s*\(|class\s+\w+|import\s+\w+|from\s+\w+\s+import|"
    r"#include\s*<|#define\s+|int\s+main\s*\(|void\s+\w+\s*\(|printf\s*\(|"
    r"#!/bin/|#!\s*/usr/bin/|echo\s+[\"'\$]|chmod\s+|export\s+\w+=|pip\s+install|python3?\s+|"
    r"(?i:SELECT\s+.+\s+FROM|INSERT\s+INTO|CREATE\s+TABLE|UPDATE\s+\w+\s+SET)|"
    r"return\s+[a-zA-Z0-9_\(\{\[\"']|elif\s+|except\s*[\w\s]*:|lambda\s+\w+:|"
    r"public\s+static\s+void|fn\s+main\s*\(|func\s+\w+\s*\())"
)


def _strip_comments_and_docstrings(text: str) -> str:
    """去除代码中的注释与文档字符串，用于自然语言散文特征纯净分析。"""
    # 1. Python/多行文档字符串（三引号）
    t = re.sub(r'"""[\s\S]*?"""', '', text)
    t = re.sub(r"'''[\s\S]*?'''", '', t)
    # 2. C/C++/Java/JS 块注释
    t = re.sub(r'/\*[\s\S]*?\*/', '', t)
    # 3. HTML/XML 注释
    t = re.sub(r'<!--[\s\S]*?-->', '', t)
    # 4. 单行注释（保留 #include, #define, shebang）
    t = re.sub(r'(?m)^\s*#(?!(\s*/|include|define)).*$', '', t)
    t = re.sub(r'(?m)\s+#(?!(\s*/)).*$', '', t)
    t = re.sub(r'(?m)^\s*//.*$', '', t)
    t = re.sub(r'(?m)\s+//.*$', '', t)
    t = re.sub(r'(?m)^\s*--.*$', '', t)
    t = re.sub(r'(?m)\s+--.*$', '', t)
    return t


def classify_code_block(lang: str, content: str) -> bool:
    """精准区分真实计算机程序代码与历史打字机等宽正文/扫描全页文本块 (R1)。

    Args:
        lang: Markdown 代码围栏语言标识符（如 "python", "text", ""）。
        content: 代码块围栏内部文本内容。

    Returns:
        True: 真实计算机编程语言代码/配置数据（需 100% 字节保护与原始缩进冻结）。
        False: 历史打字机等宽散文/CommonMark 4空格缩进/扫描书文本（需解除围栏并翻译）。
    """
    clean_content = content.strip()
    if not clean_content:
        return False

    # 1. Shebang 强特征：直接识别为可执行脚本代码
    if re.match(r"^#!\s*/", clean_content):
        return True

    tag = (lang or "").strip().lower()

    RECOGNIZED_CODE_TAGS = {
        "python", "py", "c", "cpp", "c++", "bash", "sh", "zsh", "shell",
        "json", "yaml", "yml", "sql", "javascript", "js", "typescript", "ts",
        "html", "xml", "css", "java", "rust", "go", "ini", "toml",
        "dockerfile", "makefile", "ruby", "perl", "php", "markdown", "md",
    }
    PROSE_TAGS = {"text", "txt", "plain", "plaintext", "raw"}

    # 2. 编程语法关键字强模式匹配
    code_matches = len(_CODE_KEYWORDS_RE.findall(clean_content))

    # 3. JSON / 字典结构化数据判定
    is_structured_data = False
    if (clean_content.startswith("{") and clean_content.endswith("}")) or (
        clean_content.startswith("[") and clean_content.endswith("]")
    ):
        try:
            import json
            json.loads(clean_content)
            is_structured_data = True
        except Exception:
            if re.search(r'''^\s*["'][a-zA-Z0-9_-]+["']\s*:''', clean_content, re.M):
                is_structured_data = True

    # 4. 符号与结构统计
    lines = [line_item for line_item in clean_content.splitlines() if line_item.strip()]
    non_comment_lines = [
        line_item for line_item in lines
        if not re.match(r"^\s*(?:#|//|--|/\*|\*)", line_item)
    ]
    target_lines = non_comment_lines if len(non_comment_lines) >= 1 else lines

    semicolon_lines = sum(1 for line_item in lines if line_item.rstrip().endswith(";"))
    brace_count = clean_content.count("{") + clean_content.count("}")
    arrow_count = len(re.findall(r"(?:->|=>|===|!==|\+=|-=)", clean_content))
    yaml_lines = sum(1 for line_item in target_lines if re.match(r"^\s*[a-zA-Z0-9_-]+\s*:\s*(?:[^\s].*|\s*)$", line_item))
    assignment_lines = sum(1 for line_item in target_lines if re.match(r"^\s*[a-zA-Z_]\w*\s*=\s*.+$", line_item))

    has_strong_code_syntax = (
        code_matches > 0
        or is_structured_data
        or (tag in {"markdown", "md"} and bool(re.search(r"(?m)^\s*(?:`{3,}|~{3,}|#{1,6}\s+|-\s+|>\s+)", clean_content)))
        or (len(target_lines) >= 2 and yaml_lines >= len(target_lines) * 0.7)
        or (len(target_lines) >= 2 and assignment_lines >= len(target_lines) * 0.7)
        or (len(lines) == 1 and semicolon_lines == 1 and (code_matches > 0 or tag in {"sql", "c", "cpp", "javascript", "js", "java"}))
        or (len(lines) >= 2 and semicolon_lines >= max(2, len(lines) * 0.5) and (code_matches > 0 or tag in RECOGNIZED_CODE_TAGS))
    )

    # 若声明为代码语言且具备确凿代码语法特征，100% 确定为代码
    if tag in RECOGNIZED_CODE_TAGS and has_strong_code_syntax:
        return True

    # 若声明为散文且无任何代码语法特征，直接判定为散文
    if tag in PROSE_TAGS and not has_strong_code_syntax:
        return False

    code_score = 0
    prose_score = 0

    # 语言标签基础权重
    if tag in PROSE_TAGS:
        prose_score += 4
    elif tag in RECOGNIZED_CODE_TAGS:
        code_score += 2

    # 代码特征加权
    if code_matches > 0:
        code_score += code_matches * 3
    if is_structured_data:
        code_score += 5
    if len(target_lines) >= 2 and yaml_lines >= len(target_lines) * 0.7:
        code_score += 4
    if len(target_lines) >= 2 and assignment_lines >= len(target_lines) * 0.7:
        code_score += 4
    if (len(lines) == 1 and semicolon_lines == 1 and (code_matches > 0 or tag in {"sql", "c", "cpp", "javascript", "js", "java"})) or (
        len(lines) > 1 and semicolon_lines >= max(1, len(lines) * 0.3)
    ):
        code_score += 4
    if brace_count >= 2:
        code_score += 3
    if arrow_count > 0:
        code_score += arrow_count * 2

    # 去除注释与文档字符串后进行散文特征提取
    prose_analysis_text = _strip_comments_and_docstrings(clean_content).strip()
    analysis_text = prose_analysis_text if prose_analysis_text else clean_content

    words = re.findall(r"\b[a-zA-Z]{2,}\b", analysis_text.lower())
    total_words = len(words)
    stopword_count = sum(1 for w in words if w in _PROSE_STOPWORDS)
    stopword_ratio = (stopword_count / total_words) if total_words > 0 else 0.0

    # 散文自然语言特征加权
    if total_words >= 6:
        if stopword_ratio >= 0.28:
            prose_score += 4
        elif stopword_ratio >= 0.20:
            prose_score += 2
        elif stopword_ratio < 0.12 and code_score > 0:
            code_score += 2

    # 科技公文/规程特定词频与句式（存在代码语法时实施衰减，防止领域注释误伤）
    prose_terms = len(
        re.findall(
            r"\b(?:shall|should|reactor|safety|limit|temperature|pressure|accordance|system|operation|experiment|containment|warranty|liabilities|disclosed|provisions|report)\b",
            analysis_text.lower(),
        )
    )
    if prose_terms >= 2:
        if has_strong_code_syntax:
            prose_score += min(2, prose_terms)
        else:
            prose_score += prose_terms * 2

    sentence_endings = len(re.findall(r"\.\s+[A-Z]", analysis_text))
    if sentence_endings > 0:
        if has_strong_code_syntax:
            prose_score += 1
        else:
            prose_score += sentence_endings * 2

    analysis_lines = [line_item for line_item in analysis_text.splitlines() if line_item.strip()]
    avg_words_per_line = total_words / max(1, len(analysis_lines))
    if avg_words_per_line >= 6 and total_words >= 15 and not has_strong_code_syntax:
        prose_score += 3

    return code_score > prose_score


def clean_historical_ocr_text(text: str) -> str:
    """清理历史文献打字机 OCR 典型击打与识别缺陷（Pre-translation 英文微规整，R4）。

    包含 30+ 条确定性启发式修复规则，消除数字/字母混淆、打字机连词、断行连字符与工程符号误识。
    行内代码与数学公式受到原子级占位隔离，避免误伤。
    """
    if not text:
        return text

    # 保护行内代码与数学公式
    stashed_inline: Dict[str, str] = {}
    counter = 0

    def _stash_inline(m: re.Match) -> str:
        nonlocal counter
        k = f"__HIST_OCR_STASH_{counter}__"
        stashed_inline[k] = m.group(0)
        counter += 1
        return k

    text = re.sub(
        r"(`[^`\n]+`|\$\$[\s\S]*?\$\$|\$(?!\s)[^\$\n]+?(?<!\s)\$(?!\d))",
        _stash_inline,
        text,
    )

    # 1. 跨行连字符断词重组：ex- \n ceeded -> exceeded, ele- \n ments -> elements
    text = re.sub(r"\b([a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,})\b", r"\1\2", text)
    text = re.sub(r"\bex-\s*ceeded\b", "exceeded", text)
    text = re.sub(r"\bEx-\s*ceeded\b", "Exceeded", text)

    # 2. 类别 A：数字与字母击打混淆 (Digit/Letter Confusions)
    # 2.1 机械打字机字母 o/O 替代数字 0：4o -> 40, 20oo -> 2000
    def _repl_num_o(m: re.Match) -> str:
        return m.group(1) + ("0" * len(m.group(2)))

    text = re.sub(r"\b(\d+)([oO]+)\b", _repl_num_o, text)

    # 2.2 孤立 1s -> is
    text = re.sub(r"\b1s\b", "is", text)
    text = re.sub(r"\b1S\b", "IS", text)

    # 2.3 墨迹 crossbar 粘连 ts -> is
    text = re.sub(r"\bts\b", "is", text)
    text = re.sub(r"\bTs\b", "Is", text)
    text = re.sub(r"\bTS\b", "IS", text)

    # 2.4 词首 1imit / 1limits -> limit / limits
    text = re.sub(r"\b1l?imit(s?)\b", r"limit\1", text)
    text = re.sub(r"\b1L?IMIT(S?)\b", r"LIMIT\1", text)

    # 2.5 章节序号混淆：2.h -> 2.4, L.2 -> 4.2, L.k -> 4.4, L.t -> 4.7, L1k -> 4.14, k11 -> 4.11
    text = re.sub(r"(?m)(?:^|(?<=\s))2\.h\b", "2.4", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))L\.(\d+)\b", r"4.\1", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))L\.k\b", "4.4", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))L\.t\b", "4.7", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))L1k\b", "4.14", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))k11\b", "4.11", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))[oO]l\s*2\.9\b", "2.9", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))4,10\b", "4.10", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))4,15\b", "4.15", text)
    text = re.sub(r"(?m)(?:^|(?<=\s))4,16\b", "4.16", text)

    # 2.6 标高与数字混淆：8Lg-ft -> 849-ft, L5 psig -> 45 psig
    text = re.sub(r"\b8Lg-ft\b", "849-ft", text)
    text = re.sub(r"\bL(\d+)\b(?=\s*(?:psig|scfd|gpm|Mw|MW|kW|ft|in|rpm|vol|elevation|%|°F|°C))", r"4\1", text)

    # 2.7 典型字母识别错词
    text = re.sub(r"\bOFERATING\b", "OPERATING", text)
    text = re.sub(r"\boferating\b", "operating", text)
    text = re.sub(r"\bOPERATIN\s+G\b", "OPERATING", text)
    text = re.sub(r"\bO\s+RNL\b", "ORNL", text)
    text = re.sub(r"\bvse\b", "use", text)
    text = re.sub(r"\bVse\b", "Use", text)
    text = re.sub(r"\btais\b", "this", text)
    text = re.sub(r"\bTais\b", "This", text)
    text = re.sub(r"\bbhe\b", "be", text)
    text = re.sub(r"\bBhe\b", "Be", text)
    text = re.sub(r"\buwatil\b", "until", text)
    text = re.sub(r"\bUwatil\b", "Until", text)
    text = re.sub(r"\bintec\b", "into", text)
    text = re.sub(r"\bIntec\b", "Into", text)
    text = re.sub(r"\b[wW]?main-\s*tained\b", "maintained", text)
    text = re.sub(r"\bwmaintained\b", "maintained", text)
    text = re.sub(r"\bWmaintained\b", "Maintained", text)
    text = re.sub(r"\bwmain-", "main-", text)
    text = re.sub(r"\bobove\b", "above", text)
    text = re.sub(r"\bObove\b", "Above", text)
    text = re.sub(r"\bpossgible\b", "possible", text)
    text = re.sub(r"\bPossgible\b", "Possible", text)
    text = re.sub(r"\bcon=[-~]?\s*centration\b", "concentration", text)
    text = re.sub(r"\bCon=[-~]?\s*centration\b", "Concentration", text)
    text = re.sub(r"\bAdminist\s+strator\b", "Administrator", text)
    text = re.sub(r"\badminist\s+strator\b", "administrator", text)
    text = re.sub(r"\brequi\s+guires\b", "requires", text)
    text = re.sub(r"\bRequi\s+guires\b", "Requires", text)
    text = re.sub(r"\bgverflow\b", "overflow", text)
    text = re.sub(r"\bGverflow\b", "Overflow", text)
    text = re.sub(r"\boT\b", "or", text)
    text = re.sub(r"\bapparotus\b", "apparatus", text)
    text = re.sub(r"\bapperatus\b", "apparatus", text)
    text = re.sub(r"\biniringe\b", "infringe", text)
    text = re.sub(r"\bcompletenens\b", "completeness", text)
    text = re.sub(r"\brighta\b", "rights", text)
    text = re.sub(r"\bGuymnon\b", "Guymon", text)
    text = re.sub(r"\bAgsicies\b", "Agencies", text)
    text = re.sub(r"\bThair\b", "Their", text)
    text = re.sub(r"\bab-\s*normality\b", "abnormality", text)
    text = re.sub(r"\bhigh~efficiency\b", "high-efficiency", text)
    text = re.sub(r"\bTest\*--", "Test --", text)
    text = re.sub(r"\b\*H\b", "**", text)
    text = re.sub(r"\bTIf\b", "If", text)
    text = re.sub(r"\bIeak\b", "Leak", text)
    text = re.sub(r"\bteken\b", "taken", text)
    text = re.sub(r"\bprepored\b", "prepared", text)
    text = re.sub(r"\bSiates\b", "States", text)
    text = re.sub(r"\bDOTUMENT\b", "DOCUMENT", text)
    text = re.sub(r"\bLMITED\b", "LIMITED", text)
    text = re.sub(r"\breactorfuel-outlet\b", "reactor fuel-outlet", text)
    text = re.sub(r"\bfihat\b", "that", text)
    text = re.sub(r"\bs0\b", "so", text)
    text = re.sub(r"\bpro=-?\s*cess\b", "process", text)
    text = re.sub(r"\b£ill\b", "fill", text)
    text = re.sub(r"\bb\?PErhedes\b", "supersedes", text)
    text = re.sub(r"\banext\b", "the next", text)
    text = re.sub(r"\bbétween\b", "between", text)
    text = re.sub(r"\boperatingli-l\b", "operating.", text)
    text = re.sub(r"\bcocolant\b", "coolant", text)

    # 2.8 经典历史文献报告声明与封面 OCR 严重残缺规范化
    text = re.sub(r"^[-=~_\s]*LEGAL\s+NOTICE[-=~_\sA-Z]*$", "LEGAL NOTICE", text, flags=re.I)
    text = re.sub(r"count of on posse (?:o he )?Keer the \"", "account of Government sponsored work. Neither the", text, flags=re.I)
    text = re.sub(r"(?:[£&]|(?<=\s))ACY\b", "Accuracy", text)
    text = re.sub(r"\bprocesd\b", "process", text, flags=re.I)
    text = re.sub(r"\{nfringe\b", "infringe", text)
    text = re.sub(r"\bCommisaion\b", "Commission", text)
    text = re.sub(r"\bempioyment\b", "employment", text)
    text = re.sub(r"\bempioyse\b", "employee", text)
    text = re.sub(r"\bpxtension\b", "Extension", text)
    text = re.sub(r"\bins\s+tallation\b", "installation", text)
    text = re.sub(r"\bpussed\b", "passed", text)
    text = re.sub(r"\byesulting\b", "resulting", text)
    text = re.sub(r"\bconiractor\b", "contractor", text)
    text = re.sub(r"\bpre!\b", "preliminary", text)
    text = re.sub(r"&\s*pre!\s*liminary", "a preliminary", text)
    text = re.sub(r"\bo he\b", "Neither the", text, flags=re.I)
    text = re.sub(r"subject to re-\s*i\s*is\s*pussed\s*to\s*the\s*disclosed", "subject to revision. It is not to be disclosed", text, flags=re.I)

    # 3. 类别 B：打字机油墨粘连与连词 (Ink Ligatures & Conjoined Words)
    text = re.sub(r"\benergydemands\b", "energy demands", text, flags=re.I)
    text = re.sub(r"\beconomyfrcm\b", "economy from", text, flags=re.I)
    text = re.sub(r"\bItis\b", "It is", text)
    text = re.sub(r"\bitis\b", "it is", text)
    text = re.sub(r"\bmadeit\b", "made it", text, flags=re.I)
    text = re.sub(r"\bplusthe\b", "plus the", text, flags=re.I)
    text = re.sub(r"\bThejustificatlon\b", "The justification", text)
    text = re.sub(r"\bthejustificatlon\b", "the justification", text)
    text = re.sub(r"\bOAKRIDGENATIONALLABORATORY\b", "OAK RIDGE NATIONAL LABORATORY", text)
    text = re.sub(r"\bCENTRAL\s+FILESNUMBER\b", "CENTRAL FILES NUMBER", text)
    text = re.sub(r"\bHamogeneous\b", "Homogeneous", text)
    text = re.sub(r"\bhamogeneous\b", "homogeneous", text)
    text = re.sub(r"\b(?:flsslonable|fisslonable|tissionable)\b", "fissionable", text, flags=re.I)
    text = re.sub(r"\bfertlle\b", "fertile", text, flags=re.I)

    # 4. 类别 C：物理单位与核工程符号修复
    # 4.1 立方英尺上标 3 误读为度数符号 °：ft° -> ft³
    text = re.sub(r"\bft°\b", "ft³", text)
    text = re.sub(r"\bft\s*°", "ft³", text)
    text = re.sub(r"\b5,0\b(?=\s*\|?\s*ft[°³])", "5.0", text)
    text = re.sub(r"\b0\.62\s*yc/sec\b", "0.62 μCi/sec", text)

    # 4.2 反应性变化率 3k/k 误读：3k/k -> Δk/k
    text = re.sub(r"(?:\b|(?<=%|\s))3k/k\b", "Δk/k", text)

    # 4.3 内部人员分发表打字机序号与 OCR 错字规整
    text = re.sub(r"^Lo,\s*R\.\s*E\.\s*MacPherson\b", "40. R. E. MacPherson", text)
    text = re.sub(r"^L1,\s*H\.\s*E\.\s*McCoy\b", "41. H. E. McCoy", text)
    text = re.sub(r"^L,\s*A,\s*J\.\s*Miller\b", "44. A. J. Miller", text)
    text = re.sub(r"^k5,\s*R\.\s*L\.,?\s*Moore\b", "45. R. L. Moore", text)
    text = re.sub(r"^4\.\s*E,\s*L\.\s*Nicholson\b", "46. E. L. Nicholson", text)
    text = re.sub(r"^5k,\s*TI\.\s*Spiewak\b", "54. I. Spiewak", text)
    text = re.sub(r"^61l\.\s*M\.\s*E\.\s*Whatley\b", "61. M. E. Whatley", text)
    text = re.sub(r"^¥-12\b", "Y-12", text)
    text = re.sub(r"\bM\.,\s*Ferris\b", "M. Ferris", text)
    text = re.sub(r"\bR\.\s*G,\s*Affel\b", "R. G. Affel", text)
    text = re.sub(r"\bA,\s*Cox\b", "A. Cox", text)
    text = re.sub(r"\bH,\s*Gabbard\b", "H. Gabbard", text)

    # 还原行内代码与数学公式
    for k, v in stashed_inline.items():
        text = text.replace(k, v)

    return text


def normalize_chinese_text(text: str) -> str:
    """标准化中文译文排版：落实 GB/T 15834-2011 标准规范。

    包含：
    1. 盘古之白 (Pangu Spacing)：中文字符与英文字母或半角数字之间保留一个半角空格。
    2. 全角中文标点规范：中文字符后的西文标点转换为全角。
    3. 全角标点零空格守卫：确保全角标点两侧零多余空格。
    4. CJK 字符间无意义空格剥离与 NMT 循环结巴消除。
    5. 行内代码与公式紧邻全角标点零空格排版。
    """
    if not text:
        return text

    # 1. 规范全角中文标点（在汉字后出现的半角逗号、分号、冒号、问号、感叹号）
    text = re.sub(r"([一-龥])\s*,\s*", r"\1，", text)
    text = re.sub(r"([一-龥])\s*;\s*", r"\1；", text)
    text = re.sub(r"([一-龥])\s*:\s*", r"\1：", text)
    text = re.sub(r"([一-龥])\s*\?\s*", r"\1？", text)
    # 避免将 Markdown 图片语法 ![alt](url) 中的感叹号误转为全角！
    text = re.sub(r"([一-龥])\s*!(?!\[)\s*", r"\1！", text)
    text = re.sub(r"([一-龥])\s*\.(?!\.)(?=\s|$|[\u4e00-\u9fa5\"'”’）\]】」』])\s*", r"\1。", text)
    text = re.sub(r"\s*([，。！？；：])\s*", r"\1", text)
    text = re.sub(r"\s*\.\s*$", "。", text)

    # 2. 去除中文字符之间的多余空格（NMT 分词空格残留）
    text = re.sub(r"(?<=[\u4e00-\u9fa5])\s+(?=[\u4e00-\u9fa5])", "", text)

    # 3. 盘古之白 (Pangu Spacing, GB/T 15834-2011)：在 CJK 汉字与英文字母或半角数字之间保留一个半角空格
    text = re.sub(r"([\u4e00-\u9fa5])\s*([A-Za-z0-9])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z0-9])\s*([\u4e00-\u9fa5])", r"\1 \2", text)

    # 4. 确保全角标点两侧零多余空格
    fullwidth_punc_close = r"[\uff0c\u3002\uff01\uff1f\uff1b\uff1a\u3001\uff09\u3011\u300b\u201d\u2019]"
    fullwidth_punc_open = r"[\uff08\u3010\u300a\u201c\u2018]"
    text = re.sub(rf"\s+({fullwidth_punc_close})", r"\1", text)
    text = re.sub(rf"({fullwidth_punc_close})\s+", r"\1", text)
    text = re.sub(rf"\s+({fullwidth_punc_open})", r"\1", text)
    text = re.sub(rf"({fullwidth_punc_open})\s+", r"\1", text)

    # 5. 去除 NMT 常见结巴循环复读（如“公式公式公式”、“名称名称名称”）
    for _ in range(2):
        text = re.sub(r"([\u4e00-\u9fa5]{2,6})\1{2,}", r"\1", text)
        text = re.sub(r"([\u4e00-\u9fa5])\1{2,}", r"\1", text)
        text = re.sub(r"([\u4e00-\u9fa5]{1,6}[，。、；\s]+)\1{2,}", r"\1", text)

    # 6. 规范行内代码和公式与中文之间微间距，但紧随标点时绝无空格
    text = re.sub(r"([\u4e00-\u9fa5])([`$])", r"\1 \2", text)
    text = re.sub(r"([`$])([\u4e00-\u9fa5])", r"\1 \2", text)
    text = re.sub(rf"([`$])\s+({fullwidth_punc_close})", r"\1\2", text)
    text = re.sub(rf"({fullwidth_punc_open})\s+([`$])", r"\1\2", text)

    return text.strip()


def chunk_long_text(text: str, max_words: int = 50) -> List[str]:
    """将超长无标点文本切分为适合模型位置编码的短片段。"""
    if len(text.split()) <= max_words:
        return [text]
    sub_chunks = re.split(r"(?<=[;:,])\s+|\s*\.{2,}\s*", text)
    result = []
    curr = []
    curr_len = 0
    for sc in sub_chunks:
        sc = sc.strip()
        if not sc:
            continue
        w_len = len(sc.split())
        if w_len > max_words:
            words = sc.split()
            for i in range(0, len(words), max_words):
                result.append(" ".join(words[i:i + max_words]))
        elif curr_len + w_len > max_words:
            if curr:
                result.append(" ".join(curr))
            curr = [sc]
            curr_len = w_len
        else:
            curr.append(sc)
            curr_len += w_len
    if curr:
        result.append(" ".join(curr))
    return result or [text]


def split_sentences(text: str) -> List[str]:
    """智能句子切分：识别缩写、段落号、公式，避免误断句。"""
    if not text or not text.strip():
        return []

    # 规范化异常连缀标点 (如打字机 OCR 残留的 ., 或 ,.)
    cleaned_text = re.sub(r"[\.,]{2,}", ".", text.strip())

    # 按照句子终结符（. ! ?）后跟空格与大写字母/数字切分
    raw_splits = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\(])", cleaned_text)
    sentences = []
    buffer = []

    for chunk in raw_splits:
        buffer.append(chunk)
        # 检查是否以已知缩写结尾
        words = chunk.split()
        last_word = words[-1].lower() if words else ""
        if last_word in _ABBREVIATIONS:
            continue
        # 检查单字母缩写如 A. 或 J. (排除工程温度单位如 1210°F. 或 100°C.)
        if re.search(r"\b[A-Za-z]\.$", chunk) and not re.search(r"[°\d][FCK]\.$", chunk):
            continue
        # 检查孤立序号/编号前缀（如 35. 或 1. 或 4.10 或 49-50.），仅当其位于句首时保留在 buffer 等待正文，绝不切断为独立句子
        if len(buffer) == 1 and re.match(r"^(\*+\s*)?(\d+([\.\,\-]\d+)*[\.\,:]|\d+\s*[\-\–]\s*|\([a-zA-Z0-9]+\)|\[\d+\]|[A-Za-z0-9]{1,4}[\.\,])\s*$", chunk.strip()):
            continue
        sentences.append(" ".join(buffer))
        buffer = []

    if buffer:
        if sentences:
            sentences[-1] += " " + " ".join(buffer)
        else:
            sentences.append(" ".join(buffer))

    # 对超长无标点句子进行次级拆分，防止超出模型位置编码上限 (512 tokens)
    final_sentences = []
    for s in sentences:
        if len(s.split()) > 50:
            final_sentences.extend(chunk_long_text(s, max_words=50))
        else:
            final_sentences.append(s)

    return final_sentences


@dataclass
class TranslationConfig:
    model_dir: Path
    batch_size: int = 32
    beam_size: int = 4
    compute_type: str = "int8"
    bilingual: bool = False
    glossary: List[Tuple[str, str]] = field(default_factory=lambda: list(_DEFAULT_GLOSSARY))

    def load_glossary_file(self, glossary_path: Path):
        """从项目 GLOSSARY.md 加载术语表规则。"""
        if not glossary_path.is_file():
            return
        content = glossary_path.read_text(encoding="utf-8", errors="replace")
        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith("|---"):
                continue
            cols = [c.strip() for c in line.split("|")[1:-1]]
            if len(cols) >= 2 and cols[0] and cols[1] and cols[0] != "English":
                en_term = re.sub(r"\(.*?\)", "", cols[0]).strip()
                zh_term = re.sub(r"\(.*?\)", "", cols[1]).strip()
                if en_term and zh_term and "/" not in zh_term:
                    self.glossary.append((en_term, zh_term))


class TranslationEngine:
    """CTranslate2 本地推理翻译引擎封装。"""

    def __init__(self, model_dir: Path, compute_type: str = "int8"):
        self.model_dir = Path(model_dir)
        self.compute_type = compute_type
        self._translator = None
        self._sp_source = None
        self._sp_target = None
        self._cache: Dict[str, str] = {}
        self._loaded = False

    def is_available(self) -> Tuple[bool, str]:
        """检查翻译模型与依赖库是否就绪。"""
        if importlib.util.find_spec("ctranslate2") is None:
            return False, "未安装 ctranslate2 Python 库"

        if importlib.util.find_spec("sentencepiece") is None:
            return False, "未安装 sentencepiece Python 库"

        if not self.model_dir.is_dir():
            return False, "翻译模型目录不存在：%s" % self.model_dir

        required_files = ["model.bin", "source.spm", "target.spm"]
        for f in required_files:
            if not (self.model_dir / f).is_file():
                return False, "缺少翻译模型文件：%s" % (self.model_dir / f)

        return True, "翻译引擎就绪（CTranslate2 + %s）" % self.model_dir.name

    def load(self):
        """载入模型和分词器。"""
        if self._loaded:
            return

        ok, reason = self.is_available()
        if not ok:
            raise RuntimeError(reason)

        import ctranslate2
        import sentencepiece as spm

        self._sp_source = spm.SentencePieceProcessor()
        self._sp_source.load(str(self.model_dir / "source.spm"))

        self._sp_target = spm.SentencePieceProcessor()
        self._sp_target.load(str(self.model_dir / "target.spm"))

        # 使用 int8 极速 CPU 推理
        self._translator = ctranslate2.Translator(
            str(self.model_dir),
            compute_type=self.compute_type,
        )
        self._loaded = True

    def translate_sentences(
        self,
        sentences: List[str],
        batch_size: int = 32,
        beam_size: int = 4,
    ) -> List[str]:
        """批量翻译句子列表，使用内存缓存规避重复句翻译，真正实现 O(N) 批处理。"""
        if not sentences:
            return []

        self.load()

        results = [""] * len(sentences)
        to_translate_indices: List[int] = []
        to_translate_sents: List[str] = []

        # 1. 过滤空句并检查缓存
        for idx, s in enumerate(sentences):
            trimmed = s.strip()
            if not trimmed:
                results[idx] = s
                continue
            if trimmed in self._cache:
                results[idx] = self._cache[trimmed]
            else:
                to_translate_indices.append(idx)
                to_translate_sents.append(trimmed)

        # 2. 对未缓存的句子切分 batch 并执行推理（外层批处理，严禁在句子循环内部重复触发）
        if to_translate_sents:
            actual_batch_size = max(1, batch_size)
            for chunk_start in range(0, len(to_translate_sents), actual_batch_size):
                chunk_sents = to_translate_sents[chunk_start : chunk_start + actual_batch_size]
                chunk_indices = to_translate_indices[chunk_start : chunk_start + actual_batch_size]

                batch_tokens = []
                for s in chunk_sents:
                    toks = self._sp_source.encode(s, out_type=str)
                    if len(toks) > 480:
                        toks = toks[:480]
                    batch_tokens.append(toks + ["</s>"])

                ct2_results = self._translator.translate_batch(
                    batch_tokens,
                    batch_type="examples",
                    max_batch_size=actual_batch_size,
                    beam_size=beam_size,
                    repetition_penalty=1.15,
                    no_repeat_ngram_size=3,
                )

                for orig_text, res, res_idx in zip(chunk_sents, ct2_results, chunk_indices):
                    hyp_tokens = [
                        t for t in res.hypotheses[0]
                        if t not in {"<s>", "</s>", "<pad>", "<unk>"}
                    ]
                    decoded = self._sp_target.decode(hyp_tokens)
                    normalized = normalize_chinese_text(decoded)
                    self._cache[orig_text] = normalized
                    results[res_idx] = normalized

        return results


class MarkdownDocumentTranslator:
    """结构化 Markdown 文档翻译器。

    精确识别代码块、数学公式、表格、标题、列表与内联元素，
    全篇提取句子进行批量并行翻译，确保技术符号与原始缩进完全保真。
    """

    _table_short_circuit_enabled: bool = True

    def __init__(self, engine: TranslationEngine, config: TranslationConfig):
        self.engine = engine
        self.config = config

    def _apply_glossary(self, text: str) -> str:
        """应用术语表强制规范（包含中西文边界、连字符容错与复数兼容）。"""
        # 1. 英文术语匹配（长度倒序优先长词组）
        en_glossary = [
            (pat, rep) for pat, rep in self.config.glossary
            if re.search(r"[a-zA-Z]", pat)
        ]
        en_glossary.sort(key=lambda x: len(x[0]), reverse=True)
        for en_term, zh_target in en_glossary:
            core = en_term.strip(r"\b")
            term_pattern = re.sub(r"(\\?[\s\-])+", lambda m: r"[-\s]+", re.escape(core))
            p = rf"(?i)(?:\b|(?<=[\u4e00-\u9fa5])){term_pattern}(?:s|es)?(?:\b|(?=[\u4e00-\u9fa5]))"
            text = re.sub(p, zh_target, text)

        # 2. 中文规范与表头映射
        for pattern, replacement in self.config.glossary:
            if not re.search(r"[a-zA-Z]", pattern):
                text = text.replace(pattern, replacement)

        return text

    def _mask_sentence(
        self,
        sentence: str,
        counter_start: int = 0,
    ) -> Tuple[str, Dict[str, str], int]:
        """提取句中所有需要保护的结构化标记为无歧义安全占位符 XPH{counter}X。

        严格两阶段隔离保护：
        阶段 A (Step A): 提取并隔离 HTML、图片、数学公式 ($$...$$, $...$)、行内代码 (`...`)、
                         管道符标记 (XPH_PIPE_X) 与链接，确保编程代码与数学公式不被术语篡改。
        阶段 B (Step B): 针对剩余文本匹配英文核工程/MSR领域专有术语 (长词优先 + 连字符容错)，
                         将其置换为 XPH{counter}X 占位符。
        """
        if not sentence.strip():
            return sentence, {}, counter_start

        placeholders: Dict[str, str] = {}
        counter = counter_start

        def stash(token: str) -> str:
            nonlocal counter
            tag = f"XPH{counter}X"
            placeholders[tag] = token
            counter += 1
            return tag

        text = sentence

        # ==========================================
        # 阶段 A (Step A): 结构、公式、行内代码与链接隔离
        # ==========================================

        # 1. 保护原始 HTML 标签（如 <script>alert(1)</script> 或 <div>）
        text = re.sub(r"(</?[a-zA-Z][^>]*>)", lambda m: stash(m.group(0)), text)

        # 2. 保护图片 Markdown：![alt](url)，支持 URL 内嵌套括号
        img_pattern = r"!\[([^\]]*)\]\(((?:[^\s()]+|\([^\s()]*\))+)(?:\s+[\"\']([^\"]*)[\"\'])?\)"
        text = re.sub(img_pattern, lambda m: stash(m.group(0)), text)

        # 3. 保护行内代码：`...` (严格优先于术语与公式，杜绝 `scram` 被篡改)
        text = re.sub(r"(`[^`\n]+?`)", lambda m: stash(m.group(0)), text)

        # 4. 保护数学公式：$$...$$ 与 $...$
        text = re.sub(
            r"(\$\$[\s\S]*?\$\$|\$(?!\s)[^\$\n]+?(?<!\s)\$(?!\d))",
            lambda m: stash(m.group(0)),
            text,
        )

        # 5. 保护表格转义管道符标记 XPH_PIPE_X
        if "XPH_PIPE_X" in text:
            text = re.sub(r"XPH_PIPE_X", lambda m: stash(r"\|"), text)

        # 6. 保护超链接 URL，翻译链接文本，安全审查危险 URL scheme
        link_pattern = r"\[([^\]]+)\]\(((?:[^\s()]+|\([^\s()]*\))+)(?:\s+[\"\']([^\"]*)[\"\'])?\)"

        def link_repl(match):
            link_text = match.group(1)
            raw_url = match.group(2)
            safe_url = _safe_link_url(raw_url) or "#"
            # 若链接文本纯为符号数字，原样保留
            if not re.search(r"[a-zA-Z]", link_text):
                return stash(f"[{link_text}]({safe_url})")
            # 翻译链接文本
            tr_link_list = self.engine.translate_sentences(
                [link_text],
                batch_size=self.config.batch_size,
                beam_size=self.config.beam_size,
            )
            tr_text = tr_link_list[0] if tr_link_list else link_text
            tr_text = re.sub(r"[。.]+$", "", tr_text.strip())
            return stash(f"[{tr_text}]({safe_url})")

        text = re.sub(link_pattern, link_repl, text)

        # ==========================================
        # 阶段 B (Step B): 英文专业术语前置匹配保护
        # ==========================================
        en_glossary = [
            (pat, rep) for pat, rep in self.config.glossary
            if re.search(r"[a-zA-Z]", pat) and not pat.startswith(r"\b")
        ]
        # 长度倒序贪婪优先匹配长词组
        en_glossary.sort(key=lambda x: len(x[0]), reverse=True)
        for en_term, zh_target in en_glossary:
            # 连字符与空白容错匹配：如 fuel-pump bowl 匹配 fuel pump bowl / fuel-pump-bowl
            term_pattern = re.sub(r"(\\?[\s\-])+", lambda m: r"[-\s]+", re.escape(en_term))
            p = rf"(?i)(?:\b|(?<=[\u4e00-\u9fa5])){term_pattern}(?:s|es)?(?:\b|(?=[\u4e00-\u9fa5]))"
            text = re.sub(p, lambda m, z=zh_target: stash(z), text)

        return text, placeholders, counter

    def _restore_sentence(self, translated_text: str, placeholders: Dict[str, str]) -> str:
        """还原占位符并应用排版规范与术语表。"""
        res = translated_text
        # 1. 应用中文术语表与标点规范
        res = normalize_chinese_text(res)
        res = self._apply_glossary(res)

        # 2. 还原占位符（支持 XPH{i}X、XPho{i}X 与 Z{i}Z，数字倒序优先匹配避免前缀遮挡）
        def _tag_sort_key(item):
            tag_str = item[0]
            m_num = re.search(r"\d+", tag_str)
            return (int(m_num.group(0)) if m_num else 0), len(tag_str)

        sorted_phs = sorted(placeholders.items(), key=_tag_sort_key, reverse=True)
        for tag, val in sorted_phs:
            m = re.match(r"^(?:XPH|Z)(\d+)X?$", tag, re.I)
            if m:
                num = m.group(1)
                pat = rf"(?i)(?:\bX\s+)?(?:XP[A-Za-z]*?|Z){num}X?(?:\s+X\b)?"
            else:
                pat = rf"(?i){re.escape(tag)}"
            res = re.sub(pat, lambda m, v=val: v, res)

        # 3. 清理 NMT 常见的无上下文对齐幻觉残余
        res = re.sub(r"排会[会议总会排拉]*", "", res)
        res = re.sub(r"联[年月日联]{2,}", "", res)
        res = re.sub(r"天然气气体", "天然气", res)
        res = re.sub(r"总计共计", "总计", res)

        # 4. 后置排版清理（确保公式、代码与中文标点间无多余空格）
        res = normalize_chinese_text(res)
        return res.strip()

    def _translate_sentence_with_placeholders(self, sentence: str) -> str:
        """带安全占位符保护的单句翻译（向后兼容）。"""
        if not sentence.strip():
            return sentence

        cleaned_sentence = clean_historical_ocr_text(sentence)
        masked, placeholders, _ = self._mask_sentence(cleaned_sentence)
        translated_list = self.engine.translate_sentences(
            [masked],
            batch_size=self.config.batch_size,
            beam_size=self.config.beam_size,
        )
        translated = translated_list[0] if translated_list else masked
        return self._restore_sentence(translated, placeholders)

    def translate_paragraph(self, paragraph: str) -> str:
        """翻译普通段落文本。"""
        if not paragraph.strip():
            return paragraph

        cleaned_para = clean_historical_ocr_text(paragraph)
        sentences = split_sentences(cleaned_para)
        if not sentences:
            return paragraph

        masked_sents = []
        all_placeholders = []
        nmt_indices = []
        nmt_masked = []
        counter = 0

        for idx, s in enumerate(sentences):
            masked, phs, counter = self._mask_sentence(s, counter_start=counter)
            masked_sents.append(masked)
            all_placeholders.append(phs)
            clean_text = re.sub(r"(?i)\b(?:XPH|Z)\d+X?\b|(?:XPH|Z)\d+X?", "", masked).strip()
            if re.search(r"[a-zA-Z]", clean_text):
                nmt_indices.append(idx)
                nmt_masked.append(masked)

        translated_sents = list(masked_sents)
        if nmt_masked:
            tr_list = self.engine.translate_sentences(
                nmt_masked,
                batch_size=self.config.batch_size,
                beam_size=self.config.beam_size,
            )
            for idx, tr in zip(nmt_indices, tr_list):
                translated_sents[idx] = tr

        restored_sents = [
            self._restore_sentence(tr, phs)
            for tr, phs in zip(translated_sents, all_placeholders)
        ]
        return "".join(restored_sents)

    def translate_table(self, table_lines: List[str]) -> List[str]:
        r"""翻译 Markdown 表格，消除停用词对齐幻觉，守恒基准列数 N，保护转义管道符 \|。

        四阶分流规则：
        1. 纯符号 / 数字 / 公式 / 空单元格：直接保留。
        2. 孤立停用词 / 虚词 (TABLE_STOPWORDS_MAP)：字典确定性短路映射，绝不调用 NMT。
        3. 领域专有术语：通过 _mask_sentence 占位，无剩余英文时直接还原。
        4. 完整短语 / 句子：送入 CTranslate2 进行批处理并行神经翻译。
        """
        if not table_lines:
            return []

        # 1. 探测表头基准列数 N
        target_cols = 0
        for line in table_lines:
            stripped = line.strip()
            if not stripped.startswith("|"):
                continue
            if re.match(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$", stripped):
                continue
            # 保护转义管道符后计算列数
            protected = re.sub(r"\\\|", "XPH_PIPE_X", stripped)
            parts = [c.strip() for c in protected.split("|")]
            if stripped.startswith("|"):
                parts = parts[1:]
            if stripped.endswith("|") and parts:
                parts = parts[:-1]
            if len(parts) > 0:
                target_cols = len(parts)
                break

        out_lines = []
        parsed_rows = []
        to_translate_cells = []
        cell_coords = []  # (row_idx, col_idx)

        # 2. 逐行解析与列数 N 守恒规整
        for row_idx, line in enumerate(table_lines):
            stripped = line.strip()
            # 2.1 分隔线行格式化为 N 列对齐
            if re.match(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$", stripped):
                if target_cols > 0:
                    delim_cells = [c.strip() for c in stripped.split("|")]
                    if stripped.startswith("|"):
                        delim_cells = delim_cells[1:]
                    if stripped.endswith("|") and delim_cells:
                        delim_cells = delim_cells[:-1]
                    delim_cells = [c for c in delim_cells if c]
                    if len(delim_cells) == target_cols:
                        parsed_rows.append(("delim", stripped))
                    else:
                        if len(delim_cells) < target_cols:
                            delim_cells.extend(["---"] * (target_cols - len(delim_cells)))
                        elif len(delim_cells) > target_cols:
                            delim_cells = delim_cells[:target_cols]
                        parsed_rows.append(("delim", "| " + " | ".join(delim_cells) + " |"))
                else:
                    parsed_rows.append(("delim", stripped))
                continue

            if not stripped.startswith("|"):
                parsed_rows.append(("raw", line))
                continue

            # 2.2 数据行：隔离 \| 并按 | 分割单元格
            pipe_protected = re.sub(r"\\\|", "XPH_PIPE_X", stripped)
            raw_cells = [c.strip() for c in pipe_protected.split("|")]
            if stripped.startswith("|"):
                raw_cells = raw_cells[1:]
            if stripped.endswith("|") and raw_cells:
                raw_cells = raw_cells[:-1]

            # 列数守恒约束：不足补齐，超出合并至末尾
            if target_cols > 0:
                if len(raw_cells) < target_cols:
                    raw_cells.extend([""] * (target_cols - len(raw_cells)))
                elif len(raw_cells) > target_cols:
                    merged_last = " ".join(c for c in raw_cells[target_cols - 1:] if c)
                    raw_cells = raw_cells[:target_cols - 1] + [merged_last]

            row_cells = []
            for col_idx, cell in enumerate(raw_cells):
                cleaned_c = clean_historical_ocr_text(cell)
                row_cells.append(cleaned_c)
                if cleaned_c:
                    to_translate_cells.append(cleaned_c)
                    cell_coords.append((row_idx, col_idx))
            parsed_rows.append(("row", row_cells))

        # 3. 单元格四阶分流与翻译处理
        translated_cell_map: Dict[Tuple[int, int], str] = {}
        if to_translate_cells:
            counter = 0
            nmt_cells = []
            for (r_idx, c_idx), ct in zip(cell_coords, to_translate_cells):
                trimmed = ct.strip()
                lower = trimmed.lower()

                # 阶 1: 纯符号 / 数字 / 无字母 -> 原样保留
                if not re.search(r"[a-zA-Z]", trimmed):
                    translated_cell_map[(r_idx, c_idx)] = trimmed
                    continue

                # 阶 2: 停用词 / 虚词短路映射 (TABLE_STOPWORDS_MAP)
                if trimmed in TABLE_STOPWORDS_MAP:
                    translated_cell_map[(r_idx, c_idx)] = TABLE_STOPWORDS_MAP[trimmed]
                    continue
                if lower in TABLE_STOPWORDS_MAP:
                    translated_cell_map[(r_idx, c_idx)] = TABLE_STOPWORDS_MAP[lower]
                    continue
                if len(trimmed) <= 3 and lower in _PROSE_STOPWORDS:
                    translated_cell_map[(r_idx, c_idx)] = TABLE_STOPWORDS_MAP.get(lower, "")
                    continue

                # 阶 2.5: 短路常见停用词短语（如 of the / in the）
                phrase_clean = re.sub(r"[,\.:;]+$", "", lower).strip()
                if phrase_clean in TABLE_STOPWORDS_MAP:
                    translated_cell_map[(r_idx, c_idx)] = TABLE_STOPWORDS_MAP[phrase_clean]
                    continue
                phrase_words = [w.strip(".,;:()") for w in lower.split() if w.strip(".,;:()")]
                if phrase_words and all(w in TABLE_STOPWORDS_MAP for w in phrase_words):
                    translated_cell_map[(r_idx, c_idx)] = "".join(TABLE_STOPWORDS_MAP.get(w, "") for w in phrase_words)
                    continue

                # 阶 3: 领域专有术语占位与前置提取
                masked, phs, counter = self._mask_sentence(trimmed, counter_start=counter)
                clean_text = re.sub(r"(?i)\b(?:XPH|Z)\d+X?\b|(?:XPH|Z)\d+X?", "", masked).strip()
                if not re.search(r"[a-zA-Z]", clean_text):
                    restored = self._restore_sentence(masked, phs)
                    translated_cell_map[(r_idx, c_idx)] = re.sub(r"[。.]+$", "", restored.strip())
                else:
                    # 阶 4: 完整短语 / 句子送入 CTranslate2 NMT 推理
                    nmt_cells.append(((r_idx, c_idx), masked, phs))

            if nmt_cells:
                tr_results = self.engine.translate_sentences(
                    [item[1] for item in nmt_cells],
                    batch_size=self.config.batch_size,
                    beam_size=self.config.beam_size,
                )
                for ((r_idx, c_idx), _masked, phs), tr in zip(nmt_cells, tr_results):
                    restored = self._restore_sentence(tr, phs)
                    restored = re.sub(r"[。.]+$", "", restored.strip())
                    for h in ["排会会议和排会总会会排排联合国经费分摊比额表排排拉会的排排", "排会会议", "排会总会", "联联年月日", "联年月日", "天然气气体", "总计共计"]:
                        restored = restored.replace(h, "")
                    translated_cell_map[(r_idx, c_idx)] = restored

        # 4. 重建表格行，还原转义管道符并强制转义裸管道符
        for row_idx, (r_type, r_data) in enumerate(parsed_rows):
            if r_type in {"delim", "raw"}:
                out_lines.append(r_data)
            else:
                new_cells = []
                for col_idx, orig_c in enumerate(r_data):
                    cell_text = translated_cell_map.get((row_idx, col_idx), orig_c)
                    # 还原 XPH_PIPE_X -> \|
                    cell_text = cell_text.replace("XPH_PIPE_X", r"\|")
                    # 单元格内若出现未转义的单个 |，转义为 \|，防止列数破坏
                    cell_text = re.sub(r"(?<!\\)\|", r"\|", cell_text)
                    new_cells.append(cell_text.strip())
                out_lines.append("| " + " | ".join(new_cells) + " |")

        return out_lines

    def translate_document(self, markdown_text: str, bilingual: bool = False) -> str:
        """翻译完整 Markdown 文档，支持纯中文与中英对齐双语模式。

        结构感知解析：
        - 代码块（```或~~~）：完整保留所有行与缩进，不插入多余空行。
        - 数学公式块（$$...$$）：完整保留多行 LaTeX 格式与对齐符号。
        - 标题、表格、引用、列表、段落：批量并行翻译并排版。
        """
        if not markdown_text or not markdown_text.strip():
            return ""

        lines = markdown_text.splitlines()
        total_lines = len(lines)
        index = 0

        blocks: List[Tuple[str, any]] = []

        while index < total_lines:
            line = lines[index]
            stripped = line.strip()

            # 1. 空行、水平分割线、HTML 注释
            if not stripped or re.match(r"^\s*(\*{3,}|-{3,}|_{3,})\s*$", stripped) or stripped.startswith("<!--"):
                blocks.append(("raw", line))
                index += 1
                continue

            # 2. 代码块（原子收集整个块，精准判定真实代码与打字机正文）
            fence_match = re.match(r"^(\s*)(`{3,}|~{3,})(.*)$", line)
            if fence_match:
                marker = fence_match.group(2)
                block_lines = [line]
                index += 1
                while index < total_lines:
                    cur = lines[index]
                    block_lines.append(cur)
                    index += 1
                    if re.match(r"^(\s*)" + re.escape(marker[0]) + rf"{{{len(marker)},}}\s*$", cur.strip()):
                        break

                lang = fence_match.group(3).strip()
                if len(block_lines) >= 2 and re.match(r"^(\s*)" + re.escape(marker[0]) + rf"{{{len(marker)},}}\s*$", block_lines[-1].strip()):
                    content = "\n".join(block_lines[1:-1])
                else:
                    content = "\n".join(block_lines[1:])

                if classify_code_block(lang, content):
                    blocks.append(("code", "\n".join(block_lines)))
                else:
                    # 打字机等宽正文 / 扫描文本块：解除围栏并进行 OCR 清洗与段落分块
                    cleaned_content = clean_historical_ocr_text(content)
                    raw_paras = [p.strip() for p in re.split(r"\n\s*\n", cleaned_content) if p.strip()]
                    for p in raw_paras:
                        sub_lines = p.splitlines()
                        curr_lines = []
                        for sl in sub_lines:
                            sl_str = sl.strip()
                            if curr_lines and re.match(r"^(?:[A-Z0-9]\.|\d+\.[\d\w]+|[L4]\.[\d\w]+)\s+[A-Z]", sl_str):
                                blocks.append(("para", " ".join(curr_lines)))
                                curr_lines = [sl_str]
                            else:
                                curr_lines.append(sl_str)
                        if curr_lines:
                            blocks.append(("para", " ".join(curr_lines)))
                continue

            # 3. 独立数学公式块 $$...$$
            if stripped.startswith("$$"):
                block_lines = [line]
                index += 1
                if not (stripped.endswith("$$") and len(stripped) > 2):
                    while index < total_lines:
                        cur = lines[index]
                        block_lines.append(cur)
                        index += 1
                        if cur.strip().endswith("$$"):
                            break
                blocks.append(("math", "\n".join(block_lines)))
                continue

            # 4. 标题行 (# Heading)
            heading_match = re.match(r"^\s{0,3}(#{1,6}\s+)(.*?)(?:\s+(\{#[^}]+\}))?$", line)
            if heading_match:
                prefix = heading_match.group(1)
                title = heading_match.group(2)
                anchor = f" {heading_match.group(3)}" if heading_match.group(3) else ""
                blocks.append(("heading", (prefix, title, anchor)))
                index += 1
                continue

            # 5. 表格块检测
            if stripped.startswith("|") and index + 1 < total_lines and re.match(r"^\|?(\s*:?-{3,}:?\s*\|)", lines[index + 1].strip()):
                tbl_lines = []
                while index < total_lines and lines[index].strip().startswith("|"):
                    tbl_lines.append(lines[index].strip())
                    index += 1
                blocks.append(("table", tbl_lines))
                continue

            # 6. 列表项与连续行
            list_match = re.match(r"^(\s*([-+*]|\d+[.)])\s+)(.+)$", line)
            if list_match:
                items = []
                while index < total_lines:
                    cur_line = lines[index]
                    cur_match = re.match(r"^(\s*([-+*]|\d+[.)])\s+)(.+)$", cur_line)
                    if cur_match:
                        items.append((cur_match.group(1), cur_match.group(3)))
                        index += 1
                    elif items and (cur_line.startswith("    ") or cur_line.startswith("\t") or (
                        cur_line.strip() and not re.match(r"^(#{1,6}|`{3,}|~{3,}|\$\$|\||>)\s*", cur_line.strip())
                    )):
                        pfx, prev_txt = items[-1]
                        items[-1] = (pfx, prev_txt + " " + cur_line.strip())
                        index += 1
                    else:
                        break
                blocks.append(("list", items))
                continue

            # 7. 连续引用块 (> quote)
            if stripped.startswith(">"):
                quote_lines = []
                while index < total_lines and lines[index].strip().startswith(">"):
                    q_text = re.sub(r"^\s*>\s?", "", lines[index])
                    quote_lines.append(q_text)
                    index += 1
                blocks.append(("quote", "\n".join(quote_lines)))
                continue

            # 8. 普通段落聚合
            paragraph_lines = []
            while (
                index < total_lines
                and lines[index].strip()
                and not re.match(r"^\s{0,3}#{1,6}\s+", lines[index])
                and not re.match(r"^(\s*)(`{3,}|~{3,})", lines[index])
                and not lines[index].strip().startswith("$$")
                and not (lines[index].strip().startswith("|") and index + 1 < total_lines and re.match(r"^\|?(\s*:?-{3,}:?\s*\|)", lines[index + 1].strip()))
                and not re.match(r"^(\s*([-+*]|\d+[.)])\s+)", lines[index])
                and not lines[index].strip().startswith(">")
                and not re.match(r"^\s*(\*{3,}|-{3,}|_{3,})\s*$", lines[index].strip())
                and not lines[index].strip().startswith("<!--")
            ):
                paragraph_lines.append(lines[index].strip())
                index += 1

            if not paragraph_lines:
                paragraph_lines.append(lines[index].strip())
                index += 1

            blocks.append(("para", " ".join(paragraph_lines)))

        # 提取并批量并行翻译所有文本
        translatable_items = []  # (b_idx, item_type, masked_text, placeholders)
        counter = 0

        for b_idx, (b_type, b_data) in enumerate(blocks):
            if b_type == "heading":
                prefix, title, anchor = b_data
                cleaned_title = clean_historical_ocr_text(title)
                masked, phs, counter = self._mask_sentence(cleaned_title, counter_start=counter)
                translatable_items.append((b_idx, "heading", masked, phs))
            elif b_type == "para":
                cleaned_para = clean_historical_ocr_text(b_data)
                sents = split_sentences(cleaned_para)
                for s_idx, s in enumerate(sents):
                    masked, phs, counter = self._mask_sentence(s, counter_start=counter)
                    translatable_items.append((b_idx, ("para", s_idx), masked, phs))
            elif b_type == "quote":
                cleaned_quote = clean_historical_ocr_text(b_data)
                sents = split_sentences(cleaned_quote)
                for s_idx, s in enumerate(sents):
                    masked, phs, counter = self._mask_sentence(s, counter_start=counter)
                    translatable_items.append((b_idx, ("quote", s_idx), masked, phs))
            elif b_type == "list":
                for item_idx, (pfx, itxt) in enumerate(b_data):
                    cleaned_itxt = clean_historical_ocr_text(itxt)
                    sents = split_sentences(cleaned_itxt)
                    for s_idx, s in enumerate(sents):
                        masked, phs, counter = self._mask_sentence(s, counter_start=counter)
                        translatable_items.append((b_idx, ("list", item_idx, s_idx), masked, phs))

        # 区分需要 NMT 推理的文本与纯占位符/非英文文本
        nmt_items = []
        translated_results: Dict[Tuple[int, any], str] = {}

        for b_idx, item_type, masked, phs in translatable_items:
            clean_text = re.sub(r"(?i)\b(?:XPH|Z)\d+X?\b|(?:XPH|Z)\d+X?", "", masked).strip()
            if not re.search(r"[a-zA-Z]", clean_text):
                # 纯图片、公式、符号或数字，无需 NMT 模型推理，直接还原占位符规避结巴数字
                restored = self._restore_sentence(masked, phs)
                if item_type == "heading":
                    restored = re.sub(r"[。.]+$", "", restored.strip())
                translated_results[(b_idx, item_type)] = restored
            else:
                nmt_items.append((b_idx, item_type, masked, phs))

        if nmt_items:
            all_masked = [item[2] for item in nmt_items]
            all_translated = self.engine.translate_sentences(
                all_masked,
                batch_size=self.config.batch_size,
                beam_size=self.config.beam_size,
            )
            for (b_idx, item_type, _masked, phs), tr in zip(nmt_items, all_translated):
                restored = self._restore_sentence(tr, phs)
                if item_type == "heading":
                    restored = re.sub(r"[。.]+$", "", restored.strip())
                translated_results[(b_idx, item_type)] = restored

        # 文档重组输出
        output_blocks: List[str] = []

        for b_idx, (b_type, b_data) in enumerate(blocks):
            if b_type == "raw":
                output_blocks.append(b_data)
            elif b_type == "code":
                output_blocks.append(b_data)
            elif b_type == "math":
                output_blocks.append(b_data)
            elif b_type == "heading":
                prefix, title, anchor = b_data
                cleaned_title = clean_historical_ocr_text(title)
                tr_title = translated_results.get((b_idx, "heading"), cleaned_title)
                if bilingual:
                    output_blocks.append(f"{prefix}{cleaned_title} / {tr_title}{anchor}")
                else:
                    output_blocks.append(f"{prefix}{tr_title}{anchor}")
            elif b_type == "table":
                tr_table_lines = self.translate_table(b_data)
                if bilingual:
                    output_blocks.append("\n".join(b_data) + "\n\n> **【中文译表】**\n" + "\n".join(tr_table_lines))
                else:
                    output_blocks.append("\n".join(tr_table_lines))
            elif b_type == "quote":
                cleaned_quote = clean_historical_ocr_text(b_data)
                sents = split_sentences(cleaned_quote)
                tr_sents = [translated_results.get((b_idx, ("quote", s_idx)), s) for s_idx, s in enumerate(sents)]
                tr_quote = "".join(tr_sents)
                if bilingual:
                    orig_quote = "\n".join(f"> {quote_line}" for quote_line in cleaned_quote.splitlines())
                    output_blocks.append(f"{orig_quote}\n>\n> *译文*：{tr_quote}")
                else:
                    output_blocks.append(f"> {tr_quote}")
            elif b_type == "list":
                item_lines = []
                for item_idx, (pfx, itxt) in enumerate(b_data):
                    cleaned_itxt = clean_historical_ocr_text(itxt)
                    sents = split_sentences(cleaned_itxt)
                    tr_sents = [translated_results.get((b_idx, ("list", item_idx, s_idx)), s) for s_idx, s in enumerate(sents)]
                    tr_item = "".join(tr_sents)
                    if bilingual:
                        item_lines.append(f"{pfx}{cleaned_itxt}\n{pfx}*译文*：{tr_item}")
                    else:
                        item_lines.append(f"{pfx}{tr_item}")
                output_blocks.append("\n".join(item_lines))
            elif b_type == "para":
                cleaned_para = clean_historical_ocr_text(b_data)
                sents = split_sentences(cleaned_para)
                tr_sents = [translated_results.get((b_idx, ("para", s_idx)), s) for s_idx, s in enumerate(sents)]
                tr_para = "".join(tr_sents)
                if bilingual:
                    output_blocks.append(f"{cleaned_para}\n\n> **译文**：{tr_para}")
                else:
                    output_blocks.append(tr_para)

        # 规整段落间距（保留代码与数学块的原始缩进与格式）
        result_lines: List[str] = []
        for block in output_blocks:
            if not block.strip():
                continue
            result_lines.append(block.strip())

        return "\n\n".join(result_lines)


def translate_document_file(
    source_md: Path,
    output_md: Optional[Path] = None,
    output_html: Optional[Path] = None,
    model_dir: Optional[Path] = None,
    bilingual: bool = False,
    image_base_dir: Optional[Path] = None,
    batch_size: int = 32,
    beam_size: int = 4,
    compute_type: str = "int8",
    glossary_path: Optional[Path] = None,
) -> Tuple[Path, Optional[Path]]:
    """翻译 Markdown 文件并原子输出到目标路径。

    遵循 AGENTS.md 准则：
    - 临时文件以 .partial 命名，先完整写入。
    - 成功后原子更名（os.replace）至 outbox/。
    - 发生异常立即清理残留临时文件。
    - 纯本地确定性生成，不可信 HTML 转义，危险 URL 过滤。
    """
    source_md = Path(source_md).resolve()
    if not source_md.is_file():
        raise FileNotFoundError("源 Markdown 文件不存在：%s" % source_md)

    project_root = Path(__file__).resolve().parent.parent
    if model_dir is None:
        model_dir = project_root / "assets" / "models" / "translation"

    stem = source_md.stem
    clean_stem = re.sub(r"\.(zh|bilingual)$", "", stem)
    suffix = ".bilingual" if bilingual else ".zh"

    if output_md is None:
        output_md = source_md.parent / f"{clean_stem}{suffix}.md"
    if output_html is None:
        output_html = source_md.parent / f"{clean_stem}{suffix}.html"

    # 初始化配置
    config = TranslationConfig(
        model_dir=model_dir,
        batch_size=batch_size,
        beam_size=beam_size,
        bilingual=bilingual,
        compute_type=compute_type,
    )
    if glossary_path and glossary_path.is_file():
        config.load_glossary_file(glossary_path)

    engine = TranslationEngine(model_dir, compute_type=compute_type)
    doc_translator = MarkdownDocumentTranslator(engine, config)

    # 暂存临时文件
    temp_md = output_md.parent / f".{output_md.name}.partial"
    temp_html = output_html.parent / f".{output_html.name}.partial" if output_html else None

    # 清理残留
    temp_md.unlink(missing_ok=True)
    if temp_html:
        temp_html.unlink(missing_ok=True)

    published_files: List[Path] = []
    try:
        raw_markdown = source_md.read_text(encoding="utf-8", errors="replace")
        translated_md = doc_translator.translate_document(raw_markdown, bilingual=bilingual)

        temp_md.write_text(translated_md, encoding="utf-8")

        if temp_html:
            doc_title = f"{clean_stem} (中文精译版)" if not bilingual else f"{clean_stem} (中英对齐双语版)"
            rendered_html = render_markdown_document(
                translated_md,
                fallback_title=doc_title,
                source_filename=source_md.name,
                image_base_dir=image_base_dir or (source_md.parent / f"{clean_stem}_assets"),
            )
            temp_html.write_text(rendered_html, encoding="utf-8")

        # 原子更名发布
        os.replace(str(temp_md), str(output_md))
        published_files.append(output_md)

        if temp_html and output_html:
            os.replace(str(temp_html), str(output_html))
            published_files.append(output_html)

    except Exception:
        # 异常回滚清理
        temp_md.unlink(missing_ok=True)
        if temp_html:
            temp_html.unlink(missing_ok=True)
        for pub in published_files:
            try:
                pub.unlink(missing_ok=True)
            except OSError:
                pass
        raise

    return output_md, output_html


def scan_and_translate_outbox(
    outbox_dir: Path,
    model_dir: Optional[Path] = None,
    bilingual: bool = False,
    batch_size: int = 32,
    beam_size: int = 4,
) -> int:
    """扫描 outbox/，翻译所有尚未有中文译本的 .md 文件。"""
    outbox_dir = Path(outbox_dir).resolve()
    if not outbox_dir.is_dir():
        print(f"目录不存在：{outbox_dir}")
        return 0

    md_files = [
        f for f in sorted(outbox_dir.glob("*.md"))
        if not f.name.endswith(".zh.md") and not f.name.endswith(".bilingual.md")
    ]

    translated_count = 0
    for md_file in md_files:
        clean_stem = md_file.stem
        target_md = outbox_dir / f"{clean_stem}.zh.md"
        target_html = outbox_dir / f"{clean_stem}.zh.html"

        if target_md.is_file() and target_html.is_file():
            continue

        print(f"正在翻译文献：{md_file.name} ...")
        t0 = time.time()
        try:
            assets_dir = outbox_dir / f"{clean_stem}_assets"
            translate_document_file(
                source_md=md_file,
                output_md=target_md,
                output_html=target_html,
                model_dir=model_dir,
                bilingual=bilingual,
                image_base_dir=assets_dir if assets_dir.is_dir() else None,
                batch_size=batch_size,
                beam_size=beam_size,
            )
            elapsed = time.time() - t0
            print(f"  ✓ 成功完成：{target_html.name}（耗时 {elapsed:.1f} 秒）")
            translated_count += 1
        except Exception as exc:
            print(f"  ✗ 翻译失败 {md_file.name}：{exc}")

    return translated_count


def interactive_cli(root: Path):
    """macOS .command 双击启动的交互控制台。"""
    print("=" * 64)
    print("      LiteParse 本地离线科技文献翻译引擎 (方案二)")
    print("  完全离线 · 免装 Ollama · 轻量级 CTranslate2 · 极致速度")
    print("=" * 64)

    outbox = root / "outbox"
    model_dir = root / "assets" / "models" / "translation"

    engine = TranslationEngine(model_dir)
    ok, status = engine.is_available()
    print(f"引擎状态：{status}")
    if not ok:
        print("\n请检查模型目录：assets/models/translation/")
        return 1

    print(f"\n检查识别成果箱：{outbox}")
    candidates = [
        f for f in sorted(outbox.glob("*.md"))
        if not f.name.endswith(".zh.md") and not f.name.endswith(".bilingual.md")
    ]

    if not candidates:
        print("当前 outbox/ 中没有待翻译的文献（全部已翻译或为空）。")
        print("您可以将 PDF 放入 inbox/ 等待自动识别后再次运行。")
        return 0

    print(f"发现 {len(candidates)} 篇待翻译文献：")
    for i, c in enumerate(candidates, 1):
        has_zh = (outbox / f"{c.stem}.zh.html").is_file()
        tag = " [已生成中文版]" if has_zh else " [未翻译]"
        print(f"  [{i}] {c.name}{tag}")

    print("\n请选择操作：")
    print("  [A] 翻译所有未翻译文献（默认纯中文版）")
    print("  [B] 翻译所有未翻译文献（对齐双语版）")
    print("  [1-%d] 指定单篇文献序号翻译" % len(candidates))
    print("  [Q] 退出")

    choice = input("\n请输入选项 (默认 A): ").strip() or "A"

    if choice.upper() == "Q":
        return 0

    if choice.upper() == "A":
        scan_and_translate_outbox(outbox, model_dir=model_dir, bilingual=False)
    elif choice.upper() == "B":
        scan_and_translate_outbox(outbox, model_dir=model_dir, bilingual=True)
    elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
        target = candidates[int(choice) - 1]
        print(f"正在翻译：{target.name} ...")
        t0 = time.time()
        translate_document_file(
            source_md=target,
            model_dir=model_dir,
            bilingual=False,
        )
        print(f"翻译完成，耗时 {time.time() - t0:.1f} 秒！")
    else:
        print("无效选项。")

    print("\n操作已完成。可前往 outbox/ 查看精译 HTML 与 Markdown。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="LiteParse 本地离线科技文献翻译器")
    parser.add_argument("--input", "-i", type=str, help="输入 Markdown 文件路径")
    parser.add_argument("--output-md", "-o", type=str, help="输出 Markdown 文件路径")
    parser.add_argument("--output-html", type=str, help="输出 HTML 文件路径")
    parser.add_argument("--model-dir", type=str, help="模型目录")
    parser.add_argument("--bilingual", action="store_true", help="输出对齐双语版")
    parser.add_argument("--batch-size", type=int, default=32, help="翻译批量大小")
    parser.add_argument("--beam-size", type=int, default=4, help="Beam search 大小")
    parser.add_argument("--scan-outbox", action="store_true", help="扫描 outbox/ 翻译所有未翻译文献")
    parser.add_argument("--check", action="store_true", help="检查翻译引擎可用性")
    parser.add_argument("--interactive", action="store_true", help="进入交互式终端")

    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent

    if args.check:
        model_dir = Path(args.model_dir) if args.model_dir else root / "assets" / "models" / "translation"
        engine = TranslationEngine(model_dir)
        ok, msg = engine.is_available()
        print(msg)
        return 0 if ok else 1

    if args.interactive:
        return interactive_cli(root)

    if args.scan_outbox:
        outbox = root / "outbox"
        model_dir = Path(args.model_dir) if args.model_dir else root / "assets" / "models" / "translation"
        count = scan_and_translate_outbox(
            outbox,
            model_dir=model_dir,
            bilingual=args.bilingual,
            batch_size=args.batch_size,
            beam_size=args.beam_size,
        )
        print(f"处理完成，共翻译 {count} 篇文献。")
        return 0

    if args.input:
        in_path = Path(args.input).resolve()
        out_md = Path(args.output_md).resolve() if args.output_md else None
        out_html = Path(args.output_html).resolve() if args.output_html else None
        model_dir = Path(args.model_dir) if args.model_dir else root / "assets" / "models" / "translation"

        print(f"正在翻译文献：{in_path.name} ...")
        t0 = time.time()
        md_res, html_res = translate_document_file(
            source_md=in_path,
            output_md=out_md,
            output_html=out_html,
            model_dir=model_dir,
            bilingual=args.bilingual,
            batch_size=args.batch_size,
            beam_size=args.beam_size,
        )
        print(f"✓ 翻译完成（耗时 {time.time() - t0:.1f} 秒）：\n  Markdown: {md_res}\n  HTML: {html_res}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
