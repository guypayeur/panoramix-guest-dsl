/** Sugiyama / ELK Layered auto-layout for the React Flow canvas.
 *
 * Compound (Matryoshka) graphs use elkjs `layered` with
 * `elk.hierarchyHandling: INCLUDE_CHILDREN` so cross-scope edges participate
 * in one run. Child coordinates are parent-relative (React Flow convention).
 * If elkjs fails to load, `layeredLayout` is a deterministic edge-aware
 * fallback — longest-path layers + barycenter ordering — not type columns.
 */

import { SCOPE_TYPE, isScope, parentIdOf } from "./scopes.js";

const COLUMNS = {
  dataSource: 0,
  formula: 1,
  loop: 2,
  aggregation: 3,
  [SCOPE_TYPE]: 1,
};

const TYPE_RANK = {
  dataSource: 0,
  formula: 1,
  loop: 2,
  aggregation: 3,
  [SCOPE_TYPE]: 2,
};

const PAD_X = 32;
const PAD_TOP = 72;
const PAD_BOTTOM = 32;
const NODE_W = 220;
const NODE_H = 96;
const COLLAPSED_H = 72;
const SCOPE_MIN_W = 360;
const SCOPE_MIN_H = 160;
const NODE_SEP = 48;
const LAYER_SEP = 88;

function columnOf(node) {
  const type = node.type || (node.data && node.data.type);
  return COLUMNS[type] ?? 1;
}

function typeRankOf(node) {
  const type = node.type || (node.data && node.data.type);
  return TYPE_RANK[type] ?? 1;
}

function isCollapsed(node) {
  return !!(node && (node.collapsed || (node.data && node.data.collapsed)));
}

function nodeSize(node, options = {}) {
  const fallbackW = options.width ?? NODE_W;
  const fallbackH = options.height ?? NODE_H;
  const measured = node.measured || {};
  const style = node.style || {};
  const data = node.data || {};
  if (isScope(node) && isCollapsed(node)) {
    return {
      width: Number(style.width || data.width || node.width || SCOPE_MIN_W) || SCOPE_MIN_W,
      height: COLLAPSED_H,
    };
  }
  const width =
    Number(measured.width || style.width || data.width || node.width || 0) ||
    (isScope(node) ? SCOPE_MIN_W : fallbackW);
  const height =
    Number(measured.height || style.height || data.height || node.height || 0) ||
    (isScope(node) ? SCOPE_MIN_H : fallbackH);
  return { width, height };
}

function posOf(node) {
  if (node.position && Number.isFinite(node.position.x) && Number.isFinite(node.position.y)) {
    return { x: node.position.x, y: node.position.y };
  }
  return { x: Number(node.x) || 0, y: Number(node.y) || 0 };
}

function aabbOverlap(a, b, slack = 0) {
  return (
    a.x + slack < b.x + b.w &&
    a.x + a.w > b.x + slack &&
    a.y + slack < b.y + b.h &&
    a.y + a.h > b.y + slack
  );
}

export function looksPiled(nodes, options = {}) {
  const byParent = new Map();
  for (const node of nodes || []) {
    if (node.hidden) continue;
    const pid = parentIdOf(node);
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid).push(node);
  }
  let overlaps = 0;
  for (const kids of byParent.values()) {
    const boxes = kids.map((node) => {
      const p = posOf(node);
      const size = nodeSize(node, options);
      return { x: p.x, y: p.y, w: size.width, h: size.height };
    });
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        if (aabbOverlap(boxes[i], boxes[j], 8)) overlaps += 1;
      }
    }
  }
  return overlaps >= (options.threshold ?? 2);
}

function decorate(node, x, y, width, height) {
  const next = {
    ...node,
    position: { x, y },
    x,
    y,
  };
  if (isScope(node) || width != null) {
    next.width = width;
    next.height = height;
    next.style = { ...(node.style || {}), width, height };
    next.data = { ...(node.data || {}), width, height };
  }
  return next;
}

function groupByParent(nodes) {
  const byParent = new Map();
  for (const node of nodes || []) {
    const pid = parentIdOf(node);
    if (!byParent.has(pid)) byParent.set(pid, []);
    byParent.get(pid).push(node);
  }
  return byParent;
}

function parentMap(nodes) {
  const out = new Map();
  for (const node of nodes || []) {
    out.set(node.id, parentIdOf(node));
  }
  return out;
}

