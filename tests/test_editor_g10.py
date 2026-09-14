"""G10 React Flow polish — info flags, chrome, APIs intact. G8 chat stays; no G9.

In-process DslApp.handle only. Node unit tests live under editor/.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "editor"


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


class InfoG10Tests(unittest.TestCase):
    def test_react_flow_true_north_star_false(self) -> None:
        app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-g10-info", iterations=1000),
        )
        body = _json(app.handle("GET", "/v0/info"))
        self.assertEqual(body["pin"], "0.5")
        self.assertEqual(body["contract_version"], "0.5")
        self.assertIs(body["ui"], True)
        self.assertIs(body["runs_ux"], True)
        self.assertIs(body["ux_journey"], True)
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["auth_api"], True)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertIs(INFO_PAYLOAD["north_star_done"], False)
        self.assertIs(INFO_PAYLOAD["editor"]["react_flow"], True)
        editor = body["editor"]
        self.assertIs(editor["react_flow"], True)
        self.assertIs(editor["undo_redo"], True)
        self.assertIs(editor["minimap"], True)
        self.assertIs(editor["auto_layout"], True)
        self.assertIs(editor["multi_select"], True)
        self.assertEqual(editor["persistence"], "localStorage + overlay PUT")
        self.assertIs(editor["equivalent_canvas"], False)
        self.assertIs(body["auth"]["cognito"], False)
        self.assertIs(body["runs"]["spot"], False)
        blob = json.dumps(body).lower()
        self.assertNotIn("user_pool", blob)
        self.assertNotIn("on-demand", blob)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("matryoshka", blob)
        self.assertIs(body["chat_api"], True)


class ChromeG10Tests(unittest.TestCase):
    def test_html_and_bundle_are_react_flow(self) -> None:
        app = DslApp()
        html = app.handle("GET", "/").body.decode("utf-8")
        for hook in (
            'data-testid="canvas"',
            'data-testid="undo"',
            'data-testid="redo"',
            'data-testid="auto-layout"',
            'data-testid="minimap"',
            'data-testid="theme-toggle"',
            'data-testid="multi-select"',
            'data-testid="revert-spec"',
            "/ui/app.js",
        ):
            self.assertIn(hook, html)
        self.assertNotIn("spot", html.lower())
        self.assertNotIn("cognito", html.lower())

        js = app.handle("GET", "/ui/app.js")
        self.assertEqual(js.status, 200)
        script = js.body.decode("utf-8")
        self.assertGreater(len(script), 10_000)
        self.assertTrue(
            "react-flow" in script or "ReactFlow" in script or "MiniMap" in script,
            "served bundle must be React Flow",
        )
        self.assertIn("localStorage", script)
        self.assertIn("/v0/graph/validate", script)
        self.assertNotIn("amazon-cognito", script.lower())
        self.assertNotIn("matryoshka", script.lower())

        css = app.handle("GET", "/ui/app.css")
        self.assertEqual(css.status, 200)
        self.assertIn("text/css", css.content_type)

    def test_editor_toolchain_is_documented(self) -> None:
        readme = (EDITOR / "README.md").read_text(encoding="utf-8")
        self.assertIn("npm run build", readme)
        self.assertIn("@xyflow/react", readme)
        self.assertIn("platform_run.py", readme)
        pkg = json.loads((EDITOR / "package.json").read_text(encoding="utf-8"))
        self.assertIn("@xyflow/react", pkg["dependencies"])
        self.assertIn("@dagrejs/dagre", pkg["dependencies"])
        self.assertNotIn("amazon-cognito-identity-js", pkg.get("dependencies", {}))


class ApisStillWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-g10-apis", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_g3_g4_g5_g6_still_work(self) -> None:
        parsed = self.app.handle(
            "POST",
            "/v0/graph/parse",
            json.dumps({"yaml": "metadata:\n  id: mini\n  kind: catalog-stub\n"}).encode(),
        )
        self.assertEqual(parsed.status, 200)
        self.assertTrue(_json(parsed)["stub"])
        listed = self.app.handle("GET", "/v0/specs")
        self.assertEqual(_json(listed)["total_count"], 4)
        files = self.app.handle("GET", "/v0/files")
        self.assertEqual(files.status, 200)
        self.assertEqual([tab["id"] for tab in _json(files)["tabs"]], ["specs", "data", "results"])
        denied = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "g10"}).encode(),
        )
        self.assertEqual(denied.status, 401)
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "g10"}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        me = self.app.handle("GET", "/v0/auth/me", headers=self.auth)
        self.assertEqual(me.status, 200)
        self.assertEqual(_json(me)["user"]["email"], SEED_EMAIL)


if __name__ == "__main__":
    unittest.main()
