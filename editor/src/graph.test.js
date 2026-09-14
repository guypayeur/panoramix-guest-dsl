import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyPanelFields,
  blankNode,
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
