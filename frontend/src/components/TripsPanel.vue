<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { loadRoutes } from "../actions/routes.js";
import { loadServices } from "../actions/services.js";
import {
  applyTripTimes,
  deleteTrip,
  generateFrequency,
  loadTripTimes,
  pickTimetableRoute,
  shiftTrip,
  stopStopPicking,
} from "../actions/trips.js";
import { currentFeed } from "../catalogue.js";
import { stopsData } from "../entities.js";
import * as mapBridge from "../map.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import { store } from "../store.js";
import { estimateTrips, suggestTripId, tripMatches } from "../trips.js";
import FeedSelect from "./FeedSelect.vue";
import NewTripForm from "./NewTripForm.vue";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));

onMounted(async () => {
  await loadRoutes();
  await loadServices();
});
watch(
  () => store.currentFeedId,
  async () => {
    await loadRoutes();
    await loadServices();
    formOpen.value = false;
  },
);

const modeColor = (routeType) =>
  ([...MODES, UNKNOWN_MODE].find((mode) => mode.code === routeType) ||
    UNKNOWN_MODE).color;

const pickedRoute = computed(() =>
  store.routes.find((route) => route.route_id === store.timetableRoute),
);
const routeShort = computed(
  () =>
    (pickedRoute.value &&
      (pickedRoute.value.route_short_name || pickedRoute.value.route_id)) ||
    "trip",
);

// Frequency form state.
const freqStart = ref("05:30");
const freqEnd = ref("23:45");
const headwayMin = ref(8);
const estimate = computed(() =>
  estimateTrips(freqStart.value, freqEnd.value, headwayMin.value * 60),
);
const freqServiceId = computed(() => store.services[0]?.serviceId || "");

async function generate() {
  await generateFrequency({
    tripId: suggestTripId(routeShort.value, freqStart.value, "F"),
    serviceId: freqServiceId.value,
    start: `${freqStart.value}:00`,
    end: `${freqEnd.value}:00`,
    headway: headwayMin.value * 60,
  });
}

// Timetable.
const formOpen = ref(false);
const q = ref("");

// Stop picking is only meaningful while the new-trip form is open on
// this panel; closing either disarms it.
watch(
  () => [store.activePanel, formOpen.value],
  ([panel, open]) => {
    if (panel !== "trips" || !open) stopStopPicking();
  },
);
const shownTrips = computed(() =>
  store.routeTrips.filter((trip) => tripMatches(trip, q.value)),
);
const hhmm = (time) => (time ? String(time).slice(0, 5) : "—");

// Stop-time list two-way selection with the map.
function pickStopRow(row) {
  const feature = stopsData().find(
    (f) =>
      f.properties.stop_id === row.stop_id &&
      f.properties.feed_id === store.currentFeedId,
  );
  store.selectedStopId = {
    stopId: row.stop_id,
    feedId: store.currentFeedId,
  };
  mapBridge.setSelectedStop({
    stop_id: row.stop_id,
    feed_id: store.currentFeedId,
  });
  return feature;
}

function zoomStopRow(row) {
  const feature = pickStopRow(row);
  if (feature) mapBridge.flyToPoint(feature.geometry.coordinates);
}

const rowSelected = (row) =>
  store.selectedStopId && store.selectedStopId.stopId === row.stop_id;
</script>

