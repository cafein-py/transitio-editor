<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { addService, loadServices } from "../actions/services.js";
import { currentFeed } from "../catalogue.js";
import {
  calendarSpan,
  DAY_ABBR,
  daySummary,
  gtfsToInput,
  inputToGtfs,
} from "../services.js";
import { store } from "../store.js";
import FeedSelect from "./FeedSelect.vue";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));

const serviceId = ref("");
const days = ref(Array(7).fill(false));
const from = ref("");
const to = ref("");
const selectedServiceId = ref(null);
const idInput = ref(null);

const span = computed(() => calendarSpan(store.services));

// A blank form: no id, no days, dates prefilled from the calendar span.
function resetForm(focus = false) {
  serviceId.value = "";
  days.value = Array(7).fill(false);
  const s = span.value;
  from.value = s ? gtfsToInput(s.from) : "";
  to.value = s ? gtfsToInput(s.to) : "";
  selectedServiceId.value = null;
  if (focus) idInput.value?.focus();
}

onMounted(async () => {
  await loadServices();
  resetForm();
});

// A feed switch clears the draft IMMEDIATELY (before the new feed's
// services arrive), so the old feed's draft can never be submitted
// against the new one, then reloads and re-prefills the dates.
watch(
  () => [store.currentFeedId, store.workspaceVersion],
  async () => {
    store.services = [];
    resetForm();
    await loadServices();
    resetForm();
  },
);
// Prefill dates once the span is known (initial load).
watch(span, (value, old) => {
  if (value && !old && !from.value && !selectedServiceId.value) {
    from.value = gtfsToInput(value.from);
    to.value = gtfsToInput(value.to);
  }
});

const editing = computed(() => selectedServiceId.value !== null);

function pickService(row) {
  selectedServiceId.value = row.serviceId;
  serviceId.value = row.serviceId;
  days.value = [...row.days];
  from.value = gtfsToInput(row.from);
  to.value = gtfsToInput(row.to);
}

function toggleDay(index) {
  if (!store.editMode || editing.value) return;
  days.value = days.value.map((on, i) => (i === index ? !on : on));
}

async function submit() {
  const added = await addService({
    serviceId: serviceId.value,
    days: days.value,
    from: inputToGtfs(from.value),
    to: inputToGtfs(to.value),
  });
  if (added) resetForm();
}
</script>

<template>
  <div class="cal-panel">
    <div class="head">
      <h1>Services</h1>
      <span class="mono meta">{{ store.services.length }} services</span>
    </div>

    <FeedSelect />

    <div class="form card">
      <div class="form-head">
        <span class="form-title">
          {{ editing ? "Edit service" : "New service" }}
        </span>
        <button
          v-if="editing"
          class="btn small"
          @click="resetForm(true)"
        >
          + New service
        </button>
      </div>
      <input
        ref="idInput"
        v-model="serviceId"
        class="id-input mono"
        :class="{ unnamed: !serviceId.trim() }"
        placeholder="give this service an id…"
        :disabled="!store.editMode || editing"
      />
      <div class="day-row">
        <button
          v-for="(abbr, index) in DAY_ABBR"
          :key="abbr"
          class="day mono"
          :class="{ on: days[index] }"
          :disabled="!store.editMode || editing"
          @click="toggleDay(index)"
        >
          {{ abbr }}
        </button>
      </div>
      <div class="dates">
        <label class="field">
          <span class="mono-label">From</span>
          <input
            v-model="from"
            type="date"
            :disabled="!store.editMode || editing"
          />
        </label>
        <label class="field">
          <span class="mono-label">To</span>
          <input
            v-model="to"
            type="date"
            :disabled="!store.editMode || editing"
          />
        </label>
      </div>
      <p class="note">
        {{
          editing
            ? "Editing an existing service needs backend support — view only for now."
            : span
              ? `Dates prefilled from ${feed ? feed.name : "the feed"}'s calendar span.`
              : "No calendar yet — pick the dates yourself."
        }}
      </p>
      <div class="actions">
        <template v-if="editing">
          <button class="btn small dark" disabled title="Needs backend support">
            Save changes
          </button>
          <button class="btn small danger" disabled title="Needs backend support">
            Delete
          </button>
        </template>
        <button
          v-else
          class="btn dark add"
          :disabled="!store.editMode"
          :title="store.editMode ? null : 'Turn on editing first'"
          @click="submit"
        >
          Add service
        </button>
      </div>
    </div>

    <div class="list-head">
      <span class="mono-label">In {{ feed ? feed.name : "…" }}</span>
      <button class="btn small" @click="resetForm(true)">+ New service</button>
    </div>

    <div class="rows">
      <button
        v-for="row in store.services"
        :key="row.serviceId"
        class="row"
        :class="{ selected: selectedServiceId === row.serviceId }"
        @click="pickService(row)"
      >
        <span class="row-main">
          <span class="mono row-id">{{ row.serviceId }}</span>
          <span class="mono row-meta">
            {{ daySummary(row.days) }} · {{ gtfsToInput(row.from) }} →
            {{ gtfsToInput(row.to) }}
          </span>
        </span>
        <span class="pencil">✎</span>
      </button>
      <p v-if="!store.services.length" class="mono empty">
        no services in this feed yet
      </p>
    </div>

    <button class="manage mono" @click="store.activePanel = 'agencies'">
      Manage agencies →
    </button>
  </div>
</template>

<style scoped>
.cal-panel {
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
.form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.form-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.form-title {
  font-size: 12.5px;
  font-weight: 600;
}
.id-input {
  font-size: 11.5px;
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 7px 9px;
  background: var(--surface);
  color: var(--ink);
}
.id-input.unnamed {
  border-color: var(--accent-border);
  background: var(--accent-tint);
  color: var(--accent);
}
.id-input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.id-input:disabled {
  background: var(--track);
  color: var(--ink-4);
}
.day-row {
  display: flex;
  gap: 4px;
}
.day {
  flex: 1;
  font-size: 9.5px;
  border: 1px solid var(--border-3);
  background: var(--surface);
  color: var(--ink-4);
  border-radius: var(--r-chip);
  padding: 5px 0;
  cursor: pointer;
}
.day.on {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.day:disabled {
  cursor: default;
  opacity: 0.6;
}
.dates {
  display: flex;
  gap: 8px;
}
.field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field input {
  font: 11.5px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
  background: var(--surface);
}
.field input:disabled {
  background: var(--track);
  color: var(--ink-4);
}
.note {
  margin: 0;
  font-size: 10.5px;
  color: var(--ink-5);
}
.actions {
  display: flex;
  gap: 6px;
}
.actions .add {
  flex: 1;
  justify-content: center;
}
.actions .danger {
  color: var(--error);
}
.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 2px;
}
.rows {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
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
.pencil {
  color: var(--ink-5);
  font-size: 11px;
  flex: none;
}
.empty {
  margin: 4px 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
.manage {
  border: 0;
  background: none;
  color: var(--accent);
  font-size: 10px;
  text-align: left;
  cursor: pointer;
  padding: 2px;
}
</style>
