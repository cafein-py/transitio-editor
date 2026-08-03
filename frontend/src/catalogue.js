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
