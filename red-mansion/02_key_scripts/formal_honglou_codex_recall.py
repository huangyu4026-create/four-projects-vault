#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import re
import time
import threading
from datetime import datetime
from pathlib import Path
import formal_honglou_closed_loop as closed_loop
import formal_honglou_question_decomposer as decomposer
import formal_honglou_reading_triangle as reading_triangle


ROOT = Path(__file__).resolve().parents[1]
CODEX_ANSWER_ROOT = ROOT / "outputs" / "红楼梦Codex最终答案"
CODEX_PENDING_DIR = CODEX_ANSWER_ROOT / "待回答"
CODEX_FINAL_DIR = CODEX_ANSWER_ROOT / "最终答案"
CODEX_QUEUE_JSON = CODEX_ANSWER_ROOT / "Codex召回队列.json"
CODEX_QUEUE_MD = CODEX_ANSWER_ROOT / "Codex召回队列.md"
FINAL_ANSWER_FILE_LABEL = "红楼梦工程最终回显稿"
FINAL_DISPLAY_WAIT_STATUS = "待最终回显稿"
REQUEST_LOCK_STATUSES = {
    "待Codex处理",
    "待处理",
    "处理中",
    "待最终回显稿",
    "等待补证",
    "待人工复核",
}
CODEX_RUN_DIR = CODEX_ANSWER_ROOT / "Codex运行记录"
CODEX_ABORT_DIR = CODEX_ANSWER_ROOT / "已终止请求"
CODEX_QUEUE_CLEANUP_DIR = CODEX_ANSWER_ROOT / "队列清理归档"
CODEX_RUNTIME_HOME = CODEX_ANSWER_ROOT / "codex_runtime_home"
CODEX_EXEC_TIMEOUT = 720
CODEX_QUERY_TIMEOUT = 240
CODEX_MATERIAL_TIMEOUT = 480
CODEX_PROCESS_TIMEOUT = 480
CODEX_CLOSE_READING_TIMEOUT = 480
CODEX_ORIGINAL_REREAD_TIMEOUT = 900
CODEX_DEEP_INSIGHT_TIMEOUT = 720
CODEX_EXEC_RETRY_HINTS = (
    "Reading additional input from stdin",
    "reading additional input from stdin",
    "input from stdin",
    "additional input from stdin",
)
CODEX_EXEC_RETRY_MARKERS = (
    "stream disconnected",
    "reconnecting",
    "error sending request",
    "failed to send request",
    "connection",
)
MAX_SUPPLEMENT_PASSES = 1
PROCESSING_STALE_SECONDS = 900
try:
    PROCESSING_AUTO_CLEAR_SECONDS = max(
        60,
        int(os.environ.get("CODEX_AUTO_CLEAR_STALE_SECONDS", str(PROCESSING_STALE_SECONDS)).strip()),
    )
except ValueError:
    PROCESSING_AUTO_CLEAR_SECONDS = PROCESSING_STALE_SECONDS
PROCESSING_ABANDON_SECONDS = 21600
PROCESS_RETRY_MAX_ATTEMPTS = 2
PROCESS_FINAL_RETRY_BUDGET = 4
PROCESS_RETRY_INTERVAL_SECONDS = 90
PROCESS_HEARTBEAT_INTERVAL_SECONDS = 60
PROCESS_HEARTBEAT_DISABLE_VALUES = {"0", "false", "off", "no", "n", "关闭", "关"}
PROCESS_HEARTBEAT_OFF_MODES = {"off", "none", "disabled", "关闭", "关"}
PROCESS_HEARTBEAT_PRODUCTION_MODES = {"production", "prod", "formal", "正式", "quiet"}
PROCESS_HEARTBEAT_INTERVAL_BY_MODE = {
    "debug": 60,
    "observe": 60,
    "观察": 60,
    "production": 180,
    "prod": 180,
    "formal": 180,
    "正式": 180,
    "quiet": 300,
}
PROCESS_HEARTBEAT_NOTE = "OBSERVABILITY_SCAFFOLD｜运行时心跳是可撤销的观察脚手架，不参与答案生成；默认观察期启用。正式稳定后可用 CODEX_RUN_MODE=production 降频，或 CODEX_PROCESS_HEARTBEAT=0 关闭。"
SUSPICIOUS_CLI_HINTS = ("/tmp/codex_fake_bin",)
CODEX_CANDIDATES = (
    Path.home() / ".local" / "bin" / "codex",
    Path("/Applications/Codex.app/Contents/Resources/codex"),
    Path("/opt/homebrew/bin/codex"),
    Path("/usr/local/bin/codex"),
)


def clean_text(value: object) -> str:
    return str(value or "").strip()


def safe_filename_part(value: str, max_len: int = 72) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_一二三四五六七八九十百千万回章卷集册上下前后中天地人物情理心梦" else "_" for ch in value)
    safe = "_".join(part for part in safe.split("_") if part)
    return (safe or "未命名")[:max_len]



def read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass



def _run_mode() -> str:
    return os.environ.get("CODEX_RUN_MODE", "observe").strip().lower() or "observe"


def _heartbeat_interval_seconds() -> int:
    explicit = os.environ.get("CODEX_PROCESS_HEARTBEAT_INTERVAL", "").strip()
    if explicit:
        try:
            return max(30, int(explicit))
        except ValueError:
            pass
    return PROCESS_HEARTBEAT_INTERVAL_BY_MODE.get(_run_mode(), PROCESS_HEARTBEAT_INTERVAL_SECONDS)


def _heartbeat_enabled() -> bool:
    explicit = os.environ.get("CODEX_PROCESS_HEARTBEAT")
    if explicit is not None:
        return explicit.strip().lower() not in PROCESS_HEARTBEAT_DISABLE_VALUES
    return _run_mode() not in PROCESS_HEARTBEAT_OFF_MODES


def _heartbeat_queue_update_enabled() -> bool:
    explicit = os.environ.get("CODEX_PROCESS_HEARTBEAT_QUEUE")
    if explicit is not None:
        return explicit.strip().lower() not in PROCESS_HEARTBEAT_DISABLE_VALUES
    return _run_mode() not in PROCESS_HEARTBEAT_PRODUCTION_MODES and _run_mode() not in PROCESS_HEARTBEAT_OFF_MODES


def _append_heartbeat_line(path: Path, line: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _emit_heartbeat_note(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size > 0:
            return
    except OSError:
        pass
    _append_heartbeat_line(path, f"[{datetime.now().isoformat(timespec='seconds')}] {PROCESS_HEARTBEAT_NOTE}")


def _start_cli_heartbeat(label: str, timeout: int = 0) -> threading.Event:
    stop = threading.Event()
    if not _heartbeat_enabled():
        return stop
    label = clean_text(label) or "Codex 子进程"
    started = time.monotonic()
    heartbeat_path = CODEX_RUN_DIR / "process_heartbeat.log"
    _emit_heartbeat_note(heartbeat_path)

    def worker() -> None:
        while not stop.wait(_heartbeat_interval_seconds()):
            elapsed = int(time.monotonic() - started)
            timeout_note = f"，超时上限 {timeout} 秒" if timeout else ""
            line = f"[{datetime.now().isoformat(timespec='seconds')}] {label} 仍在运行，已运行 {elapsed} 秒{timeout_note}。"
            print(f"[Codex心跳] {line}", flush=True)
            _append_heartbeat_line(heartbeat_path, line)

    threading.Thread(target=worker, daemon=True).start()
    return stop


def _emit_process_heartbeat(item: dict, phase: str, message: str = "") -> None:
    if not _heartbeat_enabled():
        return
    request_id = clean_text(item.get("request_id")) or "unknown_request"
    now = datetime.now().isoformat(timespec="seconds")
    phase = clean_text(phase) or "处理中"
    message = clean_text(message)
    line = f"[{now}] {request_id}｜{phase}" + (f"｜{message}" if message else "")
    log_path = CODEX_RUN_DIR / f"{request_id}_process_heartbeat.log"
    _emit_heartbeat_note(log_path)
    print(f"[Codex心跳] {line}", flush=True)
    _append_heartbeat_line(log_path, line)
    if not _heartbeat_queue_update_enabled():
        return
    try:
        upsert_item(
            {
                **item,
                "status": "处理中",
                "heartbeat_phase": phase,
                "heartbeat_message": message,
                "heartbeat_at": now,
                "heartbeat_note": PROCESS_HEARTBEAT_NOTE,
            }
        )
    except Exception:
        pass


def mark_request_aborted(request_id: str, reason: str = "") -> Path:
    request_id = clean_text(request_id)
    if not request_id:
        raise ValueError("缺少 request_id，不能停止解语。")
    CODEX_ABORT_DIR.mkdir(parents=True, exist_ok=True)
    marker = CODEX_ABORT_DIR / f"{request_id}.json"
    write_json(
        marker,
        {
            "request_id": request_id,
            "aborted_at": datetime.now().isoformat(timespec="seconds"),
            "reason": clean_text(reason) or "用户点击停止解语。",
        },
    )
    return marker


def is_request_aborted(request_id: str) -> bool:
    request_id = clean_text(request_id)
    return bool(request_id and (CODEX_ABORT_DIR / f"{request_id}.json").exists())


def current_question_record() -> dict:
    latest = read_json(CODEX_ANSWER_ROOT / "latest_question.json", {})
    return latest if isinstance(latest, dict) else {}


def current_request_id() -> str:
    return clean_text(current_question_record().get("request_id"))


def _is_request_lock_stale(item: dict, timeout_seconds: int = PROCESSING_AUTO_CLEAR_SECONDS) -> bool:
    if not isinstance(item, dict):
        return False
    status = clean_text(item.get("status"))
    if status not in REQUEST_LOCK_STATUSES:
        return False
    if status == "处理中":
        return is_stale_processing_item(item, max_age_seconds=timeout_seconds)
    marker = parse_iso_datetime(item.get("processing_started_at")) or parse_iso_datetime(item.get("updated_at"))
    if not marker:
        return False
    return (datetime.now() - marker).total_seconds() > timeout_seconds


def auto_recover_stale_request_lock(timeout_seconds: int = PROCESSING_AUTO_CLEAR_SECONDS, reason: str = "") -> dict:
    reason = clean_text(reason) or f"请求 {datetime.now().isoformat(timespec='seconds')} 后检测到死线程，自动清空。"
    request_id = current_request_id()
    if not request_id:
        return {
            "ok": True,
            "released": False,
            "request_id": "",
            "status": "no_active_thread",
            "reason": "当前无 active 锁可清空。",
            "queue_json": str(CODEX_QUEUE_JSON),
            "queue_md": str(CODEX_QUEUE_MD),
        }
    raw = read_json(CODEX_QUEUE_JSON, {"items": []})
    items = raw.get("items", []) if isinstance(raw, dict) else []
    target_item = next(
        (dict(item) for item in items if isinstance(item, dict) and clean_text(item.get("request_id")) == request_id),
        {},
    )
    if not target_item:
        (CODEX_ANSWER_ROOT / "latest_question.json").write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "released": False,
            "request_id": request_id,
            "status": "latest_orphaned",
            "reason": "latest_question 锁无队列记录，已清理孤立锁。",
            "queue_json": str(CODEX_QUEUE_JSON),
            "queue_md": str(CODEX_QUEUE_MD),
            "latest_request_cleared": True,
        }
    if not _is_request_lock_stale(target_item, timeout_seconds=timeout_seconds):
        return {
            "ok": True,
            "released": False,
            "request_id": request_id,
            "status": clean_text(target_item.get("status")),
            "reason": "active 锁未超过清空阈值。",
            "queue_json": str(CODEX_QUEUE_JSON),
            "queue_md": str(CODEX_QUEUE_MD),
        }
    reason = (
        f"{reason}，当前状态={clean_text(target_item.get('status'))}，重入点={clean_text(target_item.get('question'))[:80]}"
    )
    return clear_request_lock(request_id=request_id, reason=reason, auto_requeue=True)


def clear_request_lock(request_id: str = "", reason: str = "", auto_requeue: bool = False) -> dict:
    reason = clean_text(reason) or "用户手动清空旧线程。"
    request_id = clean_text(request_id)
    raw = read_json(CODEX_QUEUE_JSON, {"items": []})
    items = raw.get("items", []) if isinstance(raw, dict) else []
    candidates = [
        dict(item)
        for item in items
        if isinstance(item, dict) and clean_text(item.get("request_id"))
    ]
    candidates.sort(key=lambda item: clean_text(item.get("updated_at")), reverse=True)
    latest_request_id = current_request_id()
    target_request_id = request_id or latest_request_id
    target_item = {}

    if target_request_id:
        target_item = next(
            (item for item in candidates if clean_text(item.get("request_id")) == target_request_id),
            {},
        )

    if not target_item and target_request_id:
        raise SystemExit(f"未找到请求 {target_request_id}，无法清空线程。")

    if not target_item and not target_request_id:
        target_item = next(
            (
                item
                for item in candidates
                if clean_text(item.get("status")) in REQUEST_LOCK_STATUSES
            ),
            {},
        )
        target_request_id = clean_text(target_item.get("request_id"))

    latest_question_path = CODEX_ANSWER_ROOT / "latest_question.json"
    if not target_request_id:
        if latest_request_id:
            latest_question_path.write_text("{}", encoding="utf-8")
            return {
                "ok": True,
                "released": False,
                "request_id": latest_request_id,
                "status": "latest_cleared",
                "reason": "已清空 latest_question 锁；当前队列无活跃线程。",
                "queue_json": str(CODEX_QUEUE_JSON),
                "queue_md": str(CODEX_QUEUE_MD),
            }
        return {
            "ok": True,
            "released": False,
            "request_id": "",
            "status": "no_active_thread",
            "reason": "当前无可清理线程。",
            "queue_json": str(CODEX_QUEUE_JSON),
            "queue_md": str(CODEX_QUEUE_MD),
        }

    latest_question_path.write_text("{}", encoding="utf-8")
    existing_status = clean_text(target_item.get("status"))
    if existing_status in REQUEST_LOCK_STATUSES:
        release_status = "待Codex处理" if auto_requeue else "已终止"
        retry_count = _int_value(target_item.get("retry_count"), 0) + (1 if auto_requeue else 0)
        updated = upsert_item(
            {
                "request_id": target_request_id,
                "question": clean_text(target_item.get("question")),
                "question_key": clean_text(target_item.get("question_key")),
                "task_intent": clean_text(target_item.get("task_intent")),
                "requirements": clean_text(target_item.get("requirements")),
                "status": release_status,
                "recall_phrase": clean_text(target_item.get("recall_phrase"))
                    or f"处理红楼梦待回答 {target_request_id}",
                "pending_md": clean_text(target_item.get("pending_md")),
                "answer_md": "",
                "error": reason,
                "error_category": "runtime" if auto_requeue else "manual_release",
                "error_stage": "thread_auto_recover" if auto_requeue else "request_clear",
                "error_snippet": "",
                "return_code": "",
                "error_retryable": auto_requeue,
                "retry_count": retry_count,
                "processing_started_at": "",
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return {
            "ok": True,
            "released": True,
            "request_id": target_request_id,
            "status": clean_text(updated.get("status")),
            "previous_status": existing_status,
            "reason": reason,
            "queue_json": str(CODEX_QUEUE_JSON),
            "queue_md": str(CODEX_QUEUE_MD),
            "updated_at": clean_text(updated.get("updated_at")),
            "latest_request_cleared": True,
        }

    latest_question_path.write_text("{}", encoding="utf-8")
    return {
        "ok": True,
        "released": False,
        "request_id": target_request_id,
        "status": existing_status,
        "reason": f"线程已存在但非锁定状态：{existing_status or '未知'}，未改写状态；已清空 latest_question。",
        "queue_json": str(CODEX_QUEUE_JSON),
        "queue_md": str(CODEX_QUEUE_MD),
        "latest_request_cleared": True,
    }


def single_queue_items(items: list[dict], preferred_request_id: str = "") -> list[dict]:
    preferred_request_id = clean_text(preferred_request_id) or current_request_id()
    clean_items = [dict(item) for item in items if isinstance(item, dict) and clean_text(item.get("request_id"))]
    if preferred_request_id:
        for item in clean_items:
            if clean_text(item.get("request_id")) == preferred_request_id:
                return [item]
        return []
    clean_items.sort(key=lambda item: clean_text(item.get("updated_at")), reverse=True)
    return clean_items[:1]


def archive_old_queue_items(items: list[dict], keep_request_id: str, reason: str) -> None:
    keep_request_id = clean_text(keep_request_id)
    if not keep_request_id:
        return
    archived = [
        dict(item)
        for item in items
        if isinstance(item, dict)
        and clean_text(item.get("request_id"))
        and clean_text(item.get("request_id")) != keep_request_id
    ]
    if not archived:
        return
    CODEX_QUEUE_CLEANUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    write_json(
        CODEX_QUEUE_CLEANUP_DIR / f"recall_queue_snapshot_{stamp}.json",
        {
            "archived_at": datetime.now().isoformat(timespec="seconds"),
            "reason": clean_text(reason),
            "keep_request_id": keep_request_id,
            "items": archived,
        },
    )


def _as_existing_file(value: object) -> Path | None:
    text = clean_text(value)
    if not text:
        return None
    path = Path(text)
    if path.exists() and path.is_file():
        return path
    return None


def _is_talk_style_content(text: str) -> bool:
    sample = text[:2400]
    lines = [line.strip() for line in sample.splitlines() if line.strip()]
    title_area = " ".join(lines[:20])
    if "谈心式论证稿" in title_area and "红楼梦工程｜" in title_area:
        return True
    return "谈心式论证稿" in sample and ("模" + "板依据") in sample and "先说人话" in sample


def _answer_quality_by_type(source_type: str) -> str:
    if source_type == "codex_synthesized":
        return "codex_final"
    if source_type == "codex_target_writeback":
        return "codex_final"
    if source_type == "manual_copy":
        return "manual_copy"
    return "unknown_source"


def _is_trustworthy_codex_path(path: Path) -> bool:
    normalized = str(path.resolve()).lower()
    if not normalized.endswith("/codex"):
        return False
    return not any(hint in normalized for hint in SUSPICIOUS_CLI_HINTS)


def _sync_codex_identity(codex_home: Path) -> None:
    source_home = Path.home() / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    for name in ("auth.json", "config.toml", "installation_id", ".codex-global-state.json"):
        source = source_home / name
        target = codex_home / name
        if source.exists():
            shutil.copy2(source, target)


def _codex_env() -> dict[str, str]:
    env = os.environ.copy()
    codex_home = CODEX_RUNTIME_HOME.resolve()
    _sync_codex_identity(codex_home)
    tmpdir = codex_home / ".tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(codex_home),
            "CODEX_HOME": str(codex_home),
            "CODEX_SANDBOX_NETWORK_DISABLED": "0",
            "TMPDIR": str(tmpdir.resolve()),
        }
    )
    env.pop("CODEX_SANDBOX", None)
    env.pop("CODEX_CI", None)
    return env


def _verify_codex_executable(path: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(path), "-h"],
            text=True,
            capture_output=True,
            timeout=20,
            env=_codex_env(),
        )
        return proc.returncode == 0
    except Exception:
        return False


def _codex_executable() -> str:
    explicit = os.environ.get("CODEX_EXECUTABLE")
    if explicit:
        candidate = Path(explicit)
        if candidate.exists() and _is_trustworthy_codex_path(candidate) and _verify_codex_executable(candidate):
            return str(candidate)
        raise FileNotFoundError(f"CODEX_EXECUTABLE 无效：{explicit}")

    found = shutil.which("codex")
    if found:
        candidate = Path(found)
        if _is_trustworthy_codex_path(candidate) and _verify_codex_executable(candidate):
            return str(candidate)

    for candidate in CODEX_CANDIDATES:
        if candidate.exists() and _is_trustworthy_codex_path(candidate) and _verify_codex_executable(candidate):
            return str(candidate)

    raise FileNotFoundError("没有找到可用的 codex 命令。")


def _should_retry_codex_input_error(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in (m.lower() for m in CODEX_EXEC_RETRY_HINTS))


def _should_retry_codex_network_error(text: str, attempt: int) -> bool:
    if attempt >= 3:
        return False
    lowered = clean_text(text).lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in (m.lower() for m in CODEX_EXEC_RETRY_MARKERS))


def _run_codex_command(
    cmd: list[str],
    prompt: str,
    *,
    timeout: int,
    event_path: Path,
    request_id: str,
    stage: str,
) -> subprocess.CompletedProcess:
    heartbeat_stop = _start_cli_heartbeat("Codex CLI 子进程", timeout=timeout)
    try:
        attempts = 0
        last_proc = subprocess.CompletedProcess(args=cmd, returncode=1)
        prompt_hint = clean_text(prompt[:200]).replace("\n", " ")
        max_attempts = 3
        event_path.parent.mkdir(parents=True, exist_ok=True)
        event_path.write_text("", encoding="utf-8")
        for attempt_index in range(max_attempts):
            attempts += 1
            use_stdin = attempt_index == 0
            execute_cmd = list(cmd)
            execute_input = None
            if use_stdin:
                execute_cmd.append("-")
                execute_input = prompt
            else:
                execute_cmd.append(prompt)
            execute_mode = "stdin" if use_stdin else "argv"
            event_path.parent.mkdir(parents=True, exist_ok=True)
            if not event_path.exists():
                event_path.write_text("", encoding="utf-8")
            with event_path.open("a", encoding="utf-8") as events:
                events.write(
                    f"\n===== {stage} attempt {attempts}/{max_attempts} mode={execute_mode} request_id={request_id} prompt_hint={prompt_hint} =====\n"
                )
                events.flush()
                last_proc = subprocess.run(
                    execute_cmd,
                    cwd=str(ROOT),
                    text=True,
                    input=execute_input if use_stdin else None,
                    stdout=events,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    env=_codex_env(),
                )
            if last_proc.returncode == 0:
                return last_proc

            latest = _read_limited(event_path, 5000)
            if not use_stdin and _should_retry_codex_input_error(latest):
                continue
            if _should_retry_codex_network_error(latest, attempts) and attempt_index + 1 < max_attempts:
                time.sleep(attempts)
                continue

        return last_proc

    finally:
        heartbeat_stop.set()

def _readable_codex_error(path: Path, limit: int = 2400) -> str:
    return _read_limited(path, limit)


