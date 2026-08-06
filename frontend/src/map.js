// The imperative MapLibre bridge: owns the map, the draw-interaction
// state, layer refreshes, click handling and highlighting. Vue
// components call these functions; the map itself is never reactive.
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import { api } from "./api.js";
import { BASEMAPS, basemapLayerId } from "./basemaps.js";
import { setNetworkEntities, setStopsData } from "./entities.js";
import {
  initStreetsHandles,
  initStreetsLayers,
  refreshStreets,
  selectWay,
  setStreetsVisible,
} from "./map/streets.js";
import { logServerEdit } from "./session.js";
import { SNAP_FILTERS, store } from "./store.js";
import { wayHighway } from "./streets.js";
import { cropShapeFromRing } from "./catalogue.js";
import { editTarget } from "./network.js";
import {
  MODES,
  feedColorExpression,
  modeColorExpression,
  modeFilterExpression,
  presentModeCodes,
} from "./modes.js";

let map = null;
// Selection-halo styling: amber reads over the basemap and clashes with no
// mode or feed color; the false filter means "nothing selected".
const SELECT_COLOR = "#ffd60a";
const NO_SELECTION = ["boolean", false];
// The shapes' selection and report-highlight layers must respect the mode
// filter too, or a hidden mode's shape stays visible through its overlay.
let shapesModeFilter = null;
let selectedShapeFilter = NO_SELECTION;
let highlightShapesFilter = ["in", ["get", "shape_id"], ["literal", []]];

function withModeFilter(filter) {
  return shapesModeFilter ? ["all", shapesModeFilter, filter] : filter;
}
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

let previewSettled = Promise.resolve(); // the latest draw/snap update

// The preview after any in-flight snap lands — what Finish must save.
export async function previewCoordsSettled() {
  try {
    await previewSettled;
  } catch (error) {
    /* the click handler already reported the snap failure */
  }
  return previewCoords;
}

function syncBasemapLayers() {
  if (!map || !map.getLayer(basemapLayerId(store.basemap))) return;
  for (const basemap of BASEMAPS) {
    map.setLayoutProperty(
      basemapLayerId(basemap.key),
      "visibility",
      basemap.key === store.basemap ? "visible" : "none",
    );
  }
}

export function setBasemap(key) {
  if (!BASEMAPS.some((basemap) => basemap.key === key)) return;
  store.basemap = key;
  // Before the style has built its layers this is a no-op; the load
  // handler re-syncs, so an early click is not silently lost.
  syncBasemapLayers();
}

export function setCursor(kind) {
  if (map) map.getCanvas().style.cursor = kind;
}

// The current viewport as [minx, miny, maxx, maxy] for a bbox feed
// search. A viewport that crosses the antimeridian or spans the globe
// can't be one WGS84 bbox, so skip the bounds filter rather than send a
// clamped (wrong) one that silently drops the wrapped half.
// MapLibre reports unwrapped longitudes on rendered world copies (e.g. 384°);
// normalize to [-180, 180] so the backend's range check accepts them.
function wrapLng(lng) {
  return ((((lng + 180) % 360) + 360) % 360) - 180;
}

const clampLat = (value) => Math.max(-90, Math.min(90, value));

export function getViewportBbox() {
  if (!map) return null;
  const bounds = map.getBounds();
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();
  if (ne.lng - sw.lng >= 360) return null; // whole world: not a usable bbox
  const minx = wrapLng(sw.lng);
  const maxx = wrapLng(ne.lng);
  if (minx >= maxx) return null; // straddles the antimeridian: not one bbox
  return [minx, clampLat(sw.lat), maxx, clampLat(ne.lat)];
}

export function getCamera() {
  if (!map) return null;
  const center = map.getCenter();
  return { center: [center.lng, center.lat], zoom: map.getZoom() };
}

export function jumpTo(center, zoom) {
  if (map) map.jumpTo({ center, zoom });
}

// Fly close to a point (a double-clicked list row); never zooms OUT past
// a view the user already narrowed further.
export function flyToPoint(center, zoom = 16) {
  if (map) map.flyTo({ center, zoom: Math.max(map.getZoom(), zoom) });
}

export function fitToStops() {
  if (!map || !lastStops || !lastStops.features.length) return;
  const bounds = new maplibregl.LngLatBounds();
  for (const feature of lastStops.features) {
    bounds.extend(feature.geometry.coordinates);
  }
  map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
}

// Fit the map to a set of shapes of one feed (a route's geometry, a
// shape-only validation notice).
let lastShapes = null;

