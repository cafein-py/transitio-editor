import { describe, expect, it } from "vitest";

import { workspaceFileName } from "../src/actions/workspace.js";

describe("workspaceFileName", () => {
  it("keeps ordinary names, adding the extension", () => {
    expect(workspaceFileName("Helsinki region")).toBe("Helsinki region.json");
  });

  it("drops separators and filesystem-hostile characters", () => {
    expect(workspaceFileName("a/b\\c:d*e?f")).toBe("a b c d e f.json");
    expect(workspaceFileName('x"<y>|z')).toBe("x y z.json");
  });

  it("collapses whitespace and refuses an empty result", () => {
    expect(workspaceFileName("  spaced   out  ")).toBe("spaced out.json");
    expect(workspaceFileName("")).toBeNull();
    expect(workspaceFileName("///")).toBeNull();
    expect(workspaceFileName(null)).toBeNull();
  });
});
