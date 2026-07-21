import { describe, expect, it } from "vitest";

import { describeContext, groupNotices, severityCounts } from "../src/notices.js";

const report = {
  notices: [
    { code: "empty_row", severity: "WARNING", context: { filename: "routes.txt" } },
    { code: "empty_row", severity: "WARNING", context: { filename: "trips.txt" } },
    { code: "missing_required_file", severity: "ERROR", context: {} },
    { code: "unknown_column", severity: "INFO", context: { column: "x" } },
  ],
  row_counts: { "agency.txt": 1 },
  service_window: ["20260101", "20261231"],
};

describe("severityCounts", () => {
  it("tallies by severity", () => {
    expect(severityCounts(report)).toEqual({ ERROR: 1, WARNING: 2, INFO: 1 });
  });
  it("is zero for no report", () => {
    expect(severityCounts(null)).toEqual({ ERROR: 0, WARNING: 0, INFO: 0 });
  });
});

describe("groupNotices", () => {
  it("groups by code, ordered by severity then count", () => {
    const groups = groupNotices(report);
    expect(groups.map((g) => g.code)).toEqual([
      "missing_required_file", // ERROR first
      "empty_row", // WARNING, count 2
      "unknown_column", // INFO
    ]);
    expect(groups[1].count).toBe(2);
    expect(groups[1].contexts).toHaveLength(2);
  });
  it("caps sample contexts", () => {
    const many = {
      notices: Array.from({ length: 50 }, () => ({
        code: "empty_row",
        severity: "WARNING",
        context: {},
      })),
    };
    const [group] = groupNotices(many, { sampleLimit: 5 });
    expect(group.count).toBe(50);
    expect(group.contexts).toHaveLength(5);
  });
  it("splits one code across severities", () => {
    const mixed = {
      notices: [
        { code: "c", severity: "ERROR", context: {} },
        { code: "c", severity: "WARNING", context: {} },
        { code: "c", severity: "WARNING", context: {} },
      ],
    };
    const groups = groupNotices(mixed);
    expect(groups).toHaveLength(2);
    expect(groups.map((g) => [g.severity, g.count])).toEqual([
      ["ERROR", 1],
      ["WARNING", 2],
    ]);
    expect(new Set(groups.map((g) => g.id)).size).toBe(2);
  });
  it("is empty for no report", () => {
    expect(groupNotices(null)).toEqual([]);
  });
});

describe("describeContext", () => {
  it("renders key=value pairs", () => {
    expect(describeContext({ filename: "stops.txt", csvRowNumber: 3 })).toBe(
      "filename=stops.txt, csvRowNumber=3",
    );
  });
  it("handles empty context", () => {
    expect(describeContext({})).toBe("(no context)");
  });
});
