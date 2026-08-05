<script setup>
import {
  endFeedDrag,
  removeFeed,
  startFeedDrag,
  toggleEditTarget,
  toggleFeedActive,
} from "../actions/catalogue.js";
import { feedTableSummary } from "../catalogue.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import { store } from "../store.js";
import Icon from "./Icon.vue";

defineProps({ feed: { type: Object, required: true } });

const ALL_MODES = [...MODES, UNKNOWN_MODE];
const modeOf = (code) =>
  ALL_MODES.find((mode) => mode.code === code) || UNKNOWN_MODE;
const modeAbbr = (code) => modeOf(code).label.split(" ")[0].toUpperCase();

const tint = (hex, alpha) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};
</script>

<template>
  <div
    class="feed-card"
    :class="{
      current: feed.current,
      dragging: store.draggingFeedId === feed.feed_id,
      inactive: !feed.active,
    }"
    draggable="true"
    @dragstart="startFeedDrag(feed)"
    @dragend="endFeedDrag"
  >
    <span class="grip">⠿</span>
    <button
      class="eye"
      :class="{ off: !feed.active }"
      :title="feed.active ? 'Hide from the map' : 'Show on the map'"
      @click="toggleFeedActive(feed)"
    >
      <Icon :name="feed.active ? 'eye' : 'eye-off'" />
    </button>
    <div class="feed-main">
      <div class="feed-name-row">
        <span class="swatch" :style="{ background: feed.color }"></span>
        <span class="feed-name">{{ feed.name }}</span>
      </div>
      <div v-if="(feed.modes || []).length" class="pills">
        <span
          v-for="code in feed.modes"
          :key="code"
          class="pill mono"
          :class="{ dim: store.hiddenModes.includes(code) }"
          :style="{
            background: tint(modeOf(code).color, 0.14),
            color: modeOf(code).color,
          }"
        >
          {{ modeAbbr(code) }}
        </span>
      </div>
      <div class="mono feed-meta">{{ feedTableSummary(feed.tables) }}</div>
    </div>
    <button
      class="tool pencil"
      :class="{ on: feed.current && store.editMode }"
      :title="
        feed.current && store.editMode
          ? 'Stop editing this feed'
          : 'Edit this feed'
      "
      @click="toggleEditTarget(feed)"
    >
      <Icon name="pencil" />
    </button>
    <button
      class="tool"
      title="Remove from the workspace"
      @click="removeFeed(feed)"
    >
      <Icon name="trash" />
    </button>
  </div>
</template>

<style scoped>
.feed-card {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 8px 8px 7px;
}
.feed-card.current {
  border-color: var(--accent-border);
  box-shadow: 0 0 0 1px var(--accent-border);
}
.feed-card.dragging {
  opacity: 0.5;
}
.feed-card.inactive .feed-main {
  opacity: 0.55;
}
.grip {
  color: var(--ink-6);
  cursor: grab;
  font-size: 11px;
  flex: none;
  padding-top: 2px;
}
.eye {
  border: 0;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
  padding: 3px 2px 1px;
  flex: none;
}
.eye svg {
  width: 14px;
  height: 14px;
  display: block;
}
.eye.off {
  color: var(--ink-disabled);
}
.feed-main {
  flex: 1;
  min-width: 0;
}
.feed-name-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.feed-name {
  font-size: 12.5px;
  font-weight: 550;
  line-height: 1.25;
}
.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.pill {
  font-size: 8.5px;
  letter-spacing: 0.05em;
  border-radius: 4px;
  padding: 2px 5px;
}
.pill.dim {
  opacity: 0.35;
}
.feed-meta {
  font-size: 10px;
  color: var(--ink-6);
  margin-top: 4px;
}
.tool {
  border: 0;
  background: none;
  color: var(--ink-5);
  cursor: pointer;
  padding: 3px;
  border-radius: 5px;
  flex: none;
}
.tool svg {
  width: 13px;
  height: 13px;
  display: block;
}
.tool:hover {
  color: var(--ink);
  background: rgba(20, 22, 26, 0.06);
}
.pencil.on {
  color: var(--accent);
  background: var(--accent-tint);
}
</style>
