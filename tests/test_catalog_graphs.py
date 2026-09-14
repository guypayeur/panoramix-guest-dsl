"""G11 rich catalog YAML — full graphs, no engine lift."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dsl.catalog import CATALOG_IDS, CatalogStore
from dsl.graph import emit_yaml, parse_yaml, validation_payload
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog"
README = CATALOG / "README.md"
NO_LIFT = (
    "import cupy",
    "import numpy",
    "dsl-engine.py",
    "src/kernel",
    "def kernel",
)


class ProvenanceTests(unittest.TestCase):
    def test_readme_names_seed_files(self) -> None:
        self.assertTrue(README.is_file())
        text = README.read_text(encoding="utf-8")
        for needle in (
            "getafix-seed-paul",
            "320dee4",
            "spec_sos.yaml",
            "spec_reserve_ifrs17.yaml",
            "spec_sos_lite_t_outer_101_s_outer_100.yaml",
            "qa_reserve_ifrs17.yaml",
            "domain YAML",
            "north_star_done",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("north_star_done: true", text)
        self.assertNotIn("import cupy", text.lower())

    def test_info_north_star_still_false(self) -> None:
        self.assertIs(INFO_PAYLOAD["north_star_done"], False)
        body = json.loads(DslApp(JobStore()).handle("GET", "/v0/info").body.decode())
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["pin"], "0.5")


class RichCatalogTests(unittest.TestCase):
    EXPECTED = {
        "sos": {"entity": "SOS", "seed": "spec_sos.yaml", "types": {"dataSource", "loop", "formula", "aggregation"}},
        "reserve": {
            "entity": "RESERVE",
            "seed": "spec_reserve_ifrs17.yaml",
            "types": {"dataSource", "loop", "formula", "aggregation"},
        },
        "sos-lite": {
            "entity": "SOS",
            "seed": "spec_sos_lite_t_outer_101_s_outer_100.yaml",
            "types": {"dataSource", "loop", "formula", "aggregation"},
        },
        "qa-reserve": {
            "entity": "RESERVE",
            "seed": "qa_reserve_ifrs17.yaml",
            "types": {"dataSource"},
        },
    }

    def test_catalog_ids_unchanged(self) -> None:
        self.assertEqual(list(CATALOG_IDS), ["sos", "reserve", "sos-lite", "qa-reserve"])

    def test_each_row_is_a_full_graph(self) -> None:
        store = CatalogStore()
        for spec_id, expect in self.EXPECTED.items():
            with self.subTest(spec_id=spec_id):
                raw = store.get(spec_id)["content"]
                low = raw.lower()
                for needle in NO_LIFT:
                    self.assertNotIn(needle, low)
                self.assertNotIn("kind: catalog-stub", raw)
                self.assertIn("kind: graph", raw)
                self.assertIn("cupy: false", raw)
                self.assertIn(expect["seed"], raw)
                doc = parse_yaml(raw)
                self.assertFalse(doc.is_stub)
                self.assertEqual(doc.metadata.get("id"), spec_id)
                self.assertEqual(doc.metadata.get("kind"), "graph")
                self.assertIs(doc.metadata.get("cupy"), False)
                types = {node.type for node in doc.nodes}
                self.assertTrue(doc.nodes, spec_id)
                self.assertTrue(expect["types"].issubset(types), (spec_id, types))
                self.assertGreaterEqual(len(doc.nodes), 4 if spec_id != "qa-reserve" else 6)
                if spec_id != "qa-reserve":
                    self.assertTrue(doc.edges)
                payload = validation_payload(doc)
                self.assertTrue(payload["ok"], payload)
                self.assertFalse(payload["stub"])
                emitted = emit_yaml(doc)
                self.assertEqual(emitted, raw if raw.endswith("\n") else raw + "\n")
                doc.dirty = True
                again = parse_yaml(emit_yaml(doc, preserve_source=False))
                self.assertEqual({node.type for node in again.nodes}, types)
                self.assertEqual(again.metadata.get("id"), spec_id)
                self.assertTrue(validation_payload(again)["ok"])

    def test_http_parse_validate_export(self) -> None:
        app = DslApp(JobStore())
        for spec_id, expect in self.EXPECTED.items():
            with self.subTest(spec_id=spec_id):
                yaml_row = json.loads(
                    app.handle("GET", f"/v0/specs/{spec_id}/yaml").body.decode()
                )["yaml"]
                parsed = app.handle(
                    "POST",
                    "/v0/graph/parse",
                    json.dumps({"yaml": yaml_row}).encode(),
                )
                self.assertEqual(parsed.status, 200, spec_id)
                body = json.loads(parsed.body.decode())
                self.assertFalse(body["stub"])
                types = {node["type"] for node in body["graph"]["nodes"]}
                self.assertTrue(expect["types"].issubset(types), types)
                validated = app.handle(
                    "POST",
                    "/v0/graph/validate",
                    json.dumps({"yaml": yaml_row}).encode(),
                )
                self.assertEqual(validated.status, 200)
                check = json.loads(validated.body.decode())
                self.assertTrue(check["ok"], check)
                exported = app.handle(
                    "POST",
                    "/v0/graph/export",
                    json.dumps({"graph": body["graph"]}).encode(),
                )
                self.assertEqual(exported.status, 200)
                again = json.loads(
                    app.handle(
                        "POST",
                        "/v0/graph/parse",
                        json.dumps({"yaml": json.loads(exported.body.decode())["yaml"]}).encode(),
                    ).body.decode()
                )
                self.assertEqual(
                    {node["type"] for node in again["graph"]["nodes"]},
                    types,
                )


if __name__ == "__main__":
    unittest.main()
