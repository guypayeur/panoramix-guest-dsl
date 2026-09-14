"""G4 runs UX helpers + G12 submit dialog (accounts / precision / overrides)."""

from __future__ import annotations

import json
import time
import unittest

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.errors import InvalidAccounts, InvalidClass, InvalidOverrides, InvalidPrecision
from dsl.handoff import digest_canonical, parse_submit
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore
from dsl.runs import (
    PRECISIONS,
    R2_RESERVE_F32_DIGEST,
    R2_SOS_NESTED_DIGEST,
    SUBMIT_LABELS,
    classes_for_label,
    defaults_for_catalog,
    extract_sizes,
    honest_progress,
    resolve_submit_options,
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
        self.assertIs(body["runs"]["accounts"], True)
        self.assertEqual(body["runs"]["precision"], ["f32", "f64"])
        self.assertIs(body["runs"]["overrides"], True)
        self.assertIs(body["runs"]["spot"], False)
        self.assertIs(body["runs"]["cost_estimate"], False)
        self.assertEqual(body["runs"]["r2_catalogs"], ["reserve-f32", "sos-nested"])
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


class SubmitDialogTests(unittest.TestCase):
    def test_catalog_defaults_from_g11_yaml(self) -> None:
        reserve = defaults_for_catalog("reserve")
        self.assertEqual(reserve["accounts"], 200000)
        self.assertEqual(reserve["precision"], "f32")
        self.assertEqual(reserve["r2"], "reserve-f32")
        sos_lite = defaults_for_catalog("sos-lite")
        self.assertEqual(sos_lite["accounts"], 25)
        self.assertEqual(sos_lite["sizes"]["T_OUTER"], 101)
        yaml_sizes = extract_sizes("tensor:\n  sizes:\n    ACCOUNT: 12\n    S_OUTER: 4\n")
        self.assertEqual(yaml_sizes["ACCOUNT"], 12)
        overlaid = defaults_for_catalog("reserve", "sizes:\n  ACCOUNT: 9\n")
        self.assertEqual(overlaid["accounts"], 9)

    def test_accounts_precision_override_priority(self) -> None:
        base = resolve_submit_options("reserve", {})
        self.assertEqual(base.accounts, 200000)
        self.assertEqual(base.precision, "f32")
        explicit = resolve_submit_options("reserve", {"accounts": 1000, "precision": "f64"})
        self.assertEqual(explicit.accounts, 1000)
        self.assertEqual(explicit.precision, "f64")
        overridden = resolve_submit_options(
            "reserve",
            {"accounts": 1000, "overrides": {"ACCOUNT": 50, "S_OUTER": 20}},
        )
        self.assertEqual(overridden.accounts, 50)
        self.assertEqual(overridden.scenarios, 20)
        self.assertEqual(overridden.overrides["ACCOUNT"], 50)

    def test_precision_and_accounts_rejected(self) -> None:
        with self.assertRaises(InvalidPrecision):
            resolve_submit_options("reserve", {"precision": "fp16"})
        with self.assertRaises(InvalidAccounts):
            resolve_submit_options("reserve", {"accounts": 0})
        with self.assertRaises(InvalidAccounts):
            resolve_submit_options("reserve", {"accounts": True})
        with self.assertRaises(InvalidOverrides):
            resolve_submit_options("reserve", {"overrides": ["ACCOUNT"]})
        self.assertEqual(PRECISIONS, ("f32", "f64"))

    def test_r2_golden_digests_when_params_match(self) -> None:
        reserve = parse_submit(
            {
                "demo": "dsl",
                "catalog": "reserve",
                "precision": "f32",
                "accounts": 200000,
            }
        )
        self.assertEqual(reserve.payload_digest, R2_RESERVE_F32_DIGEST)
        self.assertEqual(reserve.local["r2"], "reserve-f32")
        self.assertEqual(reserve.kind, "job")
        self.assertEqual(
            reserve.payload_digest,
            digest_canonical(
                {
                    "workload": "dsl",
                    "spec": "spec_reserve_ifrs17",
                    "accounts": 200000,
                    "scenarios": 100,
                    "horizon": 1201,
                    "precision": "f32",
                    "mode": "production",
                    "kernel": "flat",
                }
            ),
        )

        lite = parse_submit({"demo": "dsl", "catalog": "sos-lite", "precision": "f32"})
        self.assertEqual(lite.payload_digest, R2_SOS_NESTED_DIGEST)
        self.assertEqual(lite.local["r2"], "sos-nested")
        self.assertEqual(lite.local["accounts"], 25)

        qa = parse_submit({"demo": "dsl", "catalog": "qa-reserve", "precision": "f32"})
        self.assertEqual(qa.payload_digest, R2_RESERVE_F32_DIGEST)

    def test_custom_params_stay_handoff_not_r2_golden(self) -> None:
        f64 = parse_submit(
            {"demo": "dsl", "catalog": "reserve", "precision": "f64"}
        )
        self.assertNotEqual(f64.payload_digest, R2_RESERVE_F32_DIGEST)
        self.assertNotIn("r2", f64.local)
        self.assertEqual(f64.local["precision"], "f64")
        self.assertRegex(f64.payload_digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            f64.payload_digest,
            digest_canonical(
                {
                    "workload": "dsl",
                    "spec": "spec_reserve_ifrs17",
                    "accounts": 200000,
                    "scenarios": 100,
                    "horizon": 1201,
                    "precision": "f64",
                    "mode": "production",
                    "kernel": "flat",
                }
            ),
        )

        small = parse_submit(
            {"demo": "dsl", "catalog": "reserve", "accounts": 25, "precision": "f32"}
        )
        self.assertNotEqual(small.payload_digest, R2_RESERVE_F32_DIGEST)
        self.assertEqual(small.local["accounts"], 25)

        sos = parse_submit({"demo": "dsl", "catalog": "sos", "precision": "f32"})
        self.assertNotEqual(sos.payload_digest, R2_SOS_NESTED_DIGEST)
        self.assertEqual(sos.local["accounts"], 25)

    def test_g1_stub_digest_without_dialog_fields(self) -> None:
        parsed = parse_submit({"demo": "dsl", "catalog": "qa-reserve"})
        self.assertNotEqual(parsed.payload_digest, R2_RESERVE_F32_DIGEST)
        self.assertNotIn("accounts", parsed.local or {})
        self.assertIn(b"catalog-stub", parsed.payload_bytes or b"")


class SubmitDialogHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            auth=LocalAuth(secret="test-g12", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_bearer_required_and_handoff_opaque(self) -> None:
        denied = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"demo": "dsl", "catalog": "reserve", "precision": "f32"}
            ).encode(),
        )
        self.assertEqual(denied.status, 401)
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {
                    "demo": "dsl",
                    "catalog": "reserve",
                    "precision": "f32",
                    "accounts": 200000,
                    "class": "gpu",
                }
            ).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "gpu")
        self.assertEqual(job["payload_digest"], R2_RESERVE_F32_DIGEST)
        self.assertEqual(job["local"]["r2"], "reserve-f32")
        self.assertEqual(job["local"]["accounts"], 200000)
        self.assertEqual(job["local"]["precision"], "f32")
        self.assertNotIn("progress", job)
        handoff = _json(self.app.handle("GET", f"/v0/jobs/{job['id']}/handoff"))
        self.assertEqual(
            set(handoff),
            {"id", "kind", "class", "payload_digest", "status"},
        )
        self.assertEqual(handoff["payload_digest"], R2_RESERVE_F32_DIGEST)
        payload = _json(self.app.handle("GET", f"/v0/jobs/{job['id']}/payload"))
        body = json.loads(payload["utf8"])
        self.assertEqual(body["workload"], "dsl")
        self.assertNotIn("ray", body)
        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["north_star_done"], False)
        self.assertIs(info["runs"]["spot"], False)

    def test_overrides_and_bad_precision(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {
                    "demo": "dsl",
                    "catalog": "sos-lite",
                    "precision": "f32",
                    "overrides": {"ACCOUNT": 10, "S_OUTER": 8},
                }
            ).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["local"]["accounts"], 10)
        self.assertEqual(job["local"]["overrides"]["S_OUTER"], 8)
        self.assertNotEqual(job["payload_digest"], R2_SOS_NESTED_DIGEST)
        bad = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps(
                {"demo": "dsl", "catalog": "reserve", "precision": "fp8"}
            ).encode(),
            self.auth,
        )
        self.assertEqual(bad.status, 400)
        self.assertEqual(_json(bad)["error"], "invalid_precision")

    def test_spec_defaults_exposed(self) -> None:
        spec = _json(self.app.handle("GET", "/v0/specs/reserve"))
        self.assertEqual(spec["defaults"]["accounts"], 200000)
        self.assertEqual(spec["defaults"]["precision"], "f32")
        self.assertIn("ACCOUNT", spec["defaults"]["sizes"])


if __name__ == "__main__":
    unittest.main()
