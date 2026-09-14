"""G3 graph YAML I/O + validate — no sockets."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dsl.catalog import CATALOG_IDS, CatalogStore
from dsl.graph import (
    emit_yaml,
    formula_refs,
    parse_yaml,
    validate,
    validation_payload,
)
from dsl.yaml_io import dumps, loads

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_graph.yaml"


class YamlSubsetTests(unittest.TestCase):
    def test_scalar_and_nested_roundtrip(self) -> None:
        raw = {
            "metadata": {"id": "sos", "math": False, "count": 2},
            "description": "hello (path/in)",
            "list": ["a", "b"],
            "nested": {"k": "v"},
        }
        text = dumps(raw)
        self.assertEqual(loads(text), raw)
        self.assertIn("math: false", text)

    def test_inline_collections(self) -> None:
        data = loads("provides: [AGE, PREMIUM]\nmap: {a: 1, b: two}\n")
        self.assertEqual(data["provides"], ["AGE", "PREMIUM"])
        self.assertEqual(data["map"], {"a": 1, "b": "two"})


class CatalogRoundtripTests(unittest.TestCase):
    def test_catalog_stubs_preserve_source(self) -> None:
        store = CatalogStore()
        for spec_id in CATALOG_IDS:
            with self.subTest(spec_id=spec_id):
                original = store.get(spec_id)["content"]
                doc = parse_yaml(original)
                self.assertTrue(doc.is_stub)
                self.assertEqual(doc.nodes, [])
                self.assertEqual(doc.metadata.get("id"), spec_id)
                self.assertIn("catalog-stub", str(doc.metadata.get("kind")))
                emitted = emit_yaml(doc)
                self.assertEqual(emitted, original if original.endswith("\n") else original + "\n")
                again = parse_yaml(emitted)
                self.assertEqual(again.metadata.get("id"), spec_id)
                self.assertEqual(again.description, doc.description)
                self.assertEqual(validation_payload(doc)["ok"], True)

    def test_catalog_semantic_keys_survive_forced_emit(self) -> None:
        original = (ROOT / "catalog" / "sos.yaml").read_text(encoding="utf-8")
        doc = parse_yaml(original)
        doc.dirty = True
        emitted = emit_yaml(doc, preserve_source=False)
        again = parse_yaml(emitted)
        self.assertEqual(again.metadata["id"], "sos")
        self.assertEqual(again.metadata["entity"], "SOS")
        self.assertIs(again.metadata["cupy"], False)
        self.assertEqual(again.metadata["seed_file"], "spec_sos.yaml")


class MiniGraphTests(unittest.TestCase):
    def test_seed_shaped_import_four_node_types(self) -> None:
        doc = parse_yaml(FIXTURE.read_text(encoding="utf-8"))
        types = sorted(node.type for node in doc.nodes)
        self.assertEqual(types.count("dataSource"), 1)
        self.assertEqual(types.count("loop"), 2)
        self.assertEqual(types.count("formula"), 2)
        self.assertEqual(types.count("aggregation"), 1)
        ds = next(node for node in doc.nodes if node.type == "dataSource")
        self.assertEqual(ds.filename, "accounts.csv")
        self.assertIn("AGE", ds.provides)
        self.assertTrue(any(node.loop_type == "outer" for node in doc.nodes if node.type == "loop"))
        self.assertTrue(any(node.section == "init" for node in doc.nodes if node.type == "formula"))

    def test_graph_yaml_roundtrip_nodes(self) -> None:
        doc = parse_yaml(FIXTURE.read_text(encoding="utf-8"))
        emitted = emit_yaml(doc)
        again = parse_yaml(emitted)
        self.assertEqual([node.type for node in again.nodes], [node.type for node in doc.nodes])
        self.assertEqual(
            [node.filename for node in again.nodes if node.type == "dataSource"],
            [node.filename for node in doc.nodes if node.type == "dataSource"],
        )
        first = next(node for node in doc.nodes if node.type == "formula" and node.section == "step")
        second = next(node for node in again.nodes if node.type == "formula" and node.section == "step")
        self.assertEqual(first.formulas, second.formulas)
        third = parse_yaml(emit_yaml(again))
        self.assertEqual(
            [node.to_dict() for node in third.nodes],
            [node.to_dict() for node in again.nodes],
        )

    def test_undefined_var_and_missing_filename(self) -> None:
        text = """
metadata: {id: bad, kind: graph}
nodes:
  - id: ds-1
    type: dataSource
    label: Empty file
    filename: ""
    provides: [PREMIUM]
  - id: formula-step
    type: formula
    section: step
    formulas:
      PV: PREMIUM * MISSING_RATE
"""
        doc = parse_yaml(text)
        issues = {item.code: item for item in validate(doc)}
        self.assertIn("undefined_var", issues)
        self.assertEqual(issues["undefined_var"].name, "MISSING_RATE")
        self.assertEqual(issues["undefined_var"].severity, "error")
        self.assertIn("missing_filename", issues)
        self.assertEqual(issues["missing_filename"].severity, "warning")
        payload = validation_payload(doc)
        self.assertFalse(payload["ok"])

    def test_formula_refs_strip_temporal(self) -> None:
        self.assertEqual(formula_refs("PV[-1] * (1 + RATE)"), ["PV", "RATE"])
        self.assertNotIn("where", formula_refs("where(AGE > 0, PV, 0)"))


class NoLiftTests(unittest.TestCase):
    def test_fixture_is_not_seed_engine(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8").lower()
        self.assertNotIn("import cupy", text)
        self.assertNotIn("nsm-math", text)
        self.assertNotIn("getafix", text)
        blob = json.dumps(parse_yaml(FIXTURE.read_text(encoding="utf-8")).to_dict())
        self.assertNotIn("ray://", blob)


if __name__ == "__main__":
    unittest.main()
