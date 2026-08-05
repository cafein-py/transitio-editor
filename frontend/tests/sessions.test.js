import { describe, expect, it } from "vitest";

import {
  restoreSessionStatus,
  saveSessionStatus,
  sessionRestorePlan,
  sessionView,
} from "../src/sessions.js";

describe("sessionView", () => {
  it("captures the map-only state, with the working panel", () => {
    const state = {
      basemap: "dark",
      hiddenModes: [-1, 4],
      shapeColorBy: "feed",
      stopsVisible: false,
      workingPanel: "validate",
      activePanel: "data", // the neutral home — not recorded
    };
    const camera = { center: [24.9, 60.2], zoom: 9 };
    expect(sessionView(state, camera)).toEqual({
      camera,
      basemap: "dark",
      hidden_modes: [-1, 4],
      shape_color_by: "feed",
      stops_visible: false,
      active_tab: "validate",
    });
  });

  it("falls back to the Data panel when nothing else was visited", () => {
    expect(sessionView({ hiddenModes: [] }, null).active_tab).toBe("data");
  });
});

describe("sessionRestorePlan", () => {
  it("plans every recognised field", () => {
    const plan = sessionRestorePlan({
      basemap: "voyager",
      hidden_modes: [0, 3, "bad"],
      shape_color_by: "feed",
      stops_visible: false,
      active_tab: "validate",
      camera: { center: [24.9, 60.2], zoom: 9 },
    });
    expect(plan).toEqual({
      basemap: "voyager",
      hiddenModes: [0, 3], // non-numbers dropped
      shapeColorBy: "feed",
      stopsVisible: false,
      activePanel: "validate",
      camera: { center: [24.9, 60.2], zoom: 9 },
    });
  });

  it("maps pre-redesign tab names to their panels", () => {
    expect(sessionRestorePlan({ active_tab: "view" }).activePanel).toBe("data");
    expect(sessionRestorePlan({ active_tab: "network" }).activePanel).toBe(
      "streets",
    );
    expect(sessionRestorePlan({ active_tab: "report" }).activePanel).toBe(
      "validate",
    );
    expect(sessionRestorePlan({ active_tab: "catalogue" }).activePanel).toBe(
      "data",
    );
  });

  it("fits to the feeds when the camera is missing or malformed", () => {
    expect(sessionRestorePlan({}).fit).toBe(true);
    expect(sessionRestorePlan({ camera: { zoom: 9 } }).fit).toBe(true);
    expect(
      sessionRestorePlan({ camera: { center: ["a", "b"], zoom: 9 } }).fit,
    ).toBe(true);
    // non-finite numbers and impossible latitudes would throw in MapLibre
    expect(
      sessionRestorePlan({ camera: { center: [24.9, 100], zoom: 9 } }).fit,
    ).toBe(true);
    expect(
      sessionRestorePlan({ camera: { center: [1e999, 60], zoom: 9 } }).fit,
    ).toBe(true);
  });

  it("ignores unknown fields and bad values", () => {
    const plan = sessionRestorePlan({
      shape_color_by: "rainbow",
      active_tab: "hand-edited-nonsense", // would blank every panel
      future_field: 42,
    });
    expect(plan.shapeColorBy).toBeUndefined();
    expect(plan.activePanel).toBeUndefined();
    expect(plan).not.toHaveProperty("future_field");
  });
});

describe("session status lines", () => {
  it("names embedded and referenced feeds on save", () => {
    expect(saveSessionStatus({ embedded: ["Merged"], referenced: [] })).toBe(
      "session saved — 1 feed embedded",
    );
    expect(
      saveSessionStatus({ embedded: [], referenced: ["a", "b"] }),
    ).toContain("2 referenced by path");
    // the standing limitation is stated at save time
    expect(saveSessionStatus({ referenced: ["a"] })).toContain("not captured");
  });

  it("reports restored, skipped and warned separately", () => {
    expect(restoreSessionStatus({ feeds: [{}, {}] })).toBe("restored 2 feeds");
    expect(
      restoreSessionStatus({
        feeds: [{}],
        skipped: [{ name: "Gone", reason: "file not found" }],
        warnings: ["city.zip: changed since the session was saved"],
      }),
    ).toBe(
      "restored 1 feed — skipped: Gone (file not found) — " +
        "city.zip: changed since the session was saved",
    );
    expect(restoreSessionStatus({})).toBe("nothing restored");
  });
});
