// Map view-state actions: layer visibility, mode filtering and shape
// colouring. Pure view state — none of this is logged to the session.
import * as mapBridge from "../map.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";

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

// Double-clicking a mode chip solos it: every other mode goes dark, and
// the toast's action really brings them all back.
export function soloMode(code, label) {
  const others = [...MODES.map((mode) => mode.code), UNKNOWN_MODE.code].filter(
    (candidate) => candidate !== code,
  );
  store.hiddenModes.splice(0, store.hiddenModes.length, ...others);
  mapBridge.setHiddenModes([...store.hiddenModes]);
  pushToast({
    title: `showing only ${label}`,
    action: { label: "show all", run: () => setAllModesHidden(false) },
  });
}
