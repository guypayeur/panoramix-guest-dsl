import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyPanelFields,
  applyToolResult,
  blankNode,
  emptyDoc,
  classesForLabel,
  fromFlow,
  jobBodies,
  nodeSummary,
  retargetEdges,
  toFlow,
} from "./graph.js";

describe("graph", () => {
  it("roundtrips a four-node doc through React Flow nodes", () => {
    const doc = {
      metadata: { id: "mini" },
      nodes: [
        blankNode("dataSource"),
        blankNode("loop"),
        blankNode("formula"),
        blankNode("aggregation"),
      ],
      edges: [],
      stub: false,
    };
    doc.edges = [{ id: "e1", source: doc.nodes[0].id, target: doc.nodes[1].id }];
    const flow = toFlow(doc, doc.nodes[1].id);
    assert.equal(flow.nodes.length, 4);
    assert.equal(flow.nodes.filter((node) => node.selected).length, 1);
    const back = fromFlow(flow.nodes, flow.edges, doc);
    assert.equal(back.nodes.length, 4);
    assert.equal(back.edges[0].source, doc.nodes[0].id);
    assert.match(nodeSummary(doc.nodes[0]), /filename|no filename/);
  });

  it("keeps compound parent/child through React Flow and hides collapsed kids", () => {
    const doc = {
      metadata: { id: "nested" },
      nodes: [
        { id: "scope-outer", type: "scope", label: "Outer", x: 0, y: 0, width: 400, height: 240 },
        { id: "scope-inner", type: "scope", label: "Inner", x: 20, y: 80, parentId: "scope-outer", collapsed: true },
        { id: "ds-1", type: "dataSource", x: 24, y: 40, parentId: "scope-outer", filename: "a.csv" },
        { id: "f-1", type: "formula", x: 40, y: 120, parentId: "scope-inner", formulas: { A: "1" } },
      ],
      edges: [],
      stub: false,
    };
    const flow = toFlow(doc, null);
    const inner = flow.nodes.find((node) => node.id === "scope-inner");
    const hidden = flow.nodes.find((node) => node.id === "f-1");
    assert.equal(inner.parentId, "scope-outer");
    assert.equal(hidden.hidden, true);
    assert.equal(inner.extent, "parent");
    const drilled = toFlow(doc, null, { focusScopeId: "scope-inner" });
    assert.equal(drilled.nodes.find((node) => node.id === "scope-inner").parentId, undefined);
    assert.equal(drilled.nodes.find((node) => node.id === "ds-1").hidden, true);
    assert.equal(drilled.nodes.find((node) => node.id === "f-1").hidden, false);
    const back = fromFlow(flow.nodes, flow.edges, doc);
    assert.equal(back.nodes.find((node) => node.id === "f-1").parentId, "scope-inner");
    assert.equal(back.nodes.find((node) => node.id === "ds-1").parentId, "scope-outer");
  });

  it("applies panel fields and retargets edges", () => {
    const node = blankNode("formula");
    const next = applyPanelFields(node, {
      id: "formula-step",
      label: "Step",
      section: "init",
      formulas: "PV: PREMIUM\nRATE: 0.01",
    });
    assert.equal(next.id, "formula-step");
    assert.equal(next.section, "init");
    assert.equal(next.formulas.PV, "PREMIUM");
    const edges = retargetEdges([{ id: "e1", source: node.id, target: "loop-1" }], node.id, next.id);
    assert.equal(edges[0].source, "formula-step");
  });

  it("applies G8 chat tool results onto the live doc", () => {
    const created = applyToolResult(emptyDoc(), {
      success: true,
      action: "create",
      node: { id: "ds-1", type: "dataSource", filename: "population.csv" },
    });
    assert.equal(created.changed, true);
    assert.equal(created.doc.nodes[0].id, "ds-1");
    const linked = applyToolResult(created.doc, {
      success: true,
      action: "connect",
      edge: { id: "e1", source: "ds-1", target: "loop-1" },
    });
    assert.equal(linked.doc.edges.length, 1);
    const gone = applyToolResult(linked.doc, { success: true, action: "delete", nodeId: "ds-1" });
    assert.equal(gone.doc.nodes.length, 0);
    assert.equal(gone.doc.edges.length, 0);
    assert.equal(applyToolResult.toolName, "applyToolResult");
  });

  it("maps cpu/gpu/both without Spot labels", () => {
    assert.deepEqual(classesForLabel("both"), ["cpu", "gpu"]);
    assert.deepEqual(jobBodies("both", { demo: "dsl", catalog: "sos" }).map((row) => row.class), [
      "cpu",
      "gpu",
    ]);
    assert.deepEqual(jobBodies("cpu", { demo: "echo", message: "x" }), [
      { demo: "echo", message: "x" },
    ]);
  });
});
