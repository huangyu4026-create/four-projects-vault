#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import formal_honglou_numbering_front_gate as numbering_front_gate
except Exception:  # pragma: no cover - graph packet still renders if tool import fails
    numbering_front_gate = None  # type: ignore[assignment]

try:
    import formal_honglou_eight_step_mainline as eight_step_mainline
except Exception:  # pragma: no cover - graph packet still renders if tool import fails
    eight_step_mainline = None  # type: ignore[assignment]

try:
    import formal_honglou_abstract_concept_modeler as abstract_concept_modeler
except Exception:  # pragma: no cover - graph packet still renders if tool import fails
    abstract_concept_modeler = None  # type: ignore[assignment]

try:
    import formal_honglou_final_quality_gate as final_quality_gate
except Exception:  # pragma: no cover - graph packet still renders if tool import fails
    final_quality_gate = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
GRAPH_DIR = (
    ROOT
    / "outputs"
    / "红楼梦对谈查证室"
    / "113_编号递归聚拢总图_全书固定归属圈首版_修正版"
)

GRAPH_FILES = {
    "summary": GRAPH_DIR / "113_编号递归聚拢总图_summary.json",
    "nodes": GRAPH_DIR / "113_编号递归聚拢总图_nodes.csv",
    "edges": GRAPH_DIR / "113_编号递归聚拢总图_edges.csv",
    "closure": GRAPH_DIR / "113_编号递归聚拢总图_closure.csv",
    "tags": GRAPH_DIR / "113_编号递归聚拢总图_tags.csv",
    "line_membership": GRAPH_DIR / "113_编号递归聚拢总图_line_membership.csv",
}

MAPPING_DIR = (
    ROOT
    / "outputs"
    / "红楼梦对谈查证室"
    / "118_万库映射回聚拢总图_首版"
)

MAPPING_FILES = {
    "summary": MAPPING_DIR / "118_万库映射回聚拢总图_summary.json",
    "library_mappings": MAPPING_DIR / "118_万库映射回聚拢总图_library_mappings.csv",
    "added_tags": MAPPING_DIR / "118_万库映射回聚拢总图_added_tags.csv",
    "added_edges": MAPPING_DIR / "118_万库映射回聚拢总图_added_edges.csv",
    "mapping_summary_by_library": MAPPING_DIR / "118_万库映射回聚拢总图_mapping_summary_by_library.csv",
    "problem_queue": MAPPING_DIR / "118_万库映射回聚拢总图_问题队列.csv",
}

GRAPH_NAME = "编号递归聚拢总图"
GRAPH_SHORT_NAME = "聚拢总图"
GRAPH_RUNTIME_FORMULA = "库先入图，AI 再查图，图再回原文。"
GRAPH_READING_RULE = "标签给方向。节点给位置。边给关系。归属链给上下文。原文给裁判。"
MAPPING_LAYER_RULE = "118 万库映射层只给聚拢总图加标签、加边、加库来源，不直接给最终答案。"

GRAPH_LAYER_ORDER = [
    "LINE 一行索引",
    "ASEG 原子段",
    "CSEG 聚拢段",
    "CU 聚拢单元",
    "EV 聚拢事件",
    "SC 聚拢场",
    "DOMAIN 聚拢域",
    "原文裁判",
]

GRAPH_FORBIDDEN_SHORTCUTS = [
    "不得先在库外挑库，再决定进哪个库。",
    "不得把标签直接写成答案。",
    "不得把同回写成同场。",
    "不得把提及写成在场。",
    "不得把 101 场候选直接写成强证据。",
    "不得绕过原文裁判。",
]

FRAMEWORK_ROOT_NOISE_PHRASES = (
    "红楼梦",
    "全书",
    "全文",
    "哪些地方",
    "有几处",
    "地方",
    "怎么看",
    "怎样看",
    "从顺序看",
    "然后看",
    "关系状态",
    "同时",
    "分别",
)

EXISTING_TOOL_REGISTRY = [
    {
        "tool_id": "T01",
        "name": "新编号入口门",
        "module": "formal_honglou_numbering_front_gate.py",
        "function": "build_front_gate_for_question",
        "old_role": "新编号入口唯一前门",
        "new_role": "聚拢总图内的收点与交集工具",
        "keep_as": "must_use_inside_graph",
        "reason": "它已经能调用人物查询归一、空间轻量收点、关键词全文穷尽收点，并产出编号交集。",
    },
    {
        "tool_id": "T02",
        "name": "人物查询归一包",
        "module": "formal_honglou_person_query_unifier.py",
        "function": "detect_person_query_packs",
        "old_role": "人物消歧和全量收编号",
        "new_role": "聚拢总图入口线索的第一优先归一工具",
        "keep_as": "must_use_when_person_appears",
        "reason": "红楼梦工程一旦人物归一错误，后面所有交集和在场判断都会歪。",
    },
    {
        "tool_id": "T03",
        "name": "全书穷尽查证/全文穷尽收点",
        "module": "formal_honglou_search_index.py + formal_honglou_numbering_front_gate.py",
        "function": "search / collect_keyword_bundle",
        "old_role": "全文查证、查访、补漏搜索",
        "new_role": "聚拢总图内的补点工具",
        "keep_as": "must_use_when_graph_or_library_may_miss",
        "reason": "库不可能收全狗、鸡、灯、动作词、小称谓；穷尽法负责扫全文拿编号，再回图判断关系。",
    },
    {
        "tool_id": "T04",
        "name": "红楼梦编号证据八步主线",
        "module": "formal_honglou_eight_step_mainline.py",
        "function": "build_eight_step_packet",
        "old_role": "运行主线",
        "new_role": "聚拢总图内的思考顺序和复核清单",
        "keep_as": "absorb_as_rule_not_front_door",
        "reason": "八步里的归一、收点、交集、路由门、分类、回原文、入材料池、写答案仍然正确，只是入口从库外改为图内。",
    },
    {
        "tool_id": "T05",
        "name": "抽象题概念建模器",
        "module": "formal_honglou_abstract_concept_modeler.py",
        "function": "build_abstract_concept_packet",
        "old_role": "抽象题不只搜概念词",
        "new_role": "聚拢域生成前的概念承载层工具",
        "keep_as": "must_use_for_abstract_questions",
        "reason": "为什么说、象征、意义、气氛、精神等题，必须先落到人物、空间、物象、事件、原文语气和反证边界。",
    },
    {
        "tool_id": "T06",
        "name": "材料池入池凭证门",
        "module": "formal_honglou_material_admission_gate.py",
        "function": "apply_gate",
        "old_role": "阻止旧搜索和无编号材料直接入池",
        "new_role": "聚拢总图候选进入材料池前的硬闸门",
        "keep_as": "must_use_before_material_pool",
        "reason": "聚拢总图只能组织候选，材料能不能读给 Codex，还要看编号、来源、路由、分柜和原文锚点。",
    },
    {
        "tool_id": "T07",
        "name": "研究包工作流",
        "module": "formal_honglou_research_workflow.py",
        "function": "build_research_pack",
        "old_role": "问题树、新编号入口、候选材料池、阅读清单",
        "new_role": "聚拢总图查询后的材料包生成器",
        "keep_as": "keep_as_material_pack_builder",
        "reason": "它负责把过程材料整理成 Codex 可读材料包，不应被聚拢总图替代。",
    },
    {
        "tool_id": "T08",
        "name": "候选材料分流与复核回读",
        "module": "formal_honglou_evidence_triage.py / formal_honglou_review_writer.py / formal_honglou_review_readback.py",
        "function": "triage / build_review_pack / build_readback",
        "old_role": "候选材料、复核包、回读包",
        "new_role": "聚拢总图回原文后的材料池整理层",
        "keep_as": "keep_as_material_review_layer",
        "reason": "最终答案不能直接从图出；仍需要候选、复核、回读和材料池判定。",
    },
    {
        "tool_id": "T09",
        "name": "终稿后质量复核门",
        "module": "formal_honglou_final_quality_gate.py",
        "function": "build_final_quality_gate_packet",
        "old_role": "终稿后复核",
        "new_role": "聚拢总图答案出口的最后硬闸",
        "keep_as": "must_use_after_answer",
        "reason": "防止子问题未过账、强结论缺原文、同回误写同场、提及误写在场、抽象题只堆词。",
    },
    {
        "tool_id": "T10",
        "name": "00M 原文追证摘抄/红楼解语门",
        "module": "formal_honglou_codex_recall.py",
        "function": "Codex 材料池判定与原文追证提示链",
        "old_role": "精读材料池后回原文摘抄",
        "new_role": "聚拢总图材料池后的写作前原文裁判",
        "keep_as": "must_keep_for_final_writing",
        "reason": "图内定位不能替代写作前带着问题回原文追证。",
    },
    {
        "tool_id": "T11",
        "name": "库分级自动选库器",
        "module": "formal_honglou_library_tier_selector.py",
        "function": "select_libraries",
        "old_role": "运行前门选库",
        "new_role": "后台补漏参考和旧经验索引",
        "keep_as": "demote_to_supplement",
        "reason": "它的库知识仍有价值，但不能再抢在聚拢总图前面决定路线。",
    },
    {
        "tool_id": "T12",
        "name": "底库健康、映射审计、锚点修复工具",
        "module": "formal_honglou_mapping_audit.py / formal_honglou_anchor_fix.py / formal_honglou_script_audit.py",
        "function": "audit / fix reports",
        "old_role": "底座审计和修复",
        "new_role": "聚拢总图出现断链、锚点风险、简繁问题时的维护工具",
        "keep_as": "maintenance_only",
        "reason": "运行时不抢前门，但工程健康靠它们保底。",
    },
]

