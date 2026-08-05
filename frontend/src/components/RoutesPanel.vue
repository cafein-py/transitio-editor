<script setup>
import { computed, onMounted, ref, watch } from "vue";

import { loadRoutes, selectRoute } from "../actions/routes.js";
import { toggleEditTarget } from "../actions/catalogue.js";
import { currentFeed } from "../catalogue.js";
import { MODES, UNKNOWN_MODE } from "../modes.js";
import { fetchQuality } from "../quality.js";
import { store } from "../store.js";
import { useEntityList } from "../composables/useEntityList.js";
import FlagChips from "./FlagChips.vue";
import Icon from "./Icon.vue";
import ListPager from "./ListPager.vue";
import NewRouteForm from "./NewRouteForm.vue";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));
const formOpen = ref(false);

// The routes endpoint serves the current feed only; reload when the feed
// changes or after any edit refresh.
onMounted(loadRoutes);
watch(
  () => [store.currentFeedId, store.dataVersion],
  () => loadRoutes(),
);

const modeOf = (code) =>
  [...MODES, UNKNOWN_MODE].find((mode) => mode.code === code) || UNKNOWN_MODE;

const items = computed(() =>
  store.routes.map((route) => ({
    routeId: route.route_id,
    shortName: route.route_short_name || "",
    longName: route.route_long_name || "",
    routeType: route.route_type ?? -1,
  })),
);

const list = useEntityList({
  items,
  fields: (route) => [route.routeId, route.shortName, route.longName],
  noun: "routes",
});

// "No shape" / "No trips" need per-route joins the backend does not
// serve yet; the chips disable themselves until it does.
const quality = ref(null);
onMounted(async () => {
  quality.value = await fetchQuality("routes");
});

const chips = computed(() => [
  { key: "all", label: "All", count: list.flagCount("all") },
  { key: "noshape", label: "No shape", count: null, disabled: !quality.value },
  { key: "notrips", label: "No trips", count: null, disabled: !quality.value },
]);

async function openForm() {
  if (!feed.value) return;
  // The form writes to the current feed; step editing on first if needed.
  if (!store.editMode) await toggleEditTarget(feed.value);
  formOpen.value = true;
}
</script>

<template>
  <div class="routes-panel">
    <div class="head">
      <h1>Routes</h1>
      <span class="mono meta">{{ list.total.value }} matches</span>
    </div>

    <button class="new-route" :disabled="!feed" @click="openForm">
      + New route in {{ feed ? feed.name : "…" }}
    </button>

    <NewRouteForm
      v-if="formOpen && feed"
      :feed-name="feed.name"
      @close="formOpen = false"
    />

    <input
      v-model="list.q.value"
      class="search"
      placeholder="Search route_id, short or long name…"
    />

    <div class="seg scope">
      <button disabled title="Needs backend support (routes are served for the current feed only)">
        All visible
      </button>
      <button class="active">{{ feed ? feed.name : "Current feed" }}</button>
    </div>

    <FlagChips v-model="list.flag.value" :chips="chips" />

    <ListPager
      :label="list.label.value"
      :can-prev="list.canPrev.value"
      :can-next="list.canNext.value"
      @prev="list.prev"
      @next="list.next"
    />

    <div :ref="(el) => (list.listEl.value = el)" class="rows">
      <button
        v-for="route in list.rows.value"
        :key="route.routeId"
        class="row"
        :class="{ selected: store.selectedRouteId === route.routeId }"
        :data-selected="store.selectedRouteId === route.routeId || null"
        @click="selectRoute(route.routeId)"
      >
        <span
          class="badge mono"
          :style="{ background: modeOf(route.routeType).color }"
        >
          {{ (route.shortName || route.routeId).slice(0, 4) }}
        </span>
        <span class="row-main">
          <span class="row-name">
            {{ route.longName || route.shortName || route.routeId }}
          </span>
          <span class="mono row-meta">
            {{ route.routeId }} ·
            {{ modeOf(route.routeType).label.toUpperCase() }}
          </span>
        </span>
        <span
          class="tool pencil"
          :class="{ on: store.editMode }"
          :title="store.editMode ? 'Stop editing this feed' : 'Edit this feed'"
          @click.stop="feed && toggleEditTarget(feed)"
        >
          <Icon name="pencil" />
        </span>
      </button>
      <p v-if="!list.rows.value.length" class="mono empty">no matching routes</p>
    </div>
  </div>
</template>

<style scoped>
.routes-panel {
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
.new-route {
  border: 1px dashed var(--accent-border);
  background: transparent;
  border-radius: 9px;
  padding: 7px;
  font: 11.5px var(--sans);
  color: var(--accent);
  cursor: pointer;
}
.new-route:hover {
  background: var(--accent-tint);
}
.new-route:disabled {
  color: var(--ink-disabled);
  border-color: var(--border-4);
  cursor: default;
}
.search {
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 7px 10px;
  background: var(--surface);
}
.search:focus {
  outline: none;
  border-color: var(--accent-border);
}
.seg {
  display: flex;
  background: var(--track);
  border-radius: var(--r-input);
  padding: 2px;
  gap: 1px;
}
.seg button {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 4px 6px;
  font: 500 11px var(--sans);
  color: var(--ink-4);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-thumb);
}
.seg button:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
.rows {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.row {
  display: flex;
  align-items: center;
  gap: 9px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 8px 9px;
  cursor: pointer;
}
.row:hover {
  border-color: var(--border-4);
}
.row.selected {
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.badge {
  width: 28px;
  height: 18px;
  border-radius: 4px;
  color: #fff;
  font-size: 9px;
  font-weight: 600;
  display: grid;
  place-items: center;
  flex: none;
  overflow: hidden;
}
.row-main {
  flex: 1;
  min-width: 0;
}
.row-name {
  display: block;
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1.3;
}
.row-meta {
  display: block;
  font-size: 9.5px;
  color: var(--ink-6);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tool {
  border: 1px solid var(--border-2);
  border-radius: var(--r-btn-sm);
  background: var(--surface);
  color: var(--ink-5);
  padding: 4px;
  flex: none;
}
.tool svg {
  width: 12px;
  height: 12px;
  display: block;
}
.tool:hover {
  color: var(--ink);
}
.tool.on {
  color: var(--accent);
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.empty {
  margin: 4px 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
</style>
