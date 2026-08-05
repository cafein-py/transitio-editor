<script setup>
import { computed, reactive, ref, watch } from "vue";

import { saveFeed } from "../actions.js";
import {
  clearNoticeHighlight,
  highlightNotice,
  validateWorkspace,
} from "../actions/validate.js";
import {
  codeHint,
  describeContext,
  groupNotices,
  severityCounts,
} from "../notices.js";
import { store } from "../store.js";

const SEVERITY_COLORS = {
  ERROR: "var(--error)",
  WARNING: "var(--warning)",
  INFO: "var(--ink-4)",
};

const openFeeds = reactive(new Set());
const openNotice = ref(null); // `${feedId}|${group.id}`

// The current feed's card starts open.
watch(
  () => store.currentFeedId,
  (feedId) => {
    if (feedId) openFeeds.add(feedId);
  },
  { immediate: true },
);

const feedRows = computed(() =>
  store.catalogue.map((feed) => {
    const report = store.reports[feed.feed_id] || null;
    const counts = report ? severityCounts(report) : null;
    return { feed, report, counts };
  }),
);

const totals = computed(() => {
  const sum = { ERROR: 0, WARNING: 0, INFO: 0 };
  for (const { counts } of feedRows.value) {
    if (!counts) continue;
    sum.ERROR += counts.ERROR;
    sum.WARNING += counts.WARNING;
    sum.INFO += counts.INFO;
  }
  return sum;
});

const hasReports = computed(() =>
  feedRows.value.some((row) => row.report !== null),
);
const flaggedCount = computed(
  () =>
    feedRows.value.filter(
      (row) => row.counts && (row.counts.ERROR || row.counts.WARNING),
    ).length,
);

function toggleFeed(feedId) {
  if (openFeeds.has(feedId)) openFeeds.delete(feedId);
  else openFeeds.add(feedId);
}

function toggleNotice(feedId, groupId) {
  const key = `${feedId}|${groupId}`;
  openNotice.value = openNotice.value === key ? null : key;
}

// Save & validate while editing; plain Validate writes nothing.
async function run() {
  if (store.editMode && store.currentFeedId) await saveFeed();
  await validateWorkspace();
}
</script>

<template>
  <div class="validate-panel">
    <div class="head">
      <h1>Validate</h1>
      <span class="mono meta">
        {{ hasReports ? `${flaggedCount} feeds flagged` : "not validated yet" }}
      </span>
    </div>

    <div class="stats">
      <div class="stat">
        <span class="count" :style="{ color: SEVERITY_COLORS.ERROR }">
          {{ totals.ERROR }}
        </span>
        <span class="mono-label">Errors</span>
      </div>
      <div class="stat">
        <span class="count" :style="{ color: SEVERITY_COLORS.WARNING }">
          {{ totals.WARNING }}
        </span>
        <span class="mono-label">Warnings</span>
      </div>
      <div class="stat">
        <span class="count" :style="{ color: SEVERITY_COLORS.INFO }">
          {{ totals.INFO }}
        </span>
        <span class="mono-label">Infos</span>
      </div>
    </div>

    <div class="run-row">
      <button
        class="btn dark"
        :disabled="store.validating || !store.catalogue.length"
        @click="run"
      >
        {{
          store.validating
            ? "Validating…"
            : store.editMode
              ? "Save & validate"
              : "Validate"
        }}
      </button>
      <span v-if="hasReports && store.reportStale" class="stale">
        Edited since — revalidate
      </span>
      <button
        v-if="store.highlightActive"
        class="btn small"
        @click="clearNoticeHighlight"
      >
        Clear highlight
      </button>
    </div>

    <div
      v-for="{ feed, report, counts } in feedRows"
      :key="feed.feed_id"
      class="feed-card"
      :class="{ current: feed.current }"
    >
      <button class="feed-head" @click="toggleFeed(feed.feed_id)">
        <span class="caret">{{ openFeeds.has(feed.feed_id) ? "▾" : "▸" }}</span>
        <span class="swatch" :style="{ background: feed.color }"></span>
        <span class="feed-name">{{ feed.name }}</span>
        <template v-if="counts">
          <span v-if="counts.ERROR" class="pill error mono">
            {{ counts.ERROR }}e
          </span>
          <span v-if="counts.WARNING" class="pill warning mono">
            {{ counts.WARNING }}w
          </span>
          <span
            v-if="!counts.ERROR && !counts.WARNING"
            class="clean"
          >
            Clean
          </span>
        </template>
        <span v-else class="mono not-run">—</span>
      </button>

      <div v-if="openFeeds.has(feed.feed_id) && report" class="groups">
        <div
          v-for="group in groupNotices(report)"
          :key="group.id"
          class="group"
        >
          <button
            class="group-head"
            :style="{ borderLeftColor: SEVERITY_COLORS[group.severity] }"
            @click="toggleNotice(feed.feed_id, group.id)"
          >
            <span class="group-main">
              <span class="mono code">{{ group.code }}</span>
              <span class="hint">{{ codeHint(group.code) }}</span>
            </span>
            <span class="mono group-count">{{ group.count }}</span>
          </button>
          <div
            v-if="openNotice === `${feed.feed_id}|${group.id}`"
            class="contexts"
          >
            <button
              v-for="(context, index) in group.contexts"
              :key="index"
              class="ctx mono"
              title="Highlight on the map"
              @click="highlightNotice(feed.feed_id, context)"
            >
              {{ describeContext(context) }}
            </button>
            <p v-if="group.count > group.contexts.length" class="mono more">
              +{{ group.count - group.contexts.length }} more
            </p>
          </div>
        </div>
        <p v-if="!report.notices.length" class="mono none">no notices</p>
      </div>
    </div>

    <p v-if="!store.catalogue.length" class="mono none">no feeds loaded</p>
  </div>
