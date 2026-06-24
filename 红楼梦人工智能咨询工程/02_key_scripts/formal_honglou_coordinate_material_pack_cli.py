#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import formal_honglou_coordinate_material_gate as coordinate_gate


DEFAULT_OUT_ROOT = ROOT / "outputs" / "坐标材料门正式包"


def clean(value: Any) -> str:
    return str(value or "").strip()


def safe_name(value: str, limit: int = 40) -> str:
    text = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_-]+", "_", clean(value))
    text = re.sub(r"_+", "_", text).strip("_")
    return (text[:limit] or "坐标查询").strip("_")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


COORDINATE_EIGHT_STEP_SPINE = [
    "归一",
    "收点",
    "交集",
    "路由门",
    "分类",
    "回原文",
    "入材料池",
    "写答案",
]


def _count(value: Any) -> int:
    try:
        return len(value or []) if isinstance(value, list) else int(value or 0)
    except (TypeError, ValueError):
        return 0


def _eight_step_row(
    step_no: int,
    name: str,
    status: str,
    program_evidence: str,
    tooling: str,
    output_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "step_no": step_no,
        "name": name,
        "status": status,
        "program_evidence": program_evidence,
        "tooling": tooling,
        "output_files": output_files or [],
    }


def build_coordinate_eight_step_status(
    bundle: dict[str, Any],
    route_context: str,
    paths: dict[str, str],
    admission_status: str,
    first_candidate: dict[str, Any],
) -> dict[str, Any]:
    rows = bundle.get("rows") or []
    term_hits = _count(bundle.get("term_hits"))
    coordinate_hits = _count(bundle.get("coordinate_hits"))
    nearest_pairs = _count(bundle.get("nearest_pairs"))
    cooccurrence = _count(bundle.get("cooccurrence"))
    source_atoms = _count(bundle.get("source_atoms"))
    source_sentences = _count(bundle.get("source_sentences"))
    evidence_layers = bundle.get("evidence_layers") or []
    has_query_terms = bool(coordinate_gate.context_value(route_context, "Codex查询词"))
    has_query_term_strategy = bool(coordinate_gate.context_value(route_context, "Codex查询词策略"))
    has_strategy = coordinate_gate.has_query_logic_strategy_choice(route_context)
    structure_conversion_status = coordinate_gate.structure_conversion_status(route_context)
    has_structure_conversion = bool(structure_conversion_status.get("ok"))
    revision_ledger_status = coordinate_gate.interactive_revision_ledger_status(route_context)
    has_revision_ledger = bool(revision_ledger_status.get("ok"))
    has_source_anchor = bool(
        rows
        and (
            clean(first_candidate.get("segment_no"))
            or clean(first_candidate.get("chapter_no"))
            or clean(first_candidate.get("source_sentence"))
            or clean(first_candidate.get("material_source_sentences"))
            or clean(first_candidate.get("atom_code"))
        )
    )
    intersection_count = nearest_pairs + cooccurrence + source_atoms + source_sentences
    steps = [
        _eight_step_row(
            1,
            "归一",
            "完成" if has_query_term_strategy and has_query_terms and has_strategy and has_structure_conversion and has_revision_ledger else "阻断",
            f"Codex查询词策略={'有' if has_query_term_strategy else '缺'}；Codex查询词={'有' if has_query_terms else '缺'}；查询逻辑策略={'有' if has_strategy else '缺'}；结构转化表={'有' if has_structure_conversion else '缺'}；现场修正活账={'通过' if has_revision_ledger else '阻断'}；取材门=坐标。",
            "坐标入口词路 + 策略学习后结构转化 + 人物变量归一",
            [paths.get("tokens", ""), paths.get("route_context", "")],
        ),
        _eight_step_row(
            2,
            "收点",
            "完成" if rows or term_hits or coordinate_hits else "阻断",
            f"候选行={len(rows)}；词位命中={term_hits}；坐标命中={coordinate_hits}。",
            "全文词位库 + 变量投影库",
            [paths.get("bundle", "")],
        ),
        _eight_step_row(
            3,
            "交集",
            "完成" if rows or intersection_count else "阻断",
            f"距离对={nearest_pairs}；共现场={cooccurrence}；来源原子={source_atoms}；原文句={source_sentences}。",
            "字位桥表 + 距离/共场/来源交集",
            [paths.get("bundle", "")],
        ),
        _eight_step_row(
            4,
            "路由门",
            "完成",
            f"material_admission_status={admission_status}；第一取材入口=坐标材料门；坐标取材链已登记。",
            "坐标材料门准入凭证",
            [paths.get("admission_voucher_json", "")],
        ),
        _eight_step_row(
            5,
            "分类",
            "完成" if evidence_layers or clean(bundle.get("final_answer_status")) or clean(first_candidate.get("material_status")) else "阻断",
            f"evidence_layers={'、'.join(evidence_layers)}；final_answer_status={clean(bundle.get('final_answer_status'))}；material_status={clean(first_candidate.get('material_status'))}。",
            "证据层级 + 材料状态字段",
            [paths.get("bundle", "")],
        ),
        _eight_step_row(
            6,
            "回原文",
            "完成" if has_source_anchor or source_sentences > 0 else "阻断",
            f"来源锚点={'有' if has_source_anchor else '缺'}；source_sentences={source_sentences}。",
            "原子段 / 回目 / 原文句锚点",
            [paths.get("markdown", ""), paths.get("admission_voucher_json", "")],
        ),
        _eight_step_row(
            7,
            "入材料池",
            "完成" if admission_status == "准入待判" else "阻断",
            f"material_admission_status={admission_status}。",
            "坐标候选 -> 材料池四态判定入口",
            [paths.get("admission_voucher_json", ""), paths.get("admission_voucher_md", "")],
        ),
        _eight_step_row(
            8,
            "写答案",
            "未执行",
            "坐标材料包程序只到材料池入口；最终答案必须等待材料池四态、精读材料词、写作前原文追证完成后生成。",
            "硬阻断：候选不作答",
            [paths.get("admission_voucher_md", "")],
        ),
    ]
    completed = sum(1 for row in steps if row["status"] == "完成")
    return {
        "query_head": "进入坐标查询",
        "lane": "coordinate",
        "coordinate_spine": COORDINATE_EIGHT_STEP_SPINE,
        "coordinate_program_scope": "坐标查询工程只负责坐标取材、库表验链、材料池入口凭证。",
        "steps": steps,
        "completed_or_ready_steps": completed,
        "total_steps": len(COORDINATE_EIGHT_STEP_SPINE),
        "answer_gate": {
            "write_answer_allowed": False,
            "program_answer_written": False,
            "reason": "坐标查询工程只负责编码坐标取材、库表验链、送入材料池；不能把候选升级成最终答案。",
        },
    }


