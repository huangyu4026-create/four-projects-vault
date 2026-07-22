#!/usr/bin/env python3
"""数字生命 OS｜数据库运行路径分流.

读取优先走稳定快照，写入仍走正式主库。这样后台进程占用正式库时，
日常出库、验收和查询不会误读到不完整运行态。
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1]


def _project_entry_path() -> Path | None:
    for parent in (CORE_ROOT, *CORE_ROOT.parents):
        candidate = parent / "PROJECT_ENTRY.json"
        if candidate.is_file():
            return candidate
    return None


def _project_entry() -> dict:
    path = _project_entry_path()
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


PROJECT_ENTRY_PATH = _project_entry_path()
PROJECT_ENTRY = _project_entry()
OFFICIAL_DB_PATH = Path(PROJECT_ENTRY.get("official_database") or CORE_ROOT / "runtime" / "digital_life_os_core.sqlite")
STABLE_DB_PATH = Path(PROJECT_ENTRY.get("stable_database") or CORE_ROOT / "runtime" / "digital_life_os_core_stable_v1_20260722.sqlite")


def read_db_path() -> Path:
    override = os.environ.get("DIGITAL_LIFE_DB_PATH", "").strip()
    if override:
        return Path(override)
    if os.environ.get("DIGITAL_LIFE_USE_OFFICIAL_DB") == "1":
        return OFFICIAL_DB_PATH
    return STABLE_DB_PATH if STABLE_DB_PATH.exists() else OFFICIAL_DB_PATH


def write_db_path() -> Path:
    override = os.environ.get("DIGITAL_LIFE_DB_PATH", "").strip()
    if override:
        return Path(override)
    return OFFICIAL_DB_PATH


def connect_readonly() -> sqlite3.Connection:
    path = read_db_path()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def connect_writable() -> sqlite3.Connection:
    conn = sqlite3.connect(write_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def best_effort_connect_writable() -> sqlite3.Connection | None:
    try:
        return connect_writable()
    except sqlite3.Error:
        return None


def path_summary() -> dict:
    return {
        "official_db_path": str(OFFICIAL_DB_PATH),
        "stable_db_path": str(STABLE_DB_PATH),
        "read_db_path": str(read_db_path()),
        "write_db_path": str(write_db_path()),
        "read_mode": "official" if read_db_path() == OFFICIAL_DB_PATH else "stable_snapshot",
        "project_entry_path": str(PROJECT_ENTRY_PATH or ""),
    }
