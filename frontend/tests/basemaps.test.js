import { describe, expect, it } from "vitest";

import {
  BASEMAPS,
  DEFAULT_BASEMAP,
  basemapLabel,
  basemapLayerId,
} from "../src/basemaps.js";

describe("BASEMAPS", () => {
  it("offers exactly the four styles, default among them", () => {
    const keys = BASEMAPS.map((basemap) => basemap.key);
    expect(keys).toEqual(["positron", "voyager", "osm", "dark"]);
    expect(keys).toContain(DEFAULT_BASEMAP);
    expect(BASEMAPS.map((basemap) => basemap.label)).toEqual([
      "CartoDB Positron",
      "Voyager",
      "OpenStreetMap",
      "Dark Matter",
    ]);
  });

  it("defaults to CartoDB Positron", () => {
    expect(DEFAULT_BASEMAP).toBe("positron");
    const positron = BASEMAPS.find((basemap) => basemap.key === "positron");
    expect(positron.tiles.every((url) => url.includes("light_all"))).toBe(true);
  });

  it("carries tiles and attribution for every entry", () => {
    for (const basemap of BASEMAPS) {
      expect(basemap.tiles.length).toBeGreaterThan(0);
      // every provider requires OSM attribution; Carto styles theirs too
      expect(basemap.attribution).toContain("OpenStreetMap");
      if (basemap.tiles[0].includes("cartocdn")) {
        expect(basemap.attribution).toContain("CARTO");
      }
    }
  });

  it("derives stable layer ids and labels", () => {
    expect(basemapLayerId("positron")).toBe("basemap-positron");
    expect(basemapLabel("positron")).toBe("CartoDB Positron");
    expect(basemapLabel("unknown-key")).toBe("unknown-key");
  });
});
