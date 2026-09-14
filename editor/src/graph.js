/** Guest graph helpers — canvas document ↔ React Flow nodes/edges. */

export const NODE_TYPES = ["dataSource", "loop", "formula", "aggregation"];

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
  return (node.reduce || "mean") + " " + (node.variable || "");
}

export function toFlow(doc, selectedId) {
  const nodes = (doc.nodes || []).map((node) => ({
    id: node.id,
    type: node.type,
    position: { x: Number(node.x) || 0, y: Number(node.y) || 0 },
    data: { ...node },
    selected: selectedId ? node.id === selectedId : undefined,
  }));
  const edges = (doc.edges || []).map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    type: "smoothstep",
  }));
  return { nodes, edges };
}

export function fromFlow(nodes, edges, doc) {
  const previous = Object.fromEntries((doc.nodes || []).map((node) => [node.id, node]));
  return {
    ...doc,
    stub: false,
    nodes: nodes.map((node) => {
      const data = node.data || {};
      const prior = previous[node.id] || {};
      return {
        ...prior,
        ...data,
        id: node.id,
        type: node.type || data.type || prior.type,
        label: data.label || prior.label || node.id,
        x: node.position ? node.position.x : data.x || 0,
        y: node.position ? node.position.y : data.y || 0,
      };
    }),
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
