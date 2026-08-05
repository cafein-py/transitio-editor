<script setup>
import { computed, onMounted, ref, watch } from "vue";

import {
  downloadFeed,
  downloadSelected,
  openBrowser,
  setAllSelected,
  toggleFeedSelected,
} from "../actions.js";
import { addFeed } from "../actions/catalogue.js";
import {
  clearUnifiedSearch,
  flyToPlace,
  listLocalFeeds,
  unifiedSearch,
} from "../actions/palette.js";
import { acquireOsm } from "../actions/streets.js";
import * as mapBridge from "../map.js";
import { feedLocation, isDownloaded, selectableFeeds } from "../search.js";
import { store } from "../store.js";
import FileBrowser from "./FileBrowser.vue";

// context: "landing" (no map yet) or "app" (the ⌘K palette).
const props = defineProps({
  context: { type: String, required: true },
});

const q = ref(store.search.q);
let debounce = null;

watch(q, (value) => {
  store.search.q = value;
  clearTimeout(debounce);
  if (!value.trim()) {
    clearUnifiedSearch();
    if (props.context === "app") searchInView();
    return;
  }
  debounce = setTimeout(() => unifiedSearch(value), 450);
});

// The palette opens onto "In view" results before anything is typed.
function searchInView() {
  const bbox = mapBridge.getViewportBbox();
  if (bbox) unifiedSearch("", bbox);
}

const local = ref(null); // { path, feeds } of the download folder

async function refreshLocal() {
  local.value = await listLocalFeeds(store.search.downloadDir.trim() || null);
}

onMounted(async () => {
  if (props.context === "app" && !q.value.trim()) searchInView();
  else if (q.value.trim()) unifiedSearch(q.value);
  await refreshLocal();
});
watch(
  () => store.search.downloadDir,
  () => refreshLocal(),
);

const loadingLocal = ref(null);

async function loadLocal(name) {
  if (!local.value) return;
  loadingLocal.value = name;
  await addFeed(`${local.value.path}/${name}`);
  loadingLocal.value = null;
}

const resolved = computed(() => store.network.acquire.resolved);
const selectable = computed(() =>
  selectableFeeds(store.search.results, store.catalogue),
);
const inView = computed(
  () => props.context === "app" && !q.value.trim() && store.search.searched,
);
</script>

