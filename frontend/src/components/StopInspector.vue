<script setup>
import { computed, ref, watch } from "vue";

import { closeInspector, startMovingStop, toggleEditMode } from "../actions.js";
import { toggleEditTarget } from "../actions/catalogue.js";
import { applyStopEdits } from "../actions/stops.js";
import { currentFeed } from "../catalogue.js";
import { stopsData } from "../entities.js";
import { store } from "../store.js";

// The selected stop's full properties, from the stops layer data.
const feature = computed(() => {
  void store.dataVersion;
  const selected = store.inspector;
  if (!selected) return null;
  return (
    stopsData().find(
      (f) =>
        f.properties.stop_id === selected.stopId &&
        (!selected.feedId || f.properties.feed_id === selected.feedId),
    ) || null
  );
});

const feed = computed(() => {
  const feedId = store.inspector && store.inspector.feedId;
  return (
    store.catalogue.find((entry) => entry.feed_id === feedId) ||
    currentFeed(store.catalogue, store.currentFeedId)
  );
});

const ownFeed = computed(
  () =>
    store.inspector &&
    (!store.inspector.feedId ||
      store.inspector.feedId === store.currentFeedId),
);
const editable = computed(() => store.editMode && ownFeed.value);

// Draft fields, re-seeded whenever the selection or data changes.
const name = ref("");
const latLon = ref("");
watch(
  feature,
  (f) => {
    if (!store.inspector) return;
    name.value = store.inspector.name || "";
    if (f) {
      const [lon, lat] = f.geometry.coordinates;
      latLon.value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
      name.value = f.properties.stop_name || "";
    }
  },
  { immediate: true },
);

const zoneId = computed(
  () => (feature.value && feature.value.properties.zone_id) || null,
);

// The band's action: editing this stop may first need its feed current.
async function enable() {
  if (ownFeed.value) toggleEditMode();
  else if (feed.value) await toggleEditTarget(feed.value);
}

async function apply() {
  await applyStopEdits({
    stopId: store.inspector.stopId,
    name: name.value,
    latLon: latLon.value,
  });
}
</script>

<template>
  <div v-if="store.inspector" class="stop-card">
    <div class="card-head">
      <span
        class="swatch"
        :style="{ background: feed ? feed.color : '#ccc' }"
      ></span>
      <span class="feed-name">{{ feed ? feed.name : "" }}</span>
      <button class="close" aria-label="Close" @click="closeInspector">×</button>
    </div>

    <div v-if="!editable" class="band">
      <span>
        {{
          store.editMode
            ? "Read-only — this stop belongs to another feed."
            : "Editing is off for this workspace."
        }}
      </span>
      <button class="band-btn" @click="enable">
        {{ store.editMode ? "Switch" : "Enable" }}
      </button>
    </div>

    <div class="fields">
      <label class="field">
        <span class="mono-label">Stop_name</span>
        <input v-model="name" :readonly="!editable" :class="{ ro: !editable }" />
      </label>
      <label class="field">
        <span class="mono-label">Stop_id</span>
        <input class="mono ro" :value="store.inspector.stopId" readonly />
      </label>
      <label class="field">
        <span class="mono-label">Stop_lat / stop_lon</span>
        <input
          v-model="latLon"
          class="mono"
          :readonly="!editable"
          :class="{ ro: !editable }"
        />
      </label>
      <label v-if="zoneId" class="field">
        <span class="mono-label">Zone_id</span>
        <input class="mono ro" :value="zoneId" readonly />
      </label>
    </div>

    <div v-if="editable" class="card-actions">
      <button class="btn small dark" @click="apply">Apply</button>
      <button
        class="btn small"
        :class="{ moving: store.movingStop }"
        @click="startMovingStop"
      >
        {{ store.movingStop ? "Click the new location…" : "Move" }}
      </button>
    </div>
    <p v-if="editable" class="note">
      Move, then click the stop's new location on the map.
    </p>
  </div>
</template>

<style scoped>
.stop-card {
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
  padding: 11px 12px;
}
.feed-name {
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
.band {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--accent-tint);
  border-top: 1px solid var(--border-1);
  border-bottom: 1px solid var(--border-1);
  padding: 8px 12px;
  font-size: 11.5px;
  color: var(--accent);
}
.band span {
  flex: 1;
}
.band-btn {
  border: 1px solid var(--accent-border);
  background: var(--surface);
  color: var(--accent);
  border-radius: var(--r-input);
  padding: 4px 11px;
  font: 500 11.5px var(--sans);
  cursor: pointer;
  flex: none;
}
.fields {
  display: flex;
  flex-direction: column;
  gap: 9px;
  padding: 11px 12px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field input {
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 7px 9px;
  background: var(--surface);
  color: var(--ink);
}
.field input.mono {
  font-family: var(--mono);
  font-size: 11.5px;
}
.field input.ro {
  background: var(--track);
  color: var(--ink-4);
}
.field input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.card-actions {
  display: flex;
  gap: 7px;
  padding: 0 12px;
}
.card-actions .moving {
  border-color: var(--accent-border);
  color: var(--accent);
}
.note {
  margin: 0;
  padding: 7px 12px 11px;
  font-size: 10.5px;
  color: var(--ink-5);
}
</style>
