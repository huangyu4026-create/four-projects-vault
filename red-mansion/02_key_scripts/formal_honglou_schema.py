#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Honglou project schema rules restored from the local Notion base.

This module centralizes the controlled fields used by the Red Chamber
reading/production workflow.  It does not invent a new ontology; it encodes the
existing local base rules:

- production assets live in the work/article layer, not in the original-source
  layer;
- user approval is required before a candidate can become a formal asset;
- study notes and extension pages are learning outputs and must stay linked back
  to original evidence, chapter study notes, condensed/quick reading pages, and
  the workflow package.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
READING_LOOP_DIR = OUTPUT_ROOT / "正式底库阅读闭环还原台"
WRITEBACK_ROOT = OUTPUT_ROOT / "红楼梦Codex最终答案" / "学习型写回候选"
LOCAL_NOTION_STUDY_ROOT = Path(
    "/Users/yu/Documents/Codex/coex项目总库/10-19_四项目工程域/13_P03_红楼梦_HLM/00_域门/来源路径保留/2026-06-03/notion-3-crv/红楼梦/红楼梦研学/文学系统入口（研学工作台｜研究与产出）/红楼梦章回学习心得｜1—120回"
)
TRIANGLE_HTML = READING_LOOP_DIR / "红楼梦_三角阅读闭环.html"
TRIANGLE_INDEX_JSON = READING_LOOP_DIR / "01_三角阅读闭环索引.json"

CANDIDATE_FIELDS = [
    "标题",
    "编号",
    "章回",
    "小类",
    "文章性质",
    "内容状态",
    "价值",
    "可挖掘",
    "可信度",
    "来源位置",
    "标签",
    "来源页URL",
    "入库日期",
    "备注",
    "大类",
    "关联人物",
    "关联出库任务",
    "关联回目",
    "生命周期状态",
]

REQUIRED_CANDIDATE_FIELDS = [
    "标题",
    "章回",
    "小类",
    "文章性质",
    "内容状态",
    "可信度",
    "来源位置",
    "来源页URL",
    "大类",
    "关联回目",
    "生命周期状态",
]

LINK_FIELDS = ["回挂对象", "类型", "目标", "状态", "说明"]

REQUIRED_LINK_OBJECTS = [
    "红楼解语",
    "章回学习心得",
    "延伸阅读页",
    "快读/凝缩页",
    "工程包",
    "真源核验",
    "作品总库候选行",
]

CONTROLLED_VALUES: dict[str, set[str]] = {
    "大类": {"作品"},
    "小类": {
        "红楼解语",
        "学习心得",
        "延伸阅读",
        "专题页",
        "问答归档",
        "人物关系链",
        "结构机制链",
        "应验链",
        "路线图",
        "资料卡",
        "2.9 论文/长稿",
    },
    "文章性质": {
        "Codex最终回答",
        "学习型再整理",
        "章回学习心得",
        "延伸阅读专题",
        "专题页",
        "问题答疑",
        "关系链整理",
        "结构链整理",
        "本地预检候选",
        "论述稿",
        "评论稿",
        "学术稿",
    },
    "内容状态": {
        "已生成",
        "已成稿",
        "学习型再整理候选",
        "待整理",
        "待补证",
        "已认可",
        "已闭环",
    },
    "生命周期状态": {
        "待核证",
        "待闭环",
        "已闭环",
        "已归档",
        "退回补证",
        "🔍 待核证",
        "🟡 待闭环",
        "✅ 已归档",
    },
    "价值": {"待人工确认", "长期复读", "可复用", "高", "中", "基础"},
    "可挖掘": {"高", "中", "低", "待定"},
    "可信度": {
        "以材料池判定和真源核验为准",
        "待真源核验",
        "已回原文核验",
        "以原文钉子为准",
        "本地候选，待人工确认",
    },
}

SOURCE_CONTROLLED_VALUES: dict[str, set[str]] = {
    "source_system": {"A+B对账候选", "A类原文真源候选", "B类库线索候选", "待回源候选"},
    "source_promotion_gate": {"可入强证候选", "可入原文事实候选", "停在回源门", "仅作线索"},
    "frontstage_evidence_gate": {
        "可进入材料池候选区，由 Codex 决定采用方式。",
        "只能作为线索显示，不能作为结论证据。",
        "需先回原文，不可前台定论。",
    },
    "human_decision": {"保留", "删除", "降级", "反证", "待复核"},
    "source_verify_status": {"待核验", "已核验"},
}

