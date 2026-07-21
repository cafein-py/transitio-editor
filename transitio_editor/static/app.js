/* transitio editor frontend: a Vue app over the /api endpoints, with
   MapLibre kept imperative behind a small bridge. Vue interpolation
   escapes all feed-derived values. */
"use strict";

// pyrosm tag filters behind the snap-network presets; "streets" uses the
// server's default network (no filter).
const SNAP_FILTERS = {
  streets: null,
  tram: { railway: ["tram"] },
  rail: { railway: ["rail", "light_rail"] },
};

const store = Vue.reactive({
  source: null,
  tables: {},
  snapAvailable: false,
  mode: "select",
  snapOn: true,
  snapNetwork: "streets",
  inspector: null, // { stopId, name }
  movingStop: null,
  tripStops: [], // [{ stopId, offset }]
  tripPicking: false,
  saving: false,
  saveResult: null, // { clean, message }
  routes: [],
  timetableRoute: "",
  routeTrips: [],
  trip: null, // { trip_id, times: [...] }
  shiftSeconds: 600,
  report: null, // last validation report
  reportStale: false, // edits happened after the last validation
  highlightActive: false,
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
let lastStops = null; // latest stops GeoJSON, for highlight fly-to

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
  drawSequence += 1; // invalidate any in-flight snap response
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

async function refreshAll(fit) {
  // Every mutation path funnels through here, so the last validation
  // report is marked stale even for unwrapped actions (map clicks).
  if (store.report) store.reportStale = true;
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

/* ---------------- the Vue application ---------------- */

function wrap(action) {
  return async (...args) => {
    try {
      await action(...args);
      store.status = "";
      if (store.report) store.reportStale = true;
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

    const expandedCode = Vue.ref(null);
    const toggleGroup = (code) => {
      expandedCode.value = expandedCode.value === code ? null : code;
    };

    const noticeGroups = Vue.computed(() => {
      if (!store.report) return [];
      const order = { ERROR: 0, WARNING: 1, INFO: 2 };
      const groups = new Map();
      for (const notice of store.report.notices) {
        let group = groups.get(notice.code);
        if (!group) {
          group = {
            code: notice.code,
            severity: notice.severity,
            count: 0,
            contexts: [],
          };
          groups.set(notice.code, group);
        }
        group.count += 1;
        if (group.contexts.length < 20) {
          group.contexts.push(notice.context || {});
        }
      }
      return [...groups.values()].sort(
        (a, b) =>
          (order[a.severity] ?? 3) - (order[b.severity] ?? 3) ||
          b.count - a.count,
      );
    });

    const describeContext = (context) => {
      const parts = Object.entries(context).map(
        ([key, value]) => `${key}=${value}`,
      );
      return parts.length ? parts.join(", ") : "(no context)";
    };

    const setHighlight = (stopIds, shapeIds) => {
      map.setFilter("stops-highlight", [
        "in",
        ["get", "stop_id"],
        ["literal", stopIds],
      ]);
      map.setFilter("shapes-highlight", [
        "in",
        ["get", "shape_id"],
        ["literal", shapeIds],
      ]);
      store.highlightActive = stopIds.length > 0 || shapeIds.length > 0;
    };

    const clearHighlight = () => setHighlight([], []);

    const highlightContext = (context) => {
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
    };

    const validateFeed = async () => {
      try {
        const body = await api("POST", "/api/validate", {});
        store.report = body.report;
        store.reportStale = false;
        store.status = "";
      } catch (error) {
        store.status = error.message;
      }
    };

    const onTimetableToggle = async (open) => {
      if (!open) return;
      try {
        store.routes = (await api("GET", "/api/routes")).routes;
      } catch (error) {
        store.status = error.message;
      }
    };

    const loadTrips = async () => {
      store.trip = null;
      try {
        const route = encodeURIComponent(store.timetableRoute);
        store.routeTrips = (
          await api("GET", `/api/routes/${route}/trips`)
        ).trips;
      } catch (error) {
        store.status = error.message;
      }
    };

    const loadTrip = async (tripId) => {
      try {
        const body = await api(
          "GET",
          `/api/trips/${encodeURIComponent(tripId)}/times`,
        );
        store.trip = body;
      } catch (error) {
        store.status = error.message;
      }
    };

    const applyTripTimes = wrap(async () => {
      const updates = {};
      for (const row of store.trip.times) {
        updates[row.stop_sequence] = {
          arrival_time: row.arrival_time,
          departure_time: row.departure_time,
        };
      }
      await api(
        "PUT",
        `/api/trips/${encodeURIComponent(store.trip.trip_id)}/times`,
        { times: updates },
      );
      await loadTrip(store.trip.trip_id);
    });

    const deleteTrip = wrap(async () => {
      await api(
        "DELETE",
        `/api/trips/${encodeURIComponent(store.trip.trip_id)}`,
      );
      store.trip = null;
      await loadTrips();
      await refreshAll(false);
    });

    const shiftTrip = wrap(async () => {
      await api(
        "POST",
        `/api/trips/${encodeURIComponent(store.trip.trip_id)}/shift`,
        { seconds: store.shiftSeconds },
      );
      await loadTrip(store.trip.trip_id);
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
        store.report = saved.report;
        store.reportStale = false;
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
      expandedCode,
      noticeGroups,
      toggleGroup,
      describeContext,
      highlightContext,
      clearHighlight,
      validateFeed,
      onTimetableToggle,
      loadTrips,
      loadTrip,
      applyTripTimes,
      deleteTrip,
      shiftTrip,
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
