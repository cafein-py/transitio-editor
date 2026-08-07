// Saving the workspace from the header: first save names it (dialog),
// later saves reuse the stored path. Restore stays with the session
// actions until the landing page takes it over.
import { api } from "../api.js";
import { getCamera } from "../map.js";
import { sessionLogForSave, sessionRevision } from "../session.js";
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

async function persistWorkspace(path, name) {
  const session = store.session;
  if (session.saving) return false;
  const revision = sessionRevision();
  session.saving = true;
  try {
    const view = {
      ...sessionView(store, getCamera()),
      ws_name: name,
      log: sessionLogForSave(),
    };
    const body = await api("POST", "/api/session/save", { path, view });
    session.wsName = name;
    session.named = true;
    session.savedAt = Date.now();
    // The server's returned path is canonical; keep name/dir derived
    // from it so later saves and the Save-as prefill agree with it.
    session.path = body.path;
    session.dir = body.path.split(/[\\/]/).slice(0, -1).join("/");
    // an edit that landed while the save ran is NOT in this snapshot
    if (sessionRevision() === revision) store.dirty = false;
    pushToast({ title: "workspace saved", body: body.path });
    return true;
  } catch (error) {
    pushToast({ title: "workspace not saved", body: error.message });
    return false;
  } finally {
    session.saving = false;
  }
}

export async function saveWorkspaceAs(name, dir) {
  const file = workspaceFileName(name);
  if (!file || !dir) return false;
  return persistWorkspace(`${dir.replace(/[/\\]$/, "")}/${file}`, name.trim());
}

// Direct save once named; false tells the caller to open the naming
// dialog. A restored workspace saves to its canonical restored path —
// never to a directory retained from a previous workspace.
export async function saveWorkspace() {
  const session = store.session;
  if (!session.named) return false;
  if (session.path.trim()) {
    return persistWorkspace(session.path.trim(), session.wsName);
  }
  return saveWorkspaceAs(session.wsName, session.dir);
}
