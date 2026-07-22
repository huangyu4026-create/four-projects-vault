#!/usr/bin/env python3
"""数字生命 OS｜稳定读取快照刷新器.

将正式主库用 SQLite backup API 刷新为稳定读取快照。
这不是事实写入，不修改 Notion 母本，只用于让日常读取层与正式主库对齐。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import db_runtime


CORE_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = CORE_ROOT.parents[1]
RUNTIME_ROOT = CORE_ROOT / "runtime"
REPORT_ROOT = CORE_ROOT / "reports"
OUTPUTS_ROOT = WORKSPACE_ROOT / "outputs"

DB_PATH = RUNTIME_ROOT / "digital_life_os_core.sqlite"
STABLE_DB_PATH = db_runtime.STABLE_DB_PATH
TEMP_DB_PATH = STABLE_DB_PATH.with_suffix(STABLE_DB_PATH.suffix + ".tmp")

REPORT_JSON = REPORT_ROOT / "127_stable_snapshot_refresh.json"
REPORT_MD = REPORT_ROOT / "127_stable_snapshot_refresh.md"
OUTPUT_MD = OUTPUTS_ROOT / "数字生命OS_稳定读取快照刷新报告.md"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()[0]
    )


def table_count(conn: sqlite3.Connection, table: str) -> int:
    if not table_exists(conn, table):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def db_snapshot(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "integrity": "missing", "counts": {}}
    conn = connect_ro(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        keys = [
            "source_documents",
            "timeline_nodes",
            "timeline_days",
            "qingfeng_logs",
            "people",
            "evidence_index",
            "evidence_grade_index",
            "workflow_definitions",
            "trigger_routes",
        ]
        return {
            "path": str(path),
            "exists": True,
            "integrity": integrity,
            "counts": {key: table_count(conn, key) for key in keys},
        }
    finally:
        conn.close()


def refresh() -> dict[str, Any]:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUTS_ROOT.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"正式主库不存在：{DB_PATH}")

    before = db_snapshot(STABLE_DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        temp_path = Path(f"{TEMP_DB_PATH}{suffix}")
        if temp_path.exists():
            temp_path.unlink()
    source = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=30)
    target = sqlite3.connect(TEMP_DB_PATH, timeout=30)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    temp = db_snapshot(TEMP_DB_PATH)
    if temp.get("integrity") != "ok":
        raise RuntimeError(f"稳定快照临时库完整性失败：{temp}")

    TEMP_DB_PATH.replace(STABLE_DB_PATH)
    after = db_snapshot(STABLE_DB_PATH)
    official = db_snapshot(DB_PATH)
    matched = official.get("counts") == after.get("counts")
    payload = {
        "project": "数字生命 OS｜Mac 本地版",
        "generated_at": now_iso(),
        "status": "pass" if matched and after.get("integrity") == "ok" else "fail",
        "passed": bool(matched and after.get("integrity") == "ok"),
        "official_db": official,
        "stable_before": before,
        "stable_after": after,
        "counts_matched": matched,
        "notion_mother_modified": False,
    }
    write_reports(payload)
    return payload


def write_reports(payload: dict[str, Any]) -> None:
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    official = payload.get("official_db", {}).get("counts", {})
    stable = payload.get("stable_after", {}).get("counts", {})
    lines = [
        "# 数字生命 OS｜稳定读取快照刷新报告",
        "",
        f"- 生成时间：{payload.get('generated_at')}",
        f"- 状态：{payload.get('status')}",
        f"- 正式主库：`{payload.get('official_db', {}).get('path')}`",
        f"- 稳定快照：`{payload.get('stable_after', {}).get('path')}`",
        f"- 计数一致：{payload.get('counts_matched')}",
        "- Notion 母本：未修改",
        "",
        "## 核心计数",
        "",
        "| 项目 | 正式主库 | 稳定快照 |",
        "|---|---:|---:|",
    ]
    for key in sorted(set(official) | set(stable)):
        lines.append(f"| {key} | {official.get(key, 0)} | {stable.get(key, 0)} |")
    lines.append("")
    text = "\n".join(lines)
    REPORT_MD.write_text(text, encoding="utf-8")
    OUTPUT_MD.write_text(text, encoding="utf-8")


def main() -> int:
    payload = refresh()
    print(
        json.dumps(
            {
                "status": payload["status"],
                "passed": payload["passed"],
                "stable": payload.get("stable_after", {}).get("path"),
                "report": str(REPORT_JSON),
                "notion_mother_modified": payload["notion_mother_modified"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
