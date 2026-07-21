/* transitio editor frontend: a Vue app over the /api endpoints, with
   MapLibre kept imperative behind a small bridge. Vue interpolation
   escapes all feed-derived values. */
"use strict";

const store = Vue.reactive({
  source: null,
  tables: {},
  snapAvailable: false,
  mode: "select",
  snapOn: true,
  inspector: null, // { stopId, name }
  movingStop: null,
  tripStops: [], // [{ stopId, offset }]
  tripPicking: false,
  saving: false,
  saveResult: null, // { clean, message }
  status: "",
});

const forms = Vue.reactive({
  route: { route_id: "", route_short_name: "", route_type: 3, agency_id: "" },
  trip: {
    route_id: "",
    service_id: "",
    trip_id: "",
    shape_id: "",
    start: "06:00:00",
    end: "22:00:00",
    headway: 600,
  },
  agency: {
    agency_id: "",
    agency_name: "",
    agency_url: "",
    agency_timezone: "",
  },
  service: {
    service_id: "",
    days: "weekdays",
    start_date: "20260101",
    end_date: "20261231",
  },
});

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (error) {
      /* not JSON */
    }
    throw new Error(`${method} ${path}: ${detail}`);
  }
  return response.json();
}

/* ---------------- map bridge (imperative MapLibre) ---------------- */

const map = new maplibregl.Map({
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

let drawnPoints = []; // [lat, lon]
let previewCoords = []; // [lon, lat]
let drawSequence = 0; // discards out-of-order snap responses

function renderPreview() {
  const source = map.getSource("preview");
  if (source) {
    source.setData({
      type: "Feature",
      geometry: { type: "LineString", coordinates: previewCoords },
    });
  }
}

function resetDraw() {
  drawnPoints = [];
  previewCoords = [];
  renderPreview();
}

async function refreshSummary() {
  const summary = await api("GET", "/api/feed");
  store.source = summary.source;
  store.tables = summary.tables;
  store.snapAvailable = Boolean(summary.snapAvailable);
}

async function refreshLayers(fit) {
  const [stops, shapes] = await Promise.all([
    api("GET", "/api/stops"),
    api("GET", "/api/shapes"),
  ]);
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

async function refreshAll(fit) {
  await refreshSummary();
  await refreshLayers(fit);
}

async function handleMapClick(event) {
  const { lng, lat } = event.lngLat;
  try {
    if (store.movingStop) {
      await api(
        "PATCH",
        `/api/stops/${encodeURIComponent(store.movingStop)}`,
        { stop_lat: lat, stop_lon: lng },
      );
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
        const feature = await api("POST", "/api/shapes/snap", {
          waypoints: [...drawnPoints],
        });
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

map.on("load", async () => {
  map.addSource("stops", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource("shapes", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
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
    paint: {
      "line-color": "#c0392b",
      "line-width": 3,
      "line-dasharray": [2, 1],
    },
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

/* ---------------- the Vue application ---------------- */

function wrap(action) {
  return async (...args) => {
    try {
      await action(...args);
      store.status = "";
    } catch (error) {
      store.status = error.message;
    }
  };
}

Vue.createApp({
  setup() {
    const setMode = (mode) => {
      store.mode = mode;
      if (mode !== "draw") resetDraw();
      map.getCanvas().style.cursor = mode === "select" ? "" : "crosshair";
    };

    const cancelShape = () => {
      resetDraw();
      setMode("select");
    };

    const finishShape = wrap(async () => {
      if (previewCoords.length < 2) {
        throw new Error("draw at least two points first");
      }
      const shapeId = prompt("shape_id?");
      if (!shapeId) return;
      await api("POST", "/api/shapes", {
        shape_id: shapeId,
        points: previewCoords.map(([lon, lat]) => [lat, lon]),
      });
      cancelShape();
      await refreshAll(false);
    });

    const updateInspectedStop = wrap(async () => {
      await api(
        "PATCH",
        `/api/stops/${encodeURIComponent(store.inspector.stopId)}`,
        { stop_name: store.inspector.name },
      );
      await refreshAll(false);
    });

    const startMovingStop = () => {
      store.movingStop = store.inspector.stopId;
      store.status = `click the new location of ${store.movingStop}`;
      map.getCanvas().style.cursor = "crosshair";
    };

    const submitRoute = wrap(async () => {
      await api("POST", "/api/routes", {
        ...forms.route,
        agency_id: forms.route.agency_id || null,
      });
      forms.route.route_id = "";
      forms.route.route_short_name = "";
      await refreshAll(false);
    });

    const submitTrip = wrap(async () => {
      await api("POST", "/api/trips/frequency", {
        ...forms.trip,
        shape_id: forms.trip.shape_id || null,
        stops: store.tripStops.map((entry) => [entry.stopId, entry.offset]),
      });
      store.tripStops.length = 0;
      forms.trip.trip_id = "";
      await refreshAll(false);
    });

    const submitAgency = wrap(async () => {
      await api("POST", "/api/agencies", { ...forms.agency });
      await refreshAll(false);
    });

    const submitService = wrap(async () => {
      await api("POST", "/api/services", { ...forms.service });
      await refreshAll(false);
    });

    const saveFeed = async () => {
      store.saving = true;
      store.saveResult = null;
      try {
        const saved = await api("POST", "/api/save", {});
        const counts = saved.report.notices.reduce((acc, notice) => {
          acc[notice.severity] = (acc[notice.severity] || 0) + 1;
          return acc;
        }, {});
        store.saveResult = {
          clean: saved.clean,
          message: saved.clean
            ? "saved — no errors"
            : `saved with ${counts.ERROR || 0} errors, ` +
              `${counts.WARNING || 0} warnings`,
        };
        await refreshSummary();
      } catch (error) {
        store.saveResult = { clean: false, message: error.message };
      } finally {
        store.saving = false;
      }
    };

    return {
      store,
      forms,
      setMode,
      cancelShape,
      finishShape,
      updateInspectedStop,
      startMovingStop,
      submitRoute,
      submitTrip,
      submitAgency,
      submitService,
      saveFeed,
    };
  },
}).mount("#sidebar");
