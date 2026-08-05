// Feature actions shared by the sidebar panels. Each mutates the store
// and/or calls the API, then refreshes the map. `wrap` funnels errors to
// the status line and marks the validation report stale.
import { api } from "./api.js";
import { loadCatalogue } from "./actions/catalogue.js";
import {
  restoreSessionStatus,
  saveSessionStatus,
  sessionRestorePlan,
  sessionView,
} from "./sessions.js";
import * as mapBridge from "./map.js";
import { MODES, UNKNOWN_MODE } from "./modes.js";
import { isDownloaded } from "./search.js";
import {
  NETWORK_FEED,
  installRestoredLog,
  logPlain,
  logRequestEdit,
  logServerEdit,
  sessionLogForSave,
  sessionUndo,
} from "./session.js";
import { forms, resetForms, store } from "./store.js";
import { pushToast } from "./toasts.js";

// A slow pre-restore availability check must not overwrite the state a
// session restore has since installed.
let networkAvailableSeq = 0;

export async function checkNetworkAvailable() {
  const seq = ++networkAvailableSeq;
  try {
    const body = await api("GET", "/api/network");
    if (seq !== networkAvailableSeq) return;
    store.network.available = Boolean(body.available);
    store.network.source = body.source || null;
    // Both domains are visible by default: load the network eagerly so it
    // shows alongside the feed from the start, not only after opening the tab.
    if (store.network.available) await loadNetwork();
  } catch (error) {
    if (seq !== networkAvailableSeq) return;
    store.network.available = false;
  }
}

export async function loadNetwork() {
  const net = store.network;
  if (net.loaded || net.loading || !net.available) return;
  net.loading = true;
  net.error = "";
  try {
    await mapBridge.mapReady; // sources exist before we set their data
    if ((await mapBridge.fetchNetwork()) === false) return; // superseded
    net.loaded = true;
    mapBridge.setNetworkVisible(net.visible);
  } catch (error) {
    net.error = error.message;
  } finally {
    net.loading = false;
  }
}

export function setNetworkMode(mode) {
  store.network.mode = mode;
  store.network.movingNode = null;
  mapBridge.clearNetworkDraw();
  mapBridge.setCursor(
    mode === "add-node" || mode === "draw-way" ? "crosshair" : "",
  );
}

export async function finishDrawWay(tags) {
  if (store.network.draw.length < 2) return;
  const vertices = store.network.draw.map((point) => point.vertex);
  try {
    await api("POST", "/api/network/ways", { vertices, tags });
    setNetworkMode("select"); // clears the draw and its preview
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    logPlain("Way drawn", `${vertices.length} vertices`, NETWORK_FEED);
  } catch (error) {
    store.status = error.message;
  }
}

export function cancelDrawWay() {
  setNetworkMode("select");
}

export async function deleteNetworkWay() {
  const selected = store.network.selected;
  if (!selected) return;
  try {
    await api("DELETE", `/api/network/ways/${selected.id}`);
    store.network.selected = null;
    mapBridge.setSelectedNetworkFeature(null);
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    // A deleted way cannot be recreated with its id: logged, not undoable.
    logPlain("Way deleted", `way/${selected.id}`, NETWORK_FEED);
  } catch (error) {
    store.status = error.message;
  }
}

// The previous value of a network tag, for the compensating undo PATCH:
// a promoted column, or a key inside the stringified `tags` dict.
function previousTagValue(selected, key) {
  if (selected[key] !== undefined) return selected[key];
  const tags = selected.tags;
  if (!tags) return undefined;
  try {
    const dict = typeof tags === "string" ? JSON.parse(tags) : tags;
    return dict ? dict[key] : undefined;
  } catch (error) {
    return undefined;
  }
}

function logRetag(osmType, id, key, value, previous) {
  const path = `/api/network/${osmType === "way" ? "ways" : "nodes"}/${id}`;
  logRequestEdit(
    key === "highway" && osmType === "way"
      ? "Way reclassified"
      : `${osmType === "way" ? "Way" : "Node"} retagged`,
    `${osmType}/${id} ${key}=${value}`,
    previous == null
      ? null // no old value known: logged, not undoable
      : { method: "PATCH", path, body: { tags: { [key]: previous } } },
    { method: "PATCH", path, body: { tags: { [key]: value } } },
  );
}

