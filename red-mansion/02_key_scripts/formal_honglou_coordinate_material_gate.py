#!/usr/bin/env python3
from __future__ import annotations

import re
import sqlite3
import json
import csv
from itertools import combinations
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import quote

try:
    import formal_honglou_aggregation_graph_runtime as graph_runtime
except Exception:  # pragma: no cover - coordinate gate should still run as a standalone material gate
    graph_runtime = None  # type: ignore[assignment]

try:
    import formal_honglou_question_decomposer as decomposer
except Exception:  # pragma: no cover
    decomposer = None  # type: ignore[assignment]

try:
    import formal_honglou_text_normalizer as text_normalizer
except Exception:  # pragma: no cover
    text_normalizer = None  # type: ignore[assignment]


SUBQUESTION_STRATEGY_QUEUE_LABELS = ("Codex子问题策略队列", "Codex子问题策略", "Codex子问题策略选择", "Codex子问题排队")
CONTEXT_LABELS = (
    "Codex查询词",
    "Codex查询逻辑策略",
    "Codex策略模板",
    "Codex查询策略模板",
    "Codex策略执行口径",
    "Codex策略执行方式",
    "Codex执行口径",
    "Codex策略组合",
    "Codex组合策略",
    "Codex策略调整记录",
    "Codex策略调整",
    "Codex换卡理由",
    "Codex实际执行策略",
    "Codex偏离理由",
    "Codex策略偏离理由",
    "Codex子问题",
    "Codex子问题策略队列",
    "Codex子问题策略",
    "Codex子问题策略选择",
    "Codex子问题排队",
    "Codex词角色",
    "Codex强复合",
    "Codex查证顺序",
    "Codex材料升级条件",
    "Codex优先库",
    "取材门",
    "recall_gate",
)

MATERIAL_RECALL_ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs/红楼梦正式取材专库")
VARIABLE_DB = MATERIAL_RECALL_ROOT / "00_双中心取材总库" / "02_坐标查询中心库" / "红楼梦坐标查询中心库_CH001_120.sqlite"
CHAR_DB = MATERIAL_RECALL_ROOT / "01_正文原文与词位库" / "红楼梦全文字位原子段桥表_CH001_120.sqlite"
TERM_DB = MATERIAL_RECALL_ROOT / "01_正文原文与词位库" / "红楼梦全文词位材料索引库_CH001_120.sqlite"
PERSON_ALIAS_CSV = MATERIAL_RECALL_ROOT / "03_人物归一库" / "70_全人物别名归一总表.csv"
PERSON_QUERY_PACKAGE_CSV = MATERIAL_RECALL_ROOT / "03_人物归一库" / "72_人物查询归一包_全量生成表.csv"
SHARED_EIGHT_STEP_SPINE = [
    "归一",
    "收点",
    "交集",
    "路由门",
    "分类",
    "回原文",
    "入材料池",
    "写答案",
]
SHARED_EIGHT_STEP_FORMULA = " -> ".join(SHARED_EIGHT_STEP_SPINE)

COORDINATE_TOOL_USAGE_GUIDE = (
    "完整八步法硬锁：坐标头与聚拢头共用取词之前的思考，先读题、判断题型、拆对象、定主轴、生成入口词令牌；"
    "取词以后进入坐标分析法，不走聚拢场组织法，而是用坐标中心库、词位库和字位桥表收点、交集、测距、回原文；"
    "有明确字词/短语/原文片段时先走词位穷尽；"
    "有人物/空间/季节/物件/行动时走坐标变量；问最近/靠近/相邻时加距离测量；"
    "问同场/同时/共同出现时加共场交集；问第一次/最早/全书哪里时必须全量按回序和字位排序；"
    "对象词取材时，全文词位负责防漏，变量坐标负责定点；变量未登记不等于原文没有，精确变量也不能替代全文词位和原文裁判；"
    "复杂比较题先拆子问题再两两查询；候选出来后必须回原文句子和材料池裁判，不能裸答。"
)

def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_labeled_context(text: str) -> str:
    normalized = str(text or "")
    labels = context_label_regex()
    normalized = re.sub(rf"\s+(?=(?:{labels})\s*[：:])", "\n", normalized)
    normalized = re.sub(r"\s*[｜|]\s*(?=\S+?[：:])", "\n", normalized)
    return normalized


def context_label_regex() -> str:
    return "|".join(re.escape(label) for label in CONTEXT_LABELS)


def context_stop_regex() -> str:
    return rf"(?=\n\s*(?:{context_label_regex()})\s*[：:]|\Z)"


def assert_under_material_recall_root(path: Path) -> None:
    root = MATERIAL_RECALL_ROOT.resolve()
    target = path.resolve()
    if root != target and root not in target.parents:
        raise PermissionError(f"坐标取材硬锁阻断：{target} 不在正式取材专库 {root} 内。")


def is_coordinate_gate(question: str = "", route_context: str = "") -> bool:
    text = f"{question}\n{route_context}"
    if (
        re.search(r"(^|\n)\s*取材门\s*[：:]\s*语义", text)
        or re.search(r"(^|\n)\s*recall_gate\s*[：:]\s*semantic", text, flags=re.I)
        or clean(question).startswith("语义")
    ):
        return False
    return bool(
        re.search(r"(^|\n)\s*取材门\s*[：:]\s*坐标", text)
        or re.search(r"(^|\n)\s*recall_gate\s*[：:]\s*coordinate", text, flags=re.I)
        or re.search(r"(^|\n)\s*进入坐标查询", text)
        or re.search(r"(^|\n)\s*(坐标查询|坐标法查询|用坐标法查|从坐标查|坐标取材)", text)
        or clean(question).startswith("坐标")
    )


def context_value(text: str, label: str) -> str:
    text = normalize_labeled_context(text)
    if label not in SUBQUESTION_STRATEGY_QUEUE_LABELS:
        for queue_label in SUBQUESTION_STRATEGY_QUEUE_LABELS:
            text = re.sub(
                rf"(^|\n)\s*{re.escape(queue_label)}\s*[：:].*?{context_stop_regex()}",
                r"\1",
                text or "",
                flags=re.S,
            )
    normalized = normalize_labeled_context(text)
    pattern = re.compile(rf"(^|\n)\s*{re.escape(label)}\s*[：:]\s*(.+?){context_stop_regex()}", re.S)
    match = pattern.search(normalized)
    return clean(match.group(2)) if match else ""


def raw_context_value(text: str, label: str) -> str:
    text = normalize_labeled_context(text)
    pattern = re.compile(rf"(^|\n)\s*{re.escape(label)}\s*[：:]\s*(.+?){context_stop_regex()}", re.S)
    match = pattern.search(text or "")
    return clean(match.group(2)) if match else ""


def query_logic_strategy_value(text: str) -> str:
    for label in ("Codex查询逻辑策略", "Codex策略模板", "Codex查询策略模板"):
        value = context_value(text, label)
        if value:
            return value
    return ""


