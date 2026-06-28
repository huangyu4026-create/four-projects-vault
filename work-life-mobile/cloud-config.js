window.WORK_LIFE_CLOUD_SYNC_URL = "";

(function () {
  const apiBase = "https://api.telegra.ph";
  const pathKey = "workLifeTelegraphPath";
  const tokenKey = "workLifeTelegraphToken";
  const clientIdKey = "workLifeTelegraphClientId";

  function readParams() {
    const query = new URLSearchParams(location.search || "");
    const hashText = location.hash && location.hash.startsWith("#") ? location.hash.slice(1) : "";
    const hash = new URLSearchParams(hashText);
    const path = (query.get("telegraphPath") || hash.get("telegraphPath") || localStorage.getItem(pathKey) || "").trim();
    const token = (hash.get("telegraphToken") || query.get("telegraphToken") || localStorage.getItem(tokenKey) || "").trim();
    if (path) localStorage.setItem(pathKey, path);
    if (token) localStorage.setItem(tokenKey, token);
    if (hash.get("telegraphToken")) {
      hash.delete("telegraphToken");
      const nextHash = hash.toString();
      history.replaceState(null, "", `${location.pathname}${location.search}${nextHash ? `#${nextHash}` : ""}`);
    }
    return { path, token };
  }

  function getTelegraphClientId() {
    let id = localStorage.getItem(clientIdKey);
    if (id) return id;
    id = `phone-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem(clientIdKey, id);
    return id;
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

  async function fetchTelegraphState() {
    const config = readParams();
    if (!config.path) return null;
    const url = `${apiBase}/getPage/${encodeURIComponent(config.path)}?return_content=true&t=${Date.now()}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`Telegraph 读取失败：HTTP ${res.status}`);
    const body = await res.json().catch(() => null);
    if (body?.ok === false) throw new Error(body.error || "Telegraph 返回失败");
    const text = contentText(body?.result?.content);
    if (!text) return null;
    const payload = JSON.parse(text);
    if (payload?.ok === false) throw new Error(payload.error || "Telegraph 数据失败");
    const state = payload?.state && typeof payload.state === "object" ? payload.state : null;
    return state ? { state, updatedAt: payload.updatedAt || "" } : null;
  }

  async function postTelegraphState(state) {
    const config = readParams();
    if (!config.path || !config.token) throw new Error("Telegraph 同步未配置写入链接");
    const payload = {
      ok: true,
      updatedAt: new Date().toISOString(),
      clientId: getTelegraphClientId(),
      state
    };
    const params = new URLSearchParams();
    params.set("access_token", config.token);
    params.set("title", "work-life-mobile-shared-state");
    params.set("author_name", "Work Life Mobile");
    params.set("content", JSON.stringify([{ tag: "pre", children: [JSON.stringify(payload)] }]));
    params.set("return_content", "false");
    const res = await fetch(`${apiBase}/editPage/${encodeURIComponent(config.path)}`, {
      method: "POST",
      cache: "no-store",
      body: params
    });
    if (!res.ok) throw new Error(`Telegraph 写入失败：HTTP ${res.status}`);
    const body = await res.json().catch(() => null);
    if (body?.ok === false) throw new Error(body.error || "Telegraph 保存失败");
    return payload;
  }

  function hasTelegraphSync() {
    const config = readParams();
    return Boolean(config.path && config.token);
  }

  function installTelegraphSync() {
    if (!hasTelegraphSync()) return true;
    if (typeof window.fetchCloudState !== "function" || typeof window.postCloudState !== "function" || typeof window.isCloudSyncEnabled !== "function") {
      return false;
    }
    window.isCloudSyncEnabled = hasTelegraphSync;
    window.configuredCloudSyncUrl = () => `telegraph://${readParams().path}`;
    window.cloudUrl = () => "";
    window.fetchCloudState = fetchTelegraphState;
    window.postCloudState = postTelegraphState;
    if (!window.__WORK_LIFE_TELEGRAPH_INSTALLED__) {
      window.__WORK_LIFE_TELEGRAPH_INSTALLED__ = true;
      setTimeout(() => {
        if (typeof window.refreshAllState === "function") window.refreshAllState().catch(() => {});
      }, 250);
    }
    return true;
  }

  let tries = 0;
  const timer = setInterval(() => {
    tries += 1;
    if (installTelegraphSync() || tries > 80) clearInterval(timer);
  }, 50);
})();
