#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$(/usr/bin/env which python3 2>/dev/null || true)}"
if [ -z "$PYTHON_BIN" ]; then
  PYTHON_BIN="/usr/bin/python3"
fi
LOCAL_IP=""
for IFACE in en0 en1; do
  LOCAL_IP="${LOCAL_IP:-$(ipconfig getifaddr "$IFACE" 2>/dev/null || true)}"
done
if [ -z "$LOCAL_IP" ]; then
  LOCAL_IP="$(ifconfig | rg -m 1 \"inet \" | awk 'NR==1{print $2}')"
fi

LOG_FILE="runtime/work_plan_recall_server.command.log"
echo "Python: $PYTHON_BIN"
echo "服务入口（电脑）：http://127.0.0.1:8798/desktop-entry.html"
if [ -n "$LOCAL_IP" ]; then
  echo "服务入口（手机）：http://${LOCAL_IP}:8798/mobile-entry.html"
fi
echo "日志文件：$(pwd)/$LOG_FILE"

set +e
"$PYTHON_BIN" work_plan_recall_server.py serve --host 0.0.0.0 --port 8798 --worker-interval 10 --worker-timeout 900 2>&1 | tee "$LOG_FILE"
ret=$?
if [ $ret -ne 0 ]; then
  echo ""
  echo "服务启动失败，错误码：$ret"
  echo "请把窗口里的报错行截图给我"
  read -n 1 -s -r -p "按任意键关闭..."
  echo ""
  exit $ret
fi
