<script setup>
import { store } from "../store.js";

// Ordered to follow the workflow: find data (Search), manage what's loaded
// (Data), explore it read-only (View), edit the current feed (Edit), edit
// the OSM network (OSM), validate the result (Report).
const TABS = [
  { key: "search", label: "Search" },
  { key: "catalogue", label: "Data" },
  { key: "view", label: "View/Edit" },
  { key: "network", label: "OSM" },
  { key: "report", label: "Report" },
];
</script>

<template>
  <div class="tab-bar">
    <button
      v-for="tab in TABS"
      :key="tab.key"
      :class="{ active: store.activeTab === tab.key }"
      @click="store.activeTab = tab.key"
    >
      {{ tab.label }}
      <span
        v-if="tab.key === 'catalogue' && store.catalogue.length > 1"
        class="badge"
      >
        {{ store.catalogue.length }}
      </span>
      <span
        v-if="tab.key === 'report' && store.reportStale"
        class="dot"
        title="edited since last validation"
      ></span>
    </button>
  </div>
</template>
