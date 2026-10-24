#!/usr/bin/env python3
"""Shared test fixtures, authoritative catalogs, and helper utilities for E2E testing."""

from pathlib import Path
import re
from typing import Callable, Dict, List, Optional, Set, Tuple

# Project root and asset directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = PROJECT_ROOT / "assets" / "models" / "translation"
OUTBOX_DIR = PROJECT_ROOT / "outbox"
PROCESSED_DIR = PROJECT_ROOT / "processed"

# 30 Core Benchmark Nuclear Engineering / MSR Terms
# Format: (English Key, Standard Chinese Accepted Variants, Forbidden False Translations)
BENCHMARK_30_TERMS: List[Tuple[str, Set[str], Set[str]]] = [
    ("scram", {"停堆", "紧急停堆"}, {"螺旋藻", "倾斜", "碎裂", "争先恐后"}),
    ("scram test", {"停堆试验", "停堆测试", "紧急停堆试验"}, {"螺旋藻气候试验", "倾斜测试"}),
    ("scram trip", {"停堆跳闸", "停堆动作", "紧急停堆跳闸"}, {"滚动旅行旅费", "倾斜旅行"}),
    ("scram circuit", {"停堆电路", "紧急停堆回路", "停堆跳闸电路"}, {"碎裂电路", "螺旋藻回路"}),
    ("fuel drain tank", {"燃料排盐罐", "燃料排盐槽"}, {"排水池", "排油罐", "燃料坦克", "排气罐"}),
    ("drain tank", {"排盐罐", "排盐槽"}, {"排水池", "排水箱", "坦克", "排气罐"}),
    ("drain-tank cell", {"排盐罐舱", "排盐罐室"}, {"排气罐", "排污室", "电池"}),
    ("reactor cell", {"反应堆舱", "反应堆室"}, {"反应堆电池", "反应堆细胞"}),
    ("cell shield blocks", {"舱室屏蔽块", "反应堆舱屏蔽块"}, {"保护罩区块", "电池屏蔽"}),
    ("reactor vessel", {"反应堆容器", "反应堆压力容器", "反应堆压力壳"}, {"反应堆船舶", "船只", "飞船"}),
    ("fuel salt", {"燃料盐"}, {"软化盐", "燃料食盐", "燃料盐盐"}),
    ("coolant salt", {"冷却盐"}, {"冷却液食盐"}),
    ("flush salt", {"清洗盐", "冲洗盐"}, {"刷新盐", "冲水盐"}),
    ("cover gas", {"覆盖气体", "覆盖气", "保护气体"}, {"封面天然气", "盖气体", "封面气体"}),
    ("offgas", {"尾气", "离堆气体", "废气"}, {"沼气", "天然气气体", "脱气"}),
    ("ventilation stack", {"通风烟囱", "排气烟囱"}, {"堆叠", "堆栈", "通风书架"}),
    ("graphite moderator", {"石墨慢化剂"}, {"石墨游戏主持人", "石墨主持人", "石墨调节剂"}),
    ("control rod", {"控制棒"}, {"控制杆", "棍子", "棒杆"}),
    ("safety rod", {"安全棒"}, {"安全杆", "安全反应器", "安全棍"}),
    ("subcritical", {"次临界"}, {"亚临界值", "亚关键", "次关键"}),
    ("critical", {"临界"}, {"关键", "危急"}),
    ("reactivity", {"反应性"}, {"反应过度", "活性", "反应度"}),
    ("reactivity anomaly", {"反应性异常"}, {"活动异常点", "反应过度反常", "自由异常点"}),
    ("period trip", {"周期停堆保护", "周期跳闸", "周期停堆跳闸"}, {"时期旅行", "时段跳闸", "期间跳闸"}),
    ("thermal shield", {"热屏蔽", "热屏蔽层"}, {"热保护罩", "热护盾"}),
    ("vapor-condensing system", {"蒸汽冷凝系统"}, {"蒸气封存系统", "水汽凝结"}),
    ("containment", {"安全壳", "密闭室", "包容体"}, {"遏制", "保护罩", "围堵"}),
    ("tellurium embrittlement", {"碲脆化"}, {"碲变脆", "碲脆"}),
    ("breeder reactor", {"增殖堆", "增殖反应堆"}, {"饲养堆", "繁殖反应堆", "育种反应堆"}),
    ("FLiBe", {"FLiBe", "氟化锂铍", "氟化锂铍盐"}, {"飞利贝", "弗利比", "飞利浦"}),
]

