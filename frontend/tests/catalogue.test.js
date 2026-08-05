import { describe, expect, it } from "vitest";

import {
  cropRequestBody,
  cropShapeFromRing,
  cropStatus,
  currentFeed,
  feedModes,
  feedTableSummary,
  groupedCatalogue,
  initialPanel,
  mergeStatus,
  moveFeedToGroup,
} from "../src/catalogue.js";

describe("feedTableSummary", () => {
  it("pluralizes counts and defaults missing tables to zero", () => {
    // counts are keyed by GTFS filename, matching the catalogue API
    expect(feedTableSummary({ "stops.txt": 12, "routes.txt": 3 })).toBe(
      "12 stops, 3 routes",
    );
    expect(feedTableSummary({ "stops.txt": 1, "routes.txt": 1 })).toBe(
      "1 stop, 1 route",
    );
    expect(feedTableSummary({})).toBe("0 stops, 0 routes");
    expect(feedTableSummary(undefined)).toBe("0 stops, 0 routes");
  });
});

describe("currentFeed", () => {
  const catalogue = [
    { feed_id: "feed-1", name: "buses" },
    { feed_id: "feed-2", name: "underground" },
  ];

  it("returns the entry matching the current id", () => {
    expect(currentFeed(catalogue, "feed-2").name).toBe("underground");
  });

  it("returns null when nothing matches or no current is set", () => {
    expect(currentFeed(catalogue, "feed-9")).toBeNull();
    expect(currentFeed(catalogue, null)).toBeNull();
    expect(currentFeed([], "feed-1")).toBeNull();
  });
});

describe("initialPanel", () => {
  it("starts on the data when a feed is loaded", () => {
    expect(
      initialPanel([{ feed_id: "feed-1", source: "/feeds/hsl.zip" }]),
    ).toBe("data");
    // a feed built in the GUI has no source file but does have tables
    expect(
      initialPanel([{ feed_id: "feed-1", tables: { "stops.txt": 2 } }]),
    ).toBe("data");
  });

  it("starts on Search with nothing to show", () => {
    // launching without a feed registers an empty builder to build on
    expect(
      initialPanel([{ feed_id: "feed-1", source: null, tables: {} }]),
    ).toBe("search");
    expect(initialPanel([])).toBe("search");
    expect(initialPanel(undefined)).toBe("search");
  });
});

describe("mergeStatus", () => {
  it("names the merged feed and any files the merge dropped", () => {
    expect(mergeStatus("HSL + Metro", [])).toBe('merged into "HSL + Metro"');
    expect(mergeStatus("HSL + Metro", undefined)).toBe(
      'merged into "HSL + Metro"',
    );
    expect(mergeStatus("Combined", ["feed_info.txt", "translations.txt"])).toBe(
      'merged into "Combined" — feed_info.txt, translations.txt not carried over',
    );
  });

  it("names the file it was saved to", () => {
    expect(mergeStatus("Combined", [], "/data/Combined.zip")).toBe(
      'merged into "Combined", saved to /data/Combined.zip',
    );
    expect(
      mergeStatus("Combined", ["feed_info.txt"], "/data/Combined.zip"),
    ).toBe(
      'merged into "Combined", saved to /data/Combined.zip — feed_info.txt not carried over',
    );
  });
});

describe("feedModes", () => {
  it("maps present mode codes to legend entries, skipping unknown codes", () => {
    const chips = feedModes([0, 3, 99]);
    expect(chips.map((mode) => mode.label)).toEqual(["tram", "bus"]);
    expect(chips.every((mode) => mode.color)).toBe(true);
  });

  it("is empty without modes", () => {
    expect(feedModes([])).toEqual([]);
    expect(feedModes(undefined)).toEqual([]);
  });
});