</template>

<style scoped>
.validate-panel {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.head h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.meta {
  font-size: 9.5px;
  color: var(--ink-5);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.stats {
  display: flex;
  gap: 7px;
}
.stat {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 9px 11px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.stat .count {
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.02em;
  line-height: 1;
}
.run-row {
  display: flex;
  align-items: center;
  gap: 9px;
}
.stale {
  font-size: 11.5px;
  color: var(--stale);
  flex: 1;
}
.feed-card {
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  overflow: hidden;
}
.feed-card.current {
  border-color: var(--accent-border);
}
.feed-head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  border: 0;
  background: none;
  padding: 8px 10px;
  cursor: pointer;
  text-align: left;
}
.caret {
  color: var(--ink-4);
  font-size: 10px;
  flex: none;
}
.feed-name {
  flex: 1;
  min-width: 0;
  font-size: 12.5px;
  font-weight: 550;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pill {
  font-size: 9.5px;
  border-radius: var(--r-pill);
  padding: 2px 7px;
  flex: none;
}
.pill.error {
  color: var(--error);
  background: rgba(184, 58, 58, 0.1);
}
.pill.warning {
  color: var(--warning);
  background: rgba(201, 118, 46, 0.12);
}
.clean {
  font-size: 11px;
  color: var(--ok);
  flex: none;
}
.not-run {
  font-size: 10px;
  color: var(--ink-6);
}
.groups {
  border-top: 1px solid var(--border-1);
  padding: 7px 9px 9px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  border-left: 3px solid var(--ink-4);
  background: var(--panel);
  border-radius: 0 var(--r-chip) var(--r-chip) 0;
  padding: 6px 9px;
  cursor: pointer;
  text-align: left;
}
.group-main {
  flex: 1;
  min-width: 0;
}
.code {
  display: block;
  font-size: 10px;
  color: var(--ink);
}
.hint {
  display: block;
  font-size: 10.5px;
  color: var(--ink-4);
  margin-top: 1px;
}
.group-count {
  font-size: 10px;
  color: var(--ink-5);
  flex: none;
}
.contexts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 5px 2px 2px 12px;
}
.ctx {
  font-size: 9.5px;
  color: var(--accent);
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  border-radius: var(--r-ctx);
  padding: 3px 7px;
  cursor: pointer;
  text-align: left;
}
.ctx:hover {
  background: var(--surface);
}
.more {
  margin: 2px 0 0;
  font-size: 9.5px;
  color: var(--ink-6);
}
.none {
  margin: 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
</style>