function promoteEndpoint(nodeId, groupIds, parents) {
  let current = nodeId;
  const seen = new Set();
  while (current && !seen.has(current)) {
    if (groupIds.has(current)) return current;
    seen.add(current);
    current = parents.get(current) || "";
  }
  return "";
}

function breakCycles(ids, adj) {
  const state = new Map();
  const reversed = new Set();
  function dfs(u) {
    state.set(u, 1);
    for (const v of adj.get(u) || []) {
      if (state.get(v) === 1) {
        reversed.add(u + "->" + v);
      } else if (state.get(v) !== 2) {
        dfs(v);
      }
    }
    state.set(u, 2);
  }
  for (const id of ids) {
    if (!state.has(id)) dfs(id);
  }
  return reversed;
}

function longestPathRanks(ids, fwd) {
  const indeg = new Map(ids.map((id) => [id, 0]));
  for (const id of ids) {
    for (const v of fwd.get(id) || []) {
      indeg.set(v, (indeg.get(v) || 0) + 1);
    }
  }
  const rank = new Map(ids.map((id) => [id, 0]));
  const queue = ids.filter((id) => (indeg.get(id) || 0) === 0);
  const seen = new Set();
  while (queue.length) {
    const u = queue.shift();
    if (seen.has(u)) continue;
    seen.add(u);
    for (const v of fwd.get(u) || []) {
      rank.set(v, Math.max(rank.get(v) || 0, (rank.get(u) || 0) + 1));
      indeg.set(v, (indeg.get(v) || 0) - 1);
      if ((indeg.get(v) || 0) === 0) queue.push(v);
    }
  }
  return rank;
}

function barycenterOrder(layers, fwd, back, sweeps = 3) {
  const ordered = layers.map((layer) => layer.slice());
  const indexOf = new Map();
  function reindex() {
    indexOf.clear();
    ordered.forEach((layer, li) => {
      layer.forEach((id, idx) => indexOf.set(id, { li, idx }));
    });
  }
  reindex();
  for (let sweep = 0; sweep < sweeps; sweep++) {
    const forward = sweep % 2 === 0;
    const seq = forward ? [...ordered.keys()] : [...ordered.keys()].reverse();
    for (const li of seq) {
      if ((forward && li === 0) || (!forward && li === ordered.length - 1)) continue;
      const neigh = forward ? back : fwd;
      ordered[li].sort((a, b) => {
        const avg = (id) => {
          const xs = (neigh.get(id) || [])
            .map((n) => indexOf.get(n))
            .filter(Boolean)
            .map((hit) => hit.idx);
          if (!xs.length) return indexOf.get(id)?.idx ?? 0;
          return xs.reduce((s, n) => s + n, 0) / xs.length;
        };
        const d = avg(a) - avg(b);
        return d !== 0 ? d : String(a).localeCompare(String(b));
      });
    }
    reindex();
  }
  return ordered;
}

function packLayer(ids, sizes, nodeSep) {
  const height = ids.reduce((sum, id, i) => sum + sizes.get(id).height + (i ? nodeSep : 0), 0);
  const width = Math.max(0, ...ids.map((id) => sizes.get(id).width));
  return { width, height };
}

function assignLayerCoords(ordered, sizes, originX, originY, layerSep, nodeSep) {
  const coords = new Map();
  let x = originX;
  for (const layer of ordered) {
    const pack = packLayer(layer, sizes, nodeSep);
    let y = originY;
    for (const id of layer) {
      const size = sizes.get(id);
      coords.set(id, { x, y, width: size.width, height: size.height });
      y += size.height + nodeSep;
    }
    x += pack.width + layerSep;
  }
  return coords;
}