export async function retagNetworkWay(key, value) {
  const selected = store.network.selected;
  if (!selected || !key.trim()) return;
  const previous = previousTagValue(selected, key.trim());
  try {
    await api("PATCH", `/api/network/ways/${selected.id}`, {
      tags: { [key.trim()]: value },
    });
    store.network.selected = { ...selected, [key.trim()]: value };
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    logRetag("way", selected.id, key.trim(), value, previous);
  } catch (error) {
    store.status = error.message;
  }
}

export function startMoveNode() {
  const selected = store.network.selected;
  if (!selected) return;
  store.network.movingNode = selected.id;
  store.status = "click the new location of the node";
  mapBridge.setCursor("crosshair");
}

export async function deleteNetworkNode() {
  const selected = store.network.selected;
  if (!selected) return;
  try {
    await api("DELETE", `/api/network/nodes/${selected.id}`);
    store.network.selected = null;
    mapBridge.setSelectedNetworkFeature(null);
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    logPlain("Node deleted", `node/${selected.id}`, NETWORK_FEED);
  } catch (error) {
    store.status = error.message;
  }
}

export async function retagNetworkNode(key, value) {
  const selected = store.network.selected;
  if (!selected || !key.trim()) return;
  const previous = previousTagValue(selected, key.trim());
  try {
    await api("PATCH", `/api/network/nodes/${selected.id}`, {
      tags: { [key.trim()]: value },
    });
    // reflect the tag on the still-selected node without a re-click
    store.network.selected = { ...selected, [key.trim()]: value };
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    logRetag("node", selected.id, key.trim(), value, previous);
  } catch (error) {
    store.status = error.message;
  }
}

export async function saveNetwork(path) {
  if (!path.trim()) return;
  try {
    const body = await api("POST", "/api/network/save", { path: path.trim() });
    store.status = `network saved to ${body.path}`;
  } catch (error) {
    store.status = error.message;
  }
}

export async function resetNetwork() {
  try {
    await api("POST", "/api/network/reset");
    store.network.selected = null;
    mapBridge.setSelectedNetworkFeature(null);
    setNetworkMode("select"); // clears an in-progress draw and its preview
    await mapBridge.fetchNetwork();
    store.status = "network edits discarded";
  } catch (error) {
    store.status = error.message;
  }
}

let resolveSeq = 0;

export async function resolveOsm(aoi) {
  const acquire = store.network.acquire;
  const seq = ++resolveSeq; // only the latest resolve may write the result
  acquire.resolving = true;
  acquire.error = "";
  acquire.resolved = null;
  try {
    const resolved = await api("POST", "/api/osm/resolve", { aoi });
    if (seq !== resolveSeq) return;
    acquire.resolved = resolved;
    store.status = "";
  } catch (error) {
    if (seq !== resolveSeq) return;
    acquire.error = error.message;
  } finally {
    if (seq === resolveSeq) acquire.resolving = false;
  }
}

export function resolveOsmByPlace() {
  const place = store.network.acquire.place.trim();
  if (place) resolveOsm(place);
}

export function resolveOsmByView() {
  const bbox = mapBridge.getViewportBbox();
  if (bbox) {
    resolveOsm(bbox);
  } else {
    // A failed new request must invalidate any prior resolved extract so its
    // Download button can't act on a stale AOI.
    store.network.acquire.resolved = null;
    store.network.acquire.error = "the current map view is not a valid area";
  }
}

export function resolveOsmByDrawn() {
  if (store.aoi) resolveOsm(store.aoi);
  else store.network.acquire.error = "draw an area on the map first";
}

export function cancelAcquire() {
  store.network.acquire.resolved = null;
  store.network.acquire.error = "";
}

export { startAoiDraw, clearAoi } from "./map.js";

