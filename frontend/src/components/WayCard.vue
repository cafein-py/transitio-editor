<script setup>
import { computed } from "vue";

import { deleteNetworkWay, reclassifyWay } from "../actions/streets.js";
import { waysData } from "../entities.js";
import { selectWay, setVertexEdit } from "../map/streets.js";
import { networkTags } from "../network.js";
import { highwayClass, lineLengthKm, wayClass, wayHighway } from "../streets.js";
import { store } from "../store.js";

const selected = computed(() => store.network.selected);
const tags = computed(() =>
  Object.fromEntries(networkTags(selected.value || {})),
);
const highway = computed(() => wayHighway(selected.value) || "");
const classColor = computed(() => {
  const entry = highwayClass(wayClass(selected.value || {}));
  return entry ? entry.color : "#9aa0a8";
});

const lengthKm = computed(() => {
  void store.networkVersion;
  if (!selected.value) return null;
  const way = waysData().find((f) => f.properties.id === selected.value.id);
  return way ? lineLengthKm(way.geometry.coordinates) : null;
});

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
    <div class="card-head">
      <span class="class-dot" :style="{ background: classColor }"></span>
      <span class="head-name">{{ tags.name || `way/${selected.id}` }}</span>
      <button class="close" aria-label="Close" @click="selectWay(null)">
        ×
      </button>
    </div>

    <div class="fields">
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
  width: 300px;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: 12px;
  box-shadow: 0 4px 18px rgba(20, 22, 26, 0.14);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 11px 12px 8px;
}
.class-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--r-swatch);
  flex: none;
}
.head-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 650;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.close {
  border: 0;
  background: none;
  color: var(--ink-4);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
}
.close:hover {
  color: var(--ink);
}
.fields {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 0 12px 10px;
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
  padding: 0 12px 10px;
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
  padding: 0 12px 11px;
  font-size: 10.5px;
  color: var(--ink-5);
}
</style>
