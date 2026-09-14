import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  autoLayout,
  estimateNodeSize,
  layeredLayout,
  looksPiled,
  simpleLayout,
  undersizedLeaves,
} from "./layout.js";

function byId(nodes) {
  return Object.fromEntries(nodes.map((node) => [node.id, node]));
}

function overlapCount(nodes) {
  let overlaps = 0;
  const boxes = nodes.map((node) => {
    const est = estimateNodeSize(node);
    return {
      x: node.x,
      y: node.y,
      w: node.width || est.width,
      h: node.height || est.height,
    };
  });
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      if (a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y) overlaps += 1;
    }
  }
  return overlaps;
}

describe("layout", () => {
  it("places types in left-to-right columns", () => {
    const nodes = [
      { id: "agg", type: "aggregation", position: { x: 0, y: 0 } },
      { id: "ds", type: "dataSource", position: { x: 0, y: 0 } },
      { id: "loop", type: "loop", position: { x: 0, y: 0 } },
      { id: "f", type: "formula", position: { x: 0, y: 0 } },
    ];
    const placed = simpleLayout(nodes, [], { dx: 100, dy: 50, originX: 0, originY: 0 });
    const got = byId(placed);
    assert.equal(got.ds.x, 0);
    assert.equal(got.f.x, 100);
    assert.equal(got.loop.x, 200);
    assert.equal(got.agg.x, 300);
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
    const placed = simpleLayout(nodes, [], { originX: 10, originY: 10 });
    const got = byId(placed);
    assert.ok(got.ds.x >= 0);
    assert.ok(got.ds.y >= 0);
    assert.ok(got.f.x >= 0);
    assert.ok(got["scope-inner"].width >= 220);
    assert.ok((got["scope-outer"].width || 0) >= 360);
    assert.ok(got.ds.x + 220 <= got["scope-outer"].width + 48);
    assert.ok(got.f.x + 220 <= got["scope-inner"].width + 48);
  });

  it("layered fallback follows edges, not type columns", () => {
    const nodes = [
      { id: "agg", type: "aggregation", position: { x: 0, y: 0 } },
      { id: "ds", type: "dataSource", position: { x: 0, y: 0 } },
      { id: "f-late", type: "formula", position: { x: 0, y: 0 } },
    ];
    const edges = [
      { source: "ds", target: "f-late" },
      { source: "f-late", target: "agg" },
    ];
    const placed = layeredLayout(nodes, edges, { originX: 0, originY: 0 });
    const got = byId(placed);
    assert.ok(got.ds.x < got["f-late"].x, "formula that consumes a source sits to its right");
    assert.ok(got["f-late"].x < got.agg.x, "aggregation sits after its formula");
    assert.equal(overlapCount(placed), 0);
  });

  it("does not pile sibling leaves inside a Matryoshka scope", () => {
    const nodes = [
      { id: "scope-outer", type: "scope" },
      { id: "scope-inner", type: "scope", parentId: "scope-outer" },
      { id: "ds-a", type: "dataSource", parentId: "scope-outer" },
      { id: "ds-b", type: "dataSource", parentId: "scope-outer" },
      { id: "ds-c", type: "dataSource", parentId: "scope-outer" },
      { id: "loop-o", type: "loop", parentId: "scope-outer" },
      { id: "f-init", type: "formula", parentId: "scope-outer" },
      { id: "ds-i", type: "dataSource", parentId: "scope-inner" },
      { id: "loop-i", type: "loop", parentId: "scope-inner" },
      { id: "f-step", type: "formula", parentId: "scope-inner" },
      { id: "agg-0", type: "aggregation", parentId: "scope-inner" },
      { id: "agg-1", type: "aggregation", parentId: "scope-inner" },
    ];
    const edges = [
      { source: "ds-a", target: "loop-o" },
      { source: "ds-b", target: "loop-o" },
      { source: "ds-c", target: "loop-o" },
      { source: "f-init", target: "loop-o" },
      { source: "loop-o", target: "loop-i" },
      { source: "ds-i", target: "loop-i" },
      { source: "f-step", target: "loop-i" },
      { source: "loop-i", target: "agg-0" },
      { source: "loop-i", target: "agg-1" },
    ];
    const placed = layeredLayout(nodes, edges);
    const got = byId(placed);
    const outerLeaves = placed.filter((node) => node.parentId === "scope-outer" && node.type !== "scope");
    const innerLeaves = placed.filter((node) => node.parentId === "scope-inner");
    assert.equal(overlapCount(outerLeaves), 0);
    assert.equal(overlapCount(innerLeaves), 0);
    assert.ok(got["loop-o"].x > got["ds-a"].x);
    assert.ok(got["scope-inner"].x > got["loop-o"].x);
    assert.ok(got["agg-0"].x > got["loop-i"].x);
    assert.ok(got["scope-outer"].width >= got["scope-inner"].x + got["scope-inner"].width);
    assert.ok(got["scope-inner"].width >= got["agg-0"].x + 220);
    assert.equal(looksPiled(placed), false);
  });

  it("looksPiled detects overlapping type stacks", () => {
    const piled = [
      { id: "a", type: "dataSource", position: { x: 40, y: 80 } },
      { id: "b", type: "dataSource", position: { x: 40, y: 120 } },
      { id: "c", type: "loop", position: { x: 40, y: 160 } },
    ];
    assert.equal(looksPiled(piled), true);
    const spaced = layeredLayout(piled, [
      { source: "a", target: "c" },
      { source: "b", target: "c" },
    ]);
    assert.equal(looksPiled(spaced), false);
  });

  it("estimates formula height from wrapped key list", () => {
    const short = estimateNodeSize({ id: "f", type: "formula", formulas: { A: "1" }, section: "step" });
    const formulas = Object.fromEntries(Array.from({ length: 40 }, (_, i) => ["VAR_" + i, "1"]));
    const tall = estimateNodeSize({ id: "f-step", type: "formula", formulas, section: "step" });
    assert.ok(short.height >= 96);
    assert.ok(tall.height > short.height + 80);
    assert.equal(
      undersizedLeaves([{ id: "f-step", type: "formula", formulas, height: 96, style: { height: 96 } }]),
      true
    );
  });

  it("tall formula cards do not overlap a nested sibling scope", () => {
    const formulas = Object.fromEntries(Array.from({ length: 40 }, (_, i) => ["VAR_" + i, "1"]));
    const nodes = [
      { id: "scope-outer", type: "scope" },
      { id: "f-step", type: "formula", parentId: "scope-outer", section: "step", formulas },
      { id: "scope-inner", type: "scope", parentId: "scope-outer" },
      { id: "loop", type: "loop", parentId: "scope-inner", loopType: "inner", dimension: "T_INNER" },
    ];
    const placed = layeredLayout(nodes, [{ source: "f-step", target: "loop" }]);
    const got = byId(placed);
    assert.ok(got["f-step"].height > 200, "layout must reserve content height, not 96px");
    const a = {
      x: got["f-step"].x,
      y: got["f-step"].y,
      w: got["f-step"].width,
      h: got["f-step"].height,
    };
    const b = {
      x: got["scope-inner"].x,
      y: got["scope-inner"].y,
      w: got["scope-inner"].width,
      h: got["scope-inner"].height,
    };
    const overlap = a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
    assert.equal(overlap, false);
    assert.ok(got["scope-inner"].x >= got["f-step"].x + got["f-step"].width);
    assert.ok(got["scope-outer"].width >= got["scope-inner"].x + got["scope-inner"].width);
  });

  it("elk layered (or fallback) keeps parent-relative children", async () => {
    const nodes = [
      { id: "scope-outer", type: "scope" },
      { id: "ds", type: "dataSource", parentId: "scope-outer" },
      { id: "loop", type: "loop", parentId: "scope-outer" },
    ];
    const edges = [{ source: "ds", target: "loop" }];
    const placed = await autoLayout(nodes, edges);
    const got = byId(placed);
    assert.ok(got.ds.x >= 0);
    assert.ok(got.loop.x > got.ds.x);
    assert.ok(got["scope-outer"].width >= got.loop.x + 200);
    assert.equal(looksPiled(placed), false);
  });
});