export function fitShapes(shapeIds, feedId) {
  if (!map || !lastShapes || !shapeIds || !shapeIds.length) return false;
  const wanted = new Set(shapeIds);
  const bounds = new maplibregl.LngLatBounds();
  let found = false;
  for (const feature of lastShapes.features) {
    const properties = feature.properties;
    if (!wanted.has(properties.shape_id)) continue;
    if (feedId && properties.feed_id !== feedId) continue;
    const coords =
      feature.geometry.type === "MultiLineString"
        ? feature.geometry.coordinates.flat()
        : feature.geometry.coordinates;
    for (const coord of coords) bounds.extend(coord);
    found = true;
  }
  if (!found) return false;
  map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
  return true;
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

let aoiStart = null; // the first corner of a rectangle being dragged

function aoiBox(a, b) {
  const minx = Math.min(wrapLng(a.lng), wrapLng(b.lng));
  const maxx = Math.max(wrapLng(a.lng), wrapLng(b.lng));
  // An honest bbox has wrapped width equal to the drag's true (unwrapped)
  // width; any difference means the drag crossed a wrap boundary and can't be
  // one [minx, maxx] bbox — reject it (covers both wider and narrower cases).
  if (Math.abs(maxx - minx - Math.abs(a.lng - b.lng)) > 1e-9) return null;
  return [
    minx,
    clampLat(Math.min(a.lat, b.lat)),
    maxx,
    clampLat(Math.max(a.lat, b.lat)),
  ];
}

function renderAoi(bbox) {
  const source = map && map.getSource("aoi");
  if (!source) return;
  if (!bbox) {
    source.setData({ type: "FeatureCollection", features: [] });
    return;
  }
  const [minx, miny, maxx, maxy] = bbox;
  source.setData({
    type: "Feature",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [minx, miny],
          [maxx, miny],
          [maxx, maxy],
          [minx, maxy],
          [minx, miny],
        ],
      ],
    },
  });
}

export function startAoiDraw() {
  if (!map) return;
  store.aoiDrawing = true;
  map.dragPan.disable(); // so the drag draws a box instead of panning
  setCursor("crosshair");
}

export function clearAoi() {
  store.aoi = null;
  store.aoiDrawing = false;
  aoiStart = null;
  if (map) {
    map.dragPan.enable();
    setCursor("");
  }
  renderAoi(null);
}

// The crop area being drawn or finished: a box drag or a click-built
// polygon. Kept apart from store.aoi (the search box) so the two tools
// cannot overwrite each other.
let cropVertices = []; // [lng, lat] of a polygon under construction
let cropBoxStart = null;
// A box drag ends with a click event; it must not reach select or an
// armed add-stop/shape mode — including the layer handlers, which run
// before the general one.
let swallowClickAfterCrop = false;

function croppingClick() {
  return Boolean(store.cropDrawing) || swallowClickAfterCrop;
}

function cropFeatures(ring, closed) {
  const features = ring.map((coord) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: coord },
    properties: {},
  }));
  if (ring.length >= 2) {
    features.push({
      type: "Feature",
      geometry: closed
        ? { type: "Polygon", coordinates: [[...ring, ring[0]]] }
        : { type: "LineString", coordinates: ring },
      properties: {},
    });
  }
  return { type: "FeatureCollection", features };
}

function renderCrop(ring, closed) {
  const source = map && map.getSource("crop");
  if (!source) return;
  source.setData(
    ring && ring.length
      ? cropFeatures(ring, closed)
      : { type: "FeatureCollection", features: [] },
  );
}

function boxRing(box) {
  const [minx, miny, maxx, maxy] = box;
  return [
    [minx, miny],
    [maxx, miny],
    [maxx, maxy],
    [minx, maxy],
  ];
}

// Finished shapes are stored as the GeoJSON the crop endpoint takes.
function finishCropPolygon(ring) {
  const { shape, error } = cropShapeFromRing(
    ring.map(([lng, lat]) => [lng, clampLat(lat)]),
  );
  if (error) {
    store.status = error;
    cancelCropDraw();
    return;
  }
  store.cropShape = shape;
  store.cropDrawing = null;
  renderCrop(ring, true);
}

export function startCropDraw(kind) {
  if (!map) return;
  cropVertices = [];
  cropBoxStart = null;
  store.cropShape = null;
  store.cropDrawing = kind; // "box" | "polygon"
  if (kind === "box") map.dragPan.disable();
  setCursor("crosshair");
  renderCrop([], false);
}

