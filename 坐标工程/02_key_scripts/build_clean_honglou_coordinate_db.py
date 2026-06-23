#!/usr/bin/env python3
"""Build a read-only-derived clean coordinate index for the Honglou project.

The source project is never modified. This script creates a new SQLite library
and companion CSV/report files under the current Codex workspace outputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path("/Users/yu/Documents/Codex/2026-06-03/notion-3-crv")
MATERIAL_RECALL_ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs/红楼梦正式取材专库")
SOURCE_DB = MATERIAL_RECALL_ROOT / "00_双中心取材总库" / "01_语义聚拢查询中心库" / "红楼梦语义聚拢中心库_CH001_120.sqlite"
W32_DIR = PROJECT_ROOT / "outputs/红楼梦对谈查证室"
W32_UNITS = W32_DIR / "33_W32_聚拢单元库_cluster_units.csv"
W32_LINES = W32_DIR / "33_W32_聚拢单元库_cluster_unit_lines.csv"
W33_EVENTS = W32_DIR / "34_W33_聚拢事件库_events.csv"
W33_UNITS = W32_DIR / "34_W33_聚拢事件库_event_units.csv"
SCENE_DIR = W32_DIR / "101_红楼梦回目时间场库_120回全量施工"
SCENE_POINTS = SCENE_DIR / "101_120回场面库_scene_points.csv"
SCENE_GROUPS = SCENE_DIR / "101_120回场面库_scene_groups.csv"
TIME_BLOCKS = SCENE_DIR / "101_120回场面库_time_blocks.csv"

OUTPUT_ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3/outputs")


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_int(value: Any, default: int | None = None) -> int | None:
    text = clean(value)
    if not text:
        return default
    try:
        return int(float(text))
    except ValueError:
        return default


def truthy(value: Any) -> bool:
    text = clean(value).lower()
    if not text:
        return False
    return text in {
        "1",
        "true",
        "yes",
        "y",
        "是",
        "已解析",
        "resolved",
        "ok",
        "pass",
        "a",
        "a｜原文明示具体空间",
    }


def stable_id(prefix: str, *parts: Any, size: int = 14) -> str:
    raw = "\u241f".join(clean(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:size].upper()
    return f"{prefix}-{digest}"


def split_values(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    values: list[str] = []
    if text.startswith("[") and text.endswith("]"):
        try:
            loaded = json.loads(text)
            if isinstance(loaded, list):
                for item in loaded:
                    values.extend(split_values(item))
                return unique_keep_order(values)
        except json.JSONDecodeError:
            pass
    text = text.strip("[]")
    parts = re.split(r"[、,，;；|/]+", text)
    for part in parts:
        item = part.strip().strip('"').strip("'").strip()
        if item:
            values.append(item)
    return unique_keep_order(values)


def unique_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def dict_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur = conn.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def source_label(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def review_from_bool(ok: bool) -> str:
    return "resolved" if ok else "needs_review"


def confidence_from_bool(ok: bool, low: float = 0.65) -> float:
    return 1.0 if ok else low


def confidence_from_space_level(level: str) -> float:
    level = clean(level)
    if level.startswith("A"):
        return 1.0
    if level.startswith("B"):
        return 0.82
    if level.startswith("C"):
        return 0.65
    if level.startswith("D"):
        return 0.45
    return 0.6


def evidence_axis_to_link_type(axis: str) -> str:
    axis = clean(axis)
    if axis == "space_evidence":
        return "space"
    return axis or "evidence"


def ensure_sources_exist() -> None:
    missing = [
        path
        for path in [
            SOURCE_DB,
            W32_UNITS,
            W32_LINES,
            W33_EVENTS,
            W33_UNITS,
            SCENE_POINTS,
            SCENE_GROUPS,
            TIME_BLOCKS,
        ]
        if not path.exists()
    ]
    if missing:
        joined = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing required source files:\n{joined}")


SCHEMA_SQL = """
PRAGMA journal_mode = DELETE;
PRAGMA foreign_keys = ON;

CREATE TABLE build_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE clean_atoms (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL UNIQUE,
    chapter_no INTEGER NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL UNIQUE,
    old_segment_no TEXT NOT NULL UNIQUE,
    page_id TEXT,
    chapter_page_id TEXT,
    chapter_label TEXT,
    summary TEXT,
    quote TEXT,
    original_version TEXT,
    scene_place_raw TEXT,
    time_point_raw TEXT,
    is_focus_raw TEXT,
    perspective_raw TEXT,
    note_type_raw TEXT,
    note_dimension_raw TEXT,
    function_tags_raw TEXT,
    old_cluster_unit_raw TEXT,
    source_row INTEGER,
    source_db TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_status TEXT NOT NULL
);

CREATE TABLE atom_source_map (
    atom_id TEXT PRIMARY KEY,
    old_segment_no TEXT NOT NULL,
    page_id TEXT,
    source_db TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_row INTEGER,
    source_key TEXT NOT NULL
);

