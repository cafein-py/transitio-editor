<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import {
  setAllModesHidden,
  setShapeColorBy,
  toggleModeHidden,
  toggleStopsVisible,
} from "../actions.js";

// Only modes the loaded feeds actually contain; the unknown row (sentinel
// -1, hidden by default) appears only when unclassified shapes exist.
const legendModes = computed(() =>
  [...MODES, UNKNOWN_MODE].filter((mode) =>
    store.presentModes.includes(mode.code),
  ),
);
</script>

<template>
  <!-- Open by default: the mode legend is the first thing to see and use. -->
  <details class="panel route-legend" open>
    <summary>Map display</summary>
    <label class="check legend-stops">
      <input
        type="checkbox"
        :checked="store.stopsVisible"
        @change="toggleStopsVisible"
      />
      show stops
    </label>
    <div class="legend-colorby">
      color routes by
      <label>
        <input
          type="radio"
          value="mode"
          :checked="store.shapeColorBy === 'mode'"
          @change="setShapeColorBy('mode')"
        />
        mode
      </label>
      <label>
        <input
          type="radio"
          value="feed"
          :checked="store.shapeColorBy === 'feed'"
          @change="setShapeColorBy('feed')"
        />
        feed
      </label>
    </div>
    <template v-if="legendModes.length">
      <div class="legend-modes">
        <label v-for="mode in legendModes" :key="mode.code" class="legend-mode">
          <input
            type="checkbox"
            :checked="!store.hiddenModes.includes(mode.code)"
            @change="toggleModeHidden(mode.code)"
          />
          <span class="swatch" :style="{ background: mode.color }"></span>
          {{ mode.label }}
        </label>
      </div>
      <div class="legend-all">
        <button type="button" @click="setAllModesHidden(false)">
          select all
        </button>
        <button type="button" @click="setAllModesHidden(true)">
          deselect all
        </button>
      </div>
      <p class="hint">
        Unchecked modes are hidden from the map; "other / unknown" (off by
        default) covers routes whose type could not be determined.
      </p>
    </template>
    <p v-else class="hint">no routes on the map yet.</p>
  </details>
</template>