def render_markdown(bundle: dict[str, Any], route_context: str) -> str:
    rows = bundle.get("rows") or []
    lines = [
        "# 坐标材料池入口候选",
        "",
        "## 入口令牌",
        "",
        "- 取材门：坐标",
        "- recall_gate：coordinate",
        "- 第一取材入口：坐标材料门",
        "- 坐标入口状态：已确认",
        "- 坐标第一动作：坐标取材",
        "",
        "## 查询词路",
        "",
    ]
    for label in (
        "Codex查询逻辑策略",
        "Codex结构转化表",
        "Codex子问题",
        "Codex子问题策略队列",
        "Codex查询词策略",
        "Codex查询词",
        "Codex强复合",
        "Codex词角色",
        "Codex查证顺序",
        "Codex材料升级条件",
    ):
        value = (
            coordinate_gate.subquestion_strategy_queue_value(route_context)
            if label == "Codex子问题策略队列"
            else coordinate_gate.context_value(route_context, label)
        )
        if value:
            lines.append(f"- {label}：{value}")
    lines.extend(
        [
            "- 人物先过归一强令牌；人物变量优先按 variable_value_name 精确命中。",
            "- 明确字词先走全文词位库；变量库负责定点；同场/距离只生成候选。",
            "- 候选送入材料池入口：不写最终答案。",
            "",
            "## 材料包状态",
            "",
            f"- status：{clean(bundle.get('status'))}",
            f"- final_answer_status：{clean(bundle.get('final_answer_status'))}",
            f"- evidence_layers：{'、'.join(bundle.get('evidence_layers') or [])}",
            f"- query_type：{' / '.join(bundle.get('query_type') or [])}",
            f"- rows：{len(rows)}",
            f"- warnings：{'；'.join(bundle.get('warnings') or [])}",
            "",
            "## 候选预览",
            "",
        ]
    )
    for index, row in enumerate(rows[:20], 1):
        lines.extend(
            [
                f"### {index}. {clean(row.get('atom_id'))} / {clean(row.get('atom_code'))}",
                "",
                f"- chapter_no：{row.get('chapter_no')}",
                f"- segment_no：{clean(row.get('segment_no'))}",
                f"- score：{row.get('score')}",
                f"- direct_terms：{clean(row.get('coordinate_direct_terms'))}",
                f"- distance_basis：{clean(row.get('distance_basis'))}",
                f"- evidence_layer：{clean(row.get('evidence_layer'))}",
                f"- final_answer_status：{clean(row.get('final_answer_status'))}",
                f"- source_sentence：{clean(row.get('source_sentence'))}",
                "",
            ]
        )
    return "\n".join(lines)


