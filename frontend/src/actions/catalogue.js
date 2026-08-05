// Catalogue-domain actions: the feed list, groups, drag filing, the edit
// target, merge and crop. Structural changes log to the session; pure
// view state (visibility, colour-by) does not.
import { api } from "../api.js";
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
    store.catalogue = body.feeds;
    store.groups = body.groups || [];
    store.currentFeedId = body.current;
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
export async function createGroup() {
  const name = store.newGroupName.trim();
  if (!name) return;
  try {
    await api("POST", "/api/catalogue/groups", { name });
    store.newGroupName = "";
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
    } finally {
      if (requested.get(move.feed_id) === move.group) {
        requested.delete(move.feed_id);
      }
    }
  });
  await dropQueue;
}

export async function addFeed() {
  const path = store.newFeedPath.trim();
  if (!path) return;
  try {
    await api("POST", "/api/catalogue", { path });
    store.newFeedPath = "";
    logPlain("Feed loaded", path.split(/[\\/]/).pop());
    await loadCatalogue();
    await mapBridge.refreshAll(true);
    store.status = "";
  } catch (error) {
    store.status = error.message;
  }
}

export async function setCurrentFeed(feed) {
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
  } catch (error) {
    store.status = error.message;
  }
}

// The row pencil: make the feed the edit target, or step editing off it.
export async function toggleEditTarget(feed) {
  if (feed.current) {
    toggleEditMode();
    return;
  }
  if (!feed.active) await toggleFeedActive(feed);
  await setCurrentFeed(feed);
  if (!store.editMode) toggleEditMode();
}

export async function toggleFeedActive(feed) {
  try {
    await api("PATCH", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`, {
      active: !feed.active,
    });
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  } catch (error) {
    store.status = error.message;
  }
}

// One PATCH per feed that differs, one reload at the end (a group's eye
// or "Show all feeds" flips many at once).
export async function setFeedsActive(feeds, active) {
  const changing = feeds.filter((feed) => feed.active !== active);
  if (!changing.length) return;
  try {
    for (const feed of changing) {
      await api("PATCH", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`, {
        active,
      });
    }
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  } catch (error) {
    store.status = error.message;
  }
}

export async function removeFeed(feed) {
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
