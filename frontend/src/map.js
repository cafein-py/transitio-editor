// The imperative MapLibre bridge: owns the map, the draw-interaction
// state, layer refreshes, click handling and highlighting. Vue
// components call these functions; the map itself is never reactive.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { api } from "./api.js";
import { SNAP_FILTERS, store } from "./store.js";
import { editTarget } from "./network.js";

let map = null;
// Resolves once the map's sources and layers exist, so network data applied
// from actions never races the map "load" event.
let resolveMapReady;
export const mapReady = new Promise((resolve) => {
  resolveMapReady = resolve;
});
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

// The current viewport as [minx, miny, maxx, maxy] for a bbox feed
// search. A viewport that crosses the antimeridian or spans the globe
// can't be one WGS84 bbox, so skip the bounds filter rather than send a
// clamped (wrong) one that silently drops the wrapped half.
export function getViewportBbox() {
  if (!map) return null;
  const bounds = map.getBounds();
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  if (ne.lng - sw.lng >= 360 || sw.lng < -180 || ne.lng > 180) return null;
  const clampLat = (value) => Math.max(-90, Math.min(90, value));
  return [sw.lng, clampLat(sw.lat), ne.lng, clampLat(ne.lat)];
}

export function fitBbox(bbox) {
  if (!map || !bbox) return;
  const [minx, miny, maxx, maxy] = bbox;
  map.fitBounds(
    [
      [minx, miny],
      [maxx, maxy],
    ],
    { padding: 40, maxZoom: 15 },
  );
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
  store.currentFeedId = summary.currentFeedId ?? null;
  store.snapAvailable = Boolean(summary.snapAvailable);
  // Keep the current feed's catalogue counts in step with its table sizes
  // so the Catalogue tab doesn't show stale counts after a mutation.
  const entry = store.catalogue.find((f) => f.feed_id === store.currentFeedId);
  if (entry) entry.tables = summary.tables;
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
  // A report is for the current feed; entity IDs repeat across active
  // feeds, so scope the highlight to the current feed's features.
  const feedId = store.currentFeedId;
  const scoped = (idKey, ids) => {
    const match = ["in", ["get", idKey], ["literal", ids]];
    return feedId ? ["all", ["==", ["get", "feed_id"], feedId], match] : match;
  };
  map.setFilter("stops-highlight", scoped("stop_id", stopIds));
  map.setFilter("shapes-highlight", scoped("shape_id", shapeIds));
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
      (feature) =>
        feature.properties.stop_id === stopIds[0] &&
        (!store.currentFeedId ||
          feature.properties.feed_id === store.currentFeedId),
    );
    if (hit) {
      map.flyTo({ center: hit.geometry.coordinates, zoom: 15 });
    }
  }
}

