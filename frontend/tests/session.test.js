import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LOG_LIMIT,
  NETWORK_FEED,
  configureSession,
  logAction,
  logLocal,
  logPlain,
  logRequestEdit,
  logServerEdit,
  restoredLogEntries,
  installRestoredLog,
  sessionLogForSave,
  sessionRedo,
  sessionUndo,
} from "../src/session.js";
import { store } from "../src/store.js";
import { dismissToast, toasts } from "../src/toasts.js";

function resetSession() {
  store.session.log.length = 0;
  store.session.redoStack.length = 0;
  store.dirty = false;
  store.currentFeedId = "feed-1";
  for (const toast of [...toasts]) dismissToast(toast.id);
}

beforeEach(() => {
  resetSession();
  configureSession({ refresh: async () => {}, makeCurrent: async () => {} });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const okFetch = () => {
  const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
};

describe("logAction", () => {
  it("stamps defaults, marks dirty and clears the redo stack", () => {
    store.session.redoStack.push({ id: 99, title: "old", kind: "server" });
    logServerEdit("Stop moved", "S1");
    const entry = store.session.log.at(-1);
    expect(entry.kind).toBe("server");
    expect(entry.feedId).toBe("feed-1");
    expect(entry.time).toBeGreaterThan(0);
    expect(store.session.redoStack).toHaveLength(0);
    expect(store.dirty).toBe(true);
  });

  it("caps the log at the limit", () => {
    for (let i = 0; i < LOG_LIMIT + 10; i += 1) {
      logPlain(`action ${i}`, "");
    }
    expect(store.session.log).toHaveLength(LOG_LIMIT);
    expect(store.session.log[0].title).toBe("action 10");
  });
});

describe("undo/redo over local entries", () => {
  it("restores the snapshot and reapplies on redo", async () => {
    store.shapeColorBy = "feed";
    logLocal(
      "Colour by feed",
      "",
      { shapeColorBy: "mode" },
      { shapeColorBy: "feed" },
    );
    await sessionUndo();
    expect(store.shapeColorBy).toBe("mode");
    expect(store.session.log).toHaveLength(0);
    expect(store.session.redoStack).toHaveLength(1);
    await sessionRedo();
    expect(store.shapeColorBy).toBe("feed");
    expect(store.session.log).toHaveLength(1);
  });
});

describe("undo over server entries", () => {
  it("posts /api/undo pinned to the entry's feed", async () => {
    const fetchMock = okFetch();
    logServerEdit("Trip deleted", "T1");
    await sessionUndo();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/undo",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      feed_id: "feed-1",
    });
    expect(store.session.redoStack).toHaveLength(1);
  });

  it("switches the current feed first when the entry is another feed's", async () => {
    okFetch();
    const calls = [];
    configureSession({
      refresh: async () => {},
      makeCurrent: async (feedId) => {
        calls.push(feedId);
        store.currentFeedId = feedId;
      },
    });
    logServerEdit("Stop added", "S9"); // logged against feed-1
    store.currentFeedId = "feed-2"; // the user switched since
    await sessionUndo();
    expect(calls).toEqual(["feed-1"]);
    expect(store.session.log).toHaveLength(0);
  });

  it("keeps the entry when the request fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 409,
        statusText: "Conflict",
        json: async () => ({ detail: "nothing to undo" }),
      })),
    );
    logServerEdit("Stop added", "S1");
    await sessionUndo();
    expect(store.session.log).toHaveLength(1);
    expect(store.session.redoStack).toHaveLength(0);
    expect(toasts.at(-1).title).toContain("undo failed");
  });
});

describe("undo over request entries", () => {
  it("sends the compensating request", async () => {
    const fetchMock = okFetch();
    logRequestEdit(
      "Way reclassified",
      "way/42 highway=residential",
      { method: "PATCH", path: "/api/network/ways/42", body: { tags: { highway: "service" } } },
      { method: "PATCH", path: "/api/network/ways/42", body: { tags: { highway: "residential" } } },
    );
    await sessionUndo();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/network/ways/42");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      tags: { highway: "service" },
    });
  });

  it("falls back to a non-undoable entry without a compensating request", async () => {
    logRequestEdit("Way retagged", "way/42 name=x", null, null);
    expect(store.session.log.at(-1).kind).toBe("none");
    await sessionUndo();
    expect(store.session.log).toHaveLength(1); // refused, kept
    expect(toasts.at(-1).title).toContain("cannot undo");
  });
});

describe("persistence", () => {
  it("saves only the visible record", () => {
    logServerEdit("Trip shifted", "T1 by 600s");
    const saved = sessionLogForSave();
    expect(saved).toEqual([
      expect.objectContaining({ title: "Trip shifted", feedId: "feed-1" }),
    ]);
    expect(saved[0]).not.toHaveProperty("kind");
    expect(saved[0]).not.toHaveProperty("undoReq");
  });

  it("restores entries as viewable but not undoable", () => {
    const restored = restoredLogEntries([
      { time: 5, title: "Stop moved", detail: "S1", feedId: "feed-1" },
      { bogus: true },
      "junk",
    ]);
    expect(restored).toHaveLength(1);
    expect(restored[0].kind).toBe("none");
    expect(restored[0].feedId).toBe("feed-1");
  });

  it("replaces the live log wholesale on restore", () => {
    logServerEdit("Stop moved", "S1");
    store.session.redoStack.push({ id: 1, title: "x", kind: "server" });
    installRestoredLog([{ title: "Service added", feedId: NETWORK_FEED }]);
    expect(store.session.log).toHaveLength(1);
    expect(store.session.log[0].title).toBe("Service added");
    expect(store.session.redoStack).toHaveLength(0);
  });

  it("clears the log when the restored session has none", () => {
    logAction({ kind: "server", title: "Stop moved" });
    installRestoredLog(undefined);
    expect(store.session.log).toHaveLength(0);
  });
});
