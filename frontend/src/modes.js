// GTFS route-type modes: display palette and the MapLibre expressions that
// color and filter the shapes layer by mode. The backend normalises extended
// route types to these base codes.
export const MODES = [
  // Colorblind-validated palette (OKLab CVD separation >= 8 across every
  // co-occurring pair, checked programmatically): the five common modes keep
  // widely used semantic transit colors (blue bus, green tram, orange metro,
  // purple rail, cyan ferry); rare modes use a muted secondary family.
  { code: 0, label: "tram", color: "#00794a" },
  { code: 1, label: "metro", color: "#ff6319" },
  { code: 2, label: "rail", color: "#a34d9f" },
  { code: 3, label: "bus", color: "#007ac9" },
  { code: 4, label: "ferry", color: "#00b9e4" },
  { code: 5, label: "cable tram", color: "#a0522d" },
  { code: 6, label: "aerial lift", color: "#33689e" },
  { code: 7, label: "funicular", color: "#b085c9" },
  { code: 11, label: "trolleybus", color: "#009c82" },
  { code: 12, label: "monorail", color: "#ad1457" },
];

// Shapes with no known route type (e.g. hand-drawn, or no trip yet). They
// render and toggle like a mode of their own, keyed by the sentinel -1 that
// the color/filter expressions coalesce a missing route_type to.
export const UNKNOWN_MODE_COLOR = "#7f7f7f"; // neutral gray: supplemental, not a mode
export const UNKNOWN_MODE = {
  code: -1,
  label: "other / unknown",
  color: UNKNOWN_MODE_COLOR,
};

// The distinct mode codes present in a shapes FeatureCollection, sorted;
// a missing route_type counts as the unknown sentinel -1. Drives which
// rows the legend offers (only modes the loaded feeds actually contain).
export function presentModeCodes(features) {
  const codes = new Set();
  for (const feature of features) {
    codes.add(feature.properties?.route_type ?? -1);
  }
  return [...codes].sort((a, b) => a - b);
}

export function modeColorExpression() {
  const expression = ["match", ["coalesce", ["get", "route_type"], -1]];
  for (const mode of MODES) expression.push(mode.code, mode.color);
  expression.push(UNKNOWN_MODE_COLOR);
  return expression;
}

export function feedColorExpression() {
  return ["coalesce", ["get", "feed_color"], "#35507a"];
}

// A layer filter hiding the given mode codes; unknown-mode shapes are only
// hidden when -1 is listed. Null clears the filter.
export function modeFilterExpression(hiddenCodes) {
  if (!hiddenCodes.length) return null;
  return [
    "!",
    [
      "in",
      ["coalesce", ["get", "route_type"], -1],
      ["literal", [...hiddenCodes]],
    ],
  ];
}
