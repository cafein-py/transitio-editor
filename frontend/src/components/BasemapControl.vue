<script setup>
import { ref } from "vue";

import { store } from "../store.js";
import { BASEMAPS, basemapLabel } from "../basemaps.js";
import { setBasemap } from "../map.js";
import Icon from "./Icon.vue";

const open = ref(false);

function choose(key) {
  setBasemap(key);
  open.value = false;
}
</script>

<template>
  <!-- Floating basemap switcher; the map stays imperative, so the choice
       goes through the map bridge like every other map mutation. -->
  <div class="basemap-control">
    <button type="button" class="basemap-btn" title="Basemap style" @click="open = !open">
      <Icon name="map" /> {{ basemapLabel(store.basemap) }}
    </button>
    <ul v-if="open">
      <li v-for="basemap in BASEMAPS" :key="basemap.key">
        <button
          type="button"
          :class="{ active: basemap.key === store.basemap }"
          @click="choose(basemap.key)"
        >
          {{ basemap.label }}
        </button>
      </li>
    </ul>
  </div>
</template>
