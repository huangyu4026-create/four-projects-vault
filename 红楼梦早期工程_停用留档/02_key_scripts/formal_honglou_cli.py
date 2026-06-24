#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
if str(WORK) not in sys.path:
    sys.path.insert(0, str(WORK))

import formal_honglou_evidence_pack as evidence_pack
import formal_honglou_evidence_triage as evidence_triage
import formal_honglou_feedback_optimizer as feedback_optimizer
import formal_honglou_anchor_fix as anchor_fix
import formal_honglou_closed_loop as closed_loop
import formal_honglou_ledger_refresh as ledger_refresh
try:
    import formal_honglou_library_audit as library_audit
except ModuleNotFoundError:
    library_audit = None
import formal_honglou_mapping_audit as mapping_audit
import formal_honglou_p0_fix as p0_fix
import formal_honglou_question_evidence_pool as evidence_pool
import formal_honglou_question_decomposer as decomposer
import formal_honglou_research_workflow as research_workflow
import formal_honglou_review_readback as review_readback
import formal_honglou_review_writer as review_writer
import formal_honglou_search_index as search_index
import formal_honglou_script_audit as script_audit
import formal_honglou_v02_question_tests as v02_tests


PYTHON = Path(sys.executable)

LEGACY_PIPELINE_UNLOCK_ENV = "HONGLOU_ALLOW_LEGACY_PIPELINE"
LEGACY_PIPELINE_UNLOCK_VALUE = "YES_I_KNOW_THIS_IS_LEGACY"


def _legacy_pipeline_blocked_payload(command: str) -> dict:
    return {
        "ok": False,
        "sealed": True,
        "command": command,
        "status": "旧闭环流水线已封存，默认禁止进入。",
        "reason": "当前主路已切换为“红楼梦对谈查证室”：问题先由 Codex/对谈式阅读拆词、查库、回原文，再形成结论。旧 run/talk 流水线只作为历史档案和材料库保留，不再自动生成候选池、精读池或终稿。",
        "new_entry": "python3 work/formal_honglou_dialogue_probe.py --question \"你的问题\"",
        "legacy_override": f"如确需人工抢修旧流水线，必须临时设置 {LEGACY_PIPELINE_UNLOCK_ENV}={LEGACY_PIPELINE_UNLOCK_VALUE}。",
    }


def _require_legacy_pipeline_unlocked(command: str) -> bool:
    return os.environ.get(LEGACY_PIPELINE_UNLOCK_ENV) == LEGACY_PIPELINE_UNLOCK_VALUE


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _talk_route_context_from_question(question: str = "") -> str:
    question = (question or "").strip()
    if not question:
        return ""
    terms = decomposer.compact_strategy_terms(decomposer.terms_from_question(question), limit=6)
    if not terms:
        clean_question = re.sub(r"[。？！!?；;,:，:：、?]", " ", question)
        clean_question = re.sub(r"\s+", " ", clean_question).strip()
        chapter_terms = re.findall(r"第[一二三四五六七八九十百千万]+回|第\d+回", question)
        fallback_terms = []
        if chapter_terms:
            fallback_terms.extend(chapter_terms)
        if "章回" in question and "章回" not in fallback_terms:
            fallback_terms.append("章回")
        if "红楼梦" in question and "红楼梦" not in fallback_terms:
            fallback_terms.append("红楼梦")
        fallback_terms.extend(decomposer.compact_strategy_terms([part for part in clean_question.split() if len(part) <= 16], limit=6))
        terms = [term for term in fallback_terms if decomposer.is_searchable_term(term)][:6]
        if not terms:
            terms = ["红楼梦", "章回"]
        terms = terms[:6]
    if not terms:
        return ""
    fallback_libraries = [
        "全文检索库",
        "段落库",
        "章节真源库",
    ]
    return "\n".join(
        [
            f"Codex查询词：{'、'.join(terms[:6])}",
            f"Codex优先库：{'、'.join(fallback_libraries)}",
        ]
    )


