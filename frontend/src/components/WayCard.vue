<script setup>
import { computed } from "vue";

import { deleteNetworkWay, reclassifyWay } from "../actions/streets.js";
import { setVertexEdit } from "../map/streets.js";
import { networkTags } from "../network.js";
import { wayHighway } from "../streets.js";
import { store } from "../store.js";

const props = defineProps({
  lengthKm: { type: Number, default: null },
});

const selected = computed(() => store.network.selected);
const tags = computed(() =>
  Object.fromEntries(networkTags(selected.value || {})),
);
const highway = computed(() => wayHighway(selected.value) || "");

// The select offers common values; the way's own value always appears.
const HIGHWAY_VALUES = [
  "motorway",
  "trunk",
  "primary",
  "secondary",
  "tertiary",
  "residential",
  "living_street",
  "unclassified",
  "service",
  "track",
  "cycleway",
  "footway",
  "path",
  "pedestrian",
];
const options = computed(() =>
  highway.value && !HIGHWAY_VALUES.includes(highway.value)
    ? [highway.value, ...HIGHWAY_VALUES]
    : HIGHWAY_VALUES,
);
</script>

<template>
  <div v-if="selected" class="way-card">
    <div class="row">
      <span class="mono-label">Osm id</span>
      <span class="mono value">way/{{ selected.id }}</span>
    </div>
    <div class="row">
      <span class="mono-label">Highway</span>
      <select
        v-if="store.network.editing"
        :value="highway"
        @change="reclassifyWay($event.target.value)"
      >
        <option v-for="value in options" :key="value" :value="value">
          {{ value }}
        </option>
      </select>
      <span v-else class="mono value">{{ highway || "—" }}</span>
    </div>
    <div class="row">
      <span class="mono-label">Name</span>
      <span class="value">{{ tags.name || "—" }}</span>
    </div>
    <div class="row">
      <span class="mono-label">Length</span>
      <span class="mono value">
        {{ lengthKm != null ? `${lengthKm.toFixed(2)} km` : "—" }}
      </span>
    </div>
    <div class="row">
      <span class="mono-label">Oneway</span>
      <span class="mono value">{{ tags.oneway || "—" }}</span>
    </div>
    <div class="row">
      <span class="mono-label">Surface</span>
      <span class="mono value">{{ tags.surface || "—" }}</span>
    </div>

    <div v-if="store.network.editing" class="actions">
      <button
        class="btn small"
        :class="{ on: store.network.vertexEdit }"
        @click="setVertexEdit(!store.network.vertexEdit)"
      >
        {{ store.network.vertexEdit ? "Done editing shape" : "Edit shape" }}
      </button>
      <button class="btn small danger" @click="deleteNetworkWay">Delete</button>
    </div>
    <p v-if="store.network.editing && store.network.vertexEdit" class="note">
      Drag the white handles to move the way's vertices.
    </p>
  </div>
</template>

<style scoped>
.way-card {
  background: var(--surface);
  border: 1px solid var(--accent-border);
  border-radius: var(--r-card);
  padding: 10px 11px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row .mono-label {
  width: 68px;
  flex: none;
}
.value {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mono.value {
  font-size: 10.5px;
}
.row select {
  flex: 1;
  font: 11.5px var(--mono);
  border: 1px solid var(--border-3);
  border-radius: var(--r-btn-sm);
  padding: 3px 5px;
  background: var(--surface);
}
.actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}
.actions .on {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.actions .danger {
  color: var(--error);
}
.note {
  margin: 0;
  font-size: 10.5px;
  color: var(--ink-5);
}
</style>
