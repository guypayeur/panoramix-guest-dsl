"""G0/G1 listen + info tests — no listening sockets."""

from __future__ import annotations

import json
import unittest

from dsl.http import INFO_PAYLOAD, DslApp
from platform_run import parse_listen


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


class ParseListenTests(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertEqual(parse_listen("18380"), ("127.0.0.1", 18380))
        self.assertEqual(parse_listen(":18380"), ("0.0.0.0", 18380))
        self.assertEqual(parse_listen("0.0.0.0:18380"), ("0.0.0.0", 18380))
        self.assertEqual(parse_listen("127.0.0.1:18380"), ("127.0.0.1", 18380))


class HandleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp()

    def test_health_and_info(self) -> None:
        health = self.app.handle("GET", "/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(_json(health), {"status": "ok"})

        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertEqual(body["unit"], "dsl")
        self.assertEqual(body["name"], "dsl")
        self.assertEqual(body["pin"], "0.5")
        self.assertEqual(body["contract_version"], "0.5")
        self.assertEqual(body["status"], "ux-probe")
        self.assertNotEqual(body["status"], "skeleton")
        self.assertNotEqual(body["status"], "jobs-seam")
        self.assertNotEqual(body["status"], "specs-catalog")
        self.assertNotEqual(body["status"], "local-auth")
        self.assertNotEqual(body["status"], "editor-mvp")
        self.assertNotEqual(body["status"], "runs-ux")
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["auth_api"], True)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["ui"], True)
        self.assertIs(body["runs_ux"], True)
        self.assertIs(body["ux_journey"], True)
        self.assertIs(body["chat_api"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertIs(body["auth"]["cognito"], False)
        self.assertIs(body["auth"]["mfa"], False)
        self.assertIs(body["auth"]["rbac"], False)
        self.assertEqual(body["specs"]["ids"], ["sos", "reserve", "sos-lite", "qa-reserve"])
        self.assertEqual(body["specs"]["rules"], ["no empty content", "no sticky Untitled"])
        self.assertIs(body["getafix_equivalent"], False)
        self.assertEqual(body["engines"], "runtime-bindings-only")
        self.assertEqual(body["handoff"], ["kind", "class", "payload_digest"])
        self.assertEqual(body["jobs"]["kinds"], ["chunk", "job", "stage"])
        self.assertEqual(body["jobs"]["classes"], ["cpu", "gpu"])
        self.assertEqual(
            body["jobs"]["statuses"],
            ["queued", "running", "succeeded", "failed", "canceled"],
        )
        self.assertNotIn("paused", body["jobs"]["statuses"])
        self.assertNotIn("held", body["jobs"]["statuses"])
        self.assertEqual(body["jobs"]["local_demo"], ["dsl", "echo", "sleep"])
        self.assertIs(body["jobs"]["pause_resume"], False)
        self.assertEqual(body, INFO_PAYLOAD)
        blob = json.dumps(body)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("temporal://", blob)
        self.assertNotIn("aws://", blob)

    def test_ui_is_served(self) -> None:
        for path in ("/", "/ui", "/files"):
            resp = self.app.handle("GET", path)
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.content_type)
            self.assertIn("guest-dsl", resp.body.decode("utf-8"))

    def test_method_and_missing(self) -> None:
        resp = self.app.handle("POST", "/health")
        self.assertEqual(resp.status, 405)
        self.assertEqual(_json(resp)["error"], "method_not_allowed")

        resp = self.app.handle("GET", "/nope")
        self.assertEqual(resp.status, 404)
        self.assertEqual(_json(resp)["path"], "/nope")


if __name__ == "__main__":
    unittest.main()
