// Street-network actions: availability, loading, the editing toggle,
// reclassifying and deleting ways, saving/discarding edits, and swapping
// the extract. Vertex-drag editing lives in map/streets.js.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { applyHiddenClasses, selectWay, setStreetsVisible } from "../map/streets.js";
import { NETWORK_FEED, logPlain, logRequestEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

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
    if (!store.network.savePath && store.network.source) {
      store.network.savePath = store.network.source;
    }
    // Both domains are visible by default: load the network eagerly so it
    // shows alongside the feed from the start, not only on panel open.
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
    setStreetsVisible(net.visible);
  } catch (error) {
    net.error = error.message;
  } finally {
    net.loading = false;
  }
}

export function toggleNetworkVisible() {
  store.network.visible = !store.network.visible;
  setStreetsVisible(store.network.visible);
}

export function toggleNetworkEditing() {
  store.network.editing = !store.network.editing;
  if (!store.network.editing) store.network.vertexEdit = false;
}

export function toggleHighwayClass(key) {
  const hidden = store.hiddenHighwayClasses;
  const index = hidden.indexOf(key);
  if (index === -1) hidden.push(key);
  else hidden.splice(index, 1);
  applyHiddenClasses();
}

export function setAllHighwayClasses(hiddenAll, keys) {
  store.hiddenHighwayClasses.splice(
    0,
    store.hiddenHighwayClasses.length,
    ...(hiddenAll ? keys : []),
  );
  applyHiddenClasses();
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

// The selection card's highway <select>: reclassifies the way live.
export async function reclassifyWay(value) {
  const selected = store.network.selected;
  if (!selected || !value) return;
  const previous = previousTagValue(selected, "highway");
  const path = `/api/network/ways/${selected.id}`;
  try {
    await api("PATCH", path, { tags: { highway: value } });
    store.network.selected = { ...selected, highway: value };
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    logRequestEdit(
      "Way reclassified",
      `way/${selected.id} highway=${value}`,
      previous == null
        ? null // no old value known: logged, not undoable
        : { method: "PATCH", path, body: { tags: { highway: previous } } },
      { method: "PATCH", path, body: { tags: { highway: value } } },
    );
    // the halo width follows the class
    selectWay(store.network.selected);
  } catch (error) {
    store.status = error.message;
  }
}

export async function deleteNetworkWay() {
  const selected = store.network.selected;
  if (!selected) return;
  if (!window.confirm(`Delete way/${selected.id}? This cannot be undone.`)) {
    return;
  }
  try {
    await api("DELETE", `/api/network/ways/${selected.id}`);
    selectWay(null);
    await mapBridge.fetchNetwork();
    store.status = "";
    store.dirty = true;
    // A deleted way cannot be recreated with its id: logged, not undoable.
    logPlain("Way deleted", `way/${selected.id}`, NETWORK_FEED);
  } catch (error) {
    store.status = error.message;
  }
}

export async function saveNetwork() {
  const path = store.network.savePath.trim();
  if (!path) return;
  try {
    const body = await api("POST", "/api/network/save", { path });
    pushToast({ title: "network saved", body: body.path });
  } catch (error) {
    pushToast({ title: "network not saved", body: error.message });
  }
}

export async function resetNetwork() {
  if (!window.confirm("Discard all street-network edits?")) return;
  try {
    await api("POST", "/api/network/reset");
    selectWay(null);
    await mapBridge.fetchNetwork();
    logPlain("Network edits discarded", "", NETWORK_FEED);
    pushToast({ title: "network edits discarded" });
  } catch (error) {
    store.status = error.message;
  }
}

// ---- Acquiring a different extract -----------------------------------

let resolveSeq = 0;

// A session restore replaces the network; an in-flight resolve from the
// old one must not land afterwards.
export function invalidateResolve() {
  resolveSeq += 1;
}

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

export async function acquireOsm(discardEdits = false) {
  const net = store.network;
  const acquire = net.acquire;
  const resolved = acquire.resolved;
  if (!resolved || acquire.downloading) return;
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
        window.confirm("Discard unsaved network edits and load the new extract?")
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
  net.savePath = net.source || "";
  selectWay(null);
  net.error = "";
  try {
    await mapBridge.mapReady;
    await mapBridge.fetchNetwork();
    net.loaded = true;
    setStreetsVisible(net.visible);
    mapBridge.fitBbox(resolved.bbox);
    await mapBridge.refreshSummary(); // snapping is now available
    logPlain("Extract swapped", resolved.name, NETWORK_FEED);
    pushToast({ title: "loaded OSM extract", body: resolved.name });
  } catch (error) {
    net.error = error.message;
  } finally {
    acquire.downloading = false;
    acquire.resolved = null;
    acquire.place = "";
  }
}
