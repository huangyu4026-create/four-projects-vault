#!/usr/bin/env python3
"""数字生命 2.0 可演化个人模型层运行内核。

本模块只管理派生记忆、模型候选、校准和最小上下文包；
不修改原始日记、事件、事实断言或 Notion 母本。
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import db_runtime


CORE_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_OUTBOX = CORE_ROOT / "runtime" / "dl2_context_packages" / "outbox"
MIGRATION_ID = "DL2-001-core-model-v1"


class DL2Error(ValueError):
    """对用户可解释的领域错误。"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_hash(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def make_id(prefix: str) -> str:
    return f"{prefix}:{secrets.token_hex(12)}"


def _json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, bool, int, float)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _require(payload: dict, *keys: str) -> None:
    missing = [key for key in keys if payload.get(key) in (None, "", [])]
    if missing:
        raise DL2Error(f"缺少必填字段: {', '.join(missing)}")


def _one(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(params)).fetchone()


SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS dl2_schema_migrations (
  migration_id TEXT PRIMARY KEY,
  checksum TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dl2_write_previews (
  preview_id TEXT PRIMARY KEY CHECK(preview_id LIKE 'dlpreview:%'),
  operation TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('READY','CONSUMED','EXPIRED','CANCELLED')),
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed_at TEXT
);

