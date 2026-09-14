import { useEffect, useRef, useState } from "react";
import { applyToolResult } from "./graph.js";

function parseSseChunk(buffer, onEvent) {
  const parts = buffer.split("\n\n");
  const rest = parts.pop() || "";
  parts.forEach((block) => {
    const line = block
      .split("\n")
      .filter((item) => item.indexOf("data: ") === 0)
      .map((item) => item.slice(6))
      .join("");
    if (!line || line === "[DONE]") return;
    try {
      onEvent(JSON.parse(line));
    } catch (_err) {
      /* skip broken frames */
    }
  });
  return rest;
}

export default function ChatPanel({ view, doc, specId, token, onGraph, setStatus }) {
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState(false);
  const [mode, setMode] = useState("unavailable");
  const [tab, setTab] = useState("chat");
  const [messages, setMessages] = useState([]);
  const [debug, setDebug] = useState([]);
  const [usage, setUsage] = useState({
    usage: [],
    totals: { inputTokens: 0, outputTokens: 0, totalTokens: 0, requestCount: 0 },
  });
  const [busy, setBusy] = useState(false);
  const [persist, setPersist] = useState(false);
  const [draft, setDraft] = useState("");
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const dragRef = useRef(null);
  const docRef = useRef(doc);
  docRef.current = doc;
  const onEditor = view === "editor";

  function log(message) {
    const stamp = new Date().toISOString().slice(11, 19);
    setDebug((rows) => [...rows, "[" + stamp + "] " + message]);
  }

  async function refreshStatus() {
    try {
      const status = await (await fetch("/v0/chat")).json();
      setAvailable(!!status.available);
      const bits = [status.mode || "unavailable"];
      if (status.available && (status.provider || status.family)) {
        bits.push([status.provider, status.family].filter(Boolean).join("/"));
      }
      setMode(bits.join(" · "));
    } catch (_err) {
      setAvailable(false);
      setMode("unavailable");
    }
  }

  async function refreshUsage() {
    try {
      setUsage(await (await fetch("/v0/chat/usage")).json());
    } catch (_err) {
      /* optional */
    }
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  function applyResult(result) {
    const applied = applyToolResult(docRef.current, result);
    if (applied.changed) onGraph(applied.doc, applied.selected);
  }

  async function send(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || busy) return;
    if (!available) {
      setStatus("Chat fail-closed (no API key / stub)", true);
      return;
    }
    if (persist && !token) {
      setStatus("Log in to save overlay (G6 Bearer)", true);
      return;
    }
    if (persist && !specId) {
      setStatus("Open a catalog spec before saving overlay", true);
      return;
    }
    setBusy(true);
    setDraft("");
    setMessages((rows) => [...rows, { role: "user", content: message }]);
    log('Sending: "' + message + '"');
    log("State: " + (docRef.current.nodes || []).length + " nodes, " + (docRef.current.edges || []).length + " edges");
    const body = {
      message,
      dslState: {
        metadata: docRef.current.metadata || {},
        description: docRef.current.description || "",
        nodes: docRef.current.nodes || [],
        edges: docRef.current.edges || [],
      },
      persist,
    };
    if (persist) body.spec_id = specId;
    try {
      const headers = { Accept: "text/event-stream", "Content-Type": "application/json" };
      if (persist && token) headers.Authorization = "Bearer " + token;
      const resp = await fetch("/v0/chat", { method: "POST", headers, body: JSON.stringify(body) });
      const ctype = resp.headers.get("content-type") || "";
      if (!resp.ok && ctype.indexOf("text/event-stream") === -1) {
        const text = await resp.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (_err) {
          data = { error: "request_failed" };
        }
        throw Object.assign(new Error(data.detail || data.error || "request_failed"), { payload: data });
      }
      let toolResults = [];
      let assistant = "";
      if (ctype.indexOf("text/event-stream") !== -1 && resp.body && resp.body.getReader) {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let leftover = "";
        while (true) {
          const chunk = await reader.read();
          leftover = parseSseChunk(
            leftover + decoder.decode(chunk.value || new Uint8Array(), { stream: !chunk.done }),
            (evt) => {
              if (evt.type === "tool_use" && evt.result) {
                toolResults.push(evt.result);
                applyResult(evt.result);
                log("Tool: " + (evt.toolName || evt.result.action) + " - " + evt.result.message);
              } else if (evt.type === "message") {
                assistant = evt.content || "";
                (evt.toolResults || []).forEach((result) => {
                  if (!toolResults.some((item) => item.message === result.message && item.action === result.action)) {
                    toolResults.push(result);
                    applyResult(result);
                  }
                });
              } else if (evt.type === "error") {
                throw new Error(evt.error || "chat_error");
              }
            }
          );
          if (chunk.done) break;
        }
      } else {
        const text = await resp.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch (_err) {
          data = { error: "invalid_json" };
        }
        if (!resp.ok) {
          throw Object.assign(new Error(data.error || "request_failed"), { payload: data });
        }
        assistant = data.content || "";
        toolResults = data.toolResults || [];
        toolResults.forEach(applyResult);
      }
      if (!resp.ok && !assistant) throw new Error("chat_unavailable");
      setMessages((rows) => [...rows, { role: "assistant", content: assistant, toolResults }]);
      log("Request completed");
      await refreshUsage();
      setStatus(assistant || "Chat applied " + toolResults.length + " tool(s)");
    } catch (err) {
      const detail = (err.payload && (err.payload.detail || err.payload.error)) || err.message;
      setMessages((rows) => [...rows, { role: "assistant", content: "Error: " + detail }]);
      log("Error: " + detail);
      setStatus(detail, true);
    } finally {
      setBusy(false);
    }
  }

  function onHeaderDown(event) {
    dragRef.current = { x: event.clientX - pos.x, y: event.clientY - pos.y };
    event.preventDefault();
  }

  useEffect(() => {
    const move = (event) => {
      if (!dragRef.current) return;
      setPos({ x: event.clientX - dragRef.current.x, y: event.clientY - dragRef.current.y });
    };
    const up = () => {
      dragRef.current = null;
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, [pos.x, pos.y]);

  const totals = usage.totals || {};

  return (
    <>
      <button
        type="button"
        id="chat-toggle"
        data-testid="chat-toggle"
        className={"chat-toggle" + (!onEditor || open ? " hidden" : "")}
        title="Open AI Assistant"
        onClick={() => {
          setOpen(true);
          refreshStatus();
        }}
      >
        ✦
      </button>
      <aside
        id="chat-panel"
        className={"chat-panel" + (!onEditor || !open ? " hidden" : "")}
        data-testid="chat-panel"
        aria-label="AI chat"
        style={{ transform: "translate(" + pos.x + "px," + pos.y + "px)" }}
      >
        <div className="chat-header" id="chat-header" onMouseDown={onHeaderDown}>
          <h3>AI Assistant</h3>
          <span id="chat-mode" className="chat-mode" data-testid="chat-mode">
            {mode}
          </span>
          <div className="chat-header-actions">
            <button type="button" id="chat-clear" title="Clear chat" onClick={() => { setMessages([]); setDebug([]); }}>
              🗑️
            </button>
            <button type="button" id="chat-close" title="Close" onClick={() => setOpen(false)}>
              ✕
            </button>
          </div>
        </div>
        <div className="chat-tabs" role="tablist">
          <button type="button" id="chat-tab-chat" data-testid="chat-tab-chat" className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button type="button" id="chat-tab-debug" data-testid="chat-tab-debug" className={tab === "debug" ? "active" : ""} onClick={() => setTab("debug")}>
            Debug
          </button>
          <button type="button" id="chat-tab-usage" data-testid="chat-tab-usage" className={tab === "usage" ? "active" : ""} onClick={() => { setTab("usage"); refreshUsage(); }}>
            Usage
          </button>
        </div>
        <p id="chat-unavailable" className={"chat-banner" + (available ? " hidden" : "")} data-testid="chat-unavailable">
          Chat fail-closed — set XAI_API_KEY, ~/.xai, or DSL_CHAT_STUB=1.
        </p>
        <div id="chat-pane" className={"chat-pane" + (tab !== "chat" ? " hidden" : "")}>
          <div id="chat-messages" className="chat-messages" data-testid="chat-messages">
            {!messages.length && (
              <div className="chat-welcome">
                <p>Hi! I can help you create and modify your DSL specification.</p>
                <p>Try asking:</p>
                <ul>
                  <li>Create a data source for population.csv</li>
                  <li>Add an outer loop with 100 iterations</li>
                  <li>Create a formula for calculating returns</li>
                </ul>
              </div>
            )}
            {messages.map((msg, idx) => (
              <div key={idx} className={"chat-message " + msg.role} data-testid="chat-message">
                <div>{msg.content}</div>
                {(msg.toolResults || []).map((result, i) => (
                  <div key={i} className={"tool-result" + (result.success ? "" : " bad")}>
                    {(result.success ? "✓ " : "✗ ") + (result.message || result.action)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div id="chat-debug" className={"chat-pane" + (tab !== "debug" ? " hidden" : "")} data-testid="chat-debug">
          {debug.map((line, idx) => (
            <div key={idx} className="chat-debug-line">
              {line}
            </div>
          ))}
        </div>
        <div id="chat-usage" className={"chat-pane" + (tab !== "usage" ? " hidden" : "")} data-testid="chat-usage">
          <div className="usage-row">
            <span>requests</span>
            <span>{totals.requestCount || 0}</span>
          </div>
          <div className="usage-row">
            <span>tokens</span>
            <span>{totals.totalTokens || 0}</span>
          </div>
          {(usage.usage || []).map((row, idx) => (
            <div key={idx} className="usage-row">
              <span>{row.model || row.id || "turn"}</span>
              <span>{row.totalTokens || 0}</span>
            </div>
          ))}
        </div>
        <form id="chat-form" className="chat-form" data-testid="chat-form" onSubmit={send}>
          <label className="chat-persist">
            <input type="checkbox" id="chat-persist" data-testid="chat-persist" checked={persist} onChange={(e) => setPersist(e.target.checked)} />
            Save overlay (G6 Bearer)
          </label>
          <textarea
            id="chat-input"
            data-testid="chat-input"
            rows="2"
            placeholder="Ask me to create or modify nodes..."
            value={draft}
            disabled={!available || busy}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" id="chat-send" data-testid="chat-send" disabled={!available || busy}>
            Send
          </button>
        </form>
      </aside>
    </>
  );
}
