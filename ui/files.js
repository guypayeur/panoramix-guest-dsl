/* G5 files browse — dsl-gui FilesPage intention, not a SPA lift. */
(function () {
  const TABS = ["specs", "data", "results"];
  const state = {
    tab: tabFromPath(),
    folder: new URLSearchParams(location.search).get("folder") || "",
    items: [],
    folders: [],
    counts: { specs: 0, data: 0, results: 0 },
    selected: null,
    query: "",
  };

  const $ = (id) => document.getElementById(id);
  const rowsEl = $("rows");
  const previewEl = $("preview");
  const previewMeta = $("preview-meta");
  const statusEl = $("status");
  const crumbEl = $("crumb");
  const emptyHint = $("empty-hint");

  function tabFromPath() {
    const parts = location.pathname.replace(/\/+$/, "").split("/");
    const last = parts[parts.length - 1];
    return TABS.includes(last) ? last : "specs";
  }

  async function api(method, path, body) {
    const headers = { Accept: "application/json" };
    const opts = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
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

  function setTabButtons() {
    document.querySelectorAll("[data-tab]").forEach((btn) => {
      const tab = btn.getAttribute("data-tab");
      const count = state.counts[tab] || 0;
      btn.textContent =
        (tab === "specs" ? "Specifications" : tab === "data" ? "Data" : "Results") +
        " (" +
        count +
        ")";
      btn.classList.toggle("active", tab === state.tab);
    });
  }

  function syncUrl() {
    const path = "/files/" + state.tab;
    const params = new URLSearchParams();
    if (state.folder) params.set("folder", state.folder);
    const next = path + (params.toString() ? "?" + params.toString() : "");
    history.replaceState({}, "", next);
  }

  function renderCrumb() {
    crumbEl.innerHTML = "";
    const root = document.createElement("button");
    root.type = "button";
    root.textContent = state.tab;
    root.addEventListener("click", () => openFolder(""));
    crumbEl.appendChild(root);
    if (!state.folder) return;
    const parts = state.folder.split("/").filter(Boolean);
    let acc = "";
    parts.forEach((part) => {
      acc = acc ? acc + "/" + part : part;
      const sep = document.createElement("span");
      sep.textContent = " / ";
      sep.className = "muted";
      crumbEl.appendChild(sep);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = part;
      const target = acc;
      btn.addEventListener("click", () => openFolder(target));
      crumbEl.appendChild(btn);
    });
  }

  function visibleItems() {
    const q = state.query.trim().toLowerCase();
    const items = state.items.filter((item) => {
      if (!q) return true;
      return (
        String(item.name || "").toLowerCase().includes(q) ||
        String(item.path || "").toLowerCase().includes(q) ||
        String(item.id || "").toLowerCase().includes(q)
      );
    });
    return items;
  }

  function renderRows() {
    rowsEl.innerHTML = "";
    const folders = state.folder ? [] : state.folders;
    const items = visibleItems();
    emptyHint.classList.toggle("hidden", folders.length + items.length > 0);

    folders.forEach((folder) => {
      const tr = document.createElement("tr");
      tr.dataset.testid = "folder-" + folder.path;
      tr.innerHTML =
        "<td>📁 " +
        escapeHtml(folder.name) +
        "</td><td class=\"muted\">" +
        escapeHtml(folder.path) +
        "</td><td class=\"muted\">" +
        (folder.file_count || 0) +
        " files</td><td></td>";
      tr.addEventListener("click", () => openFolder(folder.path));
      rowsEl.appendChild(tr);
    });

    items.forEach((item) => {
      const tr = document.createElement("tr");
      tr.dataset.testid = "file-" + item.id;
      tr.classList.toggle("selected", state.selected === item.id);
      const open =
        item.open && item.tab === "specs"
          ? "<a href=\"" + item.open + "\">Open in editor</a>"
          : "";
      tr.innerHTML =
        "<td>📄 " +
        escapeHtml(item.name || item.filename || item.id) +
        (item.overlay ? " <span class=\"muted\">overlay</span>" : "") +
        "</td><td class=\"muted\">" +
        escapeHtml(item.path || "") +
        "</td><td class=\"muted\">" +
        (item.size_bytes == null ? "" : String(item.size_bytes)) +
        "</td><td>" +
        open +
        "</td>";
      tr.addEventListener("click", () => selectFile(item));
      rowsEl.appendChild(tr);
    });
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function selectFile(item) {
    state.selected = item.id;
    renderRows();
    previewMeta.textContent = (item.path || item.id) + " · " + (item.location || "guest-local");
    try {
      const text = await api("GET", "/v0/files/" + item.tab + "/" + encodeURIComponent(item.id) + "/text");
      if (text.encoding === "binary") {
        previewEl.textContent = "(binary; " + text.bytes + " bytes)";
      } else {
        previewEl.textContent = text.content || "";
      }
      setStatus("Read " + item.path);
    } catch (err) {
      previewEl.textContent = "";
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
  }

  async function openFolder(folder) {
    state.folder = folder || "";
    state.selected = null;
    previewEl.textContent = "";
    previewMeta.textContent = "Select a file.";
    syncUrl();
    await loadTab();
  }

  async function loadSummary() {
    const listed = await api("GET", "/v0/files");
    for (const tab of listed.tabs || []) {
      state.counts[tab.id] = tab.count || 0;
    }
    setTabButtons();
  }

  async function loadTab() {
    const params = new URLSearchParams();
    if (state.folder) params.set("folder", state.folder);
    const qs = params.toString() ? "?" + params.toString() : "";
    const listed = await api("GET", "/v0/files/" + state.tab + qs);
    state.items = listed.items || [];
    state.folders = listed.folders || [];
    state.counts[state.tab] = listed.total_count || 0;
    setTabButtons();
    renderCrumb();
    renderRows();
    setStatus(
      "Browsing " +
        state.tab +
        (state.folder ? " / " + state.folder : "") +
        " · guest-local · writes refused"
    );
  }

  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      state.tab = btn.getAttribute("data-tab");
      state.folder = "";
      state.selected = null;
      previewEl.textContent = "";
      previewMeta.textContent = "Select a file.";
      syncUrl();
      try {
        await loadTab();
      } catch (err) {
        setStatus((err.payload && err.payload.detail) || err.message, true);
      }
    });
  });

  $("search").addEventListener("input", (event) => {
    state.query = event.target.value || "";
    renderRows();
  });

  $("btn-upload").addEventListener("click", async () => {
    try {
      await api("POST", "/v0/files/" + state.tab, { filename: "upload-refused.csv" });
      setStatus("unexpected write", true);
    } catch (err) {
      const code = err.payload && err.payload.error;
      const detail = err.payload && err.payload.detail;
      setStatus(detail || code || err.message, code === "write_refused");
    }
  });

  async function boot() {
    try {
      await loadSummary();
      await loadTab();
    } catch (err) {
      setStatus((err.payload && err.payload.detail) || err.message, true);
    }
  }

  boot();
})();
