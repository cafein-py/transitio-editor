// Thin fetch wrapper over the editor's JSON API. Errors carry the
// server's `detail` message.

// Writes in flight: most mutating endpoints act on the backend's
// CURRENT feed, so a feed switch while any write runs could redirect
// it. setCurrentFeed refuses while this is non-zero.
let pendingWrites = 0;

export function writesPending() {
  return pendingWrites > 0;
}

export async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  if (method !== "GET") pendingWrites += 1;
  let response;
  try {
    response = await fetch(path, options);
  } finally {
    if (method !== "GET") pendingWrites -= 1;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (error) {
      /* not JSON */
    }
    const text = typeof detail === "string" ? detail : JSON.stringify(detail);
    const error = new Error(`${method} ${path}: ${text}`);
    error.status = response.status;
    error.detail = detail; // structured 409 details keep their shape
    throw error;
  }
  return response.json();
}
