import { describe, expect, it } from "vitest";

import {
  MODES,
  UNKNOWN_MODE,
  UNKNOWN_MODE_COLOR,
  modeColorExpression,
  modeFilterExpression,
  presentModeCodes,
} from "../src/modes.js";

describe("modeColorExpression", () => {
  it("matches every mode code and falls back for unknown types", () => {
    const expression = modeColorExpression();
    expect(expression[0]).toBe("match");
    for (const mode of MODES) {
      const index = expression.indexOf(mode.code);
      expect(index).toBeGreaterThan(0);
      expect(expression[index + 1]).toBe(mode.color);
    }
    expect(expression[expression.length - 1]).toBe(UNKNOWN_MODE_COLOR);
  });

  it("uses distinct colors per mode", () => {
    const colors = MODES.map((mode) => mode.color);
    expect(new Set(colors).size).toBe(colors.length);
  });
});

describe("modeFilterExpression", () => {
  it("is null when nothing is hidden (clears the layer filter)", () => {
    expect(modeFilterExpression([])).toBeNull();
  });

  it("hides listed codes; unknown-mode shapes stay unless -1 is listed", () => {
    const filter = modeFilterExpression([3, 1]);
    expect(filter[0]).toBe("!");
    // unknown route_type coalesces to -1, which is not in this hidden list
    expect(filter[1][2]).toEqual(["literal", [3, 1]]);
  });

  it("hides unknown-mode shapes via the sentinel row", () => {
    // the legend's "other / unknown" row hides shapes with no route_type
    expect(UNKNOWN_MODE.code).toBe(-1);
    const filter = modeFilterExpression([UNKNOWN_MODE.code]);
    expect(filter[1][2]).toEqual(["literal", [-1]]);
  });
});

describe("presentModeCodes", () => {
  it("collects distinct route types, mapping missing ones to -1", () => {
    const features = [
      { properties: { route_type: 3 } },
      { properties: { route_type: 0 } },
      { properties: { route_type: 3 } },
      { properties: {} }, // hand-drawn shape without a resolved type
    ];
    expect(presentModeCodes(features)).toEqual([-1, 0, 3]);
  });

  it("is empty for an empty layer", () => {
    expect(presentModeCodes([])).toEqual([]);
  });
});