CREATE TABLE IF NOT EXISTS dl2_memory_units (
  memory_id TEXT PRIMARY KEY CHECK(memory_id LIKE 'dlmem:%'),
  statement_type TEXT NOT NULL CHECK(statement_type IN ('FACT','EXPERIENCE_SUMMARY','USER_QUOTE','SYSTEM_INTERPRETATION','HYPOTHESIS_PENDING')),
  status TEXT NOT NULL CHECK(status IN ('CANDIDATE','USER_CONFIRMED','HELD','REJECTED','REVISED','SUPERSEDED','WITHDRAWN')),
  current_version_id TEXT NOT NULL,
  event_time TEXT,
  formed_at TEXT NOT NULL,
  valid_from TEXT,
  valid_to TEXT,
  confidence_state TEXT NOT NULL CHECK(confidence_state IN ('HIGH','MEDIUM','LOW','INSUFFICIENT')),
  ownership_state TEXT NOT NULL CHECK(ownership_state IN ('SOURCE_FACT','USER_WORDS','SYSTEM_CANDIDATE','USER_CONFIRMED_SELF_UNDERSTANDING')),
  sensitivity_level TEXT NOT NULL CHECK(sensitivity_level IN ('S0_PUBLIC','S1_PERSONAL','S2_SENSITIVE','S3_RESTRICTED','S4_WITHHELD')),
  access_scope_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dl2_memory_versions (
  version_id TEXT PRIMARY KEY CHECK(version_id LIKE 'dlmemv:%'),
  memory_id TEXT NOT NULL REFERENCES dl2_memory_units(memory_id),
  previous_version_id TEXT REFERENCES dl2_memory_versions(version_id),
  version_no INTEGER NOT NULL CHECK(version_no >= 1),
  statement_snapshot TEXT NOT NULL,
  change_type TEXT NOT NULL CHECK(change_type IN ('CREATED','EVIDENCE_ADDED','USER_CORRECTION','COUNTEREVIDENCE_ADDED','PERIOD_EXPIRED','SCOPE_NARROWED','EXPLANATION_REPLACED','WITHDRAWN')),
  change_reason TEXT NOT NULL,
  trigger_source_json TEXT NOT NULL DEFAULT '{}',
  changed_by TEXT NOT NULL CHECK(changed_by IN ('AI','USER','PROGRAM_AUDIT')),
  created_at TEXT NOT NULL,
  UNIQUE(memory_id, version_no)
);

CREATE TABLE IF NOT EXISTS dl2_memory_evidence_links (
  link_id TEXT PRIMARY KEY CHECK(link_id LIKE 'dlmele:%'),
  memory_id TEXT NOT NULL REFERENCES dl2_memory_units(memory_id),
  version_id TEXT NOT NULL REFERENCES dl2_memory_versions(version_id),
  evidence_role TEXT NOT NULL CHECK(evidence_role IN ('SOURCE','SUPPORT','COUNTER','CONFLICT')),
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
  source_anchor TEXT NOT NULL,
  char_start INTEGER,
  char_end INTEGER,
  fact_id TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(version_id, evidence_role, source_type, source_id, source_anchor)
);

CREATE TABLE IF NOT EXISTS dl2_user_corrections (
  correction_id TEXT PRIMARY KEY CHECK(correction_id LIKE 'dlcorr:%'),
  target_type TEXT NOT NULL CHECK(target_type IN ('MEMORY','HYPOTHESIS')),
  target_id TEXT NOT NULL,
  user_feedback_raw TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('RECEIVED','APPLIED','HELD','REJECTED')),
  resulting_version_id TEXT,
  receipt_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS dl2_model_hypotheses (
  hypothesis_id TEXT PRIMARY KEY CHECK(hypothesis_id LIKE 'dlhyp:%'),
  source_pattern_id TEXT,
  domain TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('SYSTEM_CANDIDATE','USER_CONFIRMED_AS_SELF_UNDERSTANDING','HELD','CONTESTED','REVISED','RETIRED')),
  current_version_id TEXT NOT NULL,
  ownership_state TEXT NOT NULL CHECK(ownership_state IN ('SYSTEM_CANDIDATE','USER_CONFIRMED_SELF_UNDERSTANDING')),
  sensitivity_level TEXT NOT NULL CHECK(sensitivity_level IN ('S0_PUBLIC','S1_PERSONAL','S2_SENSITIVE','S3_RESTRICTED','S4_WITHHELD')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dl2_hypothesis_versions (
  version_id TEXT PRIMARY KEY CHECK(version_id LIKE 'dlhypv:%'),
  hypothesis_id TEXT NOT NULL REFERENCES dl2_model_hypotheses(hypothesis_id),
  previous_version_id TEXT REFERENCES dl2_hypothesis_versions(version_id),
  version_no INTEGER NOT NULL CHECK(version_no >= 1),
  claim TEXT NOT NULL,
  applicable_period TEXT NOT NULL,
  applicable_context TEXT NOT NULL,
  strongest_counterargument TEXT NOT NULL,
  alternative_explanations_json TEXT NOT NULL DEFAULT '[]',
  failure_conditions_json TEXT NOT NULL DEFAULT '[]',
  evidence_sufficiency TEXT NOT NULL CHECK(evidence_sufficiency IN ('SUFFICIENT','PARTIAL','INSUFFICIENT')),
  change_reason TEXT NOT NULL,
  changed_by TEXT NOT NULL CHECK(changed_by IN ('AI','USER','PROGRAM_AUDIT')),
  created_at TEXT NOT NULL,
  UNIQUE(hypothesis_id, version_no)
);

CREATE TABLE IF NOT EXISTS dl2_hypothesis_memory_links (
  link_id TEXT PRIMARY KEY CHECK(link_id LIKE 'dlhml:%'),
  hypothesis_id TEXT NOT NULL REFERENCES dl2_model_hypotheses(hypothesis_id),
  hypothesis_version_id TEXT NOT NULL REFERENCES dl2_hypothesis_versions(version_id),
  memory_id TEXT NOT NULL REFERENCES dl2_memory_units(memory_id),
  relation_role TEXT NOT NULL CHECK(relation_role IN ('SUPPORT','COUNTER','EXCEPTION')),
  created_at TEXT NOT NULL,
  UNIQUE(hypothesis_version_id, memory_id, relation_role)
);

CREATE TABLE IF NOT EXISTS dl2_calibration_cases (
  case_id TEXT PRIMARY KEY CHECK(case_id LIKE 'dlcal:%'),
  question TEXT NOT NULL,
  question_domain TEXT NOT NULL,
  system_answer_before_user_answer TEXT NOT NULL,
  system_answer_sha256 TEXT NOT NULL CHECK(length(system_answer_sha256)=64),
  retrieved_context_manifest_json TEXT NOT NULL,
  user_answer_raw TEXT,
  comparison_dimensions_json TEXT NOT NULL DEFAULT '[]',
  difference_summary TEXT,
  error_class TEXT CHECK(error_class IS NULL OR error_class IN ('MATERIAL_INSUFFICIENT','RETRIEVAL_ERROR','PERIOD_MISPLACED','OVER_INFERENCE','USER_CHANGED','QUESTION_AMBIGUOUS','RIGHT_ANSWER_WRONG_EVIDENCE','NO_MATERIAL_DIFFERENCE')),
  affected_memory_ids_json TEXT NOT NULL DEFAULT '[]',
  affected_hypothesis_ids_json TEXT NOT NULL DEFAULT '[]',
  revision_decision_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL CHECK(status IN ('SEALED','USER_ANSWERED','COMPARED','REVISION_REQUIRED','COMPLETE')),
  created_at TEXT NOT NULL,
  sealed_at TEXT NOT NULL,
  answered_at TEXT,
  compared_at TEXT
);

CREATE TABLE IF NOT EXISTS dl2_context_packages (
  package_id TEXT PRIMARY KEY CHECK(package_id LIKE 'dlctx:%'),
  requester TEXT NOT NULL,
  purpose TEXT NOT NULL,
  question TEXT NOT NULL,
  authorization_id TEXT NOT NULL,
  allowed_domains_json TEXT NOT NULL,
  excluded_domains_json TEXT NOT NULL,
  source_manifest_json TEXT NOT NULL,
  uncertainties_json TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  revocable INTEGER NOT NULL CHECK(revocable IN (0,1)),
  package_hash TEXT NOT NULL CHECK(length(package_hash)=64),
  status TEXT NOT NULL CHECK(status IN ('ISSUED','DELIVERED_NOT_ADOPTED','ACCEPTED','REJECTED','REVOKED','EXPIRED')),
  artifact_path TEXT,
  created_at TEXT NOT NULL,
  issued_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dl2_context_package_items (
  item_id TEXT PRIMARY KEY CHECK(item_id LIKE 'dlctxi:%'),
  package_id TEXT NOT NULL REFERENCES dl2_context_packages(package_id),
  item_type TEXT NOT NULL CHECK(item_type IN ('MEMORY','HYPOTHESIS','SOURCE_ANCHOR','UNCERTAINTY')),
  item_ref TEXT NOT NULL,
  item_role TEXT NOT NULL CHECK(item_role IN ('SUPPORT','COUNTER','CONTEXT','BOUNDARY')),
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
  created_at TEXT NOT NULL,
  UNIQUE(package_id, item_type, item_ref, item_role)
);

CREATE TABLE IF NOT EXISTS dl2_access_receipts (
  receipt_id TEXT PRIMARY KEY CHECK(receipt_id LIKE 'dlreceipt:%'),
  package_id TEXT NOT NULL REFERENCES dl2_context_packages(package_id),
  receiver TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('ACCEPTED','REJECTED','HELD','REVOKED')),
  actual_read_json TEXT NOT NULL DEFAULT '[]',
  refused_json TEXT NOT NULL DEFAULT '[]',
  returned_json TEXT NOT NULL DEFAULT '{}',
  target_writeback INTEGER NOT NULL DEFAULT 0 CHECK(target_writeback IN (0,1)),
  receipt_ref TEXT NOT NULL,
  receipt_hash TEXT NOT NULL CHECK(length(receipt_hash)=64),
  created_at TEXT NOT NULL,
  UNIQUE(package_id, receiver, receipt_hash)
);

CREATE TABLE IF NOT EXISTS dl2_feature_gates (
  feature_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('DISABLED','READY_FOR_AUTHORIZATION','ENABLED','RETIRED')),
  authorization_required INTEGER NOT NULL CHECK(authorization_required IN (0,1)),
  authorization_receipt TEXT,
  preconditions_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dl2_audit_log (
  audit_id TEXT PRIMARY KEY CHECK(audit_id LIKE 'dlaudit:%'),
  operation TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  receipt_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dl2_memory_status ON dl2_memory_units(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_dl2_memory_type ON dl2_memory_units(statement_type, sensitivity_level);
CREATE INDEX IF NOT EXISTS idx_dl2_memory_evidence_source ON dl2_memory_evidence_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_dl2_hypothesis_status ON dl2_model_hypotheses(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_dl2_calibration_status ON dl2_calibration_cases(status, created_at);
CREATE INDEX IF NOT EXISTS idx_dl2_context_requester ON dl2_context_packages(requester, status, issued_at);

CREATE TRIGGER IF NOT EXISTS trg_dl2_memory_versions_no_update
BEFORE UPDATE ON dl2_memory_versions BEGIN SELECT RAISE(ABORT, 'DL2 memory versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_dl2_memory_versions_no_delete
BEFORE DELETE ON dl2_memory_versions BEGIN SELECT RAISE(ABORT, 'DL2 memory versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_dl2_hypothesis_versions_no_update
BEFORE UPDATE ON dl2_hypothesis_versions BEGIN SELECT RAISE(ABORT, 'DL2 hypothesis versions are append-only'); END;
CREATE TRIGGER IF NOT EXISTS trg_dl2_hypothesis_versions_no_delete
BEFORE DELETE ON dl2_hypothesis_versions BEGIN SELECT RAISE(ABORT, 'DL2 hypothesis versions are append-only'); END;
"""


def migrate(conn: sqlite3.Connection) -> dict:
    checksum = text_hash(SCHEMA_SQL)
    existing = _one(conn, "SELECT * FROM dl2_schema_migrations WHERE migration_id=?", (MIGRATION_ID,)) if _table_exists(conn, "dl2_schema_migrations") else None
    if existing:
        if existing["checksum"] != checksum:
            raise DL2Error("已应用迁移的校验值发生变化，拒绝静默覆盖")
        return {"migration_id": MIGRATION_ID, "status": "ALREADY_APPLIED", "checksum": checksum}
    conn.executescript(SCHEMA_SQL)
    now = utc_now()
    conn.execute(
        "INSERT INTO dl2_schema_migrations(migration_id,checksum,details_json,applied_at) VALUES(?,?,?,?)",
        (MIGRATION_ID, checksum, canonical_json({"layer": "digital_life_2", "source_tables_modified": []}), now),
    )
    for feature, status, conditions in (
        ("M5_ACTIVITYWATCH", "DISABLED", ["explicit_user_authorization", "registered_research_question", "M0_M4_value_confirmed"]),
        ("M6_READ_ONLY_AGENT", "DISABLED", ["explicit_user_authorization", "at_least_20_calibrations", "real_model_revision", "zero_critical_regression_failures"]),
    ):
        conn.execute(
            "INSERT OR REPLACE INTO dl2_feature_gates(feature_id,status,authorization_required,authorization_receipt,preconditions_json,updated_at) VALUES(?,?,1,NULL,?,?)",
            (feature, status, canonical_json(conditions), now),
        )
    return {"migration_id": MIGRATION_ID, "status": "APPLIED", "checksum": checksum}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(_one(conn, "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)))


def _audit(conn: sqlite3.Connection, operation: str, target_type: str, target_id: str, actor: str, payload: Any, receipt: dict | None = None) -> str:
    audit_id = make_id("dlaudit")
    conn.execute(
        "INSERT INTO dl2_audit_log(audit_id,operation,target_type,target_id,actor,payload_hash,receipt_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (audit_id, operation, target_type, target_id, actor, json_hash(payload), canonical_json(receipt or {}), utc_now()),
    )
    return audit_id


def create_preview(conn: sqlite3.Connection, operation: str, payload: dict, ttl_minutes: int = 30) -> dict:
    preview_id = make_id("dlpreview")
    now_dt = datetime.now(timezone.utc)
    payload_hash = json_hash(payload)
    expires = (now_dt + timedelta(minutes=ttl_minutes)).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO dl2_write_previews(preview_id,operation,payload_json,payload_hash,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
        (preview_id, operation, canonical_json(payload), payload_hash, "READY", now_dt.isoformat(timespec="seconds"), expires),
    )
    return {"preview_id": preview_id, "operation": operation, "payload": payload, "payload_hash": payload_hash, "expires_at": expires, "status": "READY"}


def consume_preview(conn: sqlite3.Connection, preview_id: str, operation: str) -> dict:
    row = _one(conn, "SELECT * FROM dl2_write_previews WHERE preview_id=?", (preview_id,))
    if not row:
        raise DL2Error("预览许可不存在")
    if row["operation"] != operation:
        raise DL2Error("预览许可与确认操作不匹配")
    if row["status"] != "READY":
        raise DL2Error(f"预览许可不可用: {row['status']}")
    if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        conn.execute("UPDATE dl2_write_previews SET status='EXPIRED' WHERE preview_id=?", (preview_id,))
        raise DL2Error("预览许可已过期")
    payload = json.loads(row["payload_json"])
    if json_hash(payload) != row["payload_hash"]:
        raise DL2Error("预览内容校验失败")
    conn.execute("UPDATE dl2_write_previews SET status='CONSUMED',consumed_at=? WHERE preview_id=?", (utc_now(), preview_id))
    return payload


SOURCE_MAP = {
    "qingfeng_log": ("qingfeng_logs", "log_id", "original_text"),
    "event": ("events", "event_id", "raw_json"),
    "fact_assertion": ("fact_assertions", "fact_id", "assertion_text"),
    "psychological_pattern": ("psychological_patterns", "pattern_id", "definition"),
    "source_document": ("source_documents", "document_id", "body"),
    "evidence_item": ("evidence_items", "evidence_id", "body"),
}


def resolve_source(conn: sqlite3.Connection, source_type: str, source_id: str) -> dict:
    spec = SOURCE_MAP.get(source_type)
    if not spec:
        raise DL2Error(f"不支持的来源类型: {source_type}")
    table, id_col, text_col = spec
    row = _one(conn, f"SELECT * FROM {table} WHERE {id_col}=?", (source_id,))
    if not row:
        raise DL2Error(f"来源不存在: {source_type}/{source_id}")
    content = str(row[text_col] or "")
    if not content.strip():
        raise DL2Error(f"来源没有可校验原文: {source_type}/{source_id}")
    return {"source_type": source_type, "source_id": source_id, "content": content, "source_sha256": text_hash(content)}


def normalize_evidence(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    if not items:
        raise DL2Error("没有来源锚点，拒绝升级为活记忆")
    normalized = []
    for raw in items:
        _require(raw, "source_type", "source_id", "source_anchor")
        source = resolve_source(conn, raw["source_type"], raw["source_id"])
        supplied_hash = str(raw.get("source_sha256") or "")
        if supplied_hash and supplied_hash != source["source_sha256"]:
            raise DL2Error(f"来源哈希不匹配: {raw['source_id']}")
        start = raw.get("char_start")
        end = raw.get("char_end")
        if start is not None and (not isinstance(start, int) or start < 0):
            raise DL2Error("char_start 必须是非负整数")
        if end is not None and (not isinstance(end, int) or (start is not None and end < start)):
            raise DL2Error("char_end 无效")
        normalized.append({
            "evidence_role": raw.get("evidence_role") or "SOURCE",
            "source_type": source["source_type"],
            "source_id": source["source_id"],
            "source_sha256": source["source_sha256"],
            "source_anchor": str(raw["source_anchor"]),
            "char_start": start,
            "char_end": end,
            "fact_id": raw.get("fact_id"),
        })
    return normalized


def preview_memory(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "statement", "statement_type", "change_reason")
    evidence = normalize_evidence(conn, list(payload.get("evidence") or []))
    prepared = dict(payload)
    prepared["evidence"] = evidence
    prepared.setdefault("status", "CANDIDATE")
    prepared.setdefault("confidence_state", "LOW")
    prepared.setdefault("ownership_state", "SYSTEM_CANDIDATE")
    prepared.setdefault("sensitivity_level", "S1_PERSONAL")
    prepared.setdefault("access_scope", ["P01"])
    prepared.setdefault("changed_by", "AI")
    return create_preview(conn, "MEMORY_CREATE", prepared)


def confirm_memory(conn: sqlite3.Connection, preview_id: str) -> dict:
    payload = consume_preview(conn, preview_id, "MEMORY_CREATE")
    memory_id = payload.get("memory_id") or make_id("dlmem")
    version_id = make_id("dlmemv")
    now = utc_now()
    conn.execute(
        """INSERT INTO dl2_memory_units(
             memory_id,statement_type,status,current_version_id,event_time,formed_at,valid_from,valid_to,
             confidence_state,ownership_state,sensitivity_level,access_scope_json,created_at,updated_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (memory_id, payload["statement_type"], payload["status"], version_id, payload.get("event_time"), now,
         payload.get("valid_from"), payload.get("valid_to"), payload["confidence_state"], payload["ownership_state"],
         payload["sensitivity_level"], canonical_json(payload["access_scope"]), now, now),
    )
    conn.execute(
        """INSERT INTO dl2_memory_versions(
             version_id,memory_id,previous_version_id,version_no,statement_snapshot,change_type,change_reason,
             trigger_source_json,changed_by,created_at
           ) VALUES(?,?,NULL,1,?,?,?,?,?,?)""",
        (version_id, memory_id, payload["statement"], payload.get("change_type") or "CREATED", payload["change_reason"],
         canonical_json(payload.get("trigger_source") or {}), payload["changed_by"], now),
    )
    _insert_memory_evidence(conn, memory_id, version_id, payload["evidence"])
    receipt = {"memory_id": memory_id, "version_id": version_id, "version_no": 1, "source_count": len(payload["evidence"]), "status": payload["status"]}
    receipt["audit_id"] = _audit(conn, "MEMORY_CREATE", "MEMORY", memory_id, payload["changed_by"], payload, receipt)
    return receipt


def _insert_memory_evidence(conn: sqlite3.Connection, memory_id: str, version_id: str, evidence: list[dict]) -> None:
    now = utc_now()
    for item in evidence:
        conn.execute(
            """INSERT INTO dl2_memory_evidence_links(
                 link_id,memory_id,version_id,evidence_role,source_type,source_id,source_sha256,source_anchor,
                 char_start,char_end,fact_id,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (make_id("dlmele"), memory_id, version_id, item["evidence_role"], item["source_type"], item["source_id"],
             item["source_sha256"], item["source_anchor"], item.get("char_start"), item.get("char_end"), item.get("fact_id"), now),
        )


def preview_memory_revision(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "memory_id", "statement", "change_type", "change_reason")
    if not _one(conn, "SELECT 1 FROM dl2_memory_units WHERE memory_id=?", (payload["memory_id"],)):
        raise DL2Error("记忆不存在")
    prepared = dict(payload)
    prepared["evidence"] = normalize_evidence(conn, list(payload.get("evidence") or []))
    prepared.setdefault("changed_by", "AI")
    return create_preview(conn, "MEMORY_REVISE", prepared)


def confirm_memory_revision(conn: sqlite3.Connection, preview_id: str) -> dict:
    payload = consume_preview(conn, preview_id, "MEMORY_REVISE")
    row = _one(conn, "SELECT * FROM dl2_memory_units WHERE memory_id=?", (payload["memory_id"],))
    previous = row["current_version_id"]
    version_no = int(_one(conn, "SELECT MAX(version_no) n FROM dl2_memory_versions WHERE memory_id=?", (row["memory_id"],))["n"]) + 1
    version_id = make_id("dlmemv")
    now = utc_now()
    conn.execute(
        """INSERT INTO dl2_memory_versions(
             version_id,memory_id,previous_version_id,version_no,statement_snapshot,change_type,change_reason,
             trigger_source_json,changed_by,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (version_id, row["memory_id"], previous, version_no, payload["statement"], payload["change_type"],
         payload["change_reason"], canonical_json(payload.get("trigger_source") or {}), payload["changed_by"], now),
    )
    _insert_memory_evidence(conn, row["memory_id"], version_id, payload["evidence"])
    status = payload.get("status") or ("WITHDRAWN" if payload["change_type"] == "WITHDRAWN" else "REVISED")
    conn.execute(
        "UPDATE dl2_memory_units SET current_version_id=?,status=?,confidence_state=COALESCE(?,confidence_state),updated_at=? WHERE memory_id=?",
        (version_id, status, payload.get("confidence_state"), now, row["memory_id"]),
    )
    receipt = {"memory_id": row["memory_id"], "previous_version_id": previous, "version_id": version_id, "version_no": version_no, "status": status}
    receipt["audit_id"] = _audit(conn, "MEMORY_REVISE", "MEMORY", row["memory_id"], payload["changed_by"], payload, receipt)
    return receipt


def preview_hypothesis(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "claim", "domain", "applicable_period", "applicable_context", "strongest_counterargument")
    support = list(payload.get("supporting_memory_ids") or [])
    counter = list(payload.get("counter_memory_ids") or [])
    if not support or not counter:
        raise DL2Error("模型候选必须同时具有支持记忆和反方/例外记忆")
    for memory_id in [*support, *counter, *list(payload.get("exception_memory_ids") or [])]:
        if not _one(conn, "SELECT 1 FROM dl2_memory_units WHERE memory_id=?", (memory_id,)):
            raise DL2Error(f"模型引用的记忆不存在: {memory_id}")
    prepared = dict(payload)
    prepared.setdefault("status", "SYSTEM_CANDIDATE")
    prepared.setdefault("ownership_state", "SYSTEM_CANDIDATE")
    prepared.setdefault("sensitivity_level", "S1_PERSONAL")
    prepared.setdefault("evidence_sufficiency", "PARTIAL")
    prepared.setdefault("alternative_explanations", [])
    prepared.setdefault("failure_conditions", [])
    prepared.setdefault("changed_by", "AI")
    prepared.setdefault("change_reason", "由现有心理模式改造为可反证的阶段性候选")
    return create_preview(conn, "HYPOTHESIS_CREATE", prepared)


def confirm_hypothesis(conn: sqlite3.Connection, preview_id: str) -> dict:
    payload = consume_preview(conn, preview_id, "HYPOTHESIS_CREATE")
    hypothesis_id = payload.get("hypothesis_id") or make_id("dlhyp")
    version_id = make_id("dlhypv")
    now = utc_now()
    conn.execute(
        """INSERT INTO dl2_model_hypotheses(
             hypothesis_id,source_pattern_id,domain,status,current_version_id,ownership_state,sensitivity_level,created_at,updated_at
           ) VALUES(?,?,?,?,?,?,?,?,?)""",
        (hypothesis_id, payload.get("source_pattern_id"), payload["domain"], payload["status"], version_id,
         payload["ownership_state"], payload["sensitivity_level"], now, now),
    )
    conn.execute(
        """INSERT INTO dl2_hypothesis_versions(
             version_id,hypothesis_id,previous_version_id,version_no,claim,applicable_period,applicable_context,
             strongest_counterargument,alternative_explanations_json,failure_conditions_json,evidence_sufficiency,
             change_reason,changed_by,created_at
           ) VALUES(?,?,NULL,1,?,?,?,?,?,?,?,?,?,?)""",
        (version_id, hypothesis_id, payload["claim"], payload["applicable_period"], payload["applicable_context"],
         payload["strongest_counterargument"], canonical_json(payload["alternative_explanations"]),
         canonical_json(payload["failure_conditions"]), payload["evidence_sufficiency"], payload["change_reason"], payload["changed_by"], now),
    )
    _insert_hypothesis_links(conn, hypothesis_id, version_id, payload)
    receipt = {"hypothesis_id": hypothesis_id, "version_id": version_id, "version_no": 1, "status": payload["status"]}
    receipt["audit_id"] = _audit(conn, "HYPOTHESIS_CREATE", "HYPOTHESIS", hypothesis_id, payload["changed_by"], payload, receipt)
    return receipt


def _insert_hypothesis_links(conn: sqlite3.Connection, hypothesis_id: str, version_id: str, payload: dict) -> None:
    now = utc_now()
    groups = (("SUPPORT", payload.get("supporting_memory_ids") or []), ("COUNTER", payload.get("counter_memory_ids") or []), ("EXCEPTION", payload.get("exception_memory_ids") or []))
    for role, memory_ids in groups:
        for memory_id in memory_ids:
            conn.execute(
                "INSERT INTO dl2_hypothesis_memory_links(link_id,hypothesis_id,hypothesis_version_id,memory_id,relation_role,created_at) VALUES(?,?,?,?,?,?)",
                (make_id("dlhml"), hypothesis_id, version_id, memory_id, role, now),
            )


def preview_hypothesis_revision(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "hypothesis_id", "claim", "applicable_period", "applicable_context", "strongest_counterargument", "change_reason")
    if not _one(conn, "SELECT 1 FROM dl2_model_hypotheses WHERE hypothesis_id=?", (payload["hypothesis_id"],)):
        raise DL2Error("模型候选不存在")
    for key in ("supporting_memory_ids", "counter_memory_ids"):
        if not payload.get(key):
            raise DL2Error("修订仍必须保留支持与反方记忆")
    prepared = dict(payload)
    prepared.setdefault("alternative_explanations", [])
    prepared.setdefault("failure_conditions", [])
    prepared.setdefault("evidence_sufficiency", "PARTIAL")
    prepared.setdefault("changed_by", "AI")
    return create_preview(conn, "HYPOTHESIS_REVISE", prepared)


def confirm_hypothesis_revision(conn: sqlite3.Connection, preview_id: str) -> dict:
    payload = consume_preview(conn, preview_id, "HYPOTHESIS_REVISE")
    row = _one(conn, "SELECT * FROM dl2_model_hypotheses WHERE hypothesis_id=?", (payload["hypothesis_id"],))
    previous = row["current_version_id"]
    version_no = int(_one(conn, "SELECT MAX(version_no) n FROM dl2_hypothesis_versions WHERE hypothesis_id=?", (row["hypothesis_id"],))["n"]) + 1
    version_id = make_id("dlhypv")
    now = utc_now()
    conn.execute(
        """INSERT INTO dl2_hypothesis_versions(
             version_id,hypothesis_id,previous_version_id,version_no,claim,applicable_period,applicable_context,
             strongest_counterargument,alternative_explanations_json,failure_conditions_json,evidence_sufficiency,
             change_reason,changed_by,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (version_id, row["hypothesis_id"], previous, version_no, payload["claim"], payload["applicable_period"],
         payload["applicable_context"], payload["strongest_counterargument"], canonical_json(payload["alternative_explanations"]),
         canonical_json(payload["failure_conditions"]), payload["evidence_sufficiency"], payload["change_reason"], payload["changed_by"], now),
    )
    _insert_hypothesis_links(conn, row["hypothesis_id"], version_id, payload)
    status = payload.get("status") or "REVISED"
    conn.execute("UPDATE dl2_model_hypotheses SET current_version_id=?,status=?,updated_at=? WHERE hypothesis_id=?", (version_id, status, now, row["hypothesis_id"]))
    receipt = {"hypothesis_id": row["hypothesis_id"], "previous_version_id": previous, "version_id": version_id, "version_no": version_no, "status": status}
    receipt["audit_id"] = _audit(conn, "HYPOTHESIS_REVISE", "HYPOTHESIS", row["hypothesis_id"], payload["changed_by"], payload, receipt)
    return receipt


def prepare_calibration(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "question", "question_domain", "system_answer_before_user_answer", "retrieved_context_manifest")
    case_id = payload.get("case_id") or make_id("dlcal")
    now = utc_now()
    answer_hash = text_hash(payload["system_answer_before_user_answer"])
    conn.execute(
        """INSERT INTO dl2_calibration_cases(
             case_id,question,question_domain,system_answer_before_user_answer,system_answer_sha256,
             retrieved_context_manifest_json,comparison_dimensions_json,status,created_at,sealed_at
           ) VALUES(?,?,?,?,?,?,?,'SEALED',?,?)""",
        (case_id, payload["question"], payload["question_domain"], payload["system_answer_before_user_answer"], answer_hash,
         canonical_json(payload["retrieved_context_manifest"]), canonical_json(payload.get("comparison_dimensions") or []), now, now),
    )
    receipt = {"case_id": case_id, "status": "SEALED", "system_answer_sha256": answer_hash, "user_answer_present": False}
    receipt["audit_id"] = _audit(conn, "CALIBRATION_PREPARE", "CALIBRATION", case_id, "AI", payload, receipt)
    return receipt


def answer_calibration(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "case_id", "user_answer_raw")
    row = _one(conn, "SELECT * FROM dl2_calibration_cases WHERE case_id=?", (payload["case_id"],))
    if not row or row["status"] != "SEALED":
        raise DL2Error("校准题不存在或不再等待本人回答")
    if text_hash(row["system_answer_before_user_answer"]) != row["system_answer_sha256"]:
        raise DL2Error("封存的系统回答已变化")
    now = utc_now()
    conn.execute("UPDATE dl2_calibration_cases SET user_answer_raw=?,status='USER_ANSWERED',answered_at=? WHERE case_id=?", (payload["user_answer_raw"], now, payload["case_id"]))
    receipt = {"case_id": payload["case_id"], "status": "USER_ANSWERED", "user_answer_sha256": text_hash(payload["user_answer_raw"])}
    receipt["audit_id"] = _audit(conn, "CALIBRATION_ANSWER", "CALIBRATION", payload["case_id"], "USER", payload, receipt)
    return receipt


def compare_calibration(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "case_id", "difference_summary", "error_class")
    row = _one(conn, "SELECT * FROM dl2_calibration_cases WHERE case_id=?", (payload["case_id"],))
    if not row or row["status"] != "USER_ANSWERED":
        raise DL2Error("必须先收到本人回答才能比较")
    revision = payload.get("revision_decision") or {}
    status = "REVISION_REQUIRED" if revision.get("required") else "COMPLETE"
    now = utc_now()
    conn.execute(
        """UPDATE dl2_calibration_cases SET comparison_dimensions_json=?,difference_summary=?,error_class=?,
             affected_memory_ids_json=?,affected_hypothesis_ids_json=?,revision_decision_json=?,status=?,compared_at=?
           WHERE case_id=?""",
        (canonical_json(payload.get("comparison_dimensions") or []), payload["difference_summary"], payload["error_class"],
         canonical_json(payload.get("affected_memory_ids") or []), canonical_json(payload.get("affected_hypothesis_ids") or []),
         canonical_json(revision), status, now, payload["case_id"]),
    )
    receipt = {"case_id": payload["case_id"], "status": status, "error_class": payload["error_class"], "revision_required": bool(revision.get("required"))}
    receipt["audit_id"] = _audit(conn, "CALIBRATION_COMPARE", "CALIBRATION", payload["case_id"], "AI", payload, receipt)
    return receipt


def _context_item_payload(conn: sqlite3.Connection, item_type: str, item_ref: str) -> dict:
    if item_type == "MEMORY":
        row = _one(conn, """SELECT u.*,v.statement_snapshot,v.version_no FROM dl2_memory_units u JOIN dl2_memory_versions v ON v.version_id=u.current_version_id WHERE u.memory_id=?""", (item_ref,))
    elif item_type == "HYPOTHESIS":
        row = _one(conn, """SELECT h.*,v.claim,v.applicable_period,v.applicable_context,v.strongest_counterargument,v.alternative_explanations_json,v.failure_conditions_json,v.evidence_sufficiency,v.version_no FROM dl2_model_hypotheses h JOIN dl2_hypothesis_versions v ON v.version_id=h.current_version_id WHERE h.hypothesis_id=?""", (item_ref,))
    else:
        raise DL2Error(f"上下文包不支持对象类型: {item_type}")
    if not row:
        raise DL2Error(f"上下文包对象不存在: {item_ref}")
    data = dict(row)
    if data.get("sensitivity_level") in {"S3_RESTRICTED", "S4_WITHHELD"}:
        raise DL2Error(f"对象不允许跨工程包含: {item_ref}")
    return data


def _context_source_manifest(conn: sqlite3.Connection, items: list[dict]) -> list[dict]:
    """从已选记忆/假说反向生成来源清单，不信任请求方手写的 manifest。"""
    manifest: list[dict] = []
    seen: set[tuple] = set()

    def append_memory(memory_id: str, via_hypothesis_id: str = "", relation_role: str = "") -> None:
        memory = _one(conn, "SELECT current_version_id FROM dl2_memory_units WHERE memory_id=?", (memory_id,))
        if not memory:
            raise DL2Error(f"来源清单引用的记忆不存在: {memory_id}")
        rows = conn.execute(
            """SELECT evidence_role,source_type,source_id,source_sha256,source_anchor,char_start,char_end,fact_id
                 FROM dl2_memory_evidence_links WHERE memory_id=? AND version_id=? ORDER BY created_at""",
            (memory_id, memory["current_version_id"]),
        ).fetchall()
        for row in rows:
            key = (
                memory_id, memory["current_version_id"], row["evidence_role"], row["source_type"],
                row["source_id"], row["source_sha256"], row["source_anchor"], via_hypothesis_id, relation_role,
            )
            if key in seen:
                continue
            seen.add(key)
            manifest.append({
                "memory_id": memory_id,
                "memory_version_id": memory["current_version_id"],
                "evidence_role": row["evidence_role"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "source_sha256": row["source_sha256"],
                "source_anchor": row["source_anchor"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "fact_id": row["fact_id"],
                "via_hypothesis_id": via_hypothesis_id or None,
                "hypothesis_relation_role": relation_role or None,
            })

    for item in items:
        if item["item_type"] == "MEMORY":
            append_memory(item["item_ref"])
            continue
        hypothesis_id = item["item_ref"]
        version_id = item["payload"]["current_version_id"]
        links = conn.execute(
            """SELECT memory_id,relation_role FROM dl2_hypothesis_memory_links
                 WHERE hypothesis_id=? AND hypothesis_version_id=? ORDER BY created_at""",
            (hypothesis_id, version_id),
        ).fetchall()
        for link in links:
            append_memory(link["memory_id"], hypothesis_id, link["relation_role"])
    if not manifest:
        raise DL2Error("上下文包无法生成真实来源清单")
    return manifest


def _verify_context_artifact(package: sqlite3.Row) -> dict:
    path = Path(str(package["artifact_path"] or ""))
    try:
        path.resolve().relative_to(CONTEXT_OUTBOX.resolve())
    except (OSError, ValueError):
        raise DL2Error("上下文包产物路径越界")
    if not path.is_file():
        raise DL2Error("上下文包产物不存在")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DL2Error(f"上下文包产物无法校验: {exc}") from exc
    embedded_hash = str(artifact.pop("package_hash", ""))
    calculated_hash = json_hash(artifact)
    if embedded_hash != package["package_hash"] or calculated_hash != package["package_hash"]:
        raise DL2Error("上下文包产物哈希校验失败")
    artifact["package_hash"] = embedded_hash
    return artifact


def preview_context_package(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "requester", "purpose", "question", "authorization_id", "allowed_domains", "items")
    requester = str(payload["requester"]).upper()
    authorization_id = str(payload["authorization_id"])
    if requester == "P05" and not (authorization_id.startswith("P05-AUTH-") or authorization_id.startswith("USER-EXPLICIT-")):
        raise DL2Error("P05普通入口默认禁读，缺少明确授权")
    if requester == "LWG" and authorization_id != "P05-AUTH-LWG-DL-20260720":
        raise DL2Error("人生漫游馆必须使用已登记的持续只读授权")
    if requester not in {"P05", "LWG"}:
        raise DL2Error("首批只允许 P05 和 LWG 请求上下文包")
    resolved_items = []
    for raw in list(payload["items"]):
        _require(raw, "item_type", "item_ref", "item_role")
        if raw["item_role"] not in {"SUPPORT", "COUNTER", "CONTEXT", "BOUNDARY"}:
            raise DL2Error(f"上下文包 item_role 无效: {raw['item_role']}")
        item_payload = _context_item_payload(conn, raw["item_type"], raw["item_ref"])
        resolved_items.append({"item_type": raw["item_type"], "item_ref": raw["item_ref"], "item_role": raw["item_role"], "payload": item_payload})
    prepared = dict(payload)
    prepared["requester"] = requester
    prepared["items"] = resolved_items
    prepared.setdefault("excluded_domains", [])
    prepared["source_manifest"] = _context_source_manifest(conn, resolved_items)
    prepared.setdefault("uncertainties", [])
    prepared.setdefault("expires_at", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(timespec="seconds"))
    prepared.setdefault("revocable", True)
    return create_preview(conn, "CONTEXT_ISSUE", prepared)


def issue_context_package(conn: sqlite3.Connection, preview_id: str) -> dict:
    payload = consume_preview(conn, preview_id, "CONTEXT_ISSUE")
    package_id = payload.get("package_id") or make_id("dlctx")
    now = utc_now()
    export = {
        "package_id": package_id,
        "requester": payload["requester"],
        "purpose": payload["purpose"],
        "question": payload["question"],
        "authorization_id": payload["authorization_id"],
        "allowed_domains": payload["allowed_domains"],
        "excluded_domains": payload["excluded_domains"],
        "memory_items": [item["payload"] for item in payload["items"] if item["item_type"] == "MEMORY"],
        "hypothesis_items": [item["payload"] for item in payload["items"] if item["item_type"] == "HYPOTHESIS"],
        "source_manifest": payload["source_manifest"],
        "uncertainties": payload["uncertainties"],
        "expires_at": payload["expires_at"],
        "revocable": bool(payload["revocable"]),
    }
    package_hash = json_hash(export)
    export["package_hash"] = package_hash
    CONTEXT_OUTBOX.mkdir(parents=True, exist_ok=True)
    artifact_path = CONTEXT_OUTBOX / f"{package_id.replace(':', '-')}.json"
    artifact_path.write_text(json.dumps(export, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    conn.execute(
        """INSERT INTO dl2_context_packages(
             package_id,requester,purpose,question,authorization_id,allowed_domains_json,excluded_domains_json,
             source_manifest_json,uncertainties_json,expires_at,revocable,package_hash,status,artifact_path,created_at,issued_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (package_id, payload["requester"], payload["purpose"], payload["question"], payload["authorization_id"],
         canonical_json(payload["allowed_domains"]), canonical_json(payload["excluded_domains"]),
         canonical_json(payload["source_manifest"]), canonical_json(payload["uncertainties"]), payload["expires_at"],
         1 if payload["revocable"] else 0, package_hash, "DELIVERED_NOT_ADOPTED", str(artifact_path), now, now),
    )
    for item in payload["items"]:
        conn.execute(
            """INSERT INTO dl2_context_package_items(
                 item_id,package_id,item_type,item_ref,item_role,payload_json,payload_hash,created_at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (make_id("dlctxi"), package_id, item["item_type"], item["item_ref"], item["item_role"],
             canonical_json(item["payload"]), json_hash(item["payload"]), now),
        )
    receipt = {"package_id": package_id, "status": "DELIVERED_NOT_ADOPTED", "package_hash": package_hash, "artifact_path": str(artifact_path), "item_count": len(payload["items"])}
    receipt["audit_id"] = _audit(conn, "CONTEXT_ISSUE", "CONTEXT_PACKAGE", package_id, "AI", payload, receipt)
    return receipt


def register_access_receipt(conn: sqlite3.Connection, payload: dict) -> dict:
    _require(payload, "package_id", "package_hash", "receiver", "decision", "receipt_ref")
    package = _one(conn, "SELECT * FROM dl2_context_packages WHERE package_id=?", (payload["package_id"],))
    if not package:
        raise DL2Error("上下文包不存在")
    if str(payload["receiver"]).upper() != package["requester"]:
        raise DL2Error("回执接收方与上下文包请求方不一致")
    if str(payload["package_hash"]) != package["package_hash"]:
        raise DL2Error("回执引用的上下文包哈希不匹配")
    if payload["decision"] not in {"ACCEPTED", "REJECTED", "HELD", "REVOKED"}:
        raise DL2Error("回执 decision 无效")
    if datetime.fromisoformat(package["expires_at"]) < datetime.now(timezone.utc):
        conn.execute("UPDATE dl2_context_packages SET status='EXPIRED' WHERE package_id=?", (payload["package_id"],))
        raise DL2Error("上下文包已过期，拒绝接收回执")
    _verify_context_artifact(package)
    allowed_refs = {row["item_ref"] for row in conn.execute("SELECT item_ref FROM dl2_context_package_items WHERE package_id=?", (payload["package_id"],)).fetchall()}
    actual_read = list(payload.get("actual_read") or [])
    refused = list(payload.get("refused") or [])
    unknown_refs = (set(actual_read) | set(refused)) - allowed_refs
    if unknown_refs:
        raise DL2Error(f"回执引用了包外对象: {', '.join(sorted(unknown_refs))}")
    if payload["decision"] == "ACCEPTED" and not actual_read:
        raise DL2Error("ACCEPTED 回执必须列出 actual_read")
    receipt_body = {
        "package_id": payload["package_id"], "package_hash": package["package_hash"],
        "receiver": str(payload["receiver"]).upper(), "decision": payload["decision"],
        "actual_read": actual_read, "refused": refused,
        "returned": payload.get("returned") or {}, "target_writeback": bool(payload.get("target_writeback")), "receipt_ref": payload["receipt_ref"],
    }
    receipt_hash = json_hash(receipt_body)
    existing = _one(conn, "SELECT * FROM dl2_access_receipts WHERE package_id=? AND receiver=? AND receipt_hash=?", (payload["package_id"], receipt_body["receiver"], receipt_hash))
    if existing:
        return {"receipt_id": existing["receipt_id"], "package_id": payload["package_id"], "status": "IDEMPOTENT", "receipt_hash": receipt_hash}
    receipt_id = make_id("dlreceipt")
    now = utc_now()
    conn.execute(
        """INSERT INTO dl2_access_receipts(
             receipt_id,package_id,receiver,decision,actual_read_json,refused_json,returned_json,target_writeback,
             receipt_ref,receipt_hash,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (receipt_id, payload["package_id"], receipt_body["receiver"], payload["decision"], canonical_json(receipt_body["actual_read"]),
         canonical_json(receipt_body["refused"]), canonical_json(receipt_body["returned"]), 1 if receipt_body["target_writeback"] else 0,
         payload["receipt_ref"], receipt_hash, now),
    )
    new_status = {"ACCEPTED": "ACCEPTED", "REJECTED": "REJECTED", "REVOKED": "REVOKED", "HELD": "DELIVERED_NOT_ADOPTED"}[payload["decision"]]
    conn.execute("UPDATE dl2_context_packages SET status=? WHERE package_id=?", (new_status, payload["package_id"]))
    receipt = {"receipt_id": receipt_id, "package_id": payload["package_id"], "status": new_status, "receipt_hash": receipt_hash}
    receipt["audit_id"] = _audit(conn, "CONTEXT_RECEIPT", "CONTEXT_PACKAGE", payload["package_id"], receipt_body["receiver"], receipt_body, receipt)
    return receipt


def _decode_row(row: sqlite3.Row | dict) -> dict:
    item = dict(row)
    for key in list(item):
        if key.endswith("_json"):
            item[key[:-5]] = _json(item.pop(key), [] if key.endswith("ids_json") or key in {"access_scope_json", "alternative_explanations_json", "failure_conditions_json", "allowed_domains_json", "excluded_domains_json", "source_manifest_json", "uncertainties_json", "actual_read_json", "refused_json", "preconditions_json", "comparison_dimensions_json"} else {})
    return item


def list_memories(conn: sqlite3.Connection, limit: int = 100, status: str = "") -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("u.status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT u.*,v.statement_snapshot,v.version_no,v.change_type,v.change_reason,
                   (SELECT COUNT(*) FROM dl2_memory_evidence_links e WHERE e.memory_id=u.memory_id) evidence_count
            FROM dl2_memory_units u JOIN dl2_memory_versions v ON v.version_id=u.current_version_id
            {where} ORDER BY u.updated_at DESC LIMIT ?""", (*params, min(max(int(limit), 1), 500))).fetchall()
    return [_decode_row(row) for row in rows]


def memory_detail(conn: sqlite3.Connection, memory_id: str) -> dict:
    unit = _one(conn, "SELECT * FROM dl2_memory_units WHERE memory_id=?", (memory_id,))
    if not unit:
        raise DL2Error("记忆不存在")
    versions = [_decode_row(row) for row in conn.execute("SELECT * FROM dl2_memory_versions WHERE memory_id=? ORDER BY version_no", (memory_id,)).fetchall()]
    evidence = [_decode_row(row) for row in conn.execute("SELECT * FROM dl2_memory_evidence_links WHERE memory_id=? ORDER BY created_at", (memory_id,)).fetchall()]
    return {"unit": _decode_row(unit), "versions": versions, "evidence": evidence}


def list_hypotheses(conn: sqlite3.Connection, limit: int = 100, status: str = "") -> list[dict]:
    clauses, params = [], []
    if status:
        clauses.append("h.status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT h.*,v.claim,v.applicable_period,v.applicable_context,v.strongest_counterargument,
                   v.alternative_explanations_json,v.failure_conditions_json,v.evidence_sufficiency,v.version_no
            FROM dl2_model_hypotheses h JOIN dl2_hypothesis_versions v ON v.version_id=h.current_version_id
            {where} ORDER BY h.updated_at DESC LIMIT ?""", (*params, min(max(int(limit), 1), 500))).fetchall()
    return [_decode_row(row) for row in rows]


def hypothesis_detail(conn: sqlite3.Connection, hypothesis_id: str) -> dict:
    item = _one(conn, "SELECT * FROM dl2_model_hypotheses WHERE hypothesis_id=?", (hypothesis_id,))
    if not item:
        raise DL2Error("模型候选不存在")
    versions = [_decode_row(row) for row in conn.execute("SELECT * FROM dl2_hypothesis_versions WHERE hypothesis_id=? ORDER BY version_no", (hypothesis_id,)).fetchall()]
    links = [_decode_row(row) for row in conn.execute("SELECT * FROM dl2_hypothesis_memory_links WHERE hypothesis_id=? ORDER BY created_at", (hypothesis_id,)).fetchall()]
    return {"hypothesis": _decode_row(item), "versions": versions, "memory_links": links}


def calibration_detail(conn: sqlite3.Connection, case_id: str) -> dict:
    row = _one(conn, "SELECT * FROM dl2_calibration_cases WHERE case_id=?", (case_id,))
    if not row:
        raise DL2Error("校准案例不存在")
    return _decode_row(row)


def list_calibrations(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM dl2_calibration_cases ORDER BY created_at DESC LIMIT ?",
        (min(max(int(limit), 1), 500),),
    ).fetchall()
    return [_decode_row(row) for row in rows]


def context_package_detail(conn: sqlite3.Connection, package_id: str) -> dict:
    row = _one(conn, "SELECT * FROM dl2_context_packages WHERE package_id=?", (package_id,))
    if not row:
        raise DL2Error("上下文包不存在")
    items = [_decode_row(item) for item in conn.execute("SELECT * FROM dl2_context_package_items WHERE package_id=? ORDER BY created_at", (package_id,)).fetchall()]
    receipts = [_decode_row(item) for item in conn.execute("SELECT * FROM dl2_access_receipts WHERE package_id=? ORDER BY created_at", (package_id,)).fetchall()]
    return {"package": _decode_row(row), "items": items, "receipts": receipts}


def list_context_packages(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM dl2_context_packages ORDER BY created_at DESC LIMIT ?",
        (min(max(int(limit), 1), 500),),
    ).fetchall()
    return [_decode_row(row) for row in rows]


def status_payload(conn: sqlite3.Connection) -> dict:
    if not _table_exists(conn, "dl2_schema_migrations"):
        return {"installed": False, "stage": "M0"}
    counts = {}
    for key, table in (
        ("memories", "dl2_memory_units"), ("memory_versions", "dl2_memory_versions"),
        ("hypotheses", "dl2_model_hypotheses"), ("hypothesis_versions", "dl2_hypothesis_versions"),
        ("calibrations", "dl2_calibration_cases"), ("context_packages", "dl2_context_packages"),
        ("access_receipts", "dl2_access_receipts"),
    ):
        counts[key] = int(_one(conn, f"SELECT COUNT(*) n FROM {table}")["n"])
    counts["memory_revision_chains"] = int(_one(conn, "SELECT COUNT(*) n FROM (SELECT memory_id FROM dl2_memory_versions GROUP BY memory_id HAVING COUNT(*)>=2)")["n"])
    counts["hypothesis_revision_chains"] = int(_one(conn, "SELECT COUNT(*) n FROM (SELECT hypothesis_id FROM dl2_hypothesis_versions GROUP BY hypothesis_id HAVING COUNT(*)>=2)")["n"])
    counts["completed_calibrations"] = int(_one(conn, "SELECT COUNT(*) n FROM dl2_calibration_cases WHERE status IN ('COMPLETE','REVISION_REQUIRED')")["n"])
    gates = [_decode_row(row) for row in conn.execute("SELECT * FROM dl2_feature_gates ORDER BY feature_id").fetchall()]
    return {
        "installed": True,
        "version": "2.0.0",
        "counts": counts,
        "milestones": {
            "M1": "PASS" if counts["memories"] >= 20 and counts["memory_revision_chains"] >= 5 else "IN_PROGRESS",
            "M2": "PASS" if counts["hypotheses"] >= 10 and counts["hypothesis_revision_chains"] >= 2 else "IN_PROGRESS",
            "M3": "PASS" if counts["completed_calibrations"] >= 20 else "WAITING_REAL_USER_CALIBRATION",
            "M4": "PASS" if counts["access_receipts"] >= 2 else "WAITING_REAL_RECEIVER_REQUESTS",
            "M5": "DISABLED",
            "M6": "DISABLED",
        },
        "feature_gates": gates,
        "database": db_runtime.path_summary(),
    }
