import { describe, expect, it } from "vitest";

// The context-key matcher used by highlightContext: validation contexts
// carry GTFS snake_case keys (`stop_id`) as well as camelCase ones, and
// both must resolve to the same highlight.
function classifyContextKeys(context) {
  const stopIds = [];
  const shapeIds = [];
  for (const [key, value] of Object.entries(context)) {
    const flat = key.replace(/[^a-z]/gi, "").toLowerCase();
    if (flat.includes("stopid")) stopIds.push(String(value));
    if (flat.includes("shapeid")) shapeIds.push(String(value));
  }
  return { stopIds, shapeIds };
}

describe("validation context keys", () => {
  it("matches snake_case GTFS keys", () => {
    expect(classifyContextKeys({ stop_id: "S014" }).stopIds).toEqual(["S014"]);
    expect(classifyContextKeys({ shape_id: "1042" }).shapeIds).toEqual(["1042"]);
  });

  it("still matches camelCase keys", () => {
    expect(classifyContextKeys({ stopId: "S1" }).stopIds).toEqual(["S1"]);
    expect(classifyContextKeys({ shapeId: "9" }).shapeIds).toEqual(["9"]);
  });

  it("ignores unrelated context keys", () => {
    const { stopIds, shapeIds } = classifyContextKeys({
      distance_m: 184,
      csvRowNumber: 3,
      stop_sequence: 2,
    });
    expect(stopIds).toEqual([]);
    expect(shapeIds).toEqual([]);
  });
});
