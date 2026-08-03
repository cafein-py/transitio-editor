// GTFS route-type modes: display palette and the MapLibre expressions that
// color and filter the shapes layer by mode. The backend normalises extended
// route types to these base codes.
export const MODES = [
  { code: 0, label: "tram", color: "#d81b60" },
  { code: 1, label: "metro", color: "#e65100" },
  { code: 2, label: "rail", color: "#6a1b9a" },
  { code: 3, label: "bus", color: "#1565c0" },
  { code: 4, label: "ferry", color: "#00838f" },
  { code: 5, label: "cable tram", color: "#8d6e63" },
  { code: 6, label: "aerial lift", color: "#5d4037" },
  { code: 7, label: "funicular", color: "#7b1fa2" },
  { code: 11, label: "trolleybus", color: "#2e7d32" },
  { code: 12, label: "monorail", color: "#c2185b" },
];

// Shapes with no known route type (e.g. hand-drawn, or no trip yet).
export const UNKNOWN_MODE_COLOR = "#c0392b";

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