function sugiyamaPlace(items, edges, options = {}) {
  const originX = options.originX ?? 0;
  const originY = options.originY ?? 0;
  const nodeSep = options.nodeSep ?? NODE_SEP;
  const layerSep = options.layerSep ?? LAYER_SEP;
  const ids = items.map((item) => item.id);
  const idSet = new Set(ids);
  const sizes = new Map(items.map((item) => [item.id, { width: item.width, height: item.height }]));
  const byId = new Map(items.map((item) => [item.id, item]));

  const rawFwd = new Map(ids.map((id) => [id, []]));
  for (const edge of edges) {
    if (!idSet.has(edge.source) || !idSet.has(edge.target) || edge.source === edge.target) continue;
    rawFwd.get(edge.source).push(edge.target);
  }
  const reversed = breakCycles(ids, rawFwd);
  const fwd = new Map(ids.map((id) => [id, []]));
  const back = new Map(ids.map((id) => [id, []]));
  for (const edge of edges) {
    if (!idSet.has(edge.source) || !idSet.has(edge.target) || edge.source === edge.target) continue;
    let source = edge.source;
    let target = edge.target;
    if (reversed.has(source + "->" + target)) {
      const tmp = source;
      source = target;
      target = tmp;
    }
    if (!fwd.get(source).includes(target)) fwd.get(source).push(target);
    if (!back.get(target).includes(source)) back.get(target).push(source);
  }

  const connected = new Set();
  for (const id of ids) {
    if ((fwd.get(id) || []).length || (back.get(id) || []).length) connected.add(id);
  }
  const rank = longestPathRanks(ids, fwd);
  for (const id of ids) {
    if (!connected.has(id)) rank.set(id, typeRankOf(byId.get(id).node));
  }
  const maxRank = Math.max(0, ...[...rank.values()]);
  const layers = Array.from({ length: maxRank + 1 }, () => []);
  for (const id of ids) layers[rank.get(id) || 0].push(id);
  for (const layer of layers) layer.sort((a, b) => String(a).localeCompare(String(b)));
  const nonempty = layers.filter((layer) => layer.length);
  const ordered = barycenterOrder(nonempty, fwd, back);
  return assignLayerCoords(ordered, sizes, originX, originY, layerSep, nodeSep);
}

/** Edge-aware layered layout. Parent-relative child coords. */
export function layeredLayout(nodes, edges = [], options = {}) {
  const originX = options.originX ?? 48;
  const originY = options.originY ?? 48;
  const visible = (nodes || []).filter((node) => !node.hidden);
  const hidden = (nodes || []).filter((node) => node.hidden);
  const byParent = groupByParent(visible);
  const parents = parentMap(visible);
  const placed = new Map();

  function layoutGroup(parentId, ox, oy) {
    const kids = (byParent.get(parentId) || []).slice();
    if (!kids.length) return { maxX: ox, maxY: oy };

    const sizes = new Map();
    for (const kid of kids) {
      if (isScope(kid) && !isCollapsed(kid)) {
        const inner = layoutGroup(kid.id, PAD_X, PAD_TOP);
        const width = Math.max(SCOPE_MIN_W, inner.maxX + PAD_X);
        const height = Math.max(SCOPE_MIN_H, inner.maxY + PAD_BOTTOM);
        sizes.set(kid.id, { width, height });
      } else {
        sizes.set(kid.id, nodeSize(kid, options));
      }
    }

    const groupIds = new Set(kids.map((kid) => kid.id));
    const promoted = [];
    const seen = new Set();
    for (const edge of edges || []) {
      const source = promoteEndpoint(edge.source, groupIds, parents);
      const target = promoteEndpoint(edge.target, groupIds, parents);
      if (!source || !target || source === target) continue;
      if (!groupIds.has(source) || !groupIds.has(target)) continue;
      const key = source + "->" + target;
      if (seen.has(key)) continue;
      seen.add(key);
      promoted.push({ source, target });
    }

    const items = kids.map((kid) => ({
      id: kid.id,
      width: sizes.get(kid.id).width,
      height: sizes.get(kid.id).height,
      node: kid,
    }));
    const coords = sugiyamaPlace(items, promoted, {
      originX: ox,
      originY: oy,
      nodeSep: options.nodeSep ?? NODE_SEP,
      layerSep: options.layerSep ?? LAYER_SEP,
    });

    let maxX = ox;
    let maxY = oy;
    for (const kid of kids) {
      const box = coords.get(kid.id) || { x: ox, y: oy, ...sizes.get(kid.id) };
      placed.set(kid.id, decorate(kid, box.x, box.y, box.width, box.height));
      maxX = Math.max(maxX, box.x + box.width);
      maxY = Math.max(maxY, box.y + box.height);
    }
    return { maxX, maxY };
  }

  layoutGroup("", originX, originY);
  return nodes.map((node) => placed.get(node.id) || hidden.find((item) => item.id === node.id) || node);
}

/** Legacy type-column helper for flat graphs. Compound graphs use layeredLayout. */
export function nestedLayout(nodes, edges = [], options = {}) {
  return layeredLayout(nodes, edges, options);
}

