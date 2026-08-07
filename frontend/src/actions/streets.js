// Street-network actions: availability, loading, the editing toggle,
// reclassifying and deleting ways, saving/discarding edits, and swapping
// the extract. Vertex-drag editing lives in map/streets.js.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import {
  applyHiddenClasses,
  selectWay,
  setStreetsVisible,
  setVertexEdit,
} from "../map/streets.js";
import { NETWORK_FEED, logPlain, logRequestEdit } from "../session.js";
import { store } from "../store.js";
import { extractDisplay } from "../streets.js";
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
    // Identity from the file name when nothing better is known (a fresh
    // start; an acquire in this session sets the resolver's area name).
    // A bbox-crop file keeps no area name — label it for what it is.
    if (!store.network.displayName) {
      const parsed = extractDisplay(store.network.source);
      store.network.displayName =
        parsed.name || (parsed.bbox ? "Map view extract" : null);
      store.network.bbox = parsed.bbox;
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
  // Through the map bridge so the on-map vertex handles clear too.
  if (!store.network.editing) setVertexEdit(false);
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
  } catch (error) {
    store.status = error.message;
    return;
  }
  // Committed: log before the fallible refresh, or a refresh hiccup
  // would leave a real backend mutation without an entry or undo.
  logRequestEdit(
    "Way reclassified",
    `way/${selected.id} highway=${value}`,
    previous == null
      ? null // no old value known: logged, not undoable
      : { method: "PATCH", path, body: { tags: { highway: previous } } },
    { method: "PATCH", path, body: { tags: { highway: value } } },
  );
  store.dirty = true;
  store.network.selected = { ...selected, highway: value };
  // the halo width follows the class
  selectWay(store.network.selected);
  try {
    await mapBridge.fetchNetwork();
    store.status = "";
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
  } catch (error) {
    store.status = error.message;
    return;
  }
  // A deleted way cannot be recreated with its id: logged, not undoable.
  // Logged before the fallible refresh — the deletion has committed.
  logPlain("Way deleted", `way/${selected.id}`, NETWORK_FEED);
  store.dirty = true;
  selectWay(null);
  try {
    await mapBridge.fetchNetwork();
    store.status = "";
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
  } catch (error) {
    store.status = error.message;
    return;
  }
  // Committed: log before the fallible refresh.
  logPlain("Network edits discarded", "", NETWORK_FEED);
  pushToast({ title: "network edits discarded" });
  selectWay(null);
  try {
    await mapBridge.fetchNetwork();
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
    // A failed new request must invalidate any prior resolved extract AND
    // any resolve still in flight, so the Download button can never act
    // on a stale area.
    invalidateResolve();
    store.network.acquire.resolving = false;
    store.network.acquire.resolved = null;
    store.network.acquire.error = "the current map view is not a valid area";
  }
}

export function resolveOsmByDrawn() {
  if (store.aoi) {
    resolveOsm(store.aoi);
    return;
  }
  invalidateResolve();
  store.network.acquire.resolving = false;
  store.network.acquire.resolved = null;
  store.network.acquire.error = "draw an area on the map first";
}

export function cancelAcquire() {
  invalidateResolve(); // a pending resolve must not repopulate the row
  store.network.acquire.resolving = false;
  store.network.acquire.resolved = null;
  store.network.acquire.error = "";
}

// Acquisitions have their own generation: a download begun before a
// session restore must not install its result into the restored
// workspace (the backend swap has already happened server-side, so a
// stale completion re-syncs availability instead of applying itself).
let acquireSeq = 0;

export function invalidateAcquire() {
  acquireSeq += 1;
}

export async function acquireOsm(discardEdits = false) {
  const net = store.network;
  const acquire = net.acquire;
  const resolved = acquire.resolved;
  if (!resolved || acquire.downloading) return;
  const seq = ++acquireSeq;
  acquire.downloading = true;
  acquire.error = "";
  try {
    const downloaded = await api("POST", "/api/osm/download", {
      bbox: resolved.bbox,
      url: resolved.url,
      discard_edits: discardEdits,
    });
    if (seq !== acquireSeq) {
      // A restore replaced the workspace mid-download. The backend has
      // already swapped to the downloaded extract (a true prevention
      // needs a backend-side abort); re-derive the client view from it
      // and say plainly what happened.
      acquire.downloading = false;
      store.network.loaded = false;
      logPlain("Extract replaced by an earlier download", downloaded.path.split("/").pop(), NETWORK_FEED);
      pushToast({
        title: "a download from the previous workspace finished",
        body: "it replaced the street network — swap again if unwanted",
      });
      await checkNetworkAvailable();
      return;
    }
    net.source = downloaded.path;
  } catch (error) {
    if (seq !== acquireSeq) {
      // a stale failed download has nothing to report to the new workspace
      acquire.downloading = false;
      return;
    }
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
  // The resolver's readable area name (e.g. "new-york"), not the crop
  // file's bbox_… name; the crop bbox becomes row metadata.
  net.displayName = extractDisplay(`${resolved.name}.osm.pbf`).name;
  net.bbox = resolved.bbox || null;
  selectWay(null);
  net.error = "";
  // The backend swap has committed: log it before the fallible render.
  logPlain("Extract swapped", resolved.name, NETWORK_FEED);
  try {
    await mapBridge.mapReady;
    await mapBridge.fetchNetwork();
    net.loaded = true;
    setStreetsVisible(net.visible);
    mapBridge.fitBbox(resolved.bbox);
    await mapBridge.refreshSummary(); // snapping is now available
    pushToast({ title: "loaded OSM extract", body: resolved.name });
  } catch (error) {
    net.error = error.message;
  } finally {
    acquire.downloading = false;
    acquire.resolved = null;
    acquire.place = "";
  }
}
