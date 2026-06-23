#!/usr/bin/env python3
"""Standalone coordinate-search workbench for the Honglou project.

This program does not import or mutate the legacy research app. It reads the
published coordinate mapping database and writes a per-query evidence package.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3")
DB_PATH = ROOT / "outputs/红楼梦聚拢坐标映射总库_CH001_120/红楼梦聚拢坐标映射总库_CH001_120.sqlite"
RUN_ROOT = ROOT / "outputs/红楼梦坐标搜索工作台/runs"
DECISION_DOC = ROOT / "outputs/红楼梦坐标搜索工作台/00_二选一决策_独立坐标程序.md"

PERSON_ALIASES: dict[str, list[str]] = {
    "宝玉": ["宝玉", "贾宝玉"],
    "贾宝玉": ["宝玉", "贾宝玉"],
    "黛玉": ["黛玉", "林黛玉"],
    "林黛玉": ["黛玉", "林黛玉"],
    "宝钗": ["宝钗", "薛宝钗"],
    "薛宝钗": ["宝钗", "薛宝钗"],
    "湘云": ["湘云", "史湘云"],
    "史湘云": ["湘云", "史湘云"],
    "妙玉": ["妙玉"],
    "晴雯": ["晴雯"],
    "袭人": ["袭人"],
}

SEASON_ALIASES: dict[str, list[str]] = {
    "春": ["春", "春天", "春日"],
    "春天": ["春", "春天", "春日"],
    "夏": ["夏", "夏天", "炎夏"],
    "夏天": ["夏", "夏天", "炎夏"],
    "秋": ["秋", "秋天", "秋日", "秋夜", "中秋", "深秋", "秋冬"],
    "秋天": ["秋", "秋天", "秋日", "秋夜", "中秋", "深秋", "秋冬"],
    "冬": ["冬", "冬天", "冬日", "雪", "寒"],
    "冬天": ["冬", "冬天", "冬日", "雪", "寒"],
}

OBJECT_ALIASES: dict[str, list[str]] = {
    "花": ["花", "海棠", "菊", "菊花", "芙蓉", "梅花", "桃花", "杏花", "梨花", "荷花", "蔷薇", "牡丹", "芍药"],
    "海棠": ["海棠", "白海棠"],
    "菊花": ["菊", "菊花"],
    "玉": ["玉", "通灵宝玉"],
    "诗": ["诗", "诗词", "诗稿", "诗社"],
    "冷": ["冷", "寒", "霜", "雪", "秋雨", "夜", "孤", "清", "病", "薄衣", "冷月"],
}

SPACE_ALIASES: dict[str, list[str]] = {
    "大观园": ["大观园"],
    "潇湘馆": ["潇湘馆"],
    "怡红院": ["怡红院"],
    "蘅芜苑": ["蘅芜苑"],
    "藕香榭": ["藕香榭"],
    "秋爽斋": ["秋爽斋"],
}

VARIABLE_TYPES = {
    "person": ["person", "scene_person_hint"],
    "season": ["season", "time_axis", "time_point", "time_block_label"],
    "object": ["object", "poem", "event", "scene_object_hint"],
    "space": ["space", "scene_space_hint"],
}


@dataclass
class QueryFacet:
    facet_type: str
    name: str
    aliases: list[str]


def clean(text: Any) -> str:
    return str(text or "").strip()


def safe_name(text: str, limit: int = 60) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "_", text).strip("_")
    return (text or "query")[:limit]


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def detect_facets(query: str) -> list[QueryFacet]:
    facets: list[QueryFacet] = []
    seen: set[tuple[str, str]] = set()
    object_query = query

    def add(facet_type: str, name: str, aliases: list[str]) -> None:
        key = (facet_type, name)
        if key in seen:
            return
        seen.add(key)
        facets.append(QueryFacet(facet_type, name, aliases))

    for name, aliases in PERSON_ALIASES.items():
        if name in query:
            canonical = "贾宝玉" if name in {"宝玉", "贾宝玉"} else "林黛玉" if name in {"黛玉", "林黛玉"} else aliases[-1]
            add("person", canonical, aliases)
            for alias in aliases:
                object_query = object_query.replace(alias, "")
    for name, aliases in SEASON_ALIASES.items():
        if name in query:
            canonical = "秋" if name in {"秋", "秋天"} else "春" if name in {"春", "春天"} else "夏" if name in {"夏", "夏天"} else "冬" if name in {"冬", "冬天"} else name
            add("season", canonical, aliases)
    for name, aliases in OBJECT_ALIASES.items():
        if name in object_query:
            add("object", name, aliases)
    for name, aliases in SPACE_ALIASES.items():
        if name in query:
            add("space", name, aliases)
    if not facets:
        # Fallback: use short Chinese words as broad object/text facets.
        for token in re.findall(r"[\u4e00-\u9fff]{1,4}", query):
            add("object", token, [token])
    return facets


def placeholders(values: list[str]) -> str:
    return ", ".join("?" for _ in values)


def fetch_atom_ids_for_facet(conn: sqlite3.Connection, facet: QueryFacet) -> dict[str, dict[str, Any]]:
    rows_by_atom: dict[str, dict[str, Any]] = {}
    link_types = VARIABLE_TYPES.get(facet.facet_type, [])
    for alias in facet.aliases:
        like = f"%{alias}%"
        params: list[Any] = []
        where_parts: list[str] = []
        if link_types:
            where_parts.append(f"(variable_type IN ({placeholders(link_types)}) AND (variable_value_name LIKE ? OR variable_value_id LIKE ?))")
            params.extend(link_types)
            params.extend([like, like])
        else:
            where_parts.append("(variable_value_name LIKE ?)")
            params.append(like)
        sql = f"""
            SELECT atom_id, atom_code, variable_type, variable_value_name, granularity_level,
                   evidence_grade, confidence, coordinate_summary
            FROM atom_projection_codebook
            WHERE {' OR '.join(where_parts)}
        """
        for row in conn.execute(sql, params):
            atom_id = row["atom_id"]
            current = rows_by_atom.setdefault(
                atom_id,
                {
                    "atom_id": atom_id,
                    "atom_code": row["atom_code"],
                    "facet": facet.name,
                    "facet_type": facet.facet_type,
                    "hits": [],
                    "best_grade": "",
                    "best_confidence": 0.0,
                    "coordinate_summary": row["coordinate_summary"],
                },
            )
            current["hits"].append(
                {
                    "alias": alias,
                    "variable_type": row["variable_type"],
                    "value": row["variable_value_name"],
                    "granularity_level": row["granularity_level"],
                    "evidence_grade": row["evidence_grade"],
                    "confidence": row["confidence"],
                }
            )
            try:
                current["best_confidence"] = max(float(current["best_confidence"]), float(row["confidence"] or 0))
            except ValueError:
                pass
            grade = clean(row["evidence_grade"])
            if grade == "hard" or not current["best_grade"]:
                current["best_grade"] = grade

        # Literal fallback in source text/summary. This catches words not yet
        # mapped into atom_projection_codebook.
        if facet.facet_type in {"object", "season", "space"}:
            for row in conn.execute(
                """
                SELECT c.atom_id, c.atom_code, c.coordinate_summary
                FROM clean_atoms a
                JOIN atom_codebook c ON c.atom_id=a.atom_id
                WHERE a.summary LIKE ? OR a.quote LIKE ?
                """,
                (like, like),
            ):
                atom_id = row["atom_id"]
                current = rows_by_atom.setdefault(
                    atom_id,
                    {
                        "atom_id": atom_id,
                        "atom_code": row["atom_code"],
                        "facet": facet.name,
                        "facet_type": facet.facet_type,
                        "hits": [],
                        "best_grade": "literal",
                        "best_confidence": 0.7,
                        "coordinate_summary": row["coordinate_summary"],
                    },
                )
                current["hits"].append(
                    {
                        "alias": alias,
                        "variable_type": "literal_text",
                        "value": alias,
                        "granularity_level": "atom",
                        "evidence_grade": "literal",
                        "confidence": 0.7,
                    }
                )
    return rows_by_atom


def atom_context(conn: sqlite3.Connection, atom_id: str) -> dict[str, Any]:
    row = atom_basic_row(conn, atom_id)
    if not row:
        return {}
    context = dict(row)
    context["same_scene_variables"] = grouped_values(
        conn,
        """
        SELECT p.variable_type, p.variable_value_name, COUNT(DISTINCT p.atom_id) AS n
        FROM atom_codebook c
        JOIN atom_projection_codebook p ON p.atom_id=c.atom_id
        WHERE c.scene_id=? AND p.evidence_grade IN ('hard', 'resolved', 'literal', 'context')
        GROUP BY p.variable_type, p.variable_value_name
        ORDER BY n DESC, p.variable_type, p.variable_value_name
        LIMIT 30
        """,
        (row["scene_id"],),
    )
    context["same_event_variables"] = grouped_values(
        conn,
        """
        SELECT p.variable_type, p.variable_value_name, COUNT(DISTINCT p.atom_id) AS n
        FROM atom_codebook c
        JOIN atom_projection_codebook p ON p.atom_id=c.atom_id
        WHERE c.event_id=? AND p.variable_type IN ('person', 'object', 'space', 'season', 'poem')
        GROUP BY p.variable_type, p.variable_value_name
        ORDER BY n DESC, p.variable_type, p.variable_value_name
        LIMIT 30
        """,
        (row["event_id"],),
    )
    return context


def atom_basic_row(conn: sqlite3.Connection, atom_id: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT c.atom_id, c.atom_code, c.old_segment_no, c.global_atom_order, c.chapter_no,
               c.coordinate_summary, c.overlap_status, c.summary, c.quote,
               c.cluster_id, c.event_id, c.scene_id, c.scene_group_id, c.time_block_id
        FROM atom_codebook c
        WHERE c.atom_id=?
        """,
        (atom_id,),
    ).fetchone()


