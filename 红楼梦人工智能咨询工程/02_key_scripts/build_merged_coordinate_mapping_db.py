#!/usr/bin/env python3
"""Build the single published coordinate mapping database.

This keeps the old project and the two construction databases untouched. The
published output is one SQLite file that contains the clean coordinate tables,
the codebook tables, and the distance/read views in a single place.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3")
OUTPUTS = WORKSPACE / "outputs"
CLEAN_DB = OUTPUTS / "红楼梦干净聚拢坐标库_CH001_120_全量/红楼梦干净聚拢坐标库_CH001_120_全量.sqlite"
CODEBOOK_DB = OUTPUTS / "红楼梦编码增强追加层_CH001_120_全量/红楼梦编码增强追加层_CH001_120_全量.sqlite"
PUBLISHED_DIR = OUTPUTS / "红楼梦聚拢坐标映射总库_CH001_120"
PUBLISHED_DB = PUBLISHED_DIR / "红楼梦聚拢坐标映射总库_CH001_120.sqlite"
REPORT = PUBLISHED_DIR / "红楼梦聚拢坐标映射总库_CH001_120_说明与验收.md"

CODEBOOK_TABLES = [
    "atom_codebook",
    "container_codebook",
    "atom_projection_codebook",
    "coordinate_reading_rules",
]


def scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def copy_codebook_tables(conn: sqlite3.Connection) -> None:
    source_sql: dict[str, str] = {}
    source_columns: dict[str, list[str]] = {}
    source_conn = sqlite3.connect(CODEBOOK_DB)
    try:
        for table in CODEBOOK_TABLES:
            row = source_conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not row or not row[0]:
                raise RuntimeError(f"Missing codebook table in source database: {table}")
            source_sql[table] = row[0]
            source_columns[table] = [
                info[1] for info in source_conn.execute(f"PRAGMA table_info({table})").fetchall()
            ]
    finally:
        source_conn.close()

    conn.execute(f"ATTACH DATABASE '{CODEBOOK_DB}' AS codebook_src")
    try:
        for table in CODEBOOK_TABLES:
            conn.execute(f"DROP TABLE IF EXISTS main.{table}")
            conn.execute(source_sql[table])
            columns = source_columns[table]
            joined = ", ".join(columns)
            conn.execute(
                f"INSERT INTO {table} ({joined}) SELECT {joined} FROM codebook_src.{table}"
            )

        index_rows = list(conn.execute(
            """
            SELECT name, sql
            FROM codebook_src.sqlite_master
            WHERE type='index'
              AND sql IS NOT NULL
              AND tbl_name IN ('atom_codebook', 'container_codebook', 'atom_projection_codebook', 'coordinate_reading_rules')
            ORDER BY name
            """
        ).fetchall())
        for row in index_rows:
            conn.execute(row[1])
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE codebook_src")


def rebuild_views(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS v_atom_pair_distance")
    conn.execute("DROP VIEW IF EXISTS v_atom_pair_distance_directed")
    conn.execute("DROP VIEW IF EXISTS v_enhanced_atom_distance")
    conn.execute(
        """
        CREATE VIEW v_atom_pair_distance AS
        SELECT
            a.atom_id AS left_atom_id,
            b.atom_id AS right_atom_id,
            a.atom_code AS left_atom_code,
            b.atom_code AS right_atom_code,
            ABS(a.global_atom_order - b.global_atom_order) AS atom_distance,
            CASE WHEN a.chapter_no = b.chapter_no THEN 1 ELSE 0 END AS same_chapter,
            CASE WHEN a.cluster_id IS NOT NULL AND a.cluster_id = b.cluster_id THEN 1 ELSE 0 END AS same_cluster,
            CASE WHEN a.event_id IS NOT NULL AND a.event_id = b.event_id THEN 1 ELSE 0 END AS same_event,
            CASE WHEN a.scene_id IS NOT NULL AND a.scene_id = b.scene_id THEN 1 ELSE 0 END AS same_scene,
            CASE WHEN a.scene_group_id IS NOT NULL AND a.scene_group_id = b.scene_group_id THEN 1 ELSE 0 END AS same_scene_group,
            CASE WHEN a.time_block_id IS NOT NULL AND a.time_block_id = b.time_block_id THEN 1 ELSE 0 END AS same_time_block
        FROM atom_distance_basis a
        JOIN atom_distance_basis b ON a.atom_id < b.atom_id
        """
    )
    conn.execute(
        """
        CREATE VIEW v_atom_pair_distance_directed AS
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
        FROM atom_distance_basis a
        JOIN atom_distance_basis b ON 1 = 1
        """
    )
    conn.execute(
        """
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
        JOIN atom_codebook b ON 1 = 1
        """
    )


def write_meta(conn: sqlite3.Connection) -> None:
    meta = {
        "published_library_name": "红楼梦聚拢坐标映射总库",
        "published_library_type": "single_coordinate_mapping_database",
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "CH001-CH120",
        "construction_rule": "Merged clean coordinate tables and codebook tables into one published SQLite file.",
        "old_project_writeback": "no",
        "atom_id_rule": "Keep original global atom_id A000001..A002706 unchanged.",
        "atom_code_rule": "Keep atom_code C{chapter:03d}-A{atom_order_in_chapter:04d} unchanged.",
    }
    for key, value in meta.items():
        conn.execute(
            "INSERT OR REPLACE INTO build_meta(key, value) VALUES (?, ?)",
            (key, value),
        )


def write_report(conn: sqlite3.Connection) -> None:
    counts = {
        "clean_atoms": scalar(conn, "SELECT COUNT(*) FROM clean_atoms"),
        "atom_memberships": scalar(conn, "SELECT COUNT(*) FROM atom_memberships"),
        "atom_links": scalar(conn, "SELECT COUNT(*) FROM atom_links"),
        "container_hierarchy": scalar(conn, "SELECT COUNT(*) FROM container_hierarchy"),
        "quality_findings": scalar(conn, "SELECT COUNT(*) FROM quality_findings"),
        "atom_codebook": scalar(conn, "SELECT COUNT(*) FROM atom_codebook"),
        "container_codebook": scalar(conn, "SELECT COUNT(*) FROM container_codebook"),
        "atom_projection_codebook": scalar(conn, "SELECT COUNT(*) FROM atom_projection_codebook"),
    }
    coverage = conn.execute(
        "SELECT MIN(chapter_no), MAX(chapter_no), COUNT(DISTINCT chapter_no), COUNT(*) FROM clean_atoms"
    ).fetchone()
    missing = conn.execute(
        """
        SELECT
            SUM(cluster_id IS NULL),
            SUM(event_id IS NULL),
            SUM(scene_id IS NULL),
            SUM(scene_group_id IS NULL),
            SUM(time_block_id IS NULL)
        FROM atom_distance_basis
        """
    ).fetchone()
    code_mismatch = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM clean_atoms a
        LEFT JOIN atom_codebook c ON c.atom_id=a.atom_id AND c.atom_code=a.atom_code
        WHERE c.atom_id IS NULL
        """,
    )
    projection_orphans = scalar(
        conn,
        """
        SELECT COUNT(*)
        FROM atom_projection_codebook p
        LEFT JOIN clean_atoms a ON a.atom_id=p.atom_id
        WHERE a.atom_id IS NULL
        """,
    )
    sample = conn.execute(
        """
        SELECT a.atom_id, a.atom_code, a.old_segment_no, c.coordinate_summary
        FROM clean_atoms a
        JOIN atom_codebook c ON c.atom_id=a.atom_id
        ORDER BY a.global_atom_order
        LIMIT 1
        """
    ).fetchone()
    quality_rows = conn.execute(
        """
        SELECT severity, finding_type, COUNT(*)
        FROM quality_findings
        GROUP BY severity, finding_type
        ORDER BY severity DESC, COUNT(*) DESC
        """
    ).fetchall()

    lines = [
        "# 红楼梦聚拢坐标映射总库说明与验收",
        "",
        f"- 输出库：`{PUBLISHED_DB.name}`",
        "- 性质：单一发布态映射编码库，不是正文实体库",
        "- 旧工程：只读来源，不写回",
        "- 编号：保留 `atom_id/atom_code`，不重编",
        "- 合并原则：物理上一个 SQLite，逻辑上仍分为门牌、归属、指向、距离、读法",
        "",
        "## 表规模",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in counts.items())
    lines.extend(
        [
            "",
            "## 覆盖验收",
            "",
            f"- 回目范围：{coverage[0]}-{coverage[1]}",
            f"- 回目数量：{coverage[2]}",
            f"- 原子段数量：{coverage[3]}",
            f"- 编码表与原子段不一致：{code_mismatch}",
            f"- 投影表孤儿记录：{projection_orphans}",
            "",
            "## 距离锚缺口",
            "",
            f"- cluster_id 缺失：{missing[0]}",
            f"- event_id 缺失：{missing[1]}",
            f"- scene_id 缺失：{missing[2]}",
            f"- scene_group_id 缺失：{missing[3]}",
            f"- time_block_id 缺失：{missing[4]}",
            "",
            "## 质量发现",
            "",
        ]
    )
    lines.extend(f"- {severity} / {kind}: {count}" for severity, kind, count in quality_rows)
    if sample:
        lines.extend(
            [
                "",
                "## 样例",
                "",
                f"- atom_id: `{sample[0]}`",
                f"- atom_code: `{sample[1]}`",
                f"- old_segment_no: `{sample[2]}`",
                f"- coordinate_summary: `{sample[3]}`",
            ]
        )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> None:
    if not CLEAN_DB.exists():
        raise FileNotFoundError(CLEAN_DB)
    if not CODEBOOK_DB.exists():
        raise FileNotFoundError(CODEBOOK_DB)
    PUBLISHED_DIR.mkdir(parents=True, exist_ok=True)
    for path in [PUBLISHED_DB, Path(f"{PUBLISHED_DB}-wal"), Path(f"{PUBLISHED_DB}-shm")]:
        if path.exists():
            path.unlink()
    shutil.copy2(CLEAN_DB, PUBLISHED_DB)
    conn = sqlite3.connect(PUBLISHED_DB)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        copy_codebook_tables(conn)
        rebuild_views(conn)
        write_meta(conn)
        conn.commit()
        write_report(conn)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--allow-retired-source-republish",
        action="store_true",
        help="Dangerous: republish the retired 2706-source-segment database over the refined atom-segment publication.",
    )
    args = parser.parse_args()
    if not args.allow_retired_source_republish:
        raise SystemExit(
            "Blocked: the official coordinate mapping database now uses the refined 3754 atom-segment publication. "
            "Do not run this retired-source publisher unless you intentionally want to roll back with "
            "--allow-retired-source-republish."
        )
    build()
    print(PUBLISHED_DB)
    print(REPORT)


if __name__ == "__main__":
    main()
