#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import db_runtime
import dl2_runtime


def main() -> int:
    parser = argparse.ArgumentParser(description="数字生命2.0幂等数据库迁移")
    parser.add_argument("--db", type=Path, default=db_runtime.write_db_path())
    args = parser.parse_args()
    with sqlite3.connect(args.db, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        before = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result = dl2_runtime.migrate(conn)
        conn.commit()
        after = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result["database"] = str(args.db)
        result["new_tables"] = sorted(name for name in after - before if name.startswith("dl2_"))
        result["quick_check"] = conn.execute("PRAGMA quick_check").fetchone()[0]
        result["dl2_foreign_key_violations"] = [
            list(row) for row in conn.execute("PRAGMA foreign_key_check") if str(row[0]).startswith("dl2_")
        ]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["quick_check"] == "ok" and not result["dl2_foreign_key_violations"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
