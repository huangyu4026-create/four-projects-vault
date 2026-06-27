const STORE_KEY = "work-life-mobile-shared-state";
const CHUNK_SIZE = 8000;
const CHUNK_COUNT_KEY = `${STORE_KEY}:chunk-count`;
const CHUNK_PREFIX = `${STORE_KEY}:chunk:`;
const EMPTY_PAYLOAD = {
  ok: true,
  updatedAt: "",
  clientId: "",
  state: {}
};

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
  try {
    const props = PropertiesService.getScriptProperties();
    const text = readChunkedPayload(props) || props.getProperty(STORE_KEY);
    const payload = JSON.parse(text || "{}");
    return {
      ok: true,
      updatedAt: payload.updatedAt || "",
      clientId: payload.clientId || "",
      state: payload.state && typeof payload.state === "object" ? payload.state : {}
    };
  } catch (err) {
    return EMPTY_PAYLOAD;
  }
}

function savePayload(payload) {
  const props = PropertiesService.getScriptProperties();
  const text = JSON.stringify(payload);
  const oldCount = Number(props.getProperty(CHUNK_COUNT_KEY) || 0);
  const chunks = [];
  for (let i = 0; i < text.length; i += CHUNK_SIZE) {
    chunks.push(text.slice(i, i + CHUNK_SIZE));
  }
  const values = {};
  values[CHUNK_COUNT_KEY] = String(chunks.length);
  chunks.forEach((chunk, index) => {
    values[`${CHUNK_PREFIX}${index}`] = chunk;
  });
  props.setProperties(values, false);
  props.deleteProperty(STORE_KEY);
  for (let index = chunks.length; index < oldCount; index += 1) {
    props.deleteProperty(`${CHUNK_PREFIX}${index}`);
  }
}

function readChunkedPayload(props) {
  const count = Number(props.getProperty(CHUNK_COUNT_KEY) || 0);
  if (!count) return "";
  const chunks = [];
  for (let index = 0; index < count; index += 1) {
    chunks.push(props.getProperty(`${CHUNK_PREFIX}${index}`) || "");
  }
  return chunks.join("");
}

function json(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