export function cancelCropDraw() {
  cropVertices = [];
  cropBoxStart = null;
  store.cropDrawing = null;
  store.cropShape = null;
  if (map) {
    map.dragPan.enable();
    setCursor("");
  }
  renderCrop([], false);
}

// Enough vertices to bound an area; a closing click on the first vertex
// or Enter finishes the polygon.
export function closeCropPolygon() {
  if (store.cropDrawing !== "polygon" || cropVertices.length < 3) return false;
  const ring = cropVertices;
  cropVertices = [];
  if (map) {
    map.dragPan.enable();
    setCursor("");
  }
  finishCropPolygon(ring);
  return true;
}

function addCropVertex(lngLat) {
  const point = [lngLat.lng, lngLat.lat];
  if (cropVertices.length >= 3) {
    const [firstLng, firstLat] = cropVertices[0];
    const start = map.project({ lng: firstLng, lat: firstLat });
    const here = map.project(lngLat);
    if (Math.hypot(start.x - here.x, start.y - here.y) < 12) {
      closeCropPolygon(); // clicked back on the first vertex
      return;
    }
  }
  cropVertices = [...cropVertices, point];
  renderCrop(cropVertices, false);
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

let summarySeq = 0; // a pre-restore summary must not paint over a newer one

async function refreshSummary() {
  const seq = ++summarySeq;
  // The summary and the catalogue are two samples of the same backend
  // state; a feed switch between them would blend two feeds' fields.
  // Retry once on mismatch; if still unstable, discard the per-feed
  // summary fields rather than show one feed's tables under another's id.
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const summary = await api("GET", "/api/feed");
    if (seq !== summarySeq) return;
    let catalogue = null;
    try {
      catalogue = await api("GET", "/api/catalogue");
    } catch (error) {
      /* catalogue refresh is best-effort */
    }
    if (seq !== summarySeq) return;
    const summaryFeed = summary.currentFeedId ?? null;
    if (catalogue && catalogue.current !== summaryFeed) {
      if (attempt === 0) continue; // resample: the two disagreed
      // still unstable: trust the catalogue's current feed, drop the
      // summary-derived per-feed fields instead of misattributing them
      store.catalogue = catalogue.feeds;
      store.currentFeedId = catalogue.current;
      store.source = null;
      store.tables = {};
      store.undoLabel = null;
      store.redoLabel = null;
      store.snapAvailable = Boolean(summary.snapAvailable);
      return;
    }
    store.source = summary.source;
    store.tables = summary.tables;
    store.currentFeedId = summaryFeed;
    store.snapAvailable = Boolean(summary.snapAvailable);
    store.undoLabel = summary.undo ?? null;
    store.redoLabel = summary.redo ?? null;
    if (catalogue) {
      store.catalogue = catalogue.feeds;
      store.currentFeedId = catalogue.current;
    } else {
      // keep the current feed's catalogue counts in step with its
      // table sizes when the catalogue re-fetch was unavailable
      const entry = store.catalogue.find(
        (f) => f.feed_id === store.currentFeedId,
      );
      if (entry) entry.tables = summary.tables;
    }
    return;
  }
}
export { refreshSummary };

let refreshSeq = 0; // an older, slower refresh must not overwrite a newer one

async function refreshLayers(fit) {
  const seq = ++refreshSeq;
  const [stops, shapes] = await Promise.all([
    api("GET", "/api/stops"),
    api("GET", "/api/shapes"),
  ]);
  if (seq !== refreshSeq) return;
  lastStops = stops;
  lastShapes = shapes;
  map.getSource("stops").setData(stops);
  map.getSource("shapes").setData(shapes);
  setStopsData(stops.features);
  store.dataVersion += 1; // panel lists recompute
  // The legend offers only modes the loaded feeds actually contain.
  store.presentModes = presentModeCodes(shapes.features);
  if (fit && stops.features.length) {
    const bounds = new maplibregl.LngLatBounds();
    for (const feature of stops.features) {
      bounds.extend(feature.geometry.coordinates);
    }
    map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
  }
}

export async function refreshAll(fit) {
  // Pure visibility refreshes route through here too, so staleness is
  // NOT flagged here — the session log marks it for real mutations.
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
  highlightShapesFilter = scoped("shape_id", shapeIds);
  map.setFilter("shapes-highlight", withModeFilter(highlightShapesFilter));
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
      return;
    }
  }
  // No stop to fly to (a shape-only notice): fit the highlighted shapes
  // so the chip always takes the user to what it highlighted.
  if (shapeIds.length) fitShapes(shapeIds, store.currentFeedId);
}

