#!/usr/bin/env python3
"""Local coordinate-search research desk for the Honglou project.

This is the sibling "coordinate edition" of the legacy semantic research desk.
It keeps runtime packages and ledgers in this workspace, while reading the
shared base and the published coordinate mapping database read-only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import traceback
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


ROOT = Path("/Users/yu/Documents/Codex/2026-06-21/new-chat-3")
WORK_DIR = ROOT / "work"
APP_ROOT = ROOT / "outputs/红楼梦坐标查询台"
PACKAGE_ROOT = APP_ROOT / "查询包"
RUN_LOG = APP_ROOT / "坐标版运行记录.jsonl"
LEDGER = APP_ROOT / "00_坐标版工程总账.md"
LEGACY_ROOT = Path("/Users/yu/Documents/Codex/2026-06-03/notion-3-crv")
LEGACY_SEMANTIC_APP = LEGACY_ROOT / "work/formal_honglou_local_app.py"
SHARED_BASE_SEARCH_DB = LEGACY_ROOT / "outputs/正式底库全文检索原型/formal_honglou_search.sqlite"
COORDINATE_DB = ROOT / "outputs/红楼梦聚拢坐标映射总库_CH001_120/红楼梦聚拢坐标映射总库_CH001_120.sqlite"

if str(WORK_DIR) not in sys.path:
    sys.path.insert(0, str(WORK_DIR))

import honglou_coordinate_search_workbench as coordinate_engine  # noqa: E402


APP_TITLE = "红楼梦坐标查询台"
APP_VERSION = "coordinate-sibling-20260621"


def clean(text: Any) -> str:
    return str(text or "").strip()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_dirs() -> None:
    PACKAGE_ROOT.mkdir(parents=True, exist_ok=True)
    APP_ROOT.mkdir(parents=True, exist_ok=True)


def db_counts() -> dict[str, Any]:
    if not COORDINATE_DB.exists():
        return {"exists": False, "path": str(COORDINATE_DB)}
    conn = sqlite3.connect(COORDINATE_DB)
    try:
        out: dict[str, Any] = {"exists": True, "path": str(COORDINATE_DB)}
        for table in [
            "clean_atoms",
            "atom_codebook",
            "atom_projection_codebook",
            "atom_memberships",
            "atom_links",
            "container_codebook",
        ]:
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        chapters = conn.execute(
            "SELECT MIN(chapter_no), MAX(chapter_no), COUNT(DISTINCT chapter_no) FROM atom_codebook"
        ).fetchone()
        out["chapter_min"] = chapters[0]
        out["chapter_max"] = chapters[1]
        out["chapter_count"] = chapters[2]
        return out
    finally:
        conn.close()


def append_run_log(event: dict[str, Any]) -> None:
    ensure_dirs()
    event = {"created_at": now(), **event}
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def write_app_package(payload: dict[str, Any]) -> dict[str, str]:
    ensure_dirs()
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + coordinate_engine.safe_name(payload["query"])
    out_dir = PACKAGE_ROOT / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    adjusted = {
        **payload,
        "mode": "coordinate_search_sibling_app",
        "decision": "坐标版独立研究台：程序、输出、运行包与旧语义版分开；底座只读共用。",
        "app_version": APP_VERSION,
        "app_root": str(APP_ROOT),
        "legacy_semantic_app": str(LEGACY_SEMANTIC_APP),
        "shared_base_search_db": str(SHARED_BASE_SEARCH_DB),
    }
    json_path = out_dir / "coordinate_search_result.json"
    md_path = out_dir / "coordinate_search_report.md"
    json_path.write_text(json.dumps(adjusted, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(coordinate_engine.render_markdown(adjusted), encoding="utf-8")
    append_run_log(
        {
            "event": "write_package",
            "query": payload["query"],
            "run_id": run_id,
            "json_path": str(json_path),
            "md_path": str(md_path),
            "result_count": len(payload.get("results", [])),
        }
    )
    return {"run_id": run_id, "json_path": str(json_path), "md_path": str(md_path)}


def run_coordinate_search(query: str, limit: int, write_package: bool) -> dict[str, Any]:
    query = clean(query)
    if not query:
        raise ValueError("缺少查询内容。")
    limit = max(1, min(int(limit or 12), 50))
    payload = coordinate_engine.run_query(query, limit)
    payload["mode"] = "coordinate_search_sibling_app"
    payload["decision"] = "坐标版独立研究台：程序、输出、运行包与旧语义版分开；底座只读共用。"
    payload["app_version"] = APP_VERSION
    if write_package:
        payload["package"] = write_app_package(payload)
    else:
        append_run_log(
            {
                "event": "preview_search",
                "query": query,
                "limit": limit,
                "result_count": len(payload.get("results", [])),
            }
        )
    return payload


def status_payload() -> dict[str, Any]:
    return {
        "title": APP_TITLE,
        "version": APP_VERSION,
        "app_root": str(APP_ROOT),
        "package_root": str(PACKAGE_ROOT),
        "ledger": str(LEDGER),
        "coordinate_db": db_counts(),
        "legacy_semantic_app": {
            "path": str(LEGACY_SEMANTIC_APP),
            "exists": LEGACY_SEMANTIC_APP.exists(),
        },
        "shared_base_search_db": {
            "path": str(SHARED_BASE_SEARCH_DB),
            "exists": SHARED_BASE_SEARCH_DB.exists(),
            "note": "底座只读共用；坐标版不复制。",
        },
    }


def write_ledger() -> None:
    ensure_dirs()
    counts = db_counts()
    LEDGER.write_text(
        f"""# 红楼梦坐标版工程总账

