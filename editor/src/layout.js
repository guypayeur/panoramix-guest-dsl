/** Layered auto-layout. Dagre when available; deterministic columns otherwise. */

const COLUMNS = {
  dataSource: 0,
  formula: 1,
  loop: 2,
  aggregation: 3,
};

function columnOf(node) {
  const type = node.type || (node.data && node.data.type);
  return COLUMNS[type] ?? 1;
}

export function simpleLayout(nodes, edges = [], options = {}) {
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
