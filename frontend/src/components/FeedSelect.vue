<script setup>
import { computed } from "vue";

import { makeEditTarget, toggleEditTarget } from "../actions/catalogue.js";
import { currentFeed } from "../catalogue.js";
import { store } from "../store.js";

// The Cal/Trips/Agencies feed selector: choosing a feed makes it
// visible and the edit target; the pill toggles editing on it.
const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));

async function onPick(event) {
  const picked = store.catalogue.find(
    (entry) => entry.feed_id === event.target.value,
  );
  if (picked) await makeEditTarget(picked);
}
</script>

<template>
  <div class="feed-select">
    <span class="mono-label">Feed</span>
    <div class="row">
      <span
        class="swatch"
        :style="{ background: feed ? feed.color : '#ccc' }"
      ></span>
      <select :value="store.currentFeedId || ''" @change="onPick">
        <option v-for="entry in store.catalogue" :key="entry.feed_id" :value="entry.feed_id">
          {{ entry.name }}
        </option>
      </select>
      <button
        class="pill mono"
        :class="{ on: store.editMode }"
        :disabled="!feed"
        :title="store.editMode ? 'Turn editing off' : 'Turn editing on'"
        @click="feed && toggleEditTarget(feed)"
      >
        {{ store.editMode ? "Editing" : "Read-only" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.feed-select {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.row select {
  flex: 1;
  min-width: 0;
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
  background: var(--surface);
  color: var(--ink);
}
.pill {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border: 1px solid var(--border-3);
  background: var(--surface);
  color: var(--ink-5);
  border-radius: var(--r-pill);
  padding: 4px 9px;
  cursor: pointer;
  flex: none;
}
.pill.on {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.pill:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
</style>
