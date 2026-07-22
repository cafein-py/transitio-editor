<script setup>
import { onMounted } from "vue";

import { store } from "./store.js";
import { createMap } from "./map.js";
import { loadCatalogue } from "./actions.js";
import AgencyServiceForm from "./components/AgencyServiceForm.vue";
import CataloguePanel from "./components/CataloguePanel.vue";
import SearchPanel from "./components/SearchPanel.vue";
import FeedSummary from "./components/FeedSummary.vue";
import ModeBar from "./components/ModeBar.vue";
import RouteForm from "./components/RouteForm.vue";
import SaveBar from "./components/SaveBar.vue";
import StopInspector from "./components/StopInspector.vue";
import TabBar from "./components/TabBar.vue";
import TimetablePanel from "./components/TimetablePanel.vue";
import TripForm from "./components/TripForm.vue";
import ValidationReport from "./components/ValidationReport.vue";

onMounted(() => {
  createMap();
  loadCatalogue();
});
</script>

<template>
  <div id="sidebar">
    <h1>transitio</h1>
    <TabBar />

    <div v-show="store.activeTab === 'edit'">
      <FeedSummary />
      <ModeBar />
      <StopInspector />
      <RouteForm />
      <TripForm />
      <AgencyServiceForm />
      <TimetablePanel />
      <SaveBar />
    </div>

    <CataloguePanel v-show="store.activeTab === 'catalogue'" />

    <SearchPanel v-show="store.activeTab === 'search'" />

    <ValidationReport v-show="store.activeTab === 'report'" />

    <div id="status">{{ store.status }}</div>
  </div>
  <div id="map"></div>
</template>
