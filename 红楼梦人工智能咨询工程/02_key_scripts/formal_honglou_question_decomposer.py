#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import formal_honglou_evidence_pack as evidence_pack
from formal_honglou_text_normalizer import normalize_for_match


OUT_DIR = ROOT / "outputs" / "正式底库复杂拆题器原型"
DEFAULT_QUESTION = "这个问题应该如何进入红楼梦工程查证？"
KNOWN_TERMS = [
    "贾宝玉",
    "林黛玉",
    "薛宝钗",
    "王熙凤",
    "贾母",
    "甄士隐",
    "空空道人",
    "茫茫大士",
    "渺渺真人",
    "警幻仙姑",
    "通灵宝玉",
    "顽石",
    "神瑛侍者",
    "绛珠仙草",
    "青埂峰",
    "太虚幻境",
    "薄命司",
    "木石前盟",
    "木石",
    "金玉良缘",
    "金玉",
    "还泪",
    "葬花",
    "葬花吟",
    "葬花词",
    "伤春",
    "花冢",
    "花落人亡",
    "质本洁来还洁去",
    "题帕",
    "旧帕",
    "手帕",
    "鲛绡",
    "文字凭证",
    "焚稿",
    "结局",
    "成婚",
    "婚姻",
    "冲喜",
    "死亡",
    "病逝",
    "亡故",
    "出家",
    "佛门",
    "道心",
    "情",
    "空",
    "幻",
]

GENERIC_SEARCH_TERMS = {
    "情",
    "空",
    "幻",
    "诗",
    "词",
    "原文",
    "段落",
    "问题",
    "普通",
    "为什么",
    "怎么",
    "怎样",
    "如何",
    "不是",
}

QUESTION_WORDS = ["为什么", "怎么", "怎样", "如何", "是不是", "不是", "普通", "？", "?"]
TASK_INSTRUCTION_MARKERS = [
    "哪些地方",
    "比较强烈",
    "包括",
    "等等",
    "也都算",
    "从全文",
    "全文搜索",
    "搜索",
    "找出",
    "重要事实",
    "说明",
    "关联",
    "每个事实",
    "尽量",
    "回到",
    "原文段落",
    "上下文",
    "请",
]
RELATION_TERM_EXPANSIONS = {
    "宝黛": ["贾宝玉", "林黛玉", "宝玉", "黛玉"],
    "钗黛": ["薛宝钗", "林黛玉", "宝钗", "黛玉"],
    "宝钗黛": ["贾宝玉", "薛宝钗", "林黛玉", "宝玉", "宝钗", "黛玉"],
    "宝黛钗": ["贾宝玉", "林黛玉", "薛宝钗", "宝玉", "黛玉", "宝钗"],
}

LEXICAL_SEARCH_EXPANSIONS = {
    "题帕": ["题帕", "题帕三绝", "旧帕", "手帕", "帕", "鲛绡", "尺幅", "解赠", "题诗", "诗稿", "焚稿", "晴雯"],
    "旧帕": ["题帕", "旧帕", "手帕", "帕", "鲛绡", "题诗", "诗稿", "焚稿", "晴雯"],
    "手帕": ["题帕", "旧帕", "手帕", "帕", "鲛绡", "题诗", "诗稿", "焚稿", "晴雯"],
    "文字凭证": ["文字凭证", "题诗", "题帕", "诗稿", "旧帕", "焚稿", "帕"],
    "定情物": ["定情", "赠", "送", "旧帕", "手帕", "题诗", "宝玉", "黛玉"],
    "葬花": ["葬花", "葬花吟", "葬花词", "花冢", "落花", "花落人亡", "质本洁来还洁去"],
    "金玉": ["金玉", "金锁", "通灵宝玉", "莫失莫忘", "不离不弃", "好姻缘"],
    "木石": ["木石", "木石前盟", "绛珠", "神瑛", "还泪"],
}


@dataclass
class SubQuestion:
    order: int
    dimension: str
    question: str
    purpose: str
    entities: list[str]
    keywords: list[str]
    preferred_axes: list[str]
    evidence_expectation: str
    source_layers: list[str] | None = None


def terms_from_question(question: str) -> list[str]:
    question_norm = normalize_for_match(question)
    terms = [term for term in KNOWN_TERMS if normalize_for_match(term) in question_norm]
    terms.extend(evidence_pack.clean_terms([question]))
    cleaned = []
    seen = set()
    for term in terms:
        term = normalize_search_term(term)
        if not is_searchable_term(term):
            continue
        if term and term not in seen:
            seen.add(term)
            cleaned.append(term)
    return cleaned[:16] or [question[:18]]


def lexical_expansion_terms(question: str, base_terms: list[str]) -> list[str]:
    question_norm = normalize_for_match(question)
    values: list[str] = []
    for key, expansions in RELATION_TERM_EXPANSIONS.items():
        if normalize_for_match(key) in question_norm:
            values.extend(expansions)
    for key, expansions in LEXICAL_SEARCH_EXPANSIONS.items():
        key_norm = normalize_for_match(key)
        if key_norm in question_norm or any(key_norm in normalize_for_match(term) for term in base_terms):
            values.extend(expansions)
    return values


