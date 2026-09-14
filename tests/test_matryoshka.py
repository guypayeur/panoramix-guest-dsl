"""G9 Matryoshka nested-scope visualization — graph fields + chrome.

In-process DslApp.handle only. Does not stamp north_star_done.
Closes #11 only; epic #1 stays open.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dsl.catalog import CatalogStore
from dsl.graph import (
    SCOPE_INNER_ID,
    SCOPE_OUTER_ID,
    attach_scopes,
    emit_yaml,
    has_nested_scopes,
    parse_yaml,
    validation_payload,
)
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini_graph.yaml"
NESTED = ROOT / "tests" / "fixtures" / "nested_scopes.yaml"


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class InfoG9Tests(unittest.TestCase):
    def test_matryoshka_true_north_star_false(self) -> None:
        app = DslApp(JobStore())
        body = _json(app.handle("GET", "/v0/info"))
        self.assertEqual(body["pin"], "0.5")
        self.assertEqual(body["contract_version"], "0.5")
        self.assertIs(body["north_star_done"], False)
        self.assertIs(INFO_PAYLOAD["north_star_done"], False)
        editor = body["editor"]
        self.assertIs(editor["react_flow"], True)
        self.assertIs(editor["undo_redo"], True)
        self.assertIs(editor["minimap"], True)
        self.assertIs(editor["auto_layout"], True)
        self.assertIs(editor["matryoshka"], True)
        self.assertIs(editor["nested_scopes"], True)
        self.assertIs(editor["compound_nodes"], True)
        self.assertIs(editor["drill_in"], True)
        self.assertEqual(editor["canvas"], ["dataSource", "loop", "formula", "aggregation"])
        self.assertIs(body["chat_api"], True)
        blob = json.dumps(body).lower()
        self.assertIn("matryoshka", blob)
        self.assertNotIn("user_pool", blob)
        self.assertNotIn("ray://", blob)


class NestedScopeGraphTests(unittest.TestCase):
    def test_mini_graph_infers_outer_inner(self) -> None:
        doc = parse_yaml(FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(has_nested_scopes(doc))
        self.assertTrue(doc.to_dict()["matryoshka"])
        scopes = [node for node in doc.nodes if node.type == "scope"]
        self.assertEqual({node.id for node in scopes}, {SCOPE_OUTER_ID, SCOPE_INNER_ID})
        inner = next(node for node in scopes if node.id == SCOPE_INNER_ID)
        self.assertEqual(inner.parent_id, SCOPE_OUTER_ID)
        by_id = {node.id: node for node in doc.nodes}
        self.assertEqual(by_id["ds-accounts"].parent_id, SCOPE_OUTER_ID)
        init = next(node for node in doc.nodes if node.type == "formula" and node.section == "init")
        step = next(node for node in doc.nodes if node.type == "formula" and node.section == "step")
        self.assertEqual(init.parent_id, SCOPE_OUTER_ID)
        self.assertEqual(step.parent_id, SCOPE_INNER_ID)
        self.assertFalse(doc.is_stub)

    def test_explicit_yaml_scopes_roundtrip(self) -> None:
        text = NESTED.read_text(encoding="utf-8")
        doc = parse_yaml(text)
        self.assertTrue(has_nested_scopes(doc))
        inner = next(node for node in doc.nodes if node.id == "scope-inner")
        self.assertEqual(inner.parent_id, "scope-outer")
        self.assertTrue(inner.collapsed)
        child = next(node for node in doc.nodes if node.id == "formula-step")
        self.assertEqual(child.parent_id, "scope-inner")
        doc.dirty = True
        again = parse_yaml(emit_yaml(doc, preserve_source=False))
        self.assertTrue(again.to_dict()["matryoshka"])
        again_inner = next(node for node in again.nodes if node.id == "scope-inner")
        self.assertEqual(again_inner.parent_id, "scope-outer")
        self.assertTrue(again_inner.collapsed)

    def test_catalog_sos_has_nested_scopes(self) -> None:
        store = CatalogStore()
        doc = parse_yaml(store.get("sos")["content"])
        self.assertTrue(has_nested_scopes(doc))
        scopes = {node.id: node for node in doc.nodes if node.type == "scope"}
        self.assertIn(SCOPE_OUTER_ID, scopes)
        self.assertIn(SCOPE_INNER_ID, scopes)
        self.assertEqual(scopes[SCOPE_INNER_ID].parent_id, SCOPE_OUTER_ID)
        self.assertIn("T_OUTER", scopes[SCOPE_OUTER_ID].dimensions)
        self.assertTrue(validation_payload(doc)["ok"])

    def test_qa_reserve_has_no_inferred_scopes(self) -> None:
        store = CatalogStore()
        doc = parse_yaml(store.get("qa-reserve")["content"])
        self.assertFalse(any(node.type == "scope" for node in doc.nodes))

    def test_attach_scopes_is_idempotent(self) -> None:
        doc = parse_yaml(FIXTURE.read_text(encoding="utf-8"))
        once = attach_scopes(doc.nodes, {})
        twice = attach_scopes(once, {})
        self.assertEqual(len([node for node in once if node.type == "scope"]), 2)
        self.assertEqual(len([node for node in twice if node.type == "scope"]), 2)


class ChromeG9Tests(unittest.TestCase):
    def test_html_and_bundle_name_matryoshka(self) -> None:
        app = DslApp()
        html = app.handle("GET", "/").body.decode("utf-8")
        for hook in (
            'data-testid="canvas"',
            'data-testid="scope-crumbs"',
            'data-testid="matryoshka"',
            'data-testid="undo"',
            'data-testid="minimap"',
            'data-testid="chat-panel"',
        ):
            self.assertIn(hook, html)
        self.assertIn("matryoshka", html.lower())
        script = app.handle("GET", "/ui/app.js").body.decode("utf-8")
        self.assertIn("matryoshka", script.lower())
        self.assertIn("scope-toggle", script)
        self.assertIn("scope-drill", script)
        self.assertIn("applyToolResult", script)
        self.assertTrue(
            "react-flow" in script or "ReactFlow" in script or "MiniMap" in script
        )
        self.assertNotIn("amazon-cognito", script.lower())
        self.assertNotIn("import cupy", script.lower())


class GraphHttpG9Tests(unittest.TestCase):
    def test_parse_returns_matryoshka_graph(self) -> None:
        app = DslApp(JobStore())
        parsed = app.handle(
            "POST",
            "/v0/graph/parse",
            json.dumps({"yaml": FIXTURE.read_text(encoding="utf-8")}).encode(),
        )
        self.assertEqual(parsed.status, 200)
        body = _json(parsed)
        self.assertTrue(body["graph"]["matryoshka"])
        types = {node["type"] for node in body["graph"]["nodes"]}
        self.assertIn("scope", types)
        parents = {node["id"]: node.get("parentId") for node in body["graph"]["nodes"]}
        self.assertEqual(parents[SCOPE_INNER_ID], SCOPE_OUTER_ID)


if __name__ == "__main__":
    unittest.main()
