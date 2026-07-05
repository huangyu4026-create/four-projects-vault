#!/usr/bin/env python3
"""Mac 本地拉取器：从数字生命公网收件箱拉回今日日志，并送入 8790 本地数字生命入口。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_LOCAL_API = "http://127.0.0.1:8790/api/entries"
DEFAULT_TIMEOUT = 300
TELEGRAPH_API = "https://api.telegra.ph"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def load_json_file(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def request_json(url: str, method: str = "GET", body: Dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT, form: Dict[str, str] | None = None) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
    elif body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "text/plain;charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw or "{}")


def node_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict) and isinstance(node.get("children"), list):
        return "".join(node_text(child) for child in node["children"])
    return ""


def content_text(content: Any) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(node_text(node) for node in content).strip()


def normalize_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    state = payload.get("state") if isinstance(payload.get("state"), dict) else payload
    return {
        "updatedAt": state.get("updatedAt", "") if isinstance(state, dict) else "",
        "items": state.get("items", []) if isinstance(state, dict) and isinstance(state.get("items"), list) else [],
    }


def telegraph_config(args: argparse.Namespace) -> tuple[str, str]:
    path = args.telegraph_path or ""
    token = args.telegraph_token or ""
    if args.cloud_url.startswith("telegraph://"):
        path = args.cloud_url.replace("telegraph://", "", 1).strip("/")
    return path, token


def fetch_telegraph_state(args: argparse.Namespace) -> Dict[str, Any]:
    path, _ = telegraph_config(args)
    if not path:
        raise SystemExit("缺少 Telegraph path。请设置 DIGITAL_LIFE_PUBLIC_TELEGRAPH_PATH。")
    data = request_json(f"{TELEGRAPH_API}/getPage/{urllib.parse.quote(path)}?return_content=true&t={int(time.time())}", timeout=args.timeout)
    if data.get("ok") is False:
        raise RuntimeError(data.get("error") or "Telegraph 读取失败")
    text = content_text(data.get("result", {}).get("content"))
    if not text:
        return {"ok": True, "state": {"updatedAt": "", "items": []}}
    return {"ok": True, "state": normalize_state(json.loads(text))}


def save_telegraph_state(args: argparse.Namespace, state: Dict[str, Any]) -> None:
    path, token = telegraph_config(args)
    if not path or not token:
        raise SystemExit("缺少 Telegraph path/token。请设置 DIGITAL_LIFE_PUBLIC_TELEGRAPH_PATH 和 DIGITAL_LIFE_PUBLIC_TELEGRAPH_TOKEN。")
    payload = {"ok": True, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "state": normalize_state(state)}
    payload["state"]["updatedAt"] = payload["updatedAt"]
    content = json.dumps([{"tag": "pre", "children": [json.dumps(payload, ensure_ascii=False)]}], ensure_ascii=False)
    data = request_json(f"{TELEGRAPH_API}/editPage/{urllib.parse.quote(path)}", method="POST", form={
        "access_token": token,
        "title": "digital-life-public-today-log-inbox",
        "author_name": "Digital Life Public Inbox",
        "content": content,
        "return_content": "false",
    }, timeout=args.timeout)
    if data.get("ok") is False:
        raise RuntimeError(data.get("error") or "Telegraph 保存失败")


def use_telegraph(args: argparse.Namespace) -> bool:
    path, token = telegraph_config(args)
    return bool(path or token)


def fetch_cloud_state(args: argparse.Namespace) -> Dict[str, Any]:
    if args.cloud_file:
        return load_json_file(args.cloud_file)
    if use_telegraph(args):
        return fetch_telegraph_state(args)
    if not args.cloud_url:
        raise SystemExit("缺少云端收件箱 URL。请设置 --cloud-url 或 DIGITAL_LIFE_PUBLIC_INBOX_URL。")
    query = {"action": "list"}
    if args.token:
        query["token"] = args.token
    sep = "&" if "?" in args.cloud_url else "?"
    url = args.cloud_url + sep + urllib.parse.urlencode(query)
    data = request_json(url, timeout=args.timeout)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "云端收件箱读取失败")
    return data


def update_state_object(state_data: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    state = state_data.get("state", state_data)
    items = list(state.get("items", []))
    for index, item in enumerate(items):
        if item.get("id") == patch.get("id"):
            items[index] = {**item, **patch, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            state["items"] = items
            state["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return {"ok": True, "state": state}
    raise RuntimeError(f"未找到 item: {patch.get('id')}")


def cloud_update(args: argparse.Namespace, patch: Dict[str, Any]) -> None:
    if args.dry_run or args.cloud_file:
        return
    if use_telegraph(args):
        data = fetch_telegraph_state(args)
        updated = update_state_object(data, patch)
        save_telegraph_state(args, updated["state"])
        return
    body = {"action": "update", "token": args.token, "item": patch}
    data = request_json(args.cloud_url, method="POST", body=body, timeout=args.timeout)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"云端状态更新失败: {patch.get('id')}")


def select_pending_items(state: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
    items = state.get("state", state).get("items", [])
    selected = []
    for item in items:
        if item.get("project") != "digital_life":
            continue
        if item.get("entry_type") != "today_log":
            continue
        if item.get("status") not in ("pending", "retry"):
            continue
        if not str(item.get("text") or "").strip():
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def build_local_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    date = str(item.get("date") or "").strip() or time.strftime("%Y-%m-%d")
    text = str(item.get("text") or "").strip()
    public_id = str(item.get("id") or "").strip()
    return {
        "project": "digital_life",
        "type": "inbox",
        "stage": "今日日志",
        "title": str(item.get("title") or f"公网今日日志｜{date}"),
        "content": text,
        "source": "digital-life-public",
        "sourceId": public_id,
        "publicWebId": public_id,
        "date": date,
        "needsCodexRecall": False,
        "projectToolKeys": ["清风场域理解包", "今日日志规则包", "时空轴查询包"],
        "projectControlKeys": ["全局接管", "全局联动"],
    }


def post_to_local_api(args: argparse.Namespace, payload: Dict[str, Any]) -> Dict[str, Any]:
    if args.dry_run:
        return {"ok": True, "dryRun": True, "payload": payload}
    return request_json(args.local_api, method="POST", body=payload, timeout=args.timeout)


def patch_ack_file(args: argparse.Namespace, patches: List[Dict[str, Any]], state_data: Dict[str, Any]) -> None:
    if not args.ack_file:
        return
    state = state_data.get("state", state_data)
    items = state.get("items", [])
    by_id = {patch["id"]: patch for patch in patches if patch.get("id")}
    for index, item in enumerate(items):
        patch = by_id.get(item.get("id"))
        if patch:
            items[index] = {**item, **patch}
    Path(args.ack_file).write_text(json.dumps({"ok": True, "state": state}, ensure_ascii=False, indent=2), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    state_data = fetch_cloud_state(args)
    pending = select_pending_items(state_data, args.limit)
    if not pending:
        print("没有待拉取的数字生命今日日志。")
        return 0
    patches: List[Dict[str, Any]] = []
    for item in pending:
        item_id = item.get("id")
        print(f"处理 {item_id} ｜ {item.get('date')}")
        try:
            cloud_update(args, {"id": item_id, "status": "processing", "result": {"message": "Mac 已拉取，正在送入数字生命本地入口。"}})
            payload = build_local_payload(item)
            local_result = post_to_local_api(args, payload)
            if not local_result.get("ok", True):
                raise RuntimeError(local_result.get("error") or "本地数字生命入口返回失败")
            patch = {
                "id": item_id,
                "status": "done" if not args.dry_run else "pending",
                "result": {
                    "message": "已送入 Mac 数字生命今日日志流程。" if not args.dry_run else "dry-run：未真实送入本地入口。",
                    "localReceipt": local_result,
                    "localApi": args.local_api,
                    "processedAt": now_iso(),
                },
                "error": "",
            }
            cloud_update(args, patch)
            patches.append(patch)
            print(f"完成 {item_id}")
        except Exception as exc:
            patch = {"id": item_id, "status": "error", "error": str(exc), "result": {"message": "Mac 拉取或本地入库失败", "processedAt": now_iso()}}
            patches.append(patch)
            try:
                cloud_update(args, patch)
            except Exception:
                pass
            print(f"失败 {item_id}: {exc}", file=sys.stderr)
            if args.stop_on_error:
                patch_ack_file(args, patches, state_data)
                return 1
    patch_ack_file(args, patches, state_data)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从数字生命公网今日日志收件箱拉取并送入本地 8790 数字生命入口。")
    parser.add_argument("--cloud-url", default=os.environ.get("DIGITAL_LIFE_PUBLIC_INBOX_URL", ""), help="Google Apps Script Web App /exec URL，或 telegraph://path")
    parser.add_argument("--token", default=os.environ.get("DIGITAL_LIFE_PUBLIC_TOKEN", ""), help="云端收件箱口令")
    parser.add_argument("--telegraph-path", default=os.environ.get("DIGITAL_LIFE_PUBLIC_TELEGRAPH_PATH", ""), help="Telegraph 页面 path")
    parser.add_argument("--telegraph-token", default=os.environ.get("DIGITAL_LIFE_PUBLIC_TELEGRAPH_TOKEN", ""), help="Telegraph access token")
    parser.add_argument("--local-api", default=os.environ.get("DIGITAL_LIFE_LOCAL_ENTRY_API", DEFAULT_LOCAL_API), help="本地数字生命手机入口 API")
    parser.add_argument("--limit", type=int, default=int(os.environ.get("DIGITAL_LIFE_PUBLIC_PULL_LIMIT", "5")), help="一次最多处理几条")
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("DIGITAL_LIFE_PUBLIC_TIMEOUT", str(DEFAULT_TIMEOUT))))
    parser.add_argument("--cloud-file", default="", help="验证用：从本地 JSON 文件读取云端状态")
    parser.add_argument("--ack-file", default="", help="验证用：把处理后的状态写到本地 JSON 文件")
    parser.add_argument("--dry-run", action="store_true", help="只演练，不写云端，不送入本地入口")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
