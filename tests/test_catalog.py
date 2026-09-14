"""G2 specs catalog — store + HTTP, no sockets."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.catalog import CATALOG_IDS, CATALOG_ROWS, CatalogStore, is_sticky_untitled
from dsl.errors import CatalogReadOnly, EmptyContent, SpecNotFound, StickyUntitled
from dsl.http import INFO_PAYLOAD, DslApp
from dsl.jobs import JobStore


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


class UntitledRuleTests(unittest.TestCase):
    def test_untitled_forms(self) -> None:
        for name in (
            "Untitled",
            "untitled",
            "Untitled Spec",
            "Untitled Specification",
            "  untitled specification.  ",
        ):
            with self.subTest(name=name):
                self.assertTrue(is_sticky_untitled(name))

    def test_real_names_are_not_untitled(self) -> None:
        for name in ("SOS", "QA RESERVE IFRS17", "My spec", "Untitled-but-named"):
            with self.subTest(name=name):
                self.assertFalse(is_sticky_untitled(name))


class CatalogStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = CatalogStore()

    def test_day_one_rows(self) -> None:
        rows = self.store.rows()
        self.assertEqual([row["id"] for row in rows], list(CATALOG_IDS))
        self.assertEqual(list(CATALOG_IDS), ["sos", "reserve", "sos-lite", "qa-reserve"])
        self.assertEqual(len(CATALOG_ROWS), 4)

    def test_list_and_get_stub(self) -> None:
        listed = self.store.list()
        self.assertEqual(listed["folders"], [])
        self.assertEqual(listed["total_count"], 4)
        self.assertEqual([item["id"] for item in listed["items"]], list(CATALOG_IDS))
        for item in listed["items"]:
            self.assertEqual(item["status"], "published")
            self.assertFalse(item["overlay"])
            self.assertEqual(item["version"], 1)

        got = self.store.get("sos")
        self.assertEqual(got["id"], "sos")
        self.assertEqual(got["name"], "SOS")
        self.assertEqual(got["entity"], "SOS")
        self.assertIn("catalog-stub", got["content"])
        self.assertIn("spec_sos.yaml", got["content"])
        self.assertIn("cupy: false", got["content"])
        self.assertNotIn("import cupy", got["content"].lower())
        self.assertNotIn("nsm-math", got["content"])
        self.assertIs(got["storage"]["overlay"], False)
        self.assertEqual(got["storage"]["stage"], "guest-local")
        self.assertEqual(got["storage"]["backend"], "catalog")
        blob = json.dumps(got)
        self.assertNotIn("cognito", blob.lower())
        self.assertNotIn("getafixFold", blob)

        yaml_body = self.store.yaml("qa-reserve")
        self.assertIn("qa_reserve_ifrs17.yaml", yaml_body["yaml"])
        self.assertIs(yaml_body["storage"]["overlay"], False)

    def test_unknown_spec(self) -> None:
        with self.assertRaises(SpecNotFound) as ctx:
            self.store.get("ifrs17-live")
        self.assertEqual(ctx.exception.to_dict()["error"], "unknown_spec")

    def test_overlay_then_get(self) -> None:
        saved = self.store.save(
            "reserve",
            {"content": "metadata:\n  id: reserve\n  kind: overlay-stub\n"},
        )
        self.assertEqual(saved["content"].strip(), "metadata:\n  id: reserve\n  kind: overlay-stub")
        self.assertEqual(saved["name"], "RESERVE IFRS17")
        self.assertEqual(saved["version"], 2)
        self.assertIs(saved["storage"]["overlay"], True)
        self.assertEqual(saved["storage"]["backend"], "memory")

        listed = self.store.list()
        reserve = next(item for item in listed["items"] if item["id"] == "reserve")
        self.assertTrue(reserve["overlay"])
        self.assertEqual(reserve["name"], "RESERVE IFRS17")

        stub_on_disk = (self.store.catalog_dir / "reserve.yaml").read_text(encoding="utf-8")
        self.assertIn("catalog-stub", stub_on_disk)
        self.assertNotIn("overlay-stub", stub_on_disk)

    def test_overlay_custom_name(self) -> None:
        saved = self.store.save(
            "sos-lite",
            {
                "yaml": "kind: overlay\n",
                "name": "SOS lite lab",
                "description": "smaller loops, local overlay",
            },
        )
        self.assertEqual(saved["name"], "SOS lite lab")
        self.assertEqual(saved["description"], "smaller loops, local overlay")
        listed = self.store.list()
        row = next(item for item in listed["items"] if item["id"] == "sos-lite")
        self.assertEqual(row["name"], "SOS lite lab")

    def test_empty_content_rejected(self) -> None:
        for body in (
            {},
            {"content": ""},
            {"content": "   \n\t"},
            {"yaml": "  "},
        ):
            with self.subTest(body=body):
                with self.assertRaises(EmptyContent):
                    self.store.save("sos", body)

    def test_sticky_untitled_rejected(self) -> None:
        with self.assertRaises(StickyUntitled) as ctx:
            self.store.save(
                "sos",
                {"content": "kind: x\n", "name": "Untitled Specification"},
            )
        self.assertEqual(ctx.exception.to_dict()["error"], "sticky_untitled")

    def test_missing_stub_file_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = CatalogStore(catalog_dir=Path(tmp))
            self.assertEqual(empty.rows(), [])
            self.assertEqual(empty.list()["total_count"], 0)

    def test_refuse_create_and_delete(self) -> None:
        with self.assertRaises(CatalogReadOnly):
            self.store.refuse_create()
        with self.assertRaises(CatalogReadOnly):
            self.store.refuse_delete("sos")


class CatalogHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            CatalogStore(),
            LocalAuth(secret="test-catalog", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_info_specs_with_ui(self) -> None:
        info = self.app.handle("GET", "/v0/info")
        body = _json(info)
        self.assertIs(body["specs_api"], True)
        self.assertIs(body["jobs_api"], True)
        self.assertIs(body["auth_api"], True)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["ui"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["status"], "runs-ux")
        self.assertEqual(body["specs"]["ids"], list(CATALOG_IDS))
        self.assertEqual(body, INFO_PAYLOAD)
        self.assertIs(body["getafix_equivalent"], False)
        blob = json.dumps(body)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("user_pool", blob)

    def test_list_get_yaml(self) -> None:
        listed = self.app.handle("GET", "/v0/specs")
        self.assertEqual(listed.status, 200)
        body = _json(listed)
        self.assertEqual(body["total_count"], 4)
        self.assertEqual([item["id"] for item in body["items"]], list(CATALOG_IDS))

        got = self.app.handle("GET", "/v0/specs/sos")
        self.assertEqual(got.status, 200)
        self.assertEqual(_json(got)["id"], "sos")
        self.assertIn("kind: catalog-stub", _json(got)["content"])

        yaml_resp = self.app.handle("GET", "/v0/specs/reserve/yaml")
        self.assertEqual(yaml_resp.status, 200)
        self.assertIn("spec_reserve_ifrs17.yaml", _json(yaml_resp)["yaml"])

        folders = self.app.handle("GET", "/v0/specs/folders")
        self.assertEqual(folders.status, 200)
        self.assertEqual(_json(folders), {"folders": []})

    def test_put_overlay_and_reread(self) -> None:
        put = self.app.handle(
            "PUT",
            "/v0/specs/qa-reserve",
            json.dumps({"content": "metadata:\n  id: qa-reserve\n  note: overlay\n"}).encode(),
            self.auth,
        )
        self.assertEqual(put.status, 200)
        saved = _json(put)
        self.assertIn("note: overlay", saved["content"])
        self.assertIs(saved["storage"]["overlay"], True)
        self.assertEqual(saved["name"], "QA RESERVE IFRS17")

        again = _json(self.app.handle("GET", "/v0/specs/qa-reserve/yaml"))
        self.assertIn("note: overlay", again["yaml"])
        self.assertIs(again["storage"]["overlay"], True)

    def test_put_empty_and_untitled(self) -> None:
        empty = self.app.handle(
            "PUT",
            "/v0/specs/sos",
            json.dumps({"content": "  \n"}).encode(),
            self.auth,
        )
        self.assertEqual(empty.status, 400)
        self.assertEqual(_json(empty)["error"], "empty_content")

        untitled = self.app.handle(
            "PUT",
            "/v0/specs/sos",
            json.dumps({"content": "kind: x\n", "name": "Untitled"}).encode(),
            self.auth,
        )
        self.assertEqual(untitled.status, 400)
        self.assertEqual(_json(untitled)["error"], "sticky_untitled")

    def test_unknown_and_readonly(self) -> None:
        missing = self.app.handle("GET", "/v0/specs/not-a-spec")
        self.assertEqual(missing.status, 404)
        self.assertEqual(_json(missing)["error"], "unknown_spec")

        created = self.app.handle(
            "POST", "/v0/specs", json.dumps({"name": "x"}).encode(), self.auth
        )
        self.assertEqual(created.status, 400)
        self.assertEqual(_json(created)["error"], "catalog_readonly")

        deleted = self.app.handle("DELETE", "/v0/specs/sos", headers=self.auth)
        self.assertEqual(deleted.status, 400)
        self.assertEqual(_json(deleted)["error"], "catalog_readonly")

    def test_put_engine_smuggle_rejected(self) -> None:
        resp = self.app.handle(
            "PUT",
            "/v0/specs/sos",
            json.dumps({"content": "kind: x\n", "engine": "ray"}).encode(),
            self.auth,
        )
        self.assertEqual(resp.status, 400)
        self.assertEqual(_json(resp)["error"], "engine_smuggle")

    def test_jobs_seam_intact(self) -> None:
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "catalog-ok"}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        job = _json(created)
        self.assertEqual(job["kind"], "job")
        self.assertEqual(job["class"], "cpu")
        self.assertIn("payload_digest", job)
        self.assertEqual(job["local"]["demo"], "echo")


if __name__ == "__main__":
    unittest.main()
