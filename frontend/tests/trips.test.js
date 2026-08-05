import { describe, expect, it } from "vitest";

import {
  estimateTrips,
  offsetsFromTimes,
  suggestTripId,
  toSeconds,
  tripMatches,
  validStart,
} from "../src/trips.js";

describe("toSeconds", () => {
  it("parses H:MM and H:MM:SS, over-midnight included", () => {
    expect(toSeconds("05:30")).toBe(19800);
    expect(toSeconds("5:30")).toBe(19800);
    expect(toSeconds("05:30:15")).toBe(19815);
    expect(toSeconds("25:00")).toBe(90000);
  });

  it("rejects malformed times", () => {
    expect(toSeconds("5.30")).toBeNull();
    expect(toSeconds("05:61")).toBeNull();
    expect(toSeconds("")).toBeNull();
    expect(validStart("05:30")).toBe(true);
    expect(validStart("x")).toBe(false);
  });
});

describe("suggestTripId", () => {
  it("builds SHORT_HHMM_dir", () => {
    expect(suggestTripId("A", "05:30", 0)).toBe("A_0530_0");
    expect(suggestTripId("60 X", "7:05", 1)).toBe("60X_0705_1");
    expect(suggestTripId("", "05:30", 0)).toBe("TRIP_0530_0");
    expect(suggestTripId("A", "bad", 0)).toBe("");
  });
});

describe("estimateTrips", () => {
  it("counts the template run plus one per headway", () => {
    expect(estimateTrips("05:30", "06:30", 600)).toBe(7);
    expect(estimateTrips("05:30", "05:30", 600)).toBe(0);
    expect(estimateTrips("06:30", "05:30", 600)).toBe(0);
    expect(estimateTrips("bad", "06:30", 600)).toBe(0);
  });
});

describe("offsetsFromTimes", () => {
  it("derives relative offsets from stop_times", () => {
    expect(
      offsetsFromTimes([
        { stop_id: "S1", departure_time: "05:30:00" },
        { stop_id: "S2", departure_time: "05:32:00" },
        { stop_id: "S3", arrival_time: "05:35:00", departure_time: "" },
      ]),
    ).toEqual([
      ["S1", 0],
      ["S2", 120],
      ["S3", 300],
    ]);
    expect(offsetsFromTimes([])).toEqual([]);
  });
});

describe("tripMatches", () => {
  const trip = { trip_id: "A_0530_0", first_departure: "05:30:00" };

  it("matches by id or start time", () => {
    expect(tripMatches(trip, "a_05")).toBe(true);
    expect(tripMatches(trip, "05:3")).toBe(true);
    expect(tripMatches(trip, "07:")).toBe(false);
    expect(tripMatches(trip, "")).toBe(true);
  });
});
