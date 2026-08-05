// Workspace-wide validation. The backend validates the current feed
// only, so the sweep walks every loaded feed through PUT current →
// POST validate, then restores the original current feed — real
// endpoints in sequence, no invented backend behaviour. A dedicated
// per-feed validate endpoint would make this one request each.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { setCurrentFeed } from "./catalogue.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

export async function validateWorkspace() {
  if (store.validating || !store.catalogue.length) return;
  const original = store.currentFeedId;
  let serverCurrent = original;
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
    store.status = "";
  } catch (error) {
    pushToast({ title: "validation failed", body: error.message });
    store.status = "";
  } finally {
    if (serverCurrent !== original && original) {
      try {
        await api("PUT", "/api/catalogue/current", { feed_id: original });
      } catch (error) {
        store.status = error.message;
      }
    }
    store.validating = false;
  }
}

// A context chip: make its feed current, highlight and zoom to the
// entities it names.
export async function highlightNotice(feedId, context) {
  if (feedId && feedId !== store.currentFeedId) {
    const feed = store.catalogue.find((entry) => entry.feed_id === feedId);
    if (feed) await setCurrentFeed(feed); // also clears the old highlight
  }
  mapBridge.highlightContext(context);
}

export function clearNoticeHighlight() {
  mapBridge.clearHighlight();
}