def has_query_logic_strategy_choice(text: str) -> bool:
    value = query_logic_strategy_value(text)
    if not value:
        return False
    if re.search(r"(未选择|待定|不确定|不知道|无策略|不用策略)", value):
        return False
    if not re.search(r"(模板\s*0?[0-9]|模板\s*10|拆子问题|复杂策略|策略)", value):
        return False
    if query_logic_strategy_requires_subquestions(text) and not context_value(text, "Codex子问题"):
        return False
    return True


def query_logic_strategy_requires_subquestions(text: str) -> bool:
    value = query_logic_strategy_value(text)
    return bool(re.search(r"(模板\s*0?0(?!\d)|拆子问题)", value))


def first_context_value(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        value = context_value(text, label)
        if value:
            return value
    return ""


def strategy_execution_mode_value(text: str) -> str:
    return first_context_value(text, ("Codex策略执行口径", "Codex策略执行方式", "Codex执行口径"))


def strategy_combination_value(text: str) -> str:
    return first_context_value(text, ("Codex策略组合", "Codex组合策略"))


def strategy_adjustment_value(text: str) -> str:
    return first_context_value(text, ("Codex策略调整记录", "Codex策略调整", "Codex换卡理由"))


def strategy_deviation_value(text: str) -> str:
    return first_context_value(text, ("Codex偏离理由", "Codex策略偏离理由"))


def actual_execution_strategy_value(text: str) -> str:
    return context_value(text, "Codex实际执行策略")


def query_logic_strategy_flexibility_profile(text: str) -> dict[str, Any]:
    strategy = query_logic_strategy_value(text)
    execution_mode = strategy_execution_mode_value(text)
    combination = strategy_combination_value(text)
    adjustment = strategy_adjustment_value(text)
    deviation = strategy_deviation_value(text)
    actual_execution = actual_execution_strategy_value(text)
    combined = "\n".join(
        clean(item)
        for item in (strategy, execution_mode, combination, adjustment, deviation, actual_execution)
        if clean(item)
    )
    is_combination = bool(re.search(r"(组合|主卡|辅卡|\+|叠加|并用)", combined))
    is_switch = bool(re.search(r"(换卡|调整|原卡|新卡|转为|改用|证据反馈)", combined))
    is_deviation = bool(re.search(r"(偏离|不按|不能按|不死套|不死跑|例外)", combined))
    has_flex_reason = bool(
        combination
        or adjustment
        or deviation
        or re.search(r"(因为|原因|理由|触发证据|证据反馈|为什么)", combined)
    )
    warnings: list[str] = []
    if (is_combination or is_switch or is_deviation) and not has_flex_reason:
        warnings.append("策略文本出现组合/换卡/偏离信号，但没有写出理由；建议补 Codex策略组合 / Codex策略调整记录 / Codex偏离理由。")
    return {
        "strategy_value": strategy,
        "execution_mode": execution_mode,
        "combination": combination,
        "adjustment_record": adjustment,
        "deviation_reason": deviation,
        "actual_execution": actual_execution,
        "is_combination": is_combination,
        "is_switch": is_switch,
        "is_deviation": is_deviation,
        "has_flex_reason": has_flex_reason,
        "warnings": warnings,
        "rule": "强制的是有策略意识：必须显式选择起手策略；允许组合、换卡、偏离，但应留理由并回原文裁判。",
    }


def numbered_items(value: str) -> list[str]:
    text = clean(value)
    if not text:
        return []
    text = re.sub(r"[；;]\s*(?=\d+[.、)]\s*)", "\n", text)
    text = re.sub(r"\s+(?=\d+[.、)]\s*)", "\n", text)
    matches = list(
        re.finditer(
            r"(?:^|\n)\s*(?:\d+[.、)]|[-*])\s*(.+?)(?=(?:\n\s*(?:\d+[.、)]|[-*])\s*)|\Z)",
            text,
            flags=re.S,
        )
    )
    if matches:
        return [clean(match.group(1)) for match in matches if clean(match.group(1))]
    parts = [clean(part) for part in re.split(r"[；;\n]+", text) if clean(part)]
    return parts or [text]


def subquestion_items(text: str) -> list[str]:
    return numbered_items(context_value(text, "Codex子问题"))


def subquestion_strategy_queue_value(text: str) -> str:
    for label in SUBQUESTION_STRATEGY_QUEUE_LABELS:
        value = raw_context_value(text, label)
        if value:
            return value
    return ""


def subquestion_strategy_queue_items(text: str) -> list[str]:
    return numbered_items(subquestion_strategy_queue_value(text))


def subquestion_strategy_queue_status(text: str) -> dict[str, Any]:
    if not query_logic_strategy_requires_subquestions(text):
        return {"ok": True, "reason": "未选择模板00，不要求子问题策略队列。"}
    subquestions = subquestion_items(text)
    queue = subquestion_strategy_queue_items(text)
    if not subquestions:
        return {"ok": False, "reason": "缺 Codex子问题。"}
    if not queue:
        return {"ok": False, "reason": "缺 Codex子问题策略队列。"}
    if len(queue) < len(subquestions):
        return {
            "ok": False,
            "reason": f"子问题有 {len(subquestions)} 个，但策略队列只有 {len(queue)} 条。",
        }
    missing_strategy = [
        str(idx)
        for idx, item in enumerate(queue[: len(subquestions)], start=1)
        if not re.search(r"(Codex查询逻辑策略|模板\s*0?[1-9]|模板\s*10|策略)", item)
    ]
    if missing_strategy:
        return {"ok": False, "reason": "下列子问题没有重新选择策略：" + "、".join(missing_strategy)}
    missing_pairwise = [
        str(idx)
        for idx, item in enumerate(queue[: len(subquestions)], start=1)
        if not re.search(r"(两两|对象A|对象B|强复合|\+|对照|交集|同场|关系)", item)
    ]
    if missing_pairwise:
        return {"ok": False, "reason": "下列子问题没有写成两两可查对象或强复合：" + "、".join(missing_pairwise)}
    return {
        "ok": True,
        "reason": f"模板00已拆出 {len(subquestions)} 个子问题，并为每个子问题建立策略队列。",
        "subquestion_count": len(subquestions),
        "strategy_queue_count": len(queue),
    }


def split_terms(value: str) -> list[str]:
    value = re.sub(r"[｜|]", "、", value or "")
    parts = re.split(r"[、，,；;\s]+", value)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = clean(part)
        if not part:
            continue
        for bit in re.split(r"[+/]", part):
            bit = clean(bit)
            if bit and bit not in seen:
                seen.add(bit)
                out.append(bit)
    return out


PRONOUN_OR_ROLE_ONLY_TERMS = {
    "我",
    "你",
    "他",
    "她",
    "它",
    "吾",
    "俺",
    "咱",
    "自己",
    "本人",
}


def term_bag_terms(values: list[str]) -> list[str]:
    """Use the migrated Codex query-term pocket; do not machine-compile the question."""
    if decomposer is not None:
        try:
            return decomposer.significant_search_terms(values, limit=0)
        except Exception:
            pass
    return values


TERM_VARIANT_OVERRIDES = {
    "梦": ["夢"],
    "梦境": ["夢境"],
    "做梦": ["做夢"],
    "说": ["說"],
    "说道": ["說道"],
    "说话": ["說話"],
    "讲": ["講"],
    "泪": ["淚"],
    "眼泪": ["眼淚"],
    "流泪": ["流淚"],
    "哭泣": ["哭泣"],
    "鸡": ["雞", "鷄"],
    "乌眼鸡": ["烏眼雞", "烏眼鷄"],
    "黄": ["黃"],
    "黄金": ["黃金"],
    "药": ["藥"],
    "灯": ["燈"],
    "书": ["書"],
    "宝": ["寶"],
    "宝玉": ["寶玉"],
    "黛玉": ["黛玉"],
    "林黛玉": ["林黛玉"],
}


def term_variants(term: str) -> list[str]:
    term = clean(term)
    if not term:
        return []
    variants: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = clean(value)
        if value and value not in seen:
            seen.add(value)
            variants.append(value)

    add(term)
    for value in TERM_VARIANT_OVERRIDES.get(term, []):
        add(value)
    if text_normalizer is not None:
        try:
            normalized = text_normalizer.normalize_for_match(term)
            add(normalized)
            for key, values in TERM_VARIANT_OVERRIDES.items():
                if text_normalizer.normalize_for_match(key) == normalized:
                    add(key)
                    for value in values:
                        add(value)
        except Exception:
            pass
    return variants


_PERSON_PACKAGE_CACHE: tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]] | None = None


