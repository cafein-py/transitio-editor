// Catalogue-domain actions: the feed list, groups, drag filing, the edit
// target, merge and crop. Structural changes log to the session; pure
// view state (visibility, colour-by) does not.
import { api, writesPending } from "../api.js";
import {
  cropRequestBody,
  cropStatus,
  mergeStatus,
  moveFeedToGroup,
} from "../catalogue.js";
import * as mapBridge from "../map.js";
import { logPlain, logRequestEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";
import { resetFeedScopedState, toggleEditMode } from "../actions.js";

// Overlapping reloads (a drop while another mutation settles) must not
// let an older listing paint over a newer one.
let catalogueSeq = 0;

export async function loadCatalogue() {
  const seq = ++catalogueSeq;
  try {
    const body = await api("GET", "/api/catalogue");
    if (seq !== catalogueSeq) return;
    const previous = store.currentFeedId;
    store.catalogue = body.feeds;
    store.groups = body.groups || [];
    store.currentFeedId = body.current;
    // Some endpoints reassign the current feed as a side effect (a
    // download with activate, removing the current feed). The old
    // feed's selections, drafts and timetable must not stay actionable
    // against the new edit target. (Explicit switches reset first and
    // pre-set currentFeedId, so they don't re-enter here.)
    if (previous !== null && body.current !== previous) {
      resetFeedScopedState();
    }
  } catch (error) {
    if (seq !== catalogueSeq) return;
    store.status = error.message;
  }
}

const groupsPath = (name) =>
  `/api/catalogue/groups?name=${encodeURIComponent(name)}`;

// Every group mutation re-reads the catalogue rather than assigning the
// response directly: loadCatalogue is the one guarded writer, so an
// older in-flight listing cannot paint over the change.
export async function createGroup(rawName) {
  const name = (rawName || "").trim();
  if (!name) return;
  try {
    await api("POST", "/api/catalogue/groups", { name });
    store.status = "";
    logRequestEdit(
      "Group added",
      name,
      { method: "DELETE", path: groupsPath(name) },
      { method: "POST", path: "/api/catalogue/groups", body: { name } },
      null,
    );
    await loadCatalogue();
  } catch (error) {
    store.status = error.message;
  }
}

export async function renameGroup(name, newName) {
  const target = (newName || "").trim();
  if (!target || target === name) return;
  try {
    await api("PATCH", "/api/catalogue/groups", { name, new_name: target });
    logRequestEdit(
      "Group renamed",
      `${name} → ${target}`,
      {
        method: "PATCH",
        path: "/api/catalogue/groups",
        body: { name: target, new_name: name },
      },
      {
        method: "PATCH",
        path: "/api/catalogue/groups",
        body: { name, new_name: target },
      },
      null,
    );
    await loadCatalogue();
  } catch (error) {
    store.status = error.message;
  }
}

export async function deleteGroup(name) {
  if (!window.confirm(`Remove the group "${name}"? Its feeds stay loaded.`)) {
    return;
  }
  try {
    await api("DELETE", groupsPath(name));
    // Its feeds' group assignments are gone with it: logged, not undoable.
    logPlain("Group removed", name);
    await loadCatalogue();
  } catch (error) {
    store.status = error.message;
  }
}

// Group reordering has no backend endpoint yet (groups list in creation
// order); the stub keeps the arrows honest until it exists.
export async function reorderGroup(name, direction) {
  try {
    await api("PATCH", "/api/catalogue/groups/order", { name, direction });
    await loadCatalogue();
  } catch (error) {
    pushToast({
      title: "group reorder is not supported by the backend yet",
      body: error.message,
    });
  }
}

// Drag and drop between group sections; the pure part is moveFeedToGroup.
export function startFeedDrag(feed) {
  store.draggingFeedId = feed.feed_id;
}

export function endFeedDrag() {
  store.draggingFeedId = null;
}

// Drops are applied one at a time, in the order they happened: parallel
// PATCHes could otherwise land out of order and file a feed in the group
// it was dragged out of. `requested` holds each feed's latest requested
// group so a quick drag-back is not read as a no-op against the
// not-yet-reloaded catalogue.
let dropQueue = Promise.resolve();
const requested = new Map();

export async function dropFeedInGroup(group) {
  const feed = store.catalogue.find(
    (entry) => entry.feed_id === store.draggingFeedId,
  );
  store.draggingFeedId = null;
  if (!feed) return;
  const pending = requested.has(feed.feed_id)
    ? { ...feed, group: requested.get(feed.feed_id) }
    : feed;
  const move = moveFeedToGroup(pending, group);
  if (!move) return;
  const previous = pending.group || null;
  requested.set(move.feed_id, move.group);
  dropQueue = dropQueue.then(async () => {
    try {
      const path = `/api/catalogue/${encodeURIComponent(move.feed_id)}`;
      await api("PATCH", path, { group: move.group });
      logRequestEdit(
        "Feed moved",
        `${feed.name} → ${move.group || "ungrouped"}`,
        { method: "PATCH", path, body: { group: previous } },
        { method: "PATCH", path, body: { group: move.group } },
        move.feed_id,
      );
      await loadCatalogue();
    } catch (error) {
      store.status = error.message;
      // rebase: drop the optimistic intent and re-read committed state,
      // so a queued follow-up cannot log an undo to an uncommitted group
      requested.delete(move.feed_id);
      await loadCatalogue();
    } finally {
      if (requested.get(move.feed_id) === move.group) {
        requested.delete(move.feed_id);
      }
    }
  });
  await dropQueue;
}

export async function addFeed(rawPath) {
  const path = (rawPath || "").trim();
  if (!path) return false;
  if (store.validating) {
    store.status = "validation is running — try again in a moment";
    return false;
  }
  try {
    await api("POST", "/api/catalogue", { path });
    logPlain("Feed loaded", path.split(/[\\/]/).pop());
    await loadCatalogue();
    await mapBridge.refreshAll(true);
    store.status = "";
    return true;
  } catch (error) {
    store.status = error.message;
    return false;
  }
}

export async function setCurrentFeed(feed) {
  if (store.validating || store.saving || writesPending()) {
    // Mutating endpoints act on the backend's current feed; switching
    // while any of them is still in flight could redirect it.
    store.status = store.validating
      ? "validation is running — try again in a moment"
      : "an edit is still saving — try again in a moment";
    return false;
  }
  try {
    const body = await api("PUT", "/api/catalogue/current", {
      feed_id: feed.feed_id,
    });
    resetFeedScopedState();
    // Reflect the committed switch locally so the UI stays consistent even
    // if the follow-up reload fails; loadCatalogue then refreshes the rest.
    store.currentFeedId = body.current;
    for (const entry of store.catalogue) {
      entry.current = entry.feed_id === body.current;
    }
    await loadCatalogue();
    await mapBridge.refreshSummary();
    return true;
  } catch (error) {
    store.status = error.message;
    return false;
  }
}

// Make a feed the edit target: visible, current, editing on. Editing is
// enabled only once the feed is verifiably the current one — a failed
// activation or switch must not arm editing on the previous target.
export async function makeEditTarget(feed) {
  if (!feed.active && !(await toggleFeedActive(feed))) return false;
  if (!feed.current && !(await setCurrentFeed(feed))) return false;
  if (store.currentFeedId !== feed.feed_id) return false;
  if (!store.editMode) toggleEditMode();
  return true;
}

// The row pencil: make the feed the edit target, or step editing off it.
export async function toggleEditTarget(feed) {
  if (feed.current) {
    toggleEditMode();
    return;
  }
  await makeEditTarget(feed);
}

export async function renameFeed(feed, rawName) {
  const name = (rawName || "").trim();
  if (!name || name === feed.name) return;
  const path = `/api/catalogue/${encodeURIComponent(feed.feed_id)}`;
  try {
    await api("PATCH", path, { name });
    logRequestEdit(
      "Feed renamed",
      `${feed.name} → ${name}`,
      { method: "PATCH", path, body: { name: feed.name } },
      { method: "PATCH", path, body: { name } },
      feed.feed_id,
    );
    await loadCatalogue();
  } catch (error) {
    store.status = error.message;
  }
}

export async function toggleFeedActive(feed) {
  try {
    await api("PATCH", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`, {
      active: !feed.active,
    });
    await loadCatalogue();
    await mapBridge.refreshAll(false);
    return true;
  } catch (error) {
    store.status = error.message;
    return false;
  }
}

// One PATCH per feed that differs, one reload at the end (a group's eye
// or "Show all feeds" flips many at once). The reload runs even when a
// later PATCH fails: the earlier ones committed, and the UI must show
// the backend's actual state, not the pre-attempt one.
export async function setFeedsActive(feeds, active) {
  const changing = feeds.filter((feed) => feed.active !== active);
  if (!changing.length) return;
  try {
    for (const feed of changing) {
      try {
        await api(
          "PATCH",
          `/api/catalogue/${encodeURIComponent(feed.feed_id)}`,
          { active },
        );
      } catch (error) {
        pushToast({
          title: `could not update ${feed.name}`,
          body: error.message,
        });
        break;
      }
    }
  } finally {
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  }
}

export async function removeFeed(feed) {
  if (store.validating || store.saving) {
    store.status = "busy — try again in a moment";
    return;
  }
  if (!window.confirm(`Remove "${feed.name}" from the workspace?`)) return;
  try {
    await api("DELETE", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`);
    logPlain("Feed removed", feed.name, feed.feed_id);
    // Removing the current feed reassigns current, so drop its state too.
    if (feed.current) resetFeedScopedState();
    store.merge.selected = store.merge.selected.filter(
      (id) => id !== feed.feed_id,
    );
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  } catch (error) {
    store.status = error.message;
  }
}

// Cropping the feeds on the map to the drawn area. The shape is drawn
// first and confirmed here, so an accidental double-click cannot start a
// long operation and the options can be set before it runs.
export async function cropToShape() {
  // The crop rewrites feeds; the read-only state must not execute it
  // even if a stale confirm card is still on screen.
  if (!store.editMode || store.validating) return;
  const body = cropRequestBody(store.cropShape, store.crop);
  if (!body || store.crop.running) return;
  store.crop.running = true;
  try {
    const result = await api("POST", "/api/catalogue/crop", body);
    mapBridge.cancelCropDraw(); // clears the shape and the drawing state
    logPlain("Feeds cropped", `${(result.feeds || []).length} copies`);
    await loadCatalogue();
    await mapBridge.refreshAll(false);
    await mapBridge.refreshSummary();
    store.status = cropStatus(result);
  } catch (error) {
    store.status = error.message;
  } finally {
    store.crop.running = false;
  }
}

export function toggleMergeSelected(feed) {
  const selected = store.merge.selected;
  store.merge.selected = selected.includes(feed.feed_id)
    ? selected.filter((id) => id !== feed.feed_id)
    : [...selected, feed.feed_id];
}

export async function mergeSelected() {
  const merge = store.merge;
  if (merge.selected.length < 2 || merge.merging) return;
  if (store.validating || store.saving) {
    store.status = "busy — try again in a moment";
    return;
  }
  merge.merging = true;
  try {
    const directory = merge.directory.trim();
    const body = await api("POST", "/api/catalogue/merge", {
      feed_ids: [...merge.selected],
      name: merge.name.trim(),
      ...(directory ? { directory } : {}),
    });
    logPlain("Feeds merged", body.name);
    // The merge makes the new feed current, so old feed-scoped state goes.
    resetFeedScopedState();
    merge.selected = [];
    merge.name = "";
    await loadCatalogue();
    await mapBridge.refreshAll(false);
    await mapBridge.refreshSummary();
    store.status = mergeStatus(body.name, body.dropped_files, body.saved);
  } catch (error) {
    store.status = error.message;
  } finally {
    merge.merging = false;
  }
}
