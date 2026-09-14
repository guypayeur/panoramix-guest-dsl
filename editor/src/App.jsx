import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  SelectionMode,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { api, progressBits } from "./api.js";
import {
  NODE_TYPES,
  applyPanelFields,
  blankNode,
  emptyDoc,
  fromFlow,
  jobBodies,
  retargetEdges,
  toFlow,
} from "./graph.js";
import { cloneDoc } from "./history.js";
import { createHistory } from "./history.js";
import { autoLayout } from "./layout.js";
import { nodeTypes } from "./nodes.jsx";
import {
  cachedSpec,
  loadPersist,
  rememberSpec,
  savePersist,
  shouldReplaceSnapshot,
  specSnapshot,
} from "./persist.js";
import ChatPanel from "./ChatPanel.jsx";

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  document.body.dataset.theme = next;
  return next;
}

function minimapColor(node) {
  const type = node.type;
  const data = node.data || {};
  if (type === "dataSource") return "#64748b";
  if (type === "loop") return data.loopType === "inner" ? "#ca8a04" : "#3b82f6";
  if (type === "formula") return data.section === "init" ? "#22d3ee" : "#a855f7";
  if (type === "aggregation") return "#22c55e";
  return "#94a3b8";
}

export default function App() {
  const persistRef = useRef(loadPersist());
  const historyRef = useRef(createHistory(50));
  const [, setPersist] = useState(() => persistRef.current);
  const [theme, setTheme] = useState(() => applyTheme(persistRef.current.theme));
  const [specs, setSpecs] = useState([]);
  const [specId, setSpecId] = useState(persistRef.current.specId || "");
  const [token, setToken] = useState(persistRef.current.token || "");
  const [user, setUser] = useState(persistRef.current.user || null);
  const [doc, setDoc] = useState(emptyDoc);
  const [yaml, setYaml] = useState("");
  const [selected, setSelected] = useState(null);
  const [issues, setIssues] = useState([]);
  const [status, setStatusState] = useState("");
  const [statusBad, setStatusBad] = useState(false);
  const [view, setView] = useState("editor");
  const [statusFilter, setStatusFilter] = useState("");
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [rfNodes, setRfNodes] = useState([]);
  const [rfEdges, setRfEdges] = useState([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [email, setEmail] = useState("guy.payeur@gp2.ca");
  const [password, setPassword] = useState("admin123!");
  const [editorClass, setEditorClass] = useState("both");
  const [globalClass, setGlobalClass] = useState("both");
  const [globalDemo, setGlobalDemo] = useState("dsl");
  const [globalSpec, setGlobalSpec] = useState("");
  const [historyTick, setHistoryTick] = useState(0);
  const [boxSelect, setBoxSelect] = useState(false);
  const fileRef = useRef(null);
  const pollRef = useRef(null);
  const viewportRef = useRef(persistRef.current.viewport || { x: 0, y: 0, zoom: 1 });
  const skipSelectSync = useRef(false);
  const flow = useReactFlow();

  const docRef = useRef(doc);
  const yamlRef = useRef(yaml);
  const selectedRef = useRef(selected);
  const specRef = useRef(specId);
  const tokenRef = useRef(token);
  const userRef = useRef(user);
  const themeRef = useRef(theme);
  const rfNodesRef = useRef(rfNodes);
  const rfEdgesRef = useRef(rfEdges);
  docRef.current = doc;
  yamlRef.current = yaml;
  selectedRef.current = selected;
  specRef.current = specId;
  tokenRef.current = token;
  userRef.current = user;
  themeRef.current = theme;
  rfNodesRef.current = rfNodes;
  rfEdgesRef.current = rfEdges;

  const setStatus = useCallback((message, bad) => {
    setStatusState(message || "");
    setStatusBad(!!bad);
  }, []);

  const refreshHistoryFlags = useCallback(() => {
    setCanUndo(historyRef.current.canUndo());
    setCanRedo(historyRef.current.canRedo());
    setHistoryTick((n) => n + 1);
  }, []);

  const persistNow = useCallback(
    (overrides = {}) => {
      const specId = overrides.specId !== undefined ? overrides.specId : specRef.current;
      const nextDoc = overrides.doc || docRef.current;
      const existing = cachedSpec(persistRef.current, specId);
      const session = {
        ...persistRef.current,
        token: tokenRef.current,
        user: userRef.current,
        specId,
        theme: themeRef.current,
        viewport: overrides.viewport || viewportRef.current,
      };
      if (!shouldReplaceSnapshot(existing, nextDoc) && !overrides.force) {
        persistRef.current = session;
        setPersist(session);
        savePersist(session);
        return;
      }
      const snapshot = specSnapshot(nextDoc, {
        selected: overrides.selected !== undefined ? overrides.selected : selectedRef.current,
        yaml: overrides.yaml !== undefined ? overrides.yaml : yamlRef.current,
        viewport: overrides.viewport || viewportRef.current,
        history: historyRef.current.dump(),
      });
      const next = rememberSpec(session, specId, snapshot);
      persistRef.current = next;
      setPersist(next);
      savePersist(next);
    },
    []
  );

  const applyDoc = useCallback(
    (nextDoc, options = {}) => {
      const selectedId = options.selected !== undefined ? options.selected : selectedRef.current;
      const keepSelected = (nextDoc.nodes || []).some((node) => node.id === selectedId)
        ? selectedId
        : null;
      if (options.record !== false) {
        historyRef.current.push(cloneDoc(docRef.current));
      }
      if (options.persist !== false) {
        persistNow({ doc: nextDoc, selected: keepSelected });
      }
      setDoc(nextDoc);
      setSelected(keepSelected);
      const flowState = toFlow(nextDoc, keepSelected);
      setRfNodes(flowState.nodes);
      setRfEdges(flowState.edges);
      refreshHistoryFlags();
      return keepSelected;
    },
    [persistNow, refreshHistoryFlags]
  );

  const syncYaml = useCallback(
    async (nextDoc) => {
      const exported = await api("POST", "/v0/graph/export", { graph: nextDoc });
      setYaml(exported.yaml || "");
      persistNow({ doc: nextDoc, yaml: exported.yaml || "" });
      return exported.yaml || "";
    },
    [persistNow]
  );

  const openSpec = useCallback(
    async (id, { force = false } = {}) => {
      if (!id) return;
      if (specRef.current && specRef.current !== id) {
        persistNow({ specId: specRef.current });
      }
      setSpecId(id);
      specRef.current = id;
      const cached = !force ? cachedSpec(persistRef.current, id) : null;
      if (cached && cached.doc) {
        historyRef.current.reset();
        if (cached.history) historyRef.current.hydrate(cached.history);
        applyDoc(cached.doc, { record: false, selected: cached.selected || null });
        setYaml(cached.yaml || "");
        if (cached.viewport) viewportRef.current = cached.viewport;
        refreshHistoryFlags();
        persistNow({ specId: id, doc: cached.doc, yaml: cached.yaml || "" });
        setStatus("Restored " + id + " from local editor state");
        return;
      }
      const spec = await api("GET", "/v0/specs/" + encodeURIComponent(id));
      const parsed = await api("POST", "/v0/graph/parse", { yaml: spec.content });
      historyRef.current.reset();
      applyDoc(parsed.graph, { record: false, selected: null });
      setYaml(parsed.yaml || spec.content || "");
      persistNow({ specId: id, doc: parsed.graph, yaml: parsed.yaml || spec.content || "" });
      setStatus("Opened catalog spec " + id);
    },
    [applyDoc, persistNow, refreshHistoryFlags, setStatus]
  );

  useEffect(() => {
    applyTheme(theme);
    persistNow({ force: false });
  }, [theme, persistNow]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const listed = await api("GET", "/v0/specs");
        if (cancelled) return;
        const items = listed.items || [];
        setSpecs(items);
        const wanted =
          new URLSearchParams(location.search).get("spec") ||
          persistRef.current.specId ||
          (items[0] && items[0].id);
        if (wanted) {
          setGlobalSpec(wanted);
          await openSpec(wanted);
        }
        if (location.hash.indexOf("#runs") === 0) {
          const parts = location.hash.split("/");
          if (parts[1]) setSelectedJob(parts[1]);
          setView("runs");
        }
      } catch (err) {
        if (!cancelled) setStatus(err.message, true);
      }
    })();
    return () => {
      cancelled = true;
    };
    // boot once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const hash = view === "runs" ? (selectedJob ? "#runs/" + selectedJob : "#runs") : "#editor";
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }, [view, selectedJob]);

  useEffect(() => {
    const onHash = () => {
      if (location.hash.indexOf("#runs") === 0) {
        const parts = location.hash.split("/");
        if (parts[1]) setSelectedJob(parts[1]);
        setView("runs");
      } else {
        setView("editor");
      }
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const refreshRuns = useCallback(async () => {
    const q = statusFilter ? "?status=" + encodeURIComponent(statusFilter) : "";
    const payload = await api("GET", "/v0/jobs" + q);
    let next = payload.jobs || [];
    if (selectedJob && !next.some((job) => job.id === selectedJob)) {
      try {
        const one = await api("GET", "/v0/jobs/" + encodeURIComponent(selectedJob));
        next = [one, ...next];
      } catch (_err) {
        /* filtered or gone */
      }
    }
    setJobs(next);
    const live = next.some((job) => job.status === "queued" || job.status === "running");
    if (live && !pollRef.current) {
      pollRef.current = setInterval(() => {
        refreshRuns().catch(() => {});
      }, 400);
    }
    if (!live && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [selectedJob, statusFilter]);

  useEffect(() => {
    if (view === "runs") refreshRuns().catch((err) => setStatus(err.message, true));
    return () => {
      if (view !== "runs" && pollRef.current) {
        /* keep polling only while runs are live */
      }
    };
  }, [view, refreshRuns, setStatus]);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const onNodesChange = useCallback((changes) => {
    setRfNodes((nodes) => applyNodeChanges(changes, nodes));
    const select = changes.find((change) => change.type === "select" && change.selected);
    if (select && !skipSelectSync.current) setSelected(select.id);
  }, []);

  const onEdgesChange = useCallback((changes) => {
    setRfEdges((edges) => applyEdgeChanges(changes, edges));
  }, []);

  const commitFlow = useCallback(
    async (nodes, edges, { record = true, statusMessage } = {}) => {
      const next = fromFlow(nodes, edges, docRef.current);
      applyDoc(next, { record, selected: selectedRef.current });
      try {
        await syncYaml(next);
        if (statusMessage) setStatus(statusMessage);
      } catch (err) {
        setStatus(err.message, true);
      }
    },
    [applyDoc, setStatus, syncYaml]
  );

  const onConnect = useCallback(
    (connection) => {
      const nextEdges = addEdge({ ...connection, type: "smoothstep" }, rfEdgesRef.current);
      commitFlow(rfNodesRef.current, nextEdges, { statusMessage: "Connected" });
    },
    [commitFlow]
  );

  const onNodeDragStop = useCallback(() => {
    commitFlow(rfNodesRef.current, rfEdgesRef.current, { statusMessage: "" });
  }, [commitFlow]);

  const onSelectionChange = useCallback(({ nodes }) => {
    if (skipSelectSync.current) return;
    const id = nodes && nodes[0] ? nodes[0].id : null;
    setSelected(id);
  }, []);

  const addNode = useCallback(
    async (type) => {
      if (!NODE_TYPES.includes(type)) return;
      const node = blankNode(type, docRef.current.nodes || []);
      const next = {
        ...docRef.current,
        stub: false,
        nodes: [...(docRef.current.nodes || []), node],
      };
      applyDoc(next, { selected: node.id });
      try {
        await syncYaml(next);
        setStatus("Added " + type);
      } catch (err) {
        setStatus(err.message, true);
      }
    },
    [applyDoc, setStatus, syncYaml]
  );

  const undo = useCallback(() => {
    const prev = historyRef.current.undo(cloneDoc(docRef.current));
    if (!prev) return;
    applyDoc(prev, { record: false });
    syncYaml(prev).catch((err) => setStatus(err.message, true));
    setStatus("Undo");
  }, [applyDoc, setStatus, syncYaml]);

  const redo = useCallback(() => {
    const next = historyRef.current.redo(cloneDoc(docRef.current));
    if (!next) return;
    applyDoc(next, { record: false });
    syncYaml(next).catch((err) => setStatus(err.message, true));
    setStatus("Redo");
  }, [applyDoc, setStatus, syncYaml]);

  const runLayout = useCallback(async () => {
    const placed = await autoLayout(rfNodesRef.current, rfEdgesRef.current);
    setRfNodes(placed);
    await commitFlow(placed, rfEdgesRef.current, { statusMessage: "Auto-layout" });
    requestAnimationFrame(() => flow.fitView({ padding: 0.2 }));
  }, [commitFlow, flow]);

  const applyYaml = useCallback(
    async (text) => {
      const parsed = await api("POST", "/v0/graph/parse", { yaml: text });
      applyDoc(parsed.graph, { selected: selectedRef.current });
      setYaml(parsed.yaml);
      persistNow({ doc: parsed.graph, yaml: parsed.yaml });
      setStatus("YAML applied (" + parsed.graph.nodes.length + " nodes)");
    },
    [applyDoc, persistNow, setStatus]
  );

  const applyPanel = useCallback(
    async (fields) => {
      const node = (docRef.current.nodes || []).find((item) => item.id === selectedRef.current);
      if (!node) return;
      const nextNode = applyPanelFields(node, fields);
      if (JSON.stringify({ ...node, id: nextNode.id }) === JSON.stringify(nextNode) && node.id === nextNode.id) {
        return;
      }
      const nodes = (docRef.current.nodes || []).map((item) => (item.id === node.id ? nextNode : item));
      const edges = retargetEdges(docRef.current.edges || [], node.id, nextNode.id);
      const next = { ...docRef.current, stub: false, nodes, edges };
      applyDoc(next, { selected: nextNode.id });
      try {
        await syncYaml(next);
      } catch (err) {
        setStatus(err.message, true);
      }
    },
    [applyDoc, setStatus, syncYaml]
  );

  useEffect(() => {
    const onKey = (event) => {
      const key = event.key.toLowerCase();
      const meta = event.metaKey || event.ctrlKey;
      if (meta && key === "z" && event.shiftKey) {
        event.preventDefault();
        redo();
      } else if (meta && key === "z") {
        event.preventDefault();
        undo();
      } else if (meta && key === "y") {
        event.preventDefault();
        redo();
      } else if (meta && key === "l") {
        event.preventDefault();
        runLayout();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [redo, runLayout, undo]);

  const selectedNode = useMemo(
    () => (doc.nodes || []).find((node) => node.id === selected) || null,
    [doc, selected]
  );

  async function submitJobs(label, work) {
    if (!tokenRef.current) {
      setStatus("Log in to submit (G6 Bearer)", true);
      return [];
    }
    const created = [];
    for (const body of jobBodies(label, work)) {
      created.push(await api("POST", "/v0/jobs", body, tokenRef.current));
    }
    return created;
  }

  const job = jobs.find((item) => item.id === selectedJob);
  const bits = progressBits(job);
  void historyTick;

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <strong>guest-dsl</strong>
          <span className="muted">G10 React Flow · G4 runs · G8 chat · pin 0.5</span>
        </div>
        <nav className="surfaces views" aria-label="Surfaces">
          <button
            type="button"
            id="tab-editor"
            data-testid="tab-editor"
            className={view === "editor" ? "active" : ""}
            onClick={() => setView("editor")}
          >
            Editor
          </button>
          <button
            type="button"
            id="tab-runs"
            data-testid="tab-runs"
            className={view === "runs" ? "active" : ""}
            onClick={() => setView("runs")}
          >
            Runs
          </button>
          <a href="/files" data-testid="nav-files">
            Files
          </a>
        </nav>
        <nav className="catalog" aria-label="Catalog specs">
          <label>
            Spec
            <select
              id="spec-select"
              data-testid="spec-select"
              value={specId}
              onChange={(event) => openSpec(event.target.value).catch((err) => setStatus(err.message, true))}
            >
              {specs.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.id})
                </option>
              ))}
            </select>
          </label>
          <button type="button" id="btn-open" data-testid="open-spec" onClick={() => openSpec(specId)}>
            Open
          </button>
          <button
            type="button"
            id="btn-revert"
            data-testid="revert-spec"
            onClick={() => openSpec(specId, { force: true }).catch((err) => setStatus(err.message, true))}
          >
            Revert catalog
          </button>
        </nav>
        <div className="auth" id="auth-box">
          {user && token ? (
            <div id="session" className="session">
              <span id="who" data-testid="who">
                {user.email}
              </span>
              <button
                type="button"
                id="btn-logout"
                onClick={() => {
                  setToken("");
                  setUser(null);
                  tokenRef.current = "";
                  userRef.current = null;
                  persistNow();
                  setStatus("Logged out");
                }}
              >
                Log out
              </button>
            </div>
          ) : (
            <form
              id="login-form"
              data-testid="login-form"
              autoComplete="on"
              onSubmit={async (event) => {
                event.preventDefault();
                try {
                  const session = await api("POST", "/v0/auth/login", { email, password });
                  setToken(session.tokens.accessToken);
                  setUser(session.user);
                  tokenRef.current = session.tokens.accessToken;
                  userRef.current = session.user;
                  persistNow();
                  setStatus("Signed in as " + session.user.email);
                } catch (err) {
                  setStatus((err.payload && err.payload.detail) || err.message, true);
                }
              }}
            >
              <input id="email" name="email" type="email" placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              <input
                id="password"
                name="password"
                type="password"
                placeholder="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button type="submit" id="btn-login" data-testid="login">
                Log in
              </button>
            </form>
          )}
        </div>
      </header>

      <div className={"toolbar" + (view === "editor" ? "" : " hidden")} id="editor-toolbar">
        <div className="adders">
          <button type="button" data-add="dataSource" onClick={() => addNode("dataSource")}>
            + DataSource
          </button>
          <button type="button" data-add="loop" onClick={() => addNode("loop")}>
            + Loop
          </button>
          <button type="button" data-add="formula" onClick={() => addNode("formula")}>
            + Formula
          </button>
          <button type="button" data-add="aggregation" onClick={() => addNode("aggregation")}>
            + Aggregation
          </button>
        </div>
        <div className="io history-io">
          <button type="button" id="btn-undo" data-testid="undo" disabled={!canUndo} onClick={undo}>
            Undo
          </button>
          <button type="button" id="btn-redo" data-testid="redo" disabled={!canRedo} onClick={redo}>
            Redo
          </button>
          <button type="button" id="btn-layout" data-testid="auto-layout" onClick={runLayout}>
            Auto-layout
          </button>
          <button
            type="button"
            id="btn-box-select"
            data-testid="multi-select"
            className={boxSelect ? "active" : ""}
            onClick={() => setBoxSelect((on) => !on)}
          >
            {boxSelect ? "Box select on" : "Box select"}
          </button>
          <button
            type="button"
            id="btn-theme"
            data-testid="theme-toggle"
            onClick={() => setTheme((cur) => (cur === "dark" ? "light" : "dark"))}
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          <button type="button" id="btn-import" data-testid="import-yaml" onClick={() => fileRef.current && fileRef.current.click()}>
            Import YAML
          </button>
          <input
            id="file-import"
            ref={fileRef}
            type="file"
            accept=".yaml,.yml,text/yaml"
            hidden
            onChange={async (event) => {
              const file = event.target.files && event.target.files[0];
              if (!file) return;
              try {
                await applyYaml(await file.text());
                setStatus("Imported " + file.name);
              } catch (err) {
                setStatus((err.payload && err.payload.detail) || err.message, true);
              }
              event.target.value = "";
            }}
          />
          <button
            type="button"
            id="btn-export"
            data-testid="export-yaml"
            onClick={async () => {
              try {
                const exported = await api("POST", "/v0/graph/export", { graph: docRef.current });
                setYaml(exported.yaml || "");
                const blob = new Blob([exported.yaml], { type: "text/yaml" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = (specRef.current || "spec") + ".yaml";
                a.click();
                URL.revokeObjectURL(a.href);
                persistNow({ yaml: exported.yaml || "" });
                setStatus("Exported YAML");
              } catch (err) {
                setStatus(err.message, true);
              }
            }}
          >
            Export YAML
          </button>
          <button
            type="button"
            id="btn-validate"
            data-testid="validate"
            onClick={async () => {
              try {
                await syncYaml(docRef.current);
                const payload = await api("POST", "/v0/graph/validate", { graph: docRef.current });
                setIssues(payload.issues || []);
                setStatus(payload.ok ? "Valid" : "Validation found issues", !payload.ok);
              } catch (err) {
                setStatus(err.message, true);
              }
            }}
          >
            Validate
          </button>
          <button
            type="button"
            id="btn-save"
            data-testid="save"
            className="primary"
            onClick={async () => {
              if (!specRef.current) {
                setStatus("Open a catalog spec before saving", true);
                return;
              }
              if (!tokenRef.current) {
                setStatus("Log in to save (G6 Bearer)", true);
                return;
              }
              try {
                const exported = await api("POST", "/v0/graph/export", { graph: docRef.current });
                setYaml(exported.yaml || "");
                const saved = await api(
                  "PUT",
                  "/v0/specs/" + encodeURIComponent(specRef.current),
                  { content: exported.yaml },
                  tokenRef.current
                );
                persistNow({ yaml: exported.yaml || "" });
                setStatus("Saved overlay v" + saved.version + " (" + saved.storage.backend + ")");
              } catch (err) {
                setStatus((err.payload && err.payload.detail) || err.message, true);
              }
            }}
          >
            Save overlay
          </button>
        </div>
        <form
          className="submit-box"
          id="editor-submit"
          data-testid="editor-submit"
          onSubmit={async (event) => {
            event.preventDefault();
            if (!specRef.current) {
              setStatus("Open a catalog spec before submit", true);
              return;
            }
            try {
              const created = await submitJobs(editorClass, { demo: "dsl", catalog: specRef.current });
              setSelectedJob(created[0] && created[0].id);
              setStatus("Submitted " + created.length + " job(s) on " + editorClass);
              setView("runs");
            } catch (err) {
              setStatus((err.payload && err.payload.detail) || err.message, true);
            }
          }}
        >
          <fieldset>
            <legend>Submit on</legend>
            <label>
              <input type="radio" name="editor-class" value="cpu" checked={editorClass === "cpu"} onChange={() => setEditorClass("cpu")} /> cpu
            </label>
            <label>
              <input type="radio" name="editor-class" value="gpu" checked={editorClass === "gpu"} onChange={() => setEditorClass("gpu")} /> gpu
            </label>
            <label>
              <input type="radio" name="editor-class" value="both" checked={editorClass === "both"} onChange={() => setEditorClass("both")} /> both
            </label>
          </fieldset>
          <button type="submit" id="btn-submit-editor" data-testid="submit-editor" className="primary">
            Submit
          </button>
        </form>
      </div>

      <div className={"toolbar" + (view === "runs" ? "" : " hidden")} id="runs-toolbar">
        <form
          className="submit-box"
          id="global-submit"
          data-testid="global-submit"
          onSubmit={async (event) => {
            event.preventDefault();
            const spec = globalSpec || specId;
            let work;
            if (globalDemo === "echo") work = { demo: "echo", message: spec || "ok" };
            else if (globalDemo === "sleep") work = { demo: "sleep", seconds: 8 };
            else {
              if (!spec) {
                setStatus("Pick a catalog spec", true);
                return;
              }
              work = { demo: "dsl", catalog: spec };
            }
            try {
              const created = await submitJobs(globalClass, work);
              setSelectedJob(created[0] && created[0].id);
              setStatus("Submitted " + created.length + " job(s) on " + (globalDemo === "dsl" ? globalClass : "cpu"));
              setView("runs");
            } catch (err) {
              setStatus((err.payload && err.payload.detail) || err.message, true);
            }
          }}
        >
          <label>
            Spec
            <select id="global-spec" data-testid="global-spec" value={globalSpec || specId} onChange={(e) => setGlobalSpec(e.target.value)}>
              {specs.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.id})
                </option>
              ))}
            </select>
          </label>
          <label>
            Work
            <select id="global-demo" data-testid="global-demo" value={globalDemo} onChange={(e) => setGlobalDemo(e.target.value)}>
              <option value="dsl">catalog stub</option>
              <option value="echo">echo</option>
              <option value="sleep">sleep</option>
            </select>
          </label>
          <fieldset>
            <legend>Submit on</legend>
            <label>
              <input type="radio" name="global-class" value="cpu" checked={globalClass === "cpu"} onChange={() => setGlobalClass("cpu")} /> cpu
            </label>
            <label>
              <input type="radio" name="global-class" value="gpu" checked={globalClass === "gpu"} onChange={() => setGlobalClass("gpu")} /> gpu
            </label>
            <label>
              <input type="radio" name="global-class" value="both" checked={globalClass === "both"} onChange={() => setGlobalClass("both")} /> both
            </label>
          </fieldset>
          <button type="submit" id="btn-submit-global" data-testid="submit-global" className="primary">
            Submit
          </button>
          <p id="runs-status" className={"status" + (statusBad ? " bad" : "")} data-testid="runs-status">
            {status}
          </p>
        </form>
        <div className="filters" id="status-filter" data-testid="status-filter" role="group" aria-label="Status filter">
          {["", "queued", "running", "succeeded", "failed", "canceled"].map((value) => (
            <button
              key={value || "all"}
              type="button"
              data-status={value}
              className={statusFilter === value ? "active" : ""}
              onClick={() => setStatusFilter(value)}
            >
              {value || "all"}
            </button>
          ))}
        </div>
      </div>

      <main className={"workspace" + (view === "editor" ? "" : " hidden")} id="editor-view" data-testid="editor-view">
        <section className="canvas-wrap" aria-label="Graph canvas">
          <div id="canvas" className="canvas" data-testid="canvas">
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onSelectionChange={onSelectionChange}
              onMoveEnd={(_event, viewport) => {
                viewportRef.current = viewport;
                persistNow({ viewport });
              }}
              defaultViewport={viewportRef.current}
              fitView
              nodesDraggable
              nodesConnectable
              elementsSelectable
              selectNodesOnDrag
              selectionOnDrag={boxSelect}
              selectionMode={SelectionMode.Partial}
              panOnDrag={!boxSelect}
              panOnScroll
              zoomOnScroll
              zoomOnPinch
              selectionKeyCode="Shift"
              multiSelectionKeyCode="Shift"
              deleteKeyCode={["Backspace", "Delete"]}
              nodeDragThreshold={0}
              proOptions={{ hideAttribution: true }}
            >
              <Background id="editor-dots" variant={BackgroundVariant.Dots} gap={18} size={1.2} />
              <Controls position="top-left" showInteractive />
              <div className="minimap-wrap" data-testid="minimap">
                <MiniMap nodeColor={minimapColor} pannable zoomable />
              </div>
            </ReactFlow>
            <p className={"hint" + ((doc.nodes || []).length ? " hidden" : "")} id="canvas-hint">
              Open a catalog spec or import YAML. Add DataSource / Loop / Formula / Aggregation. Pan, zoom, connect, Shift-select.
            </p>
          </div>
        </section>
        <aside className="side" aria-label="Side panel">
          <h2>Side panel</h2>
          {selectedNode ? (
            <PanelForm key={selectedNode.id} node={selectedNode} onChange={applyPanel} />
          ) : (
            <div id="panel-empty" className="muted">
              Select a node to edit properties.
            </div>
          )}
          <h2>YAML</h2>
          <textarea id="yaml" data-testid="yaml-preview" spellCheck={false} value={yaml} onChange={(e) => setYaml(e.target.value)} />
          <div className="yaml-actions">
            <button type="button" id="btn-apply-yaml" onClick={() => applyYaml(yaml).catch((err) => setStatus((err.payload && err.payload.detail) || err.message, true))}>
              Apply YAML to canvas
            </button>
          </div>
          <h2>Validation</h2>
          <ul id="issues" data-testid="issues">
            {(issues || []).length === 0 ? (
              <li>No issues reported</li>
            ) : (
              issues.map((issue, idx) => (
                <li key={idx} className={issue.severity || "error"}>
                  {(issue.severity || "error") + ": " + issue.detail}
                </li>
              ))
            )}
          </ul>
          <p id="status" className={"status" + (statusBad ? " bad" : "")} data-testid="status">
            {status}
          </p>
        </aside>
      </main>

      <main className={"workspace" + (view === "runs" ? "" : " hidden")} id="runs-view" data-testid="runs-view">
        <section className="runs-list-wrap" aria-label="Runs list">
          <h2>Runs</h2>
          <p className={"muted" + (jobs.length ? " hidden" : "")} id="runs-empty" data-testid="runs-empty">
            No runs yet. Submit from the editor or the form above.
          </p>
          <table className="runs-table" id="runs-table">
            <thead>
              <tr>
                <th>id</th>
                <th>status</th>
                <th>class</th>
                <th>kind</th>
                <th>updated</th>
              </tr>
            </thead>
            <tbody id="runs-list" data-testid="runs-list">
              {jobs.map((row) => (
                <tr
                  key={row.id}
                  data-id={row.id}
                  data-testid="run-row"
                  className={selectedJob === row.id ? "selected" : ""}
                  onClick={() => {
                    setSelectedJob(row.id);
                    setView("runs");
                  }}
                >
                  <td>{escapeHtml(row.id.slice(0, 8))}</td>
                  <td className={"st-" + row.status}>{row.status}</td>
                  <td>{row.class || ""}</td>
                  <td>{row.kind || ""}</td>
                  <td>{(row.updated_at || "").replace("T", " ").slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <aside className="side run-detail" aria-label="Run detail" id="run-detail" data-testid="run-detail">
          <h2>Run detail</h2>
          {!job ? (
            <p className="muted" id="detail-empty">
              Select a run.
            </p>
          ) : (
            <>
              <dl id="detail-fields">
                {[
                  ["id", job.id],
                  ["status", job.status],
                  ["class", job.class],
                  ["kind", job.kind],
                  ["digest", job.payload_digest],
                  ["message", job.message || ""],
                  ["error", job.error || ""],
                  ["created", job.created_at],
                  ["updated", job.updated_at],
                ]
                  .filter((row) => row[1])
                  .map((row) => (
                    <span key={row[0]} className="detail-row">
                      <dt>{row[0]}</dt>
                      <dd>{String(row[1])}</dd>
                    </span>
                  ))}
              </dl>
              {bits.length ? (
                <div id="detail-progress" data-testid="run-progress">
                  {bits.join(" · ")}
                </div>
              ) : (
                <p className="muted" id="detail-progress-omit" data-testid="progress-omitted">
                  Progress omitted — stub did not report any.
                </p>
              )}
              {(job.status === "queued" || job.status === "running") && (
                <button
                  type="button"
                  id="btn-cancel"
                  data-testid="cancel-run"
                  onClick={async () => {
                    if (!tokenRef.current) {
                      setStatus("Log in to cancel (G6 Bearer)", true);
                      return;
                    }
                    try {
                      const canceled = await api(
                        "POST",
                        "/v0/jobs/" + encodeURIComponent(job.id) + "/cancel",
                        {},
                        tokenRef.current
                      );
                      setStatus("Canceled " + canceled.id.slice(0, 8));
                      await refreshRuns();
                    } catch (err) {
                      setStatus((err.payload && err.payload.detail) || err.message, true);
                    }
                  }}
                >
                  Cancel
                </button>
              )}
            </>
          )}
          {!job && (
            <>
              <div id="detail-progress" data-testid="run-progress" className="hidden" />
              <p className="muted hidden" id="detail-progress-omit" data-testid="progress-omitted">
                Progress omitted — stub did not report any.
              </p>
              <button type="button" id="btn-cancel" data-testid="cancel-run" className="hidden">
                Cancel
              </button>
            </>
          )}
        </aside>
      </main>
      <ChatPanel
        view={view}
        doc={doc}
        specId={specId}
        token={token}
        setStatus={setStatus}
        onGraph={(next, selectedId) => {
          applyDoc(next, { selected: selectedId || selectedRef.current });
          syncYaml(next).catch((err) => setStatus(err.message, true));
        }}
      />
    </>
  );
}

function PanelForm({ node, onChange }) {
  const [fields, setFields] = useState(() => fieldsFrom(node));
  useEffect(() => {
    setFields(fieldsFrom(node));
  }, [node]);

  function update(name, value) {
    const next = { ...fields, [name]: value };
    setFields(next);
  }

  function commit() {
    onChange(fields);
  }

  return (
    <form
      id="panel"
      className="panel"
      data-testid="side-panel"
      onBlur={commit}
    >
      <label>
        Id
        <input name="id" value={fields.id} onChange={(e) => update("id", e.target.value)} />
      </label>
      <label>
        Label
        <input name="label" value={fields.label} onChange={(e) => update("label", e.target.value)} />
      </label>
      {node.type === "dataSource" && (
        <>
          <label>
            Filename
            <input name="filename" value={fields.filename} onChange={(e) => update("filename", e.target.value)} />
          </label>
          <label>
            Context (outer|inner)
            <input name="context" value={fields.context} onChange={(e) => update("context", e.target.value)} />
          </label>
          <label>
            Provides (comma)
            <input name="provides" value={fields.provides} onChange={(e) => update("provides", e.target.value)} />
          </label>
          <label>
            Index (comma)
            <input name="index" value={fields.index} onChange={(e) => update("index", e.target.value)} />
          </label>
        </>
      )}
      {node.type === "loop" && (
        <>
          <label>
            Loop type (outer|inner)
            <input name="loopType" value={fields.loopType} onChange={(e) => update("loopType", e.target.value)} />
          </label>
          <label>
            Dimension
            <input name="dimension" value={fields.dimension} onChange={(e) => update("dimension", e.target.value)} />
          </label>
          <label>
            Size
            <input name="size" value={fields.size} onChange={(e) => update("size", e.target.value)} />
          </label>
          <label>
            Vectorize (comma)
            <input name="vectorize" value={fields.vectorize} onChange={(e) => update("vectorize", e.target.value)} />
          </label>
        </>
      )}
      {node.type === "formula" && (
        <>
          <label>
            Section (init|step)
            <input name="section" value={fields.section} onChange={(e) => update("section", e.target.value)} />
          </label>
          <label>
            Formulas (NAME: expr per line)
            <textarea name="formulas" value={fields.formulas} onChange={(e) => update("formulas", e.target.value)} />
          </label>
        </>
      )}
      {node.type === "aggregation" && (
        <>
          <label>
            Variable
            <input name="variable" value={fields.variable} onChange={(e) => update("variable", e.target.value)} />
          </label>
          <label>
            Condition variable
            <input name="condVar" value={fields.condVar} onChange={(e) => update("condVar", e.target.value)} />
          </label>
          <label>
            Condition operator
            <input name="condOp" value={fields.condOp} onChange={(e) => update("condOp", e.target.value)} />
          </label>
          <label>
            Condition value
            <input name="condValue" value={fields.condValue} onChange={(e) => update("condValue", e.target.value)} />
          </label>
          <label>
            Reduce
            <input name="reduce" value={fields.reduce} onChange={(e) => update("reduce", e.target.value)} />
          </label>
          <label>
            Over
            <input name="over" value={fields.over} onChange={(e) => update("over", e.target.value)} />
          </label>
        </>
      )}
    </form>
  );
}

function fieldsFrom(node) {
  const cond = node.condition || {};
  return {
    id: node.id,
    label: node.label || "",
    filename: node.filename || "",
    context: node.context || "outer",
    provides: (node.provides || []).join(", "),
    index: (node.index || []).join(", "),
    loopType: node.loopType || "outer",
    dimension: node.dimension || "",
    size: node.size == null ? "" : String(node.size),
    vectorize: (node.vectorize || []).join(", "),
    section: node.section || "step",
    formulas: Object.entries(node.formulas || {})
      .map(([k, v]) => k + ": " + v)
      .join("\n"),
    variable: node.variable || "",
    condVar: cond.variable || "",
    condOp: cond.operator || "==",
    condValue: cond.value == null ? "" : String(cond.value),
    reduce: node.reduce || "mean",
    over: node.over || "",
  };
}
