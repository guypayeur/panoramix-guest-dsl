/** Layered auto-layout. Dagre when available; deterministic columns otherwise. */

import { SCOPE_TYPE, isScope, parentIdOf } from "./scopes.js";

const COLUMNS = {
  dataSource: 0,
  formula: 1,
  loop: 2,
  aggregation: 3,
  [SCOPE_TYPE]: 1,
};

const PAD_X = 28;
const PAD_TOP = 64;
const PAD_BOTTOM = 28;
const NODE_W = 220;
const NODE_H = 88;
const COLLAPSED_H = 72;
const SCOPE_MIN_W = 360;

function columnOf(node) {
  const type = node.type || (node.data && node.data.type);
  return COLUMNS[type] ?? 1;
}

export function nestedLayout(nodes, edges = [], options = {}) {
  const dx = options.dx ?? 240;
  const dy = options.dy ?? 110;
  const originX = options.originX ?? 48;
  const originY = options.originY ?? 48;
  const byParent = new Map();
  for (const node of nodes) {
    const pid = parentIdOf(node);
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid).push(node);
  }
  const placed = new Map();

  function layoutGroup(parentId, ox, oy) {
    const kids = byParent.get(parentId) || [];
    const scopes = kids.filter((node) => isScope(node));
    const leaves = kids.filter((node) => !isScope(node));
    const buckets = [[], [], [], []];
    for (const node of leaves) {
      buckets[columnOf(node)].push(node);
    }
    let maxY = oy;
    let maxX = ox;
    buckets.forEach((bucket, col) => {
      bucket.sort((a, b) => String(a.id).localeCompare(String(b.id)));
      bucket.forEach((node, row) => {
        const x = ox + col * dx;
        const y = oy + row * dy;
        placed.set(node.id, { ...node, position: { x, y }, x, y });
        maxY = Math.max(maxY, y + NODE_H);
        maxX = Math.max(maxX, x + NODE_W);
      });
    });
    let scopeY = leaves.length ? maxY + 24 : oy;
    scopes
      .slice()
      .sort((a, b) => String(a.id).localeCompare(String(b.id)))
      .forEach((scope) => {
        const collapsed = !!(scope.collapsed || (scope.data && scope.data.collapsed));
        const inner = layoutGroup(scope.id, ox + PAD_X, scopeY + PAD_TOP);
        const width = collapsed ? SCOPE_MIN_W : Math.max(SCOPE_MIN_W, inner.maxX - ox + PAD_X);
        const height = collapsed ? COLLAPSED_H : Math.max(160, inner.maxY - scopeY + PAD_BOTTOM);
        placed.set(scope.id, {
          ...scope,
          position: { x: ox, y: scopeY },
          x: ox,
          y: scopeY,
          width,
          height,
          style: { ...(scope.style || {}), width, height },
          data: { ...(scope.data || {}), width, height },
        });
        scopeY += height + 24;
        maxY = Math.max(maxY, scopeY);
        maxX = Math.max(maxX, ox + width);
      });
    return { maxX, maxY };
  }

  layoutGroup("", originX, originY);
  return nodes.map((node) => placed.get(node.id) || node);
}

export function simpleLayout(nodes, edges = [], options = {}) {
  if ((nodes || []).some((node) => isScope(node) || parentIdOf(node)) && options.flat !== true) {
    return nestedLayout(nodes, edges, options);
  }
  const dx = options.dx ?? 280;
  const dy = options.dy ?? 130;
  const originX = options.originX ?? 48;
  const originY = options.originY ?? 48;
  const buckets = [[], [], [], []];
  for (const node of nodes) {
    buckets[columnOf(node)].push(node);
  }
  const incoming = new Map();
  for (const edge of edges) {
    if (!incoming.has(edge.target)) incoming.set(edge.target, []);
    incoming.get(edge.target).push(edge.source);
  }
  for (const bucket of buckets) {
    bucket.sort((a, b) => String(a.id).localeCompare(String(b.id)));
  }
  const placed = [];
  buckets.forEach((bucket, col) => {
    bucket.forEach((node, row) => {
      placed.push({
        ...node,
        position: {
          x: originX + col * dx,
          y: originY + row * dy,
        },
        x: originX + col * dx,
        y: originY + row * dy,
      });
    });
  });
  return placed;
}

export function dagreLayout(dagre, nodes, edges = [], options = {}) {
  const compound = (nodes || []).some((node) => isScope(node) || parentIdOf(node));
  if (compound && options.flat !== true) {
    return nestedLayout(nodes, edges, options);
  }
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: options.rankdir || "LR",
    nodesep: options.nodesep ?? 56,
    ranksep: options.ranksep ?? 90,
    marginx: options.marginx ?? 24,
    marginy: options.marginy ?? 24,
  });
  const width = options.width ?? 220;
  const height = options.height ?? 88;
  for (const node of nodes) {
    graph.setNode(node.id, { width, height });
  }
  for (const edge of edges) {
    if (edge.source && edge.target) graph.setEdge(edge.source, edge.target);
  }
  dagre.layout(graph);
  return nodes.map((node) => {
    const placed = graph.node(node.id) || { x: node.position?.x || 0, y: node.position?.y || 0 };
    const x = placed.x - width / 2;
    const y = placed.y - height / 2;
    return { ...node, position: { x, y }, x, y };
  });
}

export async function autoLayout(nodes, edges = [], options = {}) {
  if (options.engine === "simple") {
    return simpleLayout(nodes, edges, options);
  }
  try {
    const mod = await import("@dagrejs/dagre");
    const dagre = mod.default || mod;
    if (dagre && dagre.graphlib) {
      return dagreLayout(dagre, nodes, edges, options);
    }
  } catch (_err) {
    /* guest stays runnable without the npm graph — fall back */
  }
  return simpleLayout(nodes, edges, options);
}
