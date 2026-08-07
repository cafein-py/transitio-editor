import { describe, expect, it } from "vitest";

import {
  calendarSpan,
  daySummary,
  dayNames,
  gtfsToInput,
  inputToGtfs,
  serviceRows,
} from "../src/services.js";

describe("serviceRows", () => {
  it("reads calendar.txt rows", () => {
    const rows = serviceRows([
      {
        service_id: "WK",
        monday: "1",
        tuesday: 1,
        wednesday: "1",
        thursday: "1",
        friday: "1",
        saturday: "0",
        sunday: 0,
        start_date: "20260101",
        end_date: "20261231",
      },
    ]);
    expect(rows[0].serviceId).toBe("WK");
    expect(rows[0].days).toEqual([true, true, true, true, true, false, false]);
    expect(rows[0].from).toBe("20260101");
  });
});

describe("daySummary", () => {
  const days = (...on) =>
    [0, 1, 2, 3, 4, 5, 6].map((index) => on.includes(index));

  it("collapses runs of three or more", () => {
    expect(daySummary(days(0, 1, 2, 3, 4))).toBe("Mo–Fr");
    expect(daySummary(days(0, 1, 2, 3, 4, 5, 6))).toBe("Mo–Su");
  });

  it("lists short runs and singles", () => {
    expect(daySummary(days(5, 6))).toBe("Sa, Su");
    expect(daySummary(days(0, 2, 4))).toBe("Mo, We, Fr");
    expect(daySummary(days(0, 1, 2, 4))).toBe("Mo–We, Fr");
    expect(daySummary(days())).toBe("no days");
  });
});

describe("calendarSpan", () => {
  it("spans the earliest start to the latest end", () => {
    const span = calendarSpan([
      { from: "20260301", to: "20260601" },
      { from: "20260101", to: "20260501" },
    ]);
    expect(span).toEqual({ from: "20260101", to: "20260601" });
    expect(calendarSpan([])).toBeNull();
    expect(calendarSpan([{ from: "bad", to: "" }])).toBeNull();
  });
});

describe("date conversion", () => {
  it("round-trips GTFS dates", () => {
    expect(gtfsToInput("20260805")).toBe("2026-08-05");
    expect(inputToGtfs("2026-08-05")).toBe("20260805");
    expect(gtfsToInput("nope")).toBe("");
    expect(inputToGtfs("nope")).toBe("");
  });
});

describe("dayNames", () => {
  it("names the checked days", () => {
    expect(
      dayNames([true, false, false, false, true, false, false]),
    ).toEqual(["monday", "friday"]);
  });
});
