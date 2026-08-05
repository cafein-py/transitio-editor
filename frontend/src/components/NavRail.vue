<script setup>
import { store } from "../store.js";

// Panel keys with their rail glyphs (inline SVG paths, stroke-drawn).
const ITEMS = [
  { key: "data", label: "Data" },
  { key: "stops", label: "Stops" },
  { key: "routes", label: "Routes" },
  { key: "cal", label: "Cal" },
  { key: "trips", label: "Trips" },
  { key: "agencies", label: "Agency" },
  { key: "streets", label: "Streets" },
  { key: "validate", label: "Validate" },
];
</script>

<template>
  <nav class="rail">
    <button
      v-for="item in ITEMS"
      :key="item.key"
      class="rail-item"
      :class="{ active: store.activePanel === item.key }"
      @click="store.activePanel = item.key"
    >
      <svg viewBox="0 0 18 18" fill="none" stroke="currentColor">
        <template v-if="item.key === 'data'">
          <rect x="2.5" y="3" width="13" height="3.4" rx="1" stroke-width="1.5" />
          <rect x="2.5" y="8.5" width="13" height="3.4" rx="1" stroke-width="1.5" opacity="0.7" />
          <rect x="2.5" y="14" width="8" height="1.4" rx="0.7" stroke-width="1.5" opacity="0.45" />
        </template>
        <template v-else-if="item.key === 'stops'">
          <circle cx="9" cy="9" r="5.2" stroke-width="1.7" />
          <circle cx="9" cy="9" r="1.4" fill="currentColor" stroke="none" />
        </template>
        <template v-else-if="item.key === 'routes'">
          <path d="M3 5h12M3 9h12M3 13h8" stroke-width="1.7" stroke-linecap="round" />
        </template>
        <template v-else-if="item.key === 'cal'">
          <rect x="2.8" y="3.6" width="12.4" height="11.4" rx="1.6" stroke-width="1.5" />
          <path d="M2.8 7.4h12.4M6 2v3M12 2v3" stroke-width="1.5" stroke-linecap="round" />
        </template>
        <template v-else-if="item.key === 'trips'">
          <!-- a run from stop A to stop B -->
          <circle cx="4.4" cy="13.6" r="2" fill="currentColor" stroke="none" />
          <path
            d="M6.2 11.8C9 9 9 9 12.4 5.6"
            stroke-width="1.7"
            stroke-linecap="round"
          />
          <path
            d="M9.6 4.4h4v4"
            stroke-width="1.7"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </template>
        <template v-else-if="item.key === 'agencies'">
          <path
            d="M3 8l6-4.6L15 8M4.4 8v6.4h9.2V8M7.4 14.4v-3.6h3.2v3.6"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </template>
        <template v-else-if="item.key === 'streets'">
          <path d="M6 2.5v13M12 2.5v13M2.5 6h13M2.5 12h13" stroke-width="1.5" stroke-linecap="round" />
        </template>
        <template v-else-if="item.key === 'validate'">
          <rect x="3" y="3" width="12" height="12" rx="2" stroke-width="1.6" />
          <path d="M6.2 9.2l2 2 3.6-4" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        </template>
      </svg>
      <span>{{ item.label }}</span>
    </button>

  </nav>
</template>

<style scoped>
.rail {
  width: 56px;
  flex: none;
  background: var(--panel);
  border-right: 1px solid var(--border-2);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 9px 0;
  overflow-y: auto;
}
.rail-item {
  width: 46px;
  border: 0;
  background: none;
  border-radius: var(--r-input);
  padding: 6px 0 5px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  color: var(--ink-4);
  cursor: pointer;
}
.rail-item svg {
  width: 18px;
  height: 18px;
}
.rail-item span {
  font: 500 9px var(--mono);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.rail-item:hover {
  color: var(--ink-2);
  background: var(--track);
}
.rail-item.active {
  color: var(--accent);
  background: var(--accent-tint);
}
</style>
