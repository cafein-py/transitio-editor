import { describe, expect, it } from "vitest";

import { parseLatLon } from "../src/actions/stops.js";

describe("parseLatLon", () => {
  it("parses the card's combined field", () => {
    expect(parseLatLon("40.71714, -73.80923")).toEqual({
      lat: 40.71714,
      lon: -73.80923,
    });
    expect(parseLatLon(" 60.2 , 24.9 ")).toEqual({ lat: 60.2, lon: 24.9 });
  });

  it("rejects malformed or out-of-range input", () => {
    expect(parseLatLon("60.2")).toBeNull();
    expect(parseLatLon("a, b")).toBeNull();
    expect(parseLatLon("95, 24")).toBeNull();
    expect(parseLatLon("60, 185")).toBeNull();
    expect(parseLatLon("")).toBeNull();
  });
});