# 77 Comprehensive MSR & Nuclear Engineering Terms (Ordered by length descending for greedy match)
MSR_GLOSSARY_77: List[Tuple[str, str]] = [
    ("effective delayed neutron fraction", "有效缓发中子份额"),
    ("delayed neutron precursor", "缓发中子先驱体"),
    ("vapor-condensing system", "蒸汽冷凝系统"),
    ("flux safety channels", "中子通量安全通道"),
    ("period trip point", "周期停堆跳闸设定值"),
    ("secondary containment", "二道安全壳"),
    ("tellurium embrittlement", "碲脆化"),
    ("flux trip point", "通量跳闸设定值"),
    ("primary containment", "一道安全壳"),
    ("cell shield blocks", "舱室屏蔽块"),
    ("reactivity anomaly", "反应性异常"),
    ("particulate emitters", "颗粒放射源"),
    ("delayed neutron", "缓发中子"),
    ("prompt neutron", "瞬发中子"),
    ("excess reactivity", "剩余反应性"),
    ("fuel-pump bowl", "燃料泵泵池"),
    ("fuel drain tank", "燃料排盐罐"),
    ("drain-tank cell", "排盐罐舱"),
    ("graphite moderator", "石墨慢化剂"),
    ("sampler-enricher", "取样浓缩添加器"),
    ("reactivity worth", "反应性价值"),
    ("breeder reactor", "增殖堆"),
    ("prompt critical", "瞬发临界"),
    ("fissile material", "可裂变材料"),
    ("fertile material", "可转换材料"),
    ("neutron count rate", "中子计数率"),
    ("absolute filters", "高效空气过滤器"),
    ("reactor vessel", "反应堆容器"),
    ("ventilation stack", "通风烟囱"),
    ("fuel offgas system", "燃料尾气系统"),
    ("reactor period", "反应堆周期"),
    ("scram circuit", "停堆跳闸电路"),
    ("scram trip", "停堆跳闸"),
    ("scram test", "停堆试验"),
    ("scram time", "停堆时间"),
    ("reactor cell", "反应堆舱"),
    ("control rod", "控制棒"),
    ("safety rod", "安全棒"),
    ("regulating rod", "调节棒"),
    ("drain tank", "排盐罐"),
    ("overflow tank", "溢流罐"),
    ("thermal shield", "热屏蔽"),
    ("freeze valve", "冷冻阀"),
    ("freeze flange", "冷冻法兰"),
    ("salt sampler", "熔盐取样器"),
    ("fission product", "裂变产物"),
    ("cover gas", "覆盖气体"),
    ("coolant salt", "冷却盐"),
    ("flush salt", "冲洗盐"),
    ("fuel salt", "燃料盐"),
    ("carrier salt", "载体盐"),
    ("breeding ratio", "增殖比"),
    ("breeding gain", "增殖增益"),
    ("doubling time", "倍增时间"),
    ("fuel burnup", "燃料燃耗"),
    ("specific power", "比功率"),
    ("conversion ratio", "转换比"),
    ("grain boundary", "晶界"),
    ("pump bowl", "泵池"),
    ("decay heat", "衰变热"),
    ("containment", "安全壳"),
    ("subcritical", "次临界"),
    ("charcoal bed", "活性炭吸附床"),
    ("xenon poisoning", "氙中毒"),
    ("Hastelloy-N", "哈氏合金N"),
    ("INOR-8", "INOR-8合金"),
    ("radiator", "空冷散热器"),
    ("offgas", "尾气"),
    ("burnup", "燃耗"),
    ("corrosion", "腐蚀"),
    ("block valve", "隔离阀"),
    ("check valve", "止回阀"),
    ("leak detector", "泄漏探测器"),
    ("instrument well", "仪表井"),
    ("drained", "排空"),
    ("FLiBe", "FLiBe"),
    ("FLiNaK", "FLiNaK"),
    ("scram", "停堆"),
    ("critical", "临界"),
    ("reactivity", "反应性"),
    ("annulus", "环形空间"),
    ("header", "联箱"),
]

