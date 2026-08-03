<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { setCurrentFeed } from "../actions.js";

const current = computed(
  () => store.catalogue.find((feed) => feed.current) || null,
);

function onSwitch(event) {
  const feed = store.catalogue.find((f) => f.feed_id === event.target.value);
  if (feed && !feed.current) setCurrentFeed(feed);
}
</script>

<template>
  <!-- Edits, validation and save target the current feed; keep that visible
       (and switchable) outside the Catalogue tab too. -->
  <div v-if="store.catalogue.length" class="feed-bar">
    <span
      class="swatch"
      :style="{ background: current ? current.color : '#ccc' }"
    ></span>
    <label>feed</label>
    <select :value="store.currentFeedId" @change="onSwitch">
      <option
        v-for="feed in store.catalogue"
        :key="feed.feed_id"
        :value="feed.feed_id"
      >
        {{ feed.name }}
      </option>
    </select>
  </div>
</template>