export async function acquireOsm(discardEdits = false) {
  const net = store.network;
  const acquire = net.acquire;
  const resolved = acquire.resolved;
  if (!resolved || acquire.downloading) return;
  // An in-progress draw/move references the current network and would be
  // discarded by the swap; confirm rather than dropping it silently.
  const hasDraft = net.draw.length > 0 || net.movingNode != null;
  if (hasDraft && !discardEdits) {
    if (
      !window.confirm(
        "Discard the in-progress drawing and acquire a new extract?",
      )
    )
      return;
  }
  acquire.downloading = true;
  acquire.error = "";
  try {
    const downloaded = await api("POST", "/api/osm/download", {
      bbox: resolved.bbox,
      url: resolved.url,
      discard_edits: discardEdits,
    });
    net.source = downloaded.path;
  } catch (error) {
    // 409 on submitted-but-unsaved edits: confirm discarding, then retry once.
    if (
      error.status === 409 &&
      !discardEdits &&
      /unsaved network edits/.test(error.message)
    ) {
      acquire.downloading = false;
      if (
        window.confirm(
          "Discard unsaved network edits and load the new extract?",
        )
      ) {
        return acquireOsm(true);
      }
      return;
    }
    acquire.error = error.message;
    acquire.downloading = false;
    return;
  }
  // The network changed: reset view state and render the new one.
  net.available = true;
  net.loaded = false;
  net.selected = null;
  mapBridge.setSelectedNetworkFeature(null);
  net.error = "";
  setNetworkMode("select"); // clears any in-progress draw/move
  try {
    await mapBridge.mapReady;
    await mapBridge.fetchNetwork();
    net.loaded = true;
    mapBridge.setNetworkVisible(net.visible);
    mapBridge.fitBbox(resolved.bbox);
    await mapBridge.refreshSummary(); // snapping is now available
    store.status = `loaded OSM extract "${resolved.name}"`;
  } catch (error) {
    net.error = error.message;
  } finally {
    acquire.downloading = false;
    acquire.resolved = null;
    acquire.place = "";
  }
}

export function toggleNetworkVisible() {
  store.network.visible = !store.network.visible;
  mapBridge.setNetworkVisible(store.network.visible);
}

export function toggleFeedVisible() {
  store.feedVisible = !store.feedVisible;
  mapBridge.setFeedVisible(store.feedVisible);
}

export function toggleStopsVisible() {
  store.stopsVisible = !store.stopsVisible;
  mapBridge.setStopsVisible(store.stopsVisible);
}

export function setShapeColorBy(colorBy) {
  store.shapeColorBy = colorBy;
  mapBridge.setShapeColorBy(colorBy);
}

export function toggleModeHidden(code) {
  const hidden = store.hiddenModes;
  const index = hidden.indexOf(code);
  if (index === -1) hidden.push(code);
  else hidden.splice(index, 1);
  mapBridge.setHiddenModes([...hidden]);
}

export function setAllModesHidden(hidden) {
  const codes = hidden
    ? [...MODES.map((mode) => mode.code), UNKNOWN_MODE.code]
    : [];
  store.hiddenModes.splice(0, store.hiddenModes.length, ...codes);
  mapBridge.setHiddenModes([...store.hiddenModes]);
}

export function wrap(action) {
  return async (...args) => {
    try {
      await action(...args);
      store.status = "";
      store.dirty = true;
      if (store.report) store.reportStale = true;
    } catch (error) {
      store.status = error.message;
    }
  };
}

export function toggleEditMode() {
  store.editMode = !store.editMode;
  // Leaving edit mode disarms any pending map mutation (add stop, draw,
  // move, trip-stop picking) so the read-only view really is read-only.
  if (!store.editMode) {
    setMode("select");
    store.tripPicking = false;
  }
}

let tableSeq = 0; // only the latest table request may write the view

export async function loadTable(patch = {}) {
  const view = store.tableView;
  Object.assign(view, patch);
  if (!view.file) {
    const files = Object.keys(store.tables);
    if (!files.length) return;
    view.file = files[0];
  }
  const seq = ++tableSeq;
  view.loading = true;
  try {
    const params = new URLSearchParams({
      offset: String(view.offset),
      limit: String(view.limit),
    });
    if (view.q.trim()) params.set("q", view.q.trim());
    const body = await api(
      "GET",
      `/api/tables/${encodeURIComponent(view.file)}?${params.toString()}`,
    );
    if (seq !== tableSeq) return; // a newer request superseded this one
    view.total = body.total;
    view.columns = body.columns;
    view.rows = body.rows;
  } catch (error) {
    if (seq === tableSeq) store.status = error.message;
  } finally {
    if (seq === tableSeq) view.loading = false;
  }
}

