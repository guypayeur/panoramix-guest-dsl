"""G8 AI chat — dsl-gui ChatPanel *intention*, not a Getafix/SPA lift.

SSE / MCP-style tools mutate the live editor graph (create / update /
connect / delete). Live model is xAI Grok Chat Completions (stdlib
urllib). Fail closed without a Grok key unless documented stub mode
(DSL_CHAT_STUB=1) or a test-injected driver. Key order: XAI_API_KEY /
GROK_API_KEY / DSL_CHAT_API_KEY, else XAI_API_KEY_FILE, else ~/.xai.
Never log or persist the key. Persisting a mutated overlay is G6 Bearer
(same as PUT /v0/specs). No Cognito. No Spot. Stdlib only — no SDK.
"""

from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from dsl.errors import ChatError, ChatUnavailable, InvalidChat
from dsl.graph import NODE_TYPES, document_from_graph, emit_yaml

STUB_ENV = "DSL_CHAT_STUB"
KEY_ENV = "XAI_API_KEY"
KEY_ENV_GROK = "GROK_API_KEY"
KEY_ENV_ALT = "DSL_CHAT_API_KEY"
KEY_ENVS = (KEY_ENV, KEY_ENV_GROK, KEY_ENV_ALT)
KEY_FILE_ENV = "XAI_API_KEY_FILE"
DEFAULT_KEY_FILE = "~/.xai"
MODEL_ENV = "DSL_CHAT_MODEL"
MODEL_ENV_ALT = "XAI_MODEL"
DEFAULT_MODEL = "grok-3"
XAI_URL = "https://api.x.ai/v1/chat/completions"
URL_ENV = "XAI_API_URL"
URL_ENV_ALT = "DSL_CHAT_URL"
PROVIDER = "xai"
FAMILY = "grok"

TOOL_NAMES = (
    "create_data_source",
    "create_loop",
    "create_formula",
    "create_aggregation",
    "update_node",
    "delete_node",
    "connect_nodes",
    "get_current_state",
    "load_skill",
)

SKILLS: dict[str, str] = {
    "actuarial-dsl": (
        "Guest-dsl graph: DataSource, Loop (outer/inner), Formula (init/step), "
        "Aggregation (mean/sum/min/max/count). Not a dsl-work CuPy lift."
    ),
    "data-sources": (
        "DataSource nodes load CSV. Set filename, context (outer|inner), "
        "provides (column names), optional index."
    ),
    "loops": (
        "Loop nodes: outer = time / accounts, inner = scenarios. "
        "Set loopType, dimension, size, optional vectorize."
    ),
    "formulas": (
        "Formula nodes: section init (T0) or step (T>0). "
        "formulas is a name → expression map. Names must be provided."
    ),
    "aggregation": (
        "Aggregation nodes reduce a variable over a dimension "
        "(mean/sum/min/max/count) with an optional condition."
    ),
}

SYSTEM_PROMPT = (
    "You are the guest-dsl editor assistant. Mutate the live DSL graph only "
    "via tools. Node types: dataSource, loop, formula, aggregation. "
    "Do not invent engine URLs, Cognito, Spot, or Matryoshka cones. "
    "Prefer the smallest set of tool calls that satisfies the user."
)

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FILENAME_RE = re.compile(
    r"(?:for|from|named|called)\s+([A-Za-z0-9._/-]+\.(?:csv|txt|json|yaml|yml))",
    re.IGNORECASE,
)
_CONNECT_RE = re.compile(
    r"connect\s+(\S+)\s+to\s+(\S+)",
    re.IGNORECASE,
)
_DELETE_RE = re.compile(
    r"delete\s+(?:node\s+)?(\S+)",
    re.IGNORECASE,
)
_UPDATE_RE = re.compile(
    r"update\s+(?:node\s+)?(\S+)",
    re.IGNORECASE,
)
_SIZE_RE = re.compile(r"(\d+)\s+iterations", re.IGNORECASE)


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUTHY


def env_model() -> str:
    return (
        (os.environ.get(MODEL_ENV) or os.environ.get(MODEL_ENV_ALT) or "").strip()
        or DEFAULT_MODEL
    )


def env_url() -> str:
    return (
        (os.environ.get(URL_ENV) or os.environ.get(URL_ENV_ALT) or "").strip()
        or XAI_URL
    )


