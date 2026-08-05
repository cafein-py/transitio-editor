<script setup>
import { computed, onMounted, watch } from "vue";

import { store } from "./store.js";
import { currentFeed, initialPanel } from "./catalogue.js";
import { createMap } from "./map.js";
import { editTarget } from "./network.js";
import { refreshAfterHistory, toggleEditMode } from "./actions.js";
import { loadCatalogue, setCurrentFeed } from "./actions/catalogue.js";
import { checkNetworkAvailable } from "./actions/streets.js";
import { configureSession, sessionRedo, sessionUndo } from "./session.js";
import { undoShortcut } from "./undo.js";
import AppHeader from "./components/AppHeader.vue";
import DataPanel from "./components/DataPanel.vue";
import NavRail from "./components/NavRail.vue";
import RoutesPanel from "./components/RoutesPanel.vue";
import SessionDrawer from "./components/SessionDrawer.vue";
import StopsPanel from "./components/StopsPanel.vue";
import StreetsPanel from "./components/StreetsPanel.vue";
import WayCard from "./components/WayCard.vue";
import Toasts from "./components/Toasts.vue";
import AttributeTable from "./components/AttributeTable.vue";
import BasemapControl from "./components/BasemapControl.vue";
import MapToolbar from "./components/MapToolbar.vue";
/* Pre-redesign panels, hosted until each port step replaces them. */
import AgencyServiceForm from "./components/AgencyServiceForm.vue";
import CropPanel from "./components/CropPanel.vue";
import CurrentFeedBar from "./components/CurrentFeedBar.vue";
import RouteLegend from "./components/RouteLegend.vue";
import SearchPanel from "./components/SearchPanel.vue";
import StopInspector from "./components/StopInspector.vue";
import TimetablePanel from "./components/TimetablePanel.vue";
import TripForm from "./components/TripForm.vue";
import ValidationReport from "./components/ValidationReport.vue";

const PANEL_TITLES = {
  data: "Data",
  stops: "Stops",
  routes: "Routes",
  cal: "Services",
  trips: "Trips",
  agencies: "Agencies",
  streets: "Street network",
  validate: "Validate",
  search: "Search",
};

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));
const feedPanel = computed(() => editTarget(store.activePanel) === "feed");

// A workspace records the panel the user was working in; the Data panel
// is the neutral home and is not recorded.
watch(
  () => store.activePanel,
  (panel) => {
    if (panel !== "data") store.workingPanel = panel;
  },
);

// Closing the attribute drawer from its own × leaves the table layout;
// the layout switcher is the one source of truth.
watch(
  () => store.tableView.open,
  (open) => {
    if (!open && store.layout === "table") store.layout = "sidebar";
  },
);

// Ctrl/Cmd+Z and Ctrl/Cmd+Shift+Z (or +Y) act on the session log,
// globally; keystrokes inside form fields stay with the field.
window.addEventListener("keydown", (event) => {
  const kind = undoShortcut({
    key: event.key,
    ctrlKey: event.ctrlKey,
    metaKey: event.metaKey,
    shiftKey: event.shiftKey,
    targetTag: event.target && event.target.tagName,
  });
  if (!kind) return;
  event.preventDefault();
  if (kind === "undo") sessionUndo();
  else sessionRedo();
});

onMounted(async () => {
  // The session core stays import-cycle-free by having its refresh and
  // feed-switching injected here.
  configureSession({
    refresh: refreshAfterHistory,
    makeCurrent: async (feedId) => {
      const feed = store.catalogue.find((entry) => entry.feed_id === feedId);
      if (feed && !feed.current) await setCurrentFeed(feed);
    },
  });
  createMap();
  await loadCatalogue();
  // Only on startup: later removing every feed must not move the user.
  store.activePanel = initialPanel(store.catalogue);
  // the decided startup panel counts as "worked in" (the watcher only
  // sees changes made after this)
  if (store.activePanel !== "data") store.workingPanel = store.activePanel;
  checkNetworkAvailable();
});
</script>

<template>
  <AppHeader />
  <div class="shell-body">
    <NavRail />
    <aside
      class="shell-aside"
      :class="{ narrow: store.layout === 'inspector' }"
    >
      <!-- Ported panels render their own header. -->
      <div
        v-if="!['data', 'stops', 'routes', 'streets'].includes(store.activePanel)"
        class="panel-title"
      >
        {{ PANEL_TITLES[store.activePanel] }}
      </div>

      <div v-show="store.activePanel === 'data'">
        <DataPanel />
        <div class="legacy">
          <RouteLegend />
          <CropPanel />
        </div>
      </div>

      <StopsPanel v-show="store.activePanel === 'stops'" />

      <RoutesPanel v-show="store.activePanel === 'routes'" />

      <div v-show="store.activePanel === 'cal'" class="legacy">
        <CurrentFeedBar />
        <AgencyServiceForm v-if="store.editMode" />
        <p v-else class="hint">Turn on editing to manage agencies and services.</p>
      </div>

      <div v-show="store.activePanel === 'trips'" class="legacy">
        <CurrentFeedBar />
        <TripForm v-if="store.editMode" />
        <TimetablePanel v-if="store.editMode" />
        <p v-if="!store.editMode" class="hint">
          Turn on editing to work on trips and timetables.
        </p>
      </div>

      <div v-show="store.activePanel === 'agencies'" class="legacy">
        <CurrentFeedBar />
        <p class="hint">
          The agencies panel arrives in a later step — agencies are managed
          under Services for now.
        </p>
      </div>

      <StreetsPanel v-show="store.activePanel === 'streets'" />

      <div v-show="store.activePanel === 'validate'" class="legacy">
        <CurrentFeedBar />
        <ValidationReport />
      </div>

      <div v-show="store.activePanel === 'search'" class="legacy">
        <SearchPanel />
      </div>

      <div v-if="store.status" class="legacy">
        <div id="status">{{ store.status }}</div>
      </div>
    </aside>

    <div class="shell-main">
      <div class="map-wrap">
        <div id="map"></div>
        <div class="map-overlay top-left">
          <button
            v-if="!store.editMode"
            class="mode-badge"
            :disabled="!store.catalogue.length"
            title="Turn editing on"
            @click="toggleEditMode"
          >
            <span class="badge-dot off"></span>
            Editing mode off — read-only
            <span class="badge-action">Enable</span>
          </button>
          <div v-else class="mode-badge on">
            <span
              class="badge-dot"
              :style="{ background: feed ? feed.color : '#ccc' }"
            ></span>
            Edits go to the current feed<template v-if="feed">
              · {{ feed.name }}</template
            >
          </div>
          <MapToolbar />
        </div>
        <div class="map-overlay top-right">
          <StopInspector v-if="feedPanel" />
          <WayCard v-if="store.activePanel === 'streets'" />
        </div>
        <div class="map-overlay bottom-left">
          <BasemapControl />
        </div>
      </div>
      <AttributeTable />
    </div>
  </div>
  <SessionDrawer />
  <Toasts />
</template>

<style scoped>
.panel-title {
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-overlay);
  padding: 4px 11px;
  font: 11.5px var(--sans);
  color: var(--ink-3);
  cursor: default;
}
button.mode-badge {
  cursor: pointer;
}
.mode-badge.on {
  color: var(--ink);
}
.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
  flex: none;
}
.badge-dot.off {
  background: var(--ink-disabled);
}
.badge-action {
  color: var(--accent);
  font-weight: 600;
}
</style>
