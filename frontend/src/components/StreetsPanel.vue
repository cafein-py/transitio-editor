<script setup>
import { computed, ref, watch } from "vue";

import {
  acquireOsm,
  cancelAcquire,
  loadNetwork,
  resetNetwork,
  resolveOsmByPlace,
  resolveOsmByView,
  saveNetwork,
  toggleNetworkEditing,
  toggleNetworkVisible,
} from "../actions/streets.js";
import { toggleFeedVisible } from "../actions.js";
import { waysData } from "../entities.js";
import * as mapBridge from "../map.js";
import { selectWay } from "../map/streets.js";
import {
  classCounts,
  HIGHWAY_CLASSES,
  highwayClass,
  lineLengthKm,
  wayClass,
  wayHighway,
} from "../streets.js";
import { store } from "../store.js";
import { useEntityList } from "../composables/useEntityList.js";
import HighwayLegend from "./HighwayLegend.vue";
import ListPager from "./ListPager.vue";

// The panel retries the eager startup load (no-op once loaded).
watch(
  () => store.activePanel,
  (panel) => {
    if (panel === "streets") loadNetwork();
  },
);

const extractName = computed(() => {
  const source = store.network.source;
  return source ? source.split("/").pop() : "no extract loaded";
});

// Way rows from the raw network data; class and length are cached on the
// feature (a 100k-way extract cannot re-measure per keystroke).
const rows = computed(() => {
  void store.networkVersion;
  return waysData().map((feature) => {
    if (!feature._streets) {
      const properties = feature.properties;
      feature._streets = {
        id: properties.id,
        name: (() => {
          let tags = properties.tags;
          if (typeof tags === "string") {
            try {
              tags = JSON.parse(tags);
            } catch (error) {
              tags = null;
            }
          }
          return (
            properties.name || (tags && tags.name) || ""
          );
        })(),
        cls: wayClass(properties),
        km: lineLengthKm(feature.geometry.coordinates),
        properties,
      };
    }
    return feature._streets;
  });
});

const counts = computed(() => {
  void store.networkVersion;
  return classCounts(waysData());
});

const visibleRows = computed(() =>
  rows.value.filter((row) => !store.hiddenHighwayClasses.includes(row.cls)),
);

const list = useEntityList({
  items: visibleRows,
  fields: (row) => [row.name, String(row.id)],
  noun: "ways",
});

function selectRow(row) {
  selectWay(row.properties);
}

function zoomToRow(row) {
  selectRow(row);
  const way = waysData().find((f) => f.properties.id === row.id);
  if (!way) return;
  const coords = way.geometry.coordinates;
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  mapBridge.fitBbox([
    Math.min(...lons),
    Math.min(...lats),
    Math.max(...lons),
    Math.max(...lats),
  ]);
}

const swatchStyle = (cls) => {
  const entry = highwayClass(cls);
  return entry || { color: "#9aa0a8", width: 1.5, dash: null };
};

const acquireOpen = ref(false);
</script>

