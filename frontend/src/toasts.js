// Toast notifications: a reactive queue the Toasts component renders.
// Confirmations carry at most one action (e.g. Undo); titles and bodies
// are stored as written and capitalized at render time.
import { reactive } from "vue";

const DEFAULT_DURATION = 6000;
const MAX_VISIBLE = 4;

export const toasts = reactive([]);

let nextId = 1;
const timers = new Map();

export function pushToast({ title, body = "", action = null, duration }) {
  const id = nextId++;
  toasts.push({ id, title, body, action });
  while (toasts.length > MAX_VISIBLE) {
    dismissToast(toasts[0].id);
  }
  const ms = duration ?? DEFAULT_DURATION;
  if (ms > 0) {
    timers.set(
      id,
      setTimeout(() => dismissToast(id), ms),
    );
  }
  return id;
}

export function dismissToast(id) {
  const index = toasts.findIndex((toast) => toast.id === id);
  if (index !== -1) toasts.splice(index, 1);
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }
}

// The action runs once; the toast leaves with it either way, so a slow
// or failing handler cannot be triggered twice.
export function runToastAction(id) {
  const toast = toasts.find((entry) => entry.id === id);
  if (!toast || !toast.action) return;
  const { run } = toast.action;
  dismissToast(id);
  run();
}

// Display rule from the design: sentence-case at render time.
export function capitalize(text) {
  const value = String(text ?? "");
  return value ? value[0].toUpperCase() + value.slice(1) : "";
}
