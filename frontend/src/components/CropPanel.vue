<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { cropToShape } from "../actions/catalogue.js";
import { cancelCropDraw } from "../map.js";

const activeFeeds = computed(() =>
  store.catalogue.filter((feed) => feed.active),
);
</script>

<template>
  <!-- A drawn area is not cropped until it is confirmed here. -->
  <div v-if="store.cropShape" class="crop-card">
    <span class="title">Crop to the drawn area</span>
    <p class="note">
      Crops the {{ activeFeeds.length }}
      feed{{ activeFeeds.length === 1 ? "" : "s" }} shown on the map. The
      originals stay; the copies land in a group.
    </p>
    <label class="check">
      <input type="checkbox" v-model="store.crop.fullTripsOnly" />
      Keep only trips entirely inside the area
    </label>
    <input
      v-model="store.crop.group"
      class="group-input"
      placeholder="Group for the copies"
    />
    <div class="actions">
      <button
        class="btn small dark"
        :disabled="store.crop.running || !activeFeeds.length"
        @click="cropToShape"
      >
        {{ store.crop.running ? "Cropping…" : "Crop" }}
      </button>
      <button
        class="btn small"
        :disabled="store.crop.running"
        @click="cancelCropDraw"
      >
        Discard
      </button>
    </div>
  </div>
</template>

<style scoped>
.crop-card {
  background: var(--surface);
  border: 1px dashed var(--accent-border);
  border-radius: var(--r-card);
  padding: 10px 11px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 9px;
}
.title {
  font-size: 12.5px;
  font-weight: 600;
}
.note {
  margin: 0;
  font-size: 10.5px;
  line-height: 1.45;
  color: var(--ink-4);
}
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--ink-2);
}
.check input {
  accent-color: var(--accent);
}
.group-input {
  font: 11.5px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 9px;
  background: var(--surface);
}
.group-input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.actions {
  display: flex;
  gap: 6px;
}
</style>
