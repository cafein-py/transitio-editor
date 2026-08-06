// The workspace session core: an activity log every mutation reports to,
// and undo/redo over it. Three entry kinds carry their own reversal:
//   server  — the backend's per-feed history reverts it (/api/undo, pinned
//             to the entry's feed; the feed is made current first if needed)
//   request — a compensating API request reverts/reapplies it (OSM edits,
//             which have no server history)
//   local   — a snapshot of store keys restores it client-side
//   none    — logged for the record, not undoable (says so when tried)
import { api, writesPending } from "./api.js";
import { store } from "./store.js";
import { pushToast } from "./toasts.js";

export const LOG_LIMIT = 300;

// Log entries for street-network actions file under this pseudo feed id.
export const NETWORK_FEED = "__network__";

let seq = 1;

// Injected by App.vue so this module never imports actions.js: refresh
// re-reads server state into the open views after a server/request
// reversal; makeCurrent switches the current feed (server undo acts on
// the current feed only).
const hooks = {
  refresh: async () => {},
  makeCurrent: async () => {},
};

export function configureSession(overrides) {
  Object.assign(hooks, overrides);
}

// Monotonic across the session: the exact "did anything change since?"
// token. The log's length is not one — it stops growing at LOG_LIMIT,
// and an undo followed by a new action leaves it unchanged. Bumped by
// logAction AND by a committed undo/redo (both change the data).
let revision = 0;

export function sessionRevision() {
  return revision;
}

// Returns the new entry's id, so a caller can offer an undo bound to
// exactly its own action (a toast that outlives later edits).
export function logAction(entry) {
  const log = store.session.log;
  const id = seq++;
  log.push({
    id,
    time: Date.now(),
    kind: "none",
    feedId: null,
    detail: "",
    ...entry,
  });
  if (log.length > LOG_LIMIT) log.splice(0, log.length - LOG_LIMIT);
  revision += 1;
  // A new action invalidates what was undone before it, and any
  // validation report no longer reflects the data.
  store.session.redoStack.length = 0;
  store.dirty = true;
  store.reportStale = true;
  const logged = log[log.length - 1];
  if (logged.feedId && logged.feedId !== NETWORK_FEED) {
    store.staleReportFeeds = {
      ...store.staleReportFeeds,
      [logged.feedId]: true,
    };
  }
  return id;
}

// The common cases, so call sites stay one line. Callers snapshot the
// feed id BEFORE their await: a feed switch during the request must not
// pin the entry (and its undo) to the wrong feed.
export function logServerEdit(title, detail, feedId) {
  return logAction({
    kind: "server",
    feedId: feedId ?? store.currentFeedId,
    title,
    detail,
  });
}

export function logRequestEdit(title, detail, undoReq, redoReq, feedId = NETWORK_FEED) {
  if (!undoReq) {
    // no way back known: keep the record, refuse the undo
    logAction({ kind: "none", feedId, title, detail });
    return;
  }
  logAction({
    kind: "request",
    feedId,
    title,
    detail,
    undoReq,
    redoReq,
  });
}

export function logPlain(title, detail, feedId = null) {
  logAction({ kind: "none", feedId, title, detail });
}

export function logLocal(title, detail, snapshot, redo) {
  logAction({ kind: "local", title, detail, snapshot, redo });
}

async function applyEntry(entry, direction) {
  if (entry.kind === "server") {
    // Server history is per feed and current-feed-only; switch first.
    if (entry.feedId && entry.feedId !== store.currentFeedId) {
      await hooks.makeCurrent(entry.feedId);
      if (store.currentFeedId !== entry.feedId) {
        throw new Error(`could not make ${entry.feedId} the current feed`);
      }
    }
    const path = direction === "undo" ? "/api/undo" : "/api/redo";
    await api("POST", path, { feed_id: entry.feedId });
  } else if (entry.kind === "request") {
    const request = direction === "undo" ? entry.undoReq : entry.redoReq;
    if (!request) throw new Error(`${entry.title} cannot be ${direction}ne`);
    await api(request.method, request.path, request.body);
  } else if (entry.kind === "local") {
    const patch = direction === "undo" ? entry.snapshot : entry.redo;
    for (const [key, value] of Object.entries(patch || {})) {
      store[key] = structuredClone(value);
    }
  }
}