def coordinate_admission_voucher(bundle: dict[str, Any], route_context: str, paths: dict[str, str]) -> dict[str, Any]:
    rows = bundle.get("rows") or []
    first = rows[0] if rows else {}
    has_source_anchor = bool(
        rows
        and (
            clean(first.get("segment_no"))
            or clean(first.get("chapter_no"))
            or clean(first.get("source_sentence"))
            or clean(first.get("material_source_sentences"))
            or clean(first.get("atom_code"))
        )
    )
    has_route_note = bool(coordinate_gate.context_value(route_context, "Codex查询词"))
    has_query_term_strategy = bool(coordinate_gate.context_value(route_context, "Codex查询词策略"))
    has_strategy_note = coordinate_gate.has_query_logic_strategy_choice(route_context)
    structure_conversion_status = coordinate_gate.structure_conversion_status(route_context)
    has_structure_conversion = bool(structure_conversion_status.get("ok"))
    revision_ledger = coordinate_gate.build_interactive_revision_ledger("", route_context)
    revision_ledger_status = revision_ledger.get("revision_status") or {}
    has_revision_ledger = bool(revision_ledger_status.get("ok"))
    admission_status = "准入待判" if rows and has_source_anchor and has_query_term_strategy and has_route_note and has_strategy_note and has_structure_conversion and has_revision_ledger else "阻断待补"
    admission_reason = (
        "具备坐标取材来源、原子段/回目/原文句等锚点，并具备 Codex 查询词策略、查询词路、查询逻辑策略和结构转化表；可交给材料池四态判定。"
        if admission_status == "准入待判"
        else "缺少候选、来源锚点、Codex 查询词策略、查询词路、查询逻辑策略、结构转化表或现场修正活账，只能作为补证对象，不能进入写作。"
    )
    eight_step_status = build_coordinate_eight_step_status(bundle, route_context, paths, admission_status, first)
    return {
        "voucher_name": "坐标入材料池凭证门",
        "material_admission_status": admission_status,
        "material_admission_reason": admission_reason,
        "material_admission_rule": "坐标候选必须具备坐标取材来源、入口词路、查询逻辑策略、结构转化表、现场修正活账、原子段/回目/原文句锚点，才可交给材料池四态判定。",
        "interactive_revision_ledger": revision_ledger,
        "eight_step_status": eight_step_status,
        "route_credentials": {
            "取材门": "坐标",
            "recall_gate": "coordinate",
            "坐标入口状态": "已确认",
            "第一取材入口": "坐标材料门",
            "后身": "材料池四态判定 -> 精读材料词 -> 写作前原文追证",
            "现场修正活账": "通过" if has_revision_ledger else "阻断",
        },
        "query_route": {
            label: (
                coordinate_gate.subquestion_strategy_queue_value(route_context)
                if label == "Codex子问题策略队列"
                else coordinate_gate.context_value(route_context, label)
            )
            for label in (
                "Codex查询逻辑策略",
                "Codex结构转化表",
                "Codex子问题",
                "Codex子问题拆解策略",
                "Codex子问题两两交集表",
                "Codex子问题可查性裁判",
                "Codex子问题策略队列",
                "Codex查询词策略",
                "Codex查询词",
                "Codex强复合",
                "Codex词角色",
                "Codex查证顺序",
                "Codex材料升级条件",
                "Codex取词查表策略",
                "Codex表路收点方法",
                "Codex现场修正活账",
                "Codex修正归类",
                "Codex回到门",
                "Codex当前激活版本",
                "Codex最终综合依据",
            )
        },
        "structure_conversion_gate": structure_conversion_status,
        "interactive_revision_ledger_gate": revision_ledger_status,
        "admission_counts": {
            "query_type": bundle.get("query_type") or [],
            "variables": bundle.get("variables") or [],
            "term_hits_count": len(bundle.get("term_hits") or []),
            "coordinate_hits_count": len(bundle.get("coordinate_hits") or []),
            "nearest_pairs_count": len(bundle.get("nearest_pairs") or []),
            "cooccurrence_count": len(bundle.get("cooccurrence") or []),
            "source_atoms_count": len(bundle.get("source_atoms") or []),
            "source_sentences_count": len(bundle.get("source_sentences") or []),
            "evidence_layers": bundle.get("evidence_layers") or [],
            "final_answer_status": bundle.get("final_answer_status") or "",
            "warnings": bundle.get("warnings") or [],
            "status": bundle.get("status") or "",
        },
        "first_candidate_admission_fields": {
            "codex_query_lane": "coordinate",
            "source_system": "坐标材料门",
            "source_trace": "词位库 / 变量投影库 / 字位桥表 / 距离共场",
            "evidence_status": first.get("material_status", ""),
            "evidence_layer": first.get("evidence_layer", ""),
            "final_answer_status": first.get("final_answer_status", ""),
            "self_report_dream_rule": first.get("self_report_dream_rule", ""),
            "atom_code": first.get("atom_code", ""),
            "segment_no": first.get("segment_no", ""),
            "chapter_no": first.get("chapter_no", ""),
            "source_sentence": first.get("source_sentence", ""),
            "codex_original_passages": first.get("source_sentence", ""),
            "material_term_hits": first.get("material_term_hits", ""),
            "material_coordinate_hits": first.get("material_coordinate_hits", ""),
            "material_nearest_pairs": first.get("material_nearest_pairs", ""),
            "material_cooccurrence": first.get("material_cooccurrence", ""),
            "material_source_atoms": first.get("material_source_atoms", ""),
            "material_source_sentences": first.get("material_source_sentences", ""),
            "material_status": first.get("material_status", ""),
        },
        "voucher_files": paths,
        "hard_stop": "本清单不是最终答案；缺材料池四态、精读材料词、写作前原文追证时不得写红楼解语。",
    }