def _person_split(value: str) -> list[str]:
    parts = re.split(r"[；;、，,\s]+", clean(value))
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        part = clean(part)
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out


def load_person_packages() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    global _PERSON_PACKAGE_CACHE
    if _PERSON_PACKAGE_CACHE is not None:
        return _PERSON_PACKAGE_CACHE

    by_key: dict[str, dict[str, Any]] = {}
    by_term: dict[str, dict[str, Any]] = {}

    assert_under_material_recall_root(PERSON_QUERY_PACKAGE_CSV)
    assert_under_material_recall_root(PERSON_ALIAS_CSV)

    if PERSON_QUERY_PACKAGE_CSV.exists():
        with PERSON_QUERY_PACKAGE_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                character_key = clean(row.get("character_key"))
                canonical = clean(row.get("canonical_mapping_name")) or clean(row.get("default_display_name"))
                if not character_key or not canonical:
                    continue
                query_terms = _person_split(row.get("query_terms", ""))
                aliases = _person_split(row.get("aliases", ""))
                package = {
                    "character_key": character_key,
                    "character_code": clean(row.get("character_code")),
                    "canonical_mapping_name": canonical,
                    "default_display_name": clean(row.get("default_display_name")) or canonical,
                    "query_terms": query_terms,
                    "aliases": aliases,
                    "ambiguity_status": clean(row.get("ambiguity_status")),
                    "ambiguity_rule": clean(row.get("ambiguity_rule")),
                    "identity_label": clean(row.get("identity_label")),
                    "source": "72_人物查询归一包_全量生成表.csv",
                }
                by_key[character_key] = package
                for term in [canonical, package["default_display_name"], *query_terms, *aliases]:
                    if clean(term):
                        by_term.setdefault(clean(term), package)

    if PERSON_ALIAS_CSV.exists():
        with PERSON_ALIAS_CSV.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                character_key = clean(row.get("character_key"))
                canonical = clean(row.get("canonical_mapping_name")) or clean(row.get("character_name"))
                if not character_key or not canonical:
                    continue
                package = by_key.get(character_key) or {
                    "character_key": character_key,
                    "character_code": clean(row.get("character_code")),
                    "canonical_mapping_name": canonical,
                    "default_display_name": clean(row.get("character_name")) or canonical,
                    "query_terms": [canonical],
                    "aliases": _person_split(row.get("aliases_raw", "")),
                    "ambiguity_status": "",
                    "ambiguity_rule": "",
                    "identity_label": clean(row.get("identity_label")),
                    "source": "70_全人物别名归一总表.csv",
                }
                by_key.setdefault(character_key, package)
                for term in [row.get("input_name"), canonical, row.get("character_name"), row.get("aliases_raw")]:
                    for bit in _person_split(term or ""):
                        by_term.setdefault(bit, package)

    _PERSON_PACKAGE_CACHE = (by_term, by_key)
    return _PERSON_PACKAGE_CACHE


def person_normalization_profile(terms: list[str]) -> dict[str, Any]:
    by_term, _by_key = load_person_packages()
    expanded_terms: list[str] = []
    packages: list[dict[str, Any]] = []
    alias_expansions: dict[str, list[str]] = {}
    canonical_to_package: dict[str, dict[str, Any]] = {}
    seen_terms: set[str] = set()
    seen_keys: set[str] = set()

    for term in terms:
        package = by_term.get(clean(term))
        if package:
            key = clean(package.get("character_key"))
            if key and key not in seen_keys:
                seen_keys.add(key)
                packages.append(package)
            canonical = clean(package.get("canonical_mapping_name"))
            candidates = [canonical]
            if canonical:
                canonical_to_package[canonical] = package
                alias_expansions[canonical] = _person_split("；".join(package.get("query_terms") or []))
        else:
            candidates = [term]
        for candidate in candidates:
            candidate = clean(candidate)
            if candidate and candidate not in seen_terms:
                seen_terms.add(candidate)
                expanded_terms.append(candidate)

    return {
        "terms": expanded_terms[:48],
        "packages": packages,
        "status": "已接入70/72全人物归一包" if packages else "未命中人物归一包",
        "character_keys": [clean(pkg.get("character_key")) for pkg in packages],
        "canonical_names": [clean(pkg.get("canonical_mapping_name")) for pkg in packages],
        "alias_expansions": alias_expansions,
        "canonical_to_package": canonical_to_package,
    }


def query_terms(question: str, route_context: str) -> list[str]:
    terms = split_terms(context_value(route_context, "Codex查询词"))
    terms.extend(split_terms(context_value(route_context, "Codex强复合")))
    blocked = {"坐标", "查询", "搜索", "这个", "那个", "一个", "两个", "状态", "比较", "接近", "两个人"}
    terms = term_bag_terms(terms)
    out: list[str] = []
    seen: set[str] = set()
    for term in terms:
        term = clean(term)
        if not term or term in blocked or term in PRONOUN_OR_ROLE_ONLY_TERMS:
            continue
        if len(term) > 12:
            continue
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out[:36]


def safe_root_terms(base_terms: list[str], root_terms: list[str]) -> list[str]:
    """Keep 126/root terms useful without letting broad single characters dominate."""
    base = {clean(term) for term in base_terms if clean(term)}
    out: list[str] = []
    seen: set[str] = set()
    for term in root_terms:
        term = clean(term)
        if not term or term in seen:
            continue
        if len(term) <= 1 and term not in base:
            continue
        seen.add(term)
        out.append(term)
    return out


