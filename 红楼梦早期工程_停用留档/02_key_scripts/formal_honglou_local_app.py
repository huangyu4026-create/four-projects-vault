#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import mimetypes
import os
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import formal_honglou_evidence_pack as evidence_pack
import formal_honglou_feedback_optimizer as feedback_optimizer
import formal_honglou_question_decomposer as decomposer
import formal_honglou_research_workflow as research_workflow
import formal_honglou_review_readback as review_readback
import formal_honglou_search_index as search_index
import formal_honglou_person_query_unifier as person_query_unifier
import formal_honglou_numbering_front_gate as numbering_front_gate
import formal_honglou_closed_loop as closed_loop
import formal_honglou_codex_recall as codex_recall
import formal_honglou_triangle_sync as triangle_sync
import formal_honglou_study_extension_writer as study_extension_writer
import formal_honglou_closure_check as closure_check


APP_TITLE = "红楼梦研究台"
APP_BUILD = "route-context-product-gate-archive-article-judge-recall-history-20260618"
TRIANGLE_HTML_CANDIDATES: list[Path] = [
    ROOT / "outputs" / "正式底库阅读闭环还原台" / "红楼梦_三角阅读闭环.html",
    Path(
        "/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/13_P03_红楼梦_HLM/50_输出区/来源路径保留/2026-06-03/notion-3-crv/outputs/正式底库阅读闭环还原台/红楼梦_三角阅读闭环.html"
    ),
]
TRIANGLE_INDEX_HTML_CANDIDATES: list[Path] = [
    TRIANGLE_HTML_CANDIDATES[0].parent / "index.html",
    Path(
        "/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/13_P03_红楼梦_HLM/50_输出区/来源路径保留/2026-06-03/notion-3-crv/outputs/正式底库阅读闭环还原台/index.html"
    ),
]
CODEX_PROCESSING_TTL_SECONDS = getattr(codex_recall, "PROCESSING_STALE_SECONDS", 900)
REVIEW_CSV = review_readback.DEFAULT_REVIEW_CSV
REVIEW_UPDATE_FIELDS = {"human_decision", "human_role", "usable_level", "writing_use", "human_note"}
REVIEW_DECISIONS = ["待复核", "保留", "剔除", "降级", "反证"]
REVIEW_EXPORT_DIR = ROOT / "outputs" / "正式底库本地查询入口" / "复核筛选导出"
CODEX_ANSWER_ROOT = ROOT / "outputs" / "红楼梦Codex最终答案"
CODEX_PENDING_DIR = CODEX_ANSWER_ROOT / "待回答"
CODEX_FINAL_DIR = CODEX_ANSWER_ROOT / "最终答案"
CODEX_QUEUE_JSON = CODEX_ANSWER_ROOT / "Codex召回队列.json"
CODEX_QUEUE_MD = CODEX_ANSWER_ROOT / "Codex召回队列.md"
READER_DIRECT_QA_DIR = ROOT / "outputs" / "正式底库阅读闭环还原台" / "随读直答"
READER_DIRECT_QA_JSON = READER_DIRECT_QA_DIR / "reader_direct_qa.json"
READER_DIRECT_RUN_DIR = READER_DIRECT_QA_DIR / "运行记录"
READER_DIRECT_MD_DIR = READER_DIRECT_QA_DIR / "章回问答录"
READER_DIRECT_ALL_MD = READER_DIRECT_QA_DIR / "随读直答总记录.md"
READER_DIRECT_TIMEOUT_SECONDS = 240
READER_DIRECT_ACTIVE: set[str] = set()
READER_DIRECT_LOCK = threading.Lock()
CODEX_ARCHIVE_MD = CODEX_ANSWER_ROOT / "问答记录总档案.md"
CODEX_INGEST_DIR = CODEX_ANSWER_ROOT / "红楼解语入库预检"
CODEX_MACHINE_EXPORT_DIR = CODEX_ANSWER_ROOT / "机器分析导出"
CODEX_CONTINUOUS_EXPORT_DIR = CODEX_MACHINE_EXPORT_DIR / "连续导出"
CODEX_CONTINUOUS_EXPORT_MD = CODEX_CONTINUOUS_EXPORT_DIR / "当前连续导出.md"
CODEX_CONTINUOUS_EXPORT_JSONL = CODEX_CONTINUOUS_EXPORT_DIR / "当前连续导出.jsonl"
CODEX_QUEUE_CLEANUP_DIR = CODEX_ANSWER_ROOT / "队列清理归档"
CODEX_ABORT_DIR = getattr(codex_recall, "CODEX_ABORT_DIR", CODEX_ANSWER_ROOT / "已终止请求")
MACHINE_EXPORT_TEXT_LIMIT = 60000
MACHINE_EXPORT_ROW_LIMIT = 80
DEFAULT_QUESTION_PLACEHOLDERS = {
    "请在这里输入你的红楼梦问题。",
    "请在这里输入你的红楼梦问题",
}
ENGINEERING_TRIGGER_PHRASE = "进入红楼梦工程"
ENGINEERING_TRIGGER_PREFIX = f"{ENGINEERING_TRIGGER_PHRASE}："
ACTIVE_LOCK_STATUSES = {
    "待Codex处理",
    "待处理",
    "处理中",
    "待最终回显稿",
}
TERMINAL_QUEUE_STATUSES = {"已处理", "处理失败", "已终止"}


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, body: str, status: int = 200) -> None:
    raw = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def html_file_response(handler: BaseHTTPRequestHandler, path: Path, status: int = 200) -> None:
    raw = path.read_bytes()
    content_type, _ = mimetypes.guess_type(str(path))
    handler.send_response(status)
    handler.send_header("Content-Type", content_type or "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def pick_triangle_html() -> Path | None:
    return next((path for path in TRIANGLE_HTML_CANDIDATES if path.exists()), None)


def pick_triangle_index() -> Path | None:
    return next((path for path in TRIANGLE_INDEX_HTML_CANDIDATES if path.exists()), None)


def split_terms(value: str) -> list[str]:
    return evidence_pack.clean_terms([value])


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_json_file(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json_file(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def clean_text(value: object) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = clean_text(value).lower()
    if not text:
        return default
    if text in {"true", "1", "yes", "y", "on", "是", "真"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", "假", "none", "null"}:
        return False
    return default


def short_text(value: object, limit: int = 220) -> str:
    text = " ".join(clean_text(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def codex_error_summary(
    value: object,
    error_category: str = "",
    error_stage: str = "",
    return_code: object = None,
    error_snippet: str = "",
) -> str:
    text = clean_text(value)
    details = []
    category = clean_text(error_category)
    stage = clean_text(error_stage)
    code = clean_text(return_code)
    snippet = clean_text(error_snippet)
    if category:
        details.append(f"分类：{category}")
    if stage:
        details.append(f"阶段：{stage}")
    if code:
        details.append(f"返回码：{code}")
    if details:
        suffix = "；".join(details)
        if text:
            return f"{suffix}；{text}"
        if snippet:
            return f"{suffix}；{snippet}"
        return suffix
    if not text:
        return "未记录原因"
    lowered = text.lower()
    if "chatgpt.com" in lowered or "stream disconnected" in lowered or "could not resolve host" in lowered:
        if snippet:
            return "Codex 外部连接失败；" + snippet
        return "Codex 外部连接失败；本地工程包已生成，已停在 Codex 判别门，等待连接恢复后继续。"
    return short_text(text, 240)


def read_text_excerpt(path: str | Path, limit: int = 4200) -> str:
    source = Path(clean_text(path))
    if not source.exists() or not source.is_file():
        return ""
    text = source.read_text(encoding="utf-8", errors="ignore").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n……后文已省略，完整内容见工程文件。"


def read_csv_preview(path: str | Path, limit: int = 8) -> list[dict]:
    source = Path(clean_text(path))
    if not source.exists() or not source.is_file():
        return []
    rows = read_csv(source)
    return rows[:limit]


def workflow_trigger_excerpt(record: dict) -> str:
    question = clean_text(record.get("question"))
    display_question = clean_text(record.get("display_question")) or strip_honglou_engineering_trigger(question)
    engineering_question = clean_text(record.get("engineering_question")) or honglou_engineering_question(display_question or question)
    task_intent = clean_text(record.get("task_intent"))
    requirements = clean_text(record.get("requirements"))
    request_id = clean_text(record.get("request_id"))
    lines = [
        "## 问题入口",
        "",
        f"- 原始提问：{display_question or '未记录'}",
        f"- 工程触发问题：{engineering_question or '未记录'}",
        f"- 请求 ID：{request_id or '未记录'}",
        f"- 页面触发词/路线：{task_intent or '红楼解语'}",
        f"- 附加要求：{requirements or '无'}",
        "",
        "## 工程入口规矩",
        "",
        "- 页面提交的不是普通聊天，而是“问题 + 触发词 + 路线参数”的工程输入。",
        "- 入口先规范为：问题入口 -> 新编号入口门 -> 对象收点与编号交集 -> 路由门 -> 原文复核 -> 材料池 -> Codex 红楼解语。",
        "- 拆解问题时优先判断要搜什么词、走哪类库、回哪些原文，再由红楼解语层自由组织。",
        "- 搜索命中只是线索；每条候选都必须回到原文段落和上下文复合，才能进入材料池。",
        "- 工程过程显示在过程区，红楼解语区只显示 Codex 读取工程产物后的回答。",
        "- 每次题目都要沉淀路径经验：题目如何理解、关键词如何生成、哪些证据有效、哪些误召回应降级。",
    ]
    return "\n".join(lines)


def pending_trigger_packet(question: str, task_intent: str, requirements: str, request_id: str, question_key: str) -> str:
    engineering_question = honglou_engineering_question(question)
    lines = [
        "## 工程触发包",
        "",
        f"- 请求 ID：`{request_id}`",
        f"- 问题 key：`{question_key}`",
        f"- 工程触发问题：{engineering_question}",
        f"- 页面路线：{task_intent or '红楼解语'}",
        f"- 附加要求：{requirements or '无'}",
        "",
        "### 运行链",
        "",
        "1. 过库地图：先读取 `128_聚拢库总入口_全库地图与流程记录.md` 与 `25_库登记处机器总表.csv`，生成四格流程记录。",
        "2. 进聚拢库：把问题先放入聚拢总图运行总线，不从单个 SQLite 或旧搜索词网络直接开答。",
        "3. 问题类型：判断人物 / 关系 / 物象 / 空间 / 事件 / 主题 / 文本功能 / 全文穷尽。",
        "4. 相关库深盘：按题型进入人物、关系、物象、空间、事件、专题或全文穷尽工具。",
        "5. 回聚拢库：相关库得到的规范名、标签、入口词、候选编号必须回到编号、聚拢段、聚拢单元、聚拢事件、聚拢场或聚拢域。",
        "6. 聚拢层判断：在聚拢库内放大、缩小、交集、串域；旧搜索词网络只能补点，不能直接入池。",
        "7. 原文裁判：所有候选必须回原文段落与上下文确认，不能只用模块摘要、外层标题或旧文稿下结论。",
        "8. 材料池：只有具备编号来源、穷尽来源说明、路由门说明或原文锚点的材料才能进入材料池。",
        "9. 规则学习：记录本题的对象识别、收点路径、编号交集、路由门、有效证据和误召回原因，作为后续问题的规则经验。",
        "10. Codex 红楼解语：Codex 只读取工程产物和材料池来写回答，不能用本地模块搜索结果冒充红楼解语。",
        "",
        "### 页面回显规则",
        "",
        "- 红楼解语区只显示 Codex 读完工程材料后的回答。",
        "- 问题树、新编号入口门、对象收点、编号交集、路由门、证据池、原文复核、材料池、二次补查和状态台只显示在工程运转结果区。",
        "- 如果材料池不足，应输出缺口和补查词，而不是硬写结论。",
        "",
        person_query_unification_entry_packet(question),
        "",
        numbering_front_gate_entry_packet(question),
    ]
    return "\n".join(lines)


def person_query_unification_entry_packet(question: str) -> str:
    lines = [
        "### 人物消歧与查询归一入口门",
        "",
        "- 入口级硬规则：进入红楼梦工程后，默认开启人物消歧与人物查询归一状态。",
        "- 不能等判成“人物题”以后才想起来消歧；新增题型也不得绕过人物归一门。",
        "- 只要问题、材料池、结构库、路由门或原文回读中出现人物名、别名、称谓、代称、亲属身份、职分、关系、同场、空间归属、物件归属、事件参与者，必须先归一到 `character_key`。",
        "- 归一以后必须使用人物查询归一包：规范名、结构库映射名、全部别名、全文查询词、`segment_no`、`cluster_unit`、`event_id`。",
        "- 当前可调用包：`72_人物查询归一包_全量生成表.csv/json`。",
        "",
    ]
    packs: list[dict] = []
    try:
        if search_index.SEARCH_DB.exists():
            conn = sqlite3.connect(search_index.SEARCH_DB)
            conn.row_factory = sqlite3.Row
            try:
                packs = person_query_unifier.detect_person_query_packs(conn, question, max_matches=8)
            finally:
                conn.close()
    except Exception as exc:
        lines.append(f"- 自动识别状态：读取归一包时出现异常，规则仍必须执行。异常摘要：{short_text(exc, 120)}")
        return "\n".join(lines)

    if not packs:
        lines.append("- 自动识别状态：本题入口暂未识别到明确人物线索；但后续查库和回原文过程中一旦出现人物，仍必须先消歧再查询归一。")
        return "\n".join(lines)

    lines.append("- 自动识别到的人物线索：")
    for pack in packs:
        matched = "、".join(pack.get("matched_terms", [])) or "未记录"
        lines.append(
            f"  - {pack['default_display_name']} / {pack['canonical_mapping_name']} / `{pack['character_key']}`；入口词：{matched}；segment_no：{pack['segment_count']}；cluster_unit：{pack['cluster_unit_count']}；event_id：{pack['event_count']}。"
        )
    return "\n".join(lines)


def numbering_front_gate_entry_packet(question: str) -> str:
    try:
        return numbering_front_gate.render_front_gate_packet(question)
    except Exception as exc:
        return "\n".join(
            [
                "### 新编号入口门",
                "",
                "- 入口级硬规则：旧前门封城，新编号入口仍为唯一前门。",
                f"- 自动生成编号门票时出现异常：{short_text(exc, 160)}",
                "- 异常时不得回落到旧候选提示独立入口；只能等待编号入口修复或人工转入可追溯收点。",
            ]
        )


def resolve_workflow_package_for_record(record: dict) -> Path:
    package_text = clean_text(record.get("workflow_package"))
    if package_text:
        package_path = Path(package_text)
        if package_path.exists() and package_path.is_dir():
            return package_path
    question = clean_text(record.get("question"))
    if not question:
        return Path("")
    out_root = Path(getattr(closed_loop, "OUT_ROOT", ROOT / "outputs" / "正式底库闭环工作流"))
    if not out_root.exists():
        return Path("")
    question_head = question[:60]
    safe_head = safe_filename_part(question, 30)
    candidates = sorted(
        [path for path in out_root.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates[:80]:
        if safe_head and safe_head in path.name:
            return path
        overview = path / "00_闭环总览.md"
        if overview.exists():
            try:
                if question_head and question_head in overview.read_text(encoding="utf-8", errors="ignore")[:1800]:
                    return path
            except OSError:
                continue
    return Path("")


def workflow_process_payload(record: dict) -> dict:
    workflow_files = record.get("workflow_files", {})
    if not isinstance(workflow_files, dict):
        workflow_files = {}
    workflow_files = dict(workflow_files)
    package_path = resolve_workflow_package_for_record(record)
    has_package = bool(package_path.name) and package_path.exists() and package_path.is_dir()
    if has_package:
        manifest_path = package_path / closed_loop.CORE_FILES["manifest"]
        manifest = read_json_file(manifest_path, {})
        if isinstance(manifest, dict):
            core_files = manifest.get("core_files", {})
            if isinstance(core_files, dict):
                for key, value in core_files.items():
                    if clean_text(value) and not clean_text(workflow_files.get(key)):
                        workflow_files[key] = clean_text(value)
        for key, filename in closed_loop.CORE_FILES.items():
            if clean_text(workflow_files.get(key)):
                continue
            candidate = package_path / filename
            if candidate.exists():
                workflow_files[key] = str(candidate)
    for top_key in (
        "codex_process_judgment_md",
        "codex_process_judgment_json",
        "codex_material_judgment_md",
        "codex_material_judgment_json",
        "codex_close_reading_md",
        "codex_close_reading_json",
    ):
        if clean_text(record.get(top_key)) and not clean_text(workflow_files.get(top_key)):
            workflow_files[top_key] = clean_text(record.get(top_key))
    summary = record.get("workflow_summary", {})
    if not isinstance(summary, dict):
        summary = {}
    if has_package:
        status_summary = read_json_file(package_path / "21_闭环状态摘要.json", {})
        if isinstance(status_summary, dict):
            review_progress = status_summary.get("review_progress", {})
            if isinstance(review_progress, dict):
                summary = {
                    **summary,
                    "review_rows": summary.get("review_rows") or review_progress.get("total_rows"),
                    "usable_rows": summary.get("usable_rows") or review_progress.get("usable_rows"),
                    "pending_rows": summary.get("pending_rows") or review_progress.get("pending_rows"),
                }
            files_from_status = status_summary.get("files", {})
            if isinstance(files_from_status, dict):
                for key, value in files_from_status.items():
                    if clean_text(value) and not clean_text(workflow_files.get(key)):
                        workflow_files[key] = clean_text(value)
    sections = []

    def add_synthetic(key: str, title: str, description: str, excerpt: str) -> None:
        if excerpt:
            sections.append(
                {
                    "key": key,
                    "title": title,
                    "description": description,
                    "path": "",
                    "excerpt": excerpt,
                    "rows": [],
                }
            )

    def add_text(key: str, title: str, description: str, limit: int = 4200) -> None:
        path = workflow_files.get(key, "")
        add_path_text(key, title, description, path, limit=limit)

    def add_path_text(key: str, title: str, description: str, path: str, limit: int = 4200) -> None:
        excerpt = read_text_excerpt(path, limit=limit)
        if path or excerpt:
            sections.append(
                {
                    "key": key,
                    "title": title,
                    "description": description,
                    "path": path,
                    "excerpt": excerpt,
                    "rows": [],
                }
            )

    def add_csv(key: str, title: str, description: str, limit: int = 8) -> None:
        path = workflow_files.get(key, "")
        rows = read_csv_preview(path, limit=limit)
        if path or rows:
            sections.append(
                {
                    "key": key,
                    "title": title,
                    "description": description,
                    "path": path,
                    "excerpt": "",
                    "rows": rows,
                }
            )

    strategy_excerpt = ""
    query_strategy = record.get("query_strategy", {})
    if isinstance(query_strategy, dict) and query_strategy:
        execution_terms = [
            str(item)
            for item in record.get("query_strategy_terms", [])
            if clean_text(item)
        ]
        if not execution_terms:
            execution_terms = [
                str(item)
                for item in query_strategy.get("search_terms", [])[:8]
                if clean_text(item)
            ]
        full_terms = [
            str(item)
            for item in query_strategy.get("search_terms", [])
            if clean_text(item)
        ]
        full_terms_note = (
            f"完整词网底账：{len(full_terms)} 个，保留作归一/补查说明，不作为首轮实际执行词。"
            if full_terms
            else "完整词网底账：未记录。"
        )
        strategy_lines = [
            "## Codex 查询词路",
            "",
            f"- 问题中心：{clean_text(query_strategy.get('question_center')) or '未记录'}",
            f"- 实际执行词：{'、'.join(execution_terms) or '未记录'}",
            f"- {full_terms_note}",
            f"- 优先库：{'、'.join(str(item) for item in query_strategy.get('preferred_libraries', []) if clean_text(item)) or '未记录'}",
            f"- 查证顺序：{clean_text(query_strategy.get('source_order')) or '未记录'}",
            "",
            "### 注意事项",
            "",
        ]
        guardrails = query_strategy.get("guardrails", [])
        if isinstance(guardrails, list) and guardrails:
            for item in guardrails:
                strategy_lines.append(f"- {clean_text(item)}")
        else:
            strategy_lines.append("- 未记录")
        strategy_excerpt = "\n".join(strategy_lines)

    add_path_text("answer_md", "1. 红楼解语", "给人看的解惑答疑；它应当基于工程材料池再思考，不显示模块搜索结果。", clean_text(record.get("answer_md")), limit=7600)
    add_text("codex_final_answer_gate_md", "1A. 红楼解语生成门", "最终答案入口；未生成时显示等待 Codex，不用模块搜索替代。", limit=5200)
    add_text("codex_final_answer_target_md", "1B. 红楼解语目标稿位", "Codex 最终答案唯一写入位置。", limit=4200)
    add_text("aggregation_flow_lock_md", "1C. 128 聚拢库流程锁", "进入工程先过全库地图、先回聚拢库、相关库深盘、最后原文裁判。", limit=5200)
    add_text("machine_short_card_md", "1D. 机器短卡与证据分层策略", "每题只打一张小票：对象、入口词、相关库、排除触发；后台做证据分层，前台不加重。", limit=3600)
    add_path_text("codex_close_reading_md", "2. Codex 精读材料词", "Codex 在最终写作前逐条读材料、舍取材料、整理原文锚点和文风方向。", clean_text(record.get("codex_close_reading_md")), limit=7600)
    add_text("codex_close_reading_gate_md", "2A. 精读材料词生成门", "最终答案前的材料判别入口。", limit=5200)
    add_text("codex_close_reading_target_md", "2B. 精读材料词目标稿位", "Codex 写材料取舍和证据支点的稿位。", limit=4200)
    add_text("final_reading_gate_md", "3. 材料池精读门", "红楼解语前必须先读材料池、逐条判定证据，并保留原子段原文追溯。", limit=6200)
    add_text("reading_md", "4. 复核阅读单", "按复核顺序生成的原文阅读提示。", limit=4200)
    add_csv("triaged_csv", "5. 证据池 / 候选材料池", "工程按查询线索召回的候选材料；它只供 Codex 判定，不再自动充当主证。")
    add_text("cards", "6. 候选材料卡片", "工程整理出的候选原文卡片，便于 Codex 和人先读。", limit=4200)
    add_csv("review_csv", "7. 原文复核表", "工程把证据池转成可人工判断、可二次修正的复核表。")
    add_text("writing_md", "8. 复核后写作材料", "工程按复核状态回读出来的候选写作材料池。", limit=4200)
    add_path_text("codex_material_judgment_md", "9. Codex 指挥中心 / 材料池判定", "Codex 逐条判定候选材料能否使用；没有这一道判定，最终答案不继续。", clean_text(record.get("codex_material_judgment_md")), limit=7200)
    add_path_text("codex_process_judgment_md", "10. Codex 全流程过程判别", "Codex 按本题自然流程检查问题判断、关键词网络、证据池、复核表和回读材料是否足以进入下一步。", clean_text(record.get("codex_process_judgment_md")), limit=7200)
    add_text("process_inventory_md", "11. 全流程产物与判别门总账", "运行前置总规则：Codex 策略是方向盘和调度单；底层完整出包，Codex 回收后决定采用、降级、补查、跳过或停止。", limit=6200)
    add_text("library_flow_md", "12. 库线原文流转骨架", "工程按 Notion 源结构和本地底库生成的盘库入口：库、映射、原文、原子段和材料池的关系。", limit=5200)
    if strategy_excerpt:
        add_synthetic("query_strategy", "13. Codex 查询词路", "Codex 先读题目和经验仓后给出的查证路线；本地程序只按此执行查询。", strategy_excerpt)
    add_text("question_judgment_md", "14. 问题判断程序", "红楼梦工程自己的第0步：判断问题类型、查证路径、关键词网络和经验仓。", limit=4200)
    add_text("question_tree", "15. 问题拆解 / 搜索词网络", "红楼梦工程真实生成的搜索词网络、子问题、实体、关键词、优先证据轴。")
    add_text("review_coverage_md", "16. 复核覆盖矩阵", "检查材料池是否覆盖问题的关键方向。", limit=3200)
    add_text("source_verify_md", "17. 真源核验统一报告", "原文锚点、段落、回目和引文核验的统一报告。", limit=3600)
    add_csv("source_verify_csv", "18. 真源核验清单", "红楼解语和文章可追溯原证的核验清单。")
    add_text("next_plan_md", "19. 二次追问与补证计划", "拆题或证据池不足时，工程建议下一轮怎么补。", limit=3600)
    add_csv("next_tasks_csv", "20. 下一轮出库任务", "二次补证的任务表、检索词和优先级。")
    add_text("review_plan_md", "21. 复核优先清单", "工程根据证据池生成的下一步复核优先级。", limit=3200)
    add_csv("review_sheet_csv", "22. 当前批次复核工作表", "人工或后续智能复核可以逐条回填的工作表。")
    add_text("review_firstpass_cards_md", "23. 首轮复核逐条判读卡片", "首轮证据逐条判读材料。", limit=3200)

    add_text("keyword_precheck_json", "30. 关键词网络预检（机器摘要）", "结构化记录：候选实体、搜索词、经验类型、成功信号和误召回信号。", limit=4200)
    add_text("library_flow_json", "31. 库线原文流转摘要（机器摘要）", "结构化记录本题应看哪些库组、库到线、线到原文、原文到材料池的流转路径。", limit=3600)
    add_text("final_reading_gate_json", "32. 精读门摘要（机器摘要）", "结构化记录材料池精读门槛、文风状态和原证追溯规则。", limit=3600)
    add_text("experience_entry_md", "33. 经验复盘入账", "每题自动增加经验值，并说明后续经验复盘、经验提取、经验总结的触发方式。", limit=3600)
    add_text("experience_entry_json", "34. 经验复盘入账摘要（机器摘要）", "结构化记录本题主路径、经验值增量和全局经验总账位置。", limit=2600)
    add_synthetic("trigger_packet", "36. 触发词与工程入口", "页面下拉、按钮和用户问题合成的工程请求。", workflow_trigger_excerpt(record))
    add_csv("review_queue_csv", "37. 复核批次队列", "把复核任务拆成可执行批次。")
    add_text("review_workbench_md", "38. 复核填表工作台", "把复核表整理成更适合检查的工作台。", limit=2600)
    add_csv("review_workbench_csv", "39. 复核填表工作台表", "工作台对应的结构化行。")
    add_csv("review_coverage_csv", "40. 复核覆盖矩阵表", "覆盖矩阵对应的结构化行。")
    add_text("review_firstpass_md", "41. 首轮复核执行单", "工程建议先复核的最小覆盖证据。", limit=2600)
    add_csv("review_firstpass_sheet_csv", "42. 首轮复核小表", "首轮复核的轻量表。")
    add_text("continue_report_md", "43. 一键续跑报告", "本次把工程过程件补齐的执行记录。", limit=2600)
    add_text("overview", "44. 闭环总览", "本次工程运转的总览和核心文件。", limit=2400)
    add_text("workflow_status_md", "45. 工程状态台", "闭环状态、下一步和可继续操作。", limit=2400)

    return {
        "status": clean_text(record.get("workflow_status")),
        "package": str(package_path) if has_package else clean_text(record.get("workflow_package")),
        "summary": summary,
        "files": workflow_files,
        "sections": sections,
        "ready": bool(has_package or sections or workflow_files or summary),
    }


def _to_iso_datetime(value: str) -> datetime | None:
    value = clean_text(value)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_stale_final_wait_item(item: dict, timeout_seconds: int | None = None) -> bool:
    if clean_text(item.get("status")) != "待最终回显稿":
        return False
    workflow_package = clean_text(item.get("workflow_package") or item.get("package") or item.get("package_dir"))
    if workflow_package and Path(workflow_package).exists():
        return False
    timeout_seconds = int(timeout_seconds or (getattr(codex_recall, "PROCESS_RETRY_INTERVAL_SECONDS", 90) * 2))
    timeout_seconds = max(60, timeout_seconds)
    last_update = _to_iso_datetime(clean_text(item.get("updated_at") or item.get("processing_started_at")))
    if not last_update:
        return True
    return (datetime.now() - last_update).total_seconds() >= timeout_seconds


def _is_processing_stale(item: dict) -> bool:
    started_mark = clean_text(item.get("processing_started_at") or item.get("updated_at"))
    start_dt = _to_iso_datetime(started_mark)
    if not start_dt:
        return False
    return (datetime.now() - start_dt).total_seconds() > CODEX_PROCESSING_TTL_SECONDS


def review_missing_fields(row: dict) -> list[str]:
    normalized = row.get("normalized_decision") or review_readback.normalize_decision(row.get("human_decision", ""))
    if normalized == "待复核":
        return []
    missing = []
    if normalized == "剔除":
        if not clean_text(row.get("human_role")):
            missing.append("角色")
        if not clean_text(row.get("human_note")):
            missing.append("备注")
        return missing
    if not clean_text(row.get("usable_level")):
        missing.append("等级")
    if not clean_text(row.get("human_role")):
        missing.append("角色")
    if not clean_text(row.get("writing_use")):
        missing.append("写作用途")
    return missing


def enriched_review_rows(rows: list[dict]) -> list[dict]:
    enriched = []
    for row in rows:
        normalized = review_readback.normalize_decision(row.get("human_decision", ""))
        enriched_row = {**row, "normalized_decision": normalized}
        missing = review_missing_fields(enriched_row)
        enriched.append(
            {
                **enriched_row,
                "missing_fields": "、".join(missing),
                "quality_status": "需补字段" if missing else "完整",
            }
        )
    return enriched


def review_counts(rows: list[dict]) -> dict:
    return dict(Counter(row.get("normalized_decision", "待复核") for row in rows))


def review_progress(rows: list[dict]) -> dict:
    counts = review_counts(rows)
    total = len(rows)
    pending = counts.get("待复核", 0)
    completed = max(0, total - pending)
    incomplete = sum(1 for row in rows if row.get("missing_fields"))
    completion_rate = round((completed / total) * 100, 1) if total else 0.0
    quality_rate = round(((completed - incomplete) / completed) * 100, 1) if completed else 0.0
    return {
        "total_rows": total,
        "completed_rows": completed,
        "pending_rows": pending,
        "incomplete_rows": incomplete,
        "completion_rate": completion_rate,
        "quality_rate": quality_rate,
        "decision_counts": {key: counts.get(key, 0) for key in REVIEW_DECISIONS},
    }


def loop_status_api(package: str = "latest") -> dict:
    package = clean_text(package) or "latest"
    status_payload = closed_loop.loop_status(package=package, out_root=closed_loop.OUT_ROOT)
    package_dir = Path(status_payload["package"])
    manifest = closed_loop.load_manifest(package_dir)
    manifest_path = package_dir / closed_loop.CORE_FILES["manifest"]

    files = status_payload.get("files", {})
    preferred_files = [
        "20_闭环状态与下一步操作台",
        "09_可写作证据包",
        "04_复核表",
        "00_闭环总览",
        "21_闭环状态摘要.json",
    ]

    important_files = []
    for name in preferred_files:
        info = files.get(name)
        if not info:
            # 兼容关键字变动或手工改名
            continue
        important_files.append(
            {
                "name": name,
                "exists": bool(info.get("exists")),
                "size": info.get("size", 0),
                "path": info.get("path", ""),
            }
        )

    return {
        "package": status_payload.get("package", ""),
        "question": status_payload.get("question", ""),
        "status": status_payload.get("status", ""),
        "status_file": status_payload.get("status_file", ""),
        "status_json": status_payload.get("status_json", ""),
        "generated_at": manifest.get("generated_at", ""),
        "updated_at": manifest.get("updated_at", ""),
        "phase": status_payload.get("recommended_next", {}).get("phase", ""),
        "next_action": status_payload.get("recommended_next", {}).get("next_action", ""),
        "primary_file": status_payload.get("recommended_next", {}).get("primary_file", ""),
        "commands": status_payload.get("recommended_next", {}).get("commands", []),
        "review_progress": status_payload.get("review_progress", {}),
        "sheet_progress": status_payload.get("sheet_progress", {}),
        "firstpass_sheet_progress": status_payload.get("firstpass_sheet_progress", {}),
        "sheet_quality": status_payload.get("sheet_quality", {}),
        "firstpass_sheet_quality": status_payload.get("firstpass_sheet_quality", {}),
        "files": important_files,
        "core_file_count": len(manifest.get("core_files", {})),
        "manifest": str(manifest_path),
        "steps": manifest.get("steps", []),
    }


def loop_list_api() -> dict:
    return closed_loop.loop_list(out_root=closed_loop.OUT_ROOT)


def filter_review_rows(rows: list[dict], decision: str) -> list[dict]:
    decision_filter = clean_text(decision)
    if not decision_filter or decision_filter in {"全部", "all"}:
        return rows
    if decision_filter in {"保留剔除对照", "保留/剔除对照", "compare"}:
        return [row for row in rows if row.get("normalized_decision") in {"保留", "剔除"}]
    if decision_filter in {"未填写字段", "需补字段", "incomplete"}:
        return [row for row in rows if row.get("missing_fields")]
    return [row for row in rows if row.get("normalized_decision") == decision_filter]


def safe_filename_part(text: str, limit: int = 40) -> str:
    value = clean_text(text) or "全部"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)[:limit] or "全部"



def reader_direct_safe_part(value: str, max_len: int = 80) -> str:
    text = clean_text(value)
    safe = "".join(ch if ch.isalnum() or ch in "-_一二三四五六七八九十百千万回章卷集册上下前后中天地人物情理心梦" else "_" for ch in text)
    safe = "_".join(part for part in safe.split("_") if part)
    return (safe or "未分章")[:max_len]


def reader_direct_chapter_label(record: dict) -> str:
    chapter_no = clean_text(record.get("chapter_no"))
    chapter_title = clean_text(record.get("chapter_title"))
    if chapter_no and chapter_title:
        return f"第{chapter_no}回｜{chapter_title}"
    if chapter_no:
        return f"第{chapter_no}回"
    return chapter_title or "未分章"


def reader_direct_record_markdown(record: dict) -> str:
    question = clean_text(record.get("question"))
    answer = clean_text(record.get("answer_markdown")) or clean_text(record.get("status")) or "等待回答。"
    updated_at = clean_text(record.get("updated_at"))
    request_id = clean_text(record.get("request_id"))
    chapter = reader_direct_chapter_label(record)
    mode = "解释" if clean_text(record.get("reader_mode")) == "explain" else "问题"
    if answer and f"记录时间：{updated_at}" not in answer:
        answer = answer.rstrip() + f"\n\n记录时间：{updated_at}"
    return (
        f"## {updated_at}｜{chapter}｜{mode}\n\n"
        f"- 请求：{request_id}\n"
        f"- 类型：{mode}\n"
        f"- 时间：{updated_at}\n"
        f"- 内容：{question}\n\n"
        f"**回答**\n\n{answer}\n"
    )


def reader_direct_write_markdown_files(data: dict) -> None:
    records = [item for item in data.get("records", []) if isinstance(item, dict)]
    READER_DIRECT_QA_DIR.mkdir(parents=True, exist_ok=True)
    READER_DIRECT_MD_DIR.mkdir(parents=True, exist_ok=True)
    header = "# 随读直答总记录\n\n本文件只记录阅读页左侧随读问答，不进入红楼梦工程召回队列。\n\n"
    READER_DIRECT_ALL_MD.write_text(header + "\n---\n\n".join(reader_direct_record_markdown(item) for item in records), encoding="utf-8")
    grouped: dict[str, list[dict]] = {}
    for item in records:
        grouped.setdefault(reader_direct_chapter_label(item), []).append(item)
    for label, items in grouped.items():
        path = READER_DIRECT_MD_DIR / f"{reader_direct_safe_part(label)}.md"
        path.write_text(f"# {label}｜随读问答录\n\n" + "\n---\n\n".join(reader_direct_record_markdown(item) for item in items), encoding="utf-8")


def reader_direct_update_record(request_id: str, updates: dict) -> dict:
    request_id = clean_text(request_id)
    with READER_DIRECT_LOCK:
        data = reader_direct_load()
        record = reader_direct_find_record(data, request_id=request_id)
        if not record:
            return {}
        record.update(updates)
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        answer = clean_text(record.get("answer_markdown"))
        if answer and clean_text(record.get("answer_state")) == "answered" and "记录时间：" not in answer:
            record["answer_markdown"] = answer.rstrip() + f"\n\n记录时间：{record['updated_at']}"
        reader_direct_save(data)
        try:
            reader_direct_write_markdown_files(data)
        except Exception:
            pass
        return dict(record)


def reader_direct_build_prompt(record: dict) -> str:
    chapter = reader_direct_chapter_label(record)
    question = clean_text(record.get("question"))
    reader_mode = clean_text(record.get("reader_mode")) or "question"
    if clean_text(record.get("chapter_title")) == "红楼梦工程工作台":
        return f"""
你是红楼梦工程工作台右侧的红楼解语助手。现在直接回答用户刚刚提交的问题，这个回复显示在页面最上方的“红楼解语”框里。

要求：
- 先给答案，不要只说流程，不要只说“我会去查”。
- 像对话一样直接回答，不输出后台路径、队列、JSON、文件名或调试信息。
- 如果依据还不够，仍要给“目前可以先这样判断”的回答，同时说明哪一点需要下方工程页继续查证。
- 下方工程页会显示问题拆解、证据页和材料池；这些流程不要占据顶部答案区。
- 回答要清楚、自然、短一些，优先让用户马上看懂你在回应什么。

用户问题：{question}
""".strip()
    if reader_mode == "explain":
        mode_rules = """
本次是【解释】模式。读者输入的内容可能是一个字、一个词、一句话、一首诗或一小段原文。
回答要求：
- 直接解释输入内容，不要把它当成开放研究问题。
- 如果是单字或难字：先给读音/拼音，再解释字义、在文中的意思；必要时说明古今义差别。
- 如果是词语：解释每个关键字，再合起来解释整体意思。
- 如果是句子或诗：先给白话意思，再解释难字难词、语气、上下文作用。
- 如果和《红楼梦》当前回目有关，补一句它在当前语境里的作用。
- 篇幅适中，清楚好读。
""".strip()
    else:
        mode_rules = """
本次是【问题】模式。读者输入的是随读问题。
回答要求：
- 直接给读者可读答案，不解释后台工程。
- 如果问题涉及《红楼梦》章回、人物、物象、文字读音、词义、情节，请优先给清楚结论，再给必要依据。
- 如果不确定，不要硬编，说明边界，并给出可继续查证的方向。
- 篇幅适中；读书页里优先清楚、好读、能马上用。
""".strip()
    return f"""
你是阅读页左侧的随读答疑助手。现在直接回答读者，不进入红楼梦工程召回队列，不写入材料池，不启动三角闭环工程。

{mode_rules}
- 只输出回答正文，不要输出 JSON，不要输出文件路径，不要输出“已收到问题”。

当前阅读位置：{chapter}
读者输入：{question}
""".strip()


def reader_direct_codex_output_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return clean_text(value)


def reader_direct_generate_answer(request_id: str) -> None:
    request_id = clean_text(request_id)
    try:
        data = reader_direct_load()
        record = reader_direct_find_record(data, request_id=request_id)
        if not record:
            return
        if clean_text(record.get("answer_markdown")) and clean_text(record.get("answer_state")) == "answered":
            return
        current_answer = clean_text(record.get("answer_markdown"))
        reader_direct_update_record(request_id, {"status": "正在补充完整回答。" if current_answer else "正在直接回答。", "answer_state": "processing", "answer_checked": bool(current_answer)})
        record = reader_direct_find_record(reader_direct_load(), request_id=request_id)
        prompt = reader_direct_build_prompt(record)
        READER_DIRECT_RUN_DIR.mkdir(parents=True, exist_ok=True)
        prompt_path = READER_DIRECT_RUN_DIR / f"{request_id}_prompt.md"
        output_path = READER_DIRECT_RUN_DIR / f"{request_id}_output.log"
        prompt_path.write_text(prompt, encoding="utf-8")
        last_path = READER_DIRECT_RUN_DIR / f"{request_id}_last_message.md"
        cmd = [
            codex_recall._codex_executable(),
            "exec",
            "-C",
            str(ROOT),
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "-s",
            "read-only",
            "--output-last-message",
            str(last_path),
            "-",
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                text=True,
                input=prompt,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=READER_DIRECT_TIMEOUT_SECONDS,
                env=codex_recall._codex_env(),
            )
            output = reader_direct_codex_output_text(proc.stdout)
            last_message = last_path.read_text(encoding="utf-8", errors="ignore") if last_path.exists() else ""
            output_path.write_text(output, encoding="utf-8")
            if proc.returncode != 0:
                snippet = clean_text((last_message or output)[-1200:]) or f"Codex 返回码：{proc.returncode}"
                reader_direct_update_record(
                    request_id,
                    {
                        "status": f"直接回答失败：{snippet}",
                        "answer_state": "failed",
                        "answer_checked": False,
                        "answer_markdown": "",
                    },
                )
                return
            answer = clean_text(last_message) or clean_text(output)
            if not answer:
                answer = "这次没有生成可显示的回答。你可以把问题换一种说法再问一次。"
            reader_direct_update_record(
                request_id,
                {
                    "status": "已回答。",
                    "answer_state": "answered",
                    "answer_checked": True,
                    "answer_markdown": answer,
                    "answer_file": str(output_path),
                },
            )
        except subprocess.TimeoutExpired as exc:
            partial = reader_direct_codex_output_text(getattr(exc, "stdout", ""))
            if partial:
                output_path.write_text(partial, encoding="utf-8")
            reader_direct_update_record(
                request_id,
                {
                    "status": "直接回答超时，请稍后再问一次。",
                    "answer_state": "failed",
                    "answer_checked": False,
                    "answer_markdown": clean_text(partial),
                },
            )
        except Exception as exc:
            reader_direct_update_record(
                request_id,
                {
                    "status": f"直接回答失败：{exc}",
                    "answer_state": "failed",
                    "answer_checked": False,
                    "answer_markdown": "",
                },
            )
    finally:
        with READER_DIRECT_LOCK:
            READER_DIRECT_ACTIVE.discard(request_id)


def reader_direct_start_generation(request_id: str) -> None:
    request_id = clean_text(request_id)
    if not request_id:
        return
    with READER_DIRECT_LOCK:
        if request_id in READER_DIRECT_ACTIVE:
            return
        READER_DIRECT_ACTIVE.add(request_id)
    thread = threading.Thread(target=reader_direct_generate_answer, args=(request_id,), daemon=True)
    thread.start()


def reader_direct_request_id(question: str, chapter_no: str = "", reader_mode: str = "question") -> str:
    payload = "reader-direct\n" + clean_text(reader_mode or "question") + "\n" + clean_text(chapter_no) + "\n" + clean_text(question)
    return "rd_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def reader_direct_load() -> dict:
    data = read_json_file(READER_DIRECT_QA_JSON, {"updated_at": "", "records": []})
    if not isinstance(data, dict):
        data = {"updated_at": "", "records": []}
    if not isinstance(data.get("records"), list):
        data["records"] = []
    return data


def reader_direct_save(data: dict) -> None:
    READER_DIRECT_QA_DIR.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json_file(READER_DIRECT_QA_JSON, data)


def reader_direct_find_record(data: dict, request_id: str = "", question: str = "", chapter_no: str = "") -> dict:
    request_id = clean_text(request_id)
    question = clean_text(question)
    chapter_no = clean_text(chapter_no)
    records = data.get("records") or []
    if request_id:
        for record in records:
            if clean_text(record.get("request_id")) == request_id:
                return record
    if question:
        exact_id = reader_direct_request_id(question, chapter_no, "question")
        for record in records:
            if clean_text(record.get("request_id")) == exact_id:
                return record
        for record in records:
            if clean_text(record.get("question")) == question and clean_text(record.get("answer_markdown")):
                return record
    return {}


def reader_direct_quick_answer(question: str, chapter_no: str = "", chapter_title: str = "", reader_mode: str = "question") -> str:
    question = clean_text(question)
    chapter_label = clean_text(chapter_title) or (f"第{chapter_no}回" if clean_text(chapter_no) else "当前回目")
    if clean_text(chapter_title) == "红楼梦工程工作台":
        return (
            f"我先按红楼解语回答这一问：**{question}**。\n\n"
            "目前先给可读答案；如果题目需要查原文、人物关系或材料池，下面工程页会继续展开依据。\n\n"
            "完整回答正在补充。"
        )
    if reader_mode == "explain":
        compact = question.replace("\n", " ").strip()
        if len(compact) <= 2:
            return (
                f"先按字解释：**{compact}**。\n\n"
                "我会优先给出读音、拼音、字义，以及它在文中的意思；如果是生僻字或古义词，会补充古今义差别。\n\n"
                f"当前位置：{chapter_label}。\n\n"
                "完整解释正在补充。"
            )
        if len(compact) <= 8:
            return (
                f"先按词语解释：**{compact}**。\n\n"
                "我会先拆关键字，再合起来解释整体意思，并补它在当前回目里的语气和作用。\n\n"
                f"当前位置：{chapter_label}。\n\n"
                "完整解释正在补充。"
            )
        return (
            "先按句段解释：\n\n"
            f"> {compact}\n\n"
            "我会先翻成白话，再解释难字难词、语气和上下文作用。\n\n"
            f"当前位置：{chapter_label}。\n\n"
            "完整解释正在补充。"
        )
    return (
        f"已收到这个随读问题：**{question}**。\n\n"
        f"当前位置：{chapter_label}。\n\n"
        "我先把问题放在本回阅读语境里，完整回答正在补充。"
    )


def reader_direct_payload(record: dict) -> dict:
    answer = clean_text(record.get("answer_markdown"))
    state = clean_text(record.get("answer_state")) or ("answered" if answer else "waiting_for_direct_answer")
    return {
        "request_id": clean_text(record.get("request_id")),
        "question": clean_text(record.get("question")),
        "chapter_no": clean_text(record.get("chapter_no")),
        "chapter_title": clean_text(record.get("chapter_title")),
        "reader_mode": clean_text(record.get("reader_mode")) or "question",
        "status": clean_text(record.get("status")) or ("已回答。" if answer else "等待回答。"),
        "answer_markdown": answer,
        "answer_checked": bool(record.get("answer_checked")) or bool(answer),
        "answer_state": state,
        "updated_at": clean_text(record.get("updated_at")),
        "store_json": str(READER_DIRECT_QA_JSON),
    }


def reader_direct_answer_api(question: str, chapter_no: str = "", chapter_title: str = "", reader_mode: str = "question") -> dict:
    question = clean_text(question)
    chapter_no = clean_text(chapter_no)
    chapter_title = clean_text(chapter_title)
    reader_mode = "explain" if clean_text(reader_mode) == "explain" else "question"
    if not question or question in DEFAULT_QUESTION_PLACEHOLDERS:
        return {
            "status": "请先输入问题。",
            "answer_state": "rejected",
            "answer_checked": False,
            "answer_markdown": "",
        }
    should_start = False
    with READER_DIRECT_LOCK:
        data = reader_direct_load()
        records = data.setdefault("records", [])
        record = reader_direct_find_record(data, request_id=reader_direct_request_id(question, chapter_no, reader_mode))
        now = datetime.now().isoformat(timespec="seconds")
        if not record:
            record = {
                "request_id": reader_direct_request_id(question, chapter_no, reader_mode),
                "question": question,
                "chapter_no": chapter_no,
                "chapter_title": chapter_title,
                "reader_mode": reader_mode,
                "status": "快速回答已显示，正在补充完整回答。",
                "answer_markdown": reader_direct_quick_answer(question, chapter_no, chapter_title, reader_mode),
                "answer_checked": True,
                "answer_state": "quick_answered",
                "created_at": now,
                "updated_at": now,
            }
            records.insert(0, record)
            should_start = True
        else:
            record["reader_mode"] = reader_mode
            if chapter_title and not clean_text(record.get("chapter_title")):
                record["chapter_title"] = chapter_title
            if chapter_no and not clean_text(record.get("chapter_no")):
                record["chapter_no"] = chapter_no
            if clean_text(record.get("answer_markdown")) and clean_text(record.get("answer_state")) == "answered":
                record["status"] = "已回答。"
                record["answer_state"] = "answered"
                record["answer_checked"] = True
            else:
                if not clean_text(record.get("answer_markdown")):
                    record["answer_markdown"] = reader_direct_quick_answer(question, chapter_no, chapter_title, reader_mode)
                record["status"] = "快速回答已显示，正在补充完整回答。"
                record["answer_state"] = "quick_answered"
                record["answer_checked"] = True
                should_start = True
            record["updated_at"] = now
        reader_direct_save(data)
        try:
            reader_direct_write_markdown_files(data)
        except Exception:
            pass
        payload = reader_direct_payload(record)
    if should_start:
        reader_direct_start_generation(payload.get("request_id", ""))
    return payload

def reader_direct_history_api(chapter_no: str = "") -> dict:
    chapter_no = clean_text(chapter_no)
    data = reader_direct_load()
    records = []
    for record in data.get("records", []):
        if not isinstance(record, dict):
            continue
        if chapter_no and clean_text(record.get("chapter_no")) != chapter_no:
            continue
        records.append({
            "request_id": clean_text(record.get("request_id")),
            "question": clean_text(record.get("question")),
            "chapter_no": clean_text(record.get("chapter_no")),
            "chapter_title": clean_text(record.get("chapter_title")),
            "reader_mode": clean_text(record.get("reader_mode")) or "question",
            "answer_markdown": clean_text(record.get("answer_markdown")),
            "answer_state": clean_text(record.get("answer_state")) or ("answered" if clean_text(record.get("answer_markdown")) else "waiting"),
            "updated_at": clean_text(record.get("updated_at")),
        })
    return {
        "ok": True,
        "chapter_no": chapter_no,
        "count": len(records),
        "records": records,
        "store_json": str(READER_DIRECT_QA_JSON),
        "all_markdown": str(READER_DIRECT_ALL_MD),
        "chapter_dir": str(READER_DIRECT_MD_DIR),
    }


def reader_direct_answer_status_api(request_id: str = "") -> dict:
    request_id = clean_text(request_id)
    should_start = False
    with READER_DIRECT_LOCK:
        data = reader_direct_load()
        records = data.get("records", [])
        record = reader_direct_find_record(data, request_id=request_id) if request_id else (records[0] if records else {})
        if not record:
            return {
                "status": "还没有随读问答记录。",
                "answer_state": "empty",
                "answer_checked": False,
                "answer_markdown": "",
                "store_json": str(READER_DIRECT_QA_JSON),
            }
        if clean_text(record.get("answer_state")) in {"waiting_for_direct_answer", "processing", "quick_answered"}:
            should_start = True
        payload = reader_direct_payload(record)
    if should_start:
        reader_direct_start_generation(payload.get("request_id", ""))
    return payload

def talk_live_reply_api(question: str, start: bool = False, wait_seconds: float = 0) -> dict:
    question = clean_text(question)
    if not question or question in DEFAULT_QUESTION_PLACEHOLDERS:
        return {}
    try:
        if start:
            payload = reader_direct_answer_api(
                question=question,
                chapter_no="",
                chapter_title="红楼梦工程工作台",
                reader_mode="question",
            )
        else:
            payload = reader_direct_answer_status_api(
                request_id=reader_direct_request_id(question, "", "question")
            )
            if clean_text(payload.get("answer_state")) == "empty":
                return {}
        request_id = clean_text(payload.get("request_id"))
        deadline = time.time() + max(0.0, float(wait_seconds or 0))
        while request_id and time.time() < deadline:
            if clean_text(payload.get("answer_state")) == "answered":
                break
            time.sleep(0.5)
            latest = reader_direct_answer_status_api(request_id=request_id)
            if clean_text(latest.get("answer_state")) != "empty":
                payload = latest
        payload["reply_role"] = "live_reply"
        return payload
    except Exception as exc:
        return {
            "status": f"实时回复暂时不可用：{exc}",
            "answer_state": "failed",
            "answer_checked": False,
            "answer_markdown": "",
            "reply_role": "live_reply",
        }


def engineering_live_reply_payload(
    question: str,
    status: str = "",
    request_id: str = "",
    queue_status: str = "",
    queue_error: str = "",
    workflow: dict | None = None,
    answer_state: str = "engineering_status",
    blocked_question: str = "",
    engineering_question: str = "",
) -> dict:
    question = clean_text(question)
    blocked_question = clean_text(blocked_question)
    display_question = strip_honglou_engineering_trigger(blocked_question or question)
    engineering_question = clean_text(engineering_question) or honglou_engineering_question(display_question or question)
    request_id = clean_text(request_id)
    status = clean_text(status)
    queue_status = clean_text(queue_status)
    queue_error = clean_text(queue_error)
    workflow = workflow if isinstance(workflow, dict) else {}
    package = clean_text(workflow.get("package"))
    summary = workflow.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    if answer_state == "blocked_by_active_processing":
        lines = [
            "这次提问没有进入红楼梦工程。",
            "",
            f"被挡住的问题：{display_question or '未记录'}",
            f"工程触发问题：{engineering_question or '未记录'}",
            f"当前占用入口的请求：`{request_id or '未记录'}`",
            f"当前工程状态：{queue_status or status or '未记录'}",
        ]
        if package:
            lines.append(f"当前工程包：`{package}`")
        if queue_error:
            lines.extend(["", f"原因：{queue_error}"])
        lines.extend(
            [
                "",
                "真正进入工程时，入口会先写入 Codex 召回队列和待回答文件，再生成或更新正式底库闭环工作流过程包。",
                "顶部红楼解语区只能显示这个工程链路的状态或最终回答，不能再用随读直答冒充工程结果。",
            ]
        )
        reply_status = "新问题未入队"
    else:
        lines = [
            "本问已经交给红楼梦工程入口。",
            "",
            f"本问：{display_question or question or '未记录'}",
            f"工程触发问题：{engineering_question or '未记录'}",
            f"请求 ID：`{request_id or '未记录'}`",
            f"队列状态：{queue_status or status or '待确认'}",
        ]
        if request_id:
            lines.append(f"工程触发词：`处理红楼梦待回答 {request_id}`")
        if package:
            lines.append(f"工程包：`{package}`")
        subquestion_count = summary.get("subquestion_count")
        review_rows = summary.get("review_rows")
        pending_rows = summary.get("pending_rows")
        usable_rows = summary.get("usable_rows")
        process_file_count = summary.get("process_file_count")
        counts = []
        if subquestion_count not in (None, ""):
            counts.append(f"问题拆解 {subquestion_count}")
        if review_rows not in (None, ""):
            counts.append(f"证据/复核行 {review_rows}")
        if usable_rows not in (None, ""):
            counts.append(f"可用材料 {usable_rows}")
        if pending_rows not in (None, ""):
            counts.append(f"待判定 {pending_rows}")
        if process_file_count not in (None, ""):
            counts.append(f"过程文件 {process_file_count}")
        if counts:
            lines.append("当前过程：" + "｜".join(str(item) for item in counts))
        if queue_error:
            lines.extend(["", f"当前提示：{queue_error}"])
        lines.extend(
            [
                "",
                "下面的问题拆解、证据页和材料池显示的是工程包里的过程材料。",
                "最终红楼解语生成后，顶部会替换为工程产出的最后答案。",
            ]
        )
        reply_status = status or queue_status or "工程状态已显示"

    return {
        "request_id": "",
        "question": display_question or blocked_question or question,
        "chapter_no": "",
        "chapter_title": "红楼梦工程工作台",
        "reader_mode": "engineering",
        "status": reply_status,
        "answer_markdown": "\n".join(lines),
        "answer_checked": True,
        "answer_state": answer_state,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "store_json": "",
        "reply_role": "engineering_status",
    }

def is_codex_final_answer_file(path: str | Path) -> bool:
    """Compatibility wrapper: validate a Codex final answer, not a local article draft."""
    try:
        validator = getattr(codex_recall, "is_valid_codex_final_answer_file", None)
        if validator:
            return bool(validator(path))
    except Exception:
        return False
    return False


def codex_request_id(question: str, task_intent: str = "", requirements: str = "") -> str:
    payload = "\n".join([clean_text(question), clean_text(task_intent), clean_text(requirements)])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def new_codex_request_id(question: str, task_intent: str = "", requirements: str = "") -> str:
    base = codex_request_id(question, task_intent, requirements)
    nonce = f"{datetime.now().isoformat(timespec='microseconds')}:{time.time_ns()}"
    return hashlib.sha1(f"{base}:{nonce}".encode("utf-8")).hexdigest()[:12]


def codex_recall_phrase(request_id: str) -> str:
    return f"处理红楼梦待回答 {clean_text(request_id)}"


def current_codex_question_record() -> dict:
    latest_json = CODEX_ANSWER_ROOT / "latest_question.json"
    data = read_json_file(latest_json, {})
    return data if isinstance(data, dict) else {}


def current_codex_request_id() -> str:
    return clean_text(current_codex_question_record().get("request_id"))


def is_placeholder_question(question: str) -> bool:
    text = clean_text(question)
    return not text or text in DEFAULT_QUESTION_PLACEHOLDERS


def strip_honglou_engineering_trigger(question: str) -> str:
    text = clean_text(question)
    if text.startswith(ENGINEERING_TRIGGER_PREFIX):
        return clean_text(text[len(ENGINEERING_TRIGGER_PREFIX) :])
    if text.startswith(ENGINEERING_TRIGGER_PHRASE):
        rest = text[len(ENGINEERING_TRIGGER_PHRASE) :].lstrip("：: \n\t")
        return clean_text(rest) or text
    return text


def honglou_engineering_question(question: str) -> str:
    text = clean_text(question)
    if not text:
        return ""
    if text.startswith(ENGINEERING_TRIGGER_PHRASE):
        return text
    return f"{ENGINEERING_TRIGGER_PREFIX}{text}"


def honglou_engineering_intent(task_intent: str) -> str:
    intent = clean_text(task_intent) or "红楼解语"
    if intent.startswith(ENGINEERING_TRIGGER_PHRASE):
        return intent
    return f"{ENGINEERING_TRIGGER_PHRASE}｜{intent}"


def codex_queue_items_raw() -> list[dict]:
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def single_queue_items_for_save(items: list[dict], preferred_request_id: str = "") -> list[dict]:
    preferred_request_id = clean_text(preferred_request_id) or current_codex_request_id()
    clean_items = [dict(item) for item in items if isinstance(item, dict) and clean_text(item.get("request_id"))]
    if preferred_request_id:
        for item in clean_items:
            if clean_text(item.get("request_id")) == preferred_request_id:
                return [item]
        return []
    clean_items.sort(key=lambda item: clean_text(item.get("updated_at")), reverse=True)
    return clean_items[:1]


def archive_queue_snapshot(items: list[dict], reason: str, keep_request_id: str = "") -> None:
    archived_items = [
        dict(item)
        for item in items
        if isinstance(item, dict)
        and clean_text(item.get("request_id"))
        and clean_text(item.get("request_id")) != clean_text(keep_request_id)
    ]
    if not archived_items:
        return
    CODEX_QUEUE_CLEANUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CODEX_QUEUE_CLEANUP_DIR / f"queue_snapshot_{stamp}.json"
    write_json_file(
        path,
        {
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "reason": clean_text(reason),
            "keep_request_id": clean_text(keep_request_id),
            "items": archived_items,
        },
    )


def archive_old_pending_files(current_request_id: str) -> None:
    current_request_id = clean_text(current_request_id)
    if not current_request_id or not CODEX_PENDING_DIR.exists():
        return
    archive_dir = CODEX_QUEUE_CLEANUP_DIR / "待回答归档"
    for path in sorted(CODEX_PENDING_DIR.glob("Q_*.md")):
        if path.stem.startswith(f"Q_{current_request_id}_"):
            continue
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / path.name
        if target.exists():
            target = archive_dir / f"{path.stem}_{int(path.stat().st_mtime)}{path.suffix}"
        try:
            path.rename(target)
        except OSError:
            continue


def active_codex_lock_item(exclude_request_id: str = "") -> dict:
    exclude_request_id = clean_text(exclude_request_id)
    recover_stale = getattr(codex_recall, "auto_recover_stale_request_lock", None)
    if callable(recover_stale):
        try:
            recover_stale()
        except Exception:
            pass
    items = codex_queue_items_raw()
    items.sort(key=lambda item: clean_text(item.get("updated_at")), reverse=True)
    for item in items:
        request_id = clean_text(item.get("request_id"))
        if not request_id or request_id == exclude_request_id:
            continue
        status = clean_text(item.get("status"))
        if status == "待最终回显稿" and _is_stale_final_wait_item(item):
            retry_count = 0
            try:
                retry_count = int(item.get("retry_count", 0))
            except (TypeError, ValueError):
                retry_count = 0
            codex_recall.upsert_item(
                {
                    "request_id": request_id,
                    "question": clean_text(item.get("question")),
                    "question_key": clean_text(item.get("question_key")),
                    "task_intent": clean_text(item.get("task_intent")),
                    "requirements": clean_text(item.get("requirements")),
                    "status": "处理失败",
                    "answer_md": "",
                    "error": "待最终回显稿缺少 workflow_package，疑似死锁，已自动转失败并释放线程锁。",
                    "error_category": "runtime",
                    "error_stage": "thread_auto_release",
                    "error_snippet": "待最终回显稿缺少 workflow_package",
                    "error_retryable": True,
                    "retry_count": retry_count + 1,
                    "processing_started_at": "",
                }
            )
            continue
        if status in ACTIVE_LOCK_STATUSES:
            answer_md = clean_text(item.get("answer_md"))
            answer_path = Path(answer_md) if answer_md else latest_codex_final_answer_for_key(
                clean_text(item.get("question_key")),
                request_id=request_id,
            )
            if answer_path and answer_path.exists() and answer_file_matches_request(answer_path, request_id):
                valid, _ = answer_file_is_valid(answer_path)
                if valid:
                    continue
            return dict(item)
    return {}


def stale_thread_payload(request_id: str, current: dict | None = None) -> dict:
    current = current or current_codex_question_record()
    current_request_id = clean_text(current.get("request_id"))
    queue_item = codex_queue_item_record(request_id=current_request_id) if current_request_id else {}
    if queue_item:
        current = {**current, **queue_item}
    return {
        "package": "",
        "question": clean_text(current.get("question")),
        "question_key": clean_text(current.get("question_key")),
        "request_id": current_request_id,
        "task_intent": clean_text(current.get("task_intent")),
        "requirements": clean_text(current.get("requirements")),
        "status": f"旧线程 {clean_text(request_id)} 已退出当前队列；当前队列只保留一个线程。",
        "talk_md": "",
        "article_md": "",
        "top_n": 0,
        "talk_markdown": "",
        "status_file": clean_text(current.get("pending_md")),
        "status_json": "",
        "created_new_package": False,
        "codex_only": True,
        "pending_md": clean_text(current.get("pending_md")),
        "answer_dir": str(CODEX_FINAL_DIR),
        "answer_state": "stale_ignored",
        "answer_signature": "",
        "answer_file": "",
        "answer_checked": False,
        "queue_status": clean_text(current.get("status")) or "旧线程已退出",
        "queue_error": "旧线程完成后不再回写当前队列；如需继续，请以当前入口重新提交。",
        "error_category": "stale_thread",
        "error_stage": "single_thread_queue",
        "error_snippet": "",
        "return_code": None,
        "error_retryable": False,
        "retry_count": current.get("retry_count", 0),
        "processing": {},
        "workflow": workflow_process_payload(current) if current else {"ready": False},
        "answer_type": clean_text(current.get("answer_type")),
        "answer_source": clean_text(current.get("answer_source")),
        "answer_quality": clean_text(current.get("answer_quality", "")),
        "poll_after_ms": 3000,
        "recall_phrase": clean_text(current.get("recall_phrase")),
        "queue_md": str(CODEX_QUEUE_MD),
        "queue_json": str(CODEX_QUEUE_JSON),
    }


def render_codex_queue_markdown(items: list[dict]) -> str:
    pending = [item for item in items if item.get("status") != "已处理"]
    processed = [item for item in items if item.get("status") == "已处理"]
    pending.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    processed.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

    def row(item: dict, done: bool = False) -> str:
        question = clean_text(item.get("question")).replace("\n", " ")[:80]
        answer = clean_text(item.get("answer_md") or "尚未回写")
        audit_note = clean_text(item.get("audit_note") or item.get("archive_note")).replace("\n", " ")[:120]
        retry_count = item.get("retry_count", 0)
        stage = clean_text(item.get("error_stage") or item.get("stage"))
        category = clean_text(item.get("error_category"))
        return_code = item.get("return_code")
        rc_text = clean_text(return_code)
        return (
            f"| {item.get('request_id', '')} | {item.get('status', '')} | {retry_count} | "
            f"{question} | `{item.get('recall_phrase', '')}` | {category or '—'} | {stage or '—'} | "
            f"{rc_text or '—'} | {item.get('pending_md', '')} | {answer} | {item.get('updated_at', '')} | {audit_note} |"
        )

    text = [
        "# 红楼梦研究台｜Codex召回队列",
        "",
        "## 当前未处理",
        "",
        "| 请求ID | 状态 | 重试 | 原始问题 | 召回口令 | 错误分类 | 阶段 | 返回码 | 待回答文件 | 答案文件 | 更新时间 | 审计备注 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    text.extend(row(item) for item in pending)
    text.extend(
        [
            "",
            "## 已处理",
            "",
            "| 请求ID | 状态 | 原始问题 | 召回口令 | 错误分类 | 阶段 | 返回码 | 待回答文件 | 答案文件 | 更新时间 | 审计备注 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    text.extend(row(item, done=True) for item in processed)
    return "\n".join(text) + "\n"


def archive_record_summary(item: dict) -> dict:
    workflow_files = item.get("workflow_files", {})
    if not isinstance(workflow_files, dict):
        workflow_files = {}
    answer_md = clean_text(item.get("answer_md"))
    pending_md = clean_text(item.get("pending_md"))
    workflow_package = clean_text(item.get("workflow_package"))
    answer_exists = bool(answer_md and Path(answer_md).exists())
    package_exists = bool(workflow_package and Path(workflow_package).exists())
    question = clean_text(item.get("question"))
    return {
        "request_id": clean_text(item.get("request_id")),
        "question": question,
        "question_short": short_text(question, 90),
        "status": clean_text(item.get("status")),
        "updated_at": clean_text(item.get("updated_at")),
        "task_intent": clean_text(item.get("task_intent")),
        "requirements": clean_text(item.get("requirements")),
        "pending_md": pending_md,
        "answer_md": answer_md,
        "answer_exists": answer_exists,
        "workflow_package": workflow_package,
        "package_exists": package_exists,
        "process_file_count": len(workflow_files),
        "answer_type": clean_text(item.get("answer_type")),
        "answer_quality": clean_text(item.get("answer_quality")),
        "audit_note": clean_text(item.get("audit_note") or item.get("archive_note")),
        "error_category": clean_text(item.get("error_category")),
        "error_stage": clean_text(item.get("error_stage")),
        "error_snippet": clean_text(item.get("error_snippet")),
        "return_code": clean_text(item.get("return_code")),
        "error_retryable": _parse_bool(item.get("error_retryable"), default=False),
        "processing_started_at": clean_text(item.get("processing_started_at")),
    }


def render_codex_archive_markdown(items: list[dict]) -> str:
    records = [archive_record_summary(item) for item in items]
    records.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    lines = [
        "# 红楼梦研究台｜问答记录总档案",
        "",
        f"更新时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "每一条记录都按请求 ID 归档：红楼解语、待回答文件、工程包和过程文件互相对应。这个文件只做人的入口，不替代工程底账。",
        "",
    ]
    for index, record in enumerate(records, start=1):
        lines.extend(
            [
                f"## {index}. {record['question_short'] or '未记录问题'}",
                "",
                f"- 请求 ID：`{record['request_id']}`",
                f"- 状态：{record['status'] or '未记录'}",
                f"- 更新时间：{record['updated_at'] or '未记录'}",
                f"- 红楼解语：{record['answer_md'] or '尚未生成'}",
                f"- 工程包：{record['workflow_package'] or '尚未生成'}",
                f"- 过程文件数：{record['process_file_count']}",
                f"- 待回答文件：{record['pending_md'] or '未记录'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_codex_archive_markdown(items: list[dict]) -> None:
    CODEX_ARCHIVE_MD.parent.mkdir(parents=True, exist_ok=True)
    CODEX_ARCHIVE_MD.write_text(render_codex_archive_markdown(items), encoding="utf-8")


def archive_records_api(limit: int = 60) -> dict:
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []
    records = [archive_record_summary(item) for item in items]
    records.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    write_codex_archive_markdown(items)
    return {
        "archive_md": str(CODEX_ARCHIVE_MD),
        "count": len(records),
        "records": records[:limit],
    }


def article_files_for_record(item: dict) -> list[dict]:
    workflow_files = item.get("workflow_files", {})
    if not isinstance(workflow_files, dict):
        workflow_files = {}
    candidates = [
        ("answer_md", "红楼解语", clean_text(item.get("answer_md")), "final"),
    ]
    files = []
    for key, label, path, kind in candidates:
        exists = bool(path and Path(path).exists())
        if not path and kind != "final":
            continue
        files.append(
            {
                "key": key,
                "label": label,
                "path": path,
                "exists": exists,
                "kind": kind,
                "excerpt": read_text_excerpt(path, limit=700) if exists and kind in {"final", "article"} else "",
            }
        )
    return files


def article_record_summary(item: dict) -> dict:
    base = archive_record_summary(item)
    workflow_files = item.get("workflow_files", {})
    if not isinstance(workflow_files, dict):
        workflow_files = {}
    ingest_keys = [
        "article_ingest_report_md",
        "article_ingest_candidate_csv",
        "article_ingest_links_csv",
        "article_ingest_identity_md",
        "article_ingest_summary_json",
    ]
    ingest_files = {
        key: clean_text(workflow_files.get(key))
        for key in ingest_keys
        if clean_text(workflow_files.get(key))
    }
    return {
        **base,
        "judgment_md": clean_text(item.get("judgment_md")),
        "article_files": article_files_for_record(item),
        "ingest_files": ingest_files,
        "ingest_ready": bool(base.get("workflow_package") and Path(base.get("workflow_package")).exists()),
        "ingest_report_exists": bool(
            ingest_files.get("article_ingest_report_md")
            and Path(ingest_files["article_ingest_report_md"]).exists()
        ),
    }


def article_records_api(limit: int = 60) -> dict:
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []
    records = [article_record_summary(item) for item in items]
    records.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    write_codex_archive_markdown(items)
    return {
        "archive_md": str(CODEX_ARCHIVE_MD),
        "count": len(records),
        "records": records[:limit],
    }


def recent_talk_api(limit: int = 12) -> dict:
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []

    def is_recallable(item: dict) -> bool:
        answer_md = clean_text(item.get("answer_md"))
        request_id = clean_text(item.get("request_id"))
        return bool(request_id and answer_md and Path(answer_md).exists())

    records = [archive_record_summary(item) for item in items if is_recallable(item)]
    records.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    latest = talk_status_api(request_id=records[0]["request_id"]) if records else {}
    return {
        "count": len(records),
        "records": records[:limit],
        "latest": latest,
        "archive_md": str(CODEX_ARCHIVE_MD),
    }


def codex_answer_ingest_preview(item: dict, package: str = "") -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    answer_md = clean_text(item.get("answer_md"))
    answer_path = Path(answer_md)
    if not request_id or not answer_path.exists():
        return {
            "article_ingest_preview": {
                "status": "红楼解语尚未生成，不能入库预检。",
                "ready": False,
            },
            "package": clean_text(package),
        }

    workflow_files = item.get("workflow_files", {})
    if not isinstance(workflow_files, dict):
        workflow_files = {}
    CODEX_INGEST_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"INGEST_{request_id}_{safe_filename_part(question, 42)}"
    report_md = CODEX_INGEST_DIR / f"{stem}_预检报告.md"
    candidate_csv = CODEX_INGEST_DIR / f"{stem}_候选行.csv"
    links_csv = CODEX_INGEST_DIR / f"{stem}_回挂清单.csv"
    identity_md = CODEX_INGEST_DIR / f"{stem}_身份卡.md"
    summary_json = CODEX_INGEST_DIR / f"{stem}_摘要.json"
    answer_text = answer_path.read_text(encoding="utf-8")
    now = datetime.now().isoformat(timespec="seconds")
    package_text = clean_text(package) or clean_text(item.get("workflow_package"))
    judgment_md = clean_text(item.get("codex_material_judgment_md")) or clean_text(workflow_files.get("codex_material_judgment_md"))
    close_reading_md = clean_text(item.get("codex_close_reading_md")) or clean_text(workflow_files.get("codex_close_reading_md"))
    final_gate = clean_text(workflow_files.get("final_reading_gate_md"))
    source_verify = clean_text(workflow_files.get("source_verify_md"))
    payload = {
        "generated_at": now,
        "status": "红楼解语入库预检已完成：只保存最终回答和追溯路径，不调用本地文章稿链。",
        "ready": True,
        "request_id": request_id,
        "question": question,
        "answer_md": answer_md,
        "workflow_package": package_text,
        "codex_material_judgment_md": judgment_md,
        "codex_close_reading_md": close_reading_md,
        "final_reading_gate_md": final_gate,
        "source_verify_md": source_verify,
        "report_md": str(report_md),
        "candidate_csv": str(candidate_csv),
        "links_csv": str(links_csv),
        "identity_md": str(identity_md),
        "summary_json": str(summary_json),
        "does_not_write_notion": True,
        "does_not_call_local_article_chain": True,
    }
    candidate_row = {
        "标题": safe_filename_part(question, 48) or "红楼解语",
        "编号": "待分配",
        "章回": "待由答案与证据确认",
        "小类": "红楼解语",
        "文章性质": "Codex最终回答",
        "内容状态": "已生成",
        "价值": "待人工确认",
        "可挖掘": "高",
        "可信度": "以材料池判定和真源核验为准",
        "来源位置": answer_md,
        "标签": "红楼梦, 红楼解语, Codex最终回答",
        "来源页URL": answer_md,
        "入库日期": now.split("T", 1)[0],
        "备注": "来源为红楼解语；回挂问题、工程包、材料池判定、精读门和真源核验。",
        "大类": "作品",
        "关联人物": "待由红楼解语和材料池确认",
        "关联出库任务": request_id,
        "关联回目": "待由证据确认",
        "生命周期状态": "待核证",
    }
    links = [
        {"回挂对象": "红楼解语", "类型": "最终回答", "目标": answer_md, "状态": "已存在", "说明": "人的阅读主入口。"},
        {"回挂对象": "工程包", "类型": "过程底账", "目标": package_text, "状态": "已记录" if package_text else "缺失", "说明": "回看完整问题流转。"},
        {"回挂对象": "Codex材料池判定", "类型": "材料判断", "目标": judgment_md, "状态": "已记录" if judgment_md else "缺失", "说明": "最终回答前的材料可用性判断。"},
        {"回挂对象": "Codex精读材料词", "类型": "材料精读", "目标": close_reading_md, "状态": "已记录" if close_reading_md else "缺失", "说明": "最终回答前的材料舍取、原文锚点和文风方向。"},
        {"回挂对象": "材料池精读门", "类型": "精读门", "目标": final_gate, "状态": "已记录" if final_gate else "缺失", "说明": "最终回答前逐条读材料的门槛。"},
        {"回挂对象": "真源核验", "类型": "原文追溯", "目标": source_verify, "状态": "已记录" if source_verify else "缺失", "说明": "原文、段落、回目和引文核验线索。"},
    ]
    write_csv(candidate_csv, [candidate_row])
    write_csv(links_csv, links)
    study_writeback = study_extension_writer.run_writeback(
        answer_md=answer_md,
        workflow_package=package_text,
        question=question,
        title=safe_filename_part(question, 48) or "红楼解语",
        kind="extension",
        approved=False,
        request_id=request_id,
        source_verify_md=source_verify,
        write_base=False,
    )
    study_closure = closure_check.check_package(study_writeback["manifest_json"])
    payload["study_extension_writeback"] = study_writeback
    payload["study_extension_closure"] = study_closure
    identity_md.write_text(
        "\n".join(
            [
                "# 红楼解语入库身份卡",
                "",
                f"生成时间：{now}",
                "",
                f"- 请求 ID：`{request_id}`",
                f"- 问题：{question}",
                f"- 红楼解语：`{answer_md}`",
                f"- 工程包：`{package_text}`",
                f"- 材料池判定：`{judgment_md}`",
                f"- Codex 精读材料词：`{close_reading_md}`",
                "",
                "## 原则",
                "",
                "本卡只保存 Codex 最终回答和追溯路径，不调用本地文章稿、论述稿或润色稿。",
            ]
        ),
        encoding="utf-8",
    )
    report_md.write_text(
        "\n".join(
            [
                "# 红楼解语入库预检报告",
                "",
                f"生成时间：{now}",
                "",
                f"状态：{payload['status']}",
                "",
                "## 问题",
                "",
                question,
                "",
                "## 红楼解语全文",
                "",
                answer_text,
                "",
                "## 回挂路径",
                "",
                f"- 红楼解语：`{answer_md}`",
                f"- 工程包：`{package_text}`",
                f"- 材料池判定：`{judgment_md}`",
                f"- Codex 精读材料词：`{close_reading_md}`",
                f"- 材料池精读门：`{final_gate}`",
                f"- 真源核验：`{source_verify}`",
            ]
        ),
        encoding="utf-8",
    )
    write_json_file(summary_json, payload)
    return {"article_ingest_preview": payload, "package": package_text}


def article_ingest_api(request_id: str = "", package: str = "", main: str = "answer") -> dict:
    request_id = clean_text(request_id)
    package = clean_text(package)
    item = codex_queue_item_record(request_id=request_id) if request_id else {}
    if not package and item:
        package = clean_text(item.get("workflow_package"))
    if not package:
        package = "latest"
    result = codex_answer_ingest_preview(item, package=package)
    payload = result.get("article_ingest_preview", {})
    if not isinstance(payload, dict):
        payload = {}
    if request_id and item:
        workflow_files = item.get("workflow_files", {})
        if not isinstance(workflow_files, dict):
            workflow_files = {}
        workflow_files.update(
            {
                "article_ingest_report_md": clean_text(payload.get("report_md")),
                "article_ingest_candidate_csv": clean_text(payload.get("candidate_csv")),
                "article_ingest_links_csv": clean_text(payload.get("links_csv")),
                "article_ingest_identity_md": clean_text(payload.get("identity_md")),
                "article_ingest_summary_json": clean_text(payload.get("summary_json")),
            }
        )
        upsert_codex_queue_item(
            {
                "request_id": request_id,
                "question": clean_text(item.get("question")),
                "question_key": clean_text(item.get("question_key")),
                "task_intent": clean_text(item.get("task_intent")),
                "requirements": clean_text(item.get("requirements")),
                "status": clean_text(item.get("status")) or "已处理",
                "pending_md": clean_text(item.get("pending_md")),
                "answer_md": clean_text(item.get("answer_md")),
                "workflow_package": clean_text(result.get("package")),
                "workflow_files": workflow_files,
                "judgment_md": clean_text(item.get("judgment_md")),
            }
        )
    triangle_sync_result: dict = {}
    if payload.get("ready"):
        try:
            sync_index = triangle_sync.run()
            triangle_sync_result = {
                "ok": True,
                "index_json": str(triangle_sync.INDEX_JSON),
                "report_md": str(triangle_sync.REPORT_MD),
                "counts": sync_index.get("counts", {}),
                "sync_stats": sync_index.get("sync_stats", {}),
            }
        except Exception as exc:
            triangle_sync_result = {"ok": False, "error": str(exc)}
    return {
        "request_id": request_id,
        "package": clean_text(result.get("package")),
        "question": clean_text(result.get("question")),
        "status": clean_text(result.get("status")),
        "article_ingest_preview": payload,
        "report_excerpt": read_text_excerpt(payload.get("report_md", ""), limit=3600),
        "identity_excerpt": read_text_excerpt(payload.get("identity_md", ""), limit=2400),
        "candidate_preview": read_csv_preview(payload.get("candidate_csv", ""), limit=3),
        "links_preview": read_csv_preview(payload.get("links_csv", ""), limit=8),
        "triangle_sync": triangle_sync_result,
    }


def upsert_codex_queue_item(item: dict) -> dict:
    CODEX_ANSWER_ROOT.mkdir(parents=True, exist_ok=True)
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    if not isinstance(data, dict):
        data = {"items": []}
    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    request_id = clean_text(item.get("request_id")) or clean_text(item.get("question_key"))
    if not request_id:
        return item
    incoming = dict(item)
    current_request_id = current_codex_request_id()
    if current_request_id and request_id != current_request_id:
        current_items = single_queue_items_for_save(raw_items, preferred_request_id=current_request_id)
        if current_items:
            archive_queue_snapshot(raw_items, "ignore_stale_local_writeback", keep_request_id=current_request_id)
            now = datetime.now().isoformat(timespec="seconds")
            payload = {"updated_at": now, "items": current_items}
            write_json_file(CODEX_QUEUE_JSON, payload)
            CODEX_QUEUE_MD.write_text(render_codex_queue_markdown(current_items), encoding="utf-8")
            write_codex_archive_markdown(current_items)
            return dict(current_items[0])
        return {
            "request_id": request_id,
            "status": "旧线程已退出",
            "error": "旧线程完成后不再回写当前队列。",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    if getattr(codex_recall, "is_request_aborted", None) and codex_recall.is_request_aborted(request_id):
        incoming_status = clean_text(incoming.get("status"))
        if incoming_status != "已终止":
            existing = next((old for old in raw_items if clean_text(old.get("request_id")) == request_id), {})
            if existing:
                return dict(existing)
            incoming = {
                **incoming,
                "status": "已终止",
                "answer_md": "",
                "error": "用户已点击停止解语；忽略后台迟到写回。",
                "error_category": "user_abort",
                "error_stage": "manual_stop",
                "error_retryable": False,
                "processing_started_at": "",
            }
    incoming_answer = clean_text(incoming.get("answer_md"))
    if incoming_answer:
        answer_stem = Path(incoming_answer).stem
        if answer_stem.startswith("A_") and not answer_stem.startswith(f"A_{request_id}_"):
            incoming["answer_md"] = ""
            if clean_text(incoming.get("status")) == "已处理":
                incoming["status"] = "待Codex处理"
            incoming["error"] = f"答案文件不属于当前请求，已拦截旧答案回显：{incoming_answer}"
    existing_match = next((existing for existing in raw_items if existing.get("request_id") == request_id), {})
    items = [existing for existing in raw_items if existing.get("request_id") != request_id]
    now = datetime.now().isoformat(timespec="seconds")
    merged = dict(existing_match)
    for key, value in incoming.items():
        if key in {"answer_md", "error", "processing_started_at", "error_snippet", "return_code"} and value in {"", None}:
            merged[key] = ""
            continue
        if value not in ("", None, []):
            merged[key] = value
    if request_id:
        merged["request_id"] = request_id
    merged["updated_at"] = now
    items.append(merged)
    archive_queue_snapshot(raw_items, "single_thread_queue_save", keep_request_id=request_id)
    items = single_queue_items_for_save(items, preferred_request_id=request_id)
    archive_old_pending_files(request_id)
    payload = {"updated_at": now, "items": items}
    write_json_file(CODEX_QUEUE_JSON, payload)
    CODEX_QUEUE_MD.write_text(render_codex_queue_markdown(items), encoding="utf-8")
    write_codex_archive_markdown(items)
    return items[0] if items else merged


def latest_codex_question_record(question_key: str = "", request_id: str = "") -> dict:
    latest_json = CODEX_ANSWER_ROOT / "latest_question.json"
    data = read_json_file(latest_json, {})
    if not isinstance(data, dict):
        return {}
    question_key = clean_text(question_key)
    request_id = clean_text(request_id)
    if request_id and data.get("request_id") != request_id:
        return {}
    if question_key and data.get("question_key") != question_key:
        return {}
    return data


def codex_queue_item_record(question_key: str = "", request_id: str = "") -> dict:
    data = read_json_file(CODEX_QUEUE_JSON, {"items": []})
    if not isinstance(data, dict):
        return {}
    items = data.get("items", [])
    if not isinstance(items, list):
        return {}
    question_key = clean_text(question_key)
    request_id = clean_text(request_id)
    if request_id:
        for item in items:
            if clean_text(item.get("request_id")) == request_id:
                return dict(item)
    if question_key:
        matches = [item for item in items if clean_text(item.get("question_key")) == question_key]
        matches.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        if matches:
            return dict(matches[0])
    return {}


def ensure_codex_processing(request_id: str = "", question_key: str = "") -> dict:
    try:
        selector = request_id or question_key or "latest"
        item = codex_recall.select_item(selector)
        status = item.get("status", "")
        item_request_id = clean_text(item.get("request_id", ""))
        item_answer_md = clean_text(item.get("answer_md", ""))
        if status == "已终止" or (
            item_request_id
            and getattr(codex_recall, "is_request_aborted", None)
            and codex_recall.is_request_aborted(item_request_id)
        ):
            return {
                "processing": False,
                "status": "已终止",
                "request_id": item_request_id,
                "reason": "用户已点击停止解语；当前线程不再自动推进。",
            }
        answer_ready = False
        if item_request_id and item_answer_md:
            answer_path = Path(item_answer_md)
            stem = answer_path.stem
            answer_ready = (
                answer_path.exists()
                and stem.startswith(f"A_{item_request_id}_")
                and is_codex_final_answer_file(answer_path)
            )
        if status == "已处理":
            if answer_ready:
                return {
                    "processing": False,
                    "status": status,
                    "request_id": item_request_id,
                    "reason": "already_processed",
                }
            # 已处理但答案文件缺失或归属不对，重入队处理。
            item = codex_recall.upsert_item(
                {
                    "request_id": item_request_id,
                    "question": clean_text(item.get("question")),
                    "question_key": clean_text(item.get("question_key")),
                    "task_intent": clean_text(item.get("task_intent")),
                    "requirements": clean_text(item.get("requirements")),
                    "status": "待Codex处理",
                    "answer_md": "",
                    "error": "已清理旧答案：仅接受 Codex 最终红楼解语文件，已重新入队处理。",
                    "processing_started_at": "",
                }
            )
            status = "待Codex处理"
        if status == "处理中":
            if codex_recall.is_stale_processing_item(item):
                item = codex_recall.revive_stale_processing_item(item)
                status = item.get("status", "")
            else:
                return {
                    "processing": True,
                    "status": status,
                    "request_id": clean_text(item.get("request_id", "")),
                    "processing_started_at": clean_text(item.get("processing_started_at", "")),
                    "reason": "already_processing",
                }
        if status in {"等待补证", "待人工复核"}:
            return {
                "processing": False,
                "status": status,
                "request_id": clean_text(item.get("request_id", "")),
                "reason": clean_text(item.get("error", "")) or status,
            }
        if status in {"处理失败", "待最终回显稿"}:
            retry_count = 0
            try:
                retry_count = int(item.get("retry_count", 0))
            except (TypeError, ValueError):
                retry_count = 0
            register_retry_reason = clean_text(item.get("error", ""))
            if status == "待最终回显稿" and getattr(codex_recall, "register_codex_target_answer", None):
                registered = codex_recall.register_codex_target_answer(item)
                if registered.get("ok"):
                    return {
                        "processing": False,
                        "status": "已处理",
                        "request_id": clean_text(item.get("request_id", "")),
                        "reason": clean_text(registered.get("reason")) or "registered_codex_target",
                        "answer_md": clean_text(registered.get("answer_md")),
                    }
                register_retry_reason = clean_text(registered.get("reason")) or register_retry_reason or status

            workflow_package = clean_text(item.get("workflow_package") or item.get("package") or item.get("package_dir"))
            has_workflow_package = bool(workflow_package and Path(workflow_package).exists() and Path(workflow_package).is_dir())
            if not has_workflow_package and getattr(codex_recall, "_workflow_package_path", None):
                try:
                    has_workflow_package = bool(codex_recall._workflow_package_path(item))
                except Exception:
                    pass

            last_update = _to_iso_datetime(clean_text(item.get("updated_at") or item.get("processing_started_at")))
            if status == "待最终回显稿" and not has_workflow_package:
                reason_no_package = register_retry_reason or "待最终回显稿缺少 workflow_package"
                if not last_update:
                    is_final_wait_stale = True
                else:
                    is_final_wait_stale = (
                        (datetime.now() - last_update).total_seconds()
                        >= max(60, int(getattr(codex_recall, "PROCESS_RETRY_INTERVAL_SECONDS", 90) * 2))
                    )
                if is_final_wait_stale:
                    item = codex_recall.upsert_item(
                        {
                            "request_id": item_request_id,
                            "question": clean_text(item.get("question")),
                            "question_key": clean_text(item.get("question_key")),
                            "task_intent": clean_text(item.get("task_intent")),
                            "requirements": clean_text(item.get("requirements")),
                            "status": "处理失败",
                            "answer_md": "",
                            "error": reason_no_package,
                            "error_category": "workflow_recover",
                            "error_stage": "final_wait_dead_package",
                            "error_snippet": reason_no_package,
                            "error_retryable": True,
                            "retry_count": retry_count + 1,
                            "processing_started_at": "",
                        }
                    )
                    return {
                        "processing": False,
                        "status": "处理失败",
                        "request_id": clean_text(item.get("request_id", "")),
                        "reason": reason_no_package,
                    }

            retry_interval = getattr(codex_recall, "PROCESS_RETRY_INTERVAL_SECONDS", 90)
            final_retry_budget = getattr(codex_recall, "PROCESS_FINAL_RETRY_BUDGET", 4)
            if (
                has_workflow_package
                and retry_count < final_retry_budget
                and (
                    last_update is None
                    or (datetime.now() - last_update).total_seconds() >= max(1, retry_interval)
                )
            ):
                started_at = datetime.now().isoformat(timespec="seconds")
                item = codex_recall.upsert_item(
                    {
                        "request_id": item_request_id,
                        "question": clean_text(item.get("question")),
                        "question_key": clean_text(item.get("question_key")),
                        "task_intent": clean_text(item.get("task_intent")),
                        "requirements": clean_text(item.get("requirements")),
                        "status": "处理中",
                        "answer_md": "",
                        "error": f"待最终回显稿重试：{clean_text(item.get('error', ''))}" if clean_text(item.get("error")) else "待最终回显稿重试",
                        "processing_started_at": started_at,
                        "retry_count": retry_count + 1,
                    }
                )
                thread = threading.Thread(target=codex_recall.process_one, args=(item,), daemon=True)
                thread.start()
                return {
                    "processing": True,
                    "status": "处理中",
                    "request_id": clean_text(item_request_id),
                    "processing_started_at": started_at,
                    "reason": "retry_final_wait",
                }

            if status == "待最终回显稿":
                return {
                    "processing": False,
                    "status": status,
                    "request_id": clean_text(item.get("request_id", "")),
                    "reason": register_retry_reason or clean_text(item.get("error", "")) or status,
                }

            if status == "处理失败" and getattr(codex_recall, "_can_retry_failed_item", None):
                if codex_recall._can_retry_failed_item(item):
                    started_at = datetime.now().isoformat(timespec="seconds")
                    item = codex_recall.upsert_item(
                        {
                            "request_id": item_request_id,
                            "question": clean_text(item.get("question")),
                            "question_key": clean_text(item.get("question_key")),
                            "task_intent": clean_text(item.get("task_intent")),
                            "requirements": clean_text(item.get("requirements")),
                            "status": "处理中",
                            "answer_md": "",
                            "error": f"失败后自动重试：{clean_text(item.get('error'))}" if clean_text(item.get('error')) else "失败后自动重试",
                            "processing_started_at": started_at,
                        }
                    )
                    thread = threading.Thread(target=codex_recall.process_one, args=(item,), daemon=True)
                    thread.start()
                    return {
                        "processing": True,
                        "status": "处理中",
                        "request_id": clean_text(item.get("request_id", "")),
                        "processing_started_at": started_at,
                        "reason": "restarted_after_fail",
                    }
            return {
                "processing": False,
                "status": status,
                "request_id": clean_text(item.get("request_id", "")),
                "reason": clean_text(item.get("error", "")) or status,
            }
        if status == "待处理" or status == "待Codex处理":
            started_at = datetime.now().isoformat(timespec="seconds")
            item = codex_recall.upsert_item(
                {
                    "request_id": item_request_id,
                    "question": clean_text(item.get("question")),
                    "question_key": clean_text(item.get("question_key")),
                    "task_intent": clean_text(item.get("task_intent")),
                    "requirements": clean_text(item.get("requirements")),
                    "status": "处理中",
                    "answer_md": clean_text(item.get("answer_md")),
                    "error": "",
                    "processing_started_at": started_at,
                }
            )
            thread = threading.Thread(target=codex_recall.process_one, args=(item,), daemon=True)
            thread.start()
            return {
                "processing": True,
                "status": "处理中",
                "request_id": clean_text(item.get("request_id", "")),
                "processing_started_at": started_at,
                "reason": "started",
            }
        # 已处理状态外兜底：把状态修正为待处理并尝试重跑一次，避免脏状态卡住
        started_at = datetime.now().isoformat(timespec="seconds")
        item = codex_recall.upsert_item(
            {
                "request_id": item_request_id,
                "question": clean_text(item.get("question")),
                "question_key": clean_text(item.get("question_key")),
                "task_intent": clean_text(item.get("task_intent")),
                "requirements": clean_text(item.get("requirements")),
                "status": "处理中",
                "answer_md": "",
                "processing_started_at": started_at,
            }
        )
        thread = threading.Thread(target=codex_recall.process_one, args=(item,), daemon=True)
        thread.start()
        return {
            "processing": True,
            "status": "处理中",
            "request_id": clean_text(item.get("request_id", "")),
            "processing_started_at": started_at,
            "reason": "started_unknown_status_retry",
        }
    except BaseException as exc:  # pragma: no cover - 外部依赖异常，直接回写失败状态
        request_id = clean_text(request_id)
        if request_id:
            codex_recall.upsert_item(
                {
                    "request_id": request_id,
                    "question_key": clean_text(question_key),
                    "status": "处理失败",
                    "error": clean_text(str(exc)),
                    "processing_started_at": "",
                }
            )
        return {
            "processing": False,
            "status": "处理失败",
            "request_id": request_id,
            "reason": clean_text(str(exc)),
        }


def search_api(query: str, limit: int) -> dict:
    if not search_index.SEARCH_DB.exists():
        search_index.build_index()
    conn = sqlite3.connect(search_index.SEARCH_DB)
    conn.row_factory = sqlite3.Row
    unified = search_index.search_with_person_query_unification(conn, query, limit=limit)
    conn.close()
    rows = unified["results"]
    return {
        "query": query,
        "limit": limit,
        "count": len(rows),
        "results": rows,
        "person_query_unification": unified["person_query_unification"],
    }


def evidence_api(question: str, entities: list[str], keywords: list[str], limit: int) -> dict:
    conn = evidence_pack.connect()
    ranked, direct_edges, chars = evidence_pack.rank_segments(conn, entities, keywords, limit)
    return {
        "question": question,
        "entities": entities,
        "keywords": keywords,
        "matched_characters": [
            {
                "key": row["character_key"],
                "name": row["name"],
                "aliases": row["aliases"],
                "identity": row["identity_label"],
            }
            for row in chars.values()
        ],
        "direct_edge_hits": len(direct_edges),
        "segments": [
            {
                "segment_no": hit.segment_no,
                "chapter_no": hit.chapter_no,
                "chapter_title": hit.chapter_title,
                "score": hit.score,
                "summary": hit.summary,
                "quote": hit.quote,
                "reasons": hit.reasons,
            }
            for hit in ranked
        ],
    }


def decompose_api(question: str, limit: int) -> dict:
    plan = decomposer.build_plan(question)
    preview = decomposer.preview_evidence(plan, limit)
    preview_by_order: dict[int, list[dict]] = {}
    for row in preview:
        preview_by_order.setdefault(int(row["subquestion_order"]), []).append(row)
    return {
        "question": question,
        "subquestion_count": len(plan),
        "subquestions": [
            {
                **item.__dict__,
                "preview": preview_by_order.get(item.order, [])[:limit],
            }
            for item in plan
        ],
    }


def research_api(question: str, limit_per_question: int, top_evidence: int, use_feedback: bool) -> dict:
    result = research_workflow.build_research_pack(
        question=question,
        limit_per_question=limit_per_question,
        top_evidence=top_evidence,
        use_feedback=use_feedback,
    )
    rows = read_csv(research_workflow.OUT_DIR / "03_证据阅读顺序.csv")
    visible_rows = rows if top_evidence <= 0 else rows[:top_evidence]
    return {
        "question": question,
        "subquestion_count": result["subquestion_count"],
        "unique_segments": result["unique_segments"],
        "role_counts": result["role_counts"],
        "feedback": result.get("feedback", feedback_optimizer.profile_status(None)),
        "outputs": {
            "overview": str(research_workflow.OUT_DIR / "01_一键研究包总览.md"),
            "question_tree": str(research_workflow.OUT_DIR / "02_问题树.md"),
            "triaged_csv": str(research_workflow.OUT_DIR / "03_证据阅读顺序.csv"),
            "outline": str(research_workflow.OUT_DIR / "04_写作提纲草案.md"),
            "cards": str(research_workflow.OUT_DIR / "06_重点证据卡片.md"),
        },
        "segments": visible_rows,
        "segment_rows_total": len(rows),
        "full_output_rule": "top_evidence <= 0 时全量返回；页面显示可以筛选，但工程底账不得省略候选。",
    }


def review_api(limit: int, decision: str) -> dict:
    if not REVIEW_CSV.exists():
        return {
            "review_csv": str(REVIEW_CSV),
            "total_rows": 0,
            "filtered_rows": 0,
            "decision_counts": {},
            "progress": review_progress([]),
            "rows": [],
        }
    all_rows = enriched_review_rows(read_csv(REVIEW_CSV))
    rows = filter_review_rows(all_rows, decision)
    return {
        "review_csv": str(REVIEW_CSV),
        "total_rows": len(all_rows),
        "filtered_rows": len(rows),
        "incomplete_rows": sum(1 for row in all_rows if row.get("missing_fields")),
        "decision_counts": review_counts(all_rows),
        "progress": review_progress(all_rows),
        "rows": rows[:limit],
    }


def latest_codex_final_answer_for_key(question_key: str, request_id: str = "") -> Path | None:
    if not CODEX_FINAL_DIR.exists():
        return None
    question_key = clean_text(question_key)
    request_id = clean_text(request_id)
    candidates = sorted(CODEX_FINAL_DIR.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    if request_id:
        exact_prefix = f"A_{request_id}_"
        for path in candidates:
            stem = path.stem
            if stem.startswith(exact_prefix) and is_codex_final_answer_file(path):
                return path
        return None
    for path in candidates:
        stem = path.stem
        if question_key and question_key in stem and is_codex_final_answer_file(path):
            return path
    return None


def answer_file_signature(path: str | Path) -> str:
    source = Path(path)
    if not source.exists():
        return ""
    digest = hashlib.sha1()
    try:
        with source.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                digest.update(chunk)
    except OSError:
        return ""
    stat = source.stat()
    return f"{digest.hexdigest()}:{stat.st_size}:{int(stat.st_mtime)}"


def answer_file_is_valid(path: str | Path) -> tuple[bool, str]:
    source = Path(path)
    if not source.exists():
        return False, "missing"
    if source.suffix != ".md":
        return False, "not_markdown"
    if not is_codex_final_answer_file(source):
        return False, "not_codex_final_answer"
    return True, ""


def answer_file_matches_request(path: str | Path, request_id: str, question_key: str = "") -> bool:
    source = Path(path)
    stem = source.stem
    request_id = clean_text(request_id)
    question_key = clean_text(question_key)
    if request_id:
        return stem.startswith(f"A_{request_id}_")
    return not question_key or question_key in stem


def latest_codex_final_answer(question: str, request_id: str = "") -> Path | None:
    return latest_codex_final_answer_for_key(safe_filename_part(question), request_id=request_id)


def register_codex_question(question: str, task_intent: str = "", requirements: str = "", request_id: str = "") -> Path:
    CODEX_ANSWER_ROOT.mkdir(parents=True, exist_ok=True)
    CODEX_PENDING_DIR.mkdir(parents=True, exist_ok=True)
    CODEX_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    display_question = strip_honglou_engineering_trigger(question)
    engineering_question = honglou_engineering_question(display_question or question)
    question_key = safe_filename_part(question)
    task_intent = honglou_engineering_intent(task_intent)
    requirements = clean_text(requirements)
    request_id = clean_text(request_id) or new_codex_request_id(question, task_intent, requirements)
    path = CODEX_PENDING_DIR / f"Q_{request_id}_{question_key}.md"
    if not path.exists():
        path.write_text(
            "\n".join(
                [
                    "# 红楼梦工程｜Codex 问题入口",
                    "",
                    f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
                    "",
                    "## 用户问题",
                    "",
                    question,
                    "",
                    "## 原始提问",
                    "",
                    display_question or question,
                    "",
                    "## 工程触发问题",
                    "",
                    engineering_question,
                    "",
                    "## 任务类型",
                    "",
                    task_intent,
                    "",
                    "## 附加要求",
                    "",
                    requirements or "无",
                    "",
                    pending_trigger_packet(question, task_intent, requirements, request_id, question_key),
                    "",
                    "## 输出约束",
                    "",
                    "- 不输出本地过程稿。",
                    "- 不把材料包、证据包、自动摘要冒充答案。",
                    "- 红楼解语区只能显示 Codex 人工智能回答。",
                    "- 问题树、拆题、证据池、材料池、候选材料卡片和二次补证计划可以显示在工程运转结果区，但不能冒充红楼解语。",
                    "- 如果讨论文章归档，只能生成建议或后续清单，不自动写回 Notion 母库。",
                    "- 如果选择出库，红楼解语必须先回应显性问题，再列必要证据。",
                    "- 红楼解语文件仍写入内部 `outputs/红楼梦Codex最终答案/最终答案/`，文件名包含本问题 key 或 request_id。",
                    "",
                    f"请求 ID：`{request_id}`",
                    f"问题 key：`{question_key}`",
                ]
            ),
            encoding="utf-8",
        )
    latest_json = CODEX_ANSWER_ROOT / "latest_question.json"
    latest_json.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "question": question,
                "display_question": display_question or question,
                "engineering_question": engineering_question,
                "question_key": question_key,
                "request_id": request_id,
                "task_intent": task_intent,
                "requirements": requirements,
                "pending_md": str(path),
                "answer_dir": str(CODEX_FINAL_DIR),
                "rule": "问题入口 -> 聚拢总图加载 -> 图内读法加载 -> 现成新编号入口门收点与穷尽补点 -> 聚拢层级放大缩小与交集路由 -> 原文裁判 -> 材料池 -> Codex 红楼解语；页面触发词和用户问题一起进入工程，过程材料只进工程运转结果区，不能冒充最终结论。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    upsert_codex_queue_item(
        {
            "request_id": request_id,
            "question": question,
            "display_question": display_question or question,
            "engineering_question": engineering_question,
            "question_key": question_key,
            "task_intent": task_intent,
            "requirements": requirements,
            "status": "待Codex处理",
            "recall_phrase": codex_recall_phrase(request_id),
            "pending_md": str(path),
            "answer_md": "",
        }
    )
    return path


def talk_api(question: str, top_n: int, task_intent: str = "", requirements: str = "") -> dict:
    question = clean_text(question)
    display_question = strip_honglou_engineering_trigger(question)
    engineering_question = honglou_engineering_question(display_question or question)
    task_intent = honglou_engineering_intent(task_intent)
    requirements = clean_text(requirements)
    if is_placeholder_question(question):
        return {
            "package": "",
            "question": question,
            "display_question": display_question,
            "engineering_question": engineering_question,
            "question_key": "",
            "request_id": "",
            "task_intent": task_intent,
            "requirements": requirements,
            "status": "未提交：请先输入一个真正的问题；空问题不会进入红楼解语队列。",
            "talk_md": "",
            "article_md": "",
            "top_n": top_n,
            "talk_markdown": "",
            "status_file": "",
            "status_json": "",
            "created_new_package": False,
            "codex_only": True,
            "pending_md": "",
            "answer_dir": str(CODEX_FINAL_DIR),
            "answer_state": "rejected",
            "answer_signature": "",
            "answer_file": "",
            "answer_checked": False,
            "queue_status": "未提交",
            "queue_error": "空问题或默认占位文本已被入口拒收。",
            "error_category": "input",
            "error_stage": "question_guard",
            "error_snippet": "",
            "return_code": None,
            "error_retryable": False,
            "retry_count": 0,
            "processing": {},
            "workflow": {"ready": False},
            "live_reply": {},
            "answer_type": "",
            "answer_source": "",
            "answer_quality": "",
            "poll_after_ms": 3000,
            "recall_phrase": "",
            "queue_md": str(CODEX_QUEUE_MD),
            "queue_json": str(CODEX_QUEUE_JSON),
        }
    question_key = safe_filename_part(question)
    request_id = new_codex_request_id(question, task_intent, requirements)
    active_item = active_codex_lock_item()
    active_request_id = clean_text(active_item.get("request_id"))
    if active_item and active_request_id != request_id:
        active_payload = talk_status_api(request_id=active_request_id)
        active_payload["status"] = "已有红楼解语正在运行；新问题没有进入队列。等待完成，或按“停止解语”后再提交。"
        active_payload["answer_state"] = "blocked_by_active_processing"
        active_payload["blocked_question"] = question
        active_payload["display_question"] = display_question or question
        active_payload["engineering_question"] = engineering_question
        active_payload["queue_error"] = (
            f"被拒收的新问题：{question}。当前仅保留正在运行的请求 {active_request_id}。"
        )
        active_payload["live_reply"] = engineering_live_reply_payload(
            question=clean_text(active_payload.get("question")),
            status=clean_text(active_payload.get("status")),
            request_id=active_request_id,
            queue_status=clean_text(active_payload.get("queue_status")),
            queue_error=clean_text(active_payload.get("queue_error")),
            workflow=active_payload.get("workflow", {}),
            answer_state="blocked_by_active_processing",
            blocked_question=question,
            engineering_question=engineering_question,
        )
        return active_payload
    if active_item and active_request_id == request_id:
        active_payload = talk_status_api(request_id=request_id)
        active_payload["status"] = "当前问题已经在红楼解语队列中；本次点击没有重复入队。"
        return active_payload

    pending_path = register_codex_question(question, task_intent=task_intent, requirements=requirements, request_id=request_id)
    final_path = latest_codex_final_answer_for_key(question_key, request_id=request_id)
    final_content = ""
    final_signature = ""
    queue_status = "已处理" if final_content else "待Codex处理"
    if final_path and final_path.exists():
        if not answer_file_matches_request(final_path, request_id=request_id, question_key=question_key):
            final_path = None
        else:
            final_content = final_path.read_text(encoding="utf-8")
            queue_status = "已处理"
            final_signature = answer_file_signature(final_path)
            valid, reason = answer_file_is_valid(final_path)
            if not valid:
                final_content = ""
                final_path = None
                final_signature = ""
                queue_status = "待Codex处理"
                upsert_codex_queue_item(
                    {
                        "request_id": request_id,
                        "question": question,
                        "display_question": display_question or question,
                        "engineering_question": engineering_question,
                        "question_key": question_key,
                        "task_intent": task_intent,
                        "requirements": requirements,
                        "status": "待Codex处理",
                        "recall_phrase": codex_recall_phrase(request_id),
                        "pending_md": str(pending_path),
                        "answer_md": "",
                        "error": f"最终答案文件校验未通过：{reason}",
                        "processing_started_at": "",
                    }
                )
    queue_item = upsert_codex_queue_item(
        {
            "request_id": request_id,
            "question": question,
            "display_question": display_question or question,
            "engineering_question": engineering_question,
            "question_key": question_key,
            "task_intent": task_intent,
            "requirements": requirements,
            "status": "已处理" if final_content else "待Codex处理",
            "recall_phrase": codex_recall_phrase(request_id),
            "pending_md": str(pending_path),
            "answer_md": str(final_path or ""),
            "processing_started_at": "",
        }
    )

    processing_info = {}
    queue_error = clean_text(queue_item.get("error", ""))
    error_category = clean_text(queue_item.get("error_category", ""))
    error_stage = clean_text(queue_item.get("error_stage", ""))
    error_snippet = clean_text(queue_item.get("error_snippet", ""))
    return_code = queue_item.get("return_code")
    status = "已读取红楼解语。" if final_content else "已登记，等待 Codex 处理；本页不会用本地过程稿冒充结论。"
    if not final_content:
        processing_info = ensure_codex_processing(request_id=request_id, question_key=question_key)
        queue_error = clean_text(processing_info.get("reason", "")) if clean_text(processing_info.get("status")) == "处理失败" else queue_error
        if clean_text(processing_info.get("error_category")):
            error_category = clean_text(processing_info.get("error_category"))
        if clean_text(processing_info.get("error_stage")):
            error_stage = clean_text(processing_info.get("error_stage"))
        if clean_text(processing_info.get("error_snippet")):
            error_snippet = clean_text(processing_info.get("error_snippet"))
        if processing_info.get("return_code") is not None:
            return_code = processing_info.get("return_code")
        if processing_info.get("status") == "处理失败":
            status = f"处理失败：{codex_error_summary(processing_info.get('reason'), error_category, error_stage, return_code, error_snippet)}"
    workflow_payload = workflow_process_payload(queue_item)
    flow_scorecard, auto_corrections = talk_flow_scorecard_payload(
        {**queue_item, "status": status},
        workflow_payload,
        final_path,
    )
    live_reply = {}
    if not final_content:
        live_reply = engineering_live_reply_payload(
            question=question,
            status=status,
            request_id=request_id,
            queue_status=queue_status,
            queue_error=queue_error,
            workflow=workflow_payload,
            engineering_question=engineering_question,
        )

    return {
        "package": "",
        "question": question,
        "display_question": display_question or question,
        "engineering_question": engineering_question,
        "question_key": question_key,
        "request_id": request_id,
        "task_intent": task_intent,
        "requirements": requirements,
        "status": status,
        "talk_md": str(final_path or ""),
        "article_md": "",
        "top_n": top_n,
        "talk_markdown": final_content,
        "status_file": str(pending_path),
        "status_json": "",
        "created_new_package": False,
        "codex_only": True,
        "pending_md": str(pending_path),
        "answer_dir": str(CODEX_FINAL_DIR),
        "answer_state": "answered" if final_content else "waiting_for_codex",
        "answer_signature": final_signature,
        "answer_file": str(final_path or ""),
        "answer_checked": bool(final_signature),
        "queue_status": queue_status,
        "queue_error": queue_error,
        "error_category": error_category,
        "error_stage": error_stage,
        "error_snippet": error_snippet,
        "return_code": return_code,
        "error_retryable": _parse_bool(queue_item.get("error_retryable"), default=False),
        "retry_count": queue_item.get("retry_count", 0),
        "processing": processing_info,
        "workflow": workflow_payload,
        "live_reply": live_reply,
        "answer_type": clean_text(queue_item.get("answer_type")),
        "answer_source": clean_text(queue_item.get("answer_source")),
        "answer_quality": clean_text(queue_item.get("answer_quality", "")),
        "poll_after_ms": 3000,
        "recall_phrase": queue_item.get("recall_phrase", ""),
        "queue_md": str(CODEX_QUEUE_MD),
        "queue_json": str(CODEX_QUEUE_JSON),
        "flow_scorecard": flow_scorecard,
        "auto_corrections": auto_corrections,
    }


def module_api_to_talk(question: str, window_name: str, requirements: str = "") -> dict:
    question = clean_text(question)
    intent = (
        f"旧模块接口收口｜当前回答窗口：{window_name}｜"
        "最高底线：本窗口只能显示 Codex 人工智能回答；"
        "旧模块入口也必须收束为问题入口、新编号入口门、对象收点与编号交集、路由门、原文复核、材料池、Codex红楼解语；"
        "红楼梦工程的问题树、证据池、材料池和工程状态可以进入工程运转结果区；"
        "但本地检索、拆题、证据召回、材料包不得冒充红楼解语。"
    )
    return talk_api(question=question, top_n=10, task_intent=intent, requirements=requirements)


def talk_status_api(question_key: str = "", request_id: str = "") -> dict:
    question_key = clean_text(question_key)
    request_id = clean_text(request_id)
    current_record = current_codex_question_record()
    current_request_id = clean_text(current_record.get("request_id"))
    recover_stale = getattr(codex_recall, "auto_recover_stale_request_lock", None)
    if callable(recover_stale):
        try:
            recover_stale()
        except Exception:
            pass
        current_record = current_codex_question_record()
        current_request_id = clean_text(current_record.get("request_id"))
    if request_id and current_request_id and request_id != current_request_id:
        return stale_thread_payload(request_id, current_record)
    latest_record = latest_codex_question_record(question_key=question_key, request_id=request_id)
    question_key = question_key or clean_text(latest_record.get("question_key"))
    request_id = request_id or clean_text(latest_record.get("request_id"))
    queue_record = codex_queue_item_record(question_key=question_key, request_id=request_id)
    if queue_record:
        merged_record = dict(queue_record)
        for key, value in latest_record.items():
            if value not in ("", None, []):
                merged_record[key] = value
        latest_record = merged_record
        question_key = question_key or clean_text(latest_record.get("question_key"))
        request_id = request_id or clean_text(latest_record.get("request_id"))
    final_path = latest_codex_final_answer_for_key(question_key, request_id=request_id)
    final_signature = ""
    final_content = ""
    queue_error = ""
    processing_info: dict = {}
    request_stopped = bool(
        request_id
        and getattr(codex_recall, "is_request_aborted", None)
        and codex_recall.is_request_aborted(request_id)
    ) or clean_text(queue_record.get("status")) == "已终止"

    if request_stopped:
        final_path = None
        queue_error = clean_text(queue_record.get("error")) or "用户已点击停止解语；最终答案迟到文件不进入当前回显。"
        processing_info = {
            "processing": False,
            "status": "已终止",
            "request_id": request_id,
            "reason": queue_error,
        }
    elif final_path and final_path.exists():
        if not answer_file_matches_request(final_path, request_id=request_id, question_key=question_key):
            mismatch_path = final_path
            final_path = None
            queue_error = f"最终答案文件归属校验失败，不属于当前请求：{mismatch_path}"
            upsert_codex_queue_item(
                {
                    "request_id": request_id,
                    "question": latest_record.get("question", ""),
                    "display_question": latest_record.get("display_question", "") or strip_honglou_engineering_trigger(latest_record.get("question", "")),
                    "engineering_question": latest_record.get("engineering_question", "") or honglou_engineering_question(latest_record.get("question", "")),
                    "question_key": question_key,
                    "task_intent": honglou_engineering_intent(latest_record.get("task_intent", "")),
                    "requirements": latest_record.get("requirements", ""),
                    "status": "待Codex处理",
                    "recall_phrase": latest_record.get("recall_phrase") or codex_recall_phrase(request_id),
                    "pending_md": latest_record.get("pending_md", ""),
                    "answer_md": "",
                    "error": queue_error,
                    "processing_started_at": "",
                }
            )
        else:
            valid, reason = answer_file_is_valid(final_path)
            if valid:
                final_signature = answer_file_signature(final_path)
                final_content = final_path.read_text(encoding="utf-8")
            else:
                final_path = None
                queue_error = f"最终答案文件校验未通过：{reason}"
                upsert_codex_queue_item(
                    {
                        "request_id": request_id,
                        "question": latest_record.get("question", ""),
                        "display_question": latest_record.get("display_question", "") or strip_honglou_engineering_trigger(latest_record.get("question", "")),
                        "engineering_question": latest_record.get("engineering_question", "") or honglou_engineering_question(latest_record.get("question", "")),
                        "question_key": question_key,
                        "task_intent": honglou_engineering_intent(latest_record.get("task_intent", "")),
                        "requirements": latest_record.get("requirements", ""),
                        "status": "待Codex处理",
                        "recall_phrase": latest_record.get("recall_phrase") or codex_recall_phrase(request_id),
                        "pending_md": latest_record.get("pending_md", ""),
                        "answer_md": "",
                        "error": queue_error,
                        "processing_started_at": "",
                    }
                )

    if not final_content and not request_stopped:
        processing_info = ensure_codex_processing(request_id=request_id, question_key=question_key)
        request_id = request_id or clean_text(processing_info.get("request_id"))
        if queue_error == "":
            processing_status = clean_text(processing_info.get("status"))
            if processing_status == "处理失败":
                queue_error = clean_text(processing_info.get("reason") or "原因未记录")

    processing_status = clean_text(processing_info.get("status"))
    if request_stopped:
        queue_status_to_write = "已终止"
    elif final_content:
        queue_status_to_write = "已处理"
    elif processing_status in {"处理失败", "等待补证", "待人工复核", "待最终回显稿", "处理中", "待Codex处理", "已终止"}:
        queue_status_to_write = processing_status
    elif queue_error:
        queue_status_to_write = "待Codex处理"
    else:
        queue_status_to_write = processing_status or clean_text(latest_record.get("status")) or "待Codex处理"
    if queue_status_to_write not in {"已处理", "待Codex处理", "处理中", "处理失败", "等待补证", "待人工复核", "待最终回显稿", "已终止"}:
        queue_status_to_write = "待Codex处理"
    processing_started_at_to_write = ""
    if not final_path:
        processing_started_at_to_write = clean_text(
            processing_info.get("processing_started_at")
            or latest_record.get("processing_started_at")
            or queue_record.get("processing_started_at")
        )
    queue_item = upsert_codex_queue_item(
        {
            "request_id": request_id,
            "question": latest_record.get("question", ""),
            "display_question": latest_record.get("display_question", "") or strip_honglou_engineering_trigger(latest_record.get("question", "")),
            "engineering_question": latest_record.get("engineering_question", "") or honglou_engineering_question(latest_record.get("question", "")),
            "question_key": question_key,
            "task_intent": honglou_engineering_intent(latest_record.get("task_intent", "")),
            "requirements": latest_record.get("requirements", ""),
            "status": queue_status_to_write,
            "recall_phrase": latest_record.get("recall_phrase") or codex_recall_phrase(request_id),
            "pending_md": latest_record.get("pending_md", ""),
            "answer_md": str(final_path or ""),
            "error": queue_error,
            "processing_started_at": processing_started_at_to_write,
        }
    )
    queue_error = clean_text(queue_item.get("error", ""))
    error_category = clean_text(queue_item.get("error_category", ""))
    error_stage = clean_text(queue_item.get("error_stage", ""))
    error_snippet = clean_text(queue_item.get("error_snippet", ""))
    return_code = queue_item.get("return_code")
    error_retryable = _parse_bool(queue_item.get("error_retryable"), default=False)
    if clean_text(processing_info.get("error_category")):
        error_category = clean_text(processing_info.get("error_category"))
    if clean_text(processing_info.get("error_stage")):
        error_stage = clean_text(processing_info.get("error_stage"))
    if clean_text(processing_info.get("error_snippet")):
        error_snippet = clean_text(processing_info.get("error_snippet"))
    if processing_info.get("return_code") is not None:
        return_code = processing_info.get("return_code")
    if processing_info.get("error_retryable") is not None:
        error_retryable = _parse_bool(processing_info.get("error_retryable"), default=False)
    workflow_payload = workflow_process_payload(queue_item)
    flow_scorecard, auto_corrections = talk_flow_scorecard_payload(
        {**queue_item, "status": queue_status_to_write},
        workflow_payload,
        final_path,
    )
    queue_status = queue_item.get("status", "")
    status = "已读取红楼解语。" if final_content else "等待红楼解语。"
    if queue_status == "处理失败":
        status = f"处理失败：{codex_error_summary(queue_error, error_category, error_stage, return_code, error_snippet)}"
    elif queue_status == "等待补证":
        status = f"等待补证：{codex_error_summary(queue_error, error_category, error_stage, return_code, error_snippet) if queue_error else 'Codex 已要求先补证，再进入红楼解语。'}"
    elif queue_status == "待最终回显稿":
        status = f"待最终回显稿：{codex_error_summary(queue_error, error_category, error_stage, return_code, error_snippet) if queue_error else '本地工程包已生成，等待 Codex 写入红楼解语。'}"
    elif queue_status == "已终止":
        status = "已停止解语。现在可以提交新问题。"
    live_reply = {}
    if not final_content and queue_status != "已终止":
        live_reply = engineering_live_reply_payload(
            question=latest_record.get("question", ""),
            status=status,
            request_id=request_id,
            queue_status=queue_status,
            queue_error=queue_error,
            workflow=workflow_payload,
            engineering_question=latest_record.get("engineering_question", ""),
        )
    return {
        "package": "",
        "question": latest_record.get("question", ""),
        "display_question": latest_record.get("display_question", "") or strip_honglou_engineering_trigger(latest_record.get("question", "")),
        "engineering_question": latest_record.get("engineering_question", "") or honglou_engineering_question(latest_record.get("question", "")),
        "question_key": question_key,
        "request_id": request_id,
        "task_intent": honglou_engineering_intent(latest_record.get("task_intent", "")),
        "requirements": latest_record.get("requirements", ""),
        "status": status,
        "talk_md": str(final_path or ""),
        "article_md": "",
        "top_n": 0,
        "talk_markdown": final_content,
        "status_file": latest_record.get("pending_md", ""),
        "status_json": "",
        "created_new_package": False,
        "codex_only": True,
        "pending_md": latest_record.get("pending_md", ""),
        "answer_dir": str(CODEX_FINAL_DIR),
        "answer_state": "answered" if final_content else ("stopped" if queue_status == "已终止" else "waiting_for_codex"),
        "answer_signature": final_signature,
        "answer_file": str(final_path or ""),
        "answer_checked": bool(final_signature),
        "queue_status": queue_status,
        "queue_error": queue_error,
        "error_category": error_category,
        "error_stage": error_stage,
        "error_snippet": error_snippet,
        "return_code": return_code,
        "error_retryable": error_retryable,
        "retry_count": queue_item.get("retry_count", 0),
        "processing": processing_info,
        "workflow": workflow_payload,
        "live_reply": live_reply,
        "answer_type": clean_text(queue_item.get("answer_type")),
        "answer_source": clean_text(queue_item.get("answer_source")),
        "answer_quality": clean_text(queue_item.get("answer_quality", "")),
        "poll_after_ms": 3000,
        "recall_phrase": queue_item.get("recall_phrase", ""),
        "queue_md": str(CODEX_QUEUE_MD),
        "queue_json": str(CODEX_QUEUE_JSON),
        "flow_scorecard": flow_scorecard,
        "auto_corrections": auto_corrections,
    }


def stop_talk_api(request_id: str = "") -> dict:
    request_id = clean_text(request_id)
    current_record = current_codex_question_record()
    current_request_id = clean_text(current_record.get("request_id"))
    if request_id and current_request_id and request_id != current_request_id:
        return {
            "stopped": False,
            "request_id": current_request_id,
            "status": f"旧线程 {request_id} 已退出当前队列；无需停止。当前队列只保留 {current_request_id or '空'}。",
            "queue_status": "旧线程已退出",
        }
    request_id = request_id or current_request_id
    item = codex_queue_item_record(request_id=request_id) if request_id else {}
    if not item and current_record:
        item = dict(current_record)
    if not request_id or not item:
        return {
            "stopped": False,
            "request_id": "",
            "status": "当前没有正在运行的红楼解语。",
            "queue_status": "",
        }
    status = clean_text(item.get("status"))
    if status == "已处理":
        return {
            "stopped": False,
            "request_id": request_id,
            "status": "当前红楼解语已经完成，不需要停止；可以直接提交新问题。",
            "queue_status": status,
        }
    if getattr(codex_recall, "mark_request_aborted", None):
        codex_recall.mark_request_aborted(request_id, "用户点击停止解语。")
    updated = upsert_codex_queue_item(
        {
            **item,
            "request_id": request_id,
            "question": clean_text(item.get("question") or current_record.get("question")),
            "question_key": clean_text(item.get("question_key") or current_record.get("question_key")),
            "task_intent": clean_text(item.get("task_intent") or current_record.get("task_intent")),
            "requirements": clean_text(item.get("requirements") or current_record.get("requirements")),
            "status": "已终止",
            "answer_md": "",
            "error": "用户点击“停止解语”；当前线程停止自动推进，迟到写回不进入当前队列。",
            "error_category": "user_abort",
            "error_stage": "manual_stop",
            "error_snippet": "",
            "return_code": "",
            "error_retryable": False,
            "processing_started_at": "",
        }
    )
    return {
        "stopped": True,
        "request_id": request_id,
        "question": clean_text(updated.get("question")),
        "status": "已停止解语。当前队列已释放，可以提交新问题。",
        "queue_status": "已终止",
        "queue_md": str(CODEX_QUEUE_MD),
        "queue_json": str(CODEX_QUEUE_JSON),
    }


def render_review_export_markdown(decision: str, rows: list[dict], progress: dict, csv_path: Path) -> str:
    lines = [
        "# 红楼梦正式底库｜复核筛选导出",
        "",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 筛选",
        "",
        f"- 复核状态：{clean_text(decision) or '全部'}",
        f"- 导出行数：{len(rows)}",
        f"- CSV：`{csv_path}`",
        "",
        "## 总体进度",
        "",
        f"- 总数：{progress.get('total_rows', 0)}",
        f"- 已判断：{progress.get('completed_rows', 0)}",
        f"- 待复核：{progress.get('pending_rows', 0)}",
        f"- 需补字段：{progress.get('incomplete_rows', 0)}",
        f"- 完成比例：{progress.get('completion_rate', 0)}%",
        "",
        "## 证据",
        "",
    ]
    if not rows:
        lines.append("当前筛选没有证据。")
        return "\n".join(lines)
    for row in rows:
        missing = f"｜缺：{row.get('missing_fields')}" if row.get("missing_fields") else ""
        lines.extend(
            [
                f"### {row.get('review_order')}｜{row.get('segment_no')}｜第{row.get('chapter_no') or ''}回｜{row.get('normalized_decision')}{missing}",
                "",
                f"- 回目：{row.get('chapter_title', '')}",
                f"- 机器角色：{row.get('machine_role', '')}",
                f"- 人工角色：{row.get('human_role', '')}",
                f"- 等级：{row.get('usable_level', '')}",
                f"- 写作用途：{row.get('writing_use', '')}",
                f"- 摘要：{row.get('summary', '')}",
                f"- 引文：{row.get('quote', '')}",
                f"- 复核问题：{row.get('review_question', '')}",
                f"- 人工备注：{row.get('human_note', '')}",
                "",
            ]
        )
    return "\n".join(lines)


def review_export_api(limit: int, decision: str) -> dict:
    if not REVIEW_CSV.exists():
        raise FileNotFoundError(f"缺少人工复核表：{REVIEW_CSV}")
    REVIEW_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows = enriched_review_rows(read_csv(REVIEW_CSV))
    rows = filter_review_rows(all_rows, decision)[:limit]
    progress = review_progress(all_rows)
    generated_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"复核筛选_{safe_filename_part(decision)}_{generated_at}"
    csv_path = REVIEW_EXPORT_DIR / f"{name}.csv"
    md_path = REVIEW_EXPORT_DIR / f"{name}.md"
    write_csv(csv_path, rows)
    md_path.write_text(render_review_export_markdown(decision, rows, progress, csv_path), encoding="utf-8")
    return {
        "decision": clean_text(decision) or "全部",
        "exported_rows": len(rows),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "progress": progress,
    }


def machine_export_file_payload(path: str | Path, text_limit: int = MACHINE_EXPORT_TEXT_LIMIT, row_limit: int = MACHINE_EXPORT_ROW_LIMIT) -> dict:
    path_text = clean_text(path)
    payload = {
        "path": path_text,
        "exists": False,
        "kind": "",
        "size": 0,
        "mtime": "",
        "content": "",
        "content_truncated": False,
        "rows": [],
        "row_count": 0,
        "error": "",
    }
    if not path_text:
        return payload
    source = Path(path_text)
    payload["kind"] = source.suffix.lstrip(".").lower() or "file"
    if not source.exists() or not source.is_file():
        return payload
    try:
        stat = source.stat()
        payload.update(
            {
                "exists": True,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
            }
        )
        if source.suffix.lower() == ".csv":
            rows = read_csv(source)
            payload["row_count"] = len(rows)
            payload["rows"] = rows[:row_limit]
            payload["content_truncated"] = len(rows) > row_limit
        else:
            text = source.read_text(encoding="utf-8", errors="ignore")
            payload["content"] = text[:text_limit]
            payload["content_truncated"] = len(text) > text_limit
    except Exception as exc:
        payload["error"] = str(exc)
    return payload


def latest_runtime_log_status(request_id: str, suffix: str = "") -> dict:
    request_id = clean_text(request_id)
    result = {"path": "", "age_seconds": None, "size": 0, "interrupted": False}
    if not request_id:
        return result
    run_dir = CODEX_ANSWER_ROOT / "Codex运行记录"
    if not run_dir.exists():
        return result
    pattern = f"{request_id}{suffix}*" if suffix else f"{request_id}*"
    candidates = sorted(run_dir.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        return result
    latest = candidates[0]
    result["path"] = str(latest)
    try:
        stat = latest.stat()
        result["age_seconds"] = int(max(0, time.time() - stat.st_mtime))
        result["size"] = stat.st_size
        tail = latest.read_text(encoding="utf-8", errors="ignore")[-6000:]
        result["interrupted"] = "turn interrupted" in tail or "interrupted" in tail.lower()
    except OSError:
        pass
    return result


def score_item(stage: str, score: int, status: str, evidence: str, problem: str, next_action: str) -> dict:
    return {
        "stage": stage,
        "score": max(0, min(10, int(score))),
        "status": status,
        "evidence": evidence,
        "problem": problem,
        "next_action": next_action,
    }


def machine_export_scorecard(record: dict, workflow: dict, final_answer: dict, nodes: list[dict]) -> dict:
    request_id = clean_text(record.get("request_id"))
    queue_status = clean_text(record.get("status"))
    workflow_files = workflow.get("files", {}) if isinstance(workflow.get("files"), dict) else {}
    workflow_summary = workflow.get("summary", {}) if isinstance(workflow.get("summary"), dict) else {}
    node_keys = {clean_text(node.get("key")) for node in nodes}
    package_path = Path(clean_text(workflow.get("package")))
    pending_path = Path(clean_text(record.get("pending_md")))
    query_strategy = record.get("query_strategy", {})
    if not isinstance(query_strategy, dict):
        query_strategy = {}
    scorecard = []

    scorecard.append(
        score_item(
            "接题入队",
            9 if request_id and pending_path.exists() else 6 if request_id else 0,
            "通过" if request_id and pending_path.exists() else "部分通过" if request_id else "缺失",
            f"request_id={request_id}；pending_md={pending_path if pending_path else ''}",
            "" if request_id and pending_path.exists() else "请求登记不完整或待回答文件未落盘。",
            "保持入队记录，等待后续门继续写回。",
        )
    )

    strategy_ready = bool(query_strategy.get("source_order") and query_strategy.get("preferred_libraries"))
    scorecard.append(
        score_item(
            "查询词路",
            9 if strategy_ready else 6 if query_strategy or "query_strategy" in node_keys else 0,
            "通过" if strategy_ready else "部分通过" if query_strategy or "query_strategy" in node_keys else "缺失",
            clean_text(query_strategy.get("source_order")) or "见导出节点：Codex 查询词路",
            "" if strategy_ready else "策略字段不完整，后续机器比较只能看摘要。",
            "保留执行词、优先库、查证顺序和排除规则。",
        )
    )

    review_rows = int(workflow_summary.get("review_rows") or 0)
    package_ready = package_path.exists() and package_path.is_dir()
    scorecard.append(
        score_item(
            "本地工程出包",
            9 if package_ready and review_rows else 7 if package_ready else 0,
            "通过" if package_ready and review_rows else "部分通过" if package_ready else "缺失",
            f"package={package_path if package_ready else ''}；review_rows={review_rows}",
            "候选规模较大，需要后续材料判定控噪。" if review_rows > 500 else "",
            "进入过程判别和材料池判定，不把候选长表直接当答案。",
        )
    )

    process_md = clean_text(record.get("codex_process_judgment_md") or workflow_files.get("codex_process_judgment_md"))
    process_log = latest_runtime_log_status(request_id, "_pass1_process_judgment")
    process_problem = ""
    process_score = 8 if process_md and Path(process_md).exists() else 5 if process_log.get("path") else 0
    process_status = "通过" if process_md and Path(process_md).exists() else "运行中/待收口" if process_log.get("path") else "缺失"
    if queue_status == "处理中" and process_log.get("age_seconds") is not None and process_log["age_seconds"] > CODEX_PROCESSING_TTL_SECONDS:
        process_score = min(process_score, 3)
        process_status = "疑似卡住"
        process_problem = f"队列仍为处理中，但过程判别日志 {process_log['age_seconds']} 秒未更新。"
    if process_log.get("interrupted"):
        process_score = min(process_score, 3)
        process_status = "疑似中断"
        process_problem = "过程判别日志尾部出现 interrupted，需要重新收口或重试。"
    scorecard.append(
        score_item(
            "全流程过程判别",
            process_score,
            process_status,
            process_md or process_log.get("path", ""),
            process_problem,
            "若未自动收口，应重新触发该请求的过程判别或让队列过期后重入。",
        )
    )

    material_md = clean_text(record.get("codex_material_judgment_md") or workflow_files.get("codex_material_judgment_md"))
    scorecard.append(
        score_item(
            "材料池判定",
            9 if material_md and Path(material_md).exists() else 0,
            "通过" if material_md and Path(material_md).exists() else "未进入",
            material_md,
            "" if material_md and Path(material_md).exists() else "尚未看到 Codex 材料池判定文件。",
            "过程判别通过后进入，逐条决定主证、背景、噪音、需补证。",
        )
    )

    close_md = clean_text(record.get("codex_close_reading_md") or workflow_files.get("codex_close_reading_md"))
    scorecard.append(
        score_item(
            "精读材料词",
            9 if close_md and Path(close_md).exists() else 0,
            "通过" if close_md and Path(close_md).exists() else "未进入",
            close_md,
            "" if close_md and Path(close_md).exists() else "尚未看到 Codex 精读材料词文件。",
            "材料池判定后提炼原文支点和最终回答骨架。",
        )
    )

    final_exists = bool(final_answer.get("exists"))
    scorecard.append(
        score_item(
            "最终红楼解语",
            9 if final_exists else 0,
            "通过" if final_exists else "未生成",
            clean_text(final_answer.get("path")),
            "" if final_exists else "最终答案文件尚未写出。",
            "最终答案生成后再导出一次机器包，形成完整质量样本。",
        )
    )

    node_count = len(nodes)
    export_score = 9 if final_exists and node_count >= 18 else 6 if node_count >= 8 else 4 if node_count else 0
    scorecard.append(
        score_item(
            "机器分析导出完整度",
            export_score,
            "完整" if export_score >= 8 else "早期快照" if export_score else "缺失",
            f"node_count={node_count}",
            "" if export_score >= 8 else "当前导出还不是最终质量包，只能分析过程早期状态。",
            "等最终答案、材料判定和精读文件出现后再次导出。",
        )
    )

    scores = [item["score"] for item in scorecard]
    overall = round(sum(scores) / len(scores), 1) if scores else 0.0
    blocking = [item for item in scorecard if item["score"] <= 3]
    return {
        "overall_score": overall,
        "max_score": 10,
        "blocking_count": len(blocking),
        "blocking_stages": [item["stage"] for item in blocking],
        "items": scorecard,
    }


def _workflow_sections_to_nodes(workflow: dict) -> list[dict]:
    sections = workflow.get("sections", [])
    if not isinstance(sections, list):
        return []
    nodes = []
    for index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        nodes.append(
            {
                "order": index,
                "key": clean_text(section.get("key", "")),
                "title": clean_text(section.get("title", "")),
                "description": clean_text(section.get("description", "")),
                "excerpt": clean_text(section.get("excerpt", "")),
                "file": {
                    "path": clean_text(section.get("path", "")),
                },
            }
        )
    return nodes


def talk_flow_scorecard_payload(record: dict, workflow: dict, final_path: str | Path | None = None) -> tuple[dict, list[dict]]:
    final_path = Path(final_path) if final_path else None
    record_request_id = clean_text(record.get("request_id"))
    question_key = clean_text(record.get("question_key"))
    if final_path is None:
        candidate = latest_codex_final_answer_for_key(question_key, request_id=record_request_id)
        if candidate and answer_file_matches_request(candidate, request_id=record_request_id, question_key=question_key):
            final_path = candidate
    if final_path is not None and not final_path.exists():
        final_path = None
    final_payload = {
        "exists": bool(final_path),
        "path": str(final_path or ""),
    }
    nodes = _workflow_sections_to_nodes(workflow)
    scorecard = machine_export_scorecard(record, workflow, final_payload, nodes)
    auto_corrections = machine_export_auto_corrections(scorecard)
    return scorecard, auto_corrections


def machine_export_auto_corrections(scorecard: dict) -> list[dict]:
    corrections = []
    for item in scorecard.get("items", []):
        stage = clean_text(item.get("stage"))
        score = int(item.get("score") or 0)
        problem = clean_text(item.get("problem"))
        if score >= 8:
            continue
        if stage == "全流程过程判别":
            corrections.append(
                {
                    "stage": stage,
                    "severity": "high" if score <= 3 else "medium",
                    "diagnosis": problem or "过程判别没有稳定收口。",
                    "suggestion": "若日志中断或长时间未更新，应把请求从处理中释放出来，重新进入过程判别；重试时继续强调 human_decision=待复核、usable_rows=0 不阻断材料池判定。",
                    "safe_auto_action": "生成重试/收口建议，不自动改队列状态。",
                }
            )
        elif stage == "材料池判定":
            corrections.append(
                {
                    "stage": stage,
                    "severity": "high" if score == 0 else "medium",
                    "diagnosis": problem or "材料池判定缺失。",
                    "suggestion": "过程判别通过后必须生成 Codex 材料池判定文件，把候选材料分成主证、背景、不可用、需补证。",
                    "safe_auto_action": "在导出包中标记为下一门必跑节点。",
                }
            )
        elif stage == "精读材料词":
            corrections.append(
                {
                    "stage": stage,
                    "severity": "medium",
                    "diagnosis": problem or "精读材料词缺失。",
                    "suggestion": "材料池判定后先提炼原文支点和舍弃理由，再写最终红楼解语。",
                    "safe_auto_action": "在导出包中要求最终答案前补齐精读材料词。",
                }
            )
        elif stage == "最终红楼解语":
            corrections.append(
                {
                    "stage": stage,
                    "severity": "high" if score == 0 else "medium",
                    "diagnosis": problem or "最终答案未生成。",
                    "suggestion": "只有完成材料判定和精读后，才写入红楼解语目标稿位或最终答案目录。",
                    "safe_auto_action": "提醒再次轮询或重试，不用过程稿冒充最终答案。",
                }
            )
        elif stage == "机器分析导出完整度":
            corrections.append(
                {
                    "stage": stage,
                    "severity": "low",
                    "diagnosis": problem or "导出包还不是完整质量样本。",
                    "suggestion": "最终答案生成后再次一键导出，形成可比较的完整机器质量包。",
                    "safe_auto_action": "保留本次早期快照，并提示后续复导。",
                }
            )
        else:
            corrections.append(
                {
                    "stage": stage,
                    "severity": "medium" if score < 6 else "low",
                    "diagnosis": problem or "该节点分数偏低。",
                    "suggestion": clean_text(item.get("next_action")) or "复查该节点来源链和下一门入口。",
                    "safe_auto_action": "写入导出包作为经验候选。",
                }
            )
    return corrections


def render_machine_export_markdown(payload: dict) -> str:
    request = payload.get("request", {})
    final_answer = payload.get("final_answer", {})
    nodes = payload.get("nodes", [])
    scorecard = payload.get("flow_scorecard", {})
    corrections = payload.get("auto_corrections", [])
    lines = [
        "# 红楼梦工程｜机器分析导出包",
        "",
        f"生成时间：{payload.get('generated_at', '')}",
        "",
        "## 用途",
        "",
        payload.get("purpose", ""),
        "",
        "## 请求",
        "",
        f"- 请求 ID：`{request.get('request_id', '')}`",
        f"- 问题 key：`{request.get('question_key', '')}`",
        f"- 问题：{request.get('question', '')}",
        f"- 状态：{request.get('status', '')}",
        f"- 工程包：`{request.get('workflow_package', '')}`",
        "",
        "## 本问一问一答",
        "",
        "### 问",
        "",
        request.get("question", "") or "未记录问题。",
        "",
        "### 红楼解语",
        "",
    ]
    qa_export = payload.get("qa_export", {})
    if qa_export.get("answer"):
        lines.extend([qa_export.get("answer", ""), ""])
    else:
        lines.extend(["尚未写回红楼解语。", ""])
    lines.extend(
        [
        "## 机器比较重点",
        "",
        ]
    )
    for item in payload.get("quality_compare_focus", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 流程评分卡",
            "",
            f"- 总分：{scorecard.get('overall_score', 0)} / {scorecard.get('max_score', 10)}",
            f"- 阻断节点数：{scorecard.get('blocking_count', 0)}",
            f"- 阻断节点：{'、'.join(scorecard.get('blocking_stages', [])) or '无'}",
            "",
            "| 步骤 | 分数 | 状态 | 问题 | 下一步 |",
            "|---|---:|---|---|---|",
        ]
    )
    for item in scorecard.get("items", []):
        lines.append(
            f"| {item.get('stage', '')} | {item.get('score', 0)} | {item.get('status', '')} | {item.get('problem', '') or '无'} | {item.get('next_action', '')} |"
        )
    lines.extend(["", "## 自动矫正建议", ""])
    if corrections:
        for item in corrections:
            lines.extend(
                [
                    f"### {item.get('stage', '')}",
                    "",
                    f"- 严重度：{item.get('severity', '')}",
                    f"- 诊断：{item.get('diagnosis', '')}",
                    f"- 建议：{item.get('suggestion', '')}",
                    f"- 安全自动动作：{item.get('safe_auto_action', '')}",
                    "",
                ]
            )
    else:
        lines.append("本次没有发现需要自动矫正的流程问题。")
    lines.extend(
        [
            "",
            "## 最终红楼解语",
            "",
            f"- 文件：`{final_answer.get('path', '')}`",
            f"- 存在：{final_answer.get('exists')}",
            f"- 截断：{final_answer.get('content_truncated')}",
            "",
        ]
    )
    if final_answer.get("content"):
        lines.extend([final_answer.get("content", ""), ""])
    lines.extend(["## 过程节点", ""])
    for node in nodes:
        file_info = node.get("file", {})
        lines.extend(
            [
                f"### {node.get('order')}. {node.get('title')}",
                "",
                f"- key：`{node.get('key', '')}`",
                f"- 作用：{node.get('description', '')}",
                f"- 路径：`{file_info.get('path', '')}`",
                f"- 类型：{file_info.get('kind', '')}",
                f"- 截断：{file_info.get('content_truncated')}",
                "",
            ]
        )
        if file_info.get("content"):
            lines.extend([file_info.get("content", ""), ""])
        elif file_info.get("rows"):
            lines.extend(
                [
                    "```json",
                    json.dumps(file_info.get("rows", []), ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        elif node.get("excerpt"):
            lines.extend([node.get("excerpt", ""), ""])
        else:
            lines.append("此节点没有可导出的正文或表格预览。\n")
    return "\n".join(lines).strip() + "\n"


def talk_machine_export_api(question_key: str = "", request_id: str = "") -> dict:
    question_key = clean_text(question_key)
    request_id = clean_text(request_id)
    latest_record = latest_codex_question_record(question_key=question_key, request_id=request_id)
    queue_record = codex_queue_item_record(question_key=question_key, request_id=request_id)
    if not latest_record and not queue_record and not request_id and not question_key:
        latest_record = latest_codex_question_record()
        request_id = clean_text(latest_record.get("request_id"))
        question_key = clean_text(latest_record.get("question_key"))
        queue_record = codex_queue_item_record(question_key=question_key, request_id=request_id)
    record = dict(queue_record)
    for key, value in latest_record.items():
        if value not in ("", None, []):
            record[key] = value
    request_id = request_id or clean_text(record.get("request_id"))
    question_key = question_key or clean_text(record.get("question_key"))
    if not record and not request_id and not question_key:
        raise ValueError("还没有可导出的红楼解语请求。")

    final_path = latest_codex_final_answer_for_key(question_key, request_id=request_id)
    answer_path = Path(clean_text(record.get("answer_md")))
    if not final_path and clean_text(answer_path) and answer_path.exists() and answer_path.is_file():
        final_path = answer_path
    if final_path:
        record["answer_md"] = str(final_path)

    workflow = workflow_process_payload(record)
    generated_at = datetime.now().isoformat(timespec="seconds")
    safe_name = safe_filename_part(request_id or question_key or record.get("question", ""), limit=48)
    stem = f"机器分析包_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    CODEX_MACHINE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = CODEX_MACHINE_EXPORT_DIR / f"{stem}.json"
    md_path = CODEX_MACHINE_EXPORT_DIR / f"{stem}.md"

    nodes = []
    for index, section in enumerate(workflow.get("sections", []), start=1):
        section_path = clean_text(section.get("path"))
        file_payload = machine_export_file_payload(section_path)
        if not section_path:
            file_payload.update(
                {
                    "kind": "synthetic",
                    "content": clean_text(section.get("excerpt")),
                    "exists": bool(clean_text(section.get("excerpt"))),
                }
            )
        elif not file_payload.get("content") and section.get("excerpt"):
            file_payload["content"] = clean_text(section.get("excerpt"))
        if not file_payload.get("rows") and section.get("rows"):
            file_payload["rows"] = section.get("rows", [])
            file_payload["row_count"] = len(section.get("rows", []))
        nodes.append(
            {
                "order": index,
                "key": section.get("key", ""),
                "title": section.get("title", ""),
                "description": section.get("description", ""),
                "excerpt": section.get("excerpt", ""),
                "file": file_payload,
            }
        )

    final_answer_payload = machine_export_file_payload(final_path or "")
    question_text = clean_text(record.get("question"))
    qa_export = {
        "question": question_text,
        "answer": clean_text(final_answer_payload.get("content")),
        "answer_md": clean_text(record.get("answer_md")),
        "request_id": request_id,
        "question_key": question_key,
    }

    payload = {
        "schema": "honglou-machine-export-v1",
        "purpose": "导出当前这一问的一问一答、最终红楼解语、材料池、过程判别、补证计划、真源核验和触发词入口。",
        "generated_at": generated_at,
        "quality_compare_focus": [
            "最终红楼解语是否正面回答用户显性问题。",
            "答案使用的原文支点是否能回到材料池、复核表和真源核验。",
            "过程判别是否说明关键词、库线、原文复核和补证策略为什么有效。",
            "材料池是否区分主证、语境、对照、反证、风险和待核。",
            "补证卡和下一轮任务是否指出了证据缺口，而不是硬写结论。",
            "工程入口触发词和 Codex 查询词路是否和最终答案保持一致。",
        ],
        "request": {
            "request_id": request_id,
            "question_key": question_key,
            "question": clean_text(record.get("question")),
            "task_intent": clean_text(record.get("task_intent")),
            "requirements": clean_text(record.get("requirements")),
            "status": clean_text(record.get("status")),
            "answer_md": clean_text(record.get("answer_md")),
            "pending_md": clean_text(record.get("pending_md")),
            "workflow_package": clean_text(record.get("workflow_package")),
        },
        "workflow_summary": workflow.get("summary", {}),
        "workflow_files": workflow.get("files", {}),
        "qa_export": qa_export,
        "final_answer": final_answer_payload,
        "nodes": nodes,
        "node_count": len(nodes),
    }
    payload["flow_scorecard"] = machine_export_scorecard(record, workflow, payload["final_answer"], nodes)
    payload["auto_corrections"] = machine_export_auto_corrections(payload["flow_scorecard"])
    write_json_file(json_path, payload)
    md_path.write_text(render_machine_export_markdown(payload), encoding="utf-8")
    return {
        "status": "已导出本问工程包。",
        "request_id": request_id,
        "question_key": question_key,
        "node_count": len(nodes),
        "export_dir": str(CODEX_MACHINE_EXPORT_DIR),
        "json": str(json_path),
        "markdown": str(md_path),
        "purpose": payload["purpose"],
        "qa_export": payload["qa_export"],
        "flow_scorecard": payload["flow_scorecard"],
        "auto_corrections": payload["auto_corrections"],
    }


def talk_continuous_export_api(question_key: str = "", request_id: str = "") -> dict:
    export_payload = talk_machine_export_api(question_key=question_key, request_id=request_id)
    qa = export_payload.get("qa_export", {})
    generated_at = datetime.now().isoformat(timespec="seconds")
    CODEX_CONTINUOUS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    entry_no = 1
    if CODEX_CONTINUOUS_EXPORT_JSONL.exists():
        entry_no = sum(1 for line in CODEX_CONTINUOUS_EXPORT_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()) + 1

    if not CODEX_CONTINUOUS_EXPORT_MD.exists():
        CODEX_CONTINUOUS_EXPORT_MD.write_text(
            "\n".join(
                [
                    "# 红楼梦工程｜当前连续导出",
                    "",
                    "这个页面用于连续问题包：每次点击“连续导出”，都会把当前这一问追加到最下面。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    question = clean_text(qa.get("question")) or "未记录问题。"
    answer = clean_text(qa.get("answer")) or "尚未写回红楼解语。"
    section_lines = [
        "",
        f"## {entry_no}. {generated_at}｜{export_payload.get('request_id', '')}",
        "",
        "### 问",
        "",
        question,
        "",
        "### 红楼解语",
        "",
        answer,
        "",
        "### 本问工程包",
        "",
        f"- Markdown：`{export_payload.get('markdown', '')}`",
        f"- JSON：`{export_payload.get('json', '')}`",
        f"- 请求 ID：`{export_payload.get('request_id', '')}`",
        f"- 问题 key：`{export_payload.get('question_key', '')}`",
        "",
    ]
    with CODEX_CONTINUOUS_EXPORT_MD.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(section_lines))

    entry = {
        "entry_no": entry_no,
        "generated_at": generated_at,
        "request_id": export_payload.get("request_id", ""),
        "question_key": export_payload.get("question_key", ""),
        "question": question,
        "answer_md": clean_text(qa.get("answer_md")),
        "single_export_markdown": export_payload.get("markdown", ""),
        "single_export_json": export_payload.get("json", ""),
        "continuous_markdown": str(CODEX_CONTINUOUS_EXPORT_MD),
    }
    with CODEX_CONTINUOUS_EXPORT_JSONL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    export_payload.update(
        {
            "status": "已连续导出。",
            "continuous": True,
            "continuous_entry_no": entry_no,
            "continuous_markdown": str(CODEX_CONTINUOUS_EXPORT_MD),
            "continuous_jsonl": str(CODEX_CONTINUOUS_EXPORT_JSONL),
        }
    )
    return export_payload


def export_history_api(limit: int = 30) -> dict:
    limit = max(1, min(int(limit or 30), 80))
    records = []
    if CODEX_CONTINUOUS_EXPORT_MD.exists():
        records.append(
            {
                "kind": "continuous",
                "title": "当前连续导出",
                "markdown": str(CODEX_CONTINUOUS_EXPORT_MD),
                "json": str(CODEX_CONTINUOUS_EXPORT_JSONL) if CODEX_CONTINUOUS_EXPORT_JSONL.exists() else "",
                "updated_at": datetime.fromtimestamp(CODEX_CONTINUOUS_EXPORT_MD.stat().st_mtime).isoformat(timespec="seconds"),
                "excerpt": read_text_excerpt(CODEX_CONTINUOUS_EXPORT_MD, limit=5200),
            }
        )
    if CODEX_MACHINE_EXPORT_DIR.exists():
        files = sorted(
            [path for path in CODEX_MACHINE_EXPORT_DIR.glob("机器分析包_*.md") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in files[:limit]:
            json_path = path.with_suffix(".json")
            records.append(
                {
                    "kind": "single",
                    "title": path.stem,
                    "markdown": str(path),
                    "json": str(json_path) if json_path.exists() else "",
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "excerpt": read_text_excerpt(path, limit=4200),
                }
            )
    return {
        "status": f"已读取 {len(records[:limit])} 条导出记录。",
        "export_dir": str(CODEX_MACHINE_EXPORT_DIR),
        "continuous_markdown": str(CODEX_CONTINUOUS_EXPORT_MD),
        "records": records[:limit],
    }


def segment_context_api(segment_no: str, window: int) -> dict:
    segment_no = clean_text(segment_no)
    if not segment_no:
        raise ValueError("缺少 segment_no")
    conn = evidence_pack.connect()
    try:
        target = conn.execute(
            """
            SELECT segment_no, chapter_no, chapter_label, segment_order, summary, quote,
                   scene_place, time_point, function_tags, note_dimension
            FROM segments
            WHERE segment_no = ?
            """,
            (segment_no,),
        ).fetchone()
        if target is None:
            raise ValueError(f"没有找到段落：{segment_no}")
        chapter_no = target["chapter_no"]
        segment_order = target["segment_order"]
        if segment_order is None:
            rows = conn.execute(
                """
                SELECT segment_no, chapter_no, chapter_label, segment_order, summary, quote,
                       scene_place, time_point, function_tags, note_dimension
                FROM segments
                WHERE chapter_no = ?
                ORDER BY segment_order, segment_no
                LIMIT ?
                """,
                (chapter_no, max(1, window * 2 + 1)),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT segment_no, chapter_no, chapter_label, segment_order, summary, quote,
                       scene_place, time_point, function_tags, note_dimension
                FROM segments
                WHERE chapter_no = ?
                  AND segment_order BETWEEN ? AND ?
                ORDER BY segment_order, segment_no
                """,
                (chapter_no, max(0, int(segment_order) - window), int(segment_order) + window),
            ).fetchall()
    finally:
        conn.close()
    return {
        "segment_no": segment_no,
        "window": window,
        "target": dict(target),
        "context": [{**dict(row), "is_current": row["segment_no"] == segment_no} for row in rows],
    }


def update_review_row(review_csv: Path, payload: dict, rebuild: bool = True) -> dict:
    if not review_csv.exists():
        raise FileNotFoundError(f"缺少人工复核表：{review_csv}")
    rows = read_csv(review_csv)
    review_order = clean_text(payload.get("review_order"))
    segment_no = clean_text(payload.get("segment_no"))
    if not review_order and not segment_no:
        raise ValueError("缺少 review_order 或 segment_no")

    matched = None
    for row in rows:
        if review_order and clean_text(row.get("review_order")) == review_order:
            matched = row
            break
        if segment_no and clean_text(row.get("segment_no")) == segment_no:
            matched = row
            break
    if matched is None:
        raise ValueError(f"没有找到复核行：{review_order or segment_no}")

    for field in REVIEW_UPDATE_FIELDS:
        if field in payload:
            matched[field] = clean_text(payload.get(field))
    write_csv(review_csv, rows)

    enriched = enriched_review_rows(rows)
    updated = next(
        row
        for row in enriched
        if (review_order and clean_text(row.get("review_order")) == review_order)
        or (segment_no and clean_text(row.get("segment_no")) == segment_no)
    )
    result = {
        "review_csv": str(review_csv),
        "updated": updated,
        "decision_counts": review_counts(enriched),
    }
    if rebuild:
        result["readback"] = review_readback.build_readback(review_csv, clean_text(payload.get("question")), review_readback.OUT_DIR)
        result["feedback"] = feedback_optimizer.build_feedback_profile(review_csv, feedback_optimizer.OUT_DIR)
    return result


def update_review_rows(review_csv: Path, payloads: list[dict], rebuild: bool = True) -> dict:
    if not review_csv.exists():
        raise FileNotFoundError(f"缺少人工复核表：{review_csv}")
    if not payloads:
        raise ValueError("没有需要保存的复核行")
    rows = read_csv(review_csv)
    updated_keys = []
    question = ""

    for payload in payloads:
        review_order = clean_text(payload.get("review_order"))
        segment_no = clean_text(payload.get("segment_no"))
        if not review_order and not segment_no:
            raise ValueError("缺少 review_order 或 segment_no")
        question = question or clean_text(payload.get("question"))

        matched = None
        for row in rows:
            if review_order and clean_text(row.get("review_order")) == review_order:
                matched = row
                break
            if segment_no and clean_text(row.get("segment_no")) == segment_no:
                matched = row
                break
        if matched is None:
            raise ValueError(f"没有找到复核行：{review_order or segment_no}")

        for field in REVIEW_UPDATE_FIELDS:
            if field in payload:
                matched[field] = clean_text(payload.get(field))
        updated_keys.append((review_order, segment_no))

    write_csv(review_csv, rows)
    enriched = enriched_review_rows(rows)
    updated_rows = []
    for review_order, segment_no in updated_keys:
        for row in enriched:
            if (review_order and clean_text(row.get("review_order")) == review_order) or (
                segment_no and clean_text(row.get("segment_no")) == segment_no
            ):
                updated_rows.append(row)
                break

    result = {
        "review_csv": str(review_csv),
        "updated_count": len(updated_rows),
        "updated_rows": updated_rows[:20],
        "decision_counts": review_counts(enriched),
    }
    if rebuild:
        result["readback"] = review_readback.build_readback(review_csv, question, review_readback.OUT_DIR)
        result["feedback"] = feedback_optimizer.build_feedback_profile(review_csv, feedback_optimizer.OUT_DIR)
    return result


def page() -> str:
    page_html = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>__APP_TITLE__</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1f2933;
      --muted: #64748b;
      --line: #d7dde5;
      --panel: #f8fafc;
      --accent: #116466;
      --accent-2: #7a4f01;
      --danger: #9f1239;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #ffffff;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      padding: 18px 24px 14px;
      display: flex;
      gap: 18px;
      align-items: baseline;
      justify-content: space-between;
    }}
    h1 {{ font-size: 22px; line-height: 1.2; margin: 0; font-weight: 700; }}
    .status {{ color: var(--muted); font-size: 13px; }}
    main {{
      display: grid;
      grid-template-columns: 340px minmax(0, 1fr);
      min-height: calc(100vh - 62px);
    }}
    aside {{
      border-right: 1px solid var(--line);
      padding: 16px;
      background: var(--panel);
    }}
    section {{ padding: 16px 20px 28px; min-width: 0; background: #fbfcfd; }}
    .tabs {{ display: none; }}
    .tab {{
      border: 1px solid var(--line);
      background: #fff;
      padding: 9px 8px;
      font-size: 14px;
      cursor: pointer;
    }}
    .tab.active {{ border-color: var(--accent); color: #fff; background: var(--accent); }}
    .flow-actions {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
      margin: 10px 0;
    }}
    .flow-actions button {{
      width: 100%;
    }}
    .process-shortcuts {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-top: 10px;
    }}
    .process-shortcuts button,
    .process-toolbar button {{
      border: 1px solid var(--line);
      background: #f8fafc;
      color: var(--ink);
      min-height: 36px;
      padding: 8px 10px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }}
    .process-shortcuts button:hover,
    .process-toolbar button:hover {{
      border-color: #b8d2cb;
      background: #f1f8f6;
    }}
    .process-shortcuts button.active,
    .process-toolbar button.active {{
      border-color: var(--accent);
      background: #edf7f4;
      color: var(--accent);
      font-weight: 700;
    }}
    .workbench-brand {{
      display: grid;
      grid-template-columns: 48px minmax(0, 1fr);
      gap: 10px;
      align-items: center;
      border: 1px solid #ccb99b;
      border-radius: 8px;
      background: #fffaf1;
      padding: 10px;
      margin-bottom: 12px;
    }}
    .workbench-mark {{
      width: 48px;
      height: 48px;
      display: grid;
      place-items: center;
      border-radius: 7px;
      color: #f8e4ba;
      background: #8d1f20;
      font-family: "Songti SC", "STSong", "SimSun", serif;
      font-size: 28px;
      font-weight: 900;
    }}
    .workbench-brand strong {{ display: block; font-size: 16px; }}
    .workbench-brand span {{ display: block; color: var(--muted); font-size: 12px; line-height: 1.45; margin-top: 2px; }}
    .question-trigger-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      border: 1px solid #b89565;
      border-radius: 6px;
      background: #fff8e9;
      color: #7a261c;
      padding: 5px 9px;
      margin-bottom: 8px;
      font-size: 13px;
      font-weight: 800;
    }}
    .source-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
    }}
    .source-pill {{
      display: flex;
      align-items: center;
      gap: 6px;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 6px 8px;
      color: #475569;
      font-size: 12px;
    }}
    .source-pill input {{ width: auto; }}
    .route-step-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
      margin-top: 8px;
    }}
    .route-step {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 8px 9px;
      color: #475569;
      font-size: 12px;
      line-height: 1.45;
    }}
    .route-step input {{ width: auto; margin-top: 2px; }}
    .route-step strong {{ display: block; color: var(--ink); font-size: 13px; }}
    .route-step span {{ display: block; color: var(--muted); margin-top: 2px; }}
    .style-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
    }}
    .style-pill {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 8px;
      align-items: start;
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 8px 9px;
      color: #475569;
      font-size: 12px;
      line-height: 1.45;
    }}
    .style-pill input {{ width: auto; margin-top: 2px; }}
    .style-pill strong {{ display: block; color: var(--ink); font-size: 13px; }}
    .style-pill span {{ display: block; color: var(--muted); margin-top: 2px; }}
    .output-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin: 10px 0;
    }}
    .output-grid button:first-child {{ grid-column: 1 / -1; }}
    label {{ display: block; font-size: 13px; color: var(--muted); margin: 12px 0 6px; }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
    }}
    textarea {{ min-height: 88px; resize: vertical; }}
    .row {{ display: grid; grid-template-columns: 1fr 92px; gap: 8px; align-items: end; }}
    .route-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    .route-grid .wide {{ grid-column: 1 / -1; }}
    .route-preview {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: #475569;
      font-size: 12px;
      line-height: 1.5;
      padding: 9px 10px;
      margin-top: 8px;
    }}
    button.primary {{
      border: 0;
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      font-weight: 650;
      color: #fff;
      background: var(--accent);
      cursor: pointer;
    }}
    button.primary.suggested {{
      background: var(--accent-2);
      box-shadow: inset 0 0 0 2px rgba(255,255,255,.35);
    }}
    button.primary:disabled {{ opacity: .55; cursor: wait; }}
    .hint {{ font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.5; }}
    .check-row {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 12px 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .check-row input {{ width: auto; }}
    .result-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 12px;
    }}
    .result-head h2 {{ font-size: 18px; margin: 0; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .result-toolbar {{
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 8px;
      min-width: 0;
      flex: 1;
    }}
    .result-toolbar .meta {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      text-align: right;
    }}
    button.export-machine {{
      min-height: 32px;
      padding: 7px 10px;
      font-size: 12px;
      white-space: nowrap;
      background: var(--accent-2);
      display: none;
    }}
    button.export-machine:disabled {{
      background: #94a3b8;
    }}
    button.stop-talk {{
      min-height: 32px;
      padding: 7px 10px;
      font-size: 12px;
      white-space: nowrap;
      background: #9f1239;
      display: none;
    }}
    button.stop-talk:disabled {{
      background: #94a3b8;
    }}
    .machine-export-card {{
      border-color: #d6bd83;
      background: #fffdf7;
    }}
    .list {{ display: grid; gap: 10px; }}
    .dialogue-output {{
      border: 2px solid #b8d2cb;
      border-radius: 8px;
      background: #fff;
      box-shadow: 0 14px 34px rgba(31, 41, 51, .12);
      padding: 16px;
    }}
    .dialogue-output.waiting {{
      border-color: #d6bd83;
      box-shadow: 0 10px 24px rgba(122, 79, 1, .10);
    }}
    .dialogue-thread {{
      display: grid;
      gap: 14px;
    }}
    .message {{
      display: grid;
      gap: 6px;
      max-width: 920px;
    }}
    .message.user {{
      justify-self: end;
      width: min(760px, 92%);
    }}
    .message.assistant {{
      justify-self: stretch;
    }}
    .message-label {{
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .message.user .message-label {{
      text-align: right;
    }}
    .message-bubble {{
      border-radius: 8px;
      padding: 12px 14px;
      line-height: 1.7;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .user-bubble {{
      background: #edf7f4;
      border: 1px solid #b8d2cb;
    }}
    .assistant-bubble {{
      background: #fffdf9;
      border: 1px solid #d6bd83;
    }}
    .dialogue-output .assistant-bubble.answer-box,
    .dialogue-output .assistant-bubble.answer-wait {{
      resize: vertical;
      overflow: auto;
    }}
    .dialogue-output .assistant-bubble.answer-box {{
      height: min(520px, calc(100vh - 260px));
      max-height: none;
    }}
    .process-pages {{
      border: 1px solid #ccd7e2;
      border-radius: 8px;
      background: #fff;
      padding: 12px;
      box-shadow: 0 8px 18px rgba(31, 41, 51, .07);
    }}
    .process-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 10px;
      margin-bottom: 12px;
    }}
    .process-toolbar button {{
      width: auto;
    }}
    .process-toolbar .process-export {{
      margin-left: auto;
      border-color: #d6bd83;
      background: #fff8eb;
      color: #7a4f01;
    }}
    .process-content {{
      display: grid;
      gap: 10px;
    }}
    .export-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .export-actions button {{
      width: auto;
      min-height: 36px;
      padding: 8px 12px;
      font-weight: 700;
    }}
    .export-history-list {{
      display: grid;
      gap: 8px;
    }}
    .export-history-item {{
      text-align: left;
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 9px 10px;
    }}
    .export-history-item:hover {{
      border-color: #b8d2cb;
      background: #f8fbfa;
    }}
    .process-empty {{
      border: 1px dashed #ccd7e2;
      border-radius: 8px;
      padding: 14px;
      color: var(--muted);
      background: #fbfdff;
      line-height: 1.6;
    }}
    .process-section {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 10px;
    }}
    .process-section summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--accent);
    }}
    .process-section summary span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
      margin-top: 4px;
    }}
    .item {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .item-title {{ font-weight: 700; margin-bottom: 6px; }}
    .item-meta {{ color: var(--muted); font-size: 12px; margin-bottom: 6px; }}
    .quote {{
      border-left: 3px solid var(--accent-2);
      padding-left: 10px;
      color: #334155;
      line-height: 1.55;
      white-space: pre-wrap;
    }}
    .context-box {{
      border: 1px solid var(--line);
      background: #fbfdff;
      border-radius: 6px;
      padding: 10px;
      margin-top: 10px;
    }}
    .context-row {{
      border-top: 1px solid var(--line);
      padding: 9px 0;
    }}
    .context-row:first-child {{ border-top: 0; }}
    .context-row.current {{
      background: #eef8f3;
      margin: 0 -10px;
      padding-left: 10px;
      padding-right: 10px;
    }}
    .reasons {{ color: var(--muted); font-size: 13px; line-height: 1.5; margin-top: 8px; }}
    .review-grid {{
      display: grid;
      grid-template-columns: minmax(110px, 150px) minmax(90px, 120px) minmax(120px, 1fr);
      gap: 8px;
      margin-top: 10px;
      align-items: end;
    }}
    .review-grid textarea {{
      grid-column: 1 / -1;
      min-height: 64px;
    }}
    .review-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 10px;
    }}
    .bulk-grid {{
      display: grid;
      grid-template-columns: 1fr 82px 1fr;
      gap: 8px;
      margin-top: 12px;
      align-items: end;
    }}
    .progress-panel {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #fff;
    }}
    .progress-title {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .progress-track {{
      height: 10px;
      border-radius: 999px;
      background: #e8edf3;
      overflow: hidden;
      margin-bottom: 10px;
    }}
    .progress-fill {{
      height: 100%;
      background: var(--accent);
    }}
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
      gap: 8px;
    }}
    .stat-item {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      background: var(--panel);
    }}
    .stat-value {{ font-size: 18px; font-weight: 700; }}
    .stat-label {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .badge-row {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      border: 1px solid var(--line);
      color: #475569;
      background: #f8fafc;
    }}
    .badge.good {{ border-color: #9cc9b8; color: #116466; background: #eef8f3; }}
    .badge.warn {{ border-color: #e6c28a; color: #7a4f01; background: #fff8eb; }}
    .badge.bad {{ border-color: #f3a9ba; color: var(--danger); background: #fff1f2; }}
    .markdown-box {{
      white-space: pre-wrap;
      font-family: inherit;
      line-height: 1.55;
      max-height: calc(100vh - 240px);
      overflow: auto;
      background: #fff;
      color: var(--ink);
      border: 1px solid var(--line);
      padding: 12px;
      border-radius: 8px;
      margin-top: 10px;
    }}
    .answer-box {{
      min-height: min(520px, calc(100vh - 260px));
      max-height: calc(100vh - 220px);
      overflow: auto;
      background: #fffdf9;
      color: var(--ink);
      border: 0;
      border-radius: 8px;
      padding: 0;
      margin-top: 0;
      line-height: 1.78;
      font-size: 16px;
    }}
    .answer-title {{
      margin-top: 10px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
    }}
    .answer-box h1 {{ font-size: 22px; margin: 0 0 14px; }}
    .answer-box h2 {{ font-size: 18px; margin: 22px 0 10px; padding-top: 12px; border-top: 1px solid var(--line); }}
    .answer-box h3 {{ font-size: 15px; margin: 16px 0 8px; }}
    .answer-box p {{ margin: 8px 0; }}
    .answer-box ul {{ margin: 8px 0 12px 20px; padding: 0; }}
    .answer-box li {{ margin: 5px 0; }}
    .answer-box code {{
      font-family: Monaco, "Courier New", monospace;
      font-size: 12px;
      background: #f1f5f9;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    .answer-box pre {{
      white-space: pre-wrap;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      overflow: auto;
    }}
    .answer-wait {{
      min-height: min(420px, calc(100vh - 280px));
      color: var(--muted);
      border-radius: 8px;
      padding: 0;
      white-space: pre-wrap;
      line-height: 1.6;
      margin-top: 0;
    }}
    .meta-kv {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    .error {{ color: var(--danger); white-space: pre-wrap; }}
    .empty {{ color: var(--muted); padding: 18px 0; }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .command-list {{ margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 12px; }}
    .command-list li {{ margin: 4px 0; line-height: 1.5; }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }}
    .status-grid-item {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 8px;
    }}
    .status-grid-item .num {{ font-size: 18px; font-weight: 700; }}
    .status-grid-item .label {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
    .workflow-process {{
      margin-top: 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 14px;
    }}
    .workflow-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }}
    .workflow-head strong {{ font-size: 16px; }}
    .workflow-head span {{ color: var(--muted); font-size: 12px; line-height: 1.5; }}
    .workflow-section {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
      margin-top: 10px;
    }}
    .workflow-section summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--ink);
    }}
    .workflow-section summary span {{
      display: block;
      color: var(--muted);
      font-weight: 400;
      font-size: 12px;
      margin-top: 2px;
    }}
    .workflow-excerpt {{
      max-height: 360px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--soft);
      padding: 12px;
      margin-top: 8px;
    }}
    .workflow-excerpt h1 {{ font-size: 18px; margin: 0 0 8px; }}
    .workflow-excerpt h2 {{ font-size: 15px; margin: 12px 0 6px; }}
    .workflow-excerpt h3 {{ font-size: 14px; margin: 10px 0 4px; }}
    .table-scroll {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-top: 8px;
    }}
    .table-scroll table {{ min-width: 720px; }}
    .table-scroll th, .table-scroll td {{ vertical-align: top; }}
    @media (max-width: 820px) {{
      main {{ grid-template-columns: 1fr; }}
      aside {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      header {{ display: block; }}
      .status {{ margin-top: 6px; }}
      .result-head {{ display: block; }}
      .result-toolbar {{
        margin-top: 8px;
        justify-content: space-between;
      }}
      .result-toolbar .meta {{
        text-align: left;
        white-space: normal;
      }}
    }}
  </style>
</head>
    <body>
    <header>
    <h1>__APP_TITLE__</h1>
    <div class="status">左边提问，右边显示 Codex 的实时回复</div>
  </header>
  <main>
    <aside>
        <div class="workbench-brand">
        <div class="workbench-mark">红</div>
        <div>
          <strong>一问入红楼</strong>
          <span>输入问题，右侧显示实时回复。</span>
        </div>
      </div>
      <div class="tabs" role="tablist">
        <button class="tab active" data-mode="workflow">工作台</button>
        <button class="tab" data-mode="talk">红楼解语</button>
        <button class="tab" data-mode="articles">文章</button>
        <button class="tab" data-mode="review">复核</button>
      </div>

      <div id="workflow-form" class="form">
        <div class="question-trigger-chip">进入红楼梦工程</div>
        <textarea id="common-question" aria-label="问题"></textarea>

        <div class="flow-actions">
          <button class="primary" id="run-simple-talk">一问</button>
        </div>

        <label>过程页面</label>
        <div class="process-shortcuts">
          <button type="button" data-process-tab="decompose">问题拆解</button>
          <button type="button" data-process-tab="evidence">证据页</button>
          <button type="button" data-process-tab="materials">材料池</button>
          <button type="button" data-process-tab="export">导出页</button>
        </div>

        <div class="engineering-controls" hidden>
        <label>工程路径</label>
        <div class="route-grid">
          <div>
            <label for="task-pillar">第一层：工作目标</label>
            <select id="task-pillar">
              <option value="出库">出库取证｜查库、查原文、建材料池</option>
              <option value="现场对答">现场对答｜轻量取证、追问、回显</option>
              <option value="工程状态">工程状态｜总账、体检、问题包</option>
            </select>
          </div>
          <div>
            <label id="task-route-label" for="task-route">第二层：问题中心</label>
            <select id="task-route"></select>
          </div>
          <div class="wide">
            <label id="task-anchor-label" for="task-anchor">第三层：查证顺序</label>
            <select id="task-anchor">
              <option value="由 Codex 判断">由 Codex 判断</option>
              <option value="先原文后库">先原文后库</option>
              <option value="先库轴后原文">先库轴后原文</option>
              <option value="先关键词后原文">先关键词后原文</option>
              <option value="先章节顺读再跨回">先章节顺读再跨回</option>
              <option value="先反证排除再回答">先反证排除再回答</option>
              <option value="多路并行再回原文">多路并行再回原文</option>
            </select>
          </div>
        </div>
        <label>取证动作（可复选）</label>
        <div class="route-step-grid">
          <label class="route-step">
            <input id="route-action-original" type="checkbox" checked>
            <span><strong>原文显性词</strong><span>用问题里的原词、原句、人名、物名、诗句或回目词查全文。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-keywords" type="checkbox" checked>
            <span><strong>扩展关键词</strong><span>把问题拆成3到5组搜索词，补同义词、异称和相关概念。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-axis" type="checkbox" checked>
            <span><strong>库轴映射</strong><span>查人物、事件、空间、物象诗词等库和映射关系，再回原文。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-chapter" type="checkbox">
            <span><strong>章节顺查</strong><span>锁定章回或场景后，按前后文顺读。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-cross" type="checkbox">
            <span><strong>跨回追踪</strong><span>围绕同一线索在全书不同回目找呼应和变化。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-verify" type="checkbox" checked>
            <span><strong>双向校验</strong><span>原文命中后查库，库命中后回原文，排除串题。</span></span>
          </label>
          <label class="route-step">
            <input id="route-action-counter" type="checkbox">
            <span><strong>反证排除</strong><span>专门查不支持、易误召回、易混旧题的材料。</span></span>
          </label>
        </div>
        <div id="route-preview" class="route-preview">第一层定工作目标；第二层定问题中心；第三层定查证顺序；复选项定取证动作。</div>

        <label>材料来源</label>
        <div class="source-grid">
          <label class="source-pill"><input id="source-base" type="checkbox" checked>底库</label>
          <label class="source-pill"><input id="source-original" type="checkbox" checked>原文</label>
          <label class="source-pill"><input id="source-generated" type="checkbox" checked>生成文件</label>
        </div>

        <div class="route-grid">
          <div>
            <label for="task-depth">运行深度</label>
            <select id="task-depth">
              <option value="标准｜拆题、证据、结论都要有">标准</option>
              <option value="轻量｜短答、少证据、少跑流程">轻量</option>
              <option value="深度｜问题树、证据包、文章和反馈链">深度</option>
            </select>
          </div>
          <div>
            <label for="task-output">先看哪一块</label>
            <select id="task-output">
              <option value="红楼解语优先｜先正面回答，再展开证据">红楼解语优先</option>
              <option value="问题拆解优先｜先拆清问题树和子问题">问题拆解优先</option>
              <option value="只出证据｜先不要文章">只出证据</option>
              <option value="写作稿｜证据稳定后进入文章">写作稿</option>
              <option value="内部过程｜看问题包、清单和运行状态">内部过程</option>
            </select>
          </div>
        </div>

        <label>风格表达</label>
        <div class="style-grid" id="style-grid">
          <label class="style-pill">
            <input type="radio" name="answer-style" value="" data-label="自然回答" checked>
            <span><strong>自然回答</strong><span>不加额外口令，按问题和材料自然回答。</span></span>
          </label>
          <label class="style-pill">
            <input type="radio" name="answer-style" value="表达风格：原文慢推；证据出发；温和收束。" data-label="原文慢推">
            <span><strong>原文慢推</strong><span>适合解释型问题，从证据慢慢推到判断。</span></span>
          </label>
          <label class="style-pill">
            <input type="radio" name="answer-style" value="表达风格：研究式回答；证据、推理、结论分清；材料池自由发挥。" data-label="研究式综述">
            <span><strong>研究式综述</strong><span>适合复杂问题，把证据、推理和结论分清楚。</span></span>
          </label>
        </div>

        <label for="task-requirements">附加要求</label>
        <textarea id="task-requirements" placeholder="例如：心得式结论；研究式回答；原文慢推；温和收束；或 ars-lit-review。证据要回到原文。"></textarea>

        <div class="hint">输入问题后，先按“出库/现场对答/工程状态”进入原工程路径，再由 Codex 读库、取证、判断。页面只显示红楼解语或材料，不用本地过程稿冒充结论。</div>

        <label>Codex 回答窗口</label>
        <div class="output-grid">
          <button class="primary" id="run-workflow-talk">红楼解语</button>
          <button class="primary" id="run-workflow-decompose">问题拆解</button>
          <button class="primary" id="run-workflow-evidence">证据</button>
          <button class="primary" id="run-workflow-research">文稿/材料池</button>
          <button class="primary" id="run-workflow-status">内部过程</button>
        </div>

        <label>辅助入口</label>
        <div class="flow-actions">
          <button class="primary" id="restore-latest-talk">恢复最近回显</button>
          <button class="primary" id="load-talk-history">回显记录</button>
          <button class="primary" id="run-workflow-search">查原文</button>
          <button class="primary" id="run-loop-list">查看问题包</button>
          <button class="primary" id="run-experience-review">经验复盘</button>
        </div>

        <details>
          <summary>高级参数（数量与召回范围）</summary>
          <div class="hint">上面的三层路径负责触发工程方向；这里只调材料数量、实体词和关键词，不再替代出库或现场对答判断。</div>
          <label for="search-limit">全文检索数量</label>
          <input id="search-limit" type="number" min="1" max="80" value="20">
          <label for="common-entities">证据实体</label>
          <input id="common-entities" value="贾宝玉, 通灵宝玉, 顽石, 茫茫大士, 渺渺真人">
          <label for="common-keywords">证据关键词</label>
          <textarea id="common-keywords">道, 佛, 僧, 道人, 太虚, 顽石, 通灵, 木石, 还泪, 幻, 空, 情</textarea>
          <div class="row">
            <div>
              <label for="common-evidence-limit">每题证据段落数</label>
              <input id="common-evidence-limit" type="number" min="1" max="120" value="40">
            </div>
            <div>
              <label for="common-decompose-limit">每题拆题预览</label>
              <input id="common-decompose-limit" type="number" min="1" max="20" value="5">
            </div>
          </div>
          <div class="row">
            <div>
              <label for="common-research-limit">每题研究段落数</label>
              <input id="common-research-limit" type="number" min="1" max="30" value="20">
            </div>
            <div>
              <label for="common-research-top">显示条数</label>
              <input id="common-research-top" type="number" min="1" max="80" value="30">
            </div>
          </div>
          <label class="check-row"><input id="common-feedback" type="checkbox" checked>研究使用复核反馈排序</label>
          <label for="common-talk-top-n">红楼解语参考条数</label>
          <input id="common-talk-top-n" type="number" min="1" max="20" value="10">
        </details>
        </div>
      </div>

      <div id="talk-form" class="form" hidden>
        <label>Codex 回答台</label>
        <div class="hint">同一个问题框输入；红楼解语区只回显 Codex 读完工程材料后的回答；工程拆题、证据池和材料池显示在工程运转结果区。</div>
        <div class="flow-actions">
          <button class="primary" id="run-talk">提交/刷新 Codex 回答</button>
        </div>
      </div>

      <div id="articles-form" class="form" hidden>
        <label>文章阅读 / 文章入库</label>
        <div class="hint">文章阅读显示过去问题保存下来的文章列表；文章入库针对当前题，把前后过程、红楼解语和入库预检保存成可追溯记录。</div>
        <div class="row">
          <div>
            <label for="article-limit">显示条数</label>
            <input id="article-limit" type="number" min="1" max="120" value="30">
          </div>
          <button class="primary" id="load-articles">文章阅读</button>
        </div>
        <div class="flow-actions">
          <button class="primary" id="ingest-current-article">文章入库</button>
        </div>
        <div class="hint">“入库程序”只保存红楼解语和追溯路径：预检报告、候选行、回挂清单、身份卡和摘要；不会直接写 Notion，也不会调用本地文章稿链。</div>
      </div>

      <div id="review-form" class="form" hidden>
        <label for="review-filter">复核状态</label>
        <select id="review-filter">
          <option value="全部">全部</option>
          <option value="待复核" selected>待复核</option>
          <option value="保留">保留</option>
          <option value="剔除">剔除</option>
          <option value="保留剔除对照">保留/剔除对照</option>
          <option value="未填写字段">未填写字段</option>
          <option value="降级">降级</option>
          <option value="反证">反证</option>
        </select>
        <div class="row">
          <div>
            <label for="review-limit">显示条数</label>
            <input id="review-limit" type="number" min="1" max="120" value="20">
          </div>
          <button class="primary" id="run-review">读取</button>
        </div>
        <div class="flow-actions">
          <button class="primary" id="batch-save-review">批量保存当前显示</button>
          <button class="primary" id="export-review">导出当前筛选</button>
        </div>
        <div class="hint">保存后会刷新复核回读和反馈排序配置。</div>
        <details>
          <summary>批量设置（可选）</summary>
          <label>快速填充当前显示</label>
          <div class="bulk-grid">
            <select id="bulk-decision">
              <option value="">不改判断</option>
              <option value="待复核">待复核</option>
              <option value="保留">保留</option>
              <option value="剔除">剔除</option>
              <option value="降级" selected>降级</option>
              <option value="反证">反证</option>
            </select>
            <input id="bulk-level" value="B" placeholder="等级">
            <input id="bulk-role" value="背景/旁证" placeholder="角色">
            <input id="bulk-use" value="" placeholder="写作用途">
            <label class="check-row"><input id="bulk-empty-only" type="checkbox" checked>只改空字段</label>
            <button class="primary" id="apply-bulk-defaults">应用到当前显示</button>
          </div>
        </details>
      </div>
    </aside>
    <section>
      <div class="result-head">
        <h2 id="result-title">实时回复</h2>
        <div class="result-toolbar">
          <div class="meta" id="result-meta">左边提问，右边显示 Codex 的实时回复</div>
          <button class="primary stop-talk" id="stop-talk" disabled title="停止当前红楼解语运算，释放入口。">停止解语</button>
          <button class="primary export-machine" id="export-machine-pack" disabled title="导出当前这一问的红楼解语、问题拆解、证据页、材料池和工程追溯包。">导出本问</button>
        </div>
      </div>
      <div id="results" class="list">
        <section class="dialogue-output waiting">
          <div class="dialogue-thread">
            <div class="message assistant">
              <div class="message-label">Codex 实时回复</div>
              <div class="message-bubble assistant-bubble answer-wait">左边输入问题后，Codex 的实时回复会显示在这里。</div>
            </div>
          </div>
        </section>
        <section class="process-pages">
          <div class="process-toolbar">
            <button type="button" data-process-tab="decompose">问题拆解</button>
            <button type="button" data-process-tab="evidence">证据页</button>
            <button type="button" data-process-tab="materials">材料池</button>
            <button type="button" data-process-tab="export">导出页</button>
          </div>
          <div class="process-content" id="process-content">
            <div class="process-empty">提交问题后，问题拆解、证据页和材料池会显示在这里。</div>
          </div>
        </section>
      </div>
    </section>
  </main>
  <script>
    const state = {{
      mode: "workflow",
      talkPollTimer: null,
      liveReplyPollTimer: null,
      liveReplyPollRequestId: "",
      lastTalkData: null,
      lastMachineExport: null,
      processTab: "decompose",
      exportHistory: []
    }};
    const defaultQuestionTexts = new Set([
      "请在这里输入你的红楼梦问题。",
      "请在这里输入你的红楼梦问题"
    ]);
    const activeTalkStatuses = new Set(["待Codex处理", "待处理", "处理中", "待最终回显稿", "等待补证", "待人工复核"]);
    const modeTitles = {{
      workflow: "实时回复",
      talk: "实时回复",
      articles: "文章阅读 / 文章入库",
      review: "人工复核"
    }};
    const modeHints = {{
      workflow: "左边提问，右边显示 Codex 的实时回复。",
      talk: "左边提问，右边显示 Codex 的实时回复。",
      articles: "读取历史文章，或把当前问题生成入库预检。",
      review: "复核当前人工表并可回填判断。"
    }};
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const routeOptions = {{
      "出库": [
        {{
          label: "由工程判断｜自动判定中心",
          value: "问题中心：由工程判断｜先判断问题更像人物、事件、关系、物象、诗词、空间、章节原句还是观念主题，再选择搜索词和来源。",
          hint: "不确定问题中心时选它；工程会先判中心，再决定查法。"
        }},
        {{
          label: "人物中心｜先确定人物",
          value: "问题中心：人物中心｜先确定核心人物、别名、关系人和人物-段落映射；再按人物命中回原文核验。",
          hint: "适合问某个人、几个人、人物性格、言行变化、人物关系和身份结构。"
        }},
        {{
          label: "事件中心｜先确定事件",
          value: "问题中心：事件中心｜先确定事件、起点、转折、相关人物和事件-段落映射；再回原文追前后因果。",
          hint: "适合问一件事从哪里起、如何发展、影响谁、后面如何回响。"
        }},
        {{
          label: "关系中心｜先确定关系边",
          value: "问题中心：关系中心｜先确定人物关系、物件关系、场景关系或观念关系；查关系映射和共同段落，再回原文。",
          hint: "适合宝黛、钗黛、人物互证、物件牵连、关系变化和对照题。"
        }},
        {{
          label: "物象中心｜先确定物件/意象",
          value: "问题中心：物象中心｜先确定物件、意象、对象别名、经手人物和对象-段落映射；再回原文看功能。",
          hint: "适合题帕、通灵玉、花、梦、香囊、器物、意象和象征功能。"
        }},
        {{
          label: "诗词判词中心｜先确定文本对象",
          value: "问题中心：诗词判词中心｜先确定诗、词、曲、判词、题咏或原句；查诗词库和出现段落，再回原文上下文。",
          hint: "适合诗词、判词、题咏、回目文字、原句意义和文本互照。"
        }},
        {{
          label: "空间中心｜先确定地点/场景",
          value: "问题中心：空间中心｜先确定地点、场景、人物移动和空间关系；查空间库、场景段落和相关事件，再回原文。",
          hint: "适合潇湘馆、怡红院、大观园、场域变化、移动路线和空间象征。"
        }},
        {{
          label: "章节原句中心｜先确定回目/段落",
          value: "问题中心：章节原句中心｜先确定第几回、哪段话、哪句原文或回目标题；以原文上下文为第一真源。",
          hint: "适合问位置、原话、上下文、某一回发生了什么。"
        }},
        {{
          label: "观念主题中心｜先确定概念词",
          value: "问题中心：观念主题中心｜先确定主题词、概念词、相关人物和关键事件；用关键词网络跨库找证据，再回原文。",
          hint: "适合问情、空、幻、命运、女性、家族、哲学意味这类大题。"
        }}
      ],
      "现场对答": [
        {{
          label: "轻量问答｜少过程、快回显",
          value: "现场对答｜轻量取证后回答；问题仍进入红楼梦工程，优先用少量原文和材料池支撑红楼解语。",
          hint: "像在对话框里问我一样，但本页仍坚持不拿模块搜索冒充结论。"
        }},
        {{
          label: "连续追问｜承接上一题再补证",
          value: "现场对答｜承接上一轮问题、答案和材料池；继续追问、改问、补问或要求换一种说法。",
          hint: "用于你看完回答后继续追问，尽量沿上一题的问题包接着走。"
        }},
        {{
          label: "先谈方向｜先判断该怎么查",
          value: "现场对答｜先判断问题该拆成哪些搜索词、该查哪些库、是否需要顺读原文；暂不把过程稿冒充红楼解语。",
          hint: "用于问题还没想清楚时，先商量问题中心、检索策略和查证顺序。"
        }},
        {{
          label: "红楼解语｜读取已写答复",
          value: "现场对答｜读取 Codex 已写入的红楼解语文件，并回显到当前页面",
          hint: "用于已经在 Codex 里生成过答案，要在页面里打开查看。"
        }},
        {{
          label: "文章后续｜归档/回挂/续写建议",
          value: "现场对答｜文章已经写好并被认可后，讨论归档、分类、回挂证据、补证或后续清单。",
          hint: "这是文章后处理入口，不替代取证和最终回答。"
        }}
      ],
      "工程状态": [
        {{
          label: "当前状态",
          value: "当前状态｜查看问题包、闭环进度、复核状态、下一步和关键文件",
          hint: "用于看现在做到哪里、该看哪个文件、下一步做什么。"
        }},
        {{
          label: "总账接续",
          value: "总账接续｜读取首页、总账、状态加载卡和刷新规则，恢复工程上下文",
          hint: "用于断线后接上工程，不从头猜。"
        }},
        {{
          label: "库体检",
          value: "库体检｜检查底库、全文库、多轴库、问题包、映射和核心文件是否健康",
          hint: "用于怀疑库状态异常、页面打不开、证据不对时。"
        }},
        {{
          label: "映射体检",
          value: "映射体检｜检查人物、事件、空间、段落、ID 和跨库关系是否能互相回挂",
          hint: "用于专门查关系边、ID 对齐、跨库联动问题。"
        }},
        {{
          label: "简繁体检",
          value: "简繁体检｜检查繁体原文、简体查询、双写召回、异体字和索引一致性",
          hint: "用于处理简体查不到繁体、繁体原文和简体库不一致的问题。"
        }},
        {{
          label: "入口/桌面修复",
          value: "入口/桌面修复｜检查本地服务、桌面快捷入口、端口和页面版本是否对齐",
          hint: "用于页面打不开、进了旧页面、按钮无效、端口错位。"
        }}
      ]
    }};

    function currentQuestion() {{
      const q = ($("common-question").value || "").trim();
      return defaultQuestionTexts.has(q) ? "" : q;
    }}

    function syncRouteOptions() {{
      const pillar = $("task-pillar").value || "出库";
      const routeSelect = $("task-route");
      const routes = routeOptions[pillar] || routeOptions["出库"];
      routeSelect.innerHTML = routes.map((route, idx) => `<option value="${{esc(route.value)}}" data-hint="${{esc(route.hint)}}" ${{idx === 0 ? "selected" : ""}}>${{esc(route.label)}}</option>`).join("");
      syncRouteLabels(pillar);
      applyRouteDefaults();
      updateRoutePreview();
    }}

    function syncRouteLabels(pillar) {{
      if (pillar === "工程状态") {{
        $("task-route-label").textContent = "第二层：检查对象";
        $("task-anchor-label").textContent = "第三层：处理顺序";
      }} else if (pillar === "现场对答") {{
        $("task-route-label").textContent = "第二层：对答方式";
        $("task-anchor-label").textContent = "第三层：查证顺序";
      }} else {{
        $("task-route-label").textContent = "第二层：问题中心";
        $("task-anchor-label").textContent = "第三层：查证顺序";
      }}
    }}

    function selectOptionByPrefix(selectId, prefix) {{
      const select = $(selectId);
      if (!select || !prefix) return;
      const option = Array.from(select.options).find(item => String(item.value || "").startsWith(prefix));
      if (option) select.value = option.value;
    }}

    function routeDefaults(pillar, routeText) {{
      if (pillar === "现场对答") {{
        return {{ depth: "轻量", output: "红楼解语优先", order: "由 Codex 判断", actions: ["original", "keywords", "axis", "verify"] }};
      }}
      if (pillar === "工程状态") {{
        return {{ depth: "轻量", output: "内部过程", order: "由 Codex 判断", actions: ["axis", "verify"] }};
      }}
      if (routeText.includes("章节原句")) {{
        return {{ depth: "轻量", output: "红楼解语优先", order: "先原文后库", actions: ["original", "chapter", "axis", "verify"] }};
      }}
      if (routeText.includes("人物") || routeText.includes("事件") || routeText.includes("关系") || routeText.includes("物象") || routeText.includes("诗词") || routeText.includes("空间")) {{
        return {{ depth: "标准", output: "只出证据", order: "先库轴后原文", actions: ["original", "keywords", "axis", "verify"] }};
      }}
      if (routeText.includes("观念主题")) {{
        return {{ depth: "深度", output: "红楼解语优先", order: "先关键词后原文", actions: ["original", "keywords", "axis", "cross", "verify", "counter"] }};
      }}
      return {{ depth: "标准", output: "红楼解语优先", order: "由 Codex 判断", actions: ["original", "keywords", "axis", "verify"] }};
    }}

    function applyRouteDefaults() {{
      const pillar = $("task-pillar").value || "出库";
      const routeText = $("task-route").selectedOptions[0]?.textContent || "";
      const defaults = routeDefaults(pillar, routeText);
      selectOptionByPrefix("task-depth", defaults.depth);
      selectOptionByPrefix("task-output", defaults.output);
      if (defaults.order) $("task-anchor").value = defaults.order;
      if (defaults.actions) setRouteActionDefaults(defaults.actions);
    }}

    function setRouteActionDefaults(actions) {{
      const wanted = new Set(actions || []);
      const mapping = [
        ["route-action-original", "original"],
        ["route-action-keywords", "keywords"],
        ["route-action-axis", "axis"],
        ["route-action-chapter", "chapter"],
        ["route-action-cross", "cross"],
        ["route-action-verify", "verify"],
        ["route-action-counter", "counter"]
      ];
      mapping.forEach(([id, key]) => {{
        const input = $(id);
        if (input) input.checked = wanted.has(key);
      }});
    }}

    function syncSuggestedOutputButton() {{
      const output = $("task-output").selectedOptions[0]?.textContent || "";
      const mapping = [
        ["红楼解语", "run-workflow-talk"],
        ["问题拆解", "run-workflow-decompose"],
        ["只出证据", "run-workflow-evidence"],
        ["写作稿", "run-workflow-research"],
        ["内部过程", "run-workflow-status"]
      ];
      mapping.forEach(([, id]) => $(id).classList.remove("suggested"));
      const found = mapping.find(([key]) => output.includes(key));
      if (found) $(found[1]).classList.add("suggested");
    }}

    function updateRoutePreview() {{
      const pillar = $("task-pillar").value || "出库";
      const selected = $("task-route").selectedOptions[0];
      const routeText = selected ? selected.textContent : "";
      const order = $("task-anchor").value || "由 Codex 判断";
      const depth = $("task-depth") ? $("task-depth").selectedOptions[0]?.textContent || "" : "";
      const output = $("task-output") ? $("task-output").selectedOptions[0]?.textContent || "" : "";
      const hint = selected ? selected.dataset.hint || "" : "";
      $("route-preview").textContent = `目标：${{pillar}}；中心/方式：${{routeText}}；顺序：${{order}}；动作：${{currentRouteActions()}}；来源：${{currentSources()}}；深度：${{depth}}；产出：${{output}}；表达：${{currentStyleLabel()}}。${{hint}}`;
      syncSuggestedOutputButton();
    }}

    function currentRouteActions() {{
      const actions = [];
      if ($("route-action-original").checked) actions.push("原文显性词");
      if ($("route-action-keywords").checked) actions.push("扩展关键词");
      if ($("route-action-axis").checked) actions.push("库轴映射");
      if ($("route-action-chapter").checked) actions.push("章节顺查");
      if ($("route-action-cross").checked) actions.push("跨回追踪");
      if ($("route-action-verify").checked) actions.push("双向校验");
      if ($("route-action-counter").checked) actions.push("反证排除");
      return actions.length ? actions.join("、") : "由工程判断";
    }}

    function currentSources() {{
      const sources = [];
      if ($("source-base").checked) sources.push("底库");
      if ($("source-original").checked) sources.push("原文");
      if ($("source-generated").checked) sources.push("生成文件");
      return sources.length ? sources.join("、") : "由 Codex 判断";
    }}

    function currentStyleInput() {{
      return document.querySelector('input[name="answer-style"]:checked');
    }}

    function currentStyleLabel() {{
      return currentStyleInput()?.dataset.label || "自然回答";
    }}

    function currentStylePrompt() {{
      return (currentStyleInput()?.value || "").trim();
    }}

    function currentTaskIntent() {{
      const pillar = $("task-pillar").value || "出库";
      const route = $("task-route").value || "";
      const routeLabel = $("task-route").selectedOptions[0]?.textContent || "";
      const order = $("task-anchor").value || "由 Codex 判断";
      const depth = $("task-depth").value || "标准";
      const output = $("task-output").value || "红楼解语优先";
      return `工程触发包｜第一层工作目标：${{pillar}}｜第二层问题中心/方式：${{routeLabel}}｜第三层查证顺序：${{order}}｜取证动作：${{currentRouteActions()}}｜材料来源：${{currentSources()}}｜运行深度：${{depth}}｜优先回显：${{output}}｜表达：${{currentStyleLabel()}}｜工程规则：${{route}}｜运行链：问题入口→聚拢总图加载→现成编号入口门收点与穷尽补点→聚拢层级交集路由→原文裁判→材料池→材料池精读门→Codex红楼解语｜红楼解语要求：先逐条读材料池，再写；文末保留原文锚点/证据依据`;
    }}

    function currentRequirements() {{
      const style = currentStylePrompt();
      const manual = ($("task-requirements").value || "").trim();
      return [style, manual].filter(Boolean).join("\\n");
    }}

    function requireQuestion() {{
      const q = currentQuestion();
      if (!q) {{
        throw new Error("请先填写问题，再运行。");
      }}
      return q;
    }}

    function setMode(mode) {{
      state.mode = mode;
      document.querySelectorAll(".tab").forEach(btn => btn.classList.toggle("active", btn.dataset.mode === mode));
      ["workflow", "talk", "articles", "review"].forEach(name => $(name + "-form").hidden = name !== mode);
      $("result-title").textContent = modeTitles[mode] || "红楼梦工作流";
      if (!state.lastTalkData) {{
        $("result-meta").textContent = modeHints[mode] || "等待操作";
      }}
      syncMachineExportButton();
    }}

    async function getJSON(url) {{
      const res = await fetch(url);
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }}

    async function postJSON(url, payload) {{
      const res = await fetch(url, {{
        method: "POST",
        headers: {{"Content-Type": "application/json"}},
        body: JSON.stringify(payload)
      }});
      if (!res.ok) throw new Error(await res.text());
      return await res.json();
    }}

    function renderSearch(data) {{
      if (data.codex_only) {{
        renderTalk(data);
        startTalkPolling(data);
        return;
      }}
      $("result-meta").textContent = `${{data.count}} 条结果`;
      if (!data.results.length) {{
        $("results").innerHTML = '<div class="empty">无结果。</div>';
        return;
      }}
      $("results").innerHTML = data.results.map(row => `
        <article class="item">
          <div class="item-title">${{esc(row.title)}}</div>
          <div class="item-meta">${{esc(row.doc_type)}}｜${{esc(row.doc_key)}}｜第${{esc(row.chapter_no || "")}}回｜${{esc(row.segment_no || "")}}｜${{esc(row.source_axis)}}</div>
        </article>
      `).join("");
    }}

    function renderEvidence(data) {{
      if (data.codex_only) {{
        renderTalk(data);
        startTalkPolling(data);
        return;
      }}
      $("result-meta").textContent = `${{data.segments.length}} 个候选段落｜${{data.direct_edge_hits}} 条直接证据边`;
      $("results").innerHTML = data.segments.map(row => `
        <article class="item">
          <div class="item-title">${{esc(row.segment_no)}}｜第${{esc(row.chapter_no || "")}}回｜评分 ${{esc(row.score)}}｜${{esc(row.summary)}}</div>
          <div class="item-meta">${{esc(row.chapter_title)}}</div>
          <div class="quote">${{esc(row.quote)}}</div>
          <div class="reasons">${{esc((row.reasons || []).join("；"))}}</div>
        </article>
      `).join("") || '<div class="empty">无候选段落。</div>';
    }}

    function renderDecompose(data) {{
      if (data.codex_only) {{
        renderTalk(data);
        startTalkPolling(data);
        return;
      }}
      $("result-meta").textContent = `${{data.subquestion_count}} 个子问题`;
      $("results").innerHTML = data.subquestions.map(sub => `
        <article class="item">
          <div class="item-title">${{esc(sub.order)}}. ${{esc(sub.dimension)}}｜${{esc(sub.question)}}</div>
          <div class="item-meta">实体：${{esc((sub.entities || []).join("、"))}}｜关键词：${{esc((sub.keywords || []).join("、"))}}</div>
          <div class="reasons">${{esc(sub.purpose)}}｜${{esc(sub.evidence_expectation)}}</div>
          ${{(sub.preview || []).map(row => `<div class="quote">${{esc(row.segment_no)}}｜第${{esc(row.chapter_no)}}回｜${{esc(row.score)}}｜${{esc(row.summary)}}｜${{esc(row.quote)}}</div>`).join("")}}
        </article>
      `).join("");
    }}

    function feedbackBadge(row) {{
      const adjustment = Number(row.feedback_adjustment || 0);
      if (!adjustment) return '<span class="badge">反馈 0</span>';
      const cls = adjustment > 0 ? "good" : "bad";
      const sign = adjustment > 0 ? "+" : "";
      return `<span class="badge ${{cls}}">反馈 ${{sign}}${{esc(adjustment)}}</span>`;
    }}

    function renderResearch(data) {{
      if (data.codex_only) {{
        renderTalk(data);
        startTalkPolling(data);
        return;
      }}
      const feedback = data.feedback || {{}};
      const feedbackText = feedback.applied ? `反馈已启用，${{feedback.labeled_rows || 0}} 条人工判断` : `反馈未启用`;
      $("result-meta").textContent = `${{data.subquestion_count}} 个子问题｜${{data.unique_segments}} 个合并段落｜${{feedbackText}}`;
      $("results").innerHTML = data.segments.map(row => `
        <article class="item" data-segment-no="${{esc(row.segment_no || "")}}">
          <div class="item-title">${{esc(row.segment_no)}}｜第${{esc(row.chapter_no || "")}}回｜${{esc(row.evidence_role || "")}}｜${{esc(row.summary)}}</div>
          <div class="item-meta">${{esc(row.chapter_title)}}｜命中子问题 ${{esc(row.hit_subquestion_count || "")}}｜原优先级 ${{esc(row.triage_priority || row.priority || "")}}｜调整后优先级 ${{esc(row.adjusted_priority || row.triage_priority || row.priority || "")}}</div>
          <div class="badge-row">
            <span class="badge good">${{esc(row.evidence_role || "未分级")}}</span>
            ${{feedbackBadge(row)}}
          </div>
          <div class="quote">${{esc(row.quote)}}</div>
          <div class="reasons">说明：${{esc(row.triage_note || "")}}｜反馈：${{esc(row.feedback_reasons || "未启用或无调整")}}｜命中子问题：${{esc(row.hit_subquestions || "")}}</div>
          <div class="review-actions"><button class="primary load-context" data-segment-no="${{esc(row.segment_no || "")}}">上下文</button></div>
          <div class="context-slot"></div>
        </article>
      `).join("") || '<div class="empty">无候选段落。</div>';
      attachContextButtons();
    }}

    function renderLoopStatus(data) {{
      const progress = data.review_progress || {{}};
      const usable = Number(progress.usable_rows || 0);
      const pending = Number(progress.pending_rows || 0);
      const total = Number(progress.total_rows || 0);
      const completionRate = total ? Math.round((progress.completed_rows || 0) / total * 100) : 0;
      const writable = data.files?.find(item => item.name.startsWith("09_可写作证据包"));
      const writableReady = Boolean(writable && writable.exists);

      const canWriteHint = usable > 0 ? "已具备可写作证据" : (pending === total ? "尚未形成可写作材料（仍待复核）" : "复核表已有内容，但可写作证据不足");
      const phase = data.phase || "未启动闭环";
      const filesHtml = (data.files || []).map(item => `
        <div class="item-meta">${{esc(item.name)}}：${{item.exists ? "存在" : "缺失"}}｜${{item.size || 0}} bytes｜${{esc(item.path || "")}}</div>
      `).join("") || '<div class="item-meta">未检测到关键文件。</div>';
      const commands = Array.isArray(data.commands) ? data.commands : [];
      const commandLines = commands.length
        ? `<ul class="command-list">${{commands.map(item => `<li>${{esc(item)}}</li>`).join("")}}</ul>`
        : '<div class="item-meta">当前没有推荐命令。</div>';

      $("result-meta").textContent = `最终版状态｜${{phase}}｜可写作：${{usable}}`;
      $("results").innerHTML = `
        <article class="item">
          <div class="item-title">问题：${{esc(data.question || "")}}</div>
          <div class="item-meta">问题包：${{esc(data.package || "")}}</div>
          <div class="item-meta">状态文件：${{esc(data.status_file || "")}}</div>
          <div class="item-meta">当前摘要：${{esc(data.status || "")}}</div>
          <div class="item-meta">阶段：${{esc(phase)}}｜建议优先文件：${{esc(data.primary_file || "")}}</div>
          <div class="item-meta">写作判断：${{esc(canWriteHint)}}</div>
          <div class="status-grid">
            <div class="status-grid-item"><div class="num">${{total}}</div><div class="label">复核表行数</div></div>
            <div class="status-grid-item"><div class="num">${{progress.completed_rows || 0}}</div><div class="label">已判断</div></div>
            <div class="status-grid-item"><div class="num">${{pending}}</div><div class="label">待复核</div></div>
            <div class="status-grid-item"><div class="num">${{usable}}</div><div class="label">可写作证据</div></div>
            <div class="status-grid-item"><div class="num">${{completionRate}}%</div><div class="label">人工完成率</div></div>
          </div>
          <div class="meta">
            <span class="badge ${{writableReady ? "good" : "warn"}}">${{writableReady ? "可写作包已生成" : "可写作包未生成"}}</span>
          </div>
          <div class="context-box">
            <div class="item-title">推荐命令</div>
            ${{commandLines}}
          </div>
          <div class="context-box">
            <div class="item-title">核心文件状态</div>
            ${{filesHtml}}
          </div>
        </article>
      `;
    }}

    function renderLoopList(data) {{
      const safeData = data || {};
      const packages = Array.isArray(safeData.packages) ? safeData.packages : [];
      $("result-meta").textContent = `问题包清单｜共 ${{packages.length}} 个`;
      if (!packages.length) {{
        $("results").innerHTML = '<div class="empty">当前暂无闭环问题包。</div>';
        return;
      }}
      $("results").innerHTML = packages.map((item) => `
        <article class="item">
          <div class="item-title">${{esc(item.question || "（未设置问题）")}}</div>
          <div class="item-meta">问题包：${{esc(item.package || item.path || "")}}</div>
          <div class="item-meta">状态：${{esc(item.status || "")}}</div>
          <div class="item-meta">总行：${{esc(item.total_rows || 0)}}｜已判断：${{esc(item.completed_rows || 0)}}｜待复核：${{esc(item.pending_rows || 0)}}｜可写作：${{esc(item.usable_rows || 0)}}｜剔除：${{esc(item.rejected_rows || 0)}}｜完成率：${{esc(item.completion_rate || 0)}}%</div>
          <div class="item-meta">生成时间：${{esc(item.generated_at || "")}}</div>
          <div class="item-meta">推荐查看：formal_honglou_cli.py run --question "${{esc(item.question || "")}}"</div>
        </article>
      `).join("");
    }}

    function decisionOptions(current) {{
      const choices = ["待复核", "保留", "剔除", "降级", "反证"];
      return choices.map(choice => `<option value="${{esc(choice)}}" ${{choice === current ? "selected" : ""}}>${{esc(choice)}}</option>`).join("");
    }}

    function renderReview(data) {{
      const counts = data.decision_counts || {{}};
      const countText = Object.entries(counts).map(([key, value]) => `${{key}} ${{value}}`).join("｜") || "暂无复核表";
      $("result-meta").textContent = `${{data.filtered_rows}} / ${{data.total_rows}} 条｜需补字段 ${{data.incomplete_rows || 0}}｜${{countText}}`;
      const rowsHtml = data.rows.map(row => `
        <article class="item review-item" data-review-order="${{esc(row.review_order || "")}}" data-segment-no="${{esc(row.segment_no || "")}}">
          <div class="item-title">${{esc(row.review_order)}}｜${{esc(row.segment_no)}}｜第${{esc(row.chapter_no || "")}}回｜${{esc(row.machine_role || "")}}｜${{esc(row.summary || "")}}</div>
          <div class="item-meta">${{esc(row.chapter_title || "")}}｜机器优先级 ${{esc(row.priority || "")}}｜当前 ${{esc(row.normalized_decision || "待复核")}}</div>
          <div class="badge-row">
            <span class="badge ${{row.missing_fields ? "warn" : "good"}}">${{row.missing_fields ? "缺：" + esc(row.missing_fields) : "字段完整"}}</span>
          </div>
          <div class="quote">${{esc(row.quote || "")}}</div>
          <div class="reasons">机器说明：${{esc(row.machine_note || "")}}</div>
          <div class="reasons">复核问题：${{esc(row.review_question || "")}}</div>
          <div class="review-grid">
            <div>
              <label>判断</label>
              <select class="review-decision">${{decisionOptions(row.normalized_decision || row.human_decision || "待复核")}}</select>
            </div>
            <div>
              <label>等级</label>
              <input class="review-level" value="${{esc(row.usable_level || "")}}" placeholder="A/B/C">
            </div>
            <div>
              <label>角色</label>
              <input class="review-role" value="${{esc(row.human_role || "")}}" placeholder="主证/辅证/背景">
            </div>
            <div>
              <label>写作用途</label>
              <input class="review-use" value="${{esc(row.writing_use || row.suggested_section || "")}}">
            </div>
            <textarea class="review-note" placeholder="人工备注">${{esc(row.human_note || "")}}</textarea>
          </div>
          <div class="review-actions">
            <button class="primary load-context" data-segment-no="${{esc(row.segment_no || "")}}">上下文</button>
            <button class="primary save-review">保存</button>
          </div>
          <div class="context-slot"></div>
        </article>
      `).join("") || '<div class="empty">没有符合条件的复核行。</div>';
      $("results").innerHTML = renderReviewProgress(data) + rowsHtml;
      document.querySelectorAll(".save-review").forEach(btn => btn.addEventListener("click", () => saveReview(btn)));
      attachContextButtons();
    }}

    function renderReviewProgress(data) {{
      const progress = data.progress || {{}};
      const counts = progress.decision_counts || data.decision_counts || {{}};
      const rate = Number(progress.completion_rate || 0);
      const safeRate = Math.max(0, Math.min(100, rate));
      const stats = [
        ["总数", progress.total_rows ?? data.total_rows ?? 0],
        ["已判断", progress.completed_rows ?? 0],
        ["待复核", counts["待复核"] || 0],
        ["保留", counts["保留"] || 0],
        ["剔除", counts["剔除"] || 0],
        ["降级", counts["降级"] || 0],
        ["反证", counts["反证"] || 0],
        ["需补字段", progress.incomplete_rows ?? data.incomplete_rows ?? 0]
      ];
      return `
        <div class="progress-panel">
          <div class="progress-title">
            <span>复核进度</span>
            <span>${{esc(safeRate)}}%</span>
          </div>
          <div class="progress-track"><div class="progress-fill" style="width:${{safeRate}}%"></div></div>
          <div class="stat-grid">
            ${{stats.map(([label, value]) => `
              <div class="stat-item">
                <div class="stat-value">${{esc(value)}}</div>
                <div class="stat-label">${{esc(label)}}</div>
              </div>
            `).join("")}}
          </div>
        </div>
      `;
    }}

    async function loadReview() {{
      const limit = encodeURIComponent($("review-limit").value || "20");
      const decision = encodeURIComponent($("review-filter").value || "待复核");
      renderReview(await getJSON(`/api/review?limit=${{limit}}&decision=${{decision}}`));
    }}

    function renderArticleFiles(files) {{
      const rows = (files || []).filter(file => file.path || file.exists);
      if (!rows.length) return '<div class="reasons">尚未记录可读文章文件。</div>';
      return `
        <div class="badge-row">
          ${{rows.map(file => `<span class="badge ${{file.exists ? "good" : "warn"}}">${{esc(file.label)}}${{file.exists ? "" : "｜未生成"}}</span>`).join("")}}
        </div>
        ${{rows.slice(0, 3).map(file => `
          <div class="meta-kv">${{esc(file.label)}}：${{esc(file.path || "")}}</div>
          ${{file.excerpt ? `<div class="workflow-excerpt">${{renderAnswerMarkdown(file.excerpt)}}</div>` : ""}}
        `).join("")}}
      `;
    }}

    function renderArticles(data) {{
      const records = data.records || [];
      $("result-meta").textContent = `文章记录 ${{records.length}} 条｜总档案：${{data.archive_md || ""}}`;
      if (!records.length) {{
        $("results").innerHTML = '<div class="empty">还没有可读文章记录。</div>';
        return;
      }}
      $("results").innerHTML = records.map(record => `
        <article class="item article-record" data-request-id="${{esc(record.request_id || "")}}">
          <div class="item-title">${{esc(record.question_short || record.question || "未记录问题")}}</div>
          <div class="item-meta">状态：${{esc(record.status || "")}}｜请求：${{esc(record.request_id || "")}}｜更新：${{esc(record.updated_at || "")}}</div>
          <div class="reasons">工程包：${{esc(record.workflow_package || "尚未生成")}}</div>
          <div class="reasons">红楼解语：${{esc(record.answer_md || "尚未生成")}}</div>
          ${{renderArticleFiles(record.article_files)}}
          <div class="review-actions">
            <button class="primary open-article" data-request-id="${{esc(record.request_id || "")}}">查看文章</button>
            <button class="primary ingest-article" data-request-id="${{esc(record.request_id || "")}}" ${{record.ingest_ready ? "" : "disabled"}}>入库程序</button>
          </div>
          <div class="context-slot"></div>
        </article>
      `).join("");
      document.querySelectorAll(".open-article").forEach(btn => btn.addEventListener("click", () => openArticleRecord(btn)));
      document.querySelectorAll(".ingest-article").forEach(btn => btn.addEventListener("click", () => ingestArticleRecord(btn)));
    }}

    async function loadArticles() {{
      const limit = encodeURIComponent($("article-limit").value || "30");
      renderArticles(await getJSON(`/api/articles?limit=${{limit}}`));
    }}

    function rememberTalkData(data) {{
      if (!data) return;
      const liveRequestId = data.live_reply?.request_id || "";
      if (liveRequestId && data.live_reply?.reply_role === "live_reply") {{
        try {{
          localStorage.setItem("honglou:lastLiveReplyRequestId", liveRequestId);
        }} catch (err) {{}}
      }}
      if (!data.request_id) {{
        syncMachineExportButton();
        return;
      }}
      try {{
        localStorage.setItem("honglou:lastRequestId", data.request_id);
      }} catch (err) {{}}
      syncMachineExportButton();
    }}

    function lastRememberedRequestId() {{
      try {{
        return localStorage.getItem("honglou:lastRequestId") || "";
      }} catch (err) {{
        return "";
      }}
    }}

    function lastRememberedLiveReplyRequestId() {{
      try {{
        return localStorage.getItem("honglou:lastLiveReplyRequestId") || "";
      }} catch (err) {{
        return "";
      }}
    }}

    function syncMachineExportButton() {{
      const buttons = [
        $("export-machine-pack"),
        $("process-export"),
        $("left-process-export"),
        $("process-continuous-export"),
        $("left-process-continuous-export"),
        $("export-single-action"),
        $("export-continuous-action")
      ].filter(Boolean);
      const last = state.lastTalkData || {{}};
      const ready = Boolean(last.request_id || last.question_key);
      buttons.forEach(btn => {{
        btn.disabled = !ready;
        btn.title = ready
          ? "导出当前这一问的红楼解语、问题拆解、证据页、材料池和工程追溯包。"
          : "先提交或恢复一个红楼解语，再导出本问或连续导出。";
      }});
      const stopBtn = $("stop-talk");
      if (!stopBtn) return;
      const queueStatus = last.queue_status || last.processing?.status || "";
      const active = Boolean(last.request_id) && (
        activeTalkStatuses.has(queueStatus) ||
        last.answer_state === "waiting_for_codex" ||
        last.answer_state === "blocked_by_active_processing"
      );
      stopBtn.disabled = !active;
      stopBtn.title = active ? "停止当前红楼解语运算，释放入口。" : "当前没有需要停止的红楼解语。";
    }}

    function canRenderTalkRecord(data) {{
      return Boolean(data && data.request_id && (data.talk_markdown || data.answer_state || (data.workflow && data.workflow.ready)));
    }}

    function liveReplyCanRender(reply) {{
      return Boolean(reply && reply.request_id && (reply.answer_markdown || reply.answer_state));
    }}

    function renderLiveReplyOnly(reply) {{
      const payload = {{
        question: reply.question || "",
        display_question: reply.question || "",
        live_reply: reply,
        answer_state: reply.answer_state === "rejected" ? "rejected" : "answered",
        workflow: {{ready: false}},
      }};
      renderTalk(payload);
      startLiveReplyPolling(payload);
    }}

    function renderTalkHistory(data) {{
      const records = data.records || [];
      $("result-title").textContent = "红楼解语回显记录";
      $("result-meta").textContent = `可回显记录 ${{records.length}} 条｜总档案：${{data.archive_md || ""}}`;
      if (!records.length) {{
        $("results").innerHTML = '<div class="empty">还没有可恢复的红楼解语记录。</div>';
        return;
      }}
      $("results").innerHTML = records.map(record => `
        <article class="item talk-record" data-request-id="${{esc(record.request_id || "")}}">
          <div class="item-title">${{esc(record.question_short || record.question || "未记录问题")}}</div>
          <div class="item-meta">状态：${{esc(record.status || "")}}｜请求：${{esc(record.request_id || "")}}｜更新：${{esc(record.updated_at || "")}}</div>
          <div class="reasons">红楼解语：${{esc(record.answer_md || "尚未生成")}}</div>
          <div class="reasons">工程包：${{esc(record.workflow_package || "尚未生成")}}</div>
          <div class="review-actions">
            <button class="primary open-talk-record" data-request-id="${{esc(record.request_id || "")}}">打开回显</button>
          </div>
        </article>
      `).join("");
      document.querySelectorAll(".open-talk-record").forEach(btn => btn.addEventListener("click", () => openTalkRecord(btn)));
    }}

    async function openTalkRecord(button) {{
      const requestId = button.dataset.requestId || "";
      await run("restore-talk", button, async () => {{
        const data = await getJSON(`/api/talk-status?request_id=${{encodeURIComponent(requestId)}}`);
        renderTalk(data);
        startTalkPolling(data);
      }});
    }}

    async function loadTalkHistory() {{
      renderTalkHistory(await getJSON("/api/recent-talk?limit=20"));
    }}

    async function restoreLatestTalk(silent = false) {{
      let data = null;
      const remembered = lastRememberedRequestId();
      if (!silent) {{
        $("result-meta").textContent = "正在恢复最近回显";
      }}
      if (remembered) {{
        try {{
          data = await getJSON(`/api/talk-status?request_id=${{encodeURIComponent(remembered)}}`);
        }} catch (err) {{
          data = null;
        }}
      }}
      if (!canRenderTalkRecord(data)) {{
        const recent = await getJSON("/api/recent-talk?limit=12");
        data = recent.latest || null;
      }}
      if (canRenderTalkRecord(data)) {{
        renderTalk(data);
        startTalkPolling(data);
      }} else if (!silent) {{
        $("result-meta").textContent = "暂无可恢复回显";
        $("results").innerHTML = '<div class="empty">还没有可恢复的红楼解语记录。</div>';
      }}
    }}

    async function openArticleRecord(button) {{
      const requestId = encodeURIComponent(button.dataset.requestId || "");
      await run("article-open", button, async () => {{
        const data = await getJSON(`/api/talk-status?request_id=${{requestId}}`);
        renderTalk(data);
      }});
    }}

    async function ingestArticleRecord(button) {{
      const requestId = encodeURIComponent(button.dataset.requestId || "");
      await run("article-ingest", button, async () => {{
        const data = await getJSON(`/api/article-ingest?request_id=${{requestId}}`);
        renderArticleIngest(data);
      }});
    }}

    async function ingestCurrentArticle() {{
      const last = state.lastTalkData || {{}};
      const requestId = last.request_id || "";
      if (!requestId) {{
        $("result-meta").textContent = "还没有当前问题记录";
        $("results").innerHTML = '<div class="answer-wait">请先提交一次问题并等工程生成结果，再按“文章入库”。</div>';
        return;
      }}
      await run("article-ingest-current", $("ingest-current-article"), async () => {{
        const data = await getJSON(`/api/article-ingest?request_id=${{encodeURIComponent(requestId)}}`);
        renderArticleIngest(data);
      }});
    }}

    function renderMachineExportNotice() {{
      const data = state.lastMachineExport;
      if (!data) return "";
      const last = state.lastTalkData || {{}};
      if (data.request_id && last.request_id && data.request_id !== last.request_id) return "";
      const scorecard = data.flow_scorecard || {{}};
      const corrections = data.auto_corrections || [];
      const scoreItems = scorecard.items || [];
      const qa = data.qa_export || {{}};
      const answerText = qa.answer || "";
      const answerPreview = answerText.length > 1600 ? answerText.slice(0, 1600).trimEnd() + "…" : answerText;
      const scoreHtml = scoreItems.length ? `
        <div class="table-scroll">
          <table>
            <thead><tr><th>流程</th><th>分数</th><th>状态</th><th>问题</th><th>建议</th></tr></thead>
            <tbody>
              ${{scoreItems.map(item => `
                <tr>
                  <td>${{esc(item.stage || "")}}</td>
                  <td>${{esc(item.score ?? "")}} / 10</td>
                  <td>${{esc(item.status || "")}}</td>
                  <td>${{esc(item.problem || "无")}}</td>
                  <td>${{esc(item.next_action || "")}}</td>
                </tr>
              `).join("")}}
            </tbody>
          </table>
        </div>
      ` : "";
      const correctionHtml = corrections.length ? `
        <div class="answer-title">问题与修改意见（待人工审核）</div>
        ${{corrections.map(item => `
          <div class="context-box">
            <div class="item-title">${{esc(item.stage || "")}}｜${{esc(item.severity || "")}}</div>
            <div class="reasons">诊断：${{esc(item.diagnosis || "")}}</div>
            <div class="reasons">修改意见：${{esc(item.suggestion || "")}}</div>
            <div class="meta-kv">安全自动动作：${{esc(item.safe_auto_action || "")}}</div>
          </div>
        `).join("")}}
      ` : '<div class="reasons">本次没有发现需要优化的流程问题。</div>';
      return `
        <article class="item machine-export-card">
          <div class="item-title">本问工程包导出完成</div>
          <div class="item-meta">请求：${{esc(data.request_id || "")}}｜节点：${{esc(data.node_count || 0)}}｜流程总分：${{esc(scorecard.overall_score ?? "未评分")}} / 10｜阻断：${{esc(scorecard.blocking_count || 0)}}</div>
          <div class="reasons">${{esc(data.purpose || "")}}</div>
          <div class="answer-title">本问一问一答</div>
          <div class="context-box">
            <div class="item-title">问</div>
            <div class="quote">${{esc(qa.question || "未记录问题。")}}</div>
            <div class="item-title">红楼解语</div>
            <div class="quote">${{esc(answerPreview || "尚未写回红楼解语。")}}</div>
          </div>
          <div class="answer-title">流程评分卡</div>
          ${{scoreHtml}}
          ${{correctionHtml}}
          ${{data.continuous ? `<div class="meta-kv">连续导出页：${{esc(data.continuous_markdown || "")}}｜第 ${{esc(data.continuous_entry_no || "")}} 问</div>` : ""}}
          <div class="meta-kv">落地目录：${{esc(data.export_dir || "")}}</div>
          <div class="meta-kv">JSON：${{esc(data.json || "")}}</div>
          <div class="meta-kv">Markdown：${{esc(data.markdown || "")}}</div>
        </article>
      `;
    }}

    function renderFlowScoreNotice() {{
      const data = state.lastTalkData || {{}};
      if (!data.request_id && !data.question_key) return "";
      const scorecard = data.flow_scorecard || {{}};
      const scoreItems = scorecard.items || [];
      const corrections = data.auto_corrections || [];
      const scoreHtml = scoreItems.length ? `
        <div class="table-scroll">
          <table>
            <thead><tr><th>流程</th><th>分数</th><th>状态</th><th>问题</th><th>下一步</th></tr></thead>
            <tbody>
              ${scoreItems.map(item => `
                <tr>
                  <td>${{esc(item.stage || "")}}</td>
                  <td>${{esc(item.score ?? "")}} / 10</td>
                  <td>${{esc(item.status || "")}}</td>
                  <td>${{esc(item.problem || "无")}}</td>
                  <td>${{esc(item.next_action || "")}}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      ` : "";
      const correctionHtml = corrections.length ? `
        <div class="answer-title">问题与修改意见（待人工审核）</div>
        ${corrections.map(item => `
          <div class="context-box">
            <div class="item-title">${{esc(item.stage || "")}}｜${{esc(item.severity || "")}}</div>
            <div class="reasons">诊断：${{esc(item.diagnosis || "需要补齐该环节信息")}}</div>
            <div class="reasons">修改意见：${{esc(item.suggestion || "")}}</div>
            <div class="meta-kv">安全自动动作：${{esc(item.safe_auto_action || "")}}</div>
          </div>
        `).join("")}
      ` : '<div class="reasons">当前阶段没有生成明显问题单。继续观察后续节点。</div>';
      return `
        <article class="item machine-export-card">
          <div class="item-title">实时流程评分</div>
          <div class="item-meta">请求：${{esc(data.request_id || "")}}｜节点：${{esc(scorecard.node_count ?? (scoreItems.length || 0))}}｜流程总分：${{esc(scorecard.overall_score ?? "未评分")}} / 10｜阻断：${{esc(scorecard.blocking_count || 0)}}</div>
          <div class="reasons">若当前无可打分文件，说明流程正在收口中；后续轮询会自动补全。</div>
          ${{scoreHtml ? `<div class="answer-title">流程评分卡</div>${{scoreHtml}}` : ""}}
          ${{scoreItems.length ? `<div class="reasons">当前阻断：${{esc((scorecard.blocking_stages || []).join("，") || "无")}}</div>` : ""}}
          ${{correctionHtml}}
        </article>
      `;
    }}

    async function exportMachinePack(sourceButton) {{
      const btn = sourceButton?.currentTarget || sourceButton || $("export-machine-pack");
      const last = state.lastTalkData || {{}};
      const requestId = last.request_id || "";
      const questionKey = last.question_key || "";
      if (!requestId && !questionKey) {{
        $("result-meta").textContent = "请先提交或恢复一个红楼解语，再导出本问工程包";
        return;
      }}
      const oldLabel = btn ? btn.textContent : "";
      if (btn) {{
        btn.disabled = true;
        btn.textContent = "导出中";
      }}
      $("result-meta").textContent = "正在导出本问工程包";
      try {{
        const data = await getJSON(`/api/talk/export?request_id=${{encodeURIComponent(requestId)}}&question_key=${{encodeURIComponent(questionKey)}}`);
        state.lastMachineExport = data;
        state.processTab = "export";
        $("result-meta").textContent = `已导出本问工程包｜节点 ${{data.node_count || 0}}`;
        const latest = $("export-latest");
        const panel = $("process-content");
        if (latest) {{
          latest.innerHTML = renderMachineExportNotice();
        }} else if (panel) {{
          panel.innerHTML = renderMachineExportNotice();
        }} else {{
          document.querySelectorAll(".machine-export-card").forEach(card => card.remove());
          $("results").insertAdjacentHTML("afterbegin", renderMachineExportNotice());
        }}
        activateProcessButtons();
        if ($("export-history")) loadExportHistory();
      }} catch (err) {{
        $("result-meta").textContent = "导出失败";
        const errorHtml = `<div class="error">本问工程包导出失败：${{esc(err.message || err)}}</div>`;
        const panel = $("process-content");
        if (panel) panel.innerHTML = errorHtml;
        else $("results").insertAdjacentHTML("afterbegin", errorHtml);
      }} finally {{
        if (btn) btn.textContent = oldLabel;
        syncMachineExportButton();
      }}
    }}

    async function exportContinuousPack(sourceButton) {{
      const btn = sourceButton?.currentTarget || sourceButton || $("process-continuous-export");
      const last = state.lastTalkData || {{}};
      const requestId = last.request_id || "";
      const questionKey = last.question_key || "";
      if (!requestId && !questionKey) {{
        $("result-meta").textContent = "请先提交或恢复一个红楼解语，再连续导出";
        return;
      }}
      const oldLabel = btn ? btn.textContent : "";
      if (btn) {{
        btn.disabled = true;
        btn.textContent = "追加中";
      }}
      $("result-meta").textContent = "正在连续导出";
      try {{
        const data = await getJSON(`/api/talk/export-continuous?request_id=${{encodeURIComponent(requestId)}}&question_key=${{encodeURIComponent(questionKey)}}`);
        state.lastMachineExport = data;
        state.processTab = "export";
        $("result-meta").textContent = `已连续导出｜第 ${{data.continuous_entry_no || ""}} 问`;
        const latest = $("export-latest");
        const panel = $("process-content");
        if (latest) {{
          latest.innerHTML = renderMachineExportNotice();
        }} else if (panel) {{
          panel.innerHTML = renderMachineExportNotice();
        }} else {{
          document.querySelectorAll(".machine-export-card").forEach(card => card.remove());
          $("results").insertAdjacentHTML("afterbegin", renderMachineExportNotice());
        }}
        activateProcessButtons();
        if ($("export-history")) loadExportHistory();
      }} catch (err) {{
        $("result-meta").textContent = "连续导出失败";
        const errorHtml = `<div class="error">连续导出失败：${{esc(err.message || err)}}</div>`;
        const latest = $("export-latest");
        const panel = $("process-content");
        if (latest) latest.innerHTML = errorHtml;
        else if (panel) panel.innerHTML = errorHtml;
        else $("results").insertAdjacentHTML("afterbegin", errorHtml);
      }} finally {{
        if (btn) btn.textContent = oldLabel;
        syncMachineExportButton();
      }}
    }}

    async function stopTalk() {{
      const btn = $("stop-talk");
      const last = state.lastTalkData || {{}};
      const requestId = last.request_id || "";
      if (!requestId) {{
        $("result-meta").textContent = "当前没有正在运行的红楼解语";
        return;
      }}
      const oldLabel = btn.textContent;
      btn.disabled = true;
      btn.textContent = "停止中";
      $("result-meta").textContent = "正在停止解语";
      try {{
        const data = await getJSON(`/api/talk/stop?request_id=${{encodeURIComponent(requestId)}}`);
        stopTalkPolling();
        stopLiveReplyPolling();
        state.lastTalkData = {{
          ...last,
          request_id: data.request_id || requestId,
          status: data.status || "已停止解语。",
          queue_status: data.queue_status || "已终止",
          answer_state: data.stopped ? "stopped" : (last.answer_state || "waiting_for_codex"),
          queue_error: data.status || ""
        }};
        $("result-meta").textContent = data.status || "已停止解语";
        document.querySelectorAll(".stop-talk-card").forEach(card => card.remove());
        $("results").insertAdjacentHTML("afterbegin", `
          <article class="item stop-talk-card">
            <div class="item-title">停止解语</div>
            <div class="item-meta">请求：${{esc(data.request_id || requestId)}}｜状态：${{esc(data.queue_status || "")}}</div>
            <div class="reasons">${{esc(data.status || "")}}</div>
          </article>
        `);
      }} catch (err) {{
        $("result-meta").textContent = "停止解语失败";
        $("results").insertAdjacentHTML("afterbegin", `<div class="error">停止解语失败：${{esc(err.message || err)}}</div>`);
      }} finally {{
        btn.textContent = oldLabel;
        syncMachineExportButton();
      }}
    }}

    function renderArticleIngest(data) {{
      const preview = data.article_ingest_preview || {{}};
      const files = [
        ["预检报告", preview.report_md],
        ["候选行", preview.candidate_csv],
        ["回挂清单", preview.links_csv],
        ["身份卡", preview.identity_md],
        ["预检摘要", preview.summary_json]
      ];
      $("result-meta").textContent = data.status || "文章入库预检已完成";
      $("results").innerHTML = `
        <article class="item">
          <div class="item-title">文章入库程序</div>
          <div class="item-meta">请求：${{esc(data.request_id || "")}}｜工程包：${{esc(data.package || "")}}</div>
          <div class="reasons">${{esc(data.status || "")}}</div>
          <div class="badge-row">
            ${{files.map(([label, path]) => `<span class="badge ${{path ? "good" : "warn"}}">${{esc(label)}}</span>`).join("")}}
          </div>
          ${{files.map(([label, path]) => `<div class="meta-kv">${{esc(label)}}：${{esc(path || "未生成")}}</div>`).join("")}}
          <div class="answer-title">预检报告</div>
          <div class="answer-box">${{renderAnswerMarkdown(data.report_excerpt || "预检报告尚未生成。")}}</div>
          ${{data.identity_excerpt ? `<div class="answer-title">身份卡</div><div class="answer-box">${{renderAnswerMarkdown(data.identity_excerpt)}}</div>` : ""}}
          ${{renderWorkflowRows(data.links_preview || [])}}
        </article>
      `;
    }}

    function attachContextButtons() {{
      document.querySelectorAll(".load-context").forEach(btn => {{
        btn.addEventListener("click", () => loadSegmentContext(btn));
      }});
    }}

    async function loadSegmentContext(button) {{
      const item = button.closest(".item");
      const slot = item.querySelector(".context-slot");
      if (slot.dataset.open === "1") {{
        slot.innerHTML = "";
        slot.dataset.open = "0";
        button.textContent = "上下文";
        return;
      }}
      button.disabled = true;
      button.textContent = "读取中";
      try {{
        const segmentNo = encodeURIComponent(button.dataset.segmentNo || item.dataset.segmentNo || "");
        const data = await getJSON(`/api/segment-context?segment_no=${{segmentNo}}&window=2`);
        slot.innerHTML = renderSegmentContext(data);
        slot.dataset.open = "1";
        button.textContent = "收起";
      }} catch (err) {{
        slot.innerHTML = `<div class="error">${{esc(err.message || err)}}</div>`;
        slot.dataset.open = "1";
        button.textContent = "上下文";
      }} finally {{
        button.disabled = false;
      }}
    }}

    function renderSegmentContext(data) {{
      const rows = data.context || [];
      return `
        <div class="context-box">
          <div class="item-meta">${{esc(data.target?.chapter_label || "")}}｜当前段落 ${{esc(data.segment_no)}}｜前后 ${{esc(data.window)}} 段</div>
          ${{rows.map(row => `
            <div class="context-row ${{row.is_current ? "current" : ""}}">
              <div class="item-title">${{esc(row.segment_no)}}｜顺序 ${{esc(row.segment_order || "")}}｜${{row.is_current ? "当前证据" : "上下文"}}</div>
              <div class="item-meta">${{esc([row.scene_place, row.time_point, row.function_tags, row.note_dimension].filter(Boolean).join("｜"))}}</div>
              <div class="reasons">摘要：${{esc(row.summary || "")}}</div>
              <div class="quote">${{esc(row.quote || "")}}</div>
            </div>
          `).join("")}}
        </div>
      `;
    }}

    async function saveReview(button) {{
      const item = button.closest(".review-item");
      const payload = reviewPayloadFromItem(item);
      await run("review-save", button, async () => {{
        await postJSON("/api/review/update", payload);
        await loadReview();
        $("result-meta").textContent = "已保存，并已刷新复核回读与反馈排序配置";
      }});
    }}

    function reviewPayloadFromItem(item) {{
      return {{
        review_order: item.dataset.reviewOrder,
        segment_no: item.dataset.segmentNo,
        question: currentQuestion(),
        human_decision: item.querySelector(".review-decision").value,
        human_role: item.querySelector(".review-role").value,
        usable_level: item.querySelector(".review-level").value,
        writing_use: item.querySelector(".review-use").value,
        human_note: item.querySelector(".review-note").value
      }};
    }}

    async function saveVisibleReviews() {{
      const items = Array.from(document.querySelectorAll(".review-item"));
      if (!items.length) {{
        $("result-meta").textContent = "当前没有可保存的复核行";
        return;
      }}
      const payloads = items.map(reviewPayloadFromItem);
      await run("review-batch-save", $("batch-save-review"), async () => {{
        const result = await postJSON("/api/review/batch-update", {{ rows: payloads }});
        await loadReview();
        $("result-meta").textContent = `已批量保存 ${{result.updated_count || 0}} 条，并已刷新复核回读与反馈排序配置`;
      }});
    }}

    async function exportCurrentReview() {{
      const limit = encodeURIComponent($("review-limit").value || "20");
      const decision = encodeURIComponent($("review-filter").value || "待复核");
      await run("review-export", $("export-review"), async () => {{
        const result = await getJSON(`/api/review/export?limit=${{limit}}&decision=${{decision}}`);
        $("result-meta").textContent = `已导出 ${{result.exported_rows || 0}} 条复核结果`;
        $("results").insertAdjacentHTML("afterbegin", `
          <div class="context-box">
            <div class="item-title">导出完成</div>
            <div class="reasons">CSV：${{esc(result.csv || "")}}</div>
            <div class="reasons">Markdown：${{esc(result.markdown || "")}}</div>
          </div>
        `);
      }});
    }}

    function applyBulkDefaults() {{
      const items = Array.from(document.querySelectorAll(".review-item"));
      if (!items.length) {{
        $("result-meta").textContent = "当前没有可应用默认值的复核行";
        return;
      }}
      const values = {{
        decision: $("bulk-decision").value,
        level: $("bulk-level").value,
        role: $("bulk-role").value,
        use: $("bulk-use").value,
        emptyOnly: $("bulk-empty-only").checked
      }};
      let changed = 0;
      for (const item of items) {{
        const targets = [
          [".review-decision", values.decision],
          [".review-level", values.level],
          [".review-role", values.role],
          [".review-use", values.use]
        ];
        for (const [selector, value] of targets) {{
          if (!value) continue;
          const field = item.querySelector(selector);
          if (!field) continue;
          if (values.emptyOnly && String(field.value || "").trim()) continue;
          if (field.value !== value) {{
            field.value = value;
            changed += 1;
          }}
        }}
      }}
      $("result-meta").textContent = `已应用批量默认值，改动 ${{changed}} 个字段；确认后请批量保存`;
    }}

    async function run(kind, button, fn) {{
      button.disabled = true;
      $("result-meta").textContent = "处理中";
      if (kind === "codex-answer") {{
        stopTalkPolling();
        stopLiveReplyPolling();
        $("results").innerHTML = '<div class="answer-wait">Codex 回答台正在接收问题...\\n本窗口不会显示本地模块临时答案。</div>';
        state.lastTalkData = {};
        state.lastMachineExport = null;
        syncMachineExportButton();
      }} else {{
        $("results").innerHTML = '<div class="empty">正在处理。</div>';
      }}
      try {{
        await fn();
      }} catch (err) {{
        $("result-meta").textContent = "出错";
        $("results").innerHTML = `<div class="error">${{esc(err.message || err)}}</div>`;
      }} finally {{
        button.disabled = false;
      }}
    }}

    document.querySelectorAll(".tab").forEach(btn => btn.addEventListener("click", () => setMode(btn.dataset.mode)));
    document.querySelectorAll('input[name="answer-style"]').forEach(input => input.addEventListener("change", updateRoutePreview));
    function codexWindowIntent(windowName) {{
      return `${{currentTaskIntent()}}｜当前回答窗口：${{windowName}}｜入口规矩：本问题必须直接进入红楼梦工程真实运转；Codex 先读取聚拢总图入口包、图内读法、现成编号入口门、材料池精读门和经验仓，再判断图内入口线索、聚拢层级、穷尽补点、材料来源与补查方向；若 Codex 判断本题涉及物象、信物、器具、植物、陈设或空间物，再调用正式物象库 objects_axis，并走通用物象证据簇：物象轴→原子段→人物/事件/空间/诗词/证据边→原文上下文→材料池；本地程序只执行查询、取证、保存和回显，不自动猜题；所有候选必须回原文复核后进入材料池；红楼解语区只显示 Codex 基于工程产物写出的最终回答，过程材料固定显示在工程运转结果区；经验规矩：经验、经验值、经验复盘、经验提取、经验总结、经验入账、增加经验值都归入同一套经验流程，每题自动经验入账，结果出来后可手动补充成败原因。`;
    }}

    async function requestCodexWindow(button, windowName) {{
      await run("codex-answer", button, async () => {{
        const question = encodeURIComponent(requireQuestion());
        const top_n = encodeURIComponent($("common-talk-top-n").value || "10");
        const task_intent = encodeURIComponent(codexWindowIntent(windowName));
        const requirements = encodeURIComponent(currentRequirements());
        const data = await getJSON(`/api/talk?question=${{question}}&top_n=${{top_n}}&task_intent=${{task_intent}}&requirements=${{requirements}}`);
        renderTalk(data);
        startTalkPolling(data);
      }});
    }}

    $("run-workflow-search").addEventListener("click", () => requestCodexWindow($("run-workflow-search"), "查原文"));
    $("run-workflow-evidence").addEventListener("click", () => requestCodexWindow($("run-workflow-evidence"), "证据"));
    $("run-workflow-decompose").addEventListener("click", () => requestCodexWindow($("run-workflow-decompose"), "问题拆解"));
    $("run-workflow-research").addEventListener("click", () => requestCodexWindow($("run-workflow-research"), "文稿/材料池"));
    $("run-workflow-talk").addEventListener("click", () => requestCodexWindow($("run-workflow-talk"), "红楼解语"));
    $("run-simple-talk").addEventListener("click", () => requestCodexWindow($("run-simple-talk"), "红楼解语"));
    $("run-talk").addEventListener("click", () => requestCodexWindow($("run-talk"), "现场对答"));

    function mergeTalkData(data) {{
      const base = state.lastTalkData || {{}};
      const merged = {{...base, ...data}};
      ["question", "task_intent", "requirements", "status_file", "pending_md"].forEach(key => {{
        if (!data[key] && base[key]) merged[key] = base[key];
      }});
      state.lastTalkData = merged;
      return merged;
    }}

    function stopTalkPolling() {{
      if (state.talkPollTimer) {{
        clearInterval(state.talkPollTimer);
        state.talkPollTimer = null;
      }}
    }}

    function stopLiveReplyPolling() {{
      if (state.liveReplyPollTimer) {{
        clearInterval(state.liveReplyPollTimer);
        state.liveReplyPollTimer = null;
      }}
      state.liveReplyPollRequestId = "";
    }}

    function liveReplyIsDone(liveReply) {{
      const replyState = liveReply?.answer_state || "";
      return ["answered", "failed", "rejected", "empty"].includes(replyState);
    }}

    function startLiveReplyPolling(data) {{
      const liveReply = data?.live_reply || {{}};
      if (liveReply.reply_role !== "live_reply") return;
      const requestId = liveReply.request_id || "";
      if (!requestId || liveReplyIsDone(liveReply)) {{
        if (requestId && state.liveReplyPollRequestId === requestId) stopLiveReplyPolling();
        return;
      }}
      if (state.liveReplyPollTimer && state.liveReplyPollRequestId === requestId) return;
      stopLiveReplyPolling();
      state.liveReplyPollRequestId = requestId;
      state.liveReplyPollTimer = setInterval(async () => {{
        try {{
          const reply = await getJSON(`/api/reader-direct-answer-status?request_id=${{encodeURIComponent(requestId)}}`);
          const base = state.lastTalkData || {{}};
          const merged = {{
            ...base,
            live_reply: reply,
            display_question: base.display_question || reply.question || base.question || "",
            blocked_question: base.blocked_question || "",
          }};
          renderTalk(merged);
          if (liveReplyIsDone(reply)) stopLiveReplyPolling();
        }} catch (err) {{
          stopLiveReplyPolling();
        }}
      }}, 2500);
    }}

    function startTalkPolling(data) {{
      stopTalkPolling();
      startLiveReplyPolling(data);
      if (!data || ["answered", "rejected", "stopped", "stale_ignored", "blocked_by_active_processing"].includes(data.answer_state)) return;
      const questionKey = data.question_key || "";
      const requestId = data.request_id || "";
      if (!questionKey && !requestId) return;
      const interval = Number(data.poll_after_ms || 3000);
        state.talkPollTimer = setInterval(async () => {{
          try {{
            const q = encodeURIComponent(questionKey);
            const rid = encodeURIComponent(requestId);
            const poll = await getJSON(`/api/talk-status?question_key=${{q}}&request_id=${{rid}}`);
            renderTalk(poll);
            startLiveReplyPolling(poll);
            if (["answered", "rejected", "stopped", "stale_ignored"].includes(poll.answer_state)) stopTalkPolling();
          }} catch (err) {{
            renderTalk({
              request_id: requestId,
              question_key: questionKey,
              status: `等待红楼解语｜轮询暂时失败：${{err.message || err}}`,
              talk_markdown: "",
              answer_checked: false,
              answer_file: "",
              answer_signature: "",
              answer_state: "waiting_for_codex",
            });
          }}
        }}, interval);
      }}

    function inlineMarkdown(text) {{
      return esc(text).replace(/`([^`]+)`/g, "<code>$1</code>");
    }}

    function renderAnswerMarkdown(markdown) {{
      const lines = String(markdown || "").replace(/\\r\\n/g, "\\n").split("\\n");
      const html = [];
      let inList = false;
      let inCode = false;
      let codeLines = [];
      const closeList = () => {{
        if (inList) {{
          html.push("</ul>");
          inList = false;
        }}
      }};
      const closeCode = () => {{
        if (inCode) {{
          html.push(`<pre><code>${{esc(codeLines.join("\\n"))}}</code></pre>`);
          codeLines = [];
          inCode = false;
        }}
      }};
      for (const line of lines) {{
        const trimmed = line.trim();
        if (trimmed.startsWith("```")) {{
          closeList();
          if (inCode) closeCode();
          else inCode = true;
          continue;
        }}
        if (inCode) {{
          codeLines.push(line);
          continue;
        }}
        if (!trimmed) {{
          closeList();
          continue;
        }}
        if (trimmed.startsWith("### ")) {{
          closeList();
          html.push(`<h3>${{inlineMarkdown(trimmed.slice(4))}}</h3>`);
          continue;
        }}
        if (trimmed.startsWith("## ")) {{
          closeList();
          html.push(`<h2>${{inlineMarkdown(trimmed.slice(3))}}</h2>`);
          continue;
        }}
        if (trimmed.startsWith("# ")) {{
          closeList();
          html.push(`<h1>${{inlineMarkdown(trimmed.slice(2))}}</h1>`);
          continue;
        }}
        if (trimmed.startsWith("- ")) {{
          if (!inList) {{
            html.push("<ul>");
            inList = true;
          }}
          html.push(`<li>${{inlineMarkdown(trimmed.slice(2))}}</li>`);
          continue;
        }}
        closeList();
        html.push(`<p>${{inlineMarkdown(trimmed)}}</p>`);
      }}
      closeCode();
      closeList();
      return html.join("");
    }}

    function renderWorkflowRows(rows) {{
      if (!rows || !rows.length) return "";
      const keys = [
        "title", "kind", "source_position", "url", "note", "id",
        "segment_no", "chapter_no", "evidence_role", "machine_role", "human_role",
        "codex_original_passages", "same_chapter_passage_segments", "quote", "summary",
        "context_excerpt", "source_trace", "object_axis_hits", "person_axis_hits",
        "subquestion", "hit_subquestions", "review_question",
        "review_order", "review_sequence", "workbench_group", "coverage_question",
        "priority", "triage_priority", "reason", "triage_note", "next_question",
        "search_terms", "状态", "status"
      ];
      const available = keys.filter(key => rows.some(row => row && row[key]));
      const shown = available.slice(0, 5);
      if (!shown.length) return "";
      const compactCell = (key, value) => {{
        const text = String(value || "");
        const limits = {{
          codex_original_passages: 260,
          same_chapter_passage_segments: 260,
          quote: 220,
          context_excerpt: 220,
          summary: 180,
          source_trace: 180,
          object_axis_hits: 160,
          person_axis_hits: 160,
          hit_subquestions: 160,
          search_terms: 140,
          reason: 160,
          triage_note: 160,
        }};
        const limit = limits[key] || 140;
        return text.length > limit ? text.slice(0, limit).trimEnd() + "…" : text;
      }};
      const head = shown.map(key => `<th>${{esc(key)}}</th>`).join("");
      const body = rows.slice(0, 8).map(row => `<tr>${{shown.map(key => `<td title="${{esc(row[key] || "")}}">${{esc(compactCell(key, row[key]))}}</td>`).join("")}}</tr>`).join("");
      return `<div class="table-scroll"><table><thead><tr>${{head}}</tr></thead><tbody>${{body}}</tbody></table></div>`;
    }}

    function renderWorkflowProcess(data) {{
      const workflow = data.workflow || {{}};
      if (!workflow.ready) return "";
      const summary = workflow.summary || {{}};
      const summaryItems = [
        ["子问题", summary.subquestion_count],
        ["证据段落", summary.unique_segments],
        ["复核行", summary.review_rows],
        ["可用证据", summary.usable_rows],
        ["待复核", summary.pending_rows],
        ["过程文件", summary.process_file_count]
      ].filter(([, value]) => value !== undefined && value !== "" && value !== 0);
      const summaryHtml = summaryItems.length ? `
        <div class="status-grid">
          ${{summaryItems.map(([label, value]) => `<div class="status-grid-item"><div class="num">${{esc(value)}}</div><div class="label">${{esc(label)}}</div></div>`).join("")}}
        </div>
      ` : "";
      const sections = (workflow.sections || []).map((section, index) => `
        <details class="workflow-section" ${{index < 8 ? "open" : ""}}>
          <summary>${{esc(section.title)}}<span>${{esc(section.description || "")}}</span></summary>
          ${{section.path ? `<div class="meta-kv">${{esc(section.path)}}</div>` : ""}}
          ${{section.excerpt ? `<div class="workflow-excerpt">${{renderAnswerMarkdown(section.excerpt)}}</div>` : ""}}
          ${{renderWorkflowRows(section.rows)}}
        </details>
      `).join("");
      return `
        <section class="workflow-process">
          <div class="workflow-head">
            <strong>工程运转结果</strong>
            <span>${{esc(workflow.status || "红楼梦工程已生成过程材料。")}}</span>
          </div>
          ${{workflow.package ? `<div class="meta-kv">工程包：${{esc(workflow.package)}}</div>` : ""}}
          ${{summary.route_context ? `<div class="meta-kv">工程已接收触发包与 Codex 查询词路；完整内容见“Codex 查询词路”和“触发词与工程入口”。</div>` : ""}}
          ${{summaryHtml}}
          ${{sections}}
        </section>
      `;
    }}

    function renderProcessToolbar(data) {{
      const active = state.processTab || "decompose";
      const ready = Boolean(data.request_id || data.question_key);
      const tabs = [
        ["decompose", "问题拆解"],
        ["evidence", "证据页"],
        ["materials", "材料池"],
        ["export", "导出页"]
      ];
      return `
        <div class="process-toolbar">
          ${{tabs.map(([key, label]) => `<button type="button" data-process-tab="${{key}}" class="${{active === key ? "active" : ""}}">${{label}}</button>`).join("")}}
        </div>
      `;
    }}

    function processKeysForTab(tab) {{
      const groups = {{
        decompose: [
          "question_judgment_md",
          "question_tree",
          "query_strategy",
          "codex_process_judgment_md",
          "keyword_precheck_json",
          "trigger_packet"
        ],
        evidence: [
          "triaged_csv",
          "cards",
          "review_csv",
          "review_plan_md",
          "review_firstpass_cards_md",
          "source_verify_md",
          "source_verify_csv",
          "review_sheet_csv"
        ],
        materials: [
          "codex_material_judgment_md",
          "codex_close_reading_md",
          "final_reading_gate_md",
          "writing_md",
          "review_coverage_md",
          "next_plan_md",
          "codex_close_reading_gate_md",
          "codex_close_reading_target_md"
        ]
      }};
      return groups[tab] || groups.decompose;
    }}

    function processTitleForTab(tab) {{
      return ({{decompose: "问题拆解", evidence: "证据页", materials: "材料池", export: "导出本问"}})[tab] || "问题拆解";
    }}

    function processWaitingText(tab) {{
      const title = processTitleForTab(tab);
      const hints = {{
        decompose: "问题拆解页会显示问题判断、搜索词网络、查询词路和过程判别。",
        evidence: "证据页会显示候选证据、原文卡片、复核表和真源核验。",
        materials: "材料池页会显示材料池判定、精读门、复核后写作材料和补证计划。",
        export: "导出的是当前这一问的红楼解语、问题拆解、证据页、材料池和工程追溯包。"
      }};
      return `${{title}}已选中。${{hints[tab] || ""}}\\n\\n请先点左边“一问”；工程写回对应产物后，本页会自动显示。`;
    }}

    function sectionMatchesProcessTab(section, tab) {{
      if (!section) return false;
      const keys = new Set(processKeysForTab(tab));
      if (keys.has(section.key)) return true;
      const text = `${{section.title || ""}} ${{section.description || ""}} ${{section.key || ""}}`;
      const patterns = {{
        decompose: ["问题判断", "问题拆解", "搜索词", "查询词路", "过程判别", "关键词网络", "触发词"],
        evidence: ["证据池", "候选材料", "候选原文", "材料卡片", "复核表", "真源核验", "复核优先", "当前批次复核"],
        materials: ["材料池判定", "精读材料", "材料池精读", "复核后写作材料", "覆盖矩阵", "二次追问", "补证计划", "精读门"]
      }};
      return (patterns[tab] || []).some(pattern => text.includes(pattern));
    }}

    function processSectionsForTab(data, tab) {{
      const workflow = data.workflow || {{}};
      const sections = Array.isArray(workflow.sections) ? workflow.sections : [];
      return sections.filter(section => sectionMatchesProcessTab(section, tab));
    }}

    function renderProcessSection(section, index) {{
      return `
        <details class="process-section" ${{index < 2 ? "open" : ""}}>
          <summary>${{esc(section.title)}}<span>${{esc(section.description || "")}}</span></summary>
          ${{section.path ? `<div class="meta-kv">${{esc(section.path)}}</div>` : ""}}
          ${{section.excerpt ? `<div class="workflow-excerpt">${{renderAnswerMarkdown(section.excerpt)}}</div>` : ""}}
          ${{renderWorkflowRows(section.rows)}}
        </details>
      `;
    }}

    function renderExportPage() {{
      const last = state.lastTalkData || {{}};
      const ready = Boolean(last.request_id || last.question_key);
      return `
        <div class="export-actions">
          <button type="button" class="primary" id="export-single-action" ${{ready ? "" : "disabled"}}>导出本问</button>
          <button type="button" class="primary" id="export-continuous-action" ${{ready ? "" : "disabled"}}>连续导出</button>
          <span class="meta">导出本问是单独文案；连续导出会把当前这一问追加到连续导出页。</span>
        </div>
        <div id="export-latest">
          ${{state.lastMachineExport ? renderMachineExportNotice() : '<div class="process-empty">这里会显示刚导出的本问工程包或连续导出结果。</div>'}}
        </div>
        <div class="answer-title">历史导出</div>
        <div id="export-history" class="export-history-list">正在读取导出记录...</div>
        <div id="export-display"></div>
      `;
    }}

    function renderExportHistory(data) {{
      const records = data.records || [];
      state.exportHistory = records;
      if (!records.length) {{
        return '<div class="process-empty">还没有可回显的导出记录。</div>';
      }}
      return records.map((record, index) => `
        <button type="button" class="export-history-item" data-export-index="${{index}}">
          <strong>${{esc(record.kind === "continuous" ? "连续导出" : "单问导出")}}｜${{esc(record.title || "")}}</strong>
          <span class="meta-kv">${{esc(record.updated_at || "")}}</span>
          <span class="meta-kv">${{esc(record.markdown || "")}}</span>
        </button>
      `).join("");
    }}

    function showExportRecord(index) {{
      const record = (state.exportHistory || [])[Number(index)];
      const display = $("export-display");
      if (!record || !display) return;
      display.innerHTML = `
        <article class="item machine-export-card">
          <div class="item-title">${{esc(record.kind === "continuous" ? "连续导出页" : "单问导出页")}}｜${{esc(record.title || "")}}</div>
          <div class="meta-kv">Markdown：${{esc(record.markdown || "")}}</div>
          ${{record.json ? `<div class="meta-kv">JSON：${{esc(record.json || "")}}</div>` : ""}}
          <div class="answer-box">${{renderAnswerMarkdown(record.excerpt || "没有可显示内容。")}}</div>
        </article>
      `;
    }}

    async function loadExportHistory() {{
      const slot = $("export-history");
      if (!slot) return;
      slot.textContent = "正在读取导出记录...";
      try {{
        const data = await getJSON("/api/talk/export-history?limit=30");
        slot.innerHTML = renderExportHistory(data);
        slot.querySelectorAll("[data-export-index]").forEach(btn => {{
          btn.onclick = () => showExportRecord(btn.dataset.exportIndex);
        }});
        if ((data.records || []).length) showExportRecord(0);
      }} catch (err) {{
        slot.innerHTML = `<div class="error">导出记录读取失败：${{esc(err.message || err)}}</div>`;
      }}
    }}

    function renderProcessTabContent(data) {{
      const tab = state.processTab || "decompose";
      const workflow = data.workflow || {{}};
      if (tab === "export") {{
        return renderExportPage();
      }}
      if (!workflow.ready) {{
        return `<div class="process-empty">${{esc(processWaitingText(tab))}}</div>`;
      }}
      const sections = processSectionsForTab(data, tab);
      if (!sections.length) {{
        return `<div class="process-empty">${{processTitleForTab(tab)}}页已打开，但当前请求还没有找到对应的工程产物；等工程写回后这里会自动出现。</div>`;
      }}
      return sections.map((section, index) => renderProcessSection(section, index)).join("");
    }}

    function renderProcessPages(data) {{
      return `
        <section class="process-pages">
          ${{renderProcessToolbar(data)}}
          <div class="process-content" id="process-content">
            ${{renderProcessTabContent(data)}}
          </div>
        </section>
      `;
    }}

    function activateProcessButtons() {{
      const active = state.processTab || "decompose";
      document.querySelectorAll("[data-process-tab]").forEach(btn => {{
        btn.classList.toggle("active", btn.dataset.processTab === active);
      }});
      [$("process-export"), $("left-process-export")].filter(Boolean).forEach(btn => {{
        btn.classList.toggle("active", active === "export");
      }});
    }}

    function setProcessTab(tab) {{
      state.processTab = tab || "decompose";
      if (state.lastTalkData && (state.lastTalkData.request_id || state.lastTalkData.question || state.lastTalkData.workflow)) {{
        renderTalk(state.lastTalkData);
      }} else {{
        const panel = $("process-content");
        if (panel) {{
          panel.innerHTML = renderProcessTabContent({{workflow: {{ready: false}}}});
        }}
        attachProcessButtons();
      }}
    }}

    function attachProcessButtons() {{
      document.querySelectorAll("[data-process-tab]").forEach(btn => {{
        btn.onclick = () => setProcessTab(btn.dataset.processTab);
      }});
      const exportSingle = $("export-single-action");
      if (exportSingle) {{
        exportSingle.onclick = () => exportMachinePack(exportSingle);
      }}
      const exportContinuous = $("export-continuous-action");
      if (exportContinuous) {{
        exportContinuous.onclick = () => exportContinuousPack(exportContinuous);
      }}
      const processExport = $("process-export");
      if (processExport) {{
        processExport.onclick = () => {{
          state.processTab = "export";
          exportMachinePack(processExport);
        }};
      }}
      const leftExport = $("left-process-export");
      if (leftExport) {{
        leftExport.onclick = () => {{
          state.processTab = "export";
          exportMachinePack(leftExport);
        }};
      }}
      activateProcessButtons();
      syncMachineExportButton();
      if (state.processTab === "export" || $("export-history")) {{
        loadExportHistory();
      }}
    }}

    function renderTalk(data) {{
      data = mergeTalkData(data || {{}});
      rememberTalkData(data);
      const answerFile = data.answer_file || "";
      const answerRequestId = data.request_id || "";
      const liveReply = data.live_reply || {{}};
      const liveReplyText = liveReply.answer_markdown || "";
      const hasLiveReply = Boolean(liveReplyText);
      const isEngineeringStatusReply = liveReply.reply_role === "engineering_status";
      const errorCategory = data.error_category || "";
      const errorStage = data.error_stage || "";
      const errorRetryable = data.error_retryable === true;
      const returnCode = data.return_code;
      const errorSnippet = data.error_snippet || "";
      const hasAnswerMatch = answerRequestId ? answerFile.includes(`A_${{answerRequestId}}_`) : true;
      const hasAnswer = Boolean(data.talk_markdown) && Boolean(data.answer_checked) && hasAnswerMatch;
      const isRejected = data.answer_state === "rejected";
      const isStopped = data.answer_state === "stopped" || data.queue_status === "已终止";
      const isStale = data.answer_state === "stale_ignored";
      const isBlocked = data.answer_state === "blocked_by_active_processing";
      const errorSummary = [];
      if (errorCategory) {{
        errorSummary.push(`错误分类：${{errorCategory}}`);
      }}
      if (errorStage) {{
        errorSummary.push(`错误阶段：${{errorStage}}`);
      }}
      if (returnCode !== undefined && returnCode !== null && `${{returnCode}}` !== "") {{
        errorSummary.push(`返回码：${{returnCode}}`);
      }}
      if (errorSnippet) {{
        errorSummary.push(`摘要：${{errorSnippet}}`);
      }}
      errorSummary.push(`可重试：${{errorRetryable ? "是" : "否"}}`);
      const metaState = hasLiveReply
        ? (isEngineeringStatusReply ? (isBlocked ? "新问题未入队" : "工程状态已显示") : "已显示红楼解语")
        : (hasAnswer ? "已显示红楼解语" : (isRejected ? "未提交" : (isStopped ? "已停止解语" : (isStale ? "旧线程已退出" : (isBlocked ? "新问题未入队" : "等待红楼解语")))));
      const metaDetail = hasLiveReply
        ? (liveReply.status || "实时回复已生成")
        : (isRejected || isStopped || isStale || isBlocked ? (data.status || "") : "左边提问后，这里显示 Codex 的红楼解语。");
      $("result-meta").textContent = `${{metaState}}｜${{metaDetail}}`;
      const fallbackReply = (
        isRejected
          ? `${{data.status || "本次问题未提交。"}}`
          : (isStopped
            ? `${{data.status || "已停止解语。"}}\\n\\n当前队列已释放，可以提交新问题。`
            : (isStale
              ? `${{data.status || "旧线程已退出当前队列。"}}\\n\\n旧线程完成后不会再回写当前队列。`
              : `我已收到这个问题。这里是红楼解语区；工程拆解、证据页、材料池和导出页放在下面。\\n\\n如果完整回答还在生成，我会先把当前可显示的答案放在这里。\\n\\n▌`
            )
          )
      );
      $("result-title").textContent = "红楼解语";
      const assistantText = hasLiveReply ? liveReplyText : (hasAnswer ? data.talk_markdown : fallbackReply);
      const assistantHtml = (hasLiveReply || hasAnswer) ? renderAnswerMarkdown(assistantText) : esc(assistantText);
      const assistantClass = (hasLiveReply || hasAnswer) ? "answer-box" : "answer-wait";
      const assistantLabel = hasLiveReply ? (isEngineeringStatusReply ? "工程状态" : "红楼解语") : (hasAnswer ? "红楼解语" : "红楼解语");
      $("results").innerHTML = `
        <section class="dialogue-output ${{(hasLiveReply || hasAnswer) ? "" : "waiting"}}">
          <div class="dialogue-thread">
            <div class="message assistant">
              <div class="message-label">${{assistantLabel}}</div>
              <div class="message-bubble assistant-bubble ${{assistantClass}}">${{assistantHtml}}</div>
            </div>
          </div>
        </section>
        ${{renderProcessPages(data)}}
      `;
      attachProcessButtons();
    }}

    $("run-review").addEventListener("click", () => run("review", $("run-review"), loadReview));
    $("load-articles").addEventListener("click", () => run("articles", $("load-articles"), loadArticles));
    $("restore-latest-talk").addEventListener("click", () => run("restore-talk", $("restore-latest-talk"), () => restoreLatestTalk(false)));
    $("load-talk-history").addEventListener("click", () => run("talk-history", $("load-talk-history"), loadTalkHistory));
    $("ingest-current-article").addEventListener("click", ingestCurrentArticle);
    $("stop-talk").addEventListener("click", stopTalk);
    $("export-machine-pack").addEventListener("click", exportMachinePack);
    $("batch-save-review").addEventListener("click", saveVisibleReviews);
    $("export-review").addEventListener("click", exportCurrentReview);
    $("apply-bulk-defaults").addEventListener("click", applyBulkDefaults);
    $("run-workflow-status").addEventListener("click", () => requestCodexWindow($("run-workflow-status"), "内部过程"));
    $("run-loop-list").addEventListener("click", () => requestCodexWindow($("run-loop-list"), "已有问题包/工程状态"));
    $("run-experience-review").addEventListener("click", () => requestCodexWindow($("run-experience-review"), "经验复盘/经验值入账"));
    $("task-pillar").addEventListener("change", syncRouteOptions);
    $("task-route").addEventListener("change", () => {{
      applyRouteDefaults();
      updateRoutePreview();
    }});
    $("task-anchor").addEventListener("change", updateRoutePreview);
    $("task-depth").addEventListener("change", updateRoutePreview);
    $("task-output").addEventListener("change", updateRoutePreview);
    $("source-base").addEventListener("change", updateRoutePreview);
    $("source-original").addEventListener("change", updateRoutePreview);
    $("source-generated").addEventListener("change", updateRoutePreview);
    [
      "route-action-original",
      "route-action-keywords",
      "route-action-axis",
      "route-action-chapter",
      "route-action-cross",
      "route-action-verify",
      "route-action-counter"
    ].forEach(id => $(id).addEventListener("change", updateRoutePreview));
    syncRouteOptions();
    setMode("workflow");
    attachProcessButtons();
    restoreLatestTalk(true);
  </script>
</body>
</html>"""

    return page_html.replace("{{", "{").replace("}}", "}").replace("__APP_TITLE__", APP_TITLE)


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                html_response(self, page())
            elif parsed.path == "/health":
                feedback_status = feedback_optimizer.profile_status(feedback_optimizer.load_profile())
                json_response(
                    self,
                    {
                        "ok": True,
                        "app_title": APP_TITLE,
                        "app_build": APP_BUILD,
                        "codex_bridge": True,
                        "search_db_exists": search_index.SEARCH_DB.exists(),
                        "axis_db_exists": evidence_pack.DB_PATH.exists(),
                        "review_csv_exists": REVIEW_CSV.exists(),
                        "feedback_profile_exists": feedback_optimizer.DEFAULT_PROFILE_JSON.exists(),
                        "feedback_applied": feedback_status.get("applied", False),
                        "feedback_labeled_rows": feedback_status.get("labeled_rows", 0),
                    },
                )
            elif parsed.path == "/api/search":
                q = qs.get("q", [""])[0].strip()
                json_response(self, module_api_to_talk(q, "查原文"))
            elif parsed.path == "/api/evidence":
                question = qs.get("question", [""])[0].strip()
                entities = split_terms(qs.get("entities", [""])[0])
                keywords = split_terms(qs.get("keywords", [""])[0])
                requirements = "实体：" + "、".join(entities) + "；关键词：" + "、".join(keywords)
                json_response(self, module_api_to_talk(question, "证据", requirements=requirements))
            elif parsed.path == "/api/decompose":
                question = qs.get("question", [""])[0].strip()
                json_response(self, module_api_to_talk(question, "问题拆解"))
            elif parsed.path == "/api/research":
                question = qs.get("question", [""])[0].strip()
                json_response(self, module_api_to_talk(question, "文稿/材料池"))
            elif parsed.path == "/api/reader-direct-answer":
                question = qs.get("question", [""])[0].strip()
                chapter_no = qs.get("chapter_no", [""])[0].strip()
                chapter_title = qs.get("chapter_title", [""])[0].strip()
                reader_mode = qs.get("reader_mode", ["question"])[0].strip()
                json_response(self, reader_direct_answer_api(question=question, chapter_no=chapter_no, chapter_title=chapter_title, reader_mode=reader_mode))
            elif parsed.path == "/api/reader-direct-answer-status":
                request_id = qs.get("request_id", [""])[0].strip()
                json_response(self, reader_direct_answer_status_api(request_id=request_id))
            elif parsed.path == "/api/reader-direct-history":
                chapter_no = qs.get("chapter_no", [""])[0].strip()
                json_response(self, reader_direct_history_api(chapter_no=chapter_no))
            elif parsed.path == "/api/talk":
                question = qs.get("question", [""])[0].strip()
                top_n = min(max(int(qs.get("top_n", ["10"])[0]), 1), 20)
                task_intent = qs.get("task_intent", [""])[0].strip()
                requirements = qs.get("requirements", [""])[0].strip()
                json_response(self, talk_api(question=question, top_n=top_n, task_intent=task_intent, requirements=requirements))
            elif parsed.path == "/api/talk-status":
                question_key = qs.get("question_key", [""])[0].strip()
                request_id = qs.get("request_id", [""])[0].strip()
                json_response(self, talk_status_api(question_key=question_key, request_id=request_id))
            elif parsed.path == "/api/talk/stop":
                request_id = qs.get("request_id", [""])[0].strip()
                json_response(self, stop_talk_api(request_id=request_id))
            elif parsed.path == "/api/talk/export":
                question_key = qs.get("question_key", [""])[0].strip()
                request_id = qs.get("request_id", [""])[0].strip()
                json_response(self, talk_machine_export_api(question_key=question_key, request_id=request_id))
            elif parsed.path == "/api/talk/export-continuous":
                question_key = qs.get("question_key", [""])[0].strip()
                request_id = qs.get("request_id", [""])[0].strip()
                json_response(self, talk_continuous_export_api(question_key=question_key, request_id=request_id))
            elif parsed.path == "/api/talk/export-history":
                limit = min(max(int(qs.get("limit", ["30"])[0]), 1), 80)
                json_response(self, export_history_api(limit=limit))
            elif parsed.path == "/api/articles":
                limit = min(max(int(qs.get("limit", ["60"])[0]), 1), 120)
                json_response(self, article_records_api(limit=limit))
            elif parsed.path == "/api/recent-talk":
                limit = min(max(int(qs.get("limit", ["12"])[0]), 1), 60)
                json_response(self, recent_talk_api(limit=limit))
            elif parsed.path == "/api/article-ingest":
                request_id = qs.get("request_id", [""])[0].strip()
                package = qs.get("package", [""])[0].strip()
                main = qs.get("main", ["answer"])[0].strip()
                json_response(self, article_ingest_api(request_id=request_id, package=package, main=main))
            elif parsed.path == "/api/codex-process":
                question_key = qs.get("question_key", [""])[0].strip()
                request_id = qs.get("request_id", [""])[0].strip()
                processing = ensure_codex_processing(request_id=request_id, question_key=question_key)
                json_response(self, processing)
            elif parsed.path == "/api/segment-context":
                segment_no = qs.get("segment_no", [""])[0].strip()
                window = min(max(int(qs.get("window", ["2"])[0]), 0), 8)
                json_response(self, segment_context_api(segment_no, window))
            elif parsed.path == "/api/review":
                limit = min(max(int(qs.get("limit", ["20"])[0]), 1), 120)
                decision = qs.get("decision", ["待复核"])[0].strip()
                json_response(self, review_api(limit, decision))
            elif parsed.path == "/api/review/export":
                limit = min(max(int(qs.get("limit", ["20"])[0]), 1), 500)
                decision = qs.get("decision", ["待复核"])[0].strip()
                json_response(self, review_export_api(limit, decision))
            elif parsed.path == "/api/loop-status":
                package = qs.get("package", ["latest"])[0].strip()
                json_response(self, loop_status_api(package=package))
            elif parsed.path == "/api/loop-list":
                json_response(self, loop_list_api())
            elif parsed.path in {"/triangle", "/triangle/", "/honglou-triangle", "/honglou-triangle/"}:
                target = pick_triangle_html()
                if target:
                    html_file_response(self, target)
                else:
                    html_response(
                        self,
                        "<h1>红楼梦三角阅读闭环未找到</h1><p>请先确认文件：coex项目总库/10-19_四项目工程域/13_P03_红楼梦_HLM/50_输出区/来源路径保留/2026-06-03/notion-3-crv/outputs/正式底库阅读闭环还原台/红楼梦_三角阅读闭环.html</p>",
                        404,
                    )
            elif parsed.path in {"/triangle/index.html", "/honglou-triangle/index.html"}:
                target = pick_triangle_index() or pick_triangle_html()
                if target:
                    html_file_response(self, target)
                else:
                    html_response(
                        self,
                        "<h1>红楼梦三角阅读闭环未找到</h1><p>请先确认文件已落库。</p>",
                        404,
                    )
            else:
                html_response(self, f"<h1>404</h1><p>{html.escape(parsed.path)}</p>", 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8"))
            if parsed.path == "/api/review/update":
                json_response(self, update_review_row(REVIEW_CSV, payload, rebuild=True))
            elif parsed.path == "/api/review/batch-update":
                payloads = payload.get("rows", [])
                if not isinstance(payloads, list):
                    raise ValueError("rows 必须是列表")
                json_response(self, update_review_rows(REVIEW_CSV, payloads, rebuild=True))
            else:
                json_response(self, {"error": f"unknown endpoint: {parsed.path}"}, 404)
        except Exception as exc:
            json_response(self, {"error": str(exc)}, 500)

    def log_message(self, format: str, *args) -> None:
        return


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Red Chamber query app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    candidate_ports = [args.port + offset for offset in range(6)]
    last_error: OSError | None = None
    for port in candidate_ports:
        bind_target = (args.host, port)
        try:
            with ReusableThreadingHTTPServer(bind_target, Handler) as server:
                print(f"红楼梦研究台启动成功： http://{args.host}:{port}/")
                print("保活窗口：请保持该终端窗口不关闭")
                server.serve_forever()
                return
        except OSError as exc:
            last_error = exc
            if exc.errno in {48, 98}:
                print(f"端口 {port} 已被占用，正在尝试下一个端口。")
                continue
            print("红楼梦研究台启动失败")
            if exc.errno == 1:
                print("原因：当前环境不允许监听本地端口 (Operation not permitted)")
                print("建议：请在你本机 macOS 终端直接执行以下命令启动：")
                print("  /Users/yu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 work/formal_honglou_local_app.py --port 8765")
            else:
                print(f"错误信息：{exc}")
            raise SystemExit(1)

    print("红楼梦研究台启动失败")
    if last_error and last_error.errno in {48, 98}:
        print("原因：8765、8766、8767 都被占用。")
        print("请先关闭旧的红楼梦研究台黑色窗口，再重新双击桌面入口。")
    elif last_error:
        print(f"错误信息：{last_error}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
