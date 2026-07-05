const STORE_KEY = "digital-life-public-today-log-v1";
const CHUNK_SIZE = 8000;
const CHUNK_COUNT_KEY = `${STORE_KEY}:chunk-count`;
const CHUNK_PREFIX = `${STORE_KEY}:chunk:`;
const TOKEN_PROPERTY = "DIGITAL_LIFE_PUBLIC_TOKEN";
const MAX_ITEMS = 200;

function doGet(e) {
  const body = {};
  const auth = authorize_(e, body);
  if (!auth.ok) return json_(auth);
  const action = ((e && e.parameter && e.parameter.action) || "list").toLowerCase();
  const state = loadState_();
  if (action === "ping" || action === "pin") return json_({ ok: true, updatedAt: state.updatedAt || "", count: (state.items || []).length });
  return json_({ ok: true, state });
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const body = parseBody_(e);
    const auth = authorize_(e, body);
    if (!auth.ok) return json_(auth);
    const action = String(body.action || "submit").toLowerCase();
    const state = loadState_();
    if (action === "submit") {
      const item = normalizeItem_(body.item || {});
      if (!item.text) return json_({ ok: false, error: "日志正文为空" });
      upsertItem_(state, item);
      saveState_(state);
      return json_({ ok: true, item, state: publicState_(state) });
    }
    if (action === "update") {
      const patch = body.item || {};
      if (!patch.id) return json_({ ok: false, error: "缺少 item.id" });
      const item = updateItem_(state, patch);
      saveState_(state);
      return json_({ ok: true, item, state: publicState_(state) });
    }
    if (action === "bulkupdate" || action === "bulkUpdate") {
      const patches = Array.isArray(body.items) ? body.items : [];
      const updated = patches.map((patch) => patch && patch.id ? updateItem_(state, patch) : null).filter(Boolean);
      saveState_(state);
      return json_({ ok: true, updated, state: publicState_(state) });
    }
    return json_({ ok: false, error: `未知 action: ${action}` });
  } catch (err) {
    return json_({ ok: false, error: String(err && err.message ? err.message : err) });
  } finally {
    lock.releaseLock();
  }
}

function parseBody_(e) {
  const text = (e && e.postData && e.postData.contents) || "{}";
  try { return JSON.parse(text || "{}"); } catch (err) { return {}; }
}

function authorize_(e, body) {
  const props = PropertiesService.getScriptProperties();
  const expected = String(props.getProperty(TOKEN_PROPERTY) || "").trim();
  if (!expected) return { ok: true };
  const got = String((body && body.token) || (e && e.parameter && e.parameter.token) || "").trim();
  if (got === expected) return { ok: true };
  return { ok: false, error: "云端收件箱口令不正确" };
}

function normalizeItem_(raw) {
  const now = new Date().toISOString();
  return {
    id: String(raw.id || `dlp-${Date.now()}`).trim(),
    project: "digital_life",
    entry_type: "today_log",
    source: String(raw.source || "public_web").trim(),
    date: String(raw.date || now.slice(0, 10)).trim(),
    title: String(raw.title || `公网今日日志｜${String(raw.date || now.slice(0, 10)).trim()}`).trim(),
    text: String(raw.text || "").trim(),
    status: String(raw.status || "pending").trim(),
    createdAt: String(raw.createdAt || now).trim(),
    updatedAt: now,
    result: raw.result || null,
    error: raw.error || ""
  };
}

function upsertItem_(state, item) {
  state.items = Array.isArray(state.items) ? state.items : [];
  const index = state.items.findIndex((entry) => entry.id === item.id);
  if (index >= 0) state.items[index] = Object.assign({}, state.items[index], item, { updatedAt: new Date().toISOString() });
  else state.items.unshift(item);
  state.items = state.items.slice(0, MAX_ITEMS);
  state.updatedAt = new Date().toISOString();
}

function updateItem_(state, patch) {
  state.items = Array.isArray(state.items) ? state.items : [];
  const index = state.items.findIndex((entry) => entry.id === patch.id);
  if (index < 0) throw new Error(`未找到 item: ${patch.id}`);
  const updated = Object.assign({}, state.items[index], patch, { updatedAt: new Date().toISOString() });
  state.items[index] = updated;
  state.updatedAt = new Date().toISOString();
  return updated;
}

function publicState_(state) {
  return { updatedAt: state.updatedAt || "", items: Array.isArray(state.items) ? state.items : [] };
}

function loadState_() {
  try {
    const props = PropertiesService.getScriptProperties();
    const text = readChunkedPayload_(props) || props.getProperty(STORE_KEY) || "{}";
    const parsed = JSON.parse(text || "{}");
    return publicState_(parsed);
  } catch (err) {
    return { updatedAt: "", items: [] };
  }
}

function saveState_(state) {
  const props = PropertiesService.getScriptProperties();
  const text = JSON.stringify(publicState_(state));
  const oldCount = Number(props.getProperty(CHUNK_COUNT_KEY) || 0);
  const chunks = [];
  for (let i = 0; i < text.length; i += CHUNK_SIZE) chunks.push(text.slice(i, i + CHUNK_SIZE));
  const values = {};
  values[CHUNK_COUNT_KEY] = String(chunks.length);
  chunks.forEach((chunk, index) => { values[`${CHUNK_PREFIX}${index}`] = chunk; });
  props.setProperties(values, false);
  props.deleteProperty(STORE_KEY);
  for (let index = chunks.length; index < oldCount; index += 1) props.deleteProperty(`${CHUNK_PREFIX}${index}`);
}

function readChunkedPayload_(props) {
  const count = Number(props.getProperty(CHUNK_COUNT_KEY) || 0);
  if (!count) return "";
  const chunks = [];
  for (let index = 0; index < count; index += 1) chunks.push(props.getProperty(`${CHUNK_PREFIX}${index}`) || "");
  return chunks.join("");
}

function json_(payload) {
  return ContentService.createTextOutput(JSON.stringify(payload)).setMimeType(ContentService.MimeType.JSON);
}
