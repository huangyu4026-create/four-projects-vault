#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

MATERIAL_RECALL_ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs/红楼梦正式取材专库")
MATERIAL_RECALL_RULES_JSON = MATERIAL_RECALL_ROOT / "99_专库规则" / "正式取材专库硬锁规则.json"
MATERIAL_RECALL_WHITELIST_JSON = MATERIAL_RECALL_ROOT / "99_专库规则" / "正式取材专库_双中心白名单.json"


REQUIRED_CREDENTIAL_GROUPS = [
    ("line_id", "一行索引编号"),
    ("segment_no", "原子段编号"),
    ("graph_node_id", "聚拢总图节点"),
    ("aggregate_segment_ids", "聚拢段"),
    ("aggregate_unit_ids", "聚拢单元"),
    ("aggregate_event_ids", "聚拢事件"),
    ("aggregate_scene_ids", "聚拢场"),
    ("aggregate_domain_ids", "聚拢域"),
    ("cluster_unit", "聚拢单元"),
    ("event_id", "事件编号"),
    ("chapter_no", "回目编号"),
    ("source_trace", "来源链"),
    ("codex_original_passages", "原文回收"),
    ("same_chapter_passage_segments", "同回原文段"),
]

SUPPORTING_FIELDS = [
    "codex_query_lane",
    "codex_query_lane_reason",
    "codex_material_bucket",
    "evidence_status",
    "source_system",
    "aggregation_graph_route",
    "aggregation_graph_reason",
    "exhaustive_collect_method",
    "bucket_reason",
    "reasons",
    "triage_note",
]

FORMAL_SOURCE_FIELDS = [
    "source_scope",
    "source_db",
    "source_table",
    "source_tables",
    "source_system",
]

FORMAL_SOURCE_SCOPES = {
    "formal_registry_db",
    "formal_text_db",
    "formal_axis_db",
    "formal_coordinate_db",
    "formal_term_db",
    "formal_char_db",
    "formal_variable_db",
    "formal_person_db",
    "formal_object_db",
    "formal_event_db",
    "formal_space_db",
    "formal_scene_db",
    "formal_time_db",
    "formal_literary_db",
    "formal_relationship_db",
    "formal_quality_db",
}

FORMAL_SOURCE_TABLE_TOKENS = {
    "25_库登记处机器总表",
    "segments",
    "chapters",
    "chapter_identity",
    "chapter_source_variants",
    "search_documents",
    "search_documents_fts",
    "characters",
    "character_alias_solidification",
    "character_alias_ambiguity_queue",
    "person_segment_edges",
    "objects_axis",
    "spaces_axis",
    "space_evidence_axis",
    "event_segments",
    "event_segment_edges",
    "time_axis",
    "literary_texts_axis",
    "evidence_edges",
    "segment_range_edges",
    "segment_match_cache",
    "source_csvs",
    "axis_sources",
    "atom_coordinates",
    "variable_points",
    "variable_dictionary",
    "container_variable_index",
    "v_atom_distance_directed",
    "v_variable_point_context",
    "v_term_hits",
    "v_char_hits",
    "chapter_texts",
}

ENGINEERING_SOURCE_PATH_FIELDS = [
    "source_path",
    "source_file",
    "source_db",
    "workflow_package",
    "package_dir",
    "ledger_md",
    "ledger_json",
]

ENGINEERING_SOURCE_MARKERS = [
    "outputs/正式底库闭环工作流",
    "outputs/红楼梦坐标工程双头入口",
    "_内部过程",
    "00AC",
    "00AG",
    "00AI",
    "00AJ",
    "00AM",
    "00I",
    "00L",
    "00M",
    "Codex材料池判定",
    "Codex精读材料词",
    "Codex写作前原文",
]

ENGINEERING_SOURCE_SUFFIXES = (".md", ".json", ".log")
FORMAL_SOURCE_SUFFIXES = {".sqlite", ".csv"}


def clean(value: object) -> str:
    return str(value or "").strip()


def has_value(row: dict, field: str) -> bool:
    return bool(clean(row.get(field)))


def credential_fields(row: dict) -> list[str]:
    return [field for field, _ in REQUIRED_CREDENTIAL_GROUPS if has_value(row, field)]


def supporting_fields(row: dict) -> list[str]:
    return [field for field in SUPPORTING_FIELDS if has_value(row, field)]


