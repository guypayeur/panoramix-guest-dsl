/** G9 Matryoshka nested-scope helpers — compound parent/child + drill-in. */

export const SCOPE_TYPE = "scope";
export const COLLAPSED_HEIGHT = 72;
export const SCOPE_MIN_WIDTH = 360;
export const SCOPE_MIN_HEIGHT = 160;
export const LEAF_WIDTH = 220;
export const LEAF_HEIGHT = 88;

export function isScope(node) {
  const type = node && (node.type || (node.data && node.data.type));
  return type === SCOPE_TYPE;
}

export function parentIdOf(node) {
  if (!node) return "";
  return node.parentId || (node.data && node.data.parentId) || "";
}

export function nodesById(nodes) {
  return Object.fromEntries((nodes || []).map((node) => [node.id, node]));
}

export function ancestorsOf(nodeId, nodes) {
  const byId = nodesById(nodes);
  const path = [];
  const seen = new Set();
  let current = byId[nodeId];
  while (current && parentIdOf(current) && !seen.has(parentIdOf(current))) {
    const parent = byId[parentIdOf(current)];
    if (!parent) break;
    seen.add(parent.id);
    path.push(parent);
    current = parent;
  }
  return path;
}

export function descendantsOf(nodeId, nodes) {
  const kids = new Map();
  for (const node of nodes || []) {
    const pid = parentIdOf(node);
    if (!kids.has(pid)) kids.set(pid, []);
    kids.get(pid).push(node);
  }
  const out = [];
  const stack = [...(kids.get(nodeId) || [])];
  const seen = new Set();
  while (stack.length) {
    const node = stack.pop();
    if (!node || seen.has(node.id)) continue;
    seen.add(node.id);
    out.push(node);
    stack.push(...(kids.get(node.id) || []));
  }
  return out;
}

export function childrenOf(nodeId, nodes) {
  return (nodes || []).filter((node) => parentIdOf(node) === nodeId);
}

export function collapsedScopeIds(nodes) {
  return new Set(
    (nodes || [])
      .filter((node) => isScope(node) && (node.collapsed || (node.data && node.data.collapsed)))
      .map((node) => node.id)
  );
}

export function isHiddenByCollapse(node, nodes, collapsed, focusId) {
  const closed = collapsed || collapsedScopeIds(nodes);
  const focusAncestors = focusId ? new Set(ancestorsOf(focusId, nodes).map((item) => item.id)) : new Set();
  for (const ancestor of ancestorsOf(node.id, nodes)) {
    if (ancestor.id === focusId || focusAncestors.has(ancestor.id)) continue;
    if (closed.has(ancestor.id)) return true;
  }
  return false;
}

export function isInFocus(node, focusId, nodes) {
  if (!focusId) return true;
  if (node.id === focusId) return true;
  return descendantsOf(focusId, nodes).some((item) => item.id === node.id);
}

export function crumbPath(nodes, focusId) {
  if (!focusId) return [];
  const byId = nodesById(nodes);
  const path = [];
  const seen = new Set();
  let current = byId[focusId];
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    path.unshift({ id: current.id, label: current.label || (current.data && current.data.label) || current.id });
    const pid = parentIdOf(current);
    current = pid ? byId[pid] : null;
  }
  return path;
}

export function absolutePos(node) {
  return { x: Number(node && node.x) || 0, y: Number(node && node.y) || 0 };
}

export function relativePosition(node, nodes, focusId) {
  if (focusId && node.id === focusId) return { x: 0, y: 0 };
  const byId = nodesById(nodes);
  const abs = absolutePos(node);
  const pid = parentIdOf(node);
  if (!pid || node.id === focusId) return abs;
  const parent = byId[pid];
  if (!parent) return abs;
  const p = absolutePos(parent);
  return { x: abs.x - p.x, y: abs.y - p.y };
}

export function parentForFlow(node, focusId) {
  const pid = parentIdOf(node);
  if (!pid) return undefined;
  if (node.id === focusId) return undefined;
  return pid;
}

export function toggleCollapsed(nodes, scopeId) {
  return (nodes || []).map((node) =>
    node.id === scopeId ? { ...node, collapsed: !node.collapsed } : node
  );
}

export function scopeBoxStyle(node) {
  const collapsed = !!(node.collapsed || (node.data && node.data.collapsed));
  const width = Number(node.width || (node.data && node.data.width) || SCOPE_MIN_WIDTH);
  const height = collapsed
    ? COLLAPSED_HEIGHT
    : Number(node.height || (node.data && node.data.height) || SCOPE_MIN_HEIGHT);
  return { width, height };
}