def atom_basic(conn: sqlite3.Connection, atom_id: str) -> dict[str, Any]:
    row = atom_basic_row(conn, atom_id)
    return dict(row) if row else {}


def grouped_values(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def nearest_for_missing_facets(
    conn: sqlite3.Connection,
    atom_id: str,
    missing_facets: list[QueryFacet],
    facet_hits: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    base = conn.execute("SELECT * FROM atom_codebook WHERE atom_id=?", (atom_id,)).fetchone()
    if not base:
        return out
    for facet in missing_facets:
        candidates = facet_hits.get(facet_key(facet), {})
        best: dict[str, Any] | None = None
        for target in fetch_codebook_rows(conn, list(candidates.keys())):
            if int(base["chapter_no"]) != int(target["chapter_no"]):
                continue
            signed_distance = int(target["global_atom_order"]) - int(base["global_atom_order"])
            abs_distance = abs(signed_distance)
            same_chapter = int(base["chapter_no"] == target["chapter_no"])
            same_cluster = int(clean(base["cluster_id"]) and base["cluster_id"] == target["cluster_id"])
            same_event = int(clean(base["event_id"]) and base["event_id"] == target["event_id"])
            same_scene = int(clean(base["scene_id"]) and base["scene_id"] == target["scene_id"])
            same_scene_group = int(clean(base["scene_group_id"]) and base["scene_group_id"] == target["scene_group_id"])
            same_time_block = int(clean(base["time_block_id"]) and base["time_block_id"] == target["time_block_id"])
            score = (
                same_scene * 100000
                + same_scene_group * 50000
                + same_event * 20000
                + same_time_block * 10000
                - abs_distance
            )
            if best is None or score > best["score"]:
                best = {
                    "score": score,
                    "facet": facet.name,
                    "facet_type": facet.facet_type,
                    "target_atom_id": target["atom_id"],
                    "from_atom_code": base["atom_code"],
                    "to_atom_code": target["atom_code"],
                    "signed_atom_distance": signed_distance,
                    "abs_atom_distance": abs_distance,
                    "direction_from_source": "after" if signed_distance > 0 else "before" if signed_distance < 0 else "same",
                    "same_chapter": same_chapter,
                    "same_cluster": same_cluster,
                    "same_event": same_event,
                    "same_scene": same_scene,
                    "same_scene_group": same_scene_group,
                    "same_time_block": same_time_block,
                }
        if best:
            target = atom_basic(conn, best["target_atom_id"])
            best["target_summary"] = target.get("summary", "")
            best["target_old_segment_no"] = target.get("old_segment_no", "")
            out.append(best)
    return out


def fetch_codebook_rows(conn: sqlite3.Connection, atom_ids: list[str]) -> list[sqlite3.Row]:
    rows: list[sqlite3.Row] = []
    ids = list(dict.fromkeys(atom_ids))
    for i in range(0, len(ids), 800):
        chunk = ids[i : i + 800]
        if not chunk:
            continue
        rows.extend(
            conn.execute(
                f"""
                SELECT atom_id, atom_code, global_atom_order, chapter_no,
                       cluster_id, event_id, scene_id, scene_group_id, time_block_id
                FROM atom_codebook
                WHERE atom_id IN ({placeholders(chunk)})
                """,
                chunk,
            ).fetchall()
        )
    return rows


def facet_key(facet: QueryFacet) -> str:
    return f"{facet.facet_type}:{facet.name}"


def run_query(query: str, limit: int = 20) -> dict[str, Any]:
    conn = connect()
    try:
        facets = detect_facets(query)
        facet_hits = {facet_key(facet): fetch_atom_ids_for_facet(conn, facet) for facet in facets}
        all_atom_ids = sorted({atom_id for hits in facet_hits.values() for atom_id in hits})
        scores: dict[str, dict[str, Any]] = {}
        base_items: list[dict[str, Any]] = []
        for atom_id in all_atom_ids:
            matched: list[dict[str, Any]] = []
            missing: list[QueryFacet] = []
            for facet in facets:
                hits = facet_hits[facet_key(facet)]
                if atom_id in hits:
                    matched.append(hits[atom_id])
                else:
                    missing.append(facet)
            context = atom_basic(conn, atom_id)
            if not context:
                continue
            strict_count = len(matched)
            hardish = sum(1 for item in matched if item.get("best_grade") in {"hard", "resolved", "literal"})
            score = strict_count * 1000 + hardish * 100
            base_items.append(
                {
                    "atom_id": atom_id,
                    "score": score,
                    "matched": matched,
                    "missing": missing,
                    "context": context,
                    "strict_count": strict_count,
                }
            )

        base_items = sorted(
            base_items,
            key=lambda item: (
                item["strict_count"],
                item["score"],
                -int(item["context"].get("global_atom_order") or 0),
            ),
            reverse=True,
        )
        scan_limit = max(limit * 8, 80)
        for item in base_items[:scan_limit]:
            atom_id = item["atom_id"]
            matched = item["matched"]
            missing = item["missing"]
            context = item["context"]
            strict_count = item["strict_count"]
            score = item["score"]
            nearest = nearest_for_missing_facets(conn, atom_id, missing, facet_hits) if missing else []
            same_scene_bonus = 0
            for near in nearest:
                same_scene_bonus += int(near.get("same_scene") or 0) * 60
                same_scene_bonus += int(near.get("same_scene_group") or 0) * 40
                same_scene_bonus += int(near.get("same_event") or 0) * 20
                same_scene_bonus -= min(int(near.get("abs_atom_distance") or 999), 99)
            score += same_scene_bonus
            full_context = atom_context(conn, atom_id)
            scores[atom_id] = {
                "score": score,
                "matched_count": strict_count,
                "total_facets": len(facets),
                "matched_facets": matched,
                "missing_facets": [facet.__dict__ for facet in missing],
                "nearest_for_missing": nearest,
                "context": full_context or context,
            }

        ranked = sorted(
            scores.values(),
            key=lambda item: (
                item["matched_count"] == item["total_facets"],
                item["score"],
                -int(item["context"].get("global_atom_order") or 0),
            ),
            reverse=True,
        )[:limit]
        return {
            "query": query,
            "mode": "coordinate_search_standalone",
            "decision": "独立坐标程序，不接入旧程序分支，不修改旧工程。",
            "db_path": str(DB_PATH),
            "facet_count": len(facets),
            "facets": [facet.__dict__ for facet in facets],
            "facet_hit_counts": {key: len(value) for key, value in facet_hits.items()},
            "candidate_count": len(scores),
            "results": ranked,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    finally:
        conn.close()


def write_package(payload: dict[str, Any]) -> tuple[Path, Path]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + safe_name(payload["query"])
    out_dir = RUN_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "coordinate_search_result.json"
    md_path = out_dir / "coordinate_search_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 红楼梦坐标搜索工作台结果",
        "",
        f"- 查询：{payload['query']}",
        f"- 模式：{payload['mode']}",
        f"- 决策：{payload['decision']}",
        f"- 总库：`{payload['db_path']}`",
        f"- 识别变量数：{payload['facet_count']}",
        f"- 候选原子段数：{payload['candidate_count']}",
        "",
        "## 识别变量",
        "",
    ]
    for facet in payload["facets"]:
        lines.append(f"- {facet['facet_type']} / {facet['name']}：{'、'.join(facet['aliases'])}")
    lines.extend(["", "## 变量命中规模", ""])
    for key, count in payload["facet_hit_counts"].items():
        lines.append(f"- {key}: {count}")
    lines.extend(["", "## 排名前列", ""])
    for index, item in enumerate(payload["results"][:15], start=1):
        context = item["context"]
        lines.extend(
            [
                f"### {index}. {context.get('atom_id')} / {context.get('atom_code')} / {context.get('old_segment_no')}",
                "",
                f"- score: {item['score']}",
                f"- matched: {item['matched_count']} / {item['total_facets']}",
                f"- coordinate: `{context.get('coordinate_summary')}`",
                f"- summary: {context.get('summary')}",
                f"- quote: {shorten(context.get('quote'), 180)}",
                "- matched_facets:",
            ]
        )
        for matched in item["matched_facets"]:
            values = []
            for hit in matched.get("hits", [])[:5]:
                values.append(f"{hit.get('variable_type')}={hit.get('value')}[{hit.get('evidence_grade')}]")
            lines.append(f"  - {matched['facet_type']} / {matched['facet']}: " + "；".join(values))
        if item["missing_facets"]:
            lines.append("- missing_facets:")
            for missing in item["missing_facets"]:
                lines.append(f"  - {missing['facet_type']} / {missing['name']}")
        if item["nearest_for_missing"]:
            lines.append("- nearest_for_missing:")
            for near in item["nearest_for_missing"]:
                lines.append(
                    f"  - {near['facet_type']} / {near['facet']} -> {near['to_atom_code']} distance={near['abs_atom_distance']} same_scene={near['same_scene']} same_event={near['same_event']} summary={near.get('target_summary')}"
                )
        lines.append("- same_scene_variables_top:")
        for value in context.get("same_scene_variables", [])[:10]:
            lines.append(f"  - {value['variable_type']} / {value['variable_value_name']} ({value['n']})")
        lines.append("")
    return "\n".join(lines) + "\n"


def shorten(value: Any, limit: int) -> str:
    text = " ".join(clean(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def write_decision_doc() -> None:
    DECISION_DOC.parent.mkdir(parents=True, exist_ok=True)
    DECISION_DOC.write_text(
        """# 二选一决策：先建独立坐标搜索程序

## 结论

选第一种：新建一个独立坐标搜索程序，模拟旧程序的查询工作台，但中间算法完全换成坐标法。

## 不选旧程序内部分叉的理由

旧程序已经承载入口、队列、闭环包、Codex 召回、材料池和最终答案门。现在把坐标算法直接塞进旧搜索链路，会同时影响旧语义召回、聚拢裁判、队列状态和前端回显，一旦打架，很难判断是旧流程错、坐标算法错，还是路由状态错。

## 独立程序的原则

- 旧程序不动。
- 旧工程不写回。
- 坐标程序只读 `红楼梦聚拢坐标映射总库_CH001_120.sqlite`。
- 坐标程序自己识别触发词、变量、人物、季节、物象、空间。
- 命中后直接展开原子段、聚拢单元、事件、场面、时间块、同场变量和距离。
- 每次查询单独落一个结果包，便于和旧语义查法对照。

## 未来合流方式

等独立坐标程序稳定后，再在旧程序前门加一个轻量路由：用户选择“坐标门”或“语义探索门”。此时旧程序只负责分门，不负责混跑算法。
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--query", dest="query_opt", default="")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    query = clean(args.query_opt or args.query)
    if not query:
        raise SystemExit("缺少查询问题。")
    write_decision_doc()
    payload = run_query(query, args.limit)
    json_path, md_path = write_package(payload)
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