async function handleMapClick(event) {
  // Map clicks mutate the feed (move/add stop, draw); inert while the OSM
  // network is the edit target.
  if (editTarget(store.activePanel) !== "feed") return;
  const feedId = store.currentFeedId; // pinned before any await
  const { lng, lat } = event.lngLat;
  try {
    if (store.movingStop) {
      const movingStop = store.movingStop;
      await api("PATCH", `/api/stops/${encodeURIComponent(movingStop)}`, {
        stop_lat: lat,
        stop_lon: lng,
      });
      logServerEdit("Stop moved", movingStop, feedId);
      store.movingStop = null;
      store.status = "";
      store.dirty = true;
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
      logServerEdit("Stop added", stopId, feedId);
      store.dirty = true;
      await refreshAll(false);
      return;
    }
    if (store.mode === "draw") {
      drawnPoints.push([lat, lng]);
      // Tracked as a promise so Finish can wait for the newest geometry
      // instead of saving a preview that predates a pending snap.
      const update = (async () => {
        if (store.snapAvailable && store.snapOn && drawnPoints.length >= 2) {
          const sequence = ++drawSequence;
          const request = { waypoints: [...drawnPoints] };
          const filter = SNAP_FILTERS[store.snapNetwork];
          if (filter) request.custom_filter = filter;
          try {
            const feature = await api("POST", "/api/shapes/snap", request);
            if (sequence !== drawSequence) return; // superseded by a newer click
            previewCoords = feature.geometry.coordinates;
          } catch (error) {
            if (sequence !== drawSequence) return;
            // A failed snap must not leave the preview missing the
            // newest point — fall back to the raw polyline and say so.
            previewCoords = drawnPoints.map(([a, b]) => [b, a]);
            store.status = `snapping failed — using straight lines (${error.message})`;
          }
        } else {
          previewCoords = drawnPoints.map(([a, b]) => [b, a]);
        }
        renderPreview();
      })();
      previewSettled = update;
      await update;
    }
  } catch (error) {
    store.status = error.message;
  }
}

