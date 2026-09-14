"""G8 AI chat — tools mutate graph, fail closed, persist needs Bearer."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest import mock

from dsl.auth import DEFAULT_SEED_PASSWORD, SEED_EMAIL, LocalAuth
from dsl.chat import (
    DEFAULT_KEY_FILE,
    DEFAULT_MODEL,
    FAMILY,
    KEY_ENV,
    KEY_ENVS,
    PROVIDER,
    STUB_ENV,
    TOOL_NAMES,
    TOOL_SPECS,
    XAI_URL,
    ChatService,
    ModelTurn,
    ScriptedDriver,
    ToolCall,
    XAIDriver,
    apply_results,
    env_key,
    execute_tool,
    format_sse,
    openai_tools,
    parse_stub_message,
)
from dsl.errors import ChatUnavailable
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


def _app(chat: ChatService | None = None) -> DslApp:
    return DslApp(
        JobStore(step_seconds=0.02),
        auth=LocalAuth(secret="test-chat", iterations=1000),
        chat=chat if chat is not None else ChatService(mode="stub"),
    )


class ToolUnitTests(unittest.TestCase):
    def test_create_update_connect_delete(self) -> None:
        state: dict = {"nodes": [], "edges": []}
        created = execute_tool(
            "create_data_source",
            {
                "label": "accounts",
                "filename": "accounts.csv",
                "context": "outer",
                "provides": ["AGE"],
            },
            state,
        )
        self.assertTrue(created.success)
        self.assertEqual(created.action, "create")
        self.assertEqual(created.node["type"], "dataSource")
        state = apply_results(state, [created])

        loop = execute_tool(
            "create_loop",
            {
                "label": "Outer T",
                "loopType": "outer",
                "dimension": "T_OUTER",
                "size": 12,
            },
            state,
        )
        self.assertTrue(loop.success)
        state = apply_results(state, [loop])

        formula = execute_tool(
            "create_formula",
            {"label": "Step", "section": "step", "formulas": {"RESULT": "AGE"}},
            state,
        )
        self.assertTrue(formula.success)
        state = apply_results(state, [formula])

        agg = execute_tool(
            "create_aggregation",
            {"label": "Mean", "variable": "RESULT", "reduce": "mean", "over": "S_INNER"},
            state,
        )
        self.assertTrue(agg.success)
        state = apply_results(state, [agg])

        linked = execute_tool(
            "connect_nodes",
            {"sourceId": created.node["id"], "targetId": loop.node["id"]},
            state,
        )
        self.assertTrue(linked.success)
        state = apply_results(state, [linked])
        self.assertEqual(len(state["edges"]), 1)

        updated = execute_tool(
            "update_node",
            {"nodeId": created.node["id"], "updates": {"filename": "people.csv"}},
            state,
        )
        self.assertTrue(updated.success)
        state = apply_results(state, [updated])
        self.assertEqual(state["nodes"][0]["filename"], "people.csv")

        missing = execute_tool("delete_node", {"nodeId": "nope"}, state)
        self.assertFalse(missing.success)

        deleted = execute_tool("delete_node", {"nodeId": created.node["id"]}, state)
        self.assertTrue(deleted.success)
        state = apply_results(state, [deleted])
        self.assertEqual(len(state["nodes"]), 3)
        self.assertEqual(state["edges"], [])

        inspect = execute_tool("get_current_state", {}, state)
        self.assertTrue(inspect.success)
        self.assertIn("3 nodes", inspect.message)

        skill = execute_tool("load_skill", {"skillName": "formulas"}, state)
        self.assertTrue(skill.success)
        self.assertIn("init", skill.message)

    def test_stub_parses_chatpanel_examples(self) -> None:
        empty: dict = {"nodes": [], "edges": []}
        ds = parse_stub_message("Create a data source for population.csv", empty)
        self.assertEqual(ds[0].name, "create_data_source")
        self.assertEqual(ds[0].input["filename"], "population.csv")
        loop = parse_stub_message("Add an outer loop with 100 iterations", empty)
        self.assertEqual(loop[0].name, "create_loop")
        self.assertEqual(loop[0].input["size"], 100)
        formula = parse_stub_message("Create a formula for calculating returns", empty)
        self.assertEqual(formula[0].name, "create_formula")


class FailClosedTests(unittest.TestCase):
    def test_unavailable_without_key_or_stub(self) -> None:
        service = ChatService(mode="unavailable")
        self.assertFalse(service.available())
        self.assertEqual(service.status()["mode"], "unavailable")
        with self.assertRaises(ChatUnavailable):
            service.run({"message": "hello", "dslState": {"nodes": [], "edges": []}})

        app = _app(ChatService(mode="unavailable"))
        denied = app.handle(
            "POST",
            "/v0/chat",
            json.dumps({"message": "Create a data source for population.csv"}).encode(),
        )
        self.assertEqual(denied.status, 503)
        body = _json(denied)
        self.assertEqual(body["error"], "chat_unavailable")
        self.assertIn(STUB_ENV, body["detail"])
        self.assertIn(KEY_ENV, body["detail"])
        self.assertIn(DEFAULT_KEY_FILE, body["detail"])

        status = _json(app.handle("GET", "/v0/chat"))
        self.assertIs(status["available"], False)
        self.assertNotIn("provider", status)
        self.assertIs(status["cognito"], False)
        self.assertIs(status["getafix"], False)
        self.assertIs(status["spot"], False)
        self.assertNotIn("ANTHROPIC", json.dumps(status).upper())


class ChatHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = _app()
        self.auth = _auth_headers(self.app)

    def test_info_chat_api_north_star_false(self) -> None:
        body = _json(self.app.handle("GET", "/v0/info"))
        self.assertIs(body["chat_api"], True)
        self.assertIs(INFO_PAYLOAD["chat_api"], True)
        self.assertIs(body["north_star_done"], False)
        self.assertEqual(body["chat"]["tools"], list(TOOL_NAMES))
        self.assertIs(body["chat"]["fail_closed"], True)
        self.assertEqual(body["chat"]["provider"], PROVIDER)
        self.assertEqual(body["chat"]["family"], FAMILY)
        self.assertEqual(body["chat"]["key_env"], KEY_ENV)
        self.assertEqual(body["chat"]["key_file"], DEFAULT_KEY_FILE)
        self.assertIs(body["chat"]["cognito"], False)
        self.assertIs(body["chat"]["spot"], False)
        self.assertIs(body["auth"]["cognito"], False)
        self.assertIn("POST /v0/chat", body["auth"]["public"])
        self.assertIn("POST /v0/chat persist overlay", body["auth"]["protected"])
        blob = json.dumps(body).lower()
        self.assertNotIn("user_pool", blob)
        self.assertNotIn("spot first", blob)
        self.assertNotIn("ray://", blob)

    def test_stub_creates_and_connects(self) -> None:
        first = self.app.handle(
            "POST",
            "/v0/chat",
            json.dumps(
                {
                    "message": "Create a data source for population.csv",
                    "dslState": {"nodes": [], "edges": []},
                }
            ).encode(),
        )
        self.assertEqual(first.status, 200)
        created = _json(first)
        self.assertEqual(created["mode"], "stub")
        status = _json(self.app.handle("GET", "/v0/chat"))
        self.assertIs(status["available"], True)
        self.assertEqual(status["mode"], "stub")
        self.assertEqual(status["provider"], PROVIDER)
        self.assertEqual(status["family"], FAMILY)
        self.assertTrue(created["toolResults"][0]["success"])
        self.assertEqual(created["toolResults"][0]["action"], "create")
        types = [node["type"] for node in created["graph"]["nodes"]]
        self.assertEqual(types, ["dataSource"])

        second = _json(
            self.app.handle(
                "POST",
                "/v0/chat",
                json.dumps(
                    {
                        "message": "Add an outer loop with 100 iterations",
                        "graph": created["graph"],
                    }
                ).encode(),
            )
        )
        ids = {node["type"]: node["id"] for node in second["graph"]["nodes"]}
        linked = _json(
            self.app.handle(
                "POST",
                "/v0/chat",
                json.dumps(
                    {
                        "message": f"connect {ids['dataSource']} to {ids['loop']}",
                        "dslState": second["graph"],
                    }
                ).encode(),
            )
        )
        self.assertEqual(linked["toolResults"][0]["action"], "connect")
        self.assertEqual(len(linked["graph"]["edges"]), 1)

        removed = _json(
            self.app.handle(
                "POST",
                "/v0/chat",
                json.dumps(
                    {
                        "message": f"delete {ids['loop']}",
                        "dslState": linked["graph"],
                    }
                ).encode(),
            )
        )
        self.assertEqual([node["type"] for node in removed["graph"]["nodes"]], ["dataSource"])
        self.assertEqual(removed["graph"]["edges"], [])

    def test_explicit_tools_and_sse(self) -> None:
        payload = {
            "message": "scripted tools",
            "dslState": {"nodes": [], "edges": []},
            "tools": [
                {
                    "name": "create_formula",
                    "input": {
                        "label": "Init",
                        "section": "init",
                        "formulas": {"X": "1"},
                    },
                }
            ],
        }
        json_resp = self.app.handle("POST", "/v0/chat", json.dumps(payload).encode())
        self.assertEqual(_json(json_resp)["graph"]["nodes"][0]["type"], "formula")

        sse = self.app.handle(
            "POST",
            "/v0/chat",
            json.dumps(payload).encode(),
            {"accept": "text/event-stream"},
        )
        self.assertEqual(sse.status, 200)
        self.assertEqual(sse.content_type, "text/event-stream")
        text = sse.body.decode("utf-8")
        self.assertIn("data: ", text)
        self.assertIn("[DONE]", text)
        self.assertIn("create_formula", text)
        self.assertIn('"type":"tool_use"', text.replace(" ", ""))
        frames = format_sse(_json(json_resp)["events"]).decode("utf-8")
        self.assertIn("message", frames)

    def test_persist_requires_bearer(self) -> None:
        body = {
            "message": "Create a data source for accounts.csv",
            "dslState": {"nodes": [], "edges": []},
            "persist": True,
            "spec_id": "qa-reserve",
        }
        denied = self.app.handle("POST", "/v0/chat", json.dumps(body).encode())
        self.assertEqual(denied.status, 401)
        self.assertEqual(_json(denied)["error"], "unauthorized")

        saved = self.app.handle(
            "POST",
            "/v0/chat",
            json.dumps(body).encode(),
            self.auth,
        )
        self.assertEqual(saved.status, 200)
        payload = _json(saved)
        self.assertTrue(payload["persisted"]["storage"]["overlay"])
        opened = _json(self.app.handle("GET", "/v0/specs/qa-reserve"))
        self.assertIn("dataSource", opened["content"])

    def test_mocked_model_driver(self) -> None:
        driver = ScriptedDriver(
            [
                ModelTurn(
                    tool_calls=[
                        ToolCall(
                            "create_loop",
                            {
                                "label": "Inner S",
                                "loopType": "inner",
                                "dimension": "S_INNER",
                                "size": 50,
                            },
                        )
                    ]
                ),
                ModelTurn(text="Added the inner loop."),
            ]
        )
        app = _app(ChatService(mode="live", driver=driver))
        resp = app.handle(
            "POST",
            "/v0/chat",
            json.dumps(
                {
                    "message": "please add an inner loop",
                    "dslState": {"nodes": [], "edges": []},
                }
            ).encode(),
        )
        self.assertEqual(resp.status, 200)
        body = _json(resp)
        self.assertEqual(body["mode"], "live")
        self.assertEqual(body["content"], "Added the inner loop.")
        self.assertEqual(body["graph"]["nodes"][0]["loopType"], "inner")
        self.assertEqual(driver.calls, 2)

    def test_empty_message_and_smuggle(self) -> None:
        missing = self.app.handle("POST", "/v0/chat", json.dumps({}).encode())
        self.assertEqual(missing.status, 400)
        self.assertEqual(_json(missing)["error"], "invalid_chat")
        smuggled = self.app.handle(
            "POST",
            "/v0/chat",
            json.dumps(
                {
                    "message": "hello",
                    "engine": "ray",
                    "dslState": {"nodes": [], "edges": []},
                }
            ).encode(),
        )
        self.assertEqual(smuggled.status, 400)
        self.assertEqual(_json(smuggled)["error"], "engine_smuggle")

    def test_usage_recorded(self) -> None:
        self.app.handle(
            "POST",
            "/v0/chat",
            json.dumps(
                {
                    "message": "Create a data source for population.csv",
                    "dslState": {"nodes": [], "edges": []},
                }
            ).encode(),
        )
        usage = _json(self.app.handle("GET", "/v0/chat/usage"))
        self.assertEqual(usage["totals"]["requestCount"], 1)
        self.assertEqual(usage["usage"][0]["totalTokens"], 0)

    def test_editor_exposes_chat_panel(self) -> None:
        html = self.app.handle("GET", "/").body.decode("utf-8")
        for hook in (
            'data-testid="chat-toggle"',
            'data-testid="chat-panel"',
            'data-testid="chat-input"',
            'data-testid="chat-send"',
            'data-testid="chat-persist"',
            "XAI_API_KEY",
            "~/.xai",
        ):
            self.assertIn(hook, html)
        self.assertNotIn("ANTHROPIC_API_KEY", html)
        self.assertNotIn("spot", html.lower())
        self.assertNotIn("cognito", html.lower())
        script = self.app.handle("GET", "/ui/app.js").body.decode("utf-8")
        self.assertIn("/v0/chat", script)
        self.assertIn("applyToolResult", script)
        self.assertIn("text/event-stream", script)
        self.assertNotIn("user_pool", script)
        self.assertNotIn("spot", script.lower())


_KEY_VARS = (
    "XAI_API_KEY",
    "GROK_API_KEY",
    "DSL_CHAT_API_KEY",
    "XAI_API_KEY_FILE",
    "ANTHROPIC_API_KEY",
    "DSL_CHAT_MODEL",
    "XAI_MODEL",
)


def _isolated_env(**extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in _KEY_VARS}
    env.update(extra)
    return env


class KeyResolutionTests(unittest.TestCase):
    def test_env_order_then_file_then_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            file_key = os.path.join(tmp, "explicit.key")
            with open(file_key, "w", encoding="utf-8") as handle:
                handle.write("file-test-key\n")
            home = os.path.join(tmp, "home")
            os.makedirs(home)
            with open(os.path.join(home, ".xai"), "w", encoding="utf-8") as handle:
                handle.write("home-test-key\n")

            with mock.patch.dict(
                os.environ,
                _isolated_env(
                    XAI_API_KEY="xai-test-key",
                    GROK_API_KEY="grok-test-key",
                    DSL_CHAT_API_KEY="dsl-test-key",
                    XAI_API_KEY_FILE=file_key,
                    HOME=home,
                ),
                clear=True,
            ):
                self.assertEqual(env_key(), "xai-test-key")

            with mock.patch.dict(
                os.environ,
                _isolated_env(
                    GROK_API_KEY="grok-test-key",
                    DSL_CHAT_API_KEY="dsl-test-key",
                    XAI_API_KEY_FILE=file_key,
                    HOME=home,
                ),
                clear=True,
            ):
                self.assertEqual(env_key(), "grok-test-key")

            with mock.patch.dict(
                os.environ,
                _isolated_env(
                    DSL_CHAT_API_KEY="dsl-test-key",
                    XAI_API_KEY_FILE=file_key,
                    HOME=home,
                ),
                clear=True,
            ):
                self.assertEqual(env_key(), "dsl-test-key")

            with mock.patch.dict(
                os.environ,
                _isolated_env(XAI_API_KEY_FILE=file_key, HOME=home),
                clear=True,
            ):
                self.assertEqual(env_key(), "file-test-key")

            with mock.patch.dict(
                os.environ,
                _isolated_env(HOME=home),
                clear=True,
            ):
                self.assertEqual(env_key(), "home-test-key")
                service = ChatService()
                self.assertTrue(service.available())
                self.assertEqual(service.mode, "live")

            empty_home = os.path.join(tmp, "empty-home")
            os.makedirs(empty_home)
            with mock.patch.dict(
                os.environ,
                _isolated_env(HOME=empty_home),
                clear=True,
            ):
                self.assertEqual(env_key(), "")
                service = ChatService()
                self.assertFalse(service.available())

    def test_stub_still_works_without_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                _isolated_env(HOME=tmp, DSL_CHAT_STUB="1"),
                clear=True,
            ):
                service = ChatService()
                self.assertEqual(service.mode, "stub")
                turn = service.run(
                    {
                        "message": "Create a data source for population.csv",
                        "dslState": {"nodes": [], "edges": []},
                    }
                )
                self.assertEqual(turn.mode, "stub")
                self.assertEqual(turn.graph["nodes"][0]["type"], "dataSource")

    def test_status_never_includes_key(self) -> None:
        secret = "dummy-xai-test-key-not-for-ci"
        service = ChatService(mode="live", api_key=secret)
        blob = json.dumps(service.status())
        self.assertNotIn(secret, blob)
        self.assertEqual(service.status()["provider"], PROVIDER)
        self.assertEqual(service.status()["family"], FAMILY)
        self.assertEqual(tuple(service.status()["key_envs"]), KEY_ENVS)


class XaiHttpTests(unittest.TestCase):
    def test_driver_posts_chat_completions(self) -> None:
        captured: dict = {}

        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["authorization"] = request.get_header("Authorization")
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_loop",
                                        "type": "function",
                                        "function": {
                                            "name": "create_loop",
                                            "arguments": json.dumps(
                                                {
                                                    "label": "Inner S",
                                                    "loopType": "inner",
                                                    "dimension": "S_INNER",
                                                    "size": 50,
                                                }
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 11, "completion_tokens": 4},
                }
            ).encode("utf-8")

        driver = XAIDriver("dummy-xai-test-key", opener=opener)
        turn = driver.complete(
            [{"role": "user", "content": "add an inner loop"}],
            TOOL_SPECS,
            "sys",
        )
        self.assertEqual(captured["url"], XAI_URL)
        self.assertEqual(captured["authorization"], "Bearer dummy-xai-test-key")
        self.assertEqual(captured["body"]["model"], DEFAULT_MODEL)
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")
        self.assertEqual(captured["body"]["tools"][0]["type"], "function")
        self.assertEqual(
            captured["body"]["tools"][0]["function"]["name"],
            openai_tools(TOOL_SPECS)[0]["function"]["name"],
        )
        self.assertEqual(turn.tool_calls[0].name, "create_loop")
        self.assertEqual(turn.tool_calls[0].input["size"], 50)
        self.assertEqual(turn.input_tokens, 11)
        self.assertEqual(turn.output_tokens, 4)

    def test_live_service_uses_mocked_xai(self) -> None:
        def opener(request, timeout):
            del timeout
            body = json.loads(request.data.decode("utf-8"))
            has_tool = any(item.get("role") == "tool" for item in body["messages"])
            if not has_tool:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_ds",
                                            "type": "function",
                                            "function": {
                                                "name": "create_data_source",
                                                "arguments": json.dumps(
                                                    {
                                                        "label": "population",
                                                        "filename": "population.csv",
                                                        "context": "outer",
                                                        "provides": ["POPULATION"],
                                                    }
                                                ),
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {"prompt_tokens": 8, "completion_tokens": 6},
                    }
                ).encode("utf-8")
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "Created the data source.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 5},
                }
            ).encode("utf-8")

        service = ChatService(
            mode="live",
            api_key="dummy-xai-test-key",
            driver=XAIDriver("dummy-xai-test-key", opener=opener),
        )
        app = _app(service)
        status = _json(app.handle("GET", "/v0/chat"))
        self.assertIs(status["available"], True)
        self.assertEqual(status["mode"], "live")
        self.assertEqual(status["provider"], "xai")
        self.assertEqual(status["family"], "grok")
        self.assertNotIn("dummy-xai-test-key", json.dumps(status))

        resp = app.handle(
            "POST",
            "/v0/chat",
            json.dumps(
                {
                    "message": "Create a data source for population.csv",
                    "dslState": {"nodes": [], "edges": []},
                }
            ).encode(),
        )
        self.assertEqual(resp.status, 200)
        body = _json(resp)
        self.assertEqual(body["mode"], "live")
        self.assertEqual(body["content"], "Created the data source.")
        self.assertEqual(body["graph"]["nodes"][0]["type"], "dataSource")
        self.assertEqual(body["usage"]["totalTokens"], 31)


if __name__ == "__main__":
    unittest.main()