def _read_key_file(path: str) -> str:
    """First line of a key file. Empty on missing / unreadable. Never logs."""
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            line = handle.readline()
    except OSError:
        return ""
    return line.strip()


def env_key() -> str:
    """Resolve a Grok key. Fail closed (empty) if none. Never log the value."""
    for name in KEY_ENVS:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    file_env = (os.environ.get(KEY_FILE_ENV) or "").strip()
    if file_env:
        value = _read_key_file(file_env)
        if value:
            return value
    home = (os.environ.get("HOME") or "").strip()
    candidates: list[str] = []
    expanded = os.path.expanduser(DEFAULT_KEY_FILE)
    if expanded:
        candidates.append(expanded)
    if home:
        candidates.append(os.path.join(home, ".xai"))
    seen: set[str] = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        value = _read_key_file(path)
        if value:
            return value
    return ""


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "create_data_source",
        "description": "Create data source node for CSV",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "filename": {"type": "string"},
                "context": {"type": "string", "enum": ["outer", "inner"]},
                "provides": {"type": "array", "items": {"type": "string"}},
                "index": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "filename", "context", "provides"],
        },
    },
    {
        "name": "create_loop",
        "description": "Create loop node (outer=time, inner=scenarios)",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "loopType": {"type": "string", "enum": ["outer", "inner"]},
                "dimension": {"type": "string"},
                "size": {"type": "number"},
                "vectorize": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["label", "loopType", "dimension", "size"],
        },
    },
    {
        "name": "create_formula",
        "description": "Create formula node (init=T0, step=T>0)",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "section": {"type": "string", "enum": ["init", "step"]},
                "formulas": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["label", "section", "formulas"],
        },
    },
    {
        "name": "create_aggregation",
        "description": "Create aggregation node for statistics",
        "input_schema": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "variable": {"type": "string"},
                "condition": {
                    "type": "object",
                    "properties": {
                        "variable": {"type": "string"},
                        "operator": {
                            "type": "string",
                            "enum": ["==", "!=", ">", ">=", "<", "<="],
                        },
                        "value": {"type": "number"},
                    },
                },
                "reduce": {
                    "type": "string",
                    "enum": ["mean", "sum", "min", "max", "count"],
                },
                "over": {"type": "string"},
            },
            "required": ["label", "variable", "reduce", "over"],
        },
    },
    {
        "name": "update_node",
        "description": "Update existing node properties",
        "input_schema": {
            "type": "object",
            "properties": {
                "nodeId": {"type": "string"},
                "updates": {"type": "object"},
            },
            "required": ["nodeId", "updates"],
        },
    },
    {
        "name": "delete_node",
        "description": "Delete node by ID",
        "input_schema": {
            "type": "object",
            "properties": {"nodeId": {"type": "string"}},
            "required": ["nodeId"],
        },
    },
    {
        "name": "connect_nodes",
        "description": "Connect two nodes with edge",
        "input_schema": {
            "type": "object",
            "properties": {
                "sourceId": {"type": "string"},
                "targetId": {"type": "string"},
            },
            "required": ["sourceId", "targetId"],
        },
    },
    {
        "name": "get_current_state",
        "description": "Get current DSL nodes and edges",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "load_skill",
        "description": "Load domain knowledge for DSL concepts",
        "input_schema": {
            "type": "object",
            "properties": {"skillName": {"type": "string"}},
            "required": ["skillName"],
        },
    },
]


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = generate_id("call")


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = "end_turn"


class ModelDriver(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ModelTurn: ...


@dataclass
class ToolResult:
    success: bool
    action: str
    message: str
    node: dict[str, Any] | None = None
    edge: dict[str, Any] | None = None
    node_id: str | None = None
    tool: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "success": self.success,
            "action": self.action,
            "message": self.message,
        }
        if self.tool:
            payload["tool"] = self.tool
        if self.node is not None:
            payload["node"] = self.node
        if self.edge is not None:
            payload["edge"] = self.edge
        if self.node_id:
            payload["nodeId"] = self.node_id
        return payload


@dataclass
class ChatTurn:
    mode: str
    content: str
    tool_results: list[ToolResult]
    graph: dict[str, Any]
    usage: dict[str, int]
    persisted: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "content": self.content,
            "toolResults": [item.to_dict() for item in self.tool_results],
            "graph": self.graph,
            "usage": dict(self.usage),
            "events": list(self.events),
        }
        if self.persisted is not None:
            payload["persisted"] = self.persisted
        return payload


