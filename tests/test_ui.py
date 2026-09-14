"""G3 editor HTTP — load + YAML roundtrip, no sockets."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.catalog import CATALOG_IDS
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore
from dsl.ui import ui_available

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_graph.yaml"


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def _auth_headers(app: DslApp) -> dict[str, str]:
    resp = app.handle(
        "POST",
        "/v0/auth/login",
        json.dumps({"email": SEED_EMAIL, "password": DEFAULT_SEED_PASSWORD}).encode(),
    )
    token = json.loads(resp.body.decode("utf-8"))["tokens"]["accessToken"]
    return {"authorization": f"Bearer {token}"}


class EditorLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-ui", iterations=1000),
        )

    def test_info_ui_true_north_star_false(self) -> None:
        self.assertTrue(ui_available())
        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertIs(body["ui"], True)
        self.assertIs(INFO_PAYLOAD["ui"], True)
        self.assertIs(body["runs_ux"], True)
        self.assertIs(body["ux_journey"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["status"], "ux-probe")
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["auth_api"], True)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["chat_api"], True)
        self.assertEqual(body["editor"]["canvas"], ["dataSource", "loop", "formula", "aggregation"])
        self.assertIs(body["editor"]["react_flow"], True)
        self.assertIs(body["editor"]["equivalent_canvas"], False)
        self.assertIs(body["editor"]["undo_redo"], True)
        self.assertIs(body["editor"]["minimap"], True)
        self.assertIs(body["editor"]["auto_layout"], True)
        self.assertIs(body["editor"]["multi_select"], True)
        self.assertEqual(body["editor"]["persistence"], "localStorage + overlay PUT")
        self.assertIs(body["auth"]["cognito"], False)
        blob = json.dumps(body)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("user_pool", blob)

    def test_editor_html_and_assets(self) -> None:
        for path in ("/", "/ui", "/ui/", "/ui/index.html"):
            resp = self.app.handle("GET", path)
            self.assertEqual(resp.status, 200, path)
            self.assertIn("text/html", resp.content_type)
            html = resp.body.decode("utf-8")
            self.assertIn("data-testid=\"canvas\"", html)
            self.assertIn("data-testid=\"nav-files\"", html)
            self.assertIn("data-testid=\"tab-editor\"", html)
            self.assertIn("data-testid=\"tab-runs\"", html)
            self.assertIn("DataSource", html)
            self.assertIn("Loop", html)
            self.assertIn("Formula", html)
            self.assertIn("Aggregation", html)
            self.assertIn("/ui/app.js", html)
            self.assertIn("data-testid=\"submit-editor\"", html)
            self.assertIn("data-testid=\"submit-global\"", html)
            self.assertIn("data-testid=\"runs-list\"", html)
            self.assertIn("data-testid=\"run-detail\"", html)
            self.assertIn("data-testid=\"status-filter\"", html)
            self.assertIn("data-testid=\"cancel-run\"", html)
            self.assertIn("data-testid=\"chat-toggle\"", html)
            self.assertIn("data-testid=\"chat-panel\"", html)
            self.assertIn("data-testid=\"undo\"", html)
            self.assertIn("data-testid=\"redo\"", html)
            self.assertIn("data-testid=\"auto-layout\"", html)
            self.assertIn("data-testid=\"minimap\"", html)
            self.assertIn("data-testid=\"multi-select\"", html)
            self.assertIn('value="cpu"', html)
            self.assertIn('value="gpu"', html)
            self.assertIn('value="both"', html)
            self.assertIn('data-testid="submit-dialog"', html)
            self.assertIn('data-testid="submit-accounts"', html)
            self.assertIn('data-testid="submit-precision"', html)
            self.assertIn('data-testid="submit-overrides"', html)
            self.assertIn('value="f32"', html)
            self.assertIn('value="f64"', html)
            self.assertNotIn("spot", html.lower())
            self.assertNotIn("on-demand", html.lower())
            self.assertNotIn("cognito", html.lower())

        js = self.app.handle("GET", "/ui/app.js")
        self.assertEqual(js.status, 200)
        script = js.body.decode("utf-8")
        self.assertIn("dataSource", script)
        self.assertIn("/v0/graph/validate", script)
        self.assertIn("/v0/specs/", script)
        self.assertIn("Bearer", script)
        self.assertIn("/v0/jobs", script)
        self.assertIn("/cancel", script)
        self.assertTrue(
            "react-flow" in script or "@xyflow" in script or "ReactFlow" in script,
            "bundle must include React Flow",
        )
        self.assertIn("localStorage", script)
        self.assertIn("submit-accounts", script)
        self.assertIn("submit-precision", script)
        self.assertIn("/v0/chat", script)
        self.assertIn("applyToolResult", script)
        self.assertNotIn("spot", script.lower())
        self.assertNotIn("on-demand", script.lower())
        self.assertNotIn("user_pool", script.lower())
        self.assertNotIn("matryoshka", script.lower())
        self.assertIn("Progress omitted", self.app.handle("GET", "/").body.decode("utf-8"))

        css = self.app.handle("GET", "/ui/app.css")
        self.assertEqual(css.status, 200)
        self.assertIn("text/css", css.content_type)

    def test_files_page_served(self) -> None:
        for path in ("/files", "/files/", "/files/specs", "/files/data", "/files/results"):
            resp = self.app.handle("GET", path)
            self.assertEqual(resp.status, 200, path)
            self.assertIn("text/html", resp.content_type)
            html = resp.body.decode("utf-8")
            self.assertIn("data-testid=\"tab-specs\"", html)
            self.assertIn("data-testid=\"tab-data\"", html)
            self.assertIn("data-testid=\"tab-results\"", html)
            self.assertIn("No S3 Shared/Group", html)
            self.assertIn("data-testid=\"nav-runs\"", html)
            self.assertIn("/ui/files.js", html)
        js = self.app.handle("GET", "/ui/files.js")
        self.assertEqual(js.status, 200)
        script = js.body.decode("utf-8")
        self.assertIn("/v0/files/", script)
        self.assertIn("write_refused", script)
        self.assertNotIn("s3Key", script)

    def test_ui_path_traversal_rejected(self) -> None:
        resp = self.app.handle("GET", "/ui/../catalog/sos.yaml")
        self.assertEqual(resp.status, 404)


class GraphHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-graph-http", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_parse_catalog_and_fixture_roundtrip(self) -> None:
        catalog = self.app.handle("GET", "/v0/specs/sos/yaml")
        yaml_text = _json(catalog)["yaml"]
        parsed = self.app.handle(
            "POST",
            "/v0/graph/parse",
            json.dumps({"yaml": yaml_text}).encode(),
        )
        self.assertEqual(parsed.status, 200)
        body = _json(parsed)
        self.assertFalse(body["stub"])
        self.assertEqual(body["graph"]["metadata"]["id"], "sos")
        types = {node["type"] for node in body["graph"]["nodes"]}
        self.assertTrue({"dataSource", "loop", "formula", "aggregation"}.issubset(types))
        self.assertEqual(body["yaml"], yaml_text if yaml_text.endswith("\n") else yaml_text + "\n")

        fixture = FIXTURE.read_text(encoding="utf-8")
        once = _json(
            self.app.handle("POST", "/v0/graph/parse", json.dumps({"yaml": fixture}).encode())
        )
        types = [node["type"] for node in once["graph"]["nodes"]]
        self.assertIn("dataSource", types)
        self.assertIn("loop", types)
        self.assertIn("formula", types)
        self.assertIn("aggregation", types)
        exported = _json(
            self.app.handle(
                "POST",
                "/v0/graph/export",
                json.dumps({"graph": once["graph"]}).encode(),
            )
        )
        twice = _json(
            self.app.handle(
                "POST",
                "/v0/graph/parse",
                json.dumps({"yaml": exported["yaml"]}).encode(),
            )
        )
        self.assertEqual(
            [node["type"] for node in twice["graph"]["nodes"]],
            [node["type"] for node in once["graph"]["nodes"]],
        )

    def test_validate_prefers_live_graph_over_stale_yaml(self) -> None:
        stale = (
            "nodes:\n"
            "  - id: ds-1\n"
            "    type: dataSource\n"
            "    filename: \"\"\n"
            "    provides: [A]\n"
        )
        live = {
            "nodes": [
                {
                    "id": "ds-1",
                    "type": "dataSource",
                    "filename": "accounts.csv",
                    "provides": ["A"],
                }
            ],
            "edges": [],
            "metadata": {"id": "mini", "kind": "graph"},
        }
        resp = self.app.handle(
            "POST",
            "/v0/graph/validate",
            json.dumps({"yaml": stale, "graph": live}).encode(),
        )
        self.assertEqual(resp.status, 200)
        body = _json(resp)
        codes = {item["code"] for item in body["issues"]}
        self.assertNotIn("missing_filename", codes)
        self.assertTrue(body["ok"])

    def test_validate_undefined_and_missing_filename(self) -> None:
        yaml_text = (
            "nodes:\n"
            "  - id: ds-1\n"
            "    type: dataSource\n"
            "    filename: \"\"\n"
            "    provides: [A]\n"
            "  - id: f1\n"
            "    type: formula\n"
            "    formulas:\n"
            "      B: A * ZZZ\n"
        )
        resp = self.app.handle(
            "POST",
            "/v0/graph/validate",
            json.dumps({"yaml": yaml_text}).encode(),
        )
        self.assertEqual(resp.status, 200)
        body = _json(resp)
        self.assertFalse(body["ok"])
        codes = {item["code"] for item in body["issues"]}
        self.assertIn("undefined_var", codes)
        self.assertIn("missing_filename", codes)

    def test_save_overlay_still_needs_bearer(self) -> None:
        exported = _json(
            self.app.handle(
                "POST",
                "/v0/graph/export",
                json.dumps({"yaml": FIXTURE.read_text(encoding="utf-8")}).encode(),
            )
        )
        denied = self.app.handle(
            "PUT",
            "/v0/specs/qa-reserve",
            json.dumps({"content": exported["yaml"]}).encode(),
        )
        self.assertEqual(denied.status, 401)
        saved = self.app.handle(
            "PUT",
            "/v0/specs/qa-reserve",
            json.dumps({"content": exported["yaml"]}).encode(),
            self.auth,
        )
        self.assertEqual(saved.status, 200)
        self.assertIs(_json(saved)["storage"]["overlay"], True)
        opened = _json(self.app.handle("GET", "/v0/specs/qa-reserve"))
        parsed = _json(
            self.app.handle(
                "POST",
                "/v0/graph/parse",
                json.dumps({"content": opened["content"]}).encode(),
            )
        )
        self.assertIn("dataSource", [node["type"] for node in parsed["graph"]["nodes"]])

    def test_jobs_catalog_auth_still_work(self) -> None:
        listed = self.app.handle("GET", "/v0/specs")
        self.assertEqual(_json(listed)["total_count"], 4)
        self.assertEqual([item["id"] for item in _json(listed)["items"]], list(CATALOG_IDS))
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "editor-ok"}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        self.assertEqual(_json(created)["kind"], "job")


if __name__ == "__main__":
    unittest.main()
