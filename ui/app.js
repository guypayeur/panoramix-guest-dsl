/* G3 editor — dsl-gui intention, not a getafix-seed-paul SPA lift. */
(function () {
  const STORAGE_KEY = "guest-dsl-editor-v1";
  const NODE_TYPES = ["dataSource", "loop", "formula", "aggregation"];

  const state = {
    specId: "",
    specs: [],
    token: "",
    user: null,
    doc: emptyDoc(),
    selected: null,
    persistBySpec: {},
    dragging: null,
    linking: null,
  };

  const $ = (id) => document.getElementById(id);
  const canvas = $("canvas");
  const edgesSvg = $("edges");
  const specSelect = $("spec-select");
  const yamlBox = $("yaml");
  const issuesEl = $("issues");
  const statusEl = $("status");
  const panel = $("panel");
  const panelEmpty = $("panel-empty");

  function emptyDoc() {
    return { metadata: {}, description: "", nodes: [], edges: [], extras: {}, stub: true };
  }

  function newId(prefix) {
    return prefix + "-" + Math.random().toString(36).slice(2, 8);
  }

  function blankNode(type) {
    const id = newId(type === "dataSource" ? "ds" : type);
    const base = { id, type, label: type, x: 80 + state.doc.nodes.length * 24, y: 80 + state.doc.nodes.length * 16 };
    if (type === "dataSource") {
      return { ...base, filename: "", context: "outer", provides: [], index: [], column_map: {} };
    }
    if (type === "loop") {
      return { ...base, loopType: "outer", dimension: "T_OUTER", size: 1, vectorize: [] };
    }
    if (type === "formula") {
      return { ...base, section: "step", formulas: { RESULT: "INPUT" } };
    }
    return {
      ...base,
      variable: "RESULT",
      condition: { variable: "AGE", operator: "==", value: 0 },
      reduce: "mean",
      over: "S_INNER",
    };
  }

  function loadPersist() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      state.token = saved.token || "";
      state.user = saved.user || null;
      state.persistBySpec = saved.persistBySpec || {};
      state.specId = saved.specId || "";
    } catch (_err) {
      /* thinner day-one: sessionStorage only */
    }
  }

  function savePersist() {
    state.persistBySpec[state.specId || "_scratch"] = {
      doc: state.doc,
      selected: state.selected,
      yaml: yamlBox.value,
    };
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        token: state.token,
        user: state.user,
        specId: state.specId,
        persistBySpec: state.persistBySpec,
      })
    );
  }

  async function api(method, path, body, authed) {
    const headers = { Accept: "application/json" };
    const opts = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    if (authed && state.token) headers.Authorization = "Bearer " + state.token;
    const resp = await fetch(path, opts);
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_err) {
      data = { error: "invalid_json", detail: text };
    }
    if (!resp.ok) {
      const err = new Error(data.error || "request_failed");
      err.payload = data;
      err.status = resp.status;
      throw err;
    }
    return data;
  }

  function setStatus(message, bad) {
    statusEl.textContent = message || "";
    statusEl.classList.toggle("bad", !!bad);
  }

  function renderAuth() {
    const form = $("login-form");
    const session = $("session");
    if (state.user && state.token) {
      form.classList.add("hidden");
      session.classList.remove("hidden");
      $("who").textContent = state.user.email;
    } else {
      form.classList.remove("hidden");
      session.classList.add("hidden");
      $("who").textContent = "";
    }
  }

  function renderCatalog() {
    specSelect.innerHTML = "";
    for (const item of state.specs) {
      const opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.name + " (" + item.id + ")";
      specSelect.appendChild(opt);
    }
    if (state.specId) specSelect.value = state.specId;
  }

  function nodeSummary(node) {
    if (node.type === "dataSource") return node.filename || "(no filename)";
    if (node.type === "loop") return (node.loopType || "outer") + " · " + (node.dimension || "");
    if (node.type === "formula") return (node.section || "step") + " · " + Object.keys(node.formulas || {}).join(", ");
    return (node.reduce || "mean") + " " + (node.variable || "");
  }

  function renderCanvas() {
    canvas.innerHTML = "";
    $("canvas-hint").classList.toggle("hidden", state.doc.nodes.length > 0);
    for (const node of state.doc.nodes) {
      const el = document.createElement("article");
      el.className = "node" + (state.selected === node.id ? " selected" : "");
      el.dataset.id = node.id;
      el.dataset.type = node.type;
      el.dataset.testid = "node-" + node.type;
      if (node.loopType) el.dataset.loop = node.loopType;
      if (node.section) el.dataset.section = node.section;
      el.style.left = (node.x || 40) + "px";
      el.style.top = (node.y || 40) + "px";
      el.innerHTML =
        "<header></header><div class=\"body\"></div>" +
        "<span class=\"handle in\" data-handle=\"in\"></span>" +
        "<span class=\"handle out\" data-handle=\"out\"></span>";
      el.querySelector("header").textContent = labelFor(node);
      el.querySelector(".body").textContent = nodeSummary(node);
      el.addEventListener("mousedown", onNodeDown);
      canvas.appendChild(el);
    }
    renderEdges();
  }

  function labelFor(node) {
    const icons = { dataSource: "📄 ", loop: "🔄 ", formula: "📝 ", aggregation: "📊 " };
    return (icons[node.type] || "") + (node.label || node.id);
  }

  function renderEdges() {
    const box = canvas.getBoundingClientRect();
    edgesSvg.setAttribute("width", String(box.width));
    edgesSvg.setAttribute("height", String(box.height));
    edgesSvg.innerHTML = "";
    for (const edge of state.doc.edges || []) {
      const src = canvas.querySelector('[data-id="' + edge.source + '"]');
      const dst = canvas.querySelector('[data-id="' + edge.target + '"]');
      if (!src || !dst) continue;
      const a = src.getBoundingClientRect();
      const b = dst.getBoundingClientRect();
      const x1 = a.right - box.left;
      const y1 = a.top + a.height / 2 - box.top;
      const x2 = b.left - box.left;
      const y2 = b.top + b.height / 2 - box.top;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      const mid = (x1 + x2) / 2;
      path.setAttribute("d", "M " + x1 + " " + y1 + " C " + mid + " " + y1 + ", " + mid + " " + y2 + ", " + x2 + " " + y2);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "#38bdf8");
      path.setAttribute("stroke-width", "2");
      edgesSvg.appendChild(path);
    }
  }

  function renderPanel() {
    const node = state.doc.nodes.find((item) => item.id === state.selected);
    if (!node) {
      panel.classList.add("hidden");
      panelEmpty.classList.remove("hidden");
      panel.innerHTML = "";
      return;
    }
    panelEmpty.classList.add("hidden");
    panel.classList.remove("hidden");
    const fields = commonFields(node).concat(typeFields(node));
    panel.innerHTML = fields
      .map(function (field) {
        return (
          "<label>" +
          field.label +
          (field.area
            ? "<textarea name=\"" + field.name + "\">" + escapeHtml(field.value) + "</textarea>"
            : "<input name=\"" + field.name + "\" value=\"" + escapeAttr(field.value) + "\" />") +
          "</label>"
        );
      })
      .join("");
  }

  function commonFields(node) {
    return [
      { name: "id", label: "Id", value: node.id },
      { name: "label", label: "Label", value: node.label || "" },
    ];
  }

  function typeFields(node) {
    if (node.type === "dataSource") {
      return [
        { name: "filename", label: "Filename", value: node.filename || "" },
        { name: "context", label: "Context (outer|inner)", value: node.context || "outer" },
        { name: "provides", label: "Provides (comma)", value: (node.provides || []).join(", ") },
        { name: "index", label: "Index (comma)", value: (node.index || []).join(", ") },
      ];
    }
    if (node.type === "loop") {
      return [
        { name: "loopType", label: "Loop type (outer|inner)", value: node.loopType || "outer" },
        { name: "dimension", label: "Dimension", value: node.dimension || "" },
        { name: "size", label: "Size", value: node.size == null ? "" : String(node.size) },
        { name: "vectorize", label: "Vectorize (comma)", value: (node.vectorize || []).join(", ") },
      ];
    }
    if (node.type === "formula") {
      return [
        { name: "section", label: "Section (init|step)", value: node.section || "step" },
        {
          name: "formulas",
          label: "Formulas (NAME: expr per line)",
          value: Object.entries(node.formulas || {})
            .map(([k, v]) => k + ": " + v)
            .join("\n"),
          area: true,
        },
      ];
    }
    const cond = node.condition || {};
    return [
      { name: "variable", label: "Variable", value: node.variable || "" },
      { name: "condVar", label: "Condition variable", value: cond.variable || "" },
      { name: "condOp", label: "Condition operator", value: cond.operator || "==" },
      { name: "condValue", label: "Condition value", value: cond.value == null ? "" : String(cond.value) },
      { name: "reduce", label: "Reduce", value: node.reduce || "mean" },
      { name: "over", label: "Over", value: node.over || "" },
    ];
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(text) {
    return escapeHtml(text).replace(/"/g, "&quot;");
  }

  function csv(value) {
    return String(value || "")
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function parseFormulas(text) {
    const out = {};
    String(text || "")
      .split("\n")
      .forEach((line) => {
        const idx = line.indexOf(":");
        if (idx === -1) return;
        const key = line.slice(0, idx).trim();
        if (key) out[key] = line.slice(idx + 1).trim();
      });
    return out;
  }

  function applyPanel() {
    const node = state.doc.nodes.find((item) => item.id === state.selected);
    if (!node) return;
    const data = new FormData(panel);
    const nextId = String(data.get("id") || node.id).trim() || node.id;
    if (nextId !== node.id) {
      for (const edge of state.doc.edges) {
        if (edge.source === node.id) edge.source = nextId;
        if (edge.target === node.id) edge.target = nextId;
      }
      node.id = nextId;
      state.selected = nextId;
    }
    node.label = String(data.get("label") || node.label);
    if (node.type === "dataSource") {
      node.filename = String(data.get("filename") || "");
      node.context = String(data.get("context") || "outer");
      node.provides = csv(data.get("provides"));
      node.index = csv(data.get("index"));
    } else if (node.type === "loop") {
      node.loopType = String(data.get("loopType") || "outer");
      node.dimension = String(data.get("dimension") || "");
      const size = Number(data.get("size"));
      node.size = Number.isFinite(size) ? size : null;
      node.vectorize = csv(data.get("vectorize"));
    } else if (node.type === "formula") {
      node.section = String(data.get("section") || "step");
      node.formulas = parseFormulas(data.get("formulas"));
    } else if (node.type === "aggregation") {
      node.variable = String(data.get("variable") || "");
      node.condition = {
        variable: String(data.get("condVar") || ""),
        operator: String(data.get("condOp") || "=="),
        value: Number(data.get("condValue") || 0),
      };
      node.reduce = String(data.get("reduce") || "mean");
      node.over = String(data.get("over") || "");
    }
  }

  async function refreshYaml(fromServer) {
    if (fromServer) {
      const exported = await api("POST", "/v0/graph/export", { graph: state.doc });
      yamlBox.value = exported.yaml || "";
    }
    savePersist();
  }

  async function applyYaml(text) {
    const parsed = await api("POST", "/v0/graph/parse", { yaml: text });
    state.doc = parsed.graph;
    yamlBox.value = parsed.yaml;
    if (!state.doc.nodes.some((node) => node.id === state.selected)) state.selected = null;
    renderAll();
    setStatus("YAML applied (" + state.doc.nodes.length + " nodes)");
    savePersist();
  }

  function renderIssues(payload) {
    issuesEl.innerHTML = "";
    const issues = (payload && payload.issues) || [];
    if (!issues.length) {
      const li = document.createElement("li");
      li.textContent = payload && payload.ok ? "No issues" : "No issues reported";
      issuesEl.appendChild(li);
      return;
    }
    for (const issue of issues) {
      const li = document.createElement("li");
      li.className = issue.severity || "error";
      li.textContent = (issue.severity || "error") + ": " + issue.detail;
      issuesEl.appendChild(li);
    }
  }

  function renderAll() {
    renderAuth();
    renderCatalog();
    renderCanvas();
    renderPanel();
  }

  function onNodeDown(event) {
    const handle = event.target.closest(".handle");
    const el = event.currentTarget;
    const id = el.dataset.id;
    state.selected = id;
    renderPanel();
    Array.from(canvas.querySelectorAll(".node")).forEach((node) => {
      node.classList.toggle("selected", node.dataset.id === id);
    });
    if (handle && handle.dataset.handle === "out") {
      state.linking = { source: id };
      return;
    }
    const startX = event.clientX;
    const startY = event.clientY;
    const node = state.doc.nodes.find((item) => item.id === id);
    state.dragging = { id, x: node.x, y: node.y, startX, startY };
    event.preventDefault();
  }

  window.addEventListener("mousemove", (event) => {
    if (!state.dragging) return;
    const node = state.doc.nodes.find((item) => item.id === state.dragging.id);
    if (!node) return;
    node.x = state.dragging.x + (event.clientX - state.dragging.startX);
    node.y = state.dragging.y + (event.clientY - state.dragging.startY);
    const el = canvas.querySelector('[data-id="' + node.id + '"]');
    if (el) {
      el.style.left = node.x + "px";
      el.style.top = node.y + "px";
    }
    renderEdges();
  });

  window.addEventListener("mouseup", (event) => {
    if (state.dragging) {
      state.dragging = null;
      savePersist();
    }
    if (state.linking) {
      const target = event.target.closest(".node");
      if (target && target.dataset.id && target.dataset.id !== state.linking.source) {
        state.doc.edges = state.doc.edges || [];
        state.doc.edges.push({
          id: newId("e"),
          source: state.linking.source,
          target: target.dataset.id,
        });
        renderEdges();
        refreshYaml(true).catch(() => {});
      }
      state.linking = null;
    }
  });

  document.querySelectorAll("[data-add]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const type = btn.getAttribute("data-add");
      if (!NODE_TYPES.includes(type)) return;
      const node = blankNode(type);
      state.doc.nodes.push(node);
      state.doc.stub = false;
      state.selected = node.id;
      renderAll();
      try {
        await refreshYaml(true);
        setStatus("Added " + type);
      } catch (err) {
        setStatus(err.message, true);
      }
    });
  });

  panel.addEventListener("change", async () => {
    applyPanel();
    renderCanvas();
    try {
      await refreshYaml(true);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  $("btn-apply-yaml").addEventListener("click", async () => {
    try {
      await applyYaml(yamlBox.value);
    } catch (err) {
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
  });

  $("btn-open").addEventListener("click", () => openSpec(specSelect.value));
  specSelect.addEventListener("change", () => openSpec(specSelect.value));

  async function openSpec(specId) {
    if (!specId) return;
    savePersist();
    state.specId = specId;
    const cached = state.persistBySpec[specId];
    if (cached && cached.doc) {
      state.doc = cached.doc;
      state.selected = cached.selected || null;
      yamlBox.value = cached.yaml || "";
      renderAll();
      setStatus("Restored " + specId + " from session");
      savePersist();
      return;
    }
    const spec = await api("GET", "/v0/specs/" + encodeURIComponent(specId));
    await applyYaml(spec.content);
    setStatus("Opened catalog spec " + specId);
  }

  $("btn-import").addEventListener("click", () => $("file-import").click());
  $("file-import").addEventListener("change", async (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const text = await file.text();
    try {
      await applyYaml(text);
      setStatus("Imported " + file.name);
    } catch (err) {
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
    event.target.value = "";
  });

  $("btn-export").addEventListener("click", async () => {
    try {
      applyPanel();
      const exported = await api("POST", "/v0/graph/export", { graph: state.doc });
      yamlBox.value = exported.yaml || "";
      const blob = new Blob([exported.yaml], { type: "text/yaml" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = (state.specId || "spec") + ".yaml";
      a.click();
      URL.revokeObjectURL(a.href);
      setStatus("Exported YAML");
      savePersist();
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  $("btn-validate").addEventListener("click", async () => {
    try {
      applyPanel();
      const payload = await api("POST", "/v0/graph/validate", { yaml: yamlBox.value || undefined, graph: state.doc });
      renderIssues(payload);
      setStatus(payload.ok ? "Valid" : "Validation found issues", !payload.ok);
    } catch (err) {
      setStatus(err.message, true);
    }
  });

  $("btn-save").addEventListener("click", async () => {
    if (!state.specId) {
      setStatus("Open a catalog spec before saving", true);
      return;
    }
    if (!state.token) {
      setStatus("Log in to save (G6 Bearer)", true);
      return;
    }
    try {
      applyPanel();
      const exported = await api("POST", "/v0/graph/export", { graph: state.doc });
      yamlBox.value = exported.yaml || "";
      const saved = await api(
        "PUT",
        "/v0/specs/" + encodeURIComponent(state.specId),
        { content: exported.yaml },
        true
      );
      setStatus("Saved overlay v" + saved.version + " (" + saved.storage.backend + ")");
      savePersist();
    } catch (err) {
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
  });

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const session = await api("POST", "/v0/auth/login", {
        email: $("email").value,
        password: $("password").value,
      });
      state.token = session.tokens.accessToken;
      state.user = session.user;
      renderAuth();
      setStatus("Signed in as " + session.user.email);
      savePersist();
    } catch (err) {
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
  });

  $("btn-logout").addEventListener("click", () => {
    state.token = "";
    state.user = null;
    renderAuth();
    setStatus("Logged out");
    savePersist();
  });

  window.addEventListener("resize", renderEdges);

  async function boot() {
    loadPersist();
    renderAuth();
    try {
      const listed = await api("GET", "/v0/specs");
      state.specs = listed.items || [];
      renderCatalog();
      const wanted = new URLSearchParams(location.search).get("spec") || state.specId || (state.specs[0] && state.specs[0].id);
      if (wanted) await openSpec(wanted);
      else renderAll();
    } catch (err) {
      renderAll();
      setStatus(err.message, true);
    }
  }

  boot();
})();
