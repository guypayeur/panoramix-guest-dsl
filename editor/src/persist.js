/** Stronger-than-sessionStorage editor persistence (localStorage + write-through). */

export const STORAGE_KEY = "guest-dsl-editor-v2";
export const LEGACY_KEY = "guest-dsl-editor-v1";

function storageOf(name) {
  try {
    if (name === "local") return globalThis.localStorage;
    if (name === "session") return globalThis.sessionStorage;
  } catch (_err) {
    return null;
  }
  return null;
}

function readRaw(store, key) {
  if (!store) return null;
  try {
    const raw = store.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch (_err) {
    return null;
  }
}

export function emptyPersist() {
  return {
    token: "",
    user: null,
    specId: "",
    theme: "light",
    persistBySpec: {},
    viewport: { x: 0, y: 0, zoom: 1 },
  };
}

export function loadPersist() {
  const local = storageOf("local");
  const session = storageOf("session");
  const saved =
    readRaw(local, STORAGE_KEY) ||
    readRaw(session, STORAGE_KEY) ||
    readRaw(session, LEGACY_KEY) ||
    readRaw(local, LEGACY_KEY);
  if (!saved || typeof saved !== "object") return emptyPersist();
  return {
    ...emptyPersist(),
    token: saved.token || "",
    user: saved.user || null,
    specId: saved.specId || "",
    theme: saved.theme === "dark" ? "dark" : "light",
    persistBySpec: saved.persistBySpec && typeof saved.persistBySpec === "object" ? saved.persistBySpec : {},
    viewport: saved.viewport && typeof saved.viewport === "object" ? saved.viewport : { x: 0, y: 0, zoom: 1 },
  };
}

export function savePersist(state) {
  const payload = JSON.stringify({
    token: state.token || "",
    user: state.user || null,
    specId: state.specId || "",
    theme: state.theme === "dark" ? "dark" : "light",
    persistBySpec: state.persistBySpec || {},
    viewport: state.viewport || { x: 0, y: 0, zoom: 1 },
  });
  const local = storageOf("local");
  const session = storageOf("session");
  if (local) local.setItem(STORAGE_KEY, payload);
  if (session) session.setItem(STORAGE_KEY, payload);
  return payload;
}

export function specSnapshot(doc, extra = {}) {
  return {
    doc,
    selected: extra.selected || null,
    yaml: extra.yaml || "",
    viewport: extra.viewport || { x: 0, y: 0, zoom: 1 },
    history: extra.history || { past: [], future: [] },
    updatedAt: extra.updatedAt || new Date().toISOString(),
  };
}

export function rememberSpec(persist, specId, snapshot) {
  const key = specId || "_scratch";
  return {
    ...persist,
    specId: specId || persist.specId,
    persistBySpec: {
      ...persist.persistBySpec,
      [key]: snapshot,
    },
  };
}

export function cachedSpec(persist, specId) {
  const key = specId || "_scratch";
  const hit = persist && persist.persistBySpec ? persist.persistBySpec[key] : null;
  return hit && hit.doc ? hit : null;
}
