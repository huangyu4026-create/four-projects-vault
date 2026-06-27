const FILE_NAME = "work-life-mobile-shared-state.json";

function doGet() {
  return json(loadPayload());
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  lock.waitLock(5000);
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    const current = loadPayload();
    const state = body && body.state && typeof body.state === "object" ? body.state : current.state || {};
    const payload = {
      ok: true,
      updatedAt: new Date().toISOString(),
      clientId: body.clientId || "",
      state
    };
    savePayload(payload);
    return json(payload);
  } catch (err) {
    return json({ ok: false, error: String(err && err.message ? err.message : err) });
  } finally {
    lock.releaseLock();
  }
}

function loadPayload() {
  const file = getOrCreateFile();
  try {
    const text = file.getBlob().getDataAsString("UTF-8");
    const payload = JSON.parse(text || "{}");
    return {
      ok: true,
      updatedAt: payload.updatedAt || "",
      clientId: payload.clientId || "",
      state: payload.state && typeof payload.state === "object" ? payload.state : {}
    };
  } catch (err) {
    return { ok: true, updatedAt: "", clientId: "", state: {} };
  }
}

function savePayload(payload) {
  getOrCreateFile().setContent(JSON.stringify(payload, null, 2));
}

function getOrCreateFile() {
  const files = DriveApp.getFilesByName(FILE_NAME);
  if (files.hasNext()) return files.next();
  return DriveApp.createFile(FILE_NAME, JSON.stringify({ ok: true, updatedAt: "", state: {} }, null, 2), MimeType.PLAIN_TEXT);
}

function json(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