def render_revision_ledger_markdown(ledger: dict[str, Any]) -> str:
    status = ledger.get("revision_status") if isinstance(ledger.get("revision_status"), dict) else {}
    trigger = status.get("trigger_profile") if isinstance(status.get("trigger_profile"), dict) else {}
    fields = status.get("field_values") if isinstance(status.get("field_values"), dict) else {}
    lines = [
        "# 坐标工程｜现场交互修正活账",
        "",
        f"- status：{'通过' if status.get('ok') else '阻断'}",
        f"- required：{status.get('required')}",
        f"- reason：{clean(status.get('reason'))}",
        f"- return_gate：{clean(ledger.get('return_gate'))}",
        f"- active_versions：{clean(ledger.get('active_versions'))}",
        f"- final_synthesis_basis：{clean(ledger.get('final_synthesis_basis'))}",
        "",
        "## 触发判定",
        "",
        f"- proceed_signal：{trigger.get('proceed_signal')}",
        f"- categories：{'、'.join(trigger.get('categories') or [])}",
        f"- matched_terms：{'、'.join(trigger.get('matched_terms') or [])}",
        f"- recommended_return_gate：{clean(trigger.get('recommended_return_gate'))}",
        "",
        "## 字段",
        "",
    ]
    for key, value in fields.items():
        if clean(value):
            lines.append(f"- {key}：{clean(value)}")
    if not any(clean(value) for value in fields.values()):
        lines.append("- 未写显式字段；首轮或按上下文讨论焦点自动判定。")
    lines.extend(["", "## 当前子问题拆解策略快照", ""])
    strategy = ledger.get("current_subquestion_decomposition_strategy")
    lines.append(f"- {clean(strategy) or '未写入 Codex子问题拆解策略。'}")
    subq_status = ledger.get("current_subquestion_strategy_status") if isinstance(ledger.get("current_subquestion_strategy_status"), dict) else {}
    lines.append(f"- 可查性状态：{'通过' if subq_status.get('ok') else '阻断'}｜{clean(subq_status.get('reason'))}")
    lines.extend(["", "## 当前子问题快照", ""])
    subqs = ledger.get("current_subquestion_snapshot") or []
    if subqs:
        lines.extend(f"- {item}" for item in subqs)
    else:
        lines.append("- 未写入 Codex子问题；不能临时编子问题。")
    lines.extend(["", "## 当前子问题两两交集表快照", ""])
    pairwise_table = ledger.get("current_subquestion_pairwise_table_snapshot") or []
    if pairwise_table:
        lines.extend(f"- {item}" for item in pairwise_table)
    else:
        lines.append("- 未写入 Codex子问题两两交集表；可暂以策略队列里的两两可查记录代替。")
    lines.extend(["", "## 当前子问题策略队列快照", ""])
    queue = ledger.get("current_subquestion_strategy_queue_snapshot") or []
    if queue:
        lines.extend(f"- {item}" for item in queue)
    else:
        lines.append("- 未写入 Codex子问题策略队列。")
    lines.extend(["", "## 当前取词-查表策略快照", ""])
    strategy_snapshot = ledger.get("current_strategy_snapshot") if isinstance(ledger.get("current_strategy_snapshot"), dict) else {}
    for key, value in strategy_snapshot.items():
        lines.append(f"- {key}：{clean(value) or '未写入'}")
    warnings = status.get("warnings") or []
    lines.extend(["", "## 提示", ""])
    if warnings:
        lines.extend(f"- {clean(item)}" for item in warnings)
    else:
        lines.append("- 无。")
    return "\n".join(lines).rstrip() + "\n"

