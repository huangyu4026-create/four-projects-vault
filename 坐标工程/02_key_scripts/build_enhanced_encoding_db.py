#!/usr/bin/env python3
"""Build an enhanced encoding explanation layer for Honglou atom coordinates.

The enhanced layer does not change atom_id or atom_code. It adds coordinate
summaries, granularity, evidence grade, primary/secondary container readings,
range codes, and directed distance views.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3")
DEFAULT_SOURCE_DB = ROOT / "outputs/红楼梦干净聚拢坐标库_CH001_120_全量/红楼梦干净聚拢坐标库_CH001_120_全量.sqlite"
OUTPUT_ROOT = ROOT / "outputs"
OUTPUT_BASENAME = "红楼梦编码增强追加层"


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def stable_id(prefix: str, *parts: Any, size: int = 14) -> str:
    raw = "\u241f".join(clean(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:size].upper()}"


def coord_part(value: Any, empty: str = "NA") -> str:
    text = clean(value)
    return text if text else empty


def range_code(start_order: int | None, end_order: int | None) -> str:
    if start_order is None or end_order is None:
        return "G??????-G??????"
    return f"G{int(start_order):06d}-G{int(end_order):06d}"


def atom_range_code(global_order: int) -> str:
    return f"G{int(global_order):06d}"


def coordinate_summary(row: dict[str, Any]) -> str:
    return " / ".join(
        [
            coord_part(row.get("atom_id")),
            coord_part(row.get("atom_code")),
            f"G{int(row['global_atom_order']):06d}",
            f"CH{int(row['chapter_no']):03d}",
            coord_part(row.get("cluster_id"), "CU-NA"),
            coord_part(row.get("event_id"), "EV-NA"),
            coord_part(row.get("scene_id"), "SC-NA"),
            coord_part(row.get("scene_group_id"), "SG-NA"),
            coord_part(row.get("time_block_id"), "TB-NA"),
        ]
    )


def infer_granularity(scope: str, precision: str, source_name: str) -> str:
    scope = clean(scope)
    precision = clean(precision)
    source_name = clean(source_name)
    if "chapter_level" in precision or scope == "chapter":
        return "chapter"
    if scope == "time_block" or "time_block" in precision:
        return "time_block"
    if scope == "scene_point" or "scene" in precision:
        return "scene"
    if "event" in precision or "event" in source_name:
        return "event"
    if scope == "atom":
        return "atom"
    return scope or "unknown"


def infer_evidence_grade(review_status: str, precision: str, confidence: Any) -> str:
    review_status = clean(review_status)
    precision = clean(precision)
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    if "needs_review" in review_status or "uncertain" in review_status:
        return "needs_review"
    if "chapter_level" in review_status or "chapter_level" in precision:
        return "chapter_context"
    if review_status.startswith("hint"):
        return "hint"
    if review_status in {"raw_field", "range_context"}:
        return "context"
    if conf >= 0.95 and review_status == "resolved":
        return "hard"
    if review_status == "resolved":
        return "resolved"
    return review_status or "unknown"


SCHEMA = """
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;

CREATE TABLE build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE atom_codebook (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    old_segment_no TEXT NOT NULL,
    global_atom_order INTEGER NOT NULL,
    linear_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    chapter_code TEXT NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    self_range_code TEXT NOT NULL,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    coordinate_summary TEXT NOT NULL,
    overlap_status TEXT NOT NULL,
    scene_membership_count INTEGER NOT NULL,
    scene_group_membership_count INTEGER NOT NULL,
    time_block_membership_count INTEGER NOT NULL,
    primary_scene_id TEXT,
    secondary_scene_ids TEXT,
    primary_scene_group_id TEXT,
    secondary_scene_group_ids TEXT,
    primary_time_block_id TEXT,
    secondary_time_block_ids TEXT,
    summary TEXT,
    quote TEXT
);

CREATE TABLE container_codebook (
    container_code_id TEXT PRIMARY KEY,
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    start_atom_order INTEGER,
    end_atom_order INTEGER,
    start_atom_id TEXT,
    end_atom_id TEXT,
    start_atom_code TEXT,
    end_atom_code TEXT,
    range_code TEXT NOT NULL,
    atom_count INTEGER,
    coordinate_summary TEXT NOT NULL,
    boundary_status TEXT NOT NULL,
    review_status TEXT
);

