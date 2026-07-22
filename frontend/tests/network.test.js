import { describe, expect, it } from "vitest";

import { editTarget, networkTags } from "../src/network.js";

describe("editTarget", () => {
  it("targets the network only on the Network tab, else the feed", () => {
    expect(editTarget("network")).toBe("network");
    expect(editTarget("edit")).toBe("feed");
    expect(editTarget("catalogue")).toBe("feed");
    expect(editTarget("report")).toBe("feed");
  });
});

describe("networkTags", () => {
  it("merges the tags dict with promoted columns, dropping structural keys", () => {
    expect(
      networkTags({
        id: 123,
        osm_type: "way",
        version: 3,
        nodes: [1, 2],
        highway: "residential",
        tags: { maxspeed: "30", surface: "asphalt" },
      }),
    ).toEqual([
      ["highway", "residential"],
      ["maxspeed", "30"],
      ["surface", "asphalt"],
    ]);
  });

  it("parses a stringified tags dict (as MapLibre delivers it on click)", () => {
    expect(
      networkTags({ id: 1, osm_type: "node", tags: '{"highway":"crossing"}' }),
    ).toEqual([["highway", "crossing"]]);
    expect(networkTags({ id: 1, tags: "not json" })).toEqual([]);
  });

  it("skips null values and tolerates missing properties", () => {
    expect(networkTags({ id: 1, name: null, oneway: "yes" })).toEqual([
      ["oneway", "yes"],
    ]);
    expect(networkTags(null)).toEqual([]);
  });
});
