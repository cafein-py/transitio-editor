// Workspace-wide validation. The backend validates the current feed
// only, so the sweep walks every loaded feed through PUT current →
// POST validate, then restores the original current feed — real
// endpoints in sequence, no invented backend behaviour. A dedicated
// per-feed validate endpoint would make this one request each.
import { resetFeedScopedState } from "../actions.js";
import { api, writesPending } from "../api.js";
import * as mapBridge from "../map.js";
import { loadCatalogue, setCurrentFeed } from "./catalogue.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

export async function validateWorkspace() {
  if (store.validating || !store.catalogue.length) return;
  if (store.saving || store.historyBusy || writesPending()) {
    // The sweep repoints the backend's current feed; it must not
    // interleave with a save, an undo, or an in-flight edit.
    pushToast({ title: "busy — try validating again in a moment" });
    return;
  }
  const original = store.currentFeedId;
  let serverCurrent = original;
  // While the backend's current feed roams, the current-feed-only
  // mutation surface must stay disarmed: editing goes off for the
  // sweep (and the edit/save/feed-switch actions refuse while
  // store.validating is set).
  const wasEditing = store.editMode;
  store.editMode = false;
  store.validating = true;
  try {
    for (const feed of store.catalogue) {
      store.status = `validating ${feed.name}…`;
      if (feed.feed_id !== serverCurrent) {
        await api("PUT", "/api/catalogue/current", { feed_id: feed.feed_id });
        serverCurrent = feed.feed_id;
      }
      const body = await api("POST", "/api/validate", {});
      store.reports = { ...store.reports, [feed.feed_id]: body.report };
      if (feed.feed_id === original) store.report = body.report;
    }
    store.reportStale = false;
    store.staleReportFeeds = {};
    store.status = "";
  } catch (error) {
    pushToast({ title: "validation failed", body: error.message });
    store.status = "";
  } finally {
    let restored = serverCurrent === original;
    if (!restored && original) {
      try {
        await api("PUT", "/api/catalogue/current", { feed_id: original });
        restored = true;
      } catch (error) {
        store.status = error.message;
      }
    }
    store.validating = false;
    if (restored) {
      if (wasEditing) store.editMode = true;
    } else {
      // The backend points at a different feed than the UI believed;
      // reconcile to its truth and stay read-only.
      pushToast({
        title: "could not restore the current feed",
        body: "the edit target follows the backend's state",
      });
      try {
        const body = await api("GET", "/api/catalogue");
        store.catalogue = body.feeds;
        store.groups = body.groups || [];
        store.currentFeedId = body.current;
      } catch (error) {
        // reconciliation itself failed: keep read-only, say so
        store.status = `catalogue out of sync: ${error.message}`;
      }
      resetFeedScopedState();
    }
  }
}

// A context chip: make its feed current, highlight and zoom to the
// entities it names. The highlight is scoped to the current feed, so a
// refused/failed switch must not paint the ids onto another feed.
export async function highlightNotice(feedId, context) {
  if (feedId && feedId !== store.currentFeedId) {
    const feed = store.catalogue.find((entry) => entry.feed_id === feedId);
    if (!feed || !(await setCurrentFeed(feed))) {
      pushToast({
        title: "could not switch to the notice's feed",
        body: store.status || feedId,
      });
      return;
    }
    if (store.currentFeedId !== feedId) return;
  }
  mapBridge.highlightContext(context);
}

export function clearNoticeHighlight() {
  mapBridge.clearHighlight();
}
