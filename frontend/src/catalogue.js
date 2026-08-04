// Pure helpers for presenting the feed catalogue. The api-calling
// actions live in actions.js; these are the display-only functions.
import { MODES } from "./modes.js";

export function feedTableSummary(tables) {
  // table counts are keyed by GTFS filename ("stops.txt"), as served by
  // the catalogue endpoints
  const stops = (tables && tables["stops.txt"]) || 0;
  const routes = (tables && tables["routes.txt"]) || 0;
  const stopWord = stops === 1 ? "stop" : "stops";
  const routeWord = routes === 1 ? "route" : "routes";
  return `${stops} ${stopWord}, ${routes} ${routeWord}`;
}

export function currentFeed(catalogue, currentFeedId) {
  return catalogue.find((feed) => feed.feed_id === currentFeedId) || null;
}

// The legend entries for a feed's mode codes (unknown codes are skipped),
// for the catalogue's per-feed mode chips.
export function feedModes(modes) {
  if (!modes) return [];
  return MODES.filter((mode) => modes.includes(mode.code));
}

// Whether an entry holds an actual feed: a launch without one still
// registers an empty builder to build a feed from scratch on.
function hasFeedContent(feed) {
  return Boolean(feed.source) || Object.keys(feed.tables || {}).length > 0;
}

// The tab to open on startup: with a feed loaded the editor starts on the
// data; with nothing to show it starts where feeds are found.
export function initialTab(catalogue) {
  return (catalogue || []).some(hasFeedContent) ? "view" : "search";
}

// The status line after a merge: where it went (when saved) and any files
// the merge could not carry over, so the loss is visible.
export function mergeStatus(name, droppedFiles, savedPath) {
  const dropped = droppedFiles || [];
  const head = savedPath
    ? `merged into "${name}", saved to ${savedPath}`
    : `merged into "${name}"`;
  if (!dropped.length) return head;
  return `${head} — ${dropped.join(", ")} not carried over`;
}
