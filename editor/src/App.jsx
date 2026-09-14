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

import { api, isTerminal, progressBits } from "./api.js";
import {
  NODE_TYPES,
  SCOPE_TYPE,
  applyPanelFields,
  blankNode,
  emptyDoc,
  fromFlow,
  jobBodies,
  retargetEdges,
  toFlow,
} from "./graph.js";
import { crumbPath, isScope, parentIdOf } from "./scopes.js";
import { cloneDoc } from "./history.js";
import { createHistory } from "./history.js";
import {
  autoLayout,
  estimateNodeSize,
  leafSizeDrift,
  looksPiled,
  mergeMeasured,
  readDomNodeSizes,
  undersizedLeaves,
} from "./layout.js";
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
  if (type === SCOPE_TYPE) return data.scopeKind === "inner" ? "#c084fc" : "#818cf8";
  return "#94a3b8";
}

function defaultSubmitDefaults() {
  return { accounts: 200000, precision: "f32", sizes: {} };
}

function submitDefaultChips(defaults) {
  const sizes = (defaults && defaults.sizes) || {};
  const chips = [];
  const accounts = defaults && defaults.accounts;
  if (accounts) chips.push("ACCOUNT " + accounts);
  ["S_OUTER", "T_OUTER", "T_MONTH", "T_INNER", "S_INNER"].forEach((key) => {
    if (sizes[key] != null) chips.push(key + " " + sizes[key]);
  });
  return chips;
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
  const [focusScopeId, setFocusScopeId] = useState(null);
  const [submitSource, setSubmitSource] = useState("");
  const [submitDefaults, setSubmitDefaults] = useState({});
  const [submitAccounts, setSubmitAccounts] = useState("");
  const [submitPrecision, setSubmitPrecision] = useState("f32");
  const [submitOverrides, setSubmitOverrides] = useState({});
  const [overrideKey, setOverrideKey] = useState("");
  const [overrideValue, setOverrideValue] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [progressDurable, setProgressDurable] = useState(false);
  const [refreshHint, setRefreshHint] = useState(
    "Light auto-refresh is optional, or on when a durable hook is active. Stops when the selected job is terminal. Does not invent progress."
  );
  const fileRef = useRef(null);
  const dialogRef = useRef(null);
  const pollRef = useRef(null);
  const autoRefreshRef = useRef(false);
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
  const focusRef = useRef(focusScopeId);
  const toggleCollapseRef = useRef(() => {});
  const drillInRef = useRef(() => {});
  docRef.current = doc;
  yamlRef.current = yaml;
  selectedRef.current = selected;
  specRef.current = specId;
  tokenRef.current = token;
  userRef.current = user;
  themeRef.current = theme;
  rfNodesRef.current = rfNodes;
  rfEdgesRef.current = rfEdges;
  focusRef.current = focusScopeId;
  autoRefreshRef.current = autoRefresh;

  const flowOptions = useCallback(
    (overrides = {}) => ({
      focusScopeId: overrides.focusScopeId !== undefined ? overrides.focusScopeId : focusRef.current,
      onToggleScope: (id) => toggleCollapseRef.current(id),
      onDrillIn: (id) => drillInRef.current(id),
    }),
    []
  );

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
        focusScopeId: overrides.focusScopeId !== undefined ? overrides.focusScopeId : focusRef.current,
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
      const flowState = toFlow(nextDoc, keepSelected, flowOptions());
      setRfNodes(flowState.nodes);
      setRfEdges(flowState.edges);
      refreshHistoryFlags();
      return keepSelected;
    },
    [flowOptions, persistNow, refreshHistoryFlags]
  );

  const fitCanvas = useCallback(() => {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        try {
          flow.fitView({ padding: 0.2 });
        } catch (_err) {
          /* React Flow may not be mounted on first catalog open */
        }
      });
    });
  }, [flow]);

  const measurePassRef = useRef(0);

  const applyLaidOut = useCallback(
    async (nextDoc, options = {}) => {
      const selectedId = options.selected !== undefined ? options.selected : selectedRef.current;
      const flowState = toFlow(nextDoc, selectedId, flowOptions());
      const placed = await autoLayout(flowState.nodes, flowState.edges);
      const laid = fromFlow(placed, flowState.edges, nextDoc);
      applyDoc(laid, { ...options, selected: selectedId });
      fitCanvas();
      if (options.measure !== false) measurePassRef.current = 2;
      return laid;
    },
    [applyDoc, fitCanvas, flowOptions]
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
        const focus = cached.focusScopeId || null;
        focusRef.current = focus;
        setFocusScopeId(focus);
        const cachedFlow = toFlow(cached.doc, cached.selected || null, flowOptions({ focusScopeId: focus }));
        if (looksPiled(cachedFlow.nodes) || undersizedLeaves(cachedFlow.nodes)) {
          await applyLaidOut(cached.doc, { record: false, selected: cached.selected || null });
          setYaml(cached.yaml || "");
          persistNow({ specId: id, doc: docRef.current, yaml: cached.yaml || "", focusScopeId: focus });
          setStatus("Restored " + id + " and relaid piled graph");
        } else {
          applyDoc(cached.doc, { record: false, selected: cached.selected || null });
          setYaml(cached.yaml || "");
          if (cached.viewport) viewportRef.current = cached.viewport;
          refreshHistoryFlags();
          persistNow({ specId: id, doc: cached.doc, yaml: cached.yaml || "", focusScopeId: focus });
          setStatus("Restored " + id + " from local editor state");
          fitCanvas();
        }
        return;
      }
      const spec = await api("GET", "/v0/specs/" + encodeURIComponent(id));
      const parsed = await api("POST", "/v0/graph/parse", { yaml: spec.content });
      historyRef.current.reset();
      focusRef.current = null;
      setFocusScopeId(null);
      await applyLaidOut(parsed.graph, { record: false, selected: null });
      setYaml(parsed.yaml || spec.content || "");
      persistNow({ specId: id, doc: docRef.current, yaml: parsed.yaml || spec.content || "", focusScopeId: null });
      setStatus("Opened catalog spec " + id);
      fitCanvas();
    },
    [applyDoc, applyLaidOut, fitCanvas, flowOptions, persistNow, refreshHistoryFlags, setStatus]
  );

  useEffect(() => {
    applyTheme(theme);
    persistNow({ force: false });
  }, [theme, persistNow]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        try {
          const info = await api("GET", "/v0/info");
          const durable = !!(info.runs && info.runs.progress_durable);
          if (!cancelled) {
            setProgressDurable(durable);
            if (durable) setAutoRefresh(true);
          }
        } catch (_err) {
          if (!cancelled) setProgressDurable(false);
        }
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
    if (selectedJob) {
      try {
        const exported = await api("GET", "/v0/jobs/" + encodeURIComponent(selectedJob) + "/progress");
        if (exported && exported.progress) {
          next = next.map((job) =>
            job.id === selectedJob ? { ...job, progress: exported.progress } : job
          );
        }
      } catch (_err) {
        /* progress verb is optional */
      }
    }
    setJobs(next);
    const selected = next.find((job) => job.id === selectedJob);
    const selectedTerminal = !!(selected && isTerminal(selected.status));
    const live = next.some((job) => job.status === "queued" || job.status === "running");
    const wantPoll = !selectedTerminal && (live || autoRefreshRef.current);
    if (selectedTerminal) {
      setRefreshHint(
        "Auto-refresh stopped — selected job is terminal (" + selected.status + "). No invented progress."
      );
    } else if (wantPoll) {
      setRefreshHint(
        "Auto-refresh on (light). Polls list + selected job. Stops on terminal. No invented progress."
      );
    } else {
      setRefreshHint(
        "Light auto-refresh is optional, or on when a durable hook is active. Stops when the selected job is terminal. Does not invent progress."
      );
    }
    if (wantPoll && !pollRef.current) {
      pollRef.current = setInterval(() => {
        refreshRuns().catch(() => {});
      }, 800);
    }
    if (!wantPoll && pollRef.current) {
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
  }, [view, autoRefresh, refreshRuns, setStatus]);

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
      const focus = focusRef.current;
      if (focus) {
        node.parentId = focus;
        const parent = (docRef.current.nodes || []).find((item) => item.id === focus);
        if (parent) {
          node.x = (parent.x || 0) + 36;
          node.y = (parent.y || 0) + 72;
        }
      }
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
    const sized = mergeMeasured(rfNodesRef.current, readDomNodeSizes(rfNodesRef.current));
    const placed = await autoLayout(sized, rfEdgesRef.current);
    setRfNodes(placed);
    await commitFlow(placed, rfEdgesRef.current, { statusMessage: "Auto-layout" });
    fitCanvas();
    measurePassRef.current = 2;
  }, [commitFlow, fitCanvas]);

  useEffect(() => {
    if (!measurePassRef.current) return;
    const handle = window.setTimeout(async () => {
      if (!measurePassRef.current) return;
      const sizes = readDomNodeSizes(rfNodesRef.current);
      if (!sizes.size || !leafSizeDrift(rfNodesRef.current, sizes)) {
        measurePassRef.current = 0;
        fitCanvas();
        return;
      }
      measurePassRef.current -= 1;
      const sized = mergeMeasured(rfNodesRef.current, sizes);
      const placed = await autoLayout(sized, rfEdgesRef.current);
      setRfNodes(placed);
      await commitFlow(placed, rfEdgesRef.current, { record: false, statusMessage: "" });
      fitCanvas();
    }, 80);
    return () => window.clearTimeout(handle);
  }, [rfNodes, commitFlow, fitCanvas]);

  const paintFocus = useCallback(
    (id, message) => {
      focusRef.current = id;
      setFocusScopeId(id);
      const flowState = toFlow(docRef.current, selectedRef.current, flowOptions({ focusScopeId: id }));
      setRfNodes(flowState.nodes);
      setRfEdges(flowState.edges);
      persistNow({ focusScopeId: id });
      if (message) setStatus(message);
      requestAnimationFrame(() => flow.fitView({ padding: 0.25 }));
    },
    [flow, flowOptions, persistNow, setStatus]
  );

  const toggleCollapse = useCallback(
    async (id) => {
      const next = {
        ...docRef.current,
        stub: false,
        nodes: (docRef.current.nodes || []).map((node) =>
          node.id === id ? { ...node, collapsed: !node.collapsed } : node
        ),
      };
      const now = next.nodes.find((node) => node.id === id);
      await applyLaidOut(next, { selected: id });
      syncYaml(docRef.current).catch((err) => setStatus(err.message, true));
      setStatus(now && now.collapsed ? "Collapsed " + id : "Expanded " + id);
    },
    [applyLaidOut, setStatus, syncYaml]
  );

  const drillIn = useCallback(
    (id) => {
      paintFocus(id, "Drilled into " + id + " — outer graph stays recoverable");
    },
    [paintFocus]
  );

  const drillTo = useCallback(
    (id) => {
      paintFocus(id, id ? "Nested scope " + id : "Back to outer graph");
    },
    [paintFocus]
  );

  toggleCollapseRef.current = toggleCollapse;
  drillInRef.current = drillIn;

  const applyYaml = useCallback(
    async (text) => {
      const parsed = await api("POST", "/v0/graph/parse", { yaml: text });
      const still = (parsed.graph.nodes || []).some((node) => node.id === focusRef.current);
      if (!still) {
        focusRef.current = null;
        setFocusScopeId(null);
      }
      const flowState = toFlow(parsed.graph, selectedRef.current, flowOptions());
      if (looksPiled(flowState.nodes) || undersizedLeaves(flowState.nodes)) {
        await applyLaidOut(parsed.graph, { selected: selectedRef.current });
      } else {
        applyDoc(parsed.graph, { selected: selectedRef.current });
      }
      setYaml(parsed.yaml);
      persistNow({ doc: docRef.current, yaml: parsed.yaml });
      setStatus("YAML applied (" + parsed.graph.nodes.length + " nodes)");
    },
    [applyDoc, applyLaidOut, flowOptions, persistNow, setStatus]
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
      const sizeChanged =
        estimateNodeSize(node).height !== estimateNodeSize(nextNode).height ||
        estimateNodeSize(node).width !== estimateNodeSize(nextNode).width;
      if (sizeChanged) {
        await applyLaidOut(next, { selected: nextNode.id });
      } else {
        applyDoc(next, { selected: nextNode.id });
      }
      try {
        await syncYaml(docRef.current);
      } catch (err) {
        setStatus(err.message, true);
      }
    },
    [applyDoc, applyLaidOut, setStatus, syncYaml]
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
      } else if (key === "escape" && focusRef.current) {
        event.preventDefault();
        const crumbs = crumbPath(docRef.current.nodes || [], focusRef.current);
        const parent = crumbs.length > 1 ? crumbs[crumbs.length - 2].id : null;
        drillTo(parent);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drillTo, redo, runLayout, undo]);

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

  async function loadSubmitDefaults(spec) {
    if (!spec) return defaultSubmitDefaults();
    try {
      const body = await api("GET", "/v0/specs/" + encodeURIComponent(spec));
      return body.defaults || defaultSubmitDefaults();
    } catch (_err) {
      return defaultSubmitDefaults();
    }
  }

  async function openSubmitDialog(source, spec) {
    if (!tokenRef.current) {
      setStatus("Log in to submit (G6 Bearer)", true);
      return;
    }
    const defaults = await loadSubmitDefaults(spec);
    setSubmitDefaults(defaults);
    setSubmitOverrides({});
    setSubmitAccounts(defaults.accounts ? String(defaults.accounts) : "");
    setSubmitPrecision("f32");
    setOverrideKey("");
    setOverrideValue("");
    setSubmitSource(source);
  }

  function closeSubmitDialog() {
    setSubmitSource("");
  }

  function collectSubmitWork(spec) {
    const work = { demo: "dsl", catalog: spec };
    if (submitAccounts) work.accounts = Number(submitAccounts);
    work.precision = submitPrecision;
    const keys = Object.keys(submitOverrides);
    if (keys.length) work.overrides = { ...submitOverrides };
    return work;
  }

  function addOverride() {
    const key = overrideKey.trim();
    if (!key) return;
    setSubmitOverrides((prev) => ({ ...prev, [key]: overrideValue }));
    setOverrideKey("");
    setOverrideValue("");
  }

  useEffect(() => {
    const extra = document.querySelector("body > dialog#submit-dialog");
    if (extra) extra.remove();
  }, []);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (submitSource) {
      if (typeof dialog.showModal === "function") {
        if (!dialog.open) dialog.showModal();
      } else {
        dialog.setAttribute("open", "open");
      }
    } else if (dialog.open) {
      dialog.close();
    } else {
      dialog.removeAttribute("open");
    }
  }, [submitSource]);

  const job = jobs.find((item) => item.id === selectedJob);
  const bits = progressBits(job);
  void historyTick;

  return (
    <>
      <header className="topbar">
        <div className="brand">
          <strong>guest-dsl</strong>
          <span className="muted">G10 React Flow · G9 Matryoshka · G4 runs · G12 submit · G13 progress · G8 chat · pin 0.5</span>
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
              await openSubmitDialog("editor", specRef.current);
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
            if (globalDemo === "echo" || globalDemo === "sleep") {
              const work = globalDemo === "echo"
                ? { demo: "echo", message: spec || "ok" }
                : { demo: "sleep", seconds: 8 };
              try {
                const created = await submitJobs(globalClass, work);
                setSelectedJob(created[0] && created[0].id);
                setStatus("Submitted " + created.length + " job(s) on cpu");
                setView("runs");
              } catch (err) {
                setStatus((err.payload && err.payload.detail) || err.message, true);
              }
              return;
            }
            if (!spec) {
              setStatus("Pick a catalog spec", true);
              return;
            }
            try {
              await openSubmitDialog("global", spec);
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
        <label className="auto-refresh-label" htmlFor="auto-refresh">
          <input
            type="checkbox"
            id="auto-refresh"
            data-testid="auto-refresh"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto-refresh
        </label>
        <p className="muted auto-refresh-hint" id="auto-refresh-hint" data-testid="auto-refresh-hint">
          {refreshHint}
        </p>
      </div>

      <main className={"workspace" + (view === "editor" ? "" : " hidden")} id="editor-view" data-testid="editor-view">
        <section className="canvas-wrap" aria-label="Graph canvas">
          <div id="canvas" className="canvas" data-testid="canvas">
            <nav className="scope-crumbs" data-testid="scope-crumbs" aria-label="Matryoshka nested scopes">
              <span className="sr-only" data-testid="matryoshka">
                matryoshka
              </span>
              <button type="button" data-testid="scope-root" className={!focusScopeId ? "active" : ""} onClick={() => drillTo(null)}>
                Graph
              </button>
              {crumbPath(doc.nodes || [], focusScopeId).map((crumb) => (
                <span key={crumb.id} className="crumb-bit">
                  <span className="crumb-sep">/</span>
                  <button
                    type="button"
                    data-testid={"scope-crumb-" + crumb.id}
                    className={focusScopeId === crumb.id ? "active" : ""}
                    onClick={() => drillTo(crumb.id)}
                  >
                    {crumb.label}
                  </button>
                </span>
              ))}
            </nav>
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeDragStop={onNodeDragStop}
              onNodeDoubleClick={(_event, node) => {
                if (isScope(node) || (node.data && isScope(node.data))) drillIn(node.id);
              }}
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
              Open a catalog spec or import YAML. Nested scopes expand/collapse or drill in (Esc returns). Add DataSource / Loop / Formula / Aggregation. Pan, zoom, connect, Shift-select.
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
                  {progressDurable
                    ? "Progress omitted — runtime did not report any."
                    : "Progress omitted — stub did not report any."}
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
      <dialog
        ref={dialogRef}
        id="submit-dialog"
        className="submit-dialog"
        data-testid="submit-dialog"
        onCancel={(event) => {
          event.preventDefault();
          closeSubmitDialog();
        }}
      >
        <form
          id="submit-dialog-form"
          data-testid="submit-dialog-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const spec = submitSource === "editor" ? specRef.current : globalSpec || specId;
            const label = submitSource === "editor" ? editorClass : globalClass;
            if (!spec) {
              setStatus("Pick a catalog spec", true);
              return;
            }
            try {
              const created = await submitJobs(label, collectSubmitWork(spec));
              setSelectedJob(created[0] && created[0].id);
              closeSubmitDialog();
              setStatus("Submitted " + created.length + " job(s) on " + label);
              setView("runs");
            } catch (err) {
              setStatus((err.payload && err.payload.detail) || err.message, true);
            }
          }}
        >
          <header>
            <h2 id="submit-dialog-title">Submit</h2>
            <p className="muted">cpu / gpu / both. Accounts, precision, optional overrides. No capacity theater.</p>
          </header>
          <p id="submit-dialog-spec" className="submit-spec" data-testid="submit-dialog-spec">
            {submitSource ? "Spec " + (submitSource === "editor" ? specId : globalSpec || specId) : ""}
          </p>
          <div id="submit-defaults" className="submit-defaults" data-testid="submit-defaults">
            {submitDefaultChips(submitDefaults).length
              ? submitDefaultChips(submitDefaults).map((chip) => <span key={chip}>{chip}</span>)
              : <span>catalog default</span>}
          </div>
          <label className="submit-field">
            Accounts
            <input
              id="submit-accounts"
              data-testid="submit-accounts"
              type="number"
              min="1"
              step="1"
              value={submitAccounts}
              placeholder={submitDefaults.accounts ? String(submitDefaults.accounts) : "catalog default"}
              onChange={(event) => setSubmitAccounts(event.target.value)}
            />
          </label>
          <fieldset className="submit-precision" data-testid="submit-precision">
            <legend>Precision</legend>
            <label>
              <input
                type="radio"
                name="submit-precision"
                value="f32"
                checked={submitPrecision === "f32"}
                onChange={() => setSubmitPrecision("f32")}
              />{" "}
              f32
            </label>
            <label>
              <input
                type="radio"
                name="submit-precision"
                value="f64"
                checked={submitPrecision === "f64"}
                onChange={() => setSubmitPrecision("f64")}
              />{" "}
              f64
            </label>
          </fieldset>
          <div className="submit-overrides">
            <h3>Variable overrides</h3>
            <p className="muted">Optional. ACCOUNT override wins over the accounts field.</p>
            <div id="submit-override-list" className="override-list" data-testid="submit-overrides">
              {Object.keys(submitOverrides).map((key) => (
                <div className="override-item" key={key}>
                  <span>{key}</span>
                  <span>=</span>
                  <span>{String(submitOverrides[key])}</span>
                  <button
                    type="button"
                    aria-label={"Remove " + key}
                    onClick={() => {
                      setSubmitOverrides((prev) => {
                        const next = { ...prev };
                        delete next[key];
                        return next;
                      });
                    }}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="add-override">
              <input
                id="override-key"
                data-testid="override-key"
                type="text"
                placeholder="Variable"
                value={overrideKey}
                onChange={(event) => setOverrideKey(event.target.value)}
              />
              <span>=</span>
              <input
                id="override-value"
                data-testid="override-value"
                type="text"
                placeholder="Value"
                value={overrideValue}
                onChange={(event) => setOverrideValue(event.target.value)}
              />
              <button type="button" id="override-add" data-testid="override-add" onClick={addOverride}>
                Add
              </button>
            </div>
          </div>
          <footer>
            <button type="button" id="submit-cancel" data-testid="submit-cancel" onClick={closeSubmitDialog}>
              Cancel
            </button>
            <button type="submit" id="submit-confirm" data-testid="submit-confirm" className="primary">
              Submit
            </button>
          </footer>
        </form>
      </dialog>
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
      {node.type === SCOPE_TYPE && (
        <>
          <label>
            Scope kind (outer|inner)
            <input name="scopeKind" value={fields.scopeKind} onChange={(e) => update("scopeKind", e.target.value)} />
          </label>
          <label>
            Dimensions (comma)
            <input name="dimensions" value={fields.dimensions} onChange={(e) => update("dimensions", e.target.value)} />
          </label>
          <label>
            Parent scope
            <input name="parentId" value={fields.parentId} onChange={(e) => update("parentId", e.target.value)} />
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
    scopeKind: node.scopeKind || "outer",
    dimensions: (node.dimensions || []).join(", "),
    parentId: parentIdOf(node),
  };
}