def _field_blob(row: dict, fields: list[str]) -> str:
    return "；".join(clean(row.get(field)) for field in fields if has_value(row, field))


@lru_cache(maxsize=1)
def _route_root_paths() -> dict[str, Path]:
    if not MATERIAL_RECALL_RULES_JSON.exists():
        return {}
    try:
        rules = json.loads(MATERIAL_RECALL_RULES_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    roots: dict[str, Path] = {}
    semantic = clean(rules.get("semantic_root_db"))
    coordinate = clean(rules.get("coordinate_root_db"))
    if semantic:
        roots["semantic"] = Path(semantic).resolve()
    if coordinate:
        roots["coordinate"] = Path(coordinate).resolve()
    return roots


def _source_db_path(row: dict) -> Path | None:
    if not has_value(row, "source_db"):
        return None
    try:
        return Path(clean(row.get("source_db")).split("::", 1)[0]).resolve()
    except (OSError, RuntimeError):
        return None


def _candidate_route(row: dict) -> str:
    route_blob = _field_blob(
        row,
        [
            "recall_gate",
            "codex_query_lane",
            "codex_query_lane_reason",
            "source_scope",
            "source_system",
            "recall_method",
        ],
    ).lower()
    if "coordinate" in route_blob or "坐标" in route_blob or "formal_coordinate_db" in route_blob:
        return "coordinate"
    if "semantic" in route_blob or "语义" in route_blob or "聚拢" in route_blob or "formal_axis_db" in route_blob:
        return "semantic"
    return ""


def _route_source_gate(row: dict) -> dict[str, Any]:
    route = _candidate_route(row)
    roots = _route_root_paths()
    source_path = _source_db_path(row)
    if not route:
        return {
            "route_source_status": "阻断",
            "route_source_reason": "缺少 recall_gate/source_scope 等路由凭证，无法判断该走坐标门还是语义门。",
            "route_source_rule": "双轨铁门：坐标门只认坐标中心库，语义门只认语义聚拢中心库。",
            "route_source_route": "",
            "route_source_expected": "",
            "route_source_actual": clean(row.get("source_db")),
        }
    expected = roots.get(route)
    if expected is None:
        return {
            "route_source_status": "阻断",
            "route_source_reason": f"缺少 {route} 路径对应的中心库配置。",
            "route_source_rule": "双轨铁门必须配置 semantic_root_db 与 coordinate_root_db。",
            "route_source_route": route,
            "route_source_expected": "",
            "route_source_actual": clean(row.get("source_db")),
        }
    if source_path != expected:
        route_name = "坐标" if route == "coordinate" else "语义/聚拢"
        return {
            "route_source_status": "阻断",
            "route_source_reason": f"{route_name}路候选没有指向本路唯一中心库。",
            "route_source_rule": "双轨铁门：坐标路不得读语义库，语义路不得读坐标库；辅助库不得作候选源。",
            "route_source_route": route,
            "route_source_expected": str(expected),
            "route_source_actual": clean(row.get("source_db")),
        }
    return {
        "route_source_status": "通过",
        "route_source_reason": "候选来源与本路唯一中心库一致。",
        "route_source_rule": "双轨铁门通过。",
        "route_source_route": route,
        "route_source_expected": str(expected),
        "route_source_actual": clean(row.get("source_db")),
    }


@lru_cache(maxsize=1)
def _allowed_candidate_source_paths() -> set[Path]:
    root = MATERIAL_RECALL_ROOT.resolve()
    allowed: set[Path] = set()
    if MATERIAL_RECALL_RULES_JSON.exists():
        try:
            rules = json.loads(MATERIAL_RECALL_RULES_JSON.read_text(encoding="utf-8"))
            for folder, names in (rules.get("allowed_files") or {}).items():
                if folder in {"00_底库登记处", "99_专库规则"}:
                    continue
                for name in names or []:
                    path = (root / folder / name).resolve()
                    if path.suffix.lower() in FORMAL_SOURCE_SUFFIXES:
                        allowed.add(path)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    if MATERIAL_RECALL_WHITELIST_JSON.exists():
        try:
            whitelist = json.loads(MATERIAL_RECALL_WHITELIST_JSON.read_text(encoding="utf-8"))
            for entry in whitelist.get("entries") or []:
                if not entry.get("candidate_source_allowed"):
                    continue
                raw_path = clean(entry.get("formal_recall_path")).split("::", 1)[0]
                if not raw_path:
                    continue
                path = Path(raw_path).resolve()
                if path.suffix.lower() in FORMAL_SOURCE_SUFFIXES:
                    allowed.add(path)
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return allowed


def _source_db_is_allowed_candidate_file(value: str) -> bool:
    if not value:
        return False
    try:
        target = Path(value.split("::", 1)[0]).resolve()
        root = MATERIAL_RECALL_ROOT.resolve()
        if root != target and root not in target.parents:
            return False
        if target == root or target.is_dir():
            return False
        if target.suffix.lower() not in FORMAL_SOURCE_SUFFIXES:
            return False
        return target in _allowed_candidate_source_paths()
    except (OSError, RuntimeError):
        return False


def _has_formal_source(row: dict) -> bool:
    if not has_value(row, "source_db"):
        return False
    if not _source_db_is_allowed_candidate_file(clean(row.get("source_db"))):
        return False
    blob = _field_blob(row, FORMAL_SOURCE_FIELDS + ["source_trace", "retrieval_reasons"])
    if any(scope in blob for scope in FORMAL_SOURCE_SCOPES):
        return True
    if any(token in blob for token in FORMAL_SOURCE_TABLE_TOKENS):
        return True
    if has_value(row, "segment_no") and has_value(row, "chapter_no"):
        return True
    if has_value(row, "atom_code") and has_value(row, "chapter_no"):
        return True
    return False


def _engineering_source_hits(row: dict) -> list[str]:
    hits: list[str] = []
    path_blob = _field_blob(row, ENGINEERING_SOURCE_PATH_FIELDS)
    text_blob = _field_blob(row, ENGINEERING_SOURCE_PATH_FIELDS + ["source_trace", "retrieval_reasons", "source_system"])
    for field in ("source_path", "source_file", "source_db"):
        value = clean(row.get(field))
        if not value:
            continue
        try:
            target = Path(value).resolve()
            root = MATERIAL_RECALL_ROOT.resolve()
            if root != target and root not in target.parents:
                hits.append(f"{field}_outside_material_recall_root")
        except (OSError, RuntimeError):
            hits.append(f"{field}_unresolvable")
    if path_blob and any(path_blob.endswith(suffix) or suffix in path_blob for suffix in ENGINEERING_SOURCE_SUFFIXES):
        hits.append("source_path_is_process_file")
    for marker in ENGINEERING_SOURCE_MARKERS:
        if marker in text_blob:
            hits.append(marker)
    return list(dict.fromkeys(hits))


def source_scope_gate(row: dict) -> dict[str, Any]:
    engineering_hits = _engineering_source_hits(row)
    has_formal_source = _has_formal_source(row)
    route_gate = _route_source_gate(row)
    if engineering_hits:
        return {
            "source_scope_status": "阻断",
            "source_scope_reason": "来源指向工程过程文件、运行包或成品报告；工程文件只能验流程，不能作为正文候选材料。",
            "source_scope_rule": "专库出候选，工程文件只验流程；.md/.json/闭环包过程文件不得作为正文召回材料。",
            "source_scope_hits": "；".join(engineering_hits),
            **route_gate,
        }
    if route_gate["route_source_status"] == "阻断":
        return {
            "source_scope_status": "阻断",
            "source_scope_reason": route_gate["route_source_reason"],
            "source_scope_rule": route_gate["route_source_rule"],
            "source_scope_hits": "",
            **route_gate,
        }
    if has_formal_source:
        return {
            "source_scope_status": "通过",
            "source_scope_reason": "候选具备正式专库表、正文编号或原子段凭证，并通过本路唯一中心库硬门。",
            "source_scope_rule": "候选召回只承认本路中心库来源。",
            "source_scope_hits": "",
            **route_gate,
        }
    return {
        "source_scope_status": "阻断",
        "source_scope_reason": "缺少正式专库来源凭证。",
        "source_scope_rule": "每条候选必须能回到 source_scope/source_db/source_table 或 segment_no/chapter_no/atom_code。",
        "source_scope_hits": "",
        **route_gate,
    }


def judge_row(row: dict) -> dict[str, Any]:
    credentials = credential_fields(row)
    supports = supporting_fields(row)
    scope_gate = source_scope_gate(row)
    has_route = any(field in supports for field in ("codex_query_lane", "codex_query_lane_reason"))
    has_source_note = any(field in supports for field in ("source_system", "source_trace", "reasons", "triage_note"))
    has_material_bucket = any(field in supports for field in ("codex_material_bucket", "evidence_status", "bucket_reason"))

    pass_gate = (
        bool(credentials)
        and (has_route or has_source_note or has_material_bucket)
        and scope_gate["source_scope_status"] in {"通过", "警告"}
    )
    if pass_gate:
        status = "准入"
        reason = "具备编号/来源凭证，具备路径、分柜或来源说明，并通过正式专库来源硬门。"
    elif scope_gate["source_scope_status"] == "阻断":
        status = "阻断"
        reason = scope_gate["source_scope_reason"]
    elif credentials:
        status = "阻断"
        reason = "有编号或来源凭证，但缺少路径、分柜或来源说明，暂不能入材料池。"
    else:
        status = "阻断"
        reason = "缺少 line_id / segment_no / 聚拢总图节点 / 聚拢层级 / chapter_no / 来源链 / 原文回收等入池凭证。"

    return {
        "material_admission_status": status,
        "material_admission_reason": reason,
        "material_admission_credentials": "；".join(credentials),
        "material_admission_supports": "；".join(supports),
        "material_admission_rule": "材料池不得接收没有正式专库来源、聚拢总图编号来源、穷尽来源说明、路由门说明或原文锚点的材料；工程过程文件只作流程凭证，不作正文召回材料。",
        **scope_gate,
    }


def apply_gate(rows: list[dict], question: str = "", route_context: str = "") -> dict[str, Any]:
    admitted_rows: list[dict] = []
    blocked_rows: list[dict] = []
    all_rows: list[dict] = []

    for row in rows:
        gate = judge_row(row)
        enriched = {**row, **gate}
        all_rows.append(enriched)
        if gate["material_admission_status"] == "准入":
            admitted_rows.append(enriched)
        else:
            blocked_rows.append(enriched)

    status_counts = Counter(row["material_admission_status"] for row in all_rows)
    credential_counts = Counter()
    for row in all_rows:
        for field in clean(row.get("material_admission_credentials")).split("；"):
            if field:
                credential_counts[field] += 1

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "route_context": route_context,
        "status": "completed",
        "rule": "材料池入池前必须有聚拢总图编号来源、穷尽来源说明、路由门说明或原文锚点。",
        "total_rows": len(all_rows),
        "admitted_count": len(admitted_rows),
        "blocked_count": len(blocked_rows),
        "status_counts": dict(status_counts),
        "credential_counts": dict(credential_counts),
        "all_rows": all_rows,
        "admitted_rows": admitted_rows,
        "blocked_rows": blocked_rows,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def render_report(result: dict[str, Any], blocked_csv: Path) -> str:
    lines = [
        "# 材料池入池凭证门",
        "",
        f"生成时间：{result['generated_at']}",
        "",
        "## 一句话结论",
        "",
        result["rule"],
        "",
        "## 数量",
        "",
        f"- 候选材料总数：{result['total_rows']}",
        f"- 准入材料：{result['admitted_count']}",
        f"- 阻断材料：{result['blocked_count']}",
        "",
        "## 凭证分布",
        "",
    ]
    if result["credential_counts"]:
        for key, count in result["credential_counts"].items():
            lines.append(f"- {key}：{count}")
    else:
        lines.append("- 暂无凭证。")
    lines.extend(
        [
            "",
            "## 阻断队列",
            "",
            f"- `{blocked_csv}`",
            "",
            "## 硬规则",
            "",
            "```text",
            "旧搜索不能直接入材料池。",
            "旧候选提示不能直接决定材料池。",
            "材料必须先有聚拢总图编号来源、穷尽来源说明、路由门说明或原文锚点。",
            "阻断材料可保留为问题债或补证对象，但不能混入 Codex 材料池阅读顺序。",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_gate_outputs(md_path: Path, json_path: Path, blocked_csv: Path, result: dict[str, Any]) -> None:
    blocked_rows = result.get("blocked_rows", [])
    write_csv(blocked_csv, blocked_rows)
    public_result = {key: value for key, value in result.items() if key not in {"admitted_rows", "blocked_rows"}}
    public_result["blocked_csv"] = str(blocked_csv)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(public_result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_report(public_result, blocked_csv), encoding="utf-8")
