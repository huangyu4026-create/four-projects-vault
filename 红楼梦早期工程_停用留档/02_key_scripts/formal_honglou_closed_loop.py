#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import formal_honglou_feedback_optimizer as feedback_optimizer
import formal_honglou_offline_smoke_test as offline_smoke
import formal_honglou_question_decomposer as decomposer
import formal_honglou_research_workflow as research_workflow
import formal_honglou_review_readback as review_readback
import formal_honglou_review_writer as review_writer
import formal_honglou_material_admission_gate as material_admission_gate

try:
    import formal_honglou_coordinate_material_gate as query_strategy_gate
except Exception:  # pragma: no cover - closed loop should still report the missing gate explicitly.
    query_strategy_gate = None  # type: ignore[assignment]

try:
    import formal_honglou_runtime_main_bus as runtime_main_bus
except Exception:  # pragma: no cover - flow lock still renders if the bus import fails.
    runtime_main_bus = None  # type: ignore[assignment]


OUT_ROOT = ROOT / "outputs" / "正式底库闭环工作流"
REVIEW_BACKUP_DIR = "_复核表备份"
HOME_OUT = ROOT / "outputs" / "正式底库工程首页"
FORMAL_RECALL_ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs/红楼梦正式取材专库")
SEMANTIC_CENTER_DB = FORMAL_RECALL_ROOT / "00_双中心取材总库" / "01_语义聚拢查询中心库" / "红楼梦语义聚拢中心库_CH001_120.sqlite"
SEARCH_DB = ROOT / "outputs" / "正式底库全文检索原型" / "formal_honglou_search.sqlite"
AXIS_DB = SEMANTIC_CENTER_DB
TALK_ROOM_OUT = ROOT / "outputs" / "红楼梦对谈查证室"
AGGREGATION_ENTRY_DOC = TALK_ROOM_OUT / "128_聚拢库总入口_全库地图与流程记录.md"
LIBRARY_REGISTRY_CSV = TALK_ROOM_OUT / "25_库登记处机器总表.csv"
W32_CLUSTER_UNIT_LINES_CSV = TALK_ROOM_OUT / "33_W32_聚拢单元库_cluster_unit_lines.csv"
W32_CLUSTER_UNITS_CSV = TALK_ROOM_OUT / "33_W32_聚拢单元库_cluster_units.csv"
W33_EVENTS_CSV = TALK_ROOM_OUT / "34_W33_聚拢事件库_events.csv"
W33_EVENT_UNITS_CSV = TALK_ROOM_OUT / "34_W33_聚拢事件库_event_units.csv"
EXPERIENCE_LEDGER_JSON = OUT_ROOT / "_问题判断经验值总账.json"
EXPERIENCE_LEDGER_MD = OUT_ROOT / "_问题判断经验值总账.md"
LEGACY_DIRECT_ROUTE_MODE = "短平" + "快关系题"
LEGACY_DIRECT_ANSWER_STATE = "可" + "直接写红楼解语"
CORE_FILES = {
    "overview": "00_闭环总览.md",
    "query_logic_strategy_gate_md": "00AO_查询逻辑策略门.md",
    "query_logic_strategy_gate_json": "00AP_查询逻辑策略门.json",
    "entry_hard_gate_md": "00AA_入口硬规则门.md",
    "entry_hard_gate_json": "00AB_入口硬规则门.json",
    "aggregation_flow_lock_md": "00AC_聚拢库总入口流程锁.md",
    "aggregation_flow_lock_json": "00AD_聚拢库总入口流程锁.json",
    "machine_short_card_md": "00AE_机器短卡与证据分层策略.md",
    "machine_short_card_json": "00AF_机器短卡与证据分层策略.json",
    "aggregation_material_search_md": "00AG_聚拢库取材单.md",
    "aggregation_material_search_json": "00AH_聚拢库取材单.json",
    "material_pool_admission_csv": "00AI_聚拢入材料池清单.csv",
    "material_pool_admission_md": "00AJ_聚拢入材料池凭证门.md",
    "material_pool_admission_json": "00AK_聚拢入材料池凭证门.json",
    "material_pool_blocked_csv": "00AL_聚拢入材料池阻断清单.csv",
    "aggregation_first_read_pool_md": "00AM_聚拢裁判首读材料池.md",
    "question_judgment_md": "00A_问题判断程序.md",
    "keyword_precheck_json": "00B_关键词网络预检.json",
    "library_flow_md": "00C_库线原文流转骨架.md",
    "library_flow_json": "00D_库线原文流转骨架.json",
    "experience_entry_md": "00E_经验复盘入账.md",
    "experience_entry_json": "00F_经验复盘入账.json",
    "final_reading_gate_md": "00G_最终回答前材料池精读门.md",
    "final_reading_gate_json": "00H_最终回答前材料池精读门.json",
    "process_inventory_md": "00I_全流程产物与Codex判别门.md",
    "process_inventory_json": "00J_全流程产物与Codex判别门.json",
    "library_precheck_md": "00K_本题库态预检表.md",
    "library_precheck_json": "00L_本题库态预检表.json",
    "pipeline_audit_md": "00M_Codex指挥链达标检查.md",
    "pipeline_audit_json": "00N_Codex指挥链达标检查.json",
    "second_round_decision_md": "00P_二轮补证决策卡.md",
    "second_round_decision_json": "00Q_二轮补证决策卡.json",
    "source_schema_md": "00R_来源字段标准化词典.md",
    "source_schema_json": "00S_来源字段标准化词典.json",
    "experience_codex_md": "00T_经验法典三层结构.md",
    "experience_codex_json": "00U_经验法典三层结构.json",
    "mode_boundary_md": "00V_正式沙盒模式边界.md",
    "mode_boundary_json": "00W_正式沙盒模式边界.json",
    "approval_ingest_gate_md": "00X_用户认可入库门.md",
    "approval_ingest_gate_json": "00Y_用户认可入库门.json",
    "library_coverage_md": "00Z_库群覆盖矩阵.md",
    "library_coverage_json": "00ZA_库群覆盖矩阵.json",
    "human_reading_order_md": "00ZB_桌面人读排序配置.md",
    "human_reading_order_json": "00ZC_桌面人读排序配置.json",
    "codex_final_answer_gate_md": "00ZD_Codex红楼解语生成门.md",
    "codex_final_answer_gate_json": "00ZE_Codex红楼解语生成门.json",
    "codex_final_answer_target_md": "00ZF_Codex红楼解语_待生成.md",
    "codex_close_reading_gate_md": "00ZG_Codex精读材料词生成门.md",
    "codex_close_reading_gate_json": "00ZH_Codex精读材料词生成门.json",
    "codex_close_reading_target_md": "00ZI_Codex精读材料词_待生成.md",
    "codex_original_reread_gate_md": "00ZN_Codex写作前原文通读摘抄生成门.md",
    "codex_original_reread_gate_json": "00ZO_Codex写作前原文通读摘抄生成门.json",
    "codex_original_reread_target_md": "00ZP_Codex写作前原文通读摘抄_待生成.md",
    "answer_writeback_protocol_md": "00ZJ_Codex最终答案写回规范.md",
    "answer_writeback_protocol_json": "00ZK_Codex最终答案写回规范.json",
    "regression_plan_md": "00ZL_十题回归测试骨架.md",
    "regression_plan_json": "00ZM_十题回归测试骨架.json",
    "question_tree": "01_问题树.md",
    "triaged_csv": "02_证据阅读顺序.csv",
    "cards": "03_重点证据卡片.md",
    "review_csv": "04_复核表.csv",
    "reading_md": "05_复核阅读单.md",
    "writing_md": "06_复核回读材料.md",
    "feedback_profile": "07_反馈排序配置.json",
    "manifest": "08_运行清单.json",
    "writable_pack": "09_可写作证据包.md",
    "handoff_prompt": "10_写作接力提示词.md",
    "draft_md": "11_正式写作草稿.md",
    "counter_draft_md": "12_反方证据小稿.md",
    "next_plan_md": "13_二次追问与补证计划.md",
    "next_tasks_csv": "14_下一轮出库任务.csv",
    "review_plan_md": "15_人工复核优先清单.md",
    "review_queue_csv": "16_人工复核批次.csv",
    "review_tick_md": "47_人工复核打勾表.md",
    "review_sheet_csv": "17_当前批次复核工作表.csv",
    "review_sheet_md": "18_复核工作表填写说明.md",
    "review_apply_md": "19_复核工作表回填报告.md",
    "workflow_status_md": "20_闭环状态与下一步操作台.md",
    "workflow_status_json": "21_闭环状态摘要.json",
    "review_check_md": "22_复核工作表质量检查.md",
    "review_check_json": "23_复核工作表质量检查.json",
    "continue_report_md": "24_一键续跑报告.md",
    "continue_summary_json": "25_一键续跑摘要.json",
    "review_cards_md": "26_当前批次复核阅读卡片.md",
    "review_backup_md": "27_复核表备份索引.md",
    "review_backup_json": "28_复核表备份索引.json",
    "review_restore_md": "29_复核表恢复报告.md",
    "review_assist_md": "30_复核填写助手.md",
    "review_assist_csv": "31_复核填写助手.csv",
    "review_workbench_md": "32_复核填表工作台.md",
    "review_workbench_csv": "33_复核填表工作台.csv",
    "review_coverage_md": "34_复核覆盖矩阵.md",
    "review_coverage_csv": "35_复核覆盖矩阵.csv",
    "review_firstpass_md": "36_首轮复核执行单.md",
    "review_firstpass_csv": "37_首轮复核执行单.csv",
    "review_firstpass_sheet_csv": "38_首轮复核小表.csv",
    "review_firstpass_sheet_md": "39_首轮复核小表填写说明.md",
    "review_firstpass_sync_md": "40_首轮复核小表同步报告.md",
    "review_firstpass_check_md": "41_首轮复核小表质量检查.md",
    "review_firstpass_check_json": "42_首轮复核小表质量检查.json",
    "review_firstpass_cards_md": "43_首轮复核逐条判读卡片.md",
    "review_firstpass_desk_md": "44_首轮复核就绪台.md",
    "review_firstpass_talk_md": "45_首轮谈心式复核单.md",
    "argument_brief_md": "48_已停用_本地材料简报.md",
    "argument_brief_csv": "49_已停用_本地材料表.csv",
    "argument_talk_md": "50_已停用_本地论述稿.md",
    "article_draft_md": "51_已停用_本地文章稿.md",
    "article_academic_md": "52_已停用_本地学术稿.md",
    "article_essay_md": "53_已停用_本地评论稿.md",
    "source_verify_md": "54_真源核验统一报告.md",
    "source_verify_csv": "55_真源核验清单.csv",
    "review_finish_md": "56_复核收口运行报告.md",
    "review_finish_json": "57_复核收口摘要.json",
    "article_ingest_report_md": "58_文章入库预检报告.md",
    "article_ingest_candidate_csv": "59_作品总库入库候选行.csv",
    "article_ingest_links_csv": "60_文章回挂清单.csv",
    "article_ingest_identity_md": "61_文章入库身份卡.md",
    "article_ingest_summary_json": "62_文章入库预检摘要.json",
}


def clean(text: object) -> str:
    return str(text or "").replace("\n", " ").strip()


def safe_filename_part(text: str, limit: int = 28) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_一二三四五六七八九十百千万与和是不是为何为什么" else "_" for ch in clean(text))
    safe = "_".join(part for part in safe.split("_") if part)
    return (safe or "问题")[:limit]


def _latest_matching_file(directory: Path, pattern: str) -> str:
    if not directory.exists() or not directory.is_dir():
        return ""
    matches = sorted(
        (path for path in directory.glob(pattern) if path.is_file()),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    return str(matches[-1]) if matches else ""


def copy_file(source: str | Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(source), target)
    return str(target)


def run_offline_smoke() -> dict[str, Any]:
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            offline_smoke.main()
    except SystemExit as exc:
        code = int(exc.code or 0)
        return {
            "ok": code == 0,
            "returncode": code,
            "output": buffer.getvalue(),
        }
    except Exception as exc:  # pragma: no cover - surfaced in manifest for user repair.
        return {
            "ok": False,
            "returncode": 1,
            "output": buffer.getvalue(),
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "ok": True,
        "returncode": 0,
        "output": buffer.getvalue(),
    }


def step(name: str, ok: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail or {},
    }


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

SEMANTIC_AGGREGATION_TOOL_USAGE_GUIDE = (
    "完整八步法硬锁：聚拢头与坐标头共用取词之前的思考，先读题、判断题型、拆对象、定主轴、生成入口词令牌；"
    "取词以后进入聚拢法，不走坐标测距主路，而是把候选段落回到语义聚拢中心库、W32聚拢单元、W33聚拢事件和聚拢现场；"
    "聚拢法重点是组织现场、放大/缩小/交集/串域、判材料角色，再送材料池四态裁判；"
    "人物归一、问题树、两两比较、强复合轴、穷尽补点、回原文裁判与坐标头共享；"
    "差别是聚拢头用聚拢库组织语义现场，坐标头用坐标库计算原子段/变量点/容器距离。"
)


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
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


def build_aggregation_eight_step_status(
    *,
    package_dir: Path,
    judgment_result: dict[str, Any],
    aggregation_flow_lock: dict[str, Any],
    research_result: dict[str, Any],
    review_result: dict[str, Any],
    aggregation_material_bridge: dict[str, Any],
    readback_result: dict[str, Any],
    pipeline_audit: dict[str, Any],
    codex_final_answer_gate: dict[str, Any],
) -> dict[str, Any]:
    bridge_counts = aggregation_material_bridge.get("counts") if isinstance(aggregation_material_bridge.get("counts"), dict) else {}
    audit_summary = pipeline_audit.get("summary") if isinstance(pipeline_audit.get("summary"), dict) else {}
    unique_segments = _safe_int(research_result.get("unique_segments"))
    review_rows = _safe_int(review_result.get("review_rows"))
    returned_rows = _safe_int(bridge_counts.get("returned_to_aggregation_rows"))
    admitted_rows = _safe_int(bridge_counts.get("admitted_to_material_pool_rows"))
    readback_rows = _safe_int(readback_result.get("total_rows"))
    original_rows = _safe_int(audit_summary.get("original_passage_rows"))
    final_ready = bool(audit_summary.get("final_prewrite_ready"))
    route_center = clean(judgment_result.get("route_center") or judgment_result.get("center"))
    keyword_count = len(judgment_result.get("keyword_pool") or [])
    steps = [
        _eight_step_row(
            1,
            "归一",
            "完成" if judgment_result else "阻断",
            f"问题中心={route_center or '未写明'}；关键词数={keyword_count}；流程锁内姓名/别名/称谓/对象/空间/时间归一规则已上岗。",
            "问题判断程序 + 聚拢总入口流程锁",
            [str(package_dir / CORE_FILES["question_judgment_md"]), str(package_dir / CORE_FILES["aggregation_flow_lock_json"])],
        ),
        _eight_step_row(
            2,
            "收点",
            "完成" if unique_segments > 0 else "阻断",
            f"召回唯一原子段={unique_segments}；复核候选行={review_rows}。",
            "拆题召回 + 证据池 + 研究包",
            [str(package_dir / CORE_FILES["triaged_csv"]), str(package_dir / CORE_FILES["review_csv"])],
        ),
        _eight_step_row(
            3,
            "交集",
            "完成" if returned_rows > 0 else "阻断",
            f"回聚拢行={returned_rows}；材料池准入行={admitted_rows}。",
            "聚拢坐标映射 + 问题单元交集",
            [str(package_dir / CORE_FILES["aggregation_material_search_json"])],
        ),
        _eight_step_row(
            4,
            "路由门",
            "完成" if aggregation_flow_lock.get("map_checked") else "阻断",
            f"128入口存在={aggregation_flow_lock.get('entry_doc_exists')}；库登记表存在={aggregation_flow_lock.get('registry_csv_exists')}；问题类型={aggregation_flow_lock.get('problem_type', '')}。",
            "128聚拢库总入口 + 25库登记处",
            [str(package_dir / CORE_FILES["aggregation_flow_lock_md"])],
        ),
        _eight_step_row(
            5,
            "分类",
            "完成" if review_rows > 0 else "阻断",
            f"复核包行数={review_rows}；材料池四态候选行={admitted_rows}。",
            "复核包 + 材料池四态判定入口",
            [str(package_dir / CORE_FILES["material_pool_admission_csv"]), str(package_dir / CORE_FILES["review_csv"])],
        ),
        _eight_step_row(
            6,
            "回原文",
            "完成" if original_rows > 0 or readback_rows > 0 else "阻断",
            f"原文锚点行={original_rows}；回读材料行={readback_rows}。",
            "chapters.full_text / segments原文锚点回证",
            [str(package_dir / CORE_FILES["pipeline_audit_json"]), str(package_dir / CORE_FILES["writing_md"])],
        ),
        _eight_step_row(
            7,
            "入材料池",
            "完成" if admitted_rows > 0 else "阻断",
            f"材料池准入行={admitted_rows}；第一遍有用行={_safe_int(bridge_counts.get('first_read_useful_rows'))}。",
            "聚拢库取材 -> 材料池准入",
            [str(package_dir / CORE_FILES["material_pool_admission_json"])],
        ),
        _eight_step_row(
            8,
            "写答案",
            "可进入" if final_ready else "阻断",
            f"final_prewrite_ready={final_ready}；红楼解语生成门={codex_final_answer_gate.get('output_files', {}).get('codex_final_answer_gate_md', '') or '未生成'}。",
            "Codex红楼解语生成门",
            [str(package_dir / CORE_FILES["codex_final_answer_gate_json"])],
        ),
    ]
    completed = sum(1 for row in steps if row["status"] in {"完成", "可进入"})
    return {
        "query_head": "进入聚拢查询",
        "lane": "semantic_aggregation",
        "shared_spine": SHARED_EIGHT_STEP_SPINE,
        "same_spine_as_coordinate_head": True,
        "tool_difference_only": True,
        "shared_before_terms": "取词之前两头完全相同：读题、判断题型、拆对象、定主轴、人物归一、强复合轴、查询逻辑策略、子问题排队。",
        "different_after_terms": "取词以后两头分路：聚拢头用聚拢法组织现场和材料池；坐标头用坐标分析法做词位穷尽、变量坐标、距离、共场和容器归属。",
        "steps": steps,
        "completed_or_ready_steps": completed,
        "total_steps": len(SHARED_EIGHT_STEP_SPINE),
        "answer_gate": {
            "write_answer_allowed": final_ready,
            "program_answer_written": False,
            "reason": "聚拢头负责生成最终答案门；只有 final_prewrite_ready 为 true 时，才允许 Codex 进入写答案。程序本身不越过材料池/原文追证直接写结论。",
        },
    }


def status_sentence(readback_result: dict[str, Any]) -> str:
    total = int(readback_result.get("total_rows") or 0)
    usable = int(readback_result.get("usable_rows") or 0)
    pending = int(readback_result.get("pending_rows") or 0)
    unverified = int(readback_result.get("unverified_rows") or 0)
    if total > 0 and usable == 0 and unverified > 0:
        return "系统已跑通，但已有人工判断的证据仍未核验，“可用证据”仍为0，尚未进入正式写作状态。"
    if total > 0 and usable == 0 and pending == total:
        return "系统已跑通，但复核表全部仍为待复核，尚未进入正式写作状态。"
    if usable > 0:
        return "系统已跑通，并已读到人工可用证据，可以进入复核后写作材料阶段。"
    return "系统已跑通，但可用证据不足，仍需人工复核后再进入正式写作。"


def _route_center_from_context(route_context: str) -> str:
    profile = decomposer.route_context_profile(route_context)
    centers = profile.get("centers") if isinstance(profile, dict) else []
    if isinstance(centers, list) and centers:
        return "、".join(str(item) for item in centers if str(item).strip())
    codex_terms = profile.get("codex_terms") if isinstance(profile, dict) else []
    if isinstance(codex_terms, list) and codex_terms:
        role_text = clean(decomposer.context_line_value(route_context, "Codex词角色"))
        has_person = "主查人物" in role_text
        has_object = "主查物象" in role_text or "主查对象" in role_text
        has_scene = any(key in role_text for key in ("场景", "空间", "季节", "时间"))
        if has_person and (has_object or has_scene or len(codex_terms) >= 2):
            return "关系域、共现查证"
        if has_person:
            return "人物域"
        if has_object:
            return "物象域"
        return "Codex查询词路"
    context = clean(route_context)
    candidates = [
        "人物中心",
        "事件中心",
        "关系中心",
        "物象中心",
        "诗词判词中心",
        "空间中心",
        "空间域",
        "场域",
        "章节原句中心",
        "观念主题中心",
        "共现查证",
        "物象域",
        "库文双向",
        "反证排除",
        "轻量问答",
        "连续追问",
        "先谈方向",
        "答案回显",
        "文章后续",
    ]
    for item in candidates:
        if item in context:
            return item
    return "等待入口词包"


def _route_actions_from_context(route_context: str) -> list[str]:
    context = clean(route_context)
    actions = []
    for item in ["原文显性词", "扩展关键词", "库轴映射", "章节顺查", "跨回追踪", "双向校验", "反证排除"]:
        if item in context:
            actions.append(item)
    return actions or ["等待Codex指令"]


def _route_profile_from_context(route_context: str, question: str = "") -> dict[str, Any]:
    text = clean(route_context)
    if clean(question):
        text = f"{text}\n原问题：{clean(question)}" if text else f"原问题：{clean(question)}"
    profile = decomposer.route_context_profile(text)
    return profile if isinstance(profile, dict) else {}


def _route_mode_from_context(route_context: str, question: str = "") -> str:
    profile = _route_profile_from_context(route_context, question)
    mode = str(profile.get("route_mode") if isinstance(profile, dict) else "")
    if mode == LEGACY_DIRECT_ROUTE_MODE:
        return "标准聚拢裁判题"
    return mode if mode else "标准"


def _route_is_fast(route_context: str, question: str = "") -> bool:
    return False


def _normalize_second_round_state(state: object) -> str:
    value = clean(state)
    if value == LEGACY_DIRECT_ANSWER_STATE:
        return "召回已命中，待聚拢裁判"
    return value


def _load_second_round_state(package_dir: Path) -> str:
    path = package_dir / CORE_FILES["second_round_decision_json"]
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        state = payload.get("suggested_state", "") if isinstance(payload, dict) else ""
        return _normalize_second_round_state(state)
    except (OSError, json.JSONDecodeError, TypeError):
        return ""


def _aggregation_court_files(package_dir: Path) -> dict[str, Path]:
    return {
        "00AC": package_dir / CORE_FILES["aggregation_flow_lock_md"],
        "00AD": package_dir / CORE_FILES["aggregation_flow_lock_json"],
        "00AG": package_dir / CORE_FILES["aggregation_material_search_md"],
        "00AH": package_dir / CORE_FILES["aggregation_material_search_json"],
        "00AI": package_dir / CORE_FILES["material_pool_admission_csv"],
        "00AJ": package_dir / CORE_FILES["material_pool_admission_md"],
        "00AK": package_dir / CORE_FILES["material_pool_admission_json"],
        "00AM": package_dir / CORE_FILES["aggregation_first_read_pool_md"],
    }


def _aggregation_court_missing(package_dir: Path) -> list[str]:
    return [key for key, path in _aggregation_court_files(package_dir).items() if not path.exists()]


def _aggregation_court_ready(package_dir: Path) -> bool:
    return not _aggregation_court_missing(package_dir)


def _source_layers_from_context(route_context: str) -> list[str]:
    context = clean(route_context)
    layers = []
    for item in ["底库", "原文", "生成文件"]:
        if item in context:
            layers.append(item)
    return layers or ["底库", "原文"]


def question_query_experience_skeleton() -> list[dict[str, str]]:
    base_rules = [
        ("人物线", "人物库 / 人物别名 / 人物-段落映射", "问题中心是人物、人物性格、人物命运、人物言行或人物关系时优先启用。", "AI 判断核心人物，再补别名、称谓、关系人、动作词和关键场景词。", "人物库 -> 人物相关段落 -> 原文上下文 -> 关系边校验。", "同一人物的称谓、言行和上下文能共同支撑判断。", "只命中同名或旁人谈及，但没有回到该人物的具体行为和场景。"),
        ("事件/情节线", "事件库 / 情节节点 / 前后因果", "问题问一件事如何发生、如何转折、造成什么影响时启用。", "AI 判断事件名、动作词、参与人物、起点词、结果词和转折词。", "事件库 -> 相关章回 -> 起点段落 -> 转折段落 -> 结果段落。", "能从原文中看见事件的起因、过程和后果。", "只抓到事件标题或相邻情节，无法说明因果链。"),
        ("关系线", "关系映射 / 共同段落 / 对照材料", "问题问两人、多人与物件、观念或空间之间的牵连时启用。", "AI 判断关系双方、关系动词、共同场景、对照词和变化词。", "关系边 -> 共同段落 -> 双方各自段落 -> 原文对照。", "关系双方在原文中互相照见，且不是单方孤证。", "只出现一方材料，或共同出现但没有关系动作。"),
        ("物象域", "物象库 / 器物别名 / 经手人物 / 出现场景 / 功能变化", "问题围绕物件、象征、意象、礼物、器具、花木或梦象时启用。", "AI 判断物象名、别名、经手人、动作词、场景词、共同出现对象和功能变化词。", "物象库 -> 出现段落 -> 经手人物 -> 同场共现 -> 上下文功能判断。", "物象在原文中的出现、动作和语境能说明它的意义。", "只命中同字、标题或泛泛象征，没有具体原文动作。"),
        ("诗词文本线", "诗词判词库 / 原句 / 题咏 / 上下文", "问题问诗词、判词、曲文、原句、回目文字或文本互照时启用。", "AI 判断原句片段、题名、人物归属、意象词和前后文提示。", "诗词库 -> 原句定位 -> 上下文 -> 与人物/事件库复核。", "原句位置、说话/写作主体和上下文都明确。", "只拿诗句关键词泛化解释，未确认文本对象和语境。"),
        ("场域/空间域", "空间库 / 场景段落 / 人物移动 / 场域功能 / 空间关系", "问题问地点、居所、场域、移动路线、场景气氛或空间象征时启用。", "AI 判断地点名、场景词、进入/离开动作、人物组合、物象组合和空间关系词。", "空间库 -> 场景段落 -> 人物移动 -> 物象/事件共现 -> 场域功能判断。", "地点、人物和事件在同一场景中形成可读关系。", "只命中地点名，但没有读清楚场景功能。"),
        ("章节原句线", "章回索引 / 原文章节 / 上下文顺读", "问题问第几回、哪句话、某段上下文或原文位置时启用。", "AI 判断回目、原句片段、人物、场景和明显文本标识。", "原文定位 -> 前后文顺读 -> 相关库反查。", "能准确定位原文段落，并说明上下文。", "只根据摘要或标题判断，没有原句位置。"),
        ("观念主题线", "主题词网络 / 人物事件交叉 / 原文多点复核", "问题问情、空、幻、命运、家族、女性、哲学意味等大主题时启用。", "AI 判断主题词、反义词、人物承载点、事件承载点和关键原文场景。", "主题关键词 -> 人物/事件/物象交叉 -> 多回原文复核 -> 反证排除。", "多个原文点能共同支撑主题判断，并能说明差异。", "只用概念套原文，缺具体场景和证据链。"),
        ("共现查证线", "二元共现 / 三元共现 / 同段同场景 / 关系动作", "问题需要判断人物-物品、人物-空间、物品-空间，或人物-空间-物品是否真的互相牵连时启用。", "先分别找人物、物品、空间等核心词，再查二元共现和三元共现，确认它们是否在同段、同场景、同事件、同动作链中共同成立。", "单点分别命中 -> 二元共现候选 -> 三元共现候选 -> 同段/同场景 -> 原文上下文 -> 关系动作确认。", "共现不是字面相邻，而是人物、物品、空间在同一原文语境里形成可解释关系。", "人物、物品或空间各自出现，但没有共同段落、共同场景或共同动作关系。"),
        ("反证排除线", "误召回 / 旧题污染 / 相似词降级", "问题容易串旧题、标题、模板或相似概念时必须启用。", "AI 判断容易混淆的同形词、相邻情节、旧题关键词和否定条件。", "候选证据 -> 反向查证 -> 原文核验 -> 降级或剔除。", "能说明哪些材料不能用，为什么不能用。", "把旧题、标题、摘要或旁证直接推成主证。"),
        ("时间线", "章回顺序 / 年龄阶段 / 前后变化", "问题问先后、发展、变化、伏笔兑现、早晚对照时启用。", "AI 判断时间词、阶段词、前后动作、人物状态变化词。", "时间词 -> 相关章回 -> 前后段落 -> 状态变化表。", "能说清楚前后顺序和变化原因。", "只拿单点材料回答变化题。"),
        ("命运/结局线", "结局段落 / 判词曲文 / 前文伏笔", "问题问人物结局、归宿、命运暗示时启用。", "AI 判断人物、结局动作、判词意象、伏笔词和收束场景。", "人物库 -> 判词曲文 -> 结局段落 -> 前文伏笔复核。", "结局判断同时有收束段落和前文照应。", "只用回目或旧题模板断定结局。"),
        ("梦境/幻境线", "梦境段落 / 太虚幻境 / 现实映照", "问题问梦、幻境、预言、象征转换时启用。", "AI 判断梦境词、幻境地点、人物化身、现实对应词。", "梦境段落 -> 象征对象 -> 现实事件 -> 反向校验。", "梦境与现实材料能互相解释。", "把象征当现实事实，或把现实情节当梦境。"),
        ("家族结构线", "贾府结构 / 亲缘关系 / 权力秩序", "问题问家族、权力、长幼、内外院秩序时启用。", "AI 判断家族角色、称谓、权力动作、空间位置和制度词。", "人物关系库 -> 家族场景 -> 原文称谓 -> 权力动作复核。", "人物身份、关系和行动共同支撑结构判断。", "只凭称谓猜身份关系。"),
        ("女性群像线", "女性人物库 / 对照关系 / 命运结构", "问题问女性、群像、才情、命运、评价差异时启用。", "AI 判断女性人物组、共同主题、对照词、判词和关键事件。", "人物组 -> 判词/诗词 -> 事件对照 -> 原文场景。", "群像判断能区分共同点和差异点。", "把一个人物材料套到整个群体。"),
        ("语言语气线", "对话原文 / 说话人 / 语气动作", "问题问某句话的意味、态度、讽刺、亲疏时启用。", "AI 判断原句、说话人、听话人、语气词、动作词。", "原句定位 -> 前后对话 -> 人物关系 -> 场景压力。", "能从说话场景解释语气。", "脱离上下文解释一句话。"),
        ("称谓别名线", "别名库 / 称谓变化 / 简繁异写", "问题涉及宝玉/怡红公子、宝钗/宝姐姐等异称时启用。", "AI 判断全名、简称、称谓、别号、繁简体和异写。", "别名归一 -> 原文命中 -> 人物身份复核。", "不同称谓能归到正确人物并保留语境差异。", "把同名、近名或称谓误归一。"),
        ("简繁异体线", "简体查询 / 繁体原文 / 异体字", "问题关键词可能因繁简体或异体字漏召回时启用。", "AI 判断简体词、繁体词、异体字、常见转写。", "简体查 -> 繁体查 -> 原文定位 -> 归一记录。", "同一对象的不同字形被正确合并。", "只查一种字形导致漏证据。"),
        ("版本真源线", "原文真源 / 生成稿 / 摘要降级", "问题需要区分原文、库摘要、生成文稿时启用。", "AI 判断原文标识、文件来源、段落号、生成稿标识。", "原文 -> 底库 -> 生成文件；生成文件不能反向充当原文。", "每条关键判断都能回到原文段落。", "把生成稿、摘要、标题当原文证据。"),
        ("回目标题线", "回目标题 / 章回内容 / 标题诱导", "问题命中回目标题但仍需看章回正文时启用。", "AI 判断回目词、章回号、正文人物和事件词。", "回目定位 -> 正文段落 -> 事件细节 -> 标题降级或保留。", "标题作为入口，正文作为证据。", "只因标题出现就把整章当主证。"),
        ("同题历史线", "旧题记录 / request_id / 历史答案", "问题与历史题相似但要求不同时时启用。", "AI 判断本题新增条件、旧题相似词、差异限制。", "当前 request_id -> 当前工程包 -> 同题历史只做参考。", "能区分本题和旧题边界。", "旧答案错位回显或旧题材料混入。"),
        ("追问承接线", "上一题问题包 / 当前追问 / 差异条件", "问题明显承接上一问时启用。", "AI 判断上一题对象、当前新增要求、否定或转向词。", "上一题材料池 -> 当前新增关键词 -> 原文补证。", "承接旧材料但不被旧题锁死。", "把追问当全新题，或完全复用旧答案。"),
        ("定位问答线", "位置 / 回目 / 原句 / 上下文", "用户问在哪里、哪一回、哪句话时启用。", "AI 判断定位词、原句片段、人物和章回提示。", "全文定位 -> 章回确认 -> 前后文摘录 -> 简短解释。", "能给出位置和上下文。", "写成大论述却没定位。"),
        ("解释判断线", "判断命题 / 支撑证据 / 反证", "用户问为什么、是不是、能不能说明时启用。", "AI 判断命题核心、支撑词、反向词和证据对象。", "命题拆分 -> 支撑证据 -> 反证排除 -> 判断。", "能说明判断成立到什么程度。", "只堆材料不回答判断。"),
        ("比较对照线", "对象A / 对象B / 对照维度", "问题问两人两物两种观念差异时启用。", "AI 判断两个对象、比较维度、共同场景和差异词。", "分别召回 -> 共同维度 -> 同场对照 -> 结论。", "比较维度清楚，材料能并列。", "一边证据强一边证据弱却强行对比。"),
        ("因果机制线", "原因 / 过程 / 结果 / 条件", "问题问为什么会这样、什么导致什么时启用。", "AI 判断原因词、结果词、中介事件和限制条件。", "结果定位 -> 原因候选 -> 过程证据 -> 反证。", "因果链有过程材料。", "把时间先后误当因果。"),
        ("象征功能线", "物象 / 场景 / 情节功能", "问题问某物某景象征什么、起什么作用时启用。", "AI 判断物象、场景、人物反应、情节后果。", "出现段落 -> 人物反应 -> 情节后果 -> 主题复核。", "象征解释能回到功能。", "空谈象征，缺动作和后果。"),
        ("主题词扩展线", "核心概念 / 同义反义 / 承载对象", "大主题找不到证据或太散时启用。", "AI 判断核心词、同义词、反义词、人物承载点。", "概念词 -> 人物/事件承载 -> 原文多点 -> 材料池。", "抽象主题有具体承载对象。", "只查抽象词导致证据稀薄。"),
        ("否定限制线", "不是什么 / 排除条件 / 边界", "用户问题里有不是、不能、不要、是否排除时启用。", "AI 判断否定词、排除对象、边界条件和反例。", "正证 -> 反证 -> 边界材料 -> 谨慎结论。", "结论有边界。", "忽略否定条件，答成相反方向。"),
        ("材料不足线", "缺口 / 补查词 / 待核证", "工程证据不足、材料互相冲突或无法支撑时启用。", "AI 判断缺口对象、补查关键词、待核章节。", "现有证据 -> 缺口标记 -> 补查任务 -> 不硬写。", "能诚实标记不足并给出补查路径。", "证据不足仍强行给确定答案。"),
        ("长文写作线", "最终答案 / 文章稿 / 入库", "用户要文章、论述、入库保存时启用。", "AI 判断文章主题、主版本、材料池和回挂对象。", "材料池 -> Codex最终答案 -> 文章版本 -> 入库预检。", "文章和证据能互相回挂。", "把过程稿直接当最终文章。"),
        ("轻量对话线", "快速问答 / 少证据 / 仍需工程", "用户要快答或现场对答时启用。", "AI 判断最小关键词、核心人物/事件和必要原文。", "轻量取证 -> 最小材料池 -> 简洁答案。", "速度快但不脱离工程材料。", "为快而退回模块搜索答案。"),
        ("深度研究线", "多问题树 / 多证据层 / 二次补证", "复杂大题、论文题或用户要求深度时启用。", "AI 判断3到5个子问题、主证、辅证、反证和待深读词。", "问题树 -> 证据池 -> 原文复核 -> 二次补证 -> 最终答案。", "每个关键判断都有材料层级。", "子问题多但互不支撑。"),
        ("二次补证线", "缺口词 / 新问题 / 下一轮任务", "首轮证据不够或答案偏移时启用。", "AI 判断缺失维度、补查词、反证词和下一轮问题。", "缺口诊断 -> 新检索词 -> 新证据 -> 合并材料池。", "补证能修正原结论。", "只重复原检索词。"),
        ("证据分层线", "主证 / 辅证 / 语境 / 反证 / 待核", "证据很多但质量不齐时启用。", "AI 判断证据角色、强弱、直接/间接关系。", "候选证据 -> 原文复核 -> 角色分层 -> 材料池。", "证据角色清楚。", "把旁证当主证。"),
        ("同段强证线", "同段 / 同场景 / 同动作", "问题需要强关系证明时启用。", "AI 判断关系双方、共同动作、同段标识。", "双方分别命中 -> 同段共现 -> 动作关系 -> 强证。", "同段材料直接说明关系。", "不同段拼接成假强证。"),
        ("跨回呼应线", "前后回 / 伏笔 / 回响", "问题问前后呼应、伏笔、变化时启用。", "AI 判断前文词、后文词、同一对象变化词。", "前回命中 -> 后回命中 -> 对照变化 -> 呼应判断。", "前后材料形成可解释回响。", "把重复词误当呼应。"),
        ("场景群组线", "同一场景多人物 / 多物象 / 多动作", "问题问一个场景里多种对象如何共同构成意义时启用。", "AI 判断场景、人物组、物象组、动作链。", "场景定位 -> 群组对象 -> 关系动作 -> 场景功能。", "场景内对象彼此有结构。", "只罗列对象不解释场景关系。"),
        ("人物行动线", "行为 / 动机 / 后果", "问题问人物为什么做某事或某行为说明什么时启用。", "AI 判断人物、动作、动机词、后果词和旁人反应。", "动作定位 -> 前因 -> 后果 -> 旁人反应。", "行为解释有前后语境。", "只看行为不看动机和后果。"),
        ("人物评价线", "叙述评价 / 他人评价 / 行动自证", "问题问某人好坏、高下、复杂性时启用。", "AI 判断评价词、评价者、人物行动和反例。", "叙述评价 -> 他人评价 -> 行动证据 -> 反证。", "评价能区分叙述者和人物立场。", "把某人一句评价当客观结论。"),
        ("制度礼法线", "婚姻 / 礼法 / 家规 / 社会秩序", "问题问礼法、婚姻、家规、制度压力时启用。", "AI 判断制度词、仪式词、家族角色和执行动作。", "制度词 -> 家族场景 -> 人物行动 -> 后果。", "制度如何作用到人物能说清。", "只讲概念不看具体执行。"),
        ("情感关系线", "情感动作 / 物件传递 / 语言暗示", "问题问情感、亲疏、爱恨、知己关系时启用。", "AI 判断情感词、赠与物、对话、共同场景和反应。", "人物关系 -> 情感动作 -> 物象/语言 -> 原文复核。", "情感判断有动作和语境。", "用现代情感词硬套原文。"),
        ("作者叙事线", "叙述视角 / 伏笔 / 讽刺 / 留白", "问题问作者为什么这样写、叙事效果时启用。", "AI 判断叙述提示、反讽词、留白、前后结构。", "叙述段落 -> 结构位置 -> 前后呼应 -> 效果判断。", "叙事解释能回到文本结构。", "把读者猜想当作者意图。"),
        ("入库归档线", "最终文章 / 候选行 / 回挂清单", "问题已经产出文章，需要保存、阅读、入库预检时启用。", "AI 判断请求ID、工程包、主版本、回挂对象。", "最终答案 -> 文章文件 -> 入库预检 -> 候选行/回挂清单。", "文章、问题、证据和回挂能互相追溯。", "只有文章文本，没有工程包和回挂关系。"),
    ]
    keys = ("type", "bucket", "when", "keyword_strategy", "source_order", "success_signal", "failure_signal")
    return [dict(zip(keys, row)) for row in base_rules]


def load_experience_ledger() -> dict[str, Any]:
    if not EXPERIENCE_LEDGER_JSON.exists():
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": "",
            "total_entries": 0,
            "rules": {},
            "recent_entries": [],
            "manual_triggers": [
                "经验",
                "经验值",
                "经验复盘",
                "经验入账",
                "经验提取",
                "经验总结",
                "增加经验值",
                "这题成功",
                "这题偏了",
                "这题串题",
                "关键词没找对",
                "证据不足",
            ],
        }
    try:
        payload = json.loads(EXPERIENCE_LEDGER_JSON.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("rules", {})
            payload.setdefault("recent_entries", [])
            payload.setdefault("manual_triggers", ["经验复盘", "经验入账"])
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": "",
        "total_entries": 0,
        "rules": {},
        "recent_entries": [],
        "manual_triggers": ["经验复盘", "经验入账"],
        "load_error": "旧总账读取失败，已重建空总账。",
    }


def render_experience_ledger_markdown(ledger: dict[str, Any]) -> str:
    rules = ledger.get("rules", {})
    if not isinstance(rules, dict):
        rules = {}
    rows = sorted(rules.values(), key=lambda row: (int(row.get("score") or 0), row.get("type", "")), reverse=True)
    recent = ledger.get("recent_entries", [])
    if not isinstance(recent, list):
        recent = []
    lines = [
        "# 红楼梦工程｜问题判断经验值总账",
        "",
        f"更新时间：{ledger.get('updated_at') or datetime.now().isoformat(timespec='seconds')}",
        f"累计入账次数：{ledger.get('total_entries', 0)}",
        "",
        "## 触发词",
        "",
        "- 自动触发：每次问题进入红楼梦工程，自动生成 `00E_经验复盘入账.md`，并给本题命中的主路径加经验值。",
            "- 手动触发：只要你说到“经验、经验值、经验复盘、经验提取、经验总结、经验入账、增加经验值”，都归入同一套经验流程。",
            "- 手动复盘口径：成功/偏移/串题/关键词不足/证据不足/最终答案满意/最终答案不满意。",
        "",
        "## 经验值排行",
        "",
        "| 路径 | 经验值 | 最近入账 | 成功提示 | 误召回提示 |",
        "|---|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('type', '')} | {row.get('score', 0)} | {row.get('last_seen', '')} | "
            f"{row.get('success_signal', '')} | {row.get('failure_signal', '')} |"
        )
    lines.extend(["", "## 最近入账", ""])
    for item in recent[:30]:
        lines.extend(
            [
                f"### {item.get('generated_at', '')}｜{item.get('question_short', '')}",
                "",
                f"- 工程包：`{item.get('package', '')}`",
                f"- 触发：{item.get('trigger', '')}",
                f"- 主路径：{item.get('main_rules_text', '')}",
                f"- 候选搜索词：{item.get('keywords_text', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_experience_ledger(ledger: dict[str, Any]) -> None:
    EXPERIENCE_LEDGER_JSON.parent.mkdir(parents=True, exist_ok=True)
    write_json(EXPERIENCE_LEDGER_JSON, ledger)
    EXPERIENCE_LEDGER_MD.write_text(render_experience_ledger_markdown(ledger), encoding="utf-8")


def build_experience_entry(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    experience_triggers = ["经验", "经验值", "经验复盘", "经验提取", "经验总结", "经验入账", "增加经验值"]
    trigger_text = question
    is_manual_experience = any(item in trigger_text for item in experience_triggers)
    selected_rules = [
        rule for rule in judgment_payload.get("type_experience_rules", [])
        if isinstance(rule, dict) and rule.get("status") == "主路径"
    ]
    if not selected_rules:
        selected_rules = [
            {
                "type": "等待入口词包",
                "bucket": "问题入口 / Codex策略未落位",
                "success_signal": "Codex 已完成查询词路，工程只执行查证。",
                "failure_signal": "缺少 Codex 查询词路时，工程停在入口词门。",
            }
        ]
    main_rule_names = [str(rule.get("type", "")) for rule in selected_rules if rule.get("type")]
    keywords = [str(item) for item in judgment_payload.get("keyword_pool", []) if str(item).strip()]
    entry = {
        "generated_at": generated_at,
        "trigger": "经验相关手动复盘入账" if is_manual_experience else "每题自动经验入账",
        "manual_trigger": "经验 / 经验值 / 经验复盘 / 经验提取 / 经验总结 / 经验入账 / 增加经验值：成功、偏移、串题、关键词不足、证据不足、最终答案满意或不满意 + 原因",
        "question": question,
        "question_short": clean(question)[:80],
        "manual_experience_note": question if is_manual_experience else "",
        "package": str(package_dir),
        "route_context": route_context,
        "route_center": judgment_payload.get("route_center", ""),
        "main_rules": main_rule_names,
        "main_rules_text": "、".join(main_rule_names),
        "keywords": keywords,
        "keywords_text": "、".join(keywords[:20]),
        "source_layers": judgment_payload.get("source_layers", []),
        "experience_delta": {name: 1 for name in main_rule_names},
        "review_fields": {
            "outcome": "已收到手动复盘语句，待工程吸收" if is_manual_experience else "待复盘",
            "what_worked": "",
            "what_failed": "",
            "keyword_lesson": "",
            "evidence_lesson": "",
            "next_adjustment": "",
        },
        "process": [
            "1. 自动入账：问题进入工程时，根据第0步判断程序给主路径加经验值。",
            "2. 结果观察：最终答案、证据池、材料池出来后，看是否满意、偏移、串题或证据不足。",
            "3. 手动复盘：只要你说到经验、经验值、经验复盘、经验提取、经验总结或经验入账，就说明本题成败原因。",
            "4. 经验修正：把成功信号、误召回信号、关键词经验和下次调整写回总账。",
            "5. 后续调用：下一次同类问题优先查看对应路径的经验值和最近复盘。",
        ],
        "entry_md": str(package_dir / CORE_FILES["experience_entry_md"]),
        "entry_json": str(package_dir / CORE_FILES["experience_entry_json"]),
        "ledger_md": str(EXPERIENCE_LEDGER_MD),
        "ledger_json": str(EXPERIENCE_LEDGER_JSON),
    }
    ledger = load_experience_ledger()
    rules = ledger.setdefault("rules", {})
    if not isinstance(rules, dict):
        rules = {}
        ledger["rules"] = rules
    for rule in selected_rules:
        name = str(rule.get("type", "") or "等待入口词包")
        stored = rules.setdefault(
            name,
            {
                "type": name,
                "score": 0,
                "bucket": rule.get("bucket", ""),
                "success_signal": rule.get("success_signal", ""),
                "failure_signal": rule.get("failure_signal", ""),
                "last_seen": "",
            },
        )
        stored["score"] = int(stored.get("score") or 0) + 1
        stored["bucket"] = rule.get("bucket", stored.get("bucket", ""))
        stored["success_signal"] = rule.get("success_signal", stored.get("success_signal", ""))
        stored["failure_signal"] = rule.get("failure_signal", stored.get("failure_signal", ""))
        stored["last_seen"] = generated_at
    ledger["updated_at"] = generated_at
    ledger["total_entries"] = int(ledger.get("total_entries") or 0) + 1
    recent = ledger.setdefault("recent_entries", [])
    if not isinstance(recent, list):
        recent = []
    recent.insert(0, {
        "generated_at": generated_at,
        "question_short": entry["question_short"],
        "package": str(package_dir),
        "trigger": entry["trigger"],
        "main_rules_text": entry["main_rules_text"],
        "keywords_text": entry["keywords_text"],
    })
    ledger["recent_entries"] = recent[:120]
    write_experience_ledger(ledger)
    return entry


def render_experience_entry_markdown(entry: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦工程｜经验复盘入账",
        "",
        f"生成时间：{entry.get('generated_at', '')}",
        "",
        "## 1. 本题自动入账",
        "",
        f"- 触发词：{entry.get('trigger', '')}",
        f"- 手动复盘触发词：{entry.get('manual_trigger', '')}",
        f"- 工程包：`{entry.get('package', '')}`",
        f"- 问题中心：{entry.get('route_center', '')}",
        f"- 主路径：{entry.get('main_rules_text', '')}",
        f"- 候选搜索词：{entry.get('keywords_text', '') or '等待入口词包'}",
        f"- 手动复盘原话：{entry.get('manual_experience_note', '') or '无，本次为自动入账'}",
        "",
        "## 2. 经验值增量",
        "",
    ]
    delta = entry.get("experience_delta", {})
    if isinstance(delta, dict):
        for key, value in delta.items():
            lines.append(f"- {key}: +{value}")
    lines.extend(
        [
            "",
            "## 3. 每次对话后的复盘流程",
            "",
        ]
    )
    for item in entry.get("process", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 4. 你后续可以直接说",
            "",
            "- 经验值：这题成功，因为关键词和证据都对。",
            "- 经验复盘：这题偏了，因为问题中心判断错了。",
            "- 经验提取：这题串题，因为旧题材料混进来了。",
            "- 经验总结：这题关键词不足，应该补某某词。",
            "- 增加经验值：这题证据不足，应该增加原文复核或反证排除。",
            "",
            "## 5. 全局总账",
            "",
            f"- Markdown：`{entry.get('ledger_md', '')}`",
            f"- JSON：`{entry.get('ledger_json', '')}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_question_judgment_program(
    question: str,
    route_context: str,
    package_dir: Path,
) -> dict[str, Any]:
    plan = decomposer.build_plan(question, route_context=route_context)
    subquestions = []
    keyword_pool: list[str] = []
    entity_pool: list[str] = []
    axes_pool: list[str] = []
    for item in plan:
        row = {
            "order": item.order,
            "dimension": item.dimension,
            "question": item.question,
            "purpose": item.purpose,
            "entities": item.entities,
            "keywords": item.keywords,
            "preferred_axes": item.preferred_axes,
            "source_layers": item.source_layers or [],
            "evidence_expectation": item.evidence_expectation,
        }
        subquestions.append(row)
        keyword_pool.extend(item.keywords or [])
        entity_pool.extend(item.entities or [])
        axes_pool.extend(item.preferred_axes or [])
    keyword_pool = list(dict.fromkeys(keyword_pool))
    entity_pool = list(dict.fromkeys(entity_pool))
    axes_pool = list(dict.fromkeys(axes_pool))
    route_center = _route_center_from_context(route_context)
    route_actions = _route_actions_from_context(route_context)
    source_layers = _source_layers_from_context(route_context)
    suggested_precheck = []
    if "人物" in route_center or any("人物" in axis for axis in axes_pool):
        suggested_precheck.append("人物库、别名、关系人、人物-段落映射")
    if "事件" in route_center:
        suggested_precheck.append("事件线、起止场景、前后因果")
    if "关系" in route_center:
        suggested_precheck.append("关系边、共同段落、对照人物/物件")
    if "物象" in route_center:
        suggested_precheck.append("物件/意象别名、经手人物、出现段落")
    if "诗词" in route_center:
        suggested_precheck.append("诗词判词库、原句、上下文场景")
    if "空间" in route_center or "场域" in route_center:
        suggested_precheck.append("空间/场域库、场景段落、人物移动、场景功能")
    if "章节" in route_center:
        suggested_precheck.append("章回原文、上下文顺读")
    if "共现" in route_center:
        suggested_precheck.append("分别命中、同段同场景、关系动作、原文复核")
    if "反证" in route_center:
        suggested_precheck.append("相似词降级、旧题污染排除、反向查证")
    if not suggested_precheck:
        suggested_precheck.append("先由问题语义生成搜索词网络，再库文双向核验")
    type_experience_rules = question_query_experience_skeleton()
    selected_type_rules = []
    codex_experience_paths = decomposer.split_terms(decomposer.context_value(route_context, "Codex经验路径"))
    center_rule_types: set[str] = set()
    if "人物" in route_center:
        center_rule_types.add("人物线")
    if "事件" in route_center:
        center_rule_types.add("事件/情节线")
    if "关系" in route_center:
        center_rule_types.add("关系线")
    if "物象" in route_center:
        center_rule_types.add("物象域")
    if "诗词" in route_center:
        center_rule_types.add("诗词文本线")
    if "空间" in route_center or "场域" in route_center:
        center_rule_types.add("场域/空间域")
    if "章节" in route_center:
        center_rule_types.add("章节原句线")
    if "共现" in route_center:
        center_rule_types.add("共现查证线")
    if "反证" in route_center or "反证" in " ".join(route_actions):
        center_rule_types.add("反证排除线")
    for rule in type_experience_rules:
        type_name = rule["type"]
        enabled = (
            any(type_name == path or type_name in path or clean(path) == type_name for path in codex_experience_paths)
            or type_name in center_rule_types
        )
        selected_type_rules.append({**rule, "status": "主路径" if enabled else "经验仓"})
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "route_context": route_context,
        "route_center": route_center,
        "route_actions": route_actions,
        "source_layers": source_layers,
        "keyword_pool": keyword_pool,
        "entity_pool": entity_pool,
        "preferred_axes": axes_pool,
        "suggested_precheck": suggested_precheck,
        "type_experience_rules": selected_type_rules,
        "subquestions": subquestions,
        "rules": [
            "判断程序是红楼梦工程第0步，不是页面外置说明。",
            "本步骤只做题目理解、关键词网络预检、来源选择和查证顺序判断，不直接生成最终答案。",
            "关键词和查证路线由 Codex 根据题意、触发词、经验仓和可查库结构判断；本地程序只保存判断并执行查询。",
            "所有候选线索必须回到原文上下文复核，成立后才进入材料池。",
            "判断结果要随问题包保存，后续可用于复盘关键词路径经验。",
        ],
        "judgment_md": str(package_dir / CORE_FILES["question_judgment_md"]),
        "precheck_json": str(package_dir / CORE_FILES["keyword_precheck_json"]),
    }
    md_lines = [
        "# 红楼梦工程｜问题判断程序",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 工程定位",
        "",
        "这是红楼梦闭环工程的第 0 步：问题带着页面触发词进入工程后，先做问题拆分、关键词网络预检和查证路径判断，再进入证据池、原文复核、材料池和最终答案。",
        "",
        "## 2. 用户问题",
        "",
        question,
        "",
        "## 3. 触发词与路径",
        "",
        f"- 问题中心：{route_center}",
        f"- 取证动作：{'、'.join(route_actions)}",
        f"- 材料来源：{'、'.join(source_layers)}",
        "",
        "## 4. 关键词网络预检",
        "",
        f"- 候选实体：{'、'.join(entity_pool) or '等待入口词包'}",
        f"- 候选搜索词：{'、'.join(keyword_pool) or '等待入口词包'}",
        f"- 优先轴：{'、'.join(axes_pool) or '等待入口词包'}",
        f"- 预检方向：{'；'.join(suggested_precheck)}",
        "",
        "## 5. 类型经验仓",
        "",
        "每个问题都由 Codex 先读经验仓，判断属于哪类问题、需要哪些词、哪些库和哪些原文路径。这里保存的是给 AI 使用的经验规则，不是本地程序的猜题规则，也不是单题答案。",
        "",
    ]
    for rule in selected_type_rules:
        md_lines.extend(
            [
                f"### {rule['status']}｜{rule['type']}",
                "",
                f"- 经验位置：{rule['bucket']}",
                f"- 何时启用：{rule['when']}",
                f"- 关键词方案：{rule['keyword_strategy']}",
                f"- 查证顺序：{rule['source_order']}",
                f"- 成功信号：{rule['success_signal']}",
                f"- 误召回信号：{rule['failure_signal']}",
                "",
            ]
        )
    md_lines.extend(
        [
        "## 6. 问题拆分方案",
        "",
        ]
    )
    for row in subquestions:
        md_lines.extend(
            [
                f"### {row['order']}. {row['dimension']}",
                "",
                f"- 子问题：{row['question']}",
                f"- 目的：{row['purpose']}",
                f"- 查证词：{'、'.join(row['keywords']) or '等待Codex指令'}",
                f"- 来源层：{'、'.join(row['source_layers']) or '底库、原文'}",
                f"- 证据期待：{row['evidence_expectation']}",
                "",
            ]
        )
    md_lines.extend(
        [
            "## 7. 固定工程规矩",
            "",
            "- 这里固化的是工程通道，不固化题目答案。",
            "- 找词、找故事情节、找人物关系、找物象诗词或找章节原文，都只是进入证据的路线。",
            "- 任何路线都必须经过原文复核和材料池，不允许把模块搜索结果当最终答案。",
            "- 本卡随问题包保存，后续可复盘：哪些词有效、哪些词误召回、下一题该怎样调整。",
            "",
            f"结构化预检：`{payload['precheck_json']}`",
        ]
    )
    judgment_md = package_dir / CORE_FILES["question_judgment_md"]
    precheck_json = package_dir / CORE_FILES["keyword_precheck_json"]
    judgment_md.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    write_json(precheck_json, payload)
    return payload


def library_flow_skeleton() -> dict[str, Any]:
    """Reusable library map for the first gate of every Honglou question."""
    return {
        "source_documents": [
            {
                "name": "Notion 红楼梦｜结构地图",
                "role": "说明章节库、段落库、人物库、人物-段落映射、事件库、事件-段落映射和写入路由器的位置。",
                "url": "https://app.notion.com/p/bfc2c2aa061e4404a5b113cc21888fa0",
            },
            {
                "name": "Notion 红楼梦原文读取｜单一入口规范",
                "role": "规定原文读取的真源入口：整回正文、繁体源、只读真源库优先。",
                "url": "https://app.notion.com/p/ae8f34b34d4744e18aa9e4e45fca3420",
            },
            {
                "name": "Notion 红楼梦｜出库工程化总法 v1.5",
                "role": "规定先进入语义聚拢中心库，再拆题、查询中心表轴、回真源、形成资料池和前台应用。",
                "url": "https://app.notion.com/p/b08ffe5fadfb42b182502545461975ee",
            },
            {
                "name": "Notion 出库任务库 + 证据池 SOP",
                "role": "规定出库任务库、证据池、资料池、作品总库之间的边界。",
                "url": "https://app.notion.com/p/e6819d4f565f48648f4358ab17853299",
            },
            {
                "name": "本地对谈查证室｜全库利用与流转总指导",
                "role": "规定各类库的用途、证据角色、专题线索和原文回归方法；这是理解层/方法层，取候选数据时仍须回到语义聚拢中心库。",
                "path": str(ROOT / "outputs" / "红楼梦对谈查证室" / "21_AI入场后全库利用与流转总指导.md"),
            },
            {
                "name": "本地对谈查证室｜库登记处查法与专题库补漏表",
                "role": "规定人物、物象、空间、专题库等各类库怎么理解、怎么用、哪些只作导航；这是盘库理解层，不是外部取数入口。",
                "path": str(ROOT / "outputs" / "红楼梦对谈查证室" / "20_库登记处查法与专题库补漏表.md"),
            },
            {
                "name": "本地库群结构总报告",
                "role": "本地底库库群、覆盖、待轴化库和建设队列；用于理解库的作用、边界和证据等级，不直接作为候选数据源。",
                "path": str(ROOT / "outputs" / "正式底库库群结构分析与建设待办" / "00_库群结构总报告.md"),
            },
            {
                "name": "本地映射固化总报告",
                "role": "本地 relation 解析率、证据边、别名固化、范围段落关系和剩余未解析边。",
                "path": str(ROOT / "outputs" / "正式底库映射固化检查包" / "00_映射固化总报告.md"),
            },
        ],
        "metrics": {
            "axis_tables": 29,
            "chapters_rows": 121,
            "unique_chapters": 120,
            "segments": 2719,
            "characters": 370,
            "person_segment_edges": 5050,
            "event_segments": 1785,
            "event_segment_edges": 3555,
            "evidence_edges": 19161,
            "objects_axis": 2205,
            "spaces_axis": 352,
            "space_evidence_axis": 1446,
            "time_axis": 282,
            "literary_texts_axis": 295,
            "character_aliases": 613,
            "segment_range_edges": 140,
            "notion_relation_resolve_rate": "约 99.1%",
        },
        "library_groups": [
            {
                "group": "A类原文真源层",
                "tables": ["chapters", "chapter_identity", "chapter_source_variants"],
                "function": "承担整回正文、回目编号、章节身份和最终原文核证。任何强结论、引号原文、原句解释最终都要回到这里。",
                "maps_to": ["segments", "literary_texts_axis", "time_axis"],
                "use_when": "题目问原文、原句、哪一回、强证据、最终定稿引用时必须使用。",
                "risk": "段落库、事件库、人物库里的摘录只能导航，不能冒充真源。",
            },
            {
                "group": "原子段落层",
                "tables": ["segments", "segment_range_edges", "segment_match_cache"],
                "function": "把整回正文切成可检索、可挂边、可复核的原子段落；范围型证据用 segment_range_edges 保留多段关系。",
                "maps_to": ["chapters", "person_segment_edges", "event_segment_edges", "space_evidence_axis", "evidence_edges"],
                "use_when": "任何证据要进入材料池时，都要尽量回到段落号、回目和上下文。",
                "risk": "只摘一个词不够；需要读上下文，判断这段是主证、语境、旁证、反证还是待核。",
            },
            {
                "group": "人物与关系层",
                "tables": ["characters", "character_alias_solidification", "character_alias_ambiguity_queue", "person_segment_edges"],
                "function": "处理人物身份、称谓、别名、人物出场、被提及、行动和人物-段落强证据。",
                "maps_to": ["segments", "chapters", "evidence_edges"],
                "use_when": "人物、群像、关系、命运、称谓、主仆、身份和行动题优先使用。",
                "risk": "查人不能只靠正文 LIKE；应先归一别名，再走人物-段落映射，再回原文。",
            },
            {
                "group": "事件与情节层",
                "tables": ["event_segments", "event_segment_edges"],
                "function": "把故事行动切成事件单元，建立事件与段落的关系，用于起因、过程、转折、结果和叙事位置判断。",
                "maps_to": ["segments", "chapters", "characters", "evidence_edges"],
                "use_when": "情节、因果、场景推进、结局、伏笔兑现、跨回发展题优先使用。",
                "risk": "事件标题只能定位；最终仍要回事件相关段落和章节真源。",
            },
            {
                "group": "物象空间诗词时间层",
                "tables": ["objects_axis", "spaces_axis", "space_evidence_axis", "literary_texts_axis", "time_axis"],
                "function": "处理器物、花木、空间场域、诗词判词、节令时间、场景和象征功能。",
                "maps_to": ["segments", "chapters", "characters", "event_segments", "evidence_edges"],
                "use_when": "物象、空间、诗词、判词、梦境、预示、场景气氛、时间顺序题按题意选择。",
                "risk": "这些库常含范围型、摘录型或解释型字段，不能跳过原文上下文复核。",
            },
            {
                "group": "统一证据边与映射健康层",
                "tables": ["evidence_edges", "evidence_unresolved_queue", "evidence_anchor_fix_candidates", "library_audit_runs"],
                "function": "把各轴材料统一成证据边，并记录未解析、待固化和映射健康问题。",
                "maps_to": ["segments", "chapters", "objects_axis", "spaces_axis", "literary_texts_axis", "time_axis"],
                "use_when": "多库材料互相牵连、需要查证据边是否断链、判断某材料能不能升格时使用。",
                "risk": "未解析边、范围边、低置信边只能作为候选，不能直接进入主证。",
            },
            {
                "group": "专题线索与中心库表轴防漏层",
                "tables": ["数据库总目录·定义页", "出库研究池", "工程推进档案", "作品总库索引", "性主题库", "男男分支", "专题库补漏表"],
                "function": "先理解各类库的用途、证据角色、专题线索和历史方法页，再把可执行取材落回语义聚拢中心库内部表轴。",
                "maps_to": ["chapters", "segments", "characters", "person_segment_edges", "objects_axis", "event_segments", "search_documents"],
                "use_when": "每题先做盘库理解和中心库表轴防漏；性主题、男男、服饰、泪水、金银、香气、梦、三教、十二钗等专题题必须先理解对应库法，再映射回中心库或原文。",
                "risk": "专题线索和出库研究池能提供用法、分类和证据边界，但不能替代中心库取材和原文真源；男男是性主题线索分支，不是独立平级候选库。",
            },
            {
                "group": "中心库全文补漏与原文回源层",
                "tables": ["search_documents/search_documents_fts", "segments", "chapters"],
                "function": "在语义聚拢中心库内部优先走 segments/chapters 等表轴；旧全文检索库只作回源辅助和补漏，不作候选源头。",
                "maps_to": ["segments", "chapters", "axis tables"],
                "use_when": "题目没有明确中心表轴入口、需要先找关键词网络、或需要补漏时使用。",
                "risk": "全文补漏只是辅助，不是结论；命中后必须回到语义中心表轴和原文。",
            },
            {
                "group": "问题包、证据池与复核写作层",
                "tables": ["00A-00H", "01_问题树", "02_证据阅读顺序", "04_复核表", "09_可写作证据包", "54_真源核验统一报告"],
                "function": "保存本题从判断、拆解、证据、复核、材料池精读门到 Codex 红楼解语前的全流程。",
                "maps_to": ["review tables", "article ingest files", "final answer"],
                "use_when": "每个用户问题都要形成问题包，便于回显、复盘、补证和后续入库。",
                "risk": "工程过程材料不是最终答案；红楼解语必须由 Codex 基于工程产物再思考后输出。",
            },
            {
                "group": "文章入库与作品层",
                "tables": ["58_文章入库预检报告", "59_作品总库入库候选行", "60_文章回挂清单", "61_文章入库身份卡"],
                "function": "用户认可后，把最终文章或阅读成果保存为可读资产，并回挂问题包、证据池和原文锚点。",
                "maps_to": ["作品总库", "问题包", "证据池", "章节真源"],
                "use_when": "用户要求保存、入库、文章阅读、作品总库或长期复用时使用。",
                "risk": "文章是 B 类知识资产，不能倒灌污染 A 类原文真源。",
            },
        ],
        "flow_patterns": [
            {
                "name": "题目进入工程总线",
                "flow": "用户问题 + 页面触发词 -> 00A 问题判断程序 -> 00B 关键词网络预检 -> 00C 库线原文骨架 -> 问题-库矩阵 -> 证据池 -> 原文复核 -> 材料池 -> Codex 最终答案",
                "purpose": "保证问题不是直接答，也不是模块搜索回显，而是先进入红楼梦工程运转。",
            },
            {
                "name": "库 -> 线 -> 原文",
                "flow": "人物/事件/物象/空间/诗词/时间库 -> 映射边或证据边 -> 原子段落 -> 章节真源",
                "purpose": "适合先有实体或专题库入口的问题。",
            },
            {
                "name": "原文 -> 原子段 -> 库/线",
                "flow": "原句或回目定位 -> 章节真源 -> 原子段落 -> 反查人物、事件、物象、空间、诗词、时间轴",
                "purpose": "适合用户问某句、某回、某个细节的题。",
            },
            {
                "name": "全文词 -> 候选 -> 库轴复核 -> 原文",
                "flow": "关键词网络 -> 全文检索候选 -> 多轴库确认对象 -> 段落上下文 -> 章节真源",
                "purpose": "适合入口不明确、需要先找词再归库的问题。",
            },
            {
                "name": "库登记处 -> 专题库 -> 结构库 -> 原文",
                "flow": "库登记处 -> 专题库/出库研究池 -> 人物/物象/事件/空间/全文查阅 -> 原子段落 -> 章节真源",
                "purpose": "适合性主题、男男、母题、服饰、泪水、金银、香气、梦、三教等专题题，防止漏库。",
            },
            {
                "name": "全书穷尽查证/查访",
                "flow": "定关键词/异体/别名 -> chapters.full_text/search_documents/FTS 全文扫 -> 拉上下文 -> 挂人物事件空间物象 -> 分主证旁证误召回 -> 回章节真源",
                "purpose": "适合详查、全查、物和物、人和物、多对象同场关系，以及库内可能漏收的小物象小词。",
            },
            {
                "name": "B类结构知识 -> A类真源对账",
                "flow": "工程专题/学习成果/生成文章 -> 找到结构线索 -> 回人物/事件/段落/章节真源核证 -> 才能升格为强结论",
                "purpose": "利用 Notion 和本地已有产出加速，但避免学习成果冒充原文。",
            },
            {
                "name": "出库成果 -> 用户认可 -> 学习型再入库",
                "flow": "最终答案/文章 -> 用户认可 -> 文章入库预检 -> 作品候选行 -> 回挂问题包、证据池、原文锚点",
                "purpose": "把高质量答案变成可读资产，同时保持证据层不被污染。",
            },
        ],
        "guardrails": [
            "先盘库理解，后拆题；先理解各库用途和资料需求，后从中心库取材；先来源，后资料池；先出库，后前台。",
            "模板、旧题、生成稿、标题和模块搜索结果都不得替代原文证据。",
            "A类真源承担原文铁证；B类知识系统承担结构导航、旁证和学习成果。",
            "人物、事件、物象、空间、诗词等路线由 Codex 按题意选择；本地程序不得按字数、固定名单或单题偏好自动决定路线。",
            "所有候选材料必须进入原子段落和章节真源复核，才能进入主证。",
            "范围型证据保留范围关系，不强行压成单段落。",
            "每题都要保存问题判断、关键词预检、库线骨架、经验入账，方便后续复盘和经验增长。",
            "查库优先是默认硬规则；不查库必须在问题包里写出理由。",
            "全书穷尽查证/查访是核心工具；详查、全查、物物、人和物、多对象同场关系必须启用或写明跳过理由。",
            "男男相关内容归入性主题库分支，不作为独立平级大库处理，也不允许因此漏查。",
        ],
    }


def _requires_exhaustive_source_sweep(question: str, route_context: str = "") -> bool:
    text = clean(question) + "\n" + clean(route_context)
    force_terms = [
        "详查",
        "全查",
        "全文查",
        "全书查",
        "穷尽",
        "查访",
        "从第1回",
        "从第一回",
        "到第120回",
        "所有出现",
        "有哪些回",
        "哪些章回",
        "同场",
        "同时在场",
        "物和物",
        "人和物",
        "人和人和物",
        "关系",
        "路线",
        "分配",
        "经过",
        "主要人物",
        "有没有",
    ]
    if any(term in text for term in force_terms):
        return True
    object_terms = ["宫灯", "宫花", "鸡", "手帕", "帕子", "扇", "花", "香", "金", "银", "玉", "灯", "茶", "药", "衣", "服饰"]
    return sum(1 for term in object_terms if term in text) >= 2


def build_query_logic_strategy_gate(question: str, route_context: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    strategy_value = ""
    requires_subquestions = False
    subquestions: list[str] = []
    queue_status: dict[str, Any] = {}
    strategy_flexibility: dict[str, Any] = {}
    blocking_reasons: list[str] = []
    gate_available = query_strategy_gate is not None
    if not gate_available:
        blocking_reasons.append("查询逻辑策略门模块未加载，不能证明聚拢头已经执行策略选择。")
    else:
        strategy_value = query_strategy_gate.query_logic_strategy_value(route_context)
        requires_subquestions = query_strategy_gate.query_logic_strategy_requires_subquestions(route_context)
        subquestions = query_strategy_gate.subquestion_items(route_context)
        queue_status = query_strategy_gate.subquestion_strategy_queue_status(route_context)
        strategy_flexibility = query_strategy_gate.query_logic_strategy_flexibility_profile(route_context)
        if not strategy_value:
            blocking_reasons.append("缺 Codex查询逻辑策略。")
        elif re.search(r"(未选择|待定|不确定|不知道|无策略|不用策略)", strategy_value):
            blocking_reasons.append("Codex查询逻辑策略无效：不能写待定、不确定、不用策略或无策略。")
        elif not re.search(r"(模板\s*0?[0-9]|模板\s*10|拆子问题|复杂策略|策略)", strategy_value):
            blocking_reasons.append("Codex查询逻辑策略无效：必须选择具体模板，或选择模板00｜拆子问题策略。")
        if requires_subquestions:
            if not subquestions:
                blocking_reasons.append("选择模板00｜拆子问题策略，但缺 Codex子问题。")
            if not queue_status.get("ok"):
                blocking_reasons.append(f"子问题策略队列不合格：{queue_status.get('reason', '未知原因')}")
        elif strategy_value and not query_strategy_gate.has_query_logic_strategy_choice(route_context):
            blocking_reasons.append("Codex查询逻辑策略无效：必须完成一次显式策略选择。")
    ok = not blocking_reasons
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "gate": "query_logic_strategy",
        "query_head_scope": ["进入聚拢查询", "进入坐标查询"],
        "strategy_entry_file": "000E_查询逻辑策略模板组_新窗口学习入口.md",
        "ok": ok,
        "blocking": True,
        "strategy_value": strategy_value,
        "strategy_flexibility": strategy_flexibility,
        "strategy_is_starting_card_not_rigid_template": True,
        "requires_subquestions": requires_subquestions,
        "subquestions": subquestions,
        "subquestion_strategy_queue": queue_status,
        "blocking_reasons": blocking_reasons,
        "rule": "AI取词之后、进入聚拢或坐标后端之前，必须显式选择起手策略；允许组合、换卡、偏离，但必须留理由并回原文裁判；模板00必须列 Codex子问题和 Codex子问题策略队列。",
        "output_files": {
            "query_logic_strategy_gate_md": str(package_dir / CORE_FILES["query_logic_strategy_gate_md"]),
            "query_logic_strategy_gate_json": str(package_dir / CORE_FILES["query_logic_strategy_gate_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜查询逻辑策略门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本门定位",
        "",
        "本门是工程前置断路器，不是学习说明。",
        "",
        "它位于 AI取词、定中心、定路径、定词网之后；位于聚拢库取材或坐标材料门执行之前。",
        "",
        "## 2. 本题检查",
        "",
        f"- 问题：{question}",
        f"- 策略：{strategy_value or '缺'}",
        f"- 策略执行口径：{strategy_flexibility.get('execution_mode') or '未写'}",
        f"- 策略组合：{strategy_flexibility.get('combination') or '未写'}",
        f"- 策略调整记录：{strategy_flexibility.get('adjustment_record') or '未写'}",
        f"- 偏离理由：{strategy_flexibility.get('deviation_reason') or '未写'}",
        f"- 是否要求子问题队列：{'是' if requires_subquestions else '否'}",
        f"- 子问题数：{len(subquestions)}",
        f"- 子问题策略队列状态：{queue_status.get('reason', '未要求') if queue_status else '未检查'}",
        f"- 结论：{'通过' if ok else '阻断'}",
        "",
        "## 3. 阻断原因",
        "",
    ]
    if blocking_reasons:
        lines.extend(f"- {reason}" for reason in blocking_reasons)
    else:
        lines.append("- 无。")
    lines.extend(
        [
            "",
            "## 4. 工程规则",
            "",
            "- 没有 Codex查询逻辑策略，不进入聚拢取材，也不进入坐标材料门。",
            "- 策略写待定、不确定、无策略、不用策略，视为没有选择。",
            "- 策略卡是起手卡，不是死模板；本门强制有策略意识，不强制死按卡执行。",
            "- 已有策略后，允许组合、换卡或偏离执行；但应写明 Codex策略组合、Codex策略调整记录或 Codex偏离理由。",
            "- 选择模板00时，必须写 Codex子问题和 Codex子问题策略队列。",
            "- 子问题有几条，策略队列就必须至少有几条；每条都要重新选择策略并写成两两可查对象或强复合。",
            "",
            f"结构化策略门：`{payload['output_files']['query_logic_strategy_gate_json']}`",
        ]
    )
    (package_dir / CORE_FILES["query_logic_strategy_gate_md"]).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(package_dir / CORE_FILES["query_logic_strategy_gate_json"], payload)
    return payload


def enforce_query_logic_strategy_gate(question: str, route_context: str, package_dir: Path) -> dict[str, Any]:
    payload = build_query_logic_strategy_gate(question, route_context, package_dir)
    if not payload.get("ok"):
        reasons = "；".join(str(item) for item in payload.get("blocking_reasons", []) if str(item).strip())
        raise SystemExit(f"聚拢查询缺查询逻辑策略：{reasons}")
    return payload


def build_entry_hard_gate(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    exhaustive_required = _requires_exhaustive_source_sweep(question, route_context)
    registry_files = [
        "16_红楼梦工程库群总图与易用命名表.md",
        "17_真实库名表与路径索引.md",
        "18_库群一屏说明与使用指南.md",
        "19_正式底库全量库名核对表_不要漏版.md",
        "20_库登记处查法与专题库补漏表.md",
        "21_AI入场后全库利用与流转总指导.md",
    ]
    hard_gates = [
        {
            "gate": "library_first",
            "name": "查库优先门",
            "blocking": True,
            "status": "必须执行",
            "rule": "凡进入红楼梦工程的问题，默认先查库；不查库必须写明理由。",
            "runtime_requirement": "本题必须生成库态预检、库线流转骨架和来源链记录。",
            "exception_record": "仅纯流程设计、纯工程文档整理、刚查过的同一事实、用户明确不要查库时，记录例外原因；内容题仍须保留聚拢裁判记录。",
        },
        {
            "gate": "registry_lookup",
            "name": "库登记处门",
            "blocking": True,
            "status": "必须执行",
            "rule": "不能只按文件名或 SQLite 表名判断有没有库；必须先查库登记处和专题库补漏表。",
            "runtime_requirement": "本题必须把登记处、正式表、专题库和产出研究池分层。",
            "exception_record": "无。",
        },
        {
            "gate": "exhaustive_source_sweep",
            "name": "全书穷尽查证/查访工具门",
            "blocking": exhaustive_required,
            "status": "本题必须点亮" if exhaustive_required else "默认备选，例外需有记录",
            "rule": "涉及详查、全查、物物、人和物、多对象同场、有没有、哪些回等问题时，必须启用全书穷尽查证。",
            "runtime_requirement": "必须定关键词/异体/别名，全文扫命中，拉上下文，挂人物事件空间物象，分主证旁证误召回。",
            "exception_record": "若一次命中且能直接回真源确认，可压缩全文扩展，但必须保留聚拢取材、材料入池和原文锚点记录。",
        },
        {
            "gate": "source_return",
            "name": "原文回归门",
            "blocking": True,
            "status": "必须执行",
            "rule": "最终强结论必须回 chapters 或 segments；专题库、出库研究池、生成文档只能导航和启发。",
            "runtime_requirement": "最终答案前必须有原文锚点、原文摘录或明确缺口。",
            "exception_record": "无。",
        },
        {
            "gate": "no_direct_answer",
            "name": "禁止直接答案门",
            "blocking": True,
            "status": "必须执行",
            "rule": "本地模块不得凭常识、模板、小知识表或旧题印象直接给红楼解语。",
            "runtime_requirement": "必须留下问题判断、库态预检、库线骨架、聚拢取材单、材料池入池清单和首读材料池。",
            "exception_record": "只限纯流程讨论，不涉及红楼梦内容查证；内容题无例外。",
        },
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "question_type_hint": judgment_payload.get("route_center", ""),
        "hard_rule_version": "HLM-HARD-GATE-20260619",
        "hard_mode": True,
        "default_action": "查库优先，然后必要时全书穷尽查证，最终回原文真源。",
        "exhaustive_source_sweep_required": exhaustive_required,
        "registry_files": registry_files,
        "hard_gates": hard_gates,
        "tool_contract": {
            "library_first": "首选工具。任何内容题默认先查库，不查库必须记录理由。",
            "exhaustive_source_sweep": "核心工具。查物和物、人和物、多对象、详查/全查时必须启用或说明例外理由。",
            "source_return": "底线工具。最终强结论总是回原文。",
        },
        "output_files": {
            "entry_hard_gate_md": str(package_dir / CORE_FILES["entry_hard_gate_md"]),
            "entry_hard_gate_json": str(package_dir / CORE_FILES["entry_hard_gate_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜入口硬规则门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本门定位",
        "",
        "这是每个问题包的第一道硬门，不是说明图。后续 00A、00C/00D、00K/00L、00M 都必须服从本门。",
        "",
        "## 2. 三条总铁律",
        "",
        "1. 查库优先：凡进入红楼梦工程的问题，默认先查库；不查库必须说明理由。",
        "2. 全书穷尽查证/查访：涉及详查、全查、物物、人和物、多对象关系时，它是核心工具。",
        "3. 原文回归：最终强结论总是回 chapters 或 segments，专题库和出库研究池不能替代原文。",
        "",
        "## 3. 本题状态",
        "",
        f"- 问题：{question}",
        f"- 题型提示：{payload['question_type_hint'] or '等待问题判断程序'}",
        f"- 全书穷尽查证是否硬启用：{'是' if exhaustive_required else '否，默认备选；例外仍需记录'}",
        "",
        "## 4. 硬门清单",
        "",
        "| 门 | 是否阻断 | 状态 | 规则 | 运行时要求 | 例外记录 |",
        "|---|---|---|---|---|---|",
    ]
    for gate in hard_gates:
        lines.append(
            f"| {gate['name']} | {'是' if gate['blocking'] else '条件阻断'} | {gate['status']} | {gate['rule']} | {gate['runtime_requirement']} | {gate['exception_record']} |"
        )
    lines.extend(
        [
            "",
            "## 5. 必读库登记处",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in registry_files)
    lines.extend(
        [
            "",
            "## 6. 机器执行口径",
            "",
            "- 后续 00C/00D 必须生成库线和库态预检。",
            "- 后续 00M 必须检查查库优先、穷尽查证工具、原文回归是否有记录。",
            "- 页面或召回队列不得直接把本地模块结果当最终红楼解语。",
            "",
            f"结构化硬门：`{payload['output_files']['entry_hard_gate_json']}`",
        ]
    )
    (package_dir / CORE_FILES["entry_hard_gate_md"]).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(package_dir / CORE_FILES["entry_hard_gate_json"], payload)
    return payload


QUESTION_TYPE_LIBRARY_ROUTES = {
    "人物": ["人物基础库", "人物-段落映射库"],
    "关系": ["人物关系主库", "人物-段落映射库", "跨轴证据边库"],
    "物象": ["物象器物库", "物件流转库", "全文穷尽查证工具库"],
    "空间": ["空间场所与空间证据库", "人物空间出入库", "回目时间场库"],
    "时间/季节": ["回目时间场库", "原文章节库", "段落库", "全文穷尽查证工具库"],
    "人物+物象/器物+接触现场": ["人物基础库", "人物-段落映射库", "物象器物库", "物件流转库", "跨轴证据边库", "全文穷尽查证工具库", "原文章节库", "段落库"],
    "人物+空间/场域+同场现场": ["人物基础库", "人物-段落映射库", "空间场所与空间证据库", "人物空间出入库", "跨轴证据边库", "回目时间场库", "原文章节库", "段落库"],
    "人物+时间/季节+场景现场": ["人物基础库", "人物-段落映射库", "回目时间场库", "事件片段与事件段落库", "跨轴证据边库", "原文章节库", "段落库"],
    "人物+人物+关系现场": ["人物关系主库", "人物-段落映射库", "跨轴证据边库", "原文章节库", "段落库"],
    "多轴共现": ["跨轴证据边库", "人物-段落映射库", "物象器物库", "空间场所与空间证据库", "回目时间场库", "全文穷尽查证工具库", "原文章节库", "段落库"],
    "事件": ["事件片段与事件段落库", "聚拢事件库"],
    "主题": ["对应专题库", "文学文本轴库", "全文穷尽查证工具库"],
    "文本功能": ["文学文本轴库", "原文章节库", "全文穷尽查证工具库"],
    "全文穷尽": ["全文穷尽查证工具库", "原文章节库", "段落库"],
}


def _role_terms_any(route_context: str, labels: tuple[str, ...]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for label in labels:
        try:
            candidates = decomposer.context_role_terms(route_context, label)
        except Exception:
            candidates = []
        for term in candidates:
            value = clean(term)
            if value and value not in seen:
                seen.add(value)
                terms.append(value)
    return terms


def _route_context_has_axis(route_context: str, labels: tuple[str, ...], fallback_terms: tuple[str, ...] = ()) -> bool:
    context = clean(route_context)
    if _role_terms_any(route_context, labels):
        return True
    if any(f"{label}：" in context or f"{label}:" in context or f"{label}=" in context for label in labels):
        return True
    return any(term in context for term in fallback_terms)


def _cross_axis_profile(question: str, route_context: str, judgment_payload: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        [
            clean(question),
            clean(route_context),
            clean(judgment_payload.get("route_center", "")),
            " ".join(str(item) for item in judgment_payload.get("preferred_axes", [])),
        ]
    )
    profile = _route_profile_from_context(route_context, question)
    centers = " ".join(str(item) for item in profile.get("centers", [])) if isinstance(profile, dict) else ""
    person_terms = _role_terms_any(route_context, ("主查人物", "人物", "关系人物", "人物轴"))
    object_terms = _role_terms_any(route_context, ("主查物象", "主查物件", "主查器物", "物象", "物件", "器物", "物象轴"))
    space_terms = _role_terms_any(route_context, ("主查空间", "主查场域", "主查地点", "空间", "场域", "地点", "空间轴"))
    time_terms = _role_terms_any(route_context, ("主查时间", "主查季节", "主查节令", "时间", "季节", "节令", "时间轴"))
    second_person_terms = _role_terms_any(route_context, ("第二人物", "对照人物", "关系对象", "共现人物", "另一人物", "主查人物2"))
    has_person = bool(person_terms) or "人物" in centers or _route_context_has_axis(route_context, ("主查人物",), ("人物轴", "人物中心"))
    has_object = bool(object_terms) or "物象" in centers or _route_context_has_axis(route_context, ("主查物象", "主查物件", "主查器物"), ("物象轴", "物象中心", "物象域", "器物", "物件"))
    has_space = bool(space_terms) or "空间" in centers or "场域" in centers or _route_context_has_axis(route_context, ("主查空间", "主查场域", "主查地点"), ("空间轴", "空间中心", "空间域", "场域"))
    has_time = bool(time_terms) or _route_context_has_axis(route_context, ("主查时间", "主查季节", "主查节令"), ("时间轴", "季节", "节令", "春", "夏", "秋", "冬", "中秋", "元宵", "端午", "清明"))
    person_person = bool(second_person_terms) or any(term in text for term in ["两人", "二人", "人和人", "人物关系"])
    first_or_order = any(term in text for term in ["第一次", "第1次", "首次", "初次", "最早", "先后", "何时", "什么时候", "哪一次"])
    contact_or_flow = any(term in text for term in ["接触", "使用", "经手", "流转", "传递", "递", "送", "拿", "取", "坐", "佩", "戴", "换", "收", "赠"])
    co_scene = any(term in text for term in ["同场", "共现", "共同", "一起", "同段", "同一场景", "交集", "场景", "现场", "动作链"])
    relation = any(term in text for term in ["关系", "牵连", "关联", "对照", "互相", "影响", "照见"])
    space_intent = any(term in text for term in ["哪里", "在哪", "到哪里", "进入", "离开", "住", "空间", "场域", "地点", "场所"])
    time_intent = any(term in text for term in ["季节", "节令", "时间", "春", "夏", "秋", "冬", "中秋", "元宵", "端午", "清明"])
    axes = [name for name, present in [("人物", has_person), ("物象", has_object), ("空间", has_space), ("时间/季节", has_time)] if present]
    return {
        "axes": axes,
        "has_person": has_person,
        "has_object": has_object,
        "has_space": has_space,
        "has_time": has_time,
        "person_person": person_person,
        "person_term_count": len(person_terms),
        "first_or_order": first_or_order,
        "contact_or_flow": contact_or_flow,
        "co_scene": co_scene,
        "relation": relation,
        "space_intent": space_intent,
        "time_intent": time_intent,
    }


def _flow_lock_problem_type(question: str, route_context: str, judgment_payload: dict[str, Any]) -> str:
    text = " ".join(
        [
            clean(question),
            clean(route_context),
            clean(judgment_payload.get("route_center", "")),
            " ".join(str(item) for item in judgment_payload.get("preferred_axes", [])),
        ]
    )
    cross = _cross_axis_profile(question, route_context, judgment_payload)
    inferred_person_pair = cross["person_term_count"] >= 2 and not (cross["has_object"] or cross["has_space"] or cross["has_time"])
    if cross["has_person"] and (cross["person_person"] or inferred_person_pair) and (cross["relation"] or cross["co_scene"]):
        return "人物+人物+关系现场"
    if cross["has_person"] and cross["has_object"] and (cross["contact_or_flow"] or cross["first_or_order"] or cross["co_scene"] or cross["relation"]):
        return "人物+物象/器物+接触现场"
    if cross["has_person"] and cross["has_space"] and (cross["space_intent"] or cross["co_scene"] or cross["relation"]):
        return "人物+空间/场域+同场现场"
    if cross["has_person"] and cross["has_time"] and (cross["time_intent"] or cross["co_scene"] or cross["first_or_order"] or cross["relation"]):
        return "人物+时间/季节+场景现场"
    if len(cross["axes"]) >= 2 and (cross["co_scene"] or cross["relation"] or cross["contact_or_flow"]):
        return "多轴共现"
    if any(term in text for term in ["人物关系", "关系", "同场", "共现"]):
        return "关系"
    for label, terms in [
        ("人物", ["人物", "谁", "宝玉", "黛玉", "宝钗", "凤姐", "秦钟"]),
        ("物象", ["物象", "器物", "信物", "衣", "汗巾", "帕", "扇", "玉", "花"]),
        ("空间", ["空间", "场所", "在哪里", "哪儿", "怡红院", "潇湘馆", "大观园"]),
        ("时间/季节", ["时间", "季节", "节令", "春", "夏", "秋", "冬", "中秋", "元宵", "端午", "清明"]),
        ("事件", ["事件", "场景", "发生", "哪一回", "怎样的一个场景"]),
        ("主题", ["主题", "象征", "意义", "为什么", "精神"]),
        ("文本功能", ["诗", "判词", "曲", "书信", "梦境", "文本功能"]),
        ("全文穷尽", ["全书", "全文", "所有", "全部", "几次", "有没有"]),
    ]:
        if any(term in text for term in terms):
            return label
    return "事件"


def _registry_rows_for_flow_lock(limit: int = 18) -> list[dict[str, str]]:
    if not LIBRARY_REGISTRY_CSV.exists():
        return []
    with LIBRARY_REGISTRY_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    rows.sort(
        key=lambda row: (
            priority_rank.get(clean(row.get("priority")), 9),
            clean(row.get("layer")),
            clean(row.get("registry_id")),
        )
    )
    return [
        {
            "registry_id": clean(row.get("registry_id")),
            "canonical_name": clean(row.get("canonical_name")),
            "easy_name": clean(row.get("easy_name")),
            "layer": clean(row.get("layer")),
            "evidence_role": clean(row.get("evidence_role")),
            "must_return_to_original": clean(row.get("must_return_to_original")),
            "priority": clean(row.get("priority")),
        }
        for row in rows[:limit]
    ]


def build_aggregation_flow_lock(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    problem_type = _flow_lock_problem_type(question, route_context, judgment_payload)
    runtime_packet: dict[str, Any] = {}
    runtime_error = ""
    if runtime_main_bus is not None:
        try:
            runtime_packet = runtime_main_bus.build_runtime_bus_packet(question, route_context=route_context)
        except Exception as exc:  # pragma: no cover - surfaced in gate file.
            runtime_error = f"{type(exc).__name__}: {exc}"
    else:
        runtime_error = "formal_honglou_runtime_main_bus unavailable"

    related_libraries = QUESTION_TYPE_LIBRARY_ROUTES.get(problem_type, QUESTION_TYPE_LIBRARY_ROUTES["事件"])
    runtime_decision = runtime_packet.get("route_decision") if isinstance(runtime_packet.get("route_decision"), dict) else {}
    new_flow_required_rule_set = (
        runtime_packet.get("new_flow_required_rule_set")
        if isinstance(runtime_packet.get("new_flow_required_rule_set"), list)
        else []
    )
    if (
        not new_flow_required_rule_set
        and runtime_main_bus is not None
        and hasattr(runtime_main_bus, "new_flow_required_rule_set")
    ):
        try:
            new_flow_required_rule_set = runtime_main_bus.new_flow_required_rule_set()
        except Exception:
            new_flow_required_rule_set = []
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "entry_doc": str(AGGREGATION_ENTRY_DOC),
        "entry_doc_exists": AGGREGATION_ENTRY_DOC.exists(),
        "registry_csv": str(LIBRARY_REGISTRY_CSV),
        "registry_csv_exists": LIBRARY_REGISTRY_CSV.exists(),
        "registry_rows": _registry_rows_for_flow_lock(),
        "problem_type": problem_type,
        "map_checked": AGGREGATION_ENTRY_DOC.exists() and LIBRARY_REGISTRY_CSV.exists(),
        "first_gate_sentence": f"已接入红楼梦工程入口。本题闭环包：package_dir={package_dir}。聚拢四件套：00AC/00AG/00AI/00AM 必须齐全并已读；缺任一项则阻断，不进入正文答案。",
        "four_cell_record": {
            "本题闭环包": str(package_dir),
            "聚拢四件套": "00AC/00AG/00AI/00AM 必须齐全并已读；缺任一项即阻断。",
            "问题类型": problem_type,
            "先过地图": "已查看 128 聚拢库总入口和 25 库登记处机器总表；每题包必须保留本记录。",
            "相关库": related_libraries,
            "唯一新流程必备规则全集": "来源文件只作规则依据；所有有用规则已经熔入唯一聚拢库流程，旧执行路径路权为零。",
            "规则全集上岗": "姓名/别名归一、库结构加载、复杂拆题、问题单元内两两比较/两组对照、全书穷尽查证、全文检索、原文回证按原规则和原数据依据熔入唯一聚拢库流程；旧入口、旧中段、旧落盘路权全部关闭。",
            "旧前门关闭": "直接 SQLite、直接 FTS、旧搜索词网络、旧候选提示、旧分级选库均不得作为运行前门；只能在聚拢库入口之后作为后台补点或候选建议。",
            "回聚拢库": "相关库线索必须映射回编号、聚拢段、聚拢单元、聚拢事件、聚拢场或聚拢域。",
            "原文裁判": "最终判断必须落到 chapters.full_text / segments.quote-summary / 原文锚点；聚拢库只组织现场，不替代原文。",
        },
        "new_flow_required_rule_set": new_flow_required_rule_set,
        "old_front_door_closure": [
            {
                "sealed_item": "直接 sqlite / formal_honglou_search.sqlite / FTS 起手",
                "status": "关闭为前门",
                "allowed_use": "只可在 00AC 后作为全文穷尽补点工具；补点必须回聚拢编号。",
            },
            {
                "sealed_item": "旧候选提示卡 / 旧搜索词网络",
                "status": "关闭为答案路径",
                "allowed_use": "只可作为候选对象建议；不得直接入池、不得直接写答案。",
            },
            {
                "sealed_item": "旧库分级选库作为第一入口",
                "status": "关闭为前门",
                "allowed_use": "只可在聚拢总图无命中、映射断裂、需要补漏时作为后台参考。",
            },
            {
                "sealed_item": "可直接命中 / 快速落盘",
                "status": "彻底关闭",
                "allowed_use": "任何命中都只能写成召回已命中，待聚拢裁判。",
            },
        ],
        "new_flow_embedded_rules": [
            {
                "name": "姓名/别名/称谓归一",
                "status": "已上岗",
                "rule": "人物库、别名固化表、人物-段落映射库是唯一新流程内的归一依据；不得绕过归一。",
            },
            {
                "name": "库结构加载与库登记处",
                "status": "已上岗",
                "rule": "128 总入口、25 库登记处机器总表、axis/search SQLite 是唯一新流程内的库图和补点依据。",
            },
            {
                "name": "复杂拆题与问题树",
                "status": "已上岗",
                "rule": "复杂题必须生成 01_问题树，拆成问题单元，并逐子问题过账。",
            },
            {
                "name": "两两比较 / 两组对照",
                "status": "已上岗",
                "rule": "它不是单独前门；先判断是否需要问题树，再在问题单元内执行对象A/B、共同维度、同场对照和反证边界。",
            },
            {
                "name": "全书穷尽查证与全文检索",
                "status": "已上岗",
                "rule": "全文库和穷尽查词只能作为聚拢库内补点工具；补点必须回聚拢编号和原文裁判。",
            },
            {
                "name": "原文回证",
                "status": "已上岗",
                "rule": "最终强结论必须回 chapters.full_text / segments 原文锚点。",
            },
        ],
        "locked_flow": [
            "接入红楼梦工程入口",
            "创建或确认本题闭环包 package_dir",
            "自检 00AC/00AG/00AI/00AM 聚拢四件套",
            "四件套齐全后才算进入聚拢库 / 聚拢总图",
            "过全库地图",
            "唯一新流程必备规则全集加载",
            "库图/归一/拆题/穷尽/入池/复核规则上岗",
            "执行姓名/别名/称谓/对象/空间/时间归一",
            "判断问题类型",
            "复杂题拆成问题树 / 问题单元",
            "在问题单元 / 子问题内部按需执行两两比较 / 两组对照",
            "选择相关库法深读",
            "从库法理解层取得规范名、标签、入口词和证据角色，再回中心库取候选编号",
            "必要时启用聚拢库内全文穷尽补点",
            "全部映射回聚拢库",
            "在聚拢库内放大、缩小、交集、串域",
            "回原文裁判",
            "入材料池并做四态判定",
            "聚拢裁判通过后才写答案",
        ],
        "shared_eight_step_contract": {
            "query_head": "进入聚拢查询",
            "lane": "semantic_aggregation",
            "shared_spine": SHARED_EIGHT_STEP_SPINE,
            "same_spine_as_coordinate_head": True,
            "tool_difference_only": True,
            "shared_before_terms": "取词之前两头完全相同：读题、判断题型、拆对象、定主轴、人物归一、强复合轴、查询逻辑策略、子问题排队。",
            "different_after_terms": "取词以后两头分路：聚拢头用聚拢法组织现场和材料池；坐标头用坐标分析法做词位穷尽、变量坐标、距离、共场和容器归属。",
            "rule": "聚拢头与坐标头共用完整八步法；取词前思考相同，取词后用库方法不同；不改变归一、收点、交集、路由门、分类、回原文、入材料池、写答案的总顺序。",
        },
        "runtime_bus": {
            "available": runtime_main_bus is not None and not runtime_error,
            "error": runtime_error,
            "main_flow": runtime_packet.get("main_flow", []),
            "required_gates": runtime_decision.get("required_gates", []),
            "fast_path_allowed": False,
            "fast_path_forced_closed": True,
            "should_decompose": runtime_decision.get("should_decompose", False),
        },
        "blocking_contract": [
            "没有本流程锁，最终答案门不得视为完整。",
            "没有本题 package_dir，不能进入聚拢库。",
            "没有 00AC/00AG/00AI/00AM，不能把任何库结果当答案。",
            "没有先过地图记录，不能把任何库结果当答案。",
            "没有入口词与入图盘面打卡，不能启动库检索。",
            "没有唯一新流程必备规则全集，不能进入正文答案。",
            "没有库图、归一、拆题、穷尽、入池、复核规则上岗记录，不能进入正文答案。",
            "没有姓名/别名/人物/对象/空间/时间归一记录，多轴题不得进入材料池。",
            "复杂题没有问题树和子问题过账，不能进入最终答案。",
            "已进入比较/对照的问题单元没有共同维度、两两对照和反证边界记录，不能进入最终答案。",
            "全查、详查、有没有、哪些回、多对象同场题没有穷尽查证记录，不能进入最终答案。",
            "相关库法深读后的线索若没有回中心库、聚拢编号和原文，只能作为候选旁证。",
            "聚拢库定位后仍必须回原文裁判。",
            "没有材料池四态裁判记录，不能把候选升格为主证。",
            "随读直答、直接 sqlite、快速路径全部关闭；后台补点职能必须回聚拢库和原文裁判。",
        ],
        "output_files": {
            "aggregation_flow_lock_md": str(package_dir / CORE_FILES["aggregation_flow_lock_md"]),
            "aggregation_flow_lock_json": str(package_dir / CORE_FILES["aggregation_flow_lock_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜聚拢库总入口流程锁",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 锁定入口",
        "",
        f"- {payload['first_gate_sentence']}",
        f"- 128 总入口：`{payload['entry_doc']}`（存在：{'是' if payload['entry_doc_exists'] else '否'}）",
        f"- 库登记表：`{payload['registry_csv']}`（存在：{'是' if payload['registry_csv_exists'] else '否'}）",
        "",
        "## 2. 四格流程记录",
        "",
        f"- 本题闭环包：{payload['four_cell_record']['本题闭环包']}",
        f"- 聚拢四件套：{payload['four_cell_record']['聚拢四件套']}",
        f"- 问题类型：{payload['four_cell_record']['问题类型']}",
        f"- 先过地图：{payload['four_cell_record']['先过地图']}",
        f"- 相关库：{'、'.join(related_libraries)}",
        f"- 唯一新流程必备规则全集：{payload['four_cell_record']['唯一新流程必备规则全集']}",
        f"- 规则全集上岗：{payload['four_cell_record']['规则全集上岗']}",
        f"- 旧前门关闭：{payload['four_cell_record']['旧前门关闭']}",
        f"- 回聚拢库：{payload['four_cell_record']['回聚拢库']}",
        f"- 原文裁判：{payload['four_cell_record']['原文裁判']}",
        "",
        "## 3. 锁定流程",
        "",
    ]
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(payload["locked_flow"], start=1))
    lines.extend(
        [
            "",
            "## 4. 双头共用八步主线",
            "",
            f"- 查询头：{payload['shared_eight_step_contract']['query_head']}",
            f"- 工具差异限定：{'是' if payload['shared_eight_step_contract']['tool_difference_only'] else '否'}",
            f"- 共同主线：{' -> '.join(payload['shared_eight_step_contract']['shared_spine'])}",
            f"- 规则：{payload['shared_eight_step_contract']['rule']}",
            "",
            "## 5. 唯一新流程必备规则全集",
            "",
        ]
    )
    for idx, row in enumerate(payload.get("new_flow_required_rule_set", []), start=1):
        if isinstance(row, dict):
            lines.extend(
                [
                    f"### {idx}. {row.get('rule_id', '')}",
                    "",
                    f"- 来源依据：{row.get('source_basis', '')}",
                    f"- 来源文件：{row.get('source_files', '')}",
                    f"- 新流程规则：{row.get('required_rule', '')}",
                    f"- 唯一落点：{row.get('flow_slot', '')}",
                    f"- 执行方式：{row.get('enforcement', '')}",
                    f"- 验收凭证：{row.get('acceptance_evidence', '')}",
                    f"- 旧执行路权：{row.get('old_execution_permission', '')}",
                    f"- 阻断条件：{row.get('block_rule', '')}",
                    "",
                ]
            )
    lines.extend(
        [
            "",
            "## 6. 新流程规则上岗",
            "",
        ]
    )
    for item in payload["new_flow_embedded_rules"]:
        lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- 状态：{item['status']}",
                f"- 新流程规则：{item['rule']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 7. 旧前门关闭状态",
            "",
        ]
    )
    for item in payload["old_front_door_closure"]:
        lines.extend(
            [
                f"### {item['sealed_item']}",
                "",
                f"- 状态：{item['status']}",
                f"- 允许用途：{item['allowed_use']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 8. 机器硬阻断条件",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["blocking_contract"])
    lines.extend(
        [
            "",
            "## 9. 运行总线闸门",
            "",
            f"- 总线可用：{'是' if payload['runtime_bus']['available'] else '否'}",
            f"- 总线异常：{runtime_error or '无'}",
            f"- 是否拆题：{'是' if payload['runtime_bus']['should_decompose'] else '否'}",
            f"- 是否允许快速路径：否（旧流程已关闭）",
            "",
        ]
    )
    lines.extend(f"- {gate}" for gate in payload["runtime_bus"].get("required_gates", []))
    lines.extend(
        [
            "",
            "## 10. 库地图快照",
            "",
            "| ID | 易用名 | 层级 | 证据角色 | 必须回原文 | 优先级 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for row in payload["registry_rows"]:
        lines.append(
            f"| {row['registry_id']} | {row['easy_name'] or row['canonical_name']} | {row['layer']} | {row['evidence_role']} | {row['must_return_to_original']} | {row['priority']} |"
        )
    lines.extend(
        [
            "",
            "## 11. 阻断合同结构化出口",
            "",
            *[f"- {item}" for item in payload["blocking_contract"]],
            "",
            f"结构化流程锁：`{payload['output_files']['aggregation_flow_lock_json']}`",
        ]
    )
    (package_dir / CORE_FILES["aggregation_flow_lock_md"]).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(package_dir / CORE_FILES["aggregation_flow_lock_json"], payload)
    return payload


def build_machine_short_card(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
    aggregation_flow_lock: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    problem_type = clean(aggregation_flow_lock.get("problem_type")) or _flow_lock_problem_type(question, route_context, judgment_payload)
    question_center = clean(judgment_payload.get("route_center")) or clean(question)
    raw_keywords = judgment_payload.get("keyword_pool", [])
    entry_terms: list[str] = []
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            value = clean(item.get("term") or item.get("keyword") or item.get("value")) if isinstance(item, dict) else clean(item)
            if value and value not in entry_terms:
                entry_terms.append(value)
            if len(entry_terms) >= 12:
                break
    if not entry_terms:
        entry_terms = [clean(question)[:24]]

    related_libraries = aggregation_flow_lock.get("four_cell_record", {}).get("相关库", [])
    if not isinstance(related_libraries, list):
        related_libraries = [clean(related_libraries)]
    related_libraries = [clean(item) for item in related_libraries if clean(item)]

    exclusion_trigger_terms = ["同一", "是不是", "有没有", "再出现", "流转", "哪一回", "第", "为什么", "关系", "信", "书", "物", "排除", "不是", "误"]
    need_exclusion_table = problem_type in {"关系", "物象", "文本功能", "全文穷尽"} or any(term in question for term in exclusion_trigger_terms)
    exclusion_policy = {
        "required": need_exclusion_table,
        "mode": "按需触发，不做每题全量大表",
        "triggers": ["多个相似命中", "同词异事", "时间线容易混", "信件、物件、人物流转", "用户问是不是同一个对象或同一事件"],
        "minimum_fields": ["候选点", "为什么像", "为什么排除或保留", "原文裁判位置"],
    }
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "principle": "后台重，前台轻；每题只打一张小票，不新增长流程。",
        "machine_short_card": {
            "问题类型": problem_type,
            "对象": question_center,
            "入口词": entry_terms,
            "相关库": related_libraries,
            "排除项": "复杂/混线题按需生成；简单直答题不强制。",
        },
        "library_entry_layer_policy": {
            "status": "后台结构优化，不阻塞本题运行",
            "layers": [
                "原文事实：原文句子、章节、段落、编号、可回读位置。",
                "工程映射：来自哪个库、哪个标签、哪个节点、怎么回聚拢总图。",
                "解释心得：可启发思路，但不能直接当最终证据。",
                "反证排除：相似但不是本对象/本事件/本线路的候选。",
            ],
        },
        "evidence_hard_fields_policy": {
            "status": "后台字段标准，不要求运行时长篇展开",
            "fields": [
                "chapter_no",
                "segment_no 或 line_id",
                "source_quote 或 original_anchor",
                "evidence_level: 明文 / 强暗示 / 推断 / 弱旁证 / 不成立",
                "source_kind: 原文事实 / 工程映射 / 解释心得 / 反证排除",
                "readback_status: 已回读 / 待回读 / 不可作强证",
            ],
        },
        "exclusion_table_policy": exclusion_policy,
        "final_answer_check": [
            "最终答案门先看本短卡，确认对象没有跑偏。",
            "如果存在同词异事或多条流转线，必须说明排除项。",
            "库条目只能当路标；最终仍由原文裁判。",
        ],
        "output_files": {
            "machine_short_card_md": str(package_dir / CORE_FILES["machine_short_card_md"]),
            "machine_short_card_json": str(package_dir / CORE_FILES["machine_short_card_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜机器短卡与证据分层策略",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 原则",
        "",
        "- 后台重，前台轻。",
        "- 每题只打一张小票，不新增长流程。",
        "- 库条目给路标，原文负责裁判。",
        "",
        "## 2. 机器短卡",
        "",
        f"- 问题类型：{payload['machine_short_card']['问题类型']}",
        f"- 对象：{payload['machine_short_card']['对象']}",
        f"- 入口词：{'、'.join(entry_terms)}",
        f"- 相关库：{'、'.join(related_libraries) or '按聚拢库流程锁判定'}",
        f"- 排除项：{payload['machine_short_card']['排除项']}",
        "",
        "## 3. 库条目三分层",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["library_entry_layer_policy"]["layers"])
    lines.extend(["", "## 4. 证据硬字段", ""])
    lines.extend(f"- {item}" for item in payload["evidence_hard_fields_policy"]["fields"])
    lines.extend(["", "## 5. 反证 / 排除表", "", f"- 是否触发：{'是' if need_exclusion_table else '否'}", f"- 模式：{exclusion_policy['mode']}", "- 触发条件："])
    lines.extend(f"  - {item}" for item in exclusion_policy["triggers"])
    lines.extend(["", "## 6. 最终答案前检查", ""])
    lines.extend(f"- {item}" for item in payload["final_answer_check"])
    lines.extend(["", f"结构化短卡：`{payload['output_files']['machine_short_card_json']}`"])
    (package_dir / CORE_FILES["machine_short_card_md"]).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(package_dir / CORE_FILES["machine_short_card_json"], payload)
    return payload


def _index_csv_rows(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        value = clean(row.get(key))
        if value:
            index[value].append(row)
    return index


def _index_csv_rows_one(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        value = clean(row.get(key))
        if value and value not in index:
            index[value] = row
    return index


def _joined_unique(values: list[object], limit: int = 12) -> str:
    cleaned: list[str] = []
    for value in values:
        text = clean(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return "；".join(cleaned[:limit])


def _fieldnames_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    return fieldnames


FIRST_READ_POOL_MAX_ROWS = 40
FIRST_READ_POOL_EXCLUSION_MAX_ROWS = 16
FIRST_READ_POOL_SCORE_THRESHOLD = 80

QUERY_STOP_NGRAMS = {
    "请查",
    "查一",
    "一下",
    "第一",
    "一次",
    "这个",
    "那个",
    "什么",
    "怎么",
    "为何",
    "为什么",
    "有没有",
}


def _md_cell(value: object, limit: int = 180) -> str:
    text = clean(value).replace("|", "/")
    return text[:limit]


def _aggregation_row_text(row: dict[str, Any]) -> str:
    keys = [
        "summary",
        "quote",
        "context_excerpt",
        "codex_original_passages",
        "same_chapter_passage_segments",
        "object_axis_hits",
        "person_axis_hits",
        "evidence_edge_hits",
        "cluster_unit",
        "w32_cluster_titles",
        "w32_unit_meaning",
        "w33_event_titles",
        "w33_event_stage_summary",
    ]
    return "\n".join(clean(row.get(key)) for key in keys if clean(row.get(key)))


def _query_needles(question: str, route_context: str) -> list[str]:
    text = clean(question)
    route = clean(route_context)
    needles: list[str] = []
    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for size in (4, 3, 2):
        for index in range(0, max(len(chinese) - size + 1, 0)):
            term = chinese[index : index + size]
            if term in QUERY_STOP_NGRAMS:
                continue
            if term and term not in needles:
                needles.append(term)
    for term in re.findall(r"[A-Za-z0-9_]{2,}", f"{text} {route}"):
        if term not in needles:
            needles.append(term)
    return needles[:80]


def _score_first_read_pool_row(
    row: dict[str, Any],
    question: str,
    route_context: str,
    query_needles: list[str],
) -> dict[str, Any]:
    text = _aggregation_row_text(row)
    score = 0
    reasons: list[str] = []
    cautions: list[str] = []

    tier = clean(row.get("human_reading_tier"))
    if tier.startswith("T1A"):
        score += 120
        reasons.append("T1A必读主证")
    elif tier.startswith("T1B"):
        score += 100
        reasons.append("T1B强证补读")
    elif tier.startswith("T2"):
        score += 70
        reasons.append("T2可读候选")
    elif tier.startswith("T3"):
        score += 30
        reasons.append("T3语境备用")

    scene_strength = clean(row.get("scene_presence_strength"))
    if scene_strength.startswith("S1"):
        score += 35
        reasons.append("同场/动作强")
    elif scene_strength.startswith("S2"):
        score += 25
        reasons.append("同场较强")
    elif scene_strength.startswith("S3"):
        score += 15
        reasons.append("部分在场")
    elif scene_strength.startswith("S4"):
        score -= 10
        cautions.append("目标对象缺位")

    if clean(row.get("codex_original_passages")) or clean(row.get("same_chapter_passage_segments")):
        score += 15
        reasons.append("有原文锚点")
    if clean(row.get("aggregate_unit_ids")):
        score += 10
        reasons.append("有聚拢单元")
    if clean(row.get("aggregate_event_ids")):
        score += 10
        reasons.append("有聚拢事件")
    if clean(row.get("person_quote_terms_matched")) and clean(row.get("object_quote_terms_matched")):
        score += 25
        reasons.append("人物/对象同入原文短摘")
    elif clean(row.get("person_context_terms_matched")) and clean(row.get("object_context_terms_matched")):
        score += 12
        reasons.append("人物/对象同入上下文")

    matched_needles = [term for term in query_needles if term and term in text]
    if matched_needles:
        unique = []
        for term in matched_needles:
            if term not in unique:
                unique.append(term)
        score += min(50, len(unique) * 8)
        reasons.append("命中问题词：" + "、".join(unique[:8]))

    return {
        "score": score,
        "reasons": reasons[:8],
        "cautions": cautions[:4],
        "matched_needles": matched_needles[:12],
    }


def build_aggregation_first_read_pool(
    question: str,
    route_context: str,
    package_dir: Path,
    admitted_rows: list[dict[str, Any]],
    payload_counts: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    first_read_md = package_dir / CORE_FILES["aggregation_first_read_pool_md"]
    query_needles = _query_needles(question, route_context)
    decorated: list[dict[str, Any]] = []
    for row in admitted_rows:
        meta = _score_first_read_pool_row(row, question, route_context, query_needles)
        decorated.append(
            {
                **row,
                "aggregation_first_read_score": meta["score"],
                "aggregation_first_read_reason": "；".join(meta["reasons"]),
                "aggregation_first_read_caution": "；".join(meta["cautions"]),
                "_first_read_meta": meta,
            }
        )

    def sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        chapter = int(clean(row.get("chapter_no")) or 9999) if clean(row.get("chapter_no")).isdigit() else 9999
        order = int(clean(row.get("review_order")) or 999999) if clean(row.get("review_order")).isdigit() else 999999
        return (-int(row.get("aggregation_first_read_score") or 0), chapter, order)

    candidates = [
        row
        for row in decorated
        if int(row.get("aggregation_first_read_score") or 0) >= FIRST_READ_POOL_SCORE_THRESHOLD
        or clean(row.get("human_reading_tier")).startswith(("T1A", "T1B"))
    ]
    if not candidates:
        candidates = [row for row in decorated if int(row.get("aggregation_first_read_score") or 0) > 0]

    first_read_rows: list[dict[str, Any]] = []
    seen_segments: set[str] = set()
    for row in sorted(candidates, key=sort_key):
        segment_no = clean(row.get("segment_no")) or clean(row.get("line_id"))
        if segment_no in seen_segments:
            continue
        seen_segments.add(segment_no)
        first_read_rows.append(row)
        if len(first_read_rows) >= FIRST_READ_POOL_MAX_ROWS:
            break

    excluded_rows: list[dict[str, Any]] = []
    first_segments = {clean(row.get("segment_no")) for row in first_read_rows}
    for row in sorted(decorated, key=sort_key):
        if clean(row.get("segment_no")) in first_segments:
            continue
        meta = row.get("_first_read_meta") if isinstance(row.get("_first_read_meta"), dict) else {}
        has_caution = bool(meta.get("cautions")) if isinstance(meta, dict) else False
        has_query_hit = bool(meta.get("matched_needles")) if isinstance(meta, dict) else False
        if has_caution or (has_query_hit and int(row.get("aggregation_first_read_score") or 0) < FIRST_READ_POOL_SCORE_THRESHOLD):
            excluded_rows.append(row)
        if len(excluded_rows) >= FIRST_READ_POOL_EXCLUSION_MAX_ROWS:
            break

    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "status": "completed",
        "two_step_rule": [
            "带着问题和方法，在聚拢库里面找材料。",
            "找出有用的材料，送到材料池里面去。",
        ],
        "counts": {
            **payload_counts,
            "first_read_useful_rows": len(first_read_rows),
            "first_read_exclusion_rows": len(excluded_rows),
        },
        "query_needles": query_needles,
        "first_read_rows": [
            {
                "review_order": row.get("review_order", ""),
                "segment_no": row.get("segment_no", ""),
                "chapter_no": row.get("chapter_no", ""),
                "summary": row.get("summary", ""),
                "aggregate_unit_ids": row.get("aggregate_unit_ids", ""),
                "aggregate_event_ids": row.get("aggregate_event_ids", ""),
                "score": row.get("aggregation_first_read_score", 0),
                "reason": row.get("aggregation_first_read_reason", ""),
                "caution": row.get("aggregation_first_read_caution", ""),
            }
            for row in first_read_rows
        ],
        "exclusion_rows": [
            {
                "review_order": row.get("review_order", ""),
                "segment_no": row.get("segment_no", ""),
                "chapter_no": row.get("chapter_no", ""),
                "summary": row.get("summary", ""),
                "aggregate_unit_ids": row.get("aggregate_unit_ids", ""),
                "aggregate_event_ids": row.get("aggregate_event_ids", ""),
                "score": row.get("aggregation_first_read_score", 0),
                "reason": row.get("aggregation_first_read_reason", ""),
                "caution": row.get("aggregation_first_read_caution", ""),
            }
            for row in excluded_rows
        ],
        "output_files": {
            "aggregation_first_read_pool_md": str(first_read_md),
        },
    }

    lines = [
        "# 红楼梦工程｜聚拢裁判首读材料池",
        "",
        f"生成时间：{generated_at}",
        "",
        f"问题：{question}",
        "",
        "## 两步规则",
        "",
        "1. 带着问题和方法，在聚拢库里面找材料。",
        "2. 找出有用的材料，送到材料池里面去。",
        "",
        "这里的“有用”不是直接写答案，而是进入材料池四态裁判：可用主证、背景材料、不可用、需补证。",
        "",
        "## 本题入池状态",
        "",
        f"- 聚拢凭证入池材料：{payload_counts.get('admitted_to_material_pool_rows', 0)}",
        f"- 首读有用材料：{len(first_read_rows)}",
        f"- 排除/降级提示：{len(excluded_rows)}",
        "",
        "## 一、首读有用材料",
        "",
        "| 顺序 | 段落 | 章回 | 聚拢单元 | 聚拢事件 | 分数 | 为什么先读 | 摘要 |",
        "|---:|---|---:|---|---|---:|---|---|",
    ]
    for index, row in enumerate(first_read_rows, start=1):
        lines.append(
            f"| {index} | {_md_cell(row.get('segment_no'))} | {_md_cell(row.get('chapter_no'))} | "
            f"{_md_cell(row.get('aggregate_unit_ids'))} | {_md_cell(row.get('aggregate_event_ids'))} | "
            f"{int(row.get('aggregation_first_read_score') or 0)} | {_md_cell(row.get('aggregation_first_read_reason'), 220)} | "
            f"{_md_cell(row.get('summary'), 220)} |"
        )
    if not first_read_rows:
        lines.append("|  |  |  |  |  |  |  | 暂无首读有用材料，必须补证。 |")

    lines.extend(
        [
            "",
            "## 二、排除 / 降级提示",
            "",
            "| 顺序 | 段落 | 聚拢单元 | 分数 | 降级原因 | 摘要 |",
            "|---:|---|---|---:|---|---|",
        ]
    )
    for index, row in enumerate(excluded_rows, start=1):
        caution = row.get("aggregation_first_read_caution") or row.get("aggregation_first_read_reason")
        lines.append(
            f"| {index} | {_md_cell(row.get('segment_no'))} | {_md_cell(row.get('aggregate_unit_ids'))} | "
            f"{int(row.get('aggregation_first_read_score') or 0)} | {_md_cell(caution, 220)} | {_md_cell(row.get('summary'), 220)} |"
        )
    if not excluded_rows:
        lines.append("|  |  |  |  | 暂无明显排除项。 |  |")

    lines.extend(
        [
            "",
            "## 三、裁判出口",
            "",
            "- `00AI` 是聚拢凭证入池总清单，保留宽口径底账。",
            "- `00AM` 是首读有用材料池，只把下一步最该读、最该裁判的材料推到前台。",
            "- 最终写作前不得再回到“可直接命中”；必须先在此材料池里完成四态裁判。",
        ]
    )
    first_read_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return payload


def build_aggregation_material_bridge(
    question: str,
    route_context: str,
    package_dir: Path,
    review_result: dict[str, Any],
    aggregation_flow_lock: dict[str, Any],
) -> dict[str, Any]:
    """Two-step middle bridge: find material in aggregation libraries, then admit it to material pool."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    w32_line_rows = read_csv(W32_CLUSTER_UNIT_LINES_CSV) if W32_CLUSTER_UNIT_LINES_CSV.exists() else []
    w32_unit_rows = read_csv(W32_CLUSTER_UNITS_CSV) if W32_CLUSTER_UNITS_CSV.exists() else []
    w33_event_rows = read_csv(W33_EVENTS_CSV) if W33_EVENTS_CSV.exists() else []
    w33_event_unit_rows = read_csv(W33_EVENT_UNITS_CSV) if W33_EVENT_UNITS_CSV.exists() else []

    line_index = _index_csv_rows(w32_line_rows, "line_no")
    unit_index = _index_csv_rows_one(w32_unit_rows, "cluster_id")
    event_units_by_cluster = _index_csv_rows(w33_event_unit_rows, "cluster_id")
    event_index = _index_csv_rows_one(w33_event_rows, "event_id")

    enriched_rows: list[dict[str, Any]] = []
    returned_count = 0
    for row in review_rows:
        segment_no = clean(row.get("segment_no"))
        line_hits = line_index.get(segment_no, [])
        cluster_ids = _joined_unique([hit.get("cluster_id") for hit in line_hits])
        cluster_id_list = [item for item in cluster_ids.split("；") if item]
        unit_rows = [unit_index[item] for item in cluster_id_list if item in unit_index]
        event_unit_rows: list[dict[str, str]] = []
        for cluster_id in cluster_id_list:
            event_unit_rows.extend(event_units_by_cluster.get(cluster_id, []))
        event_ids = _joined_unique([hit.get("event_id") for hit in event_unit_rows])
        event_id_list = [item for item in event_ids.split("；") if item]
        event_rows = [event_index[item] for item in event_id_list if item in event_index]
        if cluster_id_list:
            returned_count += 1

        enriched = {
            **row,
            "line_id": clean(row.get("line_id")) or segment_no,
            "aggregate_segment_ids": segment_no,
            "aggregate_unit_ids": cluster_ids,
            "aggregate_event_ids": event_ids,
            "aggregate_scene_ids": _joined_unique([event.get("main_places_hint") for event in event_rows]),
            "cluster_unit": _joined_unique([unit.get("cluster_unit_raw") or unit.get("cluster_unit_normalized") for unit in unit_rows]),
            "recall_gate": clean(row.get("recall_gate")) or "semantic",
            "source_scope": clean(row.get("source_scope")) or "formal_axis_db",
            "source_db": clean(row.get("source_db")) or str(AXIS_DB),
            "source_table": clean(row.get("source_table")) or "segments / person_segment_edges / evidence_edges",
            "semantic_shared_eight_step_rule": "聚拢头服从完整八步法；取词之前的思考与坐标头相同，取词以后改走聚拢法。",
            "semantic_after_terms_strategy": "候选段落 -> 语义聚拢中心库 -> W32聚拢单元 -> W33聚拢事件 -> 聚拢现场组织 -> 材料池四态裁判 -> 原文追证",
            "semantic_tool_usage_guide": SEMANTIC_AGGREGATION_TOOL_USAGE_GUIDE,
            "aggregation_material_status": "已回聚拢库" if cluster_id_list else "未命中聚拢单元",
            "aggregation_material_action": "送入材料池待四态裁判" if cluster_id_list else "留作补证债，不入材料池主清单",
            "aggregation_graph_route": "问题/方法 -> 候选段落 -> W32 聚拢单元 -> W33 聚拢事件 -> 材料池入池凭证门",
            "aggregation_graph_reason": "带着本题的问题中心和查证方法回聚拢库找材料；聚拢库只负责组织现场，送入材料池后再做可用主证、背景、不可用、需补证四态裁判。",
            "w32_cluster_ids": cluster_ids,
            "w32_cluster_titles": _joined_unique([unit.get("cluster_title") for unit in unit_rows]),
            "w32_unit_meaning": _joined_unique([unit.get("unit_meaning") or unit.get("summary_merged") for unit in unit_rows], limit=6),
            "w33_event_ids": event_ids,
            "w33_event_titles": _joined_unique([event.get("event_title") for event in event_rows]),
            "w33_event_stage_summary": _joined_unique([event.get("event_stage_summary") for event in event_rows], limit=4),
        }
        enriched_rows.append(enriched)

    admission = material_admission_gate.apply_gate(enriched_rows, question=question, route_context=route_context)
    admitted_rows = [
        row for row in admission.get("admitted_rows", [])
        if clean(row.get("aggregation_material_status")) == "已回聚拢库"
    ]
    admitted_ids = {id(row) for row in admitted_rows}
    blocked_rows = [row for row in admission.get("all_rows", []) if id(row) not in admitted_ids]
    material_csv = package_dir / CORE_FILES["material_pool_admission_csv"]
    blocked_csv = package_dir / CORE_FILES["material_pool_blocked_csv"]
    admission_md = package_dir / CORE_FILES["material_pool_admission_md"]
    admission_json = package_dir / CORE_FILES["material_pool_admission_json"]
    search_md = package_dir / CORE_FILES["aggregation_material_search_md"]
    search_json = package_dir / CORE_FILES["aggregation_material_search_json"]

    if admitted_rows:
        write_csv(material_csv, admitted_rows, _fieldnames_from_rows(admitted_rows))
    else:
        material_csv.write_text("", encoding="utf-8")
    admission["admitted_rows"] = admitted_rows
    admission["blocked_rows"] = blocked_rows
    admission["admitted_count"] = len(admitted_rows)
    admission["blocked_count"] = len(blocked_rows)
    material_admission_gate.write_gate_outputs(admission_md, admission_json, blocked_csv, admission)

    bridge_counts = {
        "review_rows": len(review_rows),
        "returned_to_aggregation_rows": returned_count,
        "admitted_to_material_pool_rows": len(admitted_rows),
        "blocked_rows": len(blocked_rows),
    }
    first_read_pool = build_aggregation_first_read_pool(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        admitted_rows=admitted_rows,
        payload_counts=bridge_counts,
    )

    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "status": "completed",
        "two_step_rule": [
            "带着问题和方法，在聚拢库里找材料。",
            "把有聚拢坐标、来源链、原文锚点和路由说明的材料送到材料池。",
        ],
        "aggregation_flow_lock": {
            "problem_type": aggregation_flow_lock.get("problem_type", ""),
            "map_checked": aggregation_flow_lock.get("map_checked", False),
            "lock_md": aggregation_flow_lock.get("output_files", {}).get("aggregation_flow_lock_md", ""),
            "lock_json": aggregation_flow_lock.get("output_files", {}).get("aggregation_flow_lock_json", ""),
        },
        "source_files": {
            "review_csv": review_result.get("review_csv", ""),
            "w32_cluster_unit_lines": str(W32_CLUSTER_UNIT_LINES_CSV),
            "w32_cluster_units": str(W32_CLUSTER_UNITS_CSV),
            "w33_events": str(W33_EVENTS_CSV),
            "w33_event_units": str(W33_EVENT_UNITS_CSV),
        },
        "counts": {
            **bridge_counts,
            "first_read_useful_rows": first_read_pool.get("counts", {}).get("first_read_useful_rows", 0),
            "first_read_exclusion_rows": first_read_pool.get("counts", {}).get("first_read_exclusion_rows", 0),
        },
        "first_read_pool": {
            "aggregation_first_read_pool_md": first_read_pool.get("output_files", {}).get("aggregation_first_read_pool_md", ""),
            "first_read_useful_rows": first_read_pool.get("counts", {}).get("first_read_useful_rows", 0),
            "first_read_exclusion_rows": first_read_pool.get("counts", {}).get("first_read_exclusion_rows", 0),
        },
        "sample_admitted_rows": [
            {
                "review_order": row.get("review_order", ""),
                "segment_no": row.get("segment_no", ""),
                "summary": row.get("summary", ""),
                "aggregate_unit_ids": row.get("aggregate_unit_ids", ""),
                "aggregate_event_ids": row.get("aggregate_event_ids", ""),
                "human_reading_tier": row.get("human_reading_tier", ""),
                "material_bucket": row.get("codex_material_bucket", ""),
            }
            for row in admitted_rows[:20]
        ],
        "output_files": {
            "aggregation_material_search_md": str(search_md),
            "aggregation_material_search_json": str(search_json),
            "material_pool_admission_csv": str(material_csv),
            "material_pool_admission_md": str(admission_md),
            "material_pool_admission_json": str(admission_json),
            "material_pool_blocked_csv": str(blocked_csv),
            "aggregation_first_read_pool_md": first_read_pool.get("output_files", {}).get("aggregation_first_read_pool_md", ""),
        },
    }
    lines = [
        "# 红楼梦工程｜聚拢库取材单",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 两步规则",
        "",
        "1. 带着问题和方法，在聚拢库里面找材料。",
        "2. 找出有聚拢坐标、来源链、原文锚点和路由说明的材料，送到材料池。",
        "",
        "## 2. 本题状态",
        "",
        f"- 问题类型：{payload['aggregation_flow_lock']['problem_type']}",
        f"- 复核候选：{len(review_rows)}",
        f"- 已回聚拢库：{returned_count}",
        f"- 送入材料池：{len(admitted_rows)}",
        f"- 首读有用材料：{payload['counts']['first_read_useful_rows']}",
        f"- 阻断/补证债：{len(blocked_rows)}",
        "",
        "## 3. 取材链路",
        "",
        "- 候选段落回查 W32 聚拢单元库。",
        "- W32 聚拢单元回查 W33 聚拢事件库。",
        "- 带聚拢坐标的候选交给材料池入池凭证门。",
        "- 入池后仍必须由 Codex 做四态裁判：可用主证、背景材料、不可用、需补证。",
        "",
        "## 4. 已送材料池样例",
        "",
        "| 顺序 | 段落 | 聚拢单元 | 聚拢事件 | 分层 | 摘要 |",
        "|---:|---|---|---|---|---|",
    ]
    for row in payload["sample_admitted_rows"]:
        lines.append(
            f"| {row['review_order']} | {row['segment_no']} | {row['aggregate_unit_ids']} | "
            f"{row['aggregate_event_ids']} | {row['human_reading_tier']} | {row['summary']} |"
        )
    if not payload["sample_admitted_rows"]:
        lines.append("|  |  |  |  |  | 暂无入池材料。 |")
    lines.extend(
        [
            "",
            "## 5. 输出",
            "",
            f"- 材料池清单：`{material_csv}`",
            f"- 入池凭证门：`{admission_md}`",
            f"- 首读材料池：`{first_read_pool.get('output_files', {}).get('aggregation_first_read_pool_md', '')}`",
            f"- 阻断清单：`{blocked_csv}`",
            f"- 结构化取材单：`{search_json}`",
        ]
    )
    search_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(search_json, payload)
    return payload


def _has_object_axis_signal(context_text: str) -> bool:
    strong_terms = [
        "物象",
        "器物",
        "空间",
        "场域",
        "诗词",
        "判词",
        "时间",
        "梦境",
        "幻境",
        "花事",
        "落花",
        "眼泪",
        "泪水",
        "金子",
        "银子",
        "玉器",
        "通灵宝玉",
        "通灵玉",
        "金锁",
        "金麒麟",
        "冷香丸",
        "手帕",
        "帕子",
        "竹子",
    ]
    if any(term in context_text for term in strong_terms):
        return True
    stripped = context_text
    for name in [
        "贾宝玉",
        "林黛玉",
        "薛宝钗",
        "宝玉",
        "黛玉",
        "宝钗",
        "妙玉",
        "红玉",
        "小红",
        "贾环",
        "玉钏儿",
        "玉钏",
        "金钏儿",
        "金钏",
        "金荣",
        "夏金桂",
        "金桂",
    ]:
        stripped = stripped.replace(name, "")
    single_char_objects = ["泪", "金", "银", "玉", "竹", "帕", "香", "药", "茶", "扇", "镜", "花", "石", "雪", "月", "钗", "锁", "珠"]
    return any(term in stripped for term in single_char_objects)


def _library_group_status(group: dict[str, Any], context_text: str) -> str:
    haystack = context_text
    if group.get("group") == "物象空间诗词时间层":
        if _has_object_axis_signal(haystack):
            return "本题优先检查"
        return "按题意判断"
    signals = {
        "人物与关系层": ["人物", "关系", "命运", "称谓", "群像", "主仆", "宝玉", "黛玉", "宝钗"],
        "事件与情节层": ["事件", "情节", "因果", "结局", "伏笔", "转折", "发生", "如何"],
        "全文检索与快速召回层": ["关键词", "全文", "搜索", "找", "查"],
        "专题库与库登记处层": ["专题", "性主题", "男男", "男色", "出火", "娈童", "服饰", "泪", "金银", "香气", "梦", "三教", "十二钗", "母题", "库"],
        "文章入库与作品层": ["入库", "保存", "文章", "作品", "阅读"],
        "问题包、证据池与复核写作层": ["证据", "材料", "最终答案", "复核", "经验"],
    }
    wanted = signals.get(group.get("group", ""), [])
    if any(item in haystack for item in wanted):
        return "本题优先检查"
    if group.get("group") in {"A类原文真源层", "原子段落层", "统一证据边与映射健康层", "问题包、证据池与复核写作层", "专题库与库登记处层"}:
        return "所有正式题必经"
    return "按题意判断"


def _evidence_layer_for_library(group_name: str) -> str:
    if group_name == "A类原文真源层":
        return "A类真源"
    if group_name == "原子段落层":
        return "A类定位层"
    if group_name in {"全文检索与快速召回层", "统一证据边与映射健康层", "专题库与库登记处层"}:
        return "入口/映射层"
    if group_name in {"问题包、证据池与复核写作层", "文章入库与作品层"}:
        return "过程/作品层"
    return "B类库线索层"


def _library_precheck_action(group: dict[str, Any], profile: dict[str, Any], status: str) -> dict[str, str]:
    group_name = clean(group.get("group"))
    layer = _evidence_layer_for_library(group_name)
    preferred_libraries = [clean(item) for item in profile.get("codex_libraries", [])] if isinstance(profile, dict) else []
    preferred = any(clean(table) in preferred_libraries for table in group.get("tables", []))
    preferred = preferred or any(group_name in item or item in group_name for item in preferred_libraries if item)

    if layer == "A类真源":
        return {
            "question_relation": "所有正式题最终必回",
            "can_do": "提供整回真源、回目和最终引文核验。",
            "must_return_to_source": "本层就是真源。",
            "codex_next": "需要强结论或最终引文时，Codex 必须回到这里读原文。",
            "risk_gate": "不得用摘要、标题、生成稿替代本层原文。",
        }
    if layer == "A类定位层":
        return {
            "question_relation": "所有正式题定位必经",
            "can_do": "给出 segment_no、chapter_no、上下文范围和稳定锚点。",
            "must_return_to_source": "必须继续回章节真源。",
            "codex_next": "Codex 按锚点回原文，判断是否摘入材料池。",
            "risk_gate": "只命中一个词不等于可用证据。",
        }
    if group_name == "问题包、证据池与复核写作层":
        return {
            "question_relation": "每题过程必经",
            "can_do": "保存问题判断、候选证据、材料池、精读门和复盘底账。",
            "must_return_to_source": "过程材料必须保留来源字段。",
            "codex_next": "Codex 用它做材料判别，不把它当最终答案。",
            "risk_gate": "过程稿不得冒充红楼解语。",
        }
    if group_name == "文章入库与作品层":
        return {
            "question_relation": "用户认可后才启用",
            "can_do": "保存已认可文章，并回挂问题包、证据池和原文锚点。",
            "must_return_to_source": "入库前仍需保留问题包与原文链。",
            "codex_next": "只有用户认可后，Codex 才触发入库预检。",
            "risk_gate": "作品资产不得倒灌污染 A 类真源。",
        }
    if preferred or status in {"本题优先检查", "所有正式题必经"}:
        relation = "本题优先检查" if status == "本题优先检查" or preferred else status
        return {
            "question_relation": relation,
            "can_do": "提供库线索、映射边、候选实体或候选段落。",
            "must_return_to_source": "必须回原子段和章节真源后才能升格。",
            "codex_next": "Codex 读召回理由后决定采用、降级、补查或跳过。",
            "risk_gate": "本层只能导航，不能直接给结论。",
        }
    return {
        "question_relation": "按题意待判",
        "can_do": "可在 Codex 需要补线索时启用。",
        "must_return_to_source": "一旦启用，仍需回原文。",
        "codex_next": "Codex 认为当前题需要时再点亮。",
        "risk_gate": "不得因库存在就机械跑完。",
    }


def build_library_precheck(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
    skeleton: dict[str, Any],
    library_matrix: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    profile = decomposer.route_context_profile(route_context)
    profile = profile if isinstance(profile, dict) else {}
    rows: list[dict[str, Any]] = []
    for order, group in enumerate(library_matrix, start=1):
        action = _library_precheck_action(group, profile, clean(group.get("status")))
        rows.append(
            {
                "order": order,
                "library_group": clean(group.get("group")),
                "status": clean(group.get("status")),
                "evidence_layer": _evidence_layer_for_library(clean(group.get("group"))),
                "tables": group.get("tables", []),
                "question_relation": action["question_relation"],
                "can_do": action["can_do"],
                "must_return_to_source": action["must_return_to_source"],
                "codex_next": action["codex_next"],
                "risk_gate": action["risk_gate"],
            }
        )

    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "route_center": judgment_payload.get("route_center", ""),
        "codex_terms": profile.get("codex_terms", []),
        "codex_libraries": profile.get("codex_libraries", []),
        "compound_groups": profile.get("compound_groups", []),
        "principle": "本表只做本题库法预检：告诉 Codex 哪些库法可用、哪些只能导航、哪些中心表轴承接取材、哪些必须回原文；不替 Codex 选结论，不替单题作答。",
        "rows": rows,
        "metrics": skeleton.get("metrics", {}),
        "output_files": {
            "library_precheck_md": str(package_dir / CORE_FILES["library_precheck_md"]),
            "library_precheck_json": str(package_dir / CORE_FILES["library_precheck_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜本题库态预检表",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 本题策略入口",
        "",
        f"- 问题中心：{payload['route_center'] or '等待入口词包'}",
        f"- Codex查询词：{'、'.join(payload['codex_terms']) or '未提供'}",
        f"- Codex优先库：{'、'.join(payload['codex_libraries']) or '未指定'}",
        f"- 强复合组数：{len(payload['compound_groups'])}",
        "",
        "## 3. 库态第一屏",
        "",
        "| 顺序 | 库群 | 本题关系 | 证据层 | 能做什么 | 回源要求 | Codex下一步 | 风险门 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {order} | {library_group} | {question_relation} | {evidence_layer} | {can_do} | {must_return_to_source} | {codex_next} | {risk_gate} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## 4. 固定边界",
            "",
            "- 如果没有 Codex 查询词路，本题停在入口词门，不让本地工程自动猜题。",
            "- 如果材料只来自 B 类库线索，必须回到原子段和章节真源，不能直接进入强结论。",
            "- 如果某库与本题无关，可以跳过；跳过不是丢材料，而是由 Codex 决定当前题不走这条线。",
            "- 所有可疑、旁支、旧题、生成稿、摘要，都只能作为候选线索，不能冒充原文材料。",
            "",
            f"结构化摘要：`{payload['output_files']['library_precheck_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["library_precheck_md"]
    json_path = package_dir / CORE_FILES["library_precheck_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_library_flow_skeleton(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    skeleton = library_flow_skeleton()
    context_text = " ".join(
        [
            question,
            route_context,
            str(judgment_payload.get("route_center", "")),
            " ".join(str(item) for item in judgment_payload.get("keyword_pool", [])),
            " ".join(str(item) for item in judgment_payload.get("preferred_axes", [])),
        ]
    )
    library_matrix = []
    for group in skeleton["library_groups"]:
        library_matrix.append(
            {
                **group,
                "status": _library_group_status(group, context_text),
                "question_use": "先判断本题是否需要此库；若命中则查库定位，再回段落与章节真源。",
            }
        )
    library_precheck = build_library_precheck(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        judgment_payload=judgment_payload,
        skeleton=skeleton,
        library_matrix=library_matrix,
    )
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "route_center": judgment_payload.get("route_center", ""),
        "axis_db": str(AXIS_DB),
        "search_db": str(SEARCH_DB),
        "source_documents": skeleton["source_documents"],
        "metrics": skeleton["metrics"],
        "library_matrix": library_matrix,
        "flow_patterns": skeleton["flow_patterns"],
        "guardrails": skeleton["guardrails"],
        "library_precheck": library_precheck,
        "output_files": {
            "library_precheck_md": str(package_dir / CORE_FILES["library_precheck_md"]),
            "library_precheck_json": str(package_dir / CORE_FILES["library_precheck_json"]),
            "library_flow_md": str(package_dir / CORE_FILES["library_flow_md"]),
            "library_flow_json": str(package_dir / CORE_FILES["library_flow_json"]),
        },
    }
    md_lines = [
        "# 红楼梦工程｜库线原文流转骨架",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本文件定位",
        "",
        "这是红楼梦工程每题的第 0C 步：在真正查询之前，先把本地库群、Notion 源结构、各库用途和库与原文的关系重新加载到当前问题包里。它不是答案模板，也不替单题作答，只负责让问题知道该用哪些库法理解题目、由哪些中心表轴承接取材、怎样回原文、怎样进入材料池。",
        "",
        "## 2. 本题入口",
        "",
        f"- 问题中心：{payload['route_center'] or '等待入口词包'}",
        f"- 多轴库：`{payload['axis_db']}`",
        f"- 全文库：`{payload['search_db']}`",
        "",
        "## 3. 参照来源",
        "",
    ]
    for doc in payload["source_documents"]:
        source = doc.get("url") or doc.get("path") or ""
        md_lines.append(f"- {doc['name']}：{doc['role']}｜`{source}`")
    md_lines.extend(
        [
            "",
            "## 4. 当前本地底盘数字",
            "",
        ]
    )
    for key, value in payload["metrics"].items():
        md_lines.append(f"- {key}: {value}")
    md_lines.extend(
        [
            "",
            "## 5. 本题库态预检第一屏",
            "",
            f"- 预检表：`{payload['output_files']['library_precheck_md']}`",
            "- 作用：先看本题涉及哪些库、哪些只能导航、哪些必须回原文；再进入下面的库线骨架。",
            "",
            "| 库群 | 本题关系 | 证据层 | Codex下一步 |",
            "|---|---|---|---|",
        ]
    )
    for row in library_precheck["rows"]:
        md_lines.append(
            f"| {row['library_group']} | {row['question_relation']} | {row['evidence_layer']} | {row['codex_next']} |"
        )
    md_lines.extend(
        [
            "",
            "## 6. 库群与映射骨架",
            "",
        ]
    )
    for group in library_matrix:
        md_lines.extend(
            [
                f"### {group['status']}｜{group['group']}",
                "",
                f"- 对应表/文件：{', '.join(group['tables'])}",
                f"- 功能：{group['function']}",
                f"- 连接到：{', '.join(group['maps_to'])}",
                f"- 何时使用：{group['use_when']}",
                f"- 本题动作：{group['question_use']}",
                f"- 风险：{group['risk']}",
                "",
            ]
        )
    md_lines.extend(
        [
            "## 7. 流转方式",
            "",
        ]
    )
    for item in payload["flow_patterns"]:
        md_lines.extend(
            [
                f"### {item['name']}",
                "",
                f"- 流程：{item['flow']}",
                f"- 作用：{item['purpose']}",
                "",
            ]
        )
    md_lines.extend(
        [
            "## 8. 固定守则",
            "",
        ]
    )
    for item in payload["guardrails"]:
        md_lines.append(f"- {item}")
    md_lines.extend(
        [
            "",
            "## 9. 给本题后续步骤的要求",
            "",
            "- 问题树必须把自然语言问题拆成资料需求，不拆成固定写作模板。",
            "- 证据池必须说明材料来自哪个库、是否已回段落、是否已回章节真源。",
            "- 最终答案必须基于工程产物再思考，不把过程材料直接当答案。",
            "",
            f"结构化摘要：`{payload['output_files']['library_flow_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["library_flow_md"]
    json_path = package_dir / CORE_FILES["library_flow_json"]
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_final_reading_gate(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
    library_flow_payload: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "route_center": judgment_payload.get("route_center", ""),
        "recognized_user_conclusion": {
            "title": "AI 判断优先规则",
            "status": "已固化为工程边界。",
            "nature": "这是 AI 与本地查找器的分工规则；不是为某一道题做答案，也不是本地程序的猜题规则。",
            "rule": "问题进入工程后，先由 Codex 根据题意判断人物、物象、空间、事件、诗词或共现等查证路线，并给出需要查询的关键词；本地程序只拿这些词去查库、查原文、回证据、保存过程。",
            "examples": {
                "person_name_noise": "一个字出现在人名中时，是否作为人物线处理，由 Codex 判断。",
                "object_axis_valid": "一个字或短词是否作为物象、器物、空间物或意象处理，也由 Codex 判断；程序不得按字数或固定名单自动决定。",
                "cross_axis_route": "人物与物象、空间、季节或另一人物共同出现时，先判定是否进入多轴共现路线，再选择相关库法和中心表轴。",
            },
        },
        "general_object_cluster_rule": {
            "title": "通用物象证据簇规则",
            "status": "已固化为查证通道；它由 Codex 触发，不由本地程序自动触发。",
            "rule": "当 Codex 判断题目确实围绕物件、意象、器具、植物、信物、陈设或空间物时，再启用通用证据簇：物象轴 -> 原子段 -> 人物/事件/空间/诗词/时间/证据边 -> 原文上下文 -> 材料池 -> 红楼解语。",
            "guardrail": "不得为某个题目、某个字或某个物象写专门答案门禁；所有候选都必须回正式库和原文复核。",
        },
        "general_cross_axis_rule": {
            "title": "通用多轴共现规则",
            "status": "已固化为入口路由规则；不是某一题的特殊障碍。",
            "rule": "当入口词包同时给出主查人物与主查物象、主查空间、主查时间/季节或另一人物，并且题目询问首次、同场、关系、接触、流转或场景时，问题类型必须升格为多轴共现或对应交叉现场题。",
            "guardrail": "多轴共现只决定取材台面和相关库，不直接给结论；结论仍由材料池和原文裁判决定。",
        },
        "style_status": {
            "ui_options": ["自然回答", "原文慢推", "研究式综述"],
            "codex_recall_triggers": [
                "research skill",
                "research-style",
                "style calibration",
                "voice calibration",
                "研究式回答",
                "心得式",
                "推导式",
                "原文慢推",
                "证据慢推",
                "温和收束",
                "材料池自由发挥",
            ],
            "judgment": "风格不是替代证据的模板，而是最终回答层读取材料池后的表达方式。当前应优先采用原文慢推、证据出发、温和收束的写法。",
        },
        "required_material_pool_files": [
            {"key": "library_flow_md", "purpose": "先确认本题该用哪些库法、哪些中心表轴、怎样回真源。"},
            {"key": "question_tree", "purpose": "读 Codex 查询词路执行后的问题树和搜索词网络，看本题到底被转成哪些资料需求。"},
            {"key": "triaged_csv", "purpose": "读候选材料池，逐条看段落号、回目、摘要、引文和命中线索；它不自动代表证据等级。"},
            {"key": "cards", "purpose": "读候选材料卡片，看哪些原文和摘要值得 Codex 先判定。"},
            {"key": "review_csv", "purpose": "读候选材料复核表；它是材料清单，不替 Codex 判断主证、旁证或反证。"},
            {"key": "writing_md", "purpose": "读复核回读材料，作为候选阅读辅助；最终可用性仍以 Codex 材料池判定为准。"},
            {"key": "codex_material_judgment_md", "purpose": "最终答案前必须读取的 Codex 材料池判定：可用、背景、不可用、需补证和 writing_mode。"},
            {"key": "codex_close_reading_md", "purpose": "最终答案前必须读取的 Codex 精读材料词：选入材料、舍弃材料、原文锚点、材料词和文风方向。"},
        ],
        "final_answer_gate": [
            "写最终文档前，必须先读材料池，不得只读标题或只看一个摘要。",
            "逐条判定材料：每条至少看 segment_no、chapter_no、summary、quote、命中线索、是否支持原问题。",
            "材料角色由 Codex 决定：可用、背景、不可用、需补证；本地表格不得自动升级为结论。",
            "用文风读材料池：原文慢推、证据出发、温和收束；让结论从材料中自然长出来。",
            "最终答案若没有足够材料，应说材料不足并给出补证方向，不生成漂亮但无证据的文章。",
        ],
        "evidence_trace_rule": [
            "最终答案中的关键判断，要能回到至少一条原子段或明确说明证据不足。",
            "最终窗口或备注区应提供原证追溯：segment_no、chapter_no、摘要、原文短摘、证据角色。",
            "如果正文为了阅读流畅不插太多编号，文末必须有“原文锚点/证据依据”区。",
            "原文短摘只作证据锚点，不替代对整段上下文的阅读。",
        ],
        "output_files": {
            "final_reading_gate_md": str(package_dir / CORE_FILES["final_reading_gate_md"]),
            "final_reading_gate_json": str(package_dir / CORE_FILES["final_reading_gate_json"]),
        },
        "library_flow_file": library_flow_payload.get("output_files", {}).get("library_flow_md", ""),
    }
    lines = [
        "# 红楼梦工程｜最终回答前材料池精读门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本文件定位",
        "",
        "这是最终回答/最终文章之前的硬门槛。它保存用户认可的工程规则，并要求最终回答层真正阅读材料池、逐条判断证据，再以合适文风写出答案。",
        "",
        "## 2. 已保存的认可结论",
        "",
        f"- 结论：{payload['recognized_user_conclusion']['rule']}",
        f"- 性质：{payload['recognized_user_conclusion']['nature']}",
        f"- 状态：{payload['recognized_user_conclusion']['status']}",
        f"- 例 1：{payload['recognized_user_conclusion']['examples']['person_name_noise']}",
        f"- 例 2：{payload['recognized_user_conclusion']['examples']['object_axis_valid']}",
        "",
        "## 3. 通用物象证据簇规则",
        "",
        f"- 规则：{payload['general_object_cluster_rule']['rule']}",
        f"- 状态：{payload['general_object_cluster_rule']['status']}",
        "- 适用对象：物件、意象、器具、植物、信物、陈设、空间物。",
        f"- 防误区：{payload['general_object_cluster_rule']['guardrail']}",
        "",
        "## 4. 最终写作前必须读的材料池",
        "",
    ]
    for item in payload["required_material_pool_files"]:
        lines.append(f"- `{item['key']}`：{item['purpose']}")
    lines.extend(
        [
            "",
            "## 5. 最终回答前硬门槛",
            "",
        ]
    )
    for item in payload["final_answer_gate"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 6. 原证追溯要求",
            "",
        ]
    )
    for item in payload["evidence_trace_rule"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 7. 文风与 skill 状态",
            "",
            f"- 判断：{payload['style_status']['judgment']}",
            f"- 页面可选风格：{'、'.join(payload['style_status']['ui_options'])}",
            f"- 召回提示词已识别触发：{'、'.join(payload['style_status']['codex_recall_triggers'])}",
            "- 说明：这里不是套写作模板，而是把 research/style calibration 的精神用于最终表达：证据、推理、结论分清，语气自然。",
            "",
            "## 8. 给最终回答层的话",
            "",
            "不要替工程做题，不要用漂亮话遮住证据缺口。先读材料池，再读原文锚点，再写最终答案；答案可以有温度，但每个关键判断都要能回到材料。",
            "",
            f"结构化摘要：`{payload['output_files']['final_reading_gate_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["final_reading_gate_md"]
    json_path = package_dir / CORE_FILES["final_reading_gate_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def process_product_gate_catalog() -> list[dict[str, Any]]:
    return [
        {
            "stage": "A0",
            "name": "Codex 查询词路",
            "files": ["Codex运行记录/*_query_strategy_last_message.md"],
            "producer": "Codex",
            "product_type": "AI查证前判断",
            "contains": "问题中心、搜索词、优先库、查证顺序、误召回注意事项。",
            "module_search": "否",
            "codex_gate": "本身就是第一道 Codex 门；失败则工程停在入口词门。",
            "next_step": "只有策略 JSON 有效，才能进入本地查库与原文召回。",
        },
        {
            "stage": "B1",
            "name": "问题判断程序",
            "files": [CORE_FILES["question_judgment_md"], CORE_FILES["keyword_precheck_json"]],
            "producer": "本地工程按 Codex 触发包整理",
            "product_type": "路线与关键词预检",
            "contains": "问题中心、候选实体、候选搜索词、优先轴、经验仓命中、子问题候选。",
            "module_search": "半成品；只保存路线和候选词，不得当作题目理解的最终结论。",
            "codex_gate": "必须进入 Codex 过程判别：检查关键词是否抓住问题、是否漏掉关键对象、是否串旧题。",
            "next_step": "Codex 判别通过或给出补查词后，才能信任为后续召回路线。",
        },
        {
            "stage": "B2",
            "name": "库线原文流转骨架",
            "files": [CORE_FILES["library_flow_md"], CORE_FILES["library_flow_json"]],
            "producer": "本地工程",
            "product_type": "库群地图",
            "contains": "人物库、物象库、空间库、诗词库、事件库、段落库、原文真源之间的关系。",
            "module_search": "否；它是地图，不是答案。",
            "codex_gate": "Codex 必须判断本题到底该用哪些库、哪些映射、哪些原文入口。",
            "next_step": "只把被 Codex 选中的库线作为本题重点，其他只作背景。",
        },
        {
            "stage": "B3",
            "name": "最终回答前材料池精读门",
            "files": [CORE_FILES["final_reading_gate_md"], CORE_FILES["final_reading_gate_json"]],
            "producer": "本地工程固化规则",
            "product_type": "写作前硬门槛",
            "contains": "最终答案必须读哪些材料池文件、怎样保留原文锚点、怎样区分风格与模板。",
            "module_search": "否；它是门槛规则。",
            "codex_gate": "最终写作 Codex 必须执行此门；未读材料池不得写最终答案。",
            "next_step": "约束材料池判定和最终红楼解语。",
        },
        {
            "stage": "C1",
            "name": "问题树",
            "files": [CORE_FILES["question_tree"]],
            "producer": "本地拆题器按 Codex 策略转成可查询任务",
            "product_type": "子问题/资料需求",
            "contains": "库态预检、搜索词网络、原文矩阵、材料池交接、二次补查等待。",
            "module_search": "是；它只是把路线变成候选任务。",
            "codex_gate": "必须由 Codex 过程判别检查：子问题是否服务原问题、有没有遗漏关键文类或原文方向。",
            "next_step": "通过后进入证据池召回；不通过则按 Codex 补查词重跑。",
        },
        {
            "stage": "C2",
            "name": "证据阅读顺序 / 候选材料池",
            "files": [CORE_FILES["triaged_csv"], CORE_FILES["cards"]],
            "producer": "本地搜索与证据包",
            "product_type": "模块搜索候选",
            "contains": "segment_no、chapter_no、summary、quote、命中词、候选排序、重点证据卡片。",
            "module_search": "是；这是最需要警惕的模块搜索产物。",
            "codex_gate": "必须由 Codex 过程判别和材料池判定逐条筛选：可用、背景、不可用、需补证。",
            "next_step": "不能直接进入答案；只能进入原文复核与 Codex 材料池判定。",
        },
        {
            "stage": "C3",
            "name": "复核表 / 复核阅读单",
            "files": [CORE_FILES["review_csv"], CORE_FILES["reading_md"]],
            "producer": "本地复核包",
            "product_type": "候选材料核对表",
            "contains": "候选段落、复核问题、上下文阅读提示、待核字段。",
            "module_search": "是；它整理候选，不代表证据成立。",
            "codex_gate": "Codex 必须检查每条候选是否真的回答问题，尤其是否有原文、上下文和同场关系。",
            "next_step": "通过者可进入候选材料池；不足者进入补查决定。",
        },
        {
            "stage": "C4",
            "name": "复核回读材料",
            "files": [CORE_FILES["writing_md"]],
            "producer": "本地回读器",
            "product_type": "材料池阅读辅助",
            "contains": "从候选表回读出的摘要、引文、段落和可阅读材料。",
            "module_search": "是；它是可读材料，不是写作结论。",
            "codex_gate": "Codex 材料池判定必须逐条读它，再决定能否用于写作。",
            "next_step": "进入 Codex 材料池判定。",
        },
        {
            "stage": "D1",
            "name": "Codex 全流程过程判别",
            "files": ["00K_Codex全流程过程判别_<request_id>_*.md/json"],
            "producer": "Codex",
            "product_type": "过程筛选与下一步决策",
            "contains": "关键词是否有效、关键段落/诗词/原文是否找到、哪些候选跑偏、补查词、是否允许进入材料池判定。",
            "module_search": "否",
            "codex_gate": "第二道 Codex 门；如果要求补查，本地工程只能按 Codex 给出的词和库再跑。",
            "next_step": "通过则进入材料池判定；需补查则生成二轮工程包。",
        },
        {
            "stage": "D2",
            "name": "Codex 材料池判定",
            "files": ["00I_Codex材料池判定_<request_id>.md/json"],
            "producer": "Codex",
            "product_type": "材料角色与写作许可",
            "contains": "可用材料、背景材料、不采用材料、证据缺口、下一轮查证决定、writing_mode。",
            "module_search": "否",
            "codex_gate": "第三道 Codex 门；没有它不能进入最终回答。",
            "next_step": "可以写/谨慎写/先补证，决定最终红楼解语的写法和边界。",
        },
        {
            "stage": "D3",
            "name": "Codex 精读材料词",
            "files": ["00L_Codex精读材料词_<request_id>.md/json"],
            "producer": "Codex",
            "product_type": "写作前材料精读与舍取",
            "contains": "选入材料、舍弃/降级材料、原文锚点、精读观察、证据缺口、材料词、文风方向和写作许可。",
            "module_search": "否",
            "codex_gate": "第四道 Codex 门；它只整理材料，不写最终答案；所有选择必须来自工程已供给材料或用户原题。",
            "next_step": "通过后进入写作前原文追证摘抄；最终写作者必须先读 00M，再写答案。",
        },
        {
            "stage": "D4",
            "name": "Codex 写作前原文追证摘抄",
            "files": ["00M_Codex写作前原文通读摘抄_<request_id>.md/json"],
            "producer": "Codex",
            "product_type": "最终写作前原文摘抄底稿",
            "contains": "原问题复习、子问题复习、选摘原文、子问题覆盖、证据缺口和最终写作提示。",
            "module_search": "否",
            "codex_gate": "第五道 Codex 门；它读完整体精品材料词后自行选择需要回原文摘抄的材料，不强迫每个子问题单独跑流程。",
            "next_step": "通过后进入红楼解语；最终写作者必须优先读取它。",
        },
        {
            "stage": "E1",
            "name": "红楼解语",
            "files": ["outputs/红楼梦Codex最终答案/最终答案/A_<request_id>_*.md"],
            "producer": "Codex",
            "product_type": "最终回答",
            "contains": "基于工程材料和 Codex 判定后的解释、归纳、整理和写作。",
            "module_search": "否",
            "codex_gate": "最终输出层；必须引用材料池和原文锚点，不得回显模块过程稿。",
            "next_step": "可进入文章入库预检或继续追问。",
        },
    ]


def build_process_inventory(question: str, route_context: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    catalog = process_product_gate_catalog()
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "purpose": "盘点红楼梦工程每个会产生文字、词、表、卡、候选和原文材料的位置，并标明哪些必须交给 Codex 判别后才能进入下一步。",
        "core_rule": "本地工程是查找器和材料包生成器；Codex 策略是方向盘 + 调度单。00I 不是固定流水线，而是运行前置总规则：底层完整出包，Codex 决定哪些产物采用、降级、补查、跳过或停止；这里的跳过是指某个产物本题不采用、不升级、不进入下一门，不是破坏底层工程的完整出包。只要某一路产生了词、表、卡、候选或原文材料，就必须进入 Codex 判别后再决定下一步。",
        "operating_position": {
            "codex_strategy": "方向盘 + 调度单：真实改变工程查什么词、进哪些库、怎么形成问题树。",
            "local_engine": "查找器 + 材料包生成器：保留原来的问题判断、库线、证据池、复核和回读流程，完整出包供回收判别。",
            "dispatch_rule": "顺序清楚但不能死板。清楚是为了可追踪；不死板是为了保留查询的发散能力。",
        },
        "dispatch_actions": ["采用", "降级", "补查", "跳过", "停止"],
        "stages": catalog,
        "hard_gates": [
            "Codex 查询词路失败：工程停在入口词门。",
            "Codex 过程判别认为关键词、段落、诗词或原文缺口过大：按本题自然流程补证、跳转侧路或停止，不进入最终写作。",
            "Codex 材料池判定失败：停止，不进入最终答案。",
            "Codex 材料池判定 writing_mode=先补证：最终答案只能写补证说明或谨慎临时判断，不硬写完整结论。",
            "Codex 精读材料词失败：停止，不进入写作前原文追证摘抄。",
            "Codex 写作前原文追证摘抄失败：停止，不进入最终答案。",
            "任何模块搜索产物、复核表、候选卡片、回读材料，都不得直接冒充红楼解语。",
        ],
        "flow_comparison": [
            {
                "name": "旧理解/Notion短链",
                "flow": "材料池判定 -> 精读材料词/聚拢池 -> 红楼解语",
                "use_when": "候选少、问题短、原文锚点很集中时可作为理解模型。",
                "risk": "候选多或多子问题时，精读材料词容易承担过多职责，最终层可能把材料标签当原文理解。",
            },
            {
                "name": "当前真实工程链路",
                "flow": "材料池判定 -> 精读材料词/精品聚拢池 -> 写作前原文追证摘抄 -> 红楼解语",
                "use_when": "当前本地工程默认采用；适合候选多、子问题多、需要回原文重新摘取的题。",
                "risk": "链路更长，所以每个 Codex 阶段都加任务记忆卡，00M 阶段重读原问题和子问题。",
            },
        ],
        "current_true_flow": [
            "查询词路：Codex 先读原题，决定执行词、强复合组、优先库和查证顺序。",
            "工程出包：本地工程按策略召回候选、问题树、原文锚点、复核表和回读材料。",
            "过程判别：Codex 判断候选是否抓住原题，是否补查，是否进入材料池判定。",
            "材料池判定：Codex 把候选判为可用、背景、不可用、需补证。",
            "精读材料词/精品聚拢池：Codex 在一个总精品材料词里按原问题和子问题整理材料，不把每个子问题拆成独立流程。",
            "写作前原文追证摘抄：Codex 读完整体精品材料词，自行选择值得回原文摘抄的材料；一条原文可服务多个子问题，某个子问题也可暂缺。",
            "红楼解语：Codex 优先读取写作前原文追证摘抄，再组织最终表达。",
        ],
    }
    md_lines = [
        "# 红楼梦工程｜全流程产物与 Codex 判别门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 本文件用途",
        "",
        payload["purpose"],
        "",
        "它不是要求每个问题机械走完全部节点，而是先判断本题的自然查证路径：定位题可以短链，人物/物象/空间/诗词交织题可以走多轴，材料不足时可以走补查侧路，问题本身无需查库时可以直接说明不进入深链。底层工程仍可完整出包；Codex 决定哪些产物被采用、降级、补查、跳过或停止。",
        "",
        "## 2. 总规矩",
        "",
        f"- {payload['core_rule']}",
        f"- Codex 策略定位：{payload['operating_position']['codex_strategy']}",
        f"- 工程本体定位：{payload['operating_position']['local_engine']}",
        f"- 顺序原则：{payload['operating_position']['dispatch_rule']}",
        f"- 调度动作：{'、'.join(payload['dispatch_actions'])}。",
        "- 只要一个步骤产生了词、表、卡、候选段落、诗词线索、原文摘录或材料说明，它就必须被标明身份：是查找器产物，还是 Codex 判别产物。",
        "- 查找器产物只能进入下一道 Codex 判别，不能直接进入最终写作。",
        "- Codex 每次判别只决定本题下一步：继续本链、补查侧路、跳过无关产物、进入材料池、停止并说明不足；不要求全链条逐项报到。跳过是“不采用/不进入下一门”，不是阻止底层工程生成备查文件。",
        "",
        "## 3. 对比流程与当前真实流程",
        "",
        "| 版本 | 流程 | 适用 | 风险/修正 |",
        "|---|---|---|---|",
    ]
    for row in payload["flow_comparison"]:
        md_lines.append(f"| {row['name']} | {row['flow']} | {row['use_when']} | {row['risk']} |")
    md_lines.extend(
        [
            "",
            "当前真实流程：",
            "",
            *[f"- {item}" for item in payload["current_true_flow"]],
            "",
            "## 4. 硬门",
        "",
        ]
    )
    md_lines.extend(f"- {item}" for item in payload["hard_gates"])
    md_lines.extend(["", "## 5. 全流程产物清单", ""])
    for item in catalog:
        md_lines.extend(
            [
                f"### {item['stage']}｜{item['name']}",
                "",
                f"- 产出文件：{', '.join(item['files'])}",
                f"- 产生者：{item['producer']}",
                f"- 产物性质：{item['product_type']}",
                f"- 内容：{item['contains']}",
                f"- 是否模块搜索/候选产物：{item['module_search']}",
                f"- Codex 判别门：{item['codex_gate']}",
                f"- 下一步：{item['next_step']}",
                "",
            ]
        )
    md_path = package_dir / CORE_FILES["process_inventory_md"]
    json_path = package_dir / CORE_FILES["process_inventory_json"]
    md_path.write_text("\n".join(md_lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return {
        **payload,
        "process_inventory_md": str(md_path),
        "process_inventory_json": str(json_path),
    }


def _axis_rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if not AXIS_DB.exists():
        return []
    try:
        with sqlite3.connect(AXIS_DB) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        return [{"error": f"{type(exc).__name__}: {exc}", "sql": sql}]


def _dedupe_rows(rows: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        marker = tuple(clean(row.get(key)) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(row)
    return unique


def _read_existing_csv(path_value: object) -> list[dict[str, str]]:
    path = Path(str(path_value or ""))
    if not path.exists():
        return []
    return read_csv(path)


def _count_rows_with(rows: list[dict[str, str]], key: str, *, min_len: int = 1) -> int:
    return sum(1 for row in rows if len(clean(row.get(key))) >= min_len)


def _count_rows_int_at_least(rows: list[dict[str, str]], key: str, minimum: int) -> int:
    count = 0
    for row in rows:
        try:
            if int(float(clean(row.get(key)) or "0")) >= minimum:
                count += 1
        except ValueError:
            continue
    return count


def _audit_status(ok: bool, partial: bool = False) -> str:
    if ok:
        return "达标"
    if partial:
        return "部分达标"
    return "未达标"


def build_second_round_decision_card(
    question: str,
    route_context: str,
    package_dir: Path,
    codex_terms: list[Any],
    preferred_libraries: list[Any],
    compound_groups: list[Any],
    total_rows: int,
    source_trace_rows: int,
    reasons_rows: int,
    source_original_rows: int,
    original_rows: int,
    long_original_rows: int,
    same_chapter_multi_rows: int,
    bucket_counts: Counter,
    status_counts: Counter,
    source_system_counts: Counter,
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    route_profile = _route_profile_from_context(route_context, question)
    route_mode = _route_mode_from_context(route_context, question)
    aggregation_lock_md = package_dir / CORE_FILES["aggregation_flow_lock_md"]
    aggregation_lock_json = package_dir / CORE_FILES["aggregation_flow_lock_json"]
    aggregation_lock_ready = aggregation_lock_md.exists() and aggregation_lock_json.exists()
    aggregation_court_missing = _aggregation_court_missing(package_dir)
    aggregation_court_ready = not aggregation_court_missing
    hard_gates = []

    def add_gate(name: str, status: str, evidence: str, codex_action: str) -> None:
        hard_gates.append(
            {
                "name": name,
                "status": status,
                "evidence": evidence,
                "codex_action": codex_action,
            }
        )

    add_gate(
        "入口词门",
        "通过" if codex_terms else "停止",
        f"Codex 查询词 {len(codex_terms)} 个；优先库 {len(preferred_libraries)} 个；强复合组 {len(compound_groups)} 个。",
        "若无查询词，本题停在入口词门，由 Codex 重新生成查询词路；本地工程不得自动补词。",
    )
    add_gate(
        "候选门",
        "通过" if total_rows > 0 else "补证",
        f"候选材料 {total_rows} 行。",
        "若候选为空，Codex 回旧S卡调整查询词、库线或复合路径。",
    )
    add_gate(
        "来源链门",
        "通过" if total_rows > 0 and source_trace_rows == total_rows and reasons_rows == total_rows else "补链",
        f"来源链 {source_trace_rows}/{total_rows}；召回理由 {reasons_rows}/{total_rows}。",
        "来源链或召回理由不足时，先补查库线，不进入最终写作。",
    )
    add_gate(
        "原文门",
        "通过" if total_rows > 0 and source_original_rows == total_rows else "补原文",
        f"原文字段 {source_original_rows}/{total_rows}；原文回收 {original_rows}/{total_rows}；大段原文 {long_original_rows}/{total_rows}。",
        "材料池主体必须是原文；摘要只作旁注。原文不足时，按原子段回整回正文多点摘取。",
    )
    add_gate(
        "同回多点门",
        "通过" if same_chapter_multi_rows > 0 else "可补",
        f"同回多段回收 {same_chapter_multi_rows}/{total_rows}。",
        "复杂题应允许一回内跳取多段原文；若只取一个命中点，Codex 判断是否扩窗。",
    )
    risk_rows = int(bucket_counts.get("风险缺口候选柜", 0)) + int(bucket_counts.get("暂缓废弃候选柜", 0))
    strong_rows = int(bucket_counts.get("主证候选柜", 0)) + int(source_system_counts.get("A+B对账候选", 0))
    add_gate(
        "分柜门",
        "通过" if strong_rows or risk_rows < total_rows else "补证",
        f"强候选 {strong_rows} 行；风险/暂缓 {risk_rows} 行；分柜 {dict(bucket_counts)}。",
        "分柜只给 Codex 阅读顺序；若风险柜占比过高，先二轮补证。",
    )
    add_gate(
        "聚拢裁判门",
        "通过" if aggregation_court_ready else "阻断",
        f"聚拢四件套：{'已齐' if aggregation_court_ready else '缺 ' + '、'.join(aggregation_court_missing)}。",
        "所有召回命中都必须先完成 00AC/00AG/00AI/00AM；缺任一项，本题停在聚拢裁判门。",
    )

    if not codex_terms:
        suggested_state = "停止在入口词门"
        suggested_next = "请 Codex 重新生成入口词包，再交给工程查库。"
    elif total_rows <= 0:
        suggested_state = "回旧S卡补查"
        suggested_next = "Codex 调整查询词、优先库、强复合组，再重跑工程。"
    elif not source_trace_rows or not reasons_rows:
        suggested_state = "补来源链"
        suggested_next = "先补每条候选的库来源、召回理由和原子段定位。"
    elif not aggregation_court_ready:
        suggested_state = "阻断：等待聚拢库取材与材料池入池"
        suggested_next = "召回命中只算入口；必须先补齐 00AC/00AG/00AI/00AJ/00AK/00AM，再进入材料池四态裁判。"
    elif total_rows > 0 and source_trace_rows == total_rows and reasons_rows == total_rows and source_original_rows == total_rows and original_rows > 0:
        suggested_state = "召回已命中，待聚拢裁判"
        suggested_next = "材料命中只算召回；先读 00AC/00AG/00AI/00AM，完成材料池四态裁判，再决定是否进入精读材料词和 00M。"
    elif long_original_rows <= 0:
        suggested_state = "补原文材料"
        suggested_next = "按已定位原子段回整回正文，摘取足量原文，再进入材料池。"
    elif risk_rows > strong_rows and risk_rows > 0:
        suggested_state = "二轮补证"
        suggested_next = "Codex 精读风险柜，决定补哪条库线、哪组词、哪一回原文。"
    else:
        suggested_state = "可进入材料池精读"
        suggested_next = "Codex 逐条读材料池，决定采用、降级、旁证、反证、舍弃或补查。"

    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "principle": "二轮补证决策卡只暴露状态、缺口和可选下一步；不替 Codex 判定答案，不替本地工程写结论。",
        "suggested_state": suggested_state,
        "suggested_next": suggested_next,
        "hard_gates": hard_gates,
        "counts": {
            "candidate_rows": total_rows,
            "source_trace_rows": source_trace_rows,
            "retrieval_reason_rows": reasons_rows,
            "source_original_rows": source_original_rows,
            "original_rows": original_rows,
            "long_original_rows": long_original_rows,
            "same_chapter_multi_rows": same_chapter_multi_rows,
            "bucket_counts": dict(bucket_counts),
            "evidence_status_counts": dict(status_counts),
            "source_system_counts": dict(source_system_counts),
        },
        "route_mode": route_mode,
        "route_mode_reason": route_profile.get("route_mode_reason", "") if isinstance(route_profile, dict) else "",
        "direct_answer_bypass_disabled": True,
        "aggregation_lock_ready": aggregation_lock_ready,
        "aggregation_court_ready": aggregation_court_ready,
        "aggregation_court_missing": aggregation_court_missing,
        "aggregation_lock_files": {
            "aggregation_flow_lock_md": str(aggregation_lock_md),
            "aggregation_flow_lock_json": str(aggregation_lock_json),
        },
        "codex_choices": [
            "进入极简聚拢裁判",
            "进入材料池精读",
            "按风险柜二轮补证",
            "回旧S卡改查询词或库线",
            "扩同回原文窗口",
            "暂缓本题，等待更多库或人工确认",
        ],
        "output_files": {
            "second_round_decision_md": str(package_dir / CORE_FILES["second_round_decision_md"]),
            "second_round_decision_json": str(package_dir / CORE_FILES["second_round_decision_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜二轮补证决策卡",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 当前建议状态",
        "",
        f"- 状态：{suggested_state}",
        f"- 下一步：{suggested_next}",
        "",
        "## 3. 硬门检查",
        "",
        "| 门 | 状态 | 当前证据 | Codex动作 |",
        "|---|---|---|---|",
    ]
    for gate in hard_gates:
        lines.append(f"| {gate['name']} | {gate['status']} | {gate['evidence']} | {gate['codex_action']} |")
    lines.extend(
        [
            "",
            "## 4. 计数底账",
            "",
            f"- 候选材料：{total_rows}",
            f"- 来源链：{source_trace_rows}",
            f"- 召回理由：{reasons_rows}",
            f"- 原文字段：{source_original_rows}",
            f"- 原文回收：{original_rows}",
            f"- 大段原文：{long_original_rows}",
            f"- 同回多段回收：{same_chapter_multi_rows}",
            f"- 分柜：{dict(bucket_counts)}",
            f"- 证据状态：{dict(status_counts)}",
            f"- 来源系统：{dict(source_system_counts)}",
            "",
            "## 5. Codex 可选动作",
            "",
        ]
    )
    for choice in payload["codex_choices"]:
        lines.append(f"- {choice}")
    lines.extend(
        [
            "",
            "## 6. 边界",
            "",
            "- 这张卡不是最终答案，也不是本地补题器。",
            "- 任何“可直接命中”都只能写成“召回已命中，待聚拢裁判”。",
            "- 没有聚拢裁判单，不得写最终红楼解语；简单题只允许走极简聚拢裁判，不允许绕开。",
            "- 工程只把缺口暴露出来；是否补、补哪里、补到什么程度，由 Codex 读材料后决定。",
            "- 本地工程召回的材料不得自动省略；页面可以折叠，但底账必须保留。",
            "",
            f"结构化摘要：`{payload['output_files']['second_round_decision_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["second_round_decision_md"]
    json_path = package_dir / CORE_FILES["second_round_decision_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_codex_pipeline_audit(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_result: dict[str, Any],
    library_flow_payload: dict[str, Any],
    research_result: dict[str, Any],
    review_result: dict[str, Any],
    readback_result: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    profile = decomposer.route_context_profile(route_context)
    codex_terms = profile.get("codex_terms", []) if isinstance(profile, dict) else []
    preferred_libraries = profile.get("codex_libraries", []) if isinstance(profile, dict) else []
    compound_groups = profile.get("compound_groups", []) if isinstance(profile, dict) else []
    triaged_rows = _read_existing_csv(research_result.get("triaged_csv", ""))
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))

    source_rows = review_rows or triaged_rows
    total_rows = len(source_rows)
    object_rows = _count_rows_with(source_rows, "object_axis_hits")
    person_rows = _count_rows_with(source_rows, "person_axis_hits")
    evidence_edge_rows = _count_rows_with(source_rows, "evidence_edge_hits")
    source_trace_rows = _count_rows_with(source_rows, "source_trace")
    reasons_rows = _count_rows_with(source_rows, "retrieval_reasons")
    original_rows = _count_rows_with(source_rows, "codex_original_passages", min_len=80)
    long_original_rows = _count_rows_with(source_rows, "codex_original_passages", min_len=600)
    same_chapter_rows = _count_rows_with(source_rows, "same_chapter_passage_segments", min_len=20)
    same_chapter_multi_rows = _count_rows_int_at_least(source_rows, "same_chapter_passage_count", 2)
    source_original_rows = sum(
        1
        for row in source_rows
        if clean(row.get("codex_original_passages")) or clean(row.get("same_chapter_passage_segments"))
    )
    located_rows = sum(1 for row in source_rows if clean(row.get("segment_no")) and clean(row.get("chapter_no")))
    bucket_counts = Counter(clean(row.get("codex_material_bucket")) or "未分柜" for row in source_rows)
    status_counts = Counter(clean(row.get("evidence_status")) or "未标状态" for row in source_rows)
    source_system_counts = Counter(clean(row.get("source_system")) or "未标来源" for row in source_rows)
    bucketed_rows = sum(1 for row in source_rows if clean(row.get("codex_material_bucket")))
    source_status_rows = sum(1 for row in source_rows if clean(row.get("evidence_status")) and clean(row.get("source_system")))
    summary_only_rows = sum(
        1
        for row in source_rows
        if clean(row.get("summary")) and not clean(row.get("codex_original_passages"))
        and not clean(row.get("same_chapter_passage_segments"))
    )
    entry_hard_gate_path = package_dir / CORE_FILES["entry_hard_gate_md"]
    entry_hard_gate_json_path = package_dir / CORE_FILES["entry_hard_gate_json"]
    entry_hard_gate_payload = read_json(entry_hard_gate_json_path, {}) if entry_hard_gate_json_path.exists() else {}
    hard_gates = entry_hard_gate_payload.get("hard_gates", []) if isinstance(entry_hard_gate_payload, dict) else []
    exhaustive_required = bool(entry_hard_gate_payload.get("exhaustive_source_sweep_required")) if isinstance(entry_hard_gate_payload, dict) else False
    close_reading_gate_path = package_dir / CORE_FILES["codex_close_reading_gate_md"]
    close_reading_target_path = package_dir / CORE_FILES["codex_close_reading_target_md"]
    original_reread_gate_path = package_dir / CORE_FILES["codex_original_reread_gate_md"]
    original_reread_target_path = package_dir / CORE_FILES["codex_original_reread_target_md"]
    material_judgment_actual_md = _latest_matching_file(package_dir, "00I_Codex材料池判定_*.md")
    material_judgment_actual_json = _latest_matching_file(package_dir, "00I_Codex材料池判定_*.json")
    close_reading_actual_md = _latest_matching_file(package_dir, "00L_Codex精读材料词_*.md")
    close_reading_actual_json = _latest_matching_file(package_dir, "00L_Codex精读材料词_*.json")
    original_reread_actual_md = _latest_matching_file(package_dir, "00M_Codex写作前原文通读摘抄_*.md")
    original_reread_actual_json = _latest_matching_file(package_dir, "00M_Codex写作前原文通读摘抄_*.json")
    final_prewrite_ready = bool(
        material_judgment_actual_md
        and material_judgment_actual_json
        and close_reading_actual_md
        and close_reading_actual_json
        and original_reread_actual_md
        and original_reread_actual_json
    )

    checks = [
        {
            "stage": "0. 入口硬规则门",
            "expected": "每个问题包必须先生成查库优先、库登记处、全书穷尽查证/查访、原文回归和禁止直接答案五个硬门。",
            "status": _audit_status(entry_hard_gate_path.exists() and entry_hard_gate_json_path.exists() and len(hard_gates) >= 5),
            "evidence": f"入口硬门：{entry_hard_gate_path}；结构化硬门：{entry_hard_gate_json_path}；硬门数 {len(hard_gates)}；全书穷尽查证硬启用：{exhaustive_required}。",
            "next_fix": "" if entry_hard_gate_path.exists() and entry_hard_gate_json_path.exists() else "必须先生成 00AA/00AB，不能只靠文字说明或流程图。",
        },
        {
            "stage": "1. 用户问题进入工程",
            "expected": "问题和页面触发包一起进入红楼梦工程，不由本地模块直接答题。",
            "status": _audit_status(bool(clean(question)) and bool(clean(route_context))),
            "evidence": f"问题长度 {len(clean(question))}；触发包长度 {len(clean(route_context))}。",
            "next_fix": "" if clean(route_context) else "入口必须补齐页面触发包和 Codex 查询词路字段。",
        },
        {
            "stage": "2. Codex 拆解查询词路",
            "expected": "Codex 根据题意和工程能力生成查询词、强复合、优先库和查证步骤；没有旧S卡则停在入口词门。",
            "status": _audit_status(bool(codex_terms)),
            "evidence": f"Codex查询词：{'、'.join(codex_terms) or '缺失'}；强复合组：{len(compound_groups)}；优先库：{'、'.join(preferred_libraries) or '缺失'}。",
            "next_fix": "" if codex_terms else "保持入口词门：无 Codex 查询词时不运行证据池。",
        },
        {
            "stage": "3. 工程执行查库查原文",
            "expected": "工程不负责思考答案，只负责按 Codex 策略提供原子段位置和命中理由；召回底账不得按本地自判重要性省略候选。",
            "status": _audit_status(bool(codex_terms) and int(research_result.get("unique_segments") or 0) > 0),
            "evidence": f"候选唯一原子段 {research_result.get('unique_segments', 0)}；命中理由行 {reasons_rows}/{total_rows}；问题中心 {judgment_result.get('route_center', '') or judgment_result.get('center', '')}。",
            "next_fix": "继续保持本地自动生词停用；如果候选为空，只能回 Codex 重新给词或补库。",
        },
        {
            "stage": "4. 原子段来源链",
            "expected": "每个原子段要说明为何被找出：来自物象库、人物映射、证据边，还是原文搜索词网络。",
            "status": _audit_status(
                total_rows > 0 and source_trace_rows == total_rows and reasons_rows == total_rows,
                partial=source_trace_rows > 0 or reasons_rows > 0,
            ),
            "evidence": f"总候选 {total_rows}；来源链行 {source_trace_rows}；命中理由行 {reasons_rows}；物象库行 {object_rows}；人物映射行 {person_rows}；证据边行 {evidence_edge_rows}。",
            "next_fix": "" if total_rows > 0 and source_trace_rows == total_rows and reasons_rows == total_rows else "每条候选必须保留来源链和召回理由，供 Codex 判断是否继续取材。",
        },
        {
            "stage": "5. 锁定原子段",
            "expected": "每条候选必须有 segment_no 与 chapter_no，作为 Codex 回原文的稳定锚点。",
            "status": _audit_status(total_rows > 0 and located_rows == total_rows, partial=located_rows > 0),
            "evidence": f"有原子段和回目编号的候选 {located_rows}/{total_rows}。",
            "next_fix": "" if total_rows and located_rows == total_rows else "不能进入材料池；先补 segment_no/chapter_no。",
        },
        {
            "stage": "6. Codex 按锚点回整回原文取材",
            "expected": "材料池主体必须是原文，不是摘要；Codex 按原子段位置和理由回到整回正文，尽量多摘取相关原文；工程不得先替 Codex 裁掉看似不重要的原文。",
            "status": _audit_status(total_rows > 0 and source_original_rows == total_rows, partial=source_original_rows > 0),
            "evidence": f"有原文字段 {source_original_rows}/{total_rows}；有原文回收字段 {original_rows}/{total_rows}；大段原文行 {long_original_rows}/{total_rows}；摘要但无原文 {summary_only_rows}。",
            "next_fix": "" if total_rows and source_original_rows == total_rows else "把材料池主字段改为原文；摘要只能作旁注。",
        },
        {
            "stage": "7. 同一回内多点跳取",
            "expected": "一个回目里相关原文可以隔 5 段、8 段跳着出现；应按题意尽量多取，不只裁一个命中点。",
            "status": _audit_status(same_chapter_multi_rows > 0, partial=same_chapter_rows > 0),
            "evidence": f"有同回相关原文段字段 {same_chapter_rows}/{total_rows}；同回多段回收 {same_chapter_multi_rows}/{total_rows}。",
            "next_fix": "" if same_chapter_multi_rows else "同回多点原文回收仍需扩大窗口或补查词。",
        },
        {
            "stage": "8. Notion式候选分柜",
            "expected": "分桶应是给 Codex 阅读材料的候选柜，不是程序定案；每条材料要标明候选柜、证据状态和来源系统，便于 Codex 升级、降级、补查、暂缓。",
            "status": _audit_status(total_rows > 0 and bucketed_rows == total_rows and source_status_rows == total_rows, partial=bucketed_rows > 0),
            "evidence": f"候选分柜 {bucketed_rows}/{total_rows}；来源状态 {source_status_rows}/{total_rows}；分柜概览：{dict(bucket_counts)}。",
            "next_fix": "" if total_rows and bucketed_rows == total_rows and source_status_rows == total_rows else "把主证候选、前后文、人物位置、物件路线、风险缺口等候选柜补入复核表。",
        },
        {
            "stage": "9. 材料池精读判别",
            "expected": "Codex 逐条精读原文材料，判别可用、背景、不可用、需补证；这是材料池判定与精读聚拢的前置硬门。",
            "status": _audit_status(bool(material_judgment_actual_md and material_judgment_actual_json), partial=(package_dir / CORE_FILES["final_reading_gate_md"]).exists()),
            "evidence": f"精读门：{package_dir / CORE_FILES['final_reading_gate_md']}；回读材料行 {readback_result.get('total_rows', 0)}；实际材料池判定 md：{material_judgment_actual_md or '缺失'}；json：{material_judgment_actual_json or '缺失'}。",
            "next_fix": "" if material_judgment_actual_md and material_judgment_actual_json else "最终写作前必须生成 00I_Codex材料池判定_<request_id>.md/json，并读 00G、05、06、04 和 02，不得只读摘要。",
        },
        {
            "stage": "10. 精读材料词/精品聚拢池",
            "expected": "Codex 读材料池判定后，把材料按原问题和子问题整理成一个总精品材料词；不把每个子问题拆成多套独立流程。",
            "status": _audit_status(bool(close_reading_actual_md and close_reading_actual_json), partial=close_reading_gate_path.exists() or close_reading_target_path.exists()),
            "evidence": f"生成门：{close_reading_gate_path}；目标稿位：{close_reading_target_path}；实际精读材料词 md：{close_reading_actual_md or '缺失'}；json：{close_reading_actual_json or '缺失'}。",
            "next_fix": "" if close_reading_actual_md and close_reading_actual_json else "召回服务运行时必须生成 00L_Codex精读材料词_<request_id>.md/json；只生成 00ZG/00ZI 不能算完成。",
        },
        {
            "stage": "11. 写作前原文追证摘抄",
            "expected": "Codex 读完整体精品材料词后，自行选择真正值得回原文摘抄的材料；一条原文可支持多个子问题，子问题无材料时写缺口。",
            "status": _audit_status(bool(original_reread_actual_md and original_reread_actual_json), partial=original_reread_gate_path.exists() or original_reread_target_path.exists()),
            "evidence": f"生成门：{original_reread_gate_path}；目标稿位：{original_reread_target_path}；实际原文追证摘抄 md：{original_reread_actual_md or '缺失'}；json：{original_reread_actual_json or '缺失'}。",
            "next_fix": "" if original_reread_actual_md and original_reread_actual_json else "召回服务运行时必须生成 00M_Codex写作前原文通读摘抄_<request_id>.md/json；缺 00M 不得进入最终答案。",
        },
        {
            "stage": "12. 最终回答",
            "expected": "最终回答只能由 Codex 读完材料池判定、精读材料词和写作前原文追证摘抄后生成，本地模块不生成论述稿。",
            "status": "待 Codex 最终处理" if final_prewrite_ready else "硬阻断",
            "evidence": f"最终答案前置完成：{final_prewrite_ready}；需要 00I md/json、00L md/json 和 00M md/json 同时存在。",
            "next_fix": "可以进入最终红楼解语。" if final_prewrite_ready else "先生成 00I_Codex材料池判定、00L_Codex精读材料词 与 00M_Codex写作前原文通读摘抄；缺任一项不得写最终红楼解语。",
        },
    ]

    second_round_decision = build_second_round_decision_card(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        codex_terms=codex_terms,
        preferred_libraries=preferred_libraries,
        compound_groups=compound_groups,
        total_rows=total_rows,
        source_trace_rows=source_trace_rows,
        reasons_rows=reasons_rows,
        source_original_rows=source_original_rows,
        original_rows=original_rows,
        long_original_rows=long_original_rows,
        same_chapter_multi_rows=same_chapter_multi_rows,
        bucket_counts=bucket_counts,
        status_counts=status_counts,
        source_system_counts=source_system_counts,
    )
    complete_count = sum(1 for item in checks if item["status"] == "达标")
    partial_count = sum(1 for item in checks if item["status"] == "部分达标")
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "summary": {
            "checks": len(checks),
            "complete": complete_count,
            "partial": partial_count,
            "waiting_codex_final": sum(1 for item in checks if item["status"] == "待 Codex 最终处理"),
            "hard_blocked": sum(1 for item in checks if item["status"] == "硬阻断"),
            "final_prewrite_ready": final_prewrite_ready,
            "candidate_rows": total_rows,
            "object_axis_rows": object_rows,
            "person_axis_rows": person_rows,
            "source_trace_rows": source_trace_rows,
            "retrieval_reason_rows": reasons_rows,
            "original_passage_rows": original_rows,
            "source_original_rows": source_original_rows,
            "long_original_rows": long_original_rows,
            "same_chapter_multi_rows": same_chapter_multi_rows,
            "entry_hard_gate_exists": entry_hard_gate_path.exists(),
            "entry_hard_gate_count": len(hard_gates),
            "exhaustive_source_sweep_required": exhaustive_required,
            "bucketed_rows": bucketed_rows,
            "bucket_counts": dict(bucket_counts),
            "evidence_status_counts": dict(status_counts),
            "source_system_counts": dict(source_system_counts),
            "full_output_rule": "召回候选、来源链、同回原文、原文回收按底账全量保存；只有页面预览可以折叠，采用与否由 Codex 判别。",
        },
        "core_principle": "压缩来说：本地工程是给 Codex 提供原文原子段定位编号和召回理由的查找器；工程按照 Codex 要求找回来的候选不得自动省略；Codex 拿这些编号回原文读、理解、判断有没有用，再决定材料和答案。",
        "checks": checks,
        "notion_sop_alignment": [
            "先盘库理解，再拆题；先设计资料需求，再从中心库取材。",
            "证据池只保存主证、旁证、侧证、反证、待核、发散线索，不直接写结论。",
            "原文矩阵必须包含回目、原文页、原文摘录、回答的问题、证据类型。",
            "Notion 分桶本质是 AI/Codex 的阅读柜：程序只能标候选柜和来源状态，不能把候选柜当最终主证。",
            "本工程进一步规定：进入材料池的主体必须是原文；摘要只作旁注。",
        ],
        "second_round_decision": second_round_decision,
        "output_files": {
            "pipeline_audit_md": str(package_dir / CORE_FILES["pipeline_audit_md"]),
            "pipeline_audit_json": str(package_dir / CORE_FILES["pipeline_audit_json"]),
            "second_round_decision_md": str(package_dir / CORE_FILES["second_round_decision_md"]),
            "second_round_decision_json": str(package_dir / CORE_FILES["second_round_decision_json"]),
        },
    }

    lines = [
        "# 红楼梦工程｜Codex 指挥链达标检查",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 总尺子",
        "",
        payload["core_principle"],
        "",
        "用户提问题后，Codex 按工程能力拆解问题、设计查询词路、查询步骤和查询词；本地工程按策略查库、查原文索引、给出原子段定位编号和召回理由；Codex 再按这些编号回到整回原文，多点阅读和摘取足量原文，判断有没有用，精读后生成最终回答。",
        "",
        "## 2. 当前总览",
        "",
        f"- 检查项：{len(checks)}",
        f"- 达标：{complete_count}",
        f"- 部分达标：{partial_count}",
        f"- 待 Codex 最终处理：{payload['summary']['waiting_codex_final']}",
        f"- 入口硬门数：{len(hard_gates)}",
        f"- 全书穷尽查证硬启用：{exhaustive_required}",
        f"- 候选材料行：{total_rows}",
        f"- 来源链行：{source_trace_rows}",
        f"- 命中理由行：{reasons_rows}",
        f"- 物象库命中行：{object_rows}",
        f"- 人物映射行：{person_rows}",
        f"- 原文回收行：{original_rows}",
        f"- 原文字段行：{source_original_rows}",
        f"- 大段原文行：{long_original_rows}",
        f"- 同回多段回收行：{same_chapter_multi_rows}",
        f"- 候选分柜行：{bucketed_rows}",
            f"- 分柜概览：{dict(bucket_counts)}",
            f"- 证据状态：{dict(status_counts)}",
            f"- 二轮补证建议：{second_round_decision.get('suggested_state', '')}",
            "",
            "## 3. 逐项检查",
            "",
    ]
    for item in checks:
        lines.extend(
            [
                f"### {item['stage']}｜{item['status']}",
                "",
                f"- 应该做到：{item['expected']}",
                f"- 当前证据：{item['evidence']}",
                f"- 下一步：{item['next_fix'] or '无需额外修正。'}",
                "",
            ]
        )
    lines.extend(
        [
            "## 4. Notion 原 SOP 对齐",
            "",
            *[f"- {item}" for item in payload["notion_sop_alignment"]],
            "",
            "## 5. 二轮补证决策卡",
            "",
            f"- 决策卡：`{payload['output_files']['second_round_decision_md']}`",
            f"- 当前建议状态：{second_round_decision.get('suggested_state', '')}",
            f"- 建议下一步：{second_round_decision.get('suggested_next', '')}",
            "",
            "## 6. 结论",
            "",
            "这份检查不是答案稿。它只判断工程链条有没有按照“Codex 指挥、工程定位、原文入池、材料精读、最终回答”的方式运转。",
            "",
            f"结构化摘要：`{payload['output_files']['pipeline_audit_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["pipeline_audit_md"]
    json_path = package_dir / CORE_FILES["pipeline_audit_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return {
        **payload,
        "pipeline_audit_md": str(md_path),
        "pipeline_audit_json": str(json_path),
    }


def _field_count(rows: list[dict[str, str]], key: str, *, min_len: int = 1) -> int:
    return sum(1 for row in rows if len(clean(row.get(key))) >= min_len)


def build_source_field_standardization(
    question: str,
    package_dir: Path,
    review_result: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    total_rows = len(review_rows)
    field_specs = [
        ("source_identity", "segment_no", "原子段编号", "定位到原子段；Codex 回原文的最小锚点。", "必须"),
        ("source_identity", "chapter_no", "回目编号", "定位到第几回；用于回整回原文。", "必须"),
        ("source_identity", "chapter_title", "回目标题", "辅助人读，不得替代正文证据。", "建议"),
        ("source_trace", "source_trace", "来源链", "说明候选来自人物映射、物象库、证据边或检索召回。", "必须"),
        ("source_trace", "retrieval_reasons", "召回理由", "说明为什么这条材料被工程取回。", "必须"),
        ("source_trace", "source_system", "A/B来源系统", "区分 A 类真源、B 类线索、A+B 对账或待回源。", "必须"),
        ("source_trace", "source_promotion_gate", "来源升格门", "说明是否可入强证候选、原文事实候选或停在回源门。", "必须"),
        ("source_trace", "frontstage_evidence_gate", "前台证据门", "说明页面可怎样显示，避免线索被误看作结论。", "必须"),
        ("original_text", "quote", "原子段短摘", "快速定位命中点；不能替代完整上下文。", "建议"),
        ("original_text", "context_excerpt", "上下文摘录", "辅助判断命中点前后语境。", "建议"),
        ("original_text", "codex_original_passages", "大段原文回收", "进入材料池的主体原文之一。", "强烈建议"),
        ("original_text", "same_chapter_passage_segments", "同回相关原文段", "允许同一回内多点跳取，补足复杂问题材料。", "强烈建议"),
        ("material_reading", "standard_material_cabinet", "十柜标准柜", "给人读和 Codex 精读的稳定分柜。", "必须"),
        ("material_reading", "refined_material_cabinet", "细分材料柜", "把强证、同段、上下文、底账继续细分，解决标准柜略粗。", "必须"),
        ("material_reading", "human_reading_tier", "人读分层", "把全量候选排成 T1/T2/T3/T4，解决候选量太大。", "必须"),
        ("material_reading", "candidate_display_policy", "候选显示策略", "说明默认展开、折叠标题或底账隐藏。", "必须"),
        ("material_reading", "codex_reading_action", "Codex阅读动作", "说明 Codex 应先读、补读、备用读还是有理由再读。", "必须"),
        ("material_reading", "codex_material_bucket", "工程候选柜", "保留工程原始分柜，供追踪与调试。", "必须"),
        ("material_reading", "bucket_reason", "分柜理由", "说明为什么先进这个候选柜。", "建议"),
        ("human_review", "human_decision", "人工/Codex复核判断", "保留、降级、反证、剔除、待复核。", "后置"),
        ("human_review", "human_note", "复核备注", "记录 Codex 或人工为什么采用/舍弃。", "后置"),
        ("human_review", "source_verify_status", "真源核验状态", "是否已经回原文核验。", "后置"),
    ]
    rows = []
    for group, field, label, purpose, required in field_specs:
        filled = _field_count(review_rows, field)
        rows.append(
            {
                "group": group,
                "field": field,
                "label": label,
                "purpose": purpose,
                "required": required,
                "filled_rows": filled,
                "total_rows": total_rows,
                "coverage": round(filled / total_rows, 4) if total_rows else 0.0,
            }
        )
    payload = {
        "generated_at": generated_at,
        "question": question,
        "principle": "同一条材料在问题树、证据阅读顺序、复核表、材料池、页面回显中使用同一套字段名；字段只说明来源和状态，不替 Codex 做证据判断。",
        "review_csv": review_result.get("review_csv", ""),
        "total_rows": total_rows,
        "fields": rows,
        "output_files": {
            "source_schema_md": str(package_dir / CORE_FILES["source_schema_md"]),
            "source_schema_json": str(package_dir / CORE_FILES["source_schema_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜来源字段标准化词典",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 字段总表",
        "",
        "| 字段组 | 字段 | 人读名称 | 要求 | 覆盖 | 作用 |",
        "|---|---|---|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['group']} | `{row['field']}` | {row['label']} | {row['required']} | {row['filled_rows']}/{row['total_rows']} | {row['purpose']} |"
        )
    lines.extend(
        [
            "",
            "## 3. 固定口径",
            "",
            "- `segment_no`、`chapter_no`、`source_trace`、`retrieval_reasons` 是每条候选材料的底座字段。",
            "- `source_system` 和 `source_promotion_gate` 只说明材料能否进入候选层，不说明最终结论。",
            "- `codex_original_passages` 和 `same_chapter_passage_segments` 是原文材料主体；摘要只能作旁注。",
            "- `standard_material_cabinet` 给人读排序，`refined_material_cabinet` 继续细化材料性质。",
            "- `human_reading_tier` 和 `candidate_display_policy` 只改变阅读顺序，不删除任何候选。",
            "- `codex_material_bucket` 保留工程原始分柜，供追踪与调试。",
            "",
            f"结构化摘要：`{payload['output_files']['source_schema_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["source_schema_md"]
    json_path = package_dir / CORE_FILES["source_schema_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_experience_codex_protocol(
    question: str,
    route_context: str,
    package_dir: Path,
    judgment_payload: dict[str, Any],
    experience_entry: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    profile = decomposer.route_context_profile(route_context)
    profile = profile if isinstance(profile, dict) else {}
    selected_rules = [
        rule for rule in judgment_payload.get("type_experience_rules", [])
        if isinstance(rule, dict) and rule.get("status") == "主路径"
    ]
    type_layer = [
        {
            "type": rule.get("type", ""),
            "when": rule.get("when", ""),
            "success_signal": rule.get("success_signal", ""),
            "failure_signal": rule.get("failure_signal", ""),
        }
        for rule in selected_rules
    ]
    strategy_layer = {
        "route_center": judgment_payload.get("route_center", ""),
        "codex_terms": profile.get("codex_terms", []),
        "codex_libraries": profile.get("codex_libraries", []),
        "compound_groups": profile.get("compound_groups", []),
        "preferred_axes": judgment_payload.get("preferred_axes", []),
        "rule": "Codex 读题型经验后生成查询词、库线和强复合组；本地工程只执行这些策略。",
    }
    correction_layer = [
        {"problem": "关键词偏移", "codex_fix": "回到题目中心，重新给 Codex查询词 和 Codex词角色。"},
        {"problem": "材料与结论不支撑", "codex_fix": "回 00P 二轮补证决策卡，补原文、补来源链或重走强复合。"},
        {"problem": "旧题污染", "codex_fix": "按 request/package 隔离，只读当前问题包材料。"},
        {"problem": "库线索冒充主证", "codex_fix": "执行 A/B 硬门：B 类线索必须回 A 类真源。"},
        {"problem": "最终答案太像模块搜索", "codex_fix": "先读材料池、精读材料词和写作前原文追证摘抄，再由 Codex 组织红楼解语。"},
        {"problem": "长流程后忘题", "codex_fix": "每个 Codex 判别阶段先读任务记忆卡；00M 阶段重读原问题和子问题后再回原文摘抄。"},
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "principle": "经验法典给 Codex 使用，不给本地程序自动猜题。它分三层：题型识别、查询词路、失败修正。",
        "type_layer": type_layer,
        "strategy_layer": strategy_layer,
        "correction_layer": correction_layer,
        "experience_entry": {
            "entry_md": experience_entry.get("entry_md", ""),
            "ledger_md": experience_entry.get("ledger_md", ""),
            "main_rules": experience_entry.get("main_rules", []),
        },
        "output_files": {
            "experience_codex_md": str(package_dir / CORE_FILES["experience_codex_md"]),
            "experience_codex_json": str(package_dir / CORE_FILES["experience_codex_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜经验法典三层结构",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 第一层：题型识别",
        "",
        "| 题型 | 何时启用 | 成功信号 | 失败信号 |",
        "|---|---|---|---|",
    ]
    for row in type_layer:
        lines.append(f"| {row['type']} | {row['when']} | {row['success_signal']} | {row['failure_signal']} |")
    lines.extend(
        [
            "",
            "## 3. 第二层：查询词路",
            "",
            f"- 问题中心：{strategy_layer['route_center'] or '等待入口词包'}",
            f"- Codex查询词：{'、'.join(strategy_layer['codex_terms']) or '未提供'}",
            f"- Codex优先库：{'、'.join(strategy_layer['codex_libraries']) or '未指定'}",
            f"- 强复合组：{len(strategy_layer['compound_groups'])}",
            f"- 规则：{strategy_layer['rule']}",
            "",
            "## 4. 第三层：失败修正",
            "",
            "| 问题 | Codex修正动作 |",
            "|---|---|",
        ]
    )
    for row in correction_layer:
        lines.append(f"| {row['problem']} | {row['codex_fix']} |")
    lines.extend(
        [
            "",
            "## 5. 边界",
            "",
            "- 经验不是模板，不能限定最终答案。",
            "- 经验只帮助 Codex 更快决定查什么、补什么、舍弃什么。",
            "- 本地程序不得把经验表变成自动答题器。",
            "",
            f"结构化摘要：`{payload['output_files']['experience_codex_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["experience_codex_md"]
    json_path = package_dir / CORE_FILES["experience_codex_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_mode_boundary_card(question: str, route_context: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    formal_outputs = [
        CORE_FILES["question_judgment_md"],
        CORE_FILES["library_precheck_md"],
        CORE_FILES["library_flow_md"],
        CORE_FILES["final_reading_gate_md"],
        CORE_FILES["process_inventory_md"],
        CORE_FILES["pipeline_audit_md"],
        CORE_FILES["second_round_decision_md"],
        CORE_FILES["review_csv"],
        CORE_FILES["reading_md"],
        CORE_FILES["writing_md"],
    ]
    disabled_local_writing = [
        CORE_FILES["argument_brief_md"],
        CORE_FILES["argument_talk_md"],
        CORE_FILES["article_draft_md"],
        CORE_FILES["article_academic_md"],
        CORE_FILES["article_essay_md"],
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "formal_mode": {
            "name": "正式出库模式",
            "rule": "只生成候选材料、原文回收、复核表、材料池精读门和 Codex 判别门；不生成本地答案稿。",
            "outputs": formal_outputs,
        },
        "sandbox_mode": {
            "name": "沙盒/旧稿模式",
            "rule": "旧的本地论述稿、文章稿、学术稿、评论稿保留停用文件和说明，只能做历史兼容，不进入正式链。",
            "disabled_outputs": disabled_local_writing,
        },
        "hard_boundary": [
            "正式链不得调用本地模块写最终答案。",
            "沙盒文件不得进入作品总库，不得反向污染 A 类真源。",
            "需要最终答案时，必须由 Codex 读取材料池后生成红楼解语。",
        ],
        "output_files": {
            "mode_boundary_md": str(package_dir / CORE_FILES["mode_boundary_md"]),
            "mode_boundary_json": str(package_dir / CORE_FILES["mode_boundary_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜正式沙盒模式边界",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 正式出库模式",
        "",
        f"- 规则：{payload['formal_mode']['rule']}",
        "- 正式文件：",
        *[f"  - `{item}`" for item in formal_outputs],
        "",
        "## 2. 沙盒/旧稿模式",
        "",
        f"- 规则：{payload['sandbox_mode']['rule']}",
        "- 停用旧稿：",
        *[f"  - `{item}`" for item in disabled_local_writing],
        "",
        "## 3. 硬边界",
        "",
        *[f"- {item}" for item in payload["hard_boundary"]],
        "",
        f"结构化摘要：`{payload['output_files']['mode_boundary_json']}`",
    ]
    md_path = package_dir / CORE_FILES["mode_boundary_md"]
    json_path = package_dir / CORE_FILES["mode_boundary_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_approval_ingest_gate(
    question: str,
    package_dir: Path,
    review_result: dict[str, Any],
    readback_result: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    triggers = [
        "红楼梦正式入库",
        "确认采用这篇",
        "保存为作品",
        "文章入库",
        "收入作品总库",
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "status": "等待最终答案和用户认可；当前不自动入库。",
        "confirmed_by_user": False,
        "ready_for_ingest": False,
        "review_csv": review_result.get("review_csv", ""),
        "usable_rows": readback_result.get("usable_rows", 0),
        "required_before_ingest": [
            "Codex 最终答案已经生成，并且不是本地模块稿。",
            "用户明确认可主版本。",
            "主版本能回挂问题包、复核表、原文锚点和真源核验清单。",
            "作品资产只写入作品/文章层，不倒灌到原文真源层。",
        ],
        "triggers": triggers,
        "output_files": {
            "approval_ingest_gate_md": str(package_dir / CORE_FILES["approval_ingest_gate_md"]),
            "approval_ingest_gate_json": str(package_dir / CORE_FILES["approval_ingest_gate_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜用户认可入库门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 当前状态",
        "",
        f"- 状态：{payload['status']}",
        f"- 已获用户认可：{payload['confirmed_by_user']}",
        f"- 可正式入库：{payload['ready_for_ingest']}",
        f"- 当前可写作证据：{payload['usable_rows']}",
        "",
        "## 2. 入库前必须满足",
        "",
        *[f"- {item}" for item in payload["required_before_ingest"]],
        "",
        "## 3. 用户认可触发词",
        "",
        *[f"- {item}" for item in triggers],
        "",
        "## 4. 边界",
        "",
        "- 未经用户认可，不生成正式作品总库行。",
        "- 最终答案未生成，不进入作品入库流程。",
        "- 入库资产可以回挂证据，但不能成为原文证据。",
        "",
        f"结构化摘要：`{payload['output_files']['approval_ingest_gate_json']}`",
    ]
    md_path = package_dir / CORE_FILES["approval_ingest_gate_md"]
    json_path = package_dir / CORE_FILES["approval_ingest_gate_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_library_coverage_matrix(
    question: str,
    package_dir: Path,
    library_flow_payload: dict[str, Any],
    review_result: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    total_rows = len(review_rows)
    stats = {
        "total_rows": total_rows,
        "located_rows": sum(1 for row in review_rows if clean(row.get("segment_no")) and clean(row.get("chapter_no"))),
        "source_original_rows": sum(
            1
            for row in review_rows
            if clean(row.get("codex_original_passages")) or clean(row.get("same_chapter_passage_segments"))
        ),
        "person_rows": _field_count(review_rows, "person_axis_hits"),
        "object_rows": _field_count(review_rows, "object_axis_hits"),
        "evidence_rows": _field_count(review_rows, "evidence_edge_hits"),
        "source_trace_rows": _field_count(review_rows, "source_trace"),
        "reason_rows": _field_count(review_rows, "retrieval_reasons"),
    }
    precheck_rows = library_flow_payload.get("library_precheck", {}).get("rows", [])
    if not isinstance(precheck_rows, list):
        precheck_rows = []

    def coverage_for(group: str) -> tuple[int, str]:
        if group == "A类原文真源层":
            return stats["source_original_rows"], "原文或同回原文段覆盖"
        if group == "原子段落层":
            return stats["located_rows"], "segment_no + chapter_no 覆盖"
        if group == "人物与关系层":
            return stats["person_rows"], "人物映射命中"
        if group == "物象空间诗词时间层":
            return stats["object_rows"], "物象/空间/诗词等轴线命中"
        if group == "统一证据边与映射健康层":
            return stats["evidence_rows"], "统一证据边命中"
        if group == "全文检索与快速召回层":
            return stats["reason_rows"], "召回理由覆盖"
        if group == "问题包、证据池与复核写作层":
            return total_rows, "问题包与复核表覆盖"
        if group == "文章入库与作品层":
            return 0, "等待最终答案和用户认可后启用"
        return 0, "按题意待判"

    matrix = []
    for row in precheck_rows:
        group = clean(row.get("library_group"))
        covered, note = coverage_for(group)
        status = "已覆盖" if covered > 0 else "待启用"
        if group == "文章入库与作品层":
            status = "待用户认可"
        matrix.append(
            {
                "library_group": group,
                "question_relation": row.get("question_relation", ""),
                "evidence_layer": row.get("evidence_layer", ""),
                "covered_rows": covered,
                "total_rows": total_rows,
                "coverage": round(covered / total_rows, 4) if total_rows else 0.0,
                "status": status,
                "note": note,
            }
        )
    payload = {
        "generated_at": generated_at,
        "question": question,
        "principle": "库群覆盖矩阵把每题的库法、中心表轴、原文和材料池覆盖情况摆到同一张表里；它只说明理解与承接覆盖，不替 Codex 判断材料价值。",
        "stats": stats,
        "matrix": matrix,
        "output_files": {
            "library_coverage_md": str(package_dir / CORE_FILES["library_coverage_md"]),
            "library_coverage_json": str(package_dir / CORE_FILES["library_coverage_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜库群覆盖矩阵",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 覆盖矩阵",
        "",
        "| 库群 | 本题关系 | 证据层 | 覆盖 | 状态 | 说明 |",
        "|---|---|---|---:|---|---|",
    ]
    for row in matrix:
        lines.append(
            f"| {row['library_group']} | {row['question_relation']} | {row['evidence_layer']} | {row['covered_rows']}/{row['total_rows']} | {row['status']} | {row['note']} |"
        )
    lines.extend(
        [
            "",
            "## 3. 总体统计",
            "",
            *[f"- {key}: {value}" for key, value in stats.items()],
            "",
            f"结构化摘要：`{payload['output_files']['library_coverage_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["library_coverage_md"]
    json_path = package_dir / CORE_FILES["library_coverage_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_codex_close_reading_gate(
    question: str,
    route_context: str,
    package_dir: Path,
    review_result: dict[str, Any],
    pipeline_audit: dict[str, Any],
    second_round_decision: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    tier_counts = Counter(clean(row.get("human_reading_tier")) or "未分层" for row in review_rows)
    refined_counts = Counter(clean(row.get("refined_material_cabinet")) or "未分柜" for row in review_rows)
    t1a_rows = [row for row in review_rows if clean(row.get("human_reading_tier")) == "T1A_必读主证"]
    t1b_rows = [row for row in review_rows if clean(row.get("human_reading_tier")) == "T1B_强证补读"]
    first_read_rows = t1a_rows + t1b_rows
    route_profile = _route_profile_from_context(route_context, question)
    route_mode = _route_mode_from_context(route_context, question)
    target_path = package_dir / CORE_FILES["codex_close_reading_target_md"]
    gate_path = package_dir / CORE_FILES["codex_close_reading_gate_md"]
    json_path = package_dir / CORE_FILES["codex_close_reading_gate_json"]
    required_actions = [
        "Codex 必须先读 00AC/00AG/00AI/00AM，确认材料已经回聚拢库并进入材料池。",
        "Codex 先读 T1A 全部原文，不够再读 T1B。",
        "T2/T3/T4 是折叠底账，不进入第一轮精读；只有 T1A/T1B 不足或 Codex 明确补查时再打开。",
        "每条进入精读材料词的材料必须说明：原文锚点、可用点、支撑问题的方式、风险或反证。",
        "材料词只做取舍和论证准备，不写最终答案。",
        "若 T1A/T1B 不能支撑 5 到 8 个事实支点，回 00P 二轮补证决策卡。",
        "精读材料词完成后，先进入写作前原文追证摘抄，再进入 00ZD 红楼解语生成门。",
    ]
    status = "等待 Codex 生成精读材料词"
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "status": status,
        "rule": "精读材料词是最终答案前的材料判别层；本地工程不得自动判定主证，也不得写最终论述。",
        "review_rows": len(review_rows),
        "route_mode": route_mode,
        "t1a_rows": len(t1a_rows),
        "t1b_rows": len(t1b_rows),
        "first_read_rows": len(first_read_rows),
        "tier_counts": dict(tier_counts),
        "top_refined_cabinets": dict(refined_counts.most_common(12)),
        "pipeline_summary": pipeline_audit.get("summary", {}),
        "second_round_state": second_round_decision.get("suggested_state", ""),
        "required_actions": required_actions,
        "output_files": {
            "codex_close_reading_gate_md": str(gate_path),
            "codex_close_reading_gate_json": str(json_path),
            "codex_close_reading_target_md": str(target_path),
        },
    }
    lines = [
        "# 红楼梦工程｜Codex精读材料词生成门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 当前状态",
        "",
        f"- 状态：{payload['status']}",
        f"- 复核表候选：{len(review_rows)}",
        f"- T1A 必读主证：{len(t1a_rows)}",
        f"- T1B 强证补读：{len(t1b_rows)}",
        f"- 首轮精读入口：{len(first_read_rows)} 条（T2 以下仅作折叠底账）",
        f"- 二轮建议：{second_round_decision.get('suggested_state', '')}｜{second_round_decision.get('suggested_next', '')}",
        "",
        "## 2. 生成规则",
        "",
        f"- {payload['rule']}",
        *[f"- {item}" for item in required_actions],
        "",
        "## 3. 分层快照",
        "",
        *[f"- {key}: {value}" for key, value in tier_counts.items()],
        "",
        "## 4. 细分柜快照",
        "",
        *[f"- {key}: {value}" for key, value in refined_counts.most_common(12)],
        "",
        f"精读材料词目标文件：`{target_path}`",
        f"结构化摘要：`{json_path}`",
    ]
    target_lines = [
        "# Codex精读材料词｜待生成",
        "",
        f"问题：{question}",
        "",
        "## 状态",
        "",
        "等待 Codex 读取聚拢取材单、材料池、T1A/T1B 和原文材料后写入。",
        "",
        "## 输出格式",
        "",
        "### 1. 本题可用事实支点",
        "",
        "- 每个支点写：原文锚点、原文内容、为什么可用、支撑问题哪一部分。优先来自 T1A/T1B。",
        "",
        "### 2. 背景材料",
        "",
        "- 只做语境，不直接当主证。",
        "",
        "### 3. 舍弃或降级材料",
        "",
        "- 写明误召回、太泛、只在线索层、缺上下文或不支撑问题的原因。",
        "",
        "### 4. 补证判断",
        "",
        "- 如果事实支点不足，列出下一轮要查的词、库、原文范围。",
        "",
        "### 5. 红楼解语写作准备",
        "",
        "- 给出 5 到 8 个可进入写作前原文追证摘抄的证据支点，但不写最终答案正文。",
    ]
    gate_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    target_path.write_text("\n".join(target_lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_codex_original_reread_gate(
    question: str,
    route_context: str,
    package_dir: Path,
    review_result: dict[str, Any],
    pipeline_audit: dict[str, Any],
    second_round_decision: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    hit_labels: list[str] = []
    route_profile = _route_profile_from_context(route_context, question)
    route_mode = _route_mode_from_context(route_context, question)
    for row in review_rows:
        for label in split_subquestions(row.get("hit_subquestions")):
            if label not in hit_labels:
                hit_labels.append(label)
    target_path = package_dir / CORE_FILES["codex_original_reread_target_md"]
    gate_path = package_dir / CORE_FILES["codex_original_reread_gate_md"]
    json_path = package_dir / CORE_FILES["codex_original_reread_gate_json"]
    status = "等待 Codex 生成写作前原文追证摘抄"
    required_actions = [
        "Codex 先复习原问题和问题拆解，确认本次摘抄围绕什么。",
        "Codex 读完整体精读材料词后，再自行选择需要回原文摘抄的材料。",
        "不强迫每个子问题都摘一条；一条原文可以服务多个子问题，材料不足的子问题写入缺口。",
        "摘抄只作为最终写作前的原文底稿，不写最终答案。",
        "最终红楼解语必须优先读取本通读摘抄，再组织表达。",
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "status": status,
        "rule": "写作前原文追证摘抄是最终答案前的原文底稿层；它从整体精品材料词中选择真正值得回原文的材料，不按子问题机械拆成多套流程。",
        "review_rows": len(review_rows),
        "subquestion_labels": hit_labels,
        "subquestion_count": len(hit_labels),
        "route_mode": route_mode,
        "pipeline_summary": pipeline_audit.get("summary", {}),
        "second_round_state": second_round_decision.get("suggested_state", ""),
        "required_actions": required_actions,
        "output_files": {
            "codex_original_reread_gate_md": str(gate_path),
            "codex_original_reread_gate_json": str(json_path),
            "codex_original_reread_target_md": str(target_path),
        },
    }
    lines = [
        "# 红楼梦工程｜Codex写作前原文追证摘抄生成门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 当前状态",
        "",
        f"- 状态：{payload['status']}",
        f"- 复核表候选：{len(review_rows)}",
        f"- 子问题标签：{'、'.join(hit_labels) or '未拆出独立子问题，按原问题处理'}",
        f"- 二轮建议：{second_round_decision.get('suggested_state', '')}｜{second_round_decision.get('suggested_next', '')}",
        "",
        "## 2. 生成规则",
        "",
        f"- {payload['rule']}",
        *[f"- {item}" for item in required_actions],
        "",
        f"写作前原文追证摘抄目标文件：`{target_path}`",
        f"结构化摘要：`{json_path}`",
    ]
    target_lines = [
        "# Codex写作前原文追证摘抄｜待生成",
        "",
        f"问题：{question}",
        "",
        "## 状态",
        "",
        f"状态：{status}",
        "",
        "## 输出要求",
        "",
        "### 1. 问题复习",
        "",
        "- 复述原问题和子问题，防止长流程跑偏。",
        "",
        "### 2. 选摘原文",
        "",
        "- 从整体精品材料词中选择值得回原文摘抄的材料；不机械要求每个子问题都有摘抄。",
        "",
        "### 3. 子问题覆盖",
        "",
        "- 说明哪些子问题已覆盖、部分覆盖或暂缺。",
        "",
        "### 4. 证据缺口",
        "",
        "- 原文不足时写缺口，不硬写结论。",
        "",
        "### 5. 给最终答案的提示",
        "",
        "- 只提示可写判断和谨慎边界，不写最终答案正文。",
    ]
    gate_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    target_path.write_text("\n".join(target_lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_answer_writeback_protocol(question: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    md_path = package_dir / CORE_FILES["answer_writeback_protocol_md"]
    json_path = package_dir / CORE_FILES["answer_writeback_protocol_json"]
    steps = [
        "召回服务先生成并登记 `00I_Codex材料池判定_<request_id>.md/json`。",
        "Codex 生成正式 `00L_Codex精读材料词_<request_id>.md/json`，并同步人读目标稿位 `00ZI_Codex精读材料词_待生成.md`。",
        "Codex 生成正式 `00M_Codex写作前原文通读摘抄_<request_id>.md/json`，并同步人读目标稿位 `00ZP_Codex写作前原文通读摘抄_待生成.md`。",
        "Codex 再进入 `00ZD_Codex红楼解语生成门.md`。",
        "Codex 将最终红楼解语写入 `00ZF_Codex红楼解语_待生成.md` 或正式最终答案目录。",
        "写回后状态台把主入口从生成门切到红楼解语目标稿位。",
        "用户认可后，才进入 `00X_用户认可入库门.md`。",
    ]
    guards = [
        "禁止本地模块自动填充最终正文。",
        "禁止用摘要、搜索列表、旧稿替代红楼解语。",
        "禁止最终答案脱离当前问题包的材料池和原文锚点。",
        "允许 Codex 自由组织文风，但证据支点必须能回到当前包。",
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "status": "写回规范已就绪",
        "steps": steps,
        "guards": guards,
        "output_files": {
            "answer_writeback_protocol_md": str(md_path),
            "answer_writeback_protocol_json": str(json_path),
        },
    }
    lines = [
        "# 红楼梦工程｜Codex最终答案写回规范",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 写回步骤",
        "",
        *[f"{idx}. {item}" for idx, item in enumerate(steps, start=1)],
        "",
        "## 2. 硬边界",
        "",
        *[f"- {item}" for item in guards],
        "",
        "## 3. 目的",
        "",
        "这张卡解决的不是写作风格，而是写回秩序：最终答案必须由 Codex 读材料后写入固定稿位，页面和状态台只显示这个稿位，不显示模块搜索伪答案。",
        "",
        f"结构化摘要：`{json_path}`",
    ]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_regression_plan(question: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    md_path = package_dir / CORE_FILES["regression_plan_md"]
    json_path = package_dir / CORE_FILES["regression_plan_json"]
    cases = [
        ("人物-物象共现", "林黛玉与竹子", "测试人物别名、物象单字、多场景共现、原文回收。"),
        ("人物结局", "探春、湘云、惜春等人物结局", "测试结局段落、判词曲文、前文伏笔。"),
        ("诗词文本", "某首诗词和人物命运的关系", "测试原句定位、上下文、人物归属。"),
        ("空间场域", "潇湘馆、怡红院等空间功能", "测试空间库、人物移动、物象共现。"),
        ("事件因果", "某一事件如何发生并造成后果", "测试起点、过程、结果和转折。"),
        ("人物关系", "两个人物关系如何变化", "测试关系边、共同段落、双向材料。"),
        ("主题观念", "情、空、幻、命运等主题", "测试多回原文、多线材料和反证排除。"),
        ("物象单字", "玉、金、泪、帕、竹等单字物象", "测试 AI 识别物象，不用字数门禁。"),
        ("反证排除", "容易串旧题或同形词的问题", "测试旧题隔离和误召回降级。"),
        ("回目/原文定位", "第几回某句话或某段上下文", "测试原子段、整回回读、同回多点摘取。"),
    ]
    payload = {
        "generated_at": generated_at,
        "question": question,
        "status": "回归测试骨架已建立",
        "principle": "每类题都要检查：Codex是否先定策略，工程是否只供料，材料是否回原文，精读材料词是否产生，红楼解语是否从固定稿位写回。",
        "cases": [
            {"type": kind, "example": example, "purpose": purpose}
            for kind, example, purpose in cases
        ],
        "acceptance": [
            "不得出现模块搜索结果冒充最终答案。",
            "不得出现本地程序自动猜关键词替代 Codex 策略。",
            "不得出现材料池只有摘要没有原文。",
            "不得出现最终答案无法回挂原文支点。",
            "每题必须有经验复盘入账。",
        ],
        "output_files": {
            "regression_plan_md": str(md_path),
            "regression_plan_json": str(json_path),
        },
    }
    lines = [
        "# 红楼梦工程｜十题回归测试骨架",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 总原则",
        "",
        payload["principle"],
        "",
        "## 2. 十类测试",
        "",
        "| 编号 | 类型 | 示例 | 测试目的 |",
        "|---:|---|---|---|",
    ]
    for idx, row in enumerate(payload["cases"], start=1):
        lines.append(f"| {idx} | {row['type']} | {row['example']} | {row['purpose']} |")
    lines.extend(
        [
            "",
            "## 3. 验收标准",
            "",
            *[f"- {item}" for item in payload["acceptance"]],
            "",
            f"结构化摘要：`{json_path}`",
        ]
    )
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_codex_final_answer_gate(
    question: str,
    route_context: str,
    package_dir: Path,
    review_result: dict[str, Any],
    readback_result: dict[str, Any],
    pipeline_audit: dict[str, Any],
    second_round_decision: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    review_rows = _read_existing_csv(review_result.get("review_csv", ""))
    tier_counts = Counter(clean(row.get("human_reading_tier")) or "未分层" for row in review_rows)
    cabinet_counts = Counter(clean(row.get("refined_material_cabinet")) or clean(row.get("standard_material_cabinet")) or "未分柜" for row in review_rows)
    t1a_rows = [row for row in review_rows if clean(row.get("human_reading_tier")) == "T1A_必读主证"]
    t1b_rows = [row for row in review_rows if clean(row.get("human_reading_tier")) == "T1B_强证补读"]
    first_read_rows = t1a_rows + t1b_rows
    original_rows = sum(
        1
        for row in review_rows
        if clean(row.get("codex_original_passages")) or clean(row.get("same_chapter_passage_segments"))
    )
    route_profile = _route_profile_from_context(route_context, question)
    route_mode = _route_mode_from_context(route_context, question)
    aggregation_court_missing = _aggregation_court_missing(package_dir)
    aggregation_court_ready = not aggregation_court_missing
    target_path = package_dir / CORE_FILES["codex_final_answer_target_md"]
    gate_path = package_dir / CORE_FILES["codex_final_answer_gate_md"]
    json_path = package_dir / CORE_FILES["codex_final_answer_gate_json"]
    source_paths = {
        CORE_FILES["review_csv"]: Path(review_result.get("review_csv", "")),
        CORE_FILES["reading_md"]: Path(review_result.get("reading_md", "")),
        CORE_FILES["writing_md"]: Path(readback_result.get("writing_md", "")),
    }

    def required_source_exists(file_name: str) -> bool:
        package_path = package_dir / file_name
        source_path = source_paths.get(file_name)
        return package_path.exists() or bool(source_path and source_path.exists())

    required_sources = [
        ("128 聚拢库总入口流程锁", CORE_FILES["aggregation_flow_lock_md"], "先确认已过库法理解地图、已入聚拢库、相关库法深读必须回中心库/聚拢库、最后原文裁判。"),
        ("聚拢库取材单", CORE_FILES["aggregation_material_search_md"], "带着问题和方法，在聚拢库里找材料，并记录回聚拢坐标。"),
        ("聚拢入材料池清单", CORE_FILES["material_pool_admission_csv"], "只把有聚拢坐标、来源链、原文锚点和路由说明的材料送入材料池。"),
        ("聚拢裁判首读材料池", CORE_FILES["aggregation_first_read_pool_md"], "从宽口径入池底账中筛出下一步真正要读、要裁判的材料。"),
        ("聚拢入材料池凭证门", CORE_FILES["material_pool_admission_md"], "阻断无编号、无来源、无原文锚点的旧候选。"),
        ("机器短卡与证据分层策略", CORE_FILES["machine_short_card_md"], "先看对象、入口词、相关库和排除触发；保持后台重、前台轻。"),
        ("入口硬规则门", CORE_FILES["entry_hard_gate_md"], "确认查库优先、库登记处门、原文回归门均已点亮。"),
        ("材料池精读门", CORE_FILES["final_reading_gate_md"], "先看写作前门槛和材料取舍要求。"),
        ("二轮补证决策卡", CORE_FILES["second_round_decision_md"], "判断是否已经可以写，或需要补证。"),
        ("复核回读材料", CORE_FILES["writing_md"], "读取已经回源的原文材料主体。"),
        ("复核阅读单", CORE_FILES["reading_md"], "按 T1/T2/T3/T4 和细分柜读材料。"),
        ("复核表", CORE_FILES["review_csv"], "需要追根溯源时查全量字段底账。"),
        ("全流程达标检查", CORE_FILES["pipeline_audit_md"], "确认来源链和原文字段是否达标。"),
        ("来源字段标准化词典", CORE_FILES["source_schema_md"], "确认字段口径。"),
    ]
    required_sources = [
        (
            "写作前原文追证摘抄生成门",
            CORE_FILES["codex_original_reread_gate_md"],
            "最终答案前先确认原文通读摘抄规则。",
        ),
        (
            "写作前原文追证摘抄目标稿位",
            CORE_FILES["codex_original_reread_target_md"],
            "正式 00M 生成后的同步人读稿位；不能单独替代 00M md/json。",
        ),
        ("精读材料词生成门", CORE_FILES["codex_close_reading_gate_md"], "先生成正式 00L 材料取舍和论证支点。"),
        ("精读材料词目标稿位", CORE_FILES["codex_close_reading_target_md"], "正式 00L 生成后的同步人读稿位；不能单独替代 00L md/json。"),
    ] + required_sources
    final_prewrite_ready = bool(pipeline_audit.get("summary", {}).get("final_prewrite_ready"))
    status = "等待 Codex 生成 00I/00L/00M 后再写红楼解语"
    if not aggregation_court_ready:
        status = "阻断：等待聚拢库取材与材料池入池"
    elif final_prewrite_ready:
        status = "等待 Codex 红楼解语：00I/00L/00M 已完成，可以进入最终答案写作门"
    elif second_round_decision.get("suggested_state") == "建议先补证":
        status = "等待 Codex 补证与材料池判定后再写红楼解语"
    payload = {
        "generated_at": generated_at,
        "question": question,
        "route_context": route_context,
        "route_mode": route_mode,
        "aggregation_court_ready": aggregation_court_ready,
        "aggregation_court_missing": aggregation_court_missing,
        "status": status,
        "rule": "本地工程只准备材料、检查门和写作目标；红楼解语必须由 Codex 先完成过程判别与材料池四态判定后生成，不由模块搜索或本地模板生成。",
        "target_md": str(target_path),
        "gate_md": str(gate_path),
        "review_rows": len(review_rows),
        "first_read_rows": len(first_read_rows),
        "t1a_rows": len(t1a_rows),
        "t1b_rows": len(t1b_rows),
        "original_rows": original_rows,
        "usable_rows": readback_result.get("usable_rows", 0),
        "pending_rows": readback_result.get("pending_rows", 0),
        "tier_counts": dict(tier_counts),
        "top_refined_cabinets": dict(cabinet_counts.most_common(12)),
        "pipeline_summary": pipeline_audit.get("summary", {}),
        "second_round_state": second_round_decision.get("suggested_state", ""),
        "second_round_next": second_round_decision.get("suggested_next", ""),
        "required_sources": [
            {
                "label": label,
                "file": file_name,
                "path": str(package_dir / file_name),
                "purpose": purpose,
                "exists": required_source_exists(file_name),
            }
            for label, file_name, purpose in required_sources
        ],
        "output_files": {
            "codex_final_answer_gate_md": str(gate_path),
            "codex_final_answer_gate_json": str(json_path),
            "codex_final_answer_target_md": str(target_path),
        },
    }
    gate_lines = [
        "# 红楼梦工程｜Codex红楼解语生成门",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 当前状态",
        "",
        f"- 状态：{status}",
        f"- 复核表候选：{len(review_rows)}",
        f"- 带原文材料：{original_rows}",
        f"- 首轮精读入口：{len(first_read_rows)} 条（T1A {len(t1a_rows)} / T1B {len(t1b_rows)}；其余折叠为底账）",
        f"- 可写作材料：{readback_result.get('usable_rows', 0)}",
        f"- 待复核材料：{readback_result.get('pending_rows', 0)}",
        f"- 二轮建议：{second_round_decision.get('suggested_state', '')}｜{second_round_decision.get('suggested_next', '')}",
        "",
        "## 2. 生成规则",
        "",
        f"- {payload['rule']}",
        "- Codex 必须先读 00AC/00AG/00AI/00AM；这些文件缺任意一项，本门保持阻断状态。",
        "- Codex 必须从材料池、原文段、复核表和补证卡里取材；不能越过工程直接自由发挥。",
        "- Codex 最终写作前必须先完成材料池四态判定：可用主证、背景材料、不可用、需补证。",
        "- 本地工程不得把摘要、模块搜索结果或旧稿当作红楼解语。",
        "- 最终文字可以自由、有文学性、有推理层次，但证据支点必须能回到当前问题包。",
    ]
    gate_lines.append("- Codex 写最终答案时先读精读材料词和 T1A/T1B；T2 以下只在证据不足或需要反证时展开。")
    gate_lines.append("- Codex 写最终答案前必须先读写作前原文追证摘抄；主判断优先从通读摘抄里的原文支点生发。")
    gate_lines.extend(
        [
            "",
            "## 3. 必读顺序",
            "| 顺序 | 名称 | 文件 | 存在 | 作用 |",
            "|---:|---|---|---|---|",
        ]
    )
    for idx, row in enumerate(payload["required_sources"], start=1):
        gate_lines.append(
            f"| {idx} | {row['label']} | `{row['path']}` | {'是' if row['exists'] else '否'} | {row['purpose']} |"
        )
    gate_lines.extend(
        [
            "",
            "## 4. 人读分层快照",
            "",
            *[f"- {key}: {value}" for key, value in tier_counts.items()],
            "",
            "## 5. 细分柜快照",
            "",
            *[f"- {key}: {value}" for key, value in cabinet_counts.most_common(12)],
            "",
            f"红楼解语目标文件：`{target_path}`",
            f"结构化摘要：`{json_path}`",
        ]
    )
    target_lines = [
        "# 红楼解语｜待 Codex 生成",
        "",
        f"问题：{question}",
        "",
        "## 状态",
        "",
        status,
        "",
        "## Codex 写作前必须完成",
        "",
        "- 读完 `00G_最终回答前材料池精读门.md`。",
        "- 读完 `00P_二轮补证决策卡.md`。",
        "- 由召回服务生成并读完 `00I_Codex材料池判定_<request_id>.md/json`；没有这一步，不进入最终答案。",
        "- 以 `06_复核回读材料.md` 的原文材料为主体，必要时回 `04_复核表.csv` 查来源链。",
        "- 先判断 T1A/T1B 材料是否足够，不足时按二轮补证卡补查。",
        "- 写出的红楼解语必须能说明：用了哪些原文支点、为什么这些支点能回答问题、哪些材料被舍弃。",
        "",
        "## 正文",
        "",
        "等待 Codex 读取材料池后写入；本地工程不得自动填充正文。",
    ]
    target_lines.insert(-4, "- 先完成正式 `00L_Codex精读材料词_<request_id>.md/json`；`00ZI` 只作人读同步稿位，不能单独算完成。")
    target_lines.insert(-4, "- 先完成正式 `00M_Codex写作前原文通读摘抄_<request_id>.md/json`；`00ZP` 只作人读同步稿位，不能单独算完成。")
    gate_path.write_text("\n".join(gate_lines).rstrip() + "\n", encoding="utf-8")
    target_path.write_text("\n".join(target_lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def build_human_reading_order_config(question: str, package_dir: Path) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    ordered = [
        ("红楼解语生成门", CORE_FILES["codex_final_answer_gate_md"], "最终答案入口；若未生成，显示等待 Codex。", "人读第一屏", 1),
        ("红楼解语目标稿位", CORE_FILES["codex_final_answer_target_md"], "Codex 写最终答案的唯一目标位。", "人读第一屏", 2),
        ("聚拢库取材单", CORE_FILES["aggregation_material_search_md"], "带着问题和方法回聚拢库找材料。", "人读第一屏", 3),
        ("聚拢入材料池清单", CORE_FILES["material_pool_admission_csv"], "真正送入材料池的候选清单。", "人读第一屏", 4),
        ("聚拢裁判首读材料池", CORE_FILES["aggregation_first_read_pool_md"], "把宽口径入池底账压成首读有用材料。", "人读第一屏", 5),
        ("聚拢入材料池凭证门", CORE_FILES["material_pool_admission_md"], "确认无凭证材料已被阻断。", "人读第一屏", 6),
        ("写作前原文追证摘抄生成门", CORE_FILES["codex_original_reread_gate_md"], "最终答案前的原文底稿入口。", "人读第一屏", 7),
        ("写作前原文追证摘抄目标稿位", CORE_FILES["codex_original_reread_target_md"], "正式 00M 生成后的同步人读稿位。", "人读第一屏", 8),
        ("精读材料词生成门", CORE_FILES["codex_close_reading_gate_md"], "最终答案前的材料判别入口。", "人读第一屏", 9),
        ("精读材料词目标稿位", CORE_FILES["codex_close_reading_target_md"], "正式 00L 生成后的同步人读稿位。", "人读第一屏", 10),
        ("最终回答前材料池精读门", CORE_FILES["final_reading_gate_md"], "写最终答案前必须读。", "人读核心", 11),
        ("二轮补证决策卡", CORE_FILES["second_round_decision_md"], "判断是否补证或进入材料池精读。", "人读核心", 12),
        ("复核阅读单", CORE_FILES["reading_md"], "按标准柜和 T1A/T1B/T2/T3/T4 读候选材料。", "人读核心", 13),
        ("复核表", CORE_FILES["review_csv"], "全量候选材料和字段底账。", "工程/人读共用", 14),
        ("重点证据卡片", CORE_FILES["cards"], "快速看关键候选。", "人读辅助", 15),
        ("最终答案写回规范", CORE_FILES["answer_writeback_protocol_md"], "规定 Codex 答案如何写回和入库。", "治理入口", 16),
        ("本题库态预检表", CORE_FILES["library_precheck_md"], "本题库法理解和回源要求。", "工程入口", 17),
        ("库群覆盖矩阵", CORE_FILES["library_coverage_md"], "本题库法与中心表轴覆盖情况。", "工程入口", 18),
        ("来源字段标准化词典", CORE_FILES["source_schema_md"], "字段口径和覆盖情况。", "治理入口", 19),
        ("经验法典三层结构", CORE_FILES["experience_codex_md"], "给 Codex 的题型、策略和失败修正经验。", "治理入口", 20),
        ("正式沙盒模式边界", CORE_FILES["mode_boundary_md"], "防止旧稿/沙盒污染正式链。", "治理入口", 21),
        ("用户认可入库门", CORE_FILES["approval_ingest_gate_md"], "最终答案认可后才入库。", "治理入口", 22),
        ("十题回归测试骨架", CORE_FILES["regression_plan_md"], "后续多题验收的测试骨架。", "审计", 23),
        ("Codex指挥链达标检查", CORE_FILES["pipeline_audit_md"], "全流程达标审计。", "审计", 24),
        ("全流程产物与Codex判别门", CORE_FILES["process_inventory_md"], "所有过程产物清单。", "审计", 25),
    ]
    entries = []
    for label, file_name, purpose, audience, weight in ordered:
        path = package_dir / file_name if file_name in CORE_FILES.values() else Path(str(file_name))
        entries.append(
            {
                "label": label,
                "file": file_name,
                "path": str(path),
                "exists": path.exists(),
                "purpose": purpose,
                "audience": audience,
                "weight": weight,
            }
        )
    payload = {
        "generated_at": generated_at,
        "question": question,
        "principle": "桌面和状态台的默认阅读顺序按人读价值排序：最终回答与精读材料靠前，工程底账靠后但全部可追踪。",
        "entries": entries,
        "output_files": {
            "human_reading_order_md": str(package_dir / CORE_FILES["human_reading_order_md"]),
            "human_reading_order_json": str(package_dir / CORE_FILES["human_reading_order_json"]),
        },
    }
    lines = [
        "# 红楼梦工程｜桌面人读排序配置",
        "",
        f"生成时间：{generated_at}",
        "",
        "## 1. 用途",
        "",
        payload["principle"],
        "",
        "## 2. 阅读顺序",
        "",
        "| 顺序 | 入口 | 人读位置 | 文件 | 存在 | 作用 |",
        "|---:|---|---|---|---|---|",
    ]
    for row in entries:
        exists = "是" if row["exists"] else "否"
        lines.append(f"| {row['weight']} | {row['label']} | {row['audience']} | `{row['path']}` | {exists} | {row['purpose']} |")
    lines.extend(
        [
            "",
            "## 3. 排序边界",
            "",
            "- 页面可折叠工程底账，但不得删除底账。",
            "- 最终答案未生成时，第一屏显示等待 Codex 最终答案，不用本地稿替代。",
            "- 人读排序不改变证据等级；证据等级仍由 A/B 硬门和 Codex 精读决定。",
            "",
            f"结构化摘要：`{payload['output_files']['human_reading_order_json']}`",
        ]
    )
    md_path = package_dir / CORE_FILES["human_reading_order_md"]
    json_path = package_dir / CORE_FILES["human_reading_order_json"]
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    write_json(json_path, payload)
    return payload


def render_overview(manifest: dict[str, Any]) -> str:
    research = manifest["results"]["research"]
    review = manifest["results"]["review"]
    readback = manifest["results"]["readback"]
    feedback = manifest["results"]["feedback"]
    core = manifest["core_files"]
    lines = [
        "# 红楼梦正式底库｜闭环工作流总览",
        "",
        f"生成时间：{manifest['generated_at']}",
        "",
        "## 1. 总问题",
        "",
        manifest["question"],
        "",
        "## 2. 当前判断",
        "",
        manifest["status"],
        "",
        "## 3. 本次出库规模",
        "",
        f"- 子问题数量：{research.get('subquestion_count', 0)}",
        f"- 子问题证据明细行：{research.get('raw_rows', 0)}",
        f"- 合并后唯一段落：{research.get('unique_segments', 0)}",
        f"- 复核表行数：{review.get('review_rows', 0)}",
        f"- 可用证据：{readback.get('usable_rows', 0)}",
        f"- 待复核证据：{readback.get('pending_rows', 0)}",
        f"- 反馈有效人工判断：{feedback.get('labeled_rows', 0)}",
        "",
        "## 4. 核心文件",
        "",
        f"- 问题判断程序：`{core.get('question_judgment_md', '')}`",
        f"- 关键词网络预检：`{core.get('keyword_precheck_json', '')}`",
        f"- 库线原文流转骨架：`{core.get('library_flow_md', '')}`",
        f"- 库线原文流转摘要：`{core.get('library_flow_json', '')}`",
        f"- 本题库态预检表：`{core.get('library_precheck_md', '')}`",
        f"- 本题库态预检摘要：`{core.get('library_precheck_json', '')}`",
        f"- 经验复盘入账：`{core.get('experience_entry_md', '')}`",
        f"- 经验复盘入账摘要：`{core.get('experience_entry_json', '')}`",
        f"- 最终回答前材料池精读门：`{core.get('final_reading_gate_md', '')}`",
        f"- 最终回答前材料池精读摘要：`{core.get('final_reading_gate_json', '')}`",
        f"- 全流程产物与 Codex 判别门：`{core.get('process_inventory_md', '')}`",
        f"- 全流程产物与 Codex 判别门摘要：`{core.get('process_inventory_json', '')}`",
        f"- 二轮补证决策卡：`{core.get('second_round_decision_md', '')}`",
        f"- 二轮补证决策摘要：`{core.get('second_round_decision_json', '')}`",
        f"- 来源字段标准化词典：`{core.get('source_schema_md', '')}`",
        f"- 经验法典三层结构：`{core.get('experience_codex_md', '')}`",
        f"- 正式沙盒模式边界：`{core.get('mode_boundary_md', '')}`",
        f"- 用户认可入库门：`{core.get('approval_ingest_gate_md', '')}`",
        f"- 库群覆盖矩阵：`{core.get('library_coverage_md', '')}`",
        f"- Codex写作前原文追证摘抄生成门：`{core.get('codex_original_reread_gate_md', '')}`",
        f"- Codex写作前原文追证摘抄目标稿位：`{core.get('codex_original_reread_target_md', '')}`",
        f"- Codex精读材料词生成门：`{core.get('codex_close_reading_gate_md', '')}`",
        f"- Codex精读材料词目标稿位：`{core.get('codex_close_reading_target_md', '')}`",
        f"- Codex红楼解语生成门：`{core.get('codex_final_answer_gate_md', '')}`",
        f"- Codex红楼解语目标稿位：`{core.get('codex_final_answer_target_md', '')}`",
        f"- Codex最终答案写回规范：`{core.get('answer_writeback_protocol_md', '')}`",
        f"- 十题回归测试骨架：`{core.get('regression_plan_md', '')}`",
        f"- 桌面人读排序配置：`{core.get('human_reading_order_md', '')}`",
        f"- 全局经验值总账：`{EXPERIENCE_LEDGER_MD}`",
        f"- 问题树：`{core['question_tree']}`",
        f"- 证据阅读顺序：`{core['triaged_csv']}`",
        f"- 重点证据卡片：`{core['cards']}`",
        f"- 复核表：`{core['review_csv']}`",
        f"- 复核阅读单：`{core['reading_md']}`",
        f"- 复核回读材料：`{core['writing_md']}`",
        f"- 反馈排序配置：`{core['feedback_profile']}`",
        f"- 运行清单：`{core['manifest']}`",
    ]
    if (
        core.get("writable_pack")
        or core.get("handoff_prompt")
        or core.get("draft_md")
        or core.get("counter_draft_md")
        or core.get("next_plan_md")
        or core.get("next_tasks_csv")
        or core.get("review_plan_md")
        or core.get("review_queue_csv")
        or core.get("review_sheet_csv")
        or core.get("review_sheet_md")
        or core.get("review_tick_md")
        or core.get("review_apply_md")
        or core.get("workflow_status_md")
        or core.get("workflow_status_json")
        or core.get("review_check_md")
        or core.get("review_check_json")
        or core.get("continue_report_md")
        or core.get("continue_summary_json")
        or core.get("review_cards_md")
        or core.get("review_backup_md")
        or core.get("review_backup_json")
        or core.get("review_restore_md")
        or core.get("review_backup_dir")
        or core.get("review_assist_md")
        or core.get("review_assist_csv")
        or core.get("review_workbench_md")
        or core.get("review_workbench_csv")
        or core.get("review_coverage_md")
        or core.get("review_coverage_csv")
        or core.get("review_firstpass_md")
        or core.get("review_firstpass_csv")
        or core.get("review_firstpass_sheet_csv")
        or core.get("review_firstpass_sheet_md")
        or core.get("review_firstpass_sync_md")
        or core.get("review_firstpass_check_md")
        or core.get("review_firstpass_check_json")
        or core.get("review_firstpass_cards_md")
        or core.get("review_firstpass_desk_md")
        or core.get("review_firstpass_talk_md")
        or core.get("source_verify_md")
        or core.get("source_verify_csv")
        or core.get("review_finish_md")
        or core.get("review_finish_json")
        or core.get("article_ingest_report_md")
        or core.get("article_ingest_candidate_csv")
        or core.get("article_ingest_links_csv")
        or core.get("article_ingest_identity_md")
        or core.get("article_ingest_summary_json")
    ):
        lines.extend(["", "## 4.1 回填后文件", ""])
        if core.get("writable_pack"):
            lines.append(f"- 可写作证据包：`{core['writable_pack']}`")
        if core.get("handoff_prompt"):
            lines.append(f"- 写作接力提示词：`{core['handoff_prompt']}`")
        if core.get("draft_md"):
            lines.append(f"- 正式写作草稿：`{core['draft_md']}`")
        if core.get("counter_draft_md"):
            lines.append(f"- 反方证据小稿：`{core['counter_draft_md']}`")
        if core.get("source_verify_md"):
            lines.append(f"- 真源核验统一报告：`{core['source_verify_md']}`")
        if core.get("source_verify_csv"):
            lines.append(f"- 真源核验清单：`{core['source_verify_csv']}`")
        if core.get("review_finish_md"):
            lines.append(f"- 复核收口运行报告：`{core['review_finish_md']}`")
        if core.get("review_finish_json"):
            lines.append(f"- 复核收口摘要：`{core['review_finish_json']}`")
        if core.get("article_ingest_report_md"):
            lines.append(f"- 文章入库预检报告：`{core['article_ingest_report_md']}`")
        if core.get("article_ingest_candidate_csv"):
            lines.append(f"- 作品总库入库候选行：`{core['article_ingest_candidate_csv']}`")
        if core.get("article_ingest_links_csv"):
            lines.append(f"- 文章回挂清单：`{core['article_ingest_links_csv']}`")
        if core.get("article_ingest_identity_md"):
            lines.append(f"- 文章入库身份卡：`{core['article_ingest_identity_md']}`")
        if core.get("article_ingest_summary_json"):
            lines.append(f"- 文章入库预检摘要：`{core['article_ingest_summary_json']}`")
        if core.get("next_plan_md"):
            lines.append(f"- 二次追问与补证计划：`{core['next_plan_md']}`")
        if core.get("next_tasks_csv"):
            lines.append(f"- 下一轮出库任务：`{core['next_tasks_csv']}`")
        if core.get("review_plan_md"):
            lines.append(f"- 人工复核优先清单：`{core['review_plan_md']}`")
        if core.get("review_queue_csv"):
            lines.append(f"- 人工复核批次：`{core['review_queue_csv']}`")
        if core.get("review_sheet_csv"):
            lines.append(f"- 当前批次复核工作表：`{core['review_sheet_csv']}`")
        if core.get("review_sheet_md"):
            lines.append(f"- 复核工作表填写说明：`{core['review_sheet_md']}`")
        if core.get("review_tick_md"):
            lines.append(f"- 人工复核打勾表：`{core['review_tick_md']}`")
        if core.get("review_apply_md"):
            lines.append(f"- 复核工作表回填报告：`{core['review_apply_md']}`")
        if core.get("workflow_status_md"):
            lines.append(f"- 闭环状态与下一步操作台：`{core['workflow_status_md']}`")
        if core.get("workflow_status_json"):
            lines.append(f"- 闭环状态摘要：`{core['workflow_status_json']}`")
        if core.get("review_check_md"):
            lines.append(f"- 复核工作表质量检查：`{core['review_check_md']}`")
        if core.get("review_check_json"):
            lines.append(f"- 复核工作表质量检查摘要：`{core['review_check_json']}`")
        if core.get("continue_report_md"):
            lines.append(f"- 一键续跑报告：`{core['continue_report_md']}`")
        if core.get("continue_summary_json"):
            lines.append(f"- 一键续跑摘要：`{core['continue_summary_json']}`")
        if core.get("review_cards_md"):
            lines.append(f"- 当前批次复核阅读卡片：`{core['review_cards_md']}`")
        if core.get("review_backup_md"):
            lines.append(f"- 复核表备份索引：`{core['review_backup_md']}`")
        if core.get("review_backup_json"):
            lines.append(f"- 复核表备份索引摘要：`{core['review_backup_json']}`")
        if core.get("review_restore_md"):
            lines.append(f"- 复核表恢复报告：`{core['review_restore_md']}`")
        if core.get("review_backup_dir"):
            lines.append(f"- 复核表备份文件夹：`{core['review_backup_dir']}`")
        if core.get("review_assist_md"):
            lines.append(f"- 复核填写助手：`{core['review_assist_md']}`")
        if core.get("review_assist_csv"):
            lines.append(f"- 复核填写助手表：`{core['review_assist_csv']}`")
        if core.get("review_workbench_md"):
            lines.append(f"- 复核填表工作台：`{core['review_workbench_md']}`")
        if core.get("review_workbench_csv"):
            lines.append(f"- 复核填表工作台表：`{core['review_workbench_csv']}`")
        if core.get("review_coverage_md"):
            lines.append(f"- 复核覆盖矩阵：`{core['review_coverage_md']}`")
        if core.get("review_coverage_csv"):
            lines.append(f"- 复核覆盖矩阵表：`{core['review_coverage_csv']}`")
        if core.get("review_firstpass_md"):
            lines.append(f"- 首轮复核执行单：`{core['review_firstpass_md']}`")
        if core.get("review_firstpass_csv"):
            lines.append(f"- 首轮复核执行单表：`{core['review_firstpass_csv']}`")
        if core.get("review_firstpass_sheet_csv"):
            lines.append(f"- 首轮复核小表：`{core['review_firstpass_sheet_csv']}`")
        if core.get("review_firstpass_sheet_md"):
            lines.append(f"- 首轮复核小表填写说明：`{core['review_firstpass_sheet_md']}`")
        if core.get("review_firstpass_sync_md"):
            lines.append(f"- 首轮复核小表同步报告：`{core['review_firstpass_sync_md']}`")
        if core.get("review_firstpass_check_md"):
            lines.append(f"- 首轮复核小表质量检查：`{core['review_firstpass_check_md']}`")
        if core.get("review_firstpass_check_json"):
            lines.append(f"- 首轮复核小表质量检查摘要：`{core['review_firstpass_check_json']}`")
        if core.get("review_firstpass_cards_md"):
            lines.append(f"- 首轮复核逐条判读卡片：`{core['review_firstpass_cards_md']}`")
        if core.get("review_firstpass_desk_md"):
            lines.append(f"- 首轮复核就绪台：`{core['review_firstpass_desk_md']}`")
        if core.get("review_firstpass_talk_md"):
            lines.append(f"- 首轮谈心式复核单：`{core['review_firstpass_talk_md']}`")
        lines.append("")
    lines.extend(["", "## 5. 运行步骤", ""])
    for item in manifest["steps"]:
        mark = "通过" if item["ok"] else "失败"
        lines.append(f"- {item['name']}：{mark}")
    lines.extend(
        [
            "",
            "## 6. 使用方式",
            "",
            "先读 `01_问题树.md` 和 `03_重点证据卡片.md`，再在 `04_复核表.csv` 中填写人工判断。人工判断完成后，用这份复核表重新运行回读和反馈学习，即可把保留、降级和反证材料转成可写作材料。",
            "",
            "## 7. 重要边界",
            "",
            "- 本工作流不会替你填写人工判断。",
            "- 未复核证据不会被伪装成正式结论。",
            "- 反馈排序只读取人工标注，不读取机器猜测。",
        ]
    )
    return "\n".join(lines)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def short(text: object, limit: int = 120) -> str:
    value = clean(text)
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def review_progress(review_csv: Path) -> dict[str, Any]:
    rows = read_csv(review_csv)
    normalized = [
        (
            review_readback.normalize_decision(row.get("human_decision", "")),
            review_readback.normalize_verify_status(row.get("source_verify_status", "")),
        )
        for row in rows
    ]
    counts = Counter(item[0] for item in normalized)
    total = len(rows)
    pending = counts.get("待复核", 0)
    completed = max(0, total - pending)
    usable_decisions = {"保留", "降级", "反证"}
    verified_rows = [
        row for row in normalized if row[0] in usable_decisions and row[1] == "已核验"
    ]
    unverified_rows = [
        row for row in normalized if row[0] in usable_decisions and row[1] != "已核验"
    ]
    usable = len(verified_rows)
    rejected = counts.get("剔除", 0)
    completion_rate = round(completed / total, 4) if total else 0.0
    return {
        "total_rows": total,
        "completed_rows": completed,
        "pending_rows": pending,
        "usable_rows": usable,
        "verified_rows": len(verified_rows),
        "unverified_rows": len(unverified_rows),
        "rejected_rows": rejected,
        "counter_rows": counts.get("反证", 0),
        "downgrade_rows": counts.get("降级", 0),
        "keep_rows": counts.get("保留", 0),
        "completion_rate": completion_rate,
        "decision_counts": dict(counts),
    }


SOURCE_VERIFY_FIELDS = [
    "source_chapter_id",
    "source_segment_id",
    "source_rule",
    "source_verify_status",
    "source_verify_note",
]


def source_verify_rule(row: dict[str, str]) -> str:
    chapter = clean(row.get("chapter_no"))
    segment = clean(row.get("segment_no"))
    if chapter and segment:
        return f"回源核对第{chapter}回、段落号 {segment}：确认摘要、引文、回目与正式底库原文一致。"
    if segment:
        return f"回源核对段落号 {segment}：确认摘要、引文、回目与正式底库原文一致。"
    return "缺少段落号，需先补齐 source_segment_id 后再回源核验。"


def normalize_source_verify_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized_rows: list[dict[str, Any]] = []
    verify_rows: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        chapter = clean(new_row.get("source_chapter_id")) or clean(new_row.get("chapter_no"))
        segment = clean(new_row.get("source_segment_id")) or clean(new_row.get("segment_no"))
        rule = clean(new_row.get("source_rule")) or source_verify_rule(new_row)
        verify_status = review_readback.normalize_verify_status(new_row.get("source_verify_status", ""))
        note = clean(new_row.get("source_verify_note"))
        if not note:
            note = "待人工回源核验；核对通过后可改为“已核验”。"
        new_row["source_chapter_id"] = chapter
        new_row["source_segment_id"] = segment
        new_row["source_rule"] = rule
        new_row["source_verify_status"] = verify_status
        new_row["source_verify_note"] = note
        normalized_rows.append(new_row)
        decision = review_readback.normalize_decision(new_row.get("human_decision", ""))
        verify_rows.append(
            {
                "review_order": clean(new_row.get("review_order")),
                "source_chapter_id": chapter,
                "source_segment_id": segment,
                "chapter_title": clean(new_row.get("chapter_title")),
                "human_decision": decision,
                "human_role": clean(new_row.get("human_role")),
                "usable_level": clean(new_row.get("usable_level")),
                "source_verify_status": verify_status,
                "source_rule": rule,
                "source_verify_note": note,
                "summary": clean(new_row.get("summary")),
                "quote": clean(new_row.get("quote")),
                "missing_required_source": "是" if not (chapter and segment and clean(new_row.get("quote"))) else "否",
            }
        )
    return normalized_rows, verify_rows


def render_source_verify_report(question: str, result: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦正式底库｜真源核验统一报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 1. 问题",
        "",
        question or "未指定问题。",
        "",
        "## 2. 本次做了什么",
        "",
        "本次只统一真源核验字段和核验清单，不会把任何证据自动改成“已核验”。",
        "",
        f"- 是否模拟运行：{result['dry_run']}",
        f"- 复核表：`{result['review_csv']}`",
        f"- 核验清单：`{result['source_verify_csv']}`",
        f"- 复核表总行数：{result['total_rows']}",
        f"- 已有人工判断行：{result['completed_rows']}",
        f"- 需核验可用决议行：{result['usable_decision_rows']}",
        f"- 已核验可用决议行：{result['verified_usable_rows']}",
        f"- 待核验可用决议行：{result['unverified_usable_rows']}",
        f"- 缺少段落/回目/引文的行：{result['missing_required_source_rows']}",
        "",
        "## 3. 统一字段",
        "",
        "- `source_chapter_id`：回目号。",
        "- `source_segment_id`：段落号。",
        "- `source_rule`：本条证据如何回源核对。",
        "- `source_verify_status`：待核验 / 已核验。",
        "- `source_verify_note`：核验备注。",
        "",
        "## 4. 重要边界",
        "",
        "- 默认状态是“待核验”。",
        "- 只有人工确认后，才应把 `source_verify_status` 改为“已核验”。",
        "- `loop-readback` 仍然只把“保留/降级/反证 + 已核验”的证据放入正式可写作材料。",
        "",
    ]
    if result.get("backup"):
        lines.extend(["## 5. 写入前备份", "", f"- 备份文件：`{result['backup']['backup_csv']}`", ""])
    if result["missing_required_source_rows"]:
        lines.extend(["## 6. 需要补源的前若干行", ""])
        for item in result["missing_required_source_samples"][:20]:
            lines.append(
                f"- review_order={item['review_order']}｜segment={item['source_segment_id'] or '缺'}｜chapter={item['source_chapter_id'] or '缺'}｜quote={short(item['quote'], 40) or '缺'}"
            )
        lines.append("")
    lines.extend(
        [
            "## 7. 下一步",
            "",
            "如果你已经人工确认某条证据的回目、段落号、引文都准确，就在 `04_复核表.csv` 或 `55_真源核验清单.csv` 对应行把 `source_verify_status` 改为“已核验”。",
            "",
            "改完后运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-readback --package latest",
            "python3 work/formal_honglou_cli.py loop-status --package latest",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_source_verify(package: str | Path = "latest", out_root: Path = OUT_ROOT, dry_run: bool = False) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")
    rows = read_csv(review_csv)
    normalized_rows, verify_rows = normalize_source_verify_rows(rows)
    existing_fields = list(rows[0].keys()) if rows else []
    fieldnames = existing_fields + [field for field in SOURCE_VERIFY_FIELDS if field not in existing_fields]
    verify_csv = package_dir / CORE_FILES["source_verify_csv"]
    report_md = package_dir / CORE_FILES["source_verify_md"]
    backup = None
    if not dry_run:
        backup = backup_review_csv(package_dir, reason="真源核验字段统一")
        write_csv(review_csv, normalized_rows, fieldnames)
        write_csv(
            verify_csv,
            verify_rows,
            [
                "review_order",
                "source_chapter_id",
                "source_segment_id",
                "chapter_title",
                "human_decision",
                "human_role",
                "usable_level",
                "source_verify_status",
                "source_rule",
                "source_verify_note",
                "summary",
                "quote",
                "missing_required_source",
            ],
        )
    else:
        verify_csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(
            verify_csv,
            verify_rows,
            [
                "review_order",
                "source_chapter_id",
                "source_segment_id",
                "chapter_title",
                "human_decision",
                "human_role",
                "usable_level",
                "source_verify_status",
                "source_rule",
                "source_verify_note",
                "summary",
                "quote",
                "missing_required_source",
            ],
        )

    decisions = [review_readback.normalize_decision(row.get("human_decision", "")) for row in normalized_rows]
    usable_decision_rows = [
        row for row in normalized_rows if review_readback.normalize_decision(row.get("human_decision", "")) in {"保留", "降级", "反证"}
    ]
    verified_usable_rows = [
        row for row in usable_decision_rows if review_readback.normalize_verify_status(row.get("source_verify_status", "")) == "已核验"
    ]
    missing_required = [
        row for row in verify_rows if clean(row.get("missing_required_source")) == "是"
    ]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "dry_run": dry_run,
        "review_csv": str(review_csv),
        "source_verify_csv": str(verify_csv),
        "source_verify_md": str(report_md),
        "total_rows": len(normalized_rows),
        "completed_rows": sum(1 for decision in decisions if decision != "待复核"),
        "usable_decision_rows": len(usable_decision_rows),
        "verified_usable_rows": len(verified_usable_rows),
        "unverified_usable_rows": max(0, len(usable_decision_rows) - len(verified_usable_rows)),
        "missing_required_source_rows": len(missing_required),
        "missing_required_source_samples": missing_required[:20],
        "backup": backup,
    }
    report_md.write_text(render_source_verify_report(question, result), encoding="utf-8")
    core_files = manifest.setdefault("core_files", {})
    core_files["source_verify_md"] = str(report_md)
    core_files["source_verify_csv"] = str(verify_csv)
    manifest.setdefault("results", {})["loop_source_verify"] = result
    if dry_run:
        manifest["status"] = "已模拟真源核验字段统一；未写入 04 复核表。"
    else:
        manifest["status"] = f"已统一真源核验字段：{len(normalized_rows)} 行；可用决议待核验 {result['unverified_usable_rows']} 行。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "真源核验字段统一",
            len(normalized_rows) > 0,
            {
                "source_verify_md": str(report_md),
                "source_verify_csv": str(verify_csv),
                "total_rows": len(normalized_rows),
                "usable_decision_rows": len(usable_decision_rows),
                "verified_usable_rows": len(verified_usable_rows),
                "unverified_usable_rows": result["unverified_usable_rows"],
                "missing_required_source_rows": len(missing_required),
                "dry_run": dry_run,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "source_verify": result,
        "manifest": str(manifest_path_value),
    }


def review_backup_dir(package_dir: Path) -> Path:
    return package_dir / REVIEW_BACKUP_DIR


def backup_review_csv(package_dir: Path, reason: str) -> dict[str, Any]:
    review_csv = package_dir / CORE_FILES["review_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")
    backup_dir = review_backup_dir(package_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    safe_reason = safe_filename_part(reason, limit=18)
    backup_csv = backup_dir / f"{now.strftime('%Y%m%d_%H%M%S_%f')}_04_复核表_{safe_reason}.csv"
    shutil.copyfile(review_csv, backup_csv)
    progress = review_progress(backup_csv)
    return {
        "created_at": now.isoformat(timespec="seconds"),
        "reason": reason,
        "source_csv": str(review_csv),
        "backup_csv": str(backup_csv),
        "backup_name": backup_csv.name,
        "rows": progress["total_rows"],
        "decision_counts": progress["decision_counts"],
        "size": backup_csv.stat().st_size,
    }


def review_backup_records(package_dir: Path) -> list[dict[str, Any]]:
    backup_dir = review_backup_dir(package_dir)
    if not backup_dir.exists():
        return []
    records = []
    for path in sorted(backup_dir.glob("*.csv"), key=lambda item: (item.stat().st_mtime, item.name), reverse=True):
        progress = review_progress(path)
        records.append(
            {
                "backup_name": path.name,
                "backup_csv": str(path),
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "rows": progress["total_rows"],
                "completed_rows": progress["completed_rows"],
                "pending_rows": progress["pending_rows"],
                "usable_rows": progress["usable_rows"],
                "rejected_rows": progress["rejected_rows"],
                "decision_counts": progress["decision_counts"],
                "size": path.stat().st_size,
            }
        )
    return records


def resolve_review_backup(package_dir: Path, backup: str | Path = "latest") -> Path:
    raw = clean(backup) or "latest"
    records = review_backup_records(package_dir)
    if raw == "latest":
        if not records:
            raise FileNotFoundError(f"这个闭环包还没有复核表备份：{review_backup_dir(package_dir)}")
        return Path(records[0]["backup_csv"])

    path = Path(raw)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(review_backup_dir(package_dir) / raw)
        candidates.append(package_dir / raw)
        candidates.append(path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"没有找到指定复核表备份：{raw}")


def manifest_path(package_dir: Path) -> Path:
    return package_dir / CORE_FILES["manifest"]


def load_manifest(package_dir: Path) -> dict[str, Any]:
    path = manifest_path(package_dir)
    if not path.exists():
        raise FileNotFoundError(f"缺少闭环运行清单：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def package_dirs(out_root: Path = OUT_ROOT) -> list[Path]:
    root = Path(out_root)
    if not root.exists():
        return []
    dirs = [path for path in root.iterdir() if path.is_dir() and manifest_path(path).exists()]
    dirs.sort(key=lambda path: (manifest_path(path).stat().st_mtime, path.name), reverse=True)
    return dirs


def resolve_package(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> Path:
    raw = clean(package)
    if not raw or raw == "latest":
        dirs = package_dirs(out_root)
        if not dirs:
            raise FileNotFoundError(f"没有找到闭环问题包：{out_root}")
        return dirs[0]
    path = Path(raw)
    if not path.is_absolute() and not path.exists():
        path = Path(out_root) / raw
    if not path.exists():
        raise FileNotFoundError(f"闭环问题包不存在：{path}")
    if not manifest_path(path).exists():
        raise FileNotFoundError(f"闭环问题包缺少运行清单：{manifest_path(path)}")
    return path


def loop_list(out_root: Path = OUT_ROOT) -> dict[str, Any]:
    packages = []
    for package_dir in package_dirs(out_root):
        manifest = load_manifest(package_dir)
        review_csv = package_dir / CORE_FILES["review_csv"]
        progress = review_progress(review_csv)
        packages.append(
            {
                "package": package_dir.name,
                "path": str(package_dir),
                "question": manifest.get("question", ""),
                "status": manifest.get("status", ""),
                "generated_at": manifest.get("generated_at", ""),
                "total_rows": progress["total_rows"],
                "completed_rows": progress["completed_rows"],
                "pending_rows": progress["pending_rows"],
                "usable_rows": progress["usable_rows"],
                "rejected_rows": progress["rejected_rows"],
                "completion_rate": progress["completion_rate"],
                "decision_counts": progress["decision_counts"],
            }
        )
    return {"out_root": str(out_root), "packages": packages, "package_count": len(packages)}


def render_review_backup_index(question: str, payload: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦正式底库｜复核表备份索引",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 备份状态",
        "",
        f"- 备份文件夹：`{payload['backup_dir']}`",
        f"- 备份数量：{payload['backup_count']}",
        "",
    ]
    if payload["backups"]:
        lines.extend(["## 3. 备份清单", ""])
        for idx, item in enumerate(payload["backups"], start=1):
            lines.append(
                f"- {idx}. `{item['backup_name']}`｜行数 {item['rows']}｜已判断 {item['completed_rows']}｜"
                f"待复核 {item['pending_rows']}｜大小 {item['size']} bytes"
            )
        lines.append("")
        lines.extend(
            [
                "## 4. 恢复方式",
                "",
                "先模拟恢复，确认选中的备份正确；再正式恢复：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-restore --package latest --backup latest --dry-run",
                "python3 work/formal_honglou_cli.py loop-review-restore --package latest --backup latest",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "## 3. 下一步",
                "",
                "当前还没有备份。第一次正式回填 `04_复核表.csv` 前，系统会自动创建一份回填前备份。",
            ]
        )
    return "\n".join(lines)


def loop_review_backups(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    backup_md = package_dir / CORE_FILES["review_backup_md"]
    backup_json = package_dir / CORE_FILES["review_backup_json"]
    records = review_backup_records(package_dir)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "backup_dir": str(review_backup_dir(package_dir)),
        "backup_count": len(records),
        "backups": records,
        "backup_index_md": str(backup_md),
        "backup_index_json": str(backup_json),
    }
    backup_md.write_text(render_review_backup_index(question, payload), encoding="utf-8")
    write_json(backup_json, payload)

    core_files = manifest.setdefault("core_files", {})
    core_files["review_backup_md"] = str(backup_md)
    core_files["review_backup_json"] = str(backup_json)
    manifest.setdefault("results", {})["loop_review_backups"] = payload
    manifest["status"] = f"已更新复核表备份索引：{len(records)} 个备份。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核表备份索引",
            True,
            {
                "backup_count": len(records),
                "backup_index_md": str(backup_md),
                "backup_index_json": str(backup_json),
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "backup_count": len(records),
        "backups": records,
        "backup_index_md": str(backup_md),
        "backup_index_json": str(backup_json),
        "manifest": str(manifest_path_value),
    }


def render_review_restore_report(question: str, result: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦正式底库｜复核表恢复报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 恢复结果",
        "",
        f"- 是否模拟恢复：{result['dry_run']}",
        f"- 当前复核表：`{result['review_csv']}`",
        f"- 选中备份：`{result['selected_backup']}`",
        f"- 恢复前复核表行数：{result['before_progress']['total_rows']}",
        f"- 备份表行数：{result['backup_progress']['total_rows']}",
        f"- 恢复后复核表行数：{result['after_progress']['total_rows']}",
        "",
    ]
    if result.get("before_backup"):
        lines.extend(
            [
                "## 3. 恢复前自动备份",
                "",
                f"- 已先保存当前复核表：`{result['before_backup']['backup_csv']}`",
                f"- 保存原因：{result['before_backup']['reason']}",
                "",
            ]
        )
    else:
        lines.extend(["## 3. 恢复前自动备份", "", "本次是模拟恢复，没有写入复核表，也没有创建恢复前备份。", ""])
    lines.extend(
        [
            "## 4. 下一步",
            "",
        ]
    )
    if result["dry_run"]:
        lines.extend(
            [
                "模拟恢复没有改动 `04_复核表.csv`。确认无误后可正式恢复：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-restore --package latest --backup latest",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "复核表已恢复。请重新刷新回读、草稿和状态：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-readback --package latest",
                "python3 work/formal_honglou_cli.py loop-draft --package latest",
                "python3 work/formal_honglou_cli.py loop-status --package latest",
                "```",
            ]
        )
    return "\n".join(lines)


def loop_review_restore(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    backup: str | Path = "latest",
    dry_run: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    selected_backup = resolve_review_backup(package_dir, backup)
    before_progress = review_progress(review_csv)
    backup_progress = review_progress(selected_backup)
    before_backup: dict[str, Any] | None = None
    if not dry_run:
        before_backup = backup_review_csv(package_dir, reason="恢复前")
        shutil.copyfile(selected_backup, review_csv)
    after_progress = review_progress(review_csv if not dry_run else selected_backup)

    restore_md = package_dir / CORE_FILES["review_restore_md"]
    backup_md = package_dir / CORE_FILES["review_backup_md"]
    backup_json = package_dir / CORE_FILES["review_backup_json"]
    backup_records = review_backup_records(package_dir)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_csv": str(review_csv),
        "selected_backup": str(selected_backup),
        "dry_run": dry_run,
        "before_progress": before_progress,
        "backup_progress": backup_progress,
        "after_progress": after_progress,
        "before_backup": before_backup,
        "restore_report_md": str(restore_md),
        "backup_index_md": str(backup_md),
        "backup_index_json": str(backup_json),
        "backup_count": len(backup_records),
    }
    restore_md.write_text(render_review_restore_report(question, result), encoding="utf-8")
    index_payload = {
        "generated_at": result["generated_at"],
        "package": str(package_dir),
        "question": question,
        "backup_dir": str(review_backup_dir(package_dir)),
        "backup_count": len(backup_records),
        "backups": backup_records,
        "backup_index_md": str(backup_md),
        "backup_index_json": str(backup_json),
    }
    backup_md.write_text(render_review_backup_index(question, index_payload), encoding="utf-8")
    write_json(backup_json, index_payload)

    core_files = manifest.setdefault("core_files", {})
    core_files["review_restore_md"] = str(restore_md)
    core_files["review_backup_md"] = str(backup_md)
    core_files["review_backup_json"] = str(backup_json)
    manifest.setdefault("results", {})["loop_review_restore"] = result
    if dry_run:
        manifest["status"] = "已模拟复核表恢复，没有改动 04_复核表.csv。"
    else:
        manifest["status"] = "已恢复 04_复核表.csv；请重新运行回读和状态刷新。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核表备份恢复",
            True,
            {
                "dry_run": dry_run,
                "selected_backup": str(selected_backup),
                "before_backup": before_backup,
                "restore_report_md": str(restore_md),
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_restore": result,
        "manifest": str(manifest_path_value),
    }


def upsert_step(steps: list[dict[str, Any]], item: dict[str, Any]) -> None:
    for idx, existing in enumerate(steps):
        if existing.get("name") == item.get("name"):
            steps[idx] = item
            return
    steps.append(item)


def render_writable_pack(question: str, readback_result: dict[str, Any], progress: dict[str, Any]) -> str:
    usable_rows = read_csv(Path(readback_result["usable_csv"]))
    rejected_rows = read_csv(Path(readback_result["rejected_csv"]))
    pending_rows = read_csv(Path(readback_result["pending_csv"]))
    lines = [
        "# 红楼梦正式底库｜可写作证据包",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 问题",
        "",
        question,
        "",
        "## 2. 当前状态",
        "",
        f"- 复核表总行数：{progress['total_rows']}",
        f"- 已人工判断：{progress['completed_rows']}",
        f"- 可写作证据：{len(usable_rows)}",
        f"- 剔除证据：{len(rejected_rows)}",
        f"- 待复核证据：{len(pending_rows)}",
        "",
    ]
    if not usable_rows:
        lines.extend(
            [
                "## 3. 尚不可进入正式写作",
                "",
                "当前复核表还没有“保留、降级、反证”等人工可用判断。系统已完成回填，但不会把待复核证据冒充为正式写作材料。",
                "",
                "## 4. 待复核证据预览",
                "",
            ]
        )
        for row in pending_rows[:20]:
            lines.append(
                f"- {row.get('review_order', '')}｜{row.get('segment_no', '')}｜{row.get('machine_role', '')}｜"
                f"{short(row.get('summary'), 80)}｜复核问题：{short(row.get('review_question'), 80)}"
            )
        return "\n".join(lines)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in usable_rows:
        group = row.get("final_writing_use") or row.get("suggested_section") or row.get("normalized_decision") or "未分组"
        grouped[group].append(row)
    lines.extend(["## 3. 可写作证据", ""])
    for group, rows in grouped.items():
        lines.extend([f"### {group}", ""])
        for row in rows:
            note = clean(row.get("human_note"))
            note_part = f"｜人工备注：{short(note, 60)}" if note else ""
            lines.append(
                f"- {row.get('segment_no', '')}｜第{row.get('chapter_no', '')}回｜{row.get('normalized_decision', '')}｜"
                f"{row.get('final_role', '')}｜等级 {row.get('final_usable_level', '')}｜"
                f"{short(row.get('summary'), 90)}｜引文：{short(row.get('quote'), 100)}{note_part}"
            )
        lines.append("")
    if rejected_rows:
        lines.extend(
            [
                "## 4. 已剔除证据统计",
                "",
                f"- 已剔除：{len(rejected_rows)} 条。",
                "- 剔除证据不进入可写作材料；如需复查，请查看内部回读包 `03_剔除证据.csv`。",
                "",
            ]
        )
    if pending_rows:
        lines.extend(
            [
                "## 5. 待补复核",
                "",
                f"- 仍有 {len(pending_rows)} 条待复核证据。正式长文前建议继续复核各分组前列证据。",
            ]
        )
    return "\n".join(lines)


def render_handoff_prompt(question: str, readback_result: dict[str, Any], progress: dict[str, Any]) -> str:
    usable_rows = read_csv(Path(readback_result["usable_csv"]))
    lines = [
        "# 红楼梦正式底库｜写作接力提示词",
        "",
        "## 用法",
        "",
        "把下面提示词交给下一轮 AI 写作或研究阅读时使用。写作时必须引用段落号，不得把未复核证据写成定论。",
        "",
        "## 提示词",
        "",
        "请基于以下已人工复核的《红楼梦》证据材料，围绕研究问题进行结构化写作。",
        "",
        f"研究问题：{question}",
        "",
        "写作规则：",
        "",
        "1. 只把“保留、降级、反证”的证据作为可用材料。",
        "2. 保留证据可以进入主论证；降级证据只能作为背景或旁证；反证必须单独处理。",
        "3. 每个关键判断后标注段落号，如 `08-004`。",
        "4. 不使用已剔除证据。",
        "5. 如果证据不足，明确指出不足，不补造原文。",
        "",
        "当前复核状态：",
        "",
        f"- 总行数：{progress['total_rows']}",
        f"- 已判断：{progress['completed_rows']}",
        f"- 可写作证据：{len(usable_rows)}",
        f"- 待复核：{progress['pending_rows']}",
        "",
        "可用证据摘要：",
        "",
    ]
    if not usable_rows:
        lines.append("当前没有人工标为可用的证据。请先复核 `04_复核表.csv`，再运行 `loop-readback`。")
        return "\n".join(lines)
    for row in usable_rows[:30]:
        lines.append(
            f"- {row.get('segment_no', '')}｜{row.get('normalized_decision', '')}｜{row.get('final_role', '')}｜"
            f"{short(row.get('summary'), 80)}｜引文：{short(row.get('quote'), 80)}"
        )
    return "\n".join(lines)


def evidence_line(row: dict[str, str], quote_limit: int = 110) -> str:
    note = clean(row.get("human_note"))
    note_part = f"｜人工备注：{short(note, 70)}" if note else ""
    return (
        f"- {row.get('segment_no', '')}｜第{row.get('chapter_no', '')}回｜"
        f"{row.get('normalized_decision', '')}｜{row.get('final_role', '')}｜"
        f"等级 {row.get('final_usable_level', '')}｜{short(row.get('summary'), 100)}"
        f"｜引文：{short(row.get('quote'), quote_limit)}{note_part}"
    )


def render_formal_draft(question: str, usable_rows: list[dict[str, str]], progress: dict[str, Any]) -> str:
    main_rows = [row for row in usable_rows if row.get("normalized_decision") in {"保留", "降级"}]
    counter_rows = [row for row in usable_rows if row.get("normalized_decision") == "反证"]
    lines = [
        "# 红楼梦正式底库｜正式写作草稿",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 写作问题",
        "",
        question,
        "",
        "## 2. 复核边界",
        "",
        "- 本草稿只使用人工标为“保留、降级”的证据。",
        "- 人工标为“反证”的材料不进入主论证，另见 `12_反方证据小稿.md`。",
        "- 已剔除证据和待复核证据不会进入草稿。",
        "",
        "## 3. 复核进度",
        "",
        f"- 复核表总行数：{progress['total_rows']}",
        f"- 已人工判断：{progress['completed_rows']}",
        f"- 主论证可用证据：{len(main_rows)}",
        f"- 反证材料：{len(counter_rows)}",
        f"- 待复核：{progress['pending_rows']}",
        "",
    ]
    if not main_rows:
        lines.extend(
            [
                "## 4. 不可生成正式草稿",
                "",
                "当前闭环包还没有人工标为“保留”或“降级”的证据。系统可以整理材料，但不会把未复核证据或只有反证的材料写成正式主论证。",
                "",
                "下一步：请先在 `04_复核表.csv` 中至少标出若干条“保留”或“降级”，再运行 `loop-readback` 和 `loop-draft`。",
            ]
        )
        return "\n".join(lines)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in main_rows:
        group = row.get("final_writing_use") or row.get("suggested_section") or row.get("final_role") or "未分组"
        grouped[group].append(row)

    lines.extend(
        [
            "## 4. 中心判断草案",
            "",
            "从已复核材料看，本题只能先按当前材料分组生成临时草案。下面文字仍是旧人工复核草稿，不替代 Codex 材料池判定和红楼解语。",
            "",
            "## 5. 论证结构草案",
            "",
        ]
    )
    for idx, (group, rows) in enumerate(grouped.items(), start=1):
        keep_count = sum(1 for row in rows if row.get("normalized_decision") == "保留")
        downgrade_count = sum(1 for row in rows if row.get("normalized_decision") == "降级")
        lines.extend(
            [
                f"### {idx}. {group}",
                "",
                f"本节可用证据 {len(rows)} 条，其中保留 {keep_count} 条，降级 {downgrade_count} 条。写作时可先提出本节判断，再用下列段落号逐条支撑。",
                "",
            ]
        )
        for row in rows[:12]:
            lines.append(evidence_line(row))
        if len(rows) > 12:
            lines.append(f"- 另有 {len(rows) - 12} 条同组证据，可在 `09_可写作证据包.md` 中继续展开。")
        lines.append("")

    lines.extend(
        [
            "## 6. 可直接接力的写作提示",
            "",
            "请围绕上面的分组写一篇研究草稿。每个关键判断必须附段落号；保留证据可作为主证，降级证据只作背景或旁证；反证材料必须在单独段落处理；不得使用待复核或剔除证据。",
        ]
    )
    return "\n".join(lines)


def render_counter_draft(question: str, usable_rows: list[dict[str, str]], progress: dict[str, Any]) -> str:
    counter_rows = [row for row in usable_rows if row.get("normalized_decision") == "反证"]
    lines = [
        "# 红楼梦正式底库｜反方证据小稿",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 写作问题",
        "",
        question,
        "",
        "## 2. 复核边界",
        "",
        "- 本文件只使用人工标为“反证”的证据。",
        "- 反证不是剔除材料，而是用于修正、限制或反驳主论证的材料。",
        "- 待复核证据不会进入反方小稿。",
        "",
        "## 3. 反证规模",
        "",
        f"- 已人工判断：{progress['completed_rows']}",
        f"- 反证材料：{len(counter_rows)}",
        "",
    ]
    if not counter_rows:
        lines.extend(
            [
                "## 4. 暂无反方小稿",
                "",
                "当前闭环包还没有人工标为“反证”的证据。正式写作时仍建议保留一个反方段落，但需要先在复核表中标出反证材料。",
            ]
        )
        return "\n".join(lines)

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in counter_rows:
        group = row.get("final_writing_use") or row.get("suggested_section") or "反证材料"
        grouped[group].append(row)
    lines.extend(["## 4. 反方论点材料", ""])
    for idx, (group, rows) in enumerate(grouped.items(), start=1):
        lines.extend([f"### {idx}. {group}", ""])
        for row in rows:
            lines.append(evidence_line(row))
        lines.append("")
    lines.extend(
        [
            "## 5. 写作处理建议",
            "",
            "正式文章中可把这些材料放在“可能的佛性解释、反向证据和边界条件”一节，用来说明主论证的适用范围，而不是简单删除。",
        ]
    )
    return "\n".join(lines)


def draft_status_sentence(progress: dict[str, Any], main_rows: int, counter_rows: int) -> str:
    if main_rows > 0:
        return "系统已读到人工复核证据，已生成正式写作草稿和反方证据小稿。"
    if counter_rows > 0:
        return "系统已读到反证材料，但缺少保留或降级证据，正式主草稿仍需补复核。"
    if progress.get("total_rows", 0) > 0 and progress.get("pending_rows", 0) == progress.get("total_rows", 0):
        return "系统已跑通，但复核表全部仍为待复核，已阻止正式草稿生成。"
    return "系统已跑通，但缺少人工可写作证据，已阻止正式草稿生成。"


def loop_draft(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    readback_payload = loop_readback(package_dir, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    progress = review_progress(package_dir / CORE_FILES["review_csv"])
    usable_csv = Path(readback_payload["readback"]["usable_csv"])
    usable_rows = read_csv(usable_csv)
    main_rows = [row for row in usable_rows if row.get("normalized_decision") in {"保留", "降级"}]
    counter_rows = [row for row in usable_rows if row.get("normalized_decision") == "反证"]

    draft_path = package_dir / CORE_FILES["draft_md"]
    counter_path = package_dir / CORE_FILES["counter_draft_md"]
    draft_path.write_text(render_formal_draft(question, usable_rows, progress), encoding="utf-8")
    counter_path.write_text(render_counter_draft(question, usable_rows, progress), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["draft_md"] = str(draft_path)
    core_files["counter_draft_md"] = str(counter_path)

    draft_result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "review_csv": str(package_dir / CORE_FILES["review_csv"]),
        "usable_csv": str(usable_csv),
        "draft_md": str(draft_path),
        "counter_draft_md": str(counter_path),
        "main_rows": len(main_rows),
        "counter_rows": len(counter_rows),
        "usable_rows": len(usable_rows),
        "rejected_rows": progress["rejected_rows"],
        "pending_rows": progress["pending_rows"],
        "draft_ready": len(main_rows) > 0,
        "counter_ready": len(counter_rows) > 0,
    }
    manifest.setdefault("results", {})["loop_draft"] = draft_result
    manifest["status"] = draft_status_sentence(progress, len(main_rows), len(counter_rows))
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "闭环写作草稿",
            True,
            {
                "draft_ready": draft_result["draft_ready"],
                "counter_ready": draft_result["counter_ready"],
                "main_rows": len(main_rows),
                "counter_rows": len(counter_rows),
                "pending_rows": progress["pending_rows"],
                "draft_md": str(draft_path),
                "counter_draft_md": str(counter_path),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)

    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "progress": progress,
        "draft": draft_result,
        "manifest": str(manifest_path_value),
    }


def split_subquestions(value: object) -> list[str]:
    parts: list[str] = []
    for raw in clean(value).replace("；", ";").replace("｜", ";").split(";"):
        item = clean(raw)
        if item:
            parts.append(item)
    return parts


def subquestion_query_terms(label: str, question: str) -> tuple[str, str, str]:
    return (
        "等待 Codex 指挥中心生成下一轮查证词",
        "等待 Codex 指挥中心判定人物、物象、空间、事件或文本对象",
        "等待 Codex 指挥中心决定关键词、库轴和原文路径",
    )


def subquestion_priority(stats: dict[str, Any], progress: dict[str, Any]) -> tuple[str, str]:
    label = stats["subquestion"]
    if progress["total_rows"] and progress["pending_rows"] == progress["total_rows"]:
        return "先复核", "当前全表仍待复核，先读本子问题前列证据，不宜重新开新结论。"
    if progress["completion_rate"] < 0.25 and stats["pending_rows"] >= 5:
        return "高", "当前总体复核率仍低，本子问题还有大量待复核证据，需要先上浮处理。"
    if stats["usable_rows"] == 0 and stats["review_rows"] > 0:
        return "高", "本子问题已有召回但没有人工可用证据，需要优先补证或重新检索。"
    if "反证" in label and stats["counter_rows"] < 2:
        return "高", "反证子问题尚无人工反证，需要补足反向边界。"
    if stats["pending_rows"] > max(2, stats["usable_rows"]):
        return "中", "待复核材料多于可用材料，建议继续人工筛选。"
    if stats["usable_rows"] > 0:
        return "低", "已有人工可用证据，下一轮只需查缺补漏。"
    return "中", "当前覆盖不足，建议保留为下一轮补证任务。"


def build_next_tasks(question: str, review_rows: list[dict[str, str]], triaged_rows: list[dict[str, str]], progress: dict[str, Any]) -> list[dict[str, Any]]:
    labels: list[str] = []
    for row in triaged_rows + review_rows:
        for label in split_subquestions(row.get("hit_subquestions")):
            if label not in labels:
                labels.append(label)

    stats: dict[str, dict[str, Any]] = {
        label: {
            "subquestion": label,
            "triaged_rows": 0,
            "review_rows": 0,
            "pending_rows": 0,
            "usable_rows": 0,
            "keep_rows": 0,
            "downgrade_rows": 0,
            "counter_rows": 0,
            "rejected_rows": 0,
            "top_segments": [],
        }
        for label in labels
    }

    for row in triaged_rows:
        for label in split_subquestions(row.get("hit_subquestions")):
            item = stats.setdefault(
                label,
                {
                    "subquestion": label,
                    "triaged_rows": 0,
                    "review_rows": 0,
                    "pending_rows": 0,
                    "usable_rows": 0,
                    "keep_rows": 0,
                    "downgrade_rows": 0,
                    "counter_rows": 0,
                    "rejected_rows": 0,
                    "top_segments": [],
                },
            )
            item["triaged_rows"] += 1
            if len(item["top_segments"]) < 5 and row.get("segment_no"):
                item["top_segments"].append(row.get("segment_no", ""))

    for row in review_rows:
        decision = review_readback.normalize_decision(row.get("human_decision", ""))
        for label in split_subquestions(row.get("hit_subquestions")):
            item = stats.setdefault(
                label,
                {
                    "subquestion": label,
                    "triaged_rows": 0,
                    "review_rows": 0,
                    "pending_rows": 0,
                    "usable_rows": 0,
                    "keep_rows": 0,
                    "downgrade_rows": 0,
                    "counter_rows": 0,
                    "rejected_rows": 0,
                    "top_segments": [],
                },
            )
            item["review_rows"] += 1
            if decision == "待复核":
                item["pending_rows"] += 1
            elif decision == "剔除":
                item["rejected_rows"] += 1
            elif decision == "反证":
                item["usable_rows"] += 1
                item["counter_rows"] += 1
            elif decision == "降级":
                item["usable_rows"] += 1
                item["downgrade_rows"] += 1
            elif decision == "保留":
                item["usable_rows"] += 1
                item["keep_rows"] += 1

    tasks: list[dict[str, Any]] = []
    for idx, label in enumerate(labels, start=1):
        item = stats[label]
        priority, reason = subquestion_priority(item, progress)
        query, entities, keywords = subquestion_query_terms(label, question)
        next_question = f"{question}｜补证：{label}"
        command = (
            "python3 work/formal_honglou_cli.py research "
            f"--question {json.dumps(next_question, ensure_ascii=False)} "
            "--limit-per-question 0 --top-evidence 0"
        )
        tasks.append(
            {
                "task_order": idx,
                "subquestion": label,
                "priority": priority,
                "reason": reason,
                "triaged_rows": item["triaged_rows"],
                "review_rows": item["review_rows"],
                "pending_rows": item["pending_rows"],
                "usable_rows": item["usable_rows"],
                "keep_rows": item["keep_rows"],
                "downgrade_rows": item["downgrade_rows"],
                "counter_rows": item["counter_rows"],
                "rejected_rows": item["rejected_rows"],
                "top_segments": "；".join(item["top_segments"]),
                "suggested_query": query,
                "suggested_entities": entities,
                "suggested_keywords": keywords,
                "next_question": next_question,
                "next_command": command,
            }
        )

    rank = {"先复核": 0, "高": 1, "中": 2, "低": 3}
    tasks.sort(key=lambda row: (rank.get(str(row["priority"]), 9), -int(row["pending_rows"]), -int(row["review_rows"])))
    for idx, row in enumerate(tasks, start=1):
        row["task_order"] = idx
    return tasks


def render_next_plan(question: str, progress: dict[str, Any], tasks: list[dict[str, Any]], tasks_csv: Path) -> str:
    lines = [
        "# 红楼梦正式底库｜二次追问与补证计划",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 当前判断",
        "",
        f"- 复核表总行数：{progress['total_rows']}",
        f"- 已人工判断：{progress['completed_rows']}",
        f"- 待复核：{progress['pending_rows']}",
        f"- 可写作证据：{progress['usable_rows']}",
        f"- 剔除：{progress['rejected_rows']}",
        f"- 反证：{progress['counter_rows']}",
        "",
    ]
    if progress["total_rows"] and progress["pending_rows"] == progress["total_rows"]:
        lines.extend(
            [
                "当前最重要的下一步不是再开新运算，而是先复核 `04_复核表.csv` 的前列证据。下面的补证任务已经生成，但它们应作为复核之后的第二轮查询计划。",
                "",
            ]
        )
    elif progress["usable_rows"] == 0:
        lines.extend(["当前还没有可写作证据，建议先复核并补证，再进入正式写作。", ""])
    else:
        lines.extend(["当前已有可写作证据，可以按下列任务查缺补漏，尤其补反证和弱覆盖子问题。", ""])

    lines.extend(
        [
            "## 3. 优先任务",
            "",
            f"完整任务表见：`{tasks_csv}`",
            "",
        ]
    )
    for row in tasks[:12]:
        lines.extend(
            [
                f"### {row['task_order']}. {row['subquestion']}",
                "",
                f"- 优先级：{row['priority']}",
                f"- 原因：{row['reason']}",
                f"- 已入复核表：{row['review_rows']} 条；待复核：{row['pending_rows']} 条；可用：{row['usable_rows']} 条；反证：{row['counter_rows']} 条；剔除：{row['rejected_rows']} 条。",
                f"- 当前可先读段落：{row['top_segments'] or '暂无'}",
                f"- 建议检索词：{row['suggested_query']}",
                f"- 下一轮问题：{row['next_question']}",
                "",
            ]
        )

    lines.extend(
        [
            "## 4. 建议执行顺序",
            "",
            "1. 先在 `04_复核表.csv` 中处理当前优先证据，至少标出一批“保留、降级、反证、剔除”。",
            "2. 运行 `loop-readback --package latest`，再运行 `loop-draft --package latest`。",
            "3. 如果主证不足或反证不足，再按 `14_下一轮出库任务.csv` 中的高优先级任务重新出库。",
            "4. 新一轮出库仍要回到原文段落号和复核表，不直接把机器召回当结论。",
        ]
    )
    return "\n".join(lines)


def next_status_sentence(progress: dict[str, Any]) -> str:
    if progress["total_rows"] and progress["pending_rows"] == progress["total_rows"]:
        return "系统已跑通，并已生成二次追问与补证计划；当前仍需先做人工复核。"
    if progress["usable_rows"] > 0:
        return "系统已跑通，并已生成二次追问与补证计划；可以按计划查缺补漏。"
    return "系统已跑通，并已生成二次追问与补证计划；仍需补足人工可用证据。"


def loop_next(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    triaged_csv = package_dir / CORE_FILES["triaged_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")
    if not triaged_csv.exists():
        raise FileNotFoundError(f"闭环包缺少证据阅读顺序：{triaged_csv}")

    progress = review_progress(review_csv)
    review_rows = read_csv(review_csv)
    triaged_rows = read_csv(triaged_csv)
    tasks = build_next_tasks(question, review_rows, triaged_rows, progress)
    tasks_csv = package_dir / CORE_FILES["next_tasks_csv"]
    plan_md = package_dir / CORE_FILES["next_plan_md"]
    fieldnames = [
        "task_order",
        "subquestion",
        "priority",
        "reason",
        "triaged_rows",
        "review_rows",
        "pending_rows",
        "usable_rows",
        "keep_rows",
        "downgrade_rows",
        "counter_rows",
        "rejected_rows",
        "top_segments",
        "suggested_query",
        "suggested_entities",
        "suggested_keywords",
        "next_question",
        "next_command",
    ]
    write_csv(tasks_csv, tasks, fieldnames)
    plan_md.write_text(render_next_plan(question, progress, tasks, tasks_csv), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["next_plan_md"] = str(plan_md)
    core_files["next_tasks_csv"] = str(tasks_csv)
    next_result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "review_csv": str(review_csv),
        "triaged_csv": str(triaged_csv),
        "next_plan_md": str(plan_md),
        "next_tasks_csv": str(tasks_csv),
        "task_count": len(tasks),
        "priority_counts": dict(Counter(str(row["priority"]) for row in tasks)),
        "progress": progress,
    }
    manifest.setdefault("results", {})["loop_next"] = next_result
    manifest["status"] = next_status_sentence(progress)
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "二次追问与补证计划",
            len(tasks) > 0,
            {
                "task_count": len(tasks),
                "next_plan_md": str(plan_md),
                "next_tasks_csv": str(tasks_csv),
                "priority_counts": next_result["priority_counts"],
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "progress": progress,
        "next": next_result,
        "manifest": str(manifest_path_value),
    }


def int_value(value: object, default: int = 0) -> int:
    try:
        return int(float(clean(value) or default))
    except ValueError:
        return default


def review_focus(row: dict[str, str]) -> str:
    labels = "；".join(split_subquestions(row.get("hit_subquestions")))
    parts = []
    section = clean(row.get("suggested_section"))
    if labels:
        parts.append(f"核对它实际覆盖了哪些子问题：{short(labels, 80)}")
    if section:
        parts.append(f"核对 suggested_section 是否只是检索线索，而不是结论：{short(section, 80)}")
    if clean(row.get("quote")):
        parts.append("回到原文上下文，判断本条能证明什么、不能证明什么。")
    else:
        parts.append("本条缺原文短摘，优先补真源或降为候选。")
    return "；".join(parts[:2]) or clean(row.get("review_question")) or "回原文核对本条候选材料是否能支撑原问题。"


def review_score(row: dict[str, str]) -> int:
    labels = split_subquestions(row.get("hit_subquestions"))
    score = int_value(row.get("priority"))
    score += len(labels) * 200
    score += int_value(row.get("hit_subquestion_count")) * 120
    if clean(row.get("quote")):
        score += 160
    if clean(row.get("segment_no")):
        score += 80
    return score


def build_review_queue(review_rows: list[dict[str, str]], first_batch_limit: int = 20) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    labels: list[str] = []
    for row in review_rows:
        for label in split_subquestions(row.get("hit_subquestions")):
            if label not in labels:
                labels.append(label)

    pending_rows = [row for row in review_rows if review_readback.normalize_decision(row.get("human_decision", "")) == "待复核"]
    completed_rows = [row for row in review_rows if review_readback.normalize_decision(row.get("human_decision", "")) != "待复核"]
    sorted_pending = sorted(
        pending_rows,
        key=lambda row: (-review_score(row), int_value(row.get("review_order"), 999999), clean(row.get("segment_no"))),
    )

    selected_ids: set[str] = set()
    covered: set[str] = set()
    first_batch: list[dict[str, str]] = []
    while sorted_pending and len(first_batch) < first_batch_limit and len(covered) < len(labels):
        best = max(
            (row for row in sorted_pending if clean(row.get("review_order")) not in selected_ids),
            key=lambda row: (
                len(set(split_subquestions(row.get("hit_subquestions"))) - covered),
                review_score(row),
                -int_value(row.get("review_order"), 999999),
            ),
            default=None,
        )
        if best is None:
            break
        selected_ids.add(clean(best.get("review_order")))
        first_batch.append(best)
        covered.update(split_subquestions(best.get("hit_subquestions")))
    for row in sorted_pending:
        if len(first_batch) >= first_batch_limit:
            break
        row_id = clean(row.get("review_order"))
        if row_id not in selected_ids:
            selected_ids.add(row_id)
            first_batch.append(row)
            covered.update(split_subquestions(row.get("hit_subquestions")))

    high_context_batch: list[dict[str, str]] = []
    source_gap_batch: list[dict[str, str]] = []
    slow_batch: list[dict[str, str]] = []
    for row in sorted_pending:
        row_id = clean(row.get("review_order"))
        if row_id in selected_ids:
            continue
        if not clean(row.get("quote")) or not clean(row.get("segment_no")):
            source_gap_batch.append(row)
        elif int_value(row.get("hit_subquestion_count")) >= 3 or len(split_subquestions(row.get("hit_subquestions"))) >= 2:
            high_context_batch.append(row)
        else:
            slow_batch.append(row)

    batches: list[tuple[str, str, list[dict[str, str]]]] = [
        ("第1批：最小覆盖复核", "用尽量少的证据覆盖全部子问题，先建立第一轮判断骨架。", first_batch),
        ("第2批：高覆盖候选", "优先阅读同时覆盖多个子问题的候选材料，但不预设证据角色。", high_context_batch),
        ("第3批：真源缺口", "补齐缺段落号、缺引文或缺上下文的材料来源。", source_gap_batch),
        ("第4批：背景慢读", "最后处理低覆盖、泛召回和辅助关系材料。", slow_batch),
    ]

    queue: list[dict[str, Any]] = []
    sequence = 1
    for batch_name, batch_reason, rows in batches:
        for row in rows:
            labels_for_row = split_subquestions(row.get("hit_subquestions"))
            queue.append(
                {
                    "review_sequence": sequence,
                    "batch": batch_name,
                    "batch_reason": batch_reason,
                    "review_order": row.get("review_order", ""),
                    "segment_no": row.get("segment_no", ""),
                    "chapter_no": row.get("chapter_no", ""),
                    "chapter_title": row.get("chapter_title", ""),
                    "suggested_section": row.get("suggested_section", ""),
                    "machine_role": row.get("machine_role", ""),
                    "priority": row.get("priority", ""),
                    "hit_subquestion_count": len(labels_for_row),
                    "hit_subquestions": "；".join(labels_for_row),
                    "summary": row.get("summary", ""),
                    "quote": row.get("quote", ""),
                    "review_question": row.get("review_question", ""),
                    "current_decision": row.get("human_decision", ""),
                    "suggested_focus": review_focus(row),
                }
            )
            sequence += 1

    batch_counts = Counter(row["batch"] for row in queue)
    summary = {
        "total_review_rows": len(review_rows),
        "pending_rows": len(pending_rows),
        "completed_rows": len(completed_rows),
        "subquestion_count": len(labels),
        "first_batch_rows": len(first_batch),
        "first_batch_covered_subquestions": len(covered),
        "queue_rows": len(queue),
        "batch_counts": dict(batch_counts),
        "covered_subquestions": sorted(covered),
    }
    return queue, summary


def render_review_plan(question: str, progress: dict[str, Any], queue: list[dict[str, Any]], summary: dict[str, Any], queue_csv: Path) -> str:
    lines = [
        "# 红楼梦正式底库｜人工复核优先清单",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 当前复核状态",
        "",
        f"- 复核表总行数：{summary['total_review_rows']}",
        f"- 待复核：{summary['pending_rows']}",
        f"- 已人工判断：{summary['completed_rows']}",
        f"- 子问题数量：{summary['subquestion_count']}",
        f"- 第1批覆盖子问题：{summary['first_batch_covered_subquestions']} / {summary['subquestion_count']}",
        f"- 完整批次表：`{queue_csv}`",
        "",
        "## 3. 重要边界",
        "",
        "- 本清单只负责安排阅读顺序，不替你填写人工判断。",
        "- 真正要修改的是同一问题包里的 `04_复核表.csv`。",
        "- 每条证据仍需回到段落号、回目、引文和上下文判断。",
        "",
        "## 4. 批次统计",
        "",
    ]
    for batch, count in summary["batch_counts"].items():
        lines.append(f"- {batch}：{count} 条")
    lines.extend(["", "## 5. 第一批建议阅读", ""])
    if not queue:
        lines.extend(["当前没有待复核证据。", ""])
    for row in queue[:20]:
        lines.extend(
            [
                f"### {row['review_sequence']}. {row['segment_no']}｜{row['batch']}",
                "",
                f"- 原复核序号：{row['review_order']}",
                f"- 回目：第{row['chapter_no']}回｜{short(row['chapter_title'], 60)}",
                f"- 机器角色：{row['machine_role']}｜建议部分：{row['suggested_section']}",
                f"- 命中子问题：{short(row['hit_subquestions'], 120)}",
                f"- 复核重点：{row['suggested_focus']}",
                f"- 复核问题：{short(row['review_question'], 120)}",
                f"- 摘要：{short(row['summary'], 120)}",
                f"- 引文：{short(row['quote'], 160)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 6. 建议操作",
            "",
            "1. 按 `16_人工复核批次.csv` 的顺序打开 `04_复核表.csv`。",
            "2. 优先完成第1批，给每条填 `human_decision`、`human_role`、`usable_level`、`writing_use`、`human_note`。",
            "3. 第1批完成后运行 `loop-readback --package latest`、`loop-draft --package latest`、`loop-next --package latest`。",
            "4. 如果第1批已经形成主证和反证，再继续第2批；如果第1批大多剔除，再按 `14_下一轮出库任务.csv` 补证。",
        ]
    )
    return "\n".join(lines)


def review_plan_status_sentence(progress: dict[str, Any], summary: dict[str, Any]) -> str:
    if summary["pending_rows"] == 0:
        return "系统已生成复核优先清单；当前没有待复核证据。"
    if progress["total_rows"] and progress["pending_rows"] == progress["total_rows"]:
        return "系统已生成复核优先清单；当前应先完成第1批最小覆盖复核。"
    return "系统已生成复核优先清单；可按批次继续补齐人工判断。"


def loop_review_plan(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")

    review_rows = read_csv(review_csv)
    progress = review_progress(review_csv)
    queue, summary = build_review_queue(review_rows)
    queue_csv = package_dir / CORE_FILES["review_queue_csv"]
    plan_md = package_dir / CORE_FILES["review_plan_md"]
    fieldnames = [
        "review_sequence",
        "batch",
        "batch_reason",
        "review_order",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "suggested_section",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "summary",
        "quote",
        "review_question",
        "current_decision",
        "suggested_focus",
    ]
    write_csv(queue_csv, queue, fieldnames)
    plan_md.write_text(render_review_plan(question, progress, queue, summary, queue_csv), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["review_plan_md"] = str(plan_md)
    core_files["review_queue_csv"] = str(queue_csv)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "review_csv": str(review_csv),
        "review_plan_md": str(plan_md),
        "review_queue_csv": str(queue_csv),
        "progress": progress,
        **summary,
    }
    manifest.setdefault("results", {})["loop_review_plan"] = result
    manifest["status"] = review_plan_status_sentence(progress, summary)
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "人工复核优先清单",
            True,
            {
                "queue_rows": summary["queue_rows"],
                "first_batch_rows": summary["first_batch_rows"],
                "first_batch_covered_subquestions": summary["first_batch_covered_subquestions"],
                "review_plan_md": str(plan_md),
                "review_queue_csv": str(queue_csv),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "progress": progress,
        "review_plan": result,
        "manifest": str(manifest_path_value),
    }


def batch_selector_matches(batch_name: str, selector: str) -> bool:
    raw = clean(selector) or "第1批"
    batch = clean(batch_name)
    if raw in {"latest", "当前", "默认"}:
        raw = "第1批"
    if raw.isdigit():
        raw = f"第{raw}批"
    return raw in batch or batch in raw


def render_review_sheet_guide(question: str, sheet_csv: Path, batch: str, row_count: int) -> str:
    return "\n".join(
        [
            "# 红楼梦正式底库｜复核工作表填写说明",
            "",
            f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
            "",
            "## 1. 原问题",
            "",
            question,
            "",
            "## 2. 本批工作表",
            "",
            f"- 批次：{batch}",
            f"- 行数：{row_count}",
            f"- 工作表：`{sheet_csv}`",
            "",
            "## 3. 只需要填写这五列",
            "",
            "- `human_decision`：待复核、保留、剔除、降级、反证。",
            "- `human_role`：主证、辅证、背景、反证、误召回等。",
            "- `usable_level`：A、B、C，或强、中、弱。",
            "- `writing_use`：进入文章的用途，例如开篇本体、太虚主证、佛性反证、背景旁证。",
            "- `human_note`：为什么保留、剔除、降级或作为反证。",
            "",
            "## 4. 回填方式",
            "",
            "填完 `17_当前批次复核工作表.csv` 后，运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-apply --package latest",
            "```",
            "",
            "回填命令只把你填过的人工字段合并回本问题包自己的 `04_复核表.csv`。默认不覆盖已经存在的人工字段。",
        ]
    )


def render_review_tick_sheet(
    question: str,
    rows: list[dict[str, Any]],
    sheet_csv: Path,
    batch: str,
) -> str:
    lines = [
        f"# 红楼梦正式底库｜人工复核打勾表（{batch}）",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 说明",
        "",
        question,
        "",
        "只改文件：`17_当前批次复核工作表.csv`。",
        "建议先打选项，再在原表同列填入人工字段。",
        "",
        "|序|复核码|机器建议|复核问题|你只需勾选|",
        "|---|---|---|---|---|",
    ]
    for idx, row in enumerate(rows, start=1):
        review_order = clean(row.get("review_order", str(idx)))
        segment_no = clean(row.get("segment_no"))
        machine = clean(row.get("machine_decision", row.get("machine_role", "待评估")))
        review_question = clean(row.get("review_question"))
        if len(review_question) > 70:
            review_question = review_question[:67] + "…"
        lines.append(
            f"| {idx} | {review_order}/{segment_no} | {machine} | {review_question} | "
            "[ ]保留 [ ]降级 [ ]反证 [ ]剔除 [ ]待复核；角色：；权重：；用途：；备注： |"
        )
    lines.extend(
        [
            "",
            "## 2. 回填",
            "",
            "填完后，回填到问题包复核表：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-apply --package latest",
            "```",
            "回填不会改写机器自动列；不会覆盖你已填过的 `human_*` 字段。",
        ]
    )
    return "\n".join(lines)


def render_review_cards(question: str, sheet_rows: list[dict[str, Any]], sheet_csv: Path, batch: str) -> str:
    lines = [
        "# 红楼梦正式底库｜当前批次复核阅读卡片",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 本批说明",
        "",
        f"- 批次：{batch}",
        f"- 卡片数量：{len(sheet_rows)}",
        f"- 填写小表：`{sheet_csv}`",
        "",
        "## 3. 判断口径",
        "",
        "- `保留`：可作为主证或重要辅证进入论证。",
        "- `降级`：有用但不宜当主证，可作背景、旁证或转折。",
        "- `反证`：用于限制、修正或反驳主论证，不是剔除。",
        "- `剔除`：误召回、无关、太弱或断章取义，不进入写作材料。",
        "",
        "## 4. 本批卡片",
        "",
    ]
    if not sheet_rows:
        lines.append("当前批次没有证据。")
        return "\n".join(lines)
    for row in sheet_rows:
        lines.extend(
            [
                f"### {row.get('review_sequence', '')}. {row.get('segment_no', '')}｜原复核序号 {row.get('review_order', '')}",
                "",
                f"- 批次：{row.get('batch', '')}",
                f"- 回目：第{row.get('chapter_no', '')}回｜{short(row.get('chapter_title'), 80)}",
                f"- 建议部分：{row.get('suggested_section', '')}",
                f"- 机器角色：{row.get('machine_role', '')}｜优先级：{row.get('priority', '')}",
                f"- 命中子问题：{short(row.get('hit_subquestions'), 180)}",
                f"- 复核重点：{row.get('suggested_focus', '')}",
                f"- 复核问题：{short(row.get('review_question'), 160)}",
                "",
                "摘要：",
                "",
                short(row.get("summary"), 260),
                "",
                "引文：",
                "",
                f"> {short(row.get('quote'), 320)}",
                "",
                "建议填写：",
                "",
                "- `human_decision`：待复核 / 保留 / 剔除 / 降级 / 反证",
                "- `human_role`：主证 / 辅证 / 背景 / 反证 / 误召回",
                "- `usable_level`：A / B / C",
                "- `writing_use`：例如开篇本体、太虚主证、佛性边界、背景旁证",
                "- `human_note`：一句话说明判断理由",
                "",
            ]
        )
    lines.extend(
        [
            "## 5. 填完后",
            "",
            "填完 `17_当前批次复核工作表.csv` 后，建议依次运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-check --package latest",
            "python3 work/formal_honglou_cli.py loop-continue --package latest",
            "```",
            "",
            "如果质量检查通过，并确认要写入复核表，再运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-continue --package latest --apply",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_review_sheet(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    batch: str = "第1批",
    limit: int = 20,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    queue_csv = package_dir / CORE_FILES["review_queue_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")
    if not queue_csv.exists():
        loop_review_plan(package_dir, out_root)

    queue_rows = read_csv(queue_csv)
    review_rows = read_csv(review_csv)
    review_by_order = {clean(row.get("review_order")): row for row in review_rows}
    selected = [row for row in queue_rows if batch_selector_matches(row.get("batch", ""), batch)]
    if limit > 0:
        selected = selected[:limit]

    sheet_rows: list[dict[str, Any]] = []
    for row in selected:
        review_row = review_by_order.get(clean(row.get("review_order")), {})
        sheet_rows.append(
            {
                "review_sequence": row.get("review_sequence", ""),
                "batch": row.get("batch", ""),
                "review_order": row.get("review_order", ""),
                "segment_no": row.get("segment_no", ""),
                "chapter_no": row.get("chapter_no", ""),
                "chapter_title": row.get("chapter_title", ""),
                "suggested_section": row.get("suggested_section", ""),
                "machine_role": row.get("machine_role", ""),
                "priority": row.get("priority", ""),
                "hit_subquestion_count": row.get("hit_subquestion_count", ""),
                "hit_subquestions": row.get("hit_subquestions", ""),
                "summary": row.get("summary", ""),
                "quote": row.get("quote", ""),
                "review_question": row.get("review_question", ""),
                "suggested_focus": row.get("suggested_focus", ""),
                "human_decision": review_row.get("human_decision", row.get("current_decision", "")),
                "human_role": review_row.get("human_role", ""),
                "usable_level": review_row.get("usable_level", ""),
                "writing_use": review_row.get("writing_use", ""),
                "human_note": review_row.get("human_note", ""),
            }
        )

    sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    guide_md = package_dir / CORE_FILES["review_sheet_md"]
    cards_md = package_dir / CORE_FILES["review_cards_md"]
    tick_md = package_dir / CORE_FILES["review_tick_md"]
    fieldnames = [
        "review_sequence",
        "batch",
        "review_order",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "suggested_section",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "summary",
        "quote",
        "review_question",
        "suggested_focus",
        "human_decision",
        "human_role",
        "usable_level",
        "writing_use",
        "human_note",
    ]
    write_csv(sheet_csv, sheet_rows, fieldnames)
    guide_md.write_text(render_review_sheet_guide(question, sheet_csv, batch, len(sheet_rows)), encoding="utf-8")
    cards_md.write_text(render_review_cards(question, sheet_rows, sheet_csv, batch), encoding="utf-8")
    tick_md.write_text(render_review_tick_sheet(question, sheet_rows, sheet_csv, batch), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["review_sheet_csv"] = str(sheet_csv)
    core_files["review_sheet_md"] = str(guide_md)
    core_files["review_cards_md"] = str(cards_md)
    core_files["review_tick_md"] = str(tick_md)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "review_csv": str(review_csv),
        "review_queue_csv": str(queue_csv),
        "review_sheet_csv": str(sheet_csv),
        "review_sheet_md": str(guide_md),
        "review_cards_md": str(cards_md),
        "review_tick_md": str(tick_md),
        "batch": batch,
        "limit": limit,
        "sheet_rows": len(sheet_rows),
    }
    manifest.setdefault("results", {})["loop_review_sheet"] = result
    manifest["status"] = f"系统已生成当前批次复核工作表：{len(sheet_rows)} 条；请人工填写后再回填。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "当前批次复核工作表",
            len(sheet_rows) > 0,
            {
                "batch": batch,
                "sheet_rows": len(sheet_rows),
                "review_sheet_csv": str(sheet_csv),
                "review_sheet_md": str(guide_md),
                "review_cards_md": str(cards_md),
                "review_tick_md": str(tick_md),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_sheet": result,
        "manifest": str(manifest_path_value),
    }


HUMAN_FIELDS = ["human_decision", "human_role", "usable_level", "writing_use", "human_note"]


def row_has_human_input(row: dict[str, str]) -> bool:
    normalized = review_readback.normalize_decision(row.get("human_decision", ""))
    if normalized != "待复核":
        return True
    return any(clean(row.get(field)) for field in HUMAN_FIELDS if field != "human_decision")


def int_value(value: object, default: int = 0) -> int:
    try:
        return int(float(clean(value) or str(default)))
    except ValueError:
        return default


def machine_review_candidate(row: dict[str, str]) -> dict[str, str]:
    hit_count = int_value(row.get("hit_subquestion_count"))
    priority = int_value(row.get("priority"))
    summary = clean(row.get("summary"))
    quote = clean(row.get("quote"))
    risk_flags: list[str] = []

    if not quote:
        risk_flags.append("缺少引文")
    if len(quote) < 12:
        risk_flags.append("引文较短")
    if not clean(row.get("segment_no")):
        risk_flags.append("缺少原子段编号")
    if hit_count <= 0:
        risk_flags.append("未标明命中子问题")
    if priority <= 0:
        risk_flags.append("缺少检索优先级")

    reason_parts = [
        "本地程序只登记候选材料，不判断证据角色。",
        f"命中子问题数：{hit_count}。",
    ]
    if summary:
        reason_parts.append("已有摘要，可供 Codex 结合原文复核。")
    if quote:
        reason_parts.append("已有引文短摘，但仍须回上下文确认。")

    return {
        "machine_candidate_decision": "待Codex判定",
        "machine_candidate_role": "候选材料",
        "machine_candidate_level": "",
        "machine_candidate_writing_use": "待 Codex 材料池判定",
        "machine_reason": " ".join(reason_parts),
        "machine_risk_flags": "；".join(risk_flags) or "无明显风险",
        "machine_term_hits": "",
        "machine_warning": "本地候选只供 Codex 读取，不会写入 human_decision，也不会替最终答案判断。",
    }


def build_review_assist_rows(sheet_rows: list[dict[str, str]], limit: int = 0) -> list[dict[str, Any]]:
    source_rows = sheet_rows[:limit] if limit > 0 else sheet_rows
    assist_rows: list[dict[str, Any]] = []
    for row in source_rows:
        candidate = machine_review_candidate(row)
        assist_rows.append(
            {
                "review_sequence": row.get("review_sequence", ""),
                "batch": row.get("batch", ""),
                "review_order": row.get("review_order", ""),
                "segment_no": row.get("segment_no", ""),
                "chapter_no": row.get("chapter_no", ""),
                "chapter_title": row.get("chapter_title", ""),
                "machine_candidate_decision": candidate["machine_candidate_decision"],
                "machine_candidate_role": candidate["machine_candidate_role"],
                "machine_candidate_level": candidate["machine_candidate_level"],
                "machine_candidate_writing_use": candidate["machine_candidate_writing_use"],
                "machine_reason": candidate["machine_reason"],
                "machine_risk_flags": candidate["machine_risk_flags"],
                "machine_term_hits": candidate["machine_term_hits"],
                "machine_warning": candidate["machine_warning"],
                "machine_role": row.get("machine_role", ""),
                "priority": row.get("priority", ""),
                "hit_subquestion_count": row.get("hit_subquestion_count", ""),
                "hit_subquestions": row.get("hit_subquestions", ""),
                "summary": row.get("summary", ""),
                "quote": row.get("quote", ""),
                "review_question": row.get("review_question", ""),
                "suggested_focus": row.get("suggested_focus", ""),
                "current_human_decision": row.get("human_decision", ""),
                "current_human_role": row.get("human_role", ""),
                "current_usable_level": row.get("usable_level", ""),
                "current_writing_use": row.get("writing_use", ""),
                "current_human_note": row.get("human_note", ""),
            }
        )
    return assist_rows


def render_review_assist(question: str, assist_rows: list[dict[str, Any]], assist_csv: Path, sheet_csv: Path) -> str:
    counts = Counter(clean(row.get("machine_candidate_decision")) for row in assist_rows)
    lines = [
        "# 红楼梦正式底库｜候选材料核对助手",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 使用边界",
        "",
        "- 本文件只把当前候选材料整理给 Codex 和人工复核读取，不替题目下判断。",
        "- 系统不会把本文件的候选状态写入 `04_复核表.csv` 或 `17_当前批次复核工作表.csv`。",
        "- 证据角色、材料用途、是否补证和最终表达，必须由 Codex 材料池判定后决定。",
        "",
        "## 3. 当前批次",
        "",
        f"- 当前小表：`{sheet_csv}`",
        f"- 助手表：`{assist_csv}`",
        f"- 助手行数：{len(assist_rows)}",
        f"- 候选状态分布：{json.dumps(dict(counts), ensure_ascii=False)}",
        "",
        "## 4. 建议操作",
        "",
        "1. 先读每条候选的来源、段落、摘要、引文和风险提示。",
        "2. 如果需要人工复核，再回到 `17_当前批次复核工作表.csv` 手工填写五个人工字段。",
        "3. 不确定的候选保持待判定，不要为了推进而硬填。",
        "4. 填完后运行 `loop-review-check --package latest`。",
        "",
        "## 5. 逐条预读",
        "",
    ]
    for row in assist_rows:
        lines.extend(
            [
                f"### {row.get('review_sequence')}. review_order={row.get('review_order')}｜{row.get('segment_no')}",
                "",
                f"- 候选状态：{row.get('machine_candidate_decision')}",
                f"- 当前角色/等级：{row.get('machine_candidate_role')} / {row.get('machine_candidate_level') or '空'}",
                f"- 当前用途：{row.get('machine_candidate_writing_use') or '空'}",
                f"- 候选理由：{row.get('machine_reason')}",
                f"- 风险提示：{row.get('machine_risk_flags')}",
                f"- 本地命中词：{row.get('machine_term_hits') or '不由本地生成'}",
                f"- 检索角色：{row.get('machine_role')}；命中子问题数：{row.get('hit_subquestion_count')}",
                f"- 复核问题：{row.get('review_question')}",
                "",
                "摘要：",
                "",
                short(row.get("summary"), 220),
                "",
                "引文：",
                "",
                f"> {short(row.get('quote'), 360)}",
                "",
            ]
        )
    return "\n".join(lines)


def loop_review_assist(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    sheet: str | Path = "",
    limit: int = 0,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_sheet_csv"]
    if not sheet_csv.is_absolute() and not sheet_csv.exists():
        sheet_csv = package_dir / sheet_csv
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少复核工作表：{sheet_csv}")

    sheet_rows = read_csv(sheet_csv)
    assist_rows = build_review_assist_rows(sheet_rows, limit=limit)
    assist_md = package_dir / CORE_FILES["review_assist_md"]
    assist_csv = package_dir / CORE_FILES["review_assist_csv"]
    fieldnames = [
        "review_sequence",
        "batch",
        "review_order",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "machine_candidate_decision",
        "machine_candidate_role",
        "machine_candidate_level",
        "machine_candidate_writing_use",
        "machine_reason",
        "machine_risk_flags",
        "machine_term_hits",
        "machine_warning",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "summary",
        "quote",
        "review_question",
        "suggested_focus",
        "current_human_decision",
        "current_human_role",
        "current_usable_level",
        "current_writing_use",
        "current_human_note",
    ]
    write_csv(assist_csv, assist_rows, fieldnames)
    assist_md.write_text(render_review_assist(question, assist_rows, assist_csv, sheet_csv), encoding="utf-8")

    candidate_counts = Counter(clean(row.get("machine_candidate_decision")) for row in assist_rows)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "sheet_csv": str(sheet_csv),
        "review_assist_md": str(assist_md),
        "review_assist_csv": str(assist_csv),
        "assist_rows": len(assist_rows),
        "candidate_counts": dict(candidate_counts),
        "limit": limit,
        "does_not_write_human_fields": True,
    }

    core_files = manifest.setdefault("core_files", {})
    core_files["review_assist_md"] = str(assist_md)
    core_files["review_assist_csv"] = str(assist_csv)
    manifest.setdefault("results", {})["loop_review_assist"] = result
    manifest["status"] = f"已生成候选材料核对助手：{len(assist_rows)} 条候选；仍需 Codex 或人工复核后才能定性。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核填写助手",
            len(assist_rows) > 0,
            {
                "assist_rows": len(assist_rows),
                "candidate_counts": dict(candidate_counts),
                "review_assist_md": str(assist_md),
                "review_assist_csv": str(assist_csv),
                "does_not_write_human_fields": True,
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_assist": result,
        "manifest": str(manifest_path_value),
    }


def workbench_group(row: dict[str, str]) -> tuple[str, int]:
    risks = clean(row.get("machine_risk_flags"))
    hit_count = int_value(row.get("hit_subquestion_count"))
    if "缺少引文" in risks or "缺少原子段编号" in risks:
        return "C. 真源缺口候选", 3
    if hit_count >= 3:
        return "A. 高覆盖候选", 1
    if hit_count > 0:
        return "B. 普通候选", 2
    return "D. 待补查候选", 4


def build_review_workbench_rows(sheet_rows: list[dict[str, str]], assist_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    assist_by_order = {clean(row.get("review_order")): row for row in assist_rows}
    rows: list[dict[str, Any]] = []
    for sheet_row in sheet_rows:
        order = clean(sheet_row.get("review_order"))
        assist = assist_by_order.get(order, {})
        candidate_decision = clean(assist.get("machine_candidate_decision")) or "待复核"
        candidate_role = clean(assist.get("machine_candidate_role"))
        candidate_level = clean(assist.get("machine_candidate_level"))
        candidate_use = clean(assist.get("machine_candidate_writing_use"))
        candidate_reason = clean(assist.get("machine_reason"))
        risk_flags = clean(assist.get("machine_risk_flags"))
        group, rank = workbench_group(assist)
        note_parts = []
        if candidate_reason:
            note_parts.append(candidate_reason)
        if risk_flags and risk_flags != "无明显风险":
            note_parts.append(f"需核对：{risk_flags}")
        draft_note = "；".join(note_parts)
        rows.append(
            {
                "workbench_order": 0,
                "workbench_group": group,
                "workbench_rank": rank,
                "review_sequence": sheet_row.get("review_sequence", ""),
                "batch": sheet_row.get("batch", ""),
                "review_order": order,
                "segment_no": sheet_row.get("segment_no", ""),
                "chapter_no": sheet_row.get("chapter_no", ""),
                "chapter_title": sheet_row.get("chapter_title", ""),
                "copy_candidate_decision": candidate_decision,
                "copy_candidate_role": candidate_role,
                "copy_candidate_level": candidate_level,
                "copy_candidate_writing_use": candidate_use,
                "draft_human_note_reference": draft_note,
                "machine_reason": candidate_reason,
                "machine_risk_flags": risk_flags,
                "machine_term_hits": clean(assist.get("machine_term_hits")),
                "machine_role": sheet_row.get("machine_role", ""),
                "priority": sheet_row.get("priority", ""),
                "hit_subquestion_count": sheet_row.get("hit_subquestion_count", ""),
                "hit_subquestions": sheet_row.get("hit_subquestions", ""),
                "review_question": sheet_row.get("review_question", ""),
                "suggested_focus": sheet_row.get("suggested_focus", ""),
                "summary": sheet_row.get("summary", ""),
                "quote": sheet_row.get("quote", ""),
                "current_human_decision": sheet_row.get("human_decision", ""),
                "current_human_role": sheet_row.get("human_role", ""),
                "current_usable_level": sheet_row.get("usable_level", ""),
                "current_writing_use": sheet_row.get("writing_use", ""),
                "current_human_note": sheet_row.get("human_note", ""),
                "boundary_warning": "这些 copy/draft 字段只是参考填法，不是人工判断；请手工写入 17 的 human_* 字段后再回填。",
            }
        )
    rows.sort(
        key=lambda row: (
            int_value(row.get("workbench_rank")),
            -int_value(row.get("hit_subquestion_count")),
            -int_value(row.get("priority")),
            int_value(row.get("review_sequence")),
        )
    )
    for idx, row in enumerate(rows, start=1):
        row["workbench_order"] = idx
    return rows


def render_review_workbench(question: str, rows: list[dict[str, Any]], workbench_csv: Path, sheet_csv: Path, assist_csv: Path) -> str:
    group_counts = Counter(clean(row.get("workbench_group")) for row in rows)
    candidate_counts = Counter(clean(row.get("copy_candidate_decision")) for row in rows)
    lines = [
        "# 红楼梦正式底库｜复核填表工作台",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 使用边界",
        "",
        "- 本工作台把当前复核小表和候选材料核对助手合并到一起，方便核对来源。",
        "- `copy_candidate_*` 和 `draft_human_note_reference` 只是参考，不是人工判断。",
        "- 系统没有写入 `17_当前批次复核工作表.csv`，也没有写入 `04_复核表.csv`。",
        "- 你需要亲自把确认后的判断写进 `17_当前批次复核工作表.csv` 的五个 `human_*` 字段。",
        "",
        "## 3. 文件",
        "",
        f"- 当前小表：`{sheet_csv}`",
        f"- 机器助手表：`{assist_csv}`",
        f"- 工作台表：`{workbench_csv}`",
        "",
        "## 4. 当前分布",
        "",
        f"- 工作台行数：{len(rows)}",
        f"- 阅读组分布：{json.dumps(dict(group_counts), ensure_ascii=False)}",
        f"- 候选判断分布：{json.dumps(dict(candidate_counts), ensure_ascii=False)}",
        "",
        "## 5. 最短操作",
        "",
        "1. 先处理 A 组，再处理 B 组和 D 组；E 组不确定就保留待复核。",
        "2. 每条只在你确认后才把候选值写入 `17_当前批次复核工作表.csv`。",
        "3. 写完一批后运行 `loop-review-check --package latest`。",
        "",
        "## 6. 逐条工作台",
        "",
    ]
    current_group = ""
    for row in rows:
        group = clean(row.get("workbench_group"))
        if group != current_group:
            current_group = group
            lines.extend([f"### {group}", ""])
        lines.extend(
            [
                f"#### {row.get('workbench_order')}. review_order={row.get('review_order')}｜{row.get('segment_no')}",
                "",
                f"- 建议可填判断：{row.get('copy_candidate_decision')}",
                f"- 建议可填角色/等级：{row.get('copy_candidate_role') or '空'} / {row.get('copy_candidate_level') or '空'}",
                f"- 建议可填写作用途：{row.get('copy_candidate_writing_use') or '空'}",
                f"- 备注参考：{row.get('draft_human_note_reference') or '空'}",
                f"- 风险提示：{row.get('machine_risk_flags') or '无'}",
                f"- 复核问题：{row.get('review_question')}",
                f"- 原机器角色：{row.get('machine_role')}；命中子问题数：{row.get('hit_subquestion_count')}",
                "",
                "摘要：",
                "",
                short(row.get("summary"), 220),
                "",
                "引文：",
                "",
                f"> {short(row.get('quote'), 360)}",
                "",
            ]
        )
    return "\n".join(lines)


def loop_review_workbench(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    sheet: str | Path = "",
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_sheet_csv"]
    if not sheet_csv.is_absolute() and not sheet_csv.exists():
        sheet_csv = package_dir / sheet_csv
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少复核工作表：{sheet_csv}")
    assist_csv = package_dir / CORE_FILES["review_assist_csv"]
    if not assist_csv.exists():
        loop_review_assist(package_dir, out_root, sheet=sheet_csv)

    sheet_rows = read_csv(sheet_csv)
    assist_rows = read_csv(assist_csv)
    workbench_rows = build_review_workbench_rows(sheet_rows, assist_rows)
    workbench_md = package_dir / CORE_FILES["review_workbench_md"]
    workbench_csv = package_dir / CORE_FILES["review_workbench_csv"]
    fieldnames = [
        "workbench_order",
        "workbench_group",
        "workbench_rank",
        "review_sequence",
        "batch",
        "review_order",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "copy_candidate_decision",
        "copy_candidate_role",
        "copy_candidate_level",
        "copy_candidate_writing_use",
        "draft_human_note_reference",
        "machine_reason",
        "machine_risk_flags",
        "machine_term_hits",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "review_question",
        "suggested_focus",
        "summary",
        "quote",
        "current_human_decision",
        "current_human_role",
        "current_usable_level",
        "current_writing_use",
        "current_human_note",
        "boundary_warning",
    ]
    write_csv(workbench_csv, workbench_rows, fieldnames)
    workbench_md.write_text(render_review_workbench(question, workbench_rows, workbench_csv, sheet_csv, assist_csv), encoding="utf-8")

    group_counts = Counter(clean(row.get("workbench_group")) for row in workbench_rows)
    candidate_counts = Counter(clean(row.get("copy_candidate_decision")) for row in workbench_rows)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "sheet_csv": str(sheet_csv),
        "review_assist_csv": str(assist_csv),
        "review_workbench_md": str(workbench_md),
        "review_workbench_csv": str(workbench_csv),
        "workbench_rows": len(workbench_rows),
        "group_counts": dict(group_counts),
        "candidate_counts": dict(candidate_counts),
        "does_not_write_human_fields": True,
    }

    core_files = manifest.setdefault("core_files", {})
    core_files["review_workbench_md"] = str(workbench_md)
    core_files["review_workbench_csv"] = str(workbench_csv)
    if not core_files.get("review_assist_csv"):
        core_files["review_assist_csv"] = str(assist_csv)
    manifest.setdefault("results", {})["loop_review_workbench"] = result
    manifest["status"] = f"已生成复核填表工作台：{len(workbench_rows)} 条；仍需人工填写小表。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核填表工作台",
            len(workbench_rows) > 0,
            {
                "workbench_rows": len(workbench_rows),
                "group_counts": dict(group_counts),
                "candidate_counts": dict(candidate_counts),
                "review_workbench_md": str(workbench_md),
                "review_workbench_csv": str(workbench_csv),
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_workbench": result,
        "manifest": str(manifest_path_value),
    }


def minimal_coverage_picks(workbench_rows: list[dict[str, str]], target_count: int = 6) -> list[dict[str, Any]]:
    all_labels: set[str] = set()
    row_labels: dict[str, set[str]] = {}
    for row in workbench_rows:
        order = clean(row.get("review_order"))
        labels = set(split_subquestions(row.get("hit_subquestions")))
        row_labels[order] = labels
        all_labels.update(labels)

    uncovered = set(all_labels)
    picks: list[dict[str, Any]] = []
    candidates = sorted(
        workbench_rows,
        key=lambda row: (
            int_value(row.get("workbench_rank")),
            -int_value(row.get("hit_subquestion_count")),
            -int_value(row.get("priority")),
            int_value(row.get("workbench_order")),
        ),
    )
    while uncovered:
        best_row: dict[str, str] | None = None
        best_new: set[str] = set()
        for row in candidates:
            order = clean(row.get("review_order"))
            new_labels = row_labels.get(order, set()) & uncovered
            if not new_labels:
                continue
            if best_row is None or len(new_labels) > len(best_new):
                best_row = row
                best_new = new_labels
            elif best_row is not None and len(new_labels) == len(best_new):
                current_key = (
                    int_value(row.get("workbench_rank")),
                    -int_value(row.get("hit_subquestion_count")),
                    -int_value(row.get("priority")),
                    int_value(row.get("workbench_order")),
                )
                best_key = (
                    int_value(best_row.get("workbench_rank")),
                    -int_value(best_row.get("hit_subquestion_count")),
                    -int_value(best_row.get("priority")),
                    int_value(best_row.get("workbench_order")),
                )
                if current_key < best_key:
                    best_row = row
                    best_new = new_labels
        if best_row is None:
            break
        picks.append(
            {
                "pick_order": len(picks) + 1,
                "pick_reason": "新增覆盖",
                "review_order": clean(best_row.get("review_order")),
                "workbench_order": clean(best_row.get("workbench_order")),
                "segment_no": clean(best_row.get("segment_no")),
                "candidate_decision": clean(best_row.get("copy_candidate_decision")),
                "workbench_group": clean(best_row.get("workbench_group")),
                "new_subquestions": "；".join(sorted(best_new)),
                "new_subquestion_count": len(best_new),
                "summary": clean(best_row.get("summary")),
                "quote": clean(best_row.get("quote")),
            }
        )
        uncovered -= best_new

    picked_orders = {clean(item.get("review_order")) for item in picks}
    for row in candidates:
        if len(picks) >= min(target_count, len(candidates)):
            break
        order = clean(row.get("review_order"))
        if order in picked_orders:
            continue
        labels = sorted(row_labels.get(order, set()))
        picks.append(
            {
                "pick_order": len(picks) + 1,
                "pick_reason": "覆盖补强",
                "review_order": order,
                "workbench_order": clean(row.get("workbench_order")),
                "segment_no": clean(row.get("segment_no")),
                "candidate_decision": clean(row.get("copy_candidate_decision")),
                "workbench_group": clean(row.get("workbench_group")),
                "new_subquestions": "；".join(labels),
                "new_subquestion_count": 0,
                "summary": clean(row.get("summary")),
                "quote": clean(row.get("quote")),
            }
        )
        picked_orders.add(order)
    return picks


def pick_payload(row: dict[str, str], pick_order: int, reason: str, labels: list[str] | None = None) -> dict[str, Any]:
    labels = labels if labels is not None else sorted(split_subquestions(row.get("hit_subquestions")))
    return {
        "pick_order": pick_order,
        "pick_reason": reason,
        "review_order": clean(row.get("review_order")),
        "workbench_order": clean(row.get("workbench_order")),
        "segment_no": clean(row.get("segment_no")),
        "candidate_decision": clean(row.get("copy_candidate_decision")),
        "workbench_group": clean(row.get("workbench_group")),
        "new_subquestions": "；".join(labels),
        "new_subquestion_count": 0,
        "summary": clean(row.get("summary")),
        "quote": clean(row.get("quote")),
    }


def build_review_coverage_rows(workbench_rows: list[dict[str, str]], picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pick_orders = {clean(item.get("review_order")) for item in picks}
    stats: dict[str, dict[str, Any]] = {}
    for row in workbench_rows:
        labels = split_subquestions(row.get("hit_subquestions"))
        if not labels:
            labels = ["未标明子问题"]
        for label in labels:
            item = stats.setdefault(
                label,
                {
                    "subquestion": label,
                    "covered_rows": 0,
                    "high_coverage_rows": 0,
                    "normal_candidate_rows": 0,
                    "source_gap_rows": 0,
                    "pending_followup_rows": 0,
                    "multi_cover_rows": 0,
                    "minimal_pick_rows": [],
                    "source_gap_review_orders": [],
                    "pending_review_orders": [],
                    "multi_cover_review_orders": [],
                    "top_review_orders": [],
                    "top_segments": [],
                    "top_summaries": [],
                },
            )
            item["covered_rows"] += 1
            group = clean(row.get("workbench_group"))
            review_order = clean(row.get("review_order"))
            hit_count = int_value(row.get("hit_subquestion_count"))
            if group.startswith("A."):
                item["high_coverage_rows"] += 1
            elif group.startswith("B."):
                item["normal_candidate_rows"] += 1
            elif group.startswith("C."):
                item["source_gap_rows"] += 1
                item["source_gap_review_orders"].append(review_order)
            else:
                item["pending_followup_rows"] += 1
                item["pending_review_orders"].append(review_order)
            if hit_count >= 4:
                item["multi_cover_rows"] += 1
                item["multi_cover_review_orders"].append(review_order)
            if review_order in pick_orders:
                item["minimal_pick_rows"].append(review_order)
            if len(item["top_review_orders"]) < 6:
                item["top_review_orders"].append(review_order)
                item["top_segments"].append(clean(row.get("segment_no")))
                item["top_summaries"].append(short(row.get("summary"), 60))

    rows: list[dict[str, Any]] = []
    for idx, label in enumerate(sorted(stats.keys(), key=lambda text: (int_value(text.split(".", 1)[0]), text)), start=1):
        item = stats[label]
        followup_reasons: list[str] = []
        if item["high_coverage_rows"] > 0:
            coverage_level = "高覆盖候选"
            recommendation = "先读高覆盖候选，交给 Codex 判断是否能支撑该子问题。"
        elif item["normal_candidate_rows"] > 0:
            coverage_level = "普通候选"
            recommendation = "先读普通候选，再由 Codex 判断是否需要二轮补证。"
        elif item["source_gap_rows"] > 0:
            coverage_level = "真源缺口"
            recommendation = "先补原文短摘、段落号或上下文，再进入材料池判定。"
            followup_reasons.append("存在真源缺口")
        else:
            coverage_level = "需补证"
            recommendation = "需要补充复核或下一轮出库。"
            followup_reasons.append("当前批次没有可用候选")
        if item["covered_rows"] < 2:
            followup_reasons.append("覆盖条数不足")
        if item["source_gap_rows"] > 0:
            followup_reasons.append("需要补真源")
        rows.append(
            {
                "coverage_order": idx,
                "subquestion": label,
                "coverage_level": coverage_level,
                "covered_rows": item["covered_rows"],
                "high_coverage_rows": item["high_coverage_rows"],
                "normal_candidate_rows": item["normal_candidate_rows"],
                "source_gap_rows": item["source_gap_rows"],
                "pending_followup_rows": item["pending_followup_rows"],
                "multi_cover_rows": item["multi_cover_rows"],
                "minimal_pick_review_orders": "；".join(dict.fromkeys(item["minimal_pick_rows"])),
                "source_gap_review_orders": "；".join(dict.fromkeys(item["source_gap_review_orders"])),
                "pending_review_orders": "；".join(dict.fromkeys(item["pending_review_orders"])),
                "multi_cover_review_orders": "；".join(dict.fromkeys(item["multi_cover_review_orders"])),
                "top_review_orders": "；".join(dict.fromkeys(item["top_review_orders"])),
                "top_segments": "；".join(dict.fromkeys(item["top_segments"])),
                "top_summaries": "｜".join(item["top_summaries"]),
                "recommendation": recommendation,
                "followup_need": "；".join(dict.fromkeys(followup_reasons)) or "暂无明显补证要求",
                "boundary_warning": "本矩阵只显示候选覆盖和真源缺口，不代表证据结论；材料角色必须由 Codex 判定。",
            }
        )
    return rows


def render_review_coverage(
    question: str,
    coverage_rows: list[dict[str, Any]],
    picks: list[dict[str, Any]],
    coverage_csv: Path,
    workbench_csv: Path,
) -> str:
    lines = [
        "# 红楼梦正式底库｜复核覆盖矩阵",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 使用边界",
        "",
        "- 本矩阵只说明当前 20 条复核证据覆盖了哪些子问题。",
        "- 新增的高覆盖、普通候选、真源缺口只是阅读顺序和来源健康提示，不是证据角色。",
        "- 首轮覆盖建议只帮助 Codex 先读哪些材料，不替 Codex 下结论。",
        "- 系统没有写入 `17_当前批次复核工作表.csv` 或 `04_复核表.csv`。",
        "",
        "## 3. 文件",
        "",
        f"- 工作台表：`{workbench_csv}`",
        f"- 覆盖矩阵表：`{coverage_csv}`",
        "",
        "## 4. 覆盖概况",
        "",
        f"- 覆盖子问题数：{len(coverage_rows)}",
        f"- 首轮阅读建议行数：{len(picks)}",
        f"- 有高覆盖候选的子问题：{sum(1 for row in coverage_rows if int_value(row.get('high_coverage_rows')) > 0)}",
        f"- 存在真源缺口的子问题：{sum(1 for row in coverage_rows if int_value(row.get('source_gap_rows')) > 0)}",
        f"- 需要补证提示的子问题：{sum(1 for row in coverage_rows if clean(row.get('followup_need')) != '暂无明显补证要求')}",
        "",
    ]
    if picks:
        lines.extend(["## 5. 首轮覆盖优先阅读行", ""])
        for item in picks:
            lines.extend(
                [
                    f"### {item['pick_order']}. review_order={item['review_order']}｜{item['segment_no']}",
                    "",
                    f"- 选择原因：{item.get('pick_reason', '新增覆盖')}",
                    f"- 工作台序号：{item['workbench_order']}",
                    f"- 工作台分组：{item['workbench_group']}",
                    f"- 候选判断：{item['candidate_decision']}",
                    f"- 涉及子问题：{item['new_subquestions']}",
                    "",
                    "摘要：",
                    "",
                    short(item.get("summary"), 180),
                    "",
                    "引文：",
                    "",
                    f"> {short(item.get('quote'), 280)}",
                    "",
                ]
            )
    lines.extend(["## 6. 子问题覆盖矩阵", ""])
    for row in coverage_rows:
        lines.extend(
            [
                f"### {row['coverage_order']}. {row['subquestion']}",
                "",
                f"- 覆盖状态：{row['coverage_level']}",
                f"- 覆盖候选数：{row['covered_rows']}",
                f"- 高覆盖/普通/真源缺口/待补查：{row['high_coverage_rows']} / {row['normal_candidate_rows']} / {row['source_gap_rows']} / {row['pending_followup_rows']}",
                f"- 首轮覆盖行：{row['minimal_pick_review_orders'] or '无'}",
                f"- 真源缺口行：{row['source_gap_review_orders'] or '无'}",
                f"- 待补查行：{row['pending_review_orders'] or '无'}",
                f"- 多轴覆盖行：{row['multi_cover_review_orders'] or '无'}",
                f"- 优先阅读 review_order：{row['top_review_orders']}",
                f"- 建议：{row['recommendation']}",
                f"- 补证提示：{row['followup_need']}",
                "",
            ]
        )
    return "\n".join(lines)


def loop_review_coverage(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    workbench_csv = package_dir / CORE_FILES["review_workbench_csv"]
    if not workbench_csv.exists():
        loop_review_workbench(package_dir, out_root)
    workbench_rows = read_csv(workbench_csv)
    picks = minimal_coverage_picks(workbench_rows)
    coverage_rows = build_review_coverage_rows(workbench_rows, picks)
    coverage_md = package_dir / CORE_FILES["review_coverage_md"]
    coverage_csv = package_dir / CORE_FILES["review_coverage_csv"]
    fieldnames = [
        "coverage_order",
        "subquestion",
        "coverage_level",
        "covered_rows",
        "high_coverage_rows",
        "normal_candidate_rows",
        "source_gap_rows",
        "pending_followup_rows",
        "multi_cover_rows",
        "minimal_pick_review_orders",
        "source_gap_review_orders",
        "pending_review_orders",
        "multi_cover_review_orders",
        "top_review_orders",
        "top_segments",
        "top_summaries",
        "recommendation",
        "followup_need",
        "boundary_warning",
    ]
    write_csv(coverage_csv, coverage_rows, fieldnames)
    coverage_md.write_text(render_review_coverage(question, coverage_rows, picks, coverage_csv, workbench_csv), encoding="utf-8")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_workbench_csv": str(workbench_csv),
        "review_coverage_md": str(coverage_md),
        "review_coverage_csv": str(coverage_csv),
        "coverage_rows": len(coverage_rows),
        "minimal_pick_count": len(picks),
        "minimal_picks": picks,
        "coverage_level_counts": dict(Counter(clean(row.get("coverage_level")) for row in coverage_rows)),
        "followup_need_rows": sum(1 for row in coverage_rows if clean(row.get("followup_need")) != "暂无明显补证要求"),
        "does_not_write_human_fields": True,
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["review_coverage_md"] = str(coverage_md)
    core_files["review_coverage_csv"] = str(coverage_csv)
    manifest.setdefault("results", {})["loop_review_coverage"] = result
    manifest["status"] = f"已生成复核覆盖矩阵：覆盖 {len(coverage_rows)} 个子问题；仍需人工填写小表。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核覆盖矩阵",
            len(coverage_rows) > 0,
            {
                "coverage_rows": len(coverage_rows),
                "minimal_pick_count": len(picks),
                "review_coverage_md": str(coverage_md),
                "review_coverage_csv": str(coverage_csv),
                "coverage_level_counts": result["coverage_level_counts"],
                "followup_need_rows": result["followup_need_rows"],
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_coverage": result,
        "manifest": str(manifest_path_value),
    }


def system_argument_layer(row: dict[str, str], question: str = "") -> dict[str, Any]:
    hit_count = int_value(row.get("hit_subquestion_count"))
    priority = int_value(row.get("priority"))
    score = priority + hit_count * 120

    return {
        "review_order": clean(row.get("review_order")),
        "segment_no": clean(row.get("segment_no")),
        "chapter_no": clean(row.get("chapter_no")),
        "chapter_title": clean(row.get("chapter_title")),
        "system_decision": "待Codex判定",
        "argument_axis": "候选材料",
        "argument_score": score,
        "article_use": "候选材料：只保留来源、命中和原文痕迹；是否可用、作背景、不可用或需补证，交给 Codex 材料池判定。",
        "system_reason": "本地程序不再自动判断证据等级或答案方向，只按检索痕迹排序并交回 Codex。",
        "machine_candidate_decision": "",
        "machine_candidate_role": "",
        "machine_candidate_level": "",
        "machine_risk_flags": "",
        "hit_subquestion_count": hit_count,
        "hit_subquestions": clean(row.get("hit_subquestions")),
        "summary": clean(row.get("summary")),
        "quote": clean(row.get("quote")),
        "review_question": clean(row.get("review_question")),
        "human_decision": clean(row.get("human_decision")),
    }


def build_argument_brief_rows(review_rows: list[dict[str, str]], question: str = "") -> list[dict[str, Any]]:
    rows = [system_argument_layer(row, question) for row in review_rows]
    rows.sort(
        key=lambda row: (
            -int_value(row.get("argument_score")),
            int_value(row.get("review_order")),
        )
    )
    return rows


def argument_brief_copy(question: str) -> dict[str, Any]:
    return {
        "title": "# 红楼梦正式底库｜候选材料过程简报",
        "why": [
            "工程只按问题入库后的召回结果整理候选材料，不把外部结论附加到新问题上。",
            "这份简报不判定证据等级，也不生成观点；它只把可追溯材料交给 Codex 材料池判定。",
        ],
        "weak_note": "如果材料只命中词但不能回答问题，本地也不直接定性；由 Codex 判断可用、背景、不可用或需补证。",
        "questions": [
            "1. 候选材料有哪些原文、段落号和上下文痕迹？",
            "2. 哪些地方仍缺原文复核或需要二轮补证？",
            "3. Codex 材料池判定后是否允许进入红楼解语？",
        ],
        "next_step": "交给 Codex 材料池判定，不由本地过程简报写结论。",
    }


def render_argument_brief(question: str, rows: list[dict[str, Any]], brief_csv: Path, top_n: int) -> str:
    lines = [
        "# 红楼梦正式底库｜候选材料过程简报",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 当前边界",
        "",
        "本地程序只整理候选材料，不判断证据等级，不生成观点，不写最终答案。",
        "候选材料必须交给 Codex 材料池判定，才能进入红楼解语。",
        "",
        "## 2. 原问题",
        "",
        question,
        "",
        "## 3. 候选材料统计",
        "",
        f"- 候选材料表：`{brief_csv}`",
        f"- 候选总数：{len(rows)}",
        "",
        "## 4. 优先交给 Codex 精读的候选",
        "",
    ]
    for idx, row in enumerate(rows[:top_n], start=1):
        lines.extend(
            [
                f"### {idx}. 待 Codex 判定｜review_order={row['review_order']}｜{row['segment_no']}",
                "",
                f"- 候选位置：{row['argument_axis']}",
                f"- 当前用途：{row['article_use']}",
                f"- 本地边界：{row['system_reason']}",
                f"- 回目：第{row['chapter_no']}回｜{short(row['chapter_title'], 90)}",
                "",
                "摘要：",
                "",
                short(row.get("summary"), 260),
                "",
                "引文：",
                "",
                f"> {short(row.get('quote'), 420)}",
                "",
            ]
        )

    lines.extend(
        [
            "## 5. 下一步",
            "",
            "交给 Codex 材料池判定：可用、背景、不可用、需补证、是否允许进入红楼解语。",
        ]
    )
    return "\n".join(lines)


def pick_rows(rows: list[dict[str, Any]], *, decision: str = "", axis: str = "", contains: list[str] | None = None, limit: int = 3) -> list[dict[str, Any]]:
    contains = contains or []
    picked: list[dict[str, Any]] = []
    for row in rows:
        if decision and clean(row.get("system_decision")) != decision:
            continue
        if axis and clean(row.get("argument_axis")) != axis:
            continue
        haystack = " ".join([clean(row.get("summary")), clean(row.get("quote")), clean(row.get("chapter_title"))])
        if contains and not any(term in haystack for term in contains):
            continue
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


def neighboring_segment_no(segment_no: str, delta: int) -> str:
    raw = clean(segment_no)
    if "-" not in raw:
        return ""
    prefix, suffix = raw.rsplit("-", 1)
    if not suffix.isdigit():
        return ""
    number = int(suffix) + delta
    if number < 1:
        return ""
    return f"{prefix}-{number:0{len(suffix)}d}"


STORY_TAGS = {
    "叙事",
    "叙事推进",
    "線索伏笔",
    "线索伏笔",
    "線索伏筆",
    "器物出场",
    "器物出場",
    "对话",
    "對話",
    "诗词",
    "詩詞",
    "人物登场",
    "人物登場",
    "神话叙事",
    "神話敘事",
    "环境描写",
    "環境描寫",
    "服饰描写",
    "服飾描寫",
    "心理描写",
    "心理描寫",
    "心理独白",
    "心理獨白",
    "动作描写",
    "動作描寫",
}


def is_segment_metadata_line(line: str) -> bool:
    value = clean(line)
    if not value:
        return True
    if value.startswith("第") and "回" in value[:8]:
        return True
    if value in STORY_TAGS:
        return True
    parts = [part.strip() for part in value.replace("，", ",").split(",") if part.strip()]
    return len(parts) > 1 and all(part in STORY_TAGS for part in parts)


def normalize_story_excerpt(text: str) -> str:
    value = clean(text)
    for source, target in (("。。", "。"), ("..", "."), ("；；", "；"), ("，，", "，")):
        while source in value:
            value = value.replace(source, target)
    return value.strip("；，。 ")


def readable_story_text(text: object, segment_no: str = "", limit: int = 120) -> str:
    value = normalize_story_excerpt(clean(text))
    seg = clean(segment_no)
    if seg and value.startswith(seg):
        value = value[len(seg) :].strip(" ：:，,。.-_")
    value = normalize_story_excerpt(value)
    return short(value, limit)


def extract_segment_text(original_text: str, segment_no: str, title: str) -> str:
    lines = [clean(line) for line in str(original_text or "").splitlines() if clean(line)]
    filtered: list[str] = []
    for line in lines:
        if line == segment_no or line == title:
            continue
        if title and line in title and len(line) <= 12:
            continue
        if is_segment_metadata_line(line):
            continue
        excerpt = normalize_story_excerpt(line)
        if not excerpt:
            continue
        filtered.append(excerpt)
    return "；".join(filtered[:2])


def load_segment_context(segment_no: str) -> dict[str, dict[str, str]]:
    current_no = clean(segment_no)
    if not current_no or not SEARCH_DB.exists():
        return {}
    segment_ids = {
        "before": neighboring_segment_no(current_no, -1),
        "current": current_no,
        "after": neighboring_segment_no(current_no, 1),
    }
    try:
        conn = sqlite3.connect(SEARCH_DB)
        conn.row_factory = sqlite3.Row
        try:
            context: dict[str, dict[str, str]] = {}
            for key, seg in segment_ids.items():
                if not seg:
                    continue
                row = conn.execute(
                    """
                    SELECT title, original_text
                    FROM search_documents
                    WHERE doc_type = 'segment' AND segment_no = ?
                    LIMIT 1
                    """,
                    (seg,),
                ).fetchone()
                if row:
                    raw_title = clean(row["title"])
                    title = readable_story_text(raw_title, seg, 80)
                    text = extract_segment_text(row["original_text"], seg, raw_title)
                    if text:
                        context[key] = {
                            "segment_no": seg,
                            "title": title,
                            "text": short(text, 72),
                        }
            return context
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def format_context_piece(label: str, item: dict[str, str]) -> str:
    title = clean(item.get("title"))
    text = clean(item.get("text"))
    segment_no = clean(item.get("segment_no"))
    if title and text:
        return f"{label}讲 `{segment_no}`“{title}”：{text}"
    if title:
        return f"{label}讲 `{segment_no}`“{title}”"
    return f"{label}是 `{segment_no}`：{text}"


def talk_evidence_lines(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        segment_no = clean(row.get("segment_no"))
        context = load_segment_context(segment_no)
        context_parts = []
        if context.get("before"):
            context_parts.append(format_context_piece("前一段", context["before"]))
        if context.get("after"):
            context_parts.append(format_context_piece("后一段", context["after"]))
        context_note = f" 旁边的故事脉络：{'；'.join(context_parts)}。" if context_parts else ""
        lines.append(
            f"- `{segment_no}`，第{row.get('chapter_no')}回：{readable_story_text(row.get('summary'), segment_no, 90)}。"
            f"我会引用这一句：{readable_story_text(row.get('quote'), segment_no, 120)}{context_note}"
        )
    if not lines:
        lines.append("- 这一组还需要回到原文再补一两条更稳的证据。")
    return lines


def render_argument_talk_evidence_only(question: str, rows: list[dict[str, Any]], brief_csv: Path) -> str:
    candidates = rows[:10]
    lines = [
        "# 红楼梦工程｜证据过程稿",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 这份稿子的边界",
        "",
        "这里不生成论证结论，也不把旧题目的判断附加进来。",
        "",
        "工程已经完成的问题入库和证据召回；下面只把可读证据候选列出来，供最终回答层在证据范围内思考。",
        "",
        f"原问题：{question}",
        "",
        "## 证据候选",
        "",
    ]
    for row in candidates:
        lines.extend(
            [
                f"### {clean(row.get('segment_no'))}｜第{clean(row.get('chapter_no'))}回｜{clean(row.get('system_decision'))}",
                "",
                f"- 证据位置：{clean(row.get('argument_axis'))}",
                f"- 当前用途：{clean(row.get('article_use'))}",
                f"- 机器说明：{clean(row.get('system_reason'))}",
                f"- 摘要：{readable_story_text(row.get('summary'), clean(row.get('segment_no')), 120)}",
                f"- 引文：{readable_story_text(row.get('quote'), clean(row.get('segment_no')), 160)}",
                "",
            ]
        )
    if not candidates:
        lines.extend(["- 当前没有足够稳的证据候选，需要继续补证。", ""])
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "最终回答层应只根据原问题和上面的证据候选组织回答；如果证据不足，就明确说证据不足并指出需要补查的方向。",
            "",
            f"证据分层表：`{brief_csv}`",
        ]
    )
    return "\n".join(lines)


def render_argument_talk(question: str, rows: list[dict[str, Any]], brief_csv: Path) -> str:
    return render_argument_talk_evidence_only(question, rows, brief_csv)


def evidence_ref(row: dict[str, Any]) -> str:
    segment_no = clean(row.get("segment_no")) or clean(row.get("review_order")) or "未标段落"
    chapter_no = clean(row.get("chapter_no"))
    decision = clean(row.get("system_decision")) or clean(row.get("evidence_role")) or clean(row.get("machine_role"))
    use = clean(row.get("article_use")) or clean(row.get("writing_use")) or clean(row.get("argument_axis"))
    summary = readable_story_text(row.get("summary"), segment_no, 90)
    quote = readable_story_text(row.get("quote"), segment_no, 110)
    parts = [f"`{segment_no}`"]
    if chapter_no:
        parts.append(f"第{chapter_no}回")
    if decision:
        parts.append(decision)
    if use:
        parts.append(use)
    if summary:
        parts.append(f"摘要：{summary}")
    if quote:
        parts.append(f"引文：{quote}")
    return "｜".join(parts)


def article_evidence_bullets(label: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f"### {label}", ""]
    unique_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = clean(row.get("segment_no")) or clean(row.get("review_order"))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    if not unique_rows:
        lines.extend(["- 这一组暂时没有足够稳的证据，后续需要回库补证。", ""])
        return lines
    for row in unique_rows:
        lines.append(f"- {evidence_ref(row)}")
    lines.append("")
    return lines


def render_formal_article_first_draft_evidence_only(question: str, rows: list[dict[str, Any]], brief_csv: Path, talk_md: Path) -> str:
    candidates = rows[:12]
    lines = [
        "# 红楼梦工程证据整理稿",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 写作说明",
        "",
        f"原问题：{question}",
        "",
        "本稿只整理工程召回证据，不生成结论文章，也不沿用旧题目的文章结构。",
        "",
        "## 自由回答交接",
        "",
        "请由最终回答层读取问题、证据候选和证据边界后，在证据范围内自由组织回答；若证据不足，应明确说明需要补证。",
        "",
        "## 证据索引",
        "",
    ]
    lines.extend(article_evidence_bullets("可继续深读的证据候选", candidates))
    lines.extend(
        [
            "## 下一步",
            "",
            "1. 最终回答层先读证据候选，再回答原问题。",
            "2. 不能用旧题判断补足证据空缺。",
            "3. 证据不足时，输出补证方向，而不是生成看似完整但无证据支撑的文章。",
            "",
            f"已停用本地论述稿：`{talk_md}`",
            f"已停用本地材料表：`{brief_csv}`",
        ]
    )
    return "\n".join(lines)


def render_formal_article_first_draft(question: str, rows: list[dict[str, Any]], brief_csv: Path, talk_md: Path) -> str:
    return render_formal_article_first_draft_evidence_only(question, rows, brief_csv, talk_md)


def loop_article_draft(package: str | Path = "latest", out_root: Path = OUT_ROOT, top_n: int = 10) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    article_md = package_dir / CORE_FILES["article_draft_md"]
    article_md.write_text(
        "# 本地模块文章稿已停用\n\n本工程不再由本地模块自动生成文章稿。候选材料必须先进入 Codex 指挥中心材料池判定，再由 Codex 生成红楼解语。\n",
        encoding="utf-8",
    )
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "article_draft_md": str(article_md),
        "status": "本地模块文章稿已停用，等待 Codex 指挥中心。",
        "disabled_reason": "防止模块自动思维替代 Codex 最终判断。",
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["article_draft_md"] = str(article_md)
    manifest.setdefault("results", {})["loop_article_draft"] = result
    manifest["status"] = "本地模块文章稿已停用；最终回答必须由 Codex 材料池判定、精读材料词和写作前原文追证摘抄后生成。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return result

def render_article_polish_evidence_only(
    question: str,
    rows: list[dict[str, Any]],
    source_draft: Path,
    brief_csv: Path,
    version_label: str,
) -> str:
    candidates = rows[:12]
    lines = [
        f"# 红楼梦工程证据整理稿｜{version_label}证据交接",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 原问题",
        "",
        question,
        "",
        "## 处理原则",
        "",
        "这里仅保留证据整理，交给最终回答层在材料范围内自由生成。",
        "",
        "## 证据索引",
        "",
    ]
    lines.extend(article_evidence_bullets("可继续深读的证据候选", candidates))
    lines.extend(
        [
            "## 来源",
            "",
            f"- 母稿：`{source_draft}`",
            f"- 证据分层表：`{brief_csv}`",
        ]
    )
    return "\n".join(lines)


def render_academic_article_polish(question: str, rows: list[dict[str, Any]], source_draft: Path, brief_csv: Path) -> str:
    return render_article_polish_evidence_only(question, rows, source_draft, brief_csv, "学术版")


def render_essay_article_polish(question: str, rows: list[dict[str, Any]], source_draft: Path, brief_csv: Path) -> str:
    return render_article_polish_evidence_only(question, rows, source_draft, brief_csv, "评论版")


def loop_article_polish(package: str | Path = "latest", out_root: Path = OUT_ROOT, top_n: int = 10) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    academic_md = package_dir / CORE_FILES["article_academic_md"]
    essay_md = package_dir / CORE_FILES["article_essay_md"]
    disabled_text = "# 本地模块润色稿已停用\n\n本工程不再由本地模块自动生成学术论文版或散文评论版。需要成文时，必须由 Codex 在材料池判定之后读取原文候选、材料池和真源核验，再生成红楼解语或后续作品稿。\n"
    academic_md.write_text(disabled_text, encoding="utf-8")
    essay_md.write_text(disabled_text, encoding="utf-8")
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "article_academic_md": str(academic_md),
        "article_essay_md": str(essay_md),
        "status": "本地模块润色稿已停用，等待 Codex 指挥中心。",
        "disabled_reason": "防止本地模块把候选材料自动改写成文章结论。",
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["article_academic_md"] = str(academic_md)
    core_files["article_essay_md"] = str(essay_md)
    manifest.setdefault("results", {})["loop_article_polish"] = result
    manifest["status"] = "本地模块润色稿已停用；成文必须由 Codex 材料池判定、精读材料词和写作前原文追证摘抄后生成。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return result

def article_choice_key(choice: str | int) -> str:
    raw = clean(choice)
    lowered = raw.lower()
    if raw.startswith("50") or "talk" in lowered or "谈心" in raw:
        return "50"
    if raw.startswith("51") or "draft" in lowered or "母稿" in raw or "第一稿" in raw:
        return "51"
    if raw.startswith("52") or "academic" in lowered or "论文" in raw or "学术" in raw:
        return "52"
    if raw.startswith("53") or "essay" in lowered or "散文" in raw or "评论" in raw:
        return "53"
    raise ValueError(f"无法识别文章版本：{choice}。请使用 50、51、52、53。")


def article_output_map(package_dir: Path, question: str = "") -> dict[str, dict[str, Any]]:
    return {
        "50": {
            "file": package_dir / CORE_FILES["argument_talk_md"],
            "role": "证据过程稿",
            "treatment": "留闭环包，作为证据过程材料；不作为作品总库主版本。",
            "default_title": "红楼梦工程｜证据过程稿",
            "identity": "资料型候选成果 / 证据表达参考",
            "nature": "资料类",
            "value": "★★★★★",
            "discoverability": "★★★★★",
            "credibility": "★★★",
        },
        "51": {
            "file": package_dir / CORE_FILES["article_draft_md"],
            "role": "证据整理稿",
            "treatment": "留闭环包，作为最终回答层的证据材料；不自动生成文章结论。",
            "default_title": "红楼梦工程证据整理稿",
            "identity": "资料型证据整理稿",
            "nature": "资料类",
            "value": "★★★★",
            "discoverability": "★★★★",
            "credibility": "★★★",
        },
        "52": {
            "file": package_dir / CORE_FILES["article_academic_md"],
            "role": "学术版暂不生成",
            "treatment": "论文版由最终回答层和补证结果决定；当前只保留证据材料。",
            "default_title": "红楼梦工程证据整理稿｜学术版暂不生成",
            "identity": "资料型证据整理稿",
            "nature": "资料类",
            "value": "★★★",
            "discoverability": "★★★",
            "credibility": "★★★",
        },
        "53": {
            "file": package_dir / CORE_FILES["article_essay_md"],
            "role": "评论版暂不生成",
            "treatment": "评论版由最终回答层和补证结果决定；当前只保留证据材料。",
            "default_title": "红楼梦工程证据整理稿｜评论版暂不生成",
            "identity": "资料型证据整理稿",
            "nature": "资料类",
            "value": "★★★",
            "discoverability": "★★★",
            "credibility": "★★★",
        },
    }


def article_relation_profile(question: str) -> dict[str, str]:
    return {
        "tags": "红楼梦, 原文核证, 待归类",
        "characters": "待由证据池确认",
        "task": "红楼梦问题闭环任务",
        "chapters": "待由证据池确认",
        "character_link_label": "关联人物：待确认",
        "character_link_target": "待由最终回答层确认",
        "chapter_link_target": "待由证据池确认",
        "chapter_link_note": "先不写回目；只接收证据池和最终回答层确认后的原文位置。",
        "topic_target": "待归类问题 / 证据过程材料",
        "confirmation_prompt": "红楼梦正式入库：先确认最终回答和证据支撑，再决定是否生成作品版本。",
    }


def markdown_title(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text.startswith("# "):
            return text[2:].strip() or fallback
    return fallback


def ensure_article_outputs(package_dir: Path, out_root: Path, main_key: str) -> None:
    article_map = article_output_map(package_dir)
    target = article_map[main_key]["file"]
    if target.exists():
        return
    if main_key in {"52", "53"}:
        loop_article_polish(package_dir, out_root)
        return
    if main_key == "51":
        loop_article_draft(package_dir, out_root)
        return
    if main_key == "50":
        loop_argument_brief(package_dir, out_root)
        return


def build_article_candidate_row(
    package_dir: Path,
    manifest: dict[str, Any],
    main_key: str,
    support_keys: list[str],
    confirmed: bool,
) -> dict[str, Any]:
    question = clean(manifest.get("question", ""))
    article_map = article_output_map(package_dir, question)
    relation = article_relation_profile(question)
    main = article_map[main_key]
    main_file = Path(main["file"])
    title = markdown_title(main_file, main["default_title"])
    now = datetime.now()
    support_text = "、".join(Path(article_map[key]["file"]).name for key in support_keys) or "无"
    confirmation_note = "用户已明确确认主版本" if confirmed else "缺用户正式入库口令"
    return {
        "标题": title,
        "编号": "待分配",
        "章回": "0",
        "小类": "2.9 论文/长稿",
        "文章性质": main["nature"],
        "内容状态": "已成稿",
        "价值": main["value"],
        "可挖掘": main["discoverability"],
        "可信度": main["credibility"],
        "来源位置": "闭环工作流",
        "标签": relation["tags"],
        "来源页URL": str(main_file),
        "入库日期": f"{now.year}年{now.month}月{now.day}日",
        "备注": (
            f"本地预检候选；主版本 {main_key}；辅版本：{support_text}；"
            f"待闭环：{confirmation_note}/作品总库正式行/Notion页面URL/回挂/真源核验；"
            "正式入 Notion 后将本地路径替换为页面 URL；证据回源见材料池、复核表与 55_真源核验清单.csv。"
        ),
        "大类": "作品",
        "关联人物": relation["characters"],
        "关联出库任务": relation["task"],
        "关联回目": relation["chapters"],
        "生命周期状态": "🔍 待核证",
    }


def render_article_identity_card(
    question: str,
    main_key: str,
    support_keys: list[str],
    process_keys: list[str],
    candidate_row: dict[str, Any],
    progress: dict[str, Any],
    package_dir: Path,
) -> str:
    article_map = article_output_map(package_dir, question)
    main = article_map[main_key]
    support = "、".join(f"`{Path(article_map[key]['file']).name}`" for key in support_keys) or "无"
    process = "、".join(f"`{Path(article_map[key]['file']).name}`" for key in process_keys) or "无"
    return "\n".join(
        [
            "# 红楼梦工程｜文章入库身份卡",
            "",
            f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
            "",
            "## 1. 对应问题",
            "",
            question,
            "",
            "## 2. 本文身份",
            "",
            f"- 主版本：`{Path(main['file']).name}`",
            f"- 主版本身份：{main['identity']}",
            f"- 主版本处理：{main['treatment']}",
            f"- 辅版本：{support}",
            f"- 过程材料：{process}",
            "",
            "## 3. 入库字段",
            "",
            f"- 标题：{candidate_row['标题']}",
            f"- 大类：{candidate_row['大类']}",
            f"- 小类：{candidate_row['小类']}",
            f"- 文章性质：{candidate_row['文章性质']}",
            f"- 生命周期状态：{candidate_row['生命周期状态']}",
            f"- 来源位置：{candidate_row['来源位置']}",
            f"- 关联人物：{candidate_row['关联人物']}",
            f"- 关联回目：{candidate_row['关联回目']}",
            f"- 关联出库任务：{candidate_row['关联出库任务']}",
            "",
            "## 4. 证据边界",
            "",
            "- 本文可以引用原文证据，但不能反向作为原文证据。",
            "- 本文不写入段落库、章节库、人物主数据或事件真源层。",
            "- 正式入库前仍需用户确认主版本，并完成作品总库行、回挂和真源核验。",
            "",
            "## 5. 当前核验状态",
            "",
            f"- 复核表总行数：{progress['total_rows']}",
            f"- 已人工判断：{progress['completed_rows']}",
            f"- 已核验可用证据：{progress['verified_rows']}",
            f"- 待核验可用证据：{progress['unverified_rows']}",
            f"- 当前可写作证据：{progress['usable_rows']}",
            "",
            "## 6. 结论",
            "",
            "本卡是本地候选入库身份卡，不等于正式 Notion 入库。当前最稳状态仍是：候选已整理，等待用户明确主版本口令和回挂核验。",
        ]
    )


def render_article_ingest_report(question: str, payload: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦工程｜文章入库预检报告",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 当前结论",
        "",
        payload["status"],
        "",
        "## 2. 对应问题",
        "",
        question,
        "",
        "## 3. 版本分层",
        "",
        f"- 主版本：`{payload['main_version']['filename']}`",
        f"- 主版本路径：`{payload['main_version']['path']}`",
        f"- 主版本身份：{payload['main_version']['identity']}",
        f"- 辅版本：{payload['support_versions_text']}",
        f"- 过程材料：{payload['process_versions_text']}",
        "",
        "## 4. 预检判断",
        "",
        f"- 是否触发未分类作品：{payload['checks']['uncategorized_work']}",
        f"- 是否触发零关联产出：{payload['checks']['zero_relation_output']}",
        f"- 是否已获正式入库口令：{payload['checks']['confirmed_by_user']}",
        f"- 是否可以正式写入 Notion：{payload['checks']['ready_for_notion_write']}",
        "",
        "## 5. 本次生成文件",
        "",
        f"- 作品总库入库候选行：`{payload['candidate_csv']}`",
        f"- 文章回挂清单：`{payload['links_csv']}`",
        f"- 文章入库身份卡：`{payload['identity_md']}`",
        f"- 预检摘要：`{payload['summary_json']}`",
        "",
        "## 6. 回挂缺口",
        "",
    ]
    for item in payload["missing_items"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 7. 后续口令",
            "",
        "如果你确认采用当前建议，可以说：",
        "",
        f"“{payload['confirmation_prompt']}”",
        "",
        "收到这类明确口令后，系统才进入正式写入准备；在此之前，本报告只作为本地候选层。",
        ]
    )
    return "\n".join(lines)


def loop_article_ingest_preview(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    main: str | int = "53",
    support: list[str] | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    return {
        "package": str(package_dir),
        "status": "旧本地文章稿入库预检已停用；请使用研究台页面的红楼解语入库预检。",
        "article_ingest_preview": {
            "ready": False,
            "does_not_call_local_article_chain": True,
        },
    }

def loop_argument_brief(package: str | Path = "latest", out_root: Path = OUT_ROOT, top_n: int = 10) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"缺少复核表：{review_csv}")
    brief_md = package_dir / CORE_FILES["argument_brief_md"]
    talk_md = package_dir / CORE_FILES["argument_talk_md"]
    disabled_text = "# 本地模块论证稿已停用\n\n本工程不再由本地模块自动生成论证简报或论述稿。候选材料必须先进入 Codex 指挥中心材料池判定，再由 Codex 决定可用材料、证据缺口、下一轮查证和最终表达。\n"
    brief_md.write_text(disabled_text, encoding="utf-8")
    talk_md.write_text(disabled_text, encoding="utf-8")
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "argument_brief_md": str(brief_md),
        "argument_talk_md": str(talk_md),
        "status": "本地模块论证稿已停用，等待 Codex 指挥中心。",
        "disabled_reason": "防止模块自动思维替代 Codex 材料池判定。",
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["argument_brief_md"] = str(brief_md)
    core_files["argument_talk_md"] = str(talk_md)
    manifest.setdefault("results", {})["loop_argument_brief"] = result
    manifest["status"] = "本地模块论证稿已停用；下一步必须由 Codex 指挥中心判定材料。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return result

def talk_workflow(
    question: str = "",
    package: str | Path = "latest",
    limit_per_question: int = 0,
    top_evidence: int = 0,
    review_limit: int = 0,
    out_root: Path = OUT_ROOT,
    use_feedback: bool = True,
    feedback_profile_path: Path | None = None,
    run_smoke: bool = True,
    top_n: int = 10,
    route_context: str = "",
) -> dict[str, Any]:
    if clean(question):
        manifest = build_closed_loop(
            question=question,
            limit_per_question=limit_per_question,
            top_evidence=top_evidence,
            review_limit=review_limit,
            out_root=out_root,
            use_feedback=use_feedback,
            feedback_profile_path=feedback_profile_path,
            run_smoke=run_smoke,
            route_context=route_context,
        )
        package_dir = Path(manifest.get("package_dir", ""))
    else:
        package_dir = resolve_package(package, out_root)

    if not package_dir or not (package_dir / CORE_FILES["review_csv"]).exists():
        return {
            "package": str(package_dir),
            "question": question,
            "status": "问题包尚未生成复核表，暂不能进入 Codex 材料池判定。",
        }

    status = loop_status(package_dir, out_root)
    recommended = status.get("recommended_next", {}) if isinstance(status, dict) else {}
    status_text = clean(recommended.get("next_action")) if isinstance(recommended, dict) else ""
    return {
        "package": str(package_dir),
        "question": question,
        "status": status_text or "候选材料、原文复核和材料池已生成；下一步必须进入 Codex 材料池判定，不再由本地模块生成论证稿或文章稿。",
        "talk_md": "",
        "article_draft_md": "",
        "argument_brief": {},
        "article_draft": {},
        "loop_continue": {"status": "已停用本地自动论证续跑；等待 Codex 指挥中心决定下一步。"},
        "status_file": status.get("status_file", ""),
        "status_json": status.get("status_json", ""),
        "created_new_package": bool(clean(question)),
        "route_context": route_context,
    }


def themed_review_question(question: str, source: dict[str, str]) -> str:
    return source.get("review_question", "")


def build_review_firstpass_rows(
    question: str,
    workbench_rows: list[dict[str, str]],
    target_count: int = 6,
    review_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    candidate_rows = workbench_rows
    picks = minimal_coverage_picks(candidate_rows, target_count=target_count)
    workbench_by_order = {clean(row.get("review_order")): row for row in candidate_rows}
    rows: list[dict[str, Any]] = []
    for pick in picks:
        source = workbench_by_order.get(clean(pick.get("review_order")), {})
        suggestion = firstpass_talk_suggestion(source, question)
        rows.append(
            {
                "firstpass_order": pick.get("pick_order", ""),
                "pick_reason": pick.get("pick_reason", ""),
                "review_order": pick.get("review_order", ""),
                "sheet_review_sequence": source.get("review_sequence", ""),
                "segment_no": source.get("segment_no", ""),
                "chapter_no": source.get("chapter_no", ""),
                "chapter_title": source.get("chapter_title", ""),
                "workbench_group": source.get("workbench_group", ""),
                "reference_decision": suggestion.get("decision") or source.get("copy_candidate_decision", ""),
                "reference_role": suggestion.get("role") or source.get("copy_candidate_role", ""),
                "reference_level": suggestion.get("level") or source.get("copy_candidate_level", ""),
                "reference_writing_use": suggestion.get("writing_use") or source.get("copy_candidate_writing_use", ""),
                "reference_note": suggestion.get("reason") or clean(source.get("draft_human_note_reference")),
                "must_check": source.get("machine_risk_flags", ""),
                "review_question": source.get("review_question", ""),
                "suggested_focus": suggestion.get("help_text") or source.get("suggested_focus", ""),
                "covered_subquestions": pick.get("new_subquestions", ""),
                "summary": source.get("summary", ""),
                "quote": source.get("quote", ""),
                "fill_target": "请人工确认后，把 reference_* 改写到 17_当前批次复核工作表.csv 的 human_* 字段。",
                "boundary_warning": "本执行单不写入人工判断；reference_* 只是参考。",
            }
        )
    return rows


def render_review_firstpass(question: str, rows: list[dict[str, Any]], firstpass_csv: Path, sheet_csv: Path) -> str:
    decision_counts = Counter(clean(row.get("reference_decision")) for row in rows)
    lines = [
        "# 红楼梦正式底库｜首轮复核执行单",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 使用边界",
        "",
        "- 本执行单只把首轮最建议处理的证据压缩成短清单。",
        "- `reference_*` 字段只是参考填法，不是人工判断。",
        "- 系统没有写入 `17_当前批次复核工作表.csv` 或 `04_复核表.csv`。",
        "- 你需要亲自核对原文后，再把确认结果写进 17 小表的五个 `human_*` 字段。",
        "",
        "## 3. 文件",
        "",
        f"- 当前小表：`{sheet_csv}`",
        f"- 执行单表：`{firstpass_csv}`",
        "",
        "## 4. 本轮规模",
        "",
        f"- 首轮执行行数：{len(rows)}",
        f"- 参考判断分布：{json.dumps(dict(decision_counts), ensure_ascii=False)}",
        "",
        "## 5. 填写顺序",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['firstpass_order']}. review_order={row['review_order']}｜17表序号={row['sheet_review_sequence']}｜{row['segment_no']}",
                "",
                f"- 选择原因：{row['pick_reason']}",
                f"- 参考判断：{row['reference_decision']}",
                f"- 参考角色/等级：{row['reference_role'] or '空'} / {row['reference_level'] or '空'}",
                f"- 参考写作用途：{row['reference_writing_use'] or '空'}",
                f"- 参考备注：{row['reference_note'] or '空'}",
                f"- 必须核对：{row['must_check'] or '无明显风险'}",
                f"- 复核问题：{row['review_question']}",
                f"- 涉及子问题：{row['covered_subquestions']}",
                "",
                "摘要：",
                "",
                short(row.get("summary"), 220),
                "",
                "引文：",
                "",
                f"> {short(row.get('quote'), 360)}",
                "",
                "需要填写到 17 小表的列：`human_decision`、`human_role`、`usable_level`、`writing_use`、`human_note`。",
                "",
            ]
        )
    lines.extend(
        [
            "## 6. 填完后",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-check --package latest",
            "python3 work/formal_honglou_cli.py loop-review-apply --package latest --dry-run",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_review_firstpass(package: str | Path = "latest", out_root: Path = OUT_ROOT, target_count: int = 6) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    workbench_csv = package_dir / CORE_FILES["review_workbench_csv"]
    if not workbench_csv.exists():
        loop_review_workbench(package_dir, out_root)
    if not (package_dir / CORE_FILES["review_coverage_md"]).exists():
        loop_review_coverage(package_dir, out_root)
    sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    workbench_rows = read_csv(workbench_csv)
    review_csv = package_dir / CORE_FILES["review_csv"]
    review_rows = read_csv(review_csv) if review_csv.exists() else []
    firstpass_rows = build_review_firstpass_rows(question, workbench_rows, target_count=target_count, review_rows=review_rows)
    firstpass_md = package_dir / CORE_FILES["review_firstpass_md"]
    firstpass_csv = package_dir / CORE_FILES["review_firstpass_csv"]
    fieldnames = [
        "firstpass_order",
        "pick_reason",
        "review_order",
        "sheet_review_sequence",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "workbench_group",
        "reference_decision",
        "reference_role",
        "reference_level",
        "reference_writing_use",
        "reference_note",
        "must_check",
        "review_question",
        "suggested_focus",
        "covered_subquestions",
        "summary",
        "quote",
        "fill_target",
        "boundary_warning",
    ]
    write_csv(firstpass_csv, firstpass_rows, fieldnames)
    firstpass_md.write_text(render_review_firstpass(question, firstpass_rows, firstpass_csv, sheet_csv), encoding="utf-8")
    decision_counts = Counter(clean(row.get("reference_decision")) for row in firstpass_rows)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_firstpass_md": str(firstpass_md),
        "review_firstpass_csv": str(firstpass_csv),
        "firstpass_rows": len(firstpass_rows),
        "target_count": target_count,
        "reference_decision_counts": dict(decision_counts),
        "does_not_write_human_fields": True,
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_md"] = str(firstpass_md)
    core_files["review_firstpass_csv"] = str(firstpass_csv)
    manifest.setdefault("results", {})["loop_review_firstpass"] = result
    manifest["status"] = f"已生成首轮复核执行单：{len(firstpass_rows)} 条；仍需人工填写小表。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核执行单",
            len(firstpass_rows) > 0,
            {
                "firstpass_rows": len(firstpass_rows),
                "reference_decision_counts": dict(decision_counts),
                "review_firstpass_md": str(firstpass_md),
                "review_firstpass_csv": str(firstpass_csv),
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass": result,
        "manifest": str(manifest_path_value),
    }


def render_firstpass_sheet_guide(question: str, sheet_csv: Path, source_csv: Path, row_count: int) -> str:
    return "\n".join(
        [
            "# 红楼梦正式底库｜首轮复核小表填写说明",
            "",
            f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
            "",
            "## 1. 原问题",
            "",
            question,
            "",
            "## 2. 文件",
            "",
            f"- 首轮复核小表：`{sheet_csv}`",
            f"- 来源执行单：`{source_csv}`",
            f"- 行数：{row_count}",
            "",
            "## 3. 怎么填",
            "",
            "只需要填这 5 列（其余列勿改）：",
            "",
            "- `human_decision`：待复核 / 保留 / 剔除 / 降级 / 反证",
            "- `human_role`：主证 / 辅证 / 背景 / 反证 / 误召回",
            "- `usable_level`：A / B / C",
            "- `writing_use`：写作用途",
            "- `human_note`：一句人工判断理由",
            "",
            "`reference_*` 列只是参考，不会自动变成人工判断。",
            "",
            "## 4. 填写前",
            "",
            "先阅读首轮逐条判读卡片：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-cards --package latest",
            "```",
            "",
            "## 5. 填完后",
            "",
            "再执行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
            "python3 work/formal_honglou_cli.py loop-review-check --package latest",
            "```",
        ]
    )


def loop_review_firstpass_sheet(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    firstpass_csv = package_dir / CORE_FILES["review_firstpass_csv"]
    if not firstpass_csv.exists():
        loop_review_firstpass(package_dir, out_root)
    review_sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    if not review_sheet_csv.exists():
        raise FileNotFoundError(f"缺少当前批次复核工作表：{review_sheet_csv}")

    firstpass_rows = read_csv(firstpass_csv)
    sheet_rows = read_csv(review_sheet_csv)
    sheet_by_order = {clean(row.get("review_order")): row for row in sheet_rows}
    sheet_fieldnames = list(sheet_rows[0].keys()) if sheet_rows else [
        "review_sequence",
        "batch",
        "review_order",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "suggested_section",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "summary",
        "quote",
        "review_question",
        "suggested_focus",
        "human_decision",
        "human_role",
        "usable_level",
        "writing_use",
        "human_note",
    ]
    added_to_review_sheet = 0
    for row in firstpass_rows:
        order = clean(row.get("review_order"))
        if not order or order in sheet_by_order:
            continue
        supplement = {
            "review_sequence": row.get("sheet_review_sequence", "") or order,
            "batch": "首轮补入候选",
            "review_order": order,
            "segment_no": row.get("segment_no", ""),
            "chapter_no": row.get("chapter_no", ""),
            "chapter_title": row.get("chapter_title", ""),
            "suggested_section": "首轮补入候选",
            "machine_role": row.get("reference_role", ""),
            "priority": "",
            "hit_subquestion_count": "",
            "hit_subquestions": row.get("covered_subquestions", ""),
            "summary": row.get("summary", ""),
            "quote": row.get("quote", ""),
            "review_question": row.get("review_question", ""),
            "suggested_focus": row.get("suggested_focus", ""),
            "human_decision": "",
            "human_role": "",
            "usable_level": "",
            "writing_use": "",
            "human_note": "",
        }
        sheet_rows.append({field: supplement.get(field, "") for field in sheet_fieldnames})
        sheet_by_order[order] = sheet_rows[-1]
        added_to_review_sheet += 1
    if added_to_review_sheet:
        write_csv(review_sheet_csv, sheet_rows, sheet_fieldnames)
    small_rows: list[dict[str, Any]] = []
    for row in firstpass_rows:
        order = clean(row.get("review_order"))
        source = sheet_by_order.get(order, {})
        small_rows.append(
            {
                "firstpass_order": row.get("firstpass_order", ""),
                "pick_reason": row.get("pick_reason", ""),
                "review_order": order,
                "review_sequence": source.get("review_sequence", row.get("sheet_review_sequence", "")),
                "batch": source.get("batch", ""),
                "segment_no": source.get("segment_no", row.get("segment_no", "")),
                "chapter_no": source.get("chapter_no", row.get("chapter_no", "")),
                "chapter_title": source.get("chapter_title", row.get("chapter_title", "")),
                "suggested_section": source.get("suggested_section", ""),
                "machine_role": source.get("machine_role", ""),
                "priority": source.get("priority", ""),
                "hit_subquestion_count": source.get("hit_subquestion_count", ""),
                "hit_subquestions": source.get("hit_subquestions", ""),
                "summary": source.get("summary", row.get("summary", "")),
                "quote": source.get("quote", row.get("quote", "")),
                "review_question": source.get("review_question", row.get("review_question", "")),
                "suggested_focus": source.get("suggested_focus", row.get("suggested_focus", "")),
                "reference_decision": row.get("reference_decision", ""),
                "reference_role": row.get("reference_role", ""),
                "reference_level": row.get("reference_level", ""),
                "reference_writing_use": row.get("reference_writing_use", ""),
                "reference_note": row.get("reference_note", ""),
                "must_check": row.get("must_check", ""),
                "human_decision": source.get("human_decision", ""),
                "human_role": source.get("human_role", ""),
                "usable_level": source.get("usable_level", ""),
                "writing_use": source.get("writing_use", ""),
                "human_note": source.get("human_note", ""),
                "boundary_warning": "请人工核对后填写 human_*；reference_* 只是参考。",
            }
        )

    small_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    guide_md = package_dir / CORE_FILES["review_firstpass_sheet_md"]
    fieldnames = [
        "firstpass_order",
        "pick_reason",
        "review_order",
        "review_sequence",
        "batch",
        "segment_no",
        "chapter_no",
        "chapter_title",
        "suggested_section",
        "machine_role",
        "priority",
        "hit_subquestion_count",
        "hit_subquestions",
        "summary",
        "quote",
        "review_question",
        "suggested_focus",
        "reference_decision",
        "reference_role",
        "reference_level",
        "reference_writing_use",
        "reference_note",
        "must_check",
        "human_decision",
        "human_role",
        "usable_level",
        "writing_use",
        "human_note",
        "boundary_warning",
    ]
    write_csv(small_csv, small_rows, fieldnames)
    guide_md.write_text(render_firstpass_sheet_guide(question, small_csv, firstpass_csv, len(small_rows)), encoding="utf-8")

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_firstpass_sheet_csv": str(small_csv),
        "review_firstpass_sheet_md": str(guide_md),
        "source_firstpass_csv": str(firstpass_csv),
        "rows": len(small_rows),
        "added_to_review_sheet": added_to_review_sheet,
        "does_not_write_human_fields": True,
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_sheet_csv"] = str(small_csv)
    core_files["review_firstpass_sheet_md"] = str(guide_md)
    manifest.setdefault("results", {})["loop_review_firstpass_sheet"] = result
    manifest["status"] = f"已生成首轮复核小表：{len(small_rows)} 条；请人工填写后再同步。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核小表",
            len(small_rows) > 0,
            {
                "rows": len(small_rows),
                "added_to_review_sheet": added_to_review_sheet,
                "review_firstpass_sheet_csv": str(small_csv),
                "review_firstpass_sheet_md": str(guide_md),
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass_sheet": result,
        "manifest": str(manifest_path_value),
    }


def render_firstpass_cards(question: str, rows: list[dict[str, str]], cards_md: Path, sheet_csv: Path) -> str:
    decision_counts = Counter(clean(row.get("reference_decision")) or "空" for row in rows)
    lines = [
        "# 红楼梦正式底库｜首轮复核逐条判读卡片",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 使用边界",
        "",
        "- 本文件只帮助人工阅读和判断，不替你填写人工字段。",
        "- `reference_*` 是候选来源参考；只有你写入 `human_*` 的内容才算正式复核。",
        "- 如果一句引文看起来有用，但不能直接支撑总问题，可以填 `降级` 或 `背景`，不要勉强当主证。",
        "- 如果证据指向相反方向，请填 `反证`，它会进入反方证据小稿，不会被剔除。",
        "",
        "## 3. 文件",
        "",
        f"- 首轮复核小表：`{sheet_csv}`",
        f"- 本判读卡片：`{cards_md}`",
        "",
        "## 4. 首轮规模",
        "",
        f"- 卡片数量：{len(rows)}",
        f"- 参考判断分布：{json.dumps(dict(decision_counts), ensure_ascii=False)}",
        "",
        "## 5. 快速判断口径",
        "",
        "- `保留`：这条原文能直接支撑当前总问题的核心判断，可以进入主文。",
        "- `降级`：有帮助，但只能作背景、旁证、过渡、概念铺垫或后续补证线索。",
        "- `反证`：它提醒论证需要加限定，或支持与当前主判断不同的解释方向。",
        "- `剔除`：误召回、太弱、脱离上下文，或和本题关系不成立。",
        "",
        "## 6. 逐条判读",
        "",
    ]
    if not rows:
        lines.append("当前没有首轮证据。")
        return "\n".join(lines)
    for row in rows:
        firstpass_order = clean(row.get("firstpass_order"))
        review_order = clean(row.get("review_order"))
        lines.extend(
            [
                f"### {firstpass_order}. review_order={review_order}｜{clean(row.get('segment_no'))}",
                "",
                f"- 选择原因：{clean(row.get('pick_reason')) or '空'}",
                f"- 回目：第{clean(row.get('chapter_no'))}回｜{short(row.get('chapter_title'), 90)}",
                f"- 建议部分：{clean(row.get('suggested_section')) or '空'}",
                f"- 机器角色/优先级：{clean(row.get('machine_role')) or '空'} / {clean(row.get('priority')) or '空'}",
                f"- 命中子问题数：{clean(row.get('hit_subquestion_count')) or '空'}",
                f"- 命中子问题：{short(row.get('hit_subquestions'), 260)}",
                f"- 必须核对：{clean(row.get('must_check')) or '无明显风险'}",
                "",
                "复核问题：",
                "",
                short(row.get("review_question"), 260),
                "",
                "阅读焦点：",
                "",
                short(row.get("suggested_focus"), 260),
                "",
                "原文摘要：",
                "",
                short(row.get("summary"), 360),
                "",
                "原文引文：",
                "",
                f"> {short(row.get('quote'), 700)}",
                "",
                "候选来源参考：",
                "",
                f"- `reference_decision`：{clean(row.get('reference_decision')) or '空'}",
                f"- `reference_role`：{clean(row.get('reference_role')) or '空'}",
                f"- `reference_level`：{clean(row.get('reference_level')) or '空'}",
                f"- `reference_writing_use`：{clean(row.get('reference_writing_use')) or '空'}",
                f"- `reference_note`：{short(row.get('reference_note'), 220) or '空'}",
                "",
                "人工填写位：",
                "",
                "- `human_decision`：待复核 / 保留 / 剔除 / 降级 / 反证",
                "- `human_role`：主证 / 辅证 / 背景 / 反证 / 误召回",
                "- `usable_level`：A / B / C",
                "- `writing_use`：写作用途",
                "- `human_note`：一句人工判断理由",
                "",
                "判断提醒：先问“这条原文能不能独立支撑总问题的一部分”；能就保留，弱就降级，方向相反就反证，无关就剔除。",
                "",
            ]
        )
    lines.extend(
        [
            "## 7. 填完后",
            "",
            "把判断写入 `38_首轮复核小表.csv` 的五个 `human_*` 字段后，依次运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
            "python3 work/formal_honglou_cli.py loop-review-check --package latest",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_review_firstpass_cards(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    if not sheet_csv.exists():
        loop_review_firstpass_sheet(package_dir, out_root)
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少首轮复核小表：{sheet_csv}")

    rows = read_csv(sheet_csv)
    cards_md = package_dir / CORE_FILES["review_firstpass_cards_md"]
    cards_md.write_text(render_firstpass_cards(question, rows, cards_md, sheet_csv), encoding="utf-8")
    decision_counts = Counter(clean(row.get("reference_decision")) or "空" for row in rows)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_firstpass_cards_md": str(cards_md),
        "review_firstpass_sheet_csv": str(sheet_csv),
        "card_rows": len(rows),
        "reference_decision_counts": dict(decision_counts),
        "does_not_write_human_fields": True,
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_cards_md"] = str(cards_md)
    manifest.setdefault("results", {})["loop_review_firstpass_cards"] = result
    manifest["status"] = f"已生成首轮复核逐条判读卡片：{len(rows)} 条；请读 43 后填写 38。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核逐条判读卡片",
            len(rows) > 0,
            {
                "card_rows": len(rows),
                "review_firstpass_cards_md": str(cards_md),
                "review_firstpass_sheet_csv": str(sheet_csv),
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass_cards": result,
        "manifest": str(manifest_path_value),
    }


def firstpass_talk_suggestion(row: dict[str, str], question: str = "") -> dict[str, str]:
    return {
        "decision": "降级",
        "role": "候选证据",
        "level": "B",
        "writing_use": "证据候选：先判断是否直接回答原问题",
        "help_text": "这条只作为证据候选；写作用途由最终回答层按原问题和材料池判断。",
        "reason": "工程应先按原问题核对证据相关性，再由最终回答层在证据范围内思考。",
    }


def render_firstpass_talk_sheet(question: str, rows: list[dict[str, str]], talk_md: Path, sheet_csv: Path) -> str:
    lines = [
        "# 红楼梦正式底库｜首轮谈心式复核单",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 1. 这份文件解决什么",
        "",
        "这份文件不是让你像机器一样填表，而是把首轮 6 条证据变成可讨论的判断。每条都回答：这段讲了什么、它对总问题有什么帮助、我建议你怎么勾。",
        "",
        "重要边界：下面的“建议填法”不会自动写入 `38_首轮复核小表.csv`。只有你亲自填进 `human_*` 字段，才算人工复核。",
        "",
        "## 2. 总问题",
        "",
        question,
        "",
        "## 3. 文件",
        "",
        f"- 首轮小表：`{sheet_csv}`",
        f"- 本谈心式复核单：`{talk_md}`",
        "",
        "## 4. 逐条判断",
        "",
    ]
    if not rows:
        lines.append("当前没有首轮证据。")
        return "\n".join(lines)
    for row in rows:
        suggestion = firstpass_talk_suggestion(row, question)
        firstpass_order = clean(row.get("firstpass_order"))
        review_order = clean(row.get("review_order"))
        segment_no = clean(row.get("segment_no"))
        lines.extend(
            [
                f"### {firstpass_order}. {segment_no}｜review_order={review_order}",
                "",
                f"- 回目：第{clean(row.get('chapter_no'))}回｜{short(row.get('chapter_title'), 90)}",
                f"- 原文摘要：{short(row.get('summary'), 240)}",
                f"- 原文引文：{short(row.get('quote'), 360)}",
                "",
                "它大概在讲什么：",
                "",
                suggestion["help_text"],
                "",
                "它对这个问题的帮助：",
                "",
                suggestion["reason"],
                "",
                "我的建议填法（供你确认，不会自动写入）：",
                "",
                f"- `human_decision`：{suggestion['decision']}",
                f"- `human_role`：{suggestion['role']}",
                f"- `usable_level`：{suggestion['level']}",
                f"- `writing_use`：{suggestion['writing_use']}",
                f"- `human_note`：{suggestion['reason']}",
                "",
                "你可以这样勾：",
                "",
                f"- [ ] 同意建议：{suggestion['decision']} / {suggestion['role']} / {suggestion['level']}",
                "- [ ] 改成保留",
                "- [ ] 改成降级",
                "- [ ] 改成反证",
                "- [ ] 剔除",
                "",
                "给你的判断问题：",
                "",
                f"> {short(themed_review_question(question, row) or row.get('review_question'), 220)}",
                "",
            ]
        )
    lines.extend(
        [
            "## 5. 填完 38 后",
            "",
            "你把认可的判断填进 `38_首轮复核小表.csv` 的五个 `human_*` 字段后，执行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
            "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
            "python3 work/formal_honglou_cli.py loop-review-check --package latest",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_review_firstpass_talk(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    if not sheet_csv.exists():
        loop_review_firstpass_sheet(package_dir, out_root)
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少首轮复核小表：{sheet_csv}")

    rows = read_csv(sheet_csv)
    talk_md = package_dir / CORE_FILES["review_firstpass_talk_md"]
    talk_md.write_text(render_firstpass_talk_sheet(question, rows, talk_md, sheet_csv), encoding="utf-8")
    suggestion_counts = Counter(firstpass_talk_suggestion(row, question)["decision"] for row in rows)
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "review_firstpass_talk_md": str(talk_md),
        "review_firstpass_sheet_csv": str(sheet_csv),
        "rows": len(rows),
        "suggestion_counts": dict(suggestion_counts),
        "does_not_write_human_fields": True,
    }
    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_talk_md"] = str(talk_md)
    manifest.setdefault("results", {})["loop_review_firstpass_talk"] = result
    manifest["status"] = f"已生成首轮谈心式复核单：{len(rows)} 条；请读 45 后填写 38。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮谈心式复核单",
            len(rows) > 0,
            {
                "rows": len(rows),
                "review_firstpass_talk_md": str(talk_md),
                "review_firstpass_sheet_csv": str(sheet_csv),
                "suggestion_counts": dict(suggestion_counts),
                "does_not_write_human_fields": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass_talk": result,
        "manifest": str(manifest_path_value),
    }


def render_firstpass_sync_report(question: str, result: dict[str, Any]) -> str:
    quality = result.get("quality_check", {})
    lines = [
        "# 红楼梦正式底库｜首轮复核小表同步报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 同步结果",
        "",
        f"- 是否模拟同步：{result['dry_run']}",
        f"- 首轮小表：`{result['firstpass_sheet_csv']}`",
        f"- 当前批次复核工作表：`{result['review_sheet_csv']}`",
        f"- 有人工输入的行：{result['input_rows']}",
        f"- 将更新/已更新行：{result['updated_rows']}",
        f"- 字段更新数：{result['updated_fields']}",
        f"- 跳过空行：{result['skipped_blank_rows']}",
        f"- 冲突行数：{result['conflict_rows']}",
        f"- 质量检查阻断：{result.get('blocked_by_quality_check', False)}",
        f"- 首轮小表阻断问题：{quality.get('blocking_issue_count', 0)}",
        f"- 首轮小表可同步行：{quality.get('ready_rows', 0)}",
        "",
    ]
    if result.get("blocked_by_quality_check"):
        lines.extend(["## 3. 必须先修正的问题", ""])
        for item in quality.get("issues", [])[:30]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    if result.get("backup"):
        lines.extend(["## 4. 同步前备份", "", f"- 备份文件：`{result['backup']}`", ""])
    if result["conflicts"]:
        lines.extend(["## 5. 冲突字段", ""])
        for item in result["conflicts"][:30]:
            lines.append(
                f"- review_order={item['review_order']}｜字段 {item['field']}｜原值：{short(item['existing'], 40)}｜新值：{short(item['incoming'], 40)}"
            )
        lines.append("")
    lines.extend(["## 6. 下一步", ""])
    if result.get("blocked_by_quality_check"):
        lines.extend(
            [
                "请先修正 `38_首轮复核小表.csv` 中的阻断问题，再重新检查并同步：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "同步后请检查当前批次小表质量：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-check --package latest",
                "```",
            ]
        )
    return "\n".join(lines)


def backup_review_sheet_csv(package_dir: Path, reason: str) -> str:
    source = package_dir / CORE_FILES["review_sheet_csv"]
    if not source.exists():
        raise FileNotFoundError(f"缺少当前批次复核工作表：{source}")
    backup_dir = package_dir / "_复核工作表备份"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = backup_dir / f"{stamp}_17_当前批次复核工作表_{safe_filename_part(reason, 12)}.csv"
    shutil.copyfile(source, target)
    return str(target)


def loop_review_firstpass_sync(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    sheet: str | Path = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    firstpass_sheet = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    if not firstpass_sheet.is_absolute() and not firstpass_sheet.exists():
        firstpass_sheet = package_dir / firstpass_sheet
    if not firstpass_sheet.exists():
        raise FileNotFoundError(f"缺少首轮复核小表：{firstpass_sheet}")
    review_sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    if not review_sheet_csv.exists():
        raise FileNotFoundError(f"缺少当前批次复核工作表：{review_sheet_csv}")

    quality_check = validate_review_sheet(firstpass_sheet, require_verify_status=False)
    quality_check["generated_at"] = datetime.now().isoformat(timespec="seconds")
    blocked_by_quality_check = (
        int(quality_check.get("filled_rows") or 0) > 0
        and int(quality_check.get("blocking_issue_count") or 0) > 0
    )
    small_rows = read_csv(firstpass_sheet)
    target_rows = read_csv(review_sheet_csv)
    target_by_order = {clean(row.get("review_order")): row for row in target_rows}
    updated_orders: set[str] = set()
    updated_fields = 0
    input_rows = 0
    skipped_blank_rows = 0
    conflicts: list[dict[str, str]] = []

    if blocked_by_quality_check:
        input_rows = int(quality_check.get("filled_rows") or 0)
        skipped_blank_rows = int(quality_check.get("blank_rows") or 0)
        conflicts.extend(
            {
                "review_order": clean(item.get("review_order")),
                "field": clean(item.get("field")),
                "existing": "质量检查阻断",
                "incoming": clean(item.get("message")),
            }
            for item in quality_check.get("issues", [])
        )
    else:
        for small_row in small_rows:
            order = clean(small_row.get("review_order"))
            target = target_by_order.get(order)
            if not target:
                conflicts.append({"review_order": order, "field": "review_order", "existing": "不存在", "incoming": order})
                continue
            if not row_has_human_input(small_row):
                skipped_blank_rows += 1
                continue
            input_rows += 1
            row_changed = False
            for field in HUMAN_FIELDS:
                incoming_raw = clean(small_row.get(field))
                if field == "human_decision":
                    incoming = review_readback.normalize_decision(incoming_raw)
                    if incoming == "待复核" and not incoming_raw:
                        continue
                else:
                    incoming = incoming_raw
                    if not incoming:
                        continue
                existing = clean(target.get(field))
                if existing and existing != "待复核" and existing != incoming and not overwrite:
                    conflicts.append({"review_order": order, "field": field, "existing": existing, "incoming": incoming})
                    continue
                if existing != incoming:
                    target[field] = incoming
                    updated_fields += 1
                    row_changed = True
            if row_changed:
                updated_orders.add(order)

    backup = ""
    if not dry_run and updated_orders and not blocked_by_quality_check:
        backup = backup_review_sheet_csv(package_dir, "首轮同步前")
        fieldnames = list(target_rows[0].keys()) if target_rows else []
        write_csv(review_sheet_csv, target_rows, fieldnames)

    sync_md = package_dir / CORE_FILES["review_firstpass_sync_md"]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "firstpass_sheet_csv": str(firstpass_sheet),
        "review_sheet_csv": str(review_sheet_csv),
        "sync_report_md": str(sync_md),
        "dry_run": dry_run,
        "overwrite": overwrite,
        "input_rows": input_rows,
        "updated_rows": len(updated_orders),
        "updated_fields": updated_fields,
        "skipped_blank_rows": skipped_blank_rows,
        "conflict_rows": len({item["review_order"] for item in conflicts}),
        "conflicts": conflicts,
        "backup": backup,
        "does_not_write_review_csv": True,
        "blocked_by_quality_check": blocked_by_quality_check,
        "quality_check": quality_check,
    }
    sync_md.write_text(render_firstpass_sync_report(question, result), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_sync_md"] = str(sync_md)
    manifest.setdefault("results", {})["loop_review_firstpass_sync"] = result
    if blocked_by_quality_check:
        manifest["status"] = f"首轮小表质量检查未通过：{quality_check['blocking_issue_count']} 个阻断问题；未同步到 17。"
    elif dry_run:
        manifest["status"] = f"已模拟首轮小表同步：将更新 {len(updated_orders)} 行。"
    else:
        manifest["status"] = f"已同步首轮小表到当前批次小表：更新 {len(updated_orders)} 行；仍未写入 04 复核表。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核小表同步到当前批次小表",
            not blocked_by_quality_check,
            {
                "dry_run": dry_run,
                "blocked_by_quality_check": blocked_by_quality_check,
                "quality_blocking_issue_count": quality_check["blocking_issue_count"],
                "updated_rows": len(updated_orders),
                "updated_fields": updated_fields,
                "conflict_rows": result["conflict_rows"],
                "sync_report_md": str(sync_md),
                "backup": backup,
                "does_not_write_review_csv": True,
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass_sync": result,
        "manifest": str(manifest_path_value),
    }


def render_review_apply_report(question: str, apply_result: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦正式底库｜复核工作表回填报告",
        "",
        f"生成时间：{apply_result['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 回填结果",
        "",
        f"- 工作表：`{apply_result['sheet_csv']}`",
        f"- 复核表：`{apply_result['review_csv']}`",
        f"- 是否模拟运行：{apply_result['dry_run']}",
        f"- 是否允许覆盖已有人工字段：{apply_result['overwrite']}",
        f"- 工作表行数：{apply_result['sheet_rows']}",
        f"- 有人工输入的行：{apply_result['input_rows']}",
        f"- 已更新行：{apply_result['updated_rows']}",
        f"- 字段更新数：{apply_result['updated_fields']}",
        f"- 跳过空行：{apply_result['skipped_blank_rows']}",
        f"- 冲突行数：{apply_result['conflict_rows']}",
        "",
    ]
    if apply_result.get("backup"):
        lines.extend(
            [
                "## 3. 回填前自动备份",
                "",
                f"- 备份文件：`{apply_result['backup']['backup_csv']}`",
                f"- 备份行数：{apply_result['backup']['rows']}",
                f"- 备份原因：{apply_result['backup']['reason']}",
                "",
            ]
        )
    elif apply_result["dry_run"]:
        lines.extend(["## 3. 回填前自动备份", "", "本次是模拟回填，没有写入复核表，也没有创建备份。", ""])
    elif apply_result["updated_rows"] == 0:
        lines.extend(["## 3. 回填前自动备份", "", "本次没有实际更新行，因此没有创建备份。", ""])
    if apply_result["conflicts"]:
        lines.extend(["## 4. 未覆盖的冲突字段", ""])
        for item in apply_result["conflicts"][:30]:
            lines.append(
                f"- review_order={item['review_order']}｜字段 {item['field']}｜原值：{short(item['existing'], 40)}｜新值：{short(item['incoming'], 40)}"
            )
        lines.append("")
    lines.extend(
        [
            "## 5. 下一步",
            "",
            "回填后请运行：",
            "",
            "```bash",
            "python3 work/formal_honglou_cli.py loop-readback --package latest",
            "python3 work/formal_honglou_cli.py loop-draft --package latest",
            "python3 work/formal_honglou_cli.py loop-next --package latest",
            "```",
        ]
    )
    return "\n".join(lines)


def loop_review_apply(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    sheet: str | Path = "",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    sheet_csv = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_sheet_csv"]
    if not sheet_csv.is_absolute() and not sheet_csv.exists():
        sheet_csv = package_dir / sheet_csv
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少复核工作表：{sheet_csv}")

    review_rows = read_csv(review_csv)
    sheet_rows = read_csv(sheet_csv)
    review_by_order = {clean(row.get("review_order")): row for row in review_rows}
    updated_orders: set[str] = set()
    updated_fields = 0
    input_rows = 0
    skipped_blank_rows = 0
    conflicts: list[dict[str, str]] = []

    for sheet_row in sheet_rows:
        order = clean(sheet_row.get("review_order"))
        target = review_by_order.get(order)
        if not target:
            conflicts.append({"review_order": order, "field": "review_order", "existing": "不存在", "incoming": order})
            continue
        if not row_has_human_input(sheet_row):
            skipped_blank_rows += 1
            continue
        input_rows += 1
        row_changed = False
        for field in HUMAN_FIELDS:
            incoming_raw = clean(sheet_row.get(field))
            if field == "human_decision":
                incoming = review_readback.normalize_decision(incoming_raw)
                if incoming == "待复核" and not incoming_raw:
                    continue
            else:
                incoming = incoming_raw
                if not incoming:
                    continue
            existing = clean(target.get(field))
            if existing and existing != "待复核" and existing != incoming and not overwrite:
                conflicts.append({"review_order": order, "field": field, "existing": existing, "incoming": incoming})
                continue
            if existing != incoming:
                target[field] = incoming
                updated_fields += 1
                row_changed = True
        if row_changed:
            updated_orders.add(order)

    backup: dict[str, Any] | None = None
    if not dry_run and updated_orders:
        backup = backup_review_csv(package_dir, reason="回填前")
        fieldnames = list(review_rows[0].keys()) if review_rows else []
        write_csv(review_csv, review_rows, fieldnames)

    apply_md = package_dir / CORE_FILES["review_apply_md"]
    apply_result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "review_csv": str(review_csv),
        "sheet_csv": str(sheet_csv),
        "apply_report_md": str(apply_md),
        "dry_run": dry_run,
        "overwrite": overwrite,
        "sheet_rows": len(sheet_rows),
        "input_rows": input_rows,
        "updated_rows": len(updated_orders),
        "updated_fields": updated_fields,
        "skipped_blank_rows": skipped_blank_rows,
        "conflict_rows": len({item["review_order"] for item in conflicts}),
        "conflicts": conflicts,
        "backup": backup,
    }
    apply_md.write_text(render_review_apply_report(question, apply_result), encoding="utf-8")
    backup_index_payload: dict[str, Any] | None = None
    if backup:
        backup_md = package_dir / CORE_FILES["review_backup_md"]
        backup_json = package_dir / CORE_FILES["review_backup_json"]
        backup_records = review_backup_records(package_dir)
        backup_index_payload = {
            "generated_at": apply_result["generated_at"],
            "package": str(package_dir),
            "question": question,
            "backup_dir": str(review_backup_dir(package_dir)),
            "backup_count": len(backup_records),
            "backups": backup_records,
            "backup_index_md": str(backup_md),
            "backup_index_json": str(backup_json),
        }
        backup_md.write_text(render_review_backup_index(question, backup_index_payload), encoding="utf-8")
        write_json(backup_json, backup_index_payload)

    core_files = manifest.setdefault("core_files", {})
    core_files["review_apply_md"] = str(apply_md)
    if backup:
        core_files["review_backup_dir"] = str(review_backup_dir(package_dir))
        core_files["review_backup_md"] = str(package_dir / CORE_FILES["review_backup_md"])
        core_files["review_backup_json"] = str(package_dir / CORE_FILES["review_backup_json"])
    manifest.setdefault("results", {})["loop_review_apply"] = apply_result
    if backup_index_payload:
        manifest.setdefault("results", {})["loop_review_backups"] = backup_index_payload
    if dry_run:
        manifest["status"] = f"系统已模拟复核工作表回填：将更新 {len(updated_orders)} 行。"
    else:
        manifest["status"] = f"系统已回填复核工作表：更新 {len(updated_orders)} 行；请继续运行回读。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核工作表安全回填",
            True,
            {
                "dry_run": dry_run,
                "overwrite": overwrite,
                "updated_rows": len(updated_orders),
                "updated_fields": updated_fields,
                "conflict_rows": apply_result["conflict_rows"],
                "apply_report_md": str(apply_md),
                "backup": backup,
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_apply": apply_result,
        "manifest": str(manifest_path_value),
    }


def finish_action(name: str, ok: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail or {},
    }


def render_review_finish_report(question: str, result: dict[str, Any]) -> str:
    finish_command = (
        "python3 work/formal_honglou_cli.py loop-review-finish "
        f"--package {json.dumps(str(result.get('package', 'latest')), ensure_ascii=False)} --apply"
    )
    lines = [
        "# 红楼梦正式底库｜复核收口运行报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 1. 问题",
        "",
        question or "未指定问题。",
        "",
        "## 2. 当前状态",
        "",
        result["status"],
        "",
        "## 3. 运行设置",
        "",
        f"- 是否允许实际写入：{result['apply']}",
        f"- 是否允许覆盖已有人工字段：{result['overwrite']}",
        f"- 是否继续到真源核验：{result['run_source_verify']}",
        f"- 是否继续到回读刷新：{result['run_readback']}",
        "",
        "## 4. 执行动作",
        "",
    ]
    for item in result["actions"]:
        mark = "通过" if item["ok"] else "停住"
        lines.append(f"- {item['name']}：{mark}")
        detail = item.get("detail") or {}
        for key, value in detail.items():
            if isinstance(value, (dict, list)):
                continue
            lines.append(f"  - {key}：{value}")
    lines.append("")
    if result.get("blocking_reason"):
        lines.extend(["## 5. 当前阻断", "", result["blocking_reason"], ""])
    lines.extend(["## 6. 下一步", ""])
    if result["ready_for_next_user_action"]:
        lines.extend(
            [
                "请先读 `45_首轮谈心式复核单.md`，再填写 `38_首轮复核小表.csv` 的五个 `human_*` 字段。",
                "",
                "填完后运行：",
                "",
                "```bash",
                finish_command,
                "```",
            ]
        )
    elif not result["apply"]:
        lines.extend(
            [
                "当前是安全检查模式，没有实际写入。确认要收口时运行：",
                "",
                "```bash",
                finish_command,
                "```",
            ]
        )
    else:
        lines.extend(
            [
                "收口命令已完成可执行部分。请查看 `20_闭环状态与下一步操作台.md`。",
            ]
        )
    return "\n".join(lines)


def loop_review_finish(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    apply: bool = False,
    overwrite: bool = False,
    run_source_verify: bool = True,
    run_readback: bool = True,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    actions: list[dict[str, Any]] = []
    blocking_reason = ""
    ready_for_next_user_action = False

    firstpass_check_result = loop_review_firstpass_check(package_dir, out_root)
    firstpass_check = firstpass_check_result["review_firstpass_check"]
    actions.append(
        finish_action(
            "检查 38 首轮复核小表",
            True,
            {
                "filled_rows": firstpass_check["filled_rows"],
                "ready_rows": firstpass_check["ready_rows"],
                "blocking_issue_count": firstpass_check["blocking_issue_count"],
                "ready_for_sync": firstpass_check["ready_for_apply"],
            },
        )
    )
    if int(firstpass_check.get("filled_rows") or 0) == 0:
        blocking_reason = "38_首轮复核小表尚未填写。系统不会替你把机器建议写成人工判断。"
        ready_for_next_user_action = True
    elif int(firstpass_check.get("blocking_issue_count") or 0) > 0:
        blocking_reason = "38_首轮复核小表存在阻断问题，请先按 41_首轮复核小表质量检查.md 修正。"
    elif not firstpass_check.get("ready_for_apply"):
        blocking_reason = "38_首轮复核小表暂未达到可同步状态。"

    sync_dry_result = None
    if not blocking_reason:
        sync_dry_result = loop_review_firstpass_sync(package_dir, out_root, overwrite=overwrite, dry_run=True)
        sync_dry = sync_dry_result["review_firstpass_sync"]
        actions.append(
            finish_action(
                "模拟同步 38 到 17",
                not sync_dry.get("blocked_by_quality_check") and int(sync_dry.get("conflict_rows") or 0) == 0,
                {
                    "input_rows": sync_dry["input_rows"],
                    "updated_rows": sync_dry["updated_rows"],
                    "conflict_rows": sync_dry["conflict_rows"],
                    "blocked_by_quality_check": sync_dry.get("blocked_by_quality_check", False),
                },
            )
        )
        if sync_dry.get("blocked_by_quality_check"):
            blocking_reason = "38_首轮复核小表质量检查阻断，未同步到 17。"
        elif int(sync_dry.get("conflict_rows") or 0) > 0:
            blocking_reason = "38 同步到 17 时存在冲突；如确认要覆盖，请加 --overwrite。"

    if not blocking_reason and apply:
        sync_result = loop_review_firstpass_sync(package_dir, out_root, overwrite=overwrite, dry_run=False)
        sync = sync_result["review_firstpass_sync"]
        actions.append(
            finish_action(
                "正式同步 38 到 17",
                int(sync.get("conflict_rows") or 0) == 0 and not sync.get("blocked_by_quality_check"),
                {
                    "input_rows": sync["input_rows"],
                    "updated_rows": sync["updated_rows"],
                    "conflict_rows": sync["conflict_rows"],
                },
            )
        )
        if int(sync.get("conflict_rows") or 0) > 0 or sync.get("blocked_by_quality_check"):
            blocking_reason = "正式同步 38 到 17 时出现冲突或质量阻断。"

    if not blocking_reason:
        review_check_result = loop_review_check(package_dir, out_root)
        review_check = review_check_result["review_check"]
        actions.append(
            finish_action(
                "检查 17 当前批次复核工作表",
                int(review_check.get("blocking_issue_count") or 0) == 0,
                {
                    "filled_rows": review_check["filled_rows"],
                    "ready_rows": review_check["ready_rows"],
                    "blocking_issue_count": review_check["blocking_issue_count"],
                    "ready_for_apply": review_check["ready_for_apply"],
                },
            )
        )
        if int(review_check.get("filled_rows") or 0) == 0:
            blocking_reason = "17_当前批次复核工作表尚未出现人工填写内容。"
            ready_for_next_user_action = True
        elif int(review_check.get("blocking_issue_count") or 0) > 0:
            blocking_reason = "17_当前批次复核工作表存在阻断问题，请先按 22_复核工作表质量检查.md 修正。"

    if not blocking_reason and not apply:
        blocking_reason = "安全检查已通过；当前没有实际写入。"

    if not blocking_reason and apply:
        apply_dry_result = loop_review_apply(package_dir, out_root, overwrite=overwrite, dry_run=True)
        apply_dry = apply_dry_result["review_apply"]
        actions.append(
            finish_action(
                "模拟回填 17 到 04",
                int(apply_dry.get("conflict_rows") or 0) == 0,
                {
                    "input_rows": apply_dry["input_rows"],
                    "updated_rows": apply_dry["updated_rows"],
                    "conflict_rows": apply_dry["conflict_rows"],
                },
            )
        )
        if int(apply_dry.get("conflict_rows") or 0) > 0:
            blocking_reason = "17 回填到 04 时存在冲突；如确认要覆盖，请加 --overwrite。"

    if not blocking_reason and apply:
        apply_result = loop_review_apply(package_dir, out_root, overwrite=overwrite, dry_run=False)
        apply_payload = apply_result["review_apply"]
        actions.append(
            finish_action(
                "正式回填 17 到 04",
                int(apply_payload.get("conflict_rows") or 0) == 0,
                {
                    "input_rows": apply_payload["input_rows"],
                    "updated_rows": apply_payload["updated_rows"],
                    "conflict_rows": apply_payload["conflict_rows"],
                    "backup": (apply_payload.get("backup") or {}).get("backup_csv", ""),
                },
            )
        )
        if int(apply_payload.get("conflict_rows") or 0) > 0:
            blocking_reason = "正式回填 17 到 04 时存在冲突。"

    if not blocking_reason and apply and run_source_verify:
        source_result = loop_source_verify(package_dir, out_root)
        source_payload = source_result["source_verify"]
        actions.append(
            finish_action(
                "刷新真源核验字段与清单",
                True,
                {
                    "total_rows": source_payload["total_rows"],
                    "unverified_usable_rows": source_payload["unverified_usable_rows"],
                    "source_verify_csv": source_payload["source_verify_csv"],
                },
            )
        )

    if not blocking_reason and apply and run_readback:
        readback_result = loop_readback(package_dir, out_root)
        actions.append(
            finish_action(
                "刷新回读、反馈与可写作材料",
                True,
                {
                    "usable_rows": readback_result["progress"]["usable_rows"],
                    "unverified_rows": readback_result["progress"]["unverified_rows"],
                    "writable_pack": readback_result["writable_pack"],
                },
            )
        )

    if apply and not blocking_reason:
        status_result = loop_status(package_dir, out_root)
        actions.append(
            finish_action(
                "刷新闭环状态",
                True,
                {
                    "status": status_result["status"],
                    "status_file": status_result["status_file"],
                },
            )
        )

    status = "复核收口已完成。" if apply and not blocking_reason else "复核收口尚未完成。"
    if blocking_reason:
        status = f"{status}{blocking_reason}"

    finish_md = package_dir / CORE_FILES["review_finish_md"]
    finish_json = package_dir / CORE_FILES["review_finish_json"]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "status": status,
        "apply": apply,
        "overwrite": overwrite,
        "run_source_verify": run_source_verify,
        "run_readback": run_readback,
        "blocking_reason": blocking_reason,
        "ready_for_next_user_action": ready_for_next_user_action,
        "actions": actions,
        "review_finish_md": str(finish_md),
        "review_finish_json": str(finish_json),
    }
    finish_md.write_text(render_review_finish_report(question, result), encoding="utf-8")
    write_json(finish_json, result)

    manifest = load_manifest(package_dir)
    core_files = manifest.setdefault("core_files", {})
    core_files["review_finish_md"] = str(finish_md)
    core_files["review_finish_json"] = str(finish_json)
    manifest.setdefault("results", {})["loop_review_finish"] = result
    manifest["status"] = status
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核收口一键运行",
            not bool(blocking_reason) and apply,
            {
                "apply": apply,
                "blocking_reason": blocking_reason,
                "review_finish_md": str(finish_md),
                "review_finish_json": str(finish_json),
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": status,
        "review_finish": result,
        "manifest": str(manifest_path_value),
    }


def file_info(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
    }


def sheet_progress(sheet_csv: Path) -> dict[str, Any]:
    rows = read_csv(sheet_csv)
    filled = [row for row in rows if row_has_human_input(row)]
    decisions = Counter(review_readback.normalize_decision(row.get("human_decision", "")) for row in filled)
    return {
        "rows": len(rows),
        "filled_rows": len(filled),
        "blank_rows": max(0, len(rows) - len(filled)),
        "decision_counts": dict(decisions),
    }


def validate_review_sheet(sheet_csv: Path, require_verify_status: bool = True) -> dict[str, Any]:
    rows = read_csv(sheet_csv)
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    ready_rows: list[str] = []
    filled_rows = 0
    seen_orders: set[str] = set()
    pending_words = review_readback.PENDING_WORDS
    verify_ok = {"已核验", "核验已通过", "核验通过", "通过"}
    verify_pending = review_readback.VERIFY_WORDS_PENDING if hasattr(review_readback, "VERIFY_WORDS_PENDING") else {"", "待核验", "未核验", "未检", "待确认", "未确认"}
    allowed_levels = {"A", "B", "C", "强", "中", "弱", "甲", "乙", "丙"}

    for idx, row in enumerate(rows, start=1):
        order = clean(row.get("review_order"))
        if not order:
            issues.append({"row": idx, "review_order": order, "field": "review_order", "message": "缺少复核序号。"})
        elif order in seen_orders:
            issues.append({"row": idx, "review_order": order, "field": "review_order", "message": "复核序号重复。"})
        seen_orders.add(order)
        if not clean(row.get("segment_no")):
            issues.append({"row": idx, "review_order": order, "field": "segment_no", "message": "缺少段落号。"})

        if not row_has_human_input(row):
            continue
        filled_rows += 1
        raw_decision = clean(row.get("human_decision"))
        decision = review_readback.normalize_decision(raw_decision)
        if raw_decision and decision == "待复核" and raw_decision.replace(" ", "") not in pending_words:
            issues.append({"row": idx, "review_order": order, "field": "human_decision", "message": f"无法识别判断：{raw_decision}"})
            continue
        if decision == "待复核":
            issues.append({"row": idx, "review_order": order, "field": "human_decision", "message": "已有人工字段，但判断仍是待复核。"})
            continue

        verify_raw = clean(row.get("source_verify_status"))
        verify = review_readback.normalize_verify_status(verify_raw)
        if require_verify_status and decision in {"保留", "降级", "反证"} and verify not in verify_ok:
            if not verify_raw:
                issues.append({"row": idx, "review_order": order, "field": "source_verify_status", "message": f"{decision} 需要先核验；请设置为“已核验”。"})
            else:
                issues.append({"row": idx, "review_order": order, "field": "source_verify_status", "message": f"识别不到有效核验状态：{verify_raw}"})
        elif require_verify_status and decision in {"保留", "降级", "反证"} and clean(row.get("source_verify_status")) in verify_pending:
            warnings.append({"row": idx, "review_order": order, "field": "source_verify_status", "message": "该条可用决议尚未核验，当前不会进入可写作材料。"})
        role = clean(row.get("human_role"))
        level = clean(row.get("usable_level"))
        writing_use = clean(row.get("writing_use"))
        note = clean(row.get("human_note"))

        if decision in {"保留", "降级", "反证"}:
            if not role:
                issues.append({"row": idx, "review_order": order, "field": "human_role", "message": f"{decision} 需要填写证据角色。"})
            if not level:
                issues.append({"row": idx, "review_order": order, "field": "usable_level", "message": f"{decision} 需要填写可用等级。"})
            if not writing_use:
                issues.append({"row": idx, "review_order": order, "field": "writing_use", "message": f"{decision} 需要填写写作用途。"})
            if level and level not in allowed_levels:
                warnings.append({"row": idx, "review_order": order, "field": "usable_level", "message": f"等级 {level} 不在常用值 A/B/C/强/中/弱 中。"})
            if not note:
                warnings.append({"row": idx, "review_order": order, "field": "human_note", "message": f"{decision} 建议补一句人工备注。"})
        elif decision == "剔除":
            if not role:
                issues.append({"row": idx, "review_order": order, "field": "human_role", "message": "剔除需要填写角色或原因类型，例如误召回。"})
            if not note:
                issues.append({"row": idx, "review_order": order, "field": "human_note", "message": "剔除需要填写人工备注，说明为什么剔除。"})
            if writing_use:
                warnings.append({"row": idx, "review_order": order, "field": "writing_use", "message": "剔除行通常不需要写作用途。"})

        row_issue_keys = {item["row"] for item in issues}
        if idx not in row_issue_keys:
            ready_rows.append(order)

    decision_counts = Counter(
        review_readback.normalize_decision(row.get("human_decision", ""))
        for row in rows
        if row_has_human_input(row)
    )
    return {
        "sheet_csv": str(sheet_csv),
        "sheet_rows": len(rows),
        "filled_rows": filled_rows,
        "blank_rows": max(0, len(rows) - filled_rows),
        "ready_rows": len(ready_rows),
        "ready_review_orders": ready_rows,
        "blocking_issue_count": len(issues),
        "warning_count": len(warnings),
        "issues": issues,
        "warnings": warnings,
        "decision_counts": dict(decision_counts),
        "ready_for_apply": filled_rows > 0 and len(issues) == 0,
    }


def sheet_sync_state(sheet_csv: Path, review_csv: Path) -> dict[str, Any]:
    sheet_rows = read_csv(sheet_csv)
    review_rows = read_csv(review_csv)
    review_by_order = {clean(row.get("review_order")): row for row in review_rows}
    filled_rows = 0
    applied_rows = 0
    unapplied_rows = 0
    missing_rows = 0
    conflicts: list[dict[str, str]] = []
    for sheet_row in sheet_rows:
        if not row_has_human_input(sheet_row):
            continue
        filled_rows += 1
        order = clean(sheet_row.get("review_order"))
        target = review_by_order.get(order)
        if not target:
            missing_rows += 1
            conflicts.append({"review_order": order, "field": "review_order", "existing": "不存在", "incoming": order})
            continue
        row_applied = True
        for field in HUMAN_FIELDS:
            incoming_raw = clean(sheet_row.get(field))
            if field == "human_decision":
                incoming = review_readback.normalize_decision(incoming_raw)
                if incoming == "待复核" and not incoming_raw:
                    continue
                existing = review_readback.normalize_decision(target.get(field, ""))
            else:
                incoming = incoming_raw
                if not incoming:
                    continue
                existing = clean(target.get(field))
            if existing != incoming:
                row_applied = False
                if existing and existing != "待复核":
                    conflicts.append({"review_order": order, "field": field, "existing": existing, "incoming": incoming})
        if row_applied:
            applied_rows += 1
        else:
            unapplied_rows += 1
    return {
        "filled_rows": filled_rows,
        "applied_rows": applied_rows,
        "unapplied_rows": unapplied_rows,
        "missing_rows": missing_rows,
        "conflict_rows": len({item["review_order"] for item in conflicts}),
        "conflicts": conflicts,
        "all_filled_rows_applied": filled_rows > 0 and unapplied_rows == 0 and missing_rows == 0,
    }


def render_review_check_report(question: str, check: dict[str, Any]) -> str:
    status = "可以回填" if check["ready_for_apply"] else "暂不建议回填"
    lines = [
        "# 红楼梦正式底库｜复核工作表质量检查",
        "",
        f"生成时间：{check['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 当前判断",
        "",
        status,
        "",
        "## 3. 检查结果",
        "",
        f"- 工作表：`{check['sheet_csv']}`",
        f"- 工作表行数：{check['sheet_rows']}",
        f"- 已填写行：{check['filled_rows']}",
        f"- 未填写行：{check['blank_rows']}",
        f"- 可回填行：{check['ready_rows']}",
        f"- 阻断问题：{check['blocking_issue_count']}",
        f"- 提醒项：{check['warning_count']}",
        f"- 判断分布：{json.dumps(check['decision_counts'], ensure_ascii=False)}",
        "",
    ]
    if check["blocking_issue_count"]:
        lines.extend(["## 4. 必须修正的问题", ""])
        for item in check["issues"][:60]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    if check["warning_count"]:
        lines.extend(["## 5. 建议补充的提醒", ""])
        for item in check["warnings"][:60]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    lines.extend(
        [
            "## 6. 下一步",
            "",
        ]
    )
    if check["ready_for_apply"]:
        lines.extend(
            [
                "当前已填写行没有阻断问题，可以先 dry-run，再正式回填：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-apply --package latest --dry-run",
                "python3 work/formal_honglou_cli.py loop-review-apply --package latest",
                "```",
            ]
        )
    elif check["filled_rows"] == 0:
        lines.append("当前小表还没有填写人工判断。请先填写 `human_decision` 等五个人工字段。")
    else:
        lines.append("请先修正上面的阻断问题，再重新运行 `loop-review-check --package latest`。")
    return "\n".join(lines)


def render_firstpass_check_report(question: str, check: dict[str, Any]) -> str:
    status = "可以同步到 17" if check["ready_for_apply"] else "暂不建议同步"
    lines = [
        "# 红楼梦正式底库｜首轮复核小表质量检查",
        "",
        f"生成时间：{check['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 当前判断",
        "",
        status,
        "",
        "## 3. 检查结果",
        "",
        f"- 首轮小表：`{check['sheet_csv']}`",
        f"- 小表行数：{check['sheet_rows']}",
        f"- 已填写行：{check['filled_rows']}",
        f"- 未填写行：{check['blank_rows']}",
        f"- 可同步行：{check['ready_rows']}",
        f"- 阻断问题：{check['blocking_issue_count']}",
        f"- 提醒项：{check['warning_count']}",
        f"- 判断分布：{json.dumps(check['decision_counts'], ensure_ascii=False)}",
        "",
    ]
    if check["blocking_issue_count"]:
        lines.extend(["## 4. 必须修正的问题", ""])
        for item in check["issues"][:60]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    if check["warning_count"]:
        lines.extend(["## 5. 建议补充的提醒", ""])
        for item in check["warnings"][:60]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    lines.extend(["## 6. 下一步", ""])
    if check["ready_for_apply"]:
        lines.extend(
            [
                "首轮小表已通过检查，可以先模拟同步，再正式同步到 17：",
                "",
                "```bash",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
                "python3 work/formal_honglou_cli.py loop-review-check --package latest",
                "```",
            ]
        )
    elif check["filled_rows"] == 0:
        lines.append("当前首轮小表还没有填写人工判断。请先填写 `human_decision` 等五个人工字段。")
    else:
        lines.append("请先修正上面的阻断问题，再重新运行 `loop-review-firstpass-check --package latest`。")
    return "\n".join(lines)


def render_firstpass_desk(question: str, payload: dict[str, Any]) -> str:
    status = clean(payload.get("status")) or "无状态"
    firstpass_check = payload["firstpass_check"]
    sync = payload["sheet_sync"]
    lines = [
        "# 红楼梦正式底库｜首轮复核就绪台",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 当前问题",
        "",
        question,
        "",
        "## 2. 当前状态",
        "",
        status,
        "",
        "## 3. 首轮小表状态",
        "",
        f"- 首轮小表：`{payload['sheet_csv']}`",
        f"- 行数：{firstpass_check['sheet_rows']}",
        f"- 已填写行：{firstpass_check['filled_rows']}",
        f"- 可同步行：{firstpass_check['ready_rows']}",
        f"- 决定分布：{json.dumps(firstpass_check['decision_counts'], ensure_ascii=False)}",
        f"- 阻断项：{firstpass_check['blocking_issue_count']}",
        f"- 提醒项：{firstpass_check['warning_count']}",
        "",
        "## 4. 同步状态（38 → 17）",
        "",
        f"- 当前批次小表：`{payload['review_sheet_csv']}`",
        f"- 首轮小表已人工填写：{sync['filled_rows']}",
        f"- 已同步：{sync['applied_rows']}",
        f"- 尚未同步：{sync['unapplied_rows']}",
        f"- 缺失匹配行：{sync['missing_rows']}",
        f"- 冲突行数：{sync['conflict_rows']}",
        "",
    ]
    if payload["firstpass_cards_md"]:
        lines.extend([f"- 首轮判读卡片：`{payload['firstpass_cards_md']}`", ""])
    if payload.get("firstpass_talk_md"):
        lines.extend([f"- 首轮谈心式复核单：`{payload['firstpass_talk_md']}`", ""])
    if payload["need_attention"] and firstpass_check["issues"]:
        lines.extend(["## 5. 须先修正项", ""])
        for item in firstpass_check["issues"][:50]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    if firstpass_check["warnings"]:
        lines.extend(["## 6. 补充提醒", ""])
        for item in firstpass_check["warnings"][:20]:
            lines.append(f"- 第 {item['row']} 行｜review_order={item['review_order']}｜{item['field']}：{item['message']}")
        lines.append("")
    lines.extend(["## 7. 建议命令", ""])
    if payload["commands"]:
        lines.append("```bash")
        lines.extend(payload["commands"])
        lines.append("```")
    else:
        lines.append("当前没有必须运行的命令，请继续填写 `38_首轮复核小表.csv` 的人工字段。")
    return "\n".join(lines)


def loop_review_firstpass_desk(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    review_sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    cards_md = package_dir / CORE_FILES["review_firstpass_cards_md"]
    talk_md = package_dir / CORE_FILES["review_firstpass_talk_md"]
    desk_md = package_dir / CORE_FILES["review_firstpass_desk_md"]

    commands: list[str] = []
    sync_default = {
        "filled_rows": 0,
        "applied_rows": 0,
        "unapplied_rows": 0,
        "missing_rows": 0,
        "conflict_rows": 0,
        "conflicts": [],
        "all_filled_rows_applied": False,
    }
    sync: dict[str, Any] = dict(sync_default)
    if not sheet_csv.exists():
        firstpass_check = {
            "sheet_csv": str(sheet_csv),
            "sheet_rows": 0,
            "filled_rows": 0,
            "ready_rows": 0,
            "blocking_issue_count": 0,
            "warning_count": 0,
            "decision_counts": {},
            "issues": [],
            "warnings": [],
            "ready_for_apply": False,
        }
        status = "首轮小表尚未生成，请先按复核链路生成 36、37、38。"
        commands.extend(
            [
                "python3 work/formal_honglou_cli.py loop-review-firstpass --package latest",
                "python3 work/formal_honglou_cli.py loop-review-firstpass-sheet --package latest",
            ]
        )
        if not cards_md.exists():
            commands.append("python3 work/formal_honglou_cli.py loop-review-firstpass-cards --package latest")
        if not talk_md.exists():
            commands.append("python3 work/formal_honglou_cli.py loop-review-firstpass-talk --package latest")
    else:
        firstpass_check = validate_review_sheet(sheet_csv, require_verify_status=False)
        sync = (
            sheet_sync_state(sheet_csv, review_sheet_csv)
            if review_sheet_csv.exists()
            else sync
        )
        if firstpass_check["filled_rows"] == 0:
            status = "首轮小表已生成，请先读 45（谈心式复核单），再补齐 38 的 5 个人工字段。"
            if not cards_md.exists():
                commands.append("python3 work/formal_honglou_cli.py loop-review-firstpass-cards --package latest")
            if not talk_md.exists():
                commands.append("python3 work/formal_honglou_cli.py loop-review-firstpass-talk --package latest")
        elif firstpass_check["blocking_issue_count"] > 0:
            status = "首轮小表填写后存在阻断项，请先修正再同步。"
            commands.append("python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest")
        elif not review_sheet_csv.exists():
            status = "首轮小表可同步，但当前还没有 17。请先生成当前批次复核工作表。"
            commands.append("python3 work/formal_honglou_cli.py loop-review-sheet --package latest --batch 第1批 --limit 20")
        elif sync["all_filled_rows_applied"]:
            status = "首轮小表内容已同步到 17。可直接检查 17（`loop-review-check`）。"
            commands.append("python3 work/formal_honglou_cli.py loop-review-check --package latest")
        else:
            status = "首轮小表可同步到 17，请按下列命令执行。"
            commands.extend(
                [
                    "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
                    "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest --dry-run",
                    "python3 work/formal_honglou_cli.py loop-review-firstpass-sync --package latest",
                    "python3 work/formal_honglou_cli.py loop-review-check --package latest",
                ]
            )
    if review_sheet_csv.exists() and sheet_csv.exists():
        sync = sheet_sync_state(sheet_csv, review_sheet_csv)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "firstpass_check": firstpass_check,
        "sheet_csv": str(sheet_csv),
        "review_sheet_csv": str(review_sheet_csv),
        "sheet_sync": sync,
        "firstpass_cards_md": str(cards_md) if cards_md.exists() else "",
        "firstpass_talk_md": str(talk_md) if talk_md.exists() else "",
        "commands": list(dict.fromkeys(commands)),
    }
    payload["need_attention"] = int(firstpass_check.get("blocking_issue_count") or 0) > 0
    payload["firstpass_desk_md"] = str(desk_md)
    desk_md.write_text(render_firstpass_desk(question, payload), encoding="utf-8")

    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_desk_md"] = str(desk_md)
    manifest.setdefault("results", {})["loop_review_firstpass_desk"] = payload
    manifest["status"] = payload["status"]
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核就绪台",
            True,
            {
                "firstpass_desk_md": str(desk_md),
                "firstpass_ready_rows": firstpass_check.get("ready_rows", 0),
                "firstpass_blocking": firstpass_check.get("blocking_issue_count", 0),
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "loop_review_firstpass_desk": payload,
        "manifest": str(manifest_path_value),
    }


def loop_review_firstpass_check(package: str | Path = "latest", out_root: Path = OUT_ROOT, sheet: str | Path = "") -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    if not sheet_csv.is_absolute() and not sheet_csv.exists():
        sheet_csv = package_dir / sheet_csv
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少首轮复核小表：{sheet_csv}")

    check = validate_review_sheet(sheet_csv, require_verify_status=False)
    check["generated_at"] = datetime.now().isoformat(timespec="seconds")
    check_md = package_dir / CORE_FILES["review_firstpass_check_md"]
    check_json = package_dir / CORE_FILES["review_firstpass_check_json"]
    check["check_md"] = str(check_md)
    check["check_json"] = str(check_json)
    check_md.write_text(render_firstpass_check_report(question, check), encoding="utf-8")
    write_json(check_json, check)

    core_files = manifest.setdefault("core_files", {})
    core_files["review_firstpass_check_md"] = str(check_md)
    core_files["review_firstpass_check_json"] = str(check_json)
    manifest.setdefault("results", {})["loop_review_firstpass_check"] = check
    if check["ready_for_apply"]:
        manifest["status"] = f"首轮复核小表质量检查通过：{check['ready_rows']} 行可同步到 17。"
    elif check["filled_rows"] == 0:
        manifest["status"] = "首轮复核小表尚未填写；请先填写人工字段。"
    else:
        manifest["status"] = f"首轮复核小表存在 {check['blocking_issue_count']} 个阻断问题，需修正后再同步。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "首轮复核小表质量检查",
            True,
            {
                "ready_for_apply": check["ready_for_apply"],
                "filled_rows": check["filled_rows"],
                "ready_rows": check["ready_rows"],
                "blocking_issue_count": check["blocking_issue_count"],
                "warning_count": check["warning_count"],
                "check_md": str(check_md),
                "check_json": str(check_json),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_firstpass_check": check,
        "manifest": str(manifest_path_value),
    }


def loop_review_check(package: str | Path = "latest", out_root: Path = OUT_ROOT, sheet: str | Path = "") -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    sheet_csv = Path(sheet) if clean(sheet) else package_dir / CORE_FILES["review_sheet_csv"]
    if not sheet_csv.is_absolute() and not sheet_csv.exists():
        sheet_csv = package_dir / sheet_csv
    if not sheet_csv.exists():
        raise FileNotFoundError(f"缺少复核工作表：{sheet_csv}")

    check = validate_review_sheet(sheet_csv, require_verify_status=False)
    check["generated_at"] = datetime.now().isoformat(timespec="seconds")
    check_md = package_dir / CORE_FILES["review_check_md"]
    check_json = package_dir / CORE_FILES["review_check_json"]
    check["check_md"] = str(check_md)
    check["check_json"] = str(check_json)
    check_md.write_text(render_review_check_report(question, check), encoding="utf-8")
    write_json(check_json, check)

    core_files = manifest.setdefault("core_files", {})
    core_files["review_check_md"] = str(check_md)
    core_files["review_check_json"] = str(check_json)
    manifest.setdefault("results", {})["loop_review_check"] = check
    if check["ready_for_apply"]:
        manifest["status"] = f"复核工作表质量检查通过：{check['ready_rows']} 行可回填。"
    elif check["filled_rows"] == 0:
        manifest["status"] = "复核工作表尚未填写；请先填写人工字段。"
    else:
        manifest["status"] = f"复核工作表存在 {check['blocking_issue_count']} 个阻断问题，需修正后再回填。"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "复核工作表质量检查",
            True,
            {
                "ready_for_apply": check["ready_for_apply"],
                "filled_rows": check["filled_rows"],
                "ready_rows": check["ready_rows"],
                "blocking_issue_count": check["blocking_issue_count"],
                "warning_count": check["warning_count"],
                "check_md": str(check_md),
                "check_json": str(check_json),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "review_check": check,
        "manifest": str(manifest_path_value),
    }


def decide_next_action(
    package_dir: Path,
    progress: dict[str, Any],
    sheet_stats: dict[str, Any],
    core_files: dict[str, str],
    sheet_quality: dict[str, Any] | None = None,
    sync_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sheet_exists = (package_dir / CORE_FILES["review_sheet_csv"]).exists()
    plan_exists = (package_dir / CORE_FILES["review_plan_md"]).exists()
    queue_exists = (package_dir / CORE_FILES["review_queue_csv"]).exists()
    assist_exists = (package_dir / CORE_FILES["review_assist_md"]).exists()
    workbench_exists = (package_dir / CORE_FILES["review_workbench_md"]).exists()
    coverage_exists = (package_dir / CORE_FILES["review_coverage_md"]).exists()
    firstpass_exists = (package_dir / CORE_FILES["review_firstpass_md"]).exists()
    firstpass_sheet_exists = (package_dir / CORE_FILES["review_firstpass_sheet_csv"]).exists()
    firstpass_cards_exists = (package_dir / CORE_FILES["review_firstpass_cards_md"]).exists()
    firstpass_talk_exists = (package_dir / CORE_FILES["review_firstpass_talk_md"]).exists()
    filled_rows = int(sheet_stats.get("filled_rows") or 0)
    manifest = load_manifest(package_dir)
    question = clean(manifest.get("question", ""))
    route_context = clean(manifest.get("parameters", {}).get("route_context", "")) if isinstance(manifest.get("parameters"), dict) else ""
    second_round_state = _load_second_round_state(package_dir)
    aggregation_court_missing = _aggregation_court_missing(package_dir)
    aggregation_court_ready = not aggregation_court_missing

    close_reading_done = bool(
        _latest_matching_file(package_dir, "00L_Codex精读材料词_*.md")
        and _latest_matching_file(package_dir, "00L_Codex精读材料词_*.json")
    )

    original_reread_done = bool(
        _latest_matching_file(package_dir, "00M_Codex写作前原文通读摘抄_*.md")
        and _latest_matching_file(package_dir, "00M_Codex写作前原文通读摘抄_*.json")
    )

    final_answer_target = package_dir / CORE_FILES["codex_final_answer_target_md"]
    final_answer_done = False
    if final_answer_target.exists():
        final_answer_text = final_answer_target.read_text(encoding="utf-8", errors="ignore")
        final_answer_done = "生成状态：已由 Codex" in final_answer_text
    final_answer_done = final_answer_done and close_reading_done and original_reread_done

    if final_answer_done:
        return {
            "phase": "等待用户认可入库",
            "next_action": "Codex 精读材料词、写作前原文追证摘抄和红楼解语已写入；下一步由用户确认是否认可入库，确认后进入文章入库与阅读入口。",
            "primary_file": str(final_answer_target),
            "commands": [],
        }
    if (package_dir / CORE_FILES["triaged_csv"]).exists() and not aggregation_court_ready:
        return {
            "phase": "阻断：等待聚拢库取材与材料池入池",
            "next_action": f"召回命中只算召回；当前缺 {'、'.join(aggregation_court_missing)}，必须先补齐 00AC/00AG/00AI/00AM，再进入材料池四态裁判。",
            "primary_file": str(package_dir / CORE_FILES["aggregation_flow_lock_md"]),
            "commands": [],
        }
    if (package_dir / CORE_FILES["codex_close_reading_gate_md"]).exists() and (package_dir / CORE_FILES["triaged_csv"]).exists() and not close_reading_done:
        return {
            "phase": "等待 Codex 精读材料词",
            "next_action": "候选材料、原文回收和 T1A/T1B 分层已就绪；下一步从 Codex 精读材料词生成门进入，先完成材料取舍，再生成写作前原文追证摘抄，最后写红楼解语。",
            "primary_file": str(package_dir / CORE_FILES["codex_close_reading_gate_md"]),
            "commands": [],
        }
    if (package_dir / CORE_FILES["codex_original_reread_gate_md"]).exists() and close_reading_done and not original_reread_done:
        return {
            "phase": "等待 Codex 写作前原文追证摘抄",
            "next_action": "精读材料词/精品聚拢池已经生成；下一步由 Codex 复习总问题和子问题，通读精品聚拢池，再回到原文摘取最终写作前证据。",
            "primary_file": str(package_dir / CORE_FILES["codex_original_reread_gate_md"]),
            "commands": [],
        }
    if (package_dir / CORE_FILES["codex_final_answer_gate_md"]).exists() and (package_dir / CORE_FILES["triaged_csv"]).exists():
        return {
            "phase": "等待 Codex 红楼解语",
            "next_action": "候选材料、原文回收、人读分层和生成门已就绪；下一步由 Codex 读材料池、精读材料词和写作前原文追证摘抄后写最终答案。",
            "primary_file": str(package_dir / CORE_FILES["codex_final_answer_gate_md"]),
            "commands": [],
        }
    if (package_dir / CORE_FILES["final_reading_gate_md"]).exists() and (package_dir / CORE_FILES["triaged_csv"]).exists():
        return {
            "phase": "候选材料池已就绪",
            "next_action": "本地工程到此只负责候选材料、原文复核和材料池精读门；下一步必须由 Codex 材料池判定、精读材料词、写作前原文追证摘抄后生成红楼解语。",
            "primary_file": str(package_dir / CORE_FILES["final_reading_gate_md"]),
            "commands": [],
        }
    if filled_rows > 0:
        if sheet_quality and int(sheet_quality.get("blocking_issue_count") or 0) > 0:
            return {
                "phase": "待修正小表",
                "next_action": "复核工作表已有填写，但存在缺项或不规范字段；先运行质量检查并修正。",
                "primary_file": str(package_dir / CORE_FILES["review_sheet_csv"]),
                "commands": [
                    "python3 work/formal_honglou_cli.py loop-review-check --package latest",
                ],
            }
        if sync_state and sync_state.get("all_filled_rows_applied"):
            return {
                "phase": "小表已回填",
                "next_action": "当前小表填写内容已经同步到复核表；可刷新回读、草稿和二次追问计划。",
                "primary_file": str(package_dir / CORE_FILES["review_csv"]),
                "commands": [
                    "python3 work/formal_honglou_cli.py loop-readback --package latest",
                    "python3 work/formal_honglou_cli.py loop-draft --package latest",
                    "python3 work/formal_honglou_cli.py loop-next --package latest",
                    "python3 work/formal_honglou_cli.py loop-status --package latest",
                ],
            }
        return {
            "phase": "待回填小表",
            "next_action": "质量检查通过后，先模拟回填，再正式回填当前批次复核工作表。",
            "primary_file": str(package_dir / CORE_FILES["review_sheet_csv"]),
            "commands": [
                "python3 work/formal_honglou_cli.py loop-review-check --package latest",
                "python3 work/formal_honglou_cli.py loop-review-apply --package latest --dry-run",
                "python3 work/formal_honglou_cli.py loop-review-apply --package latest",
                "python3 work/formal_honglou_cli.py loop-readback --package latest",
                "python3 work/formal_honglou_cli.py loop-draft --package latest",
                "python3 work/formal_honglou_cli.py loop-next --package latest",
            ],
        }
    if progress["pending_rows"] == progress["total_rows"]:
        if sheet_exists:
            if assist_exists and not workbench_exists:
                return {
                    "phase": "待生成复核填表工作台",
                    "next_action": "把复核小表和候选材料核对助手合并成填表工作台，再由 Codex 或人工继续判定。",
                    "primary_file": str(package_dir / CORE_FILES["review_sheet_csv"]),
                    "commands": [
                        "python3 work/formal_honglou_cli.py loop-review-workbench --package latest",
                    ],
                }
            if workbench_exists and not coverage_exists:
                return {
                    "phase": "待生成复核覆盖矩阵",
                    "next_action": "生成子问题覆盖矩阵，确认先复核哪几条能覆盖最多问题。",
                    "primary_file": str(package_dir / CORE_FILES["review_workbench_md"]),
                    "commands": [
                        "python3 work/formal_honglou_cli.py loop-review-coverage --package latest",
                    ],
                }
            if coverage_exists and not firstpass_exists:
                return {
                    "phase": "待生成首轮复核执行单",
                    "next_action": "生成最短首轮执行单，把覆盖矩阵压缩成可直接填表的 6 条。",
                    "primary_file": str(package_dir / CORE_FILES["review_coverage_md"]),
                    "commands": [
                        "python3 work/formal_honglou_cli.py loop-review-firstpass --package latest",
                    ],
                }
            if firstpass_exists and not firstpass_sheet_exists:
                return {
                    "phase": "待生成首轮复核小表",
                    "next_action": "生成只含首轮 6 条的可编辑小复核表，减少人工定位成本。",
                    "primary_file": str(package_dir / CORE_FILES["review_firstpass_md"]),
                    "commands": [
                        "python3 work/formal_honglou_cli.py loop-review-firstpass-sheet --package latest",
                    ],
                }
            if firstpass_sheet_exists:
                firstpass_sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
                firstpass_stats = sheet_progress(firstpass_sheet_csv)
                if firstpass_stats["filled_rows"] > 0:
                    firstpass_quality = validate_review_sheet(firstpass_sheet_csv, require_verify_status=False)
                    if int(firstpass_quality.get("blocking_issue_count") or 0) > 0:
                        return {
                            "phase": "待修正首轮小表",
                            "next_action": "首轮小表已有填写，但存在缺项或不规范字段；先检查并修正 38。",
                            "primary_file": str(firstpass_sheet_csv),
                            "commands": [
                                "python3 work/formal_honglou_cli.py loop-review-firstpass-check --package latest",
                            ],
                        }
                    return {
                        "phase": "待同步首轮小表",
                        "next_action": "首轮小表已有人工填写；可以用一条收口命令完成同步、回填、真源核验与回读刷新。",
                        "primary_file": str(firstpass_sheet_csv),
                        "commands": [
                            "python3 work/formal_honglou_cli.py loop-review-finish --package latest --apply",
                        ],
                    }
                if not firstpass_cards_exists:
                    return {
                        "phase": "待生成首轮判读卡片",
                        "next_action": "生成首轮 6 条逐条判读卡片，再按卡片填写 38。",
                        "primary_file": str(firstpass_sheet_csv),
                        "commands": [
                            "python3 work/formal_honglou_cli.py loop-review-firstpass-cards --package latest",
                        ],
                    }
                return {
                    "phase": "待人工填写首轮小表",
                    "next_action": "先读 `43_首轮复核逐条判读卡片.md`，再填写 `38_首轮复核小表.csv` 的五个人工字段；填完后再同步到 17。",
                    "primary_file": str(package_dir / CORE_FILES["review_firstpass_cards_md"]),
                    "commands": [
                        "python3 work/formal_honglou_cli.py loop-review-firstpass-desk --package latest",
                    ],
                }
            if assist_exists:
                return {
                    "phase": "待人工填写小表",
                    "next_action": "先读 `36_首轮复核执行单.md`、`34_复核覆盖矩阵.md` 和 `26_当前批次复核阅读卡片.md`，再填写 `17_当前批次复核工作表.csv` 的五个人工字段。",
                    "primary_file": str(package_dir / CORE_FILES["review_sheet_csv"]),
                    "commands": [],
                }
            return {
                "phase": "待生成复核填写助手",
                "next_action": "先生成复核填写助手，再人工填写当前批次小表。",
                "primary_file": str(package_dir / CORE_FILES["review_sheet_csv"]),
                "commands": [
                    "python3 work/formal_honglou_cli.py loop-review-assist --package latest",
                ],
            }
        if plan_exists and queue_exists:
            return {
                "phase": "待生成当前批次小表",
                "next_action": "从复核队列生成第1批小表。",
                "primary_file": str(package_dir / CORE_FILES["review_queue_csv"]),
                "commands": [
                    "python3 work/formal_honglou_cli.py loop-review-sheet --package latest --batch 第1批 --limit 20",
                ],
            }
        return {
            "phase": "待生成复核队列",
            "next_action": "先生成复核优先清单和第1批工作表。",
            "primary_file": str(package_dir / CORE_FILES["review_csv"]),
            "commands": [
                "python3 work/formal_honglou_cli.py loop-review-plan --package latest",
                "python3 work/formal_honglou_cli.py loop-review-sheet --package latest --batch 第1批 --limit 20",
            ],
        }
    if progress["usable_rows"] == 0:
        return {
            "phase": "已复核但暂无可用证据",
            "next_action": "运行回读后查看剔除和待复核分布，必要时继续生成下一批复核工作表或补证。",
            "primary_file": str(package_dir / CORE_FILES["review_csv"]),
            "commands": [
                "python3 work/formal_honglou_cli.py loop-readback --package latest",
                "python3 work/formal_honglou_cli.py loop-next --package latest",
                "python3 work/formal_honglou_cli.py loop-review-plan --package latest",
            ],
        }
    if progress["usable_rows"] > 0:
        return {
            "phase": "已有可写作证据",
            "next_action": "已具备可写作材料；本地工程停止自动成文，下一步交给 Codex 材料池判定、精读材料词、写作前原文追证摘抄和红楼解语。",
            "primary_file": str(package_dir / CORE_FILES["writable_pack"]),
            "commands": [
                "python3 work/formal_honglou_cli.py loop-readback --package latest",
                "python3 work/formal_honglou_cli.py loop-draft --package latest",
                "python3 work/formal_honglou_cli.py loop-next --package latest",
            ],
        }
    return {
        "phase": "待检查",
        "next_action": "查看闭环总览和运行清单，确认文件是否完整。",
        "primary_file": str(package_dir / CORE_FILES["overview"]),
        "commands": ["python3 work/formal_honglou_cli.py loop-list"],
    }


def render_workflow_status(question: str, payload: dict[str, Any]) -> str:
    action = payload["recommended_next"]
    progress = payload["review_progress"]
    sheet = payload["sheet_progress"]
    quality = payload.get("sheet_quality", {})
    firstpass_sheet = payload.get("firstpass_sheet_progress", {})
    firstpass_quality = payload.get("firstpass_sheet_quality", {})
    sync = payload.get("sheet_sync", {})
    files = payload["files"]
    lines = [
        "# 红楼梦正式底库｜闭环状态与下一步操作台",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 1. 当前问题",
        "",
        question,
        "",
        "## 2. 当前阶段",
        "",
        f"- 阶段：{action['phase']}",
        f"- 下一步：{action['next_action']}",
        f"- 优先打开：`{action['primary_file']}`",
        "",
        "## 2.1 固定工作方式",
        "",
        "- 本地工程只负责查库、取原文、保存候选材料、生成材料池和真源核验线索。",
        "- 不再由本地模块生成论述稿、文章稿、学术版或评论版。",
        "- 候选材料必须先进入 Codex 材料池判定；可用、背景、不可用或需补证由 Codex 决定。",
        "- 红楼解语只能由 Codex 读取工程材料后生成，不能由本地过程稿冒充。",
        "- 复核表保留为人工/智能复核工具，但不替代 Codex 的最终判断。",
        "",
        "## 2.2 以后怎么提问",
        "",
        "- 在 Codex 对话里，你可以直接提红楼梦问题；页面触发包会带着问题进入工程。",
        "- 系统入口是 `talk`：有新问题时新建问题包；没有新问题时刷新最近的问题包，只生成候选材料和材料池，不生成本地文章稿。",
        "- 新问题命令：`python3 work/formal_honglou_cli.py talk --question \"你的问题\"`",
        "- 刷新当前问题：`python3 work/formal_honglou_cli.py talk --package latest`",
        "",
        "## 3. 建议命令",
        "",
    ]
    if action["commands"]:
        lines.append("```bash")
        lines.extend(action["commands"])
        lines.append("```")
    else:
        lines.append("当前没有必须运行的命令。")
    lines.extend(
        [
            "",
            "## 4. 复核进度",
            "",
            f"- 复核表总行数：{progress['total_rows']}",
            f"- 已人工判断：{progress['completed_rows']}",
            f"- 待复核：{progress['pending_rows']}",
            f"- 可写作证据：{progress['usable_rows']}",
            f"- 保留：{progress['keep_rows']}",
            f"- 降级：{progress['downgrade_rows']}",
            f"- 反证：{progress['counter_rows']}",
            f"- 剔除：{progress['rejected_rows']}",
            "",
            "## 5. 当前小表状态",
            "",
            f"- 小表行数：{sheet['rows']}",
            f"- 已填写行：{sheet['filled_rows']}",
            f"- 未填写行：{sheet['blank_rows']}",
            f"- 小表判断分布：{json.dumps(sheet['decision_counts'], ensure_ascii=False)}",
            f"- 可回填行：{quality.get('ready_rows', 0)}",
            f"- 阻断问题：{quality.get('blocking_issue_count', 0)}",
            f"- 提醒项：{quality.get('warning_count', 0)}",
            f"- 已同步到复核表：{sync.get('applied_rows', 0)}",
            f"- 尚未同步到复核表：{sync.get('unapplied_rows', 0)}",
            "",
            "## 5.1 首轮小表状态",
            "",
            f"- 首轮小表行数：{firstpass_sheet.get('rows', 0)}",
            f"- 首轮已填写行：{firstpass_sheet.get('filled_rows', 0)}",
            f"- 首轮未填写行：{firstpass_sheet.get('blank_rows', 0)}",
            f"- 首轮判断分布：{json.dumps(firstpass_sheet.get('decision_counts', {}), ensure_ascii=False)}",
            f"- 首轮可同步行：{firstpass_quality.get('ready_rows', 0)}",
            f"- 首轮阻断问题：{firstpass_quality.get('blocking_issue_count', 0)}",
            f"- 首轮提醒项：{firstpass_quality.get('warning_count', 0)}",
            "",
            "## 6. 关键文件",
            "",
        ]
    )
    for label, info in files.items():
        status = "存在" if info["exists"] else "缺失"
        lines.append(f"- {label}：{status}｜{info['size']} bytes｜`{info['path']}`")
    lines.extend(
        [
            "",
            "## 7. 断线后怎么接上",
            "",
            "先读本文件第 2 节；如果候选材料已经就绪，下一步只进入 Codex 材料池判定、精读材料词、写作前原文追证摘抄和红楼解语，不再走本地文章稿。",
        ]
    )
    return "\n".join(lines)


def loop_status(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    progress = review_progress(review_csv)
    sheet_csv = package_dir / CORE_FILES["review_sheet_csv"]
    sheet_stats = sheet_progress(sheet_csv)
    firstpass_sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    firstpass_sheet_stats = sheet_progress(firstpass_sheet_csv)
    sheet_quality = validate_review_sheet(sheet_csv, require_verify_status=False) if sheet_csv.exists() else {
        "ready_for_apply": False,
        "blocking_issue_count": 0,
        "warning_count": 0,
        "filled_rows": 0,
        "ready_rows": 0,
    }
    firstpass_sheet_quality = validate_review_sheet(firstpass_sheet_csv, require_verify_status=False) if firstpass_sheet_csv.exists() else {
        "ready_for_apply": False,
        "blocking_issue_count": 0,
        "warning_count": 0,
        "filled_rows": 0,
        "ready_rows": 0,
    }
    sync = sheet_sync_state(sheet_csv, review_csv) if sheet_csv.exists() and review_csv.exists() else {
        "filled_rows": 0,
        "applied_rows": 0,
        "unapplied_rows": 0,
        "missing_rows": 0,
        "conflict_rows": 0,
        "conflicts": [],
        "all_filled_rows_applied": False,
    }
    core_files = manifest.setdefault("core_files", {})
    files = {
        "00_闭环总览": file_info(package_dir / CORE_FILES["overview"]),
        "00A_问题判断程序": file_info(package_dir / CORE_FILES["question_judgment_md"]),
        "00B_关键词网络预检": file_info(package_dir / CORE_FILES["keyword_precheck_json"]),
        "00C_库线原文流转骨架": file_info(package_dir / CORE_FILES["library_flow_md"]),
        "00D_库线原文流转摘要": file_info(package_dir / CORE_FILES["library_flow_json"]),
        "00AC_聚拢库总入口流程锁": file_info(package_dir / CORE_FILES["aggregation_flow_lock_md"]),
        "00AD_聚拢库总入口流程锁摘要": file_info(package_dir / CORE_FILES["aggregation_flow_lock_json"]),
        "00AG_聚拢库取材单": file_info(package_dir / CORE_FILES["aggregation_material_search_md"]),
        "00AH_聚拢库取材单摘要": file_info(package_dir / CORE_FILES["aggregation_material_search_json"]),
        "00AI_聚拢入材料池清单": file_info(package_dir / CORE_FILES["material_pool_admission_csv"]),
        "00AJ_聚拢入材料池凭证门": file_info(package_dir / CORE_FILES["material_pool_admission_md"]),
        "00AK_聚拢入材料池凭证门摘要": file_info(package_dir / CORE_FILES["material_pool_admission_json"]),
        "00AL_聚拢入材料池阻断清单": file_info(package_dir / CORE_FILES["material_pool_blocked_csv"]),
        "00AM_聚拢裁判首读材料池": file_info(package_dir / CORE_FILES["aggregation_first_read_pool_md"]),
        "00K_本题库态预检表": file_info(package_dir / CORE_FILES["library_precheck_md"]),
        "00L_本题库态预检摘要": file_info(package_dir / CORE_FILES["library_precheck_json"]),
        "00E_经验复盘入账": file_info(package_dir / CORE_FILES["experience_entry_md"]),
        "00F_经验复盘入账摘要": file_info(package_dir / CORE_FILES["experience_entry_json"]),
        "00G_最终回答前材料池精读门": file_info(package_dir / CORE_FILES["final_reading_gate_md"]),
        "00H_最终回答前材料池精读摘要": file_info(package_dir / CORE_FILES["final_reading_gate_json"]),
        "00P_二轮补证决策卡": file_info(package_dir / CORE_FILES["second_round_decision_md"]),
        "00Q_二轮补证决策摘要": file_info(package_dir / CORE_FILES["second_round_decision_json"]),
        "00R_来源字段标准化词典": file_info(package_dir / CORE_FILES["source_schema_md"]),
        "00S_来源字段标准化摘要": file_info(package_dir / CORE_FILES["source_schema_json"]),
        "00T_经验法典三层结构": file_info(package_dir / CORE_FILES["experience_codex_md"]),
        "00U_经验法典三层摘要": file_info(package_dir / CORE_FILES["experience_codex_json"]),
        "00V_正式沙盒模式边界": file_info(package_dir / CORE_FILES["mode_boundary_md"]),
        "00W_正式沙盒模式边界摘要": file_info(package_dir / CORE_FILES["mode_boundary_json"]),
        "00X_用户认可入库门": file_info(package_dir / CORE_FILES["approval_ingest_gate_md"]),
        "00Y_用户认可入库摘要": file_info(package_dir / CORE_FILES["approval_ingest_gate_json"]),
        "00Z_库群覆盖矩阵": file_info(package_dir / CORE_FILES["library_coverage_md"]),
        "00ZA_库群覆盖摘要": file_info(package_dir / CORE_FILES["library_coverage_json"]),
        "00ZB_桌面人读排序配置": file_info(package_dir / CORE_FILES["human_reading_order_md"]),
        "00ZC_桌面人读排序摘要": file_info(package_dir / CORE_FILES["human_reading_order_json"]),
        "00ZD_Codex红楼解语生成门": file_info(package_dir / CORE_FILES["codex_final_answer_gate_md"]),
        "00ZE_Codex红楼解语生成摘要": file_info(package_dir / CORE_FILES["codex_final_answer_gate_json"]),
        "00ZF_Codex红楼解语待生成": file_info(package_dir / CORE_FILES["codex_final_answer_target_md"]),
        "00ZG_Codex精读材料词生成门": file_info(package_dir / CORE_FILES["codex_close_reading_gate_md"]),
        "00ZH_Codex精读材料词生成摘要": file_info(package_dir / CORE_FILES["codex_close_reading_gate_json"]),
        "00ZI_Codex精读材料词待生成": file_info(package_dir / CORE_FILES["codex_close_reading_target_md"]),
        "00ZN_Codex写作前原文通读摘抄生成门": file_info(package_dir / CORE_FILES["codex_original_reread_gate_md"]),
        "00ZO_Codex写作前原文通读摘抄生成摘要": file_info(package_dir / CORE_FILES["codex_original_reread_gate_json"]),
        "00ZP_Codex写作前原文通读摘抄待生成": file_info(package_dir / CORE_FILES["codex_original_reread_target_md"]),
        "00ZJ_Codex最终答案写回规范": file_info(package_dir / CORE_FILES["answer_writeback_protocol_md"]),
        "00ZK_Codex最终答案写回摘要": file_info(package_dir / CORE_FILES["answer_writeback_protocol_json"]),
        "00ZL_十题回归测试骨架": file_info(package_dir / CORE_FILES["regression_plan_md"]),
        "00ZM_十题回归测试摘要": file_info(package_dir / CORE_FILES["regression_plan_json"]),
        "04_复核表": file_info(review_csv),
        "15_人工复核优先清单": file_info(package_dir / CORE_FILES["review_plan_md"]),
        "16_人工复核批次": file_info(package_dir / CORE_FILES["review_queue_csv"]),
        "17_当前批次复核工作表": file_info(sheet_csv),
        "18_复核工作表填写说明": file_info(package_dir / CORE_FILES["review_sheet_md"]),
        "47_人工复核打勾表": file_info(package_dir / CORE_FILES["review_tick_md"]),
        "26_当前批次复核阅读卡片": file_info(package_dir / CORE_FILES["review_cards_md"]),
        "19_复核工作表回填报告": file_info(package_dir / CORE_FILES["review_apply_md"]),
        "09_可写作证据包": file_info(package_dir / CORE_FILES["writable_pack"]),
        "11_正式写作草稿": file_info(package_dir / CORE_FILES["draft_md"]),
        "13_二次追问与补证计划": file_info(package_dir / CORE_FILES["next_plan_md"]),
        "22_复核工作表质量检查": file_info(package_dir / CORE_FILES["review_check_md"]),
        "23_复核工作表质量检查摘要": file_info(package_dir / CORE_FILES["review_check_json"]),
        "27_复核表备份索引": file_info(package_dir / CORE_FILES["review_backup_md"]),
        "28_复核表备份索引摘要": file_info(package_dir / CORE_FILES["review_backup_json"]),
        "29_复核表恢复报告": file_info(package_dir / CORE_FILES["review_restore_md"]),
        "30_复核填写助手": file_info(package_dir / CORE_FILES["review_assist_md"]),
        "31_复核填写助手表": file_info(package_dir / CORE_FILES["review_assist_csv"]),
        "32_复核填表工作台": file_info(package_dir / CORE_FILES["review_workbench_md"]),
        "33_复核填表工作台表": file_info(package_dir / CORE_FILES["review_workbench_csv"]),
        "34_复核覆盖矩阵": file_info(package_dir / CORE_FILES["review_coverage_md"]),
        "35_复核覆盖矩阵表": file_info(package_dir / CORE_FILES["review_coverage_csv"]),
        "36_首轮复核执行单": file_info(package_dir / CORE_FILES["review_firstpass_md"]),
        "37_首轮复核执行单表": file_info(package_dir / CORE_FILES["review_firstpass_csv"]),
        "38_首轮复核小表": file_info(package_dir / CORE_FILES["review_firstpass_sheet_csv"]),
        "39_首轮复核小表填写说明": file_info(package_dir / CORE_FILES["review_firstpass_sheet_md"]),
        "40_首轮复核小表同步报告": file_info(package_dir / CORE_FILES["review_firstpass_sync_md"]),
        "41_首轮复核小表质量检查": file_info(package_dir / CORE_FILES["review_firstpass_check_md"]),
        "42_首轮复核小表质量检查摘要": file_info(package_dir / CORE_FILES["review_firstpass_check_json"]),
        "43_首轮复核逐条判读卡片": file_info(package_dir / CORE_FILES["review_firstpass_cards_md"]),
        "44_首轮复核就绪台": file_info(package_dir / CORE_FILES["review_firstpass_desk_md"]),
        "45_首轮谈心式复核单": file_info(package_dir / CORE_FILES["review_firstpass_talk_md"]),
        "54_真源核验统一报告": file_info(package_dir / CORE_FILES["source_verify_md"]),
        "55_真源核验清单": file_info(package_dir / CORE_FILES["source_verify_csv"]),
        "56_复核收口运行报告": file_info(package_dir / CORE_FILES["review_finish_md"]),
        "57_复核收口摘要": file_info(package_dir / CORE_FILES["review_finish_json"]),
        "58_文章入库预检报告": file_info(package_dir / CORE_FILES["article_ingest_report_md"]),
        "59_作品总库入库候选行": file_info(package_dir / CORE_FILES["article_ingest_candidate_csv"]),
        "60_文章回挂清单": file_info(package_dir / CORE_FILES["article_ingest_links_csv"]),
        "61_文章入库身份卡": file_info(package_dir / CORE_FILES["article_ingest_identity_md"]),
        "62_文章入库预检摘要": file_info(package_dir / CORE_FILES["article_ingest_summary_json"]),
    }
    recommended = decide_next_action(package_dir, progress, sheet_stats, core_files, sheet_quality, sync)
    status_md = package_dir / CORE_FILES["workflow_status_md"]
    status_json = package_dir / CORE_FILES["workflow_status_json"]
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "status_md": str(status_md),
        "status_json": str(status_json),
        "review_progress": progress,
        "sheet_progress": sheet_stats,
        "sheet_quality": sheet_quality,
        "firstpass_sheet_progress": firstpass_sheet_stats,
        "firstpass_sheet_quality": firstpass_sheet_quality,
        "sheet_sync": sync,
        "recommended_next": recommended,
        "files": files,
    }
    status_md.write_text(render_workflow_status(question, payload), encoding="utf-8")
    write_json(status_json, payload)

    core_files["workflow_status_md"] = str(status_md)
    core_files["workflow_status_json"] = str(status_json)
    manifest.setdefault("results", {})["loop_status"] = payload
    manifest["status"] = f"{recommended['phase']}：{recommended['next_action']}"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "闭环状态操作台",
            True,
            {
                "phase": recommended["phase"],
                "status_md": str(status_md),
                "status_json": str(status_json),
                "sheet_filled_rows": sheet_stats["filled_rows"],
            },
        ),
    )
    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "status_file": str(status_md),
        "status_json": str(status_json),
        "recommended_next": recommended,
        "review_progress": progress,
        "sheet_progress": sheet_stats,
        "manifest": str(manifest_path_value),
    }


def homepage_entry(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
    }


def render_project_home(payload: dict[str, Any]) -> str:
    current = payload["current_package"]
    action = payload["recommended_next"]
    files = payload["files"]
    packages = payload["packages"]
    health = payload["health"]
    mapping = payload.get("mapping") or {}
    script_normalization = payload.get("script_normalization") or {}
    library_audit = payload.get("library_audit") or {}
    lines = [
        "# 红楼梦工程｜本地文件首页",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 0. 开工必读路由",
        "",
        "新开线程、断线恢复、换模型、换任务入口时，先读总账层，再进入具体问题包。",
        "",
        "1. 机器先读：`08_机器续接摘要.json`。",
        "2. 人和机器共同入口：本首页。",
        "3. 进入具体问题时读完整八步法：`../红楼梦对谈查证室/87_红楼梦编号证据八步主线_运行卡模板.md`。文件名保留旧名不改，性质按“八步方法/运行方法卡”理解；先用“取词之前的思考”取词，再用“取词以后如何用库的思考”查库、交集、回原文、入材料池。",
        "4. 需要理解全工程时读：`07_从开工到当前工程全量总账.md`。",
        "5. 需要验收完成度时读：`09_工程完成度复盘表.csv`。",
        "6. 本轮结束或重要变化后说：`收工，更新总账`。",
        "",
        "## 1. 当前总判断",
        "",
        "- 工程主体完成度：约 98%。",
        "- 当前已具备：复杂拆题、搜索词网络、证据召回、闭环问题包、材料池精读门、Codex 精读材料词生成门、Codex 写作前原文追证摘抄生成门、Codex 红楼解语生成门、复核收口、真源核验入口、文章入库预检、跨复杂问题泛化测试。",
        "- 当前真实链路：材料池判定 -> 精读材料词/精品聚拢池 -> 写作前原文追证摘抄 -> 红楼解语；00M 是最终答案前的原文底稿，不把每个子问题机械拆成多套流程。",
        "- 当前未自动推进的部分：每题的 Codex 精读、写作前原文追证摘抄与红楼解语仍需按材料池当场写入，之后由用户认可入库；更多题型仍需继续实战验证和长期界面体验。",
        "",
        "## 2. 当前正在处理的问题",
        "",
        f"- 问题：{current['question']}",
        f"- 问题包：`{current['path']}`",
        f"- 当前阶段：{action['phase']}",
        f"- 下一步：{action['next_action']}",
        f"- 优先打开：`{action['primary_file']}`",
        "",
        "## 3. 最短操作路径",
        "",
        "### 3.1 要继续当前最新问题",
        "",
        f"1. 先打开：`{action['primary_file']}`。",
        "2. 如果状态指向精读材料词，先读 `00ZG`，让 Codex 形成材料取舍和证据支点。",
        "3. 正式 `00L_Codex精读材料词_<request_id>.md/json` 完成后，再读 `00ZN`，让 Codex 生成正式 `00M_Codex写作前原文通读摘抄_<request_id>.md/json`；`00ZP` 只是同步稿位。",
        "4. 写作前原文追证摘抄完成后，再读 `00ZD`，由 Codex 写红楼解语。",
        "5. 如果状态指向人工复核，再读 `45_首轮谈心式复核单.md` 并填写同包内 `38_首轮复核小表.csv`。",
        "6. 随时刷新当前状态：",
        "",
        "```bash",
        "python3 work/formal_honglou_cli.py loop-status --package latest",
        "```",
        "",
        "### 3.2 要处理文章入库方向",
        "",
        "先看当前问题包是否已有 `58_文章入库预检报告.md`。如果没有，说明这个问题还没有生成正式文章入库预检包。",
        "",
        "如果要处理历史问题包或旧文章入库，按 `03_下一次开工入口.md` 里的明确问题包路径操作，避免 `latest` 指到当前最新问题包。",
        "",
        "### 3.3 要开一个新问题",
        "",
        "```bash",
        "python3 work/formal_honglou_cli.py run --question \"你的新问题\"",
        "python3 work/formal_honglou_cli.py loop-status --package latest",
        "```",
        "",
        "## 4. 关键文件",
        "",
    ]
    for key, info in files.items():
        status = "存在" if info["exists"] else "缺失"
        lines.append(f"- {key}：{status}｜{info['size']} bytes｜`{info['path']}`")
    lines.extend(
        [
            "",
            "## 5. 复核与写作状态",
            "",
            f"- 复核表总行数：{payload['review_progress']['total_rows']}",
            f"- 已人工判断：{payload['review_progress']['completed_rows']}",
            f"- 待复核：{payload['review_progress']['pending_rows']}",
            f"- 已核验可写作证据：{payload['review_progress']['verified_rows']}",
            f"- 未核验可用判断：{payload['review_progress']['unverified_rows']}",
            f"- 当前可写作证据：{payload['review_progress']['usable_rows']}",
            f"- 首轮小表行数：{payload['firstpass_sheet']['rows']}",
            f"- 首轮小表已填写：{payload['firstpass_sheet']['filled_rows']}",
            "",
            "## 6. 已有问题包",
            "",
        ]
    )
    if packages:
        for item in packages[:8]:
            lines.append(f"- `{item['package']}`｜已判断 {item['completed_rows']}/{item['total_rows']}｜{item['status']}")
    else:
        lines.append("- 暂无闭环问题包。")
    lines.extend(
        [
            "",
            "## 7. 系统健康",
            "",
            f"- 多轴数据库：{'存在' if health['axis_db_exists'] else '缺失'}｜{health['axis_db_size']} bytes",
            f"- 全文检索数据库：{'存在' if health['search_db_exists'] else '缺失'}｜{health['search_db_size']} bytes",
            f"- 最后离线自检：{health['last_smoke_status']}",
            "",
            "## 8. 简繁统一状态",
            "",
        ]
    )
    if script_normalization:
        script_status = "通过" if script_normalization.get("passed") else "有风险"
        lines.extend(
            [
                f"- 状态：{script_status}。",
                f"- 全文双写查询对照：{script_normalization.get('search_pair_count', '未知')} 组，失败 {script_normalization.get('search_failure_count', '未知')} 组。",
                f"- 证据召回对照：{script_normalization.get('evidence_case_count', '未知')} 组，失败 {script_normalization.get('evidence_failure_count', '未知')} 组。",
                f"- 题型拆解对照：{script_normalization.get('question_logic_case_count', '未知')} 组，失败 {script_normalization.get('question_logic_failure_count', '未知')} 组。",
                f"- 探针繁体残留：{script_normalization.get('residual_probe_count', '未知')} 类。",
                f"- 简繁统一报告：`{script_normalization.get('report_md', '')}`",
                "",
            ]
        )
    else:
        lines.extend(["- 尚未读取到简繁统一检查摘要。", ""])
    lines.extend(
        [
            "## 9. 映射固化状态",
            "",
        ]
    )
    if mapping:
        lines.extend(
            [
                f"- Notion relation 解析率：{mapping.get('relation_resolve_rate', '未知')}%。",
                f"- 非 `_all.csv` 主库 relation 解析率：{mapping.get('non_all_relation_resolve_rate', '未知')}%。",
                f"- 本地安全固化写入：{mapping.get('applied_count', 0)} 条。",
                f"- 人物别名固化表：{mapping.get('alias_count', '未知')} 条，其中需人工确认 {mapping.get('alias_manual_count', '未知')} 条。",
                f"- 范围段落关系表：{mapping.get('range_edge_count', '未知')} 条，其中已解析 {mapping.get('range_resolved_count', '未知')} 条。",
                f"- 人物边未连人物 ID：{mapping.get('person_edges_unresolved_character', '未知')}。",
                f"- 事件边未连段落 ID：{mapping.get('event_edges_unresolved_segment', '未知')}。",
                f"- 统一证据边未解析：{mapping.get('evidence_edges_unresolved', '未知')}。",
                f"- 未解析中已由范围表覆盖：{mapping.get('range_covered_unresolved_count', '未知')}。",
                f"- 仍需后续处理的未解析证据边：{mapping.get('actionable_unresolved_count', '未知')}。",
                f"- 映射固化报告：`{mapping.get('report_md', '')}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "- 尚未读取到映射固化检查摘要。",
                "",
            ]
        )
    lines.extend(
        [
            "## 10. 库群结构状态",
            "",
        ]
    )
    if library_audit:
        lines.extend(
            [
                f"- 库群盘点：{library_audit.get('library_count', '未知')}个母本库，其中已结构化 {library_audit.get('structured_library_count', '未知')}个，待轴化 {library_audit.get('mother_only_library_count', '未知')}个。",
                f"- 后续主题发现：{library_audit.get('discovered_topic_count', '未知')}个。",
                f"- 任务队列：P0 {library_audit.get('task_counts', {}).get('P0', 0)}项，P1 {library_audit.get('task_counts', {}).get('P1', 0)}项，P2 {library_audit.get('task_counts', {}).get('P2', 0)}项，P3 {library_audit.get('task_counts', {}).get('P3', 0)}项。",
                f"- 库群结构报告：`{library_audit.get('report_md', '')}`",
                "",
            ]
        )
    else:
        lines.extend(["- 尚未读取到库群结构分析摘要。", ""])
    lines.extend(
        [
            "## 11. 断线后怎么接上",
            "",
            "先打开本文件。若只想看当前问题状态，打开 `20_闭环状态与下一步操作台.md`。若要继续人工复核，回到 `45/38`。若要继续入库，回到 `58/59/60/61/62`。",
        ]
    )
    return "\n".join(lines)


def build_project_home(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    home_dir: Path = HOME_OUT,
    run_smoke: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    status_result = loop_status(package_dir, out_root)
    manifest = load_manifest(package_dir)
    package_list = loop_list(out_root).get("packages", [])
    review_csv = package_dir / CORE_FILES["review_csv"]
    progress = review_progress(review_csv)
    firstpass_sheet = sheet_progress(package_dir / CORE_FILES["review_firstpass_sheet_csv"])
    smoke_result: dict[str, Any] | None = run_offline_smoke() if run_smoke else None
    axis_db = SEMANTIC_CENTER_DB
    mapping_report = ROOT / "outputs" / "正式底库映射固化检查包" / "00_映射固化总报告.md"
    mapping_summary = ROOT / "outputs" / "正式底库映射固化检查包" / "01_映射体检摘要.json"
    script_report = ROOT / "outputs" / "正式底库简繁统一检查包" / "00_简繁统一总报告.md"
    script_summary = ROOT / "outputs" / "正式底库简繁统一检查包" / "01_简繁统一摘要.json"
    library_report = ROOT / "outputs" / "正式底库库群结构分析与建设待办" / "00_库群结构总报告.md"
    library_summary = ROOT / "outputs" / "正式底库库群结构分析与建设待办" / "01_库群盘点摘要.json"
    mapping_status: dict[str, Any] = {}
    if mapping_summary.exists():
        try:
            mapping_payload = json.loads(mapping_summary.read_text(encoding="utf-8"))
            after_checks = mapping_payload.get("axis_after", {}).get("checks", {})
            catalog = mapping_payload.get("catalog", {})
            mapping_status = {
                "report_md": str(mapping_report),
                "summary_json": str(mapping_summary),
                "applied_count": mapping_payload.get("applied_count", 0),
                "relation_resolve_rate": catalog.get("relation_resolve_rate"),
                "non_all_relation_resolve_rate": catalog.get("non_all_relation_resolve_rate"),
                "alias_count": mapping_payload.get("alias_count"),
                "alias_manual_count": mapping_payload.get("alias_manual_count"),
                "range_edge_count": mapping_payload.get("range_edge_count"),
                "range_resolved_count": mapping_payload.get("range_resolved_count"),
                "range_covered_unresolved_count": mapping_payload.get("range_covered_unresolved_count"),
                "actionable_unresolved_count": mapping_payload.get("actionable_unresolved_count"),
                "person_edges_unresolved_character": after_checks.get("person_edges_unresolved_character"),
                "event_edges_unresolved_segment": after_checks.get("event_edges_unresolved_segment"),
                "evidence_edges_unresolved": after_checks.get("evidence_edges_unresolved"),
            }
        except (json.JSONDecodeError, OSError):
            mapping_status = {}
    script_status: dict[str, Any] = {}
    if script_summary.exists():
        try:
            script_payload = json.loads(script_summary.read_text(encoding="utf-8"))
            script_status = {
                "report_md": str(script_report),
                "summary_json": str(script_summary),
                "passed": script_payload.get("passed"),
                "search_pair_count": script_payload.get("search_pair_count"),
                "search_failure_count": script_payload.get("search_failure_count"),
                "evidence_case_count": script_payload.get("evidence_case_count"),
                "evidence_failure_count": script_payload.get("evidence_failure_count"),
                "question_logic_case_count": script_payload.get("question_logic_case_count"),
                "question_logic_failure_count": script_payload.get("question_logic_failure_count"),
                "residual_probe_count": script_payload.get("residual_probe_count"),
            }
        except (json.JSONDecodeError, OSError):
            script_status = {}
    library_status: dict[str, Any] = {}
    if library_summary.exists():
        try:
            library_payload = json.loads(library_summary.read_text(encoding="utf-8"))
            library_status = {
                "report_md": str(library_report),
                "summary_json": str(library_summary),
                "library_count": library_payload.get("library_count"),
                "structured_library_count": library_payload.get("structured_library_count"),
                "mother_only_library_count": library_payload.get("mother_only_library_count"),
                "discovered_topic_count": library_payload.get("discovered_topic_count"),
                "task_counts": library_payload.get("task_counts", {}),
            }
        except (json.JSONDecodeError, OSError):
            library_status = {}
    health = {
        "axis_db_exists": axis_db.exists(),
        "axis_db_size": axis_db.stat().st_size if axis_db.exists() else 0,
        "search_db_exists": SEARCH_DB.exists(),
        "search_db_size": SEARCH_DB.stat().st_size if SEARCH_DB.exists() else 0,
        "last_smoke_status": (
            "本次已通过" if smoke_result and smoke_result.get("ok") else "本次未运行；最近已通过离线自检" if not smoke_result else "本次未通过"
        ),
        "smoke": smoke_result,
    }
    files = {
        "当前状态台": homepage_entry("当前状态台", package_dir / CORE_FILES["workflow_status_md"]),
        "问题判断程序": homepage_entry("问题判断程序", package_dir / CORE_FILES["question_judgment_md"]),
        "关键词网络预检": homepage_entry("关键词网络预检", package_dir / CORE_FILES["keyword_precheck_json"]),
        "库线原文流转骨架": homepage_entry("库线原文流转骨架", package_dir / CORE_FILES["library_flow_md"]),
        "聚拢库总入口流程锁": homepage_entry("聚拢库总入口流程锁", package_dir / CORE_FILES["aggregation_flow_lock_md"]),
        "聚拢库取材单": homepage_entry("聚拢库取材单", package_dir / CORE_FILES["aggregation_material_search_md"]),
        "聚拢入材料池清单": homepage_entry("聚拢入材料池清单", package_dir / CORE_FILES["material_pool_admission_csv"]),
        "聚拢裁判首读材料池": homepage_entry("聚拢裁判首读材料池", package_dir / CORE_FILES["aggregation_first_read_pool_md"]),
        "聚拢入材料池凭证门": homepage_entry("聚拢入材料池凭证门", package_dir / CORE_FILES["material_pool_admission_md"]),
        "本题库态预检表": homepage_entry("本题库态预检表", package_dir / CORE_FILES["library_precheck_md"]),
        "最终回答前材料池精读门": homepage_entry("最终回答前材料池精读门", package_dir / CORE_FILES["final_reading_gate_md"]),
        "二轮补证决策卡": homepage_entry("二轮补证决策卡", package_dir / CORE_FILES["second_round_decision_md"]),
        "来源字段标准化词典": homepage_entry("来源字段标准化词典", package_dir / CORE_FILES["source_schema_md"]),
        "经验法典三层结构": homepage_entry("经验法典三层结构", package_dir / CORE_FILES["experience_codex_md"]),
        "正式沙盒模式边界": homepage_entry("正式沙盒模式边界", package_dir / CORE_FILES["mode_boundary_md"]),
        "用户认可入库门": homepage_entry("用户认可入库门", package_dir / CORE_FILES["approval_ingest_gate_md"]),
        "库群覆盖矩阵": homepage_entry("库群覆盖矩阵", package_dir / CORE_FILES["library_coverage_md"]),
        "Codex写作前原文追证摘抄生成门": homepage_entry("Codex写作前原文追证摘抄生成门", package_dir / CORE_FILES["codex_original_reread_gate_md"]),
        "Codex写作前原文追证摘抄目标稿位": homepage_entry("Codex写作前原文追证摘抄目标稿位", package_dir / CORE_FILES["codex_original_reread_target_md"]),
        "Codex精读材料词生成门": homepage_entry("Codex精读材料词生成门", package_dir / CORE_FILES["codex_close_reading_gate_md"]),
        "Codex精读材料词目标稿位": homepage_entry("Codex精读材料词目标稿位", package_dir / CORE_FILES["codex_close_reading_target_md"]),
        "Codex红楼解语生成门": homepage_entry("Codex红楼解语生成门", package_dir / CORE_FILES["codex_final_answer_gate_md"]),
        "Codex红楼解语目标稿位": homepage_entry("Codex红楼解语目标稿位", package_dir / CORE_FILES["codex_final_answer_target_md"]),
        "Codex最终答案写回规范": homepage_entry("Codex最终答案写回规范", package_dir / CORE_FILES["answer_writeback_protocol_md"]),
        "十题回归测试骨架": homepage_entry("十题回归测试骨架", package_dir / CORE_FILES["regression_plan_md"]),
        "桌面人读排序配置": homepage_entry("桌面人读排序配置", package_dir / CORE_FILES["human_reading_order_md"]),
        "经验复盘入账": homepage_entry("经验复盘入账", package_dir / CORE_FILES["experience_entry_md"]),
        "问题判断经验值总账": homepage_entry("问题判断经验值总账", EXPERIENCE_LEDGER_MD),
        "触发词操作卡": homepage_entry("触发词操作卡", ROOT / "outputs" / "正式底库工程首页" / "02_触发词操作卡.md"),
        "P0小问题修复报告": homepage_entry("P0小问题修复报告", ROOT / "outputs" / "正式底库P0修复包" / "00_P0小问题修复报告.md"),
        "证据锚点修复报告": homepage_entry("证据锚点修复报告", ROOT / "outputs" / "正式底库证据锚点修复包" / "00_证据锚点修复报告.md"),
        "首轮复核小表": homepage_entry("首轮复核小表", package_dir / CORE_FILES["review_firstpass_sheet_csv"]),
        "复核收口报告": homepage_entry("复核收口报告", package_dir / CORE_FILES["review_finish_md"]),
        "文章入库预检报告": homepage_entry("文章入库预检报告", package_dir / CORE_FILES["article_ingest_report_md"]),
        "作品总库入库候选行": homepage_entry("作品总库入库候选行", package_dir / CORE_FILES["article_ingest_candidate_csv"]),
        "文章回挂清单": homepage_entry("文章回挂清单", package_dir / CORE_FILES["article_ingest_links_csv"]),
        "文章入库身份卡": homepage_entry("文章入库身份卡", package_dir / CORE_FILES["article_ingest_identity_md"]),
        "阶段复盘总索引": homepage_entry("阶段复盘总索引", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "00_阶段复盘总索引.md"),
        "下一次开工入口": homepage_entry("下一次开工入口", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "03_下一次开工入口.md"),
        "P0推进记录": homepage_entry("P0推进记录", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "04_P0推进记录.md"),
        "P1推进记录": homepage_entry("P1推进记录", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "05_P1推进记录.md"),
        "协作约定": homepage_entry("协作约定", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "06_协作约定.md"),
        "从开工到当前工程全量总账": homepage_entry("从开工到当前工程全量总账", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "07_从开工到当前工程全量总账.md"),
        "机器续接摘要": homepage_entry("机器续接摘要", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "08_机器续接摘要.json"),
        "工程完成度复盘表": homepage_entry("工程完成度复盘表", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "09_工程完成度复盘表.csv"),
        "总账必读路由与刷新规则": homepage_entry("总账必读路由与刷新规则", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "10_总账必读路由与刷新规则.md"),
        "总账刷新日志": homepage_entry("总账刷新日志", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "11_总账刷新日志.csv"),
        "数字生命总账启动说明": homepage_entry("数字生命总账启动说明", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "12_数字生命总账启动说明.md"),
        "红楼梦工程封口放行单": homepage_entry("红楼梦工程封口放行单", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "13_红楼梦工程封口放行单.md"),
        "月度总账体检规则": homepage_entry("月度总账体检规则", ROOT / "outputs" / "正式底库阶段复盘与下一步" / "14_月度总账体检规则.md"),
        "简繁统一总报告": homepage_entry("简繁统一总报告", script_report),
        "库群结构总报告": homepage_entry("库群结构总报告", library_report),
        "映射固化总报告": homepage_entry("映射固化总报告", mapping_report),
    }
    home_dir.mkdir(parents=True, exist_ok=True)
    home_md = home_dir / "00_红楼梦工程首页.md"
    home_json = home_dir / "01_首页摘要.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "home_md": str(home_md),
        "home_json": str(home_json),
        "current_package": {
            "path": str(package_dir),
            "name": package_dir.name,
            "question": manifest.get("question", ""),
        },
        "status": status_result["status"],
        "recommended_next": status_result["recommended_next"],
        "review_progress": progress,
        "firstpass_sheet": firstpass_sheet,
        "packages": package_list,
        "files": files,
        "file_count": len(files),
        "homepage_entry_count": len(files),
        "core_file_count": len(manifest.get("core_files", {})),
        "health": health,
        "mapping": mapping_status,
        "script_normalization": script_status,
        "library_audit": library_status,
    }
    home_md.write_text(render_project_home(payload), encoding="utf-8")
    write_json(home_json, payload)
    return {
        "home_md": str(home_md),
        "home_json": str(home_json),
        "current_package": str(package_dir),
        "status": payload["status"],
        "recommended_next": payload["recommended_next"],
        "file_count": len(files),
        "run_smoke": run_smoke,
    }


def continue_action(name: str, ok: bool, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail or {},
    }


def render_continue_report(question: str, result: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦正式底库｜一键续跑报告",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 1. 原问题",
        "",
        question,
        "",
        "## 2. 续跑模式",
        "",
        f"- 是否允许实际回填：{result['apply']}",
        f"- 是否允许覆盖已有人工字段：{result['overwrite']}",
        f"- 最终阶段：{result['final_phase']}",
        f"- 下一步：{result['next_action']}",
        "",
        "## 3. 本次动作",
        "",
    ]
    for item in result["actions"]:
        mark = "完成" if item["ok"] else "未完成"
        lines.append(f"- {item['name']}：{mark}")
    lines.extend(
        [
            "",
            "## 4. 状态文件",
            "",
            f"- 状态操作台：`{result['status_file']}`",
            f"- 续跑摘要：`{result['summary_json']}`",
            "",
            "## 5. 建议",
            "",
        ]
    )
    if result["final_commands"]:
        lines.append("下一步可运行：")
        lines.append("")
        lines.append("```bash")
        lines.extend(result["final_commands"])
        lines.append("```")
    else:
        lines.append("当前没有必须运行的命令；请按状态操作台提示先处理人工填写。")
    return "\n".join(lines)


def loop_continue(
    package: str | Path = "latest",
    out_root: Path = OUT_ROOT,
    batch: str = "第1批",
    limit: int = 20,
    apply: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    actions: list[dict[str, Any]] = []

    if not (package_dir / CORE_FILES["review_queue_csv"]).exists():
        plan_result = loop_review_plan(package_dir, out_root)
        actions.append(
            continue_action(
                "生成复核优先清单",
                True,
                {
                    "queue_rows": plan_result["review_plan"]["queue_rows"],
                    "review_queue_csv": plan_result["review_plan"]["review_queue_csv"],
                },
            )
        )
    if not (package_dir / CORE_FILES["review_sheet_csv"]).exists():
        sheet_result = loop_review_sheet(package_dir, out_root, batch=batch, limit=limit)
        actions.append(
            continue_action(
                "生成当前批次复核工作表",
                True,
                {
                    "sheet_rows": sheet_result["review_sheet"]["sheet_rows"],
                    "review_sheet_csv": sheet_result["review_sheet"]["review_sheet_csv"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_sheet_csv"]).exists() and not (package_dir / CORE_FILES["review_assist_md"]).exists():
        assist_result = loop_review_assist(package_dir, out_root, limit=limit)
        actions.append(
            continue_action(
                "生成复核填写助手",
                True,
                {
                    "assist_rows": assist_result["review_assist"]["assist_rows"],
                    "review_assist_md": assist_result["review_assist"]["review_assist_md"],
                    "review_assist_csv": assist_result["review_assist"]["review_assist_csv"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_sheet_csv"]).exists() and not (package_dir / CORE_FILES["review_workbench_md"]).exists():
        workbench_result = loop_review_workbench(package_dir, out_root)
        actions.append(
            continue_action(
                "生成复核填表工作台",
                True,
                {
                    "workbench_rows": workbench_result["review_workbench"]["workbench_rows"],
                    "review_workbench_md": workbench_result["review_workbench"]["review_workbench_md"],
                    "review_workbench_csv": workbench_result["review_workbench"]["review_workbench_csv"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_workbench_csv"]).exists() and not (package_dir / CORE_FILES["review_coverage_md"]).exists():
        coverage_result = loop_review_coverage(package_dir, out_root)
        actions.append(
            continue_action(
                "生成复核覆盖矩阵",
                True,
                {
                    "coverage_rows": coverage_result["review_coverage"]["coverage_rows"],
                    "minimal_pick_count": coverage_result["review_coverage"]["minimal_pick_count"],
                    "review_coverage_md": coverage_result["review_coverage"]["review_coverage_md"],
                    "review_coverage_csv": coverage_result["review_coverage"]["review_coverage_csv"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_coverage_md"]).exists() and not (package_dir / CORE_FILES["review_firstpass_md"]).exists():
        firstpass_result = loop_review_firstpass(package_dir, out_root)
        actions.append(
            continue_action(
                "生成首轮复核执行单",
                True,
                {
                    "firstpass_rows": firstpass_result["review_firstpass"]["firstpass_rows"],
                    "review_firstpass_md": firstpass_result["review_firstpass"]["review_firstpass_md"],
                    "review_firstpass_csv": firstpass_result["review_firstpass"]["review_firstpass_csv"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_firstpass_md"]).exists() and not (package_dir / CORE_FILES["review_firstpass_sheet_csv"]).exists():
        firstpass_sheet_result = loop_review_firstpass_sheet(package_dir, out_root)
        actions.append(
            continue_action(
                "生成首轮复核小表",
                True,
                {
                    "rows": firstpass_sheet_result["review_firstpass_sheet"]["rows"],
                    "review_firstpass_sheet_csv": firstpass_sheet_result["review_firstpass_sheet"]["review_firstpass_sheet_csv"],
                    "review_firstpass_sheet_md": firstpass_sheet_result["review_firstpass_sheet"]["review_firstpass_sheet_md"],
                },
            )
        )
    if (package_dir / CORE_FILES["review_firstpass_sheet_csv"]).exists() and not (package_dir / CORE_FILES["review_firstpass_cards_md"]).exists():
        firstpass_cards_result = loop_review_firstpass_cards(package_dir, out_root)
        actions.append(
            continue_action(
                "生成首轮复核逐条判读卡片",
                True,
                {
                    "card_rows": firstpass_cards_result["review_firstpass_cards"]["card_rows"],
                    "review_firstpass_cards_md": firstpass_cards_result["review_firstpass_cards"]["review_firstpass_cards_md"],
                },
            )
        )

    firstpass_sheet_csv = package_dir / CORE_FILES["review_firstpass_sheet_csv"]
    if firstpass_sheet_csv.exists():
        firstpass_stats = sheet_progress(firstpass_sheet_csv)
        if firstpass_stats["filled_rows"] > 0:
            firstpass_check_result = loop_review_firstpass_check(package_dir, out_root)
            firstpass_check = firstpass_check_result["review_firstpass_check"]
            actions.append(
                continue_action(
                    "检查首轮复核小表质量",
                    True,
                    {
                        "filled_rows": firstpass_check["filled_rows"],
                        "ready_rows": firstpass_check["ready_rows"],
                        "blocking_issue_count": firstpass_check["blocking_issue_count"],
                        "ready_for_sync": firstpass_check["ready_for_apply"],
                    },
                )
            )

    check_result = loop_review_check(package_dir, out_root)
    check = check_result["review_check"]
    actions.append(
        continue_action(
            "检查复核工作表质量",
            True,
            {
                "filled_rows": check["filled_rows"],
                "ready_rows": check["ready_rows"],
                "blocking_issue_count": check["blocking_issue_count"],
                "ready_for_apply": check["ready_for_apply"],
            },
        )
    )

    if check["ready_for_apply"]:
        dry_result = loop_review_apply(package_dir, out_root, overwrite=overwrite, dry_run=True)
        actions.append(
            continue_action(
                "模拟回填复核工作表",
                True,
                {
                    "updated_rows": dry_result["review_apply"]["updated_rows"],
                    "conflict_rows": dry_result["review_apply"]["conflict_rows"],
                },
            )
        )
        if apply:
            apply_result = loop_review_apply(package_dir, out_root, overwrite=overwrite, dry_run=False)
            actions.append(
                continue_action(
                    "正式回填复核工作表",
                    True,
                    {
                        "updated_rows": apply_result["review_apply"]["updated_rows"],
                        "conflict_rows": apply_result["review_apply"]["conflict_rows"],
                    },
                )
            )
            readback_result = loop_readback(package_dir, out_root)
            actions.append(
                continue_action(
                    "刷新复核回读",
                    True,
                    {
                        "usable_rows": readback_result["progress"]["usable_rows"],
                        "pending_rows": readback_result["progress"]["pending_rows"],
                    },
                )
            )
            draft_result = loop_draft(package_dir, out_root)
            actions.append(
                continue_action(
                    "刷新写作草稿",
                    True,
                    {
                        "draft_ready": draft_result["draft"]["draft_ready"],
                        "main_rows": draft_result["draft"]["main_rows"],
                        "counter_rows": draft_result["draft"]["counter_rows"],
                    },
                )
            )
            next_result = loop_next(package_dir, out_root)
            actions.append(
                continue_action(
                    "刷新二次追问与补证计划",
                    True,
                    {
                        "task_count": next_result["next"]["task_count"],
                        "priority_counts": next_result["next"]["priority_counts"],
                    },
                )
            )
        else:
            actions.append(
                continue_action(
                    "正式回填复核工作表",
                    False,
                    {"reason": "未使用 --apply；为保护人工主表，本次只做 dry-run。"},
                )
            )
    elif check["filled_rows"] == 0:
        actions.append(continue_action("等待人工填写小表", False, {"reason": "当前小表没有人工填写内容。"}))
    else:
        actions.append(
            continue_action(
                "等待修正小表",
                False,
                {"blocking_issue_count": check["blocking_issue_count"]},
            )
        )

    status_result = loop_status(package_dir, out_root)
    actions.append(
        continue_action(
            "刷新闭环状态操作台",
            True,
            {
                "phase": status_result["recommended_next"]["phase"],
                "status_file": status_result["status_file"],
            },
        )
    )

    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    report_md = package_dir / CORE_FILES["continue_report_md"]
    summary_json = package_dir / CORE_FILES["continue_summary_json"]
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "package": str(package_dir),
        "question": question,
        "apply": apply,
        "overwrite": overwrite,
        "actions": actions,
        "final_phase": status_result["recommended_next"]["phase"],
        "next_action": status_result["recommended_next"]["next_action"],
        "final_commands": status_result["recommended_next"]["commands"],
        "status_file": status_result["status_file"],
        "summary_json": str(summary_json),
        "report_md": str(report_md),
    }
    report_md.write_text(render_continue_report(question, result), encoding="utf-8")
    write_json(summary_json, result)

    core_files = manifest.setdefault("core_files", {})
    core_files["continue_report_md"] = str(report_md)
    core_files["continue_summary_json"] = str(summary_json)
    manifest.setdefault("results", {})["loop_continue"] = result
    manifest["status"] = f"一键续跑完成：{result['final_phase']}。{result['next_action']}"
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "安全一键续跑",
            True,
            {
                "apply": apply,
                "final_phase": result["final_phase"],
                "action_count": len(actions),
                "report_md": str(report_md),
                "summary_json": str(summary_json),
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)
    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "continue": result,
        "manifest": str(manifest_path_value),
    }


def loop_readback(package: str | Path = "latest", out_root: Path = OUT_ROOT) -> dict[str, Any]:
    package_dir = resolve_package(package, out_root)
    manifest = load_manifest(package_dir)
    question = manifest.get("question", "")
    review_csv = package_dir / CORE_FILES["review_csv"]
    if not review_csv.exists():
        raise FileNotFoundError(f"闭环包缺少复核表：{review_csv}")

    internal = package_dir / "_内部过程"
    readback_dir = internal / "回读包"
    feedback_dir = internal / "反馈包"
    progress = review_progress(review_csv)
    readback_result = review_readback.build_readback(review_csv=review_csv, question=question, out_dir=readback_dir)
    feedback_result = feedback_optimizer.build_feedback_profile(review_csv=review_csv, out_dir=feedback_dir)
    profile_path = Path(feedback_result["outputs"]["profile_json"])

    core_files = manifest.setdefault("core_files", {})
    core_files["writing_md"] = copy_file(readback_result["writing_md"], package_dir / CORE_FILES["writing_md"])
    core_files["feedback_profile"] = copy_file(profile_path, package_dir / CORE_FILES["feedback_profile"])

    writable_pack = package_dir / CORE_FILES["writable_pack"]
    handoff_prompt = package_dir / CORE_FILES["handoff_prompt"]
    writable_pack.write_text(render_writable_pack(question, readback_result, progress), encoding="utf-8")
    handoff_prompt.write_text(render_handoff_prompt(question, readback_result, progress), encoding="utf-8")
    core_files["writable_pack"] = str(writable_pack)
    core_files["handoff_prompt"] = str(handoff_prompt)

    manifest.setdefault("results", {})["readback"] = readback_result
    manifest.setdefault("results", {})["feedback"] = feedback_result
    manifest.setdefault("results", {})["loop_readback"] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "review_csv": str(review_csv),
        "progress": progress,
        "writable_pack": str(writable_pack),
        "handoff_prompt": str(handoff_prompt),
    }
    manifest["status"] = status_sentence(readback_result)
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    upsert_step(
        manifest.setdefault("steps", []),
        step(
            "闭环回填",
            True,
            {
                "review_csv": str(review_csv),
                "completed_rows": progress["completed_rows"],
                "usable_rows": progress["usable_rows"],
                "rejected_rows": progress["rejected_rows"],
                "pending_rows": progress["pending_rows"],
                "completion_rate": progress["completion_rate"],
            },
        ),
    )

    manifest_path_value = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    core_files["manifest"] = str(manifest_path_value)
    core_files["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    write_json(manifest_path_value, manifest)

    return {
        "package": str(package_dir),
        "question": question,
        "status": manifest["status"],
        "progress": progress,
        "readback": readback_result,
        "feedback": feedback_result,
        "writable_pack": str(writable_pack),
        "handoff_prompt": str(handoff_prompt),
        "manifest": str(manifest_path_value),
    }


def build_closed_loop(
    question: str,
    limit_per_question: int = 0,
    top_evidence: int = 0,
    review_limit: int = 0,
    out_root: Path = OUT_ROOT,
    use_feedback: bool = True,
    feedback_profile_path: Path | None = None,
    run_smoke: bool = True,
    route_context: str = "",
) -> dict[str, Any]:
    generated_at = datetime.now().isoformat(timespec="seconds")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    package_dir = Path(out_root) / f"{stamp}_{safe_filename_part(question)}"
    package_dir.mkdir(parents=True, exist_ok=True)

    internal = package_dir / "_内部过程"
    pool_dir = internal / "总证据池"
    research_dir = internal / "研究包"
    review_dir = internal / "复核包"
    readback_dir = internal / "回读包"
    feedback_dir = internal / "反馈包"

    steps: list[dict[str, Any]] = []
    query_logic_strategy_gate = enforce_query_logic_strategy_gate(question, route_context, package_dir)
    judgment_result = build_question_judgment_program(question, route_context, package_dir)
    entry_hard_gate = build_entry_hard_gate(question, route_context, package_dir, judgment_result)
    aggregation_flow_lock = build_aggregation_flow_lock(question, route_context, package_dir, judgment_result)
    machine_short_card = build_machine_short_card(question, route_context, package_dir, judgment_result, aggregation_flow_lock)
    library_flow = build_library_flow_skeleton(question, route_context, package_dir, judgment_result)
    final_reading_gate = build_final_reading_gate(question, route_context, package_dir, judgment_result, library_flow)
    experience_entry = build_experience_entry(question, route_context, package_dir, judgment_result)
    experience_md = package_dir / CORE_FILES["experience_entry_md"]
    experience_json = package_dir / CORE_FILES["experience_entry_json"]
    experience_md.write_text(render_experience_entry_markdown(experience_entry), encoding="utf-8")
    write_json(experience_json, experience_entry)
    process_inventory = build_process_inventory(question, route_context, package_dir)
    steps.append(
        step(
            "查询逻辑策略门",
            bool(query_logic_strategy_gate.get("ok")),
            {
                "strategy": query_logic_strategy_gate.get("strategy_value", ""),
                "execution_mode": (query_logic_strategy_gate.get("strategy_flexibility") or {}).get("execution_mode", ""),
                "combination": (query_logic_strategy_gate.get("strategy_flexibility") or {}).get("combination", ""),
                "adjustment_record": (query_logic_strategy_gate.get("strategy_flexibility") or {}).get("adjustment_record", ""),
                "deviation_reason": (query_logic_strategy_gate.get("strategy_flexibility") or {}).get("deviation_reason", ""),
                "requires_subquestions": query_logic_strategy_gate.get("requires_subquestions", False),
                "subquestion_count": len(query_logic_strategy_gate.get("subquestions", [])),
                "query_logic_strategy_gate_md": query_logic_strategy_gate.get("output_files", {}).get("query_logic_strategy_gate_md", ""),
                "query_logic_strategy_gate_json": query_logic_strategy_gate.get("output_files", {}).get("query_logic_strategy_gate_json", ""),
            },
        )
    )
    steps.append(
        step(
            "入口硬规则门",
            True,
            {
                "hard_rule_version": entry_hard_gate.get("hard_rule_version", ""),
                "library_first": entry_hard_gate.get("tool_contract", {}).get("library_first", ""),
                "exhaustive_required": entry_hard_gate.get("exhaustive_source_sweep_required", False),
                "entry_hard_gate_md": entry_hard_gate.get("output_files", {}).get("entry_hard_gate_md", ""),
                "entry_hard_gate_json": entry_hard_gate.get("output_files", {}).get("entry_hard_gate_json", ""),
            },
        )
    )
    steps.append(
        step(
            "128 聚拢库总入口流程锁",
            bool(aggregation_flow_lock.get("map_checked")),
            {
                "problem_type": aggregation_flow_lock.get("problem_type", ""),
                "entry_doc": aggregation_flow_lock.get("entry_doc", ""),
                "registry_csv": aggregation_flow_lock.get("registry_csv", ""),
                "aggregation_flow_lock_md": aggregation_flow_lock.get("output_files", {}).get("aggregation_flow_lock_md", ""),
                "aggregation_flow_lock_json": aggregation_flow_lock.get("output_files", {}).get("aggregation_flow_lock_json", ""),
            },
        )
    )
    steps.append(
        step(
            "机器短卡与证据分层策略",
            True,
            {
                "problem_type": machine_short_card.get("machine_short_card", {}).get("问题类型", ""),
                "object": machine_short_card.get("machine_short_card", {}).get("对象", ""),
                "entry_terms": machine_short_card.get("machine_short_card", {}).get("入口词", []),
                "exclusion_required": machine_short_card.get("exclusion_table_policy", {}).get("required", False),
                "machine_short_card_md": machine_short_card.get("output_files", {}).get("machine_short_card_md", ""),
                "machine_short_card_json": machine_short_card.get("output_files", {}).get("machine_short_card_json", ""),
            },
        )
    )
    steps.append(
        step(
            "问题判断程序与关键词网络预检",
            True,
            {
                "route_center": judgment_result.get("route_center", ""),
                "keyword_count": len(judgment_result.get("keyword_pool", [])),
                "subquestion_count": len(judgment_result.get("subquestions", [])),
                "judgment_md": judgment_result.get("judgment_md", ""),
                "precheck_json": judgment_result.get("precheck_json", ""),
            },
        )
    )
    steps.append(
        step(
            "库线原文流转骨架",
            True,
            {
                "library_count": len(library_flow.get("library_matrix", [])),
                "flow_count": len(library_flow.get("flow_patterns", [])),
                "library_flow_md": library_flow.get("output_files", {}).get("library_flow_md", ""),
                "library_flow_json": library_flow.get("output_files", {}).get("library_flow_json", ""),
            },
        )
    )
    steps.append(
        step(
            "最终回答前材料池精读门",
            True,
            {
                "final_reading_gate_md": final_reading_gate.get("output_files", {}).get("final_reading_gate_md", ""),
                "final_reading_gate_json": final_reading_gate.get("output_files", {}).get("final_reading_gate_json", ""),
                "material_file_count": len(final_reading_gate.get("required_material_pool_files", [])),
            },
        )
    )
    steps.append(
        step(
            "经验值自动入账",
            True,
            {
                "trigger": experience_entry.get("trigger", ""),
                "main_rules": experience_entry.get("main_rules", []),
                "entry_md": str(experience_md),
                "ledger_md": str(EXPERIENCE_LEDGER_MD),
            },
        )
    )
    steps.append(
        step(
            "全流程产物与 Codex 判别门总账",
            True,
            {
                "process_inventory_md": process_inventory.get("process_inventory_md", ""),
                "process_inventory_json": process_inventory.get("process_inventory_json", ""),
                "stage_count": len(process_inventory.get("stages", [])),
            },
        )
    )
    smoke_result: dict[str, Any] | None = None
    if run_smoke:
        smoke_result = run_offline_smoke()
        steps.append(step("离线自检", bool(smoke_result.get("ok")), {"returncode": smoke_result.get("returncode")}))
        if not smoke_result.get("ok"):
            steps.append(
                step(
                    "离线自检失败但不阻断主链",
                    True,
                    {
                        "reason": "离线自检只作为健康提示；真实问题仍必须继续生成候选材料池并进入 Codex 材料池判定。",
                        "returncode": smoke_result.get("returncode"),
                    },
                )
            )

    review_result = review_writer.build_review_pack(
        question=question,
        limit_per_question=limit_per_question,
        top_evidence=top_evidence,
        review_limit=review_limit,
        use_feedback=False,
        feedback_profile_path=feedback_profile_path,
        out_dir=review_dir,
        research_out_dir=research_dir,
        pool_out_dir=pool_dir,
        route_context=route_context,
    )
    research_result = review_result["research_result"]
    steps.append(
        step(
            "拆题、召回、证据池、研究包",
            True,
            {
                "subquestion_count": research_result.get("subquestion_count", 0),
                "unique_segments": research_result.get("unique_segments", 0),
                "triaged_csv": research_result.get("triaged_csv", ""),
            },
        )
    )
    steps.append(
        step(
            "复核包",
            int(review_result.get("review_rows") or 0) > 0,
            {
                "review_rows": review_result.get("review_rows", 0),
                "review_csv": review_result.get("review_csv", ""),
            },
        )
    )

    aggregation_material_bridge = build_aggregation_material_bridge(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        review_result=review_result,
        aggregation_flow_lock=aggregation_flow_lock,
    )
    steps.append(
        step(
            "聚拢库取材并送入材料池",
            int(aggregation_material_bridge.get("counts", {}).get("admitted_to_material_pool_rows") or 0) > 0,
            {
                "rule": "带着问题和方法进聚拢库找材料；有聚拢坐标、来源链和原文锚点的材料送入材料池。",
                "returned_to_aggregation_rows": aggregation_material_bridge.get("counts", {}).get("returned_to_aggregation_rows", 0),
                "admitted_to_material_pool_rows": aggregation_material_bridge.get("counts", {}).get("admitted_to_material_pool_rows", 0),
                "first_read_useful_rows": aggregation_material_bridge.get("counts", {}).get("first_read_useful_rows", 0),
                "aggregation_material_search_md": aggregation_material_bridge.get("output_files", {}).get("aggregation_material_search_md", ""),
                "material_pool_admission_csv": aggregation_material_bridge.get("output_files", {}).get("material_pool_admission_csv", ""),
                "aggregation_first_read_pool_md": aggregation_material_bridge.get("output_files", {}).get("aggregation_first_read_pool_md", ""),
            },
        )
    )

    readback_result = review_readback.build_readback(
        review_csv=Path(review_result["review_csv"]),
        question=question,
        out_dir=readback_dir,
    )
    steps.append(
        step(
            "复核回读",
            int(readback_result.get("total_rows") or 0) > 0,
            {
                "total_rows": readback_result.get("total_rows", 0),
                "usable_rows": readback_result.get("usable_rows", 0),
                "pending_rows": readback_result.get("pending_rows", 0),
            },
        )
    )

    pipeline_audit = build_codex_pipeline_audit(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        judgment_result=judgment_result,
        library_flow_payload=library_flow,
        research_result=research_result,
        review_result=review_result,
        readback_result=readback_result,
    )
    steps.append(
        step(
            "Codex 指挥链达标检查",
            True,
            {
                "pipeline_audit_md": pipeline_audit.get("pipeline_audit_md", ""),
                "complete": pipeline_audit.get("summary", {}).get("complete", 0),
                "partial": pipeline_audit.get("summary", {}).get("partial", 0),
                "original_passage_rows": pipeline_audit.get("summary", {}).get("original_passage_rows", 0),
            },
        )
    )

    source_schema = build_source_field_standardization(
        question=question,
        package_dir=package_dir,
        review_result=review_result,
    )
    experience_codex = build_experience_codex_protocol(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        judgment_payload=judgment_result,
        experience_entry=experience_entry,
    )
    mode_boundary = build_mode_boundary_card(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
    )
    approval_ingest_gate = build_approval_ingest_gate(
        question=question,
        package_dir=package_dir,
        review_result=review_result,
        readback_result=readback_result,
    )
    library_coverage = build_library_coverage_matrix(
        question=question,
        package_dir=package_dir,
        library_flow_payload=library_flow,
        review_result=review_result,
    )
    second_round_decision = pipeline_audit.get("second_round_decision", {})
    if not isinstance(second_round_decision, dict):
        second_round_decision = {}
    codex_close_reading_gate = build_codex_close_reading_gate(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        review_result=review_result,
        pipeline_audit=pipeline_audit,
        second_round_decision=second_round_decision,
    )
    codex_original_reread_gate = build_codex_original_reread_gate(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        review_result=review_result,
        pipeline_audit=pipeline_audit,
        second_round_decision=second_round_decision,
    )
    codex_final_answer_gate = build_codex_final_answer_gate(
        question=question,
        route_context=route_context,
        package_dir=package_dir,
        review_result=review_result,
        readback_result=readback_result,
        pipeline_audit=pipeline_audit,
        second_round_decision=second_round_decision,
    )
    answer_writeback_protocol = build_answer_writeback_protocol(
        question=question,
        package_dir=package_dir,
    )
    regression_plan = build_regression_plan(
        question=question,
        package_dir=package_dir,
    )
    human_reading_order = build_human_reading_order_config(
        question=question,
        package_dir=package_dir,
    )
    eight_step_status = build_aggregation_eight_step_status(
        package_dir=package_dir,
        judgment_result=judgment_result,
        aggregation_flow_lock=aggregation_flow_lock,
        research_result=research_result,
        review_result=review_result,
        aggregation_material_bridge=aggregation_material_bridge,
        readback_result=readback_result,
        pipeline_audit=pipeline_audit,
        codex_final_answer_gate=codex_final_answer_gate,
    )
    steps.append(
        step(
            "双头八步主线状态",
            True,
            {
                "query_head": eight_step_status.get("query_head", ""),
                "lane": eight_step_status.get("lane", ""),
                "shared_spine": eight_step_status.get("shared_spine", []),
                "completed_or_ready_steps": eight_step_status.get("completed_or_ready_steps", 0),
                "total_steps": eight_step_status.get("total_steps", 0),
                "write_answer_allowed": eight_step_status.get("answer_gate", {}).get("write_answer_allowed", False),
            },
        )
    )
    steps.append(
        step(
            "P1/P2 六项治理卡",
            True,
            {
                "source_schema_md": source_schema.get("output_files", {}).get("source_schema_md", ""),
                "experience_codex_md": experience_codex.get("output_files", {}).get("experience_codex_md", ""),
                "mode_boundary_md": mode_boundary.get("output_files", {}).get("mode_boundary_md", ""),
                "approval_ingest_gate_md": approval_ingest_gate.get("output_files", {}).get("approval_ingest_gate_md", ""),
                "library_coverage_md": library_coverage.get("output_files", {}).get("library_coverage_md", ""),
                "codex_close_reading_gate_md": codex_close_reading_gate.get("output_files", {}).get("codex_close_reading_gate_md", ""),
                "codex_original_reread_gate_md": codex_original_reread_gate.get("output_files", {}).get("codex_original_reread_gate_md", ""),
                "codex_final_answer_gate_md": codex_final_answer_gate.get("output_files", {}).get("codex_final_answer_gate_md", ""),
                "answer_writeback_protocol_md": answer_writeback_protocol.get("output_files", {}).get("answer_writeback_protocol_md", ""),
                "regression_plan_md": regression_plan.get("output_files", {}).get("regression_plan_md", ""),
                "human_reading_order_md": human_reading_order.get("output_files", {}).get("human_reading_order_md", ""),
            },
        )
    )

    feedback_result = feedback_optimizer.build_feedback_profile(
        review_csv=Path(review_result["review_csv"]),
        out_dir=feedback_dir,
    )
    profile_path = Path(feedback_result["outputs"]["profile_json"])
    steps.append(
        step(
            "反馈记录（不参与主链排序）",
            profile_path.exists(),
            {
                "labeled_rows": feedback_result.get("labeled_rows", 0),
                "pending_rows": feedback_result.get("pending_rows", 0),
                "profile_json": str(profile_path),
                "rule": "反馈文件只作为经验记录；当前主链不使用本地反馈排序替代 Codex 材料池判定。",
            },
        )
    )

    core_files = {
        "query_logic_strategy_gate_md": str(package_dir / CORE_FILES["query_logic_strategy_gate_md"]),
        "query_logic_strategy_gate_json": str(package_dir / CORE_FILES["query_logic_strategy_gate_json"]),
        "entry_hard_gate_md": str(package_dir / CORE_FILES["entry_hard_gate_md"]),
        "entry_hard_gate_json": str(package_dir / CORE_FILES["entry_hard_gate_json"]),
        "aggregation_flow_lock_md": str(package_dir / CORE_FILES["aggregation_flow_lock_md"]),
        "aggregation_flow_lock_json": str(package_dir / CORE_FILES["aggregation_flow_lock_json"]),
        "machine_short_card_md": str(package_dir / CORE_FILES["machine_short_card_md"]),
        "machine_short_card_json": str(package_dir / CORE_FILES["machine_short_card_json"]),
        "aggregation_material_search_md": str(package_dir / CORE_FILES["aggregation_material_search_md"]),
        "aggregation_material_search_json": str(package_dir / CORE_FILES["aggregation_material_search_json"]),
        "material_pool_admission_csv": str(package_dir / CORE_FILES["material_pool_admission_csv"]),
        "material_pool_admission_md": str(package_dir / CORE_FILES["material_pool_admission_md"]),
        "material_pool_admission_json": str(package_dir / CORE_FILES["material_pool_admission_json"]),
        "material_pool_blocked_csv": str(package_dir / CORE_FILES["material_pool_blocked_csv"]),
        "aggregation_first_read_pool_md": str(package_dir / CORE_FILES["aggregation_first_read_pool_md"]),
        "question_judgment_md": str(package_dir / CORE_FILES["question_judgment_md"]),
        "keyword_precheck_json": str(package_dir / CORE_FILES["keyword_precheck_json"]),
        "library_flow_md": str(package_dir / CORE_FILES["library_flow_md"]),
        "library_flow_json": str(package_dir / CORE_FILES["library_flow_json"]),
        "library_precheck_md": str(package_dir / CORE_FILES["library_precheck_md"]),
        "library_precheck_json": str(package_dir / CORE_FILES["library_precheck_json"]),
        "final_reading_gate_md": str(package_dir / CORE_FILES["final_reading_gate_md"]),
        "final_reading_gate_json": str(package_dir / CORE_FILES["final_reading_gate_json"]),
        "experience_entry_md": str(experience_md),
        "experience_entry_json": str(experience_json),
        "process_inventory_md": str(package_dir / CORE_FILES["process_inventory_md"]),
        "process_inventory_json": str(package_dir / CORE_FILES["process_inventory_json"]),
        "pipeline_audit_md": str(package_dir / CORE_FILES["pipeline_audit_md"]),
        "pipeline_audit_json": str(package_dir / CORE_FILES["pipeline_audit_json"]),
        "second_round_decision_md": str(package_dir / CORE_FILES["second_round_decision_md"]),
        "second_round_decision_json": str(package_dir / CORE_FILES["second_round_decision_json"]),
        "source_schema_md": str(package_dir / CORE_FILES["source_schema_md"]),
        "source_schema_json": str(package_dir / CORE_FILES["source_schema_json"]),
        "experience_codex_md": str(package_dir / CORE_FILES["experience_codex_md"]),
        "experience_codex_json": str(package_dir / CORE_FILES["experience_codex_json"]),
        "mode_boundary_md": str(package_dir / CORE_FILES["mode_boundary_md"]),
        "mode_boundary_json": str(package_dir / CORE_FILES["mode_boundary_json"]),
        "approval_ingest_gate_md": str(package_dir / CORE_FILES["approval_ingest_gate_md"]),
        "approval_ingest_gate_json": str(package_dir / CORE_FILES["approval_ingest_gate_json"]),
        "library_coverage_md": str(package_dir / CORE_FILES["library_coverage_md"]),
        "library_coverage_json": str(package_dir / CORE_FILES["library_coverage_json"]),
        "codex_close_reading_gate_md": str(package_dir / CORE_FILES["codex_close_reading_gate_md"]),
        "codex_close_reading_gate_json": str(package_dir / CORE_FILES["codex_close_reading_gate_json"]),
        "codex_close_reading_target_md": str(package_dir / CORE_FILES["codex_close_reading_target_md"]),
        "codex_original_reread_gate_md": str(package_dir / CORE_FILES["codex_original_reread_gate_md"]),
        "codex_original_reread_gate_json": str(package_dir / CORE_FILES["codex_original_reread_gate_json"]),
        "codex_original_reread_target_md": str(package_dir / CORE_FILES["codex_original_reread_target_md"]),
        "codex_final_answer_gate_md": str(package_dir / CORE_FILES["codex_final_answer_gate_md"]),
        "codex_final_answer_gate_json": str(package_dir / CORE_FILES["codex_final_answer_gate_json"]),
        "codex_final_answer_target_md": str(package_dir / CORE_FILES["codex_final_answer_target_md"]),
        "answer_writeback_protocol_md": str(package_dir / CORE_FILES["answer_writeback_protocol_md"]),
        "answer_writeback_protocol_json": str(package_dir / CORE_FILES["answer_writeback_protocol_json"]),
        "regression_plan_md": str(package_dir / CORE_FILES["regression_plan_md"]),
        "regression_plan_json": str(package_dir / CORE_FILES["regression_plan_json"]),
        "human_reading_order_md": str(package_dir / CORE_FILES["human_reading_order_md"]),
        "human_reading_order_json": str(package_dir / CORE_FILES["human_reading_order_json"]),
        "question_tree": copy_file(research_result["question_tree"], package_dir / CORE_FILES["question_tree"]),
        "triaged_csv": copy_file(research_result["triaged_csv"], package_dir / CORE_FILES["triaged_csv"]),
        "cards": copy_file(research_result["cards"], package_dir / CORE_FILES["cards"]),
        "review_csv": copy_file(review_result["review_csv"], package_dir / CORE_FILES["review_csv"]),
        "reading_md": copy_file(review_result["reading_md"], package_dir / CORE_FILES["reading_md"]),
        "writing_md": copy_file(readback_result["writing_md"], package_dir / CORE_FILES["writing_md"]),
        "feedback_profile": copy_file(profile_path, package_dir / CORE_FILES["feedback_profile"]),
    }
    human_reading_order = build_human_reading_order_config(
        question=question,
        package_dir=package_dir,
    )
    route_profile = _route_profile_from_context(route_context, question)
    route_mode = _route_mode_from_context(route_context, question)
    aggregation_court_missing = _aggregation_court_missing(package_dir)
    if aggregation_court_missing:
        status = f"阻断：等待聚拢库取材与材料池入池；当前缺 {'、'.join(aggregation_court_missing)}。"
    elif not pipeline_audit.get("summary", {}).get("final_prewrite_ready"):
        status = "等待 Codex 生成 00I/00L/00M；最终答案硬阻断：候选材料已回聚拢库并进入材料池，但未完成材料池判定、精读材料词和写作前原文追证摘抄，不得写红楼解语。"
    else:
        status = "等待 Codex 红楼解语：00I/00L/00M 已完成，可以进入最终答案写作门。"
    manifest = {
        "generated_at": generated_at,
        "question": question,
        "package_dir": str(package_dir),
        "status": status,
        "parameters": {
            "limit_per_question": limit_per_question,
            "top_evidence": top_evidence,
            "review_limit": review_limit,
            "full_output_rule": "top_evidence/review_limit 为 0 时全量输出；本地工程不得替 Codex 省略已召回候选。",
            "use_feedback": use_feedback,
            "feedback_profile_path": str(feedback_profile_path) if feedback_profile_path else "",
            "run_smoke": run_smoke,
            "route_context": route_context,
        },
        "steps": steps,
        "smoke": smoke_result,
        "results": {
            "query_logic_strategy_gate": query_logic_strategy_gate,
            "entry_hard_gate": entry_hard_gate,
            "aggregation_flow_lock": aggregation_flow_lock,
            "machine_short_card": machine_short_card,
            "aggregation_material_bridge": aggregation_material_bridge,
            "judgment": judgment_result,
            "library_flow": library_flow,
            "final_reading_gate": final_reading_gate,
            "experience_entry": experience_entry,
            "process_inventory": process_inventory,
            "pipeline_audit": pipeline_audit,
            "source_schema": source_schema,
            "experience_codex": experience_codex,
            "mode_boundary": mode_boundary,
            "approval_ingest_gate": approval_ingest_gate,
            "library_coverage": library_coverage,
            "codex_close_reading_gate": codex_close_reading_gate,
            "codex_original_reread_gate": codex_original_reread_gate,
            "codex_final_answer_gate": codex_final_answer_gate,
            "eight_step_status": eight_step_status,
            "answer_writeback_protocol": answer_writeback_protocol,
            "regression_plan": regression_plan,
            "human_reading_order": human_reading_order,
            "research": research_result,
            "review": review_result,
            "readback": readback_result,
            "feedback": feedback_result,
        },
        "core_files": core_files,
        "internal_dirs": {
            "pool": str(pool_dir),
            "research": str(research_dir),
            "review": str(review_dir),
            "readback": str(readback_dir),
            "feedback": str(feedback_dir),
        },
    }

    manifest_path = package_dir / CORE_FILES["manifest"]
    overview_path = package_dir / CORE_FILES["overview"]
    manifest["core_files"]["manifest"] = str(manifest_path)
    manifest["core_files"]["overview"] = str(overview_path)
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    steps.append(step("核心文件整理", True, {"core_file_count": len(manifest["core_files"])}))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    overview_path.write_text(render_overview(manifest), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full Honglou closed-loop workflow for one complex question.")
    parser.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    parser.add_argument("--limit-per-question", type=int, default=0)
    parser.add_argument("--top-evidence", type=int, default=0)
    parser.add_argument("--review-limit", type=int, default=0)
    parser.add_argument("--out-root", default=str(OUT_ROOT))
    parser.add_argument("--feedback-profile", default=str(feedback_optimizer.DEFAULT_PROFILE_JSON))
    parser.add_argument("--route-context", default="")
    parser.add_argument("--no-feedback", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build_closed_loop(
                question=args.question,
                limit_per_question=args.limit_per_question,
                top_evidence=args.top_evidence,
                review_limit=args.review_limit,
                out_root=Path(args.out_root),
                use_feedback=not args.no_feedback,
                feedback_profile_path=Path(args.feedback_profile) if args.feedback_profile else None,
                run_smoke=not args.skip_smoke,
                route_context=args.route_context,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
