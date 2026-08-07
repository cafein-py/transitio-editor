// Stop-card actions: applying the card's edits to the current feed.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { logServerEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

// "lat, lon" as typed in the card's combined field, or null.
export function parseLatLon(text) {
  const parts = String(text || "").split(",");
  if (parts.length !== 2) return null;
  const lat = Number(parts[0].trim());
  const lon = Number(parts[1].trim());
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { lat, lon };
}

export async function applyStopEdits({ stopId, name, latLon }) {
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  if (store.historyBusy) {
    pushToast({ title: "an undo is still running" });
    return false;
  }
  const feedId = store.currentFeedId;
  const body = { stop_name: name };
  if (latLon) {
    const parsed = parseLatLon(latLon);
    if (!parsed) {
      pushToast({
        title: "coordinates not applied",
        body: "use latitude, longitude",
      });
      return false;
    }
    body.stop_lat = parsed.lat;
    body.stop_lon = parsed.lon;
  }
  try {
    await api("PATCH", `/api/stops/${encodeURIComponent(stopId)}`, body);
  } catch (error) {
    pushToast({ title: "stop not updated", body: error.message });
    return false;
  }
  logServerEdit("Stop updated", stopId, feedId);
  store.dirty = true;
  if (store.report) store.reportStale = true;
  await mapBridge.refreshAll(false);
  return true;
}
