"""HTTP dispatcher tests — DslApp.handle, no listening sockets."""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from dsl.handoff import digest_canonical
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore
from platform_run import parse_listen


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def _digest(hex_byte: str = "ab") -> str:
    return "sha256:" + hex_byte * 32


def wait_http_status(app: DslApp, job_id: str, wanted: set[str], timeout: float = 2.0) -> dict:
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        resp = app.handle("GET", f"/v0/jobs/{job_id}")
        last = _json(resp)
        if last.get("status") in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job stayed {last!r}, wanted {wanted}")


class ParseListenTests(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertEqual(parse_listen("18380"), ("127.0.0.1", 18380))
        self.assertEqual(parse_listen(":18380"), ("0.0.0.0", 18380))
        self.assertEqual(parse_listen("0.0.0.0:18380"), ("0.0.0.0", 18380))


class HttpAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(JobStore(step_seconds=0.02))

    def test_info_jobs_api_without_ui(self) -> None:
        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["ui"], False)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["jobs"]["handoff"], INFO_PAYLOAD["jobs"]["handoff"])
        self.assertIs(body["jobs"]["pause_resume"], False)

        for path in ("/", "/ui"):
            resp = self.app.handle("GET", path)
            self.assertEqual(resp.status, 404)

    def test_submit_list_get_opaque(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertEqual(job["payload_digest"], _digest())
        self.assertEqual(job["status"], "queued")
        self.assertIn("Location", created.headers or {})
        self.assertTrue(created.headers["Location"].endswith(job["id"]))

        listed = _json(self.app.handle("GET", "/v0/jobs"))
        self.assertEqual(listed["jobs"][0]["id"], job["id"])

        got = self.app.handle("GET", f"/v0/jobs/{job['id']}")
        self.assertEqual(got.status, 200)
        self.assertEqual(_json(got)["id"], job["id"])

        done = wait_http_status(self.app, job["id"], {"succeeded"})
        self.assertIn("opaque", done["message"])
        self.assertNotIn("engine", done)
        self.assertNotIn("ray", done)

        handoff = self.app.handle("GET", f"/v0/jobs/{job['id']}/handoff")
        self.assertEqual(handoff.status, 200)
        self.assertEqual(_json(handoff)["payload_digest"], _digest())
        unknown = self.app.handle("GET", f"/v0/jobs/{job['id']}/payload")
        self.assertEqual(unknown.status, 404)
        self.assertEqual(_json(unknown)["error"], "payload_unknown")

    def test_submit_demo_echo_and_dsl(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "hi"}).encode(),
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertEqual(job["payload_digest"], digest_canonical({"demo": "echo", "message": "hi"}))
        self.assertEqual(job["local"]["demo"], "echo")
        done = wait_http_status(self.app, job["id"], {"succeeded"})
        self.assertEqual(done["message"], "hi")

        payload = self.app.handle("GET", f"/v0/jobs/{job['id']}/payload")
        self.assertEqual(payload.status, 200)
        self.assertEqual(_json(payload)["encoding"], "canonical-json")

        dsl = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "dsl", "catalog": "qa-reserve"}).encode(),
        )
        self.assertEqual(dsl.status, 201)
        dsl_job = _json(dsl)
        self.assertEqual(dsl_job["local"]["demo"], "dsl")
        self.assertIs(dsl_job["local"]["nsm"], False)
        wait_http_status(self.app, dsl_job["id"], {"succeeded"})

    def test_list_status_filter(self) -> None:
        sleep = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        sleep_id = _json(sleep)["id"]
        listed = _json(self.app.handle("GET", "/v0/jobs?status=queued,running"))
        self.assertEqual(listed["status"], ["queued", "running"])
        self.assertEqual([j["id"] for j in listed["jobs"]], [sleep_id])

        bad = self.app.handle("GET", "/v0/jobs?status=cancelled")
        self.assertEqual(bad.status, 400)
        self.assertEqual(_json(bad)["error"], "invalid_status")

    def test_bad_kind(self) -> None:
        resp = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "dsl.demo.unknown", "class": "cpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(resp.status, 400)
        body = _json(resp)
        self.assertEqual(body["error"], "invalid_kind")

    def test_bad_class_and_digest(self) -> None:
        bad_class = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "tpu", "payload_digest": _digest()}
            ).encode(),
        )
        self.assertEqual(bad_class.status, 400)
        self.assertEqual(_json(bad_class)["error"], "invalid_class")

        bad_digest = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"kind": "job", "class": "cpu", "payload_digest": "not-a-digest"}
            ).encode(),
        )
        self.assertEqual(bad_digest.status, 400)
        self.assertEqual(_json(bad_digest)["error"], "invalid_digest")

    def test_engine_smuggle_rejected(self) -> None:
        probes = [
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "engine_kind": "x"},
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "payload": {}},
            {"kind": "job", "class": "cpu", "payload_digest": "s3://bucket/key"},
            {"kind": "job", "class": "cpu", "payload_digest": _digest(), "url": "cluster"},
            {"kind": "ray://127.0.0.1:10001", "class": "cpu", "payload_digest": _digest()},
            {"kind": "temporal://ns", "class": "cpu", "payload_digest": _digest()},
            {"kind": "aws://batch", "class": "cpu", "payload_digest": _digest()},
        ]
        for raw in probes:
            with self.subTest(raw=raw):
                resp = self.app.handle("POST", "/v0/jobs", json.dumps(raw).encode())
                self.assertEqual(resp.status, 400)
                self.assertEqual(_json(resp)["error"], "engine_smuggle")

    def test_missing_job(self) -> None:
        resp = self.app.handle("GET", "/v0/jobs/not-a-job")
        self.assertEqual(resp.status, 404)
        self.assertEqual(_json(resp)["error"], "not_found")

    def test_cancel_sleep(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
        )
        job_id = _json(created)["id"]
        canceled = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")
        self.assertNotEqual(_json(canceled)["status"], "cancelled")

    def test_cancel_terminal_conflict(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "x"}).encode(),
        )
        job_id = _json(created)["id"]
        wait_http_status(self.app, job_id, {"succeeded"})
        conflict = self.app.handle("POST", f"/v0/jobs/{job_id}/cancel")
        self.assertEqual(conflict.status, 409)
        self.assertEqual(_json(conflict)["error"], "already_terminal")

    def test_cancel_missing(self) -> None:
        resp = self.app.handle("POST", "/v0/jobs/missing/cancel")
        self.assertEqual(resp.status, 404)

    def test_invalid_json(self) -> None:
        resp = self.app.handle("POST", "/v0/jobs", b"{")
        self.assertEqual(resp.status, 400)
        self.assertEqual(_json(resp)["error"], "invalid_json")

    def test_unit_yaml_has_no_engine_fields(self) -> None:
        text = Path(__file__).resolve().parents[1].joinpath(".platform/contract.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn('contract_version: "0.5"', text)
        for needle in ("image:", "ray:", "temporal:", "aws:"):
            self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