def coordinate_preflight_tokens(question: str, route_context: str, terms: list[str], query_types: list[str] | None = None) -> dict[str, Any]:
    query_types = query_types or []
    route_text = f"{question}\n{route_context}"
    has_coordinate_gate = is_coordinate_gate(question, route_context)
    has_entry_terms = bool(context_value(route_context, "Codex查询词"))
    has_compound_axis = bool(context_value(route_context, "Codex强复合")) or len(terms) <= 1
    has_term_roles = bool(context_value(route_context, "Codex词角色")) or len(terms) <= 1
    has_source_order = bool(context_value(route_context, "Codex查证顺序")) or bool(context_value(route_context, "Codex优先库"))
    has_upgrade_rule = bool(context_value(route_context, "Codex材料升级条件"))
    has_query_logic_strategy = has_query_logic_strategy_choice(route_context)
    requires_subquestions = query_logic_strategy_requires_subquestions(route_context)
    has_subquestions = bool(context_value(route_context, "Codex子问题"))
    subquestion_queue_status = subquestion_strategy_queue_status(route_context)
    strategy_flexibility = query_logic_strategy_flexibility_profile(route_context)
    flex_indicated = bool(
        strategy_flexibility.get("is_combination")
        or strategy_flexibility.get("is_switch")
        or strategy_flexibility.get("is_deviation")
    )
    wants_distance = "距离" in query_types
    wants_cooccurrence = "共场" in query_types or len(terms) >= 2
    person_profile = person_normalization_profile(terms)
    role_text = context_value(route_context, "Codex词角色")
    by_term, _by_key = load_person_packages()
    requires_person_identity = any(clean(term) in by_term for term in terms) or any(
        token in role_text for token in ("人物", "人名", "名字", "姓名", "称谓", "别名")
    )
    has_person_identity = (not requires_person_identity) or bool(person_profile.get("packages"))
    tokens = [
        {
            "token": "坐标入口令牌",
            "ok": has_coordinate_gate,
            "required": True,
            "meaning": "题目明确进入坐标取材，不回落语义取材。",
        },
        {
            "token": "入口词令牌",
            "ok": has_entry_terms and bool(terms),
            "required": True,
            "meaning": "必须有 Codex查询词；坐标路不再从问题里裸猜词。",
        },
        {
            "token": "人物归一强令牌",
            "ok": has_person_identity,
            "required": requires_person_identity,
            "meaning": "凡入口词或词角色涉及人物、名字、称谓、别名，必须先过70/72全人物归一包。",
        },
        {
            "token": "词角色令牌",
            "ok": has_term_roles,
            "required": False,
            "meaning": "区分主查人物、物象、场景词、归一词、扩展词和背景锚点。",
        },
        {
            "token": "强复合轴令牌",
            "ok": has_compound_axis,
            "required": len(terms) >= 2,
            "meaning": "多对象题必须知道哪些对象要共同成立，防止单边材料冒充关系证据。",
        },
        {
            "token": "方法调度令牌",
            "ok": bool(query_types),
            "required": True,
            "meaning": "必须先判本题走词位、坐标、距离、共场、全量、综合还是原文回查。",
        },
        {
            "token": "查询逻辑策略令牌",
            "ok": has_query_logic_strategy,
            "required": True,
            "meaning": "AI取词后必须从000E查询逻辑策略模板组选择一个起手策略；若没有合适模板，必须选择拆子问题策略并列出子问题。",
        },
        {
            "token": "策略弹性记录令牌",
            "ok": (not flex_indicated) or bool(strategy_flexibility.get("has_flex_reason")),
            "required": False,
            "meaning": "策略卡是起手卡，不是死模板；组合、换卡、偏离应记录理由，但本令牌只提示质量，不替代无策略硬阻断。",
        },
        {
            "token": "拆子问题清单令牌",
            "ok": (not requires_subquestions) or has_subquestions,
            "required": requires_subquestions,
            "meaning": "选择模板00｜拆子问题策略时，必须写出 Codex子问题，不能只说复杂。",
        },
        {
            "token": "子问题策略排队令牌",
            "ok": bool(subquestion_queue_status.get("ok")),
            "required": requires_subquestions,
            "meaning": "模板00产生子问题后，每个子问题必须分别排队，并重新选择查询逻辑策略；每条子问题要写成两两可查对象或强复合。",
        },
        {
            "token": "距离/共场令牌",
            "ok": (not wants_distance and not wants_cooccurrence) or len(terms) >= 2,
            "required": wants_distance or wants_cooccurrence,
            "meaning": "最近/同场/多对象题必须形成两两关系，不能只看单个词命中。",
        },
        {
            "token": "来源顺序令牌",
            "ok": has_source_order,
            "required": False,
            "meaning": "说明先查哪个库、再回哪个原文入口，防止本地工程自作主张。",
        },
        {
            "token": "材料升级令牌",
            "ok": has_upgrade_rule,
            "required": False,
            "meaning": "说明候选怎样才能进入材料池判定，防止命中直接变答案。",
        },
        {
            "token": "原文裁判令牌",
            "ok": True,
            "required": True,
            "meaning": "所有坐标候选必须回原文句子和材料池裁判。",
        },
    ]
    missing_required = [item["token"] for item in tokens if item["required"] and not item["ok"]]
    missing_optional = [item["token"] for item in tokens if not item["required"] and not item["ok"]]
    return {
        "ok": not missing_required,
        "tokens": tokens,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
        "rule": "坐标路必须先拿入口词、方法令牌和查询逻辑策略令牌，再允许查表；模板00必须形成子问题策略队列，缺策略模板时停在坐标预检门。策略卡是起手卡，允许组合、换卡、偏离，但要留理由并回原文裁判。",
        "route_hint": "取材门：坐标" if "坐标" in route_text else "",
        "subquestion_strategy_queue": subquestion_queue_status,
        "strategy_flexibility": strategy_flexibility,
    }


def guidance_profile(question: str, route_context: str) -> dict[str, Any]:
    base_terms = query_terms(question, route_context)
    root_path: dict[str, Any] = {}
    root_terms: list[str] = []
    if graph_runtime is not None:
        try:
            root_path = graph_runtime.build_126_generic_root_path(question, base_terms)
            root_terms = safe_root_terms(base_terms, [clean(term) for term in root_path.get("generic_root_terms", []) if clean(term)])
        except Exception as exc:  # pragma: no cover
            root_path = {"source": "126_聚龙法查询词入口规范_单字宽网", "error": f"{type(exc).__name__}: {exc}"}
    terms = []
    seen: set[str] = set()
    for term in [*base_terms, *root_terms]:
        if term and term not in seen:
            seen.add(term)
            terms.append(term)
    person_profile = person_normalization_profile(terms)
    terms = person_profile["terms"]
    term_roles = context_value(route_context, "Codex词角色")
    return {
        "terms": terms[:36],
        "base_terms": base_terms,
        "root_terms": root_terms,
        "person_normalization": person_profile,
        "term_roles": term_roles,
        "root_path": root_path,
        "basis": f"{SHARED_EIGHT_STEP_FORMULA}；坐标工具细节为 Codex入口词令牌 + 70/72全人物归一包 + 126名称/对象归一与根字宽网 + 穷尽法补点 + 两两交集/近邻 + 坐标容器放大",
    }