CREATE TABLE atom_memberships (
    membership_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    role TEXT,
    order_in_container INTEGER,
    is_primary INTEGER NOT NULL DEFAULT 0,
    source_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    review_status TEXT NOT NULL DEFAULT 'resolved',
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

CREATE TABLE atom_links (
    link_id TEXT PRIMARY KEY,
    atom_id TEXT NOT NULL,
    link_type TEXT NOT NULL,
    link_value_id TEXT,
    link_value_name TEXT NOT NULL,
    link_role TEXT,
    scope TEXT NOT NULL,
    precision TEXT NOT NULL,
    chapter_no INTEGER,
    source_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    review_status TEXT NOT NULL DEFAULT 'resolved',
    raw_value TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

CREATE TABLE atom_anchors (
    atom_id TEXT PRIMARY KEY,
    old_segment_no TEXT NOT NULL,
    anchor_status TEXT,
    evidence_eligible TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    anchor_text TEXT,
    method TEXT NOT NULL,
    query_source TEXT,
    query_text TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

CREATE TABLE container_hierarchy (
    hierarchy_id TEXT PRIMARY KEY,
    lower_type TEXT NOT NULL,
    lower_id TEXT NOT NULL,
    upper_type TEXT NOT NULL,
    upper_id TEXT NOT NULL,
    chapter_no INTEGER,
    relation_type TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_key TEXT,
    review_status TEXT NOT NULL DEFAULT 'resolved'
);

CREATE TABLE container_index (
    container_type TEXT NOT NULL,
    container_id TEXT NOT NULL,
    container_label TEXT,
    chapter_no INTEGER,
    start_atom_order INTEGER,
    end_atom_order INTEGER,
    atom_count INTEGER,
    source_name TEXT,
    quality_status TEXT,
    review_status TEXT,
    PRIMARY KEY(container_type, container_id)
);

CREATE TABLE atom_distance_basis (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    atom_order_in_chapter INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    old_segment_no TEXT NOT NULL,
    cluster_id TEXT,
    event_id TEXT,
    scene_id TEXT,
    scene_group_id TEXT,
    time_block_id TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

CREATE TABLE atom_flat_index (
    atom_id TEXT PRIMARY KEY,
    atom_code TEXT NOT NULL,
    chapter_no INTEGER NOT NULL,
    global_atom_order INTEGER NOT NULL,
    old_segment_no TEXT NOT NULL,
    cluster_ids TEXT,
    event_ids TEXT,
    scene_ids TEXT,
    scene_group_ids TEXT,
    time_block_ids TEXT,
    persons TEXT,
    spaces TEXT,
    objects TEXT,
    time_points TEXT,
    seasons TEXT,
    note_types TEXT,
    note_dimensions TEXT,
    functions TEXT,
    review_flags TEXT,
    FOREIGN KEY(atom_id) REFERENCES clean_atoms(atom_id)
);

CREATE TABLE distance_metric_rules (
    rule_key TEXT PRIMARY KEY,
    rule_label TEXT NOT NULL,
    rule_sql_hint TEXT NOT NULL,
    interpretation TEXT NOT NULL
);

CREATE TABLE quality_findings (
    finding_id TEXT PRIMARY KEY,
    severity TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    detail TEXT NOT NULL,
    source_name TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'open'
);

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
JOIN atom_distance_basis b ON a.atom_id < b.atom_id;

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
JOIN atom_distance_basis b ON 1 = 1;
"""


INDEX_SQL = """
CREATE INDEX idx_atoms_chapter_order ON clean_atoms(chapter_no, atom_order_in_chapter);
CREATE INDEX idx_atoms_global_order ON clean_atoms(global_atom_order);
CREATE INDEX idx_memberships_atom ON atom_memberships(atom_id);
CREATE INDEX idx_memberships_container ON atom_memberships(container_type, container_id);
CREATE INDEX idx_links_atom ON atom_links(atom_id);
CREATE INDEX idx_links_type_value ON atom_links(link_type, link_value_name);
CREATE INDEX idx_links_chapter ON atom_links(chapter_no);
CREATE INDEX idx_hierarchy_lower ON container_hierarchy(lower_type, lower_id);
CREATE INDEX idx_hierarchy_upper ON container_hierarchy(upper_type, upper_id);
CREATE INDEX idx_distance_cluster ON atom_distance_basis(cluster_id);
CREATE INDEX idx_distance_event ON atom_distance_basis(event_id);
CREATE INDEX idx_distance_scene ON atom_distance_basis(scene_id);
CREATE INDEX idx_quality_findings_type ON quality_findings(finding_type, severity);
"""


class Builder:
    def __init__(self, start_chapter: int, end_chapter: int, output_dir: Path, build_label: str) -> None:
        self.start_chapter = start_chapter
        self.end_chapter = end_chapter
        self.output_dir = output_dir
        self.build_label = build_label
        self.db_path = output_dir / f"红楼梦干净聚拢坐标库_CH{start_chapter:03d}_{end_chapter:03d}_{build_label}.sqlite"
        self.report_path = output_dir / f"红楼梦干净聚拢坐标库_CH{start_chapter:03d}_{end_chapter:03d}_{build_label}_审计报告.md"
        self.conn: sqlite3.Connection | None = None
        self.source_conn: sqlite3.Connection | None = None
        self.all_segments: list[dict[str, Any]] = []
        self.segments: list[dict[str, Any]] = []
        self.segment_to_atom: dict[str, dict[str, Any]] = {}
        self.atom_to_segment: dict[str, dict[str, Any]] = {}
        self.segment_no_set: set[str] = set()
        self.chapter_atoms: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.cluster_units: dict[str, dict[str, str]] = {}
        self.cluster_lines_by_segment: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.events: dict[str, dict[str, str]] = {}
        self.event_units_by_cluster: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.scene_points: list[dict[str, str]] = []
        self.scene_groups: list[dict[str, str]] = []
        self.time_blocks: list[dict[str, str]] = []
        self.membership_seen: set[str] = set()
        self.link_seen: set[str] = set()
        self.hierarchy_seen: set[str] = set()

    @property
    def db(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("Output database is not open")
        return self.conn

    @property
    def source_db(self) -> sqlite3.Connection:
        if self.source_conn is None:
            raise RuntimeError("Source database is not open")
        return self.source_conn

    def run(self) -> None:
        ensure_sources_exist()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for path in [
            self.db_path,
            Path(f"{self.db_path}-wal"),
            Path(f"{self.db_path}-shm"),
        ]:
            if path.exists():
                path.unlink()

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.source_conn = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
        self.source_conn.row_factory = sqlite3.Row

        self.db.executescript(SCHEMA_SQL)
        self.load_sources()
        self.insert_meta()
        self.insert_atoms()
        self.insert_base_memberships()
        self.insert_cluster_memberships()
        self.insert_event_memberships()
        self.insert_scene_memberships_and_links()
        self.insert_edge_links()
        self.insert_hierarchy()
        self.insert_distance_rules()
        self.build_container_index()
        self.build_distance_basis()
        self.build_flat_index()
        self.build_quality_findings()
        self.db.executescript(INDEX_SQL)
        self.db.commit()
        self.export_csvs()
        self.write_report()
        self.source_db.close()
        self.db.close()

    def load_sources(self) -> None:
        self.all_segments = dict_rows(
            self.source_db,
            """
            SELECT * FROM segments
            ORDER BY chapter_no, segment_order, segment_no
            """,
        )
        chapter_counts: dict[int, int] = defaultdict(int)
        for global_index, row in enumerate(self.all_segments, start=1):
            chapter_no = int(row["chapter_no"])
            chapter_counts[chapter_no] += 1
            order_in_chapter = int(row["segment_order"] or chapter_counts[chapter_no])
            old_segment_no = clean(row["segment_no"])
            atom_id = f"A{global_index:06d}"
            atom_code = f"C{chapter_no:03d}-A{order_in_chapter:04d}"
            atom_ref = {
                "atom_id": atom_id,
                "atom_code": atom_code,
                "chapter_no": chapter_no,
                "atom_order_in_chapter": order_in_chapter,
                "global_atom_order": global_index,
                "old_segment_no": old_segment_no,
                "source": row,
            }
            self.segment_to_atom[old_segment_no] = atom_ref
            if self.start_chapter <= chapter_no <= self.end_chapter:
                self.segments.append(row)
                self.atom_to_segment[atom_id] = atom_ref
                self.segment_no_set.add(old_segment_no)
                self.chapter_atoms[chapter_no].append(atom_ref)

        self.cluster_units = {
            clean(row["cluster_id"]): row
            for row in csv_rows(W32_UNITS)
            if self.start_chapter <= (parse_int(row.get("chapter_no"), -1) or -1) <= self.end_chapter
        }
        for row in csv_rows(W32_LINES):
            chapter_no = parse_int(row.get("chapter_no"), -1) or -1
            if not self.start_chapter <= chapter_no <= self.end_chapter:
                continue
            segment_no = clean(row.get("line_no")) or clean(row.get("line_id"))
            if segment_no in self.segment_no_set:
                self.cluster_lines_by_segment[segment_no].append(row)

        self.events = {
            clean(row["event_id"]): row
            for row in csv_rows(W33_EVENTS)
            if self.start_chapter <= (parse_int(row.get("chapter_no"), -1) or -1) <= self.end_chapter
        }
        for row in csv_rows(W33_UNITS):
            chapter_no = parse_int(row.get("chapter_no"), -1) or -1
            if not self.start_chapter <= chapter_no <= self.end_chapter:
                continue
            self.event_units_by_cluster[clean(row.get("cluster_id"))].append(row)

        self.scene_points = [
            row
            for row in csv_rows(SCENE_POINTS)
            if self.start_chapter <= (parse_int(row.get("chapter_no"), -1) or -1) <= self.end_chapter
        ]
        self.scene_groups = [
            row
            for row in csv_rows(SCENE_GROUPS)
            if self.start_chapter <= (parse_int(row.get("chapter_no"), -1) or -1) <= self.end_chapter
        ]
        self.time_blocks = [
            row
            for row in csv_rows(TIME_BLOCKS)
            if self.start_chapter <= (parse_int(row.get("chapter_no"), -1) or -1) <= self.end_chapter
        ]

    def insert_meta(self) -> None:
        meta = {
            "build_name": f"红楼梦干净聚拢坐标库_CH{self.start_chapter:03d}_{self.end_chapter:03d}_{self.build_label}",
            "build_label": self.build_label,
            "chapter_start": str(self.start_chapter),
            "chapter_end": str(self.end_chapter),
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_mode": "read_only_derived_copy_no_writeback",
            "atom_id_rule": "A000001..A002706 assigned from full 1-120 segments global order; subset builds keep the same IDs.",
            "atom_code_rule": "C{chapter:03d}-A{atom_order_in_chapter:04d}; old segment_no is preserved in old_segment_no.",
            "distance_rule": "Use atom_distance_basis.global_atom_order absolute difference; then check same_cluster/same_event/same_scene/same_scene_group/same_time_block.",
            "source_db": str(SOURCE_DB),
            "source_w32_units": str(W32_UNITS),
            "source_w32_lines": str(W32_LINES),
            "source_w33_events": str(W33_EVENTS),
            "source_w33_event_units": str(W33_UNITS),
            "source_scene_points": str(SCENE_POINTS),
            "source_scene_groups": str(SCENE_GROUPS),
            "source_time_blocks": str(TIME_BLOCKS),
        }
        self.db.executemany(
            "INSERT INTO build_meta(key, value) VALUES (?, ?)",
            sorted(meta.items()),
        )

    def insert_atoms(self) -> None:
        for row in self.segments:
            old_segment_no = clean(row["segment_no"])
            atom = self.segment_to_atom[old_segment_no]
            self.db.execute(
                """
                INSERT INTO clean_atoms (
                    atom_id, atom_code, chapter_no, atom_order_in_chapter, global_atom_order,
                    old_segment_no, page_id, chapter_page_id, chapter_label, summary, quote,
                    original_version, scene_place_raw, time_point_raw, is_focus_raw,
                    perspective_raw, note_type_raw, note_dimension_raw, function_tags_raw,
                    old_cluster_unit_raw, source_row, source_db, source_table, source_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    atom["atom_id"],
                    atom["atom_code"],
                    atom["chapter_no"],
                    atom["atom_order_in_chapter"],
                    atom["global_atom_order"],
                    old_segment_no,
                    clean(row["page_id"]),
                    clean(row["chapter_page_id"]),
                    clean(row["chapter_label"]),
                    clean(row["summary"]),
                    clean(row["quote"]),
                    clean(row["original_version"]),
                    clean(row["scene_place"]),
                    clean(row["time_point"]),
                    clean(row["is_focus"]),
                    clean(row["perspective"]),
                    clean(row["note_type"]),
                    clean(row["note_dimension"]),
                    clean(row["function_tags"]),
                    clean(row["cluster_unit"]),
                    parse_int(row["source_row"], None),
                    str(SOURCE_DB),
                    "segments",
                    "derived_read_only_copy",
                ),
            )
            self.db.execute(
                """
                INSERT INTO atom_source_map (
                    atom_id, old_segment_no, page_id, source_db, source_table, source_row, source_key
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    atom["atom_id"],
                    old_segment_no,
                    clean(row["page_id"]),
                    str(SOURCE_DB),
                    "segments",
                    parse_int(row["source_row"], None),
                    old_segment_no,
                ),
            )
            self.add_anchor(
                atom["atom_id"],
                old_segment_no,
                anchor_status="segment_row",
                evidence_eligible="from_segments",
                confidence=1.0,
                anchor_text=clean(row["quote"]),
                method="segments.old_segment_no",
                query_source="segments.segment_no",
                query_text=old_segment_no,
            )

    def insert_base_memberships(self) -> None:
        for atom in self.atom_to_segment.values():
            row = atom["source"]
            chapter_id = f"CH-{atom['chapter_no']:03d}"
            self.add_membership(
                atom["atom_id"],
                "chapter",
                chapter_id,
                clean(row["chapter_label"]) or chapter_id,
                atom["chapter_no"],
                "contains_atom",
                atom["atom_order_in_chapter"],
                1,
                "segments",
                SOURCE_DB,
                chapter_id,
                1.0,
                "resolved",
            )
            self.add_membership(
                atom["atom_id"],
                "segment",
                atom["old_segment_no"],
                clean(row["summary"]) or atom["old_segment_no"],
                atom["chapter_no"],
                "source_atom_segment",
                1,
                1,
                "segments",
                SOURCE_DB,
                atom["old_segment_no"],
                1.0,
                "resolved",
            )
            self.add_hierarchy(
                "segment",
                atom["old_segment_no"],
                "chapter",
                chapter_id,
                atom["chapter_no"],
                "belongs_to",
                "segments",
                SOURCE_DB,
                atom["old_segment_no"],
                "resolved",
            )
            self.insert_segment_raw_links(atom)

    def insert_segment_raw_links(self, atom: dict[str, Any]) -> None:
        row = atom["source"]
        raw_fields = [
            ("space", "scene_place", "scene_place_raw", "atom_raw_field"),
            ("time_point", "time_point", "time_point_raw", "atom_raw_field"),
            ("perspective", "perspective", "perspective_raw", "atom_raw_field"),
            ("note_type", "note_type", "note_type_raw", "atom_raw_field"),
            ("note_dimension", "note_dimension", "note_dimension_raw", "atom_raw_field"),
            ("function", "function_tags", "function_tags_raw", "atom_raw_field"),
        ]
        for link_type, field, role, precision in raw_fields:
            for value in split_values(row[field]):
                self.add_link(
                    atom["atom_id"],
                    link_type,
                    value,
                    value,
                    role,
                    "atom",
                    precision,
                    atom["chapter_no"],
                    "segments",
                    "segments",
                    SOURCE_DB,
                    atom["old_segment_no"],
                    0.85 if value in {"待判", "待校"} else 1.0,
                    "raw_field",
                    clean(row[field]),
                )

    def insert_cluster_memberships(self) -> None:
        for segment_no, rows in self.cluster_lines_by_segment.items():
            atom = self.segment_to_atom.get(segment_no)
            if not atom:
                continue
            for row in rows:
                cluster_id = clean(row.get("cluster_id"))
                unit = self.cluster_units.get(cluster_id, {})
                label = clean(unit.get("cluster_title")) or clean(unit.get("cluster_unit_raw")) or cluster_id
                review_status = clean(unit.get("quality_status")) or clean(unit.get("review_level")) or "resolved"
                self.add_membership(
                    atom["atom_id"],
                    "cluster_unit",
                    cluster_id,
                    label,
                    atom["chapter_no"],
                    clean(row.get("line_role")) or "member_line",
                    parse_int(row.get("position_in_cluster"), atom["atom_order_in_chapter"]),
                    1,
                    "W32_cluster_unit_lines",
                    W32_LINES,
                    f"{cluster_id}:{segment_no}",
                    1.0,
                    review_status,
                )
                self.add_anchor(
                    atom["atom_id"],
                    segment_no,
                    clean(row.get("line_anchor_status")) or "W32_line",
                    clean(row.get("evidence_eligible")),
                    1.0,
                    clean(row.get("quote")),
                    "W32_cluster_unit_lines.line_no",
                    "line_no",
                    segment_no,
                )
                chapter_id = f"CH-{atom['chapter_no']:03d}"
                self.add_hierarchy(
                    "cluster_unit",
                    cluster_id,
                    "chapter",
                    chapter_id,
                    atom["chapter_no"],
                    "belongs_to",
                    "W32_cluster_units",
                    W32_UNITS,
                    cluster_id,
                    clean(unit.get("quality_status")) or "resolved",
                )

    def insert_event_memberships(self) -> None:
        for row in dict_rows(self.db, "SELECT atom_id, container_id FROM atom_memberships WHERE container_type='cluster_unit'"):
            atom_id = row["atom_id"]
            cluster_id = row["container_id"]
            atom = self.atom_to_segment.get(atom_id)
            if not atom:
                continue
            for event_unit in self.event_units_by_cluster.get(cluster_id, []):
                event_id = clean(event_unit.get("event_id"))
                event = self.events.get(event_id, {})
                label = clean(event.get("event_title")) or event_id
                order = (parse_int(event_unit.get("position_in_event"), 0) or 0) * 1000
                order += parse_int(self.cluster_line_position(atom["old_segment_no"], cluster_id), 0) or 0
                review_status = clean(event_unit.get("review_flag")) or clean(event.get("quality_status")) or "resolved"
                self.add_membership(
                    atom_id,
                    "event",
                    event_id,
                    label,
                    atom["chapter_no"],
                    clean(event_unit.get("unit_role_in_event")) or "cluster_in_event",
                    order,
                    1,
                    "W33_event_units",
                    W33_UNITS,
                    f"{event_id}:{cluster_id}",
                    0.95,
                    review_status,
                )
                self.add_hierarchy(
                    "cluster_unit",
                    cluster_id,
                    "event",
                    event_id,
                    atom["chapter_no"],
                    "rolls_up_to",
                    "W33_event_units",
                    W33_UNITS,
                    f"{event_id}:{cluster_id}",
                    review_status,
                )
                self.add_hierarchy(
                    "event",
                    event_id,
                    "chapter",
                    f"CH-{atom['chapter_no']:03d}",
                    atom["chapter_no"],
                    "belongs_to",
                    "W33_events",
                    W33_EVENTS,
                    event_id,
                    clean(event.get("quality_status")) or "resolved",
                )

    def cluster_line_position(self, segment_no: str, cluster_id: str) -> int | None:
        for row in self.cluster_lines_by_segment.get(segment_no, []):
            if clean(row.get("cluster_id")) == cluster_id:
                return parse_int(row.get("position_in_cluster"), None)
        return None

    def insert_scene_memberships_and_links(self) -> None:
        for row in self.time_blocks:
            self.add_hierarchy(
                "time_block",
                clean(row.get("time_block_id")),
                "chapter",
                f"CH-{parse_int(row.get('chapter_no'), 0) or 0:03d}",
                parse_int(row.get("chapter_no"), None),
                "belongs_to",
                "101_time_blocks",
                TIME_BLOCKS,
                clean(row.get("time_block_id")),
                "resolved",
            )
            for atom in self.atoms_in_range(row.get("chapter_no"), row.get("start_segment_no"), row.get("end_segment_no")):
                self.add_membership(
                    atom["atom_id"],
                    "time_block",
                    clean(row.get("time_block_id")),
                    clean(row.get("time_label")) or clean(row.get("time_block_id")),
                    atom["chapter_no"],
                    "within_time_block",
                    atom["atom_order_in_chapter"],
                    1,
                    "101_time_blocks",
                    TIME_BLOCKS,
                    clean(row.get("time_block_id")),
                    0.9 if clean(row.get("confidence")) != "低" else 0.65,
                    clean(row.get("confidence")) or "resolved",
                )
                self.add_link(
                    atom["atom_id"],
                    "time_block_label",
                    clean(row.get("time_block_id")),
                    clean(row.get("time_label")),
                    "time_block_context",
                    "time_block",
                    "scene_library_range",
                    atom["chapter_no"],
                    "101_time_blocks",
                    "time_blocks",
                    TIME_BLOCKS,
                    clean(row.get("time_block_id")),
                    0.9,
                    "range_context",
                    clean(row.get("time_evidence")),
                )

        for row in self.scene_groups:
            scene_group_id = clean(row.get("scene_group_id"))
            time_block_id = clean(row.get("time_block_id"))
            chapter_no = parse_int(row.get("chapter_no"), None)
            if time_block_id:
                self.add_hierarchy(
                    "scene_group",
                    scene_group_id,
                    "time_block",
                    time_block_id,
                    chapter_no,
                    "rolls_up_to",
                    "101_scene_groups",
                    SCENE_GROUPS,
                    scene_group_id,
                    clean(row.get("boundary_confidence")) or "resolved",
                )
            self.add_hierarchy(
                "scene_group",
                scene_group_id,
                "chapter",
                f"CH-{chapter_no or 0:03d}",
                chapter_no,
                "belongs_to",
                "101_scene_groups",
                SCENE_GROUPS,
                scene_group_id,
                clean(row.get("boundary_confidence")) or "resolved",
            )
            for atom in self.atoms_in_range(row.get("chapter_no"), row.get("start_segment_no"), row.get("end_segment_no")):
                self.add_membership(
                    atom["atom_id"],
                    "scene_group",
                    scene_group_id,
                    clean(row.get("scene_group_title")) or scene_group_id,
                    atom["chapter_no"],
                    "within_scene_group",
                    atom["atom_order_in_chapter"],
                    1,
                    "101_scene_groups",
                    SCENE_GROUPS,
                    scene_group_id,
                    0.9,
                    clean(row.get("boundary_confidence")) or "resolved",
                )

        for row in self.scene_points:
            scene_id = clean(row.get("scene_id"))
            scene_group_id = clean(row.get("scene_group_id"))
            time_block_id = clean(row.get("time_block_id"))
            chapter_no = parse_int(row.get("chapter_no"), None)
            review_status = "needs_review" if truthy(row.get("needs_review")) else "resolved"
            confidence = 0.65 if review_status == "needs_review" else 0.9
            if scene_group_id:
                self.add_hierarchy(
                    "scene_point",
                    scene_id,
                    "scene_group",
                    scene_group_id,
                    chapter_no,
                    "rolls_up_to",
                    "101_scene_points",
                    SCENE_POINTS,
                    scene_id,
                    review_status,
                )
            if time_block_id:
                self.add_hierarchy(
                    "scene_point",
                    scene_id,
                    "time_block",
                    time_block_id,
                    chapter_no,
                    "within_time_block",
                    "101_scene_points",
                    SCENE_POINTS,
                    scene_id,
                    review_status,
                )
            self.add_hierarchy(
                "scene_point",
                scene_id,
                "chapter",
                f"CH-{chapter_no or 0:03d}",
                chapter_no,
                "belongs_to",
                "101_scene_points",
                SCENE_POINTS,
                scene_id,
                review_status,
            )
            for atom in self.atoms_in_range(row.get("chapter_no"), row.get("start_segment_no"), row.get("end_segment_no")):
                self.add_membership(
                    atom["atom_id"],
                    "scene_point",
                    scene_id,
                    clean(row.get("scene_title")) or scene_id,
                    atom["chapter_no"],
                    "within_scene_point",
                    atom["atom_order_in_chapter"],
                    1,
                    "101_scene_points",
                    SCENE_POINTS,
                    scene_id,
                    confidence,
                    review_status,
                )
                self.add_scene_links(atom, row, confidence, review_status)

    def add_scene_links(
        self,
        atom: dict[str, Any],
        row: dict[str, str],
        confidence: float,
        review_status: str,
    ) -> None:
        scene_id = clean(row.get("scene_id"))
        direct_fields = [
            ("scene_weight", "scene_weight", "scene_point_attribute"),
            ("presence_mode", "presence_mode", "scene_point_attribute"),
            ("relationship_type", "relationship_type", "scene_point_attribute"),
            ("emotion_symbolic_function", "emotional_or_symbolic_function", "scene_point_attribute"),
            ("scene_space_hint", "place_label", "scene_point_hint"),
        ]
        for link_type, field, role in direct_fields:
            for value in split_values(row.get(field)):
                self.add_link(
                    atom["atom_id"],
                    link_type,
                    value,
                    value,
                    role,
                    "scene_point",
                    "derived_scene_range",
                    atom["chapter_no"],
                    "101_scene_points",
                    "scene_points",
                    SCENE_POINTS,
                    scene_id,
                    confidence,
                    review_status,
                    clean(row.get(field)),
                )
        multi_fields = [
            ("scene_person_hint", "characters_present", "characters_present"),
            ("scene_person_hint", "characters_mentioned", "characters_mentioned"),
            ("scene_object_hint", "objects_present", "objects_present"),
        ]
        for link_type, field, role in multi_fields:
            for value in split_values(row.get(field)):
                self.add_link(
                    atom["atom_id"],
                    link_type,
                    value,
                    value,
                    role,
                    "scene_point",
                    "derived_scene_range_hint",
                    atom["chapter_no"],
                    "101_scene_points",
                    "scene_points",
                    SCENE_POINTS,
                    scene_id,
                    min(confidence, 0.6),
                    "hint_" + review_status,
                    clean(row.get(field)),
                )

    def atoms_in_range(self, chapter_value: Any, start_segment_no: Any, end_segment_no: Any) -> list[dict[str, Any]]:
        chapter_no = parse_int(chapter_value, None)
        if chapter_no is None:
            return []
        start_atom = self.segment_to_atom.get(clean(start_segment_no))
        end_atom = self.segment_to_atom.get(clean(end_segment_no))
        if not start_atom or not end_atom:
            return []
        start_order = min(start_atom["atom_order_in_chapter"], end_atom["atom_order_in_chapter"])
        end_order = max(start_atom["atom_order_in_chapter"], end_atom["atom_order_in_chapter"])
        return [
            atom
            for atom in self.chapter_atoms.get(chapter_no, [])
            if start_order <= atom["atom_order_in_chapter"] <= end_order
        ]

    def insert_edge_links(self) -> None:
        self.insert_person_links()
        self.insert_space_axis_links()
        self.insert_event_segment_links()
        self.insert_evidence_links()
        self.insert_time_axis_links()

    def insert_person_links(self) -> None:
        for row in dict_rows(self.source_db, "SELECT * FROM person_segment_edges"):
            segment_no = clean(row.get("segment_no"))
            if segment_no not in self.segment_no_set:
                continue
            atom = self.segment_to_atom[segment_no]
            ok = truthy(row.get("resolved_character")) and truthy(row.get("resolved_segment"))
            self.add_link(
                atom["atom_id"],
                "person",
                clean(row.get("character_code")) or clean(row.get("character_key")) or clean(row.get("character_page_id")),
                clean(row.get("character_name")) or clean(row.get("character_key")),
                clean(row.get("role_type")) or clean(row.get("description_type")) or "mentioned",
                "atom",
                "person_segment_edge",
                atom["chapter_no"],
                "person_segment_edges",
                "person_segment_edges",
                SOURCE_DB,
                clean(row.get("edge_id")),
                confidence_from_bool(ok),
                review_from_bool(ok),
                clean(row.get("edge_title")),
            )

    def insert_space_axis_links(self) -> None:
        rows = dict_rows(
            self.source_db,
            """
            SELECT * FROM space_evidence_axis
            WHERE chapter_no BETWEEN ? AND ?
            """,
            (self.start_chapter, self.end_chapter),
        )
        for row in rows:
            segment_no = clean(row.get("segment_no"))
            atom = self.segment_to_atom.get(segment_no)
            if not atom:
                continue
            level = clean(row.get("evidence_level"))
            self.add_link(
                atom["atom_id"],
                "space",
                clean(row.get("standard_space_page_id")) or clean(row.get("standard_space")),
                clean(row.get("standard_space")),
                clean(row.get("relation_type")) or clean(row.get("activity_type")) or "located_in",
                "atom",
                "space_evidence_axis",
                atom["chapter_no"],
                "space_evidence_axis",
                "space_evidence_axis",
                SOURCE_DB,
                clean(row.get("space_evidence_key")),
                confidence_from_space_level(level),
                "needs_review" if level.startswith("D") else "resolved",
                clean(row.get("context_quote")),
            )

    def insert_event_segment_links(self) -> None:
        for row in dict_rows(self.source_db, "SELECT * FROM event_segment_edges"):
            segment_no = clean(row.get("segment_no"))
            if segment_no not in self.segment_no_set:
                continue
            atom = self.segment_to_atom.get(segment_no)
            if not atom:
                continue
            ok = truthy(row.get("resolved_event")) and truthy(row.get("resolved_segment"))
            self.add_link(
                atom["atom_id"],
                "event",
                clean(row.get("event_id")) or clean(row.get("event_page_id")),
                clean(row.get("event_label")) or clean(row.get("event_id")),
                clean(row.get("evidence_type")) or "event_segment_edge",
                "atom",
                "event_segment_edge",
                atom["chapter_no"],
                "event_segment_edges",
                "event_segment_edges",
                SOURCE_DB,
                clean(row.get("edge_key")),
                confidence_from_bool(ok),
                review_from_bool(ok),
                clean(row.get("note")),
            )

    def insert_evidence_links(self) -> None:
        rows = dict_rows(
            self.source_db,
            """
            SELECT * FROM evidence_edges
            WHERE chapter_no BETWEEN ? AND ?
            """,
            (self.start_chapter, self.end_chapter),
        )
        for row in rows:
            segment_no = clean(row.get("segment_no"))
            atom = self.segment_to_atom.get(segment_no)
            if not atom:
                continue
            link_type = evidence_axis_to_link_type(row.get("source_axis"))
            value_id = clean(row.get("source_key")) or clean(row.get("target_key"))
            value_name = clean(row.get("source_label")) or clean(row.get("target_label")) or value_id
            ok = truthy(row.get("resolved"))
            self.add_link(
                atom["atom_id"],
                link_type,
                value_id,
                value_name,
                clean(row.get("relation_type")) or "evidence_edge",
                "atom",
                "evidence_edge",
                atom["chapter_no"],
                "evidence_edges",
                clean(row.get("source_table")) or "evidence_edges",
                SOURCE_DB,
                clean(row.get("edge_id")),
                confidence_from_bool(ok, low=0.6),
                review_from_bool(ok),
                clean(row.get("evidence_text")),
            )

    def insert_time_axis_links(self) -> None:
        rows = dict_rows(
            self.source_db,
            """
            SELECT * FROM time_axis
            WHERE chapter_no BETWEEN ? AND ?
            """,
            (self.start_chapter, self.end_chapter),
        )
        for row in rows:
            chapter_no = parse_int(row.get("chapter_no"), None)
            if chapter_no is None:
                continue
            for atom in self.chapter_atoms.get(chapter_no, []):
                title = clean(row.get("title")) or clean(row.get("event_node")) or clean(row.get("time_key"))
                confidence = 0.55 if "待判" in clean(row.get("precision_label")) or "待判" in clean(row.get("season")) else 0.7
                review_status = "chapter_level_context"
                self.add_link(
                    atom["atom_id"],
                    "time_axis",
                    clean(row.get("time_key")),
                    title,
                    clean(row.get("coordinate_type")) or "time_axis",
                    "chapter",
                    "chapter_level_context",
                    atom["chapter_no"],
                    "time_axis",
                    "time_axis",
                    SOURCE_DB,
                    clean(row.get("time_key")),
                    confidence,
                    review_status,
                    clean(row.get("context_quote")),
                )
                for season in split_values(row.get("season")):
                    if season in {"待判", "无强季节锚"}:
                        status = "chapter_level_uncertain"
                        conf = min(confidence, 0.45)
                    else:
                        status = review_status
                        conf = confidence
                    self.add_link(
                        atom["atom_id"],
                        "season",
                        season,
                        season,
                        clean(row.get("precision_label")) or "season_context",
                        "chapter",
                        "chapter_level_context",
                        atom["chapter_no"],
                        "time_axis",
                        "time_axis",
                        SOURCE_DB,
                        clean(row.get("time_key")),
                        conf,
                        status,
                        clean(row.get("season")),
                    )

    def insert_hierarchy(self) -> None:
        for cluster_id, row in self.cluster_units.items():
            chapter_no = parse_int(row.get("chapter_no"), None)
            self.add_hierarchy(
                "cluster_unit",
                cluster_id,
                "chapter",
                f"CH-{chapter_no or 0:03d}",
                chapter_no,
                "belongs_to",
                "W32_cluster_units",
                W32_UNITS,
                cluster_id,
                clean(row.get("quality_status")) or "resolved",
            )
        for event_id, row in self.events.items():
            chapter_no = parse_int(row.get("chapter_no"), None)
            self.add_hierarchy(
                "event",
                event_id,
                "chapter",
                f"CH-{chapter_no or 0:03d}",
                chapter_no,
                "belongs_to",
                "W33_events",
                W33_EVENTS,
                event_id,
                clean(row.get("quality_status")) or "resolved",
            )

    def insert_distance_rules(self) -> None:
        rows = [
            (
                "global_atom_distance",
                "全局原子段距离",
                "ABS(a.global_atom_order - b.global_atom_order)",
                "数值越小，两个点在全文线性序列中越近；0 代表同一原子段。",
            ),
            (
                "signed_atom_distance",
                "有向原子段距离",
                "b.global_atom_order - a.global_atom_order",
                "从起点看目标点：正数代表目标在后，负数代表目标在前，0 代表同一原子段。",
            ),
            (
                "same_cluster",
                "同一聚拢单元",
                "a.cluster_id = b.cluster_id",
                "为 1 时两个点在同一 W32 聚拢单元内。",
            ),
            (
                "same_event",
                "同一事件",
                "a.event_id = b.event_id",
                "为 1 时两个点在同一 W33 事件内。",
            ),
            (
                "same_scene_group",
                "同一场面组",
                "a.scene_group_id = b.scene_group_id",
                "为 1 时两个点在同一 101 场面组内。",
            ),
            (
                "same_time_block",
                "同一时间块",
                "a.time_block_id = b.time_block_id",
                "为 1 时两个点在同一 101 时间块内。",
            ),
        ]
        self.db.executemany(
            "INSERT INTO distance_metric_rules(rule_key, rule_label, rule_sql_hint, interpretation) VALUES (?, ?, ?, ?)",
            rows,
        )

    def add_membership(
        self,
        atom_id: str,
        container_type: str,
        container_id: str,
        container_label: str,
        chapter_no: int | None,
        role: str,
        order_in_container: int | None,
        is_primary: int,
        source_name: str,
        source_path: Path,
        source_key: str,
        confidence: float,
        review_status: str,
    ) -> None:
        container_id = clean(container_id)
        if not atom_id or not container_type or not container_id:
            return
        key = f"{atom_id}|{container_type}|{container_id}|{source_name}"
        if key in self.membership_seen:
            return
        self.membership_seen.add(key)
        membership_id = stable_id("MS", atom_id, container_type, container_id, source_name)
        self.db.execute(
            """
            INSERT INTO atom_memberships (
                membership_id, atom_id, container_type, container_id, container_label,
                chapter_no, role, order_in_container, is_primary, source_name, source_path,
                source_key, confidence, review_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                membership_id,
                atom_id,
                container_type,
                container_id,
                clean(container_label),
                chapter_no,
                clean(role),
                order_in_container,
                is_primary,
                source_name,
                source_label(source_path),
                clean(source_key),
                confidence,
                clean(review_status) or "resolved",
            ),
        )

    def add_link(
        self,
        atom_id: str,
        link_type: str,
        link_value_id: str,
        link_value_name: str,
        link_role: str,
        scope: str,
        precision: str,
        chapter_no: int | None,
        source_name: str,
        source_table: str,
        source_path: Path,
        source_key: str,
        confidence: float,
        review_status: str,
        raw_value: str,
    ) -> None:
        link_type = clean(link_type)
        link_value_name = clean(link_value_name)
        if not atom_id or not link_type or not link_value_name:
            return
        key = f"{atom_id}|{link_type}|{link_value_id}|{link_value_name}|{link_role}|{scope}|{precision}|{source_name}|{source_key}"
        if key in self.link_seen:
            return
        self.link_seen.add(key)
        link_id = stable_id("LK", key)
        self.db.execute(
            """
            INSERT INTO atom_links (
                link_id, atom_id, link_type, link_value_id, link_value_name, link_role,
                scope, precision, chapter_no, source_name, source_table, source_path,
                source_key, confidence, review_status, raw_value
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                link_id,
                atom_id,
                link_type,
                clean(link_value_id),
                link_value_name,
                clean(link_role),
                clean(scope),
                clean(precision),
                chapter_no,
                clean(source_name),
                clean(source_table),
                source_label(source_path),
                clean(source_key),
                confidence,
                clean(review_status) or "resolved",
                clean(raw_value),
            ),
        )

    def add_anchor(
        self,
        atom_id: str,
        old_segment_no: str,
        anchor_status: str,
        evidence_eligible: str,
        confidence: float,
        anchor_text: str,
        method: str,
        query_source: str,
        query_text: str,
    ) -> None:
        self.db.execute(
            """
            INSERT OR REPLACE INTO atom_anchors (
                atom_id, old_segment_no, anchor_status, evidence_eligible, confidence,
                anchor_text, method, query_source, query_text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                atom_id,
                clean(old_segment_no),
                clean(anchor_status),
                clean(evidence_eligible),
                confidence,
                clean(anchor_text),
                clean(method),
                clean(query_source),
                clean(query_text),
            ),
        )

    def add_hierarchy(
        self,
        lower_type: str,
        lower_id: str,
        upper_type: str,
        upper_id: str,
        chapter_no: int | None,
        relation_type: str,
        source_name: str,
        source_path: Path,
        source_key: str,
        review_status: str,
    ) -> None:
        lower_id = clean(lower_id)
        upper_id = clean(upper_id)
        if not lower_type or not lower_id or not upper_type or not upper_id:
            return
        key = f"{lower_type}|{lower_id}|{upper_type}|{upper_id}|{relation_type}|{source_name}"
        if key in self.hierarchy_seen:
            return
        self.hierarchy_seen.add(key)
        hierarchy_id = stable_id("HR", key)
        self.db.execute(
            """
            INSERT INTO container_hierarchy (
                hierarchy_id, lower_type, lower_id, upper_type, upper_id, chapter_no,
                relation_type, source_name, source_path, source_key, review_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hierarchy_id,
                clean(lower_type),
                lower_id,
                clean(upper_type),
                upper_id,
                chapter_no,
                clean(relation_type),
                clean(source_name),
                source_label(source_path),
                clean(source_key),
                clean(review_status) or "resolved",
            ),
        )

    def build_container_index(self) -> None:
        self.db.execute("DELETE FROM container_index")
        rows = dict_rows(
            self.db,
            """
            SELECT
                m.container_type,
                m.container_id,
                MAX(m.container_label) AS container_label,
                MAX(m.chapter_no) AS chapter_no,
                MIN(a.global_atom_order) AS start_atom_order,
                MAX(a.global_atom_order) AS end_atom_order,
                COUNT(DISTINCT m.atom_id) AS atom_count,
                MAX(m.source_name) AS source_name,
                GROUP_CONCAT(DISTINCT m.review_status) AS review_status
            FROM atom_memberships m
            JOIN clean_atoms a ON a.atom_id = m.atom_id
            GROUP BY m.container_type, m.container_id
            ORDER BY m.container_type, start_atom_order
            """,
        )
        for row in rows:
            self.db.execute(
                """
                INSERT INTO container_index (
                    container_type, container_id, container_label, chapter_no, start_atom_order,
                    end_atom_order, atom_count, source_name, quality_status, review_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["container_type"],
                    row["container_id"],
                    row["container_label"],
                    row["chapter_no"],
                    row["start_atom_order"],
                    row["end_atom_order"],
                    row["atom_count"],
                    row["source_name"],
                    "derived",
                    row["review_status"],
                ),
            )

    def first_container(self, atom_id: str, container_type: str) -> str | None:
        row = self.db.execute(
            """
            SELECT container_id
            FROM atom_memberships
            WHERE atom_id=? AND container_type=?
            ORDER BY is_primary DESC, order_in_container, container_id
            LIMIT 1
            """,
            (atom_id, container_type),
        ).fetchone()
        return clean(row["container_id"]) if row else None

    def build_distance_basis(self) -> None:
        self.db.execute("DELETE FROM atom_distance_basis")
        for atom in sorted(self.atom_to_segment.values(), key=lambda item: item["global_atom_order"]):
            self.db.execute(
                """
                INSERT INTO atom_distance_basis (
                    atom_id, atom_code, chapter_no, atom_order_in_chapter, global_atom_order,
                    old_segment_no, cluster_id, event_id, scene_id, scene_group_id, time_block_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    atom["atom_id"],
                    atom["atom_code"],
                    atom["chapter_no"],
                    atom["atom_order_in_chapter"],
                    atom["global_atom_order"],
                    atom["old_segment_no"],
                    self.first_container(atom["atom_id"], "cluster_unit"),
                    self.first_container(atom["atom_id"], "event"),
                    self.first_container(atom["atom_id"], "scene_point"),
                    self.first_container(atom["atom_id"], "scene_group"),
                    self.first_container(atom["atom_id"], "time_block"),
                ),
            )

    def build_flat_index(self) -> None:
        self.db.execute("DELETE FROM atom_flat_index")
        for atom in sorted(self.atom_to_segment.values(), key=lambda item: item["global_atom_order"]):
            atom_id = atom["atom_id"]
            containers = {
                "cluster_ids": self.join_distinct(
                    "SELECT container_id FROM atom_memberships WHERE atom_id=? AND container_type='cluster_unit' ORDER BY container_id",
                    (atom_id,),
                ),
                "event_ids": self.join_distinct(
                    "SELECT container_id FROM atom_memberships WHERE atom_id=? AND container_type='event' ORDER BY container_id",
                    (atom_id,),
                ),
                "scene_ids": self.join_distinct(
                    "SELECT container_id FROM atom_memberships WHERE atom_id=? AND container_type='scene_point' ORDER BY container_id",
                    (atom_id,),
                ),
                "scene_group_ids": self.join_distinct(
                    "SELECT container_id FROM atom_memberships WHERE atom_id=? AND container_type='scene_group' ORDER BY container_id",
                    (atom_id,),
                ),
                "time_block_ids": self.join_distinct(
                    "SELECT container_id FROM atom_memberships WHERE atom_id=? AND container_type='time_block' ORDER BY container_id",
                    (atom_id,),
                ),
            }
            links = {
                "persons": self.join_links(atom_id, ["person", "scene_person_hint"]),
                "spaces": self.join_links(atom_id, ["space", "scene_space_hint"]),
                "objects": self.join_links(atom_id, ["object", "scene_object_hint"]),
                "time_points": self.join_links(atom_id, ["time_point", "time_axis", "time_block_label"]),
                "seasons": self.join_links(atom_id, ["season"]),
                "note_types": self.join_links(atom_id, ["note_type"]),
                "note_dimensions": self.join_links(atom_id, ["note_dimension"]),
                "functions": self.join_links(atom_id, ["function", "emotion_symbolic_function"]),
                "review_flags": self.join_distinct(
                    """
                    SELECT review_status
                    FROM atom_links
                    WHERE atom_id=? AND review_status NOT IN ('resolved', 'raw_field')
                    ORDER BY review_status
                    """,
                    (atom_id,),
                ),
            }
            self.db.execute(
                """
                INSERT INTO atom_flat_index (
                    atom_id, atom_code, chapter_no, global_atom_order, old_segment_no,
                    cluster_ids, event_ids, scene_ids, scene_group_ids, time_block_ids,
                    persons, spaces, objects, time_points, seasons, note_types,
                    note_dimensions, functions, review_flags
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    atom_id,
                    atom["atom_code"],
                    atom["chapter_no"],
                    atom["global_atom_order"],
                    atom["old_segment_no"],
                    containers["cluster_ids"],
                    containers["event_ids"],
                    containers["scene_ids"],
                    containers["scene_group_ids"],
                    containers["time_block_ids"],
                    links["persons"],
                    links["spaces"],
                    links["objects"],
                    links["time_points"],
                    links["seasons"],
                    links["note_types"],
                    links["note_dimensions"],
                    links["functions"],
                    links["review_flags"],
                ),
            )

    def build_quality_findings(self) -> None:
        self.db.execute("DELETE FROM quality_findings")

        def insert(
            severity: str,
            finding_type: str,
            subject_type: str,
            subject_id: str,
            detail: str,
            source_name: str,
        ) -> None:
            finding_id = stable_id("QF", severity, finding_type, subject_type, subject_id, detail)
            self.db.execute(
                """
                INSERT OR IGNORE INTO quality_findings (
                    finding_id, severity, finding_type, subject_type, subject_id,
                    detail, source_name, review_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
                """,
                (
                    finding_id,
                    clean(severity),
                    clean(finding_type),
                    clean(subject_type),
                    clean(subject_id),
                    clean(detail),
                    clean(source_name),
                ),
            )

        for container_type in ["cluster_unit", "event", "scene_point", "scene_group", "time_block"]:
            rows = dict_rows(
                self.db,
                """
                SELECT a.atom_code, a.old_segment_no, m.atom_id,
                       GROUP_CONCAT(DISTINCT m.container_id) AS container_ids,
                       COUNT(DISTINCT m.container_id) AS container_count
                FROM atom_memberships m
                JOIN clean_atoms a ON a.atom_id=m.atom_id
                WHERE m.container_type=?
                GROUP BY m.atom_id
                HAVING COUNT(DISTINCT m.container_id)>1
                ORDER BY a.global_atom_order
                """,
                (container_type,),
            )
            for row in rows:
                severity = "warning" if container_type in {"scene_point", "scene_group", "time_block"} else "error"
                insert(
                    severity,
                    f"multiple_{container_type}_memberships",
                    "atom",
                    clean(row["atom_code"]),
                    f"{row['old_segment_no']} maps to {row['container_count']} {container_type}: {row['container_ids']}",
                    "atom_memberships",
                )

        for container_type in ["cluster_unit", "event", "scene_point", "scene_group", "time_block"]:
            missing_rows = dict_rows(
                self.db,
                f"""
                SELECT a.atom_code, a.old_segment_no
                FROM clean_atoms a
                WHERE NOT EXISTS (
                    SELECT 1 FROM atom_memberships m
                    WHERE m.atom_id=a.atom_id AND m.container_type=?
                )
                ORDER BY a.global_atom_order
                """,
                (container_type,),
            )
            for row in missing_rows:
                insert(
                    "error",
                    f"missing_{container_type}_membership",
                    "atom",
                    clean(row["atom_code"]),
                    f"{row['old_segment_no']} has no {container_type} membership",
                    "atom_memberships",
                )

        chapter_time_links = self.scalar(
            "SELECT COUNT(*) FROM atom_links WHERE source_name='time_axis' AND precision='chapter_level_context'"
        )
        if chapter_time_links:
            insert(
                "info",
                "chapter_level_time_context",
                "build",
                f"CH{self.start_chapter:03d}_{self.end_chapter:03d}",
                f"{chapter_time_links} time_axis links are chapter-level context, not atom-level hard anchors",
                "time_axis",
            )
        insert(
            "info",
            "line_index_not_independent_source",
            "build",
            f"CH{self.start_chapter:03d}_{self.end_chapter:03d}",
            "No independent line_index source table was found; this clean library uses segments.segment_no as the atom source and W32 line_no/line_id as anchors.",
            "segments + W32_cluster_unit_lines",
        )

    def join_distinct(self, sql: str, params: tuple[Any, ...]) -> str:
        values = [clean(row[0]) for row in self.db.execute(sql, params).fetchall() if clean(row[0])]
        return " | ".join(unique_keep_order(values))

    def join_links(self, atom_id: str, link_types: list[str]) -> str:
        placeholders = ",".join("?" for _ in link_types)
        rows = self.db.execute(
            f"""
            SELECT link_value_name
            FROM atom_links
            WHERE atom_id=? AND link_type IN ({placeholders})
            ORDER BY link_type, confidence DESC, link_value_name
            """,
            (atom_id, *link_types),
        ).fetchall()
        return " | ".join(unique_keep_order(clean(row[0]) for row in rows if clean(row[0])))

    def export_csvs(self) -> None:
        exports = [
            "clean_atoms",
            "atom_memberships",
            "atom_links",
            "atom_distance_basis",
            "atom_flat_index",
            "container_index",
            "container_hierarchy",
            "distance_metric_rules",
            "quality_findings",
        ]
        for table in exports:
            rows = self.db.execute(f"SELECT * FROM {table}").fetchall()
            path = self.output_dir / f"{table}_CH{self.start_chapter:03d}_{self.end_chapter:03d}_{self.build_label}.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as fh:
                if not rows:
                    writer = csv.writer(fh)
                    writer.writerow([])
                    continue
                writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
                writer.writeheader()
                for row in rows:
                    writer.writerow(dict(row))

    def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        row = self.db.execute(sql, params).fetchone()
        return row[0] if row else None

    def grouped_counts(self, sql: str) -> list[tuple[Any, Any]]:
        return [(row[0], row[1]) for row in self.db.execute(sql).fetchall()]

    def write_report(self) -> None:
        atom_count = self.scalar("SELECT COUNT(*) FROM clean_atoms")
        link_count = self.scalar("SELECT COUNT(*) FROM atom_links")
        membership_count = self.scalar("SELECT COUNT(*) FROM atom_memberships")
        hierarchy_count = self.scalar("SELECT COUNT(*) FROM container_hierarchy")
        no_cluster = self.scalar(
            """
            SELECT COUNT(*) FROM clean_atoms a
            WHERE NOT EXISTS (
                SELECT 1 FROM atom_memberships m
                WHERE m.atom_id=a.atom_id AND m.container_type='cluster_unit'
            )
            """
        )
        no_event = self.scalar(
            """
            SELECT COUNT(*) FROM clean_atoms a
            WHERE NOT EXISTS (
                SELECT 1 FROM atom_memberships m
                WHERE m.atom_id=a.atom_id AND m.container_type='event'
            )
            """
        )
        no_scene = self.scalar(
            """
            SELECT COUNT(*) FROM clean_atoms a
            WHERE NOT EXISTS (
                SELECT 1 FROM atom_memberships m
                WHERE m.atom_id=a.atom_id AND m.container_type='scene_point'
            )
            """
        )
        no_scene_group = self.scalar(
            """
            SELECT COUNT(*) FROM clean_atoms a
            WHERE NOT EXISTS (
                SELECT 1 FROM atom_memberships m
                WHERE m.atom_id=a.atom_id AND m.container_type='scene_group'
            )
            """
        )
        no_time_block = self.scalar(
            """
            SELECT COUNT(*) FROM clean_atoms a
            WHERE NOT EXISTS (
                SELECT 1 FROM atom_memberships m
                WHERE m.atom_id=a.atom_id AND m.container_type='time_block'
            )
            """
        )
        chapter_counts = self.grouped_counts(
            "SELECT chapter_no, COUNT(*) FROM clean_atoms GROUP BY chapter_no ORDER BY chapter_no"
        )
        membership_counts = self.grouped_counts(
            "SELECT container_type, COUNT(*) FROM atom_memberships GROUP BY container_type ORDER BY container_type"
        )
        link_type_counts = self.grouped_counts(
            "SELECT link_type, COUNT(*) FROM atom_links GROUP BY link_type ORDER BY COUNT(*) DESC, link_type"
        )
        review_counts = self.grouped_counts(
            "SELECT review_status, COUNT(*) FROM atom_links GROUP BY review_status ORDER BY COUNT(*) DESC, review_status"
        )
        finding_counts = self.grouped_counts(
            "SELECT finding_type, COUNT(*) FROM quality_findings GROUP BY finding_type ORDER BY COUNT(*) DESC, finding_type"
        )
        finding_samples = dict_rows(
            self.db,
            """
            SELECT severity, finding_type, subject_id, detail
            FROM quality_findings
            WHERE severity IN ('warning', 'error')
            ORDER BY severity DESC, finding_type, subject_id
            LIMIT 12
            """,
        )
        sample = self.db.execute(
            """
            SELECT a.atom_id, a.atom_code, a.old_segment_no, a.chapter_no,
                   d.cluster_id, d.event_id, d.scene_id, d.scene_group_id, d.time_block_id,
                   a.summary
            FROM clean_atoms a
            LEFT JOIN atom_distance_basis d ON d.atom_id=a.atom_id
            ORDER BY a.global_atom_order
            LIMIT 1
            """
        ).fetchone()

        lines = [
            "# 红楼梦干净聚拢坐标库审计报告",
            "",
            f"- 构建范围：第 {self.start_chapter} 回至第 {self.end_chapter} 回",
            f"- 构建标签：{self.build_label}",
            f"- 输出库：`{self.db_path.name}`",
            f"- 旧库状态：只读读取，不写回，不交接",
            f"- 原子段编号规则：`A000001..A002706` 按 1-120 回 `segments` 全局顺序一次性编号；本模板只抽取本范围，所以将来全量库的同一原子段编号不变",
            f"- 单元门牌号规则：`C{{chapter:03d}}-A{{atom_order_in_chapter:04d}}`，旧门牌保存在 `old_segment_no`",
            "",
            "## 总数",
            "",
            f"- 原子段：{atom_count}",
            f"- 固定归属 membership：{membership_count}",
            f"- 指向 link/assertion：{link_count}",
            f"- 上下级 hierarchy：{hierarchy_count}",
            "",
            "## 分回原子段",
            "",
        ]
        lines.extend(f"- 第 {chapter} 回：{count}" for chapter, count in chapter_counts)
        lines.extend(
            [
                "",
                "## 归属层级统计",
                "",
            ]
        )
        lines.extend(f"- {name}：{count}" for name, count in membership_counts)
        lines.extend(
            [
                "",
                "## 指向类型统计",
                "",
            ]
        )
        lines.extend(f"- {name}：{count}" for name, count in link_type_counts)
        lines.extend(
            [
                "",
                "## 审核状态统计",
                "",
            ]
        )
        lines.extend(f"- {name}：{count}" for name, count in review_counts)
        lines.extend(
            [
                "",
                "## 质量发现",
                "",
            ]
        )
        if finding_counts:
            lines.extend(f"- {name}：{count}" for name, count in finding_counts)
        else:
            lines.append("- 无")
        if finding_samples:
            lines.extend(["", "样例："])
            lines.extend(
                f"- [{row['severity']}] {row['subject_id']}：{row['detail']}"
                for row in finding_samples
            )
        lines.extend(
            [
                "",
                "## 距离可测状态",
                "",
                f"- 无 W32 聚拢单元归属的原子段：{no_cluster}",
                f"- 无 W33 事件归属的原子段：{no_event}",
                f"- 无 101 场面点归属的原子段：{no_scene}",
                f"- 无 101 场面组归属的原子段：{no_scene_group}",
                f"- 无 101 时间块归属的原子段：{no_time_block}",
                "- 距离基础表：`atom_distance_basis`",
                "- 两点距离视图：`v_atom_pair_distance`，用 `atom_distance` 看线性距离，用 `same_cluster/same_event/same_scene/same_scene_group/same_time_block` 判断是否同层相遇",
                "",
                "## 模板样例",
                "",
            ]
        )
        if sample:
            lines.extend(
                [
                    f"- atom_id：`{sample['atom_id']}`",
                    f"- atom_code：`{sample['atom_code']}`",
                    f"- old_segment_no：`{sample['old_segment_no']}`",
                    f"- cluster/event/scene：`{sample['cluster_id']}` / `{sample['event_id']}` / `{sample['scene_id']}`",
                    f"- scene_group/time_block：`{sample['scene_group_id']}` / `{sample['time_block_id']}`",
                    f"- summary：{sample['summary']}",
                ]
            )
        lines.extend(
            [
                "",
                "## 本轮发现的问题",
                "",
                "- `一行索引库`仍未作为独立底表落地；本库以 `segments.segment_no` 作为最小原子段来源，并把 W32 的 `line_no/line_id` 回接为锚。",
                "- `time_axis` 多数是回目或阶段级时间判断，已进入 `atom_links`，但标成 `scope=chapter`、`precision=chapter_level_context`，不伪装成逐行硬锚。",
                "- 101 场面库里的 `characters_present/objects_present/place_label` 是场面范围推断，已进入 `scene_*_hint` 类型，和 `person_segment_edges/space_evidence_axis/evidence_edges` 这类硬边分开。",
                "- 固定结构不做成散乱标签：原子段身份在 `clean_atoms`，上下级在 `atom_memberships/container_hierarchy`，人物空间物件时间等指向在 `atom_links`，查询便利层在 `atom_flat_index`。",
            ]
        )
        self.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=5)
    parser.add_argument("--label", default="模板")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        safe_label = re.sub(r"[^\w\u4e00-\u9fff]+", "_", args.label).strip("_") or "build"
        output_dir = OUTPUT_ROOT / f"红楼梦干净聚拢坐标库_CH{args.start:03d}_{args.end:03d}_{safe_label}"
    builder = Builder(args.start, args.end, output_dir, args.label)
    builder.run()
    print(builder.db_path)
    print(builder.report_path)


if __name__ == "__main__":
    main()