KIND_DEFAULTS: dict[str, dict[str, str]] = {
    "honglou_jieyu": {
        "小类": "红楼解语",
        "文章性质": "Codex最终回答",
        "内容状态": "已生成",
        "生命周期状态": "待核证",
    },
    "study": {
        "小类": "学习心得",
        "文章性质": "章回学习心得",
        "内容状态": "学习型再整理候选",
        "生命周期状态": "待闭环",
    },
    "extension": {
        "小类": "延伸阅读",
        "文章性质": "延伸阅读专题",
        "内容状态": "学习型再整理候选",
        "生命周期状态": "待闭环",
    },
    "topic": {
        "小类": "专题页",
        "文章性质": "专题页",
        "内容状态": "学习型再整理候选",
        "生命周期状态": "待闭环",
    },
    "question": {
        "小类": "问答归档",
        "文章性质": "问题答疑",
        "内容状态": "学习型再整理候选",
        "生命周期状态": "待闭环",
    },
    "chain": {
        "小类": "人物关系链",
        "文章性质": "关系链整理",
        "内容状态": "学习型再整理候选",
        "生命周期状态": "待闭环",
    },
}

SECTION_REQUIREMENTS: dict[str, list[str]] = {
    "study": ["本回学习状态", "本回总问题", "原文钉子", "分层判断", "延伸阅读", "后续保留问题"],
    "extension": ["问题来源", "原文钉子", "一句话总判", "分层判断", "回链", "闭环状态"],
    "topic": ["问题来源", "原文证据", "分层判断", "最终结论", "回链"],
    "question": ["问题来源", "原文证据", "答", "边界", "回链"],
    "chain": ["链条定位", "原文节点", "运行机制", "回收/闭环", "回链"],
}

APPROVAL_TRIGGERS = ["红楼梦正式入库", "确认采用这篇", "保存为作品", "文章入库", "收入作品总库"]


@dataclass
class SchemaIssue:
    level: str
    field: str
    message: str
    value: str = ""


