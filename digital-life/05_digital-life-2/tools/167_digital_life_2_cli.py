#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import db_runtime
import dl2_runtime as dl2


def read_payload(path: str) -> dict:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="数字生命2.0命令行入口")
    parser.add_argument("command", choices=[
        "status", "memory-list", "memory-detail", "memory-preview", "memory-confirm",
        "memory-revise-preview", "memory-revise-confirm", "hypothesis-list", "hypothesis-detail",
        "hypothesis-preview", "hypothesis-confirm", "hypothesis-revise-preview", "hypothesis-revise-confirm",
        "calibration-prepare", "calibration-answer", "calibration-compare", "calibration-detail",
        "context-preview", "context-issue", "context-receipt", "context-detail",
    ])
    parser.add_argument("--input", default="-")
    parser.add_argument("--id", default="")
    parser.add_argument("--preview-id", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--status", default="")
    parser.add_argument("--db", type=Path, default=db_runtime.write_db_path())
    args = parser.parse_args()
    write_commands = {
        "memory-preview", "memory-confirm", "memory-revise-preview", "memory-revise-confirm",
        "hypothesis-preview", "hypothesis-confirm", "hypothesis-revise-preview", "hypothesis-revise-confirm",
        "calibration-prepare", "calibration-answer", "calibration-compare", "context-preview", "context-issue", "context-receipt",
    }
    mode = "rw" if args.command in write_commands else "ro"
    uri = str(args.db) if mode == "rw" else f"file:{args.db}?mode=ro"
    with sqlite3.connect(uri, uri=(mode == "ro"), timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        payload = None
        if args.command == "status": payload = dl2.status_payload(conn)
        elif args.command == "memory-list": payload = dl2.list_memories(conn, args.limit, args.status)
        elif args.command == "memory-detail": payload = dl2.memory_detail(conn, args.id)
        elif args.command == "memory-preview": payload = dl2.preview_memory(conn, read_payload(args.input))
        elif args.command == "memory-confirm": payload = dl2.confirm_memory(conn, args.preview_id)
        elif args.command == "memory-revise-preview": payload = dl2.preview_memory_revision(conn, read_payload(args.input))
        elif args.command == "memory-revise-confirm": payload = dl2.confirm_memory_revision(conn, args.preview_id)
        elif args.command == "hypothesis-list": payload = dl2.list_hypotheses(conn, args.limit, args.status)
        elif args.command == "hypothesis-detail": payload = dl2.hypothesis_detail(conn, args.id)
        elif args.command == "hypothesis-preview": payload = dl2.preview_hypothesis(conn, read_payload(args.input))
        elif args.command == "hypothesis-confirm": payload = dl2.confirm_hypothesis(conn, args.preview_id)
        elif args.command == "hypothesis-revise-preview": payload = dl2.preview_hypothesis_revision(conn, read_payload(args.input))
        elif args.command == "hypothesis-revise-confirm": payload = dl2.confirm_hypothesis_revision(conn, args.preview_id)
        elif args.command == "calibration-prepare": payload = dl2.prepare_calibration(conn, read_payload(args.input))
        elif args.command == "calibration-answer": payload = dl2.answer_calibration(conn, read_payload(args.input))
        elif args.command == "calibration-compare": payload = dl2.compare_calibration(conn, read_payload(args.input))
        elif args.command == "calibration-detail": payload = dl2.calibration_detail(conn, args.id)
        elif args.command == "context-preview": payload = dl2.preview_context_package(conn, read_payload(args.input))
        elif args.command == "context-issue": payload = dl2.issue_context_package(conn, args.preview_id)
        elif args.command == "context-receipt": payload = dl2.register_access_receipt(conn, read_payload(args.input))
        elif args.command == "context-detail": payload = dl2.context_package_detail(conn, args.id)
        if mode == "rw":
            conn.commit()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except dl2.DL2Error as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
