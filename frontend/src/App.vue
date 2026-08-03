<script setup>
import { onMounted } from "vue";

import { store } from "./store.js";
import { createMap } from "./map.js";
import { checkNetworkAvailable, loadCatalogue } from "./actions.js";
import AgencyServiceForm from "./components/AgencyServiceForm.vue";
import CataloguePanel from "./components/CataloguePanel.vue";
import CurrentFeedBar from "./components/CurrentFeedBar.vue";
import NetworkPanel from "./components/NetworkPanel.vue";
import SearchPanel from "./components/SearchPanel.vue";
import FeedSummary from "./components/FeedSummary.vue";
import ModeBar from "./components/ModeBar.vue";
import RouteForm from "./components/RouteForm.vue";
import RouteLegend from "./components/RouteLegend.vue";
import SaveBar from "./components/SaveBar.vue";
import StopInspector from "./components/StopInspector.vue";
import TabBar from "./components/TabBar.vue";
import TimetablePanel from "./components/TimetablePanel.vue";
import TripForm from "./components/TripForm.vue";
import ValidationReport from "./components/ValidationReport.vue";

onMounted(() => {
  createMap();
  loadCatalogue();
  checkNetworkAvailable();
});
</script>

<template>
  <div id="sidebar">
    <h1>transitio</h1>
    <TabBar />
    <CurrentFeedBar
      v-show="
        store.activeTab === 'view' ||
        store.activeTab === 'edit' ||
        store.activeTab === 'report'
      "
    />

    <!-- View: explore the loaded data without editing it. -->
    <div v-show="store.activeTab === 'view'">
      <FeedSummary />
      <RouteLegend />
    </div>

    <div v-show="store.activeTab === 'edit'">
      <ModeBar />
      <StopInspector />
      <RouteForm />
      <TripForm />
      <AgencyServiceForm />
      <TimetablePanel />
      <SaveBar />
    </div>

    <NetworkPanel v-show="store.activeTab === 'network'" />

    <CataloguePanel v-show="store.activeTab === 'catalogue'" />

    <SearchPanel v-show="store.activeTab === 'search'" />

    <ValidationReport v-show="store.activeTab === 'report'" />

    <div id="status">{{ store.status }}</div>
  </div>
  <div id="map"></div>
</template>
