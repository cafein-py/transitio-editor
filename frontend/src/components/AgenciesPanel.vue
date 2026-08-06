<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { addAgency, loadAgencies } from "../actions/agencies.js";
import { currentFeed } from "../catalogue.js";
import { store } from "../store.js";
import FeedSelect from "./FeedSelect.vue";
import Icon from "./Icon.vue";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));

const formOpen = ref(false);
const agencyId = ref("");
const name = ref("");
const url = ref("");
const timezone = ref("");

function resetForm() {
  agencyId.value = "";
  name.value = "";
  url.value = "";
  timezone.value = "";
}

onMounted(loadAgencies);
// The draft closes IMMEDIATELY on a feed switch — before the new feed's
// agencies arrive — so it can never be submitted against another feed.
watch(
  () => store.currentFeedId,
  async () => {
    store.agencies = [];
    resetForm();
    formOpen.value = false;
    await loadAgencies();
  },
);

async function submit() {
  const added = await addAgency({
    agencyId: agencyId.value,
    name: name.value,
    url: url.value,
    timezone: timezone.value,
  });
  if (added) {
    resetForm();
    formOpen.value = false;
  }
}
</script>

<template>
  <div class="agencies-panel">
    <div class="head">
      <h1>Agencies</h1>
      <span class="mono meta">{{ store.agencies.length }} in this feed</span>
    </div>

    <FeedSelect />

    <p class="note">
      Agencies of the current feed — listing every loaded feed at once
      needs backend support.
    </p>

    <button
      class="new-agency"
      :disabled="!feed"
      @click="formOpen = !formOpen"
    >
      + New agency
    </button>

    <div v-if="formOpen" class="form card">
      <label class="field">
        <span class="mono-label">Agency_id</span>
        <input v-model="agencyId" class="mono" placeholder="e.g. HSL" />
      </label>
      <label class="field">
        <span class="mono-label">Name</span>
        <input v-model="name" placeholder="Agency name" />
      </label>
      <label class="field">
        <span class="mono-label">Url</span>
        <input v-model="url" class="mono" placeholder="https://…" />
      </label>
      <label class="field">
        <span class="mono-label">Timezone</span>
        <input v-model="timezone" class="mono" placeholder="Europe/Helsinki" />
      </label>
      <div class="actions">
        <button
          class="btn dark add"
          :disabled="!store.editMode"
          :title="store.editMode ? null : 'Turn on editing first'"
          @click="submit"
        >
          Add agency
        </button>
        <button class="btn" @click="formOpen = false">Cancel</button>
      </div>
    </div>

    <div class="rows">
      <div v-for="agency in store.agencies" :key="agency.agencyId" class="row">
        <span class="row-main">
          <span class="row-name">{{ agency.name || agency.agencyId }}</span>
          <span class="mono row-meta">
            {{ agency.agencyId || "—" }} · {{ agency.timezone || "—" }}
          </span>
        </span>
        <span class="tool" title="Editing an agency needs backend support">
          <Icon name="pencil" />
        </span>
      </div>
      <p v-if="!store.agencies.length" class="mono empty">
        no agencies in this feed yet
      </p>
    </div>
  </div>
</template>

<style scoped>
.agencies-panel {
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
.note {
  margin: 0;
  font-size: 10.5px;
  color: var(--ink-5);
}
.new-agency {
  border: 1px dashed var(--accent-border);
  background: transparent;
  border-radius: 9px;
  padding: 7px;
  font: 11.5px var(--sans);
  color: var(--accent);
  cursor: pointer;
}
.new-agency:hover {
  background: var(--accent-tint);
}
.new-agency:disabled {
  color: var(--ink-disabled);
  border-color: var(--border-4);
  cursor: default;
}
.form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px dashed var(--accent-border);
  background: var(--accent-tint);
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
  padding: 6px 9px;
  background: var(--surface);
}
.field input.mono {
  font-family: var(--mono);
  font-size: 11px;
}
.field input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.actions {
  display: flex;
  gap: 6px;
}
.actions .add {
  flex: 1;
  justify-content: center;
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
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 8px 9px;
}
.row-main {
  flex: 1;
  min-width: 0;
}
.row-name {
  display: block;
  font-size: 12.5px;
  font-weight: 500;
}
.row-meta {
  display: block;
  font-size: 9.5px;
  color: var(--ink-6);
  margin-top: 2px;
}
.tool {
  color: var(--ink-disabled);
  flex: none;
}
.tool svg {
  width: 12px;
  height: 12px;
  display: block;
}
.empty {
  margin: 4px 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
</style>
