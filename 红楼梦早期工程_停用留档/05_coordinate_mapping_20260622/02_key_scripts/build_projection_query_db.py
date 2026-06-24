#!/usr/bin/env python3
"""Build a full projection branch from the clean Honglou coordinate DB.

This library does not decide which variables are common. It projects every
existing atom link into a uniform searchable point and pre-indexes those points
by atom and aggregation containers. Query terms are resolved later.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3")
SOURCE_DB = ROOT / "outputs/红楼梦干净聚拢坐标库_CH001_120_全量/红楼梦干净聚拢坐标库_CH001_120_全量.sqlite"
OUT_DIR = ROOT / "outputs/红楼梦全量变量投影库_CH001_120"
OUT_DB = OUT_DIR / "红楼梦全量变量投影库_CH001_120.sqlite"
REPORT = OUT_DIR / "红楼梦全量变量投影库_CH001_120_说明与验收.md"


def clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def stable_id(prefix: str, *parts: Any, size: int = 14) -> str:
    raw = "\u241f".join(clean(part) for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:size].upper()}"


SCHEMA = """
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;

CREATE TABLE build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE atom_coordinates (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    old_segment_no TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    summary TEXT,
    quote TEXT
);

CREATE TABLE variable_points (
    point_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    atom_code TEXT NOT NULL,
    old_segment_no TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    variable_type TEXT NOT NULL,
    variable_value_id TEXT,
    variable_value_name TEXT NOT NULL,
    variable_role TEXT,
    scope TEXT,
    precision TEXT,
    confidence REAL,
    review_status TEXT,
    source_name TEXT,
    source_table TEXT,
    raw_value TEXT,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    summary TEXT,
    FOREIGN KEY(atom_id) REFERENCES atom_coordinates(atom_id)
);

CREATE TABLE variable_dictionary (
    dict_id TEXT PRIMARY KEY,
    variable_type TEXT NOT NULL,
    variable_value_name TEXT NOT NULL,
    variable_value_id TEXT,
    atom_count INTEGER NOT NULL,
    point_count INTEGER NOT NULL,
    source_names TEXT,
    review_statuses TEXT,
    min_global_atom_order INTEGER,
    max_global_atom_order INTEGER,
    sample_atom_codes TEXT,
    sample_summaries TEXT,
    UNIQUE(variable_type, variable_value_name, variable_value_id)
);

CREATE TABLE container_variable_index (
    index_id TEXT PRIMARY KEY,
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    variable_type TEXT NOT NULL,
    variable_value_name TEXT NOT NULL,
    variable_value_id TEXT,
    atom_count INTEGER NOT NULL,
    point_count INTEGER NOT NULL,
    start_atom_order INTEGER,
    end_atom_order INTEGER,
    sample_atom_codes TEXT,
    review_statuses TEXT,
    source_names TEXT
);

CREATE VIEW v_atom_distance_directed AS
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
FROM atom_coordinates a
JOIN atom_coordinates b ON 1=1;

CREATE VIEW v_variable_point_context AS
SELECT
    p.*,
    c.summary AS atom_summary,
    c.quote AS atom_quote