export function simpleLayout(nodes, edges = [], options = {}) {
  if ((nodes || []).some((node) => isScope(node) || parentIdOf(node)) && options.flat !== true) {
    return layeredLayout(nodes, edges, options);
  }
  const dx = options.dx ?? 280;
  const dy = options.dy ?? 130;
  const originX = options.originX ?? 48;
  const originY = options.originY ?? 48;
  const buckets = [[], [], [], []];
  for (const node of nodes) {
    buckets[columnOf(node)].push(node);
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

function elkPadding(top, left, bottom, right) {
  return `[top=${top},left=${left},bottom=${bottom},right=${right}]`;
}

function toElkNode(node, byParent, options) {
  const size = nodeSize(node, options);
  const kids = isCollapsed(node) ? [] : byParent.get(node.id) || [];
  const elk = {
    id: node.id,
    width: size.width,
    height: size.height,
  };
  if (isScope(node)) {
    elk.layoutOptions = {
      "elk.padding": elkPadding(PAD_TOP, PAD_X, PAD_BOTTOM, PAD_X),
    };
  }
  if (kids.length) {
    elk.children = kids.map((kid) => toElkNode(kid, byParent, options));
  }
  return elk;
}

function flattenElk(elkNode, byId, placed) {
  if (elkNode.id && elkNode.id !== "root" && byId.has(elkNode.id)) {
    const node = byId.get(elkNode.id);
    const x = Number(elkNode.x) || 0;
    const y = Number(elkNode.y) || 0;
    const width = Number(elkNode.width) || nodeSize(node).width;
    const height = Number(elkNode.height) || nodeSize(node).height;
    placed.set(elkNode.id, decorate(node, x, y, width, height));
  }
  for (const child of elkNode.children || []) {
    flattenElk(child, byId, placed);
  }
}

export async function elkLayout(nodes, edges = [], options = {}) {
  const elkLib = options.elk || (await loadElk());
  if (!elkLib) throw new Error("elkjs unavailable");
  const visible = (nodes || []).filter((node) => !node.hidden);
  const byParent = groupByParent(visible);
  const byId = new Map(visible.map((node) => [node.id, node]));
  const roots = visible.filter((node) => {
    const pid = parentIdOf(node);
    return !pid || !byId.has(pid);
  });
  const visibleIds = new Set(visible.map((node) => node.id));
  const elkEdges = [];
  const seen = new Set();
  for (const edge of edges || []) {
    if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) continue;
    const id = edge.id || edge.source + "->" + edge.target;
    if (seen.has(id)) continue;
    seen.add(id);
    elkEdges.push({ id, sources: [edge.source], targets: [edge.target] });
  }
  const graph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": options.direction || "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.padding": elkPadding(48, 48, 48, 48),
      "elk.spacing.nodeNode": String(options.nodeSep ?? NODE_SEP),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(options.layerSep ?? LAYER_SEP),
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
    },
    children: roots.map((node) => toElkNode(node, byParent, options)),
    edges: elkEdges,
  };
  const laid = await elkLib.layout(graph);
  const placed = new Map();
  flattenElk(laid, byId, placed);
  return nodes.map((node) => placed.get(node.id) || node);
}

let elkPromise = null;
async function loadElk() {
  if (elkPromise) return elkPromise;
  elkPromise = (async () => {
    try {
      const mod = await import("elkjs/lib/elk.bundled.js");
      const ELK = mod.default || mod.ELK || mod;
      if (typeof ELK !== "function") return null;
      return new ELK();
    } catch (_err) {
      return null;
    }
  })();
  return elkPromise;
}

export function dagreLayout(dagre, nodes, edges = [], options = {}) {
  const compound = (nodes || []).some((node) => isScope(node) || parentIdOf(node));
  if (compound && options.flat !== true) {
    return layeredLayout(nodes, edges, options);
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
  const width = options.width ?? NODE_W;
  const height = options.height ?? NODE_H;
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
  if (options.engine === "layered") {
    return layeredLayout(nodes, edges, options);
  }
  if (options.engine === "dagre") {
    try {
      const mod = await import("@dagrejs/dagre");
      const dagre = mod.default || mod;
      if (dagre && dagre.graphlib) return dagreLayout(dagre, nodes, edges, options);
    } catch (_err) {
      /* fall through */
    }
    return layeredLayout(nodes, edges, options);
  }
  try {
    return await elkLayout(nodes, edges, options);
  } catch (_err) {
    /* guest stays runnable without elkjs — edge-aware fallback, not type columns */
  }
  return layeredLayout(nodes, edges, options);
}
