import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  STORAGE_KEY,
  LEGACY_KEY,
  cachedSpec,
  emptyPersist,
  loadPersist,
  rememberSpec,
  savePersist,
  shouldReplaceSnapshot,
  specSnapshot,
} from "./persist.js";

function memoryStore() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  };
}

describe("persist", () => {
  beforeEach(() => {
    globalThis.localStorage = memoryStore();
    globalThis.sessionStorage = memoryStore();
  });

  it("roundtrips through localStorage and session write-through", () => {
    const persist = rememberSpec(
      { ...emptyPersist(), token: "abc", specId: "sos", theme: "dark" },
      "sos",
      specSnapshot({ nodes: [{ id: "n1", type: "loop" }], edges: [] }, { yaml: "kind: graph\n" })
    );
    savePersist(persist);
    const rawLocal = JSON.parse(globalThis.localStorage.getItem(STORAGE_KEY));
    const rawSession = JSON.parse(globalThis.sessionStorage.getItem(STORAGE_KEY));
    assert.equal(rawLocal.specId, "sos");
    assert.equal(rawSession.theme, "dark");
    const loaded = loadPersist();
    assert.equal(loaded.token, "abc");
    assert.equal(cachedSpec(loaded, "sos").doc.nodes[0].id, "n1");
  });

  it("migrates legacy sessionStorage drafts across nav", () => {
    globalThis.sessionStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({
        specId: "reserve",
        persistBySpec: { reserve: { doc: { nodes: [{ id: "old" }] }, yaml: "x" } },
      })
    );
    const loaded = loadPersist();
    assert.equal(loaded.specId, "reserve");
    assert.equal(cachedSpec(loaded, "reserve").doc.nodes[0].id, "old");
  });

  it("does not replace a richer draft with an empty boot doc", () => {
    const existing = specSnapshot({ nodes: [{ id: "keep" }], edges: [] });
    assert.equal(shouldReplaceSnapshot(existing, { nodes: [] }), false);
    assert.equal(shouldReplaceSnapshot(existing, { nodes: [{ id: "a" }, { id: "b" }] }), true);
    assert.equal(shouldReplaceSnapshot(null, { nodes: [] }), true);
  });
});