export function resetTableView() {
  tableSeq += 1; // invalidate any in-flight request
  Object.assign(store.tableView, {
    open: false,
    file: "",
    q: "",
    offset: 0,
    total: 0,
    columns: [],
    rows: [],
    loading: false,
  });
}

export function toggleTableView() {
  const view = store.tableView;
  view.open = !view.open;
  if (view.open) loadTable({ offset: 0 });
}

export function setMode(mode) {
  store.mode = mode;
  // A pending "move stop" would otherwise hijack the next map click in
  // the new mode; changing mode cancels it.
  if (store.movingStop) {
    store.movingStop = null;
    store.status = "";
  }
  if (mode !== "draw") mapBridge.resetDraw();
  mapBridge.setCursor(mode === "select" ? "" : "crosshair");
}

export function cancelShape() {
  mapBridge.resetDraw();
  setMode("select");
}

export const finishShape = wrap(async () => {
  // Wait out any in-flight snap so the newest drawn point is included.
  const coords = await mapBridge.previewCoordsSettled();
  if (coords.length < 2) {
    throw new Error("draw at least two points first");
  }
  const shapeId = prompt("shape_id?");
  if (!shapeId) return;
  await api("POST", "/api/shapes", {
    shape_id: shapeId,
    points: coords.map(([lon, lat]) => [lat, lon]),
  });
  logServerEdit("Shape drawn", shapeId);
  cancelShape();
  await mapBridge.refreshAll(false);
});

export const updateInspectedStop = wrap(async () => {
  await api(
    "PATCH",
    `/api/stops/${encodeURIComponent(store.inspector.stopId)}`,
    {
      stop_name: store.inspector.name,
    },
  );
  logServerEdit("Stop renamed", store.inspector.stopId);
  await mapBridge.refreshAll(false);
});

export function closeInspector() {
  store.inspector = null;
  store.movingStop = null;
  mapBridge.setSelectedStop(null); // the halo follows the selection
}

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
  logServerEdit("Route added", forms.route.route_id);
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
  logServerEdit(
    "Trips generated",
    `${forms.trip.route_id} every ${forms.trip.headway}s`,
  );
  store.tripStops.length = 0;
  forms.trip.trip_id = "";
  await mapBridge.refreshAll(false);
});

export const submitAgency = wrap(async () => {
  await api("POST", "/api/agencies", { ...forms.agency });
  logServerEdit("Agency added", forms.agency.agency_id);
  await mapBridge.refreshAll(false);
});

export const submitService = wrap(async () => {
  await api("POST", "/api/services", { ...forms.service });
  logServerEdit("Service added", forms.service.service_id);
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
    store.trip = await api(
      "GET",
      `/api/trips/${encodeURIComponent(tripId)}/times`,
    );
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
  await api(
    "PUT",
    `/api/trips/${encodeURIComponent(store.trip.trip_id)}/times`,
    {
      times: updates,
    },
  );
  logServerEdit("Stop times applied", store.trip.trip_id);
  await loadTrip(store.trip.trip_id);
  await mapBridge.refreshSummary(); // the undo label just changed
});

export const deleteTrip = wrap(async () => {
  const tripId = store.trip.trip_id;
  await api("DELETE", `/api/trips/${encodeURIComponent(tripId)}`);
  logServerEdit("Trip deleted", tripId);
  pushToast({
    title: "trip deleted",
    body: tripId,
    action: { label: "undo", run: sessionUndo },
  });
  store.trip = null;
  await loadTrips();
  await mapBridge.refreshAll(false);
});

export const shiftTrip = wrap(async () => {
  await api(
    "POST",
    `/api/trips/${encodeURIComponent(store.trip.trip_id)}/shift`,
    {
      seconds: store.shiftSeconds,
    },
  );
  logServerEdit(
    "Trip shifted",
    `${store.trip.trip_id} by ${store.shiftSeconds}s`,
  );
  await loadTrip(store.trip.trip_id);
  await mapBridge.refreshSummary(); // the undo label just changed
});

