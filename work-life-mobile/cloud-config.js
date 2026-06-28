window.WORK_LIFE_CLOUD_SYNC_URL = "";

(function () {
  const apiBase = "https://api.telegra.ph";
  const storageKey = "workCockpitState";
  const pulseKey = "workCockpitStatePulse";
  const pathKey = "workLifeTelegraphPath";
  const tokenKey = "workLifeTelegraphToken";
  const clientIdKey = "workLifeTelegraphClientId";
  const inboxAutoFillDisableKey = "workCockpitInboxAutoFillDisabled";
  const inboxHardClearKey = "workCockpitInboxHardClearTs";
  const nativeSetItem = Storage.prototype.setItem;
  const nativeGetItem = Storage.prototype.getItem;
  let applyingRemote = false;
  let pushTimer = null;

  function storedItem(key) {
    try {
      return nativeGetItem.call(localStorage, key);
    } catch {
      return "";
    }
  }

  function readParams() {
    const query = new URLSearchParams(location.search || "");
    const hashText = location.hash && location.hash.startsWith("#") ? location.hash.slice(1) : "";
    const hash = new URLSearchParams(hashText);
    const path = String(query.get("telegraphPath") || hash.get("telegraphPath") || storedItem(pathKey) || "").trim();
    const token = String(hash.get("telegraphToken") || query.get("telegraphToken") || storedItem(tokenKey) || "").trim();
    if (path) nativeSetItem.call(localStorage, pathKey, path);
    if (token) nativeSetItem.call(localStorage, tokenKey, token);
    if (hash.get("telegraphToken")) {
      hash.delete("telegraphToken");
      const nextHash = hash.toString();
      history.replaceState(null, "", `${location.pathname}${location.search}${nextHash ? `#${nextHash}` : ""}`);
    }
    return { path, token };
  }

  function hasSync() {
    const config = readParams();
    return Boolean(config.path && config.token);
  }

  function keepMessagesReadable(value) {
    if (!hasSync() || typeof value !== "string" || !value.trim()) return value;
    try {
      const state = JSON.parse(value);
      if (!state || typeof state !== "object" || Array.isArray(state)) return value;
      state.inboxAutoFillEnabled = true;
      return JSON.stringify(state);
    } catch {
      return value;
    }
  }

  function clientId() {
    let id = storedItem(clientIdKey);
    if (id) return id;
    id = `phone-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    nativeSetItem.call(localStorage, clientIdKey, id);
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

  function readLocalState() {
    try {
      const state = JSON.parse(storedItem(storageKey) || "{}");
      return state && typeof state === "object" ? state : {};
    } catch {
      return {};
    }
  }

  function taskKey(task) {
    return String(task?.id || `${task?.name || ""}||${task?.due || ""}`);
  }

  function mergeTask(remoteTask, localTask) {
    const next = { ...(remoteTask || {}), ...(localTask || {}) };
    if (remoteTask?.status === "已完成" || localTask?.status === "已完成") {
      next.status = "已完成";
      next.completedAt = localTask?.completedAt || remoteTask?.completedAt || next.completedAt || "";
    }
    return next;
  }

  function mergeArray(remoteItems, localItems, keyFn, mergeFn) {
    const map = new Map();
    (Array.isArray(remoteItems) ? remoteItems : []).forEach(item => map.set(keyFn(item), item));
    (Array.isArray(localItems) ? localItems : []).forEach(item => {
      const key = keyFn(item);
      map.set(key, map.has(key) ? mergeFn(map.get(key), item) : item);
    });
    return [...map.values()];
  }

  function mergeState(remoteState, localState) {
    const remote = remoteState && typeof remoteState === "object" ? remoteState : {};
    const local = localState && typeof localState === "object" ? localState : {};
    const next = { ...remote, ...local };
    next.tasks = mergeArray(remote.tasks, local.tasks, taskKey, mergeTask).sort((a, b) => {
      return String(a.due || "").localeCompare(String(b.due || "")) || String(a.name || "").localeCompare(String(b.name || ""));
    });
    const remoteClear = Number(remote.inboxAutoClearEpoch || 0);
    const localClear = Number(local.inboxAutoClearEpoch || 0);
    if (localClear > remoteClear) {
      next.messages = Array.isArray(local.messages) ? local.messages : [];
    } else if (remoteClear > localClear) {
      next.messages = Array.isArray(remote.messages) ? remote.messages : [];
      next.inboxAutoClearEpoch = remoteClear;
    } else {
      next.messages = mergeArray(remote.messages, local.messages, msg => String(msg?.id || msg?.entryId || msg?.text || ""), (a, b) => ({ ...(a || {}), ...(b || {}) }))
        .sort((a, b) => String(b.time || "").localeCompare(String(a.time || "")));
    }
    next.dailyCheckin = {
      ...(remote.dailyCheckin || {}),
      ...(local.dailyCheckin || {}),
      records: { ...(remote.dailyCheckin?.records || {}), ...(local.dailyCheckin?.records || {}) },
      history: { ...(remote.dailyCheckin?.history || {}), ...(local.dailyCheckin?.history || {}) }
    };
    next.inboxAutoFillEnabled = true;
    return next;
  }

  async function fetchRemoteState() {
    const config = readParams();
    if (!config.path) return null;
    const res = await fetch(`${apiBase}/getPage/${encodeURIComponent(config.path)}?return_content=true&t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Telegraph 读取失败：HTTP ${res.status}`);
    const body = await res.json().catch(() => null);
    if (body?.ok === false) throw new Error(body.error || "Telegraph 返回失败");
    const text = contentText(body?.result?.content);
    if (!text) return null;
    const payload = JSON.parse(text);
    return payload?.state && typeof payload.state === "object" ? payload.state : null;
  }

  async function postRemoteState(state) {
    const config = readParams();
    if (!config.path || !config.token) return false;
    const payload = {
      ok: true,
      updatedAt: new Date().toISOString(),
      clientId: clientId(),
      state: { ...(state || {}), inboxAutoFillEnabled: true }
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
    return true;
  }

  function emitLocalState(state) {
    const text = JSON.stringify({ ...(state || {}), inboxAutoFillEnabled: true });
    applyingRemote = true;
    try {
      nativeSetItem.call(localStorage, storageKey, text);
      nativeSetItem.call(localStorage, pulseKey, String(Date.now()));
      try {
        window.dispatchEvent(new StorageEvent("storage", { key: storageKey, newValue: text }));
      } catch {
        const event = new Event("storage");
        Object.defineProperty(event, "key", { value: storageKey });
        window.dispatchEvent(event);
      }
    } finally {
      applyingRemote = false;
    }
  }

  function setSyncStatus(text, ok = true) {
    ["syncStatus", "syncProbeStatus", "serviceStatus"].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.className = `service-status ${ok ? "ok" : "warn"}`;
      el.textContent = text;
    });
  }

  async function pullAndMerge({ pushMerged = true } = {}) {
    if (!hasSync()) return false;
    const remote = await fetchRemoteState();
    if (!remote) return false;
    const local = readLocalState();
    const merged = mergeState(remote, local);
    emitLocalState(merged);
    if (pushMerged) await postRemoteState(merged);
    setSyncStatus(`云同步已连接：${(merged.tasks || []).length} 项，${(merged.messages || []).length} 条消息。${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`);
    return true;
  }

  function schedulePush(value) {
    if (applyingRemote || !hasSync()) return;
    if (pushTimer) clearTimeout(pushTimer);
    pushTimer = setTimeout(async () => {
      pushTimer = null;
      try {
        const local = value ? JSON.parse(keepMessagesReadable(value)) : readLocalState();
        const remote = await fetchRemoteState().catch(() => null);
        const merged = mergeState(remote, local);
        await postRemoteState(merged);
        emitLocalState(merged);
        setSyncStatus(`已同步到云端：${(merged.tasks || []).length} 项，${(merged.messages || []).length} 条消息。${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`);
      } catch (err) {
        setSyncStatus(`云同步失败：${err.message || err}`, false);
      }
    }, 900);
  }

  try {
    Storage.prototype.getItem = function (key) {
      const value = nativeGetItem.apply(this, arguments);
      if (this !== localStorage || !hasSync()) return value;
      if (key === inboxAutoFillDisableKey) return null;
      if (key === inboxHardClearKey) return "0";
      if (key === storageKey) return keepMessagesReadable(value);
      return value;
    };
    Storage.prototype.setItem = function (key, value) {
      const nextValue = this === localStorage && key === storageKey ? keepMessagesReadable(String(value)) : value;
      nativeSetItem.call(this, key, nextValue);
      if (this === localStorage && key === storageKey) schedulePush(nextValue);
    };
  } catch {
  }

  if (hasSync()) {
    setTimeout(() => pullAndMerge().catch(err => setSyncStatus(`云同步读取失败：${err.message || err}`, false)), 700);
    window.addEventListener("focus", () => pullAndMerge({ pushMerged: false }).catch(() => {}));
    window.addEventListener("visibilitychange", () => {
      if (!document.hidden) pullAndMerge({ pushMerged: false }).catch(() => {});
    });
    setInterval(() => pullAndMerge({ pushMerged: false }).catch(() => {}), 45000);
  }
})();
