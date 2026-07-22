// Pure helpers for the OSM network layer. The api-calling actions live in
// actions.js; the imperative map wiring in map.js.

// Which domain the map edits, from the active tab: the Network tab targets
// the OSM network, every other tab targets the GTFS feed.
export function editTarget(activeTab) {
  return activeTab === "network" ? "network" : "feed";
}

// Columns that are identity/topology/metadata, not OSM tags.
const STRUCTURAL = new Set([
  "id",
  "osm_type",
  "nodes",
  "version",
  "changeset",
  "timestamp",
  "visible",
  "lon",
  "lat",
]);

// The displayable OSM tags of a network feature, as sorted [key, value] pairs:
// the free-form `tags` dict merged with any promoted tag columns. MapLibre
// stringifies nested feature properties, so `tags` may arrive as a JSON
// string (from a map click) or an object (straight from the API).
export function networkTags(properties) {
  const pairs = [];
  for (const [key, value] of Object.entries(properties || {})) {
    if (STRUCTURAL.has(key) || value == null) continue;
    if (key === "tags") {
      const dict = typeof value === "string" ? safeParse(value) : value;
      if (dict && typeof dict === "object") {
        for (const [tag, tagValue] of Object.entries(dict)) {
          pairs.push([tag, String(tagValue)]);
        }
      }
    } else {
      pairs.push([key, String(value)]);
    }
  }
  return pairs.sort((a, b) => a[0].localeCompare(b[0]));
}

function safeParse(text) {
  try {
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}
