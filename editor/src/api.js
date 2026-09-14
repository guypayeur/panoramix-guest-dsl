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

export function progressBits(job) {
  const raw = job && job.progress;
  if (!raw || typeof raw !== "object") return [];
  const bits = [];
  if (raw.percent != null && Number.isFinite(Number(raw.percent))) {
    bits.push(Number(raw.percent) + "%");
  }
  if (raw.completed != null && raw.total != null) {
    bits.push(raw.completed + "/" + raw.total);
  }
  if (raw.step != null && raw.steps != null) {
    bits.push("step " + raw.step + "/" + raw.steps);
  }
  if (raw.message) bits.push(String(raw.message));
  return bits;
}
