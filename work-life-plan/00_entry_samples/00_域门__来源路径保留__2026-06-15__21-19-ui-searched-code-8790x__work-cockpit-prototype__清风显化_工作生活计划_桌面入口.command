#!/bin/zsh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="/Users/yu/Documents/Codex/2026-06-15/21-19-ui-searched-code-8790x/work-cockpit-prototype"
if [[ ! -d "$APP_DIR" ]]; then
  APP_DIR="$SCRIPT_DIR"
fi
cd "$APP_DIR"

DESKTOP_URL="http://127.0.0.1:8798/desktop-entry.html"
MOBILE_URL="http://127.0.0.1:8798/mobile-entry.html"
SERVER_PORT=8798
LOCAL_IP=""
for IFACE in en0 en1; do
  LOCAL_IP="${LOCAL_IP:-$(ipconfig getifaddr "$IFACE" 2>/dev/null || true)}"
done
if [[ -z "$LOCAL_IP" ]]; then
  LOCAL_IP="$(ifconfig | rg -m 1 "inet " | awk 'NR==1{print $2}')"
fi
if [[ -n "$LOCAL_IP" ]]; then
  MOBILE_URL="http://${LOCAL_IP}:8798/mobile-entry.html"
fi
START_CMD="启动工作事务推进驾驶舱召回服务.command"

is_server_ready() {
  /usr/bin/curl -sSf --max-time 2 "http://127.0.0.1:${SERVER_PORT}/api/health" 2>/dev/null | /usr/bin/grep -F "$APP_DIR" >/dev/null 2>&1
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
  open "$DESKTOP_URL"
  echo "桌面入口：$DESKTOP_URL"
  echo "手机入口：$MOBILE_URL"
  exit 0
fi

if [[ -x "$START_CMD" ]]; then
  open -a "Terminal" "$APP_DIR/$START_CMD"
else
  echo "未找到服务启动脚本：$START_CMD"
fi

if wait_for_service 15; then
  open "$DESKTOP_URL"
  echo "桌面入口：$DESKTOP_URL"
  echo "手机入口：$MOBILE_URL"
  exit 0
fi

echo "服务启动未就绪，或 8798 端口仍被旧工程占用。"
echo "请关闭旧服务后再重试。"
echo "不要使用 file:// 本地静态页面。"
echo "桌面入口：$DESKTOP_URL"
echo "手机入口：$MOBILE_URL"
exit 1