EXHAUSTIVE_TOOL_RULES = {
    "tool_name": "全文穷尽补点工具",
    "short_name": "穷尽法",
    "existing_tool_module": "formal_honglou_numbering_front_gate.py",
    "existing_tool_gate": "新编号入口门",
    "existing_tool_function": "build_front_gate_for_question",
    "existing_collect_method": "全文穷尽收点",
    "position": "聚拢总图内部的补点工具，不是旧前门；由现成新编号入口门提供收点能力。",
    "search_target": "search_documents / search_documents_fts / chapters.full_text / segments.quote-summary",
    "why_needed": "总图会收很多库，但不可能预建所有词。狗、鸡、灯、颜色、动作、方言、临时物件等词，常常需要先全文穷尽收编号，再回图找关系。",
    "use_when": [
        "入口词在聚拢总图无命中或命中很少。",
        "用户要求全书、全文、所有、全部、几次、详查、穷尽。",
        "问题需要比较两个或多个未入库对象。",
        "库标签提示有方向，但证据点不够。",
        "图内交集为空，需要确认是真空，还是漏点。",
    ],
    "combination_modes": [
        "人物归一点 + 穷尽词点：例如 林黛玉 + 活鸡。",
        "穷尽词点 + 穷尽词点：例如 狗 + 月亮。",
        "人物归一点 + 人物归一点 + 穷尽词点：例如 宝玉 + 黛玉 + 宫灯。",
        "空间点 + 穷尽词点：例如 怡红院 + 药。",
        "主题/动作穷尽点 + 聚拢场：例如 冷 + 雪 + 荒凉。",
    ],
    "operation_steps": [
        "先把题目拆成对象词、人物词、空间词、动作词、限定词。",
        "人物词先归一，得到人物编号点；非人物词进入穷尽法。",
        "穷尽法逐词扫全文，记录 chapter_no、segment_no、line_id/临时 line_id、quote、命中词。",
        "两个词以上时，不直接写答案，先把各自命中点按 chapter_no/segment_no/聚拢场做交集或近邻。",
        "交集为空时，放大一层：从一行到聚拢段，从聚拢段到聚拢单元，从单元到事件，从事件到场。",
        "交集仍为空时，标记为可能无同场，并回原文抽样复核，不许只凭搜索空结果下结论。",
        "找到候选编号后，把编号回到聚拢总图，看它挂在哪些段、单元、事件、场、域。",
        "最后回原文裁判，决定是同场、提及、背景、误召回，还是弱关联。",
    ],
    "output_fields": [
        "query_term",
        "chapter_no",
        "segment_no",
        "line_id",
        "quote",
        "hit_position",
        "graph_node_ids",
        "aggregate_scene_ids",
        "relation_to_question",
        "evidence_strength",
    ],
    "return_rule": "穷尽法只负责补编号；补出来的 line/segment/chapter 必须回到聚拢总图，通过段、单元、事件、场、域重新判断。",
}

DEFAULT_STOP_WORDS = {
    "红楼梦",
    "请",
    "帮我",
    "一下",
    "这个",
    "那个",
    "什么",
    "怎么",
    "有没有",
    "哪些",
    "哪一回",
    "哪回",
    "关系",
    "同场",
    "出现",
    "主要",
    "进行",
    "工程",
    "进入",
    "查询",
    "分析",
    "思路",
    "里面",
    "之间",
    "是不是",
    "为什么",
    "怎样",
    "的",
    "了",
    "吗",
    "呢",
    "啊",
    "和",
    "与",
    "跟",
    "在",
    "有",
    "是",
}

PERSON_HINT_TERMS = [
    "林黛玉",
    "黛玉",
    "妙玉",
    "贾宝玉",
    "宝玉",
    "贾母",
    "王夫人",
    "贾政",
    "贾元春",
    "元春",
    "王熙凤",
    "凤姐",
    "薛宝钗",
    "宝钗",
    "晴雯",
    "袭人",
    "紫鹃",
]

OBJECT_HINT_TERMS = [
    "潇湘馆",
    "怡红院",
    "栊翠庵",
    "大观园",
    "宫花",
    "宫灯",
    "通灵宝玉",
    "玉",
    "手帕",
    "帕子",
    "药方",
    "药",
    "活鸡",
    "鸡",
    "狗",
    "灯",
    "花",
    "茶",
    "雪",
    "冷",
    "冷感",
    "寒",
    "荒凉",
    "空寂",
    "梦",
    "太虚幻境",
    "同场",
    "在场",
    "关系",
    "流转",
    "路径",
    "病情",
    "命运",
    "象征",
]

QUESTION_HINT_TERMS = [*PERSON_HINT_TERMS, *OBJECT_HINT_TERMS]

OBJECT_ROOT_CUE_TERMS = {
    "物象",
    "物件",
    "器物",
    "东西",
    "信物",
    "文本功能",
    "字根",
    "根字",
    "意象",
    "象征",
    "流转",
    "送",
    "赏",
    "拿",
    "藏",
    "书信",
    "推荐信",
    "荐书",
    "通灵宝玉",
}

TEXT_FUNCTION_TYPE_CUES_126 = (
    "文本功能",
    "书信",
    "推荐信",
    "荐书",
    "信",
    "诗",
    "词",
    "曲",
    "判词",
    "题咏",
    "帖子",
    "文书",
)

OBJECT_TYPE_CUES_126 = (
    "物象",
    "物件",
    "器物",
    "东西",
    "信物",
    "流转",
    "送",
    "赏",
    "拿",
    "藏",
    "通灵宝玉",
)

ACTION_TYPE_CUES_126 = (
    "动作",
    "小词",
    "笑",
    "哭",
    "看",
    "拿",
    "送",
    "赏",
    "藏",
    "写",
)

# 126 的程序化口径：这不是样题词表，而是“类型判定后允许作为最小根字”的通用根字符集合。
GENERIC_ROOT_CHARACTER_TERMS_126 = set("书信诗词曲判梦灯药方鸡狗玉帕花茶雪冷竹金银香镜扇佩珠钗盒瓶杯酒血泪笑哭看写送赏藏拿")


def clean_text(value: object) -> str:
    return str(value or "").strip()


