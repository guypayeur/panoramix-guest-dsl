/** Guest graph helpers — canvas document ↔ React Flow nodes/edges. */

import { estimateNodeSize } from "./layout.js";
import {
  SCOPE_TYPE,
  ancestorsOf,
  childrenOf,
  isHiddenByCollapse,
  isInFocus,
  isScope,
  parentForFlow,
  parentIdOf,
  relativePosition,
  scopeBoxStyle,
} from "./scopes.js";

function sortParentsFirst(nodes) {
  return [...nodes].sort((left, right) => {
    const ld = ancestorsOf(left.id, nodes).length;
    const rd = ancestorsOf(right.id, nodes).length;
    if (ld !== rd) return ld - rd;
    if (isScope(left) !== isScope(right)) return isScope(left) ? -1 : 1;
    return 0;
  });
}

export const NODE_TYPES = ["dataSource", "loop", "formula", "aggregation"];
export { SCOPE_TYPE };

export function emptyDoc() {
  return { metadata: {}, description: "", nodes: [], edges: [], extras: {}, stub: true };
}

export function newId(prefix) {
  return prefix + "-" + Math.random().toString(36).slice(2, 8);
}

export function blankNode(type, existing = []) {
  const id = newId(type === "dataSource" ? "ds" : type);
  const slots = {
    dataSource: { x: 48, y: 48, label: "DataSource" },
    loop: { x: 48, y: 230, label: "Loop" },
    formula: { x: 340, y: 48, label: "Formula" },
    aggregation: { x: 340, y: 230, label: "Aggregation" },
  };
  const same = existing.filter((node) => node.type === type).length;
  const slot = slots[type] || { x: 80, y: 80, label: type };
  const base = {
    id,
    type,
    label: slot.label,
    x: slot.x + same * 36,
    y: slot.y + same * 24,
  };
  if (type === "dataSource") {
    return { ...base, filename: "", context: "outer", provides: [], index: [], column_map: {} };
  }
  if (type === "loop") {
    return { ...base, loopType: "outer", dimension: "T_OUTER", size: 1, vectorize: [] };
  }
  if (type === "formula") {
    return { ...base, section: "step", formulas: { RESULT: "INPUT" } };
  }
  return {
    ...base,
    variable: "RESULT",
    condition: { variable: "AGE", operator: "==", value: 0 },
    reduce: "mean",
    over: "S_INNER",
  };
}

export function nodeSummary(node) {
  if (!node) return "";
  if (node.type === "dataSource") return node.filename || "(no filename)";
  if (node.type === "loop") return (node.loopType || "outer") + " · " + (node.dimension || "");
  if (node.type === "formula") {
    return (node.section || "step") + " · " + Object.keys(node.formulas || {}).join(", ");
  }
  if (node.type === SCOPE_TYPE) {
    const dims = (node.dimensions || []).join(", ");
    return (node.scopeKind || "outer") + (dims ? " · " + dims : "");
  }
  return (node.reduce || "mean") + " " + (node.variable || "");
}

export function toFlow(doc, selectedId, options = {}) {
  const catalog = sortParentsFirst(doc.nodes || []);
  const focusId = options.focusScopeId || null;
  const handlers = {
    onToggleScope: options.onToggleScope,
    onDrillIn: options.onDrillIn,
  };
  const nodes = catalog.map((node) => {
    const hidden = !isInFocus(node, focusId, catalog) || isHiddenByCollapse(node, catalog, null, focusId);
    const parentId = parentForFlow(node, focusId);
    const box = isScope(node) ? scopeBoxStyle(node) : estimateNodeSize(node);
    return {
      id: node.id,
      type: node.type,
      position: relativePosition(node, catalog, focusId),
      parentId,
      extent: parentId ? "parent" : undefined,
      hidden,
      width: box.width,
      height: box.height,
      style: box,
      data: {
        ...node,
        childCount: childrenOf(node.id, catalog).length,
        ...handlers,
      },
      selected: selectedId ? node.id === selectedId : undefined,
    };
  });
  const edges = (doc.edges || []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "smoothstep",
    hidden: !nodes.some((node) => node.id === edge.source && !node.hidden) ||
      !nodes.some((node) => node.id === edge.target && !node.hidden),
  }));
  return { nodes, edges };
}

function absoluteFromFlow(flowNode, flowById, previous, cache, walking) {
  if (cache.has(flowNode.id)) return cache.get(flowNode.id);
  if (walking.has(flowNode.id)) {
    const prior = previous[flowNode.id] || {};
    return { x: prior.x || 0, y: prior.y || 0 };
  }
  walking.add(flowNode.id);
  const prior = previous[flowNode.id] || {};
  if (flowNode.hidden) {
    const kept = { x: prior.x || 0, y: prior.y || 0 };
    cache.set(flowNode.id, kept);
    return kept;
  }
  const px = flowNode.position ? flowNode.position.x : prior.x || 0;
  const py = flowNode.position ? flowNode.position.y : prior.y || 0;
  const rfParent = flowNode.parentId;
  if (!rfParent || !flowById[rfParent]) {
    let next = { x: px, y: py };
    if (prior.parentId && px === 0 && py === 0) {
      next = { x: prior.x || 0, y: prior.y || 0 };
    }
    cache.set(flowNode.id, next);
    return next;
  }
  const parentAbs = absoluteFromFlow(flowById[rfParent], flowById, previous, cache, walking);
  const next = { x: parentAbs.x + px, y: parentAbs.y + py };
  cache.set(flowNode.id, next);
  return next;
}