def _read_limited(path: Path, limit: int = 12000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore").strip()
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n……中间内容已省略，以下为文件末尾……\n\n{tail}"


def _read_process_judgment_preview(path: Path, pass_index: int = 0) -> str:
    if not path.exists() or not path.is_file():
        return ""
    name = path.name
    size = path.stat().st_size
    if name.endswith(".csv"):
        line_limit = 42 if pass_index == 0 else 24
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        preview = "\n".join(lines[:line_limit])
        omitted = max(0, len(lines) - line_limit)
        suffix = f"\n\n……CSV 已压缩预览，剩余 {omitted} 行只保留在工程底账，不直接塞入判别门……" if omitted else ""
        return f"【CSV压缩预览｜{name}｜{size} bytes】\n{preview}{suffix}"
    if size >= 180_000:
        limit = 7000 if pass_index == 0 else 3200
        return (
            f"【大文件压缩预览｜{name}｜{size} bytes】\n"
            "本文件全量保留在工程底账；本判别门只读取头尾索引，避免把全量候选长表直接塞给 Codex。\n\n"
            f"{_read_limited(path, limit)}"
        )
    limit = 10000 if pass_index == 0 else 5200
    return _read_limited(path, limit)


def _supplemental_results(result: dict) -> list[dict]:
    items = result.get("supplemental_results", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _result_direct_paths(result: dict, keys: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for key in keys:
        path = _as_existing_file(result.get(key))
        if path:
            paths.append(path)
    for child in _supplemental_results(result):
        paths.extend(_result_direct_paths(child, keys))
    return paths


def _result_packages(result: dict) -> list[Path]:
    packages: list[Path] = []
    for child in _supplemental_results(result):
        packages.extend(_result_packages(child))
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    if package.exists() and package.is_dir():
        packages.append(package)
    seen: set[str] = set()
    unique: list[Path] = []
    for package_path in packages:
        resolved = str(package_path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(package_path)
    return unique


def _latest_workflow_result(result: dict) -> dict:
    latest = result
    for child in _supplemental_results(result):
        latest = _latest_workflow_result(child)
    return latest if isinstance(latest, dict) else result


def _workflow_material_paths(result: dict) -> list[Path]:
    paths: list[Path] = []
    paths.extend(
        _result_direct_paths(
            result,
            (
                "codex_original_reread_md",
                "codex_original_reread_json",
                "codex_close_reading_md",
                "codex_close_reading_json",
                "codex_material_judgment_md",
                "codex_material_judgment_json",
                "codex_process_judgment_md",
                "codex_process_judgment_json",
                "status_file",
                "status_json",
            ),
        )
    )

    for package in _result_packages(result):
        for key in (
            "codex_final_answer_gate_md",
            "codex_original_reread_gate_md",
            "codex_original_reread_target_md",
            "codex_close_reading_gate_md",
            "final_reading_gate_md",
            "reading_md",
            "cards",
            "writing_md",
            "review_firstpass_cards_md",
            "triaged_csv",
            "review_csv",
            "process_inventory_md",
            "question_tree",
            "question_judgment_md",
            "keyword_precheck_json",
            "library_flow_md",
            "library_flow_json",
            "final_reading_gate_json",
            "process_inventory_json",
            "experience_entry_md",
            "experience_entry_json",
            "overview",
            "review_coverage_md",
            "next_plan_md",
            "source_verify_md",
            "workflow_status_md",
        ):
            filename = closed_loop.CORE_FILES.get(key)
            if not filename:
                continue
            path = package / filename
            if path.exists():
                paths.append(path)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _workflow_queue_payload(result: dict) -> dict:
    active_result = _latest_workflow_result(result)
    package = Path(clean_text(active_result.get("package") or active_result.get("package_dir")))
    manifest: dict = {}
    if package.exists() and package.is_dir():
        manifest_path = package / closed_loop.CORE_FILES["manifest"]
        loaded_manifest = read_json(manifest_path, {})
        if isinstance(loaded_manifest, dict):
            manifest = loaded_manifest

    core_files = manifest.get("core_files", {})
    if not isinstance(core_files, dict):
        core_files = {}
    result_core_files = active_result.get("core_files", {})
    if isinstance(result_core_files, dict):
        core_files.update({key: value for key, value in result_core_files.items() if clean_text(value)})
    outer_core_files = result.get("core_files", {})
    if isinstance(outer_core_files, dict):
        core_files.update({key: value for key, value in outer_core_files.items() if clean_text(value)})

    results = manifest.get("results", {})
    if not isinstance(results, dict):
        results = active_result.get("results", {}) if isinstance(active_result.get("results"), dict) else {}
    research = results.get("research", {}) if isinstance(results, dict) else {}
    review = results.get("review", {}) if isinstance(results, dict) else {}
    readback = results.get("readback", {}) if isinstance(results, dict) else {}
    feedback = results.get("feedback", {}) if isinstance(results, dict) else {}
    route_context = (
        clean_text(active_result.get("route_context"))
        or clean_text(result.get("route_context"))
        or clean_text(manifest.get("parameters", {}).get("route_context") if isinstance(manifest.get("parameters"), dict) else "")
    )

    loop_status = results.get("loop_status", {}) if isinstance(results, dict) else {}

    workflow_file_keys = (
        "codex_process_judgment_md",
        "codex_process_judgment_json",
        "codex_material_judgment_md",
        "codex_material_judgment_json",
        "codex_original_reread_md",
        "codex_original_reread_json",
        "codex_original_reread_gate_md",
        "codex_original_reread_gate_json",
        "codex_original_reread_target_md",
        "codex_close_reading_md",
        "codex_close_reading_json",
        "question_judgment_md",
        "keyword_precheck_json",
        "library_flow_md",
        "library_flow_json",
        "final_reading_gate_md",
        "final_reading_gate_json",
        "process_inventory_md",
        "process_inventory_json",
        "experience_entry_md",
        "experience_entry_json",
        "overview",
        "question_tree",
        "triaged_csv",
        "cards",
        "review_csv",
        "reading_md",
        "writing_md",
        "writable_pack",
        "handoff_prompt",
        "draft_md",
        "counter_draft_md",
        "next_plan_md",
        "next_tasks_csv",
        "review_plan_md",
        "review_queue_csv",
        "review_sheet_csv",
        "review_sheet_md",
        "review_tick_md",
        "review_cards_md",
        "review_assist_md",
        "review_assist_csv",
        "review_workbench_md",
        "review_workbench_csv",
        "review_coverage_md",
        "review_coverage_csv",
        "review_firstpass_md",
        "review_firstpass_csv",
        "review_firstpass_sheet_csv",
        "review_firstpass_sheet_md",
        "review_firstpass_cards_md",
        "review_firstpass_desk_md",
        "review_firstpass_talk_md",
        "workflow_status_md",
        "workflow_status_json",
        "continue_report_md",
        "continue_summary_json",
        "source_verify_md",
        "source_verify_csv",
        "review_finish_md",
        "review_finish_json",
        "article_ingest_report_md",
        "article_ingest_candidate_csv",
        "article_ingest_links_csv",
        "article_ingest_identity_md",
        "article_ingest_summary_json",
        "manifest",
    )
    fallback_files = {key: key for key in workflow_file_keys}
    for payload_key, core_key in fallback_files.items():
        if core_files.get(payload_key):
            continue
        filename = closed_loop.CORE_FILES.get(core_key)
        if filename and package.exists():
            candidate = package / filename
            if candidate.exists():
                core_files[payload_key] = str(candidate)

    if clean_text(result.get("status_file")):
        core_files["workflow_status_md"] = clean_text(result.get("status_file"))
    if clean_text(result.get("status_json")):
        core_files["workflow_status_json"] = clean_text(result.get("status_json"))
    if clean_text(result.get("codex_material_judgment_md")):
        core_files["codex_material_judgment_md"] = clean_text(result.get("codex_material_judgment_md"))
    if clean_text(result.get("codex_material_judgment_json")):
        core_files["codex_material_judgment_json"] = clean_text(result.get("codex_material_judgment_json"))
    if clean_text(result.get("codex_close_reading_md")):
        core_files["codex_close_reading_md"] = clean_text(result.get("codex_close_reading_md"))
    if clean_text(result.get("codex_close_reading_json")):
        core_files["codex_close_reading_json"] = clean_text(result.get("codex_close_reading_json"))
    if clean_text(result.get("codex_original_reread_md")):
        core_files["codex_original_reread_md"] = clean_text(result.get("codex_original_reread_md"))
    if clean_text(result.get("codex_original_reread_json")):
        core_files["codex_original_reread_json"] = clean_text(result.get("codex_original_reread_json"))

    for source in (loop_status,):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key == "status_md":
                core_files.setdefault("workflow_status_md", value)
            elif key == "status_json":
                core_files.setdefault("workflow_status_json", value)
            elif key in fallback_files:
                core_files.setdefault(key, value)

    review_followup = review.get("followup_md", "") if isinstance(review, dict) else ""
    if clean_text(review_followup):
        core_files.setdefault("next_plan_md", review_followup)
    workflow_files = {}
    for key in workflow_file_keys:
        value = clean_text(core_files.get(key))
        if value:
            workflow_files[key] = value
    return {
        "workflow_status": "工程已运转，已生成拆题、证据池/材料池与闭环过程文件。",
        "workflow_package": str(package) if package.exists() else clean_text(result.get("package") or result.get("package_dir")),
        "workflow_files": workflow_files,
        "workflow_summary": {
            "subquestion_count": research.get("subquestion_count", 0),
            "unique_segments": research.get("unique_segments", 0),
            "review_rows": review.get("review_rows", 0),
            "usable_rows": readback.get("usable_rows", 0),
            "pending_rows": readback.get("pending_rows", 0),
            "feedback_labeled_rows": feedback.get("labeled_rows", 0),
            "process_file_count": len(workflow_files),
            "route_context": route_context,
            "flow_profile": result.get("flow_profile", {}) if isinstance(result.get("flow_profile"), dict) else {},
        },
    }


def _looks_like_engine_draft(text: str) -> bool:
    sample = text[:3000]
    if _is_talk_style_content(sample):
        return True
    return any(
        marker in sample
        for marker in (
            "模" + "板依据：",
            "这是一版“正式文章第一稿”",
            "这是一版“正式文章第一稿”。",
            "母稿：`",
            "证据分层表：`",
            "# 红楼梦工程｜谈心式论证稿",
            "# 红楼梦工程｜金玉木石谈心式论证稿",
            "# 红楼梦工程｜太虚幻境谈心式论证稿",
            "# 红楼梦工程｜葬花谈心式论证稿",
        )
    )


def _is_valid_codex_final_answer_text(text: str) -> bool:
    sample = clean_text(text)
    if not sample:
        return False
    if _looks_like_engine_draft(sample):
        return False
    banned_markers = (
        "OpenAI Codex",
        "tokens used",
        "ERROR:",
        "WARN ",
        "===== final_synthesis",
        "===== close_reading",
        "===== material_judgment",
        "我会这样引用",
        "旁边的故事脉络",
        "内部明细",
        "证据分层表",
        "模" + "板依据：",
        "这是一版“正式文章第一稿”",
        "谈心式论证稿",
        "红楼解语｜待 Codex 生成",
        "等待 Codex 红楼解语",
        "等待 Codex 读取材料池后写入",
        "本地工程不得自动填充正文",
    )
    if any(marker in sample[:12000] for marker in banned_markers):
        return False
    compact = "".join(sample.split())
    has_cjk = any("\u4e00" <= char <= "\u9fff" for char in compact)
    if len(sample) < 80:
        return has_cjk and len(compact) >= 2
    return True


def _normalize_codex_final_answer_text(text: str) -> str:
    normalized = clean_text(text)
    for marker in (
        "当前环境只读，不能把最终稿写回最终答案目录。",
        "当前沙盒是只读权限，所以我不能把最终答案实际写回最终答案目录；下面是可写入的最终文本。",
        "受当前沙盒只读限制，不能实际写入最终答案目录；以下即为最终红楼解语文本。",
        "当前会话文件系统是只读权限，我无法把最终答案实际写入最终答案目录；以上为可写入的最终红楼解语文本。",
    ):
        normalized = normalized.replace(marker, "")
    return "\n".join(line.rstrip() for line in normalized.splitlines()).strip()


def is_valid_codex_final_answer_file(path: str | Path) -> bool:
    source = Path(path)
    if not source.exists() or source.suffix != ".md":
        return False
    try:
        return _is_valid_codex_final_answer_text(source.read_text(encoding="utf-8"))
    except OSError:
        return False


def research_style_guidance(task_intent: str, requirements: str) -> str:
    trigger_text = clean_text(f"{task_intent}\n{requirements}").lower()
    style_triggers = (
        "ars",
        "ars-plan",
        "ars-outline",
        "ars-lit-review",
        "ars-full",
        "deep-research",
        "lit-review",
        "research skill",
        "research-style",
        "academic-research",
        "style calibration",
        "style-calibration",
        "voice calibration",
        "voice-calibration",
        "研究式回答",
        "研究式表达",
        "心得式",
        "心得式结论",
        "心得式回答",
        "推导式",
        "推导式回答",
        "研究式",
        "慢慢拆解",
        "慢慢推导",
        "原文推理",
        "证据推理",
        "证据慢推",
        "原文慢推",
        "温和收束",
        "自然收束",
        "证据出发",
        "材料池自由发挥",
        "有温度",
    )
    requested = any(trigger in trigger_text for trigger in style_triggers)
    lead = (
        "用户或页面触发了研究式表达风格。"
        if requested
        else "默认表达风格。"
    )
    return "\n".join(
        [
            lead,
            "这是输出层的软指导，不改变红楼梦工程的检索、拆题、证据池规则。",
            "可借鉴 academic-research-suite 的 style calibration 思路：证据、推理、建议分开，个人表达只作软引导。",
            "对于解释型问题，允许采用心得式结论：用原文证据起步，沿着情节、人物关系和语义层次慢慢推导，把每个判断点说清楚，再自然收束。",
            "对于定位型问题，保持结论先行、证据清楚、语言简洁。",
            "无论哪种写法，都不要套统一格式；答案应从材料池和原文复核中自然生成。",
        ]
    )


def _json_from_codex_text(text: str) -> dict:
    sample = clean_text(text)
    if "```" in sample:
        parts = sample.split("```")
        for part in parts:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("{") and cleaned.endswith("}"):
                try:
                    loaded = json.loads(cleaned)
                    if isinstance(loaded, dict):
                        return loaded
                except json.JSONDecodeError:
                    pass
    start = sample.find("{")
    end = sample.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(sample[start : end + 1])
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            return {}
    return {}


def _material_segment_tokens(raw: str) -> list[str]:
    source = clean_text(raw)
    if not source:
        return []
    normalized = source.replace("，", "/").replace("；", "/").replace("、", "/")
    normalized = normalized.replace(";", "/").replace(",", "/").replace("|", "/")
    seen: set[str] = set()
    tokens: list[str] = []
    for item in normalized.split("/"):
        token = clean_text(item)
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _material_pool_anchor_keys(chapter_no: str, segment_no: str) -> list[str]:
    chapter = clean_text(chapter_no)
    segment = clean_text(segment_no)
    if not chapter or not segment:
        return []
    keys = {f"{chapter}:{segment}"}
    for token in _material_segment_tokens(segment):
        keys.add(f"{chapter}:{token}")
    return list(keys)


def _build_material_pool_decision_map(result: dict) -> dict[str, str]:
    payload_path = clean_text(result.get("codex_material_judgment_json"))
    payload = read_json(Path(payload_path), {}) if payload_path else {}
    if not isinstance(payload, dict):
        return {}

    mapping: dict[str, set[str]] = {}

    def _add_rows(rows: object, label: str) -> None:
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict):
                continue
            segment_no = clean_text(row.get("segment_no"))
            chapter_no = clean_text(row.get("chapter_no"))
            if not segment_no or not chapter_no:
                continue
            for key in _material_pool_anchor_keys(chapter_no, segment_no):
                mapping.setdefault(key, set()).add(label)

    _add_rows(payload.get("usable_materials"), "可用")
    _add_rows(payload.get("background_materials"), "背景")
    _add_rows(payload.get("rejected_materials"), "不可用")
    return {key: "、".join(sorted(values)) for key, values in mapping.items()}


def _find_material_pool_ref(mapping: dict[str, str], segment_no: str, chapter_no: str) -> str:
    for key in _material_pool_anchor_keys(chapter_no, segment_no):
        state = clean_text(mapping.get(key))
        if state:
            return f"{state}:{key}"
    return ""


def _material_pool_snapshot_for_prompt(result: dict, max_lines: int = 28) -> str:
    mapping = _build_material_pool_decision_map(result)
    if not mapping:
        return "材料池判定快照：未能读取 00I_Codex材料池判定 的结构化条目。"
    lines = ["材料池判定快照（取自 00I_Codex材料池判定）："]
    for key in sorted(mapping.keys())[:max_lines]:
        lines.append(f"- {key}｜{mapping[key]}")
    if len(mapping) > max_lines:
        lines.append(f"- ...还有 {len(mapping) - max_lines} 条未展示")
    return "\n".join(lines)


def _question_decomposition_payload(result: dict) -> dict:
    paths: list[Path] = []
    paths.extend(_result_direct_paths(result, ("keyword_precheck_json",)))
    for package in _result_packages(result):
        filename = closed_loop.CORE_FILES.get("keyword_precheck_json")
        if filename:
            path = package / filename
            if path.exists():
                paths.append(path)
    for path in paths:
        payload = read_json(path, {})
        if isinstance(payload, dict):
            return payload
    return {}


def _question_decomposition_snapshot_for_prompt(result: dict, question: str, max_items: int = 8) -> str:
    payload = _question_decomposition_payload(result)
    raw_subquestions = payload.get("subquestions") if isinstance(payload, dict) else []
    lines = ["问题复习与拆解快照：", f"- 原问题：{question or clean_text(payload.get('question'))}"]
    if isinstance(raw_subquestions, list) and raw_subquestions:
        for item in raw_subquestions[:max_items]:
            if not isinstance(item, dict):
                continue
            order = clean_text(item.get("order")) or str(len(lines))
            dimension = clean_text(item.get("dimension")) or "子问题"
            subq = clean_text(item.get("question"))
            purpose = clean_text(item.get("purpose"))
            expectation = clean_text(item.get("evidence_expectation"))
            parts = [f"{order}. {dimension}"]
            if subq:
                parts.append(f"子问题：{subq}")
            if purpose:
                parts.append(f"目的：{purpose}")
            if expectation:
                parts.append(f"证据期待：{expectation}")
            lines.append("- " + "｜".join(parts))
        if len(raw_subquestions) > max_items:
            lines.append(f"- ...还有 {len(raw_subquestions) - max_items} 个子问题未展示")
    else:
        lines.append("- 未读取到独立子问题；本题按原问题作为默认问题单元处理。")
    return "\n".join(lines)


def _task_memory_card_for_prompt(
    result: dict,
    question: str,
    stage_name: str,
    stage_job: str,
    *,
    max_items: int = 6,
    heavy: bool = False,
) -> str:
    question_snapshot = _question_decomposition_snapshot_for_prompt(result, question, max_items=max_items)
    lines = [
        "任务记忆卡：",
        f"- 当前阶段：{stage_name}",
        f"- 本阶段只做：{stage_job}",
        "- 固定原则：先记住原问题和子问题，再判断材料；材料只回答问题，不让问题迁就材料。",
        "- 材料标注：能说明就写它回答哪个问题点；不能说明就降级、写缺口或请求补证。",
    ]
    if heavy:
        lines.append("- 重复习要求：本阶段必须先完整复述原问题、子问题和摘抄中心，再开始选材。")
    return "\n".join([*lines, "", question_snapshot])


def _normalize_close_reading_material_rows(
    rows: object,
    pool_map: dict[str, str],
    insufficient: list[str],
    context: str,
) -> list[dict]:
    if not isinstance(rows, list):
        return []
    normalized: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)

        status = clean_text(item.get("evidence_readiness"))
        if status not in {"原文足证", "摘录不足", "摘要定位", "需补整回"}:
            if "足证" in status:
                status = "原文足证"
            elif "摘要" in status:
                status = "摘要定位"
            elif "补" in status or "不足" in status:
                status = "摘录不足"
            else:
                status = "需补整回"
        item["evidence_readiness"] = status

        segment_no = clean_text(item.get("segment_no"))
        chapter_no = clean_text(item.get("chapter_no"))
        if status != "原文足证":
            read_window = clean_text(item.get("read_window"))
            if not read_window:
                anchor = f"{chapter_no}-{segment_no}" if chapter_no and segment_no else (segment_no or chapter_no or "未定位锚点")
                insufficient.append(f"{context} {anchor}：{status}，无 read_window，需回读整回或上下文补证")
            evidence_gaps = clean_text(item.get("quote_or_summary"))
            if not evidence_gaps:
                insufficient.append(f"{context} {anchor}: 未给 quote_or_summary 做原文回读定位")
        pool_item_ref = clean_text(item.get("pool_item_ref"))
        if not pool_item_ref and segment_no and chapter_no:
            pool_item_ref = _find_material_pool_ref(pool_map, segment_no, chapter_no)
        if not pool_item_ref:
            pool_item_ref = "未命中材料池判定"
            anchor = f"{chapter_no}-{segment_no}" if chapter_no and segment_no else (segment_no or chapter_no or "未定位锚点")
            insufficient.append(f"{context} {anchor}：{pool_item_ref}")
        item["pool_item_ref"] = pool_item_ref

        if "不可用" in pool_item_ref and status == "原文足证":
            item["evidence_readiness"] = "需补整回"
            status = "需补整回"
            anchor = f"{chapter_no}-{segment_no}" if chapter_no and segment_no else (segment_no or chapter_no or "未定位锚点")
            insufficient.append(f"{context} {anchor}：材料池标记为不可用，不能当主证")

        if not segment_no or not chapter_no:
            anchor = clean_text(item.get("pool_item_ref"))
            insufficient.append(f"{context} {anchor}：缺少 segment_no/chapter_no，不能回到原文锚点")

        refs = _as_list(item.get("subquestion_refs") or item.get("hit_subquestions"), limit=8)
        item["subquestion_refs"] = refs or ["总问题"]

        normalized.append(item)
    return normalized


def _as_list(value: object, limit: int = 24) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        text = clean_text(value)
        for sep in ("；", ";", "，", ",", "\n"):
            text = text.replace(sep, "、")
        raw = text.split("、")
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        value_text = clean_text(item)
        if not value_text or value_text in seen:
            continue
        seen.add(value_text)
        result.append(value_text)
        if len(result) >= limit:
            break
    return result


def _compound_groups_from_payload(payload: dict, limit: int = 8) -> list[list[str]]:
    groups: list[list[str]] = []
    raw = payload.get("compound_groups")
    if isinstance(raw, list):
        for group in raw[:limit]:
            values = _as_list(group if isinstance(group, list) else [group], limit=12)
            if values:
                groups.append(values)
    return groups


def _strategy_execution_terms(payload: dict, fallback_terms: list[str]) -> list[str]:
    term_roles = payload.get("term_roles")
    role_terms: list[str] = []
    if isinstance(term_roles, dict):
        for key in ("primary_characters", "primary_objects", "primary_terms"):
            role_terms.extend(_as_list(term_roles.get(key), limit=8))
    compact = decomposer.compact_strategy_terms(role_terms, limit=10)
    if compact:
        return compact
    groups = _compound_groups_from_payload(payload)
    compact = decomposer.compact_compound_query_terms(groups, limit=10) if groups else []
    if compact:
        return compact
    return decomposer.compact_strategy_terms(fallback_terms, limit=10)


def _collect_term_role_set(payload: dict) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
    roles = payload.get("term_roles") if isinstance(payload.get("term_roles"), dict) else {}
    primary_characters = _as_list(roles.get("primary_characters"), limit=8)
    primary_objects = _as_list(roles.get("primary_objects"), limit=8)
    primary_terms = _as_list(roles.get("primary_terms"), limit=12)
    expansion_terms = _as_list(roles.get("expansion_terms"), limit=16)
    scene_terms = _as_list(roles.get("scene_terms"), limit=12)
    anchor_terms = _as_list(roles.get("anchor_terms"), limit=16)
    exclusion_terms = _as_list(roles.get("exclusion_terms"), limit=12)
    core_terms = _as_list(
        [
            *primary_characters,
            *primary_objects,
            *primary_terms,
        ],
        limit=14,
    )
    for group in _compound_groups_from_payload(payload):
        for item in _as_list(group, limit=8):
            clean = clean_text(item)
            if clean and clean not in core_terms:
                core_terms.append(clean)
    core_set = {clean_text(item) for item in core_terms if clean_text(item)}
    return (
        primary_characters,
        primary_objects,
        primary_terms,
        expansion_terms,
        scene_terms,
        anchor_terms,
        exclusion_terms,
        list(core_set),
    )


def _fast_relation_search_term_guard(payload: dict, core_terms: list[str]) -> dict:
    core_set = {clean_text(item) for item in core_terms if clean_text(item)}
    source_terms = _as_list(payload.get("search_terms"), limit=24)
    term_roles = payload.get("term_roles") if isinstance(payload.get("term_roles"), dict) else {}
    expansion_terms = _as_list(term_roles.get("expansion_terms"), limit=16)
    scene_terms = _as_list(term_roles.get("scene_terms"), limit=12)
    anchor_terms = _as_list(term_roles.get("anchor_terms"), limit=16)
    exclusion_terms = _as_list(term_roles.get("exclusion_terms"), limit=12)

    keep_terms: list[str] = []
    moved_terms: list[str] = []
    for term in source_terms:
        clean_term = clean_text(term)
        if not clean_term:
            continue
        if clean_term in core_set:
            if clean_term not in keep_terms:
                keep_terms.append(clean_term)
            continue
        # 短平快关系题只保留 Codex 标出的核心对象为第一轮执行词；
        # 其余词不由程序判断好坏，统一降为辅助锚点，交给过程判别门决定是否补查。
        moved_terms.append(clean_term)

    if not keep_terms:
        keep_terms = core_terms[:7] or source_terms[:4]

    compact_groups = []
    for group in _compound_groups_from_payload(payload):
        if not group:
            continue
        normalized_group = _as_list(group, limit=8)
        if not normalized_group:
            continue
        has_core = any(clean_text(item) in core_set for item in normalized_group)
        if has_core:
            compact_groups.append([item for item in normalized_group if clean_text(item)][:4])
    if not compact_groups and len(core_set) >= 2:
        compact_groups = [[item] for item in core_terms[:4]]
    compact_groups = compact_groups[:6]

    updated_roles = {**term_roles}
    updated_roles["anchor_terms"] = _as_list(anchor_terms + moved_terms, limit=24)
    updated_roles["scene_terms"] = scene_terms

    return {
        **payload,
        "search_terms": decomposer.compact_strategy_terms(keep_terms, limit=7),
        "compound_groups": compact_groups,
        "term_roles": updated_roles,
    }


def _short_context(value: object, limit: int = 220) -> str:
    text = " ".join(clean_text(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _query_strategy_decision_shortlist() -> list[str]:
    return [
        "【0. 快速决策口径】",
        "先用这里定大方向，再读后面的全量经验仓和库线骨架；这里不是新规则，只是把已有经验仓压缩成第一眼可用的判断地图。",
        "- 工程契约：旧召回模块只作后台补漏；语义路线直达语义聚拢中心库，所有取材只在中心库内部表轴与原文回源之间完成。",
        "- 人物/命运/性格/言行题：先选中心库人物线、称谓别名线、人物行动线或人物评价线；优先 characters、character_alias_solidification、person_segment_edges、segments、chapters 等中心表轴；关键是别名归一后回原文上下文。",
        "- 人物关系/人物与物件或空间关系题：先选中心库关系线、共现查证线、同段强证线、证据分层线；优先 evidence_edges、person_segment_edges、objects_axis、spaces_axis、segments、chapters 等中心表轴；关键是设置 compound_groups，不能只看单方材料。",
        "- 物象/器物/花木/象征题：先选中心库物象域、象征功能线、场景群组线；优先 objects_axis、evidence_edges、segments、chapters 等中心表轴；单字物象可用，由 Codex 按语义判断它是不是物，不按字数硬拦。",
        "- 空间/场景/居所/移动题：先选中心库场域/空间域、场景群组线、人物行动线；优先 spaces_axis、space_evidence_axis、segments、chapters 等中心表轴；地点只作入口，必须读同场人物、动作和物象。",
        "- 诗词/判词/回目/原句题：先选中心库诗词文本线、章节原句线、回目标题线；优先 literary_texts_axis、chapters、segments 等中心表轴；标题和诗句只能导航，最终仍要确认正文语境。",
        "- 事件/因果/发展/结局题：先选中心库事件/情节线、因果机制线、时间线、命运/结局线；优先 event_segments、event_segment_edges、segments、chapters 等中心表轴；不能把时间先后直接当因果。",
        "- 大主题/观念/比较题：先选观念主题线、主题词扩展线、比较对照线、反证排除线；先确定承载人物/事件/物象/空间，再多点原文复核，避免空讲概念。",
        "- 定位/查原文/哪一回题：先选中心库定位问答线、章节原句线、版本真源线；优先 chapters、segments、search_documents/search_documents_fts 等中心表轴；少写解释，多给位置和上下文。",
        "",
        "【0B. 第一张入口词包必须完成的四个动作】",
        "- 定中心：判断本题是人物、关系、物象、空间、诗词、事件、主题、定位，还是多轴交叉。",
        "- 定路径：从已有经验仓选择 experience_paths_used，从已有库线骨架选择 library_routes_used。",
        "- 定词网：给 search_terms、compound_groups、anchor_terms；复合关系题必须把核心对象拆成组，背景锚点不得冒充答案。",
        "- 定执行：给 preferred_libraries、source_order、guardrails 和 next_action_directive；preferred_libraries 只表示语义聚拢中心库内部优先表轴，不表示另选外部库。",
        "- 定资料化问题：按 Notion 原 SOP 的原则，拆题是拆资料需求，不是拆观点；先想查语义聚拢中心库内部哪些表轴、哪些原文、哪些材料缺口，再让工程查证。",
        "",
        "【0C. 策略质量自检】",
        "- 是否说明为什么选这些经验路径和中心表轴路径。",
        "- 是否把用户题目的核心对象都放进词网，而不是让本地程序自动猜。",
        "- 是否有强复合轴来防止单边材料冒充关系证据。",
        "- 是否区分入口词、背景锚点、主查词和反证/排除提示。",
        "- 是否把下一步说成可执行的查库/查原文动作，而不是抽象口号。",
        "",
        "【0D. 词的角色分工】",
        "- 主查词：题目真正要证明关系的核心对象，必须进入 search_terms 和 compound_groups；人物主查词只放归一人物实体。",
        "- 归一词：人物别名、简称、繁简体、异写，用来防漏；归一词放 term_roles.normalization_terms，不当第一轮执行词。",
        "- 扩展词：同类物象、动作、状态、场景词，用来扩大第一轮候选；扩展词不能自动升格为主证。",
        "- 背景锚点：地点、回目、标题、名场面、诗词入口，用来定位场景；只能帮助组证，不能单独冒充答案。",
        "- 反证/排除词：容易串题、同字误召回、旧题污染、标题诱导和无关热词；用于降级或补查。",
        "",
        "【0D-1. AI 生成检索词的基本规矩】",
        "- 人物对象：先入人物库归一为一个人物实体；search_terms 和 compound_groups 的人物组只放归一人物，例如林黛玉；黛玉、林姑娘、颦儿、潇湘妃子等放 normalization_terms，让人物库和 pm 映射处理，不要全文别名硬扫。",
        "- 物象对象：先抓最小有效物象字/词，再抓复合词、别称、器物形态和场景形态；例如竹子题，要把竹作为核心物象字，同时考虑竹子、竹枝、竹叶、竹影、竹梢、竹帘、竹扇等。",
        "- 单字物象可以是强主查词：金、玉、泪、竹、帕、灯等单字只要语义上是本题物象，就可以作为主查词；不能按字数拦截。",
        "- 复合物要守住本体：竹扇可以提示扇类线索，但普通扇/扇子不能自动算竹；只有原文或上下文能确认材质/关系时才能升级。",
        "- 关系题的第一组通常是人物/主体，第二组通常是物象/事件/空间等对象；动作、情绪、地点、回目只作辅助，不进入强复合资格。",
        "",
        "【0E. 库线选择的认识顺序】",
        "- 先判断题目的知识对象：人、物、空间、诗词、事件、主题、原文位置。",
        "- 先进入语义聚拢中心库，再回原文，再建材料池；中心库不是后补材料，中心库内部表轴会帮助 Codex 裁剪问题和决定下一轮查证。",
        "- 再判断对象之间的关系强度：单对象说明、二元关系、三元共现、跨回呼应、因果链或比较链。",
        "- 再选择中心表轴：对象明确先中心库对象轴，入口不明先中心库全文词表轴，原句明确先章节真源，多轴题走中心表轴与原文双向复核。",
        "- 再规定材料升级条件：只有回到原子段、章节真源、上下文，并能回答原问题的材料，才允许进入材料池判定。",
        "",
        "【0F. 二次补查触发】",
        "- 首轮只命中单边对象：补查另一边核心词和同段/同场景关系。",
        "- 首轮只命中标题、地点或摘要：补查正文段落和上下文。",
        "- 首轮材料多但互不支撑：补查关系动作、因果词、时间线或反证词。",
        "- 首轮材料太少：扩大同义词、别名、繁简体、物象别称、相关空间或相邻章回。",
        "- 首轮出现旧题内容：按 request_id 和本题核心词重收缩，旧题只能作反证提示。",
    ]


def _schema_columns_for_table(db_path: Path, table: str) -> list[str]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [clean_text(row[1]) for row in rows if len(row) > 1 and clean_text(row[1])]
    except sqlite3.Error:
        return []


def _database_schema_guardrail() -> str:
    table_names = (
        "characters",
        "character_alias_solidification",
        "person_segment_edges",
        "objects_axis",
        "spaces_axis",
        "space_evidence_axis",
        "literary_texts_axis",
        "evidence_edges",
        "segments",
        "chapters",
    )
    dbs = (
        ("多轴库", closed_loop.AXIS_DB),
        ("全文库", closed_loop.SEARCH_DB),
    )
    lines = [
        "【0G. 真实库表字段防猜提示】",
        "用法：只有查库/补查阶段才看这里；最终红楼解语阶段不得再现场查库。AI 不得凭 Notion 旧称或直觉编造 SQL 字段。",
        "- 字段硬令：objects_axis 使用 object_key、name、category、quote、symbolic_meaning 等字段，没有 object_id/object_name。",
        "- 字段硬令：spaces_axis 使用 space_key、name、space_code、description 等字段，没有 space_id/space_name。",
        "- 字段硬令：person_segment_edges 使用 character_name、character_key、segment_no、segment_label、role_type 等字段；查人优先走这个映射，不用正文 LIKE 替代。",
        "- 字段硬令：segments 使用 segment_no、summary、quote、original_version、chapter_no；chapters 使用 chapter_no、title、full_text。",
        "- 如果需要 SQL，只能使用下列真实字段；不确定字段时先读 schema 或改走工程函数，不要尝试 object_id/object_name 之类猜测字段。",
    ]
    for label, db_path in dbs:
        collected: list[str] = []
        for table in table_names:
            cols = _schema_columns_for_table(db_path, table)
            if cols:
                collected.append(f"{table}({', '.join(cols[:14])})")
        if collected:
            lines.append(f"- {label}：{'；'.join(collected)}")
    return "\n".join(lines)


def _query_strategy_existing_preflight_context() -> str:
    """Reuse the existing strategy/experience cards for the first Codex gate."""
    lines: list[str] = [
        "这是红楼梦工程已经存在的前置策略体系。它不是新建卡，也不是答案模板；它只帮助 Codex 在查证前理解工程、选择路径、决定查什么。",
        "",
        *_query_strategy_decision_shortlist(),
        "",
        _database_schema_guardrail(),
        "",
        "【A. 问题判断经验仓骨架】",
        "用法：Codex 读题后选择相关经验路径；本地程序只接收 Codex 已选路径进入查证。",
    ]
    try:
        for rule in closed_loop.question_query_experience_skeleton():
            lines.append(
                "- {type}｜库/轴：{bucket}｜何时用：{when}｜找词法：{keyword_strategy}｜查证顺序：{source_order}｜失败信号：{failure_signal}".format(
                    type=_short_context(rule.get("type"), 24),
                    bucket=_short_context(rule.get("bucket"), 80),
                    when=_short_context(rule.get("when"), 120),
                    keyword_strategy=_short_context(rule.get("keyword_strategy"), 160),
                    source_order=_short_context(rule.get("source_order"), 160),
                    failure_signal=_short_context(rule.get("failure_signal"), 120),
                )
            )
    except Exception as exc:
        lines.append(f"- 经验仓读取失败：{type(exc).__name__}: {exc}")

    lines.extend(
        [
            "",
            "【B. 库线原文流转骨架】",
            "用法：Codex 决定本题优先走哪些库、哪些映射、哪些原文入口；库线只是工具地图，不能代替原文证据。",
        ]
    )
    try:
        skeleton = closed_loop.library_flow_skeleton()
        metrics = skeleton.get("metrics", {})
        if isinstance(metrics, dict):
            metric_items = [
                f"{key}={value}"
                for key, value in metrics.items()
                if key in {"chapters_rows", "segments", "characters", "objects_axis", "spaces_axis", "literary_texts_axis", "evidence_edges", "character_aliases"}
            ]
            if metric_items:
                lines.append("- 当前库群规模：" + "；".join(metric_items))
        for group in skeleton.get("library_groups", []):
            if not isinstance(group, dict):
                continue
            lines.append(
                "- {group}｜表：{tables}｜功能：{function}｜使用：{use_when}｜风险：{risk}".format(
                    group=_short_context(group.get("group"), 40),
                    tables=_short_context("、".join(group.get("tables", [])) if isinstance(group.get("tables"), list) else group.get("tables"), 120),
                    function=_short_context(group.get("function"), 170),
                    use_when=_short_context(group.get("use_when"), 150),
                    risk=_short_context(group.get("risk"), 150),
                )
            )
        lines.extend(["", "【C. 允许选择的自然流】"])
        for pattern in skeleton.get("flow_patterns", []):
            if not isinstance(pattern, dict):
                continue
            lines.append(
                "- {name}：{flow}｜目的：{purpose}".format(
                    name=_short_context(pattern.get("name"), 40),
                    flow=_short_context(pattern.get("flow"), 180),
                    purpose=_short_context(pattern.get("purpose"), 120),
                )
            )
        guardrails = skeleton.get("guardrails", [])
        if isinstance(guardrails, list) and guardrails:
            lines.extend(["", "【D. 库线硬规矩】"])
            lines.extend(f"- {_short_context(item, 180)}" for item in guardrails)
    except Exception as exc:
        lines.append(f"- 库线骨架读取失败：{type(exc).__name__}: {exc}")

    lines.extend(
        [
            "",
            "【E. 全流程产物与 Codex 判别门】",
            "用法：底层完整出包，Codex 决定采用、降级、补查、跳过或停止；模块搜索产物只能进入下一道 Codex 判别，不能直接成为答案。",
        ]
    )
    try:
        for item in closed_loop.process_product_gate_catalog():
            lines.append(
                "- {stage} {name}｜产生者：{producer}｜性质：{product_type}｜判别门：{codex_gate}｜下一步：{next_step}".format(
                    stage=_short_context(item.get("stage"), 12),
                    name=_short_context(item.get("name"), 50),
                    producer=_short_context(item.get("producer"), 80),
                    product_type=_short_context(item.get("product_type"), 80),
                    codex_gate=_short_context(item.get("codex_gate"), 160),
                    next_step=_short_context(item.get("next_step"), 120),
                )
            )
    except Exception as exc:
        lines.append(f"- 判别门读取失败：{type(exc).__name__}: {exc}")

    lines.extend(["", "【F. 经验值总账高频路径】"])
    try:
        ledger = closed_loop.load_experience_ledger()
        rules = ledger.get("rules", {})
        if isinstance(rules, dict):
            rows = list(rules.values())
        elif isinstance(rules, list):
            rows = rules
        else:
            rows = []
        scored_rows = sorted(
            [row for row in rows if isinstance(row, dict)],
            key=lambda row: int(row.get("score") or 0),
            reverse=True,
        )
        if scored_rows:
            for row in scored_rows[:18]:
                lines.append(
                    "- {type}｜经验值：{score}｜成功提示：{success}｜误召回提示：{failure}".format(
                        type=_short_context(row.get("type"), 40),
                        score=clean_text(row.get("score") or 0),
                        success=_short_context(row.get("success_signal"), 120),
                        failure=_short_context(row.get("failure_signal"), 120),
                    )
                )
        else:
            lines.append("- 暂无高频路径排行；仍按经验仓骨架和库线骨架判断。")
    except Exception as exc:
        lines.append(f"- 经验值总账读取失败：{type(exc).__name__}: {exc}")

    return "\n".join(lines)


def _query_strategy_from_payload(payload: dict, request_id: str = "") -> dict:
    if not isinstance(payload, dict) or not payload.get("search_terms"):
        return {"ok": False, "route_context": "", "error": "缺少可复用的 Codex 查询词路"}
    raw_terms = _as_list(payload.get("search_terms"), limit=36)
    terms = _strategy_execution_terms(payload, raw_terms)
    libraries = _as_list(payload.get("preferred_libraries"), limit=18)
    guardrails = _as_list(payload.get("guardrails"), limit=8)
    experience_paths = _as_list(payload.get("experience_paths_used"), limit=12)
    library_routes = _as_list(payload.get("library_routes_used"), limit=12)
    strategy_reason = clean_text(payload.get("strategy_reason"))
    next_action_directive = clean_text(payload.get("next_action_directive"))
    term_roles_raw = payload.get("term_roles")
    term_role_lines: list[str] = []
    if isinstance(term_roles_raw, dict):
        role_labels = {
            "primary_characters": "主查人物",
            "primary_objects": "主查物象",
            "scene_terms": "场景词",
            "primary_terms": "主查词",
            "normalization_terms": "归一词",
            "expansion_terms": "扩展词",
            "anchor_terms": "背景锚点",
            "exclusion_terms": "排除词",
        }
        for key, label in role_labels.items():
            values = _as_list(term_roles_raw.get(key), limit=12)
            if values:
                term_role_lines.append(f"{label}={'、'.join(values)}")
    compound_groups = _compound_groups_from_payload(payload)
    route_lines = [
        "Codex查询词路",
        f"Codex问题中心：{clean_text(payload.get('question_center'))}",
        f"Codex经验路径：{'、'.join(experience_paths)}",
        f"Codex库线路径：{'、'.join(library_routes)}",
        f"Codex策略理由：{strategy_reason}",
        f"Codex下一步指令：{next_action_directive}",
        f"Codex词角色：{'；'.join(term_role_lines)}",
        f"Codex材料升级条件：{clean_text(payload.get('evidence_upgrade_rule'))}",
        f"Codex补查方案：{clean_text(payload.get('fallback_plan'))}",
        f"Codex查询词：{'、'.join(terms)}",
        f"Codex强复合：{' + '.join('/'.join(group) for group in compound_groups)}",
        f"Codex背景锚点：{'、'.join(_as_list(payload.get('anchor_terms'), limit=18))}",
        f"Codex优先库：{'、'.join(libraries)}",
        f"Codex查证顺序：{clean_text(payload.get('source_order'))}",
        f"Codex注意事项：{'；'.join(guardrails)}",
    ]
    return {
        "ok": True,
        "payload": payload,
        "route_context": "\n".join(route_lines),
        "prompt_path": "",
        "last_path": "",
        "terms": terms,
        "libraries": libraries,
        "reused": True,
        "request_id": request_id,
    }


def _recall_gate_route_context(question: str = "", task_intent: str = "", requirements: str = "") -> str:
    text = clean_text(f"{question}\n{task_intent}\n{requirements}")
    if re.search(r"(^|[\s｜|，。；;:：、])语义($|[\s｜|，。；;:：、])", text) or clean_text(question).startswith("语义"):
        return "\n".join(
            [
                "取材门：语义",
                "recall_gate：semantic",
                "取材规则：进入原语义取材系统；不得调用坐标取材模块。",
            ]
        )
    if re.search(r"(^|[\s｜|，。；;:：、])坐标($|[\s｜|，。；;:：、])", text) or clean_text(question).startswith("坐标"):
        return "\n".join(
            [
                "取材门：坐标",
                "recall_gate：coordinate",
                "取材规则：入口词包生成后，进入坐标取材系统；不得回落到原语义取材系统。",
            ]
        )
    return "\n".join(
        [
            "取材门：语义",
            "recall_gate：semantic",
            "取材规则：未显式触发坐标时，保持原语义取材系统。",
        ]
    )


def _query_strategy_fallback_terms(question: str) -> list[str]:
    question = clean_text(question)
    if not question:
        return []
    chunks = [clean_text(text) for text in re.split(r"[，。；;:：、!！?？,\.\s]+", question)]
    raw_terms: list[str] = []
    seen = set()
    for chunk in chunks:
        if not chunk:
            continue
        for piece in _as_list(chunk, limit=18):
            if piece in seen or len(piece) < 2:
                continue
            seen.add(piece)
            raw_terms.append(piece)
        if len(raw_terms) >= 18:
            break
    return decomposer.compact_strategy_terms(raw_terms or [question], limit=10)


def _build_query_strategy_fallback(item: dict, reason: str = "") -> dict:
    question = clean_text(item.get("question"))
    if not question:
        question = "红楼梦问题理解"
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    fallback_terms = _query_strategy_fallback_terms(question)
    if not fallback_terms:
        fallback_terms = ["红楼梦", "人物", "原文", "章节"]
    anchor_terms = _as_list(requirements, limit=6)
    return {
        "question_center": question[:90],
        "experience_paths_used": ["人物关系轴", "人物-物象-回目交叉核验"],
        "library_routes_used": ["人物库", "物象空间轴", "全文词 -> 候选 -> 库轴复核 -> 原文", "segments"],
        "strategy_reason": f"由于查询词路入口未回传结构化结果（{clean_text(reason)}），使用保底规则先按问题核心词执行。",
        "next_action_directive": "先按主问题人物、物象和回目关键词检索候选，再回到原文核验；缺口再补查。",
        "term_roles": {
            "primary_characters": _as_list((task_intent.split("-") if task_intent else question), limit=6),
            "primary_objects": [],
            "scene_terms": anchor_terms,
            "primary_terms": fallback_terms,
            "normalization_terms": [],
            "expansion_terms": [],
            "anchor_terms": anchor_terms,
            "exclusion_terms": [],
        },
        "evidence_upgrade_rule": "选取有 segment_no 或 chapter_no 的候选并保留原文足证线索。",
        "fallback_plan": "首轮不足时，补查关系词、场景词和事件词，优先补齐原问题主线候选。",
        "search_terms": fallback_terms,
        "compound_groups": [fallback_terms[:2]],
        "preferred_libraries": ["characters", "objects_axis", "spaces_axis", "segments", "chapters", "search_documents/search_documents_fts"],
        "source_order": "先语义聚拢中心库人物/物象表轴，再原文真源复核。",
        "guardrails": ["不得编造结论，须先回到原文再下判断。", "先抓主问题，再补充边界关系。"],
    }


def _query_flow_profile(question: str, task_intent: str, requirements: str, query_strategy_payload: dict) -> dict:
    payload = query_strategy_payload if isinstance(query_strategy_payload, dict) else {}
    terms = _strategy_execution_terms(payload, _as_list(payload.get("search_terms"), limit=36))
    roles = payload.get("term_roles") if isinstance(payload.get("term_roles"), dict) else {}
    primary_characters = _as_list(roles.get("primary_characters"), limit=8)
    primary_objects = _as_list(roles.get("primary_objects"), limit=8)
    primary_terms = _as_list(roles.get("primary_terms"), limit=10)
    compound_groups = _compound_groups_from_payload(payload)
    question_text = clean_text(question)
    text = clean_text(f"{question}\n{task_intent}\n{requirements}\n{payload.get('question_center', '')}\n{payload.get('source_order', '')}")
    deep_text = text
    for negative in ("先不要文章", "不要文章", "不需要文章", "不用文章", "先不写文章"):
        deep_text = deep_text.replace(negative, "")
    for neutral in ("运行深度：标准", "运行深度:标准", "运行深度：普通", "运行深度:普通"):
        deep_text = deep_text.replace(neutral, "")
    deep_markers = (
        "深度分析",
        "深度研究",
        "深度报告",
        "长文",
        "文章",
        "论文",
        "总论",
        "体系",
        "哲学",
        "思想",
        "比较研究",
        "跨主题",
        "多主题",
        "十个",
        "十大",
    )
    global_coverage_markers = ("全文", "120回", "全书", "全局", "全量", "完整", "所有回目", "全部回目")
    relation_markers = ("关系", "关联", "共现", "共同出现", "一起", "和", "与", "物象", "器物", "信物", "空间物")
    is_relation = bool((primary_characters and primary_objects) or len(compound_groups) >= 2)
    relation_keyword = any(marker in text for marker in relation_markers)
    profile_term_count = len(_as_list(primary_characters + primary_objects + primary_terms, limit=12))
    is_relation = is_relation or (relation_keyword and profile_term_count >= 2)
    is_short_question = len(question_text) <= 520
    has_deep_request = any(marker in deep_text for marker in deep_markers)
    has_global_coverage = any(marker in text for marker in global_coverage_markers)

    if is_relation and is_short_question and not has_deep_request and not has_global_coverage:
        return {
            "key": "fast_relation",
            "name": "短平快关系题",
            "reason": "本题中心清楚，主要是人物/物象/空间等对象之间的关系查证；需要快而准，不需要把每个底层表都升格为前台主过程。",
            "core_terms": terms[:8],
            "primary_characters": primary_characters,
            "primary_objects": primary_objects,
            "primary_terms": primary_terms,
            "steps": [
                "入口词门只保留核心对象和必要库线",
                "工程完整查回候选包",
                "过程判别只采用能支撑关系的产物",
                "材料池判定后精读、原文通读摘抄和回显",
                "仅在核心关系缺证时补查一次",
            ],
            "display_priority": ["红楼解语", "写作前原文追证摘抄", "精读材料词", "原文锚点/证据依据", "材料池判定", "问题拆解与库线", "内部表格"],
        }

    if is_relation and has_global_coverage and not has_deep_request:
        return {
            "key": "global_relation",
            "name": "全局覆盖关系题",
            "reason": "用户要求从全文/120回/全局材料中找重点；这表示覆盖范围要全，不表示把全部候选长表直接升格为深链。应先用人物库、pm 映射、段落库和库轴索引全局缩圈，再让 Codex 判别重点材料。",
            "core_terms": terms[:10],
            "primary_characters": primary_characters,
            "primary_objects": primary_objects,
            "primary_terms": primary_terms,
            "steps": [
                "入口词门确定全局覆盖对象",
                "工程用库轴/pm/段落库全局缩圈",
                "P1/T1 代表候选先交 Codex 判别",
                "不足时再打开 P2/P3 补查",
                "材料池判定后精读、原文通读摘抄和回显",
            ],
            "display_priority": ["红楼解语", "写作前原文追证摘抄", "精读材料词", "原文锚点/证据依据", "材料池判定", "全局覆盖索引", "底账长表"],
        }

    if has_deep_request:
        return {
            "key": "deep_multi_axis",
            "name": "深链多轴题",
            "reason": "题目要求全量、深度、体系化或长文论证；必须保留多轴展开、二次补查和材料精读。",
            "core_terms": terms[:12],
            "primary_characters": primary_characters,
            "primary_objects": primary_objects,
            "primary_terms": primary_terms,
            "steps": [
                "入口词门定多轴路线",
                "工程完整出包",
                "过程判别决定补查/降级/停止",
                "材料池逐条判定",
                "精读材料词后先做写作前原文追证摘抄，再写最终回显",
            ],
            "display_priority": ["红楼解语", "写作前原文追证摘抄", "精读材料词", "原文锚点/证据依据", "材料池判定", "过程判别", "全部过程文件"],
        }

    return {
        "key": "standard",
        "name": "标准出库题",
        "reason": "题目不是纯短链关系题，也未要求深链长论；按标准严谨链路运行，并由 Codex 判别门决定是否补查。",
        "core_terms": terms[:10],
        "primary_characters": primary_characters,
        "primary_objects": primary_objects,
        "primary_terms": primary_terms,
        "steps": [
            "入口词门定路线",
            "工程查回候选包",
            "过程判别",
            "材料池判定",
            "精读材料词",
            "最终回显",
        ],
        "display_priority": ["红楼解语", "写作前原文追证摘抄", "精读材料词", "原文锚点/证据依据", "材料池判定", "过程判别"],
    }


def _flow_profile_route_context(profile: dict) -> str:
    if not isinstance(profile, dict) or not clean_text(profile.get("key")):
        return ""
    steps = "；".join(_as_list(profile.get("steps"), limit=8))
    display_priority = " > ".join(_as_list(profile.get("display_priority"), limit=8))
    core_terms = "、".join(_as_list(profile.get("core_terms"), limit=12))
    lines = [
        "Codex流程档位",
        f"档位：{clean_text(profile.get('name'))}",
        f"理由：{clean_text(profile.get('reason'))}",
        f"核心执行词：{core_terms}",
        f"自然流程：{steps}",
        f"前台显示优先级：{display_priority}",
    ]
    if clean_text(profile.get("key")) == "fast_relation":
        lines.extend(
            [
                "短平快约束：search_terms 保持核心对象，不把别名、情绪词、动作词、地点词、回目词自动升格为主查词。",
                "短平快补查：只有核心关系缺少原文锚点或材料池无法支撑原问题时，才补查一次；材料够用时直接进入材料判定、精读和最终回显。",
                "短平快展示：底层表可以完整保存，但前台优先显示人读得懂的红楼解语、精读材料、原文锚点和材料判定。",
            ]
        )
    if clean_text(profile.get("key")) == "global_relation":
        lines.extend(
            [
                "全局覆盖约束：全文/120回表示覆盖范围，不表示把所有候选长表直接升为深链主过程。",
                "全局覆盖起手：先走人物库、pm 映射、段落库和库轴索引缩圈；全文词网络只作补漏和反证，不与主路径同权竞争。",
                "全局覆盖判别：判别门优先读取 P1/T1 代表候选和全局覆盖索引；完整长表留在底账，只有 Codex 指明缺口时再打开。",
            ]
        )
    return "\n".join(lines)


def _flow_profile_prompt_note(result: dict) -> str:
    profile = result.get("flow_profile") if isinstance(result.get("flow_profile"), dict) else {}
    if not profile:
        return "未标注流程档位；按标准出库题处理，但仍由 Codex 判别门决定采用、降级、补查或停止。"
    note = _flow_profile_route_context(profile)
    if clean_text(profile.get("key")) == "fast_relation":
        note += "\n本题按短平快关系题理解：严谨门不取消，但每一道门都要优先收束核心关系，避免把过程表、扩展词和背景锚点膨胀成主答案。"
    if clean_text(profile.get("key")) == "global_relation":
        note += "\n本题按全局覆盖关系题理解：覆盖必须全局，但每一道门都要先交给 Codex 可读的缩圈索引；底账全量保留，判别输入不直接膨胀。"
    return note


def _run_codex_query_strategy(item: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    if not request_id or not question:
        return {"ok": False, "route_context": "", "error": "缺少 request_id 或 question"}

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = CODEX_RUN_DIR / f"{request_id}_query_strategy_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_query_strategy_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_query_strategy_events.log"
    existing_preflight_context = _query_strategy_existing_preflight_context()
    prompt = f"""你是红楼梦工程的 Codex 查询词路员。你现在只做“查证前的 AI 判断”，不要回答题目，不要写文章，不要为单题加门禁。
这个旧召回模块不是新前门；没有入口词、对象边界和来源顺序时，只能回到 126/130 补打卡，不进入查证。

用户问题：
{question}

页面触发词/任务意图：
{task_intent or "红楼解语"}

附加要求：
{requirements or "无"}

任务记忆卡：
- 当前阶段：查询词路
- 本阶段只做：判断查哪些词、语义聚拢中心库内部哪些表轴、哪些原文方向，不回答题目。
- 原问题：{question}
- 固定原则：先抓住原问题，再给本地工程查证路线；查询词服务问题，不让问题迁就查询词。

已有工程前置策略（必须先读；这是现有工程卡，不是新建规则）：
{existing_preflight_context}

请根据题意、触发词、已有前置策略、经验值总账和语义聚拢中心库结构，判断这道题应该怎样查询。你要输出给本地程序执行的查询词路；本地程序只会按你的策略去查中心库内部表轴、查原文、保存证据。
你的拆题方向必须资料化：先判断要查中心库内部哪些表轴、哪些原文、哪些材料缺口和哪些二轮补证方向；不要把拆题变成观点提纲。

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不要回答问题，不要写结论。
3. experience_paths_used 必须填写你从现有经验仓里采用的路径名称，例如“物象域”“共现查证线”“场域/空间域”；不要编造新路径。
4. library_routes_used 必须填写你从现有库线骨架里采用的中心表轴或自然流名称，例如“A类原文真源层”“物象空间诗词时间层”“全文词 -> 候选 -> 中心库表轴复核 -> 原文”。
5. strategy_reason 用一句话说明你为什么这样定路径，只说查证理由，不说题目结论。
6. next_action_directive 写给本地工程的下一步动作，例如“按人物+物象复合轴查语义聚拢中心库内部表轴，再回原文真源复核”。
7. term_roles 用对象形式说明主查人物、主查物象、场景词、主查词、归一词、扩展词、背景锚点、反证/排除词；这帮助工程区分词的用途。
8. evidence_upgrade_rule 写材料升级条件：什么样的候选可以进入材料池判定。
9. fallback_plan 写首轮不足时的补查办法，不要写最终答案。
10. search_terms 是第一轮执行词，不是词库总表；请保持紧凑，优先放核心人物、核心物象、核心原句或核心事件，一般 6-12 个以内。人物执行词只放归一人物实体；别名、称谓、扩展词、背景锚点和排除词放到 term_roles，不要塞进 search_terms。
11. preferred_libraries 为兼容旧接口保留字段名，但内容只能写语义聚拢中心库内部优先表轴，例如 characters、character_alias_solidification、person_segment_edges、objects_axis、spaces_axis、literary_texts_axis、events、segments、chapters、evidence_edges、search_documents/search_documents_fts；不得写工程文件、产物包或另一个外部库路径。
12. source_order 写查询顺序，例如“先中心库人物表轴后原文”“先中心库物象表轴后原文”“中心库与原文双向”“先全文词表轴后对象轴复核”。对象词不要被单一路径锁死：中心库全文词表轴用于找全，变量/对象表轴用于定点，最后用人物、空间、季节、事件、距离/共场交叉和原文裁判。
13. compound_groups 写本题“强复合轴”：只放本题必须共同成立的核心对象组，例如归一人物实体组 + 物象组；人物组不要堆别名，地点、回目、情绪、动作、题、住、哭、泪等辅助词也不要放进强复合组。辅助词放 anchor_terms、term_roles.expansion_terms 或 guardrails。
14. anchor_terms 写只能作背景锚点或空间根证的词，例如地点、回目、原句入口；它们帮助组证，但不能单独冒充答案。
15. guardrails 写本题容易误召回或串题的注意事项，只写通用查证注意，不写答案。可提醒：变量精确命中是强锚点但不是唯一入口；变量未登记不等于原文没有；不要因为 object=花 少就丢掉全文“花”字，也不要让 LIKE 泛化结果直接冒充主证。

JSON 格式：
{{
	  "question_center": "一句话说明问题中心",
	  "experience_paths_used": ["经验路径1", "经验路径2"],
	  "library_routes_used": ["库线路径1", "自然流1"],
	  "strategy_reason": "一句话说明查证路径理由，不回答题目",
	  "next_action_directive": "给本地工程的下一步查证指令",
	  "term_roles": {{
	    "primary_characters": ["主查人物1"],
	    "primary_objects": ["主查物象1"],
	    "scene_terms": ["场景词1"],
	    "primary_terms": ["主查词1"],
	    "normalization_terms": ["归一词1"],
	    "expansion_terms": ["扩展词1"],
	    "anchor_terms": ["背景锚点1"],
	    "exclusion_terms": ["排除词1"]
	  }},
	  "evidence_upgrade_rule": "候选材料升级为材料池待判定的条件",
	  "fallback_plan": "首轮不足时的补查方案",
	  "search_terms": ["第一轮执行词1", "第一轮执行词2"],
	  "compound_groups": [["同义词1", "同义词2"], ["同义词3", "同义词4"]],
	  "anchor_terms": ["背景锚点1", "背景锚点2"],
	  "preferred_libraries": ["中心库表轴1", "中心库表轴2"],
	  "source_order": "查询顺序",
	  "guardrails": ["注意1", "注意2"]
}}
"""
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_QUERY_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="query_strategy",
        )
    except Exception as exc:
        return {"ok": False, "route_context": "", "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "route_context": "", "error": _readable_codex_error(event_path, 2000)}

    answer = _read_limited(last_path, 20000)
    payload = _json_from_codex_text(answer)
    if not payload:
        return {"ok": False, "route_context": "", "error": "Codex 查询词路未返回有效 JSON"}

    raw_terms = _as_list(payload.get("search_terms"), limit=36)
    terms = _strategy_execution_terms(payload, raw_terms)
    libraries = _as_list(payload.get("preferred_libraries"), limit=18)
    guardrails = _as_list(payload.get("guardrails"), limit=8)
    experience_paths = _as_list(payload.get("experience_paths_used"), limit=12)
    library_routes = _as_list(payload.get("library_routes_used"), limit=12)
    strategy_reason = clean_text(payload.get("strategy_reason"))
    next_action_directive = clean_text(payload.get("next_action_directive"))
    term_roles_raw = payload.get("term_roles")
    term_role_lines: list[str] = []
    if isinstance(term_roles_raw, dict):
        role_labels = {
            "primary_characters": "主查人物",
            "primary_objects": "主查物象",
            "scene_terms": "场景词",
            "primary_terms": "主查词",
            "normalization_terms": "归一词",
            "expansion_terms": "扩展词",
            "anchor_terms": "背景锚点",
            "exclusion_terms": "排除词",
        }
        for key, label in role_labels.items():
            values = _as_list(term_roles_raw.get(key), limit=12)
            if values:
                term_role_lines.append(f"{label}={'、'.join(values)}")
    evidence_upgrade_rule = clean_text(payload.get("evidence_upgrade_rule"))
    fallback_plan = clean_text(payload.get("fallback_plan"))
    compound_groups = _compound_groups_from_payload(payload)
    anchor_terms = _as_list(payload.get("anchor_terms"), limit=18)
    center = clean_text(payload.get("question_center"))
    order = clean_text(payload.get("source_order"))
    route_lines = [
        "Codex查询词路",
        f"Codex问题中心：{center}",
        f"Codex经验路径：{'、'.join(experience_paths)}",
        f"Codex库线路径：{'、'.join(library_routes)}",
        f"Codex策略理由：{strategy_reason}",
        f"Codex下一步指令：{next_action_directive}",
        f"Codex词角色：{'；'.join(term_role_lines)}",
        f"Codex材料升级条件：{evidence_upgrade_rule}",
        f"Codex补查方案：{fallback_plan}",
        f"Codex查询词：{'、'.join(terms)}",
        f"Codex强复合：{' + '.join('/'.join(group) for group in compound_groups)}",
        f"Codex背景锚点：{'、'.join(anchor_terms)}",
        f"Codex优先库：{'、'.join(libraries)}",
        f"Codex查证顺序：{order}",
        f"Codex注意事项：{'；'.join(guardrails)}",
    ]
    return {
        "ok": True,
        "payload": payload,
        "route_context": "\n".join(route_lines),
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "terms": terms,
        "libraries": libraries,
    }


def _process_judgment_source_paths(result: dict, pass_index: int = 0) -> list[Path]:
    paths: list[Path] = []
    paths.extend(_result_direct_paths(result, ("codex_process_judgment_md", "codex_process_judgment_json")))
    if pass_index > 0:
        active = _latest_workflow_result(result)
        active_package = Path(clean_text(active.get("package") or active.get("package_dir")))
        packages = [active_package] if active_package.exists() and active_package.is_dir() else _result_packages(result)[:1]
    else:
        packages = _result_packages(result)
    for package in packages:
        for key in (
            "process_inventory_md",
            "final_reading_gate_md",
            "reading_md",
            "cards",
            "triaged_csv",
            "review_csv",
            "process_inventory_json",
            "question_judgment_md",
            "keyword_precheck_json",
            "library_flow_md",
            "library_flow_json",
            "question_tree",
            "writing_md",
            "workflow_status_md",
        ):
            filename = closed_loop.CORE_FILES.get(key)
            if not filename:
                continue
            path = package / filename
            if path.exists():
                paths.append(path)
    paths.extend(_result_direct_paths(result, ("status_file", "status_json")))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_process_judgment_prompt(item: dict, result: dict, pass_index: int = 0) -> str:
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    flow_note = _flow_profile_prompt_note(result)
    blocks: list[str] = []
    source_limit = 14 if pass_index > 0 else 22
    for path in _process_judgment_source_paths(result, pass_index=pass_index)[:source_limit]:
        content = _read_process_judgment_preview(path, pass_index=pass_index)
        if not content:
            continue
        blocks.append(
            "\n".join(
                [
                    f"### 过程产物：{path.name}",
                    f"路径：{path}",
                    "",
                    content,
                ]
            )
        )
    materials = "\n\n---\n\n".join(blocks) or "工程没有返回可读取过程产物。"
    memory_card = _task_memory_card_for_prompt(
        result,
        question,
        "全流程过程判别",
        "判断当前工程产物是否抓住原问题、是否需要补查、是否能进入材料池判定。",
    )
    return f"""你是红楼梦工程的 Codex 全流程过程判别官。你现在只做“过程筛查和下一步决策”。这里不是靠禁词防止误写，而是靠来源约束防止半路答题：你的每个判断、取舍和补查决定，都必须来自用户原题或下面工程已经供给的产物。

用户问题：
{question}

任务意图：
{task_intent or "红楼解语"}

附加要求：
{requirements or "无"}

流程档位：
{flow_note}

{memory_card}

这是第 {pass_index + 1} 次过程判别。你要先读“全流程产物与 Codex 判别门”：它是本次运行的前置总规矩，不是固定流水线。当前定位是：Codex 策略是“方向盘 + 调度单”，本地工程是“查找器 + 材料包生成器”。底层工程可以保留完整底账，但 Codex 必须按查询路径层调度：P1 主路径先判别，P2 补强路径在 P1 不足时采用，P3 全文搜索只作补漏，P4 底账只在有明确缺口时打开。这里的“跳过”是指不采用、不升级、不进入下一门，不是要求底层工程删除底账。凡已经产生词、表、卡、候选和原文材料的位置，都必须经你判别后才能进入下一步。然后再判断本地工程在关键词、库线、关键段落、关键诗词、关键原文和候选材料上是否已经抓住了用户问题。

过程产物如下：

{materials}

真实库表字段提示（只用于提出补查路线；不要凭旧称或直觉编造 SQL 字段）：
{_database_schema_guardrail()}

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不要展开成给用户看的回答，不要写结论段落；本步骤只允许写“来自哪里、怎样判、下一步查什么”。
3. 你要逐项检查：问题判断程序、关键词网络、库线、问题树、证据池、复核表、回读材料是否支撑原问题，并为每类产物给出调度动作。
4. 本地模块的 score、排序、机器角色、摘要、候选卡片都不能直接当证据结论；你只能把它们判为：有效候选、背景候选、噪音候选、需补查，并写清来源依据。
5. accepted_keywords、missing_keywords、key_segment_targets、key_text_targets、next_search_decisions 都必须能说明来源：来自用户原题、哪个工程文件、哪个字段、哪个段落/回目，或从哪个材料缺口推导出来。
6. proceed_to_material_judgment 判断的是“能否交给 Codex 材料池判定官逐条判定”，不是判断“是否已经有人工可写作证据”。`human_decision=待复核`、`usable_rows=0`、`可写作证据=0` 是正常状态，正说明下一步应该由 Codex 材料池判定来完成取舍；除非候选为空、来源链/段落号/原文痕迹严重缺失、或题目中心明显跑偏，否则不要因为待复核而阻断。
7. 如果已经有 T1/T2 人读分层、主证候选柜、原子段号、summary/quote/原文回收、来源链或召回理由，就应优先进入材料池判定，让 Codex 决定可用、背景、不可用或需补证；不要要求过程判别门先完成人工复核。
8. supplement_required 为 true 时，必须给出 supplement_route_context，里面要有明确查询词、库、原文方向；本地工程只按这条补查，不自己猜。若补查后已有清晰主证候选层，即使底账仍保留很多候选，也应进入材料池判定，而不是再次停在等待补证。
9. 如果你想提出新关键词，只能作为“补查词”提出，并说明它是从用户原题或已有材料缺口推导来的；不能把新关键词直接扩写成答案。
10. 不要求每题走完所有节点；route_decision 要说明本题采用短链、深链、多轴链、侧路补查还是停止。跳过某节点时必须说明它是“底层可保留备查，但本题不进入下一门”。
11. product_dispatch 是本步骤核心矩阵；每个动作只能是：采用、降级、补查、跳过、停止。顺序可以清楚，但不能死板；清楚用于追踪，不死板用于保留查询发散。
12. 如果工程材料中有 codex_query_lane / human_reading_tier / candidate_display_policy 字段，必须优先按这些字段判别：先读 P1/T1，P1 不足再开 P2/T2，P3 只作查漏，P4 不得主动升格。

JSON 格式：
{{
  "process_reading": "你读完整个过程包后的总体判断",
  "route_decision": "本题自然流程选择：短链/深链/多轴链/侧路补查/停止，并说明哪些产物进入下一门，哪些只保留备查",
  "product_dispatch": [
    {{"product": "问题判断程序/关键词网络/库线/问题树/证据池/复核表/回读材料", "action": "采用/降级/补查/跳过/停止", "source_basis": "来自哪个工程产物或原题", "reason": "为什么这样调度", "next_gate": "进入哪一道门或只留备查"}}
  ],
  "stage_judgments": [
    {{"stage": "问题判断程序/关键词网络/库线/问题树/证据池/复核表/回读材料", "status": "通过/需补查/有偏移/不可用", "source_basis": "判断依据来自哪个文件/字段/原题", "reason": "理由"}}
  ],
  "accepted_keywords": ["已确认有效的关键词"],
  "missing_keywords": ["还应补的关键词"],
  "key_segment_targets": ["应重点回看的段落号或章节"],
  "key_text_targets": ["应重点找的原文、诗词、回目、物象或空间文字"],
  "source_grounding": [
    {{"decision": "某个关键词/段落/补查方向", "source": "用户原题或工程文件名/字段/段落号", "basis": "为什么只能从该来源得出"}}
  ],
  "noise_or_rejected": ["疑似跑偏、串题、不能支撑原问题的候选"],
  "next_search_decisions": [
    {{"direction": "补查方向", "terms": ["词1", "词2"], "libraries": ["库1"], "source_basis": "来自原题/哪份材料的缺口", "why": "为什么要补查"}}
  ],
  "supplement_required": true,
  "supplement_route_context": "给本地工程的二轮补查指令；如果不补查则为空",
  "proceed_to_material_judgment": false,
  "reason_to_proceed_or_stop": "为什么进入/不进入材料池判定"
}}
"""


def _render_process_judgment_markdown(payload: dict, request_id: str, question: str, pass_index: int = 0) -> str:
    def bullet_list(value: object) -> list[str]:
        items = _as_list(value, limit=40)
        return [f"- {item}" for item in items] or ["- 暂无。"]

    lines = [
        "# Codex 全流程过程判别",
        "",
        f"- 请求：{request_id}",
        f"- 轮次：{pass_index + 1}",
        f"- 问题：{question}",
        f"- 是否需要补查：{'是' if payload.get('supplement_required') else '否'}",
        f"- 是否允许进入材料池判定：{'是' if payload.get('proceed_to_material_judgment') else '否'}",
        "",
        "## 总体判断",
        "",
        clean_text(payload.get("process_reading")) or "未写明。",
        "",
        "## 本题流程选择",
        "",
        clean_text(payload.get("route_decision")) or "未写明。",
        "",
        "## 产物调度矩阵",
        "",
    ]
    product_dispatch = payload.get("product_dispatch")
    if isinstance(product_dispatch, list) and product_dispatch:
        for item in product_dispatch:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {clean_text(item.get('product'))}｜动作：{clean_text(item.get('action'))}｜来源：{clean_text(item.get('source_basis')) or '未写明'}｜下一门：{clean_text(item.get('next_gate')) or '未写明'}｜原因：{clean_text(item.get('reason'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
        "",
        "## 分步骤判别",
        "",
        ]
    )
    stages = payload.get("stage_judgments")
    if isinstance(stages, list) and stages:
        for item in stages:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {clean_text(item.get('stage'))}｜{clean_text(item.get('status'))}｜来源：{clean_text(item.get('source_basis')) or '未写明'}｜{clean_text(item.get('reason'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 已确认有效关键词", "", *bullet_list(payload.get("accepted_keywords"))])
    lines.extend(["", "## 缺失关键词", "", *bullet_list(payload.get("missing_keywords"))])
    lines.extend(["", "## 关键段落/章节目标", "", *bullet_list(payload.get("key_segment_targets"))])
    lines.extend(["", "## 关键原文/诗词/物象/空间文字", "", *bullet_list(payload.get("key_text_targets"))])
    lines.extend(["", "## 来源约束记录", ""])
    source_grounding = payload.get("source_grounding")
    if isinstance(source_grounding, list) and source_grounding:
        for item in source_grounding:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {clean_text(item.get('decision'))}｜来源：{clean_text(item.get('source'))}｜依据：{clean_text(item.get('basis'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 噪音或跑偏候选", "", *bullet_list(payload.get("noise_or_rejected"))])
    lines.extend(["", "## 下一轮查证决定", ""])
    decisions = payload.get("next_search_decisions")
    if isinstance(decisions, list) and decisions:
        for item in decisions:
            if not isinstance(item, dict):
                continue
            terms = "、".join(_as_list(item.get("terms"), limit=14))
            libraries = "、".join(_as_list(item.get("libraries"), limit=8))
            lines.append(
                f"- {clean_text(item.get('direction'))}｜词：{terms or '无'}｜库：{libraries or '无'}｜来源：{clean_text(item.get('source_basis')) or '未写明'}｜原因：{clean_text(item.get('why'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## 给本地工程的补查指令",
            "",
            clean_text(payload.get("supplement_route_context")) or "无需补查。",
            "",
            "## 进入或停止理由",
            "",
            clean_text(payload.get("reason_to_proceed_or_stop")) or "未写明。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _is_process_judgment_network_retry_error(text: str) -> bool:
    return _is_network_retry_signal(text)


def _is_network_retry_signal(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False
    markers = (
        "stream disconnected",
        "connection",
        "connecting",
        "reconnecting",
        "error sending request",
        "failed to send request",
        "could not resolve host",
        "chatgpt.com",
        "wham/apps",
        "timeout",
    )
    return any(marker in lowered for marker in markers)


def _is_fast_hit_material_judgment_fallback_needed(item: dict, result: dict, error: str) -> bool:
    if not _is_network_retry_signal(error):
        return False

    flow_profile = result.get("flow_profile")
    if isinstance(flow_profile, dict) and clean_text(flow_profile.get("key")) == "fast_relation":
        return True

    route_text = clean_text(result.get("route_mode") or result.get("suggested_state") or result.get("next_action"))
    if any(token in route_text for token in ("短平快", "一次命中", "快速直达", "可直接写")):
        return True

    return False


def _build_material_judgment_network_fallback_payload(item: dict, result: dict, reason: str = "") -> dict:
    question = clean_text(item.get("question"))
    route_text = clean_text(result.get("route_mode") or result.get("suggested_state") or result.get("next_action"))
    center = question or clean_text(result.get("question_center")) or "问题定位"
    if route_text:
        center = f"{center}｜{route_text}"

    return {
        "question_center": center,
        "material_reading": "材料池判定阶段遇到网络异常。本兜底只保留流程状态，不调用章节表、人物表或任何题型模板伪造答案；后续必须依赖已生成材料或重新补证。",
        "usable_materials": [],
        "background_materials": [],
        "rejected_materials": [],
        "evidence_gaps": [
            {
                "gap": "材料池判定未取得 Codex 有效返回",
                "reason": "网络异常时不允许用本地知识表替代材料判定。",
                "next_action": "重试材料池判定，或让后续流程读取已存在的可追溯材料后再写。",
            }
        ],
        "next_search_decisions": [],
        "writing_mode": "暂不写",
        "final_instruction_to_writer": "不要根据题型模板或本地知识表直接生成答案；只有材料池中已有可追溯命中时，才能进入快速直达写作。",
        "supplement_required": True,
        "proceed_to_material_judgment": False,
        "reason_to_proceed_or_stop": "网络异常导致材料池判定缺席；为避免伪命中，暂停直达并等待重试或真实材料补证。",
        "fallback_network_retry": True,
        "fallback_network_error": clean_text(reason),
    }


def _is_fast_hit_process_judgment_fallback_needed(item: dict, result: dict, pass_index: int, error: str) -> bool:
    if pass_index != 0:
        return False
    if not _is_process_judgment_network_retry_error(error):
        return False

    flow_profile = result.get("flow_profile")
    if isinstance(flow_profile, dict) and clean_text(flow_profile.get("key")) == "fast_relation":
        return True

    route_text = clean_text(result.get("route_mode") or result.get("suggested_state") or result.get("next_action"))
    if any(token in route_text for token in ("短平快", "一次命中", "快速直达", "可直接写")):
        return True

    return False


def _build_process_judgment_network_fallback_payload(item: dict, result: dict, reason: str = "") -> dict:
    question = clean_text(item.get("question"))
    flow_profile = result.get("flow_profile")
    if not isinstance(flow_profile, dict):
        flow_profile = {}
    accepted_keywords = _query_strategy_fallback_terms(question)
    if not accepted_keywords:
        accepted_keywords = _as_list(question, limit=8)
    profile_name = clean_text(flow_profile.get("name")) or "短平快关系题"

    return {
        "process_reading": "过程判别网络层不稳，采用保底流程：保留本地已生成工程产物，直接进入材料池判定。",
        "route_decision": f"短链兜底：{profile_name} 触发网络兜底，跳过过程判别继续推进材料池。",
        "product_dispatch": [
            {
                "product": "问题判断程序/关键词网络/库线/问题树/证据池",
                "action": "采用",
                "source_basis": "用户题目与已生成工程产物",
                "reason": "短链题目边界清晰，过程判别阶段的网络失败可降级为保守直推。",
                "next_gate": "材料池判定",
            },
            {
                "product": "复核表/回读材料",
                "action": "保留",
                "source_basis": "已生成的本地工程产物",
                "reason": "当前先保证链路连续，不在过程判别阶段重复发起联网。",
                "next_gate": "材料池判定",
            },
        ],
        "stage_judgments": [
            {
                "stage": "问题判断程序",
                "status": "通过",
                "source_basis": "用户题目",
                "reason": "题干清晰、任务可落到已生成证据路径。",
            },
            {
                "stage": "过程判别",
                "status": "有偏移",
                "source_basis": "Codex网络返回状态",
                "reason": "过程判别返回异常，允许保底继续推进。",
            },
        ],
        "accepted_keywords": accepted_keywords,
        "missing_keywords": [],
        "key_segment_targets": ["优先使用材料池内可追溯锚点"],
        "key_text_targets": ["直接相关原文、同段上下文、可核验证据"],
        "source_grounding": [
            {
                "decision": "先从材料池与写作前回读入口继续",
                "source": "本地工程已生成的00I/00L/回目产物",
                "basis": "短链问题优先保证链路闭环，不因过程判别网络失败回退重复造包。",
            }
        ],
        "noise_or_rejected": ["无"],
        "next_search_decisions": [],
        "supplement_required": False,
        "supplement_route_context": "",
        "proceed_to_material_judgment": True,
        "reason_to_proceed_or_stop": "网络异常是环境问题，不是题目证据问题；先让材料池判定接管，保守完成链路。",
        "fallback_network_retry": True,
        "fallback_network_error": clean_text(reason),
    }


def _run_codex_process_judgment(item: dict, result: dict, pass_index: int = 0) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    if not request_id or not question:
        return {"ok": False, "error": "缺少 request_id 或 question"}

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    output_dir = package if package.exists() and package.is_dir() else CODEX_RUN_DIR
    suffix = f"{request_id}_pass{pass_index + 1}"
    prompt_path = CODEX_RUN_DIR / f"{suffix}_process_judgment_prompt.md"
    last_path = CODEX_RUN_DIR / f"{suffix}_process_judgment_last_message.md"
    event_path = CODEX_RUN_DIR / f"{suffix}_process_judgment_events.log"
    json_path = output_dir / f"00K_Codex全流程过程判别_{suffix}.json"
    md_path = output_dir / f"00K_Codex全流程过程判别_{suffix}.md"

    prompt = _build_codex_process_judgment_prompt(item, result, pass_index=pass_index)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_PROCESS_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="process_judgment",
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if _is_fast_hit_process_judgment_fallback_needed(item, result, pass_index, error):
            fallback_payload = _build_process_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_process_judgment_markdown(fallback_payload, request_id, question, pass_index=pass_index), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "supplement_required": bool(fallback_payload.get("supplement_required")),
                "proceed_to_material_judgment": bool(fallback_payload.get("proceed_to_material_judgment")),
                "supplement_route_context": clean_text(fallback_payload.get("supplement_route_context")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}
    if proc.returncode != 0:
        error = _read_limited(event_path, 3000)
        if _is_fast_hit_process_judgment_fallback_needed(item, result, pass_index, error):
            fallback_payload = _build_process_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_process_judgment_markdown(fallback_payload, request_id, question, pass_index=pass_index), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "supplement_required": bool(fallback_payload.get("supplement_required")),
                "proceed_to_material_judgment": bool(fallback_payload.get("proceed_to_material_judgment")),
                "supplement_route_context": clean_text(fallback_payload.get("supplement_route_context")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}

    answer = _read_limited(last_path, 50000)
    payload = _json_from_codex_text(answer)
    if not payload:
        error = "Codex 过程判别未返回有效 JSON"
        if _is_fast_hit_process_judgment_fallback_needed(item, result, pass_index, error):
            fallback_payload = _build_process_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_process_judgment_markdown(fallback_payload, request_id, question, pass_index=pass_index), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "supplement_required": bool(fallback_payload.get("supplement_required")),
                "proceed_to_material_judgment": bool(fallback_payload.get("proceed_to_material_judgment")),
                "supplement_route_context": clean_text(fallback_payload.get("supplement_route_context")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}

    write_json(json_path, payload)
    md_path.write_text(_render_process_judgment_markdown(payload, request_id, question, pass_index=pass_index), encoding="utf-8")
    return {
        "ok": True,
        "payload": payload,
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "supplement_required": bool(payload.get("supplement_required")),
        "proceed_to_material_judgment": bool(payload.get("proceed_to_material_judgment")),
        "supplement_route_context": clean_text(payload.get("supplement_route_context")),
    }


def _supplement_route_context_from_process(process_judgment: dict) -> str:
    payload = process_judgment.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}
    explicit = clean_text(payload.get("supplement_route_context"))
    lines = ["Codex过程判别补查"]
    if explicit:
        lines.append(explicit)
    decisions = payload.get("next_search_decisions")
    if isinstance(decisions, list):
        for item in decisions[:6]:
            if not isinstance(item, dict):
                continue
            terms = "、".join(_as_list(item.get("terms"), limit=14))
            libraries = "、".join(_as_list(item.get("libraries"), limit=8))
            lines.append(
                f"补查方向：{clean_text(item.get('direction'))}｜补查词：{terms}｜补查库：{libraries}｜原因：{clean_text(item.get('why'))}"
            )
    return "\n".join(line for line in lines if clean_text(line))


def _material_judgment_source_paths(result: dict) -> list[Path]:
    paths: list[Path] = []
    paths.extend(_result_direct_paths(result, ("codex_process_judgment_md", "codex_process_judgment_json")))
    for package in _result_packages(result):
        for key in (
            "codex_close_reading_gate_md",
            "final_reading_gate_md",
            "reading_md",
            "cards",
            "triaged_csv",
            "review_csv",
            "process_inventory_md",
            "question_tree",
            "question_judgment_md",
            "library_flow_md",
            "experience_entry_md",
            "writing_md",
            "review_coverage_md",
            "review_firstpass_cards_md",
            "source_verify_md",
            "workflow_status_md",
        ):
            filename = closed_loop.CORE_FILES.get(key)
            if not filename:
                continue
            path = package / filename
            if path.exists():
                paths.append(path)
    paths.extend(_result_direct_paths(result, ("status_file", "status_json")))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_material_judgment_prompt(item: dict, result: dict) -> str:
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    flow_note = _flow_profile_prompt_note(result)
    material_blocks: list[str] = []
    for path in _material_judgment_source_paths(result)[:18]:
        content = _read_limited(path, 18000)
        if not content:
            continue
        material_blocks.append(
            "\n".join(
                [
                    f"### 工程材料：{path.name}",
                    f"路径：{path}",
                    "",
                    content,
                ]
            )
        )
    materials = "\n\n---\n\n".join(material_blocks) or "工程没有返回可读取材料。"
    memory_card = _task_memory_card_for_prompt(
        result,
        question,
        "材料池判定",
        "把候选材料判为可用、背景、不可用或需补证，并决定能否进入精读聚拢池。",
    )
    return f"""你是红楼梦工程的 Codex 指挥中心。你现在处在“材料池判定”步骤：不要写最终答案，不要替题目作文，不要套旧模板；你只决定工程刚查回来的候选材料怎样使用，以及下一步能否进入写作。

用户问题：
{question}

任务意图：
{task_intent or "红楼解语"}

附加要求：
{requirements or "无"}

流程档位：
{flow_note}

{memory_card}

工程返回的候选材料如下。注意：本地工程只负责查找、取原文、保存候选；它的分数、排序、过程稿和旧名称都不能直接当作证据判断。你必须亲自读材料池、原子段、摘要和原文短摘，再决定材料角色。

{materials}

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不要回答用户问题，不要写文章。
3. `human_decision=待复核`、`可写作证据=0`、`usable_rows=0` 不是等待人工的理由；这一步本身就是由 Codex 完成材料判定。你要把候选逐条判为：可用、背景、不可用、需补证。
4. 判断依据必须来自 segment_no、chapter_no、summary、quote、source_trace、retrieval_reasons 或原文锚点；不得用本地 score 代替判断。
5. 如果材料和问题不支撑，要明确写 evidence_gaps 和 next_search_decisions。
6. 不允许本地模块替你决定主证、反证或结论；你才是本步骤的决定者。
7. writing_mode 只能是：可以写、谨慎写、先补证。
8. 如果写“先补证”，最终回答层只能输出补证说明，不能硬写完整结论。
9. 读取顺序必须遵守路径层：先判 P1 主路径和 T1A/T1B；只有 P1 不足、需要互证或有明确缺口时，才打开 P2 补强路径；P3 全文搜索只用于查漏，P4 底账只作保留。
10. 如果 P1 已经足以支撑回答，不要因为 P2/P3/P4 底账很多而要求继续补查；底账多不是证据不足。

JSON 格式：
{{
  "question_center": "本题真正要解决的问题",
  "material_reading": "你读完材料池后的总体判断",
  "usable_materials": [
    {{"segment_no": "段落号", "chapter_no": "回目", "use": "能证明什么", "reason": "为什么可用"}}
  ],
  "background_materials": [
    {{"segment_no": "段落号", "chapter_no": "回目", "use": "只能作什么背景", "reason": "为什么不能作主证"}}
  ],
  "rejected_materials": [
    {{"segment_no": "段落号", "chapter_no": "回目", "reason": "为什么不用"}}
  ],
  "evidence_gaps": ["还缺什么证据"],
  "next_search_decisions": [
    {{"direction": "下一轮查证方向", "terms": ["词1", "词2"], "libraries": ["库1"], "why": "为什么要查"}}
  ],
  "writing_mode": "可以写/谨慎写/先补证",
  "final_instruction_to_writer": "给最终红楼解语写作者的约束"
}}
"""


def _render_material_judgment_markdown(payload: dict, request_id: str, question: str) -> str:
    def rows(items: object, fields: tuple[str, ...]) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- 暂无。"]
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parts = [clean_text(item.get(field)) for field in fields if clean_text(item.get(field))]
            if parts:
                lines.append("- " + "｜".join(parts))
        return lines or ["- 暂无。"]

    lines = [
        "# Codex 指挥中心｜材料池判定",
        "",
        f"- 请求：{request_id}",
        f"- 问题：{question}",
        f"- 问题中心：{clean_text(payload.get('question_center'))}",
        f"- 写作许可：{clean_text(payload.get('writing_mode')) or '谨慎写'}",
        "",
        "## 总体判断",
        "",
        clean_text(payload.get("material_reading")) or "未写明。",
        "",
        "## 可用材料",
        "",
        *rows(payload.get("usable_materials"), ("segment_no", "chapter_no", "use", "reason")),
        "",
        "## 背景材料",
        "",
        *rows(payload.get("background_materials"), ("segment_no", "chapter_no", "use", "reason")),
        "",
        "## 不采用材料",
        "",
        *rows(payload.get("rejected_materials"), ("segment_no", "chapter_no", "reason")),
        "",
        "## 证据缺口",
        "",
    ]
    gaps = payload.get("evidence_gaps")
    if isinstance(gaps, list) and gaps:
        lines.extend(f"- {clean_text(item)}" for item in gaps if clean_text(item))
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 下一轮查证决定", ""])
    decisions = payload.get("next_search_decisions")
    if isinstance(decisions, list) and decisions:
        for item in decisions:
            if not isinstance(item, dict):
                continue
            terms = "、".join(_as_list(item.get("terms"), limit=12))
            libraries = "、".join(_as_list(item.get("libraries"), limit=8))
            lines.append(
                f"- {clean_text(item.get('direction'))}｜词：{terms or '无'}｜库：{libraries or '无'}｜原因：{clean_text(item.get('why'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## 给最终红楼解语的约束",
            "",
            clean_text(payload.get("final_instruction_to_writer")) or "最终回答必须按上述材料判定写作，不得把候选材料直接当结论。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _run_codex_material_judgment(item: dict, result: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    if not request_id or not question:
        return {"ok": False, "error": "缺少 request_id 或 question"}

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    output_dir = package if package.exists() and package.is_dir() else CODEX_RUN_DIR
    prompt_path = CODEX_RUN_DIR / f"{request_id}_material_judgment_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_material_judgment_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_material_judgment_events.log"
    json_path = output_dir / f"00I_Codex材料池判定_{request_id}.json"
    md_path = output_dir / f"00I_Codex材料池判定_{request_id}.md"

    prompt = _build_codex_material_judgment_prompt(item, result)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_MATERIAL_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="material_judgment",
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if _is_fast_hit_material_judgment_fallback_needed(item, result, error):
            fallback_payload = _build_material_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_material_judgment_markdown(fallback_payload, request_id, question), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "writing_mode": clean_text(fallback_payload.get("writing_mode")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}
    if proc.returncode != 0:
        error = _read_limited(event_path, 3000)
        if _is_fast_hit_material_judgment_fallback_needed(item, result, error):
            fallback_payload = _build_material_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_material_judgment_markdown(fallback_payload, request_id, question), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "writing_mode": clean_text(fallback_payload.get("writing_mode")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}

    answer = _read_limited(last_path, 60000)
    payload = _json_from_codex_text(answer)
    if not payload:
        error = "Codex 材料池判定未返回有效 JSON"
        if _is_fast_hit_material_judgment_fallback_needed(item, result, error):
            fallback_payload = _build_material_judgment_network_fallback_payload(item, result, error)
            write_json(json_path, fallback_payload)
            md_path.write_text(_render_material_judgment_markdown(fallback_payload, request_id, question), encoding="utf-8")
            return {
                "ok": True,
                "payload": fallback_payload,
                "prompt_path": str(prompt_path),
                "last_path": str(last_path),
                "json_path": str(json_path),
                "md_path": str(md_path),
                "writing_mode": clean_text(fallback_payload.get("writing_mode")),
                "fallback_network_retry": True,
            }
        return {"ok": False, "error": error}

    write_json(json_path, payload)
    md_path.write_text(_render_material_judgment_markdown(payload, request_id, question), encoding="utf-8")
    return {
        "ok": True,
        "payload": payload,
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "writing_mode": clean_text(payload.get("writing_mode")),
    }


def _close_reading_source_paths(result: dict) -> list[Path]:
    paths: list[Path] = []
    paths.extend(
        _result_direct_paths(
            result,
            (
                "codex_material_judgment_md",
                "codex_material_judgment_json",
                "codex_process_judgment_md",
                "codex_process_judgment_json",
            ),
        )
    )
    for package in _result_packages(result):
        for key in (
            "codex_close_reading_gate_md",
            "final_reading_gate_md",
            "reading_md",
            "cards",
            "writing_md",
            "triaged_csv",
            "review_csv",
            "process_inventory_md",
            "question_tree",
            "question_judgment_md",
            "library_flow_md",
            "review_coverage_md",
            "review_firstpass_cards_md",
            "source_verify_md",
            "source_verify_csv",
            "workflow_status_md",
        ):
            filename = closed_loop.CORE_FILES.get(key)
            if not filename:
                continue
            path = package / filename
            if path.exists():
                paths.append(path)
    paths.extend(_result_direct_paths(result, ("status_file", "status_json")))

    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_close_reading_prompt(item: dict, result: dict) -> str:
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    flow_note = _flow_profile_prompt_note(result)
    material_blocks: list[str] = []
    for path in _close_reading_source_paths(result)[:20]:
        content = _read_limited(path, 18000)
        if not content:
            continue
        material_blocks.append(
            "\n".join(
                [
                    f"### 精读来源：{path.name}",
                    f"路径：{path}",
                    "",
                    content,
                ]
            )
        )
    materials = "\n\n---\n\n".join(material_blocks) or "工程没有返回可读取材料。"
    pool_snapshot = _material_pool_snapshot_for_prompt(result, max_lines=36)
    memory_card = _task_memory_card_for_prompt(
        result,
        question,
        "精读材料词/精品聚拢池",
        "把材料池判定后的候选按原问题和子问题整理成精品材料词，标明每条材料回答哪个问题点。",
    )
    return f"""你是红楼梦工程的 Codex 精读材料词整理官。你现在处在“材料池判定之后、最终答案之前”：只做材料精读、舍取、原文锚点整理和文风方向，不写最终答案。

用户问题：
{question}

任务意图：
{task_intent or "红楼解语"}

附加要求：
{requirements or "无"}

流程档位：
{flow_note}

{memory_card}

工程已经供给的材料如下。你的所有选择必须来自这些材料或用户原题；如果某个推断来自你对材料缺口的判断，必须写明它是“由材料缺口推导出的补证方向”。请把“原子段”当作定位器，不是证据结论；你必须回到同一回目的上下文后，才能判断可用性。不要凭空补情节，不要绕开材料池。

{materials}

{pool_snapshot}

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不要写给用户看的最终回答；本步骤只整理“哪些材料可用、怎样读、怎样舍取、最终写作应按什么材料顺序展开”。
3. selected_materials、discarded_materials、original_anchors 都必须写 source_file；有 segment_no/chapter_no/quote_or_summary 的必须写上；selected_materials / original_anchors 还必须有 pool_item_ref（如：可用:8:08-006），且必须能在材料池判定中命中。
4. 原子段（segment）是最小点位，原子库是同题/同回的一组点位候选；它是读前组织，不是最终证据本体。
5. selected_materials、original_anchors 必须有 evidence_readiness，取值只允许：
   - 原文足证：已回到原文回目并形成连续上下文，可直接支撑结论；
   - 摘录不足：只有短摘，不能单独当主证；
   - 摘要定位：只靠摘要定位到段落，未形成完整上下文；
   - 需补整回：需补回整回或关键上下文。
6. 尽量给每条 selected_materials/original_anchors 填 read_window（例如：19-004~19-008），帮助后续回读补证；无 read_window 时不得标注“原文足证”。
7. close_reading_notes 可以有思想和文风，但每条都必须绑定 source_basis，说明来自哪份材料、哪个原文锚点或哪一个证据缺口。
8. writer_material_terms 是给最终写作者看的材料词，不是文章提纲，不是结论。它只能来自 evidence_readiness=原文足证 的 selected_materials/原文锚点。
9. 如果 key 判断依赖摘录不足/摘要定位/需补整回项，writing_permission 一律写“先补证”；最终层只能谨慎说明，不能硬写完整结论。
10. 本环节是“聚拢池”，不是在原有“精读材料词”里再发明词法；它只负责把“聚拢池判定项”按可用性精读再分发给最终写作。
11. 每条 selected_materials/original_anchors 都要写 subquestion_refs，说明它服务原问题或哪些子问题；一个材料可服务多个子问题，也可以只服务总问题。

JSON 格式：
{{
  "reading_center": "本题精读材料时真正要围绕的中心",
  "material_scope": "本步骤实际读取了哪些类型的工程材料",
  "selected_materials": [
    {{"source_file": "文件名", "segment_no": "原子段号", "chapter_no": "回目", "quote_or_summary": "原文短摘或摘要", "evidence_readiness": "原文足证/摘录不足/摘要定位/需补整回", "pool_item_ref": "可用:8:08-006", "subquestion_refs": ["总问题或子问题名"], "read_window": "19-004~19-008", "why_selected": "为什么选入", "supports": "支持问题的哪个点"}}
  ],
  "discarded_materials": [
    {{"source_file": "文件名", "segment_no": "原子段号", "chapter_no": "回目", "reason": "为什么舍弃或降为背景"}}
  ],
  "original_anchors": [
    {{"source_file": "文件名", "segment_no": "原子段号", "chapter_no": "回目", "quote_or_summary": "原文短摘或摘要", "evidence_readiness": "原文足证/摘录不足/摘要定位/需补整回", "pool_item_ref": "可用:8:08-006", "subquestion_refs": ["总问题或子问题名"], "read_window": "19-004~19-008", "supports": "支撑哪个关键判断"}}
  ],
  "close_reading_notes": [
    {{"point": "精读观察", "source_basis": "来自哪份材料/原文锚点/证据缺口", "note": "怎样读这条材料"}}
  ],
  "evidence_gaps": ["还缺少的原文或材料"],
  "writer_material_terms": ["从已选材料中提炼出的材料词"],
  "style_direction": "最终回答的文风方向：原文慢推/证据出发/温和收束/结论先行等",
  "writing_permission": "可以写/谨慎写/先补证",
  "writer_notes": "给最终写作者的材料组织提示，不是最终答案正文"
}}
"""


def _render_close_reading_markdown(payload: dict, request_id: str, question: str) -> str:
    def rows(items: object, fields: tuple[str, ...]) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- 暂无。"]
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parts = []
            for field in fields:
                value = item.get(field)
                if isinstance(value, list):
                    text = "、".join(clean_text(part) for part in value if clean_text(part))
                else:
                    text = clean_text(value)
                if text:
                    parts.append(text)
            if parts:
                lines.append("- " + "｜".join(parts))
        return lines or ["- 暂无。"]

    lines = [
        "# Codex 精读材料词",
        "",
        f"- 请求：{request_id}",
        f"- 问题：{question}",
        f"- 精读中心：{clean_text(payload.get('reading_center'))}",
        f"- 写作许可：{clean_text(payload.get('writing_permission')) or '谨慎写'}",
        "",
        "## 读取范围",
        "",
        clean_text(payload.get("material_scope")) or "未写明。",
        "",
        "## 选入材料",
        "",
        *rows(payload.get("selected_materials"), ("source_file", "segment_no", "chapter_no", "subquestion_refs", "evidence_readiness", "read_window", "why_selected", "supports")),
        "",
        "## 舍弃或降级材料",
        "",
        *rows(payload.get("discarded_materials"), ("source_file", "segment_no", "chapter_no", "reason")),
        "",
        "## 原文锚点",
        "",
        *rows(payload.get("original_anchors"), ("source_file", "segment_no", "chapter_no", "subquestion_refs", "evidence_readiness", "read_window", "quote_or_summary", "supports")),
        "",
        "## 证据优先级核对",
        *rows(payload.get("selected_materials"), ("segment_no", "chapter_no", "evidence_readiness", "read_window")),
        "",
        "## 精读观察",
        "",
    ]
    notes = payload.get("close_reading_notes")
    if isinstance(notes, list) and notes:
        for item in notes:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {clean_text(item.get('point'))}｜来源：{clean_text(item.get('source_basis'))}｜{clean_text(item.get('note'))}"
            )
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 证据缺口", ""])
    gaps = payload.get("evidence_gaps")
    if isinstance(gaps, list) and gaps:
        lines.extend(f"- {clean_text(item)}" for item in gaps if clean_text(item))
    else:
        lines.append("- 暂无。")
    lines.extend(["", "## 材料词", ""])
    terms = payload.get("writer_material_terms")
    if isinstance(terms, list) and terms:
        lines.extend(f"- {clean_text(item)}" for item in terms if clean_text(item))
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## 文风方向",
            "",
            clean_text(payload.get("style_direction")) or "原文慢推、证据出发、温和收束。",
            "",
            "## 给最终红楼解语的材料组织提示",
            "",
            clean_text(payload.get("writer_notes")) or "最终回答必须从选入材料和原文锚点出发，不得绕开材料池。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _run_codex_close_reading(item: dict, result: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    if not request_id or not question:
        return {"ok": False, "error": "缺少 request_id 或 question"}

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    output_dir = package if package.exists() and package.is_dir() else CODEX_RUN_DIR
    prompt_path = CODEX_RUN_DIR / f"{request_id}_close_reading_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_close_reading_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_close_reading_events.log"
    json_path = output_dir / f"00L_Codex精读材料词_{request_id}.json"
    md_path = output_dir / f"00L_Codex精读材料词_{request_id}.md"

    prompt = _build_codex_close_reading_prompt(item, result)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_CLOSE_READING_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="close_reading",
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "error": _read_limited(event_path, 3000)}

    answer = _read_limited(last_path, 70000)
    payload = _json_from_codex_text(answer)
    if not payload:
        return {"ok": False, "error": "Codex 精读材料词未返回有效 JSON"}

    material_pool_map = _build_material_pool_decision_map(result)
    selected_materials = payload.get("selected_materials")
    original_anchors = payload.get("original_anchors")
    if isinstance(selected_materials, list) or isinstance(original_anchors, list):
        insufficient: list[str] = []
        payload["selected_materials"] = _normalize_close_reading_material_rows(
            selected_materials,
            material_pool_map,
            insufficient,
            "selected_materials",
        )
        payload["original_anchors"] = _normalize_close_reading_material_rows(
            original_anchors,
            material_pool_map,
            insufficient,
            "original_anchors",
        )
        raw_gaps = payload.get("evidence_gaps")
        if isinstance(raw_gaps, list):
            evidence_gaps = [clean_text(item) for item in raw_gaps if clean_text(item)]
        else:
            evidence_gaps = []
        if insufficient and clean_text(payload.get("writing_permission")) == "可以写":
            payload["writing_permission"] = "先补证"
            for msg in insufficient:
                evidence_gaps.append(f"{msg}，需要回读整回或上下文窗口补证")
        if evidence_gaps:
            payload["evidence_gaps"] = evidence_gaps

    write_json(json_path, payload)
    markdown = _render_close_reading_markdown(payload, request_id, question)
    md_path.write_text(markdown, encoding="utf-8")
    _sync_codex_workflow_target(
        item,
        "codex_close_reading_target_md",
        "Codex 精读材料词 / 精品聚拢池",
        md_path,
        markdown,
    )
    return {
        "ok": True,
        "payload": payload,
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "writing_permission": clean_text(payload.get("writing_permission")),
    }


def _original_reread_source_paths(result: dict) -> list[Path]:
    paths: list[Path] = []
    paths.extend(
        path
        for path in (
            ROOT / "outputs" / "正式底库阶段复盘与下一步" / "16_原文优先精读法典.md",
            ROOT / "outputs" / "正式底库阶段复盘与下一步" / "12_质量比较_智能比较_答案质量比较_旧流程过程包_vs新流程00M_20260618.md",
        )
        if path.exists()
    )
    paths.extend(
        _result_direct_paths(
            result,
            (
                "codex_close_reading_md",
                "codex_close_reading_json",
                "codex_material_judgment_md",
                "codex_material_judgment_json",
                "codex_process_judgment_md",
                "codex_process_judgment_json",
            ),
        )
    )
    for package in _result_packages(result):
        for key in (
            "codex_original_reread_gate_md",
            "codex_original_reread_target_md",
            "question_judgment_md",
            "keyword_precheck_json",
            "question_tree",
            "codex_close_reading_gate_md",
            "final_reading_gate_md",
            "writing_md",
            "reading_md",
            "review_csv",
            "triaged_csv",
            "cards",
            "source_verify_md",
            "source_verify_csv",
            "workflow_status_md",
        ):
            filename = closed_loop.CORE_FILES.get(key)
            if not filename:
                continue
            path = package / filename
            if path.exists():
                paths.append(path)
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_original_reread_prompt(item: dict, result: dict) -> str:
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    flow_note = _flow_profile_prompt_note(result)
    memory_card = _task_memory_card_for_prompt(
        result,
        question,
        "写作前原文追证摘抄",
        "读完整体精品材料词后，选择真正值得回到原文摘抄的材料，形成最终写作前的原文底稿。",
        heavy=True,
    )
    material_blocks: list[str] = []
    for path in _original_reread_source_paths(result)[:22]:
        content = _read_limited(path, 18000)
        if not content:
            continue
        material_blocks.append(
            "\n".join(
                [
                    f"### 追证来源：{path.name}",
                    f"路径：{path}",
                    "",
                    content,
                ]
            )
        )
    materials = "\n\n---\n\n".join(material_blocks) or "工程没有返回可读取材料。"
    return f"""你是红楼梦工程的 Codex 写作前原文追证摘抄官。你处在“精读材料池/精品聚拢池之后、最终答案之前”：你不写最终答案，只把最终写作前真正要回到原文的材料摘出来。

用户问题：
{question}

任务意图：
{task_intent or "红楼解语"}

附加要求：
{requirements or "无"}

流程档位：
{flow_note}

{memory_card}

工程已经供给的材料如下。你必须先读“Codex 精读材料池/精品聚拢池”，再读问题拆解、原文回读材料和材料池判定。材料池只是导航，最终摘抄要以能回答原问题的原文为主。

本环节的核心不是机械摘抄，而是观察你“回原文以后怎么行动”：你要从初始锚点进入《红楼梦》全书全文、全原文，复习前后文、同场边界、相邻回目、人物关系链、物象/空间/事件链和全书全文回声。若你判断精读材料池漏掉了关键原文，可以在只读范围内主动扩展到相关回目、相关关键词、相邻章节或全书全文范围追证；但每一次扩展都必须写明为什么扩展、扩展到哪里、发现什么、是否改变判断。每张原文追证行动卡都必须做一次“跳查决策”：需要跳查时写清跳查路线，不需要跳查时写清停止理由，避免既傻傻只摘锚点，也避免无边界乱搜。

你可以在本地工程只读地查找正式原文和已生成材料。优先走工程产物中的真源提示、章节原文入口、read_window、segment_no、chapter_no；必要时可用项目内已有原文库、SQLite、章节文件或检索文件做定点追证。不能编造查到的原文；如果没有真正找到连续原文，只能标为摘录不足、摘要定位或需补证。

{materials}

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不写最终答案，不写完整文章；本步骤只做写作前原文追证摘抄。
3. 开头必须复习原问题和子问题：不要在长流程里忘题。
4. 禁止重新拆题，禁止把每个子问题机械各跑一遍；已有子问题只作为提醒卡。真正执行的是“原文追证行动卡”。
5. 一条原文可以同时支持多个子问题；一个子问题也可以暂时没有摘抄，但必须在 subquestion_coverage 或 evidence_gaps 里说明。
6. 每条 selected_original_excerpts 必须有 source_file、chapter_no、segment_no、original_excerpt 或 quote_or_summary、subquestion_refs、why_useful、supports_final_point。
7. 如果只有摘要、没有原文上下文，只能写为“需补证”或“摘录不足”，不能当作主证。
8. 每张 pursuit_task_cards 必须来自证据伤口，不来自凭空猜题。常见证据伤口包括：摘录不足、核心段缺失、同回误召、处所关联、旁提误召、摘要替代原文、情绪词泛化、代表性不足。
9. 每次 full_text_expansion_trace 必须说明扩展理由。可以扩到前后段、相邻回、同一事件链、同一人物关系链、同一物象链或《红楼梦》全书全文、全原文相关词，但不能无理由乱搜；同时必须写明 jump_decision 和 stop_reason，让人看得出它是智慧跳查还是确认不必跳查。
10. evidence_grade_changes 要记录追证后材料升为主证、降为背景、剔除、仍需补证的变化。
11. conclusion_candidates 必须列出最终答案可采用的主结论候选，但不能写成长文。
12. evidence_to_claim_map 必须把每个结论候选绑定到原文摘抄或追证任务卡。
13. rejected_or_boundary_materials 必须写清哪些材料只能作背景、边界或反证，防止终稿误写。
14. scene_or_relation_chain 要把能支持深度文章的场景链、人物关系链或事件链先组织出来。
15. second_reread_requests 只在深度写作还需要补证时提出；不能为了显得复杂而乱提补证。
16. writing_permission 只能写：可以写、谨慎写、先补证。

JSON 格式：
{{
  "question_review": "重新复习后的原问题理解",
  "subquestion_review": [
    {{"subquestion_ref": "子问题编号或名称", "question": "子问题内容", "current_coverage": "已有材料如何覆盖/暂缺"}}
  ],
  "answer_standard": "本题判断一条材料能否进入最终答案的标准",
  "reread_center": "本次原文追证摘抄真正围绕的中心",
  "pursuit_task_cards": [
    {{"task_id": "T1", "task_type": "强证核完整/疑证补关键句/缺证追核心场景/误召回反证/代表性补足/自由追证", "evidence_wound": "这张卡来自哪个证据伤口", "initial_anchors": ["初始回目/段落/关键词"], "why_pursue": "为什么需要回原文追证", "required_reread_scope": "必须回读的原文范围", "allowed_expansion": "允许扩展到哪些前后文/相邻回/关系链/全书线索", "jump_decision": "本卡是否需要跳查，为什么", "success_standard": "找到什么才可升为可写证据", "failure_downgrade": "找不到时如何降级或标缺口", "excerpt_requirement": "摘抄时必须摘哪些上下文"}}
  ],
  "full_text_expansion_trace": [
    {{"task_id": "T1", "from_anchor": "从哪里出发", "expanded_to": "扩展到哪里", "expansion_reason": "为什么扩展", "method": "如何查/如何读", "jump_decision": "为什么这样跳查或为什么停止跳查", "stop_reason": "到哪里可以停止继续扩展", "finding": "找到什么", "changed_judgment": "是否改变材料等级或答案方向"}}
  ],
  "selected_original_excerpts": [
    {{"source_file": "文件名或原文入口", "chapter_no": "回目", "segment_no": "原子段号/整回位置/未知", "source_kind": "初始锚点/扩展追证/相邻回追证/全书回声/反证", "task_id": "对应追证任务卡", "original_excerpt": "原文摘抄或连续上下文摘要", "quote_or_summary": "短摘或摘要", "subquestion_refs": ["总问题或子问题名"], "evidence_readiness": "原文足证/摘录不足/摘要定位/需补整回", "why_useful": "为什么值得摘", "supports_final_point": "最终答案中可支撑哪个判断"}}
  ],
  "evidence_grade_changes": [
    {{"material_ref": "材料/回目/段落", "before": "追证前等级", "after": "追证后等级", "reason": "升降级原因"}}
  ],
  "conclusion_candidates": [
    {{"claim_id": "C1", "claim": "最终答案可采用的主结论候选", "supporting_excerpts": ["T1或回目"], "evidence_level": "主证/谨慎候选/背景", "risk_note": "终稿写作风险"}}
  ],
  "evidence_to_claim_map": [
    {{"claim_id": "C1", "excerpt_refs": ["T1"], "original_basis": "原文依据", "usable_sentence": "终稿可采用的判断句"}}
  ],
  "rejected_or_boundary_materials": [
    {{"material_ref": "回目/段落", "status": "边界/背景/反证/剔除", "why_not_main": "为什么不能当主证", "allowed_use": "允许如何使用"}}
  ],
  "scene_or_relation_chain": [
    {{"chain_name": "场景链或关系链名称", "nodes": ["节点1", "节点2"], "interpretive_hint": "给深度文章的结构提示"}}
  ],
  "second_reread_requests": [
    {{"reason": "为什么需要二次追证", "target_scope": "目标回目/事件链/人物链", "priority": "高/中/低"}}
  ],
  "subquestion_coverage": [
    {{"subquestion_ref": "子问题编号或名称", "status": "已覆盖/部分覆盖/暂缺", "supporting_segments": ["回目:段落号"], "note": "覆盖说明"}}
  ],
  "evidence_gaps": ["还缺哪些原文或上下文"],
  "writer_synthesis_notes": "给最终红楼解语写作者的原文组织提示",
  "writing_permission": "可以写/谨慎写/先补证"
}}
"""


def _render_original_reread_markdown(payload: dict, request_id: str, question: str) -> str:
    def rows(items: object, fields: tuple[str, ...]) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- 暂无。"]
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parts: list[str] = []
            for field in fields:
                value = item.get(field)
                if isinstance(value, list):
                    text = "、".join(clean_text(part) for part in value if clean_text(part))
                else:
                    text = clean_text(value)
                if text:
                    parts.append(text)
            if parts:
                lines.append("- " + "｜".join(parts))
        return lines or ["- 暂无。"]

    lines = [
        "# Codex 写作前原文追证摘抄",
        "",
        f"- 请求：{request_id}",
        f"- 问题：{question}",
        f"- 写作许可：{clean_text(payload.get('writing_permission')) or '谨慎写'}",
        "",
        "## 问题复习",
        "",
        clean_text(payload.get("question_review")) or "未写明。",
        "",
        "## 子问题复习",
        "",
        *rows(payload.get("subquestion_review"), ("subquestion_ref", "question", "current_coverage")),
        "",
        "## 答案判定标准",
        "",
        clean_text(payload.get("answer_standard")) or "未写明。",
        "",
        "## 原文追证中心",
        "",
        clean_text(payload.get("reread_center")) or "未写明。",
        "",
        "## 原文追证行动卡",
        "",
        *rows(
            payload.get("pursuit_task_cards"),
            ("task_id", "task_type", "evidence_wound", "initial_anchors", "why_pursue", "required_reread_scope", "allowed_expansion", "jump_decision", "success_standard", "failure_downgrade", "excerpt_requirement"),
        ),
        "",
        "## 红楼梦全书全文扩展记录",
        "",
        *rows(
            payload.get("full_text_expansion_trace"),
            ("task_id", "from_anchor", "expanded_to", "expansion_reason", "method", "jump_decision", "stop_reason", "finding", "changed_judgment"),
        ),
        "",
        "## 选摘原文",
        "",
        *rows(
            payload.get("selected_original_excerpts"),
            ("source_file", "chapter_no", "segment_no", "source_kind", "task_id", "subquestion_refs", "evidence_readiness", "original_excerpt", "quote_or_summary", "why_useful", "supports_final_point"),
        ),
        "",
        "## 证据升降级",
        "",
        *rows(payload.get("evidence_grade_changes"), ("material_ref", "before", "after", "reason")),
        "",
        "## 最终结论候选",
        "",
        *rows(payload.get("conclusion_candidates"), ("claim_id", "claim", "supporting_excerpts", "evidence_level", "risk_note")),
        "",
        "## 证据到结论映射",
        "",
        *rows(payload.get("evidence_to_claim_map"), ("claim_id", "excerpt_refs", "original_basis", "usable_sentence")),
        "",
        "## 反证/边界材料",
        "",
        *rows(payload.get("rejected_or_boundary_materials"), ("material_ref", "status", "why_not_main", "allowed_use")),
        "",
        "## 场景链/关系链",
        "",
        *rows(payload.get("scene_or_relation_chain"), ("chain_name", "nodes", "interpretive_hint")),
        "",
        "## 二次追证建议",
        "",
        *rows(payload.get("second_reread_requests"), ("reason", "target_scope", "priority")),
        "",
        "## 子问题覆盖",
        "",
        *rows(payload.get("subquestion_coverage"), ("subquestion_ref", "status", "supporting_segments", "note")),
        "",
        "## 证据缺口",
        "",
    ]
    gaps = payload.get("evidence_gaps")
    if isinstance(gaps, list) and gaps:
        lines.extend(f"- {clean_text(item)}" for item in gaps if clean_text(item))
    else:
        lines.append("- 暂无。")
    lines.extend(
        [
            "",
            "## 给最终红楼解语的原文组织提示",
            "",
            clean_text(payload.get("writer_synthesis_notes")) or "最终回答必须优先从本原文追证摘抄组织，不得绕开原文。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _run_codex_original_reread(item: dict, result: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    if not request_id or not question:
        return {"ok": False, "error": "缺少 request_id 或 question"}

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    output_dir = package if package.exists() and package.is_dir() else CODEX_RUN_DIR
    prompt_path = CODEX_RUN_DIR / f"{request_id}_original_reread_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_original_reread_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_original_reread_events.log"
    json_path = output_dir / f"00M_Codex写作前原文通读摘抄_{request_id}.json"
    md_path = output_dir / f"00M_Codex写作前原文通读摘抄_{request_id}.md"

    prompt = _build_codex_original_reread_prompt(item, result)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_ORIGINAL_REREAD_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="original_reread",
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "error": _read_limited(event_path, 3000)}

    answer = _read_limited(last_path, 70000)
    payload = _json_from_codex_text(answer)
    if not payload:
        return {"ok": False, "error": "Codex 写作前原文追证摘抄未返回有效 JSON"}

    write_json(json_path, payload)
    markdown = _render_original_reread_markdown(payload, request_id, question)
    md_path.write_text(markdown, encoding="utf-8")
    _sync_codex_workflow_target(
        item,
        "codex_original_reread_target_md",
        "Codex 写作前原文追证摘抄",
        md_path,
        markdown,
    )
    return {
        "ok": True,
        "payload": payload,
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "writing_permission": clean_text(payload.get("writing_permission")),
    }


def _deep_task_text(item: dict) -> str:
    return "\n".join(
        clean_text(item.get(key))
        for key in ("question", "task_intent", "requirements")
        if clean_text(item.get(key))
    )


def _is_deep_task(item: dict) -> bool:
    text = _deep_task_text(item)
    keywords = (
        "深度", "文章", "论证", "分析", "见解", "结构", "为什么", "如何体现", "背后", "说明什么",
        "主题", "象征", "隐喻", "伏笔", "前后照应", "人物命运", "关系中", "关系如何", "悲剧", "作用",
    )
    if _run_mode() == "deep":
        return True
    return any(keyword in text for keyword in keywords)


def _is_interpretive_locator_task(item: dict) -> bool:
    text = _deep_task_text(item)
    if not text:
        return False
    has_locator = any(token in text for token in ("哪一些", "哪些", "哪几", "主要章回", "主要的红楼梦章回"))
    has_interpretation = any(token in text for token in ("主要说", "什么情景", "情景", "主要", "关系", "同场", "在一起"))
    named_people = sum(1 for name in ("贾宝玉", "宝玉", "贾母", "林黛玉", "黛玉") if name in text)
    return has_locator and has_interpretation and named_people >= 2

def _single_hit_by_judgment(item: dict, original_payload: dict, close_reading_payload: dict | None = None, material_judgment_payload: dict | None = None) -> bool:
    original_payload = original_payload if isinstance(original_payload, dict) else {}
    close_reading_payload = close_reading_payload if isinstance(close_reading_payload, dict) else {}
    material_judgment_payload = material_judgment_payload if isinstance(material_judgment_payload, dict) else {}

    if clean_text(original_payload.get("writing_permission")) != "可以写":
        return False
    if _is_deep_task(item) or _is_interpretive_locator_task(item):
        return False
    if _original_reread_hit_quality(original_payload) != "single_hit":
        return False

    if clean_text(close_reading_payload.get("writing_permission")) == "先补证":
        return False
    if clean_text(material_judgment_payload.get("writing_mode")) == "先补证":
        return False

    second_requests = original_payload.get("second_reread_requests", [])
    high_priority_second = [
        request for request in second_requests
        if isinstance(request, dict) and clean_text(request.get("priority")) in {"高", "中"}
    ] if isinstance(second_requests, list) else []
    if high_priority_second:
        return False

    return True


def _single_hit_without_00m(item: dict, material_judgment_payload: dict, close_reading_payload: dict | None = None) -> bool:
    # 2026-06-21: "一次命中/可直接命中" no longer grants a route around
    # 00L and 00M. A hit is only recall until it has gone through close
    # reading and prewrite original reread.
    return False


def _original_reread_hit_quality(payload: dict) -> str:
    if not isinstance(payload, dict):
        return "needs_00n"
    permission = clean_text(payload.get("writing_permission"))
    if permission in {"先补证", "先二次追证"}:
        return "needs_reread_rounds"
    gaps = payload.get("evidence_gaps")
    second_requests = payload.get("second_reread_requests")
    selected = payload.get("selected_original_excerpts")
    grade_changes = payload.get("evidence_grade_changes")
    high_priority_second = [
        request for request in second_requests
        if isinstance(request, dict) and clean_text(request.get("priority")) in {"高", "中"}
    ] if isinstance(second_requests, list) else []
    if high_priority_second:
        return "needs_reread_rounds"
    if permission == "可以写" and _list_len(gaps) == 0 and _list_len(high_priority_second) == 0 and _list_len(selected) <= 3:
        return "single_hit"
    if permission == "可以写" and _list_len(gaps) <= 1 and _list_len(grade_changes) <= 2 and _list_len(selected) <= 4:
        return "single_hit"
    return "needs_00n"




def _list_len(value: object) -> int:
    return len(value) if isinstance(value, list) else 0


def _deep_insight_reread_level(item: dict, original_reread_payload: dict, close_reading_payload: dict | None = None, material_judgment_payload: dict | None = None) -> dict:
    close_reading_payload = close_reading_payload if isinstance(close_reading_payload, dict) else {}
    material_judgment_payload = material_judgment_payload if isinstance(material_judgment_payload, dict) else {}
    writing_permission = clean_text(original_reread_payload.get("writing_permission"))
    evidence_gaps = original_reread_payload.get("evidence_gaps")
    second_requests = original_reread_payload.get("second_reread_requests")
    boundary_materials = original_reread_payload.get("rejected_or_boundary_materials")
    grade_changes = original_reread_payload.get("evidence_grade_changes")
    hit_quality = _original_reread_hit_quality(original_reread_payload)
    single_hit_judgment = _single_hit_by_judgment(
        item,
        original_reread_payload,
        close_reading_payload,
        material_judgment_payload,
    )
    deep_task = _is_deep_task(item)
    interpretive_locator = _is_interpretive_locator_task(item)
    high_priority_second_requests = [
        request for request in second_requests
        if isinstance(request, dict) and clean_text(request.get("priority")) in {"高", "中"}
    ] if isinstance(second_requests, list) else []

    if hit_quality == "single_hit" and single_hit_judgment:
        decision = "不进入00N"
        reason = "这是判定级一次命中，00M 已闭合证据、写作许可可写且无二次追证需求；不需要 00N 参与。"
        material_scope = "00M"
        max_rounds = 0
        allowed = ["00M"]
        forbidden = ["精读材料池", "材料池判定", "全量底账"]
        stop = "最终答案直接读取 00M。"
    elif writing_permission in {"先补证", "先二次追证"} or high_priority_second_requests:
        decision = "进入00N"
        reason = "00M 已提示补证、写作许可不足，或存在中高优先级二次追证请求；需要 00N 组织补证轮次。"
        material_scope = "00M+精读材料池+材料池判定"
        max_rounds = 3 if deep_task else 2
        allowed = ["00M", "精读材料池", "材料池判定", "被追证任务卡点名的少量候选材料"]
        forbidden = ["全量底账", "无关候选长表", "未指定原文全量乱搜"]
        stop = "完成中高优先级追证任务，或连续一轮没有新增关键证据，或达到最大轮次。"
    elif deep_task:
        decision = "进入00N"
        reason = "用户问题要求深度分析、文章论证或结构解释；00N 需要在 00M 证据底稿上形成论点和文章骨架。"
        material_scope = "00M+精读材料池"
        max_rounds = 2 if (_list_len(evidence_gaps) or _list_len(boundary_materials) or _list_len(grade_changes) >= 5) else 1
        allowed = ["00M", "精读材料池", "必要时材料池判定中与论点有关的小片段"]
        forbidden = ["全量底账", "无关候选长表", "无理由原文重查"]
        stop = "中心论点、分论点、证据绑定和写作风险已经清楚，且 00N 写作许可为可以写。"
    elif interpretive_locator:
        decision = "进入00N"
        reason = "题目虽有定位入口，但要求判断主要性、排序、情景解释或同场边界；00N 做轻量组织能提高答案质量。"
        material_scope = "00M+精读材料池"
        max_rounds = 1
        allowed = ["00M", "精读材料池"]
        forbidden = ["材料池全量候选", "全量底账", "无理由原文重查"]
        stop = "主证、补充证、边界证的表达顺序已经清楚。"
    else:
        decision = "不进入00N"
        reason = "问题是简单定位、简单事实查询，或 00M 已经一次命中并闭合证据；最终答案直接读取 00M。"
        material_scope = "00M"
        max_rounds = 0
        allowed = ["00M"]
        forbidden = ["精读材料池", "材料池判定", "全量底账"]
        stop = "最终答案直接读取 00M。"
    return {
        "decision": decision,
        "level": decision,
        "reason": reason,
        "material_scope": material_scope,
        "hit_quality": hit_quality,
        "single_hit_judgment": single_hit_judgment,
        "max_reread_rounds": max_rounds,
        "current_round": 1 if decision == "进入00N" else 0,
        "next_round_condition": "只有出现中高优先级二次追证请求、中心论点缺证、或本轮新增证据改变主判断时，才进入下一轮。",
        "materials_allowed": allowed,
        "materials_forbidden": forbidden,
        "stop_condition": stop,
    }


def _should_run_codex_deep_insight(item: dict, result: dict, original_reread: dict) -> bool:
    payload = original_reread.get("payload", {}) if isinstance(original_reread, dict) else {}
    if not isinstance(payload, dict):
        payload = {}
    policy = _deep_insight_reread_level(
        item,
        payload,
        result.get("codex_close_reading", {}) if isinstance(result.get("codex_close_reading"), dict) else {},
        result.get("codex_material_judgment", {}) if isinstance(result.get("codex_material_judgment"), dict) else {},
    )
    return clean_text(policy.get("decision")) == "进入00N"


def _deep_insight_source_paths(result: dict, policy: dict) -> list[Path]:
    paths: list[Path] = []
    paths.extend(_result_direct_paths(result, ("codex_original_reread_md", "codex_original_reread_json")))
    decision = clean_text(policy.get("decision"))
    scope = clean_text(policy.get("material_scope"))
    if decision == "进入00N" and "精读材料池" in scope:
        paths.extend(_result_direct_paths(result, ("codex_close_reading_md", "codex_close_reading_json")))
    if decision == "进入00N" and "材料池判定" in scope:
        paths.extend(_result_direct_paths(result, ("codex_material_judgment_md", "codex_material_judgment_json")))
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen and path.exists():
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_deep_insight_prompt(item: dict, result: dict, original_reread: dict) -> str:
    question = clean_text(item.get("question"))
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    original_payload = original_reread.get("payload", {}) if isinstance(original_reread, dict) else {}
    if not isinstance(original_payload, dict):
        original_payload = {}
    policy = _deep_insight_reread_level(
        item,
        original_payload,
        result.get("codex_close_reading", {}) if isinstance(result.get("codex_close_reading"), dict) else {},
        result.get("codex_material_judgment", {}) if isinstance(result.get("codex_material_judgment"), dict) else {},
    )
    material_blocks: list[str] = []
    for path in _deep_insight_source_paths(result, policy)[:10]:
        content = _read_limited(path, 16000)
        if not content:
            continue
        material_blocks.append("\n".join([f"### 00N允许读取材料：{path.name}", f"路径：{path}", "", content]))
    materials = "\n\n---\n\n".join(material_blocks) or "没有读取到 00M 或精读材料。"
    return f"""你是红楼梦工程的 Codex 深度见解增量稿官。你处在 00M 写作前原文追证摘抄之后、最终文章之前。你不重复 00M 摘抄，不写最终文章，只做深度见解增量、论点结构和必要二次追证请求。

用户问题：
{question}

任务意图：
{task_intent or '红楼解语'}

附加要求：
{requirements or '无'}

材料复看策略：
{json.dumps(policy, ensure_ascii=False, indent=2)}

你必须先读 00M。00M 是证据官；你是论证官。你可以根据 material_reread_policy 复看精读材料池或材料池判定，但真正的主判断只有两个：是否进入 00N，以及最多允许几轮追证。不能无边界重跑 00M，也不能重新全量检索原文。

{materials}

严格规则：
1. 只输出 JSON，不要 Markdown。
2. 不写最终文章，不重复 00M 的原文摘抄。
3. 所有深度论点必须绑定 00M 证据、精读材料池复看依据，或明确列入 second_reread_requests。
4. 如果证据不足，写作许可必须是“先二次追证”或“谨慎写”，不能硬写。
5. material_reread_policy 必须保留 decision、max_reread_rounds、next_round_condition 和 stop_condition。
6. incremental_insights_over_00m 必须说明相对 00M 的增量在哪里。
7. 如果需要第二轮、第三轮追证，必须写入 second_reread_requests；不能在本轮里无边界扩展。

JSON 格式：
{{
  "question_review": "重新复习后的深度问题理解",
  "depth_task_type": "普通问答/深度分析/文章论证/主题结构/人物关系/跨回目结构",
  "should_use_00n": true,
  "material_reread_policy": {{"decision": "进入00N/不进入00N", "reason": "为什么进入或不进入", "material_scope": "00M/00M+精读材料池/00M+精读材料池+材料池判定", "max_reread_rounds": 1, "current_round": 1, "next_round_condition": "进入下一轮的条件", "materials_allowed": ["00M"], "materials_forbidden": ["全量底账"], "stop_condition": "停止条件"}},
  "00m_reading": "对00M证据底稿的总体判断",
  "central_thesis_candidates": [{{"thesis_id": "TH1", "thesis": "中心论点候选", "supporting_claims": ["C1"], "strength": "强/中/弱", "risk": "风险"}}],
  "argument_sections": [{{"section_id": "S1", "section_title": "段落标题", "main_point": "本段论点", "evidence_refs": ["T1"], "original_basis": "原文依据", "writing_note": "怎么写"}}],
  "incremental_insights_over_00m": [{{"insight": "相较00M新增的解释", "basis_type": "来自00M/来自精读材料池复看/来自材料池判定复看/需要二次追证", "basis_refs": ["T1"], "confidence": "高/中/低"}}],
  "disagreements_or_cautions_about_00m": [{{"target": "00M中的材料或判断", "opinion": "同意/谨慎/不同意", "reason": "理由", "required_action": "无/终稿谨慎/二次追证"}}],
  "second_reread_requests": [{{"reason": "为什么需要再回原文", "target_scope": "目标回目/事件链/人物链", "priority": "高/中/低", "question_to_answer": "二次追证要回答什么"}}],
  "final_writer_outline": [{{"order": 1, "paragraph_goal": "本段要完成什么", "must_use_evidence": ["T1"], "avoid": "不要怎样写"}}],
  "writing_permission": "可以写/谨慎写/先二次追证"
}}
"""


def _render_deep_insight_markdown(payload: dict, request_id: str, question: str) -> str:
    def rows(items: object, fields: tuple[str, ...]) -> list[str]:
        if not isinstance(items, list) or not items:
            return ["- 暂无。"]
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parts: list[str] = []
            for field in fields:
                value = item.get(field)
                if isinstance(value, list):
                    text = "、".join(clean_text(part) for part in value if clean_text(part))
                elif isinstance(value, dict):
                    text = json.dumps(value, ensure_ascii=False)
                else:
                    text = clean_text(value)
                if text:
                    parts.append(text)
            if parts:
                lines.append("- " + "｜".join(parts))
        return lines or ["- 暂无。"]

    policy = payload.get("material_reread_policy") if isinstance(payload.get("material_reread_policy"), dict) else {}
    lines = [
        "# Codex 深度见解增量稿",
        "",
        f"- 请求：{request_id}",
        f"- 问题：{question}",
        f"- 写作许可：{clean_text(payload.get('writing_permission')) or '谨慎写'}",
        "",
        "## 深度问题复习",
        "",
        clean_text(payload.get("question_review")) or "未写明。",
        "",
        "## 材料复看与追证轮次策略",
        "",
        f"- 进入判断：{clean_text(policy.get('decision')) or clean_text(policy.get('level')) or '未写明'}",
        f"- 理由：{clean_text(policy.get('reason')) or '未写明'}",
        f"- 材料范围：{clean_text(policy.get('material_scope')) or '未写明'}",
        f"- 当前轮次：{clean_text(policy.get('current_round')) or '0'}",
        f"- 最大轮次：{clean_text(policy.get('max_reread_rounds')) or '0'}",
        f"- 下一轮条件：{clean_text(policy.get('next_round_condition')) or '未写明'}",
        f"- 允许材料：{'、'.join(clean_text(x) for x in policy.get('materials_allowed', []) if clean_text(x)) if isinstance(policy.get('materials_allowed'), list) else clean_text(policy.get('materials_allowed'))}",
        f"- 禁止材料：{'、'.join(clean_text(x) for x in policy.get('materials_forbidden', []) if clean_text(x)) if isinstance(policy.get('materials_forbidden'), list) else clean_text(policy.get('materials_forbidden'))}",
        f"- 停止条件：{clean_text(policy.get('stop_condition')) or '未写明'}",
        "",
        "## 00M 证据底稿复核",
        "",
        clean_text(payload.get("00m_reading")) or "未写明。",
        "",
        "## 中心论点候选",
        "",
        *rows(payload.get("central_thesis_candidates"), ("thesis_id", "thesis", "supporting_claims", "strength", "risk")),
        "",
        "## 分论点结构",
        "",
        *rows(payload.get("argument_sections"), ("section_id", "section_title", "main_point", "evidence_refs", "original_basis", "writing_note")),
        "",
        "## 相对 00M 的增量见解",
        "",
        *rows(payload.get("incremental_insights_over_00m"), ("insight", "basis_type", "basis_refs", "confidence")),
        "",
        "## 对 00M 的谨慎意见",
        "",
        *rows(payload.get("disagreements_or_cautions_about_00m"), ("target", "opinion", "reason", "required_action")),
        "",
        "## 二次追证请求",
        "",
        *rows(payload.get("second_reread_requests"), ("reason", "target_scope", "priority", "question_to_answer")),
        "",
        "## 最终文章结构建议",
        "",
        *rows(payload.get("final_writer_outline"), ("order", "paragraph_goal", "must_use_evidence", "avoid")),
    ]
    return "\n".join(lines).strip() + "\n"


def _run_codex_deep_insight(item: dict, result: dict, original_reread: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    if not request_id or not question:
        return {"ok": False, "error": "缺少 request_id 或 question"}
    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    package = Path(clean_text(result.get("package") or result.get("package_dir")))
    output_dir = package if package.exists() and package.is_dir() else CODEX_RUN_DIR
    prompt_path = CODEX_RUN_DIR / f"{request_id}_deep_insight_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_deep_insight_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_deep_insight_events.log"
    json_path = output_dir / f"00N_Codex深度见解增量稿_{request_id}.json"
    md_path = output_dir / f"00N_Codex深度见解增量稿_{request_id}.md"
    prompt = _build_codex_deep_insight_prompt(item, result, original_reread)
    prompt_path.write_text(prompt, encoding="utf-8")
    cmd = [
        _codex_executable(), "exec", "-C", str(ROOT), "--skip-git-repo-check", "--ignore-user-config",
        "--ignore-rules", "--ephemeral", "-s", "read-only", "--output-last-message", str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_DEEP_INSIGHT_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="deep_insight",
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if proc.returncode != 0:
        return {"ok": False, "error": _read_limited(event_path, 3000)}
    answer = _read_limited(last_path, 70000)
    payload = _json_from_codex_text(answer)
    if not payload:
        return {"ok": False, "error": "Codex 深度见解增量稿未返回有效 JSON"}
    write_json(json_path, payload)
    markdown = _render_deep_insight_markdown(payload, request_id, question)
    md_path.write_text(markdown, encoding="utf-8")
    return {
        "ok": True,
        "payload": payload,
        "prompt_path": str(prompt_path),
        "last_path": str(last_path),
        "json_path": str(json_path),
        "md_path": str(md_path),
        "writing_permission": clean_text(payload.get("writing_permission")),
    }


def _final_answer_source_paths(result: dict) -> list[Path]:
    policy = result.get("material_reread_policy")
    policy_decision = clean_text(policy.get("decision")) if isinstance(policy, dict) else ""
    paths: list[Path] = []
    paths.extend(_result_direct_paths(result, ("codex_original_reread_md", "codex_original_reread_json")))
    paths.extend(_result_direct_paths(result, ("codex_deep_insight_md", "codex_deep_insight_json")))
    if not paths:
        paths.extend(_result_direct_paths(result, ("codex_close_reading_md", "codex_close_reading_json")))
    if not paths:
        paths.extend(_workflow_material_paths(result)[:6])
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path.resolve())
        if resolved not in seen and path.exists():
            seen.add(resolved)
            unique.append(path)
    return unique


def _build_codex_final_prompt(question: str, task_intent: str, requirements: str, result: dict) -> str:
    policy = result.get("material_reread_policy")
    policy_decision = clean_text(policy.get("decision")) if isinstance(policy, dict) else ""
    if policy_decision == "进入00N":
        read_route = "深度路径：先读 00M，再读 00N，允许 00N 提供结构/增量。"
        evidence_note = "普通问答必须以 00M 为主证据底稿，深度问答可联合 00N。"
        read_scope_note = "同样不允许新增检索或绕回全量底账。"
    else:
        read_route = "默认走 00M 路径；若 00N 存在可作为深度增量共同参与终稿。"
        evidence_note = "普通问答必须主要读取“Codex 写作前原文追证摘抄”（00M）；深度文章可读 00M+00N。"
        read_scope_note = "若 00M 缺失，本阶段不得生成最终答案，应退回生成 00M。"
    material_blocks: list[str] = []
    flow_note = _flow_profile_prompt_note(result)
    for path in _final_answer_source_paths(result)[:8]:
        content = _read_limited(path)
        if not content:
            continue
        material_blocks.append(
            "\n".join(
                [
                    f"### 材料文件：{path.name}",
                    f"路径：{path}",
                    "",
                    content,
                ]
            )
        )

    materials = "\n\n---\n\n".join(material_blocks) or "红楼梦工程未返回可读取材料。"
    memory_card = _task_memory_card_for_prompt(
        result,
        question,
        "最终红楼解语",
        "优先读取写作前原文追证摘抄，把原文支点组织成给用户看的最终回答。",
    )
    return f"""你是红楼梦工程的 Codex 最终回答者。你现在不是页面过程稿，也不是本地检索模块；你要阅读红楼梦工程已经跑出的材料，形成给用户看的红楼解语（内部仍写入最终答案目录）。

用户问题：
{question}

任务意图：
{task_intent or "最终回答"}

附加要求：
{requirements or "无"}

流程档位：
{flow_note}

{memory_card}

最终回答阶段的工具边界：
- 你现在只做“读工程产物后的红楼解语”，不再现场查库、不再运行 SQL、不再调用 shell/python/sqlite/rg/cat 等命令，也不打开新文件。
- 下面只嵌入本题最终写作阶段允许读取的材料：{read_route} 你不再默认回看材料池、过程包、复核表或全量底账。
- 凡题目涉及物件、意象、器具、植物、信物、陈设或空间物，你要检查工程产物里是否已经走过 objects_axis / 原子段 / 人物事件空间诗词证据边 / 原文上下文 / 材料池。若材料没有完成这条链，只能标为“需补证”，不能临时自己查库补写。
- 真实字段提醒：objects_axis 没有 object_id/object_name；spaces_axis 没有 space_id/space_name。最终阶段即使发现字段缺口，也只写缺口，不再查询。

工程已经产出的最终写作材料如下。{evidence_note} {read_scope_note} 材料池判定和精读材料池需作为证据组织依据，不再以“复查底账”代替材料决策。

{materials}

输出层风格指导：
{research_style_guidance(task_intent, requirements)}

红楼解语规则：
1. 先正面回答用户问的是什么、在哪一回、讲了什么；如果问题不是定位题，就先回答主判断。
2. 必须吸收红楼梦工程材料里的原文、章节、人物、场景和证据，但不要把“模块搜索结果、证据表、谈心式论证稿、正式文章第一稿”的格式直接拿来回显。
3. 不要输出旧过程稿依据、“母稿”“证据分层表”“这是一版正式文章第一稿”等工程内部话。
4. 回答要像真正的 Codex 读完材料后的判断：自然、清楚、有取舍，必要时说明“不确定处”和“下一步怎么查”。
5. 如果工程材料明显不足，明确说材料不足，并给出基于已见材料的谨慎判断；不要编造。
6. 表达上允许“心得式结论”：可以结论先行，也可以从原文证据慢慢推导；要用具体原文、情节、人物关系把道理逐点说清楚，推理自然，文字温和、清楚、有余味。
7. 不套统一格式。让答案从材料池和原文复核里自然长出来，每个关键判断都能回到证据。
8. 写作前必须逐条判定材料池里的关键材料：看 segment_no、chapter_no、summary、quote、证据角色、是否待核、是否支持原问题。不要只读一遍标题就写。
9. 写作前必须吸收“Codex 精读材料词”里的 selected_materials、original_anchors、close_reading_notes、writer_material_terms 和 style_direction；它们不是答案正文，而是你组织最终回答的材料秩序。
10. 写作前必须吸收“Codex 写作前原文追证摘抄”里的 question_review、subquestion_review、selected_original_excerpts、evidence_grade_changes、conclusion_candidates、evidence_to_claim_map、rejected_or_boundary_materials、scene_or_relation_chain、subquestion_coverage 和 writer_synthesis_notes；主判断优先从这些原文追证摘抄里长出来。若存在“Codex 深度见解增量稿”，深度论点和文章结构必须同时吸收 00N。没有 00M 时，本阶段不得生成最终答案。
11. 文末必须有一个简洁的“原文锚点 / 证据依据”小节，列出支撑关键判断的原子段编号、回目、原文短摘或摘要；若某个判断缺少原证，要标明需要补证。若你判断本题属于物象、空间物、器物或意象线，要检查该对象的主场景是否已经和原文锚点连上。
12. 主结论只能基于“写作前原文追证摘抄”中 evidence_readiness=“原文足证”的项；若有 00N，00N 只能提供论点结构和增量解释，不能替代 00M 的证据等级。若 00M 缺失，立即停止并要求先生成 00M；`摘录不足/摘要定位/需补整回` 只能写进补证说明，不得当作主线结论。
13. 文末增加“证据等级说明”小节：逐条注明每个关键判断的 evidence_readiness，并说明是否是原文连续回读支撑。
14. 如果“Codex 指挥中心｜材料池判定”的 writing_mode、“Codex 精读材料词”的 writing_permission、“Codex 写作前原文追证摘抄”的 writing_permission 或“Codex 深度见解增量稿”的 writing_permission 是“先补证/先二次追证”，你只能写补证说明和谨慎临时判断，不能硬写完整结论。
15. 输出中文 Markdown。第一行是一个自然标题，不要写文件路径，不要调用命令。若你产生了“我不能写入目录/当前环境只读/无法保存文件”之类运行说明，不要放入最终答案正文。
"""


def _run_codex_final_synthesis(item: dict, result: dict) -> tuple[Path | None, str]:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    question_key = clean_text(item.get("question_key")) or safe_filename_part(question)
    task_intent = clean_text(item.get("task_intent"))
    requirements = clean_text(item.get("requirements"))
    if not request_id:
        return None, "缺少 request_id，无法生成 Codex 最终答案。"
    prereq = _final_answer_prerequisite_status(item, result)
    if not prereq.get("ok"):
        missing = "、".join(prereq.get("missing", []))
        return None, f"最终回答硬阻断：缺少 {missing}。必须先完成聚拢四件套、00I、00L 和 00M，不能用一次命中或目标稿位绕过。"

    CODEX_RUN_DIR.mkdir(parents=True, exist_ok=True)
    CODEX_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    prompt = _build_codex_final_prompt(question, task_intent, requirements, result)
    prompt_path = CODEX_RUN_DIR / f"{request_id}_prompt.md"
    last_path = CODEX_RUN_DIR / f"{request_id}_last_message.md"
    event_path = CODEX_RUN_DIR / f"{request_id}_events.log"
    prompt_path.write_text(prompt, encoding="utf-8")

    cmd = [
        _codex_executable(),
        "exec",
        "-C",
        str(ROOT),
        "--skip-git-repo-check",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "-s",
        "read-only",
        "--output-last-message",
        str(last_path),
    ]
    try:
        proc = _run_codex_command(
            cmd,
            prompt,
            timeout=CODEX_EXEC_TIMEOUT,
            event_path=event_path,
            request_id=request_id,
            stage="final_synthesis",
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    final_path = CODEX_FINAL_DIR / f"A_{request_id}_{question_key}.md"
    if proc.returncode != 0:
        recovered_answer = _normalize_codex_final_answer_text(_read_limited(last_path, 80000))
        if _is_valid_codex_final_answer_text(recovered_answer):
            final_path.write_text(recovered_answer + "\n", encoding="utf-8")
            _sync_codex_workflow_target(
                item,
                "codex_final_answer_target_md",
                "Codex 红楼解语",
                final_path,
                recovered_answer,
            )
            return final_path, ""
        detail = _read_limited(event_path, 4000)
        return None, f"Codex 最终综合失败，返回码 {proc.returncode}。{detail}"

    answer = _normalize_codex_final_answer_text(_read_limited(last_path, 80000))
    if not _is_valid_codex_final_answer_text(answer):
        return None, "Codex 最终综合结果疑似仍是工程过程稿，已拦截，不回显。"

    final_path.write_text(answer + "\n", encoding="utf-8")
    _sync_codex_workflow_target(
        item,
        "codex_final_answer_target_md",
        "Codex 红楼解语",
        final_path,
        answer,
    )
    return final_path, ""


def _pending_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        return ""
    after = text.split(marker, 1)[1]
    lines: list[str] = []
    for raw in after.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            break
        if not lines and not line.strip():
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _valid_final_answer_for_request(request_id: str) -> Path | None:
    if not CODEX_FINAL_DIR.exists() or not request_id:
        return None
    candidates = sorted(
        CODEX_FINAL_DIR.glob(f"A_{request_id}_*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if is_valid_codex_final_answer_file(path):
            return path
    return None


def _workflow_file_path(item: dict, key: str) -> Path | None:
    workflow_files = item.get("workflow_files", {})
    if isinstance(workflow_files, dict):
        path = _as_existing_file(workflow_files.get(key))
        if path:
            return path

    package = Path(clean_text(item.get("workflow_package")))
    filename = closed_loop.CORE_FILES.get(key)
    if package.exists() and package.is_dir() and filename:
        path = package / filename
        if path.exists() and path.is_file():
            return path
    return None


def _record_existing_file(record: dict | None, key: str) -> Path | None:
    if not isinstance(record, dict):
        return None
    path = _as_existing_file(record.get(key))
    if path:
        return path
    for bucket_key in ("core_files", "workflow_files"):
        bucket = record.get(bucket_key)
        if isinstance(bucket, dict):
            path = _as_existing_file(bucket.get(key))
            if path:
                return path
    return None


def _workflow_package_from_records(*records: dict | None) -> Path | None:
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("workflow_package", "package", "package_dir"):
            text = clean_text(record.get(key))
            if text:
                path = Path(text)
                if path.exists() and path.is_dir():
                    return path
    return None


def _package_glob_existing(package: Path | None, pattern: str, request_id: str = "") -> Path | None:
    if not package or not package.exists():
        return None
    if request_id:
        exact = package / pattern.replace("*", request_id)
        if exact.exists() and exact.is_file():
            return exact
    matches = sorted(path for path in package.glob(pattern) if path.is_file())
    return matches[-1] if matches else None


def _required_artifact_path(item: dict, result: dict, key: str, package: Path | None, patterns: tuple[str, ...] = ()) -> Path | None:
    for record in (result, item):
        path = _record_existing_file(record, key)
        if path:
            return path
    path = _workflow_file_path(item, key)
    if path:
        return path
    filename = closed_loop.CORE_FILES.get(key)
    if package and filename:
        candidate = package / filename
        if candidate.exists() and candidate.is_file():
            return candidate
    request_id = clean_text(item.get("request_id") or result.get("request_id"))
    for pattern in patterns:
        path = _package_glob_existing(package, pattern, request_id=request_id)
        if path:
            return path
    return None


def _final_answer_prerequisite_status(item: dict, result: dict | None = None) -> dict:
    result = result if isinstance(result, dict) else {}
    package = _workflow_package_from_records(result, item)
    missing: list[str] = []
    resolved: dict[str, str] = {}

    if not package:
        missing.append("workflow_package/package_dir")

    required = [
        ("aggregation_flow_lock_md", "00AC_聚拢库总入口流程锁", ()),
        ("aggregation_material_search_md", "00AG_聚拢库取材单", ()),
        ("material_pool_admission_csv", "00AI_聚拢入材料池清单", ()),
        ("aggregation_first_read_pool_md", "00AM_聚拢裁判首读材料池", ()),
        ("codex_material_judgment_md", "00I_Codex材料池判定.md", ("00I_Codex材料池判定_*.md",)),
        ("codex_material_judgment_json", "00I_Codex材料池判定.json", ("00I_Codex材料池判定_*.json",)),
        ("codex_close_reading_md", "00L_Codex精读材料词.md", ("00L_Codex精读材料词_*.md",)),
        ("codex_close_reading_json", "00L_Codex精读材料词.json", ("00L_Codex精读材料词_*.json",)),
        ("codex_original_reread_md", "00M_Codex写作前原文通读摘抄.md", ("00M_Codex写作前原文通读摘抄_*.md",)),
        ("codex_original_reread_json", "00M_Codex写作前原文通读摘抄.json", ("00M_Codex写作前原文通读摘抄_*.json",)),
    ]
    for key, label, patterns in required:
        path = _required_artifact_path(item, result, key, package, patterns)
        if path:
            resolved[key] = str(path)
        else:
            missing.append(label)

    for record in (result, item):
        if not isinstance(record, dict):
            continue
        policy = record.get("material_reread_policy")
        if isinstance(policy, dict) and clean_text(policy.get("decision")) == "不进入00M":
            missing.append("00M硬规则：不允许一次命中跳过")
        if clean_text(record.get("codex_original_reread_permission")) == "跳过00M":
            missing.append("00M硬规则：不允许跳过00M")
        if clean_text(record.get("codex_close_reading_permission")) == "跳过00L":
            missing.append("00L硬规则：不允许跳过00L")

    return {
        "ok": not missing,
        "missing": missing,
        "package": str(package or ""),
        "resolved": resolved,
    }


def _codex_artifact_pair_ready(
    item: dict,
    result: dict,
    md_key: str,
    json_key: str,
    md_pattern: str,
    json_pattern: str,
) -> bool:
    package = _workflow_package_from_records(result, item)
    return bool(
        _required_artifact_path(item, result, md_key, package, (md_pattern,))
        and _required_artifact_path(item, result, json_key, package, (json_pattern,))
    )


def _merge_codex_stage_result(
    result: dict,
    payload_key: str,
    stage_result: dict,
    permission_key: str = "",
) -> dict:
    updated = dict(result)
    core_files = dict(updated.get("core_files", {}) if isinstance(updated.get("core_files"), dict) else {})
    md_path = clean_text(stage_result.get("md_path"))
    json_path = clean_text(stage_result.get("json_path"))
    if md_path:
        updated[f"{payload_key}_md"] = md_path
        core_files[f"{payload_key}_md"] = md_path
    if json_path:
        updated[f"{payload_key}_json"] = json_path
        core_files[f"{payload_key}_json"] = json_path
    if isinstance(stage_result.get("payload"), dict):
        updated[payload_key] = stage_result.get("payload", {})
    if permission_key:
        updated[permission_key] = clean_text(stage_result.get("writing_permission") or stage_result.get("writing_mode"))
    updated["core_files"] = core_files
    return updated


def _manifest_stage_payloads_for_refresh(package: Path, item: dict, result: dict) -> tuple[dict, dict, dict, dict, dict, dict, str, str]:
    manifest_path = package / closed_loop.CORE_FILES["manifest"]
    manifest = read_json(manifest_path, {}) if manifest_path.exists() else {}
    if not isinstance(manifest, dict):
        manifest = {}
    results = manifest.get("results", {})
    if not isinstance(results, dict):
        results = {}
    question = (
        clean_text(item.get("question"))
        or clean_text(result.get("question"))
        or clean_text(manifest.get("question"))
    )
    params = manifest.get("parameters", {})
    route_context = (
        clean_text(result.get("route_context"))
        or clean_text(params.get("route_context") if isinstance(params, dict) else "")
        or clean_text(item.get("task_intent"))
    )

    judgment_result = dict(results.get("judgment", {}) if isinstance(results.get("judgment"), dict) else {})
    library_flow = dict(results.get("library_flow", {}) if isinstance(results.get("library_flow"), dict) else {})
    research_result = dict(results.get("research", {}) if isinstance(results.get("research"), dict) else {})
    review_result = dict(results.get("review", {}) if isinstance(results.get("review"), dict) else {})
    readback_result = dict(results.get("readback", {}) if isinstance(results.get("readback"), dict) else {})

    def ensure_package_file(payload: dict, key: str, core_key: str) -> None:
        value = clean_text(payload.get(key))
        path = Path(value) if value else Path()
        if value and not path.is_absolute():
            rooted = ROOT / value
            if rooted.exists():
                payload[key] = str(rooted)
                return
        if value and path.exists():
            payload[key] = str(path)
            return
        candidate = package / closed_loop.CORE_FILES[core_key]
        if candidate.exists():
            payload[key] = str(candidate)

    ensure_package_file(research_result, "triaged_csv", "triaged_csv")
    ensure_package_file(review_result, "review_csv", "review_csv")
    ensure_package_file(readback_result, "writing_md", "writing_md")
    if not readback_result.get("total_rows") and (package / closed_loop.CORE_FILES["review_csv"]).exists():
        try:
            with (package / closed_loop.CORE_FILES["review_csv"]).open(encoding="utf-8-sig", newline="") as handle:
                readback_result["total_rows"] = max(sum(1 for _ in handle) - 1, 0)
        except OSError:
            pass

    return manifest, judgment_result, library_flow, research_result, review_result, readback_result, question, route_context


def _refresh_codex_package_post_exit_state(item: dict, result: dict) -> dict:
    package = _workflow_package_from_records(result, item)
    if not package:
        return {"ok": False, "error": "缺少 workflow_package/package_dir，无法刷新出口状态。", "result": result}
    try:
        (
            manifest,
            judgment_result,
            library_flow,
            research_result,
            review_result,
            readback_result,
            question,
            route_context,
        ) = _manifest_stage_payloads_for_refresh(package, item, result)
        pipeline_audit = closed_loop.build_codex_pipeline_audit(
            question=question,
            route_context=route_context,
            package_dir=package,
            judgment_result=judgment_result,
            library_flow_payload=library_flow,
            research_result=research_result,
            review_result=review_result,
            readback_result=readback_result,
        )
        second_round_decision = pipeline_audit.get("second_round_decision", {})
        if not isinstance(second_round_decision, dict):
            second_round_decision = {}
        final_gate = closed_loop.build_codex_final_answer_gate(
            question=question,
            route_context=route_context,
            package_dir=package,
            review_result=review_result,
            readback_result=readback_result,
            pipeline_audit=pipeline_audit,
            second_round_decision=second_round_decision,
        )
        if manifest:
            manifest.setdefault("results", {})
            if isinstance(manifest["results"], dict):
                manifest["results"]["pipeline_audit"] = pipeline_audit
                manifest["results"]["codex_final_answer_gate"] = final_gate
            manifest["status"] = (
                "等待 Codex 红楼解语：00I/00L/00M 已完成，可以进入最终答案写作门。"
                if pipeline_audit.get("summary", {}).get("final_prewrite_ready")
                else "等待 Codex 生成 00I/00L/00M；最终答案硬阻断：候选材料已回聚拢库并进入材料池，但未完成材料池判定、精读材料词和写作前原文追证摘抄，不得写红楼解语。"
            )
            core_files = manifest.setdefault("core_files", {})
            if isinstance(core_files, dict):
                core_files["pipeline_audit_md"] = str(package / closed_loop.CORE_FILES["pipeline_audit_md"])
                core_files["pipeline_audit_json"] = str(package / closed_loop.CORE_FILES["pipeline_audit_json"])
                core_files["codex_final_answer_gate_md"] = str(package / closed_loop.CORE_FILES["codex_final_answer_gate_md"])
                core_files["codex_final_answer_gate_json"] = str(package / closed_loop.CORE_FILES["codex_final_answer_gate_json"])
                core_files["codex_final_answer_target_md"] = str(package / closed_loop.CORE_FILES["codex_final_answer_target_md"])
            manifest_path = package / closed_loop.CORE_FILES["manifest"]
            overview_path = package / closed_loop.CORE_FILES["overview"]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            overview_path.write_text(closed_loop.render_overview(manifest), encoding="utf-8")

        updated = dict(result)
        updated["pipeline_audit"] = pipeline_audit
        updated["codex_final_answer_gate"] = final_gate
        core_files = dict(updated.get("core_files", {}) if isinstance(updated.get("core_files"), dict) else {})
        core_files["pipeline_audit_md"] = str(package / closed_loop.CORE_FILES["pipeline_audit_md"])
        core_files["pipeline_audit_json"] = str(package / closed_loop.CORE_FILES["pipeline_audit_json"])
        core_files["codex_final_answer_gate_md"] = str(package / closed_loop.CORE_FILES["codex_final_answer_gate_md"])
        core_files["codex_final_answer_gate_json"] = str(package / closed_loop.CORE_FILES["codex_final_answer_gate_json"])
        core_files["codex_final_answer_target_md"] = str(package / closed_loop.CORE_FILES["codex_final_answer_target_md"])
        updated["core_files"] = core_files
        return {
            "ok": True,
            "pipeline_audit": pipeline_audit,
            "codex_final_answer_gate": final_gate,
            "result": updated,
            "workflow_payload": _workflow_queue_payload(updated),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "result": result}


def _ensure_codex_exit_artifacts(item: dict, result: dict | None = None) -> dict:
    """Complete the generic 00I -> 00L -> 00M exit chain for an existing package."""
    result = dict(result) if isinstance(result, dict) else {}
    package = _workflow_package_from_records(result, item)
    if not package:
        return {
            "ok": False,
            "attempted": False,
            "error": "缺少 workflow_package/package_dir，无法补齐 Codex 出口材料。",
            "result": result,
        }

    result.setdefault("package", str(package))
    result.setdefault("package_dir", str(package))
    base_item = {
        **item,
        "package": str(package),
        "package_dir": str(package),
        "workflow_package": str(package),
    }
    steps: list[dict] = []
    attempted = False

    def step_item(current_result: dict) -> dict:
        return {**base_item, **_workflow_queue_payload(current_result)}

    if not _codex_artifact_pair_ready(
        base_item,
        result,
        "codex_material_judgment_md",
        "codex_material_judgment_json",
        "00I_Codex材料池判定_*.md",
        "00I_Codex材料池判定_*.json",
    ):
        attempted = True
        material_judgment = _run_codex_material_judgment(step_item(result), result)
        steps.append({"stage": "00I_Codex材料池判定", "ok": bool(material_judgment.get("ok")), "error": clean_text(material_judgment.get("error"))})
        if not material_judgment.get("ok"):
            return {
                "ok": False,
                "attempted": attempted,
                "error": f"00I_Codex材料池判定生成失败：{clean_text(material_judgment.get('error'))}",
                "steps": steps,
                "result": result,
            }
        result = _merge_codex_stage_result(
            result,
            "codex_material_judgment",
            material_judgment,
            "codex_material_writing_mode",
        )

    if not _codex_artifact_pair_ready(
        base_item,
        result,
        "codex_close_reading_md",
        "codex_close_reading_json",
        "00L_Codex精读材料词_*.md",
        "00L_Codex精读材料词_*.json",
    ):
        attempted = True
        close_reading = _run_codex_close_reading(step_item(result), result)
        steps.append({"stage": "00L_Codex精读材料词", "ok": bool(close_reading.get("ok")), "error": clean_text(close_reading.get("error"))})
        if not close_reading.get("ok"):
            return {
                "ok": False,
                "attempted": attempted,
                "error": f"00L_Codex精读材料词生成失败：{clean_text(close_reading.get('error'))}",
                "steps": steps,
                "result": result,
            }
        result = _merge_codex_stage_result(
            result,
            "codex_close_reading",
            close_reading,
            "codex_close_reading_permission",
        )

    if not _codex_artifact_pair_ready(
        base_item,
        result,
        "codex_original_reread_md",
        "codex_original_reread_json",
        "00M_Codex写作前原文通读摘抄_*.md",
        "00M_Codex写作前原文通读摘抄_*.json",
    ):
        attempted = True
        original_reread = _run_codex_original_reread(step_item(result), result)
        steps.append({"stage": "00M_Codex写作前原文通读摘抄", "ok": bool(original_reread.get("ok")), "error": clean_text(original_reread.get("error"))})
        if not original_reread.get("ok"):
            return {
                "ok": False,
                "attempted": attempted,
                "error": f"00M_Codex写作前原文通读摘抄生成失败：{clean_text(original_reread.get('error'))}",
                "steps": steps,
                "result": result,
            }
        result = _merge_codex_stage_result(
            result,
            "codex_original_reread",
            original_reread,
            "codex_original_reread_permission",
        )

    final_item = step_item(result)
    prereq = _final_answer_prerequisite_status(final_item, result)
    refresh = {}
    if prereq.get("ok"):
        refresh = _refresh_codex_package_post_exit_state(final_item, result)
        if refresh.get("ok"):
            result = refresh.get("result", result)
            steps.append({"stage": "00N/00ZD出口状态刷新", "ok": True, "error": ""})
        else:
            steps.append({"stage": "00N/00ZD出口状态刷新", "ok": False, "error": clean_text(refresh.get("error"))})
    return {
        "ok": bool(prereq.get("ok")),
        "attempted": attempted,
        "error": "" if prereq.get("ok") else "、".join(prereq.get("missing", [])),
        "steps": steps,
        "prereq": prereq,
        "result": result,
        "workflow_payload": _workflow_queue_payload(result),
        "refresh": refresh,
    }


def _sync_codex_workflow_target(
    item: dict,
    key: str,
    title: str,
    source_path: str | Path,
    body: str,
) -> Path | None:
    target = _workflow_file_path(item, key)
    if not target:
        return None
    source = clean_text(str(source_path))
    content = body if isinstance(body, str) else str(body)
    header = [
        f"# {title}",
        "",
        "生成状态：已由 Codex 写回",
        f"生成时间：{datetime.now().isoformat(timespec='seconds')}",
    ]
    if source:
        header.append(f"来源文件：`{source}`")
    target.write_text("\n".join(header).rstrip() + "\n\n" + content.rstrip() + "\n", encoding="utf-8")
    return target


def register_codex_target_answer(item: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    question = clean_text(item.get("question"))
    question_key = clean_text(item.get("question_key")) or safe_filename_part(question)
    if not request_id:
        return {"ok": False, "reason": "缺少 request_id，无法登记最终回显稿。"}
    prereq = _final_answer_prerequisite_status(item, {})
    if not prereq.get("ok"):
        return {
            "ok": False,
            "reason": "最终答案登记硬阻断：00L/00M 等前置闭环未完成，不登记已有答案或目标稿。",
            "missing": prereq.get("missing", []),
            "package": prereq.get("package", ""),
        }

    existing_answer = _valid_final_answer_for_request(request_id)
    if existing_answer:
        existing_text = existing_answer.read_text(encoding="utf-8", errors="ignore")
        normalized_text = _normalize_codex_final_answer_text(existing_text)
        if normalized_text and normalized_text != existing_text.strip():
            existing_answer.write_text(normalized_text + "\n", encoding="utf-8")
        if normalized_text:
            _sync_codex_workflow_target(
                item,
                "codex_final_answer_target_md",
                "Codex 红楼解语",
                existing_answer,
                normalized_text,
            )
        updated = upsert_item(
            {
                **item,
                "request_id": request_id,
                "processing_started_at": "",
                "status": "已处理",
                "answer_md": str(existing_answer),
                "answer_type": clean_text(item.get("answer_type")) or "codex_synthesized",
                "answer_quality": _answer_quality_by_type(clean_text(item.get("answer_type")) or "codex_synthesized"),
                "error": "",
            }
        )
        return {"ok": True, "reason": "existing_final_answer", "answer_md": str(existing_answer), "item": updated}

    target = _workflow_file_path(item, "codex_final_answer_target_md")
    last_message = CODEX_RUN_DIR / f"{request_id}_last_message.md"
    candidate_sources = [path for path in (target, last_message) if path and path.exists()]
    if not candidate_sources:
        return {"ok": False, "reason": "未找到 Codex 红楼解语目标稿位或最终运行消息。"}

    valid_source = next((path for path in candidate_sources if is_valid_codex_final_answer_file(path)), None)
    if not valid_source:
        return {
            "ok": False,
            "reason": "尚未发现有效 Codex 最终稿，保持等待；不会用占位稿、材料包或模块稿冒充答案。",
            "target_md": str(target or ""),
            "last_message_md": str(last_message if last_message.exists() else ""),
        }

    CODEX_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    final_path = CODEX_FINAL_DIR / f"A_{request_id}_{question_key}.md"
    answer_text = _normalize_codex_final_answer_text(valid_source.read_text(encoding="utf-8", errors="ignore"))
    final_path.write_text(answer_text + "\n", encoding="utf-8")
    _sync_codex_workflow_target(
        item,
        "codex_final_answer_target_md",
        "Codex 红楼解语",
        final_path,
        answer_text,
    )
    updated = upsert_item(
        {
            **item,
            "request_id": request_id,
            "processing_started_at": "",
            "question": question,
            "question_key": question_key,
            "status": "已处理",
            "answer_md": str(final_path),
            "answer_type": "codex_target_writeback",
            "answer_source": valid_source.name,
            "answer_quality": _answer_quality_by_type("codex_target_writeback"),
            "error": "",
            "audit_note": "已从 Codex 红楼解语目标稿位或最终运行消息登记到最终答案目录；未调用本地模块稿，未补写单题答案。",
            "retry_count": 0,
        }
    )
    return {"ok": True, "reason": "registered_codex_target", "answer_md": str(final_path), "source_md": str(valid_source), "item": updated}


def _item_from_pending_file(path: Path) -> dict | None:
    stem = path.stem
    if not stem.startswith("Q_"):
        return None
    rest = stem[2:]
    if "_" not in rest:
        return None
    request_id, question_key = rest.split("_", 1)
    request_id = clean_text(request_id)
    if not request_id:
        return None
    text = path.read_text(encoding="utf-8", errors="ignore")
    question = _pending_section(text, "用户问题")
    display_question = _pending_section(text, "原始提问") or question
    engineering_question = _pending_section(text, "工程触发问题")
    task_intent = _pending_section(text, "任务类型")
    requirements = _pending_section(text, "附加要求")
    answer_path = _valid_final_answer_for_request(request_id)
    stat = path.stat()
    return {
        "request_id": request_id,
        "question": question,
        "display_question": display_question,
        "engineering_question": engineering_question,
        "question_key": question_key,
        "task_intent": task_intent,
        "requirements": "" if requirements == "无" else requirements,
        "status": "已处理" if answer_path else "待Codex处理",
        "recall_phrase": f"处理红楼梦待回答 {request_id}",
        "pending_md": str(path),
        "answer_md": str(answer_path or ""),
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _merge_items_with_pending_files(items: list[dict]) -> list[dict]:
    by_id = {clean_text(item.get("request_id")): dict(item) for item in items if clean_text(item.get("request_id"))}
    active_request_id = current_request_id()
    for path in sorted(CODEX_PENDING_DIR.glob("Q_*.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        pending_item = _item_from_pending_file(path)
        if not pending_item:
            continue
        request_id = pending_item["request_id"]
        if active_request_id and request_id != active_request_id:
            continue
        existing = by_id.get(request_id, {})
        merged = {**pending_item, **existing}
        answer_md = clean_text(merged.get("answer_md"))
        answer_path = Path(answer_md) if answer_md else _valid_final_answer_for_request(request_id)
        valid_answer = bool(answer_path and answer_path.exists() and answer_path.stem.startswith(f"A_{request_id}_") and is_valid_codex_final_answer_file(answer_path))
        if valid_answer:
            merged["answer_md"] = str(answer_path)
            if merged.get("status") != "处理失败":
                merged["status"] = "已处理"
        else:
            merged["answer_md"] = ""
            if merged.get("status") == "已处理":
                merged["status"] = "待Codex处理"
                merged["error"] = "旧最终答案未通过 Codex 最终回答质量检查，已从待回答底账恢复并等待重跑。"
        by_id[request_id] = merged

    merged_items = single_queue_items(list(by_id.values()), preferred_request_id=active_request_id)
    merged_items.sort(key=lambda item: clean_text(item.get("updated_at")), reverse=True)
    return merged_items


def load_items() -> list[dict]:
    data = read_json(CODEX_QUEUE_JSON, {"items": []})
    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        items = []
    merged = _merge_items_with_pending_files(items)
    if merged:
        if merged != items:
            save_items(merged)
        return merged
    return restore_latest_item()


def restore_latest_item() -> list[dict]:
    latest_json = CODEX_ANSWER_ROOT / "latest_question.json"
    latest = read_json(latest_json, {})
    if not isinstance(latest, dict):
        return []
    request_id = clean_text(latest.get("request_id"))
    if not request_id:
        return []
    item = {
        "request_id": request_id,
        "question": clean_text(latest.get("question")),
        "display_question": clean_text(latest.get("display_question")),
        "engineering_question": clean_text(latest.get("engineering_question")),
        "question_key": clean_text(latest.get("question_key")),
        "task_intent": clean_text(latest.get("task_intent")),
        "requirements": clean_text(latest.get("requirements")),
        "status": "待Codex处理",
        "recall_phrase": f"处理红楼梦待回答 {request_id}",
        "pending_md": clean_text(latest.get("pending_md")),
        "answer_md": "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_items([item])
    return [item]


def render_queue_markdown(items: list[dict]) -> str:
    pending = [item for item in items if item.get("status") != "已处理"]
    processed = [item for item in items if item.get("status") == "已处理"]
    pending.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    processed.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

    def row(item: dict) -> str:
        question = clean_text(item.get("question")).replace("\n", " ")[:80]
        answer = clean_text(item.get("answer_md") or "尚未回写")
        audit_note = clean_text(item.get("audit_note") or item.get("archive_note")).replace("\n", " ")[:120]
        retry_count = _int_value(item.get("retry_count"), 0)
        return (
            f"| {item.get('request_id', '')} | {item.get('status', '')} | {retry_count} | "
            f"{question} | `{item.get('recall_phrase', '')}` | "
            f"{item.get('pending_md', '')} | {answer} | {item.get('updated_at', '')} | {audit_note} |"
        )

    lines = [
        "# 红楼梦研究台｜Codex召回队列",
        "",
        "## 当前未处理",
        "",
        "| 请求ID | 状态 | 重试 | 原始问题 | 召回口令 | 待回答文件 | 答案文件 | 更新时间 | 审计备注 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(row(item) for item in pending)
    lines.extend(
        [
            "",
            "## 已处理",
            "",
            "| 请求ID | 状态 | 原始问题 | 召回口令 | 待回答文件 | 答案文件 | 更新时间 | 审计备注 |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    lines.extend(row(item) for item in processed)
    return "\n".join(lines) + "\n"


def save_items(items: list[dict]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    keep_request_id = current_request_id()
    archive_old_queue_items(items, keep_request_id, "recall_save_single_thread_queue")
    items = single_queue_items(items, preferred_request_id=keep_request_id)
    write_json(CODEX_QUEUE_JSON, {"updated_at": now, "items": items})
    CODEX_QUEUE_MD.write_text(render_queue_markdown(items), encoding="utf-8")


def parse_iso_datetime(value: object) -> datetime | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _int_value(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_return_code(raw_error: str) -> int | None:
    text = clean_text(raw_error)
    if not text:
        return None
    lower = text.lower()
    for marker in ("return code", "返回码", "returncode", "返回状态"):
        idx = lower.find(marker)
        if idx >= 0:
            after = text[idx + len(marker) :]
            for token in after.replace(",", " ").replace(";", " ").split():
                if token.lstrip("-+").isdigit():
                    return int(token)
            break
    for token in text.replace(",", " ").replace(";", " ").replace(":", " ").split():
        if token.lower() in {"code", "返回码"} and token.lstrip("-+").isdigit():
            return int(token)
    return None


def _infer_error_stage(raw_error: str) -> str:
    lowered = clean_text(raw_error).lower()
    if not lowered:
        return ""
    if any(signal in lowered for signal in ("查询词路", "query plan", "入口词门", "entry gate", "query_flow_profile")):
        return "query_strategy"
    if any(signal in lowered for signal in ("过程判别", "process judgment", "codex_process_judgment", "材料池判定前")):
        return "process_judgment"
    if any(signal in lowered for signal in ("材料池判定", "material judgment", "codex_material_judgment")):
        return "material_judgment"
    if any(signal in lowered for signal in ("原文通读", "通读摘抄", "original reread", "codex_original_reread")):
        return "original_reread"
    if any(signal in lowered for signal in ("精读", "close reading", "codex_close_reading", "精读材料词")):
        return "close_reading"
    if any(signal in lowered for signal in ("最终合成", "最终回显", "final synthesis", "final answer", "read back")):
        return "final_synthesis"
    if any(signal in lowered for signal in ("traceback", "exception", "runtime", "stack")):
        return "runtime"
    return ""


def _classify_error(raw_error: str) -> dict[str, object]:
    text = clean_text(raw_error)
    lowered = text.lower()
    return_code = _extract_return_code(text)
    stage = _infer_error_stage(text)

    if any(
        signal in lowered
        for signal in (
            "timed out",
            "timeout",
            "timed_out",
            "超时",
            "execution timeout",
            "timeout_expired",
            "Process timed out",
        )
    ):
        return {
            "error_category": "timeout",
            "error_retryable": True,
            "error_stage": stage or "runtime",
            "error_snippet": text[:240],
            "return_code": return_code,
        }

    if any(
        signal in lowered
        for signal in (
            "connection",
            "连接",
            "stream disconnected",
            "could not resolve host",
            "name or service not known",
            "network is unreachable",
            "no route to host",
            "connection reset",
            "temporary failure",
            "service unavailable",
            "chatgpt.com",
        )
    ):
        return {
            "error_category": "network",
            "error_retryable": True,
            "error_stage": stage or "runtime",
            "error_snippet": text[:240],
            "return_code": return_code,
        }

    if any(
        signal in lowered
        for signal in (
            "not a valid json",
            "未返回有效 json",
            "invalid json",
            "无法读取",
            "未返回有效",
            "疑似仍是工程过程稿",
            "不是有效",
            "未通过 codex 最终回答质量检查",
        )
    ):
        return {
            "error_category": "invalid_output",
            "error_retryable": False,
            "error_stage": stage or "runtime",
            "error_snippet": text[:240],
            "return_code": return_code,
        }

    return {
        "error_category": "runtime",
        "error_retryable": False,
        "error_stage": stage or "runtime",
        "error_snippet": text[:240],
        "return_code": return_code,
    }


def _can_retry_failed_item(item: dict) -> bool:
    if item.get("status") != "处理失败":
        return False

    if _parse_bool(item.get("error_retryable"), default=True) is False:
        return False

    error_category = clean_text(item.get("error_category"))
    if error_category in {"invalid_output", "manual", "logic"}:
        return False

    max_retries = PROCESS_RETRY_MAX_ATTEMPTS
    if _parse_bool(item.get("error_retryable"), default=True) and clean_text(item.get("error_category")) == "network" and _workflow_package_path(item):
        max_retries = PROCESS_FINAL_RETRY_BUDGET

    if _int_value(item.get("retry_count")) >= max_retries:
        return False
    updated = parse_iso_datetime(item.get("updated_at")) or parse_iso_datetime(item.get("processing_started_at"))
    if not updated:
        return True
    return (datetime.now() - updated).total_seconds() >= PROCESS_RETRY_INTERVAL_SECONDS


def _parse_bool(value: object, default: bool = False) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on", "是", "ok"}:
        return True
    if text in {"false", "0", "no", "n", "off", "否", ""}:
        return False
    return default


def _workflow_package_path(item: dict) -> str:
    package = _workflow_package_from_records(item)
    if package:
        return str(package)
    return ""


def _has_final_materials_for_rewrite(item: dict) -> bool:
    return bool(_final_answer_prerequisite_status(item, {}).get("ok"))


def _has_workflow_gate_ready(item: dict) -> bool:
    gate_key = "codex_final_answer_gate_json"
    if _as_existing_file(item.get(gate_key)):
        return True
    gate_value = clean_text(item.get(gate_key))
    if gate_value:
        return True
    return bool(_workflow_package_path(item)) and _as_existing_file(item.get("workflow_status_json"))


def is_runnable_item(item: dict) -> bool:
    status = clean_text(item.get("status"))
    if status in {"已处理", "等待补证", "待人工复核"}:
        return False
    if status == "待最终回显稿":
        if not _workflow_package_path(item):
            return False
        if _int_value(item.get("retry_count")) >= PROCESS_FINAL_RETRY_BUDGET:
            return False
        updated = parse_iso_datetime(item.get("updated_at")) or parse_iso_datetime(item.get("processing_started_at"))
        if not updated:
            return True
        return (datetime.now() - updated).total_seconds() >= PROCESS_RETRY_INTERVAL_SECONDS
    if status in {"待Codex处理", "待处理"}:
        return True
    if status == "处理失败":
        return _can_retry_failed_item(item)
    if status == "处理中":
        if is_abandoned_processing_item(item):
            return False
        if _int_value(item.get("retry_count")) >= PROCESS_RETRY_MAX_ATTEMPTS:
            return False
        return is_stale_processing_item(item)
    return bool(clean_text(item.get("request_id")))


def is_stale_processing_item(item: dict, max_age_seconds: int = PROCESSING_STALE_SECONDS) -> bool:
    if item.get("status") != "处理中":
        return False
    started = parse_iso_datetime(item.get("processing_started_at")) or parse_iso_datetime(item.get("updated_at"))
    if not started:
        return True
    return (datetime.now() - started).total_seconds() > max_age_seconds


def is_abandoned_processing_item(item: dict, max_age_seconds: int = PROCESSING_ABANDON_SECONDS) -> bool:
    if item.get("status") != "处理中":
        return False
    if _int_value(item.get("retry_count")) > 0:
        return False
    started = parse_iso_datetime(item.get("processing_started_at")) or parse_iso_datetime(item.get("updated_at"))
    if not started:
        return True
    return (datetime.now() - started).total_seconds() > max_age_seconds


def revive_stale_processing_item(item: dict) -> dict:
    request_id = clean_text(item.get("request_id"))
    if not request_id:
        return item
    return upsert_item(
        {
            **item,
            "request_id": request_id,
            "status": "待Codex处理",
            "processing_started_at": "",
            "answer_md": clean_text(item.get("answer_md")),
            "error": "上一次处理中超过保护时间，已自动重新入队，避免页面永久等待。",
            "retry_count": _int_value(item.get("retry_count"), 0) + 1,
        }
    )


def _revive_stale_processing_items(items: list[dict]) -> list[dict]:
    if not items:
        return items
    revived_items: list[dict] = []
    changed = False
    for item in items:
        if item.get("status") == "处理中" and is_abandoned_processing_item(item):
            revived = revive_stale_processing_item(item)
            revived_items.append(revived)
            changed = changed or revived.get("status") != item.get("status") or revived.get("retry_count") != item.get("retry_count")
        else:
            revived_items.append(item)
    if changed:
        save_items(revived_items)
    return revived_items


def select_item(selector: str) -> dict:
    items = _revive_stale_processing_items(load_items())
    if not items:
        raise SystemExit("召回队列为空。请先在研究台提交一个问题。")
    selector = clean_text(selector) or "latest"
    if selector == "latest":
        recover = auto_recover_stale_request_lock(timeout_seconds=PROCESSING_AUTO_CLEAR_SECONDS)
        if recover.get("released"):
            items = _revive_stale_processing_items(load_items())
        candidates = [item for item in items if is_runnable_item(item)]
        if not candidates:
            raise SystemExit("队列没有可自动推进项；等待补证、人工复核或远古处理中任务不会自动抢位。")
        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return candidates[0]
    for item in items:
        if item.get("request_id") == selector:
            return item
    raise SystemExit(f"未找到请求：{selector}")


def upsert_item(item: dict) -> dict:
    items = load_items()
    request_id = clean_text(item.get("request_id"))
    if not request_id:
        return item
    incoming = dict(item)
    incoming_answer = clean_text(incoming.get("answer_md"))
    incoming_status = clean_text(incoming.get("status"))
    incoming_error = clean_text(incoming.get("error"))
    active_request_id = current_request_id()
    if active_request_id and request_id != active_request_id:
        active_item = next((old for old in items if clean_text(old.get("request_id")) == active_request_id), {})
        if active_item:
            save_items([active_item])
            return dict(active_item)
        return {
            "request_id": request_id,
            "status": "旧线程已退出",
            "error": "旧线程完成后不再回写当前队列。",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    if is_request_aborted(request_id) and incoming_status != "已终止":
        existing = next((old for old in items if old.get("request_id") == request_id), {})
        if existing:
            return dict(existing)
        incoming = {
            **incoming,
            "status": "已终止",
            "answer_md": "",
            "error": "用户已点击停止解语；忽略后台迟到写回。",
            "error_category": "user_abort",
            "error_stage": "manual_stop",
            "error_snippet": "",
            "return_code": "",
            "error_retryable": False,
            "processing_started_at": "",
        }
        incoming_status = clean_text(incoming.get("status"))
        incoming_error = clean_text(incoming.get("error"))
    if incoming_status == "已处理" and not incoming_error:
        incoming["error_category"] = ""
        incoming["error_stage"] = ""
        incoming["error_snippet"] = ""
        incoming["error_retryable"] = False
    if incoming_answer:
        answer_stem = Path(incoming_answer).stem
        if request_id and answer_stem.startswith("A_") and not answer_stem.startswith(f"A_{request_id}_"):
            incoming["answer_md"] = ""
            if clean_text(incoming.get("status")) == "已处理":
                incoming["status"] = "待Codex处理"
            incoming["error"] = f"答案文件不属于当前请求，已拦截旧答案回显：{incoming_answer}"
    existing = next((old for old in items if old.get("request_id") == request_id), {})
    remaining = [old for old in items if old.get("request_id") != request_id]
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"answer_md", "error", "error_snippet", "return_code"} and value in {"", None}:
            merged[key] = ""
            continue
        if key in {"processing_started_at"} and value == "":
            merged[key] = ""
            continue
        if value not in ("", None, []):
            merged[key] = value
    merged["request_id"] = request_id
    merged["updated_at"] = datetime.now().isoformat(timespec="seconds")
    remaining.append(merged)
    save_items(remaining)
    return merged


def extract_question_from_pending(path: Path, fallback: str = "") -> str:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8")
    marker = "## 用户问题"
    if marker not in text:
        return fallback
    after_marker = text.split(marker, 1)[1]
    lines = after_marker.splitlines()
    buffer: list[str] = []
    hit_content = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if hit_content:
                break
            continue
        if not hit_content:
            if stripped == "":
                continue
            hit_content = True
            if stripped:
                buffer.append(stripped)
        else:
            if stripped == "":
                break
            buffer.append(stripped)
    if buffer:
        return "\n".join(buffer).strip()
    return fallback


def _resolve_pending_file(item: dict) -> Path:
    pending = Path(clean_text(item.get("pending_md")))
    if pending.exists():
        return pending
    return CODEX_PENDING_DIR / clean_text(item.get("request_id"))


def aborted_process_result(item: dict, request_id: str, question_key: str) -> dict:
    upsert_item(
        {
            **item,
            "request_id": request_id,
            "question_key": question_key,
            "processing_started_at": "",
            "status": "已终止",
            "answer_md": "",
            "error": "用户点击“停止解语”；当前线程停止自动推进。",
            "error_category": "user_abort",
            "error_stage": "manual_stop",
            "error_snippet": "",
            "return_code": "",
            "error_retryable": False,
        }
    )
    return {"ok": False, "request_id": request_id, "reason": "已停止解语"}


def process_one(item: dict, run_smoke: bool = False) -> dict:
    request_id = clean_text(item.get("request_id"))
    question_key = clean_text(item.get("question_key")) or safe_filename_part(clean_text(item.get("question")))
    result: dict = {}
    flow_profile: dict = {}
    queue_status = clean_text(item.get("status"))
    if not request_id:
        return {"ok": False, "request_id": "", "reason": "缺少 request_id"}
    if is_request_aborted(request_id):
        return aborted_process_result(item, request_id, question_key)
    started_at = datetime.now().isoformat(timespec="seconds")

    if queue_status == FINAL_DISPLAY_WAIT_STATUS:
        pending_md = _resolve_pending_file(item)
        question = clean_text(item.get("question"))
        if not question:
            question = extract_question_from_pending(pending_md, fallback=question)
        if question:
            question_key = safe_filename_part(question)

        if not _workflow_package_path(item):
            upsert_item(
                {
                    "request_id": request_id,
                    "status": "处理失败",
                    "question": clean_text(item.get("question")),
                    "question_key": question_key,
                    "processing_started_at": "",
                    "answer_md": "",
                    "error": "待最终回显稿缺少 workflow_package，无法恢复到最终步骤。",
                    "error_category": "logic",
                    "error_stage": "workflow_recover",
                    "error_retryable": False,
                }
            )
            return {"ok": False, "request_id": request_id, "reason": "待最终回显稿缺少 workflow_package，无法恢复。"}

        package = _workflow_package_path(item)
        recovery_item = {
            **item,
            "request_id": request_id,
            "question": question,
            "question_key": question_key,
            "package": package,
            "status": queue_status,
        }

        if is_request_aborted(request_id):
            return aborted_process_result(recovery_item, request_id, question_key)
        if hasattr(register_codex_target_answer, "__call__"):
            registered = register_codex_target_answer(recovery_item)
            if registered.get("ok"):
                return {
                    "ok": True,
                    "request_id": request_id,
                    "reason": clean_text(registered.get("reason")) or "pending_final_target_registered",
                    "answer_md": clean_text(registered.get("answer_md")),
                }

        exit_artifacts = _ensure_codex_exit_artifacts(recovery_item, recovery_item)
        if exit_artifacts.get("ok"):
            recovery_result = exit_artifacts.get("result", recovery_item)
            workflow_payload = exit_artifacts.get("workflow_payload")
            if not isinstance(workflow_payload, dict):
                workflow_payload = _workflow_queue_payload(recovery_result)
            recovery_item = {
                **recovery_item,
                **workflow_payload,
                "codex_material_judgment_md": clean_text(recovery_result.get("codex_material_judgment_md")),
                "codex_material_judgment_json": clean_text(recovery_result.get("codex_material_judgment_json")),
                "codex_close_reading_md": clean_text(recovery_result.get("codex_close_reading_md")),
                "codex_close_reading_json": clean_text(recovery_result.get("codex_close_reading_json")),
                "codex_original_reread_md": clean_text(recovery_result.get("codex_original_reread_md")),
                "codex_original_reread_json": clean_text(recovery_result.get("codex_original_reread_json")),
            }
            upsert_item(
                {
                    **item,
                    "request_id": request_id,
                    "question": question,
                    "question_key": question_key,
                    "status": queue_status,
                    "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                    "error": "",
                    "error_category": "",
                    "error_stage": "",
                    "error_snippet": "",
                    "error_retryable": False,
                    "audit_note": "待最终回显稿已补齐正式 00I/00L/00M 出口材料，继续进入最终答案门。",
                    **workflow_payload,
                }
            )
        elif exit_artifacts.get("attempted"):
            retry_count = _int_value(item.get("retry_count"), 0) + 1
            exit_error = clean_text(exit_artifacts.get("error")) or "00I/00L/00M 出口材料补齐失败。"
            if retry_count >= PROCESS_FINAL_RETRY_BUDGET:
                upsert_item(
                    {
                        **item,
                        "request_id": request_id,
                        "question": question,
                        "question_key": question_key,
                        "processing_started_at": "",
                        "status": "处理失败",
                        "error": f"待最终回显稿补齐 00I/00L/00M 失败，且重试次数超限：{exit_error}",
                        "error_category": "runtime",
                        "error_stage": "exit_artifact_completion",
                        "error_snippet": exit_error,
                        "error_retryable": False,
                        "answer_md": "",
                        "retry_count": retry_count,
                    }
                )
                return {"ok": False, "request_id": request_id, "reason": exit_error}
            upsert_item(
                {
                    **item,
                    "request_id": request_id,
                    "question": question,
                    "question_key": question_key,
                    "processing_started_at": "",
                    "status": FINAL_DISPLAY_WAIT_STATUS,
                    "error": f"待最终回显稿补齐 00I/00L/00M 暂未成功，保留在出口恢复队列：{exit_error}",
                    "error_category": "network" if "stream disconnected" in exit_error.lower() else "runtime",
                    "error_stage": "exit_artifact_completion",
                    "error_retryable": True,
                    "answer_md": "",
                    "retry_count": retry_count,
                }
            )
            return {"ok": False, "request_id": request_id, "reason": exit_error}

        if _has_final_materials_for_rewrite(recovery_item):
            final_path, final_error = _run_codex_final_synthesis(
                recovery_item,
                recovery_result if "recovery_result" in locals() else recovery_item,
            )
            if is_request_aborted(request_id):
                return aborted_process_result(recovery_item, request_id, question_key)
            if final_path:
                updated = upsert_item(
                    {
                        **item,
                        "request_id": request_id,
                        "processing_started_at": "",
                        "question": clean_text(item.get("question")),
                        "question_key": question_key,
                        "status": "已处理",
                        "answer_md": str(final_path),
                        "answer_type": "codex_synthesized",
                        "answer_quality": _answer_quality_by_type("codex_synthesized"),
                        "error": "",
                        "retry_count": 0,
                        "audit_note": "待最终回显稿从工程产物直接恢复最终回答成功。",
                    }
                )
                return {"ok": True, "request_id": request_id, "answer_md": str(final_path), "result": updated}

            retry_count = _int_value(item.get("retry_count"), 0) + 1
            if retry_count >= PROCESS_FINAL_RETRY_BUDGET:
                upsert_item(
                    {
                        **item,
                        "request_id": request_id,
                        "question": clean_text(item.get("question")),
                        "question_key": question_key,
                        "processing_started_at": "",
                        "status": "处理失败",
                        "error": f"待最终回显稿重试次数超限，最终综合仍失败：{clean_text(final_error)}",
                        "error_category": "runtime",
                        "error_stage": "final_synthesis",
                        "error_snippet": clean_text(final_error),
                        "error_retryable": False,
                        "answer_md": "",
                        "retry_count": retry_count,
                    }
                )
                return {"ok": False, "request_id": request_id, "reason": clean_text(final_error)}

            upsert_item(
                {
                    **item,
                    "request_id": request_id,
                    "question": clean_text(item.get("question")),
                    "question_key": question_key,
                    "processing_started_at": "",
                    "status": FINAL_DISPLAY_WAIT_STATUS,
                    "error": f"待最终回显稿重试失败：{clean_text(final_error)}。",
                    "error_category": "network" if "stream disconnected" in clean_text(final_error).lower() else "runtime",
                    "error_stage": "final_synthesis",
                    "error_retryable": True,
                    "answer_md": "",
                    "retry_count": retry_count,
                }
            )
            return {"ok": False, "request_id": request_id, "reason": clean_text(final_error)}

        retry_count = _int_value(item.get("retry_count"), 0) + 1
        if retry_count >= PROCESS_FINAL_RETRY_BUDGET:
            upsert_item(
                {
                    **item,
                    "request_id": request_id,
                    "question": clean_text(item.get("question")),
                    "question_key": question_key,
                    "processing_started_at": "",
                    "status": "处理失败",
                    "error": "待最终回显稿缺少可用于续写的材料文件，已转回待处理重新启动红楼梦工程。",
                    "error_category": "logic",
                    "error_stage": "workflow_recover",
                    "error_retryable": True,
                    "answer_md": "",
                    "retry_count": retry_count,
                }
            )
            return {"ok": False, "request_id": request_id, "reason": "待最终回显稿缺少材料文件，已退回待处理。"}

        upsert_item(
            {
                **item,
                "request_id": request_id,
                "question": clean_text(item.get("question")),
                "question_key": question_key,
                "processing_started_at": "",
                "status": "待Codex处理",
                "error": "待最终回显稿缺少材料文件，已回退完整流程重跑红楼梦工程。",
                "error_category": "workflow_recover",
                "error_stage": "workflow_recover",
                "error_retryable": True,
                "answer_md": "",
                "retry_count": retry_count,
            }
        )
        return {"ok": False, "request_id": request_id, "reason": "待最终回显稿缺少材料文件，已退回完整流程重跑。"}

    upsert_item(
        {
            "request_id": request_id,
            "processing_started_at": started_at,
            "status": "处理中",
            "question": clean_text(item.get("question")),
            "question_key": question_key,
            "task_intent": clean_text(item.get("task_intent")),
            "requirements": clean_text(item.get("requirements")),
            "pending_md": clean_text(item.get("pending_md")),
            "recall_phrase": clean_text(item.get("recall_phrase")),
            "answer_md": clean_text(item.get("answer_md")),
            "error": "",
        }
    )
    try:
        pending_md = _resolve_pending_file(item)
        question = clean_text(item.get("question"))
        if not question:
            question = extract_question_from_pending(pending_md, fallback=question)
        if not question:
            raise RuntimeError("未能提取问题内容")

        existing_query_strategy = item.get("query_strategy") if isinstance(item.get("query_strategy"), dict) else {}
        query_strategy = _query_strategy_from_payload(existing_query_strategy, request_id)
        if not query_strategy.get("ok"):
            query_strategy = _run_codex_query_strategy({**item, "question": question, "question_key": question_key})
        if not query_strategy.get("ok"):
            fallback_strategy = _build_query_strategy_fallback(
                {**item, "question": question, "question_key": question_key},
                reason=clean_text(query_strategy.get("error", "")),
            )
            fallback_query_strategy = _query_strategy_from_payload(fallback_strategy, request_id)
            if not fallback_query_strategy.get("ok"):
                raise RuntimeError(f"Codex 查询词路失败，工程停在入口词门：{query_strategy.get('error', '')}")
            query_strategy = {
                **fallback_query_strategy,
                "error": clean_text(query_strategy.get("error", "") or fallback_query_strategy.get("error")),
                "reused": False,
                "fallback": True,
            }
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        flow_profile = _query_flow_profile(
            question,
            clean_text(item.get("task_intent")),
            clean_text(item.get("requirements")),
            query_strategy.get("payload", {}),
        )
        strategy_payload = query_strategy.get("payload", {})
        if clean_text(flow_profile.get("key")) == "fast_relation":
            strategy_payload = _fast_relation_search_term_guard(
                strategy_payload,
                _strategy_execution_terms(strategy_payload, _as_list(strategy_payload.get("search_terms"), limit=36)),
            )
            compact_strategy = _query_strategy_from_payload(strategy_payload, request_id)
            if compact_strategy.get("ok"):
                query_strategy = {
                    **query_strategy,
                    "payload": strategy_payload,
                    "route_context": compact_strategy.get("route_context", query_strategy.get("route_context", "")),
                    "terms": compact_strategy.get("terms", query_strategy.get("terms", [])),
                    "libraries": compact_strategy.get("libraries", query_strategy.get("libraries", [])),
                }
        upsert_item(
            {
                "request_id": request_id,
                "status": "处理中",
                "query_strategy_error": "" if query_strategy.get("ok") else clean_text(query_strategy.get("error", "")),
                "query_strategy": strategy_payload,
                "query_strategy_prompt": query_strategy.get("prompt_path", ""),
                "query_strategy_result": query_strategy.get("last_path", ""),
                "query_strategy_terms": query_strategy.get("terms", []),
                "query_strategy_libraries": query_strategy.get("libraries", []),
                "flow_profile": flow_profile,
            }
        )
        route_context = "\n".join(
            part
            for part in [
                _recall_gate_route_context(
                    question,
                    clean_text(item.get("task_intent")),
                    clean_text(item.get("requirements")),
                ),
                clean_text(item.get("task_intent")),
                clean_text(item.get("requirements")),
                clean_text(query_strategy.get("route_context")),
                _flow_profile_route_context(flow_profile),
            ]
            if part
        )
        result = closed_loop.talk_workflow(
            question=question,
            run_smoke=run_smoke,
            route_context=route_context,
        )
        result = {
            **result,
            "flow_profile": flow_profile,
        }
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        _emit_process_heartbeat(item, 'Codex 过程判定', '正在复习问题、过程包和工程链路，判断是否可继续。')
        process_judgment = _run_codex_process_judgment(
            {**item, "question": question, "question_key": question_key},
            result,
            pass_index=0,
        )
        if not process_judgment.get("ok"):
            raise RuntimeError(f"Codex 全流程过程判别失败，已停止进入材料池：{process_judgment.get('error', '')}")
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        process_judgments = [process_judgment.get("payload", {})]
        result = {
            **result,
            "codex_process_judgment_md": process_judgment.get("md_path", ""),
            "codex_process_judgment_json": process_judgment.get("json_path", ""),
            "codex_process_judgments": process_judgments,
            "core_files": {
                **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
            },
        }
        if MAX_SUPPLEMENT_PASSES > 0 and process_judgment.get("supplement_required") and _supplement_route_context_from_process(process_judgment):
            supplement_context = "\n".join(
                part
                for part in [
                    route_context,
                    _supplement_route_context_from_process(process_judgment),
                    "补查规矩：本地工程只按 Codex 过程判别给出的词、库和原文方向补查；不得自行扩写答案。",
                ]
                if part
            )
            supplement_result = closed_loop.talk_workflow(
                question=question,
                run_smoke=False,
                route_context=supplement_context,
            )
            result = {
                **result,
                "supplemental_results": [supplement_result],
                "supplemental_count": 1,
            }
            _emit_process_heartbeat(item, 'Codex 过程判定', '正在复习问题、过程包和工程链路，判断是否可继续。')
            process_judgment = _run_codex_process_judgment(
                {**item, "question": question, "question_key": question_key},
                result,
                pass_index=1,
            )
            if not process_judgment.get("ok"):
                raise RuntimeError(f"Codex 补查后过程判别失败，已停止进入材料池：{process_judgment.get('error', '')}")
            if is_request_aborted(request_id):
                return aborted_process_result(item, request_id, question_key)
            process_judgments.append(process_judgment.get("payload", {}))
            result = {
                **result,
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgments": process_judgments,
                "core_files": {
                    **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                    "codex_process_judgment_md": process_judgment.get("md_path", ""),
                    "codex_process_judgment_json": process_judgment.get("json_path", ""),
                },
            }
        workflow_payload = _workflow_queue_payload(result)
        if not process_judgment.get("proceed_to_material_judgment"):
            reason = clean_text(
                process_judgment.get("payload", {}).get("reason_to_proceed_or_stop")
                if isinstance(process_judgment.get("payload"), dict)
                else ""
            )
            upsert_item(
                {
                    "request_id": request_id,
                    "question": question,
                    "question_key": question_key,
                    "status": "等待补证",
                    "processing_started_at": "",
                    "query_strategy": query_strategy.get("payload", {}),
                    "flow_profile": flow_profile,
                    "query_strategy_error": "" if query_strategy.get("ok") else query_strategy.get("error", ""),
                    "codex_process_judgment": process_judgment.get("payload", {}),
                    "codex_process_judgment_md": process_judgment.get("md_path", ""),
                    "codex_process_judgment_json": process_judgment.get("json_path", ""),
                    "codex_process_judgment_count": len(process_judgments),
                    "answer_md": "",
                    "answer_type": "waiting_supplement",
                    "answer_quality": "process_gate",
                    "error": "Codex 过程判别要求先补证，已停止自动写最终答案。" + (f"原因：{reason}" if reason else ""),
                    **workflow_payload,
                }
            )
            return {"ok": False, "request_id": request_id, "reason": "等待补证", "result": result}
        upsert_item(
            {
                "request_id": request_id,
                "question": question,
                "question_key": question_key,
                "status": "处理中",
                "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                "query_strategy": query_strategy.get("payload", {}),
                "flow_profile": flow_profile,
                "codex_process_judgment": process_judgment.get("payload", {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgment_count": len(process_judgments),
                "error": "",
                "error_category": "",
                "error_stage": "",
                "error_snippet": "",
                "error_retryable": False,
                **workflow_payload,
            }
        )
        _emit_process_heartbeat(item, 'Codex 材料池判定', '正在从候选材料池筛出可进入精读材料池的材料。')
        material_judgment = _run_codex_material_judgment(
            {**item, "question": question, "question_key": question_key},
            result,
        )
        if not material_judgment.get("ok"):
            raise RuntimeError(f"Codex 材料池判定失败，已停止进入最终答案：{material_judgment.get('error', '')}")
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        result = {
            **result,
            "codex_material_judgment_md": material_judgment.get("md_path", ""),
            "codex_material_judgment_json": material_judgment.get("json_path", ""),
            "core_files": {
                **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                "codex_material_judgment_md": material_judgment.get("md_path", ""),
                "codex_material_judgment_json": material_judgment.get("json_path", ""),
            },
        }
        workflow_payload = _workflow_queue_payload(result)
        upsert_item(
            {
                "request_id": request_id,
                "question": question,
                "question_key": question_key,
                "status": "处理中",
                "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                "query_strategy": query_strategy.get("payload", {}),
                "flow_profile": flow_profile,
                "query_strategy_error": "" if query_strategy.get("ok") else query_strategy.get("error", ""),
                "codex_process_judgment": process_judgment.get("payload", {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgment_count": len(process_judgments),
                "codex_material_judgment": material_judgment.get("payload", {}),
                "codex_material_judgment_md": material_judgment.get("md_path", ""),
                "codex_material_judgment_json": material_judgment.get("json_path", ""),
                "codex_material_writing_mode": material_judgment.get("writing_mode", ""),
                "error": "",
                "error_category": "",
                "error_stage": "",
                "error_snippet": "",
                "error_retryable": False,
                **workflow_payload,
            }
        )
        material_reread_policy = {}
        deep_insight = {}
        _emit_process_heartbeat(item, 'Codex 精读材料池', '正在把可用材料聚拢成精读材料池/精品聚拢池。')
        close_reading = _run_codex_close_reading(
            {**item, "question": question, "question_key": question_key, **workflow_payload},
            result,
        )
        if not close_reading.get("ok"):
            raise RuntimeError(f"Codex 精读材料词失败，已停止进入最终答案：{close_reading.get('error', '')}")
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        result = {
            **result,
            "codex_close_reading": close_reading.get("payload", {}),
            "codex_close_reading_md": close_reading.get("md_path", ""),
            "codex_close_reading_json": close_reading.get("json_path", ""),
            "core_files": {
                **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                "codex_close_reading_md": close_reading.get("md_path", ""),
                "codex_close_reading_json": close_reading.get("json_path", ""),
            },
        }
        workflow_payload = _workflow_queue_payload(result)
        upsert_item(
            {
                "request_id": request_id,
                "question": question,
                "question_key": question_key,
                "status": "处理中",
                "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                "query_strategy": query_strategy.get("payload", {}),
                "flow_profile": flow_profile,
                "query_strategy_error": "" if query_strategy.get("ok") else query_strategy.get("error", ""),
                "codex_process_judgment": process_judgment.get("payload", {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgment_count": len(process_judgments),
                "codex_material_judgment": material_judgment.get("payload", {}),
                "codex_material_judgment_md": material_judgment.get("md_path", ""),
                "codex_material_judgment_json": material_judgment.get("json_path", ""),
                "codex_material_writing_mode": material_judgment.get("writing_mode", ""),
                "codex_close_reading": close_reading.get("payload", {}),
                "codex_close_reading_md": close_reading.get("md_path", ""),
                "codex_close_reading_json": close_reading.get("json_path", ""),
                "codex_close_reading_permission": close_reading.get("writing_permission", ""),
                "error": "",
                "error_category": "",
                "error_stage": "",
                "error_snippet": "",
                "error_retryable": False,
                **workflow_payload,
            }
        )
        _emit_process_heartbeat(item, '00M 原文追证摘抄', '正在带着原问题和精读材料池回到《红楼梦》全书全文、全原文追证摘抄。')
        original_reread = _run_codex_original_reread(
            {**item, "question": question, "question_key": question_key, **workflow_payload},
            result,
        )
        if not original_reread.get("ok"):
            raise RuntimeError(f"Codex 写作前原文追证摘抄失败，已停止进入最终答案：{original_reread.get('error', '')}")
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)
        material_reread_policy = _deep_insight_reread_level(
            {**item, "question": question, "question_key": question_key, **workflow_payload},
            original_reread.get("payload", {}),
            close_reading.get("payload", {}),
            material_judgment.get("payload", {}),
        )
        result = {
            **result,
            "codex_original_reread": original_reread.get("payload", {}),
            "codex_original_reread_md": original_reread.get("md_path", ""),
            "codex_original_reread_json": original_reread.get("json_path", ""),
            "material_reread_policy": material_reread_policy,
            "core_files": {
                **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                "codex_original_reread_md": original_reread.get("md_path", ""),
                "codex_original_reread_json": original_reread.get("json_path", ""),
            },
        }
        workflow_payload = _workflow_queue_payload(result)
        if clean_text(material_reread_policy.get("decision")) == "进入00N":
            _emit_process_heartbeat(item, "00N 深度见解增量稿", "正在读取 00M，并按“是否进入00N + 追证轮次”策略生成深度论证增量。")
            deep_insight = _run_codex_deep_insight(
                {**item, "question": question, "question_key": question_key, **workflow_payload},
                result,
                original_reread,
            )
            if not deep_insight.get("ok"):
                raise RuntimeError(f"Codex 深度见解增量稿失败，已停止进入最终答案：{deep_insight.get('error', '')}")
            result = {
                **result,
                "codex_deep_insight": deep_insight.get("payload", {}),
                "codex_deep_insight_md": deep_insight.get("md_path", ""),
                "codex_deep_insight_json": deep_insight.get("json_path", ""),
                "core_files": {
                    **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
                    "codex_deep_insight_md": deep_insight.get("md_path", ""),
                    "codex_deep_insight_json": deep_insight.get("json_path", ""),
                },
            }
            workflow_payload = _workflow_queue_payload(result)
        else:
            _emit_process_heartbeat(item, "00N 判定", "当前不需要 00N；终稿仍以 00M 写作前原文追证摘抄为入口。")
        result = {
            **result,
            "material_reread_policy": material_reread_policy,
            "core_files": {
                **(result.get("core_files", {}) if isinstance(result.get("core_files"), dict) else {}),
            },
        }
        workflow_payload = _workflow_queue_payload(result)
        upsert_item(
            {
                "request_id": request_id,
                "question": question,
                "question_key": question_key,
                "status": "处理中",
                "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                "query_strategy": query_strategy.get("payload", {}),
                "flow_profile": flow_profile,
                "query_strategy_error": "" if query_strategy.get("ok") else query_strategy.get("error", ""),
                "codex_process_judgment": process_judgment.get("payload", {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgment_count": len(process_judgments),
                "codex_material_judgment": material_judgment.get("payload", {}),
                "codex_material_judgment_md": material_judgment.get("md_path", ""),
                "codex_material_judgment_json": material_judgment.get("json_path", ""),
                "codex_material_writing_mode": material_judgment.get("writing_mode", ""),
                "codex_close_reading": close_reading.get("payload", {}),
                "codex_close_reading_md": close_reading.get("md_path", ""),
                "codex_close_reading_json": close_reading.get("json_path", ""),
                "codex_close_reading_permission": close_reading.get("writing_permission", ""),
                "codex_original_reread": original_reread.get("payload", {}),
                "codex_original_reread_md": original_reread.get("md_path", ""),
                "codex_original_reread_json": original_reread.get("json_path", ""),
                "codex_original_reread_permission": original_reread.get("writing_permission", ""),
                "material_reread_policy": material_reread_policy,
                "error": "",
                "error_category": "",
                "error_stage": "",
                "error_snippet": "",
                "error_retryable": False,
                **workflow_payload,
            }
        )
        post_exit_refresh = _refresh_codex_package_post_exit_state(
            {**item, "question": question, "question_key": question_key, **workflow_payload},
            result,
        )
        if post_exit_refresh.get("ok"):
            result = post_exit_refresh.get("result", result)
            workflow_payload = post_exit_refresh.get("workflow_payload")
            if not isinstance(workflow_payload, dict):
                workflow_payload = _workflow_queue_payload(result)
            upsert_item(
                {
                    "request_id": request_id,
                    "question": question,
                    "question_key": question_key,
                    "status": "处理中",
                    "processing_started_at": datetime.now().isoformat(timespec="seconds"),
                    "audit_note": "00I/00L/00M 完成后已刷新 00N 指挥链达标检查与 00ZD/00ZF 最终写作门。",
                    **workflow_payload,
                }
            )
        source_path = Path(
            clean_text((deep_insight or {}).get("md_path"))
            or clean_text(original_reread.get("md_path"))
            or clean_text(close_reading.get("md_path"))
            or clean_text(material_judgment.get("md_path"))
        )
        source_note = (
            "判定为一次命中，跳过 00N，直接基于 00M 形成最终回答。"
            if clean_text(material_reread_policy.get("decision")) == "不进入00N"
            else "最终回显以 Codex 写作前原文追证摘抄为普通题进入条件；深度题以 Codex 深度见解增量稿为增量条件。00L/00M 不允许被一次命中跳过。"
        )

        final_reading_phase = (
            "正在吸收 00I/00L/00M 与刷新后的 00N 允许材料并生成最终答案。不走一次命中直达。"
        )
        _emit_process_heartbeat(item, "Codex 红楼解语终稿", final_reading_phase)
        final_path, final_error = _run_codex_final_synthesis(
            {**item, "question": question, "question_key": question_key, **workflow_payload},
            result,
        )
        if not final_path:
            raise RuntimeError(final_error)
        if is_request_aborted(request_id):
            return aborted_process_result(item, request_id, question_key)

        upsert_item(
            {
                "request_id": request_id,
                "processing_started_at": "",
                "question": question,
                "question_key": question_key,
                "status": "已处理",
                "pending_md": str(pending_md),
                "answer_md": str(final_path),
                "answer_type": "codex_synthesized",
                "answer_source": source_path.name if source_path.exists() else "",
                "answer_quality": _answer_quality_by_type("codex_synthesized"),
                "error": "",
                "error_category": "",
                "error_stage": "",
                "error_snippet": "",
                "error_retryable": False,
                "audit_note": f"红楼梦工程已先跑候选材料；Codex 已完成材料池判定；最终回显由 Codex 读取材料判定后综合生成。{source_note}",
                "flow_profile": flow_profile,
                "codex_process_judgment": process_judgment.get("payload", {}),
                "codex_process_judgment_md": process_judgment.get("md_path", ""),
                "codex_process_judgment_json": process_judgment.get("json_path", ""),
                "codex_process_judgment_count": len(process_judgments),
                "codex_material_judgment": material_judgment.get("payload", {}),
                "codex_material_judgment_md": material_judgment.get("md_path", ""),
                "codex_material_judgment_json": material_judgment.get("json_path", ""),
                "codex_material_writing_mode": material_judgment.get("writing_mode", ""),
                "codex_close_reading": close_reading.get("payload", {}),
                "codex_close_reading_md": close_reading.get("md_path", ""),
                "codex_close_reading_json": close_reading.get("json_path", ""),
                "codex_close_reading_permission": close_reading.get("writing_permission", ""),
                "codex_original_reread": original_reread.get("payload", {}),
                "codex_original_reread_md": original_reread.get("md_path", ""),
                "codex_original_reread_json": original_reread.get("json_path", ""),
                "codex_original_reread_permission": original_reread.get("writing_permission", ""),
                "recall_phrase": clean_text(item.get("recall_phrase")),
                "retry_count": 0,
                **workflow_payload,
            }
        )
        return {"ok": True, "request_id": request_id, "answer_md": str(final_path), "result": result}

    except Exception as exc:
        raw_error = str(exc) or exc.__class__.__name__
        error_meta = _classify_error(raw_error)
        workflow_payload = _workflow_queue_payload(result) if result else {}
        has_workflow_package = bool(workflow_payload.get("workflow_package"))
        next_status = "待最终回显稿" if has_workflow_package else "处理失败"
        retry_count = _int_value(item.get("retry_count"), 0)
        retryable = _parse_bool(error_meta.get("error_retryable"), default=False)
        error_category = clean_text(error_meta.get("error_category"))
        error_stage = clean_text(error_meta.get("error_stage"))
        error_snippet = clean_text(error_meta.get("error_snippet"))
        return_code = error_meta.get("return_code")
        next_stage = error_stage or "exception"

        if not has_workflow_package and retryable and retry_count < PROCESS_RETRY_MAX_ATTEMPTS:
            next_status = "待Codex处理"
            retry_count += 1
        elif not has_workflow_package:
            retry_count += 1

        next_error = raw_error
        if has_workflow_package:
            lowered_error = raw_error.lower()
            if "chatgpt.com" in lowered_error or "stream disconnected" in lowered_error or "could not resolve host" in lowered_error:
                reason = "Codex 外部连接失败或当前未获联网授权。"
            else:
                reason = _short_context(raw_error, 260)
            next_error = (
                "本地工程包已生成，已停在 Codex 判别/精读/最终回显门；"
                "未用模块搜索冒充最终答案。等待 Codex 连接或手动重试最终回显。"
                f"原因：{reason}详细日志见 Codex 运行记录。"
            )
            next_stage = "workflow_ready"
            if error_stage:
                next_stage = f"workflow_ready:{error_stage}"
        else:
            if error_stage:
                next_stage = error_stage
            elif error_category:
                next_stage = error_category
        upsert_item(
            {
                "request_id": request_id,
                "processing_started_at": "",
                "status": next_status,
                "question": clean_text(item.get("question")),
                "question_key": question_key,
                "pending_md": clean_text(item.get("pending_md")),
                "answer_md": "",
                "answer_type": "process_exception",
                "answer_quality": "workflow_ready_waiting_codex" if has_workflow_package else "exception",
                "error": next_error,
                "error_category": error_category,
                "error_stage": next_stage,
                "error_snippet": error_snippet,
                "return_code": return_code,
                "error_retryable": retryable,
                "flow_profile": flow_profile,
                "retry_count": retry_count,
                "recall_phrase": clean_text(item.get("recall_phrase")),
                **workflow_payload,
            }
        )
        return {"ok": False, "request_id": request_id, "reason": str(exc) or exc.__class__.__name__}


def cmd_process(args: argparse.Namespace) -> None:
    if args.once:
        item = select_item(args.request)
        status = process_one(item, run_smoke=args.run_smoke)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return

    loops_remaining = max(0, int(args.loops))
    wait_s = max(int(args.interval), 1)
    import time

    while True:
        loops_exhausted = loops_remaining > 0
        if loops_exhausted:
            loops_remaining -= 1

        auto_recover_stale_request_lock(timeout_seconds=PROCESSING_AUTO_CLEAR_SECONDS)
        items = _revive_stale_processing_items(load_items())
        candidates = [item for item in items if is_runnable_item(item)]
        if not candidates:
            print("队列无可自动推进项，等待中...")
            time.sleep(wait_s)
            if loops_exhausted and loops_remaining <= 0:
                return
            continue

        candidates.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        item = candidates[0]
        status = process_one(item, run_smoke=args.run_smoke)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        if loops_exhausted and loops_remaining <= 0:
            return


def cmd_clear(args: argparse.Namespace) -> None:
    payload = clear_request_lock(request_id=args.request, reason=args.reason)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_list(args: argparse.Namespace) -> None:
    items = load_items()
    if not args.all:
        items = [item for item in items if item.get("status") != "已处理"]
    if not items:
        print("当前没有待处理的 Codex 召回问题。")
        return
    for item in sorted(items, key=lambda row: row.get("updated_at", ""), reverse=True):
        print(f"{item.get('request_id')}｜{item.get('status')}｜{clean_text(item.get('question'))[:80]}")
        print(f"  召回口令：{item.get('recall_phrase', '')}")
        print(f"  待回答：{item.get('pending_md', '')}")
        print(f"  答案：{item.get('answer_md', '') or '尚未回写'}")


def cmd_show(args: argparse.Namespace) -> None:
    item = select_item(args.request)
    pending = Path(clean_text(item.get("pending_md")))
    print(f"请求ID：{item.get('request_id')}")
    print(f"状态：{item.get('status')}")
    print(f"召回口令：{item.get('recall_phrase', '')}")
    print(f"待回答文件：{pending}")
    print()
    if pending.exists():
        print(pending.read_text(encoding="utf-8"))
    else:
        print("待回答文件不存在。")


def cmd_write(args: argparse.Namespace) -> None:
    item = select_item(args.request)
    request_id = clean_text(item.get("request_id"))
    question_key = clean_text(item.get("question_key")) or safe_filename_part(clean_text(item.get("question")))
    CODEX_FINAL_DIR.mkdir(parents=True, exist_ok=True)
    final_path = CODEX_FINAL_DIR / f"A_{request_id}_{question_key}.md"
    source = Path(args.answer_file).expanduser()
    if not source.exists():
        raise SystemExit(f"答案文件不存在：{source}")
    shutil.copyfile(source, final_path)
    upsert_item(
        {
            **item,
            "request_id": request_id,
            "processing_started_at": "",
            "status": "已处理",
            "answer_md": str(final_path),
            "answer_type": "manual_copy",
            "answer_source": source.name,
            "answer_quality": _answer_quality_by_type("manual_copy"),
        }
    )
    print(f"已回写 Codex 最终答案：{final_path}")


def cmd_register(args: argparse.Namespace) -> None:
    item = select_item(args.request)
    result = register_codex_target_answer(item)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="红楼梦研究台 Codex 召回队列工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出待处理问题")
    p_list.add_argument("--all", action="store_true", help="包含已处理问题")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="读取某个待回答文件")
    p_show.add_argument("request", nargs="?", default="latest", help="请求ID，或 latest")
    p_show.set_defaults(func=cmd_show)

    p_write = sub.add_parser("write", help="把 Codex 已写好的最终答案回写到队列")
    p_write.add_argument("request", nargs="?", default="latest", help="请求ID，或 latest")
    p_write.add_argument("--answer-file", required=True, help="Codex 最终答案 Markdown 文件")
    p_write.set_defaults(func=cmd_write)

    p_register = sub.add_parser("register", help="把工程包里的 Codex 红楼解语目标稿位登记为最终答案")
    p_register.add_argument("request", nargs="?", default="latest", help="请求ID，或 latest")
    p_register.set_defaults(func=cmd_register)

    p_process = sub.add_parser("process", help="处理队列中的待回答问题并写入最终答案")
    p_process.add_argument("request", nargs="?", default="latest", help="请求ID，或 latest；在--once模式下可选")
    p_process.add_argument("--once", action="store_true", help="只处理一次后退出")
    p_process.add_argument("--run-smoke", action="store_true", help="回写前执行离线自检（默认关闭以便快速）")
    p_process.add_argument("--interval", type=int, default=10, help="循环模式下每次轮询间隔（秒）")
    p_process.add_argument("--loops", type=int, default=0, help="循环最大轮数，0 表示无限轮询")
    p_process.set_defaults(func=cmd_process)

    p_clear = sub.add_parser("clear", help="清空当前活跃线程锁，释放入口提交下一个请求。")
    p_clear.add_argument("request", nargs="?", default="", help="可选：指定要清空的请求 ID；默认清空当前 latest 的活跃线程。")
    p_clear.add_argument("--reason", default="用户手动清空旧线程。", help="可选：清空原因说明。")
    p_clear.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
