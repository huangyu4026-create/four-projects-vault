#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import db_runtime
import dl2_runtime as dl2


CORE = Path(__file__).resolve().parents[1]


def ev(source_id: str, role: str = "SOURCE") -> dict:
    return {"source_type": "event", "source_id": source_id, "source_anchor": f"events/{source_id}", "evidence_role": role}


def log(source_id: str, role: str = "SOURCE") -> dict:
    return {"source_type": "qingfeng_log", "source_id": source_id, "source_anchor": f"qingfeng_logs/{source_id}/original_text", "evidence_role": role}


def pattern(source_id: str, role: str = "SOURCE") -> dict:
    return {"source_type": "psychological_pattern", "source_id": source_id, "source_anchor": f"psychological_patterns/{source_id}/definition", "evidence_role": role}


MEMORIES = [
    {
        "memory_id": "dlmem:seed-m01", "statement": "现有编年记录把‘父亲翻字典取名煬’登记为1970年的出生与命名事件。",
        "statement_type": "FACT", "event_time": "1970", "confidence_state": "MEDIUM", "ownership_state": "SOURCE_FACT",
        "change_reason": "将既有编年对象转为可回源活记忆，不接受其中的生命隐喻为事实", "evidence": [ev("event:08332d65d53b1e34c1e0")],
    },
    {
        "memory_id": "dlmem:seed-m02", "statement": "现有编年记录把1975年随母亲回武汉化工机械厂登记为一次家庭与生活场域转移。",
        "statement_type": "FACT", "event_time": "1975", "confidence_state": "MEDIUM", "ownership_state": "SOURCE_FACT",
        "change_reason": "保留现有时间与地点记录，不扩写意义", "evidence": [ev("event:993a0f809157557ecfc0")],
    },
    {
        "memory_id": "dlmem:seed-m03", "statement": "编年材料中有一条1975年幼儿园时期‘迷路后找回家路’的记录。",
        "statement_type": "FACT", "event_time": "1975", "confidence_state": "MEDIUM", "ownership_state": "SOURCE_FACT",
        "change_reason": "仅登记事件存在，不自动接受‘第一次体会记忆解决问题’的解释", "evidence": [ev("event:d7cb025ef575380657c6")],
    },
    {
        "memory_id": "dlmem:seed-m04", "statement": "现有编年材料记录了童年目睹母亲病弱咳血的经历；其是否形成长期离去焦虑仍属系统解释。",
        "statement_type": "EXPERIENCE_SUMMARY", "event_time": "1979", "confidence_state": "MEDIUM", "ownership_state": "SYSTEM_CANDIDATE", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "分开经历事实与原事件卡中的心理归因", "evidence": [ev("event:57abbb4335222fd41b4c")],
    },
    {
        "memory_id": "dlmem:seed-m05", "statement": "2026年6月8日的日志原话表明，煬对Codex带来的执行强度、速度和工程成形有明确的正向评价。",
        "statement_type": "USER_QUOTE", "event_time": "2026-06-08", "confidence_state": "HIGH", "ownership_state": "USER_WORDS",
        "change_reason": "保留当日对工程工具的本人表达，不外推为永久态度", "evidence": [log("qflog:bb10c002599d45dd914c0bbe4a77a32d")],
    },
    {
        "memory_id": "dlmem:seed-m06", "statement": "2026年7月15日的日志原话记录了阅读旧日记触发另一段童年记忆，同时明说‘也不知道我记了些什么’。",
        "statement_type": "USER_QUOTE", "event_time": "2026-07-15", "confidence_state": "HIGH", "ownership_state": "USER_WORDS",
        "change_reason": "保留记忆触发与自我不确定的同时存在", "evidence": [log("qflog:85334ecc3b78429d94a75b08b7c583ac")],
    },
    {
        "memory_id": "dlmem:seed-m07", "statement": "2026年7月16日的日志原话将小黄缘龟的重新出现表达为一次‘失而复得’的奇特感受。",
        "statement_type": "USER_QUOTE", "event_time": "2026-07-16", "confidence_state": "HIGH", "ownership_state": "USER_WORDS",
        "change_reason": "保留本人对当日事件的原始表达", "evidence": [log("qflog:dc67665c25004883a37dae769e3ec7db")],
    },
    {
        "memory_id": "dlmem:seed-m08", "statement": "2026年7月15日的井水缸浴记录显示，当日入水体验触发了多段与水有关的旧记忆回望。",
        "statement_type": "USER_QUOTE", "event_time": "2026-07-15", "confidence_state": "HIGH", "ownership_state": "USER_WORDS", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "记录当日触发链，不把转写层自动当作逐字原文", "evidence": [log("qflog:notion-mirror-fb3501021404450d8c96cf14462e9f54")],
    },
    {
        "memory_id": "dlmem:seed-m09", "statement": "候选：水在煬的一生中始终是稳定的记忆触发器。",
        "statement_type": "HYPOTHESIS_PENDING", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "从童年水中险境与2026年水中回望提出待审计候选", "evidence": [ev("event:7890e6a884ce59b1ab9f", "SUPPORT"), log("qflog:notion-mirror-fb3501021404450d8c96cf14462e9f54", "SUPPORT")],
        "revision": {"statement": "现有两类材料表明，童年水中险境与2026年井水缸浴回望发生了联系；它支持‘本次水体验触发记忆’，不足以证明一生始终稳定。", "change_type": "SCOPE_NARROWED", "change_reason": "证据仅覆盖两类时点，删去‘一生始终’的过度推断", "evidence": [ev("event:7890e6a884ce59b1ab9f", "SUPPORT"), log("qflog:notion-mirror-fb3501021404450d8c96cf14462e9f54", "SUPPORT")]},
    },
    {
        "memory_id": "dlmem:seed-m10", "statement": "候选：从童年砖堆到现在工程，煬始终以沉浸状态建造世界。",
        "statement_type": "HYPOTHESIS_PENDING", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "比较童年空间沉浸事件和2026年工程日志的待审计候选", "evidence": [ev("event:b7d95522d4ae458841d7", "SUPPORT"), log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT")],
        "revision": {"statement": "童年砖堆空间沉浸与2026年高强度工程投入可以作为跨时期对照；二者是否属于同一稳定机制仍待真人校准。", "change_type": "SCOPE_NARROWED", "change_reason": "材料允许对照，不允许直接宣告跨一生的同一性", "evidence": [ev("event:b7d95522d4ae458841d7", "SUPPORT"), log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT")]},
    },
    {
        "memory_id": "dlmem:seed-m11", "statement": "编年中的童年讲故事经历与2026年的创作工程记录可作跨时期对照，但不足以单独证明文学始终是最主要的精神滋养。",
        "statement_type": "SYSTEM_INTERPRETATION", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "保留可比性和不充分性", "evidence": [ev("event:3e9351baab91946d932e", "SUPPORT"), log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "COUNTER")],
    },
    {
        "memory_id": "dlmem:seed-m12", "statement": "候选：煬一直依靠记忆和系统化来解决复杂问题。",
        "statement_type": "HYPOTHESIS_PENDING", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "由童年认路事件和当前数字工程提出待审计候选", "evidence": [ev("event:d7cb025ef575380657c6", "SUPPORT"), log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT")],
        "revision": {"statement": "现有材料分别记录了童年迷路后找到家路和2026年使用数字工程组织工作；它们支持两个事件，不足以证明‘一直依靠’的稳定模式。", "change_type": "SCOPE_NARROWED", "change_reason": "将两个跨期事件与稳定人格模式分开", "evidence": [ev("event:d7cb025ef575380657c6", "SUPPORT"), log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT")]},
    },
    {
        "memory_id": "dlmem:seed-m13", "statement": "候选：煬在所有危机中都会变得异常冷静。",
        "statement_type": "HYPOTHESIS_PENDING", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "以溺水自救事件为支持、母亲病弱引发焦虑为反方的冲突试跑", "evidence": [ev("event:7890e6a884ce59b1ab9f", "SUPPORT"), ev("event:57abbb4335222fd41b4c", "COUNTER")],
        "revision": {"statement": "现有材料同时记录了急性水中险境里的冷静应对，以及面对母亲可能离去时的焦虑；因此只能提出‘特定急性身体危机可能激活冷静应对’，不能扩展到所有危机。", "change_type": "COUNTEREVIDENCE_ADDED", "change_reason": "不同危机类型呈现不同反应，原候选被反方材料限定", "evidence": [ev("event:7890e6a884ce59b1ab9f", "SUPPORT"), ev("event:57abbb4335222fd41b4c", "COUNTER")]},
    },
    {
        "memory_id": "dlmem:seed-m14", "statement": "现有童年‘肉丸规则’事件卡支持对台面规则与实际行为差异的一次观察；它不能单独证明所有正式规则都是表演。",
        "statement_type": "SYSTEM_INTERPRETATION", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "保留单一情境观察，同时拦截普遍化", "evidence": [ev("event:e31276c8c6e589b4a2b3", "SUPPORT"), pattern("pattern:6691d122c7f736c5a263", "COUNTER")],
    },
    {
        "memory_id": "dlmem:seed-m15", "statement": "日志中小黄缘龟的复得与童年讲故事者离去后未再见形成两种不同的离去经验；系统应保留差异，不把它们合并成单一的‘失去模式’。",
        "statement_type": "SYSTEM_INTERPRETATION", "confidence_state": "MEDIUM", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "保留复得与不复返的冲突经验", "evidence": [log("qflog:dc67665c25004883a37dae769e3ec7db", "CONFLICT"), ev("event:3e9351baab91946d932e", "CONFLICT")],
    },
    {
        "memory_id": "dlmem:seed-m16", "statement": "候选：煬的记忆是由自己主动、有意识地建构出来的。",
        "statement_type": "HYPOTHESIS_PENDING", "confidence_state": "LOW", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "以数字生命工程和日记中的自发回忆形成冲突候选", "evidence": [log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT"), log("qflog:85334ecc3b78429d94a75b08b7c583ac", "COUNTER")],
        "revision": {"statement": "现有材料显示记忆既会被旧日记和当下感官自发触发，也会被数字生命工程有意识地整理；‘自发回想’与‘主动建构’应并存，不能用后者吞并前者。", "change_type": "EXPLANATION_REPLACED", "change_reason": "反方原话显示记忆不全是有意控制的结果", "evidence": [log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SUPPORT"), log("qflog:85334ecc3b78429d94a75b08b7c583ac", "COUNTER")]},
    },
    {
        "memory_id": "dlmem:seed-m17", "statement": "现有单个童年‘审美图腾初觉醒’事件不足以单独证明后续稳定的审美筛选标准。",
        "statement_type": "HYPOTHESIS_PENDING", "status": "CANDIDATE", "confidence_state": "INSUFFICIENT", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "为过度审美模式保留证据不足门", "evidence": [ev("event:9da0e13ac5a3fc9e4201", "SOURCE")],
    },
    {
        "memory_id": "dlmem:seed-m18", "statement": "童年一次砖堆沉浸记录不足以单独证明跨时期、跨情境的稳定心流模式。",
        "statement_type": "HYPOTHESIS_PENDING", "status": "CANDIDATE", "confidence_state": "INSUFFICIENT", "ownership_state": "SYSTEM_CANDIDATE",
        "change_reason": "为单一事件阻止人格化外推", "evidence": [ev("event:b7d95522d4ae458841d7", "SOURCE")],
    },
    {
        "memory_id": "dlmem:seed-m19", "statement": "现有数字工程日志只能证明煬会以工程方式组织某些工作，不能直接推出亲密关系也被项目化。",
        "statement_type": "HYPOTHESIS_PENDING", "status": "CANDIDATE", "confidence_state": "INSUFFICIENT", "ownership_state": "SYSTEM_CANDIDATE", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "阻止从工作方法跨域推断亲密关系", "evidence": [log("qflog:bb10c002599d45dd914c0bbe4a77a32d", "SOURCE"), pattern("pattern:bff174a8801e07c79fa8", "COUNTER")],
    },
    {
        "memory_id": "dlmem:seed-m20", "statement": "现有少数关系材料不足以支持‘所有关系都是不对称的’这一普遍命题。",
        "statement_type": "HYPOTHESIS_PENDING", "status": "CANDIDATE", "confidence_state": "INSUFFICIENT", "ownership_state": "SYSTEM_CANDIDATE", "sensitivity_level": "S2_SENSITIVE",
        "change_reason": "为全称命题保留可证伪性", "evidence": [pattern("pattern:1dd422d4e023c3a2f40f", "SOURCE")],
    },
]


HYPOTHESES = [
    {"hypothesis_id":"dlhyp:seed-h01","source_pattern_id":"pattern:d93fa0078eec873aabd7","domain":"记忆与自我理解","claim":"在当前数字生命工程情境中，回溯早期经历是煬用于理解当下自我的一种方法，但不能因此宣告它是唯一必经之路。","applicable_period":"2026年数字生命工程阶段","applicable_context":"日记、旧记忆召回和自我理解","strongest_counterargument":"记忆也会被感官和旧文本自发触发，并非都是有意识的寻根。","alternative_explanations":["当前工程任务放大了回溯行为","旧日记的可用性而非稳定人格造成高频回望"],"failure_conditions":["后续真实问题中长期不再使用过去材料","本人明确否认寻根对自我理解的作用"],"supporting_memory_ids":["dlmem:seed-m10"],"counter_memory_ids":["dlmem:seed-m06"]},
    {"hypothesis_id":"dlhyp:seed-h02","source_pattern_id":"pattern:d74d6643544482b563a3","domain":"危机应对","claim":"在特定急性身体危机中，煬可能出现冷静应对；该模式不外推至关系或长期压力。","applicable_period":"童年已记录水中险境","applicable_context":"急性、短时、身体性危机","strongest_counterargument":"面对重要他人可能离去时，材料记录的是持续焦虑而非冷静。","alternative_explanations":["当时反应可能是偶然或生理性的","事后叙述可能强化了冷静成分"],"failure_conditions":["找到同类急性危机中明显失控的反例","原始事件归属或叙述主体被证实有误"],"supporting_memory_ids":["dlmem:seed-m13","dlmem:seed-m03"],"counter_memory_ids":["dlmem:seed-m04"],"revision":{"claim":"目前只能确认一条水中险境叙事呈现了冷静应对；在取得同类反复事件前，不登记为稳定个人模式。","change_reason":"审计后将单一事件从稳定模式降级为可观察候选","status":"CONTESTED","evidence_sufficiency":"INSUFFICIENT"}},
    {"hypothesis_id":"dlhyp:seed-h03","source_pattern_id":"pattern:42c5988123c4150886","domain":"沉浸与存在感","claim":"空间探索和复杂工程投入可能都提供强沉浸感，但尚不能确定二者是同一心理机制。","applicable_period":"1975年童年材料与2026年工程阶段","applicable_context":"空间探索和高强度创造性工作","strongest_counterargument":"童年一次事件和当下工程热情可能只是表面相似。","alternative_explanations":["新奇性","工具带来的即时反馈"],"failure_conditions":["更多同类工作中不出现沉浸","本人区分两种体验为完全不同"],"supporting_memory_ids":["dlmem:seed-m10"],"counter_memory_ids":["dlmem:seed-m18"],"revision":{"claim":"童年砖堆沉浸和2026年工程投入暂只作并置观察，不建立跨时期稳定心流模式。","change_reason":"反方证据门显示跨期同一性未被证明","status":"HELD","evidence_sufficiency":"INSUFFICIENT"}},
    {"hypothesis_id":"dlhyp:seed-h04","source_pattern_id":"pattern:162569d2df6d35e76461","domain":"文学与精神生活","claim":"童年听故事是一个明确的早期文学体验，但‘文学弥补一切物质匮乏’超出当前证据。","applicable_period":"童年及当前回望","applicable_context":"故事、阅读与创作回忆","strongest_counterargument":"单一听故事事件不能证明一生的精神滋养排序。","alternative_explanations":["讲述者的情感关系而非文学本身造成强记忆"],"failure_conditions":["后续原文显示故事体验并不重要","更强的非文学精神来源长期占主导"],"supporting_memory_ids":["dlmem:seed-m11"],"counter_memory_ids":["dlmem:seed-m06"]},
    {"hypothesis_id":"dlhyp:seed-h05","source_pattern_id":"pattern:deaea3603bc6ff46d866","domain":"记忆机制","claim":"当前记忆运行同时包含自发触发和主动整理，不应把记忆简化为单一的主动建构。","applicable_period":"2026年日志与数字生命工程阶段","applicable_context":"旧文本触发、感官触发和主动归档","strongest_counterargument":"工程化整理可能只改变记忆的表达和检索，未必改变记忆本身。","alternative_explanations":["可检索性提高造成‘记得更多’的感觉"],"failure_conditions":["后续记忆增量与工程使用无关","本人明确区分归档与记忆形成"],"supporting_memory_ids":["dlmem:seed-m16"],"counter_memory_ids":["dlmem:seed-m06"]},
    {"hypothesis_id":"dlhyp:seed-h06","source_pattern_id":"pattern:c583d96ad4b657d87ecb","domain":"匮乏与创造","claim":"童年有利用砖堆和钢铁构件进入沉浸探索的记录，但‘匮乏会稳定催生创造’仍需更多对照。","applicable_period":"童年空间材料","applicable_context":"有限物质条件下的自主游戏","strongest_counterargument":"沉浸可能来自空间新奇性，而非匮乏本身。","alternative_explanations":["儿童游戏天性","空间安全感"],"failure_conditions":["丰富材料情境同样引发沉浸","匮乏情境更常引发停滞而非创造"],"supporting_memory_ids":["dlmem:seed-m10"],"counter_memory_ids":["dlmem:seed-m18"]},
    {"hypothesis_id":"dlhyp:seed-h07","source_pattern_id":"pattern:6691d122c7f736c5a263","domain":"规则与秩序","claim":"童年肉丸事件可作为‘明示规则与实际行为有差异’的一次体验，不应推广为对一切制度的总判断。","applicable_period":"1976年幼儿园事件","applicable_context":"具体食物分配和儿童规则情境","strongest_counterargument":"事件卡本身的后来解释可能超出当年儿童的原始理解。","alternative_explanations":["单纯的儿童食物竞争","个别照护者执行不一致"],"failure_conditions":["回源后发现原文不支持规则差异","本人否认当时对规则有此感受"],"supporting_memory_ids":["dlmem:seed-m14"],"counter_memory_ids":["dlmem:seed-m03"]},
    {"hypothesis_id":"dlhyp:seed-h08","source_pattern_id":"pattern:fe5700080a6a251a4b25","domain":"离去与照护","claim":"面对重要对象的离去或失踪，现有材料可见持续记挂和寻找行动；但这不等于行动是唯一应对方式。","applicable_period":"童年母亲病弱回忆与2026年黄缘龟日志","applicable_context":"重要他者或对象的可能离去","strongest_counterargument":"材料同时包含无法改变的离去和意外复得，不能归并为一种固定程序。","alternative_explanations":["对具体对象的责任感","未完成事件的持续性效应"],"failure_conditions":["更多离去事件中主要反应是接受而非行动","本人否认行动与焦虑之间的关系"],"supporting_memory_ids":["dlmem:seed-m04","dlmem:seed-m07"],"counter_memory_ids":["dlmem:seed-m15"]},
    {"hypothesis_id":"dlhyp:seed-h09","source_pattern_id":"pattern:8283a7be940f10d99e13","domain":"身体与审美","claim":"审美敏感在早期事件和当前身体、空间叙述中都有线索，但不足以确认单一、稳定的终身筛选标准。","applicable_period":"童年审美事件与2026年身体空间日志","applicable_context":"身体、姿态、空间与感官经验","strongest_counterargument":"早期事件卡已经带有后来的‘图腾’解释，可能不是当时原始认知。","alternative_explanations":["强记忆来自新奇性而非审美规则","当前叙事反向组织了早期材料"],"failure_conditions":["更多原始材料不显示审美线索","本人否认早期事件与当前审美之间有关联"],"supporting_memory_ids":["dlmem:seed-m08","dlmem:seed-m17"],"counter_memory_ids":["dlmem:seed-m17"]},
    {"hypothesis_id":"dlhyp:seed-h10","source_pattern_id":"pattern:1dd422d4e023c3a2f40f","domain":"关系理解","claim":"现有材料允许研究具体关系中的不对称，但‘所有关系都不对称’作为全称命题目前证据不足。","applicable_period":"当前证据审计期","applicable_context":"具体关系的投入、认知和权力差异","strongest_counterargument":"不对称可能是关系的局部或阶段状态，不能从少数事件推导全部关系。","alternative_explanations":["叙述材料更容易保留失衡时刻","平衡关系因缺少冲突而记录较少"],"failure_conditions":["多类关系的长期对照显示可稳定互惠","本人对‘不对称’的定义与系统不同"],"supporting_memory_ids":["dlmem:seed-m15"],"counter_memory_ids":["dlmem:seed-m20"]},
]


def create_or_skip_memory(conn: sqlite3.Connection, spec: dict) -> dict:
    memory_id = spec["memory_id"]
    exists = conn.execute("SELECT current_version_id FROM dl2_memory_units WHERE memory_id=?", (memory_id,)).fetchone()
    if not exists:
        payload = {key: value for key, value in spec.items() if key != "revision"}
        preview = dl2.preview_memory(conn, payload)
        result = dl2.confirm_memory(conn, preview["preview_id"])
    else:
        result = {"memory_id": memory_id, "status": "EXISTS"}
    revision = spec.get("revision")
    version_count = conn.execute("SELECT COUNT(*) FROM dl2_memory_versions WHERE memory_id=?", (memory_id,)).fetchone()[0]
    if revision and version_count < 2:
        payload = dict(revision)
        payload.update({"memory_id": memory_id, "changed_by": "PROGRAM_AUDIT", "confidence_state": "LOW"})
        preview = dl2.preview_memory_revision(conn, payload)
        result["revision"] = dl2.confirm_memory_revision(conn, preview["preview_id"])
    return result


def create_or_skip_hypothesis(conn: sqlite3.Connection, spec: dict) -> dict:
    hypothesis_id = spec["hypothesis_id"]
    exists = conn.execute("SELECT current_version_id FROM dl2_model_hypotheses WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()
    if not exists:
        payload = {key: value for key, value in spec.items() if key != "revision"}
        preview = dl2.preview_hypothesis(conn, payload)
        result = dl2.confirm_hypothesis(conn, preview["preview_id"])
    else:
        result = {"hypothesis_id": hypothesis_id, "status": "EXISTS"}
    revision = spec.get("revision")
    version_count = conn.execute("SELECT COUNT(*) FROM dl2_hypothesis_versions WHERE hypothesis_id=?", (hypothesis_id,)).fetchone()[0]
    if revision and version_count < 2:
        base = {key: value for key, value in spec.items() if key not in {"revision", "hypothesis_id", "source_pattern_id", "domain"}}
        base.update(revision)
        base.update({"hypothesis_id": hypothesis_id, "changed_by": "PROGRAM_AUDIT"})
        preview = dl2.preview_hypothesis_revision(conn, base)
        result["revision"] = dl2.confirm_hypothesis_revision(conn, preview["preview_id"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="数字生命2.0 M1/M2真实材料垂直试跑")
    parser.add_argument("--db", type=Path, default=db_runtime.write_db_path())
    args = parser.parse_args()
    with sqlite3.connect(args.db, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        dl2.migrate(conn)
        memory_results = [create_or_skip_memory(conn, spec) for spec in MEMORIES]
        hypothesis_results = [create_or_skip_hypothesis(conn, spec) for spec in HYPOTHESES]
        conn.commit()
        status = dl2.status_payload(conn)
    payload = {
        "run": "DL2_VERTICAL_SEED_V1",
        "principle": "只使用现有事件、日志和心理模式；未伪造用户回答或跨工程回执。",
        "memory_results": memory_results,
        "hypothesis_results": hypothesis_results,
        "status": status,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if status["milestones"]["M1"] == "PASS" and status["milestones"]["M2"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
