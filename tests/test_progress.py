"""G13 durable progress — hook-reported stage/fraction/elapsed; stub omits."""

from __future__ import annotations

import json
import subprocess
import unittest
from types import SimpleNamespace

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore
from dsl.progress import (
    ENV_CTL_HTTP,
    LabDslApplyHook,
    LabDslHttpHook,
    apply_hook_from_env,
    describe_progress_hook,
    http_hook_from_env,
    normalize_ctl_http_base,
    progress_hook_from_env,
    work_id_for,
)
from dsl.runs import honest_progress


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


class HonestProgressG13Tests(unittest.TestCase):
    def test_stage_fraction_elapsed_copied(self) -> None:
        copied = honest_progress(
            {
                "stage": "fold",
                "fraction": 0.4,
                "elapsed": 12.5,
                "stages_completed": 2,
                "stages_total": 4,
            }
        )
        self.assertEqual(copied["stage"], "fold")
        self.assertEqual(copied["fraction"], 0.4)
        self.assertEqual(copied["elapsed"], 12.5)
        self.assertEqual(copied["stages_completed"], 2)
        self.assertEqual(copied["stages_total"], 4)
        self.assertNotIn("percent", copied)

    def test_never_invent_percent_from_fraction(self) -> None:
        copied = honest_progress({"fraction": 0.25})
        self.assertEqual(copied, {"fraction": 0.25})
        self.assertNotIn("percent", copied)
        self.assertIsNone(honest_progress({"fraction": None, "elapsed": None}))
        self.assertIsNone(honest_progress({"progress": {"fraction": None, "walls": None}}))

    def test_nested_local_dsl_walls_become_elapsed(self) -> None:
        copied = honest_progress(
            {
                "status": "succeeded",
                "progress": {
                    "catalog": "reserve-f32",
                    "executed": True,
                    "fraction": None,
                    "walls": {"wall_sec_time": 34.227},
                },
            }
        )
        self.assertEqual(copied["elapsed"], 34.227)
        self.assertEqual(copied["catalog"], "reserve-f32")
        self.assertNotIn("fraction", copied)
        self.assertNotIn("percent", copied)

    def test_numeric_stage_and_elapsed_ms(self) -> None:
        copied = honest_progress({"stage": 2, "elapsed_ms": 1500, "wall_elapsed_ms": 2100})
        self.assertEqual(copied["stage"], 2)
        self.assertEqual(copied["elapsed_ms"], 1500.0)
        self.assertEqual(copied["wall_elapsed_ms"], 2100.0)

    def test_per_stage_elapsed_only_when_present(self) -> None:
        copied = honest_progress(
            {
                "stages": [
                    {"name": "admit"},
                    {"name": "fold", "elapsed_ms": 17},
                    "skip-me",
                ]
            }
        )
        self.assertEqual(copied["stages"][0], {"name": "admit"})
        self.assertEqual(copied["stages"][1], {"name": "fold", "elapsed_ms": 17.0})