// Interaction state (selection, drafts, timetable, report) is scoped to
// the current feed; wipe it when the edit target changes so later actions
// can't target entities from the previous feed.
export function resetFeedScopedState() {
  setMode("select"); // also clears movingStop and the draw preview
  store.inspector = null;
  mapBridge.clearFeedSelection();
  resetTableView();
  store.tripStops.length = 0;
  store.tripPicking = false;
  store.trip = null;
  store.timetableRoute = "";
  store.routeTrips = [];
  store.routes = [];
  store.report = null;
  store.reportStale = false;
  store.saveResult = null;
  store.undoLabel = null; // the old feed's labels must not stay actionable
  store.redoLabel = null;
  resetForms();
  mapBridge.clearHighlight();
}

// Saving and restoring sessions. The view snapshot and the restore
// decision table are pure (sessions.js); these actions do the IO and
// call the map bridge.
export async function saveSession() {
  const session = store.session;
  const path = session.path.trim();
  if (!path || session.saving) return;
  session.saving = true;
  try {
    const base = path.split(/[\\/]/).pop(); // both separator styles
    // derive .json only for an extensionless name (a leading or trailing
    // dot is not an extension); a wrong real extension is the server's
    // 422 to give, not something to silently double up
    const hasExtension = /[^./\\]\.[^.]+$/.test(base);
    const target = hasExtension ? path : `${path.replace(/\.$/, "")}.json`;
    const body = await api("POST", "/api/session/save", {
      path: target,
      view: {
        ...sessionView(store, mapBridge.getCamera()),
        ...(store.session.wsName ? { ws_name: store.session.wsName } : {}),
        log: sessionLogForSave(),
      },
    });
    session.path = body.path;
    store.status = saveSessionStatus(body);
  } catch (error) {
    store.status = error.message;
  } finally {
    session.saving = false;
  }
}

function applySessionView(view) {
  const plan = sessionRestorePlan(view || {});
  if (plan.basemap) mapBridge.setBasemap(plan.basemap);
  if (plan.hiddenModes) {
    store.hiddenModes.splice(0, store.hiddenModes.length, ...plan.hiddenModes);
    mapBridge.setHiddenModes([...store.hiddenModes]);
  }
  if (plan.shapeColorBy) setShapeColorBy(plan.shapeColorBy);
  if (plan.stopsVisible !== undefined) {
    store.stopsVisible = plan.stopsVisible;
    mapBridge.setStopsVisible(plan.stopsVisible);
  }
  if (plan.activePanel) {
    store.activePanel = plan.activePanel;
    // the restored panel is now the working panel (or none, for Data)
    store.workingPanel = plan.activePanel === "data" ? null : plan.activePanel;
  }
  // Workspace extras ride in the same view blob: the name and the
  // activity log (viewable after a reload, not undoable — the server
  // holds no history for pre-save actions).
  if (typeof view.ws_name === "string" && view.ws_name) {
    store.session.wsName = view.ws_name;
    store.session.named = true;
  }
  installRestoredLog(view.log);
  if (plan.camera) mapBridge.jumpTo(plan.camera.center, plan.camera.zoom);
  else if (plan.fit) mapBridge.fitToStops();
}

export async function loadSession(flags = {}) {
  const session = store.session;
  const path = session.path.trim();
  if (!path || session.loading) return;
  session.loading = true;
  try {
    const body = await api("POST", "/api/session/restore", {
      path,
      ...flags,
    });
    session.confirm = null;
    await mapBridge.mapReady; // layer resets below need the sources
    resetFeedScopedState();
    // the old network's layers, drafts and acquire state must not
    // survive into the new session; bump the resolve seq so an in-flight
    // resolve cannot repopulate it either
    store.merge.selected = []; // ids from the replaced catalogue
    resolveSeq += 1;
    mapBridge.invalidateNetwork(); // an in-flight fetch must not repaint
    Object.assign(store.network.acquire, {
      place: "",
      resolving: false,
      resolved: null,
      downloading: false,
      error: "",
    });
    Object.assign(store.network, {
      loaded: false,
      loading: false,
      selected: null,
      nodeCount: 0,
      wayCount: 0,
      mode: "select",
      movingNode: null,
      draw: [],
      error: "",
    });
    mapBridge.clearNetworkDraw(); // a way begun against the old extract
    mapBridge.setNetworkData(
      { type: "FeatureCollection", features: [] },
      { type: "FeatureCollection", features: [] },
    );
    await loadCatalogue();
    await mapBridge.refreshAll(false);
    await mapBridge.refreshSummary();
    await checkNetworkAvailable();
    applySessionView(body.view);
    store.status = restoreSessionStatus(body);
  } catch (error) {
    const detail = error.status === 409 ? error.detail : null;
    if (detail && typeof detail === "object") {
      // the server names what would be lost; ask, then retry with the
      // matching flag added (both confirms can appear in sequence)
      session.confirm = { ...detail, flags };
    } else {
      store.status = error.message;
    }
  } finally {
    session.loading = false;
  }
}