def cmd_search(args: argparse.Namespace) -> None:
    if not search_index.SEARCH_DB.exists():
        search_index.build_index()
    conn = sqlite3.connect(search_index.SEARCH_DB)
    conn.row_factory = sqlite3.Row
    try:
        print_json(search_index.search(conn, args.query, limit=args.limit))
    finally:
        conn.close()


def cmd_evidence(args: argparse.Namespace) -> None:
    entities = evidence_pack.clean_terms(args.entities)
    keywords = evidence_pack.clean_terms(args.keywords)
    result = evidence_pack.generate_package(
        question=args.question,
        entities=entities or evidence_pack.DEFAULT_ENTITIES,
        keywords=keywords or evidence_pack.DEFAULT_KEYWORDS,
        limit=args.limit,
    )
    print_json(result)


def cmd_decompose(args: argparse.Namespace) -> None:
    result = decomposer.generate(args.question, args.limit_per_question)
    print_json(result)


def cmd_build_search(args: argparse.Namespace) -> None:
    print_json(search_index.build_index())


def cmd_script_audit(args: argparse.Namespace) -> None:
    print_json(
        script_audit.run(
            rebuild_search=args.rebuild_search,
            out_dir=Path(args.out_dir),
        )
    )


def cmd_mapping_audit(args: argparse.Namespace) -> None:
    print_json(
        mapping_audit.run(
            apply_safe_fixes=args.apply_safe_fixes,
            out_dir=Path(args.out_dir),
        )
    )


def cmd_library_audit(args: argparse.Namespace) -> None:
    if library_audit is None:
        print_json(
            {
                "ok": False,
                "error": "缺少 work/formal_honglou_library_audit.py，无法执行 library-audit；其他命令不受影响。",
            }
        )
        raise SystemExit(2)
    print_json(
        library_audit.run(
            out_dir=Path(args.out_dir),
        )
    )


def cmd_p0_fix(args: argparse.Namespace) -> None:
    print_json(
        p0_fix.run(
            out_dir=Path(args.out_dir),
        )
    )


def cmd_ledger_refresh(args: argparse.Namespace) -> None:
    print_json(
        ledger_refresh.refresh(
            trigger=args.trigger,
            note=args.note,
        )
    )


def cmd_anchor_fix(args: argparse.Namespace) -> None:
    print_json(
        anchor_fix.run(
            out_dir=Path(args.out_dir),
        )
    )


def cmd_pool(args: argparse.Namespace) -> None:
    print_json(evidence_pool.build_pool(args.question, args.limit_per_question))


def cmd_triage(args: argparse.Namespace) -> None:
    evidence_triage.main()


def cmd_research(args: argparse.Namespace) -> None:
    print_json(
        research_workflow.build_research_pack(
            question=args.question,
            limit_per_question=args.limit_per_question,
            top_evidence=args.top_evidence,
            use_feedback=not args.no_feedback,
            feedback_profile_path=Path(args.feedback_profile) if args.feedback_profile else None,
            out_dir=Path(args.out_dir),
            pool_out_dir=Path(args.pool_out_dir) if args.pool_out_dir else None,
            route_context=args.route_context,
        )
    )


def cmd_review_write(args: argparse.Namespace) -> None:
    print_json(
        review_writer.build_review_pack(
            question=args.question,
            limit_per_question=args.limit_per_question,
            top_evidence=args.top_evidence,
            review_limit=args.review_limit,
            use_feedback=not args.no_feedback,
            feedback_profile_path=Path(args.feedback_profile) if args.feedback_profile else None,
            out_dir=Path(args.out_dir),
            research_out_dir=Path(args.research_out_dir) if args.research_out_dir else None,
            pool_out_dir=Path(args.pool_out_dir) if args.pool_out_dir else None,
            route_context=args.route_context,
        )
    )


