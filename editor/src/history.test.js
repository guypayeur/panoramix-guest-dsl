import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createHistory, docsEqual } from "./history.js";

describe("history", () => {
  it("undoes and redoes structural snapshots", () => {
    const hist = createHistory(8);
    const a = { nodes: [{ id: "n1" }], edges: [] };
    const b = { nodes: [{ id: "n1" }, { id: "n2" }], edges: [] };
    const c = { nodes: [{ id: "n1" }, { id: "n2" }], edges: [{ id: "e1", source: "n1", target: "n2" }] };
    hist.push(a);
    hist.push(b);
    assert.equal(hist.canUndo(), true);
    assert.equal(hist.canRedo(), false);
    const back = hist.undo(c);
    assert.deepEqual(back, b);
    const first = hist.undo(back);
    assert.deepEqual(first, a);
    const again = hist.redo(first);
    assert.deepEqual(again, b);
    const last = hist.redo(again);
    assert.deepEqual(last, c);
    assert.equal(hist.canRedo(), false);
  });

  it("skips duplicate pushes and hydrates across nav", () => {
    const hist = createHistory(2);
    const a = { nodes: [{ id: "n1" }] };
    assert.equal(hist.push(a), true);
    assert.equal(hist.push(a), false);
    hist.push({ nodes: [{ id: "n2" }] });
    hist.push({ nodes: [{ id: "n3" }] });
    hist.push({ nodes: [{ id: "n4" }] });
    assert.equal(hist.size().past, 2);
    const dumped = hist.dump();
    const other = createHistory(2);
    other.hydrate(dumped);
    assert.equal(other.canUndo(), true);
    const current = { nodes: [{ id: "now" }] };
    const back = other.undo(current);
    assert.ok(docsEqual(back.nodes[0], { id: "n4" }));
    assert.ok(docsEqual(other.undo(back).nodes[0], { id: "n3" }));
  });
});