class ProgressHookEnvTests(unittest.TestCase):
    def test_non_loopback_fails_closed(self) -> None:
        self.assertIsNone(normalize_ctl_http_base("https://example.com"))
        self.assertIsNone(normalize_ctl_http_base("http://10.0.0.2:19217"))
        self.assertEqual(
            normalize_ctl_http_base("http://127.0.0.1:19217"),
            "http://127.0.0.1:19217",
        )
        self.assertIsNone(progress_hook_from_env({}))
        self.assertIsNone(http_hook_from_env({ENV_CTL_HTTP: "http://example.com:19217"}))
        self.assertIsNone(apply_hook_from_env({}))

    def test_http_hook_projects_reported_progress(self) -> None:
        calls: list[str] = []

        def transport(method, url, headers, body, timeout=None):
            del headers, body, timeout
            calls.append(method + " " + url)
            payload = {
                "progress": {
                    "stage": "fold",
                    "fraction": 0.5,
                    "elapsed": 3.2,
                }
            }
            return 200, json.dumps(payload)

        hook = LabDslHttpHook("http://127.0.0.1:19217", transport=transport)
        job = SimpleNamespace(id="cw_test", local=None)
        raw = hook.progress(job)
        shown = honest_progress(raw)
        self.assertEqual(shown["stage"], "fold")
        self.assertEqual(shown["fraction"], 0.5)
        self.assertEqual(shown["elapsed"], 3.2)
        self.assertTrue(calls[0].startswith("GET "))
        self.assertIn("/dsl/progress", calls[0])
        self.assertIn("id=cw_test", calls[0])

    def test_http_hook_omits_on_error(self) -> None:
        hook = LabDslHttpHook(
            "http://127.0.0.1:19217",
            transport=lambda *_args, **_kw: (503, "{}"),
        )
        self.assertIsNone(hook.progress(SimpleNamespace(id="x", local=None)))

    def test_apply_hook_uses_local_dsl_verb(self) -> None:
        seen: list[list[str]] = []

        def runner(cmd, **kwargs):
            del kwargs
            seen.append(cmd)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"stage": "complete", "fraction": 1.0, "elapsed": 34.227}),
                stderr="",
            )

        hook = LabDslApplyHook("/tmp/runtime", runner=runner)
        shown = honest_progress(hook.progress(SimpleNamespace(id="cw_1", local=None)))
        self.assertEqual(shown["stage"], "complete")
        self.assertEqual(shown["elapsed"], 34.227)
        self.assertIn("runtime.apply", seen[0])
        self.assertIn("dsl", seen[0])
        self.assertIn("progress", seen[0])
        self.assertIn("--id", seen[0])

    def test_work_id_prefers_runtime_ref(self) -> None:
        job = SimpleNamespace(id="guest", local={"runtime_id": "cw_real"})
        self.assertEqual(work_id_for(job), "cw_real")


class MockedHookHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reported = {
            "stage": "fold",
            "fraction": 0.4,
            "elapsed": 9.5,
            "message": "runtime",
        }
        self.store = JobStore(
            step_seconds=0.02,
            durable_progress=lambda _job: dict(self.reported),
        )
        self.app = DslApp(
            self.store,
            auth=LocalAuth(secret="test-g13", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_job_detail_and_progress_verb_surface_hook(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job_id = _json(created)["id"]
        got = _json(self.app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertEqual(got["progress"]["stage"], "fold")
        self.assertEqual(got["progress"]["fraction"], 0.4)
        self.assertEqual(got["progress"]["elapsed"], 9.5)
        self.assertNotIn("percent", got["progress"])
        exported = _json(self.app.handle("GET", f"/v0/jobs/{job_id}/progress"))
        self.assertEqual(exported["source"], "durable")
        self.assertEqual(exported["progress"]["stage"], "fold")
        self.assertEqual(exported["id"], job_id)
        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["runs"]["progress_durable"], True)
        self.assertIs(info["jobs"]["progress_durable"], True)
        self.assertEqual(info["runs"]["progress_fields"], ["stage", "fraction", "elapsed"])
        self.assertEqual(info["runs"]["auto_refresh"], "optional-stop-on-terminal")
        self.assertIs(info["north_star_done"], False)
        self.assertIs(info["progress_hook"]["durable_path"], True)
        self.store.cancel(job_id)

    def test_hook_empty_omits(self) -> None:
        self.reported = {"fraction": None, "message": "  "}
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "x"}).encode(),
            self.auth,
        )
        job_id = _json(created)["id"]
        got = _json(self.app.handle("GET", f"/v0/jobs/{job_id}"))
        self.assertNotIn("progress", got)
        exported = _json(self.app.handle("GET", f"/v0/jobs/{job_id}/progress"))
        self.assertEqual(exported["source"], "durable")
        self.assertNotIn("progress", exported)


class StubStillOmitsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-g13-stub", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_stub_job_and_progress_verb_omit(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
            self.auth,
        )
        job = _json(created)
        self.assertNotIn("progress", job)
        exported = _json(self.app.handle("GET", f"/v0/jobs/{job['id']}/progress"))
        self.assertEqual(exported["source"], "omit")
        self.assertNotIn("progress", exported)
        listed = _json(self.app.handle("GET", "/v0/jobs"))
        self.assertNotIn("progress", listed["jobs"][0])
        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["runs"]["progress_durable"], False)
        self.assertEqual(info["progress_hook"], INFO_PAYLOAD["progress_hook"])
        self.assertIs(info["north_star_done"], False)
        self.assertFalse(describe_progress_hook(None)["durable_path"])
        self.app.handle("POST", f"/v0/jobs/{job['id']}/cancel", headers=self.auth)


if __name__ == "__main__":
    unittest.main()
