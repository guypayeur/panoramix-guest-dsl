"""G6 thin local auth — login/register + 401 fail-closed. No sockets."""

from __future__ import annotations

import json
import time
import unittest

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.errors import InvalidCredentials, Unauthorized
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore


def _json(resp) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def _app() -> DslApp:
    return DslApp(
        JobStore(step_seconds=0.02),
        auth=LocalAuth(secret="test-secret", iterations=1000),
    )


def _login(
    app: DslApp,
    email: str = SEED_EMAIL,
    password: str = DEFAULT_SEED_PASSWORD,
) -> dict:
    resp = app.handle(
        "POST",
        "/v0/auth/login",
        json.dumps({"email": email, "password": password}).encode(),
    )
    return _json(resp)


def _headers(app: DslApp) -> dict[str, str]:
    token = _login(app)["tokens"]["accessToken"]
    return {"authorization": f"Bearer {token}"}


class LocalAuthStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.auth = LocalAuth(secret="unit-secret", iterations=1000)

    def test_seed_login_and_wrong_password(self) -> None:
        session = self.auth.login(SEED_EMAIL, DEFAULT_SEED_PASSWORD)
        self.assertEqual(session["user"]["email"], SEED_EMAIL)
        self.assertEqual(session["user"]["name"], "Guy Payeur")
        self.assertIn("sub", session["user"])
        self.assertNotIn("role", session["user"])
        self.assertTrue(session["tokens"]["accessToken"])
        self.assertEqual(session["tokens"]["accessToken"], session["tokens"]["idToken"])
        with self.assertRaises(InvalidCredentials):
            self.auth.login(SEED_EMAIL, "wrong")

    def test_register_then_login(self) -> None:
        created = self.auth.register("new.user@lab.local", "userpass1", "New User")
        self.assertEqual(created["user"]["email"], "new.user@lab.local")
        self.assertEqual(created["user"]["name"], "New User")
        again = self.auth.login("New.User@lab.local", "userpass1")
        self.assertEqual(again["user"]["sub"], created["user"]["sub"])

    def test_token_roundtrip_and_tamper(self) -> None:
        session = self.auth.login(SEED_EMAIL, DEFAULT_SEED_PASSWORD)
        token = session["tokens"]["accessToken"]
        user = self.auth.verify_token(token)
        self.assertEqual(user.email, SEED_EMAIL)
        tampered = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
        with self.assertRaises(Unauthorized):
            self.auth.verify_token(tampered)
        with self.assertRaises(Unauthorized):
            self.auth.verify_token("not-a-jwt")

    def test_expired_token(self) -> None:
        frozen = {"now": 1_700_000_000}

        def clock() -> float:
            return float(frozen["now"])

        auth = LocalAuth(secret="exp-secret", iterations=1000, clock=clock, token_ttl_sec=10)
        session = auth.login(SEED_EMAIL, DEFAULT_SEED_PASSWORD)
        token = session["tokens"]["accessToken"]
        auth.verify_token(token)
        frozen["now"] += 11
        with self.assertRaises(Unauthorized) as ctx:
            auth.verify_token(token)
        self.assertEqual(ctx.exception.to_dict()["error"], "unauthorized")


class AuthHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _app()

    def test_info_auth_with_ui(self) -> None:
        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertEqual(body, INFO_PAYLOAD)
        self.assertEqual(body["status"], "runs-ux")
        self.assertIs(body["auth_api"], True)
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["ui"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertIs(body["auth"]["cognito"], False)
        self.assertIs(body["auth"]["mfa"], False)
        self.assertIs(body["auth"]["rbac"], False)
        self.assertIn("PUT /v0/specs/{id}", body["auth"]["protected"])
        self.assertIn("POST /v0/jobs", body["auth"]["protected"])
        self.assertIn("GET /health", body["auth"]["public"])
        blob = json.dumps(body).lower()
        self.assertNotIn("user_pool", blob)
        self.assertNotIn("hosted_ui", blob)
        self.assertNotIn("aws_cognito", blob)

    def test_health_stays_public(self) -> None:
        health = self.app.handle("GET", "/health")
        self.assertEqual(health.status, 200)
        self.assertEqual(_json(health), {"status": "ok"})
        specs = self.app.handle("GET", "/v0/specs")
        self.assertEqual(specs.status, 200)
        self.assertEqual(_json(specs)["total_count"], 4)

    def test_login_success_and_bad_password(self) -> None:
        ok = self.app.handle(
            "POST",
            "/v0/auth/login",
            json.dumps({"email": SEED_EMAIL, "password": DEFAULT_SEED_PASSWORD}).encode(),
        )
        self.assertEqual(ok.status, 200)
        body = _json(ok)
        self.assertEqual(body["user"]["email"], SEED_EMAIL)
        self.assertNotIn("role", body["user"])
        self.assertTrue(body["tokens"]["accessToken"])

        bad = self.app.handle(
            "POST",
            "/v0/auth/login",
            json.dumps({"email": SEED_EMAIL, "password": "nope"}).encode(),
        )
        self.assertEqual(bad.status, 401)
        self.assertEqual(_json(bad)["error"], "invalid_credentials")

        missing = self.app.handle(
            "POST",
            "/v0/auth/login",
            json.dumps({"email": SEED_EMAIL}).encode(),
        )
        self.assertEqual(missing.status, 400)
        self.assertEqual(_json(missing)["error"], "missing_credentials")

    def test_register_and_me(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/auth/register",
            json.dumps(
                {
                    "email": "lab.user@example.com",
                    "password": "userpass1",
                    "name": "Lab User",
                }
            ).encode(),
        )
        self.assertEqual(created.status, 201)
        session = _json(created)
        self.assertEqual(session["user"]["email"], "lab.user@example.com")
        token = session["tokens"]["accessToken"]
        me = self.app.handle("GET", "/v0/auth/me", headers={"authorization": f"Bearer {token}"})
        self.assertEqual(me.status, 200)
        self.assertEqual(_json(me)["user"]["name"], "Lab User")

        dup = self.app.handle(
            "POST",
            "/v0/auth/register",
            json.dumps({"email": "lab.user@example.com", "password": "userpass1"}).encode(),
        )
        self.assertEqual(dup.status, 409)
        self.assertEqual(_json(dup)["error"], "account_exists")

    def test_put_overlay_requires_auth(self) -> None:
        body = json.dumps({"content": "metadata:\n  id: qa-reserve\n  note: gated\n"}).encode()
        denied = self.app.handle("PUT", "/v0/specs/qa-reserve", body)
        self.assertEqual(denied.status, 401)
        self.assertEqual(_json(denied)["error"], "unauthorized")
        self.assertEqual((denied.headers or {}).get("WWW-Authenticate"), "Bearer")

        allowed = self.app.handle("PUT", "/v0/specs/qa-reserve", body, _headers(self.app))
        self.assertEqual(allowed.status, 200)
        saved = _json(allowed)
        self.assertIn("note: gated", saved["content"])
        self.assertIs(saved["storage"]["overlay"], True)
        again = _json(self.app.handle("GET", "/v0/specs/qa-reserve"))
        self.assertIn("note: gated", again["content"])

    def test_jobs_submit_requires_auth_then_works(self) -> None:
        echo = json.dumps({"demo": "echo", "message": "authed"}).encode()
        denied = self.app.handle("POST", "/v0/jobs", echo)
        self.assertEqual(denied.status, 401)
        self.assertEqual(_json(denied)["error"], "unauthorized")

        created = self.app.handle("POST", "/v0/jobs", echo, _headers(self.app))
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["local"]["demo"], "echo")
        listed = _json(self.app.handle("GET", "/v0/jobs"))
        self.assertEqual(listed["jobs"][0]["id"], job["id"])

        sleep = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "sleep", "seconds": 8}).encode(),
            _headers(self.app),
        )
        sleep_id = _json(sleep)["id"]
        cancel_denied = self.app.handle("POST", f"/v0/jobs/{sleep_id}/cancel")
        self.assertEqual(cancel_denied.status, 401)
        canceled = self.app.handle(
            "POST", f"/v0/jobs/{sleep_id}/cancel", headers=_headers(self.app)
        )
        self.assertEqual(canceled.status, 200)
        self.assertEqual(_json(canceled)["status"], "canceled")

    def test_readonly_mutations_fail_closed_then_400(self) -> None:
        created = self.app.handle("POST", "/v0/specs", json.dumps({"name": "x"}).encode())
        self.assertEqual(created.status, 401)
        created_auth = self.app.handle(
            "POST",
            "/v0/specs",
            json.dumps({"name": "x"}).encode(),
            _headers(self.app),
        )
        self.assertEqual(created_auth.status, 400)
        self.assertEqual(_json(created_auth)["error"], "catalog_readonly")

        deleted = self.app.handle("DELETE", "/v0/specs/sos")
        self.assertEqual(deleted.status, 401)
        deleted_auth = self.app.handle("DELETE", "/v0/specs/sos", headers=_headers(self.app))
        self.assertEqual(deleted_auth.status, 400)
        self.assertEqual(_json(deleted_auth)["error"], "catalog_readonly")

    def test_me_and_bad_bearer(self) -> None:
        missing = self.app.handle("GET", "/v0/auth/me")
        self.assertEqual(missing.status, 401)
        bad = self.app.handle("GET", "/v0/auth/me", headers={"authorization": "Bearer nope"})
        self.assertEqual(bad.status, 401)
        self.assertEqual(_json(bad)["error"], "unauthorized")


class AuthTimingNote(unittest.TestCase):
    def test_login_is_in_process(self) -> None:
        app = _app()
        start = time.monotonic()
        resp = app.handle(
            "POST",
            "/v0/auth/login",
            json.dumps({"email": SEED_EMAIL, "password": DEFAULT_SEED_PASSWORD}).encode(),
        )
        self.assertEqual(resp.status, 200)
        self.assertLess(time.monotonic() - start, 2.0)


if __name__ == "__main__":
    unittest.main()