def cmd_run(args: argparse.Namespace) -> None:
    if not _require_legacy_pipeline_unlocked("run"):
        print_json(_legacy_pipeline_blocked_payload("run"))
        return
    print_json(
        closed_loop.build_closed_loop(
            question=args.question,
            limit_per_question=args.limit_per_question,
            top_evidence=args.top_evidence,
            review_limit=args.review_limit,
            out_root=Path(args.out_root),
            use_feedback=not args.no_feedback,
            feedback_profile_path=Path(args.feedback_profile) if args.feedback_profile else None,
            run_smoke=not args.skip_smoke,
            route_context=args.route_context,
        )
    )


def cmd_talk(args: argparse.Namespace) -> None:
    if not _require_legacy_pipeline_unlocked("talk"):
        print_json(_legacy_pipeline_blocked_payload("talk"))
        return
    route_context = args.route_context.strip()
    if not route_context and args.question:
        route_context = _talk_route_context_from_question(args.question)
    print_json(
        closed_loop.talk_workflow(
            question=args.question,
            package=args.package,
            limit_per_question=args.limit_per_question,
            top_evidence=args.top_evidence,
            review_limit=args.review_limit,
            out_root=Path(args.out_root),
            use_feedback=not args.no_feedback,
            feedback_profile_path=Path(args.feedback_profile) if args.feedback_profile else None,
            run_smoke=not args.skip_smoke,
            top_n=args.top_n,
            route_context=route_context,
        )
    )


def cmd_loop_list(args: argparse.Namespace) -> None:
    print_json(closed_loop.loop_list(out_root=Path(args.out_root)))


def cmd_home(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.build_project_home(
            package=args.package,
            out_root=Path(args.out_root),
            home_dir=Path(args.home_dir),
            run_smoke=args.run_smoke,
        )
    )