async function step(from, to, direction, verb) {
  const entry = from[from.length - 1];
  if (!entry || store.historyBusy) return;
  if (store.validating) {
    // The sweep lets the backend current feed roam; feed-pinned undo
    // would race it.
    pushToast({ title: `cannot ${direction} while validation runs` });
    return;
  }
  if (entry.kind === "none") {
    pushToast({ title: `cannot ${direction}`, body: `${entry.title} cannot be ${verb}` });
    return;
  }
  if (writesPending()) {
    // /api/undo reverts the backend's newest entry; an edit still
    // committing would be that entry, not the one shown here.
    pushToast({
      title: `cannot ${direction} yet`,
      body: "an edit is still saving",
    });
    return;
  }
  store.historyBusy = true;
  try {
    await applyEntry(entry, direction);
  } catch (error) {
    pushToast({ title: `${direction} failed`, body: error.message });
    store.historyBusy = false;
    return;
  }
  // Committed: the stacks move NOW, so a refresh hiccup can't read as
  // "the undo failed, try again" and revert a second entry. Remove the
  // entry we reverted by identity — an edit that logged during the
  // await sits on top of it and must stay.
  const index = from.lastIndexOf(entry);
  if (index !== -1) from.splice(index, 1);
  to.push(entry);
  revision += 1; // a reversal is a data change like any other
  store.dirty = true;
  if (entry.feedId && entry.feedId !== NETWORK_FEED) {
    store.staleReportFeeds = {
      ...store.staleReportFeeds,
      [entry.feedId]: true,
    };
    store.reportStale = true;
  }
  const title = `${direction === "undo" ? "undid" : "redid"} ${entry.title}`;
  try {
    if (entry.kind !== "local") await hooks.refresh();
    pushToast({ title, body: entry.detail, duration: 3500 });
  } catch (error) {
    pushToast({ title, body: `refresh failed: ${error.message}` });
  } finally {
    store.historyBusy = false;
  }
}

export async function sessionUndo() {
  await step(store.session.log, store.session.redoStack, "undo", "undone");
}

// The undo a toast offers: it reverts THAT action, so it refuses once
// later edits have landed on top of it rather than undoing those.
export function undoEntry(entryId) {
  return async () => {
    const log = store.session.log;
    const top = log[log.length - 1];
    if (!top || top.id !== entryId) {
      pushToast({
        title: "cannot undo that action any more",
        body: "newer edits came after it — use the session drawer",
      });
      return;
    }
    await sessionUndo();
  };
}

export async function sessionRedo() {
  await step(store.session.redoStack, store.session.log, "redo", "redone");
}

// What a workspace save embeds: the visible record, not the reversal
// machinery — server history does not survive a reload, so a restored
// entry is viewable but not undoable.
export function sessionLogForSave() {
  return store.session.log.map(({ time, title, detail, feedId }) => ({
    time,
    title,
    detail,
    feedId,
  }));
}

export function restoredLogEntries(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((entry) => entry && typeof entry.title === "string")
    .slice(-LOG_LIMIT)
    .map((entry) => ({
      id: seq++,
      time: Number.isFinite(entry.time) ? entry.time : Date.now(),
      title: entry.title,
      detail: typeof entry.detail === "string" ? entry.detail : "",
      feedId: typeof entry.feedId === "string" ? entry.feedId : null,
      kind: "none",
    }));
}

export function installRestoredLog(raw) {
  const log = store.session.log;
  log.splice(0, log.length, ...restoredLogEntries(raw));
  store.session.redoStack.length = 0;
}
