// Feature actions shared by the sidebar panels. Each mutates the store
// and/or calls the API, then refreshes the map. `wrap` funnels errors to
// the status line and marks the validation report stale.
import { api } from "./api.js";
import * as mapBridge from "./map.js";
import { forms, store } from "./store.js";

export function wrap(action) {
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

export function setMode(mode) {
  store.mode = mode;
  if (mode !== "draw") mapBridge.resetDraw();
  mapBridge.setCursor(mode === "select" ? "" : "crosshair");
}

export function cancelShape() {
  mapBridge.resetDraw();
  setMode("select");
}

export const finishShape = wrap(async () => {
  if (mapBridge.getPreviewCoords().length < 2) {
    throw new Error("draw at least two points first");
  }
  const shapeId = prompt("shape_id?");
  if (!shapeId) return;
  await api("POST", "/api/shapes", {
    shape_id: shapeId,
    points: mapBridge.getPreviewCoords().map(([lon, lat]) => [lat, lon]),
  });
  cancelShape();
  await mapBridge.refreshAll(false);
});

export const updateInspectedStop = wrap(async () => {
  await api("PATCH", `/api/stops/${encodeURIComponent(store.inspector.stopId)}`, {
    stop_name: store.inspector.name,
  });
  await mapBridge.refreshAll(false);
});

export function startMovingStop() {
  store.movingStop = store.inspector.stopId;
  store.status = `click the new location of ${store.movingStop}`;
  mapBridge.setCursor("crosshair");
}

export const submitRoute = wrap(async () => {
  await api("POST", "/api/routes", {
    ...forms.route,
    agency_id: forms.route.agency_id || null,
  });
  forms.route.route_id = "";
  forms.route.route_short_name = "";
  await mapBridge.refreshAll(false);
});

export const submitTrip = wrap(async () => {
  await api("POST", "/api/trips/frequency", {
    ...forms.trip,
    shape_id: forms.trip.shape_id || null,
    stops: store.tripStops.map((entry) => [entry.stopId, entry.offset]),
  });
  store.tripStops.length = 0;
  forms.trip.trip_id = "";
  await mapBridge.refreshAll(false);
});

export const submitAgency = wrap(async () => {
  await api("POST", "/api/agencies", { ...forms.agency });
  await mapBridge.refreshAll(false);
});

export const submitService = wrap(async () => {
  await api("POST", "/api/services", { ...forms.service });
  await mapBridge.refreshAll(false);
});

export async function validateFeed() {
  try {
    const body = await api("POST", "/api/validate", {});
    store.report = body.report;
    store.reportStale = false;
    store.status = "";
  } catch (error) {
    store.status = error.message;
  }
}

export async function onTimetableToggle(open) {
  if (!open) return;
  try {
    store.routes = (await api("GET", "/api/routes")).routes;
  } catch (error) {
    store.status = error.message;
  }
}

export async function loadTrips() {
  store.trip = null;
  try {
    const route = encodeURIComponent(store.timetableRoute);
    store.routeTrips = (await api("GET", `/api/routes/${route}/trips`)).trips;
  } catch (error) {
    store.status = error.message;
  }
}

export async function loadTrip(tripId) {
  try {
    store.trip = await api("GET", `/api/trips/${encodeURIComponent(tripId)}/times`);
  } catch (error) {
    store.status = error.message;
  }
}

export const applyTripTimes = wrap(async () => {
  const updates = {};
  for (const row of store.trip.times) {
    updates[row.stop_sequence] = {
      arrival_time: row.arrival_time,
      departure_time: row.departure_time,
    };
  }
  await api("PUT", `/api/trips/${encodeURIComponent(store.trip.trip_id)}/times`, {
    times: updates,
  });
  await loadTrip(store.trip.trip_id);
});

export const deleteTrip = wrap(async () => {
  await api("DELETE", `/api/trips/${encodeURIComponent(store.trip.trip_id)}`);
  store.trip = null;
  await loadTrips();
  await mapBridge.refreshAll(false);
});

export const shiftTrip = wrap(async () => {
  await api("POST", `/api/trips/${encodeURIComponent(store.trip.trip_id)}/shift`, {
    seconds: store.shiftSeconds,
  });
  await loadTrip(store.trip.trip_id);
});

export async function saveFeed() {
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
    await mapBridge.refreshSummary();
  } catch (error) {
    store.saveResult = { clean: false, message: error.message };
  } finally {
    store.saving = false;
  }
}
