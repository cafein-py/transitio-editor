// The street-network map layers: one line layer per highway class (the
// design's colour/width/dash scale), the amber way-selection halo, and
// the shape-vertex handles with drag editing. map.js owns the map and
// injects it here plus the callbacks this module must not import
// (fetchNetwork lives in map.js — importing it back would be a cycle).
import { api } from "../api.js";
import { nodeById, waysData } from "../entities.js";
import { logRequestEdit } from "../session.js";
import {
  classFilter,
  HAS_HIGHWAY,
  HIGHWAY_CLASSES,
  highwayClass,
  wayClass,
} from "../streets.js";
import { store } from "../store.js";

let map = null;
let hooks = { refreshNetwork: async () => {} };

const layerId = (key) => `street-${key}`;
export const STREET_LAYER_IDS = HIGHWAY_CLASSES.map((entry) =>
  layerId(entry.key),
);

// The design widths are the z15 look; interpolate around them.
const widthExpr = (width) => [
  "interpolate",
  ["exponential", 1.4],
  ["zoom"],
  10,
  Math.max(0.4, width * 0.15),
  13,
  width * 0.45,
  15,
  width,
  17,
  width * 1.8,
];

export function initStreetsLayers(m, overrides) {
  map = m;
  Object.assign(hooks, overrides);

  // Non-highway ways (railway kept for snapping) stay visible as faint
  // neutral context; they are not part of the street scale or legend.
  map.addLayer({
    id: "street-other",
    type: "line",
    source: "network-ways",
    filter: ["!", HAS_HIGHWAY],
    layout: { visibility: "none" },
    paint: {
      "line-color": "#9aa0a8",
      "line-width": 1.2,
      "line-dasharray": [3, 3],
      "line-opacity": 0.5,
    },
  });
  // Selection halo under the class layers: the way's own line stays on top.
  map.addLayer({
    id: "street-selected",
    type: "line",
    source: "network-ways",
    filter: ["boolean", false],
    layout: { visibility: "none" },
    paint: {
      "line-color": "#ffd60a",
      "line-width": widthExpr(7),
      "line-opacity": 0.85,
    },
  });
  for (const entry of HIGHWAY_CLASSES) {
    map.addLayer({
      id: layerId(entry.key),
      type: "line",
      source: "network-ways",
      filter: classFilter(entry.key),
      layout: { visibility: "none" },
      paint: {
        "line-color": entry.color,
        "line-width": widthExpr(entry.width),
        ...(entry.dash ? { "line-dasharray": entry.dash } : {}),
        "line-opacity": 0.92,
      },
    });
  }

  map.on("click", STREET_LAYER_IDS, (event) => {
    if (event.defaultPrevented || store.activePanel !== "streets") return;
    if (dragNodeId != null) return;
    selectWay(event.features[0].properties);
    event.preventDefault();
  });
}

