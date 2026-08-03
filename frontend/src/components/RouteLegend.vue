<script setup>
import { store } from "../store.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import {
  setShapeColorBy,
  toggleModeHidden,
  toggleStopsVisible,
} from "../actions.js";

// The unknown-mode row toggles like any other mode (sentinel code -1).
const legendModes = [...MODES, UNKNOWN_MODE];
</script>

<template>
  <details class="panel route-legend">
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
    <p class="hint">
      Unchecked modes are hidden from the map; "other / unknown" covers
      routes whose type could not be determined.
    </p>
  </details>
</template>
