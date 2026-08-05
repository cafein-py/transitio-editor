import { describe, expect, it } from "vitest";

import { redoButtonTitle, undoButtonTitle, undoShortcut } from "../src/undo.js";

describe("undoShortcut", () => {
  const base = { ctrlKey: true, metaKey: false, shiftKey: false };

  it("maps the usual chords", () => {
    expect(undoShortcut({ ...base, key: "z" })).toBe("undo");
    expect(undoShortcut({ ...base, key: "z", shiftKey: true })).toBe("redo");
    expect(undoShortcut({ ...base, key: "y" })).toBe("redo");
    // macOS Cmd works the same way
    expect(
      undoShortcut({
        key: "z",
        metaKey: true,
        ctrlKey: false,
        shiftKey: false,
      }),
    ).toBe("undo");
    expect(undoShortcut({ ...base, key: "Z", shiftKey: true })).toBe("redo");
  });

  it("ignores plain keys and form-field keystrokes", () => {
    expect(
      undoShortcut({ key: "z", ctrlKey: false, metaKey: false }),
    ).toBeNull();
    expect(undoShortcut({ ...base, key: "x" })).toBeNull();
    // undo inside a text box belongs to the text box
    expect(undoShortcut({ ...base, key: "z", targetTag: "input" })).toBeNull();
    expect(
      undoShortcut({ ...base, key: "z", targetTag: "TEXTAREA" }),
    ).toBeNull();
  });
});

describe("button titles", () => {
  it("name what would happen, or that nothing would", () => {
    expect(undoButtonTitle("drop_route")).toBe("undo drop_route");
    expect(undoButtonTitle(null)).toBe("nothing to undo");
    expect(redoButtonTitle("add_stop")).toBe("redo add_stop");
    expect(redoButtonTitle(null)).toBe("nothing to redo");
  });
});
