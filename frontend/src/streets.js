// Pure helpers for the Streets panel: the highway class scale (colour /
// width / dash from the design handoff), class detection, and lengths.

export const HIGHWAY_CLASSES = [
  { key: "motorway", color: "#b8412a", width: 6.0, dash: null },
  { key: "trunk", color: "#cf6a34", width: 5.0, dash: null },
  { key: "primary", color: "#dd9a2b", width: 4.2, dash: null },
  { key: "secondary", color: "#b9a02b", width: 3.4, dash: null },
  { key: "tertiary", color: "#87994a", width: 2.8, dash: null },
  { key: "residential", color: "#5f7183", width: 2.2, dash: null },
  { key: "service", color: "#93a0ac", width: 1.6, dash: [6, 4], startHidden: true },
  { key: "cycleway", color: "#2b6cb8", width: 1.9, dash: [7, 4] },
  { key: "footway", color: "#8a5cc4", width: 1.7, dash: [2, 3.5], startHidden: true },
];

export const DEFAULT_HIDDEN_CLASSES = HIGHWAY_CLASSES.filter(
  (entry) => entry.startHidden,
).map((entry) => entry.key);

export function highwayClass(key) {
  return HIGHWAY_CLASSES.find((entry) => entry.key === key) || null;
}

// OSM highway values folded into the nine display classes; link roads
// join their parent, minor path-like values join footway, and anything
// unrecognised files under service (the least prominent solid class).
const CLASS_OF_VALUE = new Map([
  ...HIGHWAY_CLASSES.map((entry) => [entry.key, entry.key]),
  ["motorway_link", "motorway"],
  ["trunk_link", "trunk"],
  ["primary_link", "primary"],
  ["secondary_link", "secondary"],
  ["tertiary_link", "tertiary"],
  ["living_street", "residential"],
  ["unclassified", "residential"],
  ["road", "residential"],
  ["track", "service"],
  ["busway", "service"],
  ["path", "footway"],
  ["pedestrian", "footway"],
  ["steps", "footway"],
  ["bridleway", "footway"],
]);

export function classOfHighway(value) {
  return CLASS_OF_VALUE.get(String(value || "").toLowerCase()) || "service";
}

// The OSM highway value of a way feature: a promoted column, or a key in
// the tags dict (which MapLibre may hand over as a JSON string).
export function wayHighway(properties) {
  if (!properties) return null;
  if (properties.highway != null) return String(properties.highway);
  let tags = properties.tags;
  if (typeof tags === "string") {
    try {
      tags = JSON.parse(tags);
    } catch (error) {
      return null;
    }
  }
  return tags && tags.highway != null ? String(tags.highway) : null;
}

export function wayClass(properties) {
  const value = wayHighway(properties);
  return value ? classOfHighway(value) : "service";
}

// Great-circle length of a [lon, lat] LineString, in kilometres.
export function lineLengthKm(coordinates) {
  const R = 6371;
  let total = 0;
  for (let i = 1; i < (coordinates || []).length; i += 1) {
    const [lon1, lat1] = coordinates[i - 1];
    const [lon2, lat2] = coordinates[i];
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) ** 2;
    total += 2 * R * Math.asin(Math.sqrt(a));
  }
  return total;
}

// Way counts per class, for the legend rows.
export function classCounts(features) {
  const counts = Object.fromEntries(
    HIGHWAY_CLASSES.map((entry) => [entry.key, 0]),
  );
  for (const feature of features || []) {
    counts[wayClass(feature.properties)] += 1;
  }
  return counts;
}

// A way with no highway value at all (e.g. railway kept for snapping) is
// not part of the street scale.
export const HAS_HIGHWAY = [
  "!=",
  ["coalesce", ["to-string", ["get", "highway"]], ""],
  "",
];

// The MapLibre filter selecting one display class: every raw highway
// value that folds into it.
export function classFilter(key) {
  const base = ["match", ["downcase", ["to-string", ["get", "highway"]]]];
  if (key === "service") {
    // service also catches values outside the table (the fallback class):
    // any highway value NOT owned by another class
    const owned = [...CLASS_OF_VALUE.entries()]
      .filter(([, target]) => target !== "service")
      .map(([value]) => value);
    return ["all", HAS_HIGHWAY, [...base, owned, false, true]];
  }
  const values = [...CLASS_OF_VALUE.entries()]
    .filter(([, target]) => target === key)
    .map(([value]) => value);
  return [...base, values, true, false];
}