def render_admission_voucher_markdown(voucher: dict[str, Any]) -> str:
    counts = voucher.get("admission_counts") or {}
    fields = voucher.get("first_candidate_admission_fields") or {}
    files = voucher.get("voucher_files") or {}
    eight_step_status = voucher.get("eight_step_status") if isinstance(voucher.get("eight_step_status"), dict) else {}
    lines = [
        "# 坐标入材料池凭证门",
        "",
        f"- material_admission_status：{clean(voucher.get('material_admission_status'))}",
        f"- material_admission_reason：{clean(voucher.get('material_admission_reason'))}",
        f"- material_admission_rule：{clean(voucher.get('material_admission_rule'))}",
        "- 后续流程：材料池四态判定 -> 精读材料词 -> 写作前原文追证",
        "- 硬阻断：本凭证门不是最终答案。",
        "",
        "## 坐标工程八步状态",
        "",
        f"- 入口令牌：{clean(eight_step_status.get('query_head'))}",
        f"- 坐标主线：{' -> '.join(eight_step_status.get('coordinate_spine') or [])}",
        f"- 工程范围：{clean(eight_step_status.get('coordinate_program_scope'))}",
        f"- 写答案许可：{'是' if eight_step_status.get('answer_gate', {}).get('write_answer_allowed') else '否'}",
        "",
    ]
    for row in eight_step_status.get("steps") or []:
        lines.append(f"{row.get('step_no')}. {row.get('name')}：{row.get('status')}｜{row.get('program_evidence')}")
    lines.extend(
        [
            "",
        "## 查询词路",
        "",
        ]
    )
    for key, value in (voucher.get("query_route") or {}).items():
        if clean(value):
            lines.append(f"- {key}：{clean(value)}")
    revision_gate = voucher.get("interactive_revision_ledger_gate") if isinstance(voucher.get("interactive_revision_ledger_gate"), dict) else {}
    lines.extend(["", "## 现场修正活账门", ""])
    lines.append(f"- status：{'通过' if revision_gate.get('ok') else '阻断'}")
    lines.append(f"- required：{revision_gate.get('required')}")
    lines.append(f"- reason：{clean(revision_gate.get('reason'))}")
    if clean(files.get("revision_ledger_md")):
        lines.append(f"- ledger_md：{clean(files.get('revision_ledger_md'))}")
    structure_gate = voucher.get("structure_conversion_gate") if isinstance(voucher.get("structure_conversion_gate"), dict) else {}
    lines.extend(["", "## 结构转化门", ""])
    lines.append(f"- status：{'通过' if structure_gate.get('ok') else '阻断'}")
    lines.append(f"- reason：{clean(structure_gate.get('reason'))}")
    if clean(structure_gate.get("value")):
        lines.append(f"- Codex结构转化表：{clean(structure_gate.get('value'))}")
    lines.extend(["", "## 准入计数", ""])
    for key, value in counts.items():
        lines.append(f"- {key}：{value}")
    lines.extend(["", "## 首条候选入池凭证", ""])
    for key, value in fields.items():
        lines.append(f"- {key}：{clean(value)}")
    lines.extend(["", "## 文件", ""])
    for key, value in files.items():
        lines.append(f"- {key}：{value}")
    return "\n".join(lines)


