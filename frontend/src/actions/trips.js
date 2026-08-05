// Trips-panel actions: the picked route's trips and timetable, frequency
// generation, single-trip creation with map stop picking, and the
// stop-time edits. New trips copy their stop pattern from one of the
// route's existing trips when no stops are picked (there is no endpoint
// serving a route's canonical stop sequence).
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { logServerEdit, sessionUndo } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";
import { offsetsFromTimes, toSeconds } from "../trips.js";

let tripsSeq = 0;

export async function loadRouteTrips() {
  const routeId = store.timetableRoute;
  if (!routeId) return;
  const seq = ++tripsSeq;
  try {
    const body = await api(
      "GET",
      `/api/routes/${encodeURIComponent(routeId)}/trips`,
    );
    if (seq !== tripsSeq || store.timetableRoute !== routeId) return;
    store.routeTrips = body.trips;
    focusRoute();
  } catch (error) {
    if (seq === tripsSeq) store.status = error.message;
  }
}

// Picking a route highlights it: its shapes stay bright, the rest dims.
function focusRoute() {
  const shapeIds = [
    ...new Set(
      store.routeTrips.map((trip) => trip.shape_id).filter((id) => id),
    ),
  ];
  mapBridge.setRouteFocus(shapeIds, store.currentFeedId);
}

export async function pickTimetableRoute(routeId) {
  store.timetableRoute = routeId || "";
  store.trip = null;
  store.routeTrips = [];
  if (!routeId) {
    mapBridge.setRouteFocus([], null);
    return;
  }
  await loadRouteTrips();
}

export async function loadTripTimes(tripId) {
  try {
    store.trip = await api(
      "GET",
      `/api/trips/${encodeURIComponent(tripId)}/times`,
    );
  } catch (error) {
    store.status = error.message;
  }
}

// The route's stop pattern, from its first trip's stop_times.
async function templateOffsets() {
  const template = store.routeTrips.find((trip) => trip.stop_count > 0);
  if (!template) return { offsets: [], shapeId: null };
  try {
    const body = await api(
      "GET",
      `/api/trips/${encodeURIComponent(template.trip_id)}/times`,
    );
    return {
      offsets: offsetsFromTimes(body.times),
      shapeId: template.shape_id || null,
    };
  } catch (error) {
    return { offsets: [], shapeId: null };
  }
}

export async function generateFrequency({ tripId, serviceId, start, end, headway }) {
  const { offsets, shapeId } = await templateOffsets();
  if (!offsets.length) {
    pushToast({
      title: "this route has no trips to copy times from",
      body: "create one with + New trip and picked stops first",
    });
    return false;
  }
  try {
    await api("POST", "/api/trips/frequency", {
      route_id: store.timetableRoute,
      service_id: serviceId,
      trip_id: tripId,
      stops: offsets,
      start,
      end,
      headway,
      shape_id: shapeId,
    });
  } catch (error) {
    pushToast({ title: "trips not generated", body: error.message });
    return false;
  }
  logServerEdit("Trips generated", `${store.timetableRoute} every ${headway}s`);
  pushToast({ title: "trips generated", body: store.timetableRoute });
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
  return true;
}

export async function addSingleTrip({ tripId, serviceId, shapeId, start }) {
  const base = toSeconds(start);
  if (base === null) {
    pushToast({ title: "start time must be HH:MM" });
    return false;
  }
  let offsets;
  let templateShape = null;
  if (store.tripStops.length) {
    offsets = store.tripStops.map((entry) => [entry.stopId, entry.offset]);
  } else {
    const template = await templateOffsets();
    offsets = template.offsets;
    templateShape = template.shapeId;
    if (!offsets.length) {
      pushToast({
        title: "pick stops on the map",
        body: "this route has no existing trip to copy a stop pattern from",
      });
      return false;
    }
  }
  const stops = offsets.map(([stopId, offset]) => [
    stopId,
    base + offset,
    base + offset,
  ]);
  try {
    await api("POST", "/api/trips", {
      route_id: store.timetableRoute,
      service_id: serviceId,
      trip_id: tripId,
      stops,
      shape_id: shapeId || templateShape,
    });
  } catch (error) {
    pushToast({ title: "trip not added", body: error.message });
    return false;
  }
  logServerEdit("Trip added", tripId);
  pushToast({ title: "trip added", body: tripId });
  store.tripStops.length = 0;
  store.tripPicking = false;
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
  return true;
}

export function toggleStopPicking() {
  store.tripPicking = !store.tripPicking;
}

export function clearPickedStops() {
  store.tripStops.length = 0;
}

export async function applyTripTimes() {
  const updates = {};
  for (const row of store.trip.times) {
    updates[row.stop_sequence] = {
      arrival_time: row.arrival_time,
      departure_time: row.departure_time,
    };
  }
  try {
    await api(
      "PUT",
      `/api/trips/${encodeURIComponent(store.trip.trip_id)}/times`,
      { times: updates },
    );
  } catch (error) {
    pushToast({ title: "times not applied", body: error.message });
    return;
  }
  logServerEdit("Stop times applied", store.trip.trip_id);
  pushToast({ title: "stop times applied", body: store.trip.trip_id });
  await loadTripTimes(store.trip.trip_id);
  await mapBridge.refreshSummary();
}

export async function shiftTrip() {
  const tripId = store.trip.trip_id;
  try {
    await api("POST", `/api/trips/${encodeURIComponent(tripId)}/shift`, {
      seconds: store.shiftSeconds,
    });
  } catch (error) {
    pushToast({ title: "trip not shifted", body: error.message });
    return;
  }
  logServerEdit("Trip shifted", `${tripId} by ${store.shiftSeconds}s`);
  await loadTripTimes(tripId);
  await mapBridge.refreshSummary();
}

export async function deleteTrip() {
  const tripId = store.trip.trip_id;
  try {
    await api("DELETE", `/api/trips/${encodeURIComponent(tripId)}`);
  } catch (error) {
    pushToast({ title: "trip not deleted", body: error.message });
    return;
  }
  logServerEdit("Trip deleted", tripId);
  pushToast({
    title: "trip deleted",
    body: tripId,
    action: { label: "undo", run: sessionUndo },
  });
  store.trip = null;
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
}