# Table Stopwords Short-Circuit Mapping
TABLE_STOPWORDS_MAP: Dict[str, str] = {
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
    "at": "于",
    "At": "于",
    "by": "由",
    "By": "由",
    "on": "处于",
    "On": "处于",
    "with": "含",
    "With": "含",
    "from": "自",
    "From": "自",
    "into": "进入",
    "Into": "进入",
    "and": "及",
    "And": "及",
    "or": "或",
    "Or": "或",
    "is": "为",
    "are": "为",
    "Is": "为",
    "Are": "为",
    "was": "曾为",
    "were": "曾为",
    "be": "为",
    "Be": "为",
    "BE": "为",
    "it": "它",
    "It": "它",
    "its": "其",
    "Its": "其",
    "this": "该",
    "This": "该",
    "that": "该",
    "That": "该",
    "no": "无",
    "not": "否",
    "No": "无",
    "Not": "否",
    "all": "全部",
    "All": "全部",
    "any": "任一",
    "Any": "任一",
    "total": "总计",
    "Total": "总计",
    "gas": "气体",
    "Gas": "气体",
    "-": "-",
    "--": "--",
    "---": "---",
    "/": "/",
}

# 33 Historical Typewriter OCR Heuristic Cleaning Rules
TYPEWRITER_OCR_RULES: List[Tuple[str, str]] = [
    (r"\benergydemands\b", "energy demands"),
    (r"\bAgsicies\b", "Agencies"),
    (r"\bThair\b", "Their"),
    (r"\bobove\b", "above"),
    (r"\bpossgible\b", "possible"),
    (r"\bintec\b", "into"),
    (r"\bAdminist\s+strator\b", "Administrator"),
    (r"\brequi\s+guires\b", "requires"),
    (r"\boT\b", "or"),
    (r"\bOFERATING\b", "OPERATING"),
    (r"\bgverflow\b", "overflow"),
    (r"\beconomyfrcm\b", "economy from"),
    (r"\bItis\b", "It is"),
    (r"\bmadeit\b", "made it"),
    (r"\bplusthe\b", "plus the"),
    (r"\bThejustificatlon\b", "The justification"),
    (r"ex-\s+ceeded", "exceeded"),
    (r"con=-\s+centration", "concentration"),
    (r"wmain-\s+tained", "maintained"),
    (r"\bmain-\s+tained", "maintained"),
    (r"\b([Ss]afety\s+)1(limits?)\b", r"\g<1>\g<2>"),
    (r"\bsafety\s+1limits\b", "safety limits"),
    (r"\blimit\s+1s\b", "limit is"),
    (r"\b4o\b", "40"),
    (r"\bts\b", "is"),
    (r"\bL5\s+psig\b", "45 psig"),
    (r"\b7O\s+scfd\b", "70 scfd"),
    (r"\b'130°F\b", "130°F"),
    (r"\bL\.k\s+Cell\b", "4.4 Cell"),
    (r"\bL\.5\s+Cell\b", "4.5 Cell"),
    (r"\bL\.6\s+Cell\b", "4.6 Cell"),
    (r"\bL\.t\.\s+Lt\b", "4.7"),
    (r"\bL\.8\s+Vapor\b", "4.8 Vapor"),
    (r"\bk11\s+Ventilation\b", "4.11 Ventilation"),
    (r"\bL\.12\s+Ventilation\b", "4.12 Ventilation"),
    (r"\bL1k\s+Ieak\b", "4.14 Leak"),
    (r"\b4,16\b", "4.16"),
    (r"\b0\.62yc/sec\b", "0.62 μCi/sec"),
    (r"\bft°/min\b", "ft³/min"),
    (r"\b5,0\s+ft°\b", "5.0 ft³"),
    (r"\buwatil\b", "until"),
    (r"\btais\b", "this"),
    (r"\bbhe\b", "be"),
]

# Shared TranslationEngine instance across all E2E tests
_SHARED_ENGINE = None


def get_shared_engine():
    """Lazily load and cache the singleton TranslationEngine."""
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        try:
            from src.translator import TranslationEngine
            _SHARED_ENGINE = TranslationEngine(MODEL_DIR)
        except Exception as e:
            raise RuntimeError(f"Failed to load shared TranslationEngine from {MODEL_DIR}: {e}")
    return _SHARED_ENGINE


def get_code_classifier() -> Optional[Callable[[str, str], bool]]:
    """Get classify_code_block if exported by src.translator."""
    try:
        import src.translator as tr_mod
        return getattr(tr_mod, "classify_code_block", None)
    except Exception:
        return None


def get_ocr_cleaner() -> Optional[Callable[[str], str]]:
    """Get clean_historical_ocr_text if exported by src.translator."""
    try:
        import src.translator as tr_mod
        return getattr(tr_mod, "clean_historical_ocr_text", None)
    except Exception:
        return None


def apply_reference_ocr_cleaner(text: str) -> str:
    """Reference implementation of typewriter OCR cleaner using TYPEWRITER_OCR_RULES."""
    res = text
    for pat, repl in TYPEWRITER_OCR_RULES:
        res = re.sub(pat, repl, res)
    return res
