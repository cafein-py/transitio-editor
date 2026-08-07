import { describe, expect, it } from "vitest";

import {
  clampPage,
  filterItems,
  pageLabel,
  pageOf,
  pageSlice,
} from "../src/listing.js";

const stops = [
  { id: "S001", name: "Times Sq" },
  { id: "S002", name: "Grand Central" },
  { id: "S003", name: "Union Sq" },
];
const fields = (stop) => [stop.id, stop.name];

describe("filterItems", () => {
  it("matches case-insensitively over any field", () => {
    expect(filterItems(stops, "sq", fields)).toHaveLength(2);
    expect(filterItems(stops, "s002", fields)).toHaveLength(1);
    expect(filterItems(stops, "", fields)).toHaveLength(3);
    expect(filterItems(stops, "  ", fields)).toHaveLength(3);
  });

  it("survives null field values", () => {
    expect(
      filterItems([{ id: null, name: "x" }], "x", (s) => [s.id, s.name]),
    ).toHaveLength(1);
  });
});

describe("paging", () => {
  const items = Array.from({ length: 30 }, (_, i) => i);

  it("slices the requested window", () => {
    expect(pageSlice(items, 0, 12)).toHaveLength(12);
    expect(pageSlice(items, 2, 12)).toEqual([24, 25, 26, 27, 28, 29]);
  });

  it("clamps out-of-range pages instead of going blank", () => {
    expect(clampPage(5, 30, 12)).toBe(2);
    expect(clampPage(-1, 30, 12)).toBe(0);
    expect(clampPage(0, 0, 12)).toBe(0);
    expect(pageSlice(items, 99, 12)).toEqual([24, 25, 26, 27, 28, 29]);
  });

  it("labels the visible window", () => {
    expect(pageLabel(0, 38, 12, "matches")).toBe("1–12 of 38 matches");
    expect(pageLabel(3, 38, 12, "matches")).toBe("37–38 of 38 matches");
    expect(pageLabel(0, 0, 12, "routes")).toBe("no routes");
  });

  it("finds the page containing a row", () => {
    expect(pageOf(0, 12)).toBe(0);
    expect(pageOf(11, 12)).toBe(0);
    expect(pageOf(12, 12)).toBe(1);
    expect(pageOf(-1, 12)).toBe(0);
  });
});