生成时间：{now()}

## 1. 总判断

可以复制一个“坐标版红楼梦查询程序”，但不复制底座。

旧工程保留为语义版；新工程为坐标版。两者共用同一个大底座或底层事实来源，但程序入口、查询 API、运行日志、查询包、工程总账分开，避免旧语义链和新坐标链互相污染。

## 2. 两个版本

- 语义版旧程序：`{LEGACY_SEMANTIC_APP}`
- 坐标版新程序：`{Path(__file__).resolve()}`
- 坐标版工程根：`{APP_ROOT}`
- 坐标版查询包：`{PACKAGE_ROOT}`

## 3. 底座原则

- 底座很大，可以共用。
- 坐标版不复制旧底库。
- 坐标版只读坐标映射总库：`{COORDINATE_DB}`
- 旧语义版仍按原路径和原流程运行。

## 4. 坐标库状态

- 坐标总库存在：{counts.get('exists')}
- 覆盖回目：{counts.get('chapter_min')} 至 {counts.get('chapter_max')}，共 {counts.get('chapter_count')} 回
- 原子段：{counts.get('atom_codebook')}
- 原子投影：{counts.get('atom_projection_codebook')}
- 原子归属：{counts.get('atom_memberships')}
- 原子关系：{counts.get('atom_links')}
- 容器编码：{counts.get('container_codebook')}

## 5. 当前边界

第一版复制的是“研究台入口和查询工作台”的程序形态：页面、API、坐标查询、结果包落盘、运行记录。它暂不复制旧工程的 Codex 精读材料词、红楼解语、文章入库门等长链条，等坐标查询稳定后再决定是否把这些长链条也做成坐标版。

## 6. 启动

```bash
python3 work/honglou_coordinate_local_app.py --port 8873
```