export function fromFlow(nodes, edges, doc) {
  const previous = Object.fromEntries((doc.nodes || []).map((node) => [node.id, node]));
  const flowById = Object.fromEntries((nodes || []).map((node) => [node.id, node]));
  const cache = new Map();
  const seen = new Set();
  function materialize(node) {
    const data = node.data || {};
    const prior = previous[node.id] || {};
    const abs = absoluteFromFlow(node, flowById, previous, cache, new Set());
    const next = {
      ...prior,
      ...data,
      id: node.id,
      type: node.type || data.type || prior.type,
      label: data.label || prior.label || node.id,
      x: abs.x,
      y: abs.y,
      parentId: data.parentId || prior.parentId || parentIdOf(node) || "",
    };
    delete next.onToggleScope;
    delete next.onDrillIn;
    delete next.childCount;
    if (node.style || node.width || node.height) {
      next.width = Number(node.width || (node.style && node.style.width) || next.width) || next.width;
      next.height = Number(node.height || (node.style && node.style.height) || next.height) || next.height;
    }
    seen.add(node.id);
    return next;
  }
  const ordered = [];
  for (const prior of doc.nodes || []) {
    if (flowById[prior.id]) ordered.push(materialize(flowById[prior.id]));
  }
  for (const node of nodes || []) {
    if (!seen.has(node.id)) ordered.push(materialize(node));
  }
  return {
    ...doc,
    stub: false,
    nodes: ordered,
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    })),
  };
}

export function csv(value) {
  return String(value || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

export function parseFormulas(text) {
  const out = {};
  String(text || "")
    .split("\n")
    .forEach((line) => {
      const idx = line.indexOf(":");
      if (idx === -1) return;
      const key = line.slice(0, idx).trim();
      if (key) out[key] = line.slice(idx + 1).trim();
    });
  return out;
}

export function applyPanelFields(node, fields) {
  const next = { ...node };
  const nextId = String(fields.id || node.id).trim() || node.id;
  next.id = nextId;
  next.label = String(fields.label || node.label || "");
  if (node.type === "dataSource") {
    next.filename = String(fields.filename || "");
    next.context = String(fields.context || "outer");
    next.provides = csv(fields.provides);
    next.index = csv(fields.index);
  } else if (node.type === "loop") {
    next.loopType = String(fields.loopType || "outer");
    next.dimension = String(fields.dimension || "");
    const size = Number(fields.size);
    next.size = Number.isFinite(size) ? size : null;
    next.vectorize = csv(fields.vectorize);
  } else if (node.type === "formula") {
    next.section = String(fields.section || "step");
    next.formulas = parseFormulas(fields.formulas);
  } else if (node.type === "aggregation") {
    next.variable = String(fields.variable || "");
    next.condition = {
      variable: String(fields.condVar || ""),
      operator: String(fields.condOp || "=="),
      value: Number(fields.condValue || 0),
    };
    next.reduce = String(fields.reduce || "mean");
    next.over = String(fields.over || "");
  } else if (node.type === SCOPE_TYPE) {
    next.scopeKind = String(fields.scopeKind || node.scopeKind || "outer");
    next.dimensions = csv(fields.dimensions);
    next.collapsed = !!fields.collapsed;
  }
  if (fields.parentId !== undefined) {
    next.parentId = String(fields.parentId || "");
  }
  return next;
}

export function retargetEdges(edges, fromId, toId) {
  if (fromId === toId) return edges;
  return (edges || []).map((edge) => ({
    ...edge,
    source: edge.source === fromId ? toId : edge.source,
    target: edge.target === fromId ? toId : edge.target,
  }));
}

export function classesForLabel(label) {
  if (label === "cpu") return ["cpu"];
  if (label === "gpu") return ["gpu"];
  return ["cpu", "gpu"];
}

export function jobBodies(label, work) {
  const demo = work.demo;
  if (demo === "echo" || demo === "sleep") return [work];
  return classesForLabel(label).map((cls) => Object.assign({}, work, { class: cls }));
}

export function applyToolResult(doc, result) {
  if (!result || !result.success) return { doc, selected: null, changed: false };
  const next = {
    ...doc,
    stub: false,
    nodes: [...(doc.nodes || [])],
    edges: [...(doc.edges || [])],
  };
  let selected = null;
  if (result.action === "create" && result.node) {
    if (!next.nodes.some((item) => item.id === result.node.id)) {
      next.nodes.push(result.node);
    }
    selected = result.node.id;
  } else if (result.action === "update" && result.node) {
    const nodeId = result.nodeId || result.node.id;
    next.nodes = next.nodes.map((item) => (item.id === nodeId ? result.node : item));
    selected = result.node.id || nodeId;
  } else if (result.action === "delete" && result.nodeId) {
    next.nodes = next.nodes.filter((item) => item.id !== result.nodeId);
    next.edges = next.edges.filter(
      (edge) => edge.source !== result.nodeId && edge.target !== result.nodeId
    );
  } else if (result.action === "connect" && result.edge) {
    const pair = result.edge.source + "->" + result.edge.target;
    const exists = next.edges.some((edge) => edge.source + "->" + edge.target === pair);
    if (!exists) next.edges.push(result.edge);
  } else {
    return { doc, selected: null, changed: false };
  }
  return { doc: next, selected, changed: true };
}

applyToolResult.toolName = "applyToolResult";