def significant_search_terms(values: list[str], limit: int = 30) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for term in values:
        value = normalize_search_term(term)
        if not value or value in seen:
            continue
        if not is_searchable_term(value):
            continue
        if value in GENERIC_SEARCH_TERMS:
            continue
        seen.add(value)
        result.append(value)
        if limit > 0 and len(result) >= limit:
            return result
    return result


def split_aliases(value: object) -> list[str]:
    text = str(value or "")
    for sep in ["；", ";", "、", ",", "，", "\n"]:
        text = text.replace(sep, " ")
    aliases: list[str] = []
    for raw in text.split():
        item = raw.strip()
        if not item or "[" in item or "]" in item:
            continue
        aliases.append(item)
    return aliases


@lru_cache(maxsize=256)
def _expand_character_alias_terms_cached(raw_terms: tuple[str, ...], limit: int) -> tuple[str, ...]:
    expanded: list[str] = []
    seen: set[str] = set()

    def add(term: object) -> None:
        value = str(term or "").strip()
        if not value or len(value) > 18 or value in seen:
            return
        seen.add(value)
        expanded.append(value)

    for term in raw_terms:
        add(term)
    try:
        conn = evidence_pack.connect()
        for term in raw_terms:
            if term in GENERIC_SEARCH_TERMS or len(term) == 1:
                continue
            normalized_term = normalize_for_match(term)
            if not normalized_term:
                continue
            rows = conn.execute(
                """
                SELECT name, aliases
                FROM characters
                WHERE hlm_norm(name) = ?
                   OR hlm_norm(aliases) LIKE ?
                ORDER BY character_code
                """,
                (normalized_term, f"%{normalized_term}%"),
            ).fetchall()
            for row in rows:
                aliases = split_aliases(row["aliases"])
                alias_norms = [normalize_for_match(alias) for alias in aliases]
                if normalize_for_match(row["name"]) != normalized_term and normalized_term not in alias_norms:
                    continue
                add(row["name"] or "")
                for alias in aliases:
                    if len(alias) <= 8:
                        add(alias)
                if limit > 0 and len(expanded) >= limit:
                    return tuple(expanded[:limit])
    except Exception:
        return tuple(expanded[:limit]) if limit > 0 else tuple(expanded)
    return tuple(expanded[:limit]) if limit > 0 else tuple(expanded)


def expand_character_alias_terms(terms: list[str], limit: int = 0) -> list[str]:
    cleaned = tuple(term for term in terms if str(term or "").strip())
    return list(_expand_character_alias_terms_cached(cleaned, limit))


def split_terms(value: str) -> list[str]:
    for sep in ["、", "，", ",", "/", "；", ";"]:
        value = value.replace(sep, " ")
    return [term.strip() for term in value.split() if term.strip()]


def is_searchable_term(term: object) -> bool:
    value = normalize_search_term(term)
    if not value:
        return False
    if len(value) > 16:
        return False
    if any(word in value for word in QUESTION_WORDS):
        return False
    if any(marker in value for marker in TASK_INSTRUCTION_MARKERS) and len(value) > 4:
        return False
    if re.search(r"[。！？?!；;：:]", value):
        return False
    if "《" in value or "》" in value:
        return False
    return True


def normalize_search_term(term: object) -> str:
    value = str(term or "").strip()
    for prefix in ["比如", "例如", "譬如", "如", "像"]:
        if value.startswith(prefix) and len(value) > len(prefix) + 1:
            value = value[len(prefix):].strip()
            break
    return value


def unique_terms(values: list[str], limit: int = 0) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in split_terms(str(value)):
            if not term or len(term) > 18 or term in seen:
                continue
            seen.add(term)
            result.append(term)
            if limit > 0 and len(result) >= limit:
                return result
    return result