def _as_map(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _as_list(raw: Any) -> list[Any]:
    return list(raw) if isinstance(raw, list) else []


def _str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item is not None and str(item) != ""]
    return [str(raw)]


def copy_state(raw: Any) -> dict[str, Any]:
    data = _as_map(raw)
    return {
        "metadata": dict(_as_map(data.get("metadata"))),
        "description": data.get("description") or "",
        "nodes": [dict(node) for node in _as_list(data.get("nodes")) if isinstance(node, dict)],
        "edges": [dict(edge) for edge in _as_list(data.get("edges")) if isinstance(edge, dict)],
        "extras": dict(_as_map(data.get("extras"))),
    }


def state_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("dslState", "dsl_state", "graph"):
        raw = payload.get(key)
        if isinstance(raw, dict):
            return copy_state(raw)
    if any(key in payload for key in ("nodes", "edges", "metadata")):
        return copy_state(payload)
    return copy_state({})


def graph_payload(state: dict[str, Any]) -> dict[str, Any]:
    nodes = [dict(node) for node in state.get("nodes") or []]
    return {
        "metadata": dict(state.get("metadata") or {}),
        "description": state.get("description") or "",
        "nodes": nodes,
        "edges": [dict(edge) for edge in state.get("edges") or []],
        "extras": dict(state.get("extras") or {}),
        "stub": not bool(nodes),
    }


def _place_node(node: dict[str, Any], existing: list[dict[str, Any]]) -> None:
    if node.get("x") not in (None, 0, 0.0) or node.get("y") not in (None, 0, 0.0):
        return
    slots = {
        "dataSource": (48.0, 48.0),
        "loop": (48.0, 230.0),
        "formula": (340.0, 48.0),
        "aggregation": (340.0, 230.0),
    }
    same = [item for item in existing if item.get("type") == node.get("type")]
    base_x, base_y = slots.get(str(node.get("type") or ""), (80.0, 80.0))
    node["x"] = base_x + len(same) * 36.0
    node["y"] = base_y + len(same) * 24.0


