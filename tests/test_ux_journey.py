"""G7 UX journey smoke — open → edit/validate → submit → watch → cancel.

In-process DslApp.handle only. No sockets. No invented progress.
Written probe: docs/ux-journey.md. Epic #1 remains open.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "docs" / "ux-journey.md"
MINI = Path(__file__).resolve().parent / "fixtures" / "mini_graph.yaml"


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


def _wait(app: DslApp, job_id: str, wanted: set[str], timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = _json(app.handle("GET", f"/v0/jobs/{job_id}"))
        if last.get("status") in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job stayed {last!r}, wanted {wanted}")


class ProbeDocTests(unittest.TestCase):
    def test_written_probe_exists(self) -> None:
        self.assertTrue(PROBE.is_file(), "docs/ux-journey.md is the G7 written probe")
        text = PROBE.read_text(encoding="utf-8")
        for needle in (
            "Representative path",
            "Side-by-side vs dsl-gui local-lab",
            "open an SOS or RESERVE-class spec",
            "Progress omitted",
            "north_star_done",
            "isLocalAuth",
            "cpu / gpu / both",
            "Epic #1 remains open",
            "never invent",
        ):
            self.assertIn(needle, text)
        self.assertNotIn("north_star_done: true", text)
        self.assertNotIn("north_star_done: True", text)


class InfoHonestyTests(unittest.TestCase):
    def test_info_ux_journey_north_star_false(self) -> None:
        app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-ux-info", iterations=1000),
        )
        body = _json(app.handle("GET", "/v0/info"))
        self.assertIs(body["ux_journey"], True)
        self.assertIs(INFO_PAYLOAD["ux_journey"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["status"], "ux-probe")
        self.assertEqual(body["ux"]["path"], ["open", "edit/validate", "submit", "watch", "cancel"])
        self.assertEqual(body["ux"]["doc"], "docs/ux-journey.md")
        self.assertIs(body["ux"]["lift"], False)
        self.assertIs(body["ux"]["north_star_done"], False)
        self.assertIs(body["runs_ux"], True)
        self.assertIs(body["ui"], True)
        self.assertEqual(body["runs"]["labels"], ["cpu", "gpu", "both"])
        self.assertIs(body["runs"]["spot"], False)
        self.assertEqual(body["runs"]["progress"], "omit-when-missing")
        self.assertIs(body["editor"]["react_flow"], False)
        self.assertIs(body["auth"]["cognito"], False)
        blob = json.dumps(body).lower()
        self.assertNotIn("spot first", blob)
        self.assertNotIn("on-demand", blob)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("user_pool", blob)


class ChromeTests(unittest.TestCase):
    def test_editor_exposes_journey_hooks(self) -> None:
        app = DslApp()
        html = app.handle("GET", "/").body.decode("utf-8")
        for hook in (
            'data-testid="spec-select"',
            'data-testid="open-spec"',
            'data-testid="canvas"',
            'data-testid="validate"',
            'data-testid="submit-editor"',
            'data-testid="submit-global"',
            'data-testid="tab-runs"',
            'data-testid="runs-list"',
            'data-testid="run-detail"',
            'data-testid="status-filter"',
            'data-testid="cancel-run"',
            'data-testid="progress-omitted"',
            "Progress omitted",
        ):
            self.assertIn(hook, html)
        self.assertNotIn("spot", html.lower())
        self.assertNotIn("on-demand", html.lower())


class RepresentativeJourneyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-ux-journey", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_open_sos_and_reserve_class_specs(self) -> None:
        sos = _json(self.app.handle("GET", "/v0/specs/sos"))
        reserve = _json(self.app.handle("GET", "/v0/specs/reserve"))
        self.assertEqual(sos["id"], "sos")
        self.assertEqual(sos["entity"], "SOS")
        self.assertIn("catalog-stub", sos["content"])
        self.assertEqual(reserve["id"], "reserve")
        self.assertEqual(reserve["entity"], "RESERVE")
        self.assertIn("catalog-stub", reserve["content"])
        for spec_id in ("sos", "reserve", "sos-lite", "qa-reserve"):
            yaml_row = _json(self.app.handle("GET", f"/v0/specs/{spec_id}/yaml"))
            parsed = self.app.handle(
                "POST",
                "/v0/graph/parse",
                json.dumps({"yaml": yaml_row["yaml"]}).encode(),
            )
            self.assertEqual(parsed.status, 200, spec_id)
            body = _json(parsed)
            self.assertTrue(body["stub"])
            self.assertEqual(body["graph"]["metadata"]["id"], spec_id)

    def test_edit_validate_submit_watch_cancel_and_succeed(self) -> None:
        # Open RESERVE-class stub, then validate a greenfield mini graph (edit).
        opened = _json(self.app.handle("GET", "/v0/specs/qa-reserve"))
        self.assertEqual(opened["entity"], "RESERVE")
        stub_ok = _json(
            self.app.handle(
                "POST",
                "/v0/graph/validate",
                json.dumps({"yaml": opened["content"]}).encode(),
            )
        )
        self.assertTrue(stub_ok["ok"])
        self.assertTrue(stub_ok["stub"])

        fixture = MINI.read_text(encoding="utf-8")
        parsed = _json(
            self.app.handle("POST", "/v0/graph/parse", json.dumps({"yaml": fixture}).encode())
        )
        types = [node["type"] for node in parsed["graph"]["nodes"]]
        self.assertEqual(set(types), {"dataSource", "loop", "formula", "aggregation"})
        first = _json(
            self.app.handle(
                "POST",
                "/v0/graph/validate",
                json.dumps({"graph": parsed["graph"]}).encode(),
            )
        )
        # Mini fixture references RATE without providing it — validate must say so.
        self.assertFalse(first["ok"])
        self.assertIn("undefined_var", {item["code"] for item in first["issues"]})
        self.assertIn("RATE", {item.get("name") for item in first["issues"]})

        graph = parsed["graph"]
        for node in graph["nodes"]:
            if node.get("type") == "dataSource":
                provides = list(node.get("provides") or [])
                if "RATE" not in provides:
                    provides.append("RATE")
                node["provides"] = provides
        second = _json(
            self.app.handle(
                "POST",
                "/v0/graph/validate",
                json.dumps({"graph": graph}).encode(),
            )
        )
        self.assertTrue(second["ok"])
        exported = _json(
            self.app.handle("POST", "/v0/graph/export", json.dumps({"graph": graph}).encode())
        )
        saved = self.app.handle(
            "PUT",
            "/v0/specs/qa-reserve",
            json.dumps({"content": exported["yaml"]}).encode(),
            self.auth,
        )
        self.assertEqual(saved.status, 200)

        # Watch + cancel (sleep stays live long enough).
        live = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
            self.auth,
        )
        self.assertEqual(live.status, 201)
        sleeping = _json(live)
        self.assertNotIn("progress", sleeping)
        watching = _wait(self.app, sleeping["id"], {"queued", "running"})
        self.assertNotIn("progress", watching)
        listed = _json(self.app.handle("GET", "/v0/jobs?status=queued,running"))
        self.assertTrue(any(row["id"] == sleeping["id"] for row in listed["jobs"]))
        self.assertTrue(all("progress" not in row for row in listed["jobs"]))
        canceled = self.app.handle(
            "POST",
            f"/v0/jobs/{sleeping['id']}/cancel",
            headers=self.auth,
        )
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")
        self.assertNotIn("progress", _json(canceled))

        # Succeed path (catalog stub digest — not CuPy).
        done = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "dsl", "catalog": "sos", "class": "gpu"}).encode(),
            self.auth,
        )
        self.assertEqual(done.status, 201)
        succeeded = _wait(self.app, _json(done)["id"], {"succeeded"})
        self.assertEqual(succeeded["status"], "succeeded")
        self.assertEqual(succeeded["class"], "gpu")
        self.assertNotIn("progress", succeeded)

        echoed = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "ux-probe"}).encode(),
            self.auth,
        )
        self.assertEqual(echoed.status, 201)
        echo = _wait(self.app, _json(echoed)["id"], {"succeeded"})
        self.assertNotIn("progress", echo)

        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["north_star_done"], False)
        self.assertIs(info["ux_journey"], True)


if __name__ == "__main__":
    unittest.main()
