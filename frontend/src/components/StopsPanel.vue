<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { stopsData } from "../entities.js";
import { currentFeed } from "../catalogue.js";
import * as mapBridge from "../map.js";
import { fetchQuality } from "../quality.js";
import { store } from "../store.js";
import { useEntityList } from "../composables/useEntityList.js";
import FlagChips from "./FlagChips.vue";
import ListPager from "./ListPager.vue";

const scope = ref("all"); // "all" | "current" | "view"

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));
const feedName = (feedId) => {
  const entry = store.catalogue.find((f) => f.feed_id === feedId);
  return entry ? entry.name : feedId;
};

// Rows from the stops layer data; dataVersion re-runs this after every
// refresh, mapMoved keeps the "In map view" scope live.
const items = computed(() => {
  void store.dataVersion;
  let features = stopsData();
  if (scope.value === "current" && store.currentFeedId) {
    features = features.filter(
      (f) => f.properties.feed_id === store.currentFeedId,
    );
  } else if (scope.value === "view") {
    void store.mapMoved;
    const bbox = mapBridge.getViewportBbox();
    if (bbox) {
      const [minx, miny, maxx, maxy] = bbox;
      features = features.filter((f) => {
        const [lon, lat] = f.geometry.coordinates;
        return lon >= minx && lon <= maxx && lat >= miny && lat <= maxy;
      });
    }
  }
  return features.map((f) => ({
    stopId: f.properties.stop_id,
    name: f.properties.stop_name || "",
    code: f.properties.stop_code || "",
    feedId: f.properties.feed_id,
    color: f.properties.feed_color || "#7f7f7f",
    lon: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
  }));
});

const list = useEntityList({
  items,
  fields: (stop) => [stop.name, stop.stopId, stop.code],
  noun: "matches",
});
list.defineFlag("noname", (stop) => !stop.name.trim());

// "No trips" / "Off shape" need server-side joins; the chips disable
// themselves until the quality endpoint exists.
const quality = ref(null);
onMounted(async () => {
  quality.value = await fetchQuality("stops");
});

const chips = computed(() => [
  { key: "all", label: "All", count: list.flagCount("all") },
  { key: "noname", label: "No name", count: list.flagCount("noname") },
  { key: "notrips", label: "No trips", count: null, disabled: !quality.value },
  { key: "offshape", label: "Off shape", count: null, disabled: !quality.value },
]);

const isSelected = (stop) =>
  store.selectedStopId &&
  store.selectedStopId.stopId === stop.stopId &&
  store.selectedStopId.feedId === stop.feedId;

function selectRow(stop) {
  store.selectedStopId = { stopId: stop.stopId, feedId: stop.feedId };
  store.inspector = { stopId: stop.stopId, name: stop.name, feedId: stop.feedId };
  mapBridge.setSelectedStop({ stop_id: stop.stopId, feed_id: stop.feedId });
}

// Map selection → the row: jump to its page and scroll it into view
// (only while this panel is the one in use).
watch(
  () => [store.selectedStopId, store.activePanel],
  () => {
    if (store.activePanel !== "stops" || !store.selectedStopId) return;
    list.reveal(isSelected);
  },
);
</script>

<template>
  <div class="stops-panel">
    <div class="head">
      <h1>Stops</h1>
      <span class="mono meta">{{ list.total.value }} matches</span>
    </div>

    <input
      v-model="list.q.value"
      class="search"
      placeholder="Search name, stop_id or code…"
    />

    <div class="seg scope">
      <button :class="{ active: scope === 'all' }" @click="scope = 'all'">
        All visible
      </button>
      <button
        :class="{ active: scope === 'current' }"
        :disabled="!feed"
        @click="scope = 'current'"
      >
        {{ feed ? feed.name : "Current feed" }}
      </button>
      <button :class="{ active: scope === 'view' }" @click="scope = 'view'">
        In map view
      </button>
    </div>

    <FlagChips v-model="list.flag.value" :chips="chips" />

    <ListPager
      :label="list.label.value"
      :can-prev="list.canPrev.value"
      :can-next="list.canNext.value"
      @prev="list.prev"
      @next="list.next"
    />

    <div :ref="(el) => (list.listEl.value = el)" class="rows">
      <button
        v-for="stop in list.rows.value"
        :key="`${stop.feedId}/${stop.stopId}`"
        class="row"
        :class="{ selected: isSelected(stop) }"
        :data-selected="isSelected(stop) || null"
        @click="selectRow(stop)"
      >
        <span class="pin" :style="{ background: stop.color }"></span>
        <span class="row-main">
          <span class="row-name">{{ stop.name || "(unnamed stop)" }}</span>
          <span class="mono row-meta">
            {{ stop.stopId }} · {{ feedName(stop.feedId) }} ·
            {{ stop.lat.toFixed(5) }}, {{ stop.lon.toFixed(5) }}
          </span>
        </span>
      </button>
      <p v-if="!list.rows.value.length" class="mono empty">no matching stops</p>
    </div>
  </div>
</template>

<style scoped>
.stops-panel {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.head h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.meta {
  font-size: 9.5px;
  color: var(--ink-5);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.search {
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 7px 10px;
  background: var(--surface);
}
.search:focus {
  outline: none;
  border-color: var(--accent-border);
}
.seg {
  display: flex;
  background: var(--track);
  border-radius: var(--r-input);
  padding: 2px;
  gap: 1px;
}
.seg button {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 4px 6px;
  font: 500 11px var(--sans);
  color: var(--ink-4);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-thumb);
}
.seg button:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
.rows {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 8px 9px;
  cursor: pointer;
}
.row:hover {
  border-color: var(--border-4);
}
.row.selected {
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.pin {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  margin-top: 3px;
}
.row-main {
  min-width: 0;
}
.row-name {
  display: block;
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.3;
}
.row-meta {
  display: block;
  font-size: 9.5px;
  color: var(--ink-6);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.empty {
  margin: 4px 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
</style>
