#!/bin/zsh
cd "/Users/yu/Documents/Codex/2026-06-18/1-2-1-2-3-5/outputs/此生何为_桌面课堂工作台"
python3 desktop_server.py > /tmp/此生何为课堂服务.log 2>&1 &
sleep 1
open "http://127.0.0.1:8797/index.html"
