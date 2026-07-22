#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import dl2_runtime as dl2


def table_digest(conn: sqlite3.Connection, table: str) -> str:
    rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
    payload = [list(row) for row in rows]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def expect_error(name: str, action, checks: list[dict]) -> None:
    try:
        action()
    except (dl2.DL2Error, sqlite3.IntegrityError) as exc:
        checks.append({"id": name, "pass": True, "evidence": str(exc)})
        return
    checks.append({"id": name, "pass": False, "evidence": "unexpected success"})


def main() -> int:
    parser = argparse.ArgumentParser(description="数字生命2.0门禁与回归验收（仅用于临时副本）")
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    checks: list[dict] = []
    dl2.CONTEXT_OUTBOX = args.db.parent / "dl2-context-outbox"
    with sqlite3.connect(args.db, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        dl2.migrate(conn)
        source_before = {table: table_digest(conn, table) for table in ("qingfeng_logs", "events", "fact_assertions", "psychological_patterns")}

        expect_error("N01_NO_SOURCE_REJECTED", lambda: dl2.preview_memory(conn, {
            "statement": "无来源内容", "statement_type": "FACT", "change_reason": "test", "evidence": []}), checks)
        expect_error("N02_BAD_HASH_REJECTED", lambda: dl2.preview_memory(conn, {
            "statement": "哈希错误", "statement_type": "FACT", "change_reason": "test", "evidence": [{
                "source_type": "event", "source_id": "event:08332d65d53b1e34c1e0",
                "source_anchor": "test", "source_sha256": "0" * 64}]}), checks)

        version_id = conn.execute("SELECT version_id FROM dl2_memory_versions LIMIT 1").fetchone()[0]
        expect_error("N03_MEMORY_VERSION_APPEND_ONLY", lambda: conn.execute(
            "UPDATE dl2_memory_versions SET statement_snapshot='tampered' WHERE version_id=?", (version_id,)), checks)
        conn.rollback()

        expect_error("N04_HYPOTHESIS_REQUIRES_COUNTER", lambda: dl2.preview_hypothesis(conn, {
            "claim": "单向结论", "domain": "test", "applicable_period": "now", "applicable_context": "test",
            "strongest_counterargument": "none", "supporting_memory_ids": ["dlmem:seed-m01"], "counter_memory_ids": []}), checks)

        sealed = dl2.prepare_calibration(conn, {
            "case_id": "dlcal:test-sealed", "question": "我会如何判断？", "question_domain": "test",
            "system_answer_before_user_answer": "系统先答案", "retrieved_context_manifest": ["dlmem:seed-m01"]})
        checks.append({"id": "N05_SYSTEM_ANSWER_SEALED", "pass": sealed["user_answer_present"] is False, "evidence": sealed["system_answer_sha256"]})
        expect_error("N06_COMPARE_BEFORE_USER_REJECTED", lambda: dl2.compare_calibration(conn, {
            "case_id": "dlcal:test-sealed", "difference_summary": "none", "error_class": "MATERIAL_MISSING"}), checks)

        base_package = {
            "requester": "P05", "purpose": "test", "question": "test", "authorization_id": "INVALID",
            "allowed_domains": ["test"], "items": [{"item_type": "MEMORY", "item_ref": "dlmem:seed-m01", "item_role": "CONTEXT"}]}
        expect_error("N07_P05_WITHOUT_AUTH_REJECTED", lambda: dl2.preview_context_package(conn, base_package), checks)
        legacy_lwg = dict(base_package, requester="LWG", authorization_id="P05-AUTH-LWG-DL-20260720")
        expect_error("N08_LEGACY_LWG_NOT_CURRENT_RECEIVER", lambda: dl2.preview_context_package(conn, legacy_lwg), checks)
        unknown = dict(base_package, requester="UNKNOWN", authorization_id="USER-EXPLICIT-test")
        expect_error("N09_UNKNOWN_RECEIVER_REJECTED", lambda: dl2.preview_context_package(conn, unknown), checks)

        conn.execute("UPDATE dl2_memory_units SET sensitivity_level='S3_RESTRICTED' WHERE memory_id='dlmem:seed-m20'")
        restricted = dict(base_package, authorization_id="P05-AUTH-test", items=[{"item_type": "MEMORY", "item_ref": "dlmem:seed-m20", "item_role": "CONTEXT"}])
        expect_error("N10_S3_CROSS_PROJECT_REJECTED", lambda: dl2.preview_context_package(conn, restricted), checks)
        conn.execute("UPDATE dl2_memory_units SET sensitivity_level='S1_PERSONAL' WHERE memory_id='dlmem:seed-m20'")

        good = dict(base_package, authorization_id="P05-AUTH-test")
        preview = dl2.preview_context_package(conn, good)
        issued = dl2.issue_context_package(conn, preview["preview_id"])
        checks.append({"id": "N11_NO_RECEIPT_NOT_ADOPTED", "pass": issued["status"] == "DELIVERED_NOT_ADOPTED", "evidence": issued["package_id"]})
        detail = dl2.context_package_detail(conn, issued["package_id"])
        checks.append({"id": "M4_AUTO_SOURCE_MANIFEST", "pass": bool(detail["package"]["source_manifest"]), "evidence": len(detail["package"]["source_manifest"])})
        expect_error("N12_RECEIVER_MISMATCH_REJECTED", lambda: dl2.register_access_receipt(conn, {
            "package_id": issued["package_id"], "package_hash": issued["package_hash"], "receiver": "LWG", "decision": "HELD", "receipt_ref": "test"}), checks)
        expect_error("M4_BAD_PACKAGE_HASH_REJECTED", lambda: dl2.register_access_receipt(conn, {
            "package_id": issued["package_id"], "package_hash": "0" * 64, "receiver": "P05", "decision": "HELD", "receipt_ref": "bad-hash"}), checks)
        artifact_path = Path(issued["artifact_path"])
        artifact_original = artifact_path.read_text(encoding="utf-8")
        artifact_tampered = json.loads(artifact_original)
        artifact_tampered["question"] = "tampered"
        artifact_path.write_text(json.dumps(artifact_tampered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        expect_error("M4_TAMPERED_ARTIFACT_REJECTED", lambda: dl2.register_access_receipt(conn, {
            "package_id": issued["package_id"], "package_hash": issued["package_hash"], "receiver": "P05", "decision": "HELD", "receipt_ref": "tampered-artifact"}), checks)
        artifact_path.write_text(artifact_original, encoding="utf-8")
        expect_error("M4_ACCEPTED_REQUIRES_ACTUAL_READ", lambda: dl2.register_access_receipt(conn, {
            "package_id": issued["package_id"], "package_hash": issued["package_hash"], "receiver": "P05", "decision": "ACCEPTED", "receipt_ref": "empty-read"}), checks)
        expect_error("M4_UNKNOWN_READ_REF_REJECTED", lambda: dl2.register_access_receipt(conn, {
            "package_id": issued["package_id"], "package_hash": issued["package_hash"], "receiver": "P05", "decision": "ACCEPTED",
            "actual_read": ["dlmem:not-in-package"], "receipt_ref": "bad-ref"}), checks)
        receipt_payload = {"package_id": issued["package_id"], "package_hash": issued["package_hash"], "receiver": "P05", "decision": "HELD", "receipt_ref": "test-idempotent"}
        first_receipt = dl2.register_access_receipt(conn, receipt_payload)
        second_receipt = dl2.register_access_receipt(conn, receipt_payload)
        checks.append({"id": "N13_RECEIPT_IDEMPOTENT", "pass": second_receipt["status"] == "IDEMPOTENT" and first_receipt["receipt_id"] == second_receipt["receipt_id"], "evidence": second_receipt["receipt_id"]})

        gates = {row["feature_id"]: row["status"] for row in conn.execute("SELECT feature_id,status FROM dl2_feature_gates")}
        checks.append({"id": "N14_M5_M6_DISABLED", "pass": gates == {"M5_ACTIVITYWATCH": "DISABLED", "M6_READ_ONLY_AGENT": "DISABLED"}, "evidence": gates})
        source_after = {table: table_digest(conn, table) for table in source_before}
        checks.append({"id": "N15_SOURCE_TABLES_UNCHANGED", "pass": source_before == source_after, "evidence": source_after})

        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        dl2_fk = [dict(row) for row in conn.execute("PRAGMA foreign_key_check").fetchall() if str(row[0]).startswith("dl2_")]
        checks.append({"id": "DB_QUICK_CHECK", "pass": quick == "ok", "evidence": quick})
        checks.append({"id": "DL2_FOREIGN_KEYS", "pass": not dl2_fk, "evidence": dl2_fk})
        conn.rollback()

    result = {"suite": "DL2_N01_N15", "passed": sum(1 for item in checks if item["pass"]), "total": len(checks), "all_pass": all(item["pass"] for item in checks), "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