<template>
  <div class="unified">
    <div class="search-row">
      <span class="glyph"></span>
      <input
        v-model="q"
        class="search-input"
        :placeholder="
          context === 'landing'
            ? 'Search a city or agency…'
            : 'Search places, agencies and feeds…'
        "
        autofocus
      />
      <span class="mono providers">Mobility Database + OSM</span>
    </div>

    <div class="folder-row">
      <span class="mono-label">Save to</span>
      <input
        v-model="store.search.downloadDir"
        placeholder="the transitio cache"
      />
      <button
        class="btn small"
        @click="
          openBrowser('downloadDir', 'dir', store.search.downloadDir.trim() || null)
        "
      >
        Browse…
      </button>
    </div>
    <FileBrowser target="downloadDir" />

    <div class="sections">
      <p v-if="store.search.searching" class="mono hint-line">searching…</p>

      <!-- In view (palette only, empty query) -->
      <div v-if="inView && store.search.results.length" class="section">
        <div class="section-head mono">In view</div>
      </div>

      <!-- Places -->
      <div v-if="store.search.place" class="section">
        <div class="section-head mono">
          Places <span class="src">nominatim</span>
        </div>
        <div class="row">
          <span class="row-glyph place"></span>
          <span class="row-main">
            <span class="row-title">{{ store.search.place.query }}</span>
            <span class="mono row-meta">geocoded place</span>
          </span>
          <button
            v-if="context === 'app'"
            class="btn small mono"
            @click="flyToPlace(store.search.place)"
          >
            fly to
          </button>
        </div>
      </div>

      <!-- Street network -->
      <div v-if="resolved || store.network.acquire.resolving" class="section">
        <div class="section-head mono">
          Street network — OpenStreetMap <span class="src">snapping</span>
        </div>
        <p v-if="store.network.acquire.resolving" class="mono hint-line">
          resolving extract…
        </p>
        <div v-if="resolved" class="row">
          <span class="row-glyph osm"></span>
          <span class="row-main">
            <span class="row-title">{{ resolved.name }} street network</span>
            <span class="mono row-meta">
              OpenStreetMap extract · download to enable snapping
            </span>
          </span>
          <button
            class="btn small"
            :disabled="store.network.acquire.downloading"
            @click="acquireOsm()"
          >
            {{ store.network.acquire.downloading ? "Downloading…" : "Download" }}
          </button>
        </div>
        <p v-if="store.network.acquire.error" class="mono error-line">
          {{ store.network.acquire.error }}
        </p>
      </div>

      <!-- Already on this machine -->
      <div v-if="local && local.feeds.length" class="section">
        <div class="section-head mono">Already on this machine</div>
        <div v-for="name in local.feeds.slice(0, 8)" :key="name" class="row">
          <span class="row-glyph zip"></span>
          <span class="row-main">
            <span class="mono row-title">{{ name }}</span>
            <span class="mono row-meta">{{ local.path }}</span>
          </span>
          <button
            class="btn small"
            :disabled="loadingLocal === name"
            @click="loadLocal(name)"
          >
            {{ loadingLocal === name ? "Loading…" : "Load" }}
          </button>
        </div>
      </div>

      <!-- Mobility Database -->
      <div v-if="store.search.results.length" class="section">
        <div class="section-head mono">
          Mobility Database — pick what to download
          <button
            v-if="selectable.length > 1"
            class="btn small addall"
            :disabled="store.search.bulk.running"
            @click="setAllSelected(selectable, true)"
          >
            Add all ({{ selectable.length }})
          </button>
        </div>
        <div v-for="feed in store.search.results" :key="feed.id" class="row">
          <input
            v-if="feed.downloadable && !isDownloaded(store.catalogue, feed.id)"
            type="checkbox"
            class="pick"
            :checked="store.search.selected.includes(feed.id)"
            :disabled="store.search.bulk.running"
            @change="toggleFeedSelected(feed.id)"
          />
          <span v-else class="pick-spacer"></span>
          <span class="row-main">
            <span class="row-title">
              {{ feed.provider || feed.id }}
              <span v-if="feed.official" class="official" title="Official feed">✓</span>
            </span>
            <span class="mono row-meta">
              {{ feedLocation(feed) }} · {{ feed.status || "—"
              }}{{ feed.official ? " · official" : "" }}
            </span>
          </span>
          <span
            v-if="isDownloaded(store.catalogue, feed.id)"
            class="mono in-catalogue"
          >
            loaded
          </span>
          <button
            v-else-if="feed.downloadable"
            class="btn small"
            :disabled="
              store.search.downloadingId === feed.id || store.search.bulk.running
            "
            @click="downloadFeed(feed)"
          >
            {{ store.search.downloadingId === feed.id ? "…" : "Download" }}
          </button>
        </div>
        <button
          v-if="store.search.selected.length"
          class="btn dark bulk"
          :disabled="store.search.bulk.running"
          @click="downloadSelected"
        >
          {{
            store.search.bulk.running
              ? `Downloading… (${store.search.bulk.done}/${store.search.bulk.total})`
              : `Download selected (${store.search.selected.length})`
          }}
        </button>
        <p v-if="store.search.csvFallback" class="mono hint-line">
          CSV fallback — no historical datasets or validation reports
        </p>
      </div>

      <p
        v-if="
          store.search.searched &&
          !store.search.searching &&
          !store.search.results.length &&
          !resolved
        "
        class="mono hint-line"
      >
        nothing found
      </p>
    </div>
  </div>
</template>

<style scoped>
.unified {
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.search-row {
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--surface);
  border: 1px solid var(--border-3);
  border-radius: var(--r-card);
  padding: 10px 13px;
}
.glyph {
  width: 13px;
  height: 13px;
  border: 1.6px solid var(--ink-5);
  border-radius: 50%;
  flex: none;
}
.search-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  font: 13.5px var(--sans);
  color: var(--ink);
}
.search-input:focus {
  outline: none;
}
.providers {
  font-size: 9.5px;
  color: var(--ink-6);
  flex: none;
}
.folder-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.folder-row input {
  flex: 1;
  min-width: 0;
  font: 11.5px var(--sans);
  border: 1px solid var(--border-2);
  border-radius: var(--r-input);
  padding: 6px 9px;
  background: var(--surface);
}
.sections {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 46vh;
  overflow-y: auto;
}
.section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-5);
  border-bottom: 1px solid var(--border-1);
  padding-bottom: 4px;
}
.section-head .src {
  margin-left: auto;
  color: var(--ink-6);
  text-transform: none;
}
.section-head .addall {
  margin-left: auto;
  text-transform: none;
  letter-spacing: 0;
}
.row {
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--surface);
  border: 1px solid var(--border-1);
  border-radius: var(--r-card);
  padding: 7px 9px;
}
.row-glyph {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  flex: none;
}
.row-glyph.place {
  background: var(--track);
  border: 1px solid var(--border-3);
  border-radius: 50%;
}
.row-glyph.osm {
  background: rgba(122, 79, 191, 0.24);
}
.row-glyph.zip {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
}
.pick {
  accent-color: var(--accent);
  flex: none;
}
.pick-spacer {
  width: 13px;
  flex: none;
}
.row-main {
  flex: 1;
  min-width: 0;
}
.row-title {
  display: block;
  font-size: 12.5px;
  font-weight: 550;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
.official {
  color: var(--ok);
}
.in-catalogue {
  font-size: 9.5px;
  color: var(--ok);
  flex: none;
}
.bulk {
  justify-content: center;
  margin-top: 3px;
}
.hint-line {
  margin: 0;
  font-size: 10px;
  color: var(--ink-6);
}
.error-line {
  margin: 0;
  font-size: 10px;
  color: var(--error);
}
</style>
