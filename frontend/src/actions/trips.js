// Trips-panel actions: the picked route's trips and timetable, frequency
// generation, single-trip creation with map stop picking, and the
// stop-time edits. New trips copy their stop pattern from one of the
// route's existing trips when no stops are picked (there is no endpoint
// serving a route's canonical stop sequence).
import { setMode } from "../actions.js";
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

// Trip-detail loads carry their own sequence plus a feed pin: a slow
// response must not overwrite a newer selection, and one from before a
// feed switch must not repopulate an old feed's trip as editable.
let tripDetailSeq = 0;

export function invalidateTripLoads() {
  tripDetailSeq += 1;
}

export async function loadTripTimes(tripId) {
  const seq = ++tripDetailSeq;
  const feedId = store.currentFeedId;
  try {
    const body = await api(
      "GET",
      `/api/trips/${encodeURIComponent(tripId)}/times`,
    );
    if (seq !== tripDetailSeq || store.currentFeedId !== feedId) return;
    store.trip = body;
  } catch (error) {
    if (seq === tripDetailSeq) store.status = error.message;
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
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  const feedId = store.currentFeedId;
  const routeId = store.timetableRoute;
  const { offsets, shapeId } = await templateOffsets();
  if (!offsets.length) {
    pushToast({
      title: "this route has no trips to copy times from",
      body: "create one with + New trip and picked stops first",
    });
    return false;
  }
  if (store.currentFeedId !== feedId || store.timetableRoute !== routeId) {
    pushToast({ title: "selection changed — trips not generated" });
    return false;
  }
  try {
    await api("POST", "/api/trips/frequency", {
      route_id: routeId,
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
  logServerEdit("Trips generated", `${routeId} every ${headway}s`, feedId);
  pushToast({ title: "trips generated", body: routeId });
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
  return true;
}

export async function addSingleTrip({ tripId, serviceId, shapeId, start }) {
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  const feedId = store.currentFeedId;
  const routeId = store.timetableRoute;
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
  if (store.currentFeedId !== feedId || store.timetableRoute !== routeId) {
    pushToast({ title: "selection changed — trip not added" });
    return false;
  }
  try {
    await api("POST", "/api/trips", {
      route_id: routeId,
      service_id: serviceId,
      trip_id: tripId,
      stops,
      shape_id: shapeId || templateShape,
    });
  } catch (error) {
    pushToast({ title: "trip not added", body: error.message });
    return false;
  }
  logServerEdit("Trip added", tripId, feedId);
  pushToast({ title: "trip added", body: tripId });
  store.tripStops.length = 0;
  store.tripPicking = false;
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
  return true;
}

export function toggleStopPicking() {
  store.tripPicking = !store.tripPicking;
  // An armed + Stop / + Shape tool would swallow the picking clicks as
  // placements; picking implies plain select mode.
  if (store.tripPicking) setMode("select");
}

// Leaving the form or the panel must never keep picking armed — a later
// map click would silently append to an invisible draft.
export function stopStopPicking() {
  store.tripPicking = false;
}

export function clearPickedStops() {
  store.tripStops.length = 0;
}

export async function applyTripTimes() {
  const feedId = store.currentFeedId;
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
  logServerEdit("Stop times applied", store.trip.trip_id, feedId);
  pushToast({ title: "stop times applied", body: store.trip.trip_id });
  await loadTripTimes(store.trip.trip_id);
  await mapBridge.refreshSummary();
}

export async function shiftTrip() {
  const feedId = store.currentFeedId;
  const tripId = store.trip.trip_id;
  try {
    await api("POST", `/api/trips/${encodeURIComponent(tripId)}/shift`, {
      seconds: store.shiftSeconds,
    });
  } catch (error) {
    pushToast({ title: "trip not shifted", body: error.message });
    return;
  }
  logServerEdit("Trip shifted", `${tripId} by ${store.shiftSeconds}s`, feedId);
  await loadTripTimes(tripId);
  await mapBridge.refreshSummary();
}

export async function deleteTrip() {
  const feedId = store.currentFeedId;
  const tripId = store.trip.trip_id;
  try {
    await api("DELETE", `/api/trips/${encodeURIComponent(tripId)}`);
  } catch (error) {
    pushToast({ title: "trip not deleted", body: error.message });
    return;
  }
  logServerEdit("Trip deleted", tripId, feedId);
  pushToast({
    title: "trip deleted",
    body: tripId,
    action: { label: "undo", run: sessionUndo },
  });
  store.trip = null;
  await loadRouteTrips();
  await mapBridge.refreshAll(false);
}
