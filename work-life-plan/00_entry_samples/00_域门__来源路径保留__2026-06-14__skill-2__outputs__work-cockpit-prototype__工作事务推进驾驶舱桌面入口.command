#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/Users/yu/Documents/Codex/2026-06-14/skill-2/outputs/work-cockpit-prototype"
if [[ ! -d "$APP_DIR" ]]; then
  APP_DIR="$SCRIPT_DIR"
fi
cd "$APP_DIR"

URL="http://127.0.0.1:8798/desktop-entry.html"
START_CMD="一键启动工作事务推进驾驶舱全链路.command"
SERVER_PORT=8798

is_server_ready() {
  /usr/bin/curl -sSf --max-time 2 "$URL" >/dev/null 2>&1
}

try_launch_server() {
  if /usr/bin/pgrep -f "work_plan_recall_server.py serve" >/dev/null 2>&1; then
    return 0
  fi

  if [[ ! -x "$START_CMD" ]]; then
    chmod +x "$START_CMD"
  fi

  if [[ -x "$START_CMD" ]]; then
    open -a "Terminal" "$APP_DIR/$START_CMD"
  fi
}

wait_for_service() {
  local timeout=$1
  local i=0
  while (( i < timeout )); do
    if is_server_ready; then
      return 0
    fi
    ((i += 1))
    sleep 1
  done
  return 1
}

if is_server_ready; then
  open "$URL"
  exit 0
fi

try_launch_server

if wait_for_service 15; then
  open "$URL"
  exit 0
fi

open "$APP_DIR/desktop-entry.html"
echo "服务启动未就绪，已打开本地静态页面。请先确认终端里服务已正常启动。"
