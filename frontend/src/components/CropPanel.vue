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
  <div v-if="store.cropShape" class="crop-panel">
    <p class="hint">
      Crop {{ activeFeeds.length }} feed{{
        activeFeeds.length === 1 ? "" : "s"
      }}
      shown on the map to the drawn area. The originals stay; the copies land in
      a group.
    </p>
    <label>
      <input type="checkbox" v-model="store.crop.fullTripsOnly" />
      keep only trips entirely inside the area
    </label>
    <div class="dir-row">
      <input v-model="store.crop.group" placeholder="group for the copies" />
    </div>
    <div class="mode-row">
      <button
        class="primary"
        :disabled="store.crop.running || !activeFeeds.length"
        @click="cropToShape"
      >
        {{ store.crop.running ? "Cropping…" : "Crop" }}
      </button>
      <button :disabled="store.crop.running" @click="cancelCropDraw">
        Discard
      </button>
    </div>
  </div>
</template>
