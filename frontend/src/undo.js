// Pure helpers for the undo/redo UI: shortcut classification and button
// labels, testable without a DOM.

// What a keydown means: "undo", "redo", or null. Cmd on macOS, Ctrl
// elsewhere; Shift flips undo into redo (Ctrl+Y works too). Keystrokes
// inside form fields belong to the field, not the map.
export function undoShortcut(event) {
  const modifier = event.metaKey || event.ctrlKey;
  if (!modifier) return null;
  const tag = (event.targetTag || "").toUpperCase();
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return null;
  const key = (event.key || "").toLowerCase();
  if (key === "z") return event.shiftKey ? "redo" : "undo";
  if (key === "y") return "redo";
  return null;
}

export function undoButtonTitle(label) {
  return label ? `undo ${label}` : "nothing to undo";
}

export function redoButtonTitle(label) {
  return label ? `redo ${label}` : "nothing to redo";
}