def _require(tool_input: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    missing = [key for key in keys if tool_input.get(key) in (None, "")]
    if missing:
        return "missing required: " + ", ".join(missing)
    return None


def execute_tool(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    current_state: dict[str, Any],
) -> ToolResult:
    """MCP-style tool. Mutates nothing; caller applies the result."""
    args = _as_map(tool_input)
    state = copy_state(current_state)

    if tool_name == "create_data_source":
        err = _require(args, ("label", "filename", "context", "provides"))
        if err:
            return ToolResult(False, "create", err, tool=tool_name)
        node = {
            "id": generate_id("ds"),
            "type": "dataSource",
            "label": str(args["label"]),
            "filename": str(args["filename"]),
            "context": str(args.get("context") or "outer"),
            "provides": _str_list(args.get("provides")),
            "index": _str_list(args.get("index")),
            "column_map": _as_map(args.get("column_map") or args.get("columnMap")),
        }
        _place_node(node, state["nodes"])
        return ToolResult(
            True,
            "create",
            f'Created data source "{node["label"]}" loading {node["filename"]}',
            node=node,
            tool=tool_name,
        )

    if tool_name == "create_loop":
        err = _require(args, ("label", "loopType", "dimension", "size"))
        if err:
            return ToolResult(False, "create", err, tool=tool_name)
        size = args.get("size")
        if not isinstance(size, (int, float)) or isinstance(size, bool):
            return ToolResult(False, "create", "size must be a number", tool=tool_name)
        node = {
            "id": generate_id("loop"),
            "type": "loop",
            "label": str(args["label"]),
            "loopType": str(args.get("loopType") or "outer"),
            "dimension": str(args["dimension"]),
            "size": size,
            "vectorize": _str_list(args.get("vectorize")),
        }
        _place_node(node, state["nodes"])
        return ToolResult(
            True,
            "create",
            f'Created {node["loopType"]} loop "{node["label"]}" with {node["size"]} iterations',
            node=node,
            tool=tool_name,
        )

    if tool_name == "create_formula":
        err = _require(args, ("label", "section", "formulas"))
        if err:
            return ToolResult(False, "create", err, tool=tool_name)
        formulas = args.get("formulas")
        if not isinstance(formulas, dict):
            return ToolResult(False, "create", "formulas must be an object", tool=tool_name)
        node = {
            "id": generate_id("formula"),
            "type": "formula",
            "label": str(args["label"]),
            "section": str(args.get("section") or "step"),
            "formulas": {str(key): "" if value is None else str(value) for key, value in formulas.items()},
        }
        _place_node(node, state["nodes"])
        count = len(node["formulas"])
        return ToolResult(
            True,
            "create",
            f'Created {node["section"]} formula "{node["label"]}" with {count} variable(s)',
            node=node,
            tool=tool_name,
        )

    if tool_name == "create_aggregation":
        err = _require(args, ("label", "variable", "reduce", "over"))
        if err:
            return ToolResult(False, "create", err, tool=tool_name)
        cond_raw = args.get("condition")
        if isinstance(cond_raw, dict) and cond_raw:
            condition = {
                "variable": str(cond_raw.get("variable") or ""),
                "operator": str(cond_raw.get("operator") or "=="),
                "value": cond_raw.get("value") if isinstance(cond_raw.get("value"), (int, float)) else 0,
            }
        else:
            condition = {"variable": "AGE", "operator": "==", "value": 100}
        node = {
            "id": generate_id("agg"),
            "type": "aggregation",
            "label": str(args["label"]),
            "variable": str(args["variable"]),
            "condition": condition,
            "reduce": str(args.get("reduce") or "mean"),
            "over": str(args["over"]),
        }
        _place_node(node, state["nodes"])
        return ToolResult(
            True,
            "create",
            f'Created aggregation "{node["label"]}" computing {node["reduce"]} of {node["variable"]}',
            node=node,
            tool=tool_name,
        )

    if tool_name == "update_node":
        node_id = str(args.get("nodeId") or "")
        updates = _as_map(args.get("updates"))
        if not node_id:
            return ToolResult(False, "update", "nodeId is required", tool=tool_name)
        existing = next((node for node in state["nodes"] if node.get("id") == node_id), None)
        if existing is None:
            return ToolResult(
                False, "update", f'Node "{node_id}" not found', node_id=node_id, tool=tool_name
            )
        updated = dict(existing)
        for key, value in updates.items():
            if key == "type" and value not in NODE_TYPES:
                continue
            if key == "id" and value:
                updated["id"] = str(value)
            else:
                updated[key] = value
        return ToolResult(
            True,
            "update",
            f'Updated node "{node_id}"',
            node=updated,
            node_id=node_id,
            tool=tool_name,
        )

    if tool_name == "delete_node":
        node_id = str(args.get("nodeId") or "")
        if not node_id:
            return ToolResult(False, "delete", "nodeId is required", tool=tool_name)
        if not any(node.get("id") == node_id for node in state["nodes"]):
            return ToolResult(
                False, "delete", f'Node "{node_id}" not found', node_id=node_id, tool=tool_name
            )
        return ToolResult(
            True, "delete", f'Deleted node "{node_id}"', node_id=node_id, tool=tool_name
        )

    if tool_name == "connect_nodes":
        source = str(args.get("sourceId") or "")
        target = str(args.get("targetId") or "")
        if not source or not target:
            return ToolResult(False, "connect", "sourceId and targetId are required", tool=tool_name)
        if source == target:
            return ToolResult(False, "connect", "cannot connect a node to itself", tool=tool_name)
        ids = {node.get("id") for node in state["nodes"]}
        if source not in ids or target not in ids:
            return ToolResult(
                False, "connect", "source and target must exist", tool=tool_name
            )
        edge = {"id": generate_id("e"), "source": source, "target": target}
        return ToolResult(
            True,
            "connect",
            f"Connected {source} to {target}",
            edge=edge,
            tool=tool_name,
        )

    if tool_name == "get_current_state":
        nodes = state["nodes"]
        edges = state["edges"]
        listing = ", ".join(
            f"{node.get('id')} ({node.get('type')})" for node in nodes
        ) or "(none)"
        return ToolResult(
            True,
            "inspect",
            f"Current state: {len(nodes)} nodes, {len(edges)} edges. Nodes: {listing}",
            tool=tool_name,
        )

    if tool_name == "load_skill":
        name = str(args.get("skillName") or args.get("skill") or "").strip()
        key = name.lower().replace("_", "-")
        aliases = {
            "dsl": "actuarial-dsl",
            "dsl-basics": "actuarial-dsl",
            "datasource": "data-sources",
            "data-source": "data-sources",
            "loop": "loops",
            "formula": "formulas",
            "aggregations": "aggregation",
        }
        skill = SKILLS.get(key) or SKILLS.get(aliases.get(key, ""))
        if skill is None:
            return ToolResult(
                False,
                "inspect",
                f'Unknown skill "{name}". Available: {", ".join(SKILLS)}',
                tool=tool_name,
            )
        return ToolResult(True, "inspect", skill, tool=tool_name)

    return ToolResult(False, "inspect", f"Unknown tool: {tool_name}", tool=tool_name)


def apply_result(state: dict[str, Any], result: ToolResult) -> dict[str, Any]:
    """Apply one tool result to a copied graph state."""
    next_state = copy_state(state)
    if not result.success:
        return next_state
    if result.action == "create" and result.node:
        node = dict(result.node)
        _place_node(node, next_state["nodes"])
        next_state["nodes"].append(node)
    elif result.action == "update" and result.node:
        node_id = result.node_id or result.node.get("id")
        next_state["nodes"] = [
            dict(result.node) if item.get("id") == node_id else item
            for item in next_state["nodes"]
        ]
        new_id = result.node.get("id")
        if node_id and new_id and new_id != node_id:
            for edge in next_state["edges"]:
                if edge.get("source") == node_id:
                    edge["source"] = new_id
                if edge.get("target") == node_id:
                    edge["target"] = new_id
    elif result.action == "delete" and result.node_id:
        next_state["nodes"] = [
            item for item in next_state["nodes"] if item.get("id") != result.node_id
        ]
        next_state["edges"] = [
            edge
            for edge in next_state["edges"]
            if edge.get("source") != result.node_id and edge.get("target") != result.node_id
        ]
    elif result.action == "connect" and result.edge:
        pair = (result.edge.get("source"), result.edge.get("target"))
        exists = any(
            (edge.get("source"), edge.get("target")) == pair for edge in next_state["edges"]
        )
        if not exists:
            next_state["edges"].append(dict(result.edge))
    return next_state


def apply_results(state: dict[str, Any], results: list[ToolResult]) -> dict[str, Any]:
    current = copy_state(state)
    for result in results:
        current = apply_result(current, result)
    return current


def parse_stub_message(message: str, state: dict[str, Any]) -> list[ToolCall]:
    """Documented stub NL → tools. Intention match for ChatPanel examples."""
    text = (message or "").strip()
    lower = text.lower()
    if not text:
        return []

    connect = _CONNECT_RE.search(text)
    if connect:
        return [
            ToolCall(
                "connect_nodes",
                {"sourceId": connect.group(1).strip(".,"), "targetId": connect.group(2).strip(".,")},
            )
        ]

    delete = _DELETE_RE.search(text)
    if "delete" in lower and delete:
        return [ToolCall("delete_node", {"nodeId": delete.group(1).strip(".,")})]

    update = _UPDATE_RE.search(text)
    if lower.startswith("update") and update:
        node_id = update.group(1).strip(".,")
        updates: dict[str, Any] = {}
        file_hit = _FILENAME_RE.search(text)
        if file_hit:
            updates["filename"] = file_hit.group(1)
        label_hit = re.search(r"label\s+(\S+)", text, re.IGNORECASE)
        if label_hit:
            updates["label"] = label_hit.group(1).strip(".,\"'")
        if not updates:
            updates["label"] = node_id
        return [ToolCall("update_node", {"nodeId": node_id, "updates": updates})]

    if "current state" in lower or lower in {"get state", "show graph", "list nodes"}:
        return [ToolCall("get_current_state", {})]

    if "skill" in lower or "how do i" in lower or lower.startswith("explain"):
        skill = "actuarial-dsl"
        if "csv" in lower or "data" in lower or "file" in lower:
            skill = "data-sources"
        elif "loop" in lower:
            skill = "loops"
        elif "formula" in lower:
            skill = "formulas"
        elif "aggreg" in lower:
            skill = "aggregation"
        return [ToolCall("load_skill", {"skillName": skill})]

    if "data source" in lower or "datasource" in lower or "csv" in lower:
        file_hit = _FILENAME_RE.search(text)
        filename = file_hit.group(1) if file_hit else "population.csv"
        stem = filename.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        return [
            ToolCall(
                "create_data_source",
                {
                    "label": stem,
                    "filename": filename,
                    "context": "inner" if "inner" in lower else "outer",
                    "provides": [stem.upper()],
                },
            )
        ]

    if "loop" in lower:
        size_hit = _SIZE_RE.search(text)
        size = int(size_hit.group(1)) if size_hit else 100
        inner = "inner" in lower and "outer" not in lower
        loop_type = "inner" if inner else "outer"
        dim = "S_INNER" if inner else "T_OUTER"
        return [
            ToolCall(
                "create_loop",
                {
                    "label": f"{loop_type.title()} {dim}",
                    "loopType": loop_type,
                    "dimension": dim,
                    "size": size,
                },
            )
        ]

    if "aggreg" in lower:
        return [
            ToolCall(
                "create_aggregation",
                {
                    "label": "Aggregation",
                    "variable": "RESULT",
                    "reduce": "mean",
                    "over": "S_INNER",
                },
            )
        ]

    if "formula" in lower or "return" in lower:
        return [
            ToolCall(
                "create_formula",
                {
                    "label": "Returns",
                    "section": "init" if "init" in lower else "step",
                    "formulas": {"RESULT": "INPUT"},
                },
            )
        ]

    if state.get("nodes"):
        return [ToolCall("get_current_state", {})]
    return [
        ToolCall(
            "create_data_source",
            {
                "label": "population",
                "filename": "population.csv",
                "context": "outer",
                "provides": ["POPULATION"],
            },
        )
    ]


def explicit_tool_calls(raw: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    if not isinstance(raw, list):
        return calls
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("tool") or "")
        if not name:
            continue
        tool_input = item.get("input")
        if tool_input is None:
            tool_input = item.get("arguments") or item.get("args") or {}
        calls.append(ToolCall(name, _as_map(tool_input)))
    return calls


def format_sse(events: list[dict[str, Any]]) -> bytes:
    chunks: list[str] = []
    for event in events:
        chunks.append("data: " + json.dumps(event, separators=(",", ":")) + "\n\n")
    chunks.append("data: [DONE]\n\n")
    return "".join(chunks).encode("utf-8")


def want_sse(headers: dict[str, str] | None, query: dict[str, list[str]] | None = None) -> bool:
    accept = ""
    if headers:
        accept = str(headers.get("accept") or headers.get("Accept") or "")
    fmt = ""
    if query:
        fmt = (query.get("format") or [""])[0]
    return "text/event-stream" in accept.lower() or fmt.lower() == "sse"


class ScriptedDriver:
    """Test double: predetermined turns, no network."""

    def __init__(self, turns: list[ModelTurn] | None = None) -> None:
        self.turns = list(turns or [])
        self.calls = 0

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ModelTurn:
        del messages, tools, system
        self.calls += 1
        if not self.turns:
            return ModelTurn(text="(script exhausted)")
        return self.turns.pop(0)


def openai_tools(specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MCP tool specs → xAI / OpenAI Chat Completions function tools."""
    out: list[dict[str, Any]] = []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        if spec.get("type") == "function" and isinstance(spec.get("function"), dict):
            out.append(spec)
            continue
        schema = spec.get("input_schema") or spec.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        out.append(
            {
                "type": "function",
                "function": {
                    "name": str(spec.get("name") or ""),
                    "description": str(spec.get("description") or ""),
                    "parameters": schema if isinstance(schema, dict) else {"type": "object"},
                },
            }
        )
    return out


class XAIDriver:
    """Thin xAI Chat Completions client (stdlib urllib). Not an SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        url: str | None = None,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.model = model or env_model()
        self.url = url or env_url()
        self.opener = opener
        self.timeout = timeout

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> ModelTurn:
        payload_messages: list[dict[str, Any]] = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        body = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": payload_messages,
            "tools": openai_tools(tools),
            "tool_choice": "auto",
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            if self.opener is not None:
                raw = self.opener(request, self.timeout)
            else:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    raw = resp.read()
        except urllib.error.HTTPError as exc:
            exc.read()
            raise ChatError(f"model HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ChatError("model request failed") from exc
        except TimeoutError as exc:
            raise ChatError("model request timed out") from exc
        try:
            payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise ChatError("model returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ChatError("model returned invalid JSON")
        return _turn_from_xai(payload)


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _turn_from_xai(payload: dict[str, Any]) -> ModelTurn:
    usage = _as_map(payload.get("usage"))
    choices = _as_list(payload.get("choices"))
    first = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = _as_map(first.get("message"))
    text = message.get("content")
    if not isinstance(text, str):
        text = ""
    calls: list[ToolCall] = []
    for item in _as_list(message.get("tool_calls")):
        if not isinstance(item, dict):
            continue
        fn = _as_map(item.get("function"))
        name = str(fn.get("name") or item.get("name") or "")
        if not name:
            continue
        calls.append(
            ToolCall(
                name=name,
                input=_parse_tool_arguments(fn.get("arguments") or item.get("arguments")),
                id=str(item.get("id") or generate_id("call")),
            )
        )
    return ModelTurn(
        text=text,
        tool_calls=calls,
        input_tokens=int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        stop_reason=str(first.get("finish_reason") or payload.get("stop_reason") or "stop"),
    )


class ChatService:
    """Process-local chat + tools. Live xAI Grok or documented stub."""

    def __init__(
        self,
        *,
        mode: str | None = None,
        api_key: str | None = None,
        driver: ModelDriver | None = None,
        max_rounds: int = 8,
    ) -> None:
        key = (api_key if api_key is not None else env_key()).strip()
        if mode in {"stub", "live", "unavailable"}:
            resolved = mode
        elif env_flag(STUB_ENV):
            resolved = "stub"
        elif key or driver is not None:
            resolved = "live"
        else:
            resolved = "unavailable"
        self.mode = resolved
        self.api_key = key
        self.driver = driver
        self.max_rounds = max(1, int(max_rounds))
        self._lock = threading.RLock()
        self._usage: list[dict[str, Any]] = []

    @classmethod
    def from_env(cls) -> ChatService:
        return cls()

    def available(self) -> bool:
        if self.mode == "stub":
            return True
        if self.mode == "live":
            return self.driver is not None or bool(self.api_key)
        return False

    def status(self) -> dict[str, Any]:
        available = self.available()
        payload: dict[str, Any] = {
            "available": available,
            "mode": self.mode if available else "unavailable",
            "tools": list(TOOL_NAMES),
            "sse": True,
            "stub_env": STUB_ENV,
            "key_env": KEY_ENV,
            "key_envs": list(KEY_ENVS),
            "key_file": DEFAULT_KEY_FILE,
            "persist_auth": "Bearer",
            "cognito": False,
            "getafix": False,
            "spot": False,
            "note": (
                "G8 AI chat. dsl-gui ChatPanel + dsl-backend POST /api/chat "
                "intention — SSE / MCP-style tools mutate the live graph. "
                "Live provider is xAI Grok (Chat Completions). Fail closed "
                "without XAI_API_KEY / GROK_API_KEY / DSL_CHAT_API_KEY, "
                "XAI_API_KEY_FILE, or ~/.xai unless DSL_CHAT_STUB=1 or a "
                "test driver is injected. Overlay persist uses G6 Bearer. "
                "Not Cognito. Not a Getafix fold. Epic #1 remains open. "
                "Cloud stays locked."
            ),
        }
        if available:
            payload["provider"] = PROVIDER
            payload["family"] = FAMILY
            if self.mode == "live":
                payload["model"] = env_model()
        return payload

    def usage(self) -> dict[str, Any]:
        with self._lock:
            rows = list(self._usage)
        totals = {
            "inputTokens": sum(int(row.get("inputTokens") or 0) for row in rows),
            "outputTokens": sum(int(row.get("outputTokens") or 0) for row in rows),
            "totalTokens": sum(int(row.get("totalTokens") or 0) for row in rows),
            "requestCount": len(rows),
        }
        return {"usage": rows, "totals": totals}

    def _driver(self) -> ModelDriver:
        if self.driver is not None:
            return self.driver
        if self.mode == "live" and self.api_key:
            return XAIDriver(self.api_key)
        raise ChatUnavailable()

    def run(self, payload: dict[str, Any]) -> ChatTurn:
        if not self.available():
            raise ChatUnavailable()
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise InvalidChat("message is required")
        state = state_from_payload(payload)
        history = payload.get("conversationHistory") or payload.get("history") or []
        if not isinstance(history, list):
            history = []

        tool_results: list[ToolResult] = []
        events: list[dict[str, Any]] = []
        input_tokens = 0
        output_tokens = 0
        content = ""

        explicit = explicit_tool_calls(payload.get("tools"))
        if self.mode == "stub":
            calls = explicit or parse_stub_message(message, state)
            working = copy_state(state)
            for call in calls:
                result = execute_tool(call.name, call.input, working)
                tool_results.append(result)
                events.append(
                    {
                        "type": "tool_use",
                        "toolName": call.name,
                        "result": result.to_dict(),
                    }
                )
                working = apply_result(working, result)
            content = _summarize(tool_results) or "No graph changes."
        else:
            working = copy_state(state)
            messages = _history_messages(history)
            messages.append(
                {
                    "role": "user",
                    "content": f"DSL: {json.dumps(_compress_state(working), separators=(',', ':'))}\n{message.strip()}",
                }
            )
            driver = self._driver()
            rounds = 0
            while True:
                rounds += 1
                turn = driver.complete(messages, TOOL_SPECS, SYSTEM_PROMPT)
                input_tokens += turn.input_tokens
                output_tokens += turn.output_tokens
                if turn.tool_calls and rounds <= self.max_rounds:
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": turn.text or None,
                    }
                    tool_calls_payload: list[dict[str, Any]] = []
                    pending_results: list[tuple[ToolCall, ToolResult]] = []
                    for call in turn.tool_calls:
                        result = execute_tool(call.name, call.input, working)
                        tool_results.append(result)
                        events.append(
                            {
                                "type": "tool_use",
                                "toolName": call.name,
                                "result": result.to_dict(),
                            }
                        )
                        working = apply_result(working, result)
                        tool_calls_payload.append(
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(
                                        call.input, separators=(",", ":")
                                    ),
                                },
                            }
                        )
                        pending_results.append((call, result))
                    if tool_calls_payload:
                        assistant_msg["tool_calls"] = tool_calls_payload
                    messages.append(assistant_msg)
                    for call, result in pending_results:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": json.dumps(
                                    {"success": result.success, "message": result.message},
                                    separators=(",", ":"),
                                ),
                            }
                        )
                    continue
                content = turn.text or _summarize(tool_results) or "Done."
                break

        usage = {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        }
        events.append(
            {
                "type": "message",
                "content": content,
                "toolResults": [item.to_dict() for item in tool_results],
                "usage": usage,
            }
        )
        self._record_usage(message.strip(), usage)
        graph = graph_payload(working)
        return ChatTurn(
            mode=self.mode,
            content=content,
            tool_results=tool_results,
            graph=graph,
            usage=usage,
            events=events,
        )

    def _record_usage(self, message: str, usage: dict[str, int]) -> None:
        with self._lock:
            self._usage.append(
                {
                    "timestamp": utcnow(),
                    "message": message[:240],
                    "inputTokens": usage["inputTokens"],
                    "outputTokens": usage["outputTokens"],
                    "totalTokens": usage["totalTokens"],
                }
            )

    def persist_yaml(self, graph: dict[str, Any]) -> str:
        doc = document_from_graph(graph, invent_edges=False)
        return emit_yaml(doc)


