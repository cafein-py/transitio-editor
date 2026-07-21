<script setup>
import { onMounted } from "vue";

import { store } from "./store.js";
import { createMap } from "./map.js";
import AgencyServiceForm from "./components/AgencyServiceForm.vue";
import FeedSummary from "./components/FeedSummary.vue";
import ModeBar from "./components/ModeBar.vue";
import NoticesPanel from "./components/NoticesPanel.vue";
import RouteForm from "./components/RouteForm.vue";
import SaveBar from "./components/SaveBar.vue";
import StopInspector from "./components/StopInspector.vue";
import TimetablePanel from "./components/TimetablePanel.vue";
import TripForm from "./components/TripForm.vue";

onMounted(createMap);
</script>

<template>
  <div id="sidebar">
    <h1>transitio</h1>
    <FeedSummary />
    <ModeBar />
    <StopInspector />
    <RouteForm />
    <TripForm />
    <AgencyServiceForm />
    <TimetablePanel />
    <NoticesPanel />
    <SaveBar />
    <div id="status">{{ store.status }}</div>
  </div>
  <div id="map"></div>
</template>