@dataclass
class SchemaReport:
    ok: bool
    issues: list[SchemaIssue] = field(default_factory=list)
    warnings: list[SchemaIssue] = field(default_factory=list)

    def add_error(self, field_name: str, message: str, value: object = "") -> None:
        self.ok = False
        self.issues.append(SchemaIssue("error", field_name, message, clean(value)))

    def add_warning(self, field_name: str, message: str, value: object = "") -> None:
        self.warnings.append(SchemaIssue("warning", field_name, message, clean(value)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [issue.__dict__ for issue in self.issues],
            "warnings": [issue.__dict__ for issue in self.warnings],
        }


def clean(value: object) -> str:
    return str(value or "").replace("\u3000", " ").strip()


def normalize_lifecycle(value: object) -> str:
    text = clean(value)
    text = re.sub(r"^[🔍🟡✅]\s*", "", text)
    return text.strip()


def normalize_chapter(value: object) -> str:
    text = clean(value)
    if not text:
        return "待由证据确认"
    match = re.search(r"(\d{1,3})", text)
    if not match:
        return text
    num = int(match.group(1))
    if 1 <= num <= 120:
        return str(num)
    return text


def chapter_int(value: object) -> int | None:
    text = normalize_chapter(value)
    if text.isdigit():
        num = int(text)
        if 1 <= num <= 120:
            return num
    return None


def safe_filename_part(text: object, limit: int = 64) -> str:
    value = clean(text)
    safe = "".join(ch if ch.isalnum() or ch in "-_一二三四五六七八九十百千万第回红楼梦学习心得延伸阅读人物关系结构专题问答" else "_" for ch in value)
    safe = "_".join(part for part in safe.split("_") if part)
    return (safe or "红楼梦写回候选")[:limit]


def is_local_path(value: str) -> bool:
    if not value or value.startswith(("http://", "https://", "notion://")):
        return False
    return value.startswith("/") or value.startswith(".") or ":" in value


def detect_approval(text: object) -> bool:
    value = clean(text)
    return any(trigger in value for trigger in APPROVAL_TRIGGERS)


def validate_candidate_row(row: dict[str, Any], *, strict: bool = True) -> SchemaReport:
    report = SchemaReport(ok=True)
    for field_name in REQUIRED_CANDIDATE_FIELDS:
        if not clean(row.get(field_name)):
            report.add_error(field_name, "必填字段为空。")

    for field_name, allowed in CONTROLLED_VALUES.items():
        value = clean(row.get(field_name))
        if not value:
            continue
        normalized = normalize_lifecycle(value) if field_name == "生命周期状态" else value
        normalized_allowed = {normalize_lifecycle(item) if field_name == "生命周期状态" else item for item in allowed}
        if strict and normalized not in normalized_allowed:
            report.add_error(field_name, "不在原底座允许值中。", value)

    if clean(row.get("大类")) == "作品":
        note = clean(row.get("备注"))
        if "不能" not in note and "不倒灌" not in note and "原文证据" not in note:
            report.add_warning("备注", "作品层资产建议写明不能反向污染原文真源层。", note)

    subclass = clean(row.get("小类"))
    nature = clean(row.get("文章性质"))
    if subclass == "红楼解语" and nature != "Codex最终回答":
        report.add_error("文章性质", "红楼解语必须保持 Codex最终回答 身份。", nature)
    if subclass in {"学习心得", "延伸阅读", "专题页", "问答归档", "人物关系链", "结构机制链", "应验链"}:
        if nature == "Codex最终回答":
            report.add_error("文章性质", "学习型再整理资产不能直接标成 Codex最终回答。", nature)

    chapter = clean(row.get("章回")) or clean(row.get("关联回目"))
    parsed_chapter = chapter_int(chapter)
    if chapter and parsed_chapter is None and "待" not in chapter and chapter != "0":
        report.add_warning("章回", "章回未能解析为 1-120；若是跨回资产，请在备注说明。", chapter)

    source_url = clean(row.get("来源页URL"))
    if source_url.startswith("http") and "notion" not in source_url and "app.notion" not in source_url:
        report.add_warning("来源页URL", "正式 Notion 入库后来源页 URL 应替换为 Notion 页面或稳定本地路径。", source_url)

    return report


def validate_source_row(row: dict[str, Any], *, strict: bool = True) -> SchemaReport:
    report = SchemaReport(ok=True)
    for field_name in ["segment_no", "chapter_no", "source_trace", "retrieval_reasons", "source_system"]:
        if not clean(row.get(field_name)):
            report.add_error(field_name, "来源字段缺失，不能进入强证候选。")
    for field_name, allowed in SOURCE_CONTROLLED_VALUES.items():
        value = clean(row.get(field_name))
        if value and strict and value not in allowed:
            report.add_error(field_name, "来源字段不在原底座允许值中。", value)
    return report


def validate_links(rows: Iterable[dict[str, Any]], required_objects: Iterable[str] = REQUIRED_LINK_OBJECTS) -> SchemaReport:
    report = SchemaReport(ok=True)
    row_list = list(rows)
    seen = {clean(row.get("回挂对象")) for row in row_list}
    for field_name in LINK_FIELDS:
        for idx, row in enumerate(row_list, start=1):
            if not clean(row.get(field_name)):
                report.add_error(field_name, f"第 {idx} 行回挂字段为空。")
    for obj in required_objects:
        if obj not in seen:
            report.add_error("回挂对象", f"缺少必要回挂对象：{obj}")
    return report


def validate_page_sections(markdown: str, kind: str) -> SchemaReport:
    report = SchemaReport(ok=True)
    requirements = SECTION_REQUIREMENTS.get(kind, [])
    for title in requirements:
        if title not in markdown:
            report.add_error("section", f"缺少底座要求小节：{title}")
    return report


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: clean(row.get(field)) for field in fieldnames})


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def default_candidate_row(
    *,
    title: str,
    chapter: str | int | None,
    kind: str,
    source_path: str,
    request_id: str = "待关联",
    tags: str = "红楼梦, 学习型再整理",
    characters: str = "待由红楼解语和材料池确认",
    now_date: str = "",
    approved: bool = False,
) -> dict[str, str]:
    defaults = KIND_DEFAULTS.get(kind, KIND_DEFAULTS["extension"])
    chapter_text = normalize_chapter(chapter)
    lifecycle = "待闭环" if not approved else "已闭环"
    if kind == "honglou_jieyu" and not approved:
        lifecycle = "待核证"
    row = {
        "标题": title,
        "编号": "待分配",
        "章回": chapter_text,
        "小类": defaults["小类"],
        "文章性质": defaults["文章性质"],
        "内容状态": "已认可" if approved else defaults["内容状态"],
        "价值": "待人工确认" if not approved else "长期复读",
        "可挖掘": "高",
        "可信度": "以材料池判定和真源核验为准",
        "来源位置": source_path,
        "标签": tags,
        "来源页URL": source_path,
        "入库日期": now_date,
        "备注": "作品层/学习产出层资产；可以回挂证据，但不能反向作为原文真源证据；正式 Notion 入库前保留用户认可门。",
        "大类": "作品",
        "关联人物": characters,
        "关联出库任务": request_id,
        "关联回目": chapter_text,
        "生命周期状态": lifecycle,
    }
    return row


def find_study_note(chapter: int | None) -> Path | None:
    if chapter is None or not LOCAL_NOTION_STUDY_ROOT.exists():
        return None
    patterns = [
        f"红楼梦章回学习心得｜第{chapter}回*.md",
        f"红楼梦章回学习心得｜第 {chapter} 回*.md",
        f"*第{chapter}回*.md",
        f"*第 {chapter} 回*.md",
    ]
    for pattern in patterns:
        matches = sorted(LOCAL_NOTION_STUDY_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None


def strip_notion_id(stem: str) -> str:
    return re.sub(r"\s+[0-9a-f]{32}$", "", stem).strip()