FROM variable_points p
JOIN atom_coordinates c ON c.atom_id=p.atom_id;
"""


INDEXES = """
CREATE INDEX idx_variable_points_type_value ON variable_points(variable_type, variable_value_name);
CREATE INDEX idx_variable_points_value_name ON variable_points(variable_value_name);
CREATE INDEX idx_variable_points_atom ON variable_points(atom_id);
CREATE INDEX idx_variable_points_order ON variable_points(global_atom_order);
CREATE INDEX idx_variable_points_scene ON variable_points(scene_id);
CREATE INDEX idx_variable_points_event ON variable_points(event_id);
CREATE INDEX idx_variable_dictionary_type_name ON variable_dictionary(variable_type, variable_value_name);
CREATE INDEX idx_container_variable_lookup ON container_variable_index(container_type, container_id, variable_type, variable_value_name);
CREATE INDEX idx_container_variable_value ON container_variable_index(variable_type, variable_value_name, container_type);
CREATE INDEX idx_atom_coordinates_order ON atom_coordinates(global_atom_order);
CREATE INDEX idx_atom_coordinates_scene ON atom_coordinates(scene_id);
CREATE INDEX idx_atom_coordinates_event ON atom_coordinates(event_id);
"""


def unique_join(values: list[str], limit: int = 12) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = clean(value)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
        if len(out) >= limit:
            break
    return " | ".join(out)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in [OUT_DB, Path(f"{OUT_DB}-wal"), Path(f"{OUT_DB}-shm")]:
        if path.exists():
            path.unlink()

    src = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    dst = sqlite3.connect(OUT_DB)
    dst.row_factory = sqlite3.Row
    dst.executescript(SCHEMA)

    dst.executemany(
        "INSERT INTO build_meta(key,value) VALUES (?,?)",
        [
            ("build_name", "红楼梦全量变量投影库_CH001_120"),
            ("built_at_utc", datetime.now(timezone.utc).isoformat()),
            ("source_db", str(SOURCE_DB)),
            ("source_mode", "read_only_full_projection_no_writeback"),
            ("purpose", "Project all atom_links into uniform variable points; no query terms are hard-coded."),
        ],
    )

    coords = [dict(row) for row in src.execute(
        """
        SELECT d.*, a.summary, a.quote
        FROM atom_distance_basis d
        JOIN clean_atoms a ON a.atom_id=d.atom_id
        ORDER BY d.global_atom_order
        """
    )]
    dst.executemany(
        """
        INSERT INTO atom_coordinates (
            atom_id, atom_code, old_segment_no, chapter_no, atom_order_in_chapter,
            global_atom_order, cluster_id, event_id, scene_id, scene_group_id,
            time_block_id, summary, quote
        )
        VALUES (:atom_id, :atom_code, :old_segment_no, :chapter_no, :atom_order_in_chapter,
            :global_atom_order, :cluster_id, :event_id, :scene_id, :scene_group_id,
            :time_block_id, :summary, :quote)
        """,
        coords,
    )

    points = [dict(row) for row in src.execute(
        """
        SELECT
            l.link_id AS point_id,
            a.atom_id, a.atom_code, a.old_segment_no, a.chapter_no, a.global_atom_order,
            l.link_type AS variable_type,
            l.link_value_id AS variable_value_id,
            l.link_value_name AS variable_value_name,
            l.link_role AS variable_role,
            l.scope, l.precision, l.confidence, l.review_status,
            l.source_name, l.source_table, l.raw_value,
            d.cluster_id, d.event_id, d.scene_id, d.scene_group_id, d.time_block_id,
            a.summary
        FROM atom_links l
        JOIN clean_atoms a ON a.atom_id=l.atom_id
        JOIN atom_distance_basis d ON d.atom_id=l.atom_id
        ORDER BY a.global_atom_order, l.link_type, l.link_value_name
        """
    )]
    dst.executemany(
        """
        INSERT INTO variable_points (
            point_id, atom_id, atom_code, old_segment_no, chapter_no, global_atom_order,
            variable_type, variable_value_id, variable_value_name, variable_role,
            scope, precision, confidence, review_status, source_name, source_table,
            raw_value, cluster_id, event_id, scene_id, scene_group_id, time_block_id, summary
        )
        VALUES (
            :point_id, :atom_id, :atom_code, :old_segment_no, :chapter_no, :global_atom_order,
            :variable_type, :variable_value_id, :variable_value_name, :variable_role,
            :scope, :precision, :confidence, :review_status, :source_name, :source_table,
            :raw_value, :cluster_id, :event_id, :scene_id, :scene_group_id, :time_block_id, :summary
        )
        """,
        points,
    )

    build_variable_dictionary(dst)
    build_container_variable_index(dst)
    dst.executescript(INDEXES)
    dst.commit()
    write_report(dst)
    dst.close()
    src.close()
    print(OUT_DB)
    print(REPORT)


def build_variable_dictionary(dst: sqlite3.Connection) -> None:
    rows = []
    for row in dst.execute(
        """
        SELECT
            variable_type,
            variable_value_name,
            COALESCE(variable_value_id, '') AS variable_value_id,
            COUNT(DISTINCT atom_id) AS atom_count,
            COUNT(*) AS point_count,
            MIN(global_atom_order) AS min_global_atom_order,
            MAX(global_atom_order) AS max_global_atom_order,
            GROUP_CONCAT(DISTINCT source_name) AS source_names,
            GROUP_CONCAT(DISTINCT review_status) AS review_statuses,
            GROUP_CONCAT(DISTINCT atom_code) AS sample_atom_codes,
            GROUP_CONCAT(DISTINCT summary) AS sample_summaries
        FROM variable_points
        GROUP BY variable_type, variable_value_name, COALESCE(variable_value_id, '')
        ORDER BY variable_type, variable_value_name
        """
    ):
        data = dict(row)
        rows.append(
            (
                stable_id("VD", data["variable_type"], data["variable_value_name"], data["variable_value_id"]),
                data["variable_type"],
                data["variable_value_name"],
                data["variable_value_id"],
                data["atom_count"],
                data["point_count"],
                unique_join(clean(data["source_names"]).split(",")),
                unique_join(clean(data["review_statuses"]).split(",")),
                data["min_global_atom_order"],
                data["max_global_atom_order"],
                unique_join(clean(data["sample_atom_codes"]).split(","), 8),
                unique_join(clean(data["sample_summaries"]).split(","), 4),
            )
        )
    dst.executemany(
        """
        INSERT INTO variable_dictionary (
            dict_id, variable_type, variable_value_name, variable_value_id,
            atom_count, point_count, source_names, review_statuses,
            min_global_atom_order, max_global_atom_order, sample_atom_codes, sample_summaries
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def build_container_variable_index(dst: sqlite3.Connection) -> None:
    container_cols = [
        ("chapter", "chapter_no"),
        ("cluster_unit", "cluster_id"),
        ("event", "event_id"),
        ("scene_point", "scene_id"),
        ("scene_group", "scene_group_id"),
        ("time_block", "time_block_id"),
    ]
    rows = []
    for container_type, col in container_cols:
        for row in dst.execute(
            f"""
            SELECT
                '{container_type}' AS container_type,
                CAST({col} AS TEXT) AS container_id,
                variable_type,
                variable_value_name,
                COALESCE(variable_value_id, '') AS variable_value_id,
                COUNT(DISTINCT atom_id) AS atom_count,
                COUNT(*) AS point_count,
                MIN(global_atom_order) AS start_atom_order,
                MAX(global_atom_order) AS end_atom_order,
                GROUP_CONCAT(DISTINCT atom_code) AS sample_atom_codes,
                GROUP_CONCAT(DISTINCT review_status) AS review_statuses,
                GROUP_CONCAT(DISTINCT source_name) AS source_names
            FROM variable_points
            WHERE {col} IS NOT NULL AND {col} != ''
            GROUP BY {col}, variable_type, variable_value_name, COALESCE(variable_value_id, '')
            """
        ):
            data = dict(row)
            rows.append(
                (
                    stable_id(
                        "CVI",
                        data["container_type"],
                        data["container_id"],
                        data["variable_type"],
                        data["variable_value_name"],
                        data["variable_value_id"],
                    ),
                    data["container_type"],
                    data["container_id"],
                    data["variable_type"],
                    data["variable_value_name"],
                    data["variable_value_id"],
                    data["atom_count"],
                    data["point_count"],
                    data["start_atom_order"],
                    data["end_atom_order"],
                    unique_join(clean(data["sample_atom_codes"]).split(","), 8),
                    unique_join(clean(data["review_statuses"]).split(",")),
                    unique_join(clean(data["source_names"]).split(",")),
                )
            )
    dst.executemany(
        """
        INSERT INTO container_variable_index (
            index_id, container_type, container_id, variable_type, variable_value_name,
            variable_value_id, atom_count, point_count, start_atom_order, end_atom_order,
            sample_atom_codes, review_statuses, source_names
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def scalar(dst: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = dst.execute(sql, params).fetchone()
    return row[0] if row else None


def write_report(dst: sqlite3.Connection) -> None:
    lines = [
        "# 红楼梦全量变量投影库 CH001-120 说明与验收",
        "",
        f"- 源库：`{SOURCE_DB.name}`",
        f"- 输出库：`{OUT_DB.name}`",
        "- 写回状态：不写回旧库，不覆盖干净坐标库",
        "- 查询词状态：不预设任何常用查询词；查询词后续临时映射到 `variable_dictionary / variable_points`",
        "",
        "## 总数",
        "",
        f"- 原子段坐标：{scalar(dst, 'SELECT COUNT(*) FROM atom_coordinates')}",
        f"- 全量变量点：{scalar(dst, 'SELECT COUNT(*) FROM variable_points')}",
        f"- 变量词典项：{scalar(dst, 'SELECT COUNT(*) FROM variable_dictionary')}",
        f"- 容器变量索引：{scalar(dst, 'SELECT COUNT(*) FROM container_variable_index')}",
        "",
        "## 变量类型",
        "",
    ]
    for row in dst.execute(
        """
        SELECT variable_type, COUNT(*) AS points, COUNT(DISTINCT variable_value_name) AS value_count,
               COUNT(DISTINCT atom_id) AS atoms
        FROM variable_points
        GROUP BY variable_type
        ORDER BY points DESC, variable_type
        """
    ):
        lines.append(f"- {row['variable_type']}：{row['points']} 点，{row['value_count']} 值，覆盖 {row['atoms']} 原子段")
    lines.extend(["", "## 容器索引", ""])
    for row in dst.execute(
        """
        SELECT container_type, COUNT(*) AS rows, COUNT(DISTINCT container_id) AS containers
        FROM container_variable_index
        GROUP BY container_type
        ORDER BY container_type
        """
    ):
        lines.append(f"- {row['container_type']}：{row['containers']} 个容器，{row['rows']} 条变量索引")
    lines.extend(["", "## 样例：查询词不预设但可映射", ""])
    samples = [
        ("person", "贾宝玉"),
        ("person", "林黛玉"),
        ("season", "秋"),
        ("space", "潇湘馆"),
        ("scene_object_hint", "药"),
    ]
    for variable_type, value in samples:
        row = dst.execute(
            """
            SELECT atom_count, point_count, sample_atom_codes, review_statuses
            FROM variable_dictionary
            WHERE variable_type=? AND variable_value_name=?
            ORDER BY atom_count DESC
            LIMIT 1
            """,
            (variable_type, value),
        ).fetchone()
        if row:
            lines.append(
                f"- `{variable_type}={value}`：{row['atom_count']} 原子段，{row['point_count']} 点，样例 {row['sample_atom_codes']}，状态 {row['review_statuses']}"
            )
    lines.extend(
        [
            "",
            "## 距离",
            "",
            "本库带 `v_atom_distance_directed`，不需要预先写死任意两点距离；任意两点通过坐标向量即可读出有向距离、绝对距离和同层状态。",
            "",
            "## 结论",
            "",
            "这个库是全量投影层：它只把所有变量点预先摊平和索引，不替用户决定常用变量。查询词到来以后，再从词典和变量点中收点、投影、求共同容器和距离。",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