describe("groupedCatalogue", () => {
  const feeds = [
    { feed_id: "a", group: "Cropped feeds" },
    { feed_id: "b", group: null },
    { feed_id: "c", group: "Cropped feeds" },
    { feed_id: "d", group: "gone" },
  ];

  it("lists a section per known group, in order, then the rest", () => {
    const { sections, ungrouped } = groupedCatalogue(feeds, [
      "Cropped feeds",
      "Empty",
    ]);
    expect(sections.map((s) => s.name)).toEqual(["Cropped feeds", "Empty"]);
    expect(sections[0].feeds.map((f) => f.feed_id)).toEqual(["a", "c"]);
    // an empty group survives: it is still a drop target
    expect(sections[1].feeds).toEqual([]);
    // "d" names a group that no longer exists, so it reads as ungrouped
    expect(ungrouped.map((f) => f.feed_id)).toEqual(["b", "d"]);
  });

  it("copes with an empty or missing catalogue", () => {
    expect(groupedCatalogue([], ["G"]).sections[0].feeds).toEqual([]);
    expect(groupedCatalogue(undefined, undefined).ungrouped).toEqual([]);
  });
});

describe("moveFeedToGroup", () => {
  it("describes the move, or nothing when it would not change", () => {
    const feed = { feed_id: "a", group: "One" };
    expect(moveFeedToGroup(feed, "Two")).toEqual({
      feed_id: "a",
      group: "Two",
    });
    expect(moveFeedToGroup(feed, null)).toEqual({ feed_id: "a", group: null });
    expect(moveFeedToGroup(feed, "One")).toBeNull();
    expect(moveFeedToGroup({ feed_id: "b", group: null }, null)).toBeNull();
    expect(moveFeedToGroup(undefined, "One")).toBeNull();
  });
});

describe("cropRequestBody", () => {
  const shape = { type: "Polygon", coordinates: [[]] };

  it("carries the shape and the tab's options", () => {
    expect(
      cropRequestBody(shape, { group: " Cropped feeds ", fullTripsOnly: true }),
    ).toEqual({ shape, full_trips_only: true, group: "Cropped feeds" });
    // a blank group leaves the server's default in place
    expect(cropRequestBody(shape, { group: "  " })).toEqual({
      shape,
      full_trips_only: false,
    });
  });

  it("is nothing without a drawn shape", () => {
    expect(cropRequestBody(null, { group: "x" })).toBeNull();
  });
});

describe("cropStatus", () => {
  it("reports created, empty and failed feeds separately", () => {
    expect(cropStatus({ feeds: [{}, {}], empty: [], skipped: [] })).toBe(
      "cropped 2 feeds",
    );
    expect(cropStatus({ feeds: [{}], empty: ["Far"], skipped: [] })).toBe(
      "cropped 1 feed — Far came back empty",
    );
    expect(
      cropStatus({
        feeds: [],
        empty: [],
        skipped: [{ name: "Broken", reason: "bad zip" }],
      }),
    ).toBe("nothing cropped — failed: Broken (bad zip)");
    expect(cropStatus({})).toBe("nothing cropped");
  });
});

describe("cropShapeFromRing", () => {
  const helsinki = [
    [24.9, 60.1],
    [25.0, 60.1],
    [25.0, 60.2],
    [24.9, 60.2],
  ];

  it("closes an ordinary ring untouched", () => {
    const { shape, error } = cropShapeFromRing(helsinki);
    expect(error).toBeUndefined();
    expect(shape.type).toBe("Polygon");
    // closed, and the eastern longitudes are left where they were
    expect(shape.coordinates[0]).toHaveLength(5);
    expect(shape.coordinates[0][0]).toEqual([24.9, 60.1]);
    expect(shape.coordinates[0][4]).toEqual([24.9, 60.1]);
  });

  it("shifts a ring drawn on another world copy back as a whole", () => {
    // the same area on MapLibre's next copy of the world
    const { shape } = cropShapeFromRing(
      helsinki.map(([lng, lat]) => [lng + 360, lat]),
    );
    shape.coordinates[0].slice(0, 4).forEach(([lng, lat], index) => {
      expect(lng).toBeCloseTo(helsinki[index][0], 9);
      expect(lat).toBe(helsinki[index][1]);
    });
  });

  it("refuses areas it cannot express", () => {
    // MapLibre reports a drag across the antimeridian continuously, so
    // the ring runs past 180 rather than wrapping
    expect(
      cropShapeFromRing([
        [179.5, 10],
        [180.5, 10],
        [180.5, 11],
      ]).error,
    ).toMatch(/antimeridian/);
    expect(cropShapeFromRing([[0, 0]]).error).toMatch(/three corners/);
    expect(cropShapeFromRing(null).error).toMatch(/three corners/);
  });
});