CREATE TABLE atom_projection_codebook (
    projection_code_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    atom_code TEXT NOT NULL,
    variable_type TEXT NOT NULL,
    variable_value_id TEXT,
    variable_value_name TEXT NOT NULL,
    variable_role TEXT,
    granularity_level TEXT NOT NULL,
    evidence_grade TEXT NOT NULL,
    scope TEXT,
    precision TEXT,
    confidence REAL,
    review_status TEXT,
    coordinate_summary TEXT NOT NULL
);

CREATE TABLE coordinate_reading_rules (
    rule_key TEXT PRIMARY KEY,
    rule_label TEXT NOT NULL,
    reading_rule TEXT NOT NULL
);

CREATE VIEW v_enhanced_atom_distance AS
SELECT
    a.atom_id AS from_atom_id,
    b.atom_id AS to_atom_id,
    a.atom_code AS from_atom_code,
    b.atom_code AS to_atom_code,
    b.global_atom_order - a.global_atom_order AS signed_atom_distance,
    ABS(b.global_atom_order - a.global_atom_order) AS abs_atom_distance,
    CASE
        WHEN b.global_atom_order > a.global_atom_order THEN 'after'
        WHEN b.global_atom_order < a.global_atom_order THEN 'before'
        ELSE 'same'
    END AS direction_from_source,
    CASE WHEN a.chapter_no = b.chapter_no THEN 1 ELSE 0 END AS same_chapter,
    CASE WHEN a.cluster_id IS NOT NULL AND a.cluster_id = b.cluster_id THEN 1 ELSE 0 END AS same_cluster,
    CASE WHEN a.event_id IS NOT NULL AND a.event_id = b.event_id THEN 1 ELSE 0 END AS same_event,
    CASE WHEN a.scene_id IS NOT NULL AND a.scene_id = b.scene_id THEN 1 ELSE 0 END AS same_scene,
    CASE WHEN a.scene_group_id IS NOT NULL AND a.scene_group_id = b.scene_group_id THEN 1 ELSE 0 END AS same_scene_group,
    CASE WHEN a.time_block_id IS NOT NULL AND a.time_block_id = b.time_block_id THEN 1 ELSE 0 END AS same_time_block
