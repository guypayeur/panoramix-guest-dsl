import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { autoLayout, simpleLayout } from "./layout.js";

describe("layout", () => {
  it("places types in left-to-right columns", () => {
    const nodes = [
      { id: "agg", type: "aggregation", position: { x: 0, y: 0 } },
      { id: "ds", type: "dataSource", position: { x: 0, y: 0 } },
      { id: "loop", type: "loop", position: { x: 0, y: 0 } },
      { id: "f", type: "formula", position: { x: 0, y: 0 } },
    ];
    const placed = simpleLayout(nodes, [], { dx: 100, dy: 50, originX: 0, originY: 0 });
    const byId = Object.fromEntries(placed.map((node) => [node.id, node]));
    assert.equal(byId.ds.x, 0);
    assert.equal(byId.f.x, 100);
    assert.equal(byId.loop.x, 200);
    assert.equal(byId.agg.x, 300);
  });

  it("autoLayout returns four distinct positions", async () => {
    const nodes = [
      { id: "ds", type: "dataSource", position: { x: 1, y: 1 } },
      { id: "loop", type: "loop", position: { x: 1, y: 1 } },
      { id: "f", type: "formula", position: { x: 1, y: 1 } },
      { id: "agg", type: "aggregation", position: { x: 1, y: 1 } },
    ];
    const edges = [
      { source: "ds", target: "loop" },
      { source: "f", target: "loop" },
      { source: "loop", target: "agg" },
    ];
    const placed = await autoLayout(nodes, edges);
    const keys = new Set(placed.map((node) => `${Math.round(node.x)},${Math.round(node.y)}`));
    assert.equal(keys.size, 4);
  });

  it("nests children inside compound scopes", () => {
    const nodes = [
      { id: "scope-outer", type: "scope", position: { x: 0, y: 0 } },
      { id: "ds", type: "dataSource", parentId: "scope-outer", position: { x: 0, y: 0 } },
      { id: "scope-inner", type: "scope", parentId: "scope-outer", position: { x: 0, y: 0 } },
      { id: "f", type: "formula", parentId: "scope-inner", position: { x: 0, y: 0 } },
    ];
    const placed = simpleLayout(nodes, [], { dx: 100, dy: 50, originX: 10, originY: 10 });
    const byId = Object.fromEntries(placed.map((node) => [node.id, node]));
    assert.ok(byId.ds.x > byId["scope-outer"].x);
    assert.ok(byId.ds.y > byId["scope-outer"].y);
    assert.ok(byId.f.x > byId["scope-inner"].x);
    assert.ok(byId["scope-inner"].y >= byId["scope-outer"].y);
    assert.ok((byId["scope-outer"].width || 0) >= 360);
  });
});