<template>
  <div class="trips-panel">
    <div class="head">
      <h1>Trips</h1>
      <span class="mono meta">
        {{ store.timetableRoute ? `${store.routeTrips.length} trips` : "" }}
      </span>
    </div>

    <FeedSelect />

    <div class="card freq">
      <span class="form-title">Frequency-based trips</span>
      <label class="field">
        <span class="mono-label">Route in {{ feed ? feed.name : "…" }}</span>
        <div class="route-row">
          <span
            v-if="pickedRoute"
            class="badge mono"
            :style="{ background: modeColor(pickedRoute.route_type) }"
          >
            {{ (pickedRoute.route_short_name || pickedRoute.route_id).slice(0, 4) }}
          </span>
          <select
            :value="store.timetableRoute"
            @change="pickTimetableRoute($event.target.value)"
          >
            <option value="">pick a route…</option>
            <option
              v-for="route in store.routes"
              :key="route.route_id"
              :value="route.route_id"
            >
              {{ route.route_short_name || route.route_id }}
              — {{ route.route_long_name || route.route_id }}
            </option>
          </select>
        </div>
      </label>
      <div class="dates">
        <label class="field">
          <span class="mono-label">Start</span>
          <input v-model="freqStart" class="mono" placeholder="05:30" />
        </label>
        <label class="field">
          <span class="mono-label">End</span>
          <input v-model="freqEnd" class="mono" placeholder="23:45" />
        </label>
      </div>
      <label class="field">
        <span class="mono-label">
          Headway <b class="headway">every {{ headwayMin }} min</b>
        </span>
        <input
          v-model.number="headwayMin"
          type="range"
          min="2"
          max="30"
          class="slider"
        />
      </label>
      <p class="note mono">≈ {{ estimate }} trips generated</p>
      <button
        class="btn dark add"
        :disabled="!store.editMode || !store.timetableRoute || !estimate"
        :title="store.editMode ? null : 'Turn on editing first'"
        @click="generate"
      >
        Generate trips
      </button>
      <p class="note">
        Stop times are copied from the route's existing pattern. Only the
        feed you are editing is written.
      </p>
    </div>

    <div class="list-head">
      <span class="mono-label">Timetable</span>
      <button
        class="btn small new-trip"
        :disabled="!store.editMode || !store.timetableRoute"
        :title="store.editMode ? null : 'Turn on editing first'"
        @click="formOpen = !formOpen"
      >
        + New trip
      </button>
      <span class="mono meta">{{ store.routeTrips.length }} trips</span>
    </div>

    <NewTripForm
      v-if="formOpen && store.timetableRoute"
      :route-short="routeShort"
      @close="formOpen = false"
    />

    <input
      v-model="q"
      class="search"
      placeholder="Search trip id or start time…"
      :disabled="!store.timetableRoute"
    />

    <div class="rows">
      <button
        v-for="trip in shownTrips"
        :key="trip.trip_id"
        class="row"
        :class="{ selected: store.trip && store.trip.trip_id === trip.trip_id }"
        @click="loadTripTimes(trip.trip_id)"
      >
        <span class="row-main">
          <span class="mono row-id">{{ trip.trip_id }}</span>
          <span class="mono row-meta">
            dir {{ trip.direction_id === "" ? "—" : trip.direction_id }} ·
            {{ hhmm(trip.first_departure) }} · {{ trip.stop_count }} stops
          </span>
        </span>
      </button>
      <p v-if="store.timetableRoute && !shownTrips.length" class="mono empty">
        no matching trips
      </p>
      <p v-if="!store.timetableRoute" class="mono empty">
        pick a route to see its timetable
      </p>
    </div>

    <div v-if="store.trip" class="card times">
      <div class="times-head">
        <span class="mono times-id">{{ store.trip.trip_id }}</span>
        <button class="btn small danger" :disabled="!store.editMode" @click="deleteTrip">
          Delete trip
        </button>
      </div>
      <p v-if="!store.editMode" class="note">Read-only — turn on editing.</p>
      <div class="time-rows">
        <div
          v-for="row in store.trip.times"
          :key="row.stop_sequence"
          class="time-row"
          :class="{ selected: rowSelected(row) }"
          title="Click to select the stop; double-click to zoom"
          @click="pickStopRow(row)"
          @dblclick="zoomStopRow(row)"
        >
          <span class="stop-name">{{ row.stop_name || row.stop_id }}</span>
          <input
            v-model="row.arrival_time"
            class="mono time-input"
            :disabled="!store.editMode"
            @click.stop
          />
          <input
            v-model="row.departure_time"
            class="mono time-input"
            :disabled="!store.editMode"
            @click.stop
          />
        </div>
      </div>
      <div class="times-actions">
        <button class="btn small dark" :disabled="!store.editMode" @click="applyTripTimes">
          Apply times
        </button>
        <span class="shift mono">
          shift by
          <input
            v-model.number="store.shiftSeconds"
            type="number"
            step="60"
            :disabled="!store.editMode"
            @click.stop
          />
          s
        </span>
        <button class="btn small" :disabled="!store.editMode" @click="shiftTrip">
          Shift
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trips-panel {
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
.card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.form-title {
  font-size: 12.5px;
  font-weight: 600;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.route-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.badge {
  width: 28px;
  height: 18px;
  border-radius: 4px;
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  display: grid;
  place-items: center;
  flex: none;
  overflow: hidden;
}
.route-row select,
.field input {
  flex: 1;
  min-width: 0;
  font: 11.5px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
  background: var(--surface);
}
.field input.mono {
  font-family: var(--mono);
  font-size: 11px;
}
.dates {
  display: flex;
  gap: 8px;
}
.dates .field {
  flex: 1;
}
.headway {
  float: right;
  font-weight: 600;
  color: var(--ink);
  text-transform: none;
  letter-spacing: 0;
}
.slider {
  accent-color: var(--accent);
  padding: 0;
  border: 0;
}
.note {
  margin: 0;
  font-size: 10.5px;
  color: var(--ink-5);
}
.add {
  justify-content: center;
}
.list-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.list-head .mono-label {
  flex: 1;
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
.row-main {
  flex: 1;
  min-width: 0;
}
.row-id {
  display: block;
  font-size: 11px;
  color: var(--ink);
}
.row-meta {
  display: block;
  font-size: 9.5px;
  color: var(--ink-6);
  margin-top: 2px;
}
.empty {
  margin: 4px 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
.times-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.times-id {
  font-size: 11px;
  font-weight: 600;
}
.danger {
  color: var(--error);
}
.time-rows {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 300px;
  overflow-y: auto;
}
.time-row {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 3px 4px;
  border-radius: var(--r-chip);
  cursor: pointer;
}
.time-row:hover {
  background: var(--track);
}
.time-row.selected {
  background: var(--accent-tint);
}
.stop-name {
  flex: 1;
  min-width: 0;
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.time-input {
  width: 68px;
  font-size: 10.5px;
  border: 1px solid var(--border-3);
  border-radius: var(--r-btn-sm);
  padding: 3px 5px;
  background: var(--surface);
  flex: none;
}
.time-input:disabled {
  background: var(--track);
  color: var(--ink-4);
}
.times-actions {
  display: flex;
  align-items: center;
  gap: 7px;
}
.shift {
  font-size: 10px;
  color: var(--ink-4);
  display: flex;
  align-items: center;
  gap: 4px;
}
.shift input {
  width: 64px;
  font: 10.5px var(--mono);
  border: 1px solid var(--border-3);
  border-radius: var(--r-btn-sm);
  padding: 3px 5px;
}
</style>