export function createMap() {
  map = new maplibregl.Map({
    container: "map",
    // Every basemap is a raster layer in the style; switching toggles
    // visibility, so the overlays above are never rebuilt (a setStyle
    // call would drop every custom source and layer).
    style: {
      version: 8,
      sources: Object.fromEntries(
        BASEMAPS.map((basemap) => [
          basemapLayerId(basemap.key),
          {
            type: "raster",
            tiles: basemap.tiles,
            tileSize: 256,
            attribution: basemap.attribution,
          },
        ]),
      ),
      layers: BASEMAPS.map((basemap) => ({
        id: basemapLayerId(basemap.key),
        type: "raster",
        source: basemapLayerId(basemap.key),
        layout: {
          visibility: basemap.key === store.basemap ? "visible" : "none",
        },
      })),
    },
    center: [24.94, 60.17],
    zoom: 11,
  });
  // Bottom-right: the floating stop card owns the map's top-right corner.
  map.addControl(new maplibregl.NavigationControl(), "bottom-right");
  // The "In map view" list scope recomputes off this counter.
  map.on("moveend", () => {
    store.mapMoved += 1;
  });

  map.on("load", async () => {
    syncBasemapLayers(); // a choice made before the style built lands now
    for (const id of ["stops", "shapes", "network-ways"]) {
      map.addSource(id, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
    }
    map.addSource("preview", {
      type: "geojson",
      data: {
        type: "Feature",
        geometry: { type: "LineString", coordinates: [] },
      },
    });
    map.addSource("aoi", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    // The drawn area sits at the bottom of the overlays so it never hides a
    // feature; a translucent fill plus a dashed outline.
    map.addLayer({
      id: "aoi-fill",
      type: "fill",
      source: "aoi",
      paint: { "fill-color": "#2d7", "fill-opacity": 0.12 },
    });
    map.addLayer({
      id: "aoi-outline",
      type: "line",
      source: "aoi",
      paint: {
        "line-color": "#1a9",
        "line-width": 2,
        "line-dasharray": [2, 1],
      },
    });
    map.addSource("crop", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    // The crop area reads as an edit, not a search: amber, above the AOI.
    map.addLayer({
      id: "crop-fill",
      type: "fill",
      source: "crop",
      paint: { "fill-color": "#f0a", "fill-opacity": 0.1 },
    });
    map.addLayer({
      id: "crop-outline",
      type: "line",
      source: "crop",
      paint: { "line-color": "#c07", "line-width": 2 },
    });
    map.addLayer({
      id: "crop-vertices",
      type: "circle",
      source: "crop",
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-radius": 4,
        "circle-color": "#fff",
        "circle-stroke-color": "#c07",
        "circle-stroke-width": 2,
      },
    });
    // The street network under the GTFS layers, styled by highway class
    // (the design's colour/width/dash scale lives in map/streets.js).
    initStreetsLayers(map, { refreshNetwork: fetchNetwork });
    // A white casing under the route lines separates them from the busy
    // basemap (and from each other), keeping even light hues readable.
    map.addLayer({
      id: "shapes-casing",
      type: "line",
      source: "shapes",
      paint: {
        "line-color": "#ffffff",
        "line-width": 5.5,
        "line-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "shapes",
      type: "line",
      source: "shapes",
      paint: {
        // colored by transport mode by default; switchable to feed colors
        "line-color": modeColorExpression(),
        "line-width": 3,
        "line-opacity": 1,
      },
    });
    map.addLayer({
      id: "preview",
      type: "line",
      source: "preview",
      paint: {
        "line-color": "#c0392b",
        "line-width": 3,
        "line-dasharray": [2, 1],
      },
    });
    map.addLayer({
      id: "shapes-highlight",
      type: "line",
      source: "shapes",
      filter: ["in", ["get", "shape_id"], ["literal", []]],
      paint: { "line-color": "#d81b60", "line-width": 6, "line-opacity": 0.6 },
    });
    // Stop size follows the zoom, so a whole-region feed reads as dots
    // instead of covering the map; street zooms keep the clickable size.
    // The low end stays tiny: a dense city feed at city scale must not
    // blanket the basemap.
    const stopRadius = (scale) => [
      "interpolate",
      ["linear"],
      ["zoom"],
      7,
      0.8 * scale,
      10,
      1.6 * scale,
      12,
      2.4 * scale,
      14,
      4.5 * scale,
      16,
      7 * scale,
      18,
      9 * scale,
    ];
    map.addLayer({
      id: "stops",
      type: "circle",
      source: "stops",
      paint: {
        "circle-radius": stopRadius(1),
        "circle-color": ["coalesce", ["get", "feed_color"], "#e67e22"],
        "circle-stroke-color": "#fff",
        "circle-stroke-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          7,
          0.3,
          12,
          0.7,
          14,
          1.2,
          16,
          1.8,
        ],
      },
    });
    map.addLayer({
      id: "stops-highlight",
      type: "circle",
      source: "stops",
      filter: ["in", ["get", "stop_id"], ["literal", []]],
      paint: {
        "circle-radius": stopRadius(1.7),
        "circle-color": "rgba(216, 27, 96, 0.35)",
        "circle-stroke-color": "#d81b60",
        "circle-stroke-width": 2,
      },
    });

    // Selection halos: an amber underlay marks the selected feature, in
    // every domain (inserted beneath its feature layer via beforeId).
    // Each width leaves an amber band about twice the feature's own
    // half-width visible on either side, so a selection reads at a glance.
    map.addLayer(
      {
        id: "shapes-selected",
        type: "line",
        source: "shapes",
        filter: NO_SELECTION,
        paint: {
          "line-color": SELECT_COLOR,
          "line-width": 15,
          "line-opacity": 0.85,
        },
      },
      "shapes",
    );
    // The stop halo sits ABOVE the stops layer: an underlay would be
    // buried by neighbouring stops in dense areas. The selected stop is
    // then redrawn enlarged on top of its own halo.
    map.addLayer({
      id: "stops-selected",
      type: "circle",
      source: "stops",
      filter: NO_SELECTION,
      paint: {
        "circle-radius": stopRadius(2.6),
        "circle-color": SELECT_COLOR,
        "circle-opacity": 0.9,
      },
    });
    map.addLayer({
      id: "stops-selected-marker",
      type: "circle",
      source: "stops",
      filter: NO_SELECTION,
      paint: {
        "circle-radius": stopRadius(1.45),
        "circle-color": ["coalesce", ["get", "feed_color"], "#e67e22"],
        "circle-stroke-color": "#fff",
        "circle-stroke-width": [
          "interpolate",
          ["linear"],
          ["zoom"],
          7,
          0.8,
          13,
          2,
        ],
      },
    });
    // Vertex handles above everything, including the GTFS layers.
    initStreetsHandles(map);

    map.on("click", "stops", (event) => {
      if (store.aoiDrawing || croppingClick()) return; // a drawing gesture
      if (store.movingStop || store.mode !== "select") return;
      // While editing the OSM network, stops are context: ignore them
      // silently (no preventDefault) so a network feature under the same
      // click stays inspectable.
      if (editTarget(store.activePanel) !== "feed") return;
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
      if (
        store.editMode &&
        store.currentFeedId &&
        properties.feed_id !== store.currentFeedId
      ) {
        // Editing targets the current feed; viewing may select any feed.
        store.status =
          "that stop belongs to another feed; make it current to edit it";
        event.preventDefault();
        return;
      }
      if (store.tripPicking && store.editMode) {
        store.tripStops.push({
          stopId: properties.stop_id,
          offset: store.tripStops.length * 120,
        });
      } else {
        store.inspector = {
          stopId: properties.stop_id,
          name: properties.stop_name || "",
          feedId: properties.feed_id || null,
        };
        // Selection state only: panels react to it in place — a map
        // click never navigates away from the panel in use.
        store.selectedStopId = {
          stopId: properties.stop_id,
          feedId: properties.feed_id || null,
        };
        setSelectedStop(properties);
      }
      event.preventDefault();
    });
    // Attribute cards: hovering a feature while viewing shows its key
    // attributes; clicking a shape pins the card. Values enter the DOM via
    // textContent only.
    const hoverPopup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      className: "attr-popup",
      maxWidth: "320px",
    });
    const pinnedPopup = new maplibregl.Popup({
      closeButton: true,
      className: "attr-popup",
      maxWidth: "320px",
    });

    function attributeCard(title, properties) {
      const wrap = document.createElement("div");
      const head = document.createElement("div");
      head.className = "attr-title";
      head.textContent = title;
      wrap.appendChild(head);
      const table = document.createElement("table");
      const skip = new Set(["feed_color"]);
      let rows = 0;
      for (const [key, value] of Object.entries(properties)) {
        if (
          skip.has(key) ||
          value === null ||
          value === undefined ||
          value === ""
        )
          continue;
        if (rows >= 8) break;
        const tr = document.createElement("tr");
        const th = document.createElement("th");
        th.textContent = key;
        const td = document.createElement("td");
        td.textContent = String(value);
        tr.append(th, td);
        table.appendChild(tr);
        rows += 1;
      }
      wrap.appendChild(table);
      return wrap;
    }

    function featureCard(feature, kind) {
      const properties = { ...feature.properties };
      let title;
      if (kind === "stop") {
        title = `stop ${properties.stop_id ?? ""}`;
      } else {
        title = `shape ${properties.shape_id ?? ""}`;
        const mode = MODES.find(
          (entry) => entry.code === properties.route_type,
        );
        if (mode) {
          properties.mode = mode.label;
          delete properties.route_type;
        }
      }
      return attributeCard(title, properties);
    }

    for (const [layer, kind] of [
      ["stops", "stop"],
      ["shapes", "shape"],
    ]) {
      map.on("mousemove", layer, (event) => {
        if (editTarget(store.activePanel) !== "feed" || store.editMode) return;
        hoverPopup
          .setLngLat(event.lngLat)
          .setDOMContent(featureCard(event.features[0], kind))
          .addTo(map);
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        hoverPopup.remove();
        if (editTarget(store.activePanel) === "feed" && !store.editMode) {
          setCursor("");
        }
      });
    }

    // Shapes are selectable with editing on or off: a click pins their card
    // and halos the line; closing the card clears the halo.
    pinnedPopup.on("close", () => setSelectedShape(null));
    map.on("click", "shapes", (event) => {
      if (event.defaultPrevented || store.aoiDrawing || croppingClick()) return;
      if (editTarget(store.activePanel) !== "feed") return;
      if (store.mode !== "select" || store.movingStop) return;
      hoverPopup.remove();
      setSelectedShape(event.features[0].properties);
      pinnedPopup
        .setLngLat(event.lngLat)
        .setDOMContent(featureCard(event.features[0], "shape"))
        .addTo(map);
      event.preventDefault();
    });

    map.on("click", (event) => {
      if (swallowClickAfterCrop) {
        swallowClickAfterCrop = false; // the tail of a box drag
        return;
      }
      if (store.cropDrawing === "polygon") {
        addCropVertex(event.lngLat); // building the crop area, not editing
        return;
      }
      if (event.defaultPrevented || store.aoiDrawing || croppingClick()) return;
      if (editTarget(store.activePanel) === "network") {
        // An empty streets click deselects the way (way clicks arrive
        // default-prevented from the class-layer handler).
        selectWay(null);
        return;
      }
      if (store.editMode) {
        // Feed mutations only with the editing switch on: an armed mode
        // (add stop, draw) must not fire while just viewing.
        handleMapClick(event);
      }
      // A click on empty map in select mode deselects the stop (feature
      // clicks never reach here — their handlers preventDefault above).
      if (store.mode === "select" && !store.movingStop && !store.tripPicking) {
        store.inspector = null;
        store.selectedStopId = null;
        setSelectedStop(null);
      }
    });

    // Enter finishes a polygon, Escape abandons the whole drawing.
    window.addEventListener("keydown", (event) => {
      if (!store.cropDrawing) return;
      if (event.key === "Enter") closeCropPolygon();
      else if (event.key === "Escape") cancelCropDraw();
    });

    // Crop-area drawing: a box drag, or clicks building a polygon.
    map.on("mousedown", (event) => {
      if (store.cropDrawing !== "box") return;
      cropBoxStart = event.lngLat;
      event.preventDefault();
    });
    map.on("mousemove", (event) => {
      if (store.cropDrawing !== "box" || !cropBoxStart) return;
      const box = aoiBox(cropBoxStart, event.lngLat);
      if (box) renderCrop(boxRing(box), true);
    });
    map.on("mouseup", (event) => {
      if (store.cropDrawing !== "box" || !cropBoxStart) return;
      const box = aoiBox(cropBoxStart, event.lngLat);
      cropBoxStart = null;
      map.dragPan.enable();
      setCursor("");
      // MapLibre fires the click for a within-tolerance gesture in this
      // same task; clearing on the next tick swallows exactly that one.
      swallowClickAfterCrop = true;
      setTimeout(() => {
        swallowClickAfterCrop = false;
      }, 0);
      if (!box || box[2] - box[0] < 1e-9 || box[3] - box[1] < 1e-9) {
        cancelCropDraw(); // a click, not a box
      } else {
        finishCropPolygon(boxRing(box));
      }
    });

    // Rectangle-draw for an area of interest (dragPan is off while drawing).
    map.on("mousedown", (event) => {
      if (!store.aoiDrawing) return;
      aoiStart = event.lngLat;
      event.preventDefault();
    });
    map.on("mousemove", (event) => {
      if (!store.aoiDrawing || !aoiStart) return;
      renderAoi(aoiBox(aoiStart, event.lngLat));
    });
    map.on("mouseup", (event) => {
      if (!store.aoiDrawing || !aoiStart) return;
      const box = aoiBox(aoiStart, event.lngLat);
      aoiStart = null;
      map.dragPan.enable();
      setCursor("");
      // A zero-size or unrepresentable (antimeridian) box is not a selection.
      if (!box || box[2] - box[0] < 1e-9 || box[3] - box[1] < 1e-9) {
        store.aoi = null;
        renderAoi(null);
      } else {
        store.aoi = box;
        renderAoi(box);
      }
      // Stay in drawing state through the click MapLibre fires for a
      // within-tolerance gesture, so that click can't leak to select/add.
      setTimeout(() => {
        store.aoiDrawing = false;
      }, 0);
    });

    // Releasing the drag outside the canvas never reaches the map's mouseup;
    // a window-level release then cancels the draw so it can't get stuck (the
    // map handlers null their start point first, so an in-canvas release
    // no-ops here). Covers both the AOI box and the crop box.
    window.addEventListener("mouseup", () => {
      if (store.aoiDrawing && aoiStart) {
        aoiStart = null;
        store.aoiDrawing = false;
        map.dragPan.enable();
        setCursor("");
        renderAoi(store.aoi); // discard the in-progress box, keep the prior one
      }
      if (store.cropDrawing === "box" && cropBoxStart) {
        cropBoxStart = null;
        cancelCropDraw(); // restores dragPan/cursor, clears the drawing
      }
    });

    // Re-apply legend state chosen before the async load finished, so an
    // early color-by switch, mode/visibility toggle isn't lost.
    setShapeColorBy(store.shapeColorBy);
    setHiddenModes([...store.hiddenModes]);
    setFeedVisible(store.feedVisible); // also composes the stops toggle

    try {
      await refreshAll(true);
    } catch (error) {
      store.status = error.message;
    }
    resolveMapReady();
  });
}

