"""Editor graph (G3) — dsl-gui *intention*, not a code lift.

Four node types: DataSource / Loop / Formula / Aggregation.
YAML import understands seed-shaped data / execution / calculations
documents (G11 catalog graphs) plus thin overlays. Export writes that
same shape (plus optional canvas positions). Unedited catalog YAML
keeps the original text for roundtrip fidelity.

Validate: undefined formula vars (error) and missing DataSource
filenames (warning). No Getafix. No Cognito. No CuPy / NSM math.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from dsl.errors import InvalidGraph, InvalidYaml
from dsl.yaml_io import dumps, loads

NODE_TYPES = ("dataSource", "loop", "formula", "aggregation")
LOOP_TYPES = ("outer", "inner")
FORMULA_SECTIONS = ("init", "step")
CONTEXTS = ("outer", "inner")
REDUCE_OPS = ("mean", "sum", "min", "max", "count")
COND_OPS = ("==", "!=", ">", ">=", "<", "<=")
BUILTINS = frozenset(
    {
        "where",
        "max",
        "min",
        "abs",
        "and",
        "or",
        "not",
        "true",
        "false",
        "null",
        "sum",
        "mean",
        "lookup",
        "cumprod",
        "over",
        "along",
        "TIME",
        "RETURN",
        "exp",
        "clip",
        "floor",
        "ceil",
        "log",
        "pow",
        "round",
        "sqrt",
        "int",
        "float",
    }
)
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
TEMPORAL_RE = re.compile(r"\[\s*-?\d+\s*\]")
SCI_RE = re.compile(r"(?<![A-Za-z_])\d+\.?\d*[eE][+-]?\d+")
STUB_KINDS = frozenset({"catalog-stub", "overlay-stub"})

GRAPH_TOP_KEYS = (
    "metadata",
    "description",
    "data",
    "execution",
    "calculations",
    "canvas",
    "nodes",
    "edges",
)


@dataclass
class Issue:
    code: str
    severity: str
    detail: str
    node_id: str | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
        }
        if self.node_id:
            payload["node_id"] = self.node_id
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass
class Edge:
    id: str
    source: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "source": self.source, "target": self.target}


@dataclass
class Node:
    id: str
    type: str
    label: str = ""
    x: float = 0.0
    y: float = 0.0
    # DataSource
    filename: str = ""
    context: str = "outer"
    provides: list[str] = field(default_factory=list)
    index: list[str] = field(default_factory=list)
    column_map: dict[str, str] = field(default_factory=dict)
    # Loop
    loop_type: str = "outer"
    dimension: str = ""
    size: int | float | None = None
    vectorize: list[str] = field(default_factory=list)
    # Formula
    section: str = "step"
    formulas: dict[str, str] = field(default_factory=dict)
    # Aggregation
    variable: str = ""
    condition: dict[str, Any] = field(default_factory=dict)
    reduce: str = "mean"
    over: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "x": self.x,
            "y": self.y,
        }
        if self.type == "dataSource":
            payload.update(
                {
                    "filename": self.filename,
                    "context": self.context,
                    "provides": list(self.provides),
                    "index": list(self.index),
                    "column_map": dict(self.column_map),
                }
            )
        elif self.type == "loop":
            payload.update(
                {
                    "loopType": self.loop_type,
                    "dimension": self.dimension,
                    "size": self.size,
                    "vectorize": list(self.vectorize),
                }
            )
        elif self.type == "formula":
            payload.update(
                {
                    "section": self.section,
                    "formulas": dict(self.formulas),
                }
            )
        elif self.type == "aggregation":
            payload.update(
                {
                    "variable": self.variable,
                    "condition": dict(self.condition),
                    "reduce": self.reduce,
                    "over": self.over,
                }
            )
        return payload


@dataclass
class GraphDocument:
    metadata: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    dirty: bool = False
    known_names: list[str] = field(default_factory=list)

    @property
    def is_stub(self) -> bool:
        kind = str(self.metadata.get("kind") or "")
        return kind in STUB_KINDS and not self.nodes

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": dict(self.metadata),
            "description": self.description,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "extras": dict(self.extras),
            "stub": self.is_stub,
            "known_names": list(self.known_names),
        }


def parse_yaml(text: str) -> GraphDocument:
    """YAML → graph. Catalog stubs become metadata + empty canvas."""
    if not isinstance(text, str) or not text.strip():
        raise InvalidYaml("yaml text is required")
    data = loads(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise InvalidGraph("document root must be a mapping")
    return document_from_mapping(data, source=text)


def document_from_mapping(
    data: dict[str, Any], *, source: str = "", dirty: bool = False
) -> GraphDocument:
    metadata = _as_map(data.get("metadata"))
    description = data.get("description")
    if description is None:
        description = metadata.get("description") or ""
    if not isinstance(description, str):
        description = str(description)

    nodes: list[Node] = []
    edges: list[Edge] = []

    explicit = data.get("nodes")
    if isinstance(explicit, list) and explicit:
        nodes.extend(_nodes_from_explicit(explicit))
    else:
        nodes.extend(_nodes_from_data(data.get("data")))
        nodes.extend(_nodes_from_execution(data.get("execution"), data.get("tensor")))
        nodes.extend(_nodes_from_calculations(data.get("calculations")))
        nodes = _dedupe_nodes(nodes)

    canvas = _as_map(data.get("canvas"))
    if isinstance(canvas.get("nodes"), list):
        _apply_canvas(nodes, canvas["nodes"])
    if isinstance(data.get("edges"), list):
        edges.extend(_edges_from_list(data["edges"]))
    if isinstance(canvas.get("edges"), list):
        edges.extend(_edges_from_list(canvas["edges"]))
    if not edges:
        edges = default_edges(nodes)
    edges = _dedupe_edges(edges)
    _layout_missing(nodes)

    extras = {
        key: value
        for key, value in data.items()
        if key not in GRAPH_TOP_KEYS
    }
    known = _known_names_from_mapping(data)
    if known:
        extras.setdefault("_known_names", sorted(known))
    ui_layout = _as_map(_as_map(extras.get("_ui")).get("layout"))
    if ui_layout:
        _apply_ui_layout(nodes, ui_layout)
    return GraphDocument(
        metadata=metadata,
        description=description,
        nodes=nodes,
        edges=edges,
        extras=extras,
        source=source,
        dirty=dirty,
        known_names=sorted(known),
    )


def document_from_graph(
    payload: dict[str, Any], *, invent_edges: bool = True
) -> GraphDocument:
    if not isinstance(payload, dict):
        raise InvalidGraph("graph must be a JSON object")
    if "nodes" in payload or "metadata" in payload or "edges" in payload:
        nodes = _nodes_from_explicit(payload.get("nodes") or [])
        edges = _edges_from_list(payload.get("edges") or [])
        metadata = _as_map(payload.get("metadata"))
        description = payload.get("description") or ""
        if not isinstance(description, str):
            description = str(description)
        extras = _as_map(payload.get("extras"))
        known = [str(name) for name in payload.get("known_names") or extras.get("_known_names") or [] if name]
        if not edges and invent_edges:
            edges = default_edges(nodes)
        _layout_missing(nodes)
        return GraphDocument(
            metadata=metadata,
            description=description,
            nodes=nodes,
            edges=edges,
            extras=extras,
            dirty=True,
            known_names=known,
        )
    return document_from_mapping(payload, dirty=True)


def emit_yaml(doc: GraphDocument, *, preserve_source: bool = True) -> str:
    """Graph → YAML. Unedited catalog documents keep the original text."""
    if preserve_source and doc.source and not doc.dirty:
        return doc.source if doc.source.endswith("\n") else doc.source + "\n"
    return dumps(_mapping_from_document(doc))


def validate(doc: GraphDocument) -> list[Issue]:
    """Undefined vars (error) and missing DataSource filenames (warning)."""
    issues: list[Issue] = []
    defined = _defined_names(doc.nodes)
    defined.update(doc.known_names)
    defined.update(_str_list(_as_map(doc.extras).get("_known_names")))
    defined.update(_known_names_from_mapping({"metadata": doc.metadata, **doc.extras}))
    for node in doc.nodes:
        if node.type == "dataSource" and not str(node.filename or "").strip():
            issues.append(
                Issue(
                    code="missing_filename",
                    severity="warning",
                    node_id=node.id,
                    detail="DataSource has no filename",
                )
            )
        if node.type == "formula":
            for name, expr in node.formulas.items():
                for ref in formula_refs(str(expr)):
                    if ref not in defined and ref != name:
                        issues.append(
                            Issue(
                                code="undefined_var",
                                severity="error",
                                node_id=node.id,
                                name=ref,
                                detail=(
                                    f"formula {name!r} references undefined "
                                    f"variable {ref!r}"
                                ),
                            )
                        )
        if node.type == "aggregation":
            for ref in (node.variable, str(node.condition.get("variable") or "")):
                token = ref.strip()
                if token and token not in defined:
                    issues.append(
                        Issue(
                            code="undefined_var",
                            severity="error",
                            node_id=node.id,
                            name=token,
                            detail=f"aggregation references undefined variable {token!r}",
                        )
                    )
    return issues


def validation_payload(doc: GraphDocument) -> dict[str, Any]:
    issues = validate(doc)
    errors = [item for item in issues if item.severity == "error"]
    return {
        "ok": not errors,
        "issues": [item.to_dict() for item in issues],
        "error_count": len(errors),
        "warning_count": len(issues) - len(errors),
        "stub": doc.is_stub,
    }


def formula_refs(expr: str) -> list[str]:
    stripped = TEMPORAL_RE.sub("", SCI_RE.sub("", expr or ""))
    refs: list[str] = []
    seen: set[str] = set()
    for match in IDENT_RE.finditer(stripped):
        name = match.group(0)
        if name in BUILTINS or name in seen:
            continue
        seen.add(name)
        refs.append(name)
    return refs


def default_edges(nodes: list[Node]) -> list[Edge]:
    """dsl-gui connection intention: DataSource→Loop, outer→inner, inner→Agg, Formula→Loop."""
    by_type: dict[str, list[Node]] = {name: [] for name in NODE_TYPES}
    for node in nodes:
        by_type.setdefault(node.type, []).append(node)
    edges: list[Edge] = []
    n = 0

    def add(source: str, target: str) -> None:
        nonlocal n
        n += 1
        edges.append(Edge(id=f"e{n}", source=source, target=target))

    outers = [node for node in by_type["loop"] if node.loop_type != "inner"]
    inners = [node for node in by_type["loop"] if node.loop_type == "inner"]
    loops = by_type["loop"]
    for src in by_type["dataSource"]:
        wanted = src.context if src.context in CONTEXTS else "outer"
        targets = [node for node in loops if node.loop_type == wanted] or loops
        if targets:
            add(src.id, targets[0].id)
    if outers and inners:
        add(outers[0].id, inners[0].id)
    tails = inners or outers
    for agg in by_type["aggregation"]:
        if tails:
            add(tails[0].id, agg.id)
    for formula in by_type["formula"]:
        wanted = "inner" if formula.section == "step" and inners else "outer"
        targets = [node for node in loops if node.loop_type == wanted] or loops
        if targets:
            add(formula.id, targets[0].id)
    return edges


def _defined_names(nodes: Iterable[Node]) -> set[str]:
    names: set[str] = set()
    for node in nodes:
        if node.type == "dataSource":
            names.update(str(item) for item in node.provides)
            names.update(str(item) for item in node.index)
            names.update(str(key) for key in node.column_map.keys())
            names.update(str(val) for val in node.column_map.values())
        elif node.type == "loop":
            if node.dimension:
                names.add(str(node.dimension))
            names.update(str(item) for item in node.vectorize)
        elif node.type == "formula":
            names.update(str(key) for key in node.formulas.keys())
        elif node.type == "aggregation":
            if node.variable:
                names.add(str(node.variable))
            if node.over:
                names.add(str(node.over))
    return names


def _known_names_from_mapping(data: dict[str, Any]) -> set[str]:
    """Seed-domain names (parameters, tensor dims, bindings) for validate."""
    names: set[str] = set()
    params = _as_map(data.get("parameters"))
    names.update(str(key) for key in params)
    tensor = _as_map(data.get("tensor"))
    names.update(_str_list(tensor.get("dims")))
    sizes = _as_map(tensor.get("sizes"))
    names.update(str(key) for key in sizes)
    variables = data.get("variables")
    if isinstance(variables, dict):
        for raw in variables.values():
            if isinstance(raw, list):
                names.update(_str_list(raw))
            elif isinstance(raw, dict):
                names.update(str(key) for key in raw)
    elif isinstance(variables, list):
        names.update(_str_list(variables))
    execution = _as_map(data.get("execution"))
    names.update(_str_list(execution.get("loop")))
    names.update(_str_list(execution.get("reuse_memory")))
    names.update(_str_list(execution.get("vectorize")))
    inner = _as_map(execution.get("inner_loop"))
    names.update(_str_list(inner.get("shared_variables")))
    names.update(_str_list(inner.get("t_inner_vars")))
    names.update(_str_list(inner.get("shifted_inner_vars")))
    names.update(_str_list(inner.get("t_eff_vars")))
    names.update(_str_list(inner.get("s_inner_arrays")))
    for spec in execution.get("aggregation") if isinstance(execution.get("aggregation"), list) else (
        [execution.get("aggregation")] if execution.get("aggregation") else []
    ):
        if not isinstance(spec, dict):
            continue
        names.update(_str_list(spec.get("variables")))
        if spec.get("variable"):
            names.add(str(spec.get("variable")))
        if spec.get("target"):
            names.add(str(spec.get("target")))
        if spec.get("target_prefix"):
            names.add(str(spec.get("target_prefix")).rstrip("_"))
    calcs = _as_map(data.get("calculations"))
    formulas = _as_map(calcs.get("formulas"))
    for block in formulas.values():
        if isinstance(block, dict):
            names.update(str(key) for key in block)
    for section in ("outer", "inner"):
        scope = _as_map(calcs.get(section))
        names.update(_str_list(scope.get("scope")))
        names.update(_str_list(scope.get("init_from_outer")))
        bindings = _as_map(scope.get("bindings"))
        names.update(str(key) for key in bindings)
        for value in bindings.values():
            names.update(formula_refs(str(value)))
    data_block = _as_map(data.get("data"))
    mapping = _as_map(data_block.get("index_mapping"))
    names.update(str(key) for key in mapping)
    computed = _as_map(data_block.get("computed_columns"))
    names.update(str(key) for key in computed)
    files = data_block.get("files")
    if isinstance(files, dict):
        for spec in files.values():
            spec_map = spec if isinstance(spec, dict) else {}
            names.update(_name_tokens(spec_map.get("provides")))
            names.update(_name_tokens(spec_map.get("index")))
            col = _as_map(spec_map.get("column_map") or spec_map.get("columnMap"))
            names.update(str(key) for key in col)
            names.update(str(val) for val in col.values())
            prep = _as_map(spec_map.get("preprocessing"))
            names.update(str(key) for key in _as_map(prep.get("computed")))
    conditions = _as_map(data.get("conditions"))
    names.update(str(key) for key in conditions)
    names.update({"TIME", "RETURN", "TIME_YEAR", "TIME_MONTH"})
    return {name for name in names if name}


def _apply_ui_layout(nodes: list[Node], layout: dict[str, Any]) -> None:
    by_id = {node.id: node for node in nodes}
    by_label = {node.label: node for node in nodes}
    for key, pos in layout.items():
        if not isinstance(pos, dict):
            continue
        node = (
            by_id.get(f"ds-{_slug(key)}")
            or by_id.get(str(key))
            or by_label.get(str(key))
        )
        if node is None:
            continue
        if pos.get("x") is not None:
            node.x = _num(pos.get("x"), node.x)
        if pos.get("y") is not None:
            node.y = _num(pos.get("y"), node.y)


def _mapping_from_document(doc: GraphDocument) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    metadata = dict(doc.metadata)
    if doc.nodes and str(metadata.get("kind") or "") in STUB_KINDS:
        metadata["kind"] = "graph"
    if metadata:
        mapping["metadata"] = metadata
    if doc.description:
        mapping["description"] = doc.description
    for key, value in doc.extras.items():
        mapping[key] = value

    files: dict[str, Any] = {}
    loops_outer: list[str] = []
    loops_inner: list[str] = []
    vectorize: list[str] = []
    aggregations: list[dict[str, Any]] = []
    init: dict[str, str] = {}
    step: dict[str, str] = {}

    for node in doc.nodes:
        if node.type == "dataSource":
            key = _slug(node.label or node.id)
            files[key] = _omit_empty(
                {
                    "file": node.filename,
                    "context": node.context or "outer",
                    "provides": list(node.provides),
                    "index": list(node.index),
                    "column_map": dict(node.column_map),
                    "label": node.label or key,
                }
            )
        elif node.type == "loop":
            dim = node.dimension or node.label or node.id
            if node.loop_type == "inner":
                loops_inner.append(str(dim))
            else:
                loops_outer.append(str(dim))
            vectorize.extend(str(item) for item in node.vectorize)
        elif node.type == "formula":
            target = init if node.section == "init" else step
            for key, expr in node.formulas.items():
                target[str(key)] = str(expr)
        elif node.type == "aggregation":
            aggregations.append(
                _omit_empty(
                    {
                        "id": node.id,
                        "label": node.label,
                        "variable": node.variable,
                        "condition": dict(node.condition) if node.condition else {},
                        "reduce": node.reduce or "mean",
                        "over": node.over,
                    }
                )
            )

    if doc.nodes:
        mapping["nodes"] = [node.to_dict() for node in doc.nodes]
    if doc.edges:
        mapping["edges"] = [edge.to_dict() for edge in doc.edges]
    if files:
        mapping["data"] = {"files": files}
    execution: dict[str, Any] = {}
    if loops_outer:
        execution["loop"] = _unique(loops_outer)
    if loops_inner:
        execution["reuse_memory"] = _unique(loops_inner)
    if vectorize:
        execution["vectorize"] = _unique(vectorize)
    if len(aggregations) == 1:
        execution["aggregation"] = aggregations[0]
    elif aggregations:
        execution["aggregation"] = aggregations
    if execution:
        mapping["execution"] = execution
    formulas: dict[str, Any] = {}
    if init:
        formulas["init"] = init
    if step:
        formulas["step"] = step
    if formulas:
        mapping["calculations"] = {"formulas": formulas}

    canvas_nodes = [
        {"id": node.id, "type": node.type, "x": node.x, "y": node.y, "label": node.label}
        for node in doc.nodes
    ]
    if canvas_nodes:
        mapping["canvas"] = {
            "nodes": canvas_nodes,
            "edges": [edge.to_dict() for edge in doc.edges],
        }
    return mapping


def _nodes_from_explicit(raw: Any) -> list[Node]:
    nodes: list[Node] = []
    if not isinstance(raw, list):
        return nodes
    for item in raw:
        if not isinstance(item, dict):
            continue
        node_type = str(item.get("type") or "")
        if node_type not in NODE_TYPES:
            continue
        node_id = str(item.get("id") or _slug(item.get("label") or node_type))
        node = Node(
            id=node_id,
            type=node_type,
            label=str(item.get("label") or node_id),
            x=_num(item.get("x"), 0.0),
            y=_num(item.get("y"), 0.0),
        )
        if node_type == "dataSource":
            node.filename = str(item.get("filename") or item.get("file") or "")
            node.context = _one_of(item.get("context"), CONTEXTS, "outer")
            node.provides = _str_list(item.get("provides"))
            node.index = _str_list(item.get("index"))
            node.column_map = _str_map(item.get("column_map") or item.get("columnMap"))
        elif node_type == "loop":
            node.loop_type = _one_of(
                item.get("loopType") or item.get("loop_type"), LOOP_TYPES, "outer"
            )
            node.dimension = str(item.get("dimension") or "")
            node.size = item.get("size") if isinstance(item.get("size"), (int, float)) else None
            node.vectorize = _str_list(item.get("vectorize"))
        elif node_type == "formula":
            node.section = _one_of(item.get("section"), FORMULA_SECTIONS, "step")
            node.formulas = _str_map(item.get("formulas"))
        elif node_type == "aggregation":
            node.variable = str(item.get("variable") or "")
            node.condition = _as_map(item.get("condition"))
            node.reduce = _one_of(item.get("reduce"), REDUCE_OPS, "mean")
            node.over = str(item.get("over") or "")
        nodes.append(node)
    return nodes


def _nodes_from_data(raw: Any) -> list[Node]:
    data = _as_map(raw)
    files = data.get("files")
    nodes: list[Node] = []
    if isinstance(files, dict):
        items = files.items()
    elif isinstance(files, list):
        items = []
        for entry in files:
            if isinstance(entry, dict):
                key = str(entry.get("id") or entry.get("label") or entry.get("file") or "file")
                items.append((key, entry))
            else:
                continue
    else:
        return nodes
    y = 80.0
    for key, spec in items:
        spec_map = spec if isinstance(spec, dict) else {"file": spec}
        filename = str(spec_map.get("file") or spec_map.get("filename") or "")
        node = Node(
            id=f"ds-{_slug(key)}",
            type="dataSource",
            label=str(spec_map.get("label") or key),
            filename=filename,
            context=_one_of(spec_map.get("context"), CONTEXTS, "outer"),
            provides=_name_tokens(spec_map.get("provides")),
            index=_str_list(spec_map.get("index")),
            column_map=_str_map(spec_map.get("column_map") or spec_map.get("columnMap")),
            x=40.0,
            y=y,
        )
        nodes.append(node)
        y += 90.0
    return nodes


def _nodes_from_execution(raw: Any, tensor: Any) -> list[Node]:
    execution = _as_map(raw)
    sizes = _as_map(_as_map(tensor).get("sizes"))
    nodes: list[Node] = []
    x = 40.0
    for dim in _str_list(execution.get("loop")):
        nodes.append(
            Node(
                id=f"loop-outer-{_slug(dim)}",
                type="loop",
                label=f"Outer {dim}",
                loop_type="outer",
                dimension=dim,
                size=_maybe_num(sizes.get(dim)),
                vectorize=_str_list(execution.get("vectorize")),
                x=x,
                y=260.0,
            )
        )
        x += 240.0
    x = 40.0
    for dim in _str_list(execution.get("reuse_memory")):
        nodes.append(
            Node(
                id=f"loop-inner-{_slug(dim)}",
                type="loop",
                label=f"Inner {dim}",
                loop_type="inner",
                dimension=dim,
                size=_maybe_num(sizes.get(dim)),
                x=x,
                y=420.0,
            )
        )
        x += 240.0
    for extra in execution.get("loops") if isinstance(execution.get("loops"), list) else []:
        if not isinstance(extra, dict):
            continue
        nodes.extend(_nodes_from_explicit([{**extra, "type": "loop"}]))
    agg_raw = execution.get("aggregation")
    aggs = agg_raw if isinstance(agg_raw, list) else [agg_raw] if agg_raw else []
    x = 40.0
    for i, spec in enumerate(aggs):
        if not isinstance(spec, dict):
            continue
        reduce_op, over = _reduce_of(spec.get("reduce"), spec.get("over"))
        variables = _str_list(spec.get("variables"))
        variable = str(spec.get("variable") or (variables[0] if variables else ""))
        label = str(
            spec.get("label")
            or spec.get("target")
            or spec.get("target_prefix")
            or "Aggregation"
        )
        nodes.append(
            Node(
                id=str(spec.get("id") or f"agg-{i}"),
                type="aggregation",
                label=label,
                variable=variable,
                condition=_as_map(spec.get("condition")),
                reduce=reduce_op,
                over=over,
                x=40.0,
                y=580.0 + i * 90.0,
            )
        )
        x += 240.0
    return nodes


def _nodes_from_calculations(raw: Any) -> list[Node]:
    calcs = _as_map(raw)
    formulas = calcs.get("formulas")
    nodes: list[Node] = []
    if isinstance(formulas, dict) and (
        "init" in formulas or "step" in formulas or any(
            isinstance(v, dict) for v in formulas.values()
        )
    ):
        if isinstance(formulas.get("init"), dict):
            nodes.append(
                Node(
                    id="formula-init",
                    type="formula",
                    label="Init formulas",
                    section="init",
                    formulas=_str_map(formulas.get("init")),
                    x=520.0,
                    y=80.0,
                )
            )
        if isinstance(formulas.get("step"), dict):
            nodes.append(
                Node(
                    id="formula-step",
                    type="formula",
                    label="Step formulas",
                    section="step",
                    formulas=_str_map(formulas.get("step")),
                    x=520.0,
                    y=260.0,
                )
            )
        if isinstance(formulas.get("post_aggregation"), dict):
            nodes.append(
                Node(
                    id="formula-post",
                    type="formula",
                    label="Post aggregation",
                    section="step",
                    formulas=_str_map(formulas.get("post_aggregation")),
                    x=520.0,
                    y=440.0,
                )
            )
        # allow a flat map as step formulas when no init/step wrappers
        if "init" not in formulas and "step" not in formulas:
            if all(not isinstance(v, dict) for v in formulas.values()):
                nodes.append(
                    Node(
                        id="formula-step",
                        type="formula",
                        label="Formulas",
                        section="step",
                        formulas=_str_map(formulas),
                        x=520.0,
                        y=260.0,
                    )
                )
        return nodes
    if isinstance(formulas, list):
        for i, spec in enumerate(formulas):
            if not isinstance(spec, dict):
                continue
            nodes.extend(
                _nodes_from_explicit(
                    [
                        {
                            "id": spec.get("id") or f"formula-{i}",
                            "type": "formula",
                            "label": spec.get("label") or f"Formula {i}",
                            "section": spec.get("section") or "step",
                            "formulas": spec.get("formulas") or spec.get("expr") or {},
                        }
                    ]
                )
            )
    return nodes


def _apply_canvas(nodes: list[Node], raw: list[Any]) -> None:
    by_id = {node.id: node for node in nodes}
    for item in raw:
        if not isinstance(item, dict):
            continue
        node = by_id.get(str(item.get("id") or ""))
        if node is None:
            continue
        if item.get("x") is not None:
            node.x = _num(item.get("x"), node.x)
        if item.get("y") is not None:
            node.y = _num(item.get("y"), node.y)
        if item.get("label"):
            node.label = str(item.get("label"))


def _edges_from_list(raw: Any) -> list[Edge]:
    edges: list[Edge] = []
    if not isinstance(raw, list):
        return edges
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "")
        target = str(item.get("target") or "")
        if not source or not target:
            continue
        edges.append(
            Edge(id=str(item.get("id") or f"e{i+1}"), source=source, target=target)
        )
    return edges


def _dedupe_nodes(nodes: list[Node]) -> list[Node]:
    seen: dict[str, Node] = {}
    order: list[str] = []
    for node in nodes:
        if node.id in seen:
            previous = seen[node.id]
            seen[node.id] = _merge_node(previous, node)
        else:
            seen[node.id] = node
            order.append(node.id)
    return [seen[key] for key in order]


def _merge_node(left: Node, right: Node) -> Node:
    data = asdict(left)
    for key, value in asdict(right).items():
        if value in (None, "", [], {}) and data.get(key) not in (None, "", [], {}):
            continue
        data[key] = value
    return Node(**data)


def _dedupe_edges(edges: list[Edge]) -> list[Edge]:
    seen: set[tuple[str, str]] = set()
    out: list[Edge] = []
    for edge in edges:
        key = (edge.source, edge.target)
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _layout_missing(nodes: list[Node]) -> None:
    columns = {
        "dataSource": (40.0, 80.0),
        "formula": (420.0, 80.0),
        "loop": (40.0, 280.0),
        "aggregation": (420.0, 280.0),
    }
    counts = {name: 0 for name in NODE_TYPES}
    for node in nodes:
        if node.x or node.y:
            continue
        base_x, base_y = columns.get(node.type, (40.0, 80.0))
        node.x = base_x + counts[node.type] * 40.0
        node.y = base_y + counts[node.type] * 90.0
        counts[node.type] += 1


def _reduce_of(reduce_raw: Any, over_raw: Any) -> tuple[str, str]:
    if isinstance(reduce_raw, list) and reduce_raw:
        first = reduce_raw[0] if isinstance(reduce_raw[0], dict) else {}
        last = reduce_raw[-1] if isinstance(reduce_raw[-1], dict) else {}
        op = str(first.get("operation") or first.get("reduce") or "mean")
        over = str(last.get("over") or over_raw or "")
        return _one_of(op, REDUCE_OPS, "mean"), over
    if isinstance(reduce_raw, dict):
        return (
            _one_of(reduce_raw.get("operation") or reduce_raw.get("reduce"), REDUCE_OPS, "mean"),
            str(reduce_raw.get("over") or over_raw or ""),
        )
    return _one_of(reduce_raw, REDUCE_OPS, "mean"), str(over_raw or "")


def _as_map(raw: Any) -> dict[str, Any]:
    return dict(raw) if isinstance(raw, dict) else {}


def _str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if item is not None and str(item) != ""]
    return [str(raw)]


def _name_tokens(raw: Any) -> list[str]:
    """Flatten provides / index entries, including `{src: dest}` maps."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        out: list[str] = []
        for key, value in raw.items():
            out.append(str(key))
            if value not in (None, "") and str(value) != str(key):
                out.append(str(value))
        return out
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, (dict, list)):
                out.extend(_name_tokens(item))
            elif item is not None and str(item) != "":
                out.append(str(item))
        return out
    return [str(raw)]


def _str_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(key): "" if value is None else str(value) for key, value in raw.items()}


def _one_of(raw: Any, allowed: tuple[str, ...], default: str) -> str:
    text = str(raw or "").strip()
    return text if text in allowed else default


def _num(raw: Any, default: float) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    return default


def _maybe_num(raw: Any) -> int | float | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw
    return None


def _slug(raw: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw or "").strip()).strip("-").lower()
    return text or "node"


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _omit_empty(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if value in (None, "", [], {}):
            continue
        out[key] = value
    return out
