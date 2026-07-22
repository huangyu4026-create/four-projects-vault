#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_P05_ROOT = Path(
    "/Users/yu/Documents/Codex/coex项目总库/10-19_项目工程域/15_P05_个人生命立场系统_LPS"
)
DEFAULT_LWG_ROOT = Path(
    "/Users/yu/Documents/Codex/coex项目总库/20-29_工具域/23_T03_人生漫游馆_LWG"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence(path: Path, root: Path) -> dict:
    if not path.is_file():
        return {"path": str(path), "exists": False, "sha256": None}
    return {
        "path": str(path.relative_to(root)),
        "exists": True,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="审计数字生命2.0协议建立前的真实跨工程调用，不倒签为M4闭环"
    )
    parser.add_argument("--p05-root", type=Path, default=DEFAULT_P05_ROOT)
    parser.add_argument("--lwg-root", type=Path, default=DEFAULT_LWG_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    p05_files = [
        args.p05_root / "runtime/runs/real_004_request.json",
        args.p05_root / "runtime/runs/real_004_packet.json",
        args.p05_root / "runtime/runs/real_004_validated.json",
        args.p05_root / "runtime/runs/real_004_evidence_audit_validated.json",
        args.p05_root / "06_材料库/02_加工中/个人经验/REAL-004_童年第一二阶段_数字生命只读证据摘录.md",
    ]
    lwg_files = [
        args.lwg_root / "10_输入与会话/已批准待分发/LWG-C-20260720-1cdb7f2a.md",
        args.lwg_root / "runtime/config.json",
        args.lwg_root / "00_域门/PROJECT_STATE.json",
        args.lwg_root / "20_规则与流程/09_数字生命2.0最小上下文包接收契约_v1.json",
    ]

    missing = [str(path) for path in p05_files + lwg_files if not path.is_file()]
    report = {
        "report_id": "DL2-PRE-PROTOCOL-CROSS-PROJECT-AUDIT-20260722",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit_scope": "P05 REAL-004 and its LWG downstream use",
        "classification": "REAL_PRE_DL2_NOT_COUNTED",
        "m4_acceptance_credit": False,
        "reason": [
            "调用与下游使用真实存在，且保留了来源和授权边界。",
            "该调用发生在数字生命2.0上下文包协议正式建立之前。",
            "不存在由P01签发的dlctx包、package_hash与dl2_access_receipts回执。",
            "因此不得倒签、重命名或补造回执以凑足M4验收。",
        ],
        "canonical_authorization_id": "P05-AUTH-LWG-DL-20260720",
        "authorization_alignment": {
            "status": "ALIGNED_20260722",
            "scope_changed": False,
            "note": "仅将LWG运行配置中的旧别名对齐到P05授权总表与既有REAL-004使用的正式编号。",
        },
        "p05_evidence": [evidence(path, args.p05_root) for path in p05_files],
        "lwg_evidence": [evidence(path, args.lwg_root) for path in lwg_files],
        "missing_evidence": missing,
        "next_valid_closure": {
            "required_receiver_requests": ["P05", "LWG"],
            "required_chain": [
                "receiver_request",
                "P01_authorization_review",
                "P01_minimal_context_package",
                "package_hash_verification",
                "receiver_independent_judgment",
                "receiver_receipt",
                "P01_receipt_registration",
            ],
            "without_receipt_status": "DELIVERED_NOT_ADOPTED",
        },
        "audit_pass": not missing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["audit_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