ROUTE_CONTEXT_CENTERS = {
    "Codex策略入口": {
        "anchor_type": "Codex策略入口",
        "starting_bus": "codex -> project index -> source review",
        "libraries": ["全文检索库", "段落库", "章节真源库", "多轴底库"],
        "terms": [],
        "guidance": "Codex 根据题目语义、经验仓和工程库线判断题目中心、关键词组、证据路径和补查方向。",
    },
    "原文优先": {
        "anchor_type": "原文优先",
        "starting_bus": "question -> chapter/source text",
        "libraries": ["全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "先回原文和上下文，由原文位置反推关键词和底库映射。",
    },
    "底库优先": {
        "anchor_type": "底库优先",
        "starting_bus": "question -> axis db -> source text",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "先用底库关系缩小范围，再回原文复核；底库命中不能直接成为答案。",
    },
    "库文双向": {
        "anchor_type": "库文双向",
        "starting_bus": "question -> axis db <-> source text",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "底库命中后回原文，原文命中后回底库，双向校验后进入材料池。",
    },
    "共现查证": {
        "anchor_type": "共现查证",
        "starting_bus": "codex inferred terms -> source co-reading",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 从题目中判断需要共同出现、互相照应或同场复核的对象；分别查、组合查、回原文上下文复核，不预置具体答案词。",
    },
    "人物域": {
        "anchor_type": "人物域",
        "starting_bus": "codex inferred character field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断人物、别名、关系人和言行线索，再回原文核验。",
    },
    "物象域": {
        "anchor_type": "物象域",
        "starting_bus": "codex inferred object field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断物件、意象、器物、文本对象及其相关人物和场景，再回原文复核其功能。",
    },
    "事件域": {
        "anchor_type": "事件域",
        "starting_bus": "codex inferred event field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断事件起点、转折、结果和相关人物，再按原文因果链复核。",
    },
    "关系域": {
        "anchor_type": "关系域",
        "starting_bus": "codex inferred relation field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断人物关系、物件关系、空间关系或观念关系，再找共同段落和互证材料。",
    },
    "诗词文本域": {
        "anchor_type": "诗词文本域",
        "starting_bus": "codex inferred text field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断诗词、判词、回目、原句或文本对象，再回到出现处和上下文解释。",
    },
    "空间域": {
        "anchor_type": "空间域",
        "starting_bus": "codex inferred space field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断地点、场景、人物移动和空间关系，再回原文复核场景功能。",
    },
    "章节原句": {
        "anchor_type": "章节原句",
        "starting_bus": "codex inferred quote/chapter -> source review",
        "libraries": ["全文检索库", "段落库", "章节真源库", "多轴底库"],
        "terms": [],
        "guidance": "由 Codex 先定位回目、段落、原句或上下文，再判断是否需要回底库补证。",
    },
    "观念主题": {
        "anchor_type": "观念主题",
        "starting_bus": "codex inferred theme field -> source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库"],
        "terms": [],
        "guidance": "由 Codex 判断主题概念和相关证据群，先找材料再形成判断，不套固定模板。",
    },
    "深度补证": {
        "anchor_type": "深度补证",
        "starting_bus": "question -> codex route -> repeated source review",
        "libraries": ["多轴底库", "全文检索库", "段落库", "章节真源库", "生成文件索引"],
        "terms": [],
        "guidance": "第一轮材料不足时，由 Codex 反推新关键词、新来源和二次复核路径。",
    },
}

ROUTE_CONTEXT_ACTIONS = ["原文显性词", "扩展关键词", "库轴映射", "章节顺查", "跨回追踪", "双向校验", "反证排除"]
ROUTE_CONTEXT_ORDERS = ["先原文后库", "先库轴后原文", "先关键词后原文", "先章节顺读再跨回", "先反证排除再回答", "多路并行再回原文"]


def _infer_route_mode(text: str, centers: list[str], codex_terms: list[str], actions: list[str], depth: str, output: str, order: str) -> tuple[str, str]:
    normalized = clean_context_line(text)
    if not normalized:
        return "标准", ""

    centers_text = "、".join(centers)
    marker = context_value(text, "档位")
    if marker:
        if "短平快" in marker or "快速" in marker:
            return "短平快关系题", f"档位标签命中：{marker}"
    quick_keywords = [
        "短平快",
        "快速",
        "快速问答",
        "轻量",
        "一次命中",
        "直接进入最终答案",
        "不触发00N",
        "若00M证据闭合",
        "直接答",
    ]
    for keyword in quick_keywords:
        if keyword in normalized:
            return "短平快关系题", f"路径文本命中快速信号：{keyword}"

    if any(item in depth for item in ["轻量", "快速", "短平快", "快"]):
        return "短平快关系题", "运行深度要求快速"

    if any(item in order for item in ["轻量", "快速", "短平快", "快"]):
        return "短平快关系题", "查证顺序要求快速"

    if any(item in output for item in ["快速", "先正面回答", "直接", "短答"]):
        return "短平快关系题", "优先回显要求快速"

    if not codex_terms:
        return "标准", "无查询词"

    direct_question_hit = any(
        item in normalized
        for item in ["是谁", "谁是", "叫什么", "名字", "姓什么", "姓甚", "哪一个", "哪位", "哪个"]
    )
    if direct_question_hit:
        return "短平快关系题", "原问题是短答定位问法，优先直达"

    if any(item in centers_text for item in ["章节原句", "章节原句线", "回目"]):
        if len(codex_terms) <= 2:
            return "短平快关系题", "章节定位类任务"

    short_query_hit = any(
        len(term) <= 22 and (
            "第" in term
            and "回" in term
            or "是谁" in term
            or "叫什么" in term
            or "姓" in term
            or "哪" in term
        )
        for term in codex_terms
    )
    if short_query_hit:
        return "短平快关系题", "查询词带定位问法，优先直达"

    if "关系" in centers_text and len(actions) <= 2 and any(item in depth for item in ["标准", "中", "深"]):
        if len(codex_terms) <= 3:
            return "短平快关系题", "关系类低复杂度查询"

    return "标准", ""


def clean_context_line(text: str, limit: int = 700) -> str:
    return " ".join(str(text or "").split())[:limit]


CONTEXT_LABELS = (
    "Codex查询词",
    "Codex查询词策略",
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
    "Codex词角色",
    "Codex强复合",
    "Codex查证顺序",
    "Codex材料升级条件",
    "Codex优先库",
    "Codex经验路径",
    "Codex词角色",
    "主查人物",
    "主查物象",
    "主查物件",
    "主查器物",
    "主查空间",
    "主查时间",
    "材料来源",
    "运行深度",
    "优先回显",
    "表达",
)


def normalize_labeled_context(text: str) -> str:
    normalized = str(text or "")
    labels = "|".join(re.escape(label) for label in CONTEXT_LABELS)
    normalized = re.sub(rf"\s+(?=(?:{labels})\s*[：:])", "\n", normalized)
    normalized = re.sub(r"\s*[｜|]\s*(?=\S+?[：:])", "\n", normalized)
    return normalized


