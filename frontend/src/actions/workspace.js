// Saving the workspace from the header: first save names it (dialog),
// later saves reuse the stored path. Restore stays with the session
// actions until the landing page takes it over.
import { api } from "../api.js";
import { getCamera } from "../map.js";
import { sessionView } from "../sessions.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

// A workspace name as a session file name: path separators and other
// characters filesystems refuse are dropped, whitespace collapsed.
export function workspaceFileName(name) {
  const cleaned = String(name || "")
    .replace(/[/\\:*?"<>|]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return cleaned ? `${cleaned}.json` : null;
}

// Where the naming dialog starts browsing: the server's default listing
// folder (the user's home), fetched once.
let defaultDir = null;

export async function defaultWorkspaceDir() {
  if (defaultDir) return defaultDir;
  const listing = await api("GET", "/api/fs/dirs");
  defaultDir = listing.path;
  return defaultDir;
}

export async function saveWorkspaceAs(name, dir) {
  const session = store.session;
  const file = workspaceFileName(name);
  if (!file || !dir || session.saving) return false;
  session.saving = true;
  try {
    const view = {
      ...sessionView(store, getCamera()),
      ws_name: name.trim(),
    };
    const body = await api("POST", "/api/session/save", {
      path: `${dir.replace(/[/\\]$/, "")}/${file}`,
      view,
    });
    session.wsName = name.trim();
    session.named = true;
    session.savedAt = Date.now();
    session.dir = dir;
    session.path = body.path;
    store.dirty = false;
    pushToast({ title: "workspace saved", body: body.path });
    return true;
  } catch (error) {
    pushToast({ title: "workspace not saved", body: error.message });
    return false;
  } finally {
    session.saving = false;
  }
}

// Direct save once named; false tells the caller to open the naming dialog.
export async function saveWorkspace() {
  const session = store.session;
  if (!session.named) return false;
  return saveWorkspaceAs(session.wsName, session.dir);
}