export async function confirmLoadSession() {
  const confirm = store.session.confirm;
  if (!confirm) return;
  const flag = confirm.reason === "osm-edits" ? "discard_edits" : "replace";
  store.session.confirm = null;
  await loadSession({ ...confirm.flags, [flag]: true });
}

export function cancelLoadSession() {
  store.session.confirm = null;
}

// Every feed-scoped view must reflect reverted tables after an undo/redo:
// stale editable values (an open timetable, the attribute table) could
// otherwise be saved back, silently re-applying what was just undone.
// The session core calls this via its injected refresh hook.
export async function refreshAfterHistory() {
  await mapBridge.refreshAll(false);
  if (store.tableView.open) await loadTable();
  if (store.timetableRoute) await loadTrips();
  if (store.trip) {
    // fetched inline: loadTrip swallows its own errors, and a trip the
    // undo removed must clear the stale editable detail, not keep it
    try {
      store.trip = await api(
        "GET",
        `/api/trips/${encodeURIComponent(store.trip.trip_id)}/times`,
      );
    } catch (error) {
      store.trip = null;
    }
  }
  closeInspector(); // its stop may no longer exist or match
}

export async function runSearch() {
  const s = store.search;
  s.searching = true;
  s.selected = []; // old selections must not survive into new results
  s.searched = true;
  try {
    const params = new URLSearchParams();
    const q = s.q.trim();
    let areaHint = "";
    if (q) {
      params.set("q", q); // a typed place decides the area
    } else {
      const bbox = searchAoiBbox();
      if (bbox) params.set("bbox", bbox.join(","));
      // Don't silently drop a requested area filter.
      if (s.aoiMode !== "none" && !bbox) {
        areaHint = "no area available — searched everywhere";
      }
    }
    if (s.officialOnly) params.set("official", "true");
    params.set("limit", String(s.limit));
    const body = await api("GET", `/api/search?${params.toString()}`);
    s.results = body.feeds;
    s.csvFallback = body.csv_fallback;
    if (body.place) {
      // the search meant a place: show it
      mapBridge.fitBbox(body.place.bbox);
      store.status = `showing ${body.place.query}`;
    } else {
      store.status = areaHint;
    }
  } catch (error) {
    s.results = [];
    s.searched = false; // an error is not "no feeds found"
    store.status = error.message;
  } finally {
    s.searching = false;
  }
}

// The bbox the Search tab's area selector points at, or null.
function searchAoiBbox() {
  if (store.search.aoiMode === "map") return mapBridge.getViewportBbox();
  if (store.search.aoiMode === "drawn") return store.aoi;
  return null;
}

// The request body for downloading one feed with the tab's settings, or
// null (with a status hint) when a requested crop has no area to crop to.
function downloadBody(feed) {
  const body = { feed_id: feed.id, activate: true };
  const directory = store.search.downloadDir.trim();
  if (directory) body.directory = directory;
  if (store.search.cropToAoi) {
    const bbox = searchAoiBbox();
    if (!bbox) {
      // Don't silently download the full feed when a crop was asked for.
      store.status = "select or draw an area to crop to, or uncheck crop";
      return null;
    }
    body.aoi = bbox;
  }
  return body;
}

export async function downloadFeed(feed) {
  const body = downloadBody(feed);
  if (!body) return;
  store.search.downloadingId = feed.id;
  try {
    await api("POST", "/api/catalogue/download", body);
    await loadCatalogue();
    await mapBridge.refreshAll(true);
    // Stay on the Search tab: downloading many of an area's feeds in a row
    // shouldn't bounce the view to the Catalogue each time. The green check
    // on the result row and the status line confirm the download.
    store.status = `downloaded ${feed.provider || feed.id}`;
  } catch (error) {
    store.status = error.message;
  } finally {
    store.search.downloadingId = null;
  }
}