def context_value(text: str, label: str) -> str:
    text = normalize_labeled_context(text)
    marker = f"{label}："
    if marker not in text:
        return ""
    value = text.split(marker, 1)[1]
    for sep in ["｜", "\n"]:
        if sep in value:
            value = value.split(sep, 1)[0]
    return value.strip()


def context_line_value(text: str, label: str) -> str:
    text = normalize_labeled_context(text)
    marker = f"{label}："
    if marker not in text:
        return ""
    value = text.split(marker, 1)[1]
    for sep in ["｜", "|", "\n"]:
        if sep in value:
            value = value.split(sep, 1)[0]
    return value.strip()


def context_compound_groups(text: str, label: str) -> list[list[str]]:
    value = context_value(text, label)
    if not value:
        return []
    groups: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for clause in re.split(r"[；;]", value):
        for group_text in re.split(r"\s*(?:\+|＋)\s*", clause):
            group_terms = split_terms(
                group_text.replace("｜", " ").replace("|", " ").replace("/", " ")
            )
            group_terms = significant_search_terms(group_terms, limit=0)
            marker = tuple(group_terms)
            if group_terms and marker not in seen:
                seen.add(marker)
                groups.append(group_terms)
    return groups


def context_role_terms(text: str, role_label: str) -> list[str]:
    value = context_line_value(text, "Codex词角色")
    if not value:
        direct = context_value(text, role_label)
        if not direct:
            direct = context_line_value(text, role_label)
        return significant_search_terms(split_terms(direct), limit=0) if direct else []
    for chunk in re.split(r"[；;]", value):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith(f"{role_label}=") or chunk.startswith(f"{role_label}:") or chunk.startswith(f"{role_label}："):
            raw = re.split(r"[=：:]", chunk, 1)[1] if re.search(r"[=：:]", chunk) else ""
            return significant_search_terms(split_terms(raw), limit=0)
    direct = context_value(text, role_label)
    if not direct:
        direct = context_line_value(text, role_label)
    if direct:
        return significant_search_terms(split_terms(direct), limit=0)
    return []


