<script setup>
import { store } from "../store.js";
import { feedModes, feedTableSummary } from "../catalogue.js";
import {
  endFeedDrag,
  removeFeed,
  setCurrentFeed,
  startFeedDrag,
  toggleFeedActive,
  toggleMergeSelected,
} from "../actions.js";

defineProps({ feed: { type: Object, required: true } });
</script>

<template>
  <tr
    :class="{
      current: feed.current,
      dragging: store.draggingFeedId === feed.feed_id,
    }"
    draggable="true"
    @dragstart="startFeedDrag(feed)"
    @dragend="endFeedDrag"
  >
    <td>
      <input
        type="checkbox"
        :checked="feed.active"
        @change="toggleFeedActive(feed)"
      />
    </td>
    <td>
      <span class="grip" title="drag into a group">⠿</span>
      <span class="swatch" :style="{ background: feed.color }"></span>
      <span class="kind-badge gtfs">GTFS</span>
      <span class="feed-name">{{ feed.name }}</span>
      <span class="feed-tables">{{ feedTableSummary(feed.tables) }}</span>
      <span v-if="feedModes(feed.modes).length" class="feed-modes">
        <span
          v-for="mode in feedModes(feed.modes)"
          :key="mode.code"
          class="mode-chip"
        >
          <span class="swatch" :style="{ background: mode.color }"></span
          >{{ mode.label }}
        </span>
      </span>
    </td>
    <td>
      <input
        type="radio"
        name="current-feed"
        :checked="feed.current"
        @change="setCurrentFeed(feed)"
      />
    </td>
    <td>
      <input
        type="checkbox"
        :checked="store.merge.selected.includes(feed.feed_id)"
        @change="toggleMergeSelected(feed)"
      />
    </td>
    <td>
      <button
        class="remove"
        title="remove from catalogue"
        @click="removeFeed(feed)"
      >
        ×
      </button>
    </td>
  </tr>
</template>
