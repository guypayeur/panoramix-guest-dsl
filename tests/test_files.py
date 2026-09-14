"""G5 files browse — store + HTTP, no sockets."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.catalog import CATALOG_IDS, CatalogStore
from dsl.errors import LocationRefused, UnknownFile, WriteRefused
from dsl.files import FileBrowser, refuse_write
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


class FileBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.browser = FileBrowser()

    def test_tabs_and_day_one_paths(self) -> None:
        summary = self.browser.tabs()
        self.assertEqual([tab["id"] for tab in summary["tabs"]], ["specs", "data", "results"])
        self.assertEqual(summary["locations"], ["guest-local"])
        self.assertEqual(summary["writes"], "refused")
        self.assertIs(summary["shared_group"], False)
        self.assertIs(summary["s3"], False)
        self.assertEqual(summary["tabs"][0]["count"], 4)

        specs = self.browser.list("specs")
        self.assertEqual([item["id"] for item in specs["items"]], list(CATALOG_IDS))
        self.assertEqual(specs["folders"][0]["path"], "catalog")
        self.assertEqual(specs["location"], "guest-local")
        sos = next(item for item in specs["items"] if item["id"] == "sos")
        self.assertEqual(sos["path"], "catalog/sos.yaml")
        self.assertEqual(sos["open"], "/?spec=sos")
        self.assertNotIn("s3Key", sos)
        self.assertNotEqual(sos["location"], "shared")

        data = self.browser.list("data")
        ids = {item["id"] for item in data["items"]}
        self.assertIn("in-sos-accounts.csv", ids)
        self.assertIn("in-reserve-accounts.csv", ids)
        folders = {folder["path"] for folder in data["folders"]}
        self.assertIn("data_in/SOS", folders)
        self.assertIn("data_in/RESERVE", folders)
        self.assertTrue(all(item["path"].startswith("fixtures/") for item in data["items"]))
        blob = json.dumps(data)
        self.assertNotIn("s3Key", blob)
        self.assertNotIn('"shared"', blob)
        self.assertNotIn("cognito", blob.lower())
        self.assertNotIn("getafixFold", blob)

        sos_only = self.browser.list("data", folder="data_in/SOS")
        self.assertTrue(sos_only["items"])
        self.assertEqual(sos_only["folders"], [])
        self.assertTrue(all(item["folder"] == "data_in/SOS" for item in sos_only["items"]))

        results = self.browser.list("results")
        result_ids = {item["id"] for item in results["items"]}
        self.assertIn("expected-sos-results.csv", result_ids)
        self.assertIn("expected-reserve-results.csv", result_ids)
        self.assertIn("out-sos-POINTER.txt", result_ids)
        self.assertIn("out-reserve-POINTER.txt", result_ids)
        self.assertGreaterEqual(results["total_count"], 4)

    def test_get_and_text(self) -> None:
        spec = self.browser.get("specs", "sos")
        self.assertIn("catalog-stub", spec["content"])
        self.assertEqual(spec["storage"]["backend"], "catalog")
        text = self.browser.text("specs", "qa-reserve")
        self.assertEqual(text["encoding"], "utf-8")
        self.assertIn("qa_reserve_ifrs17.yaml", text["content"])

        csv = self.browser.get("data", "in-sos-accounts.csv")
        self.assertEqual(csv["path"], "fixtures/data_in/SOS/accounts.csv")
        preview = self.browser.text("data", "in-sos-accounts.csv")
        self.assertIn("account_id,value", preview["content"])
        name, blob, ctype = self.browser.download("data", "in-sos-accounts.csv")
        self.assertEqual(name, "accounts.csv")
        self.assertIn(b"account_id", blob)
        self.assertIn("csv", ctype)

    def test_unknown_and_location_and_write(self) -> None:
        with self.assertRaises(UnknownFile):
            self.browser.get("data", "not-a-file")
        with self.assertRaises(LocationRefused) as ctx:
            self.browser.list("data", location="shared")
        self.assertEqual(ctx.exception.to_dict()["error"], "location_refused")
        with self.assertRaises(LocationRefused):
            self.browser.list("data", location="group")
        with self.assertRaises(WriteRefused):
            refuse_write()

    def test_empty_fixtures_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty = FileBrowser(fixtures_dir=Path(tmp))
            data = empty.list("data")
            self.assertEqual(data["total_count"], 0)
            results = empty.list("results")
            self.assertEqual(results["total_count"], 0)


class FilesHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = DslApp(
            JobStore(step_seconds=0.02),
            CatalogStore(),
            LocalAuth(secret="test-files", iterations=1000),
        )
        self.auth = _auth_headers(self.app)

    def test_info_files_api(self) -> None:
        info = self.app.handle("GET", "/v0/info")
        self.assertEqual(info.status, 200)
        body = _json(info)
        self.assertIs(body["files_api"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertIs(body["ux_journey"], True)
        self.assertEqual(body["status"], "ux-probe")
        self.assertEqual(body["files"]["tabs"], ["specs", "data", "results"])
        self.assertEqual(body["files"]["writes"], "refused")
        self.assertIs(body["files"]["shared_group"], False)
        self.assertIs(body["files"]["s3"], False)
        self.assertEqual(body, INFO_PAYLOAD)
        blob = json.dumps(body)
        self.assertNotIn("ray://", blob)
        self.assertNotIn("s3://", blob)
        self.assertNotIn("user_pool", blob)

    def test_list_get_text_http(self) -> None:
        summary = self.app.handle("GET", "/v0/files")
        self.assertEqual(summary.status, 200)
        tabs = {tab["id"]: tab for tab in _json(summary)["tabs"]}
        self.assertEqual(tabs["specs"]["count"], 4)
        self.assertGreaterEqual(tabs["data"]["count"], 4)
        self.assertGreaterEqual(tabs["results"]["count"], 4)
        self.assertIs(_json(summary)["s3"], False)

        specs = _json(self.app.handle("GET", "/v0/files/specs"))
        self.assertEqual([item["id"] for item in specs["items"]], list(CATALOG_IDS))
        sos = _json(self.app.handle("GET", "/v0/files/specs/sos"))
        self.assertEqual(sos["open"], "/?spec=sos")
        self.assertIn("catalog-stub", sos["content"])

        listed = self.app.handle("GET", "/v0/files/data")
        self.assertEqual(listed.status, 200)
        ids = [item["id"] for item in _json(listed)["items"]]
        self.assertIn("in-sos-accounts.csv", ids)

        foldered = _json(self.app.handle("GET", "/v0/files/data?folder=data_in/SOS"))
        self.assertTrue(all(item["folder"] == "data_in/SOS" for item in foldered["items"]))

        text = self.app.handle("GET", "/v0/files/data/in-sos-accounts.csv/text")
        self.assertEqual(text.status, 200)
        self.assertIn("account_id,value", _json(text)["content"])

        raw = self.app.handle("GET", "/v0/files/data/in-sos-accounts.csv/download")
        self.assertEqual(raw.status, 200)
        self.assertIn(b"account_id", raw.body)
        self.assertIn("accounts.csv", (raw.headers or {}).get("Content-Disposition", ""))

        results = _json(self.app.handle("GET", "/v0/files/results"))
        self.assertTrue(any(item["id"].startswith("expected-") for item in results["items"]))
        self.assertTrue(any(item["id"].startswith("out-") for item in results["items"]))

    def test_writes_refused_with_and_without_auth(self) -> None:
        body = json.dumps({"filename": "upload.csv"}).encode()
        for method, path in (
            ("POST", "/v0/files"),
            ("POST", "/v0/files/data"),
            ("PUT", "/v0/files/data/in-sos-accounts.csv"),
            ("DELETE", "/v0/files/data/in-sos-accounts.csv"),
            ("POST", "/v0/files/data/in-sos-accounts.csv/move"),
            ("POST", "/v0/files/specs"),
            ("DELETE", "/v0/files/results/out-sos-POINTER.txt"),
        ):
            with self.subTest(method=method, path=path, auth=False):
                resp = self.app.handle(method, path, body)
                self.assertEqual(resp.status, 400)
                self.assertEqual(_json(resp)["error"], "write_refused")
            with self.subTest(method=method, path=path, auth=True):
                resp = self.app.handle(method, path, body, self.auth)
                self.assertEqual(resp.status, 400)
                self.assertEqual(_json(resp)["error"], "write_refused")

    def test_shared_group_location_refused(self) -> None:
        for location in ("shared", "group", "user", "s3"):
            resp = self.app.handle("GET", f"/v0/files/data?location={location}")
            self.assertEqual(resp.status, 400, location)
            self.assertEqual(_json(resp)["error"], "location_refused")

    def test_unknown_file_and_bad_tab(self) -> None:
        missing = self.app.handle("GET", "/v0/files/data/not-a-file")
        self.assertEqual(missing.status, 404)
        self.assertEqual(_json(missing)["error"], "unknown_file")
        missing_spec = self.app.handle("GET", "/v0/files/specs/not-a-spec")
        self.assertEqual(missing_spec.status, 404)
        self.assertEqual(_json(missing_spec)["error"], "unknown_file")
        bad_tab = self.app.handle("GET", "/v0/files/shared")
        self.assertEqual(bad_tab.status, 404)
        traversal = self.app.handle("GET", "/v0/files/data/..%2Fcatalog")
        self.assertEqual(traversal.status, 400)
        self.assertEqual(_json(traversal)["error"], "invalid_file_id")

    def test_overlay_spec_preview_and_disk_untouched(self) -> None:
        put = self.app.handle(
            "PUT",
            "/v0/specs/sos",
            json.dumps({"content": "metadata:\n  id: sos\n  kind: overlay-stub\n"}).encode(),
            self.auth,
        )
        self.assertEqual(put.status, 200)
        preview = _json(self.app.handle("GET", "/v0/files/specs/sos/text"))
        self.assertIn("overlay-stub", preview["content"])
        listed = _json(self.app.handle("GET", "/v0/files/specs"))
        sos = next(item for item in listed["items"] if item["id"] == "sos")
        self.assertTrue(sos["overlay"])
        on_disk = (Path(__file__).resolve().parents[1] / "catalog" / "sos.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("catalog-stub", on_disk)
        self.assertNotIn("overlay-stub", on_disk)

    def test_jobs_catalog_auth_intact(self) -> None:
        listed = self.app.handle("GET", "/v0/specs")
        self.assertEqual(_json(listed)["total_count"], 4)
        created = self.app.handle(
            "POST",
            "/v0/jobs",
            json.dumps({"demo": "echo", "message": "files-ok"}).encode(),
            self.auth,
        )
        self.assertEqual(created.status, 201)
        self.assertEqual(_json(created)["kind"], "job")
        info = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(info["north_star_done"], False)
        self.assertEqual(info["pin"], "0.5")


if __name__ == "__main__":
    unittest.main()