def connect(path: Path) -> sqlite3.Connection:
    assert_under_material_recall_root(path)
    if not path.exists():
        raise FileNotFoundError(path)
    uri = "file:" + quote(str(path), safe="/:") + "?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    except sqlite3.OperationalError:
        fallback_uri = "file:" + quote(str(path), safe="/:") + "?mode=ro"
        conn = sqlite3.connect(fallback_uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.Error:
        pass
    return conn


def find_term(term: str, limit: int = 1200) -> list[dict[str, Any]]:
    variants = term_variants(term)
    if not variants:
        return []
    placeholders = ",".join("?" for _ in variants)
    conn = connect(TERM_DB)
    try:
        rows = conn.execute(
            f"""
            SELECT term_surface, term_norm, term_len, start_char, end_char, cross_atom,
                   start_span_status, start_span_confidence, atom_id, atom_code,
                   old_segment_no, chapter_no, global_atom_order, cluster_id,
                   event_id, scene_id, scene_group_id, time_block_id, summary, quote
            FROM v_term_hits
            WHERE term_norm IN ({placeholders}) OR term_surface IN ({placeholders})
            ORDER BY chapter_no, start_char
            LIMIT ?
            """,
            (*variants, *variants, limit),
        ).fetchall()
        return [
            dict(row)
            | {
                "hit_value": term,
                "matched_term_variant": clean(row["term_norm"]) if clean(row["term_norm"]) in variants else clean(row["term_surface"]),
                "hit_source": "term",
            }
            for row in rows
            if clean(row["atom_id"])
        ]
    finally:
        conn.close()


def chapter_text(chapter_no: int) -> str:
    conn = connect(TERM_DB)
    try:
        row = conn.execute(
            "SELECT full_text FROM chapter_texts WHERE chapter_no=?",
            (int(chapter_no or 0),),
        ).fetchone()
        return clean(row["full_text"]) if row else ""
    finally:
        conn.close()


def source_sentence(chapter_no: int, char_pos: int | None = None, fallback: str = "") -> str:
    text = chapter_text(int(chapter_no or 0))
    if not text:
        return clean(fallback)
    if not char_pos:
        return clean(fallback) or text[:160]
    index = max(0, min(int(char_pos) - 1, len(text) - 1))
    left = index
    while left > 0 and text[left - 1] not in "。！？；\n":
        left -= 1
    right = index
    while right < len(text) and text[right] not in "。！？；\n":
        right += 1
    sentence = text[left:right].strip()
    return sentence or clean(fallback)


def find_variable(name: str, limit: int = 1600, variable_type: str = "", exact: bool = False) -> list[dict[str, Any]]:
    conn = connect(VARIABLE_DB)
    try:
        where = "variable_value_name LIKE ? OR variable_value_id LIKE ?"
        params: list[Any] = [f"%{name}%", f"%{name}%"]
        if exact:
            where = "variable_value_name=?"
            params = [name]
        if variable_type:
            where = f"variable_type=? AND ({where})"
            params = [variable_type, *params]
        params.append(limit)
        rows = conn.execute(
            f"""
            SELECT variable_type, variable_value_name, variable_role, confidence,
                   scope, precision, review_status, raw_value,
                   atom_id, atom_code, old_segment_no, chapter_no, global_atom_order,
                   cluster_id, event_id, scene_id, scene_group_id, time_block_id,
                   atom_summary AS summary, atom_quote AS quote
            FROM v_variable_point_context
            WHERE {where}
            ORDER BY confidence DESC, chapter_no, global_atom_order
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [dict(row) | {"hit_value": name, "hit_source": "variable"} for row in rows if clean(row["atom_id"])]
    finally:
        conn.close()


def find_variable_for_term(term: str, limit: int = 1600) -> list[dict[str, Any]]:
    exact_rows = find_variable(term, limit=limit, exact=True)
    if exact_rows:
        return exact_rows
    if len(clean(term)) <= 1:
        return []
    return find_variable(term, limit=min(limit, 240), exact=False)


def variable_evidence_grade(record: dict[str, Any]) -> tuple[str, int]:
    variable_type = clean(record.get("variable_type"))
    scope = clean(record.get("scope"))
    precision = clean(record.get("precision"))
    review_status = clean(record.get("review_status"))
    if review_status and "needs_review" in review_status:
        return "待复核", -300
    if variable_type in {"person", "object", "space"} and (precision in {"atom", "resolved_atom"} or clean(record.get("atom_id"))):
        return "硬证据", 900
    if variable_type in {"season", "time", "action", "event"} and scope not in {"chapter", "chapter_level_context"}:
        return "中证据", 420
    if variable_type in {"scene_person_hint", "scene_object_hint"}:
        return "提示证据", 120
    if scope in {"chapter", "chapter_level_context"} or variable_type in {"time_axis"}:
        return "弱证据", 60
    return "中证据", 260


def dedupe_hit_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        if clean(record.get("hit_source")) == "variable":
            key = (
                clean(record.get("variable_type")),
                clean(record.get("variable_value_name")),
                clean(record.get("atom_id")),
                clean(record.get("hit_value")),
            )
        else:
            key = (
                "term",
                clean(record.get("term_surface")) or clean(record.get("hit_value")),
                clean(record.get("atom_id")),
                str(record.get("start_char") or ""),
            )
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def container_counts(records: list[dict[str, Any]], key: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for record in records:
        container = clean(record.get(key))
        value = clean(record.get("hit_value"))
        if container and value:
            out[container].add(value)
    return out


def term_point_index(records: list[dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for record in records:
        term = clean(record.get("hit_value"))
        if not term:
            continue
        for key in ("atom_id", "scene_id", "event_id", "time_block_id", "cluster_id"):
            value = clean(record.get(key))
            if value:
                out[term][key].add(value)
    return out


def term_record_index(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for record in records:
        term = clean(record.get("hit_value"))
        atom_id = clean(record.get("atom_id"))
        if not term or not atom_id:
            continue
        key = (term, atom_id)
        if key in seen:
            continue
        seen.add(key)
        out[term].append(record)
    return out


def pairwise_matrix(terms: list[str], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = term_point_index(records)
    record_index = term_record_index(records)
    rows: list[dict[str, Any]] = []
    for left, right in combinations(terms, 2):
        left_points = index.get(left, {})
        right_points = index.get(right, {})
        same_atom = left_points.get("atom_id", set()) & right_points.get("atom_id", set())
        same_scene = left_points.get("scene_id", set()) & right_points.get("scene_id", set())
        same_event = left_points.get("event_id", set()) & right_points.get("event_id", set())
        same_time = left_points.get("time_block_id", set()) & right_points.get("time_block_id", set())
        if same_atom:
            level = "same_atom"
        elif same_scene:
            level = "same_scene"
        elif same_event:
            level = "same_event"
        elif same_time:
            level = "same_time_block"
        else:
            level = "no_container_intersection"
        nearest_distance = None
        nearest_left = ""
        nearest_right = ""
        for left_record in record_index.get(left, [])[:600]:
            left_order = left_record.get("global_atom_order")
            if left_order is None:
                continue
            for right_record in record_index.get(right, [])[:600]:
                right_order = right_record.get("global_atom_order")
                if right_order is None:
                    continue
                distance = abs(int(right_order) - int(left_order))
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest_left = clean(left_record.get("atom_code"))
                    nearest_right = clean(right_record.get("atom_code"))
        rows.append(
            {
                "left": left,
                "right": right,
                "level": level,
                "distance_value": nearest_distance,
                "nearest_left_atom": nearest_left,
                "nearest_right_atom": nearest_right,
                "same_atom_count": len(same_atom),
                "same_scene_count": len(same_scene),
                "same_event_count": len(same_event),
                "same_time_block_count": len(same_time),
                "left_points": len(left_points.get("atom_id", set())),
                "right_points": len(right_points.get("atom_id", set())),
            }
        )
    return rows


def pairwise_summary(matrix: list[dict[str, Any]]) -> str:
    if not matrix:
        return "单词查询，未形成两两矩阵"
    counts = defaultdict(int)
    for row in matrix:
        counts[clean(row.get("level"))] += 1
    order = ["same_atom", "same_scene", "same_event", "same_time_block", "no_container_intersection"]
    return "；".join(f"{level}={counts[level]}" for level in order if counts[level])


def schedule_query_types(question: str, terms: list[str], route_context: str = "") -> list[str]:
    text = clean(f"{question}\n{route_context}")
    query_types: list[str] = []
    if terms:
        query_types.append("词位")
    if re.search(r"人|谁|宝玉|黛玉|春|夏|秋|冬|季|空间|哪里|房|院|园|物|花|灯|鸡|狗|药|同场|事件", text):
        query_types.append("坐标")
    if re.search(r"最近|靠近|相邻|接近|距离|离得", text):
        query_types.append("距离")
    if re.search(r"同场|同时|一起|共同|共现|在场", text):
        query_types.append("共场")
    if re.search(r"第一次|首次|最早|全书|全文|全部|所有|哪里|哪一回", text):
        query_types.append("全量")
    if re.search(r"比较|对照|两组|关系|阶段", text) or len(terms) >= 3:
        query_types.append("综合")
    if "梦" in text and re.search(r"自己|亲口|自述|说.*梦|梦.*说|醒后|醒來|醒来|讲.*梦|說.*夢|夢.*說", text):
        query_types.append("自述梦裁判")
    query_types.append("原文")
    return list(dict.fromkeys(query_types))


def evidence_layer(record: dict[str, Any]) -> str:
    if clean(record.get("hit_source")) == "term" and record.get("start_char") is not None:
        return "原文句"
    if clean(record.get("hit_source")) == "term":
        return "全文词位"
    if clean(record.get("hit_source")) == "variable":
        variable_type = clean(record.get("variable_type"))
        if variable_type:
            return f"工程变量点:{variable_type}"
        return "工程变量点"
    if clean(record.get("summary")) and not clean(record.get("quote")):
        return "段落摘要"
    return "工程推定"


def self_report_dream_rule(question: str, route_context: str) -> str:
    text = clean(f"{question}\n{route_context}")
    if "梦" not in text:
        return ""
    if not re.search(r"自己|亲口|自述|说.*梦|梦.*说|醒后|醒來|醒来|讲.*梦|說.*夢|夢.*說", text):
        return ""
    return (
        "自述梦裁判：必须区分叙述者说明、梦中人物台词、醒后本人复述、他人转述；"
        "只有醒后本人在说话边界内复述梦，才能升级为主证。"
    )


def compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "hit_value": clean(record.get("hit_value")),
        "hit_source": clean(record.get("hit_source")),
        "variable_type": clean(record.get("variable_type")),
        "variable_value_name": clean(record.get("variable_value_name")),
        "confidence": record.get("confidence"),
        "chapter_no": record.get("chapter_no"),
        "atom_id": clean(record.get("atom_id")),
        "atom_code": clean(record.get("atom_code")),
        "old_segment_no": clean(record.get("old_segment_no")),
        "global_atom_order": record.get("global_atom_order"),
        "scene_id": clean(record.get("scene_id")),
        "event_id": clean(record.get("event_id")),
        "time_block_id": clean(record.get("time_block_id")),
        "start_char": record.get("start_char"),
        "end_char": record.get("end_char"),
        "cross_atom": record.get("cross_atom"),
        "summary": clean(record.get("summary")),
        "evidence_layer": evidence_layer(record),
        "source_sentence": source_sentence(record.get("chapter_no") or 0, record.get("start_char"), record.get("quote")),
    }


def material_status(rows: list[dict[str, Any]], warnings: list[str]) -> str:
    if not rows:
        return "不足以入池"
    if any("需补证" in warning for warning in warnings):
        return "需补证"
    return "可入池"


def material_pack(question: str, route_context: str = "", limit: int = 80) -> list[dict[str, Any]]:
    profile = guidance_profile(question, route_context)
    terms = profile["terms"]
    limit = max(10, min(int(limit or 80), 240))
    query_types = schedule_query_types(question, terms, route_context)
    preflight = coordinate_preflight_tokens(question, route_context, terms, query_types)
    if not preflight["ok"]:
        return []
    if not terms:
        return []

    hit_records: list[dict[str, Any]] = []
    person_profile = profile.get("person_normalization") or {}
    person_packages: dict[str, dict[str, Any]] = person_profile.get("canonical_to_package") or {}
    alias_expansions: dict[str, list[str]] = person_profile.get("alias_expansions") or {}
    for term in terms:
        if term in person_packages:
            hit_records.extend(find_term(term))
            for alias in alias_expansions.get(term, [])[:12]:
                if alias != term:
                    for alias_record in find_term(alias):
                        alias_record["matched_alias"] = alias
                        alias_record["hit_value"] = term
                        hit_records.append(alias_record)
            for record in find_variable(term, variable_type="person", exact=True):
                record["person_character_key"] = clean(person_packages[term].get("character_key"))
                record["person_canonical_name"] = term
                record["person_normalization_source"] = clean(person_packages[term].get("source"))
                hit_records.append(record)
        else:
            hit_records.extend(find_term(term))
            hit_records.extend(find_variable_for_term(term))
    hit_records = dedupe_hit_records(hit_records)

    matrix = pairwise_matrix(terms, hit_records)
    matrix_summary = pairwise_summary(matrix)
    no_intersection_pairs = [row for row in matrix if row.get("level") == "no_container_intersection"]
    warnings: list[str] = []
    if no_intersection_pairs:
        warnings.append(f"{len(no_intersection_pairs)}组两两关系没有共同容器，只能按近邻或回原文补证。")
    if preflight.get("missing_optional"):
        warnings.append("坐标预检可补令牌缺失：" + "、".join(preflight["missing_optional"]))
    if "全量" in query_types:
        warnings.append("题目触发全量/最早/哪里类调度，必须按回序和字位排序复核。")
    dream_rule = self_report_dream_rule(question, route_context)
    if dream_rule:
        warnings.append(dream_rule)
    if not hit_records:
        warnings.append("需补证：入口词没有形成词位或坐标命中。")
    exhaustive_status = "穷尽法已接入：每个入口词先查全文词位，再查变量投影；非人物/小词/物象由词位库补点。"
    if graph_runtime is not None:
        try:
            need = graph_runtime.decide_exhaustive_tool_need(
                question,
                terms,
                {"candidate_line_count": len({clean(row.get("atom_id")) for row in hit_records if clean(row.get("atom_id"))})},
            )
            exhaustive_status = f"穷尽法判断：{'应考虑' if need.get('should_consider') else '旁路备选'}；{clean(need.get('reason'))}"
        except Exception:
            pass

    scene_hits = container_counts(hit_records, "scene_id")
    event_hits = container_counts(hit_records, "event_id")
    time_hits = container_counts(hit_records, "time_block_id")
    term_hits = [compact_record(record) for record in hit_records if clean(record.get("hit_source")) == "term"][:120]
    coordinate_hits = [compact_record(record) for record in hit_records if clean(record.get("hit_source")) == "variable"][:120]
    variables = sorted(
        {
            f"{clean(record.get('variable_type'))}={clean(record.get('variable_value_name'))}"
            for record in hit_records
            if clean(record.get("hit_source")) == "variable" and clean(record.get("variable_value_name"))
        }
    )

    by_atom: dict[str, dict[str, Any]] = {}
    atom_terms: dict[str, set[str]] = defaultdict(set)
    atom_sources: dict[str, set[str]] = defaultdict(set)
    atom_variables: dict[str, set[str]] = defaultdict(set)
    atom_evidence_grades: dict[str, set[str]] = defaultdict(set)
    atom_grade_bonus: dict[str, int] = defaultdict(int)
    for record in hit_records:
        atom_id = clean(record.get("atom_id"))
        if not atom_id:
            continue
        current = by_atom.setdefault(atom_id, dict(record))
        value = clean(record.get("hit_value"))
        source = clean(record.get("hit_source"))
        if value:
            atom_terms[atom_id].add(value)
        if source:
            atom_sources[atom_id].add(source)
        if source == "variable":
            grade, bonus = variable_evidence_grade(record)
            atom_variables[atom_id].add(f"{record.get('variable_type')}={record.get('variable_value_name')}[{grade}]")
            atom_evidence_grades[atom_id].add(grade)
            atom_grade_bonus[atom_id] += bonus
        if len(clean(record.get("quote"))) > len(clean(current.get("quote"))):
            current["quote"] = record.get("quote")

    rows: list[dict[str, Any]] = []
    person_names = set((person_profile.get("canonical_names") or []))
    focus_terms = {term for term in terms if term not in person_names}
    for atom_id, record in by_atom.items():
        scene_id = clean(record.get("scene_id"))
        event_id = clean(record.get("event_id"))
        time_block_id = clean(record.get("time_block_id"))
        direct_terms = atom_terms[atom_id]
        scene_terms = scene_hits.get(scene_id, set())
        event_terms = event_hits.get(event_id, set())
        time_terms = time_hits.get(time_block_id, set())
        score = (
            len(direct_terms) * 1200
            + len(scene_terms) * 420
            + len(event_terms) * 260
            + len(time_terms) * 120
            + (300 if {"term", "variable"}.issubset(atom_sources[atom_id]) else 0)
            + min(atom_grade_bonus[atom_id], 1800)
        )
        focus_direct_count = len(direct_terms & focus_terms)
        score += focus_direct_count * 2500
        if len(terms) >= 2 and not focus_direct_count and max(len(scene_terms), len(event_terms), len(time_terms)) < len(terms):
            score -= 1000
        if len(scene_terms) >= len(terms):
            score += 1800
        elif len(event_terms) >= len(terms):
            score += 1000
        reasons = [
            "坐标取材",
            f"直接命中：{'、'.join(sorted(direct_terms)) or '无'}",
            f"同场覆盖：{len(scene_terms)}/{len(terms)}",
            f"同事件覆盖：{len(event_terms)}/{len(terms)}",
            f"同时间块覆盖：{len(time_terms)}/{len(terms)}",
            f"两两矩阵：{matrix_summary}",
        ]
        if atom_variables[atom_id]:
            reasons.append("变量点：" + "、".join(sorted(atom_variables[atom_id])[:8]))
        if atom_evidence_grades[atom_id]:
            reasons.append("证据等级：" + "、".join(sorted(atom_evidence_grades[atom_id])))
        rows.append(
            {
                "subquestion_order": 0,
                "dimension": "坐标取材",
                "subquestion": "坐标门取材：正文词位、变量点、同场/同事件/同时间块共同收点。",
                "segment_no": clean(record.get("old_segment_no")),
                "chapter_no": record.get("chapter_no"),
                "chapter_title": "",
                "score": score,
                "summary": clean(record.get("summary")),
                "quote": clean(record.get("quote")),
                "source_sentence": source_sentence(record.get("chapter_no") or 0, record.get("start_char"), record.get("quote")),
                "reasons": "；".join(reasons),
                "direct_edge_hits": 0,
                "matched_characters": len(direct_terms),
                "recall_gate": "coordinate",
                "recall_method": "term_position + variable_projection + container_cooccurrence",
                "source_scope": "formal_coordinate_db",
                "source_db": str(VARIABLE_DB),
                "source_table": "v_term_hits / variable_points / atom_coordinates",
                "source_trace": f"{TERM_DB.name}:v_term_hits；{VARIABLE_DB.name}:variable_points/atom_coordinates；{CHAR_DB.name}:v_char_hits",
                "atom_id": atom_id,
                "atom_code": clean(record.get("atom_code")),
                "global_atom_order": record.get("global_atom_order"),
                "cluster_id": clean(record.get("cluster_id")),
                "event_id": clean(record.get("event_id")),
                "scene_id": scene_id,
                "scene_group_id": clean(record.get("scene_group_id")),
                "time_block_id": time_block_id,
                "coordinate_direct_terms": "、".join(sorted(direct_terms)),
                "coordinate_scene_terms": "、".join(sorted(scene_terms)),
                "coordinate_event_terms": "、".join(sorted(event_terms)),
                "distance_basis": f"same_scene={len(scene_terms)}/{len(terms)}; same_event={len(event_terms)}/{len(terms)}; same_time_block={len(time_terms)}/{len(terms)}",
                "coordinate_evidence_grades": "、".join(sorted(atom_evidence_grades[atom_id])),
                "coordinate_shared_eight_step_rule": "坐标头服从完整八步法；取词之前的思考与聚拢头相同，取词以后改走坐标分析法。",
                "coordinate_after_terms_strategy": "词位穷尽防漏 -> 变量坐标定点 -> atom/scene/event/time_block 收点 -> 两两交集/近邻测距 -> 容器归属放大 -> 原文句回查 -> 材料池裁判",
                "coordinate_method_profile": SHARED_EIGHT_STEP_FORMULA,
                "coordinate_tool_detail": "Codex入口词令牌 + 70/72全人物归一包 + 126根字宽网 + 词位/变量/字位桥表 + 距离/共场/来源交集",
                "coordinate_guidance_basis": profile["basis"],
                "coordinate_tool_usage_guide": COORDINATE_TOOL_USAGE_GUIDE,
                "coordinate_preflight_status": "通过",
                "coordinate_preflight_rule": preflight["rule"],
                "coordinate_preflight_tokens": json.dumps(preflight["tokens"], ensure_ascii=False),
                "coordinate_missing_required_tokens": "、".join(preflight["missing_required"]),
                "coordinate_missing_optional_tokens": "、".join(preflight["missing_optional"]),
                "coordinate_term_token_pack": "、".join(terms),
                "coordinate_root_terms_126": "、".join(profile.get("root_terms") or []),
                "coordinate_term_roles": clean(profile.get("term_roles")),
                "person_normalization_status": clean((profile.get("person_normalization") or {}).get("status")),
                "person_normalized_terms": "、".join((profile.get("person_normalization") or {}).get("canonical_names") or []),
                "person_character_keys": "、".join((profile.get("person_normalization") or {}).get("character_keys") or []),
                "person_alias_expansions": json.dumps((profile.get("person_normalization") or {}).get("alias_expansions") or {}, ensure_ascii=False),
                "coordinate_pairwise_summary": matrix_summary,
                "coordinate_pairwise_matrix": json.dumps(matrix, ensure_ascii=False),
                "coordinate_exhaustive_status": exhaustive_status,
                "coordinate_return_rule": "坐标门走同一八步主线，但本程序只完成到入材料池凭证；第8步写答案必须等待材料池四态、精读材料词和写作前原文追证。",
                "coordinate_term_bag_rule": "入口词沿用已搬入的 Codex 查询词袋规则；不另造分词器或编译器。代词/角色词如“我、你、他、自己”不得作为主查词，只能作为说话边界或裁判条件。",
                "final_answer_status": "不可作答，需回原文裁判",
                "self_report_dream_rule": dream_rule,
                "evidence_layer": evidence_layer(record),
                "material_query_type": " / ".join(query_types),
                "material_variables": "；".join(variables[:40]),
                "material_term_hits": json.dumps(term_hits[:30], ensure_ascii=False),
                "material_coordinate_hits": json.dumps(coordinate_hits[:30], ensure_ascii=False),
                "material_nearest_pairs": json.dumps(matrix[:60], ensure_ascii=False),
                "material_cooccurrence": json.dumps(
                    {
                        "same_atom_or_direct": sorted(direct_terms),
                        "same_scene": sorted(scene_terms),
                        "same_event": sorted(event_terms),
                        "same_time_block": sorted(time_terms),
                    },
                    ensure_ascii=False,
                ),
                "material_source_atoms": json.dumps(
                    [
                        {
                            "atom_id": atom_id,
                            "atom_code": clean(record.get("atom_code")),
                            "segment_no": clean(record.get("old_segment_no")),
                            "chapter_no": record.get("chapter_no"),
                            "summary": clean(record.get("summary")),
                        }
                    ],
                    ensure_ascii=False,
                ),
                "material_source_sentences": json.dumps(
                    [source_sentence(record.get("chapter_no") or 0, record.get("start_char"), record.get("quote"))],
                    ensure_ascii=False,
                ),
                "material_warnings": "；".join(warnings),
                "material_status": "需补证" if any("需补证" in warning for warning in warnings) else "可入池",
                "candidate_display_policy": "坐标门候选；可展开编号、同场、同事件和原文句。",
                "codex_evidence_hard_gate": "坐标门只负责取材和编号裁判入口；仍须回原文和材料池四态判定。",
                "codex_query_lane": "P1_坐标路径_正文落点与变量投影",
                "codex_query_lane_rank": 1,
                "codex_query_lane_reason": "用户触发坐标门，优先用词位、字位和变量投影取材。",
            }
        )
    rows.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            int(item.get("chapter_no") or 0),
            int(item.get("global_atom_order") or 0),
        )
    )
    return rows[:limit]


def material_pack_bundle(question: str, route_context: str = "", limit: int = 80) -> dict[str, Any]:
    rows = material_pack(question, route_context=route_context, limit=limit)
    if not rows:
        terms = query_terms(question, route_context)
        query_types = schedule_query_types(question, terms, route_context)
        preflight = coordinate_preflight_tokens(question, route_context, terms, query_types)
        return {
            "question": question,
            "query_head": "进入坐标查询",
            "lane": "coordinate",
            "shared_eight_step_spine": SHARED_EIGHT_STEP_SPINE,
            "shared_eight_step_formula": SHARED_EIGHT_STEP_FORMULA,
            "tool_difference_only": True,
            "query_type": query_types,
            "variables": [],
            "term_hits": [],
            "coordinate_hits": [],
            "nearest_pairs": [],
            "cooccurrence": {},
            "source_atoms": [],
            "source_sentences": [],
            "warnings": ["坐标预检未通过：" + "、".join(preflight["missing_required"] or ["无候选材料"])],
            "status": "需补证",
            "final_answer_status": "不可作答，需回原文裁判",
            "evidence_layers": [],
            "preflight": preflight,
            "rows": [],
        }
    query_types = rows[0].get("material_query_type", "").split(" / ") if rows else []
    warnings = split_terms(rows[0].get("material_warnings", "")) if rows else ["需补证：未形成候选材料包。"]
    return {
        "question": question,
        "query_head": "进入坐标查询",
        "lane": "coordinate",
        "shared_eight_step_spine": SHARED_EIGHT_STEP_SPINE,
        "shared_eight_step_formula": SHARED_EIGHT_STEP_FORMULA,
        "tool_difference_only": True,
        "query_type": [term for term in query_types if term],
        "variables": split_terms(rows[0].get("material_variables", "")) if rows else [],
        "term_hits": json.loads(rows[0].get("material_term_hits") or "[]") if rows else [],
        "coordinate_hits": json.loads(rows[0].get("material_coordinate_hits") or "[]") if rows else [],
        "nearest_pairs": json.loads(rows[0].get("material_nearest_pairs") or "[]") if rows else [],
        "cooccurrence": json.loads(rows[0].get("material_cooccurrence") or "{}") if rows else {},
        "source_atoms": [json.loads(row.get("material_source_atoms") or "[]")[0] for row in rows if row.get("material_source_atoms")],
        "source_sentences": [json.loads(row.get("material_source_sentences") or "[]")[0] for row in rows if row.get("material_source_sentences")],
        "warnings": warnings,
        "status": material_status(rows, warnings),
        "final_answer_status": "不可作答，需回原文裁判",
        "evidence_layers": sorted({clean(row.get("evidence_layer")) for row in rows if clean(row.get("evidence_layer"))}),
        "rows": rows,
    }
