// Thin fetch wrapper over the editor's JSON API. Errors carry the
// server's `detail` message.
export async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (error) {
      /* not JSON */
    }
    throw new Error(`${method} ${path}: ${detail}`);
  }
  return response.json();
}
