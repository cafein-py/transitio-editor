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

// The selected route's shapes, so a follow-up zoom does not refetch
// them. Keyed by route so a pending/failed selection cannot hand the
// previous route's geometry to the zoom.
let shapeCache = {
  routeId: null,
  feedId: null,
  shapeIds: [],
  // the data generations the cache was built against
  dataVersion: -1,
  workspaceVersion: -1,
};

const cacheIsFresh = (routeId) =>
  shapeCache.routeId === routeId &&
  shapeCache.feedId === store.currentFeedId &&
  shapeCache.dataVersion === store.dataVersion &&
  shapeCache.workspaceVersion === store.workspaceVersion &&
  shapeCache.shapeIds.length > 0;

const emptyCache = () => ({
  routeId: null,
  feedId: null,
  shapeIds: [],
  dataVersion: -1,
  workspaceVersion: -1,
});

export async function selectRoute(routeId, { toggle = true } = {}) {
  if (toggle && store.selectedRouteId === routeId) {
    store.selectedRouteId = null;
    shapeCache = emptyCache();
    mapBridge.setSelectedShapes([], null);
    return [];
  }
  const feedId = store.currentFeedId;
  // sampled before the request: a response that lands after an edit
  // must not claim the newer generation
  const dataVersion = store.dataVersion;
  const workspaceVersion = store.workspaceVersion;
  store.selectedRouteId = routeId;
  shapeCache = emptyCache();
  // clear the old halo now: a failed fetch must not leave the previous
  // route highlighted under the newly selected row
  mapBridge.setSelectedShapes([], null);
  const seq = ++selectSeq;
  try {
    const body = await api(
      "GET",
      `/api/routes/${encodeURIComponent(routeId)}/trips`,
    );
    if (
      seq !== selectSeq ||
      store.selectedRouteId !== routeId ||
      store.currentFeedId !== feedId ||
      store.dataVersion !== dataVersion ||
      store.workspaceVersion !== workspaceVersion
    ) {
      return null; // the data moved under this request
    }
    const shapeIds = [
      ...new Set(
        body.trips.map((trip) => trip.shape_id).filter((id) => id),
      ),
    ];
    shapeCache = { routeId, feedId, shapeIds, dataVersion, workspaceVersion };
    mapBridge.setSelectedShapes(shapeIds, feedId);
    return shapeIds;
  } catch (error) {
    if (seq === selectSeq) store.status = error.message;
    return null; // null = the lookup failed, [] = the route has no shape
  }
}

// Double-click on a route row: select it (never toggling it off) and fit
// the map to its geometry.
export async function zoomToRoute(routeId) {
  const shapeIds = cacheIsFresh(routeId)
    ? shapeCache.shapeIds
    : await selectRoute(routeId, { toggle: false });
  if (shapeIds === null) {
    pushToast({
      title: "could not load the route's shape",
      body: store.status || "",
    });
    return;
  }
  if (!shapeIds.length) {
    pushToast({ title: "this route has no shape to zoom to" });
    return;
  }
  // The shapes may be absent from the map (hidden mode, inactive feed):
  // say so rather than leaving the map silently unmoved.
  if (!mapBridge.fitShapes(shapeIds, store.currentFeedId)) {
    pushToast({
      title: "the route's shape is not on the map",
      body: "its mode may be hidden in the map display bar",
    });
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
  if (store.historyBusy) {
    pushToast({ title: "an undo is still running" });
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
