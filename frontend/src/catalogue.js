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

// The catalogue as display sections: one per known group in order,
// then the ungrouped feeds. Empty groups are kept — they are drop
// targets, and a group outlives its last member.
export function groupedCatalogue(catalogue, groups) {
  const feeds = catalogue || [];
  const known = groups || [];
  const sections = known.map((name) => ({
    name,
    feeds: feeds.filter((feed) => feed.group === name),
  }));
  const ungrouped = feeds.filter(
    (feed) => !feed.group || !known.includes(feed.group),
  );
  return { sections, ungrouped };
}

// Where a drop lands: the group a feed should move to, or null for the
// ungrouped section. Returns null when nothing would change, so a drop
// onto the feed's own group costs no request.
export function moveFeedToGroup(feed, group) {
  if (!feed) return null;
  const target = group || null;
  if ((feed.group || null) === target) return null;
  return { feed_id: feed.feed_id, group: target };
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

// The body POST /api/catalogue/crop takes for a drawn area, or null when
// there is nothing to crop with.
export function cropRequestBody(shape, options) {
  if (!shape) return null;
  const settings = options || {};
  const group = (settings.group || "").trim();
  return {
    shape,
    full_trips_only: Boolean(settings.fullTripsOnly),
    ...(group ? { group } : {}),
  };
}

// The status line after a crop: what was created, what came back empty,
// and what failed — three separate outcomes, never conflated.
export function cropStatus(result) {
  const created = (result && result.feeds) || [];
  const empty = (result && result.empty) || [];
  const skipped = (result && result.skipped) || [];
  const parts = [
    created.length
      ? `cropped ${created.length} feed${created.length === 1 ? "" : "s"}`
      : "nothing cropped",
  ];
  if (empty.length) parts.push(`${empty.join(", ")} came back empty`);
  if (skipped.length) {
    parts.push(
      `failed: ${skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}`,
    );
  }
  return parts.join(" — ");
}

// The GeoJSON polygon a drawn ring becomes, or an error when it cannot be
// one. MapLibre reports longitudes continuously across world copies (a
// ring drawn on the second copy of Europe reads as ~385°), so the ring is
// shifted as a whole into [-180, 180]; shifting each vertex on its own
// would turn a small area drawn across the antimeridian into a
// world-spanning one, so such an area is refused instead.
export function cropShapeFromRing(ring) {
  if (!ring || ring.length < 3) return { error: "an area needs three corners" };
  const lngs = ring.map(([lng]) => lng);
  const shift = -360 * Math.floor((Math.min(...lngs) + 180) / 360);
  const shifted = ring.map(([lng, lat]) => [lng + shift, lat]);
  if (shifted.some(([lng]) => lng < -180 || lng > 180)) {
    return { error: "an area crossing the antimeridian cannot be cropped" };
  }
  return {
    shape: { type: "Polygon", coordinates: [[...shifted, shifted[0]]] },
  };
}