// Server-side file browser behind every path box (a web page cannot read
// absolute paths from a native picker; the loopback backend can). `target`
// names the field a choice lands in, `mode` whether feeds are pickable.
export async function openBrowser(target, mode, path) {
  // Clear the old listing: entries from the previous target must not be
  // clickable under the new one while its listing is on the way.
  Object.assign(store.browse, {
    target,
    mode,
    path: "",
    parent: null,
    dirs: [],
    feeds: [],
    sessions: [],
    error: "",
  });
  await browseTo(path);
}

// Listings can land out of order; only the newest one may paint (and a
// cancel invalidates every one in flight, so none reopens the browser).
let browseSeq = 0;

export async function browseTo(path) {
  const browse = store.browse;
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const seq = ++browseSeq;
  try {
    const listing = await api("GET", `/api/fs/dirs${query}`);
    if (seq !== browseSeq) return;
    Object.assign(browse, {
      open: true,
      path: listing.path,
      parent: listing.parent,
      dirs: listing.dirs,
      feeds: listing.feeds || [],
      sessions: listing.sessions || [],
      error: "",
    });
  } catch (error) {
    if (seq !== browseSeq) return;
    browse.open = true;
    browse.error = error.message;
  }
}

export function closeBrowser() {
  browseSeq += 1; // pending listings must not reopen it
  store.browse.open = false;
}

function applyBrowseChoice(value) {
  const { target } = store.browse;
  if (target === "downloadDir") store.search.downloadDir = value;
  else if (target === "feedPath") store.newFeedPath = value;
  else if (target === "mergeDir") store.merge.directory = value;
  else if (target === "sessionPath") store.session.path = value;
  closeBrowser(); // a pending listing must not reopen it over the choice
}

export function chooseBrowsedSession(name) {
  applyBrowseChoice(`${store.browse.path}/${name}`);
}

export function chooseBrowsedDir() {
  applyBrowseChoice(store.browse.path);
}

export function chooseBrowsedFeed(name) {
  applyBrowseChoice(`${store.browse.path}/${name}`);
}

export function toggleFeedSelected(feedId) {
  const selected = store.search.selected;
  const index = selected.indexOf(feedId);
  if (index === -1) selected.push(feedId);
  else selected.splice(index, 1);
}

export function setAllSelected(feeds, on) {
  store.search.selected = on ? feeds.map((feed) => feed.id) : [];
}

// Download every selected result sequentially, keeping going on failures
// and reporting a summary; each success gets its green check as it lands.
export async function downloadSelected() {
  const s = store.search;
  if (s.bulk.running || !s.selected.length) return;
  const queue = s.results.filter((feed) => s.selected.includes(feed.id));
  if (!queue.length) return;
  // Snapshot the folder/crop settings once: a mid-run change to the
  // controls must not alter (or abort) the remaining queue.
  const template = downloadBody(queue[0]);
  if (!template) return; // crop misconfigured
  s.bulk = { running: true, done: 0, total: queue.length };
  const failed = [];
  let skipped = 0;
  try {
    for (const feed of queue) {
      // Re-check against the live catalogue: a feed downloaded individually
      // (or made undownloadable) since selection must not download again.
      if (!feed.downloadable || isDownloaded(store.catalogue, feed.id)) {
        const stale = s.selected.indexOf(feed.id);
        if (stale !== -1) s.selected.splice(stale, 1);
        s.bulk.done += 1;
        skipped += 1;
        continue;
      }
      const body = { ...template, feed_id: feed.id };
      s.downloadingId = feed.id;
      try {
        await api("POST", "/api/catalogue/download", body);
        await loadCatalogue();
        const index = s.selected.indexOf(feed.id);
        if (index !== -1) s.selected.splice(index, 1);
      } catch (error) {
        failed.push(feed.provider || feed.id);
      } finally {
        s.downloadingId = null;
        s.bulk.done += 1;
      }
    }
    await mapBridge.refreshAll(true);
    const ok = s.bulk.done - failed.length - skipped;
    let summary = failed.length
      ? `downloaded ${ok} of ${s.bulk.total} feeds — failed: ${failed.join(", ")}`
      : `downloaded ${ok} feeds`;
    if (skipped) summary += ` (${skipped} already in the catalogue)`;
    store.status = summary;
  } finally {
    s.bulk = { running: false, done: 0, total: 0 };
  }
}

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
