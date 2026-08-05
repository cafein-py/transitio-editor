<script setup>
import { computed } from "vue";

import {
  soloMode,
  toggleModeHidden,
  toggleStopsVisible,
} from "../actions/mapView.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import { store } from "../store.js";

// One chip per mode the loaded feeds actually contain.
const chips = computed(() =>
  [...MODES, UNKNOWN_MODE]
    .filter((mode) => store.presentModes.includes(mode.code))
    .map((mode) => ({
      code: mode.code,
      color: mode.color,
      label:
        mode.code === UNKNOWN_MODE.code
          ? "Other"
          : mode.label[0].toUpperCase() + mode.label.slice(1),
    })),
);

const hidden = (code) => store.hiddenModes.includes(code);

// A double-click arrives as click, click, dblclick: hold the toggle
// briefly so a solo does not first flip the chip twice.
let clickTimer = null;

function onChipClick(chip) {
  clearTimeout(clickTimer);
  clickTimer = setTimeout(() => toggleModeHidden(chip.code), 220);
}

function onChipDblclick(chip) {
  clearTimeout(clickTimer);
  soloMode(chip.code, chip.label);
}
</script>

<template>
  <div v-if="chips.length" class="display-bar">
    <button
      v-for="chip in chips"
      :key="chip.code"
      class="chip"
      :class="{ off: hidden(chip.code) }"
      @click="onChipClick(chip)"
      @dblclick="onChipDblclick(chip)"
    >
      <span
        class="dash"
        :style="{ background: hidden(chip.code) ? '#a3a6ac' : chip.color }"
      ></span>
      {{ chip.label }}
      <span class="tip">
        {{ chip.label }} — click to toggle, double-click to solo
      </span>
    </button>

    <span class="divider"></span>

    <button
      class="chip"
      :class="{ off: !store.stopsVisible }"
      @click="toggleStopsVisible"
    >
      <span
        class="stop-dot"
        :class="{ dim: !store.stopsVisible }"
      ></span>
      Stops
      <span class="tip">Show or hide stops</span>
    </button>
  </div>
</template>

<style scoped>
.display-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  box-shadow: var(--shadow-overlay);
  padding: 5px 7px;
  max-width: min(430px, calc(100vw - 480px));
}
.chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-2);
  background: var(--surface);
  border-radius: var(--r-pill);
  padding: 3px 10px;
  font: 500 11.5px var(--sans);
  color: var(--ink);
  cursor: pointer;
}
.chip:hover {
  border-color: var(--border-4);
}
.chip.off {
  color: #a3a6ac;
  background: transparent;
  border-color: transparent;
}
.dash {
  width: 14px;
  height: 3px;
  border-radius: 2px;
  flex: none;
}
.stop-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #fff;
  border: 2.4px solid var(--ink-2);
  flex: none;
}
.stop-dot.dim {
  border-color: #a3a6ac;
}
.divider {
  width: 1px;
  align-self: stretch;
  margin: 2px 3px;
  background: var(--border-3);
}
/* Custom tooltip bubble under the chip — native title is too slow. */
.tip {
  display: none;
  position: absolute;
  top: calc(100% + 7px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--ink);
  color: #fff;
  font: 400 10.5px var(--sans);
  border-radius: 6px;
  padding: 4px 8px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 20;
}
.chip:hover .tip {
  display: block;
}
</style>