async function handleMapClick(event) {
  // Map clicks mutate the feed (move/add stop, draw); inert while the OSM
  // network is the edit target.
  if (editTarget(store.activeTab) !== "feed") return;
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
    for (const id of ["stops", "shapes", "network-ways", "network-nodes"]) {
      map.addSource(id, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
    }
    map.addSource("preview", {
      type: "geojson",
      data: { type: "Feature", geometry: { type: "LineString", coordinates: [] } },
    });
    // OSM network under the GTFS layers: ways always, nodes only when zoomed
    // in (a whole-city node layer is too dense otherwise).
    map.addLayer({
      id: "network-ways",
      type: "line",
      source: "network-ways",
      layout: { visibility: "none" },
      paint: { "line-color": "#7a4fbf", "line-width": 1.5, "line-opacity": 0.6 },
    });
    map.addLayer({
      id: "network-nodes",
      type: "circle",
      source: "network-nodes",
      minzoom: 15,
      layout: { visibility: "none" },
      paint: {
        "circle-radius": 3,
        "circle-color": "#7a4fbf",
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 1,
      },
    });
    map.addLayer({
      id: "shapes",
      type: "line",
      source: "shapes",
      paint: {
        "line-color": ["coalesce", ["get", "feed_color"], "#35507a"],
        "line-width": 3,
        "line-opacity": 0.8,
      },
    });
    map.addLayer({
      id: "preview",
      type: "line",
      source: "preview",
      paint: { "line-color": "#c0392b", "line-width": 3, "line-dasharray": [2, 1] },
    });
    map.addSource("network-preview", {
      type: "geojson",
      data: { type: "Feature", geometry: { type: "LineString", coordinates: [] } },
    });
    map.addLayer({
      id: "network-preview",
      type: "line",
      source: "network-preview",
      paint: { "line-color": "#7a4fbf", "line-width": 3, "line-dasharray": [2, 1] },
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
        "circle-color": ["coalesce", ["get", "feed_color"], "#e67e22"],
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
      // While editing the OSM network, stops are context: ignore them
      // silently (no preventDefault) so a network feature under the same
      // click stays inspectable.
      if (editTarget(store.activeTab) !== "feed") return;
      // Co-located stops from several active feeds can share one click;
      // prefer the current feed's stop so it stays editable under an
      // overlay. Edits target the current feed; others are context only.
      let properties = null;
      if (store.currentFeedId) {
        const own = event.features.find(
          (feature) => feature.properties.feed_id === store.currentFeedId,
        );
        if (own) properties = own.properties;
      }
      if (!properties) properties = event.features[0].properties;
      if (store.currentFeedId && properties.feed_id !== store.currentFeedId) {
        store.status = "that stop belongs to another feed; make it current to edit it";
        event.preventDefault();
        return;
      }
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
    // One handler over both network layers: two separate listeners would
    // both fire where a node sits on its way and race to set the selection.
    map.on("click", ["network-nodes", "network-ways"], (event) => {
      if (event.defaultPrevented) return; // a stop on top already took it
      // In add-node/move-node/draw-way mode a click on a road/node is a
      // placement, not a selection: fall through to the general handler.
      if (
        editTarget(store.activeTab) === "network" &&
        (store.network.mode === "add-node" ||
          store.network.mode === "draw-way" ||
          store.network.movingNode != null)
      ) {
        return;
      }
      if (editTarget(store.activeTab) !== "network") {
        // On the feed tab the network is context. Only an idle select click
        // (no pending move, not a placement mode) is a wrong-domain inspect
        // worth a hint; otherwise it falls through so a stop/shape point —
        // including a stop being moved — can be dropped onto a road.
        if (store.mode === "select" && !store.movingStop) {
          store.status = "switch to the Network tab to inspect the network";
          event.preventDefault();
        }
        return;
      }
      const feature =
        event.features.find((f) => f.properties.osm_type === "node") ||
        event.features[0];
      store.network.selected = { ...feature.properties };
      store.status = "";
      event.preventDefault();
    });

    map.on("click", (event) => {
      if (event.defaultPrevented) return;
      if (editTarget(store.activeTab) === "network") {
        handleNetworkClick(event);
      } else {
        handleMapClick(event);
      }
    });

    try {
      await refreshAll(true);
    } catch (error) {
      store.status = error.message;
    }
    resolveMapReady();
  });
}

export function setNetworkData(nodes, ways) {
  if (!map) return;
  map.getSource("network-ways").setData(ways);
  map.getSource("network-nodes").setData(nodes);
}

// Refetch the network into the map (after an edit or the initial load). One
// combined request keeps nodes and ways from the same editor generation.
export async function fetchNetwork() {
  const { nodes, ways } = await api("GET", "/api/network/features");
  setNetworkData(nodes, ways);
  store.network.nodeCount = nodes.features.length;
  store.network.wayCount = ways.features.length;
}

// Map-click edits to the network (add/move a node), the network-side
// counterpart of handleMapClick; button edits live in actions.js.
function renderNetworkPreview() {
  const source = map && map.getSource("network-preview");
  if (source) {
    source.setData({
      type: "Feature",
      geometry: {
        type: "LineString",
        coordinates: store.network.draw.map((v) => v.coord),
      },
    });
  }
}

export function clearNetworkDraw() {
  store.network.draw = [];
  renderNetworkPreview();
}

async function handleNetworkClick(event) {
  const net = store.network;
  // Acquisition is swapping the network out; ignore edits until it settles,
  // so a click can't act on the old (or mid-swap) features.
  if (net.acquire.downloading) return;
  const { lng, lat } = event.lngLat;
  if (net.mode === "draw-way") {
    // Resolve the click against what is under it: an existing node is reused,
    // an existing way is split into a junction, empty space is a new node.
    const under = map.queryRenderedFeatures(event.point, {
      layers: ["network-nodes", "network-ways"],
    });
    const node = under.find((f) => f.properties.osm_type === "node");
    const way = under.find((f) => f.properties.osm_type === "way");
    let vertex;
    if (node) vertex = { node: node.properties.id };
    else if (way) vertex = { split_way: way.properties.id, lon: lng, lat };
    else vertex = { lon: lng, lat };
    net.draw.push({ vertex, coord: [lng, lat] });
    renderNetworkPreview();
    return;
  }
  try {
    if (net.movingNode != null) {
      await api("PATCH", `/api/network/nodes/${net.movingNode}`, {
        lon: lng,
        lat,
      });
      net.movingNode = null;
      store.status = "";
      await fetchNetwork();
      return;
    }
    if (net.mode === "add-node") {
      await api("POST", "/api/network/nodes", { lon: lng, lat });
      await fetchNetwork();
    }
  } catch (error) {
    store.status = error.message;
  }
}

function setGroupVisible(layers, visible) {
  if (!map) return;
  const value = visible ? "visible" : "none";
  for (const layer of layers) {
    // The layers are created in the async map "load" handler; guard against
    // a toggle that arrives before then.
    if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", value);
  }
}

export function setNetworkVisible(visible) {
  setGroupVisible(["network-ways", "network-nodes"], visible);
}

export function setFeedVisible(visible) {
  setGroupVisible(["stops", "shapes", "stops-highlight", "shapes-highlight"], visible);
}
