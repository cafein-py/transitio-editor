// Routes-panel actions: the current feed's route list, row selection
// (highlighting a route's shapes on the map), and the new-route form.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { logServerEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";
import { setMode } from "../actions.js";

let routesSeq = 0;

export async function loadRoutes() {
  const seq = ++routesSeq;
  try {
    const body = await api("GET", "/api/routes");
    if (seq !== routesSeq) return;
    store.routes = body.routes;
  } catch (error) {
    if (seq === routesSeq) store.status = error.message;
  }
}

// Selecting a route highlights its geometry: the shapes its trips
// reference (one fetch; the shapes layer has no route ids of its own).
let selectSeq = 0;

export async function selectRoute(routeId) {
  if (store.selectedRouteId === routeId) {
    store.selectedRouteId = null;
    mapBridge.setSelectedShapes([], null);
    return;
  }
  store.selectedRouteId = routeId;
  const seq = ++selectSeq;
  try {
    const body = await api(
      "GET",
      `/api/routes/${encodeURIComponent(routeId)}/trips`,
    );
    if (seq !== selectSeq || store.selectedRouteId !== routeId) return;
    const shapeIds = [
      ...new Set(
        body.trips.map((trip) => trip.shape_id).filter((id) => id),
      ),
    ];
    mapBridge.setSelectedShapes(shapeIds, store.currentFeedId);
  } catch (error) {
    if (seq === selectSeq) store.status = error.message;
  }
}

// The current feed's agencies for the form's select, via the attribute
// table (there is no agencies endpoint yet).
export async function agencyOptions() {
  try {
    const body = await api("GET", "/api/tables/agency.txt?limit=200");
    return body.rows
      .filter((row) => row.agency_id || row.agency_name)
      .map((row) => ({
        id: row.agency_id || "",
        name: row.agency_name || row.agency_id,
      }));
  } catch (error) {
    return []; // no agency table yet: the form offers the feed default
  }
}

export async function addRoute({ routeId, shortName, routeType, agencyId }) {
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  const feedId = store.currentFeedId;
  try {
    await api("POST", "/api/routes", {
      route_id: routeId,
      route_short_name: shortName,
      route_type: routeType,
      agency_id: agencyId || null,
    });
  } catch (error) {
    pushToast({ title: "route not added", body: error.message });
    return false;
  }
  logServerEdit("Route added", routeId, feedId);
  store.dirty = true;
  if (store.report) store.reportStale = true;
  await loadRoutes();
  await mapBridge.refreshAll(false);
  // Select it and arm the + Shape tool so its geometry comes next.
  selectRoute(routeId);
  setMode("draw");
  return true;
}
