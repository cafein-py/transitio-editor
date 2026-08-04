import { describe, expect, it } from "vitest";

import {
  currentFeed,
  feedModes,
  feedTableSummary,
  initialTab,
  mergeStatus,
} from "../src/catalogue.js";

describe("feedTableSummary", () => {
  it("pluralizes counts and defaults missing tables to zero", () => {
    // counts are keyed by GTFS filename, matching the catalogue API
    expect(
      feedTableSummary({ "stops.txt": 12, "routes.txt": 3 }),
    ).toBe("12 stops, 3 routes");
    expect(
      feedTableSummary({ "stops.txt": 1, "routes.txt": 1 }),
    ).toBe("1 stop, 1 route");
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

describe("initialTab", () => {
  it("starts on the data when a feed is loaded", () => {
    expect(initialTab([{ feed_id: "feed-1", source: "/feeds/hsl.zip" }])).toBe("view");
    // a feed built in the GUI has no source file but does have tables
    expect(initialTab([{ feed_id: "feed-1", tables: { "stops.txt": 2 } }])).toBe(
      "view",
    );
  });

  it("starts on Search with nothing to show", () => {
    // launching without a feed registers an empty builder to build on
    expect(initialTab([{ feed_id: "feed-1", source: null, tables: {} }])).toBe(
      "search",
    );
    expect(initialTab([])).toBe("search");
    expect(initialTab(undefined)).toBe("search");
  });
});

describe("mergeStatus", () => {
  it("names the merged feed and any files the merge dropped", () => {
    expect(mergeStatus("HSL + Metro", [])).toBe('merged into "HSL + Metro"');
    expect(mergeStatus("HSL + Metro", undefined)).toBe('merged into "HSL + Metro"');
    expect(
      mergeStatus("Combined", ["feed_info.txt", "translations.txt"]),
    ).toBe(
      'merged into "Combined" — feed_info.txt, translations.txt not carried over',
    );
  });

  it("names the file it was saved to", () => {
    expect(mergeStatus("Combined", [], "/data/Combined.zip")).toBe(
      'merged into "Combined", saved to /data/Combined.zip',
    );
    expect(mergeStatus("Combined", ["feed_info.txt"], "/data/Combined.zip")).toBe(
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
