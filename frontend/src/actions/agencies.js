// Agencies-panel actions: the current feed's agency.txt rows and adding
// new agencies. Cross-feed listing and agency editing need backend
// endpoints that do not exist yet.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { logServerEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

let agenciesSeq = 0;

export async function loadAgencies() {
  const seq = ++agenciesSeq;
  try {
    const body = await api("GET", "/api/tables/agency.txt?limit=500");
    if (seq !== agenciesSeq) return;
    store.agencies = body.rows.map((row) => ({
      agencyId: String(row.agency_id ?? ""),
      name: String(row.agency_name ?? ""),
      url: String(row.agency_url ?? ""),
      timezone: String(row.agency_timezone ?? ""),
    }));
  } catch (error) {
    if (seq !== agenciesSeq) return;
    store.agencies = []; // no agency.txt yet
  }
}

export async function addAgency({ agencyId, name, url, timezone }) {
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  const missing = [
    !(agencyId || "").trim() && "agency_id",
    !(name || "").trim() && "name",
    !(url || "").trim() && "url",
    !(timezone || "").trim() && "timezone",
  ].filter(Boolean);
  if (missing.length) {
    pushToast({ title: `fill in ${missing.join(", ")}` });
    return false;
  }
  const feedId = store.currentFeedId;
  try {
    await api("POST", "/api/agencies", {
      agency_id: agencyId.trim(),
      agency_name: name.trim(),
      agency_url: url.trim(),
      agency_timezone: timezone.trim(),
    });
  } catch (error) {
    pushToast({ title: "agency not added", body: error.message });
    return false;
  }
  logServerEdit("Agency added", agencyId.trim(), feedId);
  pushToast({ title: "agency added", body: name.trim() });
  await loadAgencies();
  await mapBridge.refreshSummary();
  return true;
}
