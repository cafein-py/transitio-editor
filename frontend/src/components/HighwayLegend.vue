<script setup>
import { computed } from "vue";

import {
  setAllHighwayClasses,
  toggleHighwayClass,
} from "../actions/streets.js";
import { HIGHWAY_CLASSES } from "../streets.js";
import { store } from "../store.js";

defineProps({
  counts: { type: Object, required: true }, // ways per class key
});

const hidden = computed(() => store.hiddenHighwayClasses);
const allKeys = HIGHWAY_CLASSES.map((entry) => entry.key);

const label = (key) => key[0].toUpperCase() + key.slice(1);

// The swatch draws the class's real style: colour, width, dash.
const dashArray = (entry) =>
  entry.dash ? entry.dash.map((v) => v * 1.2).join(" ") : null;
</script>

<template>
  <div class="legend">
    <div class="legend-head">
      <span class="mono-label">Highway type</span>
      <button class="btn small" @click="setAllHighwayClasses(false, allKeys)">
        All
      </button>
      <button class="btn small" @click="setAllHighwayClasses(true, allKeys)">
        None
      </button>
    </div>
    <button
      v-for="entry in HIGHWAY_CLASSES"
      :key="entry.key"
      class="legend-row"
      :class="{ off: hidden.includes(entry.key) }"
      @click="toggleHighwayClass(entry.key)"
    >
      <svg viewBox="0 0 44 10" class="line-swatch">
        <line
          x1="2"
          y1="5"
          x2="42"
          y2="5"
          :stroke="entry.color"
          :stroke-width="Math.min(7, entry.width * 1.15)"
          :stroke-dasharray="dashArray(entry)"
          stroke-linecap="round"
        />
      </svg>
      <span class="legend-label">{{ label(entry.key) }}</span>
      <span class="mono legend-count">{{ counts[entry.key] ?? 0 }}</span>
    </button>
  </div>
</template>

<style scoped>
.legend {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.legend-head {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
}
.legend-head .mono-label {
  flex: 1;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 9px;
  border: 0;
  background: var(--surface);
  border-radius: var(--r-chip);
  padding: 5px 7px;
  cursor: pointer;
  text-align: left;
}
.legend-row:hover {
  background: var(--track);
}
.line-swatch {
  width: 44px;
  height: 10px;
  flex: none;
}
.legend-label {
  flex: 1;
  font-size: 12px;
  color: var(--ink);
}
.legend-count {
  font-size: 9.5px;
  color: var(--ink-5);
}
.legend-row.off {
  background: transparent;
}
.legend-row.off .legend-label {
  color: #a3a6ac;
}
.legend-row.off .line-swatch {
  opacity: 0.4;
}
.legend-row.off .legend-count {
  color: #a3a6ac;
}
</style>