def build_package(question: str, out_root: Path, limit: int, route_context: str = "") -> dict[str, str]:
    route_context = clean(route_context)
    if not coordinate_gate.context_value(route_context, "Codex查询词策略"):
        raise SystemExit("坐标材料门缺 Codex查询词策略：必须由 AI 先说明词网取舍，工具不能只拿裸查询词入库。")
    if not coordinate_gate.context_value(route_context, "Codex查询词"):
        raise SystemExit("坐标材料门缺 Codex查询词：必须由 AI 先取词；工具只验词、归一、查表、入材料池。")
    strategy_value = coordinate_gate.query_logic_strategy_value(route_context)
    if not strategy_value:
        raise SystemExit("坐标材料门缺 Codex查询逻辑策略：AI取词后必须先进入 000E_B_坐标工程查询逻辑策略经验模板组_新窗口学习入口.md 选择一个坐标策略模板。")
    if coordinate_gate.query_logic_strategy_requires_subquestions(route_context) and not coordinate_gate.context_value(route_context, "Codex子问题"):
        raise SystemExit("坐标材料门缺 Codex子问题：选择模板00｜拆子问题策略时，必须先列出子问题。")
    subquestion_queue_status = coordinate_gate.subquestion_strategy_queue_status(route_context)
    if not subquestion_queue_status.get("ok"):
        raise SystemExit("坐标材料门缺子问题策略队列：" + coordinate_gate.clean(subquestion_queue_status.get("reason")))
    subquestion_decomposition_status = coordinate_gate.subquestion_decomposition_strategy_status(route_context)
    if not subquestion_decomposition_status.get("ok"):
        raise SystemExit("坐标材料门缺子问题拆解策略：" + coordinate_gate.clean(subquestion_decomposition_status.get("reason")))
    if not coordinate_gate.has_query_logic_strategy_choice(route_context):
        raise SystemExit("坐标材料门的 Codex查询逻辑策略无效：不能写待定、不确定、不用策略或无策略；必须选择具体模板，或选择模板00｜拆子问题策略并列出子问题。")
    structure_conversion_status = coordinate_gate.structure_conversion_status(route_context)
    revision_ledger_status = coordinate_gate.interactive_revision_ledger_status(route_context)
    if not revision_ledger_status.get("ok"):
        raise SystemExit("坐标材料门缺现场修正活账：" + coordinate_gate.clean(revision_ledger_status.get("reason")))
    if not structure_conversion_status.get("ok"):
        raise SystemExit("坐标材料门缺 Codex结构转化表：" + coordinate_gate.clean(structure_conversion_status.get("reason")))
    if not coordinate_gate.is_coordinate_gate(question, route_context):
        route_context = "\n".join(
            [
                "取材门：坐标",
                "recall_gate：coordinate",
                "坐标入口状态：已确认",
                "第一取材入口：坐标材料门",
                route_context,
            ]
        ).strip()
    bundle = coordinate_gate.material_pack_bundle(question, route_context=route_context, limit=limit)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = out_root / f"{timestamp}_{safe_name(question)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "out_dir": str(out_dir),
        "tokens": str(out_dir / "00_入口令牌.json"),
        "route_context": str(out_dir / "01_查询词路.md"),
        "revision_ledger_json": str(out_dir / "00_现场交互修正活账.json"),
        "revision_ledger_md": str(out_dir / "00_现场交互修正活账.md"),
        "bundle": str(out_dir / "02_坐标材料池入口候选.json"),
        "markdown": str(out_dir / "03_材料池入口_候选不作答.md"),
        "admission_voucher_json": str(out_dir / "04_坐标入材料池凭证门.json"),
        "admission_voucher_md": str(out_dir / "04_坐标入材料池凭证门.md"),
    }
    write_json(
        Path(paths["tokens"]),
        {
            "取材门": "坐标",
            "recall_gate": "coordinate",
            "坐标入口状态": "已确认",
            "坐标第一动作": "坐标取材",
            "第一取材入口": "坐标材料门",
            "坐标取材完成后": "送入材料池入口",
        },
    )
    Path(paths["route_context"]).write_text(route_context, encoding="utf-8")
    revision_ledger = coordinate_gate.build_interactive_revision_ledger(question, route_context)
    write_json(Path(paths["revision_ledger_json"]), revision_ledger)
    Path(paths["revision_ledger_md"]).write_text(render_revision_ledger_markdown(revision_ledger), encoding="utf-8")
    write_json(Path(paths["bundle"]), bundle)
    Path(paths["markdown"]).write_text(render_markdown(bundle, route_context), encoding="utf-8")
    voucher = coordinate_admission_voucher(bundle, route_context, paths)
    write_json(Path(paths["admission_voucher_json"]), voucher)
    Path(paths["admission_voucher_md"]).write_text(render_admission_voucher_markdown(voucher), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a formal coordinate material package.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--route-context", default="")
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()
    paths = build_package(args.question, Path(args.out_root), args.limit, args.route_context)
    print(json.dumps(paths, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
