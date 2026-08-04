<script setup>
import { computed, ref, watch } from "vue";

import { store } from "../store.js";
import { loadTable, toggleTableView } from "../actions.js";

const files = computed(() => Object.keys(store.tables));
const view = computed(() => store.tableView);
const page = computed(() => Math.floor(view.value.offset / view.value.limit) + 1);
const pages = computed(() =>
  Math.max(1, Math.ceil(view.value.total / view.value.limit)),
);

function pick(file) {
  loadTable({ file, offset: 0 });
}

// Debounced server-side search while typing.
const q = ref(store.tableView.q);
let timer = null;
watch(q, (value) => {
  clearTimeout(timer);
  if (value === store.tableView.q) return; // programmatic sync, not typing
  timer = setTimeout(() => {
    if (store.tableView.open) loadTable({ q: value, offset: 0 });
  }, 300);
});
// A store-side reset (e.g. a feed switch) must clear the input and any
// pending debounce, or the old feed's query would reapply to the new one.
watch(
  () => store.tableView.q,
  (value) => {
    if (value !== q.value) {
      clearTimeout(timer);
      q.value = value;
    }
  },
);

function previous() {
  if (view.value.offset > 0) {
    loadTable({ offset: Math.max(0, view.value.offset - view.value.limit) });
  }
}
function next() {
  if (view.value.offset + view.value.limit < view.value.total) {
    loadTable({ offset: view.value.offset + view.value.limit });
  }
}
</script>

<template>
  <div v-if="view.open" class="table-panel">
    <div class="table-bar">
      <select :value="view.file" @change="pick($event.target.value)">
        <option v-for="file in files" :key="file" :value="file">
          {{ file }} ({{ store.tables[file] }})
        </option>
      </select>
      <input v-model="q" placeholder="search all columns…" />
      <span class="table-count">
        {{ view.total }} rows
        <template v-if="pages > 1"> — page {{ page }}/{{ pages }}</template>
      </span>
      <button :disabled="view.offset === 0" @click="previous">‹</button>
      <button
        :disabled="view.offset + view.limit >= view.total"
        @click="next"
      >
        ›
      </button>
      <button class="table-close" title="close" @click="toggleTableView">
        ×
      </button>
    </div>
    <div class="table-scroll">
      <table v-if="view.rows.length" class="attr-table">
        <thead>
          <tr>
            <th v-for="column in view.columns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in view.rows" :key="index">
            <td v-for="column in view.columns" :key="column">
              {{ row[column] }}
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!view.loading" class="hint">no matching rows.</p>
    </div>
  </div>
</template>
