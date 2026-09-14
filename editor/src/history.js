/** Undo/redo stack for editor documents. No React Flow / dsl-gui imports. */

export function cloneDoc(value) {
  return JSON.parse(JSON.stringify(value));
}

export function docsEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function createHistory(limit = 50) {
  let past = [];
  let future = [];
  const cap = Math.max(1, Number(limit) || 50);

  return {
    push(snapshot) {
      const copy = cloneDoc(snapshot);
      const last = past.length ? past[past.length - 1] : null;
      if (last && docsEqual(last, copy)) return false;
      past.push(copy);
      if (past.length > cap) past.shift();
      future = [];
      return true;
    },
    undo(current) {
      if (!past.length) return null;
      future.push(cloneDoc(current));
      return cloneDoc(past.pop());
    },
    redo(current) {
      if (!future.length) return null;
      past.push(cloneDoc(current));
      return cloneDoc(future.pop());
    },
    canUndo() {
      return past.length > 0;
    },
    canRedo() {
      return future.length > 0;
    },
    size() {
      return { past: past.length, future: future.length };
    },
    reset() {
      past = [];
      future = [];
    },
    hydrate(saved) {
      past = Array.isArray(saved && saved.past) ? saved.past.map(cloneDoc) : [];
      future = Array.isArray(saved && saved.future) ? saved.future.map(cloneDoc) : [];
      if (past.length > cap) past = past.slice(past.length - cap);
      if (future.length > cap) future = future.slice(0, cap);
    },
    dump() {
      return { past: past.map(cloneDoc), future: future.map(cloneDoc) };
    },
  };
}
