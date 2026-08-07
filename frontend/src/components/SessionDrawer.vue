<script setup>
import { computed, ref } from "vue";

import { NETWORK_FEED, sessionRedo, sessionUndo } from "../session.js";
import { store } from "../store.js";
import { redoButtonTitle, undoButtonTitle } from "../undo.js";

const filter = ref("all");

const undoTop = computed(
  () => store.session.log[store.session.log.length - 1] || null,
);
const redoTop = computed(
  () => store.session.redoStack[store.session.redoStack.length - 1] || null,
);
const canUndo = computed(() => undoTop.value && undoTop.value.kind !== "none");

const hasNetworkEntries = computed(() =>
  store.session.log.some((entry) => entry.feedId === NETWORK_FEED),
);

// Newest first; the top row is the one "latest" tags.
const rows = computed(() => {
  const wanted = filter.value;
  const entries =
    wanted === "all"
      ? store.session.log
      : store.session.log.filter((entry) => entry.feedId === wanted);
  return [...entries].reverse();
});

const feedName = (feedId) => {
  if (feedId === NETWORK_FEED) return "street network";
  const feed = store.catalogue.find((entry) => entry.feed_id === feedId);
  return feed ? feed.name : null;
};

const clock = (time) =>
  new Date(time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

const savedLine = computed(() =>
  store.session.savedAt
    ? `Saved ${clock(store.session.savedAt)}`
    : "Workspace not saved yet",
);
</script>

<template>
  <div v-if="store.session.historyOpen" class="drawer">
    <div class="drawer-head">
      <h2>Session</h2>
      <button
        class="btn small"
        :disabled="!canUndo"
        :title="undoButtonTitle(canUndo ? undoTop.title : null)"
        @click="sessionUndo"
      >
        ↶ Undo
      </button>
      <button
        class="btn small"
        :disabled="!redoTop"
        :title="redoButtonTitle(redoTop ? redoTop.title : null)"
        @click="sessionRedo"
      >
        ↷ Redo
      </button>
      <button
        class="drawer-close"
        aria-label="Close"
        @click="store.session.historyOpen = false"
      >
        ×
      </button>
    </div>

    <div class="drawer-bar">
      <span class="saved mono">{{ savedLine }}</span>
      <select v-model="filter">
        <option value="all">All feeds</option>
        <option
          v-for="feed in store.catalogue"
          :key="feed.feed_id"
          :value="feed.feed_id"
        >
          {{ feed.name }}
        </option>
        <option v-if="hasNetworkEntries" :value="NETWORK_FEED">
          Street network
        </option>
      </select>
    </div>

    <div class="drawer-log">
      <p v-if="!rows.length" class="empty">
        No actions yet — edits to feeds, services, trips and the street
        network will be logged here and can be undone.
      </p>
      <div v-for="(entry, index) in rows" :key="entry.id" class="row">
        <div class="row-main">
          <div class="row-title">
            {{ entry.title }}
            <span v-if="index === 0 && filter === 'all'" class="latest">
              latest
            </span>
          </div>
          <div v-if="entry.detail || feedName(entry.feedId)" class="row-detail">
            <span v-if="feedName(entry.feedId)" class="row-feed">
              {{ feedName(entry.feedId) }}
            </span>
            {{ entry.detail }}
          </div>
        </div>
        <span class="row-time">{{ clock(entry.time) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drawer {
  position: fixed;
  top: 46px;
  right: 0;
  bottom: 0;
  width: 302px;
  background: var(--surface);
  border-left: 1px solid var(--border-3);
  box-shadow: -4px 0 18px rgba(20, 22, 26, 0.08);
  z-index: 25;
  display: flex;
  flex-direction: column;
}
.drawer-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 11px 12px;
}
.drawer-head h2 {
  margin: 0;
  flex: 1;
  font-size: 13.5px;
  font-weight: 650;
}
.drawer-close {
  border: 0;
  background: none;
  color: var(--ink-4);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}
.drawer-close:hover {
  color: var(--ink);
}
.drawer-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px 9px;
  border-bottom: 1px solid var(--border-2);
}
.saved {
  flex: 1;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-5);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.drawer-bar select {
  font: 11.5px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-btn-sm);
  padding: 3px 5px;
  background: var(--surface);
  color: var(--ink-2);
  max-width: 150px;
}
.drawer-log {
  flex: 1;
  overflow-y: auto;
  padding: 7px 12px 12px;
}
.empty {
  margin: 8px 2px;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-4);
}
.row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 7px 2px;
  border-bottom: 1px solid var(--border-1);
}
.row-main {
  flex: 1;
  min-width: 0;
}
.row-title {
  font-size: 12px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.latest {
  font: 500 8.5px var(--mono);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent);
  background: var(--accent-tint);
  border-radius: var(--r-chip);
  padding: 1px 5px;
}
.row-detail {
  font: 10px var(--mono);
  color: var(--ink-6);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row-feed {
  color: var(--ink-5);
}
.row-feed::after {
  content: " · ";
}
.row-time {
  font: 9.5px var(--mono);
  color: var(--ink-6);
  padding-top: 2px;
  flex: none;
}
</style>
