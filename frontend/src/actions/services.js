// Cal-panel actions: the current feed's services from calendar.txt and
// adding new ones. Editing/deleting a service has no backend endpoint
// yet — the form's Save changes/Delete sit disabled until it does.
import { api } from "../api.js";
import * as mapBridge from "../map.js";
import { dayNames, serviceRows } from "../services.js";
import { logServerEdit } from "../session.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

let servicesSeq = 0;

export async function loadServices() {
  const seq = ++servicesSeq;
  try {
    const body = await api("GET", "/api/tables/calendar.txt?limit=2000");
    if (seq !== servicesSeq) return;
    store.services = serviceRows(body.rows);
  } catch (error) {
    if (seq !== servicesSeq) return;
    store.services = []; // no calendar.txt yet
  }
}

export async function addService({ serviceId, days, from, to }) {
  if (!store.editMode) {
    pushToast({ title: "turn on editing first" });
    return false;
  }
  const id = (serviceId || "").trim();
  if (!id) {
    pushToast({ title: "give the service an id first" });
    return false;
  }
  const names = dayNames(days);
  if (!names.length) {
    pushToast({ title: "pick at least one day" });
    return false;
  }
  const feedId = store.currentFeedId;
  try {
    await api("POST", "/api/services", {
      service_id: id,
      days: names,
      start_date: from,
      end_date: to,
    });
  } catch (error) {
    pushToast({ title: "service not added", body: error.message });
    return false;
  }
  logServerEdit("Service added", id, feedId);
  pushToast({ title: "service added", body: id });
  await loadServices();
  await mapBridge.refreshSummary();
  return true;
}
