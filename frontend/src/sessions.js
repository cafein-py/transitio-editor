// Pure session helpers: what a save captures, how a restore is applied,
// and the status lines. The API treats the view object as opaque JSON,
// so the field-by-field logic lives here where it is testable.

// The view state a session records — everything the map cannot rebuild
// from the data alone. `workingPanel` is the panel the user was actually
// in (the Data panel is the neutral home and would otherwise always be
// the recorded one).
export function sessionView(state, camera) {
  return {
    camera, // { center: [lng, lat], zoom }
    basemap: state.basemap,
    hidden_modes: [...state.hiddenModes],
    shape_color_by: state.shapeColorBy,
    stops_visible: state.stopsVisible,
    network_visible: state.network ? state.network.visible : undefined,
    active_tab: state.workingPanel || "data",
    // the user-given street-network name lives client-side only
    network_name:
      (state.network && state.network.displayName) || undefined,
  };
}

// The decision table for applying a restored view: which setters run,
// with what, and whether the camera jumps or falls back to fitting the
// restored feeds (sessions predating the camera field). Unknown fields
// are ignored, so the format can grow.
export function sessionRestorePlan(view) {
  const plan = {};
  if (typeof view.basemap === "string") plan.basemap = view.basemap;
  if (Array.isArray(view.hidden_modes)) {
    plan.hiddenModes = view.hidden_modes.filter(
      (code) => typeof code === "number",
    );
  }
  if (view.shape_color_by === "mode" || view.shape_color_by === "feed") {
    plan.shapeColorBy = view.shape_color_by;
  }
  if (typeof view.stops_visible === "boolean") {
    plan.stopsVisible = view.stops_visible;
  }
  if (typeof view.network_visible === "boolean") {
    plan.networkVisible = view.network_visible;
  }
  const PANELS = [
    "data",
    "stops",
    "routes",
    "cal",
    "trips",
    "agencies",
    "streets",
    "validate",
  ];
  // Sessions from before the redesign recorded tab names; map them to the
  // panel that took the tab's place (the search tab became the palette).
  const LEGACY_TABS = {
    search: "data",
    catalogue: "data",
    view: "data",
    network: "streets",
    report: "validate",
  };
  const panel = LEGACY_TABS[view.active_tab] || view.active_tab;
  if (PANELS.includes(panel)) plan.activePanel = panel;
  const camera = view.camera;
  if (
    camera &&
    Array.isArray(camera.center) &&
    camera.center.length === 2 &&
    camera.center.every((value) => Number.isFinite(value)) &&
    Math.abs(camera.center[1]) <= 90 && // a latitude MapLibre accepts
    Number.isFinite(camera.zoom)
  ) {
    plan.camera = { center: camera.center, zoom: camera.zoom };
  } else {
    plan.fit = true;
  }
  return plan;
}

// The save status line: what the session holds, and the standing
// limitation that referenced feeds are captured by path, not by state.
export function saveSessionStatus(result) {
  const embedded = (result && result.embedded) || [];
  const referenced = (result && result.referenced) || [];
  const parts = [`session saved`];
  if (embedded.length) {
    parts.push(
      `${embedded.length} feed${embedded.length === 1 ? "" : "s"} embedded`,
    );
  }
  const missing = (result && result.missing) || [];
  if (missing.length) {
    parts.push(`missing on disk (cannot restore): ${missing.join(", ")}`);
  }
  if (referenced.length) {
    parts.push(
      `${referenced.length} referenced by path (edits made since those ` +
        `files were written are not captured)`,
    );
  }
  return parts.join(" — ");
}

// The restore status line: restored, skipped and warned, separately.
export function restoreSessionStatus(result) {
  const feeds = (result && result.feeds) || [];
  const skipped = (result && result.skipped) || [];
  const warnings = (result && result.warnings) || [];
  const parts = [
    feeds.length
      ? `restored ${feeds.length} feed${feeds.length === 1 ? "" : "s"}`
      : "nothing restored",
  ];
  if (skipped.length) {
    parts.push(
      `skipped: ${skipped.map((s) => `${s.name} (${s.reason})`).join(", ")}`,
    );
  }
  if (warnings.length) parts.push(warnings.join("; "));
  return parts.join(" — ");
}
