"""G15 live local-dsl admit — mocked apply; stub without engine env."""

from __future__ import annotations

import json
import subprocess
import unittest
from types import SimpleNamespace

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.http import DslApp
from dsl.jobs import JobStore
from dsl.progress import (
    BINDING_CPU,
    BINDING_GPU,
    ENV_DSL_WORK_ROOT,
    ENV_RUNTIME_ROOT,
    LabDslApplyHook,
    admit_engine_absent,
    admit_hook_from_env,
    binding_for_class,
    live_admit_ready,
    runtime_id_from_admit,
)
from dsl.runs import (
    R2_RESERVE_F32_DIGEST,
    honest_progress,
    matching_r2_catalog,
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


def _wait(store: JobStore, job_id: str, wanted: set[str], timeout: float = 2.0) -> str:
    import time

    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = store.get(job_id).status
        if last in wanted:
            return last
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stayed {last!r}, wanted {wanted}")


class BindingAndEnvTests(unittest.TestCase):
    def test_cpu_gpu_bindings(self) -> None:
        self.assertEqual(binding_for_class("cpu", {}), BINDING_CPU)
        self.assertEqual(binding_for_class("gpu", {}), BINDING_GPU)
        self.assertEqual(
            binding_for_class("gpu", {"PANORAMIX_DSL_BINDING_GPU": "bindings/mine.yaml"}),
            "bindings/mine.yaml",
        )

    def test_live_admit_requires_runtime_and_engine(self) -> None:
        self.assertFalse(live_admit_ready({}))
        self.assertFalse(live_admit_ready({ENV_RUNTIME_ROOT: "/tmp/runtime"}))
        self.assertFalse(live_admit_ready({ENV_DSL_WORK_ROOT: "/tmp/dsl-work"}))
        self.assertTrue(
            live_admit_ready(
                {ENV_RUNTIME_ROOT: "/tmp/runtime", ENV_DSL_WORK_ROOT: "/tmp/dsl-work"}
            )
        )
        self.assertIsNone(admit_hook_from_env({ENV_RUNTIME_ROOT: "/tmp/runtime"}))
        hook = admit_hook_from_env(
            {ENV_RUNTIME_ROOT: "/tmp/runtime", ENV_DSL_WORK_ROOT: "/tmp/dsl-work"}
        )
        self.assertIsInstance(hook, LabDslApplyHook)

    def test_engine_absent_keeps_stub(self) -> None:
        self.assertTrue(admit_engine_absent(None))
        self.assertTrue(admit_engine_absent({"ok": False, "error": "DSL_ENGINE_ABSENT"}))
        self.assertTrue(admit_engine_absent({"ok": True, "executed": False}))
        self.assertFalse(
            admit_engine_absent({"ok": True, "executed": True, "id": "cw_1"})
        )

    def test_matching_r2_from_digest_and_local(self) -> None:
        self.assertEqual(
            matching_r2_catalog(R2_RESERVE_F32_DIGEST, None), "reserve-f32"
        )
        self.assertEqual(
            matching_r2_catalog("sha256:dead", {"r2": "reserve-f32"}), "reserve-f32"
        )
        self.assertIsNone(matching_r2_catalog("sha256:" + "ab" * 32, {"catalog": "reserve"}))

    def test_runtime_id_from_admit(self) -> None:
        self.assertEqual(runtime_id_from_admit({"id": "cw_lab"}), "cw_lab")
        self.assertEqual(runtime_id_from_admit({"work": {"id": "cw_w"}}), "cw_w")


class ApplyAdmitHookTests(unittest.TestCase):
    def test_apply_cmd_uses_gpu_binding_and_live(self) -> None:
        seen: list[list[str]] = []

        def runner(cmd, **kwargs):
            del kwargs
            seen.append(cmd)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "id": "cw_r5",
                        "executed": True,
                        "catalog": "reserve-f32",
                        "walls": {"wall_sec_time": 34.227},
                        "bel": -152058908.82,
                    }
                ),
                stderr="",
            )

        hook = LabDslApplyHook("/tmp/runtime", runner=runner)
        raw = hook.admit(catalog="reserve-f32", resource_class="gpu", live=True)
        self.assertEqual(raw["id"], "cw_r5")
        self.assertTrue(raw["executed"])
        cmd = seen[0]
        self.assertIn("runtime.apply", cmd)
        self.assertIn("--binding", cmd)
        self.assertEqual(cmd[cmd.index("--binding") + 1], BINDING_GPU)
        self.assertIn("dsl", cmd)
        self.assertIn("admit", cmd)
        self.assertIn("--live", cmd)
        self.assertIn("reserve-f32", cmd)
        self.assertIn("gpu", cmd)

    def test_cpu_binding_on_cpu_class(self) -> None:
        seen: list[str] = []

        def runner(cmd, **kwargs):
            del kwargs
            seen.extend(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

        hook = LabDslApplyHook("/tmp/runtime", runner=runner)
        hook.admit(catalog="reserve-f32", resource_class="cpu", live=True)
        self.assertIn(BINDING_CPU, seen)
        self.assertNotIn(BINDING_GPU, seen)


class LiveAdmitJobTests(unittest.TestCase):
    def test_reserve_f32_gpu_copies_walls_bel_and_runtime_id(self) -> None:
        hook = SimpleNamespace(
            admit=lambda **_kw: {
                "ok": True,
                "id": "cw_r5",
                "executed": True,
                "catalog": "reserve-f32",
                "walls": {"wall_sec_time": 34.227},
                "bel": -152058908.82,
                "binding": BINDING_GPU,
            }
        )
        store = JobStore(step_seconds=0.01, durable_admit=hook)
        job = store.submit(
            {
                "demo": "dsl",
                "catalog": "reserve",
                "accounts": 200000,
                "precision": "f32",
                "class": "gpu",
            }
        )
        _wait(store, job.id, {"succeeded"})
        done = store.get(job.id)
        self.assertEqual(done.status, "succeeded")
        self.assertEqual(done.local["runtime_id"], "cw_r5")
        self.assertEqual(done.local["cw_id"], "cw_r5")
        self.assertIs(done.local["executed"], True)
        self.assertIs(done.local["live"], True)
        self.assertEqual(done.local["binding"], BINDING_GPU)
        self.assertEqual(done.local["r2"], "reserve-f32")
        blob = done.to_dict()
        self.assertEqual(blob["progress"]["elapsed"], 34.227)
        self.assertEqual(blob["progress"]["bel"], -152058908.82)
        self.assertEqual(blob["progress"]["walls"]["wall_sec_time"], 34.227)
        self.assertIs(blob["progress"]["executed"], True)
        self.assertIn("live local-dsl", done.message or "")
        self.assertIn("34.227", done.message or "")
        self.assertNotIn("not NSM/CuPy", done.message or "")

    def test_engine_absent_falls_back_to_stub(self) -> None:
        hook = SimpleNamespace(
            admit=lambda **_kw: {"ok": False, "error": "DSL_ENGINE_ABSENT: missing root"}
        )
        store = JobStore(step_seconds=0.01, durable_admit=hook)
        job = store.submit(
            {
                "demo": "dsl",
                "catalog": "reserve",
                "accounts": 200000,
                "precision": "f32",
                "class": "gpu",
            }
        )
        _wait(store, job.id, {"succeeded"})
        done = store.get(job.id)
        self.assertIn("not NSM/CuPy", done.message or "")
        self.assertNotIn("progress", done.to_dict())
        self.assertFalse(done.local.get("executed"))
        self.assertFalse(done.local.get("live"))

    def test_no_hook_keeps_stub_and_invents_nothing(self) -> None:
        store = JobStore(step_seconds=0.01)
        job = store.submit(
            {
                "demo": "dsl",
                "catalog": "reserve",
                "accounts": 200000,
                "precision": "f32",
                "class": "gpu",
            }
        )
        _wait(store, job.id, {"succeeded"})
        done = store.get(job.id)
        self.assertIn("not NSM/CuPy", done.message or "")
        self.assertNotIn("progress", done.to_dict())
        self.assertNotIn("runtime_id", done.local or {})

    def test_non_r2_catalog_stays_stub_even_with_hook(self) -> None:
        seen: list[str] = []
        hook = SimpleNamespace(
            admit=lambda **kw: seen.append(kw["catalog"]) or {"ok": True, "executed": True}
        )
        store = JobStore(step_seconds=0.01, durable_admit=hook)
        job = store.submit({"demo": "dsl", "catalog": "qa-reserve"})
        _wait(store, job.id, {"succeeded"})
        done = store.get(job.id)
        self.assertEqual(seen, [])
        self.assertIn("not NSM/CuPy", done.message or "")

    def test_admit_failure_marks_failed(self) -> None:
        hook = SimpleNamespace(
            admit=lambda **_kw: {"ok": False, "error": "DSL_ENGINE_FAILED: boom"}
        )
        store = JobStore(step_seconds=0.01, durable_admit=hook)
        job = store.submit(
            {
                "demo": "dsl",
                "catalog": "reserve",
                "accounts": 200000,
                "precision": "f32",
            }
        )
        _wait(store, job.id, {"failed"})
        done = store.get(job.id)
        self.assertEqual(done.status, "failed")
        self.assertIn("DSL_ENGINE_FAILED", done.error or "")


class LiveAdmitHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = SimpleNamespace(
            admit=lambda **kw: {
                "ok": True,
                "id": "cw_http",
                "executed": True,
                "catalog": kw.get("catalog"),
                "class": kw.get("resource_class"),
                "walls": {"wall_sec_time": 34.227},
                "bel": -152058908.82,
            }
        )
        self.store = JobStore(
            step_seconds=0.01,
            durable_admit=self.hook,
            durable_progress=lambda job: {
                "stage": "complete",
                "elapsed": 34.227,
                "catalog": "reserve-f32",
                "bel": -152058908.82,
            }
            if (job.local or {}).get("runtime_id")
            else None,
        )
        self.app = DslApp(
            self.store,
            auth=LocalAuth(secret="test-g15", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_info_and_job_detail(self) -> None:
        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["runs"]["live_admit"], True)
        self.assertIs(info["jobs"]["live_admit"], True)
        self.assertEqual(info["runs"]["live_admit_bindings"]["gpu"], BINDING_GPU)
        self.assertIs(info["north_star_done"], False)
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {
                    "demo": "dsl",
                    "catalog": "reserve",
                    "accounts": 200000,
                    "precision": "f32",
                    "class": "gpu",
                }
            ).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job_id = _json(created)["id"]
        import time

        deadline = time.monotonic() + 2.0
        got = {}
        while time.monotonic() < deadline:
            got = _json(self.app.handle("GET", f"/v0/jobs/{job_id}"))
            if got.get("status") == "succeeded":
                break
            time.sleep(0.02)
        self.assertEqual(got["status"], "succeeded")
        self.assertEqual(got["local"]["runtime_id"], "cw_http")
        self.assertEqual(got["progress"]["bel"], -152058908.82)
        exported = _json(self.app.handle("GET", f"/v0/jobs/{job_id}/progress"))
        self.assertEqual(exported["source"], "durable")
        self.assertEqual(exported["progress"]["elapsed"], 34.227)
        self.assertIs(info["pin"] if False else True, True)
        self.assertEqual(info["pin"], "0.5")


class HonestWallsBelTests(unittest.TestCase):
    def test_copy_walls_and_bel_never_invent(self) -> None:
        copied = honest_progress(
            {
                "executed": True,
                "bel": -152058908.82,
                "walls": {"wall_sec_time": 34.227, "gpu_kernel_sec": 12.0},
            }
        )
        self.assertEqual(copied["bel"], -152058908.82)
        self.assertEqual(copied["elapsed"], 34.227)
        self.assertEqual(copied["walls"]["wall_sec_time"], 34.227)
        self.assertEqual(copied["walls"]["gpu_kernel_sec"], 12.0)
        self.assertIs(copied["executed"], True)
        self.assertIsNone(honest_progress({"walls": None, "bel": None}))


if __name__ == "__main__":
    unittest.main()
