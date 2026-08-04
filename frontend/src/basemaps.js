// The selectable background basemaps: raster tiles, each carrying the
// attribution its provider requires. Positron's minimal, low-contrast
// tone keeps the mode colors readable, which is why it is the default
// (the palette was validated against a light surface).
const carto = (style) =>
  ["a", "b", "c", "d"].map(
    (sub) => `https://${sub}.basemaps.cartocdn.com/${style}/{z}/{x}/{y}.png`,
  );

export const BASEMAPS = [
  {
    key: "positron",
    label: "CartoDB Positron",
    tiles: carto("light_all"),
    attribution: "© OpenStreetMap contributors © CARTO",
  },
  {
    key: "voyager",
    label: "Voyager",
    tiles: carto("rastertiles/voyager"),
    attribution: "© OpenStreetMap contributors © CARTO",
  },
  {
    key: "osm",
    label: "OpenStreetMap",
    tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    attribution: "© OpenStreetMap contributors",
  },
  {
    key: "dark",
    label: "Dark Matter",
    tiles: carto("dark_all"),
    attribution: "© OpenStreetMap contributors © CARTO",
  },
];

export const DEFAULT_BASEMAP = "positron";

export function basemapLayerId(key) {
  return `basemap-${key}`;
}

export function basemapLabel(key) {
  const entry = BASEMAPS.find((basemap) => basemap.key === key);
  return entry ? entry.label : key;
}
