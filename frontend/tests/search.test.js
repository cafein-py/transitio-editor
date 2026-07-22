import { describe, expect, it } from "vitest";

import { feedLocation, safeHttpUrl, sortFeeds } from "../src/search.js";

const feed = (provider, locations, status = "active") => ({
  id: provider.toLowerCase(),
  provider,
  status,
  locations,
});

describe("feedLocation", () => {
  it("joins each location most-specific first, feeds' locations with ';'", () => {
    expect(
      feedLocation({
        locations: [
          { municipality: "Helsinki", subdivision: "Uusimaa", country: "FI" },
        ],
      }),
    ).toBe("Helsinki, Uusimaa, FI");
    expect(
      feedLocation({
        locations: [
          { municipality: "Helsinki", country: "FI" },
          { subdivision: "Skåne", country: "SE" },
        ],
      }),
    ).toBe("Helsinki, FI; Skåne, SE");
  });

  it("falls back to a dash when nothing is known", () => {
    expect(feedLocation({ locations: [] })).toBe("—");
    expect(feedLocation({})).toBe("—");
    expect(feedLocation({ locations: [{ municipality: null, country: "" }] })).toBe("—");
  });
});

describe("safeHttpUrl", () => {
  it("keeps http(s) urls and rejects unsafe schemes", () => {
    expect(safeHttpUrl("https://a.example")).toBe("https://a.example");
    expect(safeHttpUrl("http://a.example")).toBe("http://a.example");
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,x")).toBeNull();
    expect(safeHttpUrl(null)).toBeNull();
  });
});

describe("sortFeeds", () => {
  const feeds = [
    feed("Zebra", [{ municipality: "Oulu", country: "FI" }]),
    feed("Alpha", [{ municipality: "Turku", country: "FI" }]),
  ];

  it("sorts by provider ascending and descending without mutating input", () => {
    expect(sortFeeds(feeds, "provider", "asc").map((f) => f.provider)).toEqual([
      "Alpha",
      "Zebra",
    ]);
    expect(sortFeeds(feeds, "provider", "desc").map((f) => f.provider)).toEqual([
      "Zebra",
      "Alpha",
    ]);
    expect(feeds[0].provider).toBe("Zebra"); // original order intact
  });

  it("sorts by location and returns a copy for an unknown key", () => {
    expect(sortFeeds(feeds, "location", "asc").map((f) => f.provider)).toEqual([
      "Zebra", // Oulu < Turku
      "Alpha",
    ]);
    const copy = sortFeeds(feeds, "nope", "asc");
    expect(copy).not.toBe(feeds);
    expect(copy.map((f) => f.provider)).toEqual(["Zebra", "Alpha"]);
  });
});