def _compress_state(state: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node in state.get("nodes") or []:
        item: dict[str, Any] = {
            "id": node.get("id"),
            "type": node.get("type"),
            "label": node.get("label"),
        }
        if node.get("type") == "dataSource":
            item["filename"] = node.get("filename")
            item["provides"] = node.get("provides")
        elif node.get("type") == "loop":
            item["loopType"] = node.get("loopType")
            item["dimension"] = node.get("dimension")
            item["size"] = node.get("size")
        elif node.get("type") == "formula":
            item["section"] = node.get("section")
        elif node.get("type") == "aggregation":
            item["reduce"] = node.get("reduce")
            item["variable"] = node.get("variable")
        nodes.append(item)
    return {
        "nodes": nodes,
        "edges": [
            {"source": edge.get("source"), "target": edge.get("target")}
            for edge in state.get("edges") or []
        ],
    }


def _history_messages(history: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in history[-16:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content.strip()[:2000]})
    return out


def _summarize(results: list[ToolResult]) -> str:
    if not results:
        return ""
    return " ".join(item.message for item in results)


def wants_persist(payload: dict[str, Any]) -> bool:
    flag = payload.get("persist")
    if flag in (True, 1, "1", "true", "yes"):
        return True
    return bool(payload.get("save") or payload.get("save_overlay"))


def spec_id_of(payload: dict[str, Any]) -> str:
    raw = payload.get("spec_id") or payload.get("specId") or payload.get("id")
    return str(raw).strip() if isinstance(raw, str) else ""
