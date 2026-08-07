<script setup>
import { computed, ref, watch } from "vue";

import {
  addSingleTrip,
  clearPickedStops,
  toggleStopPicking,
} from "../actions/trips.js";
import { store } from "../store.js";
import { suggestTripId, validStart } from "../trips.js";

const props = defineProps({
  routeShort: { type: String, required: true },
});
const emit = defineEmits(["close"]);

const tripId = ref("");
const idOverridden = ref(false);
const shapeId = ref("");
const start = ref("05:30");
const dir = ref(0);
const serviceId = ref(store.services[0]?.serviceId || "");
const submitting = ref(false);

// The id follows short name + start + dir until the user edits it.
watch(
  [start, dir, () => props.routeShort],
  () => {
    if (!idOverridden.value) {
      tripId.value = suggestTripId(props.routeShort, start.value, dir.value);
    }
  },
  { immediate: true },
);

const startValid = computed(() => validStart(start.value));

async function submit() {
  if (submitting.value) return;
  submitting.value = true;
  const added = await addSingleTrip({
    tripId: tripId.value.trim(),
    serviceId: serviceId.value,
    shapeId: shapeId.value.trim(),
    start: start.value,
  });
  submitting.value = false;
  if (added) emit("close");
}

function cancel() {
  store.tripPicking = false;
  clearPickedStops();
  emit("close");
}
</script>

<template>
  <div class="trip-form">
    <div class="grid">
      <label class="field wide">
        <span class="mono-label">Trip_id</span>
        <input
          v-model="tripId"
          class="mono"
          @input="idOverridden = true"
        />
      </label>
      <label class="field">
        <span class="mono-label">Shape_id</span>
        <input v-model="shapeId" class="mono" placeholder="route shape" />
      </label>
      <label class="field">
        <span class="mono-label">Start</span>
        <input
          v-model="start"
          class="mono"
          :class="{ bad: !startValid }"
          placeholder="05:30"
        />
      </label>
      <label class="field">
        <span class="mono-label">Dir</span>
        <div class="seg">
          <button :class="{ active: dir === 0 }" @click="dir = 0">0</button>
          <button :class="{ active: dir === 1 }" @click="dir = 1">1</button>
        </div>
      </label>
      <label class="field">
        <span class="mono-label">Service</span>
        <select v-model="serviceId">
          <option
            v-for="service in store.services"
            :key="service.serviceId"
            :value="service.serviceId"
          >
            {{ service.serviceId }}
          </option>
        </select>
      </label>
    </div>

    <div class="picking">
      <button
        class="btn small"
        :class="{ on: store.tripPicking }"
        @click="toggleStopPicking"
      >
        {{ store.tripPicking ? "Picking… click stops" : "Pick stops on the map" }}
      </button>
      <span class="mono count">{{ store.tripStops.length }} picked</span>
      <button
        v-if="store.tripStops.length"
        class="btn small"
        @click="clearPickedStops"
      >
        Clear stops
      </button>
    </div>
    <p class="note">
      Left empty, the stop pattern is copied from one of the route's
      existing trips, shifted to the start time.
    </p>

    <div class="actions">
      <button
        class="btn dark add"
        :disabled="!tripId.trim() || !startValid || !serviceId || submitting"
        @click="submit"
      >
        Add trip
      </button>
      <button class="btn" @click="cancel">Cancel</button>
    </div>
  </div>
</template>

<style scoped>
.trip-form {
  border: 1px dashed var(--accent-border);
  background: var(--accent-tint);
  border-radius: var(--r-card);
  padding: 11px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.field.wide {
  grid-column: span 2;
}
.field input,
.field select {
  font: 11.5px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
  background: var(--surface);
  min-width: 0;
}
.field input.mono,
.field select {
  font-family: var(--mono);
  font-size: 11px;
}
.field input.bad {
  border-color: var(--error);
}
.field input:focus,
.field select:focus {
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
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 4px 0;
  font: 500 11px var(--mono);
  color: var(--ink-4);
  cursor: pointer;
}
.seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-thumb);
}
.picking {
  display: flex;
  align-items: center;
  gap: 8px;
}
.picking .on {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--surface);
}
.count {
  font-size: 9.5px;
  color: var(--ink-5);
}
.note {
  margin: 0;
  font-size: 10.5px;
  line-height: 1.45;
  color: var(--ink-4);
}
.actions {
  display: flex;
  gap: 6px;
}
.actions .add {
  flex: 1;
  justify-content: center;
}
</style>
