// Feature actions shared by the sidebar panels. Each mutates the store
// and/or calls the API, then refreshes the map. `wrap` funnels errors to
// the status line and marks the validation report stale.
import { api } from "./api.js";
import * as mapBridge from "./map.js";
import { MODES, UNKNOWN_MODE } from "./modes.js";
import { forms, resetForms, store } from "./store.js";

export async function checkNetworkAvailable() {
  try {
    const body = await api("GET", "/api/network");
    store.network.available = Boolean(body.available);
    store.network.source = body.source || null;
    // Both domains are visible by default: load the network eagerly so it
    // shows alongside the feed from the start, not only after opening the tab.
    if (store.network.available) await loadNetwork();
  } catch (error) {
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
    await mapBridge.fetchNetwork();
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
  } catch (error) {
    store.status = error.message;
  }
}

export async function retagNetworkWay(key, value) {
  const selected = store.network.selected;
  if (!selected || !key.trim()) return;
  try {
    await api("PATCH", `/api/network/ways/${selected.id}`, {
      tags: { [key.trim()]: value },
    });
    store.network.selected = { ...selected, [key.trim()]: value };
    await mapBridge.fetchNetwork();
    store.status = "";
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
  } catch (error) {
    store.status = error.message;
  }
}

export async function retagNetworkNode(key, value) {
  const selected = store.network.selected;
  if (!selected || !key.trim()) return;
  try {
    await api("PATCH", `/api/network/nodes/${selected.id}`, {
      tags: { [key.trim()]: value },
    });
    // reflect the tag on the still-selected node without a re-click
    store.network.selected = { ...selected, [key.trim()]: value };
    await mapBridge.fetchNetwork();
    store.status = "";
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
    if (!window.confirm("Discard the in-progress drawing and acquire a new extract?"))
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
      if (window.confirm("Discard unsaved network edits and load the new extract?")) {
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
  const codes = hidden ? [...MODES.map((mode) => mode.code), UNKNOWN_MODE.code] : [];
  store.hiddenModes.splice(0, store.hiddenModes.length, ...codes);
  mapBridge.setHiddenModes([...store.hiddenModes]);
}

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

export function toggleEditMode() {
  store.editMode = !store.editMode;
  // Leaving edit mode disarms any pending map mutation (add stop, draw,
  // move) so the read-only view really is read-only.
  if (!store.editMode) setMode("select");
}

export async function loadTable(patch = {}) {
  const view = store.tableView;
  Object.assign(view, patch);
  if (!view.file) {
    const files = Object.keys(store.tables);
    if (!files.length) return;
    view.file = files[0];
  }
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
    view.total = body.total;
    view.columns = body.columns;
    view.rows = body.rows;
  } catch (error) {
    store.status = error.message;
  } finally {
    view.loading = false;
  }
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

export async function loadCatalogue() {
  try {
    const body = await api("GET", "/api/catalogue");
    store.catalogue = body.feeds;
    store.currentFeedId = body.current;
  } catch (error) {
    store.status = error.message;
  }
}

export async function addFeed() {
  const path = store.newFeedPath.trim();
  if (!path) return;
  try {
    await api("POST", "/api/catalogue", { path });
    store.newFeedPath = "";
    await loadCatalogue();
    await mapBridge.refreshAll(true);
    store.status = "";
  } catch (error) {
    store.status = error.message;
  }
}

// Interaction state (selection, drafts, timetable, report) is scoped to
// the current feed; wipe it when the edit target changes so later actions
// can't target entities from the previous feed.
function resetFeedScopedState() {
  setMode("select"); // also clears movingStop and the draw preview
  store.inspector = null;
  mapBridge.clearFeedSelection();
  store.tripStops.length = 0;
  store.tripPicking = false;
  store.trip = null;
  store.timetableRoute = "";
  store.routeTrips = [];
  store.routes = [];
  store.report = null;
  store.reportStale = false;
  store.saveResult = null;
  resetForms();
  mapBridge.clearHighlight();
}

export async function setCurrentFeed(feed) {
  try {
    const body = await api("PUT", "/api/catalogue/current", {
      feed_id: feed.feed_id,
    });
    resetFeedScopedState();
    // Reflect the committed switch locally so the UI stays consistent even
    // if the follow-up reload fails; loadCatalogue then refreshes the rest.
    store.currentFeedId = body.current;
    for (const entry of store.catalogue) {
      entry.current = entry.feed_id === body.current;
    }
    await loadCatalogue();
    await mapBridge.refreshSummary();
  } catch (error) {
    store.status = error.message;
  }
}

export async function toggleFeedActive(feed) {
  try {
    await api("PATCH", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`, {
      active: !feed.active,
    });
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  } catch (error) {
    store.status = error.message;
  }
}

export async function removeFeed(feed) {
  try {
    await api("DELETE", `/api/catalogue/${encodeURIComponent(feed.feed_id)}`);
    // Removing the current feed reassigns current, so drop its state too.
    if (feed.current) resetFeedScopedState();
    await loadCatalogue();
    await mapBridge.refreshAll(false);
  } catch (error) {
    store.status = error.message;
  }
}

export async function runSearch() {
  const s = store.search;
  s.searching = true;
  s.searched = true;
  try {
    const params = new URLSearchParams();
    if (s.country.trim()) params.set("country", s.country.trim());
    if (s.subdivision.trim()) params.set("subdivision", s.subdivision.trim());
    if (s.municipality.trim()) params.set("municipality", s.municipality.trim());
    if (s.officialOnly) params.set("official", "true");
    const bbox = searchAoiBbox();
    if (bbox) params.set("bbox", bbox.join(","));
    params.set("limit", String(s.limit));
    const body = await api("GET", `/api/search?${params.toString()}`);
    s.results = body.feeds;
    s.selected = []; // a new result set invalidates the bulk selection
    s.csvFallback = body.csv_fallback;
    // Don't silently drop a requested area filter.
    store.status =
      s.aoiMode !== "none" && !bbox ? "no area available — searched everywhere" : "";
  } catch (error) {
    s.results = [];
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

// Server-side folder browser for the download directory (a web page cannot
// read absolute paths from a native picker; the loopback backend can).
export async function openDirBrowser(path) {
  const browse = store.search.browse;
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  try {
    const listing = await api("GET", `/api/fs/dirs${query}`);
    Object.assign(browse, {
      open: true,
      path: listing.path,
      parent: listing.parent,
      dirs: listing.dirs,
      error: "",
    });
  } catch (error) {
    browse.open = true;
    browse.error = error.message;
  }
}

export function closeDirBrowser() {
  store.search.browse.open = false;
}

export function chooseBrowsedDir() {
  store.search.downloadDir = store.search.browse.path;
  store.search.browse.open = false;
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
  if (queue.length && !downloadBody(queue[0])) return; // crop misconfigured
  s.bulk = { running: true, done: 0, total: queue.length };
  const failed = [];
  try {
    for (const feed of queue) {
      const body = downloadBody(feed);
      if (!body) break; // settings changed mid-run; keep remaining selected
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
    const ok = s.bulk.done - failed.length;
    store.status = failed.length
      ? `downloaded ${ok} of ${s.bulk.total} feeds — failed: ${failed.join(", ")}`
      : `downloaded ${ok} feeds`;
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