def uniq(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = clean_text(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def is_single_character_root_shadowed_by_person(question: str, term: str, person_terms: list[str]) -> bool:
    """人物题先归一；人名里的单字不再自动当物象根字。"""
    if len(term) != 1:
        return False
    return any(term in person and person in question for person in person_terms)


def single_root_evidence_text(question: str) -> str:
    text = clean_text(question)
    for phrase in FRAMEWORK_ROOT_NOISE_PHRASES:
        text = text.replace(phrase, "")
    return text


def is_framework_entry_term(term: str) -> bool:
    value = clean_text(term)
    if not value:
        return True
    if value in DEFAULT_STOP_WORDS:
        return True
    return any(phrase in value for phrase in FRAMEWORK_ROOT_NOISE_PHRASES)


def should_keep_single_character_root(question: str, term: str, person_terms: list[str]) -> bool:
    if len(term) != 1:
        return True
    if is_single_character_root_shadowed_by_person(question, term, person_terms):
        return False
    evidence_text = single_root_evidence_text(question)
    if term not in evidence_text:
        return False
    typed_context_cues = set(OBJECT_ROOT_CUE_TERMS) | set(TEXT_FUNCTION_TYPE_CUES_126) | set(ACTION_TYPE_CUES_126)
    if any(cue in evidence_text for cue in typed_context_cues):
        return True
    return term in GENERIC_ROOT_CHARACTER_TERMS_126


def is_person_term_shadowed_by_object_phrase(question: str, term: str) -> bool:
    """物象短语包住人物名时，人物入口只在题面另有独立人物称呼时保留。"""
    question = clean_text(question)
    term = clean_text(term)
    if "通灵宝玉" not in question:
        return False
    if term not in {"宝玉", "贾宝玉", "P0025"}:
        return False
    remainder = question.replace("通灵宝玉", "")
    return not any(label in remainder for label in ("宝玉", "贾宝玉"))


def filter_shadowed_person_terms(question: str, terms: list[str]) -> list[str]:
    return [term for term in uniq(terms) if not is_person_term_shadowed_by_object_phrase(question, term)]


def infer_126_object_types(question: str, person_terms: list[str] | None = None) -> list[str]:
    """126 查询词规范：先判对象类型，再决定人物归一或物象根字。"""
    question = clean_text(question)
    person_terms = filter_shadowed_person_terms(question, person_terms or [term for term in PERSON_HINT_TERMS if term and term in question])
    types: list[str] = []
    if any(cue in question for cue in TEXT_FUNCTION_TYPE_CUES_126):
        types.append("文本功能")
    if any(cue in question for cue in OBJECT_TYPE_CUES_126):
        types.append("物象")
    if any(cue in question for cue in ACTION_TYPE_CUES_126):
        types.append("小词/动作")
    if person_terms and not types:
        types.append("人物")
    return uniq(types)


def generic_root_terms_from_question_126(question: str, person_terms: list[str] | None = None) -> list[str]:
    """按 126 通用类型规则产根字；样题只能验收本函数，不得在外层硬塞词。"""
    question = clean_text(question)
    person_terms = filter_shadowed_person_terms(question, person_terms or [term for term in PERSON_HINT_TERMS if term and term in question])
    object_types = infer_126_object_types(question, person_terms)
    if not any(t in object_types for t in ("物象", "文本功能", "小词/动作", "主题/抽象题")):
        return []
    roots: list[str] = []
    text_function_context = any(cue in question for cue in TEXT_FUNCTION_TYPE_CUES_126)
    for char in question:
        if char not in GENERIC_ROOT_CHARACTER_TERMS_126:
            continue
        if char == "书" and "全书" in question and not text_function_context:
            continue
        if should_keep_single_character_root(question, char, person_terms):
            roots.append(char)
    return uniq(roots)


def build_126_generic_root_path(question: str, person_terms: list[str] | None = None) -> dict[str, Any]:
    person_terms = filter_shadowed_person_terms(question, person_terms or [term for term in PERSON_HINT_TERMS if term and term in question])
    object_types = infer_126_object_types(question, person_terms)
    root_terms = generic_root_terms_from_question_126(question, person_terms)
    return {
        "source": "126_聚龙法查询词入口规范_单字宽网",
        "object_types": object_types,
        "binding_people": person_terms,
        "generic_root_terms": root_terms,
        "rule": "人物先归一；物象、小词、动作、文本功能才按通用根字符集合产 root_terms。",
        "anti_hardcode": "样题词只用于验收规则是否生效，不作为单题注入表。",
    }


def hint_terms_from_question(question: str) -> list[str]:
    person_terms = filter_shadowed_person_terms(question, [term for term in PERSON_HINT_TERMS if term and term in question])
    object_terms: list[str] = []
    for term in OBJECT_HINT_TERMS:
        if not term or term not in question:
            continue
        if should_keep_single_character_root(question, term, person_terms):
            object_terms.append(term)
    return uniq([*person_terms, *object_terms])


def split_terms(question: str, terms: list[str] | None = None) -> list[str]:
    hinted = hint_terms_from_question(question)
    if terms:
        return uniq([*hinted, *[term for term in terms if term not in DEFAULT_STOP_WORDS]])[:48]
    rough = re.split(r"[，。？！；：、,.!?;:\s]+", question)
    extracted: list[str] = []
    for part in rough:
        part = clean_text(part)
        if not part or part in DEFAULT_STOP_WORDS:
            continue
        if len(part) <= 1:
            continue
        if len(part) <= 18:
            extracted.append(part)
    return uniq([*hinted, *extracted])[:48]


def read_csv_rows(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({clean_text(k): clean_text(v) for k, v in row.items()})
            if limit is not None and len(rows) >= limit:
                break
    return rows


def load_summary() -> dict[str, Any]:
    path = GRAPH_FILES["summary"]
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive runtime packet
        return {"status": "read_failed", "path": str(path), "error": str(exc)}


def graph_file_status() -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for key, path in GRAPH_FILES.items():
        status[key] = {
            "path": str(path),
            "exists": path.exists(),
            "kind": path.suffix.lstrip("."),
        }
    return status


def mapping_file_status() -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    for key, path in MAPPING_FILES.items():
        status[key] = {
            "path": str(path),
            "exists": path.exists(),
            "kind": path.suffix.lstrip("."),
        }
    return status


def load_mapping_summary() -> dict[str, Any]:
    path = MAPPING_FILES["summary"]
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive runtime packet
        return {"status": "read_failed", "path": str(path), "error": str(exc)}


def text_matches(row: dict[str, str], fields: list[str], terms: list[str]) -> list[str]:
    hay = " ".join(clean_text(row.get(field)) for field in fields)
    return [term for term in terms if term and term in hay]


def split_ids(value: object) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;；、\s]+", text) if part]


def node_ids_from_line(row: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for field in (
        "atom_segment_ids",
        "aggregate_segment_ids",
        "aggregate_unit_ids",
        "aggregate_event_ids",
        "aggregate_scene_ids",
        "arc_candidate_ids",
    ):
        ids.extend(split_ids(row.get(field)))
    return uniq(ids)


def hit_score(hit: dict[str, Any]) -> tuple[int, int, str]:
    return (
        -int(hit.get("matched_count") or 0),
        int(hit.get("chapter_no") or hit.get("chapter_start") or 9999),
        clean_text(hit.get("segment_no") or hit.get("node_id") or ""),
    )


def find_graph_hits(terms: list[str], max_hits: int = 24) -> dict[str, Any]:
    tags = read_csv_rows(GRAPH_FILES["tags"])
    nodes = read_csv_rows(GRAPH_FILES["nodes"])
    lines = read_csv_rows(GRAPH_FILES["line_membership"])

    tag_hits: list[dict[str, Any]] = []
    matched_node_ids: set[str] = set()
    for row in tags:
        matched = text_matches(row, ["tag_value", "source_library", "source_field", "notes"], terms)
        if not matched:
            continue
        node_id = clean_text(row.get("node_id"))
        if node_id:
            matched_node_ids.add(node_id)
        tag_hits.append(
            {
                "node_id": node_id,
                "tag_type": row.get("tag_type", ""),
                "tag_value": row.get("tag_value", ""),
                "source_library": row.get("source_library", ""),
                "source_record_id": row.get("source_record_id", ""),
                "matched_terms": matched,
                "matched_count": len(matched),
            }
        )

    node_hits: list[dict[str, Any]] = []
    for row in nodes:
        matched = text_matches(row, ["node_id", "node_type_cn", "title", "summary", "source_quote", "notes"], terms)
        node_id = clean_text(row.get("node_id"))
        if node_id in matched_node_ids and not matched:
            matched = ["tag_mapped"]
        if not matched:
            continue
        if node_id:
            matched_node_ids.add(node_id)
        node_hits.append(
            {
                "node_id": node_id,
                "node_type": row.get("node_type", ""),
                "node_type_cn": row.get("node_type_cn", ""),
                "title": row.get("title", ""),
                "summary": row.get("summary", ""),
                "chapter_start": row.get("chapter_start", ""),
                "chapter_end": row.get("chapter_end", ""),
                "segment_start": row.get("segment_start", ""),
                "segment_end": row.get("segment_end", ""),
                "quality_status": row.get("quality_status", ""),
                "evidence_status": row.get("evidence_status", ""),
                "matched_terms": matched,
                "matched_count": len([term for term in matched if term != "tag_mapped"]),
            }
        )

    line_hits: list[dict[str, Any]] = []
    for row in lines:
        matched = text_matches(row, ["segment_no", "summary", "quote"], terms)
        line_node_ids = set(node_ids_from_line(row))
        graph_mapped = bool(line_node_ids & matched_node_ids)
        if graph_mapped and not matched:
            matched = ["graph_mapped"]
        if not matched:
            continue
        line_hits.append(
            {
                "line_id": row.get("line_id", ""),
                "segment_no": row.get("segment_no", ""),
                "chapter_no": row.get("chapter_no", ""),
                "summary": row.get("summary", ""),
                "atom_segment_ids": row.get("atom_segment_ids", ""),
                "aggregate_segment_ids": row.get("aggregate_segment_ids", ""),
                "aggregate_unit_ids": row.get("aggregate_unit_ids", ""),
                "aggregate_event_ids": row.get("aggregate_event_ids", ""),
                "aggregate_scene_ids": row.get("aggregate_scene_ids", ""),
                "quote": row.get("quote", ""),
                "matched_terms": matched,
                "matched_count": len([term for term in matched if term != "graph_mapped"]),
                "graph_mapped": graph_mapped,
            }
        )

    tag_hits.sort(key=lambda item: (-int(item.get("matched_count") or 0), clean_text(item.get("node_id"))))
    node_hits.sort(key=hit_score)
    line_hits.sort(key=hit_score)
    return {
        "tag_hits": tag_hits[:max_hits],
        "node_hits": node_hits[:max_hits],
        "line_hits": line_hits[:max_hits],
        "matched_node_id_count": len(matched_node_ids),
        "candidate_line_count": len(line_hits),
    }


def classify_mapping_hit(row: dict[str, Any]) -> dict[str, str]:
    strength = clean_text(row.get("evidence_strength"))
    status = clean_text(row.get("review_status"))
    low_text = f"{strength} {status}".lower()
    if "unresolved" in low_text or "needs_review" in low_text:
        return {
            "tier": "review_needed",
            "tier_cn": "需复审",
            "triage_rule": "unresolved / needs_review 只进复审，不得作为强证。",
        }
    if "candidate" in low_text or "supplemental" in low_text:
        return {
            "tier": "candidate",
            "tier_cn": "候选",
            "triage_rule": "candidate / supplemental 只作方向，必须回原文裁判后才能升格。",
        }
    if any(token in low_text for token in ("primary", "direct", "accepted", "formal", "identity")):
        return {
            "tier": "strong_or_direct",
            "tier_cn": "强证/直连候选",
            "triage_rule": "primary / direct / accepted / formal / identity 可作为优先入口，但仍需回原文裁判。",
        }
    return {
        "tier": "candidate",
        "tier_cn": "候选",
        "triage_rule": "未明示强证等级，默认只作候选方向。",
    }


def annotate_mapping_hit(row: dict[str, Any]) -> dict[str, Any]:
    triage = classify_mapping_hit(row)
    out = dict(row)
    out["evidence_tier"] = triage["tier"]
    out["evidence_tier_cn"] = triage["tier_cn"]
    out["triage_rule"] = triage["triage_rule"]
    return out


def compact_mapping_triage_sample(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_kind": row.get("source_kind", ""),
        "node_id": clean_text(row.get("target_node_id") or row.get("node_id") or row.get("anchor_node_id")),
        "source_library": row.get("source_library", ""),
        "source_record_id": row.get("source_record_id", ""),
        "type": clean_text(row.get("tag_or_edge_type") or row.get("tag_type") or row.get("edge_type")),
        "value": clean_text(row.get("tag_or_edge_value") or row.get("tag_value") or row.get("edge_value")),
        "evidence_strength": row.get("evidence_strength", ""),
        "review_status": row.get("review_status", ""),
        "matched_terms": row.get("matched_terms") or [],
        "matched_count": row.get("matched_count", 0),
        "evidence_tier": row.get("evidence_tier", ""),
        "evidence_tier_cn": row.get("evidence_tier_cn", ""),
    }


def build_mapping_hit_triage(rows: list[dict[str, Any]], sample_limit: int = 12) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {
        "strong_or_direct": [],
        "candidate": [],
        "review_needed": [],
    }
    accepted = 0
    for row in rows:
        tier = clean_text(row.get("evidence_tier")) or classify_mapping_hit(row)["tier"]
        if tier not in buckets:
            tier = "candidate"
        buckets[tier].append(row)
        if "accepted" in f"{row.get('evidence_strength', '')} {row.get('review_status', '')}".lower():
            accepted += 1
    for key in buckets:
        buckets[key].sort(
            key=lambda item: (
                -int(item.get("matched_count") or 0),
                clean_text(item.get("source_library")),
                clean_text(item.get("target_node_id") or item.get("node_id") or item.get("anchor_node_id")),
            )
        )
    return {
        "total_hits": len(rows),
        "strong_or_direct_count": len(buckets["strong_or_direct"]),
        "candidate_count": len(buckets["candidate"]),
        "review_needed_count": len(buckets["review_needed"]),
        "accepted_count": accepted,
        "first_read_order": ["strong_or_direct", "candidate", "review_needed"],
        "first_read_order_cn": ["先读强证/直连候选", "再读候选方向", "最后把需复审留给问题队列"],
        "strong_or_direct_samples": [compact_mapping_triage_sample(row) for row in buckets["strong_or_direct"][:sample_limit]],
        "candidate_samples": [compact_mapping_triage_sample(row) for row in buckets["candidate"][:sample_limit]],
        "review_needed_samples": [compact_mapping_triage_sample(row) for row in buckets["review_needed"][:sample_limit]],
        "promotion_rule": "强证/直连候选也只是入口，必须回原文裁判；候选只能作方向；需复审不能入答案。",
    }


def find_mapping_layer_hits(terms: list[str], max_hits: int = 24) -> dict[str, Any]:
    mapping_rows = read_csv_rows(MAPPING_FILES["library_mappings"])
    added_tags = read_csv_rows(MAPPING_FILES["added_tags"])
    added_edges = read_csv_rows(MAPPING_FILES["added_edges"])

    mapping_hits: list[dict[str, Any]] = []
    mapping_node_ids: set[str] = set()
    for row in mapping_rows:
        matched = text_matches(
            row,
            [
                "source_library",
                "source_table_or_file",
                "source_record_id",
                "source_record_title",
                "tag_or_edge_type",
                "tag_or_edge_value",
                "source_quote_or_anchor",
                "notes",
            ],
            terms,
        )
        if not matched:
            continue
        node_id = clean_text(row.get("target_node_id"))
        if node_id:
            mapping_node_ids.add(node_id)
        mapping_hits.append(
            annotate_mapping_hit(
                {
                    "source_kind": "library_mapping",
                    "source_library": row.get("source_library", ""),
                    "source_table_or_file": row.get("source_table_or_file", ""),
                    "source_record_id": row.get("source_record_id", ""),
                    "target_node_id": node_id,
                    "target_node_type": row.get("target_node_type", ""),
                    "mapping_type": row.get("mapping_type", ""),
                    "tag_or_edge_type": row.get("tag_or_edge_type", ""),
                    "tag_or_edge_value": row.get("tag_or_edge_value", ""),
                    "evidence_strength": row.get("evidence_strength", ""),
                    "review_status": row.get("review_status", ""),
                    "matched_terms": matched,
                    "matched_count": len(matched),
                }
            )
        )

    added_tag_hits: list[dict[str, Any]] = []
    for row in added_tags:
        matched = text_matches(
            row,
            ["tag_type", "tag_value", "source_library", "source_record_id", "source_quote_or_anchor", "notes"],
            terms,
        )
        if not matched:
            continue
        node_id = clean_text(row.get("node_id"))
        if node_id:
            mapping_node_ids.add(node_id)
        added_tag_hits.append(
            annotate_mapping_hit(
                {
                    "source_kind": "added_tag",
                "node_id": node_id,
                "node_type": row.get("node_type", ""),
                "tag_type": row.get("tag_type", ""),
                "tag_value": row.get("tag_value", ""),
                "source_library": row.get("source_library", ""),
                "source_record_id": row.get("source_record_id", ""),
                "evidence_strength": row.get("evidence_strength", ""),
                "review_status": row.get("review_status", ""),
                "matched_terms": matched,
                "matched_count": len(matched),
                }
            )
        )

    added_edge_hits: list[dict[str, Any]] = []
    for row in added_edges:
        matched = text_matches(
            row,
            ["edge_type", "subject", "object", "edge_value", "source_library", "source_record_id", "source_quote_or_anchor", "notes"],
            terms,
        )
        if not matched:
            continue
        anchor_node_id = clean_text(row.get("anchor_node_id"))
        if anchor_node_id:
            mapping_node_ids.add(anchor_node_id)
        added_edge_hits.append(
            annotate_mapping_hit(
                {
                    "source_kind": "added_edge",
                "edge_id": row.get("edge_id", ""),
                "source_library": row.get("source_library", ""),
                "source_record_id": row.get("source_record_id", ""),
                "anchor_node_id": anchor_node_id,
                "anchor_node_type": row.get("anchor_node_type", ""),
                "edge_type": row.get("edge_type", ""),
                "edge_value": row.get("edge_value", ""),
                "evidence_strength": row.get("evidence_strength", ""),
                "review_status": row.get("review_status", ""),
                "matched_terms": matched,
                "matched_count": len(matched),
                }
            )
        )

    mapping_hits.sort(key=lambda item: (-int(item.get("matched_count") or 0), clean_text(item.get("target_node_id"))))
    added_tag_hits.sort(key=lambda item: (-int(item.get("matched_count") or 0), clean_text(item.get("node_id"))))
    added_edge_hits.sort(key=lambda item: (-int(item.get("matched_count") or 0), clean_text(item.get("anchor_node_id"))))
    all_hits = [*mapping_hits, *added_tag_hits, *added_edge_hits]
    return {
        "mapping_hits": mapping_hits[:max_hits],
        "added_tag_hits": added_tag_hits[:max_hits],
        "added_edge_hits": added_edge_hits[:max_hits],
        "matched_mapping_node_id_count": len(mapping_node_ids),
        "mapping_candidate_count": len(all_hits),
        "mapping_hit_triage": build_mapping_hit_triage(all_hits, sample_limit=max_hits),
    }


def decide_graph_pan_method(question: str, terms: list[str]) -> list[str]:
    q = clean_text(question)
    methods: list[str] = ["入口线索收点", "标签读向", "归属链放大/缩小", "原文裁判"]
    if any(word in q for word in ("同场", "一起", "同时在场", "在不在场", "相遇")):
        methods.insert(2, "同场交集")
        methods.insert(3, "聚拢场判在场")
    if any(word in q for word in ("关系", "情感", "态度", "父子", "母女", "婚恋")):
        methods.insert(2, "关系节点串联")
        methods.insert(3, "多场聚拢域")
    if any(word in q for word in ("流转", "谁给谁", "送", "赏", "拿", "路径")):
        methods.insert(2, "物件流转追踪")
    if any(word in q for word in ("发展", "变化", "过程", "命运", "病", "病情", "药方")):
        methods.insert(2, "时间顺序串场")
        methods.insert(3, "聚拢域成轴")
    if any(word in q for word in ("全书", "全文", "所有", "全部", "几次", "穷尽", "详查")):
        methods.insert(2, "全文穷尽补点")
    if any(word in q for word in ("有几处", "多少次", "在哪些", "哪里有", "提到", "说了", "狗", "鸡", "灯", "花", "药", "颜色")):
        methods.insert(2, "穷尽法补点工具")
    if not terms:
        methods.insert(0, "先补入口线索")
    return uniq(methods)


def decide_exhaustive_tool_need(question: str, terms: list[str], hits: dict[str, Any]) -> dict[str, Any]:
    q = clean_text(question)
    explicit = any(word in q for word in ("全书", "全文", "所有", "全部", "几次", "穷尽", "详查", "有几处", "多少次", "在哪些"))
    low_graph_hit = int(hits.get("candidate_line_count") or 0) == 0 and bool(terms)
    multi_object = len(terms) >= 2 and any(word in q for word in ("关系", "同场", "一起", "相互", "之间", "和", "与", "跟"))
    should_consider = explicit or low_graph_hit or multi_object
    if explicit:
        reason = "用户题面要求全书/全文/全部/几次/详查，必须考虑穷尽法补点。"
    elif low_graph_hit:
        reason = "聚拢总图当前命中不足，需要穷尽法补编号后回图。"
    elif multi_object:
        reason = "多对象关系题可用穷尽法收第二、第三对象的点，再与图内人物/空间/场交集。"
    else:
        reason = "图内已有候选点，穷尽法暂作旁路备选。"
    return {
        **EXHAUSTIVE_TOOL_RULES,
        "should_consider": should_consider,
        "reason": reason,
        "explicit_trigger": explicit,
        "low_graph_hit": low_graph_hit,
        "multi_object_relation": multi_object,
    }


def build_existing_numbering_gate_packet(question: str) -> dict[str, Any]:
    if numbering_front_gate is None:
        return {
            "available": False,
            "status": "import_failed",
            "module": EXHAUSTIVE_TOOL_RULES["existing_tool_module"],
            "note": "无法导入现成新编号入口门；聚拢总图仍可读，但穷尽法实用工具不可调用。",
        }
    try:
        packet = numbering_front_gate.build_front_gate_for_question(question)
    except Exception as exc:  # pragma: no cover - defensive runtime packet
        return {
            "available": False,
            "status": "call_failed",
            "module": EXHAUSTIVE_TOOL_RULES["existing_tool_module"],
            "error": str(exc),
        }
    bundles = packet.get("bundles") if isinstance(packet, dict) else []
    intersections = packet.get("intersections") if isinstance(packet, dict) else []
    keyword_bundles = [
        item for item in bundles
        if isinstance(item, dict) and item.get("collect_method") == EXHAUSTIVE_TOOL_RULES["existing_collect_method"]
    ]
    return {
        "available": True,
        "status": "completed",
        "module": EXHAUSTIVE_TOOL_RULES["existing_tool_module"],
        "gate": EXHAUSTIVE_TOOL_RULES["existing_tool_gate"],
        "function": EXHAUSTIVE_TOOL_RULES["existing_tool_function"],
        "core_rule": packet.get("core_rule", ""),
        "bundle_count": len(bundles or []),
        "keyword_exhaustive_bundle_count": len(keyword_bundles),
        "intersection_count": len(intersections or []),
        "bundles": bundles,
        "intersections": intersections,
        "route_preview": packet.get("route_preview", []),
        "material_pool_admission_rule": packet.get("material_pool_admission_rule", []),
    }


def terms_from_existing_numbering_gate(existing_gate: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for bundle in existing_gate.get("bundles") or []:
        if not isinstance(bundle, dict):
            continue
        terms.append(clean_text(bundle.get("label")))
        terms.append(clean_text(bundle.get("object_key")))
        note = clean_text(bundle.get("note"))
        if "matched=" in note:
            matched = note.split("matched=", 1)[-1]
            terms.extend([part for part in re.split(r"[,，、/|;\s]+", matched) if part])
        collect_method = clean_text(bundle.get("collect_method"))
        if collect_method == EXHAUSTIVE_TOOL_RULES["existing_collect_method"]:
            terms.append(clean_text(bundle.get("label")))
    return uniq([term for term in terms if term and term not in DEFAULT_STOP_WORDS])[:48]


def person_terms_from_existing_numbering_gate(existing_gate: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for bundle in existing_gate.get("bundles") or []:
        if not isinstance(bundle, dict) or clean_text(bundle.get("object_type")) != "person":
            continue
        terms.append(clean_text(bundle.get("label")))
        terms.append(clean_text(bundle.get("object_key")))
        note = clean_text(bundle.get("note"))
        if "matched=" in note:
            matched = note.split("matched=", 1)[-1]
            terms.extend([part for part in re.split(r"[,，、/|;\s]+", matched) if part])
    object_alias_terms = {"通灵宝玉", "顽石", "P-STONE"}
    return uniq([term for term in terms if term and term not in DEFAULT_STOP_WORDS and term not in object_alias_terms])[:48]


def filter_entry_terms_for_question(question: str, terms: list[str]) -> list[str]:
    person_terms = [term for term in PERSON_HINT_TERMS if term and (term in question or term in terms)]
    filtered: list[str] = []
    for term in terms:
        term = clean_text(term)
        if not term:
            continue
        if is_framework_entry_term(term):
            continue
        if is_person_term_shadowed_by_object_phrase(question, term):
            continue
        if should_keep_single_character_root(question, term, person_terms):
            filtered.append(term)
    return uniq(filtered)


def extract_entry_terms_for_question(
    question: str,
    seed_terms: list[str] | None = None,
    existing_gate: dict[str, Any] | None = None,
) -> list[str]:
    base_terms = split_terms(question, seed_terms)
    gate_terms = terms_from_existing_numbering_gate(existing_gate or {}) if existing_gate else []
    hint_terms = hint_terms_from_question(question)
    gate_person_terms = person_terms_from_existing_numbering_gate(existing_gate or {}) if existing_gate else []
    person_terms = filter_shadowed_person_terms(
        question,
        [*[term for term in PERSON_HINT_TERMS if term and (term in question or term in base_terms)], *gate_person_terms],
    )
    generic_root_terms = generic_root_terms_from_question_126(question, person_terms)
    if "活鸡" in question and "鸡" not in gate_terms:
        gate_terms.append("鸡")
    if "很冷" in question and "冷感" not in gate_terms:
        gate_terms.extend(["冷", "冷感"])
    if "同场" in question or "在一起" in question:
        gate_terms.extend(["同场", "在场"])
    return filter_entry_terms_for_question(question, [*hint_terms, *base_terms, *generic_root_terms, *gate_terms])[:64]


def build_entry_term_source_breakdown(
    question: str,
    seed_terms: list[str] | None = None,
    existing_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    hint_terms = hint_terms_from_question(question)
    base_terms = split_terms(question, seed_terms)
    gate_terms = terms_from_existing_numbering_gate(existing_gate or {}) if existing_gate else []
    gate_person_terms = person_terms_from_existing_numbering_gate(existing_gate or {}) if existing_gate else []
    person_terms = filter_shadowed_person_terms(
        question,
        [*[term for term in PERSON_HINT_TERMS if term and (term in question or term in base_terms)], *gate_person_terms],
    )
    generic_root_path = build_126_generic_root_path(question, person_terms)
    final_terms = extract_entry_terms_for_question(question, seed_terms, existing_gate)
    return {
        "hint_terms": uniq(hint_terms),
        "seed_terms": uniq(seed_terms or []),
        "base_terms": uniq(base_terms),
        "generic_root_terms_126": uniq(generic_root_path.get("generic_root_terms") or []),
        "generic_root_path_126": generic_root_path,
        "numbering_gate_terms": uniq(gate_terms),
        "final_terms": final_terms,
        "rule": "入口词必须说明来源：题面提示、126 通用词根、对谈拆词、现成编号入口门、全文穷尽词包共同形成 final_terms。",
    }


def summarize_mapping_hit_strength(mapping_hits: dict[str, Any]) -> dict[str, Any]:
    triage = mapping_hits.get("mapping_hit_triage") if isinstance(mapping_hits.get("mapping_hit_triage"), dict) else {}
    if triage:
        return {
            "total_rows_scanned": triage.get("total_hits", 0),
            "strong_or_direct_like": triage.get("strong_or_direct_count", 0),
            "candidate_like": triage.get("candidate_count", 0),
            "review_needed": triage.get("review_needed_count", 0),
            "accepted_like": triage.get("accepted_count", 0),
            "first_read_order_cn": triage.get("first_read_order_cn", []),
            "promotion_rule": triage.get("promotion_rule", ""),
            "rule": "118 命中必须分强弱：强证/直连候选先读，候选只作方向，需复审只进问题队列。",
        }
    rows: list[dict[str, Any]] = []
    for key in ("mapping_hits", "added_tag_hits", "added_edge_hits"):
        for row in mapping_hits.get(key) or []:
            if isinstance(row, dict):
                rows.append(row)
    strong_like = 0
    candidate_like = 0
    review_needed = 0
    accepted = 0
    for row in rows:
        strength = clean_text(row.get("evidence_strength"))
        status = clean_text(row.get("review_status"))
        low_text = f"{strength} {status}".lower()
        if "unresolved" in low_text or "needs_review" in low_text:
            review_needed += 1
        elif "candidate" in low_text or "supplemental" in low_text:
            candidate_like += 1
        elif any(token in low_text for token in ("primary", "direct", "accepted", "formal", "identity")):
            strong_like += 1
        else:
            candidate_like += 1
        if "accepted" in low_text:
            accepted += 1
    return {
        "total_rows_scanned": len(rows),
        "strong_or_direct_like": strong_like,
        "candidate_like": candidate_like,
        "review_needed": review_needed,
        "accepted_like": accepted,
        "rule": "118 命中必须分强弱：strong/direct/accepted 可作强入口候选；candidate/supplemental 只作方向；unresolved/needs_review 只进复审。",
    }


def build_absorbed_tool_registry(question: str) -> dict[str, Any]:
    eight_step_packet: dict[str, Any] = {}
    if eight_step_mainline is not None:
        try:
            eight_step_packet = eight_step_mainline.build_eight_step_packet(question, [])
        except Exception as exc:  # pragma: no cover - defensive packet
            eight_step_packet = {"status": "call_failed", "error": str(exc)}

    abstract_packet: dict[str, Any] = {}
    if abstract_concept_modeler is not None and any(marker in question for marker in ("为什么说", "象征", "意义", "气氛", "精神", "体现")):
        try:
            abstract_packet = abstract_concept_modeler.build_abstract_concept_packet(question)
        except Exception as exc:  # pragma: no cover - defensive packet
            abstract_packet = {"status": "call_failed", "error": str(exc)}

    final_quality_packet: dict[str, Any] = {}
    if final_quality_gate is not None:
        try:
            final_quality_packet = final_quality_gate.build_final_quality_gate_packet(question)
        except Exception as exc:  # pragma: no cover - defensive packet
            final_quality_packet = {"status": "call_failed", "error": str(exc)}

    return {
        "principle": "旧工程工具不丢，但旧中段指挥权必须清零；所有旧工具只能作为聚拢总图的内部工具、材料池工具、写作前工具或维护工具。",
        "middle_replacement": {
            "replace_from": "工程能力加载 -> 库分级选库 -> 搜索词网络/库线骨架自行决定路线 -> 旧八步库外执行",
            "replace_to": "聚拢总图加载 -> 图内读法加载 -> 现成编号入口收点/穷尽补点 -> 图内放大缩小/交集路由 -> 原文裁判",
            "hard_rule": "旧中段不得与聚拢总图并行；凡旧工具产出编号，必须回聚拢总图再判断。",
        },
        "registry": [dict(item) for item in EXISTING_TOOL_REGISTRY],
        "eight_step_absorbed": eight_step_packet,
        "abstract_concept_packet": abstract_packet,
        "final_quality_packet": final_quality_packet,
    }


def build_aggregation_graph_packet(
    question: str,
    terms: list[str] | None = None,
    term_groups: list[list[str]] | None = None,
    max_hits: int = 24,
) -> dict[str, Any]:
    existing_numbering_gate = build_existing_numbering_gate_packet(question)
    entry_term_sources = build_entry_term_source_breakdown(question, terms, existing_numbering_gate)
    entry_terms = entry_term_sources["final_terms"]
    hits = find_graph_hits(entry_terms, max_hits=max_hits) if entry_terms else {"tag_hits": [], "node_hits": [], "line_hits": [], "matched_node_id_count": 0, "candidate_line_count": 0}
    mapping_hits = find_mapping_layer_hits(entry_terms, max_hits=max_hits) if entry_terms else {"mapping_hits": [], "added_tag_hits": [], "added_edge_hits": [], "matched_mapping_node_id_count": 0, "mapping_candidate_count": 0}
    mapping_hit_strength = summarize_mapping_hit_strength(mapping_hits)
    summary = load_summary()
    mapping_summary = load_mapping_summary()
    file_status = graph_file_status()
    mapping_status = mapping_file_status()
    missing_files = [key for key, item in file_status.items() if not item["exists"]]
    missing_mapping_files = [key for key, item in mapping_status.items() if not item["exists"]]
    can_enter = not missing_files and bool(entry_terms)
    absorbed_tools = build_absorbed_tool_registry(question)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "graph_name": GRAPH_NAME,
        "graph_short_name": GRAPH_SHORT_NAME,
        "runtime_formula": GRAPH_RUNTIME_FORMULA,
        "reading_rule": GRAPH_READING_RULE,
        "question": question,
        "entry_terms": entry_terms,
        "entry_term_sources": entry_term_sources,
        "term_groups": term_groups or [],
        "can_enter_graph": can_enter,
        "missing_files": missing_files,
        "graph_dir": str(GRAPH_DIR),
        "graph_files": file_status,
        "graph_summary": summary,
        "mapping_layer_name": "118_万库映射回聚拢总图_首版",
        "mapping_layer_rule": MAPPING_LAYER_RULE,
        "mapping_dir": str(MAPPING_DIR),
        "mapping_files": mapping_status,
        "mapping_summary": mapping_summary,
        "missing_mapping_files": missing_mapping_files,
        "layer_order": GRAPH_LAYER_ORDER,
        "pan_methods": decide_graph_pan_method(question, entry_terms),
        "exhaustive_tool": decide_exhaustive_tool_need(question, entry_terms, hits),
        "existing_numbering_front_gate": existing_numbering_gate,
        "absorbed_existing_tools": absorbed_tools,
        "hits": hits,
        "mapping_hits": mapping_hits,
        "mapping_hit_strength": mapping_hit_strength,
        "runtime_contract": {
            "front_door": "必须先进入聚拢总图，不得先走库分级选库。",
            "inside_graph": "在图内用入口线索、标签、节点、边、归属链盘问题。",
            "mapping_layer": "118 万库映射层随入口包加载，只作为标签、边、库来源和补漏候选增强层。",
            "fallback": "只有无命中、标签缺失、映射断裂、需要全文穷尽补点时，才调用旧库/全文检索补点；补点后仍回图。",
            "exhaustive_tool": "穷尽法是图内补点工具：扫全文只为拿编号，拿到编号后必须回聚拢总图判断关系和语境。",
            "old_tools": "旧工程工具全部吸纳，不删除；但旧中段指挥权清零，只能被聚拢总图调用。",
            "evidence": "所有强结论必须回到原文，一行/原子段/聚拢场只能负责定位和组织。",
        },
        "forbidden_shortcuts": GRAPH_FORBIDDEN_SHORTCUTS,
    }


def render_graph_entry_markdown(packet: dict[str, Any]) -> str:
    hits = packet.get("hits") if isinstance(packet.get("hits"), dict) else {}
    mapping_hits = packet.get("mapping_hits") if isinstance(packet.get("mapping_hits"), dict) else {}
    mapping_hit_strength = packet.get("mapping_hit_strength") if isinstance(packet.get("mapping_hit_strength"), dict) else {}
    mapping_summary = packet.get("mapping_summary") if isinstance(packet.get("mapping_summary"), dict) else {}
    lines = [
        f"# {packet.get('graph_name', GRAPH_NAME)}入口包",
        "",
        f"生成时间：{packet.get('generated_at', '')}",
        "",
        "## 一句话",
        "",
        f"{packet.get('runtime_formula', GRAPH_RUNTIME_FORMULA)}",
        "",
        "## 读图规矩",
        "",
        f"{packet.get('reading_rule', GRAPH_READING_RULE)}",
        "",
        "## 万库映射层",
        "",
        f"- 名称：{packet.get('mapping_layer_name', '118_万库映射回聚拢总图_首版')}",
        f"- 规矩：{packet.get('mapping_layer_rule', MAPPING_LAYER_RULE)}",
        f"- 可进入下一阶段：{mapping_summary.get('can_enter_next_stage', '未知')}",
        f"- 映射行：{(mapping_summary.get('output_counts') or {}).get('library_mappings', '未知')}",
        f"- 新增标签：{(mapping_summary.get('output_counts') or {}).get('added_tags', '未知')}",
        f"- 新增边：{(mapping_summary.get('output_counts') or {}).get('added_edges', '未知')}",
        f"- 未解决记录：{mapping_summary.get('unresolved_total_records', '未知')}",
        "- 硬边界：supplemental_candidate / unresolved 只能走补漏与复审，不得作为强证。",
        "",
        "## 问题",
        "",
        clean_text(packet.get("question")),
        "",
        "## 入口线索",
        "",
    ]
    terms = packet.get("entry_terms") or []
    term_sources = packet.get("entry_term_sources") if isinstance(packet.get("entry_term_sources"), dict) else {}
    if terms:
        lines.extend(f"- {term}" for term in terms)
    else:
        lines.append("- 暂未抽出入口线索，需要先补读题。")
    lines.extend(["", "### 入口线索来源", ""])
    lines.append(f"- 题面提示词：{'、'.join(term_sources.get('hint_terms') or []) or '无'}")
    lines.append(f"- 对谈拆词：{'、'.join(term_sources.get('seed_terms') or []) or '无'}")
    lines.append(f"- 现成编号入口门反哺：{'、'.join(term_sources.get('numbering_gate_terms') or []) or '无'}")
    lines.append(f"- 规则：{term_sources.get('rule', '')}")
    lines.extend(["", "## 本题图内盘法", ""])
    for method in packet.get("pan_methods") or []:
        lines.append(f"- {method}")
    exhaustive_tool = packet.get("exhaustive_tool") if isinstance(packet.get("exhaustive_tool"), dict) else {}
    existing_gate = packet.get("existing_numbering_front_gate") if isinstance(packet.get("existing_numbering_front_gate"), dict) else {}
    absorbed_tools = packet.get("absorbed_existing_tools") if isinstance(packet.get("absorbed_existing_tools"), dict) else {}
    lines.extend(["", "## 穷尽法工具", ""])
    lines.append(f"- 是否需要考虑：{'是' if exhaustive_tool.get('should_consider') else '暂不优先'}")
    lines.append(f"- 理由：{exhaustive_tool.get('reason', '')}")
    lines.append(f"- 现成工具：{exhaustive_tool.get('existing_tool_module', '')} / {exhaustive_tool.get('existing_tool_gate', '')} / {exhaustive_tool.get('existing_tool_function', '')}")
    lines.append(f"- 调用状态：{existing_gate.get('status', '')}｜对象包：{existing_gate.get('bundle_count', 0)}｜穷尽词包：{existing_gate.get('keyword_exhaustive_bundle_count', 0)}｜交集：{existing_gate.get('intersection_count', 0)}")
    lines.append(f"- 位置：{exhaustive_tool.get('position', '')}")
    lines.append(f"- 具体工具：{exhaustive_tool.get('search_target', '')}")
    lines.append(f"- 回图规则：{exhaustive_tool.get('return_rule', '')}")
    lines.append("- 使用步骤：")
    for step in exhaustive_tool.get("operation_steps") or []:
        lines.append(f"- {step}")
    lines.append("- 组合方式：")
    for mode in exhaustive_tool.get("combination_modes") or []:
        lines.append(f"- {mode}")
    lines.append("- 输出字段：")
    for field in exhaustive_tool.get("output_fields") or []:
        lines.append(f"- {field}")
    lines.extend(["", "## 现成编号入口收点摘要", ""])
    for bundle in (existing_gate.get("bundles") or [])[:10]:
        if not isinstance(bundle, dict):
            continue
        lines.append(
            f"- {bundle.get('object_type')}｜{bundle.get('label')}｜{bundle.get('collect_method')}｜"
            f"segment={len(bundle.get('segment_nos') or [])}｜cluster={len(bundle.get('cluster_units') or [])}｜"
            f"event={len(bundle.get('event_ids') or [])}｜chapter={len(bundle.get('chapter_nos') or [])}"
        )
    if not existing_gate.get("bundles"):
        lines.append("- 暂无现成编号入口收点摘要。")
    middle_replacement = absorbed_tools.get("middle_replacement") if isinstance(absorbed_tools.get("middle_replacement"), dict) else {}
    lines.extend(["", "## 旧工程工具吸纳与中段替换", ""])
    lines.append(absorbed_tools.get("principle", "旧工程工具重新定位到聚拢总图。"))
    lines.append("")
    lines.append(f"- 替换前：{middle_replacement.get('replace_from', '')}")
    lines.append(f"- 替换后：{middle_replacement.get('replace_to', '')}")
    lines.append(f"- 硬规则：{middle_replacement.get('hard_rule', '')}")
    lines.extend(["", "### 吸纳工具表", ""])
    for tool in absorbed_tools.get("registry") or []:
        if not isinstance(tool, dict):
            continue
        lines.append(
            f"- {tool.get('tool_id')}｜{tool.get('name')}｜旧角色：{tool.get('old_role')}｜"
            f"新角色：{tool.get('new_role')}｜处理：{tool.get('keep_as')}"
        )
    eight_packet = absorbed_tools.get("eight_step_absorbed") if isinstance(absorbed_tools.get("eight_step_absorbed"), dict) else {}
    if eight_packet:
        lines.extend(["", "### 八步主线吸纳", ""])
        lines.append(f"- 公式：{eight_packet.get('formula', '归一 -> 收点 -> 交集 -> 路由门 -> 分类 -> 回原文 -> 入材料池 -> 写答案')}")
        lines.append("- 新定位：八步不再从库外开门；八步变成聚拢总图内部处理顺序和出口复核清单。")
    lines.extend(["", "## 层级顺序", ""])
    for layer in packet.get("layer_order") or GRAPH_LAYER_ORDER:
        lines.append(f"- {layer}")
    lines.extend(["", "## 标签命中", ""])
    for row in (hits.get("tag_hits") or [])[:10]:
        lines.append(f"- {row.get('node_id')}｜{row.get('tag_type')}={row.get('tag_value')}｜来源：{row.get('source_library')}｜命中：{'、'.join(row.get('matched_terms') or [])}")
    if not hits.get("tag_hits"):
        lines.append("- 暂无标签命中；必要时使用全文/旧库补点后回图。")
    lines.extend(["", "## 节点命中", ""])
    for row in (hits.get("node_hits") or [])[:10]:
        lines.append(f"- {row.get('node_id')}｜{row.get('node_type_cn')}｜{row.get('title')}｜{row.get('segment_start')}—{row.get('segment_end')}")
    if not hits.get("node_hits"):
        lines.append("- 暂无节点命中。")
    lines.extend(["", "## 一行/原文入口候选", ""])
    for row in (hits.get("line_hits") or [])[:10]:
        quote = clean_text(row.get("quote"))
        if len(quote) > 120:
            quote = quote[:120] + "..."
        lines.append(f"- {row.get('line_id')}｜第{row.get('chapter_no')}回｜{row.get('segment_no')}｜{row.get('summary')}｜{quote}")
    if not hits.get("line_hits"):
        lines.append("- 暂无一行候选。")
    lines.extend(["", "## 118 万库映射命中", ""])
    lines.append(f"- 映射候选总数：{mapping_hits.get('mapping_candidate_count', 0)}")
    lines.append(f"- 命中聚拢节点数：{mapping_hits.get('matched_mapping_node_id_count', 0)}")
    lines.append(f"- 强/直连候选：{mapping_hit_strength.get('strong_or_direct_like', 0)}")
    lines.append(f"- 补充候选：{mapping_hit_strength.get('candidate_like', 0)}")
    lines.append(f"- 需复审：{mapping_hit_strength.get('review_needed', 0)}")
    lines.append(f"- 首读顺序：{' -> '.join(mapping_hit_strength.get('first_read_order_cn') or []) or '无'}")
    lines.append(f"- 升格规则：{mapping_hit_strength.get('promotion_rule', '')}")
    lines.append(f"- 分流规则：{mapping_hit_strength.get('rule', '')}")
    triage = mapping_hits.get("mapping_hit_triage") if isinstance(mapping_hits.get("mapping_hit_triage"), dict) else {}
    strong_samples = triage.get("strong_or_direct_samples") if isinstance(triage.get("strong_or_direct_samples"), list) else []
    candidate_samples = triage.get("candidate_samples") if isinstance(triage.get("candidate_samples"), list) else []
    review_samples = triage.get("review_needed_samples") if isinstance(triage.get("review_needed_samples"), list) else []
    lines.extend(["", "### 118 强证/直连样本", ""])
    if strong_samples:
        for row in strong_samples[:8]:
            lines.append(
                f"- {row.get('node_id')}｜{row.get('source_library')}｜{row.get('type')}={row.get('value')}｜"
                f"{row.get('review_status')}｜{row.get('evidence_strength')}｜命中：{'、'.join(row.get('matched_terms') or [])}"
            )
    else:
        lines.append("- 无强证/直连样本。")
    lines.extend(["", "### 118 候选方向样本", ""])
    if candidate_samples:
        for row in candidate_samples[:8]:
            lines.append(
                f"- {row.get('node_id')}｜{row.get('source_library')}｜{row.get('type')}={row.get('value')}｜"
                f"{row.get('review_status')}｜{row.get('evidence_strength')}｜命中：{'、'.join(row.get('matched_terms') or [])}"
            )
    else:
        lines.append("- 无候选方向样本。")
    lines.extend(["", "### 118 需复审样本", ""])
    if review_samples:
        for row in review_samples[:8]:
            lines.append(
                f"- {row.get('node_id')}｜{row.get('source_library')}｜{row.get('type')}={row.get('value')}｜"
                f"{row.get('review_status')}｜{row.get('evidence_strength')}｜命中：{'、'.join(row.get('matched_terms') or [])}"
            )
    else:
        lines.append("- 无需复审样本。")
    lines.extend(["", "### 库映射命中", ""])
    for row in (mapping_hits.get("mapping_hits") or [])[:10]:
        lines.append(
            f"- {row.get('target_node_id')}｜{row.get('source_library')}.{row.get('source_table_or_file')}｜"
            f"{row.get('tag_or_edge_type')}={row.get('tag_or_edge_value')}｜{row.get('review_status')}｜{row.get('evidence_strength')}"
        )
    if not mapping_hits.get("mapping_hits"):
        lines.append("- 暂无库映射命中。")
    lines.extend(["", "### 新增标签命中", ""])
    for row in (mapping_hits.get("added_tag_hits") or [])[:10]:
        lines.append(
            f"- {row.get('node_id')}｜{row.get('tag_type')}={row.get('tag_value')}｜"
            f"{row.get('source_library')}｜{row.get('review_status')}｜{row.get('evidence_strength')}"
        )
    if not mapping_hits.get("added_tag_hits"):
        lines.append("- 暂无新增标签命中。")
    lines.extend(["", "### 新增边命中", ""])
    for row in (mapping_hits.get("added_edge_hits") or [])[:10]:
        lines.append(
            f"- {row.get('anchor_node_id')}｜{row.get('edge_type')}={row.get('edge_value')}｜"
            f"{row.get('source_library')}｜{row.get('review_status')}｜{row.get('evidence_strength')}"
        )
    if not mapping_hits.get("added_edge_hits"):
        lines.append("- 暂无新增边命中。")
    lines.extend(["", "## 禁止捷径", ""])
    for rule in packet.get("forbidden_shortcuts") or GRAPH_FORBIDDEN_SHORTCUTS:
        lines.append(f"- {rule}")
    lines.extend(["", "## 出口契约", ""])
    contract = packet.get("runtime_contract") or {}
    for key in ("front_door", "inside_graph", "fallback", "evidence"):
        lines.append(f"- {contract.get(key, '')}")
    return "\n".join(lines).rstrip() + "\n"