def _terms_related(left: str, right: str) -> bool:
    left_norm = normalize_for_match(left)
    right_norm = normalize_for_match(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    shorter, longer = sorted([left_norm, right_norm], key=len)
    return len(shorter) >= 1 and shorter in longer and len(longer) <= max(4, len(shorter) + 3)


def _compound_term_allowed_by_primary(term: str, primary_terms: list[str]) -> bool:
    term_norm = normalize_for_match(term)
    if not term_norm:
        return False
    for primary in primary_terms:
        primary_norm = normalize_for_match(primary)
        if not primary_norm:
            continue
        if term_norm == primary_norm:
            return True
        if len(primary_norm) == 1 and primary_norm in term_norm:
            return True
        if len(term_norm) >= 2 and len(primary_norm) >= 2 and _terms_related(term_norm, primary_norm):
            return True
    return False


def compact_strategy_terms(values: list[str], *, limit: int = 10) -> list[str]:
    """Keep the first retrieval pass small; background/expansion terms stay in route_context."""
    terms = significant_search_terms(values, limit=0)
    compact: list[str] = []
    seen_norms: set[str] = set()

    def add(term: str) -> None:
        value = normalize_search_term(term)
        norm = normalize_for_match(value)
        if not value or not norm or norm in seen_norms:
            return
        if any(existing and (existing in norm or norm in existing) for existing in seen_norms):
            if len(norm) > 1:
                return
        seen_norms.add(norm)
        compact.append(value)

    for term in terms:
        add(term)
        if limit > 0 and len(compact) >= limit:
            break
    return compact


def compact_compound_query_terms(groups: list[list[str]], *, max_per_group: int = 2, limit: int = 8) -> list[str]:
    """Translate Codex strong compound axes into a concise executable first-pass term set."""
    values: list[str] = []
    for group in groups:
        cleaned = significant_search_terms([str(term) for term in group if str(term or "").strip()], limit=0)
        if not cleaned:
            continue
        one_char_terms = [term for term in cleaned if len(normalize_for_match(term)) == 1]
        selected: list[str] = []
        if one_char_terms:
            selected.append(one_char_terms[0])
            first = cleaned[0]
            if first not in selected and len(selected) < max_per_group:
                selected.insert(0, first)
        else:
            selected.extend(cleaned[:max_per_group])
        values.extend(selected[:max_per_group])
    return compact_strategy_terms(values, limit=limit)


def filter_compound_groups_by_primary_terms(groups: list[list[str]], primary_terms: list[str]) -> list[list[str]]:
    if not groups or not primary_terms:
        return groups
    filtered: list[list[str]] = []
    for group in groups:
        if any(_compound_term_allowed_by_primary(term, primary_terms) for term in group):
            filtered.append(group)
    return filtered


CENTER_ALIASES = {
    "人物中心": "人物域",
    "人物域": "人物域",
    "人物线": "人物域",
    "称谓别名线": "人物域",
    "事件中心": "事件域",
    "事件域": "事件域",
    "事件/情节线": "事件域",
    "事件线": "事件域",
    "情节线": "事件域",
    "关系中心": "关系域",
    "关系域": "关系域",
    "关系线": "关系域",
    "物象中心": "物象域",
    "物象域": "物象域",
    "物象线": "物象域",
    "诗词判词中心": "诗词文本域",
    "诗词文本域": "诗词文本域",
    "诗词文本线": "诗词文本域",
    "诗词线": "诗词文本域",
    "空间中心": "空间域",
    "空间域": "空间域",
    "场域": "空间域",
    "场域/空间域": "空间域",
    "场域线": "空间域",
    "空间线": "空间域",
    "章节原句中心": "章节原句",
    "章节原句": "章节原句",
    "章节原句线": "章节原句",
    "观念主题中心": "观念主题",
    "观念主题": "观念主题",
    "观念主题线": "观念主题",
    "共现查证": "共现查证",
    "共现查证线": "共现查证",
    "库文双向": "库文双向",
    "原文优先": "原文优先",
    "底库优先": "底库优先",
    "深度补证": "深度补证",
}


def route_center_terms(text: str) -> list[str]:
    explicit = context_line_value(text, "Codex问题中心")
    source = explicit or text
    values = split_terms(source.replace("｜", " ").replace("|", " "))
    centers: list[str] = []
    seen: set[str] = set()
    for value in values:
        center = CENTER_ALIASES.get(value)
        if center and center not in seen:
            seen.add(center)
            centers.append(center)
    found = []
    for alias, center in CENTER_ALIASES.items():
        pos = text.find(alias)
        if pos >= 0:
            found.append((pos, center))
    for _, center in sorted(found, key=lambda item: item[0]):
        if center not in seen:
            seen.add(center)
            centers.append(center)
    return centers


def route_context_profile(route_context: str = "") -> dict[str, object]:
    text = str(route_context or "")
    if not text.strip():
        return {}
    centers = route_center_terms(text)
    center = centers[0] if centers else ""
    center_label = "、".join(centers)
    order = next((name for name in ROUTE_CONTEXT_ORDERS if name in text), "")
    actions = [name for name in ROUTE_CONTEXT_ACTIONS if name in text]
    sources = split_terms(context_value(text, "材料来源"))
    codex_terms = split_terms(context_value(text, "Codex查询词"))
    query_term_strategy = context_value(text, "Codex查询词策略")
    codex_libraries = split_terms(context_value(text, "Codex优先库"))
    compound_groups = context_compound_groups(text, "Codex强复合")
    primary_terms = context_role_terms(text, "主查词")
    compound_groups = filter_compound_groups_by_primary_terms(compound_groups, primary_terms)
    anchor_terms = split_terms(context_line_value(text, "Codex背景锚点").replace("｜", " ").replace("|", " "))
    depth = context_value(text, "运行深度")
    output = context_value(text, "优先回显")
    style = context_value(text, "表达")
    center_specs = [ROUTE_CONTEXT_CENTERS.get(item, {}) for item in centers]
    libraries = []
    terms = []
    guidance = []
    for spec in center_specs:
        libraries.extend(spec.get("libraries", []))
        terms.extend(spec.get("terms", []))
        if spec.get("guidance"):
            guidance.append(str(spec.get("guidance")))
    center_spec = ROUTE_CONTEXT_CENTERS.get(center, {})
    route_mode, route_mode_reason = _infer_route_mode(
        text,
        centers,
        codex_terms,
        actions,
        depth,
        output,
        order,
    )
    return {
        "center": center,
        "centers": centers,
        "center_label": center_label or center,
        "order": order,
        "actions": actions,
        "sources": sources,
        "depth": depth,
        "output": output,
        "style": style,
        "libraries": unique_terms(libraries + codex_libraries, limit=0),
        "terms": significant_search_terms(terms + codex_terms, limit=0),
        "codex_terms": codex_terms,
        "query_term_strategy": query_term_strategy,
        "codex_libraries": codex_libraries,
        "compound_groups": compound_groups,
        "primary_terms": primary_terms,
        "anchor_terms": significant_search_terms(anchor_terms, limit=0),
        "guidance": "；".join(guidance) or center_spec.get("guidance", ""),
        "anchor_type": center_spec.get("anchor_type", ""),
        "starting_bus": center_spec.get("starting_bus", ""),
        "route_mode": route_mode,
        "route_mode_reason": route_mode_reason,
        "raw": clean_context_line(text),
    }


def primary_strategy_terms(profile: dict[str, object], *, fallback_to_codex: bool = True) -> list[str]:
    """Terms that should drive the first retrieval pass, not every auxiliary hint."""
    primary_terms = profile.get("primary_terms", []) if isinstance(profile, dict) else []
    if isinstance(primary_terms, list):
        terms = compact_strategy_terms([str(term) for term in primary_terms], limit=10)
        if terms:
            return terms
    compound_groups = profile.get("compound_groups", []) if isinstance(profile, dict) else []
    if isinstance(compound_groups, list) and compound_groups:
        terms = compact_compound_query_terms([group for group in compound_groups if isinstance(group, list)])
        if terms:
            return terms
    if fallback_to_codex and isinstance(profile, dict):
        return compact_strategy_terms([str(term) for term in profile.get("codex_terms", [])], limit=10)
    return []


def require_codex_query_terms(route_context: str = "") -> tuple[dict[str, object], list[str]]:
    profile = route_context_profile(route_context)
    query_terms = primary_strategy_terms(profile)
    if not query_terms:
        raise ValueError("缺少 Codex 入口词包：红楼梦工程只作为 Codex 查证器运行，当前停在入口词门。")
    return profile, query_terms


def apply_route_context(route: dict[str, object], route_context: str = "") -> dict[str, object]:
    profile = route_context_profile(route_context)
    if not profile:
        return route
    updated = dict(route)
    center = str(profile.get("center") or "")
    center_label = str(profile.get("center_label") or center)
    has_codex_terms = bool(profile.get("codex_terms"))
    if center or has_codex_terms:
        original_anchor = str(route.get("anchor_type") or "")
        original_libraries = list(route.get("libraries", []))
        original_terms = list(route.get("search_terms", []))
        sources = list(profile.get("sources", []))
        source_libraries: list[str] = []
        if "原文" in sources:
            source_libraries.extend(["全文检索库", "段落库", "章节真源库"])
        if "生成文件" in sources:
            source_libraries.append("生成文件索引")
        updated["anchor_type"] = center_label or profile.get("anchor_type") or center or "Codex查询词路"
        updated["starting_bus"] = profile.get("starting_bus") or updated.get("starting_bus", "segment search")
        updated["libraries"] = unique_terms(
            list(profile.get("libraries", [])) + original_libraries + source_libraries,
            limit=14,
        )
        primary_terms = primary_strategy_terms(profile)
        if primary_terms:
            updated["search_terms"] = primary_terms
        else:
            updated["search_terms"] = significant_search_terms(
                list(profile.get("terms", [])) + original_terms,
                limit=0,
            )
    updated["route_context"] = profile
    updated["question"] = (
        str(updated.get("question") or "")
        + f" 页面触发提示：{center_label or '等待 Codex 策略'}；{profile.get('order') or '顺序等待 Codex 策略'}；取证动作：{'、'.join(profile.get('actions', [])) or '等待 Codex 指令'}。"
    )
    return updated


def infer_material_route(question: str, route_context: str = "") -> dict[str, object]:
    profile, codex_terms = require_codex_query_terms(route_context)
    libraries = [str(item) for item in profile.get("libraries", []) if str(item).strip()]
    if not libraries:
        libraries = ["全文检索库", "段落库", "章节真源库", "多轴底库"]
    return apply_route_context({
        "anchor_type": str(profile.get("center_label") or profile.get("center") or "Codex查询词路"),
        "starting_bus": "question -> codex route -> source review",
        "libraries": libraries,
        "search_terms": codex_terms,
        "question": "本题只登记工程入口；关键词、检索顺序和证据判断已由 Codex 旧S卡给出，本地工程只执行查证。",
    }, route_context)


def source_layer_plan(route: dict[str, object], search_terms: list[str]) -> list[str]:
    libraries = "、".join(str(item) for item in route.get("libraries", []))
    terms = "、".join(search_terms[:12])
    profile = route.get("route_context") if isinstance(route.get("route_context"), dict) else {}
    lines: list[str] = []
    if profile:
        center_label = profile.get("center_label") or profile.get("center")
        lines.append(
            "页面触发层："
            f"问题中心={center_label or '等待 Codex 策略'}；"
            f"查证顺序={profile.get('order') or '等待 Codex 策略'}；"
            f"查询词策略={profile.get('query_term_strategy') or '等待 Codex 策略'}；"
            f"取证动作={'、'.join(profile.get('actions', [])) or '等待 Codex 指令'}；"
            f"材料来源={'、'.join(profile.get('sources', [])) or '等待 Codex 指令'}；"
            f"运行深度={profile.get('depth') or '等待 Codex 指令'}；"
            f"优先回显={profile.get('output') or '等待 Codex 指令'}；"
            f"表达={profile.get('style') or '默认'}。"
        )
        if profile.get("guidance"):
            lines.append(f"规则小程序：{profile.get('guidance')}")
    lines.extend([
        f"底库索引层：先走 {libraries}，用 {terms} 等词缩小候选范围。",
        "原文复核层：每个候选都必须回到段落原文、章节标题和上下文，确认它到底回答哪个问题。",
        "材料池层：只保存原文复核成立的候选材料；可用、背景、不可用或需补证由 Codex 材料池判定决定。",
        "生成文件层：历史文稿和既有工程包只作回看线索，不能越过原文复核直接成为结论。",
    ])
    return lines


def flow_map_lines(route: dict[str, object], search_terms: list[str]) -> list[str]:
    profile = route.get("route_context") if isinstance(route.get("route_context"), dict) else {}
    lines: list[str] = []
    if profile:
        center_label = profile.get("center_label") or profile.get("center")
        lines.append(
            "页面触发："
            f"{center_label or '等待 Codex 策略'} / "
            f"{profile.get('order') or '等待 Codex 策略'} / "
            f"{'、'.join(profile.get('actions', [])) or '等待 Codex 指令'} / "
            f"来源={'、'.join(profile.get('sources', [])) or '等待 Codex 指令'} / "
            f"深度={profile.get('depth') or '等待 Codex 指令'} / "
            f"回显={profile.get('output') or '等待 Codex 指令'} / "
            f"表达={profile.get('style') or '默认'}"
        )
        if profile.get("guidance"):
            lines.append(f"规则小程序：{profile.get('guidance')}")
    lines.extend([
        f"入口识别：{route.get('anchor_type', '等待 Codex 策略')}，起手总线：{route.get('starting_bus', 'segment search')}",
        "拆题目标：执行 Codex 已决定的词网、库轴和原文路径，再交给 Codex 材料池判定。",
        "第一轮：Codex 词网进入全文库、段落库和指定库轴，形成候选材料。",
        "第二轮：底库索引和全文段落共同召回候选，记录命中词和命中子问题。",
        "第三轮：候选必须回原文上下文，能否回答问题只记录为待 Codex 判定，不由本地程序定性。",
        "第四轮：材料池交给最终回答层，Codex 只能在材料池和原文复核基础上组织答案。",
        f"当前首轮词网：{'、'.join(search_terms[:18])}",
    ])
    return lines


def dynamic_material_plan(question: str, route_context: str = "") -> list[SubQuestion]:
    return codex_directed_plan(question, route_context=route_context)


def codex_directed_plan(question: str, route_context: str = "") -> list[SubQuestion]:
    profile, codex_terms = require_codex_query_terms(route_context)
    libraries = [str(item) for item in profile.get("codex_libraries", []) if str(item).strip()]
    if not libraries:
        libraries = [str(item) for item in profile.get("libraries", []) if str(item).strip()]
    if not libraries:
        libraries = ["search_documents/search_documents_fts", "segments", "chapters"]
    center = str(profile.get("center_label") or profile.get("center") or profile.get("raw") or "Codex 查询词路")
    character_terms = context_role_terms(route_context, "主查人物")
    object_terms = context_role_terms(route_context, "主查物象")
    if not character_terms and isinstance(profile.get("compound_groups"), list) and profile.get("compound_groups"):
        first_group = profile["compound_groups"][0]
        if isinstance(first_group, list):
            character_terms = compact_strategy_terms([str(term) for term in first_group], limit=3)
    if not object_terms and isinstance(profile.get("compound_groups"), list) and len(profile.get("compound_groups", [])) > 1:
        second_group = profile["compound_groups"][1]
        if isinstance(second_group, list):
            object_terms = compact_compound_query_terms([second_group], limit=3)
    entities = compact_strategy_terms(character_terms, limit=4)
    keywords = compact_strategy_terms(object_terms + codex_terms, limit=8)
    source_layers = [
        "Codex 指挥中心先决定搜索词、语义聚拢中心库内部表轴和原文路径。",
        "本地工程只执行查询、取原子段、保存候选材料。",
        "候选材料必须回到 Codex 材料池判定后才能进入最终回答。",
    ]
    return [
        SubQuestion(
            1,
            "Codex查询词路执行",
            f"按 Codex 已决定的问题中心执行首轮查证：{center}",
            "本步只执行 Codex 的查询词路，不由本地程序重新猜题。",
            entities,
            keywords,
            libraries,
            "产出第一轮候选材料和命中痕迹；不产出证据结论。",
            source_layers,
        ),
        SubQuestion(
            2,
            "库轴候选召回",
            "Codex 指定的关键词应在哪些库轴、人物、物象、空间、事件或文本层里找候选？",
            "按 Codex 指定库轴查找，库只提供候选，不替 Codex 判断材料意义。",
            entities,
            keywords,
            libraries,
            "形成库轴候选清单，并保留库名、段落号、命中词和来源。",
            [
                "库轴只负责定位候选对象。",
                "同名、近名、热词命中都不能自动升格。",
                "是否需要扩大或收缩查询，由下一道 Codex 材料池判定决定。",
            ],
        ),
        SubQuestion(
            3,
            "原文上下文复核",
            "候选材料回到哪些原文段落、前后文和原子段，才能供 Codex 判断？",
            "搜索命中不是证据，必须交回原文上下文。",
            entities,
            keywords,
            unique_terms(libraries + ["segments", "chapters"], limit=0),
            "输出原子段编号、章节、摘要、短摘和上下文线索。",
            [
                "原文段落优先于摘要、标题和过程稿。",
                "章节标题只能作入口，不能替代段落证据。",
                "每条候选都保留可追溯路径。",
            ],
        ),
        SubQuestion(
            4,
            "材料池交回Codex判定",
            "这一轮候选材料能否使用、只能作背景、应剔除还是需要补证？",
            "本地工程到此停止判断，把材料交给 Codex 指挥中心逐条定性。",
            entities,
            keywords,
            unique_terms(libraries + ["material_pool"], limit=0),
            "生成供 Codex 材料池判定读取的候选材料池。",
            [
                "材料角色由 Codex 决定。",
                "本地排序只表示检索强弱，不表示证据强弱。",
                "下一轮查证词必须来自 Codex 判定。",
            ],
        ),
        SubQuestion(
            5,
            "等待Codex下一步",
            "Codex 材料池判定是否允许进入最终回答，还是要求二轮补证？",
            "没有 Codex 下一步决定，工程不自动推进补证或写作。",
            entities,
            keywords,
            libraries,
            "等待 Codex 输出 writing_mode 和 next_search_decisions。",
            [
                "可以写：进入红楼解语。",
                "谨慎写：写临时判断并标明缺口。",
                "先补证：停止完整结论，只输出补证方向。",
            ],
        ),
    ]


def build_plan(question: str, route_context: str = "") -> list[SubQuestion]:
    return codex_directed_plan(question, route_context=route_context)


def preview_evidence(subquestions: list[SubQuestion], limit_per_question: int) -> list[dict]:
    conn = evidence_pack.connect()
    rows: list[dict] = []
    for subq in subquestions:
        ranked, direct_edges, chars = evidence_pack.rank_segments(
            conn,
            evidence_pack.clean_terms(subq.entities),
            evidence_pack.clean_terms(subq.keywords),
            limit_per_question,
        )
        for hit in ranked[:limit_per_question]:
            rows.append(
                {
                    "subquestion_order": subq.order,
                    "dimension": subq.dimension,
                    "subquestion": subq.question,
                    "segment_no": hit.segment_no,
                    "chapter_no": hit.chapter_no,
                    "score": hit.score,
                    "summary": hit.summary,
                    "quote": hit.quote,
                    "reasons": "；".join(hit.reasons),
                    "matched_characters": len(chars),
                    "direct_edge_hits": len(direct_edges),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def generate(question: str, limit_per_question: int, route_context: str = "") -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subquestions = build_plan(question, route_context=route_context)
    preview_rows = preview_evidence(subquestions, limit_per_question)

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "route_context": route_context,
        "subquestion_count": len(subquestions),
        "preview_rows": len(preview_rows),
        "subquestions": [asdict(item) for item in subquestions],
    }

    guide_path = OUT_DIR / "00_复杂拆题器说明.md"
    md_path = OUT_DIR / "01_默认问题拆题方案.md"
    json_path = OUT_DIR / "02_默认问题拆题方案.json"
    csv_path = OUT_DIR / "03_子问题证据召回预览.csv"

    guide_path.write_text(
        "\n".join(
            [
                "# 复杂拆题器说明",
                "",
                "## 用途",
                "",
                "把 Codex 已判断的问题中心、查询词和库轴，转成可执行的候选材料召回任务。它不替题目下结论，也不生成答案。",
                "",
                "## 默认运行",
                "",
                "```bash",
                "/Users/yu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/formal_honglou_question_decomposer.py",
                "```",
                "",
                "## 自定义问题",
                "",
                "```bash",
                "/Users/yu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/formal_honglou_question_decomposer.py --question \"你的问题\" --route-context \"Codex查询词：词1、词2｜Codex优先库：segments、chapters\"",
                "```",
                "",
                "## 输出",
                "",
                "- `01_默认问题拆题方案.md`：人工阅读版拆题方案。",
                "- `02_默认问题拆题方案.json`：机器调用版。",
                "- `03_子问题证据召回预览.csv`：每个子问题的初步段落召回结果。",
            ]
        ),
        encoding="utf-8",
    )

    lines = [
        "# 红楼梦正式底库｜复杂问题拆题器原型",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 总问题",
        "",
        question,
        "",
        "## 2. 拆题总览",
        "",
        f"- 子问题数量：{len(subquestions)}",
        f"- 证据召回预览行数：{len(preview_rows)}",
        "",
        "## 3. 工程拆解方式",
        "",
        "当前按 Codex 指挥链执行：先接收问题中心、查询词和库轴，再形成候选召回、原文复核、材料池交接和下一步等待。",
        "",
    ]

    lines.extend(
        [
            "## 4. 子问题与检索方案",
            "",
        ]
    )
    preview_by_order: dict[int, list[dict]] = {}
    for row in preview_rows:
        preview_by_order.setdefault(row["subquestion_order"], []).append(row)

    for subq in subquestions:
        lines.extend(
            [
                f"### {subq.order}. {subq.dimension}",
                "",
                f"- 子问题：{subq.question}",
                f"- 目的：{subq.purpose}",
                f"- 实体：{'、'.join(subq.entities)}",
                f"- 关键词：{'、'.join(subq.keywords)}",
                f"- 优先证据轴：{'、'.join(subq.preferred_axes)}",
                f"- 预期证据：{subq.evidence_expectation}",
                "",
                "初步召回：",
            ]
        )
        for row in preview_by_order.get(subq.order, [])[:5]:
            lines.append(f"- {row['segment_no']}｜第{row['chapter_no']}回｜{row['score']}｜{row['summary']}｜{row['quote']}")
        lines.append("")

    lines.extend(
        [
            "## 5. 后续执行方式",
            "",
            "1. 对每个子问题调用证据包生成器。",
            "2. 每个子问题只保留候选材料、命中词、原文段落和上下文痕迹。",
            "3. 将子问题候选合并为总材料池，不在本地程序里分主证、反证或结论。",
            "4. 再进入 Codex 材料池判定、二次补证决定和最终红楼解语。",
        ]
    )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_path, preview_rows)

    return {
        "guide": str(guide_path),
        "markdown": str(md_path),
        "json": str(json_path),
        "csv": str(csv_path),
        "subquestion_count": len(subquestions),
        "preview_rows": len(preview_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Decompose complex Red Chamber research questions into evidence tasks.")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--limit-per-question", type=int, default=8)
    parser.add_argument("--route-context", default="")
    args = parser.parse_args()
    print(json.dumps(generate(args.question, args.limit_per_question, args.route_context), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
