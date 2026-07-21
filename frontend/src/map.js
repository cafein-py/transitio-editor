// The imperative MapLibre bridge: owns the map, the draw-interaction
// state, layer refreshes, click handling and highlighting. Vue
// components call these functions; the map itself is never reactive.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { api } from "./api.js";
import { SNAP_FILTERS, store } from "./store.js";

let map = null;
let drawnPoints = []; // [lat, lon]
let previewCoords = []; // [lon, lat]
let drawSequence = 0; // discards out-of-order snap responses
let lastStops = null; // latest stops GeoJSON, for highlight fly-to

export function getPreviewCoords() {
  return previewCoords;
}

export function setCursor(kind) {
  if (map) map.getCanvas().style.cursor = kind;
}

function renderPreview() {
  const source = map.getSource("preview");
  if (source) {
    source.setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: previewCoords },
    });
  }
}

export function resetDraw() {
  drawnPoints = [];
  previewCoords = [];
  drawSequence += 1; // invalidate any in-flight snap response
  renderPreview();
}

async function refreshSummary() {
  const summary = await api("GET", "/api/feed");
  store.source = summary.source;
  store.tables = summary.tables;
  store.snapAvailable = Boolean(summary.snapAvailable);
}
export { refreshSummary };

async function refreshLayers(fit) {
  const [stops, shapes] = await Promise.all([
    api("GET", "/api/stops"),
    api("GET", "/api/shapes"),
  ]);
  lastStops = stops;
  map.getSource("stops").setData(stops);
  map.getSource("shapes").setData(shapes);
  if (fit && stops.features.length) {
    const bounds = new maplibregl.LngLatBounds();
    for (const feature of stops.features) {
      bounds.extend(feature.geometry.coordinates);
    }
    map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
  }
}

export async function refreshAll(fit) {
  // Every mutation path funnels through here, so the last validation
  // report is marked stale even for unwrapped actions (map clicks).
  if (store.report) store.reportStale = true;
  await refreshSummary();
  await refreshLayers(fit);
}

export function setHighlight(stopIds, shapeIds) {
  map.setFilter("stops-highlight", ["in", ["get", "stop_id"], ["literal", stopIds]]);
  map.setFilter("shapes-highlight", [
    "in",
    ["get", "shape_id"],
    ["literal", shapeIds],
  ]);
  store.highlightActive = stopIds.length > 0 || shapeIds.length > 0;
}

export function clearHighlight() {
  setHighlight([], []);
}

export function highlightContext(context) {
  const stopIds = [];
  const shapeIds = [];
  for (const [key, value] of Object.entries(context)) {
    if (/stopid/i.test(key)) stopIds.push(String(value));
    if (/shapeid/i.test(key)) shapeIds.push(String(value));
  }
  setHighlight(stopIds, shapeIds);
  if (stopIds.length && lastStops) {
    const hit = lastStops.features.find(
      (feature) => feature.properties.stop_id === stopIds[0],
    );
    if (hit) {
      map.flyTo({ center: hit.geometry.coordinates, zoom: 15 });
    }
  }
}

async function handleMapClick(event) {
  const { lng, lat } = event.lngLat;
  try {
    if (store.movingStop) {
      await api("PATCH", `/api/stops/${encodeURIComponent(store.movingStop)}`, {
        stop_lat: lat,
        stop_lon: lng,
      });
      store.movingStop = null;
      store.status = "";
      await refreshAll(false);
      return;
    }
    if (store.mode === "add-stop") {
      const stopId = prompt("stop_id?");
      if (!stopId) return;
      const name = prompt("stop name?", stopId) || stopId;
      await api("POST", "/api/stops", {
        stop_id: stopId,
        stop_name: name,
        stop_lat: lat,
        stop_lon: lng,
      });
      await refreshAll(false);
      return;
    }
    if (store.mode === "draw") {
      drawnPoints.push([lat, lng]);
      if (store.snapAvailable && store.snapOn && drawnPoints.length >= 2) {
        const sequence = ++drawSequence;
        const request = { waypoints: [...drawnPoints] };
        const filter = SNAP_FILTERS[store.snapNetwork];
        if (filter) request.custom_filter = filter;
        const feature = await api("POST", "/api/shapes/snap", request);
        if (sequence !== drawSequence) return; // superseded by a newer click
        previewCoords = feature.geometry.coordinates;
      } else {
        previewCoords = drawnPoints.map(([a, b]) => [b, a]);
      }
      renderPreview();
    }
  } catch (error) {
    store.status = error.message;
  }
}

export function createMap() {
  map = new maplibregl.Map({
    container: "map",
    style: {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: "© OpenStreetMap contributors",
        },
      },
      layers: [{ id: "osm", type: "raster", source: "osm" }],
    },
    center: [24.94, 60.17],
    zoom: 11,
  });
  map.addControl(new maplibregl.NavigationControl());

  map.on("load", async () => {
    for (const id of ["stops", "shapes"]) {
      map.addSource(id, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
    }
    map.addSource("preview", {
      type: "geojson",
      data: { type: "Feature", geometry: { type: "LineString", coordinates: [] } },
    });
    map.addLayer({
      id: "shapes",
      type: "line",
      source: "shapes",
      paint: { "line-color": "#35507a", "line-width": 3, "line-opacity": 0.8 },
    });
    map.addLayer({
      id: "preview",
      type: "line",
      source: "preview",
      paint: { "line-color": "#c0392b", "line-width": 3, "line-dasharray": [2, 1] },
    });
    map.addLayer({
      id: "shapes-highlight",
      type: "line",
      source: "shapes",
      filter: ["in", ["get", "shape_id"], ["literal", []]],
      paint: { "line-color": "#d81b60", "line-width": 6, "line-opacity": 0.6 },
    });
    map.addLayer({
      id: "stops",
      type: "circle",
      source: "stops",
      paint: {
        "circle-radius": 6,
        "circle-color": "#e67e22",
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 1.5,
      },
    });
    map.addLayer({
      id: "stops-highlight",
      type: "circle",
      source: "stops",
      filter: ["in", ["get", "stop_id"], ["literal", []]],
      paint: {
        "circle-radius": 10,
        "circle-color": "rgba(216, 27, 96, 0.35)",
        "circle-stroke-color": "#d81b60",
        "circle-stroke-width": 2,
      },
    });

    map.on("click", "stops", (event) => {
      if (store.movingStop || store.mode !== "select") return;
      const properties = event.features[0].properties;
      if (store.tripPicking) {
        store.tripStops.push({
          stopId: properties.stop_id,
          offset: store.tripStops.length * 120,
        });
      } else {
        store.inspector = {
          stopId: properties.stop_id,
          name: properties.stop_name || "",
        };
      }
      event.preventDefault();
    });
    map.on("click", (event) => {
      if (event.defaultPrevented) return;
      handleMapClick(event);
    });

    try {
      await refreshAll(true);
    } catch (error) {
      store.status = error.message;
    }
  });
}
