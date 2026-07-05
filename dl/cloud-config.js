// 数字生命公网今日日志入口配置。
// 支持两种云端收件箱：
// 1. Telegraph：无需 Google 授权，通过一次性链接写入本机浏览器。
// 2. Apps Script：仍可在页面配置面板里手动填写 /exec URL。
// 这里绝对不要填写 OpenAI API key。

(function () {
  const telegraphApi = "https://api.telegra.ph";
  const fakeEndpoint = "https://digital-life-public.local/telegraph-inbox";
  const pathKey = "digitalLifePublicTelegraphPath";
  const tokenKey = "digitalLifePublicTelegraphToken";

  function stored(key) {
    try { return localStorage.getItem(key) || ""; } catch (_) { return ""; }
  }
  function save(key, value) {
    try { if (value) localStorage.setItem(key, value); } catch (_) {}
  }
  function readParams() {
    const query = new URLSearchParams(location.search || "");
    const hashText = location.hash && location.hash.startsWith("#") ? location.hash.slice(1) : "";
    const hash = new URLSearchParams(hashText);
    const path = String(query.get("telegraphPath") || hash.get("telegraphPath") || stored(pathKey) || "").trim();
    const token = String(hash.get("telegraphToken") || query.get("telegraphToken") || stored(tokenKey) || "").trim();
    if (path) save(pathKey, path);
    if (token) save(tokenKey, token);
    if (hash.get("telegraphToken")) {
      hash.delete("telegraphToken");
      const nextHash = hash.toString();
      try { history.replaceState(null, "", `${location.pathname}${location.search}${nextHash ? `#${nextHash}` : ""}`); } catch (_) {}
    }
    return { path, token };
  }
  function nodeText(node) {
    if (typeof node === "string") return node;
    if (!node || typeof node !== "object") return "";
    if (Array.isArray(node.children)) return node.children.map(nodeText).join("");
    return "";
  }
  function contentText(content) {
    if (!Array.isArray(content)) return "";
    return content.map(nodeText).join("\n").trim();
  }
  function normalizeState(payload) {
    const state = payload && payload.state && typeof payload.state === "object" ? payload.state : payload || {};
    return {
      updatedAt: state.updatedAt || "",
      items: Array.isArray(state.items) ? state.items : []
    };
  }
  async function fetchTelegraphState(config) {
    if (!config.path) throw new Error("Telegraph 收件箱缺少 path");
    const res = await window.__digitalLifeNativeFetch(`${telegraphApi}/getPage/${encodeURIComponent(config.path)}?return_content=true&t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Telegraph 读取失败：HTTP ${res.status}`);
    const body = await res.json().catch(() => null);
    if (body && body.ok === false) throw new Error(body.error || "Telegraph 返回失败");
    const text = contentText(body && body.result && body.result.content);
    if (!text) return { updatedAt: "", items: [] };
    return normalizeState(JSON.parse(text));
  }
  async function saveTelegraphState(config, state) {
    if (!config.path || !config.token) throw new Error("Telegraph 收件箱缺少写入口令");
    const payload = { ok: true, updatedAt: new Date().toISOString(), state: normalizeState(state) };
    payload.state.updatedAt = payload.updatedAt;
    const params = new URLSearchParams();
    params.set("access_token", config.token);
    params.set("title", "digital-life-public-today-log-inbox");
    params.set("author_name", "Digital Life Public Inbox");
    params.set("content", JSON.stringify([{ tag: "pre", children: [JSON.stringify(payload)] }]));
    params.set("return_content", "false");
    const res = await window.__digitalLifeNativeFetch(`${telegraphApi}/editPage/${encodeURIComponent(config.path)}`, {
      method: "POST",
      cache: "no-store",
      body: params
    });
    if (!res.ok) throw new Error(`Telegraph 写入失败：HTTP ${res.status}`);
    const body = await res.json().catch(() => null);
    if (body && body.ok === false) throw new Error(body.error || "Telegraph 保存失败");
    return payload.state;
  }
  function normalizeItem(raw) {
    const now = new Date().toISOString();
    const date = String(raw.date || now.slice(0, 10)).trim();
    return {
      id: String(raw.id || `dlp-${Date.now()}`).trim(),
      project: "digital_life",
      entry_type: "today_log",
      source: String(raw.source || "public_web").trim(),
      date,
      title: String(raw.title || `公网今日日志｜${date}`).trim(),
      text: String(raw.text || "").trim(),
      status: String(raw.status || "pending").trim(),
      createdAt: String(raw.createdAt || now).trim(),
      updatedAt: now,
      result: raw.result || null,
      error: raw.error || ""
    };
  }
  function upsert(items, item) {
    const list = Array.isArray(items) ? items.slice() : [];
    const index = list.findIndex(entry => entry && entry.id === item.id);
    if (index >= 0) list[index] = { ...list[index], ...item, updatedAt: new Date().toISOString() };
    else list.unshift(item);
    return list.slice(0, 200);
  }
  function update(items, patch) {
    const list = Array.isArray(items) ? items.slice() : [];
    const index = list.findIndex(entry => entry && entry.id === patch.id);
    if (index < 0) throw new Error(`未找到 item: ${patch.id}`);
    list[index] = { ...list[index], ...patch, updatedAt: new Date().toISOString() };
    return list;
  }
  async function handleTelegraphFetch(input, init) {
    const config = readParams();
    if (!config.path || !config.token) {
      return new Response(JSON.stringify({ ok: false, error: "Telegraph 收件箱未连接，请使用带 telegraphPath 和 telegraphToken 的入口链接打开一次。" }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    const method = String((init && init.method) || "GET").toUpperCase();
    const url = new URL(typeof input === "string" ? input : input.url);
    let state = await fetchTelegraphState(config);
    if (method === "GET") {
      return new Response(JSON.stringify({ ok: true, state }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    const body = JSON.parse((init && init.body) || "{}");
    const action = String(body.action || "submit").toLowerCase();
    if (action === "submit") {
      const item = normalizeItem(body.item || {});
      if (!item.text) throw new Error("日志正文为空");
      state.items = upsert(state.items, item);
    } else if (action === "update") {
      state.items = update(state.items, body.item || {});
    } else if (action === "bulkupdate") {
      (Array.isArray(body.items) ? body.items : []).forEach(patch => { state.items = update(state.items, patch || {}); });
    } else {
      throw new Error(`未知 action: ${action}`);
    }
    state = await saveTelegraphState(config, state);
    return new Response(JSON.stringify({ ok: true, state }), { status: 200, headers: { "Content-Type": "application/json" } });
  }

  const config = readParams();
  window.__digitalLifeNativeFetch = window.__digitalLifeNativeFetch || window.fetch.bind(window);
  if (config.path && config.token) {
    window.DIGITAL_LIFE_PUBLIC_INBOX_URL = fakeEndpoint;
    window.DIGITAL_LIFE_PUBLIC_TOKEN = "";
  } else {
    window.DIGITAL_LIFE_PUBLIC_INBOX_URL = "";
    window.DIGITAL_LIFE_PUBLIC_TOKEN = "";
  }
  window.fetch = function (input, init) {
    const url = typeof input === "string" ? input : input && input.url;
    if (url && String(url).startsWith(fakeEndpoint)) {
      return handleTelegraphFetch(input, init).catch(err => new Response(JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) }), { status: 200, headers: { "Content-Type": "application/json" } }));
    }
    return window.__digitalLifeNativeFetch(input, init);
  };
})();
