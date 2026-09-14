import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  crumbPath,
  descendantsOf,
  isHiddenByCollapse,
  isInFocus,
  parentForFlow,
  relativePosition,
  toggleCollapsed,
} from "./scopes.js";

const nodes = [
  { id: "scope-outer", type: "scope", label: "Outer", x: 10, y: 10, parentId: "" },
  { id: "scope-inner", type: "scope", label: "Inner", x: 30, y: 80, parentId: "scope-outer", collapsed: false },
  { id: "ds-1", type: "dataSource", x: 40, y: 40, parentId: "scope-outer" },
  { id: "f-1", type: "formula", x: 50, y: 120, parentId: "scope-inner" },
];

describe("matryoshka scopes", () => {
  it("nests inner under outer and hides children when collapsed", () => {
    const kids = descendantsOf("scope-outer", nodes).map((node) => node.id).sort();
    assert.deepEqual(kids, ["ds-1", "f-1", "scope-inner"]);
    const collapsed = toggleCollapsed(nodes, "scope-outer");
    assert.equal(collapsed.find((node) => node.id === "scope-outer").collapsed, true);
    assert.equal(isHiddenByCollapse(nodes.find((node) => node.id === "f-1"), collapsed), true);
    assert.equal(isHiddenByCollapse(nodes.find((node) => node.id === "scope-outer"), collapsed), false);
    assert.equal(isHiddenByCollapse(nodes.find((node) => node.id === "f-1"), collapsed, null, "scope-inner"), false);
  });

  it("drill-in keeps the focused subgraph and recovers crumbs", () => {
    assert.equal(isInFocus(nodes.find((node) => node.id === "f-1"), "scope-inner", nodes), true);
    assert.equal(isInFocus(nodes.find((node) => node.id === "ds-1"), "scope-inner", nodes), false);
    assert.equal(parentForFlow(nodes.find((node) => node.id === "scope-inner"), "scope-inner"), undefined);
    assert.equal(parentForFlow(nodes.find((node) => node.id === "f-1"), "scope-inner"), "scope-inner");
    const crumbs = crumbPath(nodes, "scope-inner").map((item) => item.id);
    assert.deepEqual(crumbs, ["scope-outer", "scope-inner"]);
    assert.deepEqual(relativePosition(nodes[1], nodes, "scope-inner"), { x: 0, y: 0 });
    assert.deepEqual(relativePosition(nodes[2], nodes), { x: 30, y: 30 });
  });
});
