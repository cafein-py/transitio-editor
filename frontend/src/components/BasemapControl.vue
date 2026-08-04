<script setup>
import { ref } from "vue";

import { store } from "../store.js";
import { BASEMAPS, basemapLabel } from "../basemaps.js";
import { setBasemap } from "../map.js";

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
    <button type="button" title="basemap style" @click="open = !open">
      ▦ {{ basemapLabel(store.basemap) }}
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