def cmd_loop_readback(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_readback(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_draft(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_draft(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_next(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_next(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_plan(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_plan(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_sheet(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_sheet(
            package=args.package,
            out_root=Path(args.out_root),
            batch=args.batch,
            limit=args.limit,
        )
    )


def cmd_loop_review_assist(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_assist(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
            limit=args.limit,
        )
    )


def cmd_loop_review_workbench(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_workbench(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
        )
    )


def cmd_loop_review_coverage(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_coverage(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_argument_brief(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_argument_brief(
            package=args.package,
            out_root=Path(args.out_root),
            top_n=args.top_n,
        )
    )


def cmd_loop_article_draft(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_article_draft(
            package=args.package,
            out_root=Path(args.out_root),
            top_n=args.top_n,
        )
    )


def cmd_loop_article_polish(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_article_polish(
            package=args.package,
            out_root=Path(args.out_root),
            top_n=args.top_n,
        )
    )


def cmd_article_ingest_preview(args: argparse.Namespace) -> None:
    print_json(
        {
            "status": "旧本地文章稿入库命令已停用；请从研究台页面使用红楼解语入库预检。",
            "does_not_call_local_article_chain": True,
            "package": args.package,
        }
    )


def cmd_loop_review_firstpass(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass(
            package=args.package,
            out_root=Path(args.out_root),
            target_count=args.target_count,
        )
    )


def cmd_loop_review_firstpass_sheet(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_sheet(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_firstpass_cards(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_cards(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_firstpass_desk(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_desk(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_firstpass_talk(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_talk(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_firstpass_check(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_check(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
        )
    )


def cmd_loop_review_firstpass_sync(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_firstpass_sync(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    )


def cmd_loop_review_apply(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_apply(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    )


def cmd_loop_review_check(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_check(
            package=args.package,
            out_root=Path(args.out_root),
            sheet=args.sheet,
        )
    )


def cmd_loop_review_backups(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_backups(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_review_restore(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_restore(
            package=args.package,
            out_root=Path(args.out_root),
            backup=args.backup,
            dry_run=args.dry_run,
        )
    )


def cmd_loop_source_verify(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_source_verify(
            package=args.package,
            out_root=Path(args.out_root),
            dry_run=args.dry_run,
        )
    )


def cmd_loop_review_finish(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_review_finish(
            package=args.package,
            out_root=Path(args.out_root),
            apply=args.apply,
            overwrite=args.overwrite,
            run_source_verify=not args.skip_source_verify,
            run_readback=not args.skip_readback,
        )
    )


def cmd_loop_status(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_status(
            package=args.package,
            out_root=Path(args.out_root),
        )
    )


def cmd_loop_continue(args: argparse.Namespace) -> None:
    print_json(
        closed_loop.loop_continue(
            package=args.package,
            out_root=Path(args.out_root),
            batch=args.batch,
            limit=args.limit,
            apply=args.apply,
            overwrite=args.overwrite,
        )
    )


def cmd_review_readback(args: argparse.Namespace) -> None:
    print_json(
        review_readback.build_readback(
            review_csv=Path(args.review_csv),
            question=args.question,
            out_dir=Path(args.out_dir),
        )
    )


def cmd_feedback_learn(args: argparse.Namespace) -> None:
    print_json(
        feedback_optimizer.build_feedback_profile(
            review_csv=Path(args.review_csv),
            out_dir=Path(args.out_dir),
        )
    )


def cmd_v02_test(args: argparse.Namespace) -> None:
    print_json(
        v02_tests.run_tests(
            limit_per_question=args.limit_per_question,
            top_evidence=args.top_evidence,
            review_limit=args.review_limit,
        )
    )


def cmd_smoke(args: argparse.Namespace) -> None:
    script = WORK / "formal_honglou_smoke_test.py"
    completed = subprocess.run([str(PYTHON), str(script)], cwd=ROOT)
    raise SystemExit(completed.returncode)


def cmd_smoke_offline(args: argparse.Namespace) -> None:
    script = WORK / "formal_honglou_offline_smoke_test.py"
    completed = subprocess.run([str(PYTHON), str(script)], cwd=ROOT)
    raise SystemExit(completed.returncode)


def cmd_paths(args: argparse.Namespace) -> None:
    print_json(
        {
            "root": str(ROOT),
            "axis_db": str(search_index.SOURCE_DB),
            "search_db": str(search_index.SEARCH_DB),
            "local_app": str(WORK / "formal_honglou_local_app.py"),
            "smoke_test": str(WORK / "formal_honglou_smoke_test.py"),
            "offline_smoke_test": str(WORK / "formal_honglou_offline_smoke_test.py"),
            "outputs": {
                "multi_axis": str(ROOT / "outputs" / "正式底库多轴扩展原型"),
                "evidence_pack": str(ROOT / "outputs" / "正式底库证据包生成器原型"),
                "decomposer": str(ROOT / "outputs" / "正式底库复杂拆题器原型"),
                "search": str(ROOT / "outputs" / "正式底库全文检索原型"),
                "local_entry": str(ROOT / "outputs" / "正式底库本地查询入口"),
                "closed_loop": str(ROOT / "outputs" / "正式底库闭环工作流"),
                "research_workflow": str(ROOT / "outputs" / "正式底库研究工作流原型"),
                "review_writer": str(ROOT / "outputs" / "正式底库复核写作包"),
                "review_readback": str(ROOT / "outputs" / "正式底库复核回读包"),
                "feedback_optimizer": str(ROOT / "outputs" / "正式底库复核反馈优化包"),
                "v02_tests": str(ROOT / "outputs" / "正式底库v0.2复杂问题测试"),
                "library_audit": str(ROOT / "outputs" / "正式底库库群结构分析与建设待办"),
                "p0_fix": str(ROOT / "outputs" / "正式底库P0修复包"),
                "anchor_fix": str(ROOT / "outputs" / "正式底库证据锚点修复包"),
                "ledger": str(ROOT / "outputs" / "正式底库阶段复盘与下一步"),
            },
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="红楼梦正式底库统一命令入口")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="全文检索，自动简繁归一")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("evidence", help="生成证据包")
    p.add_argument("--question", default=evidence_pack.DEFAULT_QUESTION)
    p.add_argument("--entities", nargs="*", default=evidence_pack.DEFAULT_ENTITIES)
    p.add_argument("--keywords", nargs="*", default=evidence_pack.DEFAULT_KEYWORDS)
    p.add_argument("--limit", type=int, default=80)
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("decompose", help="复杂问题拆题")
    p.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    p.add_argument("--limit-per-question", type=int, default=8)
    p.set_defaults(func=cmd_decompose)

    p = sub.add_parser("build-search", help="重建全文检索库")
    p.set_defaults(func=cmd_build_search)

    p = sub.add_parser("script-audit", help="检查简繁统一：简体问和繁体问是否等价召回")
    p.add_argument("--rebuild-search", action="store_true", help="检查前先重建全文索引")
    p.add_argument("--out-dir", default=str(script_audit.OUT_DIR))
    p.set_defaults(func=cmd_script_audit)

    p = sub.add_parser("mapping-audit", help="检查并可选安全固化 Notion relation 与本地 ID 映射")
    p.add_argument("--apply-safe-fixes", action="store_true", help="执行高置信 ID 回连；默认只检查不写入")
    p.add_argument("--out-dir", default=str(mapping_audit.OUT_DIR))
    p.set_defaults(func=cmd_mapping_audit)

    library_audit_out_dir = (
        library_audit.OUT_DIR
        if library_audit is not None
        else ROOT / "outputs" / "正式底库库群结构分析与建设待办"
    )
    p = sub.add_parser("library-audit", help="盘点库群结构、120回覆盖、待建设轴库和ID映射标准")
    p.add_argument("--out-dir", default=str(library_audit_out_dir))
    p.set_defaults(func=cmd_library_audit)

    p = sub.add_parser("p0-fix", help="安全修复P0小问题：章节身份、迎春人物边、歧义队列、未解析证据分层")
    p.add_argument("--out-dir", default=str(p0_fix.OUT_DIR))
    p.set_defaults(func=cmd_p0_fix)

    p = sub.add_parser("ledger-refresh", help="刷新总账机器摘要、必读路由和刷新日志")
    p.add_argument("--trigger", default="manual", help="刷新触发原因，如 收工、总账体检、库体检后")
    p.add_argument("--note", default="", help="本次刷新备注")
    p.set_defaults(func=cmd_ledger_refresh)

    p = sub.add_parser("anchor-fix", help="安全修复证据锚点：只写回唯一高分段落候选")
    p.add_argument("--out-dir", default=str(anchor_fix.OUT_DIR))
    p.set_defaults(func=cmd_anchor_fix)

    p = sub.add_parser("pool", help="把复杂拆题结果合并为总证据池")
    p.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    p.add_argument("--limit-per-question", type=int, default=0)
    p.set_defaults(func=cmd_pool)

    p = sub.add_parser("triage", help="对总证据池做证据分级筛选")
    p.set_defaults(func=cmd_triage)

    p = sub.add_parser("research", help="一键生成问题树、证据顺序、重点证据卡片和写作提纲")
    p.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    p.add_argument("--limit-per-question", type=int, default=0)
    p.add_argument("--top-evidence", type=int, default=0)
    p.add_argument("--feedback-profile", default=str(feedback_optimizer.DEFAULT_PROFILE_JSON))
    p.add_argument("--out-dir", default=str(research_workflow.OUT_DIR))
    p.add_argument("--pool-out-dir", default="")
    p.add_argument("--route-context", default="")
    p.add_argument("--no-feedback", action="store_true")
    p.set_defaults(func=cmd_research)

    p = sub.add_parser("review-write", help="生成人工复核表、复核阅读单、带证据写作草稿")
    p.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    p.add_argument("--limit-per-question", type=int, default=0)
    p.add_argument("--top-evidence", type=int, default=0)
    p.add_argument("--review-limit", type=int, default=0)
    p.add_argument("--feedback-profile", default=str(feedback_optimizer.DEFAULT_PROFILE_JSON))
    p.add_argument("--out-dir", default=str(review_writer.OUT_DIR))
    p.add_argument("--research-out-dir", default="")
    p.add_argument("--pool-out-dir", default="")
    p.add_argument("--route-context", default="")
    p.add_argument("--no-feedback", action="store_true")
    p.set_defaults(func=cmd_review_write)

    p = sub.add_parser("run", help="一次性跑通拆题、证据、研究包、复核包、回读、反馈和总索引")
    p.add_argument("--question", default=decomposer.DEFAULT_QUESTION)
    p.add_argument("--limit-per-question", type=int, default=0)
    p.add_argument("--top-evidence", type=int, default=0)
    p.add_argument("--review-limit", type=int, default=0)
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--feedback-profile", default=str(feedback_optimizer.DEFAULT_PROFILE_JSON))
    p.add_argument("--route-context", default="")
    p.add_argument("--no-feedback", action="store_true")
    p.add_argument("--skip-smoke", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("talk", help="生成或刷新候选材料、材料池和 Codex 红楼解语前置工程；默认刷新 latest，有问题时新建问题包")
    p.add_argument("--question", default="", help="新问题；留空则刷新 --package 指定的问题包")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--limit-per-question", type=int, default=0)
    p.add_argument("--top-evidence", type=int, default=0)
    p.add_argument("--review-limit", type=int, default=0)
    p.add_argument("--top-n", type=int, default=10, help="候选材料过程文件保留多少条核心线索")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--feedback-profile", default=str(feedback_optimizer.DEFAULT_PROFILE_JSON))
    p.add_argument("--route-context", default="")
    p.add_argument("--no-feedback", action="store_true")
    p.add_argument("--skip-smoke", action="store_true")
    p.set_defaults(func=cmd_talk)

    p = sub.add_parser("loop-list", help="列出闭环问题包和复核进度")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_list)

    p = sub.add_parser("home", help="生成红楼梦工程本地文件首页")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--home-dir", default=str(closed_loop.HOME_OUT))
    p.add_argument("--run-smoke", action="store_true", help="生成首页时顺便运行离线自检")
    p.set_defaults(func=cmd_home)

    p = sub.add_parser("loop-readback", help="读取闭环包内复核表，回填同一个问题包")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_readback)

    p = sub.add_parser("loop-draft", help="读取闭环包内人工复核结果，生成复核后的写作草稿")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_draft)

    p = sub.add_parser("loop-next", help="根据闭环包复核状态生成二次追问与补证计划")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_next)

    p = sub.add_parser("loop-review-plan", help="根据闭环包复核表生成一份人工复核优先清单")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_plan)

    p = sub.add_parser("loop-review-sheet", help="从复核优先清单生成一个可编辑的小批次复核工作表")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--batch", default="第1批", help="批次选择，如 第1批、1、反证")
    p.add_argument("--limit", type=int, default=20, help="最多生成多少行；0 表示不限制")
    p.set_defaults(func=cmd_loop_review_sheet)

    p = sub.add_parser("loop-review-assist", help="为当前批次小表生成机器预读填写助手，不写入人工字段")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="复核工作表路径；默认读取问题包内的 17_当前批次复核工作表.csv")
    p.add_argument("--limit", type=int, default=0, help="最多生成多少行；0 表示不限制")
    p.set_defaults(func=cmd_loop_review_assist)

    p = sub.add_parser("loop-review-workbench", help="合并当前小表和机器预读，生成复核填表工作台")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="复核工作表路径；默认读取问题包内的 17_当前批次复核工作表.csv")
    p.set_defaults(func=cmd_loop_review_workbench)

    p = sub.add_parser("loop-review-coverage", help="根据复核填表工作台生成子问题覆盖矩阵")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_coverage)

    p = sub.add_parser("loop-argument-brief", help="已停用：本地论证简报不再生成，只写停用说明")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--top-n", type=int, default=10, help="兼容参数；本地论证简报已停用")
    p.set_defaults(func=cmd_loop_argument_brief)

    p = sub.add_parser("loop-article-draft", help="已停用：本地文章稿不再生成，只写停用说明")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--top-n", type=int, default=10, help="兼容参数；本地文章稿已停用")
    p.set_defaults(func=cmd_loop_article_draft)

    p = sub.add_parser("loop-article-polish", help="已停用：本地润色稿不再生成，只写停用说明")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--top-n", type=int, default=10, help="兼容参数；本地润色稿已停用")
    p.set_defaults(func=cmd_loop_article_polish)

    p = sub.add_parser("article-ingest-preview", help="生成文章入库本地预检包，不写 Notion")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--main", default="answer", help="兼容参数；入库应以红楼解语为主")
    p.add_argument("--support", nargs="*", default=None, help="兼容参数；本地文章版本链已停用")
    p.add_argument("--confirmed", action="store_true", help="仅标记用户已明确确认主版本；仍不写 Notion")
    p.set_defaults(func=cmd_article_ingest_preview)

    p = sub.add_parser("loop-article-ingest-preview", help="生成文章入库本地预检包，不写 Notion")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--main", default="answer", help="兼容参数；入库应以红楼解语为主")
    p.add_argument("--support", nargs="*", default=None, help="兼容参数；本地文章版本链已停用")
    p.add_argument("--confirmed", action="store_true", help="仅标记用户已明确确认主版本；仍不写 Notion")
    p.set_defaults(func=cmd_article_ingest_preview)

    p = sub.add_parser("loop-review-firstpass", help="把覆盖矩阵压缩成首轮可执行复核清单")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--target-count", type=int, default=6, help="首轮建议处理多少条")
    p.set_defaults(func=cmd_loop_review_firstpass)

    p = sub.add_parser("loop-review-firstpass-sheet", help="生成只含首轮证据的可编辑复核小表")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_firstpass_sheet)

    p = sub.add_parser("loop-review-firstpass-cards", help="生成首轮 6 条证据的逐条判读卡片")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_firstpass_cards)

    p = sub.add_parser("loop-review-firstpass-desk", help="生成首轮复核就绪台（填表后建议执行路径）")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_firstpass_desk)

    p = sub.add_parser("loop-review-firstpass-talk", help="生成首轮谈心式复核单，帮助人工判断 38 小表")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_firstpass_talk)

    p = sub.add_parser("loop-review-firstpass-check", help="检查首轮复核小表是否可以安全同步到 17")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="首轮复核小表路径；默认读取问题包内的 38_首轮复核小表.csv")
    p.set_defaults(func=cmd_loop_review_firstpass_check)

    p = sub.add_parser("loop-review-firstpass-sync", help="把首轮复核小表同步回 17_当前批次复核工作表")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="首轮复核小表路径；默认读取问题包内的 38_首轮复核小表.csv")
    p.add_argument("--overwrite", action="store_true", help="允许覆盖 17 小表中已有的人工字段")
    p.add_argument("--dry-run", action="store_true", help="只模拟同步，不写入 17 小表")
    p.set_defaults(func=cmd_loop_review_firstpass_sync)

    p = sub.add_parser("loop-review-apply", help="把已编辑的复核工作表安全回填到同一问题包的复核表")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="复核工作表路径；默认读取问题包内的 17_当前批次复核工作表.csv")
    p.add_argument("--overwrite", action="store_true", help="允许覆盖复核表中已有的人工字段")
    p.add_argument("--dry-run", action="store_true", help="只模拟回填，不写入复核表")
    p.set_defaults(func=cmd_loop_review_apply)

    p = sub.add_parser("loop-review-check", help="检查当前批次复核工作表是否可以安全回填")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--sheet", default="", help="复核工作表路径；默认读取问题包内的 17_当前批次复核工作表.csv")
    p.set_defaults(func=cmd_loop_review_check)

    p = sub.add_parser("loop-review-backups", help="列出同一问题包内的复核表自动备份")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_review_backups)

    p = sub.add_parser("loop-review-restore", help="从同一问题包的备份恢复 04_复核表.csv")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--backup", default="latest", help="备份文件名、路径，或 latest")
    p.add_argument("--dry-run", action="store_true", help="只模拟恢复，不写入复核表")
    p.set_defaults(func=cmd_loop_review_restore)

    p = sub.add_parser("loop-source-verify", help="统一 04 复核表的真源核验字段，并生成核验清单")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--dry-run", action="store_true", help="只生成核验清单和报告，不写入 04_复核表.csv")
    p.set_defaults(func=cmd_loop_source_verify)

    p = sub.add_parser("loop-review-finish", help="一键收口复核链路：检查 38，同步 17，回填 04，刷新核验与回读")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--apply", action="store_true", help="允许实际同步、回填并刷新后续材料；不加时只做安全检查")
    p.add_argument("--overwrite", action="store_true", help="允许覆盖 17 或 04 中已有人工字段")
    p.add_argument("--skip-source-verify", action="store_true", help="跳过真源核验字段与清单刷新")
    p.add_argument("--skip-readback", action="store_true", help="跳过回读、反馈与可写作材料刷新")
    p.set_defaults(func=cmd_loop_review_finish)

    p = sub.add_parser("loop-status", help="生成闭环状态与下一步操作台")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.set_defaults(func=cmd_loop_status)

    p = sub.add_parser("loop-continue", help="安全续跑闭环：自动检查状态，并在显式允许时继续回填和刷新")
    p.add_argument("--package", default="latest", help="闭环包路径、包名，或 latest")
    p.add_argument("--out-root", default=str(closed_loop.OUT_ROOT))
    p.add_argument("--batch", default="第1批", help="缺少小表时生成哪个批次")
    p.add_argument("--limit", type=int, default=20, help="缺少小表时最多生成多少行；0 表示不限制")
    p.add_argument("--apply", action="store_true", help="质量检查通过后允许实际回填并刷新后续材料")
    p.add_argument("--overwrite", action="store_true", help="实际回填时允许覆盖已有人工字段")
    p.set_defaults(func=cmd_loop_continue)

    p = sub.add_parser("review-readback", help="读取人工复核表，生成复核后证据和写作材料")
    p.add_argument("--review-csv", default=str(review_readback.DEFAULT_REVIEW_CSV))
    p.add_argument("--question", default="")
    p.add_argument("--out-dir", default=str(review_readback.OUT_DIR))
    p.set_defaults(func=cmd_review_readback)

    p = sub.add_parser("feedback-learn", help="从人工复核表生成下一次出库排序偏好")
    p.add_argument("--review-csv", default=str(feedback_optimizer.DEFAULT_REVIEW_CSV))
    p.add_argument("--out-dir", default=str(feedback_optimizer.OUT_DIR))
    p.set_defaults(func=cmd_feedback_learn)

    p = sub.add_parser("v02-test", help="运行v0.2三类复杂问题测试并归档")
    p.add_argument("--limit-per-question", type=int, default=0)
    p.add_argument("--top-evidence", type=int, default=0)
    p.add_argument("--review-limit", type=int, default=0)
    p.set_defaults(func=cmd_v02_test)

    p = sub.add_parser("smoke", help="运行本地系统冒烟测试")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("smoke-offline", help="运行不依赖网页服务的本地系统自检")
    p.set_defaults(func=cmd_smoke_offline)

    p = sub.add_parser("paths", help="输出关键文件路径")
    p.set_defaults(func=cmd_paths)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
