// The unified search behind the landing page and the ⌘K palette: one
// query fans out to the Mobility Database (feeds + a geocoded place) and
// the OSM extract resolver. Results land in store.search so the existing
// download machinery (single, bulk, folder, crop) keeps working.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { invalidateResolve, resolveOsm } from "./streets.js";
import { store } from "../store.js";

let searchSeq = 0;

// Like the old runSearch, but the place is stored for its own result row
// instead of flying the map immediately.
export async function paletteSearch(query, bbox = null) {
  const s = store.search;
  const seq = ++searchSeq;
  s.searching = true;
  s.selected = [];
  try {
    const params = new URLSearchParams();
    const q = (query || "").trim();
    if (q) params.set("q", q);
    else if (bbox) params.set("bbox", bbox.join(","));
    else return;
    params.set("limit", String(s.limit));
    if (s.officialOnly) params.set("official", "true");
    const body = await api("GET", `/api/search?${params.toString()}`);
    if (seq !== searchSeq) return;
    s.results = body.feeds;
    s.csvFallback = body.csv_fallback;
    s.place = body.place || null;
    s.searched = true;
  } catch (error) {
    if (seq !== searchSeq) return;
    s.results = [];
    s.place = null;
    s.searched = false;
    store.status = error.message;
  } finally {
    if (seq === searchSeq) s.searching = false;
  }
}

// Both providers at once; the OSM resolver keeps its own sequence guard.
export function unifiedSearch(query, bbox = null) {
  const q = (query || "").trim();
  if (q) resolveOsm(q);
  return paletteSearch(q, bbox);
}

export function clearUnifiedSearch() {
  searchSeq += 1;
  const s = store.search;
  s.q = "";
  s.results = [];
  s.place = null;
  s.searched = false;
  s.selected = [];
  // The invalidated request can no longer clear this itself.
  s.searching = false;
  // The OSM resolver runs its own sequence; a pending resolve from the
  // cleared query must not repopulate the extract row.
  invalidateResolve();
  store.network.acquire.resolving = false;
  store.network.acquire.resolved = null;
  store.network.acquire.error = "";
}

export function flyToPlace(place) {
  if (place && place.bbox) mapBridge.fitBbox(place.bbox);
  store.paletteOpen = false;
}

// The "Already on this machine" section: GTFS zips in the chosen folder.
let localSeq = 0;

export async function listLocalFeeds(path) {
  const seq = ++localSeq;
  try {
    const query = path ? `?path=${encodeURIComponent(path)}` : "";
    const listing = await api("GET", `/api/fs/dirs${query}`);
    if (seq !== localSeq) return null;
    return { path: listing.path, feeds: listing.feeds || [] };
  } catch (error) {
    if (seq !== localSeq) return null;
    return { path: path || "", feeds: [], error: error.message };
  }
}
