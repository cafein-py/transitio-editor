import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  capitalize,
  dismissToast,
  pushToast,
  runToastAction,
  toasts,
} from "../src/toasts.js";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  for (const toast of [...toasts]) dismissToast(toast.id);
  vi.useRealTimers();
});

describe("pushToast", () => {
  it("queues and auto-dismisses after the duration", () => {
    const id = pushToast({ title: "workspace saved", duration: 1000 });
    expect(toasts.map((toast) => toast.id)).toContain(id);
    vi.advanceTimersByTime(999);
    expect(toasts.map((toast) => toast.id)).toContain(id);
    vi.advanceTimersByTime(1);
    expect(toasts.map((toast) => toast.id)).not.toContain(id);
  });

  it("keeps a sticky toast until dismissed", () => {
    const id = pushToast({ title: "stays", duration: 0 });
    vi.advanceTimersByTime(60_000);
    expect(toasts.map((toast) => toast.id)).toContain(id);
    dismissToast(id);
    expect(toasts).toHaveLength(0);
  });

  it("drops the oldest toast beyond the visible limit", () => {
    const first = pushToast({ title: "first" });
    for (let i = 0; i < 4; i += 1) pushToast({ title: `later ${i}` });
    expect(toasts.map((toast) => toast.id)).not.toContain(first);
    expect(toasts).toHaveLength(4);
  });
});

describe("runToastAction", () => {
  it("runs the action once and removes the toast", () => {
    const run = vi.fn();
    const id = pushToast({ title: "deleted", action: { label: "undo", run } });
    runToastAction(id);
    runToastAction(id); // gone: must not fire again
    expect(run).toHaveBeenCalledTimes(1);
    expect(toasts).toHaveLength(0);
  });

  it("ignores toasts without an action", () => {
    const id = pushToast({ title: "plain" });
    runToastAction(id);
    expect(toasts).toHaveLength(1);
  });
});

describe("capitalize", () => {
  it("uppercases only the first character", () => {
    expect(capitalize("undo available")).toBe("Undo available");
    expect(capitalize("")).toBe("");
    expect(capitalize(null)).toBe("");
  });
});