FROM atom_codebook a
JOIN atom_codebook b ON 1=1;
"""


INDEXES = """
CREATE INDEX idx_atom_codebook_order ON atom_codebook(global_atom_order);
CREATE INDEX idx_atom_codebook_scene ON atom_codebook(scene_id);
CREATE INDEX idx_atom_codebook_event ON atom_codebook(event_id);
CREATE INDEX idx_container_codebook_type_id ON container_codebook(container_type, container_id);
CREATE INDEX idx_container_codebook_range ON container_codebook(start_atom_order, end_atom_order);
CREATE INDEX idx_projection_type_value ON atom_projection_codebook(variable_type, variable_value_name);
CREATE INDEX idx_projection_atom ON atom_projection_codebook(atom_id);
CREATE INDEX idx_projection_grade ON atom_projection_codebook(granularity_level, evidence_grade);
"""


def rowdict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def split_ids(value: str) -> list[str]:
    return [item for item in clean(value).split(" | ") if item]


def join_ids(values: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return " | ".join(out)


def membership_ids(conn: sqlite3.Connection, atom_id: str, container_type: str) -> list[str]:
    return [
        row["container_id"]
        for row in conn.execute(
            """
            SELECT container_id
            FROM atom_memberships
            WHERE atom_id=? AND container_type=?
            ORDER BY is_primary DESC, order_in_container, container_id
            """,
            (atom_id, container_type),
        )
    ]


def build(start: int, end: int, label: str, source_db: Path) -> tuple[Path, Path]:
    safe_label = label or f"CH{start:03d}_{end:03d}"
    out_dir = OUTPUT_ROOT / f"{OUTPUT_BASENAME}_CH{start:03d}_{end:03d}_{safe_label}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_db = out_dir / f"{OUTPUT_BASENAME}_CH{start:03d}_{end:03d}_{safe_label}.sqlite"
    report = out_dir / f"{OUTPUT_BASENAME}_CH{start:03d}_{end:03d}_{safe_label}_说明与验收.md"
    for path in [out_db, Path(f"{out_db}-wal"), Path(f"{out_db}-shm")]:
        if path.exists():
            path.unlink()

    src = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(out_db)
    dst.row_factory = sqlite3.Row
    dst.executescript(SCHEMA)
    dst.executemany(
        "INSERT INTO build_meta(key,value) VALUES (?,?)",
        [
            ("build_name", f"{OUTPUT_BASENAME}_CH{start:03d}_{end:03d}_{safe_label}"),
            ("built_at_utc", datetime.now(timezone.utc).isoformat()),
            ("range", f"CH{start:03d}-CH{end:03d}"),
            ("principle", "主编号不变；追加解释层；不把人物、季节、空间、药病等变量写入主编号。"),
        ],
    )

    atoms = [
        rowdict(row)
        for row in src.execute(
            """
            SELECT a.*, d.cluster_id, d.event_id, d.scene_id, d.scene_group_id, d.time_block_id
            FROM clean_atoms a
            JOIN atom_distance_basis d ON d.atom_id=a.atom_id
            WHERE a.chapter_no BETWEEN ? AND ?
            ORDER BY a.global_atom_order
            """,
            (start, end),
        )
    ]
    atom_by_id = {atom["atom_id"]: atom for atom in atoms}
    atom_by_order = {atom["global_atom_order"]: atom for atom in atoms}
    code_rows = []
    for atom in atoms:
        scene_ids = membership_ids(src, atom["atom_id"], "scene_point")
        scene_group_ids = membership_ids(src, atom["atom_id"], "scene_group")
        time_block_ids = membership_ids(src, atom["atom_id"], "time_block")
        overlap_flags = []
        if len(scene_ids) > 1:
            overlap_flags.append("multi_scene")
        if len(scene_group_ids) > 1:
            overlap_flags.append("multi_scene_group")
        if len(time_block_ids) > 1:
            overlap_flags.append("multi_time_block")
        if not scene_group_ids:
            overlap_flags.append("missing_scene_group")
        if not overlap_flags:
            overlap_status = "single_primary"
        else:
            overlap_status = "|".join(overlap_flags)
        atom["coordinate_summary"] = coordinate_summary(atom)
        code_rows.append(
            (
                atom["atom_id"],
                atom["atom_code"],
                atom["old_segment_no"],
                atom["global_atom_order"],
                atom_range_code(atom["global_atom_order"]),
                atom["chapter_no"],
                f"CH{int(atom['chapter_no']):03d}",
                atom["atom_order_in_chapter"],
                atom_range_code(atom["global_atom_order"]),
                atom["cluster_id"],
                atom["event_id"],
                atom["scene_id"],
                atom["scene_group_id"],
                atom["time_block_id"],
                atom["coordinate_summary"],
                overlap_status,
                len(scene_ids),
                len(scene_group_ids),
                len(time_block_ids),
                scene_ids[0] if scene_ids else None,
                join_ids(scene_ids[1:]),
                scene_group_ids[0] if scene_group_ids else None,
                join_ids(scene_group_ids[1:]),
                time_block_ids[0] if time_block_ids else None,
                join_ids(time_block_ids[1:]),
                atom["summary"],
                atom["quote"],
            )
        )
    dst.executemany(
        """
        INSERT INTO atom_codebook (
            atom_id, atom_code, old_segment_no, global_atom_order, linear_code,
            chapter_no, chapter_code, atom_order_in_chapter, self_range_code,
            cluster_id, event_id, scene_id, scene_group_id, time_block_id,
            coordinate_summary, overlap_status, scene_membership_count,
            scene_group_membership_count, time_block_membership_count,
            primary_scene_id, secondary_scene_ids, primary_scene_group_id,
            secondary_scene_group_ids, primary_time_block_id, secondary_time_block_ids,
            summary, quote
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        code_rows,
    )

    container_rows = []
    for row in src.execute(
        """
        SELECT *
        FROM container_index
        WHERE chapter_no BETWEEN ? AND ?
        ORDER BY start_atom_order, container_type, container_id
        """,
        (start, end),
    ):
        item = rowdict(row)
        start_atom = atom_by_order.get(item["start_atom_order"])
        end_atom = atom_by_order.get(item["end_atom_order"])
        boundary_status = "single_atom" if item["atom_count"] == 1 else "range"
        if item["review_status"] and "needs_review" in item["review_status"]:
            boundary_status = f"{boundary_status}|needs_review"
        summary = " / ".join(
            [
                item["container_type"],
                item["container_id"],
                range_code(item["start_atom_order"], item["end_atom_order"]),
                f"CH{int(item['chapter_no']):03d}" if item["chapter_no"] is not None else "CH-NA",
            ]
        )
        container_rows.append(
            (
                stable_id("CC", item["container_type"], item["container_id"]),
                item["container_type"],
                item["container_id"],
                item["container_label"],
                item["chapter_no"],
                item["start_atom_order"],
                item["end_atom_order"],
                start_atom["atom_id"] if start_atom else None,
                end_atom["atom_id"] if end_atom else None,
                start_atom["atom_code"] if start_atom else None,
                end_atom["atom_code"] if end_atom else None,
                range_code(item["start_atom_order"], item["end_atom_order"]),
                item["atom_count"],
                summary,
                boundary_status,
                item["review_status"],
            )
        )
    dst.executemany(
        """
        INSERT INTO container_codebook (
            container_code_id, container_type, container_id, container_label, chapter_no,
            start_atom_order, end_atom_order, start_atom_id, end_atom_id,
            start_atom_code, end_atom_code, range_code, atom_count,
            coordinate_summary, boundary_status, review_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        container_rows,
    )

    projection_rows = []
    for row in src.execute(
        """
        SELECT l.*, a.atom_code, a.chapter_no
        FROM atom_links l
        JOIN clean_atoms a ON a.atom_id=l.atom_id
        WHERE a.chapter_no BETWEEN ? AND ?
        ORDER BY a.global_atom_order, l.link_type, l.link_value_name
        """,
        (start, end),
    ):
        item = rowdict(row)
        atom = atom_by_id[item["atom_id"]]
        granularity = infer_granularity(item["scope"], item["precision"], item["source_name"])
        grade = infer_evidence_grade(item["review_status"], item["precision"], item["confidence"])
        projection_rows.append(
            (
                stable_id("PC", item["link_id"]),
                item["atom_id"],
                atom["atom_code"],
                item["link_type"],
                item["link_value_id"],
                item["link_value_name"],
                item["link_role"],
                granularity,
                grade,
                item["scope"],
                item["precision"],
                item["confidence"],
                item["review_status"],
                atom["coordinate_summary"],
            )
        )
    dst.executemany(
        """
        INSERT INTO atom_projection_codebook (
            projection_code_id, atom_id, atom_code, variable_type, variable_value_id,
            variable_value_name, variable_role, granularity_level, evidence_grade,
            scope, precision, confidence, review_status, coordinate_summary
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        projection_rows,
    )

    rules = [
        ("short_doorplate", "短门牌", "atom_id 和 atom_code 只负责定位，不承载人物、季节、空间、物件等变量。"),
        ("coordinate_vector", "坐标向量", "每个原子段同时携带 G/CH/CU/EV/SC/SG/TB，用来读结构位置。"),
        ("directed_distance", "有向距离", "signed_atom_distance 为目标点减起点；正数在后，负数在前，0 为同点。"),
        ("granularity_level", "粒度等级", "变量指向必须说明 atom/scene/event/time_block/chapter 等粒度。"),
        ("evidence_grade", "证据强度", "变量指向按 hard/resolved/context/hint/chapter_context/needs_review 分级。"),
        ("primary_secondary", "主次归属", "一个原子段若有重叠归属，保留 primary 与 secondary，不改主编号。"),
        ("range_code", "范围码", "容器用 Gxxxxxx-Gxxxxxx 表示覆盖范围，单点用 Gxxxxxx。"),
    ]
    dst.executemany(
        "INSERT INTO coordinate_reading_rules(rule_key, rule_label, reading_rule) VALUES (?, ?, ?)",
        rules,
    )
    dst.executescript(INDEXES)
    dst.commit()
    write_report(dst, report, start, end, safe_label)
    dst.close()
    src.close()
    return out_db, report


def scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def grouped(conn: sqlite3.Connection, sql: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def write_report(conn: sqlite3.Connection, report: Path, start: int, end: int, label: str) -> None:
    lines = [
        "# 红楼梦编码增强追加层说明与验收",
        "",
        f"- 范围：第 {start} 回至第 {end} 回",
        f"- 标签：{label}",
        "- 原则：不改主编号，只追加编码解释层",
        "- 排除项：不把版本与来源字段放入编码解释层",
        "",
        "## 总数",
        "",
        f"- atom_codebook：{scalar(conn, 'SELECT COUNT(*) FROM atom_codebook')}",
        f"- container_codebook：{scalar(conn, 'SELECT COUNT(*) FROM container_codebook')}",
        f"- atom_projection_codebook：{scalar(conn, 'SELECT COUNT(*) FROM atom_projection_codebook')}",
        f"- coordinate_reading_rules：{scalar(conn, 'SELECT COUNT(*) FROM coordinate_reading_rules')}",
        "",
        "## 粒度统计",
        "",
    ]
    for level, count in grouped(
        conn,
        "SELECT granularity_level, COUNT(*) FROM atom_projection_codebook GROUP BY granularity_level ORDER BY COUNT(*) DESC, granularity_level",
    ):
        lines.append(f"- {level}：{count}")
    lines.extend(["", "## 证据强度统计", ""])
    for grade, count in grouped(
        conn,
        "SELECT evidence_grade, COUNT(*) FROM atom_projection_codebook GROUP BY evidence_grade ORDER BY COUNT(*) DESC, evidence_grade",
    ):
        lines.append(f"- {grade}：{count}")
    lines.extend(["", "## 重叠归属统计", ""])
    for status, count in grouped(
        conn,
        "SELECT overlap_status, COUNT(*) FROM atom_codebook GROUP BY overlap_status ORDER BY COUNT(*) DESC, overlap_status",
    ):
        lines.append(f"- {status}：{count}")
    sample = conn.execute(
        """
        SELECT atom_id, atom_code, old_segment_no, coordinate_summary, overlap_status, summary
        FROM atom_codebook
        ORDER BY global_atom_order
        LIMIT 1
        """
    ).fetchone()
    if sample:
        lines.extend(
            [
                "",
                "## 样例",
                "",
                f"- atom_id：`{sample['atom_id']}`",
                f"- atom_code：`{sample['atom_code']}`",
                f"- old_segment_no：`{sample['old_segment_no']}`",
                f"- coordinate_summary：`{sample['coordinate_summary']}`",
                f"- overlap_status：`{sample['overlap_status']}`",
                f"- summary：{sample['summary']}",
            ]
        )
    lines.extend(
        [
            "",
            "## 有向距离样例",
            "",
        ]
    )
    for row in conn.execute(
        """
        SELECT from_atom_code, to_atom_code, signed_atom_distance, abs_atom_distance,
               direction_from_source, same_cluster, same_event, same_scene
        FROM v_enhanced_atom_distance
        WHERE from_atom_id <> to_atom_id
        ORDER BY abs_atom_distance, from_atom_code, to_atom_code
        LIMIT 5
        """
    ):
        lines.append(
            f"- {row['from_atom_code']} -> {row['to_atom_code']}：signed={row['signed_atom_distance']}，abs={row['abs_atom_distance']}，{row['direction_from_source']}，same_cluster={row['same_cluster']}，same_event={row['same_event']}，same_scene={row['same_scene']}"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "这个版本不是重编原子段，而是在短门牌旁边追加解释能力：坐标摘要、范围码、粒度、证据强度、主次归属、有向距离。",
        ]
    )
    if start == 1 and end == 5:
        lines.extend(["", "若前 5 回样板通过，同一机制可以追加到 1-120 回全量版本。"])
    else:
        lines.extend(["", "全量版本已经按同一机制生成，可作为后续查询程序的编码解释层。"])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=5)
    parser.add_argument("--label", default="样板")
    parser.add_argument("--source-db", default=str(DEFAULT_SOURCE_DB))
    args = parser.parse_args()
    out_db, report = build(args.start, args.end, args.label, Path(args.source_db))
    print(out_db)
    print(report)


if __name__ == "__main__":
    main()
