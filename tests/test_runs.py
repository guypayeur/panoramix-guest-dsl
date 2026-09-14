"""G4 runs UX helpers — labels, honest progress, durable cancel hook."""

from __future__ import annotations

import json
import time
import unittest

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.errors import InvalidClass
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore
from dsl.runs import (
    SUBMIT_LABELS,
    classes_for_label,
    honest_progress,
    submit_bodies_for_label,
)


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


class SubmitLabelTests(unittest.TestCase):
    def test_cpu_gpu_both_fanout(self) -> None:
        self.assertEqual(SUBMIT_LABELS, ("cpu", "gpu", "both"))
        self.assertEqual(classes_for_label("cpu"), ("cpu",))
        self.assertEqual(classes_for_label("gpu"), ("gpu",))
        self.assertEqual(classes_for_label("both"), ("cpu", "gpu"))
        self.assertNotIn("both", classes_for_label("both"))
        # both is a UI label, not a WorkHandoff class
        bodies = submit_bodies_for_label("both", {"demo": "dsl", "catalog": "qa-reserve"})
        self.assertEqual([row["class"] for row in bodies], ["cpu", "gpu"])
        self.assertTrue(all(row["demo"] == "dsl" for row in bodies))

    def test_spot_and_unknown_rejected(self) -> None:
        for label in ("spot", "on-demand", "tpu", ""):
            with self.subTest(label=label):
                with self.assertRaises(InvalidClass):
                    classes_for_label(label)


class HonestProgressTests(unittest.TestCase):
    def test_omit_when_missing(self) -> None:
        self.assertIsNone(honest_progress(None))
        self.assertIsNone(honest_progress({}))
        self.assertIsNone(honest_progress("42"))
        self.assertIsNone(honest_progress({"percent": None, "message": "  "}))

    def test_never_invent_zero(self) -> None:
        self.assertIsNone(honest_progress({"unknown": 1}))
        copied = honest_progress({"percent": 12.5, "completed": 1, "total": 4, "message": "outer"})
        self.assertEqual(copied["percent"], 12.5)
        self.assertEqual(copied["completed"], 1)
        self.assertEqual(copied["total"], 4)
        self.assertEqual(copied["message"], "outer")
        self.assertNotIn("step", copied)


class JobProgressExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore(step_seconds=0.02)

    def test_stub_omits_progress(self) -> None:
        job = self.store.submit({"demo": "echo", "message": "x"})
        blob = job.to_dict()
        self.assertNotIn("progress", blob)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            done = self.store.get(job.id)
            if done.status == "succeeded":
                self.assertNotIn("progress", done.to_dict())
                return
            time.sleep(0.02)
        self.fail("echo did not succeed")

    def test_set_progress_then_omit_again(self) -> None:
        job = self.store.submit({"demo": "sleep", "seconds": 8})
        shown = self.store.set_progress(job.id, {"percent": 40, "message": "hook"})
        self.assertEqual(shown.to_dict()["progress"]["percent"], 40.0)
        cleared = self.store.set_progress(job.id, None)
        self.assertNotIn("progress", cleared.to_dict())
        self.store.cancel(job.id)

    def test_durable_cancel_only_when_hook_present(self) -> None:
        seen: list[str] = []
        bare = JobStore(step_seconds=0.02)
        self.assertFalse(bare.has_durable_cancel())
        live = bare.submit({"demo": "sleep", "seconds": 8})
        canceled = bare.cancel(live.id)
        self.assertEqual(canceled.status, "canceled")
        self.assertEqual(seen, [])

        hooked = JobStore(
            step_seconds=0.02,
            durable_cancel=lambda job: seen.append(job.id),
        )
        self.assertTrue(hooked.has_durable_cancel())
        job = hooked.submit({"demo": "sleep", "seconds": 8})
        hooked.cancel(job.id)
        self.assertEqual(seen, [job.id])


class RunsHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-runs", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_info_runs_ux_north_star_false(self) -> None:
        body = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(body["runs_ux"], True)
        self.assertIs(INFO_PAYLOAD["runs_ux"], True)
        self.assertIs(body["ux_journey"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["status"], "ux-probe")
        self.assertEqual(body["pin"], "0.5")
        self.assertEqual(body["runs"]["labels"], ["cpu", "gpu", "both"])
        self.assertEqual(body["runs"]["submit"], ["editor", "global"])
        self.assertIs(body["runs"]["spot"], False)
        self.assertEqual(body["runs"]["progress"], "omit-when-missing")
        self.assertIs(body["runs"]["cancel_stub"], True)
        self.assertIs(body["runs"]["cancel_durable"], False)
        self.assertIs(body["jobs"]["spot"], False)
        blob = json.dumps(body).lower()
        self.assertNotIn("spot first", blob)
        self.assertNotIn("on-demand", blob)
        self.assertNotIn("ray://", blob)

    def test_info_durable_flag_follows_hook(self) -> None:
        hooked = DslApp(
            JobStore(step_seconds=0.02, durable_cancel=lambda _job: None),
            auth=LocalAuth(secret="hook-info", iterations=1000),
        )
        body = _json(hooked.handle("GET", "/v0/info"))
        self.assertIs(body["runs"]["cancel_durable"], True)
        self.assertIs(body["jobs"]["cancel_durable"], True)
        self.assertIs(body["north_star_done"], False)

    def test_http_omits_progress_and_cancel_stub(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertNotIn("progress", job)
        listed = _json(self.app.handle("GET", "/v0/jobs?status=queued,running"))
        self.assertEqual(listed["status"], ["queued", "running"])
        self.assertEqual(listed["jobs"][0]["id"], job["id"])
        self.assertNotIn("progress", listed["jobs"][0])
        canceled = self.app.handle("POST", f"/v0/jobs/{job['id']}/cancel", headers=self.auth)
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")
        self.assertNotIn("progress", _json(canceled))


if __name__ == "__main__":
    unittest.main()
