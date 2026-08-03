import { describe, expect, it } from "vitest";

import {
  MODES,
  UNKNOWN_MODE_COLOR,
  modeColorExpression,
  modeFilterExpression,
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

  it("hides listed codes but keeps unknown-mode shapes visible", () => {
    const filter = modeFilterExpression([3, 1]);
    expect(filter[0]).toBe("!");
    // unknown route_type coalesces to -1, which is not in the hidden list
    expect(filter[1][2]).toEqual(["literal", [3, 1]]);
  });
});
