"""G0 dispatch tests — no listening sockets, no jobs API."""

from __future__ import annotations

import unittest

from platform_run import INFO_PAYLOAD, handle, parse_listen


class ParseListenTests(unittest.TestCase):
    def test_shapes(self) -> None:
        self.assertEqual(parse_listen("18380"), ("127.0.0.1", 18380))
        self.assertEqual(parse_listen(":18380"), ("0.0.0.0", 18380))
        self.assertEqual(parse_listen("0.0.0.0:18380"), ("0.0.0.0", 18380))
        self.assertEqual(parse_listen("127.0.0.1:18380"), ("127.0.0.1", 18380))


class HandleTests(unittest.TestCase):
    def test_health_and_info(self) -> None:
        status, body = handle("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

        status, body = handle("GET", "/v0/info")
        self.assertEqual(status, 200)
        self.assertEqual(body["unit"], "dsl")
        self.assertEqual(body["name"], "dsl")
        self.assertEqual(body["pin"], "0.5")
        self.assertEqual(body["contract_version"], "0.5")
        self.assertEqual(body["status"], "skeleton")
        self.assertIs(body["jobs_api"], False)
        self.assertIs(body["ui"], False)
        self.assertIs(body["north_star_done"], False)
        self.assertIs(body["getafix_equivalent"], False)
        self.assertEqual(body["engines"], "runtime-bindings-only")
        self.assertEqual(body["handoff"], ["kind", "class", "payload_digest"])
        self.assertEqual(body, INFO_PAYLOAD)

    def test_no_jobs_api(self) -> None:
        status, body = handle("POST", "/v0/jobs")
        self.assertEqual(status, 404)
        self.assertEqual(body["error"], "not_found")

        status, body = handle("GET", "/v0/jobs")
        self.assertEqual(status, 404)

    def test_method_and_missing(self) -> None:
        status, body = handle("POST", "/health")
        self.assertEqual(status, 405)
        self.assertEqual(body["error"], "method_not_allowed")

        status, body = handle("GET", "/nope")
        self.assertEqual(status, 404)
        self.assertEqual(body["path"], "/nope")


if __name__ == "__main__":
    unittest.main()