export function setNetworkData(nodes, ways) {
  if (!map || !map.getSource("network-ways")) return; // style not built yet
  // The class layers filter on the promoted `highway` property; the JS
  // classifiers also read the tags dict. Promote tags-only values here
  // so the map and the list/counts classify identically.
  for (const feature of ways.features || []) {
    const properties = feature.properties;
    if (properties && properties.highway == null) {
      const value = wayHighway(properties);
      if (value != null) properties.highway = value;
    }
  }
  map.getSource("network-ways").setData(ways);
  setNetworkEntities(nodes, ways);
  store.networkVersion += 1; // the Streets panel lists recompute
  refreshStreets(); // selection card + vertex handles follow the data
}

// Refetch the network into the map (after an edit or the initial load). One
// combined request keeps nodes and ways from the same editor generation;
// the sequence guard keeps a slow fetch from repainting a network that a
// session restore has since replaced.
let networkSeq = 0;

export function invalidateNetwork() {
  networkSeq += 1;
}

export async function fetchNetwork() {
  const seq = ++networkSeq;
  const { nodes, ways } = await api("GET", "/api/network/features");
  if (seq !== networkSeq) return false; // stale: a restore intervened
  setNetworkData(nodes, ways);
  store.network.nodeCount = nodes.features.length;
  store.network.wayCount = ways.features.length;
  return true;
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

// Street-network visibility routes through the streets module (it knows
// the per-class hidden set).
export function setNetworkVisible(visible) {
  setStreetsVisible(visible);
}

export function setFeedVisible(visible) {
  setGroupVisible(
    ["shapes", "shapes-casing", "shapes-highlight", "shapes-selected"],
    visible,
  );
  // Stops track both toggles: the feed group and the stops switch.
  setGroupVisible(
    ["stops", "stops-highlight", "stops-selected", "stops-selected-marker"],
    visible && store.stopsVisible,
  );
}

export function setStopsVisible(visible) {
  setGroupVisible(
    ["stops", "stops-highlight", "stops-selected", "stops-selected-marker"],
    store.feedVisible && visible,
  );
}

export function setSelectedStop(properties) {
  if (!map || !map.getLayer("stops-selected")) return;
  const filter = properties
    ? [
        "all",
        ["==", ["get", "stop_id"], properties.stop_id],
        ["==", ["get", "feed_id"], properties.feed_id],
      ]
    : NO_SELECTION;
  map.setFilter("stops-selected", filter);
  map.setFilter("stops-selected-marker", filter);
}

export function setSelectedShape(properties) {
  setSelectedShapes(
    properties ? [properties.shape_id] : [],
    properties ? properties.feed_id : null,
  );
}

// The amber halo over one or many shapes (a route's geometry is all the
// shapes its trips reference).
export function setSelectedShapes(shapeIds, feedId) {
  if (!map || !map.getLayer("shapes-selected")) return;
  selectedShapeFilter = shapeIds && shapeIds.length
    ? [
        "all",
        ["in", ["get", "shape_id"], ["literal", [...shapeIds]]],
        ...(feedId ? [["==", ["get", "feed_id"], feedId]] : []),
      ]
    : NO_SELECTION;
  map.setFilter("shapes-selected", withModeFilter(selectedShapeFilter));
}

// The Trips route focus: the picked route's shapes stay bright, every
// other shape drops to opacity .28.
export function setRouteFocus(shapeIds, feedId) {
  if (!map || !map.getLayer("shapes")) return;
  if (!shapeIds || !shapeIds.length) {
    map.setPaintProperty("shapes", "line-opacity", 1);
    map.setPaintProperty("shapes-casing", "line-opacity", 0.9);
    return;
  }
  const inFocus = [
    "all",
    ["in", ["get", "shape_id"], ["literal", [...shapeIds]]],
    ...(feedId ? [["==", ["get", "feed_id"], feedId]] : []),
  ];
  map.setPaintProperty("shapes", "line-opacity", ["case", inFocus, 1, 0.28]);
  map.setPaintProperty(
    "shapes-casing",
    "line-opacity",
    ["case", inFocus, 0.9, 0.25],
  );
}

export function clearFeedSelection() {
  setSelectedStop(null);
  setSelectedShape(null);
}

export function setShapeColorBy(colorBy) {
  if (!map || !map.getLayer("shapes")) return;
  map.setPaintProperty(
    "shapes",
    "line-color",
    colorBy === "feed" ? feedColorExpression() : modeColorExpression(),
  );
}

export function setHiddenModes(hiddenCodes) {
  if (!map || !map.getLayer("shapes")) return;
  shapesModeFilter = modeFilterExpression(hiddenCodes);
  map.setFilter("shapes", shapesModeFilter);
  map.setFilter("shapes-casing", shapesModeFilter); // the casing mirrors its line
  // Overlays follow: a hidden mode's shape must not shine through its
  // selection halo or report highlight.
  map.setFilter("shapes-selected", withModeFilter(selectedShapeFilter));
  map.setFilter("shapes-highlight", withModeFilter(highlightShapesFilter));
}
