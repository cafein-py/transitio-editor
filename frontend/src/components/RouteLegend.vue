<script setup>
import { store } from "../store.js";
import { MODES } from "../modes.js";
import { setShapeColorBy, toggleModeHidden } from "../actions.js";
</script>

<template>
  <details class="panel route-legend">
    <summary>Route colors</summary>
    <div class="legend-colorby">
      color by
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
      <label v-for="mode in MODES" :key="mode.code" class="legend-mode">
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
      Unchecked modes are hidden from the map; shapes without a known mode
      stay visible.
    </p>
  </details>
</template>