<template>
  <div class="streets-panel">
    <div class="head">
      <h1>Street network</h1>
      <span class="mono meta">{{ list.total.value }} ways</span>
    </div>

    <div class="extract-row">
      <span class="dot" :class="{ off: !store.network.available }"></span>
      <span class="mono extract-name" :title="store.network.source">
        {{ extractName }}
      </span>
      <button class="btn small" @click="acquireOpen = !acquireOpen">Swap</button>
    </div>

    <!-- Transitional acquire block until the unified search absorbs it. -->
    <div v-if="acquireOpen" class="acquire card">
      <input
        v-model="store.network.acquire.place"
        placeholder="Place name…"
        @keyup.enter="resolveOsmByPlace"
      />
      <div class="acquire-row">
        <button class="btn small" @click="resolveOsmByPlace">Find place</button>
        <button class="btn small" @click="resolveOsmByView">Use map view</button>
      </div>
      <p v-if="store.network.acquire.resolving" class="mono note">resolving…</p>
      <p v-if="store.network.acquire.error" class="mono error">
        {{ store.network.acquire.error }}
      </p>
      <div v-if="store.network.acquire.resolved" class="acquire-row">
        <span class="mono note resolved-name">
          {{ store.network.acquire.resolved.name }}
        </span>
        <button
          class="btn small dark"
          :disabled="store.network.acquire.downloading"
          @click="acquireOsm()"
        >
          {{ store.network.acquire.downloading ? "Downloading…" : "Download" }}
        </button>
        <button class="btn small" @click="cancelAcquire">Cancel</button>
      </div>
    </div>

    <button
      class="edit-pill"
      :class="{ on: store.network.editing }"
      :disabled="!store.network.available"
      @click="toggleNetworkEditing"
    >
      <span class="knob"></span>
      {{
        store.network.editing
          ? "Editing street network"
          : "Editing off — read-only"
      }}
    </button>

    <div class="layer-pills">
      <button
        class="pill-toggle"
        :class="{ on: store.network.visible }"
        @click="toggleNetworkVisible"
      >
        Streets
      </button>
      <button
        class="pill-toggle"
        :class="{ on: store.feedVisible }"
        @click="toggleFeedVisible"
      >
        GTFS feed
      </button>
    </div>

    <input
      v-model="list.q.value"
      class="search"
      placeholder="Search street name or osm id…"
    />

    <HighwayLegend :counts="counts" />

    <ListPager
      :label="list.label.value"
      :can-prev="list.canPrev.value"
      :can-next="list.canNext.value"
      @prev="list.prev"
      @next="list.next"
    />

    <div :ref="(el) => (list.listEl.value = el)" class="rows">
      <button
        v-for="row in list.rows.value"
        :key="row.id"
        class="row"
        :class="{
          selected: store.network.selected && store.network.selected.id === row.id,
        }"
        :data-selected="
          (store.network.selected && store.network.selected.id === row.id) ||
          null
        "
        title="Double-click to zoom to the way"
        @click="selectRow(row)"
        @dblclick="zoomToRow(row)"
      >
        <svg viewBox="0 0 30 8" class="line-swatch">
          <line
            x1="1"
            y1="4"
            x2="29"
            y2="4"
            :stroke="swatchStyle(row.cls).color"
            :stroke-width="Math.min(6, swatchStyle(row.cls).width * 1.1)"
            :stroke-dasharray="
              swatchStyle(row.cls).dash
                ? swatchStyle(row.cls).dash.join(' ')
                : null
            "
            stroke-linecap="round"
          />
        </svg>
        <span class="row-main">
          <span class="row-name">{{ row.name || "(unnamed way)" }}</span>
          <span class="mono row-meta">
            {{ row.cls }} · {{ row.km.toFixed(2) }} km · way/{{ row.id }}
          </span>
        </span>
      </button>
      <p v-if="!list.rows.value.length" class="mono empty">
        {{ store.network.available ? "no matching ways" : "no extract loaded" }}
      </p>
    </div>

    <div v-if="store.network.editing" class="save-footer card">
      <label class="field">
        <span class="mono-label">Output .osm.pbf</span>
        <input v-model="store.network.savePath" class="mono" />
      </label>
      <div class="footer-actions">
        <button
          class="btn small dark"
          :disabled="!store.network.savePath.trim()"
          @click="saveNetwork"
        >
          Save
        </button>
        <button class="btn small danger" @click="resetNetwork">
          Discard network edits
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.streets-panel {
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
.extract-row {
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 7px 9px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ok);
  flex: none;
}
.dot.off {
  background: var(--ink-disabled);
}
.extract-name {
  flex: 1;
  min-width: 0;
  font-size: 10.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acquire {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.acquire input {
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 9px;
}
.acquire-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.resolved-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.note {
  margin: 0;
  font-size: 10px;
  color: var(--ink-5);
}
.error {
  margin: 0;
  font-size: 10px;
  color: var(--error);
}
.edit-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-2);
  background: var(--surface);
  border-radius: var(--r-pill);
  padding: 6px 12px 6px 6px;
  font: 500 12px var(--sans);
  color: var(--ink-3);
  cursor: pointer;
}
.edit-pill .knob {
  width: 24px;
  height: 14px;
  border-radius: 8px;
  background: rgba(20, 22, 26, 0.18);
  box-shadow: inset -10px 0 0 -4px #fff;
  flex: none;
  transition: background 0.12s;
}
.edit-pill.on {
  border-color: var(--accent-border);
  background: var(--accent-tint);
  color: var(--ink);
}
.edit-pill.on .knob {
  background: var(--accent);
  box-shadow: inset 10px 0 0 -4px #fff;
}
.edit-pill:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
.layer-pills {
  display: flex;
  gap: 6px;
}
.pill-toggle {
  flex: 1;
  border: 1px solid var(--border-3);
  background: var(--surface);
  color: var(--ink-4);
  border-radius: var(--r-pill);
  padding: 5px 0;
  font: 500 11.5px var(--sans);
  cursor: pointer;
}
.pill-toggle.on {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-tint);
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
.rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  align-items: center;
  gap: 9px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 7px 9px;
  cursor: pointer;
}
.row:hover {
  border-color: var(--border-4);
}
.row.selected {
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.line-swatch {
  width: 30px;
  height: 8px;
  flex: none;
}
.row-main {
  flex: 1;
  min-width: 0;
}
.row-name {
  display: block;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.25;
}
.row-meta {
  display: block;
  font-size: 9.5px;
  color: var(--ink-6);
  margin-top: 1px;
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
.save-footer {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.save-footer .field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.save-footer input {
  font: 10.5px var(--mono);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
}
.footer-actions {
  display: flex;
  gap: 6px;
}
.footer-actions .danger {
  color: var(--error);
}
</style>