// The vertex-handle layer goes on top of everything (added late).
export function initStreetsHandles(m) {
  m.addSource("street-vertices", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  m.addLayer({
    id: "street-vertices",
    type: "circle",
    source: "street-vertices",
    paint: {
      "circle-radius": 4.5,
      "circle-color": "#fff",
      "circle-stroke-color": "#16181c",
      "circle-stroke-width": 2.2,
    },
  });
  // Bound here, after the layer exists.
  m.on("mousedown", "street-vertices", startVertexDrag);
}

function allStreetLayers() {
  return [
    "street-other",
    "street-selected",
    ...STREET_LAYER_IDS,
    "street-vertices",
  ];
}

export function setStreetsVisible(visible) {
  if (!map) return;
  for (const id of allStreetLayers()) {
    if (!map.getLayer(id)) continue;
    const hidden =
      !visible ||
      (STREET_LAYER_IDS.includes(id) &&
        store.hiddenHighwayClasses.includes(id.slice("street-".length)));
    map.setLayoutProperty(id, "visibility", hidden ? "none" : "visible");
  }
}

export function applyHiddenClasses() {
  setStreetsVisible(store.network.visible);
}

export function selectWay(properties) {
  store.network.selected = properties ? { ...properties } : null;
  store.network.vertexEdit = false;
  renderHandles([]);
  if (!map || !map.getLayer("street-selected")) return;
  if (!properties) {
    map.setFilter("street-selected", ["boolean", false]);
    return;
  }
  const entry = highwayClass(wayClass(properties));
  map.setPaintProperty(
    "street-selected",
    "line-width",
    widthExpr((entry ? entry.width : 2) + 5),
  );
  map.setFilter("street-selected", ["==", ["get", "id"], properties.id]);
}

// ---- Shape-vertex editing --------------------------------------------

// The selected way's node ids, from the raw ways data (map-rendered
// features stringify the list).
function selectedWayNodes() {
  const selected = store.network.selected;
  if (!selected) return [];
  const way = waysData().find((f) => f.properties.id === selected.id);
  let nodes = way ? way.properties.nodes : selected.nodes;
  if (typeof nodes === "string") {
    try {
      nodes = JSON.parse(nodes);
    } catch (error) {
      return [];
    }
  }
  return Array.isArray(nodes) ? nodes : [];
}

function handleFeatures() {
  return selectedWayNodes()
    .map((id) => {
      const node = nodeById(id);
      return node
        ? {
            type: "Feature",
            geometry: node.geometry,
            properties: { id },
          }
        : null;
    })
    .filter(Boolean);
}

function renderHandles(features) {
  const source = map && map.getSource("street-vertices");
  if (source) source.setData({ type: "FeatureCollection", features });
}

export function setVertexEdit(on) {
  store.network.vertexEdit = on;
  renderHandles(on ? handleFeatures() : []);
}

// Re-sync after the network data changed (a drag committed, an undo ran).
export function refreshStreets() {
  if (store.network.selected) {
    const still = waysData().find(
      (f) => f.properties.id === store.network.selected.id,
    );
    if (!still) {
      selectWay(null);
      return;
    }
    store.network.selected = { ...still.properties };
  }
  if (store.network.vertexEdit) renderHandles(handleFeatures());
}

let dragNodeId = null;
let dragStart = null;
let dragPosition = null;

function startVertexDrag(event) {
  if (!store.network.editing || !store.network.vertexEdit) return;
  const feature = event.features && event.features[0];
  if (!feature) return;
  dragNodeId = feature.properties.id;
  dragStart = [...feature.geometry.coordinates];
  dragPosition = dragStart;
  map.dragPan.disable();
  map.getCanvas().style.cursor = "grabbing";
  map.on("mousemove", onVertexDrag);
  map.once("mouseup", endVertexDrag);
  event.preventDefault();
}

function onVertexDrag(event) {
  if (dragNodeId == null) return;
  dragPosition = [event.lngLat.lng, event.lngLat.lat];
  const features = handleFeatures().map((f) =>
    f.properties.id === dragNodeId
      ? { ...f, geometry: { type: "Point", coordinates: dragPosition } }
      : f,
  );
  renderHandles(features);
}

async function endVertexDrag() {
  map.off("mousemove", onVertexDrag);
  map.dragPan.enable();
  map.getCanvas().style.cursor = "";
  const nodeId = dragNodeId;
  const from = dragStart;
  const to = dragPosition;
  dragNodeId = null;
  dragStart = null;
  dragPosition = null;
  if (nodeId == null || !to || (from[0] === to[0] && from[1] === to[1])) {
    return;
  }
  const path = `/api/network/nodes/${nodeId}`;
  try {
    await api("PATCH", path, { lon: to[0], lat: to[1] });
  } catch (error) {
    store.status = error.message;
    renderHandles(handleFeatures()); // snap the handle back
    return;
  }
  logRequestEdit(
    "Vertex moved",
    `node/${nodeId}`,
    { method: "PATCH", path, body: { lon: from[0], lat: from[1] } },
    { method: "PATCH", path, body: { lon: to[0], lat: to[1] } },
  );
  store.dirty = true;
  await hooks.refreshNetwork();
}
