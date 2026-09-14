export async function api(method, path, body, token) {
  const headers = { Accept: "application/json" };
  const opts = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  if (token) headers.Authorization = "Bearer " + token;
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

export function isTerminal(status) {
  return status === "succeeded" || status === "failed" || status === "canceled";
}

function fmtElapsed(raw) {
  if (raw.elapsed != null && Number.isFinite(Number(raw.elapsed))) {
    return Number(raw.elapsed) + "s";
  }
  if (raw.elapsed_ms != null && Number.isFinite(Number(raw.elapsed_ms))) {
    return Number(raw.elapsed_ms) / 1000 + "s";
  }
  if (raw.wall_elapsed_ms != null && Number.isFinite(Number(raw.wall_elapsed_ms))) {
    return Number(raw.wall_elapsed_ms) / 1000 + "s";
  }
  return "";
}

export function progressBits(job) {
  const raw = job && job.progress;
  if (!raw || typeof raw !== "object") return [];
  const bits = [];
  if (raw.stage != null && raw.stage !== "") {
    bits.push("stage " + raw.stage);
  }
  if (raw.stages_completed != null && raw.stages_total != null) {
    bits.push(raw.stages_completed + "/" + raw.stages_total);
  }
  if (raw.fraction != null && Number.isFinite(Number(raw.fraction))) {
    bits.push("fraction " + raw.fraction);
  }
  const elapsed = fmtElapsed(raw);
  if (elapsed) bits.push(elapsed);
  // percent only when the hook supplied it — never invent from fraction
  if (raw.percent != null && Number.isFinite(Number(raw.percent))) {
    bits.push(Number(raw.percent) + "%");
  }
  if (raw.completed != null && raw.total != null) {
    bits.push(raw.completed + "/" + raw.total);
  }
  if (raw.step != null && raw.steps != null) {
    bits.push("step " + raw.step + "/" + raw.steps);
  }
  if (raw.catalog) bits.push(String(raw.catalog));
  if (raw.bel != null && Number.isFinite(Number(raw.bel))) {
    bits.push("BEL " + raw.bel);
  }
  if (raw.walls && raw.walls.wall_sec_time != null && Number.isFinite(Number(raw.walls.wall_sec_time))) {
    if (!elapsed) bits.push(Number(raw.walls.wall_sec_time) + "s");
  }
  if (raw.executed === true) bits.push("executed");
  if (raw.message) bits.push(String(raw.message));
  return bits;
}
