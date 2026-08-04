<script setup>
import { onMounted } from "vue";

import { store } from "./store.js";
import { initialTab } from "./catalogue.js";
import { createMap } from "./map.js";
import {
  checkNetworkAvailable,
  loadCatalogue,
  toggleEditMode,
  toggleTableView,
} from "./actions.js";
import AgencyServiceForm from "./components/AgencyServiceForm.vue";
import AttributeTable from "./components/AttributeTable.vue";
import CataloguePanel from "./components/CataloguePanel.vue";
import CropPanel from "./components/CropPanel.vue";
import CurrentFeedBar from "./components/CurrentFeedBar.vue";
import NetworkPanel from "./components/NetworkPanel.vue";
import SearchPanel from "./components/SearchPanel.vue";
import FeedSummary from "./components/FeedSummary.vue";
import BasemapControl from "./components/BasemapControl.vue";
import MapToolbar from "./components/MapToolbar.vue";
import RouteForm from "./components/RouteForm.vue";
import RouteLegend from "./components/RouteLegend.vue";
import SaveBar from "./components/SaveBar.vue";
import StopInspector from "./components/StopInspector.vue";
import TabBar from "./components/TabBar.vue";
import TimetablePanel from "./components/TimetablePanel.vue";
import TripForm from "./components/TripForm.vue";
import ValidationReport from "./components/ValidationReport.vue";

onMounted(async () => {
  createMap();
  await loadCatalogue();
  // Only on startup: later removing every feed must not move the user.
  store.activeTab = initialTab(store.catalogue);
  checkNetworkAvailable();
});
</script>

<template>
  <div id="sidebar">
    <h1>transitio</h1>
    <TabBar />
    <CurrentFeedBar
      v-show="store.activeTab === 'view' || store.activeTab === 'report'"
    />

    <!-- View/Edit: explore the loaded data; flip the switch to edit it. -->
    <div v-show="store.activeTab === 'view'">
      <label class="check edit-switch">
        <input
          type="checkbox"
          :checked="store.editMode"
          @change="toggleEditMode"
        />
        editing mode
      </label>
      <FeedSummary />
      <CropPanel />
      <RouteLegend />
      <StopInspector />
      <template v-if="store.editMode">
        <RouteForm />
        <TripForm />
        <AgencyServiceForm />
        <TimetablePanel />
        <SaveBar />
      </template>
    </div>

    <NetworkPanel v-show="store.activeTab === 'network'" />

    <CataloguePanel v-show="store.activeTab === 'catalogue'" />

    <SearchPanel v-show="store.activeTab === 'search'" />

    <ValidationReport v-show="store.activeTab === 'report'" />

    <div id="status">{{ store.status }}</div>
  </div>
  <div id="main">
    <div id="map-wrap">
      <div id="map"></div>
      <MapToolbar />
      <BasemapControl />
      <button
        v-if="store.activeTab === 'view'"
        class="table-toggle"
        @click="toggleTableView"
      >
        {{ store.tableView.open ? "Hide table" : "Table" }}
      </button>
    </div>
    <AttributeTable />
  </div>
</template>
