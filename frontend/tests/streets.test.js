import { describe, expect, it } from "vitest";

import {
  bboxLabel,
  classCounts,
  classFilter,
  classOfHighway,
  DEFAULT_HIDDEN_CLASSES,
  extractDisplay,
  HIGHWAY_CLASSES,
  lineLengthKm,
  wayClass,
  wayHighway,
} from "../src/streets.js";

describe("class detection", () => {
  it("keeps the nine design classes and folds links into parents", () => {
    expect(HIGHWAY_CLASSES).toHaveLength(9);
    expect(classOfHighway("motorway")).toBe("motorway");
    expect(classOfHighway("motorway_link")).toBe("motorway");
    expect(classOfHighway("living_street")).toBe("residential");
    expect(classOfHighway("path")).toBe("footway");
    expect(classOfHighway("track")).toBe("service");
  });

  it("files unknown values under service", () => {
    expect(classOfHighway("proposed")).toBe("service");
    expect(classOfHighway("")).toBe("service");
  });

  it("reads the highway value from a column or the tags dict", () => {
    expect(wayHighway({ highway: "primary" })).toBe("primary");
    expect(wayHighway({ tags: { highway: "cycleway" } })).toBe("cycleway");
    // MapLibre stringifies nested properties on rendered features
    expect(wayHighway({ tags: '{"highway": "footway"}' })).toBe("footway");
    expect(wayHighway({ tags: "not json" })).toBeNull();
    expect(wayHighway({})).toBeNull();
  });

  it("classes a feature's properties", () => {
    expect(wayClass({ highway: "secondary_link" })).toBe("secondary");
    expect(wayClass({})).toBe("service");
  });
});

describe("service and footway start hidden", () => {
  it("matches the design default", () => {
    expect(DEFAULT_HIDDEN_CLASSES.sort()).toEqual(["footway", "service"]);
  });
});

describe("extractDisplay", () => {
  it("prettifies region file names", () => {
    expect(extractDisplay("/cache/new-york-latest.osm.pbf")).toEqual({
      name: "New York",
      bbox: null,
    });
    expect(extractDisplay("finland.osm.pbf").name).toBe("Finland");
  });

  it("parses map-view crop names into a bbox", () => {
    const parsed = extractDisplay(
      "/cache/bbox_-74.00303_40.72966_-73.93_40.8.osm.pbf",
    );
    expect(parsed.name).toBeNull();
    expect(parsed.bbox).toEqual([-74.00303, 40.72966, -73.93, 40.8]);
  });

  it("handles nothing loaded", () => {
    expect(extractDisplay(null)).toEqual({ name: null, bbox: null });
  });
});

describe("bboxLabel", () => {
  it("rounds to a compact chip label", () => {
    expect(bboxLabel([-74.00303, 40.72966, -73.93, 40.8])).toBe(
      "-74.003, 40.730 → -73.930, 40.800",
    );
    expect(bboxLabel(null)).toBeNull();
  });
});

describe("lineLengthKm", () => {
  it("measures a known distance", () => {
    // one degree of latitude ≈ 111.2 km
    const km = lineLengthKm([
      [24.9, 60.0],
      [24.9, 61.0],
    ]);
    expect(km).toBeGreaterThan(110);
    expect(km).toBeLessThan(112);
    expect(lineLengthKm([])).toBe(0);
    expect(lineLengthKm([[24.9, 60.0]])).toBe(0);
  });
});

describe("classCounts", () => {
  it("counts ways per display class", () => {
    const counts = classCounts([
      { properties: { highway: "primary" } },
      { properties: { highway: "primary_link" } },
      { properties: { tags: { highway: "footway" } } },
      { properties: {} },
    ]);
    expect(counts.primary).toBe(2);
    expect(counts.footway).toBe(1);
    expect(counts.service).toBe(1);
    expect(counts.motorway).toBe(0);
  });
});

describe("classFilter", () => {
  it("owns each raw value in exactly one class filter", () => {
    // the service catch-all must not also match named classes
    const service = classFilter("service");
    expect(service[0]).toBe("all");
    const primary = classFilter("primary");
    expect(primary[0]).toBe("match");
    expect(primary[2]).toContain("primary_link");
  });
});
