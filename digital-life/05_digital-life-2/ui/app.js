const state = {
  view: "timeline",
  status: null,
  timeline: null,
  chronicle: null,
  selectedNode: null,
  preview: null,
  selectedTimelineNodeId: "",
  logScope: "general",
  synthesis: null,
};

const OFFLINE_DATA = window.__OFFLINE_DATA || null;
const OFFLINE_MODE = Boolean(OFFLINE_DATA);

function safeJson(value, fallback) {
  try {
    return JSON.parse(value || "");
  } catch {
    return fallback;
  }
}

function safeDateText(value) {
  return String(value || "");
}

function monthBounds(month) {
  const [, y, m] = /^(\d{4})-(\d{1,2})$/.exec(safeDateText(month)) || [];
  if (!y || !m) return null;
  const year = Number(y);
  const monthNo = Number(m);
  const start = new Date(year, monthNo - 1, 1);
  const end = new Date(year, monthNo, 0);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

function countDays(startIso, endIso) {
  if (!startIso || !endIso) return 0;
  const startDate = new Date(`${startIso}T00:00:00`);
  const endDate = new Date(`${endIso}T00:00:00`);
  if (Number.isNaN(startDate.valueOf()) || Number.isNaN(endDate.valueOf())) return 0;
  return Math.floor((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

const titles = {
  timeline: "时空轴总览",
  chronicle: "编年史",
  synthesis: "阶段归纳",
  "log-intake": "日志入库",
  search: "全局搜索",
  entities: "关系网络",
  evidence: "原文证据",
  operations: "运行中枢",
  dl2: "数字生命2.0｜可回源个人模型",
  qingfeng: "清风场域",
  rules: "规则索引",
  flow: "心流门禁",
  people: "人物",
  events: "事件",
  terms: "术语",
  logs: "日志",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function compact(value, length = 180) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length > length ? `${text.slice(0, length - 1)}…` : text;
}

function normalizeAiResponse(value) {
  return String(value || "").replace(/^AI回应[:：]?\s*/i, "").trim();
}

function simpleHash(value) {
  let hash = 2166136261;
  const text = String(value || "");
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `hx${(hash >>> 0).toString(16)}`;
}

function normalizeAliasText(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  if (typeof value === "string") {
    return value
      .split(/[，,;；/|·\s]+/g)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return [];
}

function parseDateFromText(text) {
  const now = new Date();
  const patterns = [
    /(?<y>\d{4})年(?<m>\d{1,2})月(?<d>\d{1,2})日/,
    /(?<y>\d{4})[-/](?<m>\d{1,2})-(?<d>\d{1,2})/,
    /(?<y>\d{4})[-/](?<m>\d{1,2})\/(?<d>\d{1,2})/,
  ];
  for (const reg of patterns) {
    const match = String(text || "").match(reg);
    if (!match || !match.groups) continue;
    const y = Number(match.groups.y);
    const m = Number(match.groups.m);
    const d = Number(match.groups.d);
    if (y >= 2000 && y <= 3000 && m >= 1 && m <= 12 && d >= 1 && d <= 31) {
      const iso = `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const date = new Date(`${iso}T00:00:00`);
      if (!Number.isNaN(date.valueOf())) {
        return [iso, `${y}年${m}月${d}日`];
      }
    }
  }
  const iso = now.toISOString().slice(0, 10);
  return [iso, `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日`];
}

function saveOfflineDraft(payload) {
  if (!OFFLINE_MODE || typeof localStorage === "undefined") return;
  try {
    const key = "digital_life_offline_drafts_v1";
    const raw = localStorage.getItem(key);
    const current = raw ? JSON.parse(raw) : [];
    const list = Array.isArray(current) ? current : [];
    list.unshift({ ...payload, created_at: new Date().toLocaleString(), source: "offline_static" });
    localStorage.setItem(key, JSON.stringify(list.slice(0, 80)));
  } catch {
    // 本地存储失败不影响预览生成
  }
}

function formatDraftMarkdown(payload) {
  const receipt = payload.receipt || {};
  const lines = [
    "# 日志草稿（离线）",
    "",
    `- 生成时间：${new Date(payload.generated_at || Date.now()).toLocaleString()}`,
    `- 生成ID：${payload.draft_id || ""}`,
    `- 原文日期：${payload.inferred_date_raw || ""}`,
    `- 心流分类：${payload.flow_classification || ""}`,
    "",
    "## 原文（逐字保留）",
    "```",
    String(payload.original_text || ""),
    "```",
    "",
    "## 摘要",
    String(payload.summary || ""),
    "",
    "## 关键词",
    (payload.keywords || []).map((word) => `- ${word}`).join("\n") || "- 无",
    "",
    "## 识别人物",
    (payload.related_people || []).length
      ? (payload.related_people || []).map((item) => `- ${item.canonical_name || item.name || ""}（${item.matched_alias || ""}）`).join("\n")
      : "- 无",
    "",
    "## 识别空间",
    (payload.related_spaces || []).length
      ? (payload.related_spaces || []).map((item) => `- ${item.name || ""}（${item.matched_alias || ""}）`).join("\n")
      : "- 无",
    "",
    "## 候选时空轴",
    (payload.candidate_timeline_nodes || []).length
      ? (payload.candidate_timeline_nodes || []).map((item) => `- ${item.title || ""} | ${item.date_range?.from || ""} ~ ${item.date_range?.to || ""} | ${item.main_space || ""}`).join("\n")
      : "- 无",
    "",
    "## 回执（七项）",
    ...Object.entries(receipt).map(([key, value]) => `- ${key}：${Array.isArray(value) ? value.join("、") : value}`),
  ];
  return lines.filter((line) => line !== "").join("\n");
}


function offlineApi(path, options = {}) {
  if (!OFFLINE_MODE) {
    return Promise.reject(new Error("离线模式未启用"));
  }
  const [rawPath, rawQuery = ""] = path.split("?");
  const query = new URLSearchParams(rawQuery);
  const method = (options.method || "GET").toUpperCase();

  const getTimelineNodes = () => ensureArray(OFFLINE_DATA.timeline_query_index || []);
  const getPeople = () => ensureArray(OFFLINE_DATA.people || []);
  const getEvents = () => ensureArray(OFFLINE_DATA.events || []);
  const getTerms = () => ensureArray(OFFLINE_DATA.terms || []);
  const getPlaces = () => ensureArray(OFFLINE_DATA.places || []);
  const getCollections = () => ensureArray(OFFLINE_DATA.collections || []);
  const getSpaceFinanceRecords = () => ensureArray(OFFLINE_DATA.qingfeng_space_finance_records || []);
  const getOralSessions = () => ensureArray(OFFLINE_DATA.oral_sessions || []);
  const getPatterns = () => ensureArray(OFFLINE_DATA.psychological_patterns || []);
  const isRestrictedFlow = (flowType) => String(flowType || "").toLowerCase().startsWith("xiaoge");
  const getLogs = (flowScope = "all", explicit = false) => {
    const all = ensureArray(OFFLINE_DATA.qingfeng_logs || []);
    const scope = String(flowScope || "all").toLowerCase();
    if (scope === "general") {
      return all.filter((item) => !isRestrictedFlow(item.flow_type));
    }
    if (scope === "xiaoge" || scope === "restricted" || scope === "special" || scope === "xiaoge_flow") {
      return explicit ? all.filter((item) => isRestrictedFlow(item.flow_type)) : [];
    }
    return all;
  };
  const getSpaces = () => ensureArray(OFFLINE_DATA.qingfeng_spaces || []);
  const getContextItems = () => ensureArray(OFFLINE_DATA.qingfeng_context_items || []);
  const getRuleSources = () => ensureArray(OFFLINE_DATA.rule_sources || []);
  const getRules = () => ensureArray(OFFLINE_DATA.rules || []);
  const getTriggers = () => ensureArray(OFFLINE_DATA.trigger_routes || []);
  const getConstraints = () => ensureArray(OFFLINE_DATA.rule_constraints || []);
  const getEvidence = () => ensureArray(OFFLINE_DATA.evidence_index || []);
  const getSegments = () => ensureArray(OFFLINE_DATA.timeline_query_segments || []);
  const getEntities = () => ensureArray(OFFLINE_DATA.entity_cards || []);
  const getRelations = () => ensureArray(OFFLINE_DATA.relation_index || []);
  const getSourceFiles = () => ensureArray(OFFLINE_DATA.source_files || []);
  const getSourceDocuments = () => ensureArray(OFFLINE_DATA.source_documents || []);
  const getCsvTables = () => ensureArray(OFFLINE_DATA.csv_tables || []);
  const getCsvRows = () => ensureArray(OFFLINE_DATA.csv_rows || []);

  const queryNode = (row, args) => {
    const date = args.date;
    const month = args.month;
    const from = args.from;
    const to = args.to;
    const keyword = safeDateText(args.keyword).toLowerCase();
    const phase = safeDateText(args.phase).toLowerCase();
    const trip = args.trip;
    const status = args.status;
    if (date) {
      if (!(safeDateText(row.start_iso) <= date && safeDateText(row.end_iso) >= date)) return false;
    }
    if (month) {
      const bounds = monthBounds(month);
      if (!bounds) return false;
      if (!(safeDateText(row.start_iso) <= bounds.end && safeDateText(row.end_iso) >= bounds.start)) return false;
    }
    if (from || to) {
      const startDate = from || "0001-01-01";
      const endDate = to || "9999-12-31";
      if (!(safeDateText(row.start_iso) <= endDate && safeDateText(row.end_iso) >= startDate)) return false;
    }
    if (keyword) {
      const like = keyword;
      const text = [
        row.title || "",
        row.search_text || "",
        row.main_space || "",
        row.specific_place || "",
      ].join(" ").toLowerCase();
      if (!text.includes(like)) return false;
    }
    if (trip && !row.is_trip) return false;
    if (status && row.record_status !== status) return false;
    if (phase) {
      const normalizedPhase = phase.toLowerCase();
      const isExplicitTripPhase = ["外出", "外出段", "trip", "出行"].some((item) => normalizedPhase.includes(item));
      if (isExplicitTripPhase && !row.is_trip) return false;
      const phaseText = [
        row.phase_label,
        row.query_scope,
        row.title,
        row.main_space,
        row.specific_place,
      ].join(" ").toLowerCase();
      if (!phaseText.includes(normalizedPhase)) return false;
    }
    return true;
  };

  const isContextNode = (row, args) => {
    const hasTimeFilter = Boolean(args.date || args.month || args.from || args.to);
    if (args.include_context || hasTimeFilter) return false;
    return (row.node_level === "大段" || row.main_space === "清风别墅")
      && !row.is_trip
      && (Number(row.duration_days || 0) > 31);
  };

  const toNodePayload = (row, explicitFlow = false) => {
    const relationCounts = safeJson(row.relation_counts_json, {});
    const controlledFlow = Boolean(row.has_flow_marker) && !explicitFlow;
    return {
      id: row.timeline_node_id,
      title: row.title,
      date_range: { from: row.start_iso, to: row.end_iso, duration_days: row.duration_days },
      raw_date_range: { from: row.start_date_raw, to: row.end_date_raw },
      scope: row.query_scope,
      is_trip: Boolean(row.is_trip),
      phase_label: row.phase_label,
      main_space: row.main_space,
      specific_place: row.specific_place,
      cities: safeJson(row.cities_json, []),
      companions: safeJson(row.normalized_companions_json, []),
      record_status: row.record_status,
      node_level: row.node_level,
      has_flow_marker: Boolean(row.has_flow_marker),
      relation_counts: relationCounts,
      source_anchor: controlledFlow ? "" : row.source_anchor,
      source_page: row.source_page,
      source_file_id: row.source_file_id,
      source_row_id: row.source_row_id,
      summary: controlledFlow
        ? "该节点含心流标记。普通时空轴查询仅显示受控标记；明确触发小哥/小鸽心流后再进入专项输出。"
        : compact(row.search_text),
    };
  };

  const timelinePayload = (payloadPath, args, includeContext = false) => {
    const nodes = getTimelineNodes().filter((row) => queryNode(row, args));
    const contextNodes = includeContext
      ? nodes.filter((node) => isContextNode(node, args))
      : [];
    const pureNodes = nodes.filter((row) => !isContextNode(row, args));
    pureNodes.sort((a, b) => safeDateText(a.start_iso).localeCompare(safeDateText(b.start_iso)));
    contextNodes.sort((a, b) => safeDateText(a.start_iso).localeCompare(safeDateText(b.start_iso)));
    const cities = [];
    const spaces = [];
    const companions = [];
    pureNodes.forEach((row) => {
      cities.push(...ensureArray(safeJson(row.cities_json, [])));
      if (row.main_space) spaces.push(row.main_space);
      companions.push(...ensureArray(safeJson(row.normalized_companions_json, [])));
    });
    const nodePayloads = pureNodes.map((row) => toNodePayload(row, Boolean(args.explicit_flow)));
    const relationTypes = [];
    if (nodePayloads.length) {
      const nodeIds = nodePayloads.map((node) => node.id);
      const relatedRelations = getRelations().filter((item) => (
        (item.source_type === "timeline_node" && nodeIds.includes(item.source_id))
        || (item.target_type === "timeline_node" && nodeIds.includes(item.target_id))
      ));
      const relationMap = {};
      relatedRelations.forEach((item) => {
        relationMap[item.relation_type] = (relationMap[item.relation_type] || 0) + 1;
      });
      relationTypes.push(...Object.entries(relationMap).map(([relation_type, count]) => ({ relation_type, count })));
    }
    const starts = pureNodes.map((row) => row.start_iso).filter(Boolean);
    const ends = pureNodes.map((row) => row.end_iso).filter(Boolean);
    const scopeFrom = starts.length ? starts.reduce((acc, item) => (acc < item ? acc : item), starts[0]) : null;
    const scopeTo = ends.length ? ends.reduce((acc, item) => (acc > item ? acc : item), ends[0]) : null;
    const evidenceCount = getEvidence().filter((item) => item.entity_type === "timeline_node" && nodePayloads.some((node) => node.id === item.entity_id)).length;
    const missingSource = nodePayloads.filter((node) => !node.source_file_id).length;
    const top = (arr) => {
      const map = {};
      arr.forEach((item) => {
        if (!item) return;
        map[item] = (map[item] || 0) + 1;
      });
      return Object.entries(map).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count).slice(0, 12);
    };
    return {
      query: payloadPath,
      stats: {
        node_count: nodePayloads.length,
        from_iso: scopeFrom,
        to_iso: scopeTo,
        day_count: countDays(scopeFrom, scopeTo),
        trip_node_count: nodePayloads.filter((node) => node.is_trip).length,
        stage_node_count: nodePayloads.filter((node) => node.node_level === "大段").length,
        flow_marker_node_count: nodePayloads.filter((node) => node.has_flow_marker).length,
        pending_node_count: nodePayloads.filter((node) => ["待补录", "待确认", "记录中"].includes(node.record_status || "")).length,
        related_log_count: nodePayloads.reduce((sum, node) => sum + (Number(node.relation_counts?.logs || 0)), 0),
        related_oral_count: nodePayloads.reduce((sum, node) => sum + (Number(node.relation_counts?.oral_sessions || node.relation_counts?.oral || 0)), 0),
        city_count: top(cities).length,
        companion_count: top(companions).length,
        space_count: top(spaces).length,
        missing_source_count: missingSource,
        evidence_count: evidenceCount,
      },
      cities: top(cities),
      spaces: top(spaces),
      companions: top(companions),
      relation_types: relationTypes.slice(0, 24),
      nodes: nodePayloads,
      context_nodes: includeContext ? contextNodes.map((row) => toNodePayload(row, false)) : [],
    };
  };

  if (method !== "GET") {
    if (rawPath === "/api/preflight") {
      const body = JSON.parse((options.body || "{}"));
      return Promise.resolve({
        flow_gate_required: safeDateText(body.text || "").includes("小哥心流") || safeDateText(body.text || "").includes("小鸽心流"),
        flow_hint: "离线环境仅支持阅读，不执行写入闭环。",
      });
    }
    if (rawPath === "/api/logs/preview") {
      const body = JSON.parse((options.body || "{}"));
      const text = safeDateText(body.text || "").trim();
      if (!text) return Promise.reject(new Error("日志原话不能为空"));
      const explicitDate = safeDateText(body.date || "");
      const lowerText = text.toLowerCase();
      const [inferredIso, inferredRaw] = parseDateFromText(explicitDate || text);
      const people = getPeople();
      const spaces = getSpaces();
      const timelineRows = getTimelineNodes();
      const matchedPeople = [];
      const seenPeople = new Set();
      people.forEach((person) => {
        const aliases = normalizeAliasText(person.aliases);
        const candidates = Array.from(new Set([person.name, ...aliases].filter(Boolean)));
        const matchedAlias = candidates.find((token) => lowerText.includes(String(token).toLowerCase()));
        if (!matchedAlias) return;
        const key = String(person.person_id || person.name || matchedAlias);
        if (seenPeople.has(key)) return;
        seenPeople.add(key);
        matchedPeople.push({
          person_id: person.person_id,
          canonical_name: person.name || matchedAlias,
          matched_alias: matchedAlias,
          confidence: 95,
        });
      });

      const matchedSpaces = [];
      const seenSpaces = new Set();
      spaces.forEach((space) => {
        const aliases = normalizeAliasText(space.aliases);
        const candidates = [space.name, ...aliases, space.physical_location].filter(Boolean);
        const matchedAlias = candidates.find((token) => lowerText.includes(String(token).toLowerCase()));
        if (!matchedAlias) return;
        const key = String(space.space_id || space.name || matchedAlias);
        if (seenSpaces.has(key)) return;
        seenSpaces.add(key);
        matchedSpaces.push({
          space_id: space.space_id || "",
          name: space.name || matchedAlias,
          matched_alias: matchedAlias,
          confidence: 88,
        });
      });

      const keywordSet = Array.from(new Set([
        ...matchedPeople.map((item) => item.matched_alias || ""),
        ...matchedPeople.map((item) => item.canonical_name || ""),
        ...matchedSpaces.map((item) => item.name || ""),
        ...matchedSpaces.map((item) => item.matched_alias || ""),
        "清风",
        "陈斌",
        "小哥",
        "小鸽",
        "五台山",
        "北京",
        "桐庐",
      ].filter(Boolean).map((item) => String(item).toLowerCase())));

      const candidateMap = {};
      const addCandidate = (row, score, reason) => {
        const id = String(row.timeline_node_id || row.id || "");
        if (!id || candidateMap[id]) return;
        const payload = toNodePayload(row, false);
        candidateMap[id] = {
          timeline_node_id: id,
          title: payload.title,
          date_range: payload.date_range,
          main_space: payload.main_space,
          specific_place: payload.specific_place,
          companions: payload.companions || [],
          has_flow_marker: payload.has_flow_marker,
          match_reason: reason,
          score,
        };
      };

      if (inferredIso) {
        timelineRows.forEach((row) => {
          if (safeDateText(row.start_iso) <= inferredIso && safeDateText(row.end_iso) >= inferredIso) {
            addCandidate(row, 92, "same_day");
          }
        });
      }

      timelineRows.forEach((row) => {
        const rowText = `${row.title || ""} ${row.search_text || ""} ${row.main_space || ""} ${row.specific_place || ""}`.toLowerCase();
        keywordSet.forEach((keyword) => {
          if (keyword && rowText.includes(keyword)) {
            addCandidate(row, 68, `keyword:${keyword}`);
          }
        });
      });

      const candidates = Object.values(candidateMap)
        .map((item) => {
          const range = item.date_range || {};
          return {
            ...item,
            date_range: {
              from: range.from || "",
              to: range.to || "",
            },
          };
        })
        .sort((a, b) => (Number(b.score) - Number(a.score)) || safeDateText(a.date_range.from).localeCompare(safeDateText(b.date_range.from)))
        .slice(0, 10);

      const bodyStripped = text.replace(/^(\s*今日日志[:：]?\s*|\s*当日日志[:：]?\s*|\s*清风时空[:：]?\s*|\s*清风录入[:：]?\s*|\s*第六阶段录入[:：]?\s*|\s*日志入库[:：]?\s*)/g, "");
      const title = `${inferredRaw}｜${compact(bodyStripped, 34)}`;
      const summary = `离线草稿摘要：${compact(bodyStripped, 140)}`;
      const flowClassification = lowerText.includes("小哥心流") || lowerText.includes("小鸽心流")
        ? "xiaoge_explicit"
        : (lowerText.includes("心流") || lowerText.includes("清流") ? "general_or_controlled_marker" : "none");
      const missing = [];
      if (!candidates.length) missing.push("需确认或新建时空轴节点");
      if (!matchedPeople.length) missing.push("人物未明确或需核对");
      if (!matchedSpaces.length) missing.push("空间未明确或需核对");
      if (!missing.length) missing.push("无");

      const payload = {
        draft_id: `offline:${simpleHash(`${text}-${Date.now()}`)}`,
        original_text: text,
        original_text_saved_verbatim: true,
        notion_mother_modified: false,
        original_sha256: simpleHash(text),
        inferred_date_iso: inferredIso,
        inferred_date_raw: inferredRaw,
        title,
        summary,
        keywords: keywordSet,
        ai_response: "",
        related_people: matchedPeople,
        related_spaces: matchedSpaces,
        candidate_timeline_nodes: candidates,
        flow_classification: flowClassification,
        explicit_flow_required: lowerText.includes("小哥心流") || lowerText.includes("小鸽心流"),
        receipt: {
          "时空轴节点": candidates[0]?.title || "待确认或需新建当日节点",
          "写入日期": inferredRaw,
          "日志正文面": "离线草稿已生成，原文逐字保留",
          "双面回链": "已生成候选关联关系，未正式写入",
          "深度点评": "已完成离线识别与规则门禁预检（草稿态）",
          "待补项": missing,
          "母本未修改确认": true,
          "原文哈希": simpleHash(text),
        },
        generated_at: Date.now(),
      };
      if (body.save !== false) {
        saveOfflineDraft(payload);
      }
      return Promise.resolve(payload);
    }
    if (rawPath === "/api/logs/confirm") {
      return Promise.reject(new Error("静态版不支持日志确认写入，请启动本地服务后确认。"));
    }
    return Promise.reject(new Error("离线版本不支持该写入接口"));
  }

  if (rawPath === "/api/status") {
    return Promise.resolve(OFFLINE_DATA.status_payload || {});
  }
  if (rawPath === "/api/operations") {
    const queueItems = ensureArray(OFFLINE_DATA.intake_queue || []);
    const analyticsItems = ensureArray(OFFLINE_DATA.timeline_analytics_cache || []);
    const mediaItems = ensureArray(OFFLINE_DATA.media_assets || []);
    const phase2Runs = ensureArray(OFFLINE_DATA.phase2_optimization_runs || []);
    const privacyRows = ensureArray(OFFLINE_DATA.privacy_gate_audit || []);
    const backupRows = ensureArray(OFFLINE_DATA.external_backup_checks || []);
    const evidenceGrades = ensureArray(OFFLINE_DATA.evidence_grade_index || []);
    return Promise.resolve({
      counts: {
        intake_queue: queueItems.length,
        incremental_file_manifest: ensureArray(OFFLINE_DATA.incremental_file_manifest || []).length,
        evidence_grade_index: evidenceGrades.length,
        timeline_analytics_cache: analyticsItems.length,
        media_assets: mediaItems.length,
        media_asset_relations: ensureArray(OFFLINE_DATA.media_asset_relations || []).length,
        privacy_gate_audit: privacyRows.length,
        external_backup_checks: backupRows.length,
        phase2_optimization_runs: phase2Runs.length,
      },
      queue_status_counts: countBy(queueItems, "status"),
      queue_workflow_counts: countBy(queueItems, "workflow_id"),
      evidence_grade_counts: countBy(evidenceGrades, "evidence_grade"),
      analytics_scope_counts: countBy(analyticsItems, "scope_type"),
      media_area_counts: countBy(mediaItems, "source_area"),
      queue_items: queueItems,
      timeline_analytics: analyticsItems,
      media_assets: mediaItems,
      phase2_runs: phase2Runs,
      latest_privacy_audit: privacyRows[0] || {},
      latest_backup_check: backupRows[0] || {},
      reports: {
        phase2: {},
        pipeline: {},
        health: {},
        backup_restore: {},
      },
    });
  }
  if (rawPath === "/api/timeline") {
    return Promise.resolve(timelinePayload(rawPath, {
      date: query.get("date") || "",
      month: query.get("month") || "",
      from: query.get("from") || "",
      to: query.get("to") || "",
      keyword: query.get("keyword") || query.get("q") || "",
      phase: query.get("phase") || "",
      trip: query.get("trip") === "1",
      status: query.get("status") || "",
      explicit_flow: query.get("explicit_flow") === "1",
      include_context: query.get("include_context") === "1",
      limit: Number(query.get("limit") || 120),
    }, true));
  }
  if (rawPath === "/api/timeline/stats") {
    const data = timelinePayload(rawPath, {
      date: query.get("date") || "",
      month: query.get("month") || "",
      from: query.get("from") || "",
      to: query.get("to") || "",
      phase: query.get("phase") || "",
      trip: query.get("trip") === "1",
      status: query.get("status") || "",
      limit: Number(query.get("limit") || 120),
      explicit_flow: query.get("explicit_flow") === "1",
      include_context: query.get("include_context") === "1",
    }, false);
    return Promise.resolve({
      query: {
        date: query.get("date") || "",
        from: query.get("from") || "",
        to: query.get("to") || "",
        month: query.get("month") || "",
        trip: query.get("trip") || "",
      },
      summary: data.stats || {},
      cities: data.cities || [],
      spaces: data.spaces || [],
      companions: data.companions || [],
      relation_types: data.relation_types || [],
      nodes: data.nodes || [],
    });
  }
  if (rawPath === "/api/timeline/segments") {
    const queryType = query.get("segment_type") || query.get("type") || "stage";
    const filterDate = query.get("date") || "";
    const from = query.get("from") || "";
    const to = query.get("to") || "";
    const month = query.get("month") || "";
    const phase = query.get("phase") || "";
    const q = query.get("q") || query.get("keyword") || "";
    const limit = Math.min(Number(query.get("limit") || 200), 500);
    const rows = getSegments().filter((item) => {
      if (queryType && queryType !== "all" && item.segment_type !== queryType) return false;
      const fromIso = safeDateText(item.from_iso || "");
      const toIso = safeDateText(item.to_iso || "");
      if (filterDate && !(fromIso <= filterDate && toIso >= filterDate)) return false;
      if (from || to) {
        const start = from || "0001-01-01";
        const end = to || "9999-12-31";
        if (!(fromIso <= end && toIso >= start)) return false;
      }
      if (month) {
        const bounds = monthBounds(month);
        if (!bounds) return false;
        if (!(fromIso <= bounds.end && toIso >= bounds.start)) return false;
      }
      if (phase) {
        const like = phase.toLowerCase();
        if (!safeDateText(item.label).toLowerCase().includes(like)) return false;
      }
      if (q) {
        const like = safeDateText(q).toLowerCase();
        const searchText = `${safeDateText(item.label)} ${safeDateText(item.segment_id)} ${safeDateText(item.main_spaces_json)}`.toLowerCase();
        if (!searchText.includes(like)) return false;
      }
      return true;
    }).sort((a, b) => safeDateText(b.from_iso || "").localeCompare(safeDateText(a.from_iso || "")));
    const items = rows.map((row) => {
      const nodeCount = Number(row.node_count || 0);
      const cityCount = Number(row.city_count || 0);
      const pendingCount = Number(row.pending_count || 0);
      const relatedLogCount = Number(row.related_log_count || 0);
      const flowMarkerCount = Number(row.flow_node_count || 0);
      const anomalies = [];
      if (pendingCount > 0) anomalies.push(`待补项 ${pendingCount} 条`);
      if (relatedLogCount === 0) anomalies.push("无日志关联");
      if (cityCount === 0) anomalies.push("缺少地点");
      if (nodeCount === 0) anomalies.push("节点为空");
      return {
        segment_id: row.segment_id,
        segment_type: row.segment_type,
        label: row.label,
        from_iso: row.from_iso,
        to_iso: row.to_iso,
        node_count: nodeCount,
        day_count: Number(row.day_count || 0),
        trip_count: Number(row.trip_count || 0),
        city_count: cityCount,
        companion_count: Number(row.companion_count || 0),
        flow_node_count: flowMarkerCount,
        related_log_count: relatedLogCount,
        pending_count: pendingCount,
        timeline_node_ids: row.timeline_node_ids,
        anomalies,
        cities: (() => {
          try {
            return JSON.parse(row.cities_json || "[]");
          } catch (error) {
            return [];
          }
        })(),
        main_spaces: (() => {
          try {
            return JSON.parse(row.main_spaces_json || "[]");
          } catch (error) {
            return [];
          }
        })(),
      };
    });
    const summary = {
      segment_type: queryType,
      item_count: items.length,
      anomaly_count: items.filter((item) => item.anomalies.length).length,
      filtered_node_count: items.reduce((sum, item) => sum + item.node_count, 0),
      filtered_day_count: items.reduce((sum, item) => sum + item.day_count, 0),
      pending_count: items.reduce((sum, item) => sum + item.pending_count, 0),
      trip_count: items.reduce((sum, item) => sum + item.trip_count, 0),
    };
    return Promise.resolve({ items, summary, filters: { segment_type: queryType, date: filterDate, from, to, month, phase, q } });
  }
  if (rawPath === "/api/source-alias/status" || rawPath === "/api/source-alias/unresolved") {
    const aliases = ensureArray(OFFLINE_DATA.source_path_aliases || []);
    const counts = aliases.reduce((acc, item) => {
      const kind = item.alias_kind || "";
      acc[kind] = (acc[kind] || 0) + 1;
      return acc;
    }, {});
    const unresolved = aliases.filter((item) => item.alias_kind === "unresolved_link");
    return Promise.resolve({
      ok: aliases.length > 0,
      summary: {
        exists: aliases.length > 0,
        alias_count: aliases.length,
        alias_kind_counts: counts,
      },
      unresolved_count: unresolved.length,
      unresolved,
      validation: {},
      principle: "只用于本地读取索引和链接解析，不覆盖原始镜像，不回写 Notion/CRV。",
    });
  }
  if (rawPath === "/api/search") {
    const keyword = safeDateText(query.get("q") || "");
    if (!keyword) return Promise.resolve({ q: "", results: [] });
    const limit = Math.min(Number(query.get("limit") || 50), 200);
    const normalized = keyword.trim();
    const nodes = [];
    const timeline = getTimelineNodes().filter((node) => [node.title, node.search_text, node.main_space, node.specific_place, node.source_path]
      .join(" ").includes(normalized))
      .map((item) => ({
        type: "时空轴",
        entity_type: "timeline_node",
        id: item.timeline_node_id,
        title: item.title,
        subtitle: compact([item.start_iso, item.end_iso, item.main_space, item.specific_place].filter(Boolean).join(" / "), 96),
        body: compact(item.search_text || "", 220),
        source_file_id: item.source_file_id,
        source_row_id: item.source_row_id,
      })).slice(0, limit);
    nodes.push(...timeline);
    [
      ...getPeople(),
      ...getEvents(),
      ...getTerms(),
      ...getLogs(),
      ...ensureArray(OFFLINE_DATA.collections || []),
      ...getSpaceFinanceRecords(),
    ].forEach((item) => {
      const title = item.name || item.title || "";
      const body = item.summary || item.definition || item.original_text || "";
      const text = `${title} ${item.subtitle || ""} ${body}`;
      if (!text.includes(normalized)) return;
      const entityType = item.person_id ? "person" : (item.event_id ? "event" : (item.term_id ? "term" : (item.log_id ? "qingfeng_log" : (item.record_id ? "space_finance_record" : "collection"))));
      const typeLabel = ({
        person: "人物",
        event: "事件",
        term: "术语",
        qingfeng_log: "日志",
        space_finance_record: "空间财务",
        collection: "藏品",
      })[entityType] || "对象";
      nodes.push({
        type: typeLabel,
        entity_type: entityType,
        id: item.person_id || item.event_id || item.term_id || item.log_id || item.record_id || item.collection_id,
        title,
        subtitle: item.subtitle || "",
        body: compact(body || "", 220),
        source_file_id: item.source_file_id,
        source_row_id: item.source_row_id,
      });
    });
    return Promise.resolve({ q: normalized, results: nodes.slice(0, limit) });
  }
  if (rawPath === "/api/qingfeng/context") {
    const contextType = query.get("type");
    const items = getContextItems().filter((item) => !contextType || item.context_type === contextType);
    return Promise.resolve({
      items,
      type_counts: [],
      spaces: getSpaces(),
    });
  }
  if (rawPath === "/api/rules") {
    return Promise.resolve({
      sources: getRuleSources().map((item) => ({
        ...item,
      })),
      rules: getRules().map((item) => ({
        ...item,
      })),
      triggers: getTriggers(),
      constraints: getConstraints(),
    });
  }
  if (rawPath === "/api/people") return Promise.resolve({ items: getPeople().map((item) => ({ id: item.person_id, entity_type: "person", title: item.name, subtitle: item.relationship_to_owner || item.group_name || item.phase || "", body: item.summary, source_file_id: item.source_file_id, source_row_id: item.source_row_id })) });
  if (rawPath === "/api/events") return Promise.resolve({ items: getEvents().map((item) => ({ id: item.event_id, entity_type: "event", title: item.title, subtitle: item.event_date || "", body: item.summary, source_file_id: item.source_file_id, source_row_id: item.source_row_id })) });
  if (rawPath === "/api/terms") return Promise.resolve({ items: getTerms().map((item) => ({ id: item.term_id, entity_type: "term", title: item.name, subtitle: item.term_type || "", body: item.definition, source_file_id: item.source_file_id, source_row_id: item.source_row_id })) });
  if (rawPath === "/api/logs") {
    const flowScope = (query.get("flow_scope") || query.get("scope") || "general").toLowerCase();
    const explicit = query.get("explicit") === "1";
    const logs = getLogs(flowScope, explicit);
    if (["xiaoge", "restricted", "special", "xiaoge_flow"].includes(flowScope) && !explicit && logs.length === 0) {
      return Promise.resolve({
        allowed: false,
        gate: "小哥/小鸽心流必须明确触发后才显示专项内容。",
        items: [],
      });
    }
      return Promise.resolve({
        items: logs.map((item) => ({
          id: item.log_id,
          entity_type: "qingfeng_log",
          title: item.title,
          subtitle: item.log_date || "",
          body: item.summary,
          timeline_node_id: item.timeline_node_id,
          flow_type: item.flow_type,
          status: item.status,
          ai_response: item.ai_response,
          source_file_id: item.source_file_id,
          source_row_id: item.source_row_id,
        })),
      });
    }
  if (rawPath === "/api/drafts") return Promise.resolve({ items: ensureArray(OFFLINE_DATA.log_intake_drafts || []).map((item) => ({ id: item.draft_id, title: item.title, subtitle: item.inferred_date_raw || "", body: item.summary, status: item.status, flow_classification: item.flow_classification, created_at: item.created_at })) });
  if (rawPath === "/api/flow") {
    const flowType = query.get("type") || "general";
    const explicit = query.get("explicit") === "1";
    if ((flowType === "xiaoge" || flowType === "xiaoge_or_xiaoge" || flowType === "小哥" || flowType === "小鸽") && !explicit) {
      return Promise.resolve({
        allowed: false,
        gate: "小哥/小鸽心流必须明确触发后才显示专项内容。",
        items: [],
      });
    }
    return Promise.resolve({
      allowed: true,
      gate: "",
      timeline: timelinePayload("/api/flow", {
        keyword: "心流",
        explicit_flow: explicit,
        limit: Number(query.get("limit") || 30),
        date: query.get("date") || "",
        month: query.get("month") || "",
        from: query.get("from") || "",
        to: query.get("to") || "",
        trip: query.get("trip") === "1",
        status: query.get("status") || "",
        include_context: true,
      }).nodes,
    });
  }
  if (rawPath === "/api/synthesis") {
    const args = {
      date: query.get("date") || "",
      from: query.get("from") || "",
      to: query.get("to") || "",
      month: query.get("month") || "",
      phase: query.get("phase") || "",
      trip: query.get("trip") === "1",
      status: query.get("status") || "",
      limit: Math.min(Number(query.get("limit") || 500), 2000),
    };
    const data = timelinePayload("/api/synthesis", args, false);
    const summary = data.stats || {};
    return Promise.resolve({
      scope: {
        type: args.date ? "day" : (args.month ? "month" : (args.from || args.to ? "range" : (args.trip ? "trip" : (args.phase ? "phase" : "all")))),
        date: args.date,
        month: args.month,
        from: args.from,
        to: args.to,
        phase: args.phase,
        trip_only: args.trip,
        from_iso: summary.from_iso || null,
        to_iso: summary.to_iso || null,
      },
      summary: {
        ...summary,
        related_log_count: summary.related_log_count || 0,
        evidence_count: data.evidence_count || 0,
      },
      cities: data.cities || [],
      spaces: data.spaces || [],
      companions: data.companions || [],
      relation_types: data.relation_types || [],
      nodes: data.nodes || [],
    });
  }
  if (rawPath === "/api/evidence") {
    const limit = Math.min(Number(query.get("limit") || 80), 300);
    const type = query.get("type");
    const entityId = query.get("id");
    const sourceFileId = query.get("source_file_id");
    const keyword = query.get("q") || "";
    const sourceRows = getEvidence().filter((item) => {
      if (type && item.entity_type !== type) return false;
      if (entityId && item.entity_id !== entityId) return false;
      if (sourceFileId && item.source_file_id !== sourceFileId) return false;
      if (!keyword) return true;
      return [item.entity_title || "", item.entity_summary || "", item.evidence_text || "", item.source_path || "", item.source_title || ""].join(" ").includes(keyword);
    }).slice(0, limit);
    return Promise.resolve({
      items: sourceRows,
      type_counts: [],
    });
  }
  if (rawPath === "/api/source") {
    const sourceFileId = query.get("source_file_id") || "";
    if (!sourceFileId) return Promise.reject(new Error("缺少 source_file_id"));
    const source = getSourceFiles().find((item) => item.source_file_id === sourceFileId);
    if (!source) return Promise.reject(new Error("没有找到来源文件"));
    const sourceTable = getSourceDocuments().find((item) => item.source_file_id === sourceFileId);
    const document = sourceTable ? { ...sourceTable } : null;
    if (document && document.body) {
      const body = document.body || "";
      document.body = body.slice(0, 30000);
      document.truncated = body.length > 30000;
    }
    const rows = getCsvRows()
      .filter((item) => getCsvTables().some((table) => table.csv_table_id === item.csv_table_id && table.source_file_id === sourceFileId))
      .map((item) => {
        const table = getCsvTables().find((table) => table.csv_table_id === item.csv_table_id) || {};
        return { ...item, row_json: item.row_json || "{}", table_name: table.table_name || "" };
      })
      .slice(0, 120);
    const evidence = getEvidence().filter((item) => item.source_file_id === sourceFileId).slice(0, 160);
    return Promise.resolve({
      source,
      document,
      csv_rows: rows,
      csv_tables: getCsvTables().filter((item) => item.source_file_id === sourceFileId),
      evidence,
    });
  }
  if (rawPath === "/api/entities") {
    const limit = Math.min(Number(query.get("limit") || 80), 300);
    const type = query.get("type");
    const keyword = safeDateText(query.get("q") || "");
    const items = getEntities().filter((item) => {
      if (type && item.entity_type !== type) return false;
      if (keyword) {
        const text = [item.title, item.subtitle, item.domain, item.phase, item.summary, item.entity_key].join(" ");
        if (!text.includes(keyword)) return false;
      }
      return true;
    }).map((item) => ({
      entity_type: item.entity_type,
      entity_id: item.entity_id,
      id: item.entity_id,
      title: item.title,
      subtitle: item.subtitle,
      domain: item.domain,
      phase: item.phase,
      relation_count: item.relation_count,
      evidence_count: item.evidence_count,
      source_file_id: item.source_file_id,
      source_row_id: item.source_row_id,
      source_path: item.source_path,
      body: item.summary,
    })).slice(0, limit);
    return Promise.resolve({ items, type_counts: [] });
  }
  if (rawPath === "/api/entity") {
    const entityType = query.get("type");
    const entityId = query.get("id");
    if (!entityType || !entityId) return Promise.reject(new Error("缺少对象类型或对象 ID"));
    const card = getEntities().find((item) => item.entity_type === entityType && item.entity_id === entityId);
    if (!card) return Promise.reject(new Error("没有找到对象"));
    const relations = getRelations().filter((item) => (
      (item.source_type === entityType && item.source_id === entityId)
      || (item.target_type === entityType && item.target_id === entityId)
    )).map((item) => ({
      relation_id: item.relation_id,
      direction: item.source_type === entityType && item.source_id === entityId ? "outgoing" : "incoming",
      source_type: item.source_type,
      source_id: item.source_id,
      source_title: item.source_title,
      target_type: item.target_type,
      target_id: item.target_id,
      target_title: item.target_title,
      related_type: item.source_type === entityType && item.source_id === entityId ? item.target_type : item.source_type,
      related_id: item.source_type === entityType && item.source_id === entityId ? item.target_id : item.source_id,
      related_title: item.source_type === entityType && item.source_id === entityId ? item.target_title : item.source_title,
      relation_type: item.relation_type,
      domain: item.domain,
      confidence: item.confidence,
      note: item.note,
      source_file_id: item.source_file_id,
      source_row_id: item.source_row_id,
      source_path: item.source_path,
      source_anchor: item.source_anchor,
      evidence_excerpt: item.evidence_excerpt,
    }));
    const evidence = getEvidence().filter((item) => item.entity_type === entityType && item.entity_id === entityId).slice(0, 80);
    return Promise.resolve({
      card: {
        entity_key: card.entity_key,
        entity_type: card.entity_type,
        entity_id: card.entity_id,
        id: card.entity_id,
        title: card.title,
        subtitle: card.subtitle,
        domain: card.domain,
        phase: card.phase,
        date_start: card.date_start,
        date_end: card.date_end,
        summary: card.summary,
        source_file_id: card.source_file_id,
        source_row_id: card.source_row_id,
        source_path: card.source_path,
        evidence_count: card.evidence_count,
        outgoing_count: card.outgoing_count,
        incoming_count: card.incoming_count,
        relation_count: card.relation_count,
        raw_payload: card.raw_payload,
      },
      relations,
      evidence,
    });
  }
  if (rawPath === "/api/chronicle/context") {
    const keyword = safeDateText(query.get("q") || "");
    const phase = safeDateText(query.get("phase") || "");
    const targetEntity = query.get("entity") || "";
    const limit = Math.min(Number(query.get("limit") || 120), 400);
    const people = getPeople();
    const events = getEvents();
    const terms = getTerms();
    const places = getPlaces();
    const collections = getCollections();
    const spaceFinanceRecords = getSpaceFinanceRecords();
    const oralSessions = getOralSessions();
    const patterns = getPatterns();

    const normalizePhase = safeDateText(phase).toLowerCase();
    const normalizeKeyword = safeDateText(keyword).toLowerCase();
    const allPass = (item, fields) => {
      if (!normalizeKeyword) return true;
      const text = fields.map((field) => safeDateText(item[field])).join(" ").toLowerCase();
      return text.includes(normalizeKeyword);
    };
    const withPhase = (item) => {
      if (!normalizePhase) return true;
      const phaseText = [safeDateText(item.phase || item.event_date || item.period_text || item.session_date || ""), safeDateText(item.domain || "")].join(" ").toLowerCase();
      return phaseText.includes(normalizePhase);
    };

    const filterItems = (items, fields) => items.filter((item) => allPass(item, fields) && withPhase(item));

    const filtered = {
      person: filterItems(people, ["name", "aliases", "summary", "group_name", "relationship_to_owner"]),
      event: filterItems(events, ["title", "summary", "event_date"]),
      term: filterItems(terms, ["name", "definition", "trigger_words", "term_type"]),
      place: filterItems(places, ["name", "aliases", "summary", "place_type"]),
      collection: filterItems(collections, ["name", "summary", "relation_to_qingfeng"]),
      space_finance_record: filterItems(spaceFinanceRecords, ["title", "summary", "original_text", "space_name", "finance_category"]),
      oral_session: filterItems(oralSessions, ["title", "summary", "transcript_excerpt"]),
      pattern: filterItems(patterns, ["name", "definition", "trigger_words", "pattern_type"]),
    };
    const phaseStats = [];
    const phaseMap = new Map();
    [...filtered.person, ...filtered.event].forEach((item) => {
      const p = safeDateText(item.phase || item.group_name || item.event_date || "").trim();
      if (!p) return;
      phaseMap.set(p, (phaseMap.get(p) || 0) + 1);
    });
    [...phaseMap.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).forEach(([name, count]) => {
      phaseStats.push({ value: name, count });
    });

    const toSection = (entityType, title, subtitle, items, idKey, titleKey) => ({
      entity_type: entityType,
      title,
      subtitle,
      items: items.slice(0, limit).map((item) => ({
        id: item[idKey],
        entity_type: entityType,
        title: item[titleKey] || "",
        subtitle: item.event_date || item.session_date || item.period_text || item.relationship_to_owner || item.group_name || item.phase || "",
        body: item.summary || item.definition || item.transcript_excerpt || item.raw_json || "",
        source_file_id: item.source_file_id,
        source_row_id: item.source_row_id,
      })),
    });

    const entities = {
      person: {
        rows: filtered.person,
        idKey: "person_id",
        titleKey: "name",
      },
      event: {
        rows: filtered.event,
        idKey: "event_id",
        titleKey: "title",
      },
      term: {
        rows: filtered.term,
        idKey: "term_id",
        titleKey: "name",
      },
      place: {
        rows: filtered.place,
        idKey: "place_id",
        titleKey: "name",
      },
      collection: {
        rows: filtered.collection,
        idKey: "collection_id",
        titleKey: "name",
      },
      space_finance_record: {
        rows: filtered.space_finance_record,
        idKey: "record_id",
        titleKey: "title",
      },
      oral_session: {
        rows: filtered.oral_session,
        idKey: "oral_session_id",
        titleKey: "title",
      },
      pattern: {
        rows: filtered.pattern,
        idKey: "pattern_id",
        titleKey: "name",
      },
    };
    const targetList = targetEntity && entities[targetEntity] ? { [targetEntity]: entities[targetEntity] } : entities;
    const sectionOrder = ["person", "event", "term", "place", "pattern", "oral_session", "collection", "space_finance_record"];
    const sectionPayload = sectionOrder
      .filter((type) => !targetEntity || type === targetEntity)
      .map((type) => {
        const entity = entities[type];
        const section = toSection(
          type,
          ({
            person: "人物",
            event: "事件",
            term: "术语",
            place: "地点",
            pattern: "心理模式",
            oral_session: "口述",
            collection: "藏品",
            space_finance_record: "空间财务",
          })[type],
          ({
            person: "人物档案",
            event: "事件档案",
            term: "术语系统",
            place: "地点档案",
            pattern: "心理模式",
            oral_session: "口述记录",
            collection: "藏品归档",
            space_finance_record: "清风空间/财务专项",
          })[type],
          entity.rows,
          entity.idKey,
          entity.titleKey,
        );
        return section;
      });
    return Promise.resolve({
      query: {
        q: keyword,
        phase,
        entity: targetEntity,
      },
      summary: {
        people: filtered.person.length,
        events: filtered.event.length,
        terms: filtered.term.length,
        places: filtered.place.length,
        patterns: filtered.pattern.length,
        oral_sessions: filtered.oral_session.length,
        collections: filtered.collection.length,
        space_finance_records: filtered.space_finance_record.length,
        total_objects: sectionPayload.reduce((sum, section) => sum + section.items.length, 0),
      },
      phase_stats: phaseStats,
      people: filtered.person.slice(0, limit),
      events: filtered.event.slice(0, limit),
      terms: filtered.term.slice(0, limit),
      places: filtered.place.slice(0, limit),
      patterns: filtered.pattern.slice(0, limit),
      oral_sessions: filtered.oral_session.slice(0, limit),
      collections: filtered.collection.slice(0, limit),
      space_finance_records: filtered.space_finance_record.slice(0, limit),
      items: sectionPayload,
      meta: {
        sections: sectionOrder,
        entity: targetEntity,
      },
    });
  }
  return Promise.reject(new Error(`离线模式暂不支持接口: ${rawPath}`));
}

function api(path, options = {}) {
  if (OFFLINE_MODE) {
    return offlineApi(path, options);
  }
  const init = {
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  return fetch(path, init).then(async (response) => {
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "请求失败");
    }
    return data;
  });
}

function tag(text, tone = "") {
  if (!text) return "";
  return `<span class="tag ${tone}">${escapeHtml(text)}</span>`;
}

function metric(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function countBy(items, key) {
  return ensureArray(items).reduce((acc, item) => {
    const value = String(item?.[key] || "未标记");
    acc[value] = (acc[value] || 0) + 1;
    return acc;
  }, {});
}

function mapToRecords(map, labels = {}) {
  return Object.entries(map || {})
    .sort((a, b) => Number(b[1]) - Number(a[1]) || String(a[0]).localeCompare(String(b[0])))
    .map(([key, value]) => renderRecord({
      title: labels[key] || key,
      type: `${value} 条`,
      body: "",
    }))
    .join("") || `<div class="empty">暂无数据</div>`;
}

function setView(view, skipLoad = false) {
  state.view = view;
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  document.querySelectorAll(".view").forEach((el) => el.classList.remove("active"));
  $(`view-${view}`)?.classList.add("active");
  $("viewTitle").textContent = titles[view] || "数字生命 OS";
  if (!skipLoad) loadView(view);
}

async function loadStatus() {
  const data = await api("/api/status");
  state.status = data;
  const c = data.counts;
  $("systemState").innerHTML = [
    `底库 ${c.source_documents} 文档`,
    `时空轴 ${c.timeline_nodes} 节点`,
    `清风日志 ${c.qingfeng_logs} 条`,
    `草稿 ${c.log_drafts} 条`,
  ].join("<br>");
  $("statusSummary").innerHTML = [
    metric("时空轴", c.timeline_index),
    metric("清风日志", c.qingfeng_logs),
    metric("清风上下文", c.qingfeng_context),
    metric("规则条目", c.rules),
    metric("规则源", c.rule_sources),
    metric("规则约束", c.rule_constraints),
    metric("人物", c.people),
    metric("事件", c.events),
    metric("术语", c.terms),
    metric("空间财务", c.space_finance_records ?? 0),
    metric("原文证据", c.evidence),
    metric("证据等级", c.evidence_grade_index ?? 0),
    metric("时空统计", c.timeline_analytics_cache ?? 0),
    metric("入库队列", c.intake_queue ?? 0),
    metric("媒体附件", c.media_assets ?? 0),
    metric("关系", c.relation_index),
  ].join("");
}

function timelineQueryString() {
  const params = new URLSearchParams();
  const date = $("timelineDate").value;
  const month = $("timelineMonth").value;
  const keyword = $("timelineKeyword").value.trim();
  const phase = $("timelinePhase").value.trim();
  if (date) params.set("date", date);
  if (!date && month) params.set("month", month);
  if (keyword) params.set("keyword", keyword);
  if (phase) params.set("phase", phase);
  if ($("timelineTrip").checked) params.set("trip", "1");
  params.set("limit", "120");
  return params.toString();
}

async function loadTimeline() {
  const data = await api(`/api/timeline?${timelineQueryString()}`);
  state.timeline = data;
  state.selectedNode = data.nodes[0] || null;
  renderTimeline(data);
}

function renderTimeline(data) {
  const stats = data.stats;
  $("timelineCount").textContent = `${stats.node_count} 个主节点`;
  $("timelineRange").textContent = stats.from_iso ? `${stats.from_iso} 至 ${stats.to_iso}` : "";
  $("timelineNodes").innerHTML = data.nodes.length
    ? data.nodes.map((node) => renderNodeItem(node, node.id === state.selectedNode?.id)).join("")
    : `<div class="empty">没有节点</div>`;
  renderTimelineDetail(state.selectedNode);
  renderContextNodes(data.context_nodes || []);
  document.querySelectorAll(".node-item").forEach((el) => {
    el.addEventListener("click", () => {
      state.selectedNode = data.nodes.find((node) => node.id === el.dataset.id);
      renderTimeline(data);
    });
  });
}

function chronicleQueryString() {
  const params = new URLSearchParams();
  const q = $("chronicleKeyword").value.trim();
  const phase = $("chroniclePhase").value.trim();
  const entity = $("chronicleEntity").value;
  if (q) params.set("q", q);
  if (phase) params.set("phase", phase);
  if (entity) params.set("entity", entity);
  params.set("limit", "140");
  return params.toString();
}

function renderChronicleSection(section) {
  const sectionItems = section.items || [];
  const typeLabelMap = {
    person: "人物",
    event: "事件",
    term: "术语",
    place: "地点",
    pattern: "心理模式",
    oral_session: "口述",
    collection: "藏品",
  };
  return `
    <section class="source-block">
      <h4>${escapeHtml(section.title || typeLabelMap[section.entity_type] || section.entity_type || "对象")}</h4>
      <div class="record-meta">${tag(section.subtitle || "")}</div>
      <div class="record-list">
        ${sectionItems.length ? sectionItems.map((item) => renderRecord(item)).join("") : `<div class="empty">暂无${typeLabelMap[section.entity_type] || ""}</div>`}
      </div>
    </section>
  `;
}

async function loadChronicle() {
  const params = chronicleQueryString();
  const data = await api(`/api/chronicle/context?${params}`);
  state.chronicle = data;
  const summary = data.summary || {};
  $("chronicleSummary").innerHTML = [
    metric("人物", summary.people ?? 0),
    metric("事件", summary.events ?? 0),
    metric("术语", summary.terms ?? 0),
    metric("地点", summary.places ?? 0),
    metric("心理模式", summary.patterns ?? 0),
    metric("口述", summary.oral_sessions ?? 0),
    metric("藏品", summary.collections ?? 0),
    metric("空间财务", summary.space_finance_records ?? 0),
    metric("总计", summary.total_objects ?? 0),
  ].join("");
  const items = ensureArray(data.items || []);
  $("chronicleSummaryMeta").textContent = `${items.length} 类模块`;
  $("chroniclePanels").innerHTML = items
    .filter((section) => (data.meta?.entity ? section.entity_type === data.meta.entity : true))
    .map((section) => renderChronicleSection(section))
    .join("");
}

function renderNodeItem(node, active) {
  const range = node.date_range.from === node.date_range.to
    ? node.date_range.from
    : `${node.date_range.from} - ${node.date_range.to}`;
  const tones = [
    node.is_trip ? tag("外出", "blue") : "",
    node.has_flow_marker ? tag("心流标记", "red") : "",
    node.record_status ? tag(node.record_status, "green") : "",
  ].join("");
  return `
    <article class="node-item ${active ? "active" : ""}" data-id="${escapeHtml(node.id)}">
      <h4>${escapeHtml(node.title)}</h4>
      <div class="node-meta">${tag(range)}${tag(node.main_space || "未定空间")}${tones}</div>
    </article>
  `;
}

function renderTimelineDetail(node) {
  if (!node) {
    $("timelineDetail").innerHTML = `<div class="empty">没有选中节点</div>`;
    return;
  }
  const people = (node.companions || []).map((name) => tag(name)).join("");
  const cities = (node.cities || []).map((name) => tag(name, "blue")).join("");
  $("timelineDetail").innerHTML = `
    <h3 class="detail-title">${escapeHtml(node.title)}</h3>
    <div class="tag-row">
      ${tag(node.date_range.from === node.date_range.to ? node.date_range.from : `${node.date_range.from} - ${node.date_range.to}`, "green")}
      ${node.is_trip ? tag("外出段", "blue") : ""}
      ${node.has_flow_marker ? tag("受控心流标记", "red") : ""}
      ${tag(node.record_status || "")}
    </div>
    <div class="action-row compact-actions">
      <button class="text-button entity-link" data-entity-type="timeline_node" data-entity-id="${escapeHtml(node.id)}">对象详情</button>
      ${node.source_file_id ? `<button class="text-button evidence-link" data-source-file-id="${escapeHtml(node.source_file_id)}" data-source-row-id="${escapeHtml(node.source_row_id || "")}" data-entity-type="timeline_node" data-entity-id="${escapeHtml(node.id)}">查看原文证据</button>` : ""}
    </div>
    <div class="detail-grid">
      <div class="detail-cell"><span>主要空间</span><strong>${escapeHtml(node.main_space || "未定")}</strong></div>
      <div class="detail-cell"><span>具体地点</span><strong>${escapeHtml(node.specific_place || "未定")}</strong></div>
      <div class="detail-cell"><span>关联日志</span><strong>${escapeHtml(node.relation_counts?.logs ?? 0)}</strong></div>
      <div class="detail-cell"><span>关联事件</span><strong>${escapeHtml(node.relation_counts?.events ?? 0)}</strong></div>
    </div>
    <div class="detail-cell"><span>城市 / 地点</span><div class="tag-row">${cities || tag("未定")}</div></div>
    <div class="detail-cell"><span>同行人物</span><div class="tag-row">${people || tag("未定")}</div></div>
    <p class="detail-summary">${escapeHtml(node.summary || "")}</p>
  `;
}

function renderContextNodes(nodes) {
  $("contextNodes").innerHTML = nodes.length
    ? nodes.map((node) => `<div class="record-item"><h4>${escapeHtml(node.title)}</h4><div class="record-meta">${tag("背景")}${tag(node.date_range.from)}${tag(node.main_space)}</div></div>`).join("")
    : `<div class="empty">无背景节点</div>`;
}

async function runSearch() {
  const q = $("searchInput").value.trim();
  const data = await api(`/api/search?q=${encodeURIComponent(q)}&limit=80`);
  $("searchCount").textContent = `${data.results.length} 条`;
  $("searchResults").innerHTML = data.results.map(renderRecord).join("") || `<div class="empty">没有结果</div>`;
}

function synthesisQueryString() {
  const params = new URLSearchParams();
  const from = $("synthesisFrom").value;
  const to = $("synthesisTo").value;
  const month = $("synthesisMonth").value;
  const phase = $("synthesisPhase").value.trim();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (month) params.set("month", month);
  if (phase) params.set("phase", phase);
  if ($("synthesisTrip").checked) params.set("trip", "1");
  params.set("limit", "320");
  return params.toString();
}

function getSynthesisFilename(prefix) {
  const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  return `${prefix}_${today}`;
}

function formatSynthesisMarkdown(snapshot) {
  const data = snapshot?.data || snapshot || {};
  const summary = data.summary || {};
  const scope = data.scope || {};
  const stageSummary = snapshot?.stage?.summary || {};
  const title = `# 阶段归纳快照`;
  const lines = [
    title,
    "",
    `- 生成时间：${snapshot.generatedAt || new Date().toLocaleString()}`,
    `- 范围类型：${scope.type || "all"}`,
    `- 日期范围：${scope.from_iso || ""} ~ ${scope.to_iso || ""}`,
    `- 阶段关键词：${scope.phase || ""}`,
    `- 外出段：${scope.trip_only ? "是" : "否"}`,
    `- 月份：${scope.month || ""}`,
    "",
    "## 核心指标",
    `- 节点：${summary.node_count ?? 0}`,
    `- 覆盖天数：${summary.day_count ?? 0}`,
    `- 外出节点：${summary.trip_node_count ?? 0}`,
    `- 待补项：${summary.pending_node_count ?? 0}`,
    `- 心流标记：${summary.flow_marker_node_count ?? 0}`,
    `- 关联日志：${summary.related_log_count ?? 0}`,
    `- 原文证据：${summary.evidence_count ?? 0}`,
    "",
    "## 统计分布",
    `- 城市数：${summary.city_count ?? 0}`,
    `- 空间数：${summary.space_count ?? 0}`,
    `- 同行人数：${summary.companion_count ?? 0}`,
    `- 缺失证据源：${summary.missing_source_count ?? 0}`,
    "",
    `## 城市 Top`,
    ...(data.cities || []).map((item) => `- ${item.name}（${item.count}）`),
    "",
    `## 同行人物 Top`,
    ...(data.companions || []).map((item) => `- ${item.name}（${item.count}）`),
    "",
    `## 空间 Top`,
    ...(data.spaces || []).map((item) => `- ${item.name}（${item.count}）`),
    "",
    `## 关系类型 Top`,
    ...(data.relation_types || []).map((item) => `- ${item.relation_type}（${item.count}）`),
    "",
    "## 阶段快照",
    `- 阶段快照：${stageSummary.item_count ?? 0}`,
    `- 异常阶段：${stageSummary.anomaly_count ?? 0}`,
    `- 阶段节点总计：${stageSummary.filtered_node_count ?? 0}`,
    `- 阶段天数总计：${stageSummary.filtered_day_count ?? 0}`,
    "",
    "## 节点清单",
    ...((data.nodes || []).map((node) => `- ${node.title} | ${node.date_range?.from || ""} ~ ${node.date_range?.to || ""} | ${node.main_space || ""} | ${node.is_trip ? "外出" : "常规"}`)),
  ];
  return lines.join("\n");
}

function downloadText(filename, content, mimeType) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);
}

function getSynthesisSnapshotFilename(format) {
  const scopeFrom = state.synthesis?.data?.scope?.from_iso || "all";
  const scopeTo = state.synthesis?.data?.scope?.to_iso || "all";
  const suffix = `${scopeFrom}_to_${scopeTo}`.replace(/[^0-9_]/g, "");
  const stamp = getSynthesisFilename("阶段归纳快照");
  return `${stamp}_${suffix}.${format}`;
}

function renderRankList(items) {
  return items.length
    ? items.map((item) => `
      <article class="record-item">
        <h4>${escapeHtml(item.name || "未命名")}</h4>
        <div class="record-meta">${tag(`数量 ${item.count}`, "green")}</div>
      </article>
    `).join("")
    : `<div class="empty">暂无汇总项</div>`;
}

function renderSynthesisNodes(nodes) {
  return nodes.length
    ? nodes.map((node) => `
      <article class="record-item">
        <h4>${escapeHtml(node.title)}</h4>
        <div class="record-meta">
          ${tag(node.date_range.from === node.date_range.to ? node.date_range.from : `${node.date_range.from} - ${node.date_range.to}`)}
          ${tag(node.main_space || "未定空间")}
          ${tag(node.record_status || "")}
          ${node.is_trip ? tag("外出段", "blue") : ""}
          ${node.has_flow_marker ? tag("心流标记", "red") : ""}
          <button class="text-button entity-link" data-entity-type="timeline_node" data-entity-id="${escapeHtml(node.id)}">查看</button>
        </div>
      </article>
    `).join("")
    : `<div class="empty">没有相关节点</div>`;
}

function renderSynthesisSegments(segments) {
  return segments.length
    ? segments.map((segment) => `
      <article class="record-item">
        <h4>${escapeHtml(segment.label || "未命名阶段")}</h4>
        <div class="record-meta">
          ${tag(segment.from_iso || "", "green")}
          ${tag(segment.to_iso || "", "green")}
          ${tag(`节点 ${segment.node_count || 0}`)}
          ${tag(`日志 ${segment.related_log_count || 0}`)}
          ${segment.trip_count ? tag(`外出 ${segment.trip_count}`, "blue") : ""}
          ${segment.anomalies?.length ? tag(`异常 ${segment.anomalies.length}`, "red") : ""}
          <button class="text-button segment-apply" data-from="${escapeHtml(segment.from_iso || "")}" data-to="${escapeHtml(segment.to_iso || "")}" data-phase="${escapeHtml(segment.label || "")}">聚焦阶段</button>
        </div>
        <p>${escapeHtml(segment.main_spaces?.slice(0, 3).join(" / ") || "未设置主要空间")}</p>
      </article>
    `).join("")
    : `<div class="empty">暂无阶段快照</div>`;
}

function buildSynthesisStageAnomalyText(summary) {
  return `
    <div class="detail-grid">
      <div class="detail-cell"><span>阶段总数</span><strong>${summary.item_count || 0}</strong></div>
      <div class="detail-cell"><span>异常阶段</span><strong>${summary.anomaly_count || 0}</strong></div>
      <div class="detail-cell"><span>节点总计</span><strong>${summary.filtered_node_count || 0}</strong></div>
      <div class="detail-cell"><span>天数总计</span><strong>${summary.filtered_day_count || 0}</strong></div>
    </div>
    <p>异常率：${summary.anomaly_ratio ? `${(summary.anomaly_ratio * 100).toFixed(1)}%` : "0%"}</p>
  `;
}

async function runSynthesis() {
  const query = synthesisQueryString();
  const segmentQuery = new URLSearchParams(query);
  segmentQuery.set("segment_type", "stage");
  segmentQuery.set("limit", "120");
  const [data, stagePayload] = await Promise.all([
    api(`/api/synthesis?${query}`),
    api(`/api/timeline/segments?${segmentQuery}`),
  ]);
  const stages = stagePayload.items || [];
  const stageSummary = stagePayload.summary || {};
  state.synthesis = {
    query,
    data,
    stage: stagePayload,
    generatedAt: new Date().toLocaleString(),
  };
  const summary = data.summary || {};
  $("synthesisOverview").innerHTML = [
    metric("节点", summary.node_count ?? 0),
    metric("覆盖天数", summary.day_count ?? 0),
    metric("外出节点", summary.trip_node_count ?? 0),
    metric("待补项", summary.pending_node_count ?? 0),
    metric("心流标记", summary.flow_marker_node_count ?? 0),
    metric("关联日志", summary.related_log_count ?? 0),
    metric("原文证据", summary.evidence_count ?? 0),
  ].join("");
  $("synthesisStageCount").textContent = `${(stageSummary.item_count || 0)} 个阶段快照`;
  $("synthesisStageRange").textContent = `异常 ${stageSummary.anomaly_count || 0} / ${stageSummary.item_count || 0} 阶段`;
  $("synthesisStages").innerHTML = renderSynthesisSegments(stages);
  $("synthesisStageAnomalies").innerHTML = buildSynthesisStageAnomalyText({
    ...stageSummary,
    anomaly_ratio: stageSummary.item_count ? (stageSummary.anomaly_count || 0) / stageSummary.item_count : 0,
  });
  $("synthesisRange").textContent = data.scope?.from_iso && data.scope?.to_iso
    ? `${data.scope.from_iso} 至 ${data.scope.to_iso}`
    : "";
  $("synthesisNodeCount").textContent = `${(summary.node_count ?? 0)} 个`;
  const scopeText = [
    data.scope?.type ? `范围：${data.scope.type}` : "",
    data.scope?.trip_only ? "外出段" : "",
    data.scope?.phase ? `阶段：${data.scope.phase}` : "",
    data.scope?.month ? `月份：${data.scope.month}` : "",
  ].filter(Boolean).join(" / ");
  $("synthesisDetail").innerHTML = `
    <div class="detail-grid">
      <div class="detail-cell"><span>城市数</span><strong>${summary.city_count ?? 0}</strong></div>
      <div class="detail-cell"><span>空间数</span><strong>${summary.space_count ?? 0}</strong></div>
      <div class="detail-cell"><span>同伴数</span><strong>${summary.companion_count ?? 0}</strong></div>
      <div class="detail-cell"><span>缺证据源</span><strong>${summary.missing_source_count ?? 0}</strong></div>
    </div>
    <p>${scopeText || "无额外筛选条件"}</p>
  `;
  $("synthesisNodes").innerHTML = renderSynthesisNodes(data.nodes || []);
  $("synthesisCities").innerHTML = renderRankList(data.cities || []);
  $("synthesisCompanions").innerHTML = renderRankList(data.companions || []);
  $("synthesisSpaces").innerHTML = renderRankList(data.spaces || []);
  $("synthesisRelations").innerHTML = data.relation_types?.length
    ? data.relation_types.map((item) => `
      <article class="record-item">
        <h4>${escapeHtml(item.relation_type || "未命名")}</h4>
        <div class="record-meta">${tag(`数量 ${item.count}`, "blue")}</div>
      </article>
    `).join("")
    : `<div class="empty">暂无关系类型数据</div>`;
}

async function exportSynthesis(format) {
  if (!state.synthesis) {
    await runSynthesis();
  }
  if (!state.synthesis) return;
  const payload = state.synthesis;
  if (format === "json") {
    downloadText(
      getSynthesisSnapshotFilename("json"),
      JSON.stringify(payload, null, 2),
      "application/json",
    );
  } else {
    downloadText(
      getSynthesisSnapshotFilename("md"),
      formatSynthesisMarkdown(payload),
      "text/markdown",
    );
  }
}

function renderRecord(item) {
  const aiSummary = normalizeAiResponse(item.ai_response);
  const detailAction = item.entity_type && (item.id || item.entity_id)
    ? `<button class="text-button entity-link" data-entity-type="${escapeHtml(item.entity_type)}" data-entity-id="${escapeHtml(item.id || item.entity_id)}">详情</button>`
    : "";
  const evidenceAction = item.source_file_id
    ? `<button class="text-button evidence-link" data-source-file-id="${escapeHtml(item.source_file_id)}" data-source-row-id="${escapeHtml(item.source_row_id || "")}" data-entity-type="${escapeHtml(item.entity_type || item.type || "")}" data-entity-id="${escapeHtml(item.id || item.entity_id || "")}">证据</button>`
    : "";
  return `
    <article class="record-item">
      <h4>${escapeHtml(item.title || item.name || "无标题")}</h4>
      <div class="record-meta">${tag(item.type || item.subtitle || "")}${item.subtitle ? tag(item.subtitle) : ""}${detailAction}${evidenceAction}</div>
      <p>${escapeHtml(compact(item.body || item.summary || item.definition || "", 260))}</p>
      ${aiSummary ? `<div class="record-meta">${tag("AI点评")}</div><p>${escapeHtml(compact(aiSummary, 360))}</p>` : ""}
    </article>
  `;
}

function renderEvidenceItem(item) {
  return `
    <article class="record-item evidence-item" data-source-file-id="${escapeHtml(item.source_file_id || "")}">
      <h4>${escapeHtml(item.entity_title || "无标题")}</h4>
      <div class="record-meta">
        ${tag(item.entity_type)}
        ${tag(item.source_kind, "blue")}
        ${item.source_anchor ? tag(item.source_anchor, "green") : ""}
        ${item.source_file_id ? `<button class="text-button evidence-link" data-source-file-id="${escapeHtml(item.source_file_id)}" data-source-row-id="${escapeHtml(item.source_row_id || "")}" data-entity-type="${escapeHtml(item.entity_type)}" data-entity-id="${escapeHtml(item.entity_id)}">来源</button>` : ""}
      </div>
      <p>${escapeHtml(item.evidence_excerpt || "")}</p>
      <div class="source-path">${escapeHtml(item.source_path || item.source_title || "")}</div>
    </article>
  `;
}

function parseJsonDisplay(value) {
  try {
    const data = JSON.parse(value || "{}");
    return Object.entries(data)
      .filter(([, item]) => item !== null && item !== "")
      .map(([key, item]) => `<div><strong>${escapeHtml(key)}：</strong>${escapeHtml(item)}</div>`)
      .join("");
  } catch (error) {
    return `<pre>${escapeHtml(value || "")}</pre>`;
  }
}

function typeLabel(value) {
  const labels = {
    timeline_node: "时空轴",
    qingfeng_log: "日志",
    person: "人物",
    event: "事件",
    term: "术语",
    place: "地点",
    collection: "藏品",
    oral_session: "口述",
    pattern: "心理模式",
    qingfeng_space: "清风空间",
    qingfeng_context: "清风上下文",
    collection: "藏品",
    oral_session: "口述",
    psychological_pattern: "心理模式",
    rule_source: "规则源",
  };
  return labels[value] || value || "";
}

function relationLabel(value) {
  const labels = {
    companion: "同行",
    belongs_to_timeline: "归属时空轴",
    related_oral: "关联口述",
    mentions_person: "提及人物",
    located_in: "位于",
  };
  return labels[value] || value || "";
}

async function runEvidenceSearch() {
  const q = $("evidenceInput").value.trim();
  const data = await api(`/api/evidence?q=${encodeURIComponent(q)}&limit=120`);
  $("evidenceCount").textContent = `${data.items.length} 条`;
  $("evidenceResults").innerHTML = data.items.map(renderEvidenceItem).join("") || `<div class="empty">没有证据</div>`;
  const firstSource = data.items.find((item) => item.source_file_id)?.source_file_id;
  if (firstSource) loadSource(firstSource);
}

async function loadEntityEvidence(entityType, entityId, sourceFileId) {
  const params = new URLSearchParams();
  if (entityType) params.set("type", entityType);
  if (entityId) params.set("id", entityId);
  if (!entityType && sourceFileId) params.set("source_file_id", sourceFileId);
  params.set("limit", "120");
  const data = await api(`/api/evidence?${params.toString()}`);
  $("evidenceCount").textContent = `${data.items.length} 条`;
  $("evidenceResults").innerHTML = data.items.map(renderEvidenceItem).join("") || `<div class="empty">没有证据</div>`;
}

async function loadSource(sourceFileId) {
  if (!sourceFileId) return;
  const data = await api(`/api/source?source_file_id=${encodeURIComponent(sourceFileId)}`);
  const source = data.source;
  $("sourceMeta").textContent = source.file_name || "";
  const documentBlock = data.document
    ? `
      <section class="source-block">
        <h4>${escapeHtml(data.document.title || source.file_name)}</h4>
        <p>${escapeHtml(data.document.body_excerpt || compact(data.document.body || "", 800))}</p>
      </section>
    `
    : "";
  const tableBlock = data.csv_rows.length
    ? `
      <section class="source-block">
        <h4>表格行</h4>
        <div class="csv-row-list">
          ${data.csv_rows.slice(0, 12).map((row) => `
            <div class="csv-row">
              <div class="record-meta">${tag(row.table_name)}${tag(row.source_anchor || `第 ${row.row_index} 行`)}</div>
              ${parseJsonDisplay(row.row_json)}
            </div>
          `).join("")}
        </div>
      </section>
    `
    : "";
  const linkedBlock = data.evidence.length
    ? `
      <section class="source-block">
        <h4>关联对象</h4>
        ${data.evidence.slice(0, 30).map((item) => `
          <div class="linked-evidence">
            <strong>${escapeHtml(item.entity_title || "无标题")}</strong>
            <span>${escapeHtml(item.entity_type)}</span>
          </div>
        `).join("")}
      </section>
    `
    : "";
  $("sourceDetail").innerHTML = `
    <section class="source-block">
      <h4>${escapeHtml(source.file_name)}</h4>
      <div class="source-path">${escapeHtml(source.relative_path)}</div>
      <div class="tag-row">${tag(source.extension)}${tag(source.source_role)}${tag(source.import_status, "green")}</div>
    </section>
    ${documentBlock}
    ${tableBlock}
    ${linkedBlock}
  `;
}

async function runEntitySearch() {
  const q = $("entityInput").value.trim();
  const type = $("entityType").value;
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (type) params.set("type", type);
  params.set("limit", "120");
  const data = await api(`/api/entities?${params.toString()}`);
  $("entityCount").textContent = `${data.items.length} 个`;
  $("entityResults").innerHTML = data.items.map(renderEntityItem).join("") || `<div class="empty">没有对象</div>`;
  const first = data.items[0];
  if (first) loadEntityDetail(first.entity_type, first.id);
}

function renderEntityItem(item) {
  return `
    <article class="record-item entity-card">
      <h4>${escapeHtml(item.title || "无标题")}</h4>
      <div class="record-meta">
        ${tag(typeLabel(item.entity_type))}
        ${item.subtitle ? tag(item.subtitle, "blue") : ""}
        ${tag(`关系 ${item.relation_count}`)}
        ${tag(`证据 ${item.evidence_count}`, "green")}
        <button class="text-button entity-link" data-entity-type="${escapeHtml(item.entity_type)}" data-entity-id="${escapeHtml(item.id)}">打开</button>
        ${item.source_file_id ? `<button class="text-button evidence-link" data-source-file-id="${escapeHtml(item.source_file_id)}" data-source-row-id="${escapeHtml(item.source_row_id || "")}" data-entity-type="${escapeHtml(item.entity_type)}" data-entity-id="${escapeHtml(item.id)}">证据</button>` : ""}
      </div>
      <p>${escapeHtml(compact(item.summary || "", 220))}</p>
    </article>
  `;
}

async function loadEntityDetail(entityType, entityId) {
  if (!entityType || !entityId) return;
  const data = await api(`/api/entity?type=${encodeURIComponent(entityType)}&id=${encodeURIComponent(entityId)}`);
  renderEntityDetail(data);
}

function renderEntityDetail(data) {
  const card = data.card;
  $("entityMeta").textContent = `${typeLabel(card.entity_type)} · ${card.relation_count} 关系`;
  const relationGroups = data.relations.reduce((acc, item) => {
    const key = item.direction === "outgoing" ? "向外关系" : "向内关系";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
  const relationHtml = Object.entries(relationGroups).map(([title, items]) => `
    <section class="source-block">
      <h4>${escapeHtml(title)}</h4>
      ${items.slice(0, 80).map((item) => `
        <div class="relation-row">
          <div>
            <strong>${escapeHtml(item.related_title || item.related_id)}</strong>
            <div class="record-meta">${tag(typeLabel(item.related_type))}${tag(relationLabel(item.relation_type), "blue")}${tag(String(item.confidence), "green")}</div>
            ${item.note ? `<p>${escapeHtml(item.note)}</p>` : ""}
          </div>
          <button class="text-button entity-link" data-entity-type="${escapeHtml(item.related_type)}" data-entity-id="${escapeHtml(item.related_id)}">打开</button>
        </div>
      `).join("")}
    </section>
  `).join("");
  const evidenceHtml = data.evidence.length
    ? `
      <section class="source-block">
        <h4>原文证据</h4>
        ${data.evidence.slice(0, 20).map((item) => `
          <div class="evidence-row">
            <div class="record-meta">${tag(item.source_kind)}${item.source_anchor ? tag(item.source_anchor, "green") : ""}</div>
            <p>${escapeHtml(item.evidence_excerpt || "")}</p>
            <div class="source-path">${escapeHtml(item.source_path || "")}</div>
          </div>
        `).join("")}
      </section>
    `
    : "";
  $("entityDetail").innerHTML = `
    <section class="source-block">
      <h4>${escapeHtml(card.title)}</h4>
      <div class="tag-row">
        ${tag(typeLabel(card.entity_type))}
        ${card.subtitle ? tag(card.subtitle, "blue") : ""}
        ${card.domain ? tag(card.domain) : ""}
        ${card.phase ? tag(card.phase, "green") : ""}
      </div>
      <p>${escapeHtml(card.summary || "")}</p>
      <div class="source-path">${escapeHtml(card.source_path || "")}</div>
      <div class="action-row compact-actions">
        ${card.source_file_id ? `<button class="text-button evidence-link" data-source-file-id="${escapeHtml(card.source_file_id)}" data-source-row-id="${escapeHtml(card.source_row_id || "")}" data-entity-type="${escapeHtml(card.entity_type)}" data-entity-id="${escapeHtml(card.id)}">查看来源</button>` : ""}
      </div>
    </section>
    ${relationHtml || `<section class="source-block"><h4>关系</h4><p>暂无关系</p></section>`}
    ${evidenceHtml}
  `;
}

async function loadQingfeng() {
  const data = await api("/api/qingfeng/context");
  $("contextCount").textContent = `${data.items.length} 条`;
  $("spaceCount").textContent = `${data.spaces.length} 处`;
  $("contextItems").innerHTML = data.items.map((item) => renderRecord({
    id: item.context_item_id,
    entity_type: "qingfeng_context",
    title: item.title,
    type: item.context_type,
    body: item.summary,
    source_file_id: item.source_file_id,
    source_row_id: item.source_row_id,
  })).join("");
  $("spaceItems").innerHTML = data.spaces.map((item) => renderRecord({
    id: item.space_id,
    entity_type: "qingfeng_space",
    title: item.name,
    type: item.space_level,
    subtitle: item.physical_location,
    body: item.status_text || item.aliases,
    source_file_id: item.source_file_id,
    source_row_id: item.source_row_id,
  })).join("");
}

async function loadRules() {
  const data = await api("/api/rules");
  $("ruleSourceCount").textContent = `${data.sources.length} 个`;
  $("ruleCount").textContent = `${(data.rules || []).length} 条`;
  $("triggerCount").textContent = `${data.triggers.length} 条`;
  $("constraintCount").textContent = `${(data.constraints || []).length} 条`;
  $("ruleSources").innerHTML = data.sources.map((item) => renderRecord({
    id: item.rule_source_id,
    entity_type: "rule_source",
    title: item.title,
    type: `权威 ${item.authority_level}`,
    subtitle: item.active_status,
    body: item.source_path,
    source_file_id: item.source_file_id,
  })).join("");
  $("triggers").innerHTML = data.triggers.map((item) => renderRecord({
    title: item.normalized_trigger,
    type: item.action_type,
    subtitle: item.target_domain,
    body: item.explicit_required ? "显式触发" : "普通入口",
  })).join("");
  $("rules").innerHTML = (data.rules || []).map((item) => renderRecord({
    id: item.rule_id,
    entity_type: "",
    title: item.title || item.rule_type,
    type: item.rule_type || "",
    subtitle: item.applies_to_domain || item.priority || "",
    body: [
      item.body || "",
      item.trigger_words ? `触发词：${item.trigger_words}` : "",
      item.prohibitions ? `禁令：${item.prohibitions}` : "",
      item.receipt_requirements ? `回执要求：${item.receipt_requirements}` : "",
    ].filter(Boolean).join("\n"),
    source_file_id: item.source_file_id,
    source_row_id: item.source_row_id,
  })).join("");
  $("constraints").innerHTML = (data.constraints || []).map((item, index) => renderRecord({
    id: `${item.constraint_type || "constraint"}_${index}`,
    entity_type: "",
    title: item.constraint_type || "约束",
    type: item.target_domain || item.domain || "",
    subtitle: item.severity || item.priority || "",
    body: item.summary || item.title || item.body || "",
    source_file_id: item.source_file_id,
    source_row_id: item.source_row_id,
  })).join("");
}

async function loadList(kind, elementId, endpoint) {
  const data = await api(endpoint);
  if (data && data.allowed === false) {
    $(elementId).innerHTML = `<div class=\"record-item\"><h4>门禁</h4><p>${escapeHtml(data.gate || "未通过门禁")}</p></div>`;
    return;
  }
  $(elementId).innerHTML = data.items.map((item) => renderRecord({
    id: item.id,
    entity_type: item.entity_type,
    title: item.title,
    type: item.subtitle || item.status || "",
    subtitle: item.flow_type || "",
    body: item.body,
    ai_response: item.ai_response,
    source_file_id: item.source_file_id,
    source_row_id: item.source_row_id,
  })).join("") || `<div class="empty">暂无记录</div>`;
}

function setLogScope(scope) {
  state.logScope = scope === "restricted" ? "restricted" : "general";
  const isGeneral = state.logScope === "general";
  if ($("generalLogScope")) {
    $("generalLogScope").textContent = isGeneral ? "当前模式" : "查看通用";
  }
  if ($("xiaogeLogScope")) {
    $("xiaogeLogScope").textContent = isGeneral ? "显式进入" : "当前模式";
  }
}

async function loadLogLibrary() {
  const isRestricted = state.logScope === "restricted";
  const scope = isRestricted ? "xiaoge" : "general";
  const endpoint = `/api/logs?flow_scope=${scope}&explicit=${isRestricted ? "1" : "0"}&limit=160`;
  await loadList("logs", "logList", endpoint);
}

async function previewLog() {
  const text = $("logText").value.trim();
  if (!text) return;
  $("draftState").textContent = "生成中";
  const date = $("logDate").value || "";
  $("logDraftNote").textContent = "";
  $("exportLogJson").disabled = true;
  $("exportLogMd").disabled = true;
  try {
    const data = await api("/api/logs/preview", {
      method: "POST",
      body: JSON.stringify({ text, date: date || undefined, save: true }),
    });
    state.preview = data;
    state.selectedTimelineNodeId = data.candidate_timeline_nodes?.[0]?.timeline_node_id || "";
    $("draftState").textContent = "预览已生成";
    $("previewMeta").textContent = data.inferred_date_raw || "";
    $("confirmLog").disabled = !state.selectedTimelineNodeId;
    $("exportLogJson").disabled = !state.preview;
    $("exportLogMd").disabled = !state.preview;
    $("logDraftNote").textContent = "草稿已生成，可导出 JSON/Markdown；静态版仅支持写入草稿，正式写入请到本地服务。";
    renderPreview(data);
  } catch (error) {
    $("draftState").textContent = error.message || "生成失败";
    $("logDraftNote").textContent = "预览失败，无法导出草稿。";
  }
}

function renderPreview(data) {
  const people = (data.related_people || []).map((item) => tag(`${item.matched_alias}→${item.canonical_name}`)).join("");
  const spaces = (data.related_spaces || []).map((item) => tag(item.name, "blue")).join("");
  const candidates = (data.candidate_timeline_nodes || []).map((node, index) => `
    <div class="candidate ${index === 0 ? "selected" : ""}" data-id="${escapeHtml(node.timeline_node_id)}">
      <strong>${escapeHtml(node.title)}</strong>
      <div class="record-meta">${tag(node.date_range.from)}${tag(node.main_space)}${tag(String(node.score))}</div>
    </div>
  `).join("");
  const receipt = data.receipt || {};
  $("logPreview").innerHTML = `
    <h3 class="detail-title">${escapeHtml(data.title)}</h3>
    <p class="detail-summary">${escapeHtml(data.summary)}</p>
    <div class="detail-grid">
      <div class="detail-cell"><span>日期</span><strong>${escapeHtml(data.inferred_date_raw)}</strong></div>
      <div class="detail-cell"><span>心流分类</span><strong>${escapeHtml(data.flow_classification)}</strong></div>
    </div>
    <div class="detail-cell"><span>人物</span><div class="tag-row">${people || tag("待核对")}</div></div>
    <div class="detail-cell"><span>空间</span><div class="tag-row">${spaces || tag("待核对")}</div></div>
    <div class="receipt">
      ${Object.entries(receipt).map(([key, value]) => `<div><strong>${escapeHtml(key)}：</strong>${escapeHtml(Array.isArray(value) ? value.join("、") : value)}</div>`).join("")}
    </div>
    <div class="section-head"><h3>候选时空轴</h3><span>${(data.candidate_timeline_nodes || []).length} 个</span></div>
    ${candidates || `<div class="empty">无候选节点</div>`}
  `;
  document.querySelectorAll(".candidate").forEach((el) => {
    el.addEventListener("click", () => {
      document.querySelectorAll(".candidate").forEach((x) => x.classList.remove("selected"));
      el.classList.add("selected");
      state.selectedTimelineNodeId = el.dataset.id;
      $("confirmLog").disabled = false;
    });
  });
}

function getLogDraftFilename(format) {
  const date = safeDateText((state.preview?.inferred_date_iso || "").replace(/[^0-9-]/g, "") || "");
  const stamp = date || "offline";
  return `数字生命_日志草稿_${stamp}.${format}`;
}

function exportCurrentLogDraft(format) {
  if (!state.preview) return;
  if (format === "json") {
    downloadText(
      getLogDraftFilename("json"),
      JSON.stringify(state.preview, null, 2),
      "application/json",
    );
  } else {
    downloadText(
      getLogDraftFilename("md"),
      formatDraftMarkdown(state.preview),
      "text/markdown",
    );
  }
}

async function confirmLog() {
  if (!state.preview?.draft_id || !state.selectedTimelineNodeId) return;
  $("draftState").textContent = "写入中";
  $("logDraftNote").textContent = "静态版不支持正式写入，请启动本地服务后确认。";
  try {
    const data = await api("/api/logs/confirm", {
      method: "POST",
      body: JSON.stringify({
        draft_id: state.preview.draft_id,
        timeline_node_id: state.selectedTimelineNodeId,
        status: "confirmed",
      }),
    });
    $("draftState").textContent = "已写入";
    $("confirmLog").disabled = true;
    $("logPreview").insertAdjacentHTML("afterbegin", `<div class="receipt"><strong>正式日志：</strong>${escapeHtml(data.log_id)}<br><strong>时空轴：</strong>${escapeHtml(data.timeline_node_title)}</div>`);
    await loadStatus();
  } catch (error) {
    $("draftState").textContent = error.message || "写入失败";
    $("logDraftNote").textContent = error.message || "写入失败。";
  }
}

async function loadFlow(explicit) {
  const type = explicit ? "xiaoge" : "general";
  const data = await api(`/api/flow?type=${type}&explicit=${explicit ? "1" : "0"}&limit=30`);
  if (!data.allowed) {
    $("flowResult").innerHTML = `<div class="record-item"><h4>门禁</h4><p>${escapeHtml(data.gate)}</p></div>`;
    return;
  }
  const nodes = data.timeline?.nodes || [];
  $("flowResult").innerHTML = nodes.map((node) => renderRecord({
    title: node.title,
    type: node.has_flow_marker ? "心流标记" : "",
    subtitle: node.date_range.from,
    body: node.summary,
  })).join("") || `<div class="empty">暂无记录</div>`;
}

function renderQueueItem(item) {
  return renderRecord({
    title: item.title || item.entry_type || "未命名入库项",
    type: item.status || "pending",
    subtitle: item.workflow_id || "",
    body: [
      item.status_reason ? `状态说明：${item.status_reason}` : "",
      item.occurred_at_iso ? `发生日期：${item.occurred_at_iso}` : "",
      item.source_path ? `来源：${compact(item.source_path, 180)}` : "",
    ].filter(Boolean).join("\n"),
  });
}

function renderAnalyticsItem(item) {
  const topCities = safeJson(item.top_cities_json, []);
  const topSpaces = safeJson(item.top_spaces_json, []);
  const topCompanions = safeJson(item.top_companions_json, []);
  const body = [
    `节点 ${item.node_count || 0}，天数 ${item.day_count || 0}，外出 ${item.trip_count || 0}，日志 ${item.log_count || 0}`,
    topCities.length ? `城市/地点：${topCities.slice(0, 5).map((x) => `${x.name || x[0]}(${x.count || x[1] || 0})`).join("、")}` : "",
    topSpaces.length ? `空间：${topSpaces.slice(0, 5).map((x) => `${x.name || x[0]}(${x.count || x[1] || 0})`).join("、")}` : "",
    topCompanions.length ? `同行：${topCompanions.slice(0, 5).map((x) => `${x.name || x[0]}(${x.count || x[1] || 0})`).join("、")}` : "",
  ].filter(Boolean).join("\n");
  return renderRecord({
    title: item.title || item.scope_key || "统计项",
    type: item.scope_type || "",
    subtitle: [item.from_iso, item.to_iso].filter(Boolean).join(" 至 "),
    body,
  });
}

function renderMediaItem(item) {
  return renderRecord({
    title: item.title || item.file_name || "媒体附件",
    type: item.source_area || "",
    subtitle: item.privacy_level || item.media_type || "",
    body: item.relative_path || item.description || "",
  });
}

function renderAliasHealth(aliasStatus) {
  if (!aliasStatus) return `<div class="empty">复原基线状态暂不可用</div>`;
  const summary = aliasStatus.summary || {};
  const counts = summary.alias_kind_counts || {};
  const validation = aliasStatus.validation || {};
  const items = [
    {
      title: "复原基线总状态",
      type: aliasStatus.ok ? "通过" : "需复核",
      subtitle: validation.checked_at || "",
      body: [
        `Alias 总数：${summary.alias_count || 0}`,
        `运行文件：${summary.exists ? "存在" : "缺失"}`,
        `P0 文件恢复：${counts.p0_file_recovery || 0}`,
        `链接重定向：${counts.link_redirect || 0}`,
      ].join("\n"),
    },
    {
      title: "读取索引原则",
      type: "只读",
      subtitle: "不覆盖镜像",
      body: aliasStatus.principle || "只用于本地读取索引和链接解析。",
    },
    {
      title: "缺口收束",
      type: `${aliasStatus.unresolved_count || 0} 条`,
      subtitle: "外部回源",
      body: [
        `非文件编号：${counts.non_file_link_marker || 0}`,
        `未解析链接：${aliasStatus.unresolved_count || 0}`,
        "未解析项保留为待办，不扩大为系统性故障。",
      ].join("\n"),
    },
  ];
  return items.map(renderRecord).join("");
}

function renderAliasUnresolved(aliasStatus) {
  const unresolved = ensureArray(aliasStatus?.unresolved || []);
  if (!unresolved.length) return `<div class="empty">暂无外部回源待办</div>`;
  return unresolved.map((item) => renderRecord({
    title: item.normalized_target || item.original_target || "未解析目标",
    type: item.recovery_priority || item.resolution_class || item.alias_kind || "unresolved",
    subtitle: item.source_rel || "",
    body: [
      item.recovery_task_type ? `任务类型：${item.recovery_task_type}` : "",
      item.global_filename_search ? `全盘搜索：${item.global_filename_search}` : "",
      item.likely_meaning ? `当前判断：${item.likely_meaning}` : "当前本地资产未找到候选文件。",
      item.recovery_primary_action ? `优先动作：${item.recovery_primary_action}` : "",
      item.recovery_fallback_action ? `找不到时：${item.recovery_fallback_action}` : "",
      item.human_action ? `处理口径：${item.human_action}` : "",
    ].join("\n"),
  })).join("");
}

function renderQingfengPhotoHealth(photoStatus) {
  if (!photoStatus) return `<div class="empty">清风照片库复原状态暂不可用</div>`;
  const summary = photoStatus.summary || {};
  const completion = photoStatus.completion_summary || {};
  const priority = completion.priority_counts || {};
  const p1Capture = photoStatus.p1_capture_summary || {};
  const p1Import = photoStatus.p1_import_summary || {};
  const p1Binding = photoStatus.p1_binding_summary || {};
  const p1BindingQa = photoStatus.p1_binding_qa_summary || {};
  const validation = photoStatus.validation || {};
  const completionValidation = photoStatus.completion_validation || {};
  const p1CaptureValidation = photoStatus.p1_capture_validation || {};
  const p1ImportValidation = photoStatus.p1_import_validation || {};
  const p1BindingValidation = photoStatus.p1_binding_validation || {};
  const p1BindingQaValidation = photoStatus.p1_binding_qa_validation || {};
  const items = [
    {
      title: "清风照片库本地重建",
      type: photoStatus.ok ? "通过" : "需复核",
      subtitle: validation.checked_at || "",
      body: [
        `重建行数：${summary.row_count || 0}`,
        `已挂接图片：${summary.media_asset_rows || 0}`,
        `上下文页支撑：${summary.context_only_rows || 0}`,
        `待补空间：${summary.needs_recovery_rows || 0}`,
      ].join("\n"),
    },
    {
      title: "补全优先级",
      type: completionValidation.ok ? "已分级" : "待分级",
      subtitle: completionValidation.checked_at || "",
      body: [
        `P1 入口/动线/户外轴线：${priority.P1 || 0}`,
        `P2 生活/精神核心：${priority.P2 || 0}`,
        `P3 私密/辅助：${priority.P3 || 0}`,
        `建议新增照片：${completion.suggested_total_new_shots || 0}`,
      ].join("\n"),
    },
    {
      title: "P1 拍摄任务台",
      type: p1CaptureValidation.ok ? "可执行" : "待生成",
      subtitle: p1CaptureValidation.checked_at || "",
      body: [
        `P1 任务：${p1Capture.row_count || 0}`,
        `最小拍摄：${p1Capture.suggested_total_shots || 0} 张`,
        `待拍：${(p1Capture.capture_state_counts || {}).todo || 0}`,
        `导入状态：${(p1Capture.import_state_counts || {}).not_imported || 0} 未导入`,
      ].join("\n"),
    },
    {
      title: "P1 导入状态",
      type: p1ImportValidation.ok ? "已扫描" : "待扫描",
      subtitle: p1ImportValidation.checked_at || "",
      body: [
        `任务行：${p1Import.row_count || 0}`,
        `已发现图片：${p1Import.total_found_files || 0}`,
        `可进入 QA：${p1Import.ready_for_qa_count || 0}`,
        `未开始：${p1Import.not_started_count || 0}`,
      ].join("\n"),
    },
    {
      title: "P1 绑定候选",
      type: p1BindingValidation.ok ? "已生成" : "待生成",
      subtitle: p1BindingValidation.checked_at || "",
      body: [
        `候选行：${p1Binding.row_count || 0}`,
        `文件级候选：${p1Binding.file_candidate_count || 0}`,
        `可绑定：${p1Binding.bindable_candidate_count || 0}`,
        `等待导入：${p1Binding.waiting_import_count || 0}`,
      ].join("\n"),
    },
    {
      title: "P1 QA 门",
      type: p1BindingQaValidation.ok ? "已设门" : "待生成",
      subtitle: p1BindingQaValidation.checked_at || "",
      body: [
        `QA 行：${p1BindingQa.row_count || 0}`,
        `待人工 QA：${p1BindingQa.pending_human_qa_count || 0}`,
        `可进确认包：${p1BindingQa.approval_packet_eligible_count || 0}`,
        `正式绑定开放：${p1BindingQa.formal_binding_allowed_count || 0}`,
      ].join("\n"),
    },
    {
      title: "边界声明",
      type: photoStatus.not_original_csv ? "非原 CSV" : "待确认",
      subtitle: "不回写母本",
      body: photoStatus.principle || "本索引用于本地展示、检索和补拍清单。",
    },
  ];
  return items.map(renderRecord).join("");
}

function renderQingfengPhotoTodo(photoStatus) {
  const taskRows = ensureArray(photoStatus?.p1_capture_tasks || []);
  if (taskRows.length) return taskRows.map((item) => renderRecord({
    title: item.space_name || item.capture_task_id || "P1 拍摄任务",
    type: [item.capture_task_id, item.space_code].filter(Boolean).join("｜") || "P1",
    subtitle: [item.route_batch, item.capture_state].filter(Boolean).join("｜"),
    body: [
      item.suggested_shot_count ? `最小拍摄：${item.suggested_shot_count} 张` : "",
      item.shot_slots ? `必拍清单：${item.shot_slots}` : "",
      item.filename_pattern ? `命名：${item.filename_pattern}` : "",
      item.local_import_drop_hint ? `导入目录：${item.local_import_drop_hint}` : "",
      item.live_import_status ? `导入状态：${item.live_import_status}，已发现 ${item.found_files_count || 0} 张，缺 ${item.missing_file_count || 0} 张` : "",
      item.binding_candidate_status ? `绑定候选：${item.binding_candidate_status}，${item.binding_bindable ? "可绑定" : "不可绑定"}` : "",
      item.qa_gate_status ? `QA门：${item.qa_gate_status}，确认包 ${item.approval_packet_eligible ? "可进" : "不可进"}，正式绑定 ${item.formal_binding_allowed ? "允许" : "未开放"}` : "",
      item.privacy_gate ? `隐私门禁：${item.privacy_gate}` : "",
      item.qa_checklist ? `验收：${item.qa_checklist}` : "",
      item.qa_next_action ? `QA动作：${item.qa_next_action}` : item.binding_next_action ? `绑定动作：${item.binding_next_action}` : item.import_next_action ? `导入动作：${item.import_next_action}` : item.import_next_step ? `导入后：${item.import_next_step}` : "",
    ].join("\n"),
  })).join("");
  const rows = ensureArray(photoStatus?.needs_recovery || []);
  if (!rows.length) return `<div class="empty">暂无待补空间</div>`;
  return rows.map((item) => renderRecord({
    title: item.space_name || item.rebuilt_id || "待补空间",
    type: [item.completion_priority, item.space_code].filter(Boolean).join("｜") || item.rebuild_status || "待补",
    subtitle: [item.floor, item.status].filter(Boolean).join("｜"),
    body: [
      item.completion_batch ? `批次：${item.completion_batch}` : "",
      item.privacy_level ? `隐私：${item.privacy_level}` : "",
      item.suggested_shot_count ? `建议照片：${item.suggested_shot_count} 张` : "",
      item.suggested_shot_plan ? `拍摄清单：${item.suggested_shot_plan}` : "",
      item.completion_next_step ? `下一步：${item.completion_next_step}` : item.next_action ? `下一步：${item.next_action}` : "",
      item.function ? `功能：${item.function}` : "",
      item.action_reason ? `依据：${item.action_reason}` : "",
    ].join("\n"),
  })).join("");
}

function renderAuditItems(data) {
  const reports = data.reports || {};
  const phase2Report = reports.phase2 || {};
  const pipeline = reports.pipeline || {};
  const health = reports.health || {};
  const restore = reports.backup_restore || {};
  const privacy = data.latest_privacy_audit || {};
  const backup = data.latest_backup_check || {};
  const items = [
    {
      title: "一键重建流水线",
      type: pipeline.completed === true ? "通过" : "已记录",
      body: pipeline.completed === true ? `完整重建已通过，步骤 ${ensureArray(pipeline.steps).length}。` : "查看重建报告确认最近状态。",
    },
    {
      title: "健康检查",
      type: health.all_pass === true ? "通过" : "已记录",
      body: health.all_pass === true ? `检查项 ${ensureArray(health.checks).length}，全部通过。` : "查看健康检查报告确认最近状态。",
    },
    {
      title: "二期优化总验收",
      type: phase2Report.status || "已记录",
      body: phase2Report.passed === true ? `验收项 ${ensureArray(phase2Report.checks).length}，全部通过。` : "二期验收报告已纳入工程产物。",
    },
    {
      title: "隐私与心流门禁",
      type: privacy.status || "已审计",
      body: privacy.raw_json
        ? compact(JSON.stringify(safeJson(privacy.raw_json, {}), null, 2), 240)
        : `检查 ${privacy.checked_count || 0}，违规 ${privacy.violation_count || 0}。`,
    },
    {
      title: "备份与恢复",
      type: restore.status || backup.status || "已记录",
      body: [
        backup.latest_backup_name ? `最新备份：${backup.latest_backup_name}` : "",
        backup.message || "",
        restore.count_mismatches ? `计数不一致：${ensureArray(restore.count_mismatches).length}` : "",
      ].filter(Boolean).join("\n") || "备份恢复演练报告已纳入工程产物。",
    },
  ];
  return items.map(renderRecord).join("");
}

async function loadOperations() {
  const [data, aliasStatus, photoStatus] = await Promise.all([
    api("/api/operations"),
    api("/api/source-alias/status?include_unresolved=1").catch(() => null),
    api("/api/qingfeng-photo-library/status?limit=24").catch(() => null),
  ]);
  const counts = data.counts || {};
  const aliasSummary = aliasStatus?.summary || {};
  const aliasKinds = aliasSummary.alias_kind_counts || {};
  const photoSummary = photoStatus?.summary || {};
  const photoCompletion = photoStatus?.completion_summary || {};
  const photoPriority = photoCompletion.priority_counts || {};
  const photoP1Capture = photoStatus?.p1_capture_summary || {};
  const photoP1Import = photoStatus?.p1_import_summary || {};
  const photoP1Binding = photoStatus?.p1_binding_summary || {};
  const photoP1BindingQa = photoStatus?.p1_binding_qa_summary || {};
  $("operationsSummary").innerHTML = [
    metric("入库队列", counts.intake_queue ?? 0),
    metric("证据等级", counts.evidence_grade_index ?? 0),
    metric("时空统计", counts.timeline_analytics_cache ?? 0),
    metric("媒体附件", counts.media_assets ?? 0),
    metric("门禁审计", counts.privacy_gate_audit ?? 0),
    metric("二期运行", counts.phase2_optimization_runs ?? 0),
    metric("复原基线", aliasStatus?.ok ? "通过" : "待查"),
    metric("未解析链接", aliasStatus?.unresolved_count ?? 0),
    metric("照片库复原", photoStatus?.ok ? `${photoSummary.row_count || 0} 行` : "待查"),
    metric("照片待补", photoStatus?.needs_recovery_count ?? 0),
    metric("P1照片", photoPriority.P1 || 0),
    metric("P1任务", photoP1Capture.row_count || 0),
    metric("P1最小拍摄", photoP1Capture.suggested_total_shots || 0),
    metric("P1已导入", photoP1Import.total_found_files || 0),
    metric("P1可绑定", photoP1Binding.bindable_candidate_count || 0),
    metric("P1待QA", photoP1BindingQa.pending_human_qa_count || 0),
  ].join("");
  $("opsQueueMeta").textContent = `${counts.intake_queue ?? 0} 条`;
  $("opsQueue").innerHTML = ensureArray(data.queue_items).map(renderQueueItem).join("") || `<div class="empty">暂无队列</div>`;
  $("opsAnalyticsMeta").textContent = `${counts.timeline_analytics_cache ?? 0} 条`;
  $("opsAnalytics").innerHTML = ensureArray(data.timeline_analytics).slice(0, 60).map(renderAnalyticsItem).join("") || `<div class="empty">暂无统计</div>`;
  $("opsAuditMeta").textContent = "门禁 / 备份 / 验收";
  $("opsAudit").innerHTML = renderAuditItems(data);
  $("opsEvidenceMeta").textContent = `${counts.evidence_grade_index ?? 0} 条`;
  $("opsEvidence").innerHTML = mapToRecords(data.evidence_grade_counts || {}, {
    A: "A｜原文明确",
    B: "B｜直接推导",
    C: "C｜系统整理",
    D: "D｜待确认",
  });
  $("opsMediaMeta").textContent = `${counts.media_assets ?? 0} 个`;
  $("opsMedia").innerHTML = ensureArray(data.media_assets).map(renderMediaItem).join("") || `<div class="empty">暂无附件</div>`;
  $("opsAliasMeta").textContent = aliasStatus?.ok ? "已接入" : "未接入";
  $("opsAliasHealth").innerHTML = aliasStatus ? renderAliasHealth(aliasStatus) : `<div class="empty">复原基线状态暂不可用</div>`;
  $("opsAliasUnresolvedMeta").textContent = `${aliasStatus?.unresolved_count ?? 0} 条`;
  $("opsAliasUnresolved").innerHTML = renderAliasUnresolved(aliasStatus);
  $("opsQingfengPhotoMeta").textContent = photoStatus?.ok ? "本地重建" : "未接入";
  $("opsQingfengPhoto").innerHTML = renderQingfengPhotoHealth(photoStatus);
  $("opsQingfengPhotoTodoMeta").textContent = photoStatus?.p1_capture_task_count
    ? `${photoStatus.p1_capture_task_count} 个 P1 任务`
    : `${photoStatus?.needs_recovery_count ?? 0} 条`;
  $("opsQingfengPhotoTodo").innerHTML = renderQingfengPhotoTodo(photoStatus);
}

async function loadDL2() {
  const [status, memories, hypotheses, calibrations, packages] = await Promise.all([
    api("/api/dl2/status"), api("/api/dl2/memories?limit=100"), api("/api/dl2/hypotheses?limit=100"),
    api("/api/dl2/calibrations?limit=100"), api("/api/dl2/context-packages?limit=100"),
  ]);
  const counts = status.counts || {};
  $("dl2Summary").innerHTML = [
    metric("活记忆", counts.memories || 0), metric("记忆版本", counts.memory_versions || 0),
    metric("可反证模型", counts.hypotheses || 0), metric("真人校准", counts.completed_calibrations || 0),
    metric("上下文包", counts.context_packages || 0), metric("M6代理", status.milestones?.M6 || "DISABLED"),
  ].join("");
  $("dl2MemoryMeta").textContent = `${memories.items?.length || 0} 条`;
  $("dl2Memories").innerHTML = ensureArray(memories.items).map((item) => renderRecord({
    title: item.statement_snapshot, type: `${item.status} · v${item.version_no}`,
    body: `类型：${item.statement_type}\n证据锚点：${item.evidence_count}\n所有权：${item.ownership_state}`,
  })).join("") || `<div class="empty">暂无活记忆</div>`;
  $("dl2HypothesisMeta").textContent = `${hypotheses.items?.length || 0} 条`;
  $("dl2Hypotheses").innerHTML = ensureArray(hypotheses.items).map((item) => renderRecord({
    title: item.claim, type: `${item.status} · ${item.evidence_sufficiency}`,
    body: `适用：${item.applicable_period} / ${item.applicable_context}\n最强反驳：${item.strongest_counterargument}`,
  })).join("") || `<div class="empty">暂无模型候选</div>`;
  $("dl2CalibrationMeta").textContent = `${calibrations.items?.length || 0} 题`;
  $("dl2Calibrations").innerHTML = ensureArray(calibrations.items).map((item) => renderRecord({title: item.question, type: item.status, body: item.difference_summary || "已封存系统答案，等待本人原话。"})).join("") || `<div class="empty">等待真实对话中的校准，不伪造题目。</div>`;
  $("dl2PackageMeta").textContent = `${packages.items?.length || 0} 包`;
  $("dl2Packages").innerHTML = ensureArray(packages.items).map((item) => renderRecord({title: `${item.requester}｜${item.question}`, type: item.status, body: `授权：${item.authorization_id}\n用途：${item.purpose}\n哈希：${item.package_hash}`})).join("") || `<div class="empty">等待 P05 或人生漫游馆的真实请求，不伪造回执。</div>`;
}

function loadView(view) {
  if (view === "timeline") loadTimeline();
  if (view === "chronicle") loadChronicle();
  if (view === "synthesis") runSynthesis();
  if (view === "operations") loadOperations();
  if (view === "dl2") loadDL2();
  if (view === "search") runSearch();
  if (view === "entities") runEntitySearch();
  if (view === "evidence") runEvidenceSearch();
  if (view === "qingfeng") loadQingfeng();
  if (view === "rules") loadRules();
  if (view === "people") loadList("people", "peopleList", "/api/people?limit=160");
  if (view === "events") loadList("events", "eventList", "/api/events?limit=160");
  if (view === "terms") loadList("terms", "termList", "/api/terms?limit=200");
  if (view === "logs") loadLogLibrary();
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $("refreshButton").addEventListener("click", () => loadView(state.view));
  $("timelineRun").addEventListener("click", loadTimeline);
  $("timelineDate").addEventListener("change", () => {
    if ($("timelineDate").value) $("timelineMonth").value = "";
  });
  $("synthesisRun").addEventListener("click", runSynthesis);
  $("synthesisExportJson").addEventListener("click", () => exportSynthesis("json"));
  $("synthesisExportMd").addEventListener("click", () => exportSynthesis("md"));
  $("searchRun").addEventListener("click", runSearch);
  $("searchInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch();
  });
  $("chronicleRun").addEventListener("click", loadChronicle);
  $("chronicleKeyword").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadChronicle();
  });
  $("chroniclePhase").addEventListener("keydown", (event) => {
    if (event.key === "Enter") loadChronicle();
  });
  $("chronicleEntity").addEventListener("change", loadChronicle);
  $("evidenceRun").addEventListener("click", runEvidenceSearch);
  $("evidenceInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runEvidenceSearch();
  });
  $("entityRun").addEventListener("click", runEntitySearch);
  $("entityInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runEntitySearch();
  });
  $("entityType").addEventListener("change", runEntitySearch);
  document.body.addEventListener("click", (event) => {
    const entityButton = event.target.closest(".entity-link");
    if (entityButton) {
      event.preventDefault();
      setView("entities", true);
      loadEntityDetail(entityButton.dataset.entityType, entityButton.dataset.entityId);
      return;
    }
    const segmentButton = event.target.closest(".segment-apply");
    if (segmentButton) {
      event.preventDefault();
      const from = segmentButton.dataset.from || "";
      const to = segmentButton.dataset.to || "";
      const phase = segmentButton.dataset.phase || "";
      if ($("synthesisFrom")) $("synthesisFrom").value = from || "";
      if ($("synthesisTo")) $("synthesisTo").value = to || "";
      if ($("synthesisPhase")) $("synthesisPhase").value = phase || "";
      if ($("synthesisTrip")) $("synthesisTrip").checked = false;
      if ($("synthesisMonth")) $("synthesisMonth").value = "";
      runSynthesis();
      return;
    }
    const button = event.target.closest(".evidence-link");
    if (!button) return;
    event.preventDefault();
    setView("evidence", true);
    loadEntityEvidence(button.dataset.entityType, button.dataset.entityId, button.dataset.sourceFileId);
    loadSource(button.dataset.sourceFileId);
  });
  $("previewLog").addEventListener("click", previewLog);
  $("confirmLog").addEventListener("click", confirmLog);
  $("exportLogJson").addEventListener("click", () => exportCurrentLogDraft("json"));
  $("exportLogMd").addEventListener("click", () => exportCurrentLogDraft("md"));
  $("generalFlow").addEventListener("click", () => loadFlow(false));
  $("xiaogeFlow").addEventListener("click", () => loadFlow(true));
  $("generalLogScope").addEventListener("click", async () => {
    setLogScope("general");
    await loadLogLibrary();
  });
  $("xiaogeLogScope").addEventListener("click", async () => {
    setLogScope("restricted");
    await loadLogLibrary();
  });
}

async function init() {
  bindEvents();
  setLogScope("general");
  await loadStatus();
  await loadTimeline();
}

init().catch((error) => {
  $("systemState").textContent = error.message;
  console.error(error);
});
