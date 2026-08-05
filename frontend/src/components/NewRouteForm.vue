<script setup>
import { onMounted, ref } from "vue";

import { addRoute, agencyOptions } from "../actions/routes.js";
import { MODES } from "../modes.js";
import { store } from "../store.js";

const props = defineProps({ feedName: { type: String, required: true } });
const emit = defineEmits(["close"]);

const routeId = ref("");
const shortName = ref("");
const routeType = ref(3);
const agencyId = ref("");
const agencies = ref([]);
const submitting = ref(false);

onMounted(async () => {
  agencies.value = await agencyOptions();
});

async function submit() {
  if (!routeId.value.trim() || submitting.value) return;
  submitting.value = true;
  const added = await addRoute({
    routeId: routeId.value.trim(),
    shortName: shortName.value.trim(),
    routeType: routeType.value,
    agencyId: agencyId.value,
  });
  submitting.value = false;
  if (added) emit("close");
}
</script>

<template>
  <div class="route-form">
    <div class="grid">
      <label class="field">
        <span class="mono-label">Route_id</span>
        <input v-model="routeId" placeholder="e.g. M60" @keydown.enter="submit" />
      </label>
      <label class="field">
        <span class="mono-label">Short name</span>
        <input v-model="shortName" placeholder="e.g. 60" @keydown.enter="submit" />
      </label>
      <label class="field">
        <span class="mono-label">Mode</span>
        <select v-model="routeType">
          <option v-for="mode in MODES" :key="mode.code" :value="mode.code">
            {{ mode.label }}
          </option>
        </select>
      </label>
      <label class="field">
        <span class="mono-label">Agency</span>
        <select v-model="agencyId">
          <option value="">(feed default)</option>
          <option v-for="agency in agencies" :key="agency.id" :value="agency.id">
            {{ agency.name }}
          </option>
        </select>
      </label>
    </div>
    <p class="note">
      Creates the route in {{ feedName }}, then switches to the + Shape tool
      to draw its geometry.
    </p>
    <div class="actions">
      <button
        class="btn dark"
        :disabled="!routeId.trim() || submitting || !store.editMode"
        @click="submit"
      >
        Add route
      </button>
      <button class="btn" @click="emit('close')">Cancel</button>
    </div>
  </div>
</template>

<style scoped>
.route-form {
  border: 1px dashed var(--accent-border);
  background: var(--accent-tint);
  border-radius: var(--r-card);
  padding: 11px;
  display: flex;
  flex-direction: column;
  gap: 9px;
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
.field input,
.field select {
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 8px;
  background: var(--surface);
  color: var(--ink);
  min-width: 0;
}
.field input:focus,
.field select:focus {
  outline: none;
  border-color: var(--accent-border);
}
.note {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--ink-3);
}
.actions {
  display: flex;
  gap: 7px;
}
.actions .dark {
  flex: 1;
  justify-content: center;
}
</style>