打开：`http://127.0.0.1:8873/`
""",
        encoding="utf-8",
    )


PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__APP_TITLE__</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #202124;
      --muted: #61656f;
      --line: #d9dce2;
      --soft: #f5f6f8;
      --accent: #1b6f6a;
      --accent-2: #8c3f2b;
      --good: #2f6b3f;
      --warn: #995f15;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body {
      margin: 0;
      background: #fbfbfc;
      color: var(--ink);
    }
    header {
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    .topbar, main {
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px 20px;
    }
    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      font-size: 24px;
      line-height: 1.2;
      margin: 0;
      letter-spacing: 0;
    }
    .sub {
      margin-top: 4px;
      color: var(--muted);
      font-size: 13px;
    }
    .status {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 10px 12px;
      min-height: 52px;
    }
    .metric b {
      display: block;
      font-size: 17px;
      margin-bottom: 2px;
    }
    .metric span {
      color: var(--muted);
      font-size: 12px;
    }
    .query-panel {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      padding: 14px;
    }
    textarea {
      width: 100%;
      min-height: 92px;
      box-sizing: border-box;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 12px;
      font: inherit;
      line-height: 1.55;
      color: var(--ink);
    }
    .controls {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
      flex-wrap: wrap;
    }
    .left-controls, .right-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    button {
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      border-radius: 6px;
      padding: 8px 12px;
      font-size: 14px;
      cursor: pointer;
    }
    button.secondary {
      background: #fff;
      color: var(--accent);
    }
    button.ghost {
      background: #fff;
      border-color: var(--line);
      color: var(--ink);
    }
    input[type="number"] {
      width: 68px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 8px;
      font: inherit;
    }
    .layout {
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      gap: 16px;
      margin-top: 16px;
    }
    aside, .results {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
    }
    aside {
      padding: 12px;
    }
    .aside-title, .section-title {
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 8px;
      color: #333840;
    }
    .pill-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 12px;
    }
    .pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 8px;
      font-size: 12px;
      color: var(--muted);
      background: var(--soft);
    }
    .path {
      overflow-wrap: anywhere;
      font-size: 12px;
      line-height: 1.55;
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 10px;
      margin-top: 10px;
    }
    .results {
      padding: 12px;
      min-height: 420px;
    }
    .result {
      border-top: 1px solid var(--line);
      padding: 12px 0;
    }
    .result:first-child {
      border-top: 0;
      padding-top: 0;
    }
    .result-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 6px;
    }
    .code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--accent-2);
      font-size: 12px;
    }
    .summary {
      font-size: 15px;
      line-height: 1.55;
      margin-bottom: 6px;
    }
    .quote {
      color: var(--muted);
      line-height: 1.6;
      font-size: 13px;
      background: var(--soft);
      border-radius: 6px;
      padding: 8px;
    }
    .small {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.55;
      margin-top: 6px;
    }
    .package {
      color: var(--good);
      font-size: 13px;
      line-height: 1.5;
      margin: 10px 0;
      overflow-wrap: anywhere;
    }
    .error {
      color: #9b1c1c;
      background: #fff1f1;
      border: 1px solid #efc5c5;
      border-radius: 6px;
      padding: 10px;
      white-space: pre-wrap;
    }
    @media (max-width: 820px) {
      .status, .layout {
        grid-template-columns: 1fr;
      }
      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div>
        <h1>__APP_TITLE__</h1>
        <div class="sub">坐标版独立工程：共用底座，只读坐标总库，运行包另存。</div>
      </div>
      <button class="ghost" id="refreshBtn">刷新状态</button>
    </div>
  </header>
  <main>
    <section class="status" id="status"></section>
    <section class="query-panel">
      <textarea id="query">宝玉林黛玉两个人在秋天跟花比较接近的一个状态</textarea>
      <div class="controls">
        <div class="left-controls">
          <button id="searchBtn">坐标查</button>
          <button class="secondary" id="packageBtn">坐标查并落包</button>
          <button class="ghost sample" data-q="宝玉林黛玉两个人在秋天跟花比较接近的一个状态">样例</button>
          <button class="ghost sample" data-q="黛玉 秋天 花 冷">黛玉秋花</button>
        </div>
        <div class="right-controls">
          <label>条数 <input id="limit" type="number" min="1" max="50" value="12" /></label>
        </div>
      </div>
    </section>
    <section class="layout">
      <aside>
        <div class="aside-title">识别变量</div>
        <div class="pill-list" id="facets"></div>
        <div class="aside-title">命中规模</div>
        <div id="facetHits" class="small"></div>
        <div class="path" id="paths"></div>
      </aside>
      <section class="results">
        <div class="section-title">坐标结果</div>
        <div id="package" class="package"></div>
        <div id="results" class="small">等待查询。</div>
      </section>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);

    function metric(label, value) {
      return `<div class="metric"><b>${value ?? "-"}</b><span>${label}</span></div>`;
    }

    async function loadStatus() {
      const res = await fetch("/api/status");
      const data = await res.json();
      const db = data.coordinate_db || {};
      $("status").innerHTML = [
        metric("原子段", db.atom_codebook),
        metric("投影", db.atom_projection_codebook),
        metric("回目覆盖", `${db.chapter_min || "-"}-${db.chapter_max || "-"}`),
        metric("底座共用", data.shared_base_search_db?.exists ? "是" : "未见")
      ].join("");
      $("paths").innerHTML = [
        `<b>坐标总库</b><br>${db.path || ""}`,
        `<br><b>红楼梦人工智能咨询工程</b><br>${data.app_root}`,
        `<br><b>语义版旧程序</b><br>${data.legacy_semantic_app?.path || ""}`
      ].join("");
    }

    function shorten(text, n = 220) {
      text = (text || "").replace(/\s+/g, " ").trim();
      return text.length > n ? text.slice(0, n - 1) + "…" : text;
    }

    function renderPayload(data) {
      $("facets").innerHTML = (data.facets || []).map(
        f => `<span class="pill">${f.facet_type} / ${f.name}</span>`
      ).join("") || `<span class="pill">未识别</span>`;
      $("facetHits").innerHTML = Object.entries(data.facet_hit_counts || {}).map(
        ([k, v]) => `${k}: ${v}`
      ).join("<br>");
      if (data.package) {
        $("package").innerHTML = `已落包：${data.package.md_path}`;
      } else {
        $("package").innerHTML = "";
      }
      const results = data.results || [];
      $("results").innerHTML = results.map((item, idx) => {
        const c = item.context || {};
        const near = (item.nearest_for_missing || []).slice(0, 4).map(
          n => `${n.facet_type}/${n.facet} -> ${n.to_atom_code} 距离 ${n.abs_atom_distance} 场${n.same_scene} 事件${n.same_event}`
        ).join("<br>");
        return `<article class="result">
          <div class="result-head">
            <b>${idx + 1}. ${c.old_segment_no || c.atom_id || ""}</b>
            <span class="code">${c.atom_code || ""}</span>
          </div>
          <div class="summary">${c.summary || ""}</div>
          <div class="quote">${shorten(c.quote)}</div>
          <div class="small">score ${item.score}｜matched ${item.matched_count}/${item.total_facets}｜${c.coordinate_summary || ""}</div>
          ${near ? `<div class="small">${near}</div>` : ""}
        </article>`;
      }).join("") || "没有结果。";
    }

    async function run(writePackage) {
      $("results").innerHTML = "查询中...";
      $("package").innerHTML = "";
      try {
        const params = new URLSearchParams({
          query: $("query").value,
          limit: $("limit").value,
          package: writePackage ? "1" : "0"
        });
        const res = await fetch(`/api/coordinate-search?${params}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "查询失败");
        renderPayload(data);
      } catch (err) {
        $("results").innerHTML = `<div class="error">${err.stack || err.message || err}</div>`;
      }
    }

    $("searchBtn").addEventListener("click", () => run(false));
    $("packageBtn").addEventListener("click", () => run(true));
    $("refreshBtn").addEventListener("click", loadStatus);
    document.querySelectorAll(".sample").forEach(btn => {
      btn.addEventListener("click", () => {
        $("query").value = btn.dataset.q;
        run(false);
      });
    });
    loadStatus();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "HonglouCoordinateDesk/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (now(), fmt % args))

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_html(PAGE.replace("__APP_TITLE__", APP_TITLE))
                return
            if parsed.path == "/api/status":
                self.send_json(status_payload())
                return
            if parsed.path == "/api/coordinate-search":
                qs = parse_qs(parsed.query)
                query = clean(qs.get("query", [""])[0])
                limit = int(qs.get("limit", ["12"])[0] or 12)
                write_package = qs.get("package", ["0"])[0] in {"1", "true", "yes"}
                self.send_json(run_coordinate_search(query, limit, write_package))
                return
            self.send_json({"error": "not found", "path": parsed.path}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self.send_json(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=8),
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


def self_test() -> None:
    write_ledger()
    payload = run_coordinate_search("宝玉林黛玉两个人在秋天跟花比较接近的一个状态", 5, True)
    print(json.dumps(
        {
            "ok": True,
            "result_count": len(payload.get("results", [])),
            "top": payload.get("results", [{}])[0].get("context", {}).get("old_segment_no"),
            "package": payload.get("package", {}),
            "ledger": str(LEDGER),
        },
        ensure_ascii=False,
        indent=2,
    ))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8873)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    write_ledger()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"{APP_TITLE} running at http://{args.host}:{args.port}/")
    print(f"ledger: {LEDGER}")
    print(f"coordinate_db: {COORDINATE_DB}")
    server.serve_forever()


if __name__ == "__main__":
    main()
