<script setup>
import { computed, watch } from "vue";
import { store } from "../store.js";
import {
  feedLocation,
  isDownloaded,
  safeHttpUrl,
  selectableFeeds,
  sortFeeds,
} from "../search.js";
import {
  clearAoi,
  downloadFeed,
  chooseBrowsedDir,
  closeDirBrowser,
  downloadSelected,
  openDirBrowser,
  runSearch,
  setAllSelected,
  startAoiDraw,
  toggleFeedSelected,
} from "../actions.js";

const selectable = computed(() =>
  selectableFeeds(store.search.results, store.catalogue),
);
const allSelected = computed(
  () =>
    selectable.value.length > 0 &&
    selectable.value.every((feed) => store.search.selected.includes(feed.id)),
);

function drawArea() {
  store.search.aoiMode = "drawn"; // drawing implies searching that area
  startAoiDraw();
}

// With no area selected there is nothing to crop to, so keep the (disabled)
// crop toggle off rather than stranding a download that can't proceed.
watch(
  () => store.search.aoiMode,
  (mode) => {
    if (mode === "none") store.search.cropToAoi = false;
  },
);

const sortedResults = computed(() =>
  store.search.sortKey
    ? sortFeeds(store.search.results, store.search.sortKey, store.search.sortDir)
    : store.search.results,
);

function sortBy(key) {
  const s = store.search;
  if (s.sortKey === key) {
    s.sortDir = s.sortDir === "asc" ? "desc" : "asc";
  } else {
    s.sortKey = key;
    s.sortDir = "asc";
  }
}

function sortArrow(key) {
  if (store.search.sortKey !== key) return "";
  return store.search.sortDir === "asc" ? " ▲" : " ▼";
}
</script>

<template>
  <div class="panel search">
    <p class="hint">
      Search the Mobility Database for GTFS feeds. Without a
      <code>MOBILITY_API_REFRESH_TOKEN</code> the CSV catalogue export is used.
    </p>
    <form @submit.prevent="runSearch">
      <input v-model="store.search.country" placeholder="country code (e.g. FI)" />
      <input v-model="store.search.subdivision" placeholder="subdivision / region" />
      <input v-model="store.search.municipality" placeholder="municipality" />
      <label class="check">
        <input type="checkbox" v-model="store.search.officialOnly" />
        official feeds only
      </label>
      <div class="search-area">
        <label>
          area
          <select v-model="store.search.aoiMode">
            <option value="none">none</option>
            <option value="map">current map view</option>
            <option value="drawn">drawn area</option>
          </select>
        </label>
        <button type="button" @click="drawArea">
          {{ store.aoiDrawing ? "drag on the map…" : "Draw area" }}
        </button>
        <button type="button" v-if="store.aoi" @click="clearAoi">Clear</button>
      </div>
      <label class="check">
        <input
          type="checkbox"
          v-model="store.search.cropToAoi"
          :disabled="store.search.aoiMode === 'none'"
        />
        crop downloaded feed to area
      </label>
      <div class="dir-row">
        <input
          v-model="store.search.downloadDir"
          placeholder="download folder (optional, default: cache)"
        />
        <button
          type="button"
          @click="openDirBrowser(store.search.downloadDir.trim() || null)"
        >
          Browse…
        </button>
      </div>
      <div v-if="store.search.browse.open" class="dir-browser">
        <div class="dir-path">{{ store.search.browse.path }}</div>
        <p v-if="store.search.browse.error" class="hint net-error">
          {{ store.search.browse.error }}
        </p>
        <ul class="dir-list">
          <li v-if="store.search.browse.parent">
            <button
              type="button"
              @click="openDirBrowser(store.search.browse.parent)"
            >
              ..
            </button>
          </li>
          <li v-for="name in store.search.browse.dirs" :key="name">
            <button
              type="button"
              @click="openDirBrowser(`${store.search.browse.path}/${name}`)"
            >
              {{ name }}/
            </button>
          </li>
        </ul>
        <div class="mode-row">
          <button type="button" @click="chooseBrowsedDir">
            Use this folder
          </button>
          <button type="button" @click="closeDirBrowser">Cancel</button>
        </div>
      </div>
      <button class="primary" type="submit" :disabled="store.search.searching">
        {{ store.search.searching ? "Searching…" : "Search" }}
      </button>
    </form>

    <p v-if="store.search.csvFallback && store.search.results.length" class="hint">
      CSV fallback — no historical datasets or hosted validation reports.
    </p>

    <table v-if="store.search.results.length" class="search-table">
      <thead>
        <tr>
          <th>
            <input
              type="checkbox"
              title="select all downloadable"
              :checked="allSelected"
              :disabled="!selectable.length || store.search.bulk.running"
              @change="setAllSelected(selectable, !allSelected)"
            />
          </th>
          <th class="sortable" @click="sortBy('provider')">feed{{ sortArrow("provider") }}</th>
          <th class="sortable" @click="sortBy('location')">location{{ sortArrow("location") }}</th>
          <th class="sortable" @click="sortBy('status')">status{{ sortArrow("status") }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="feed in sortedResults" :key="feed.id">
          <td>
            <input
              v-if="feed.downloadable && !isDownloaded(store.catalogue, feed.id)"
              type="checkbox"
              :checked="store.search.selected.includes(feed.id)"
              :disabled="store.search.bulk.running"
              @change="toggleFeedSelected(feed.id)"
            />
          </td>
          <td>
            <span class="feed-name">{{ feed.provider || feed.id }}</span>
            <span v-if="feed.official" class="official" title="official feed">✓</span>
            <a
              v-if="safeHttpUrl(feed.license_url)"
              :href="safeHttpUrl(feed.license_url)"
              target="_blank"
              rel="noopener"
            >
              license
            </a>
          </td>
          <td>{{ feedLocation(feed) }}</td>
          <td>{{ feed.status || "—" }}</td>
          <td>
            <span
              v-if="isDownloaded(store.catalogue, feed.id)"
              class="in-catalogue"
              title="already in the catalogue"
            >
              ✔
            </span>
            <button
              v-else-if="feed.downloadable"
              class="download"
              :disabled="store.search.downloadingId === feed.id"
              @click="downloadFeed(feed)"
            >
              {{ store.search.downloadingId === feed.id ? "…" : "Download" }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <button
      v-if="store.search.results.length"
      class="primary bulk-download"
      :disabled="!store.search.selected.length || store.search.bulk.running"
      @click="downloadSelected"
    >
      {{
        store.search.bulk.running
          ? `Downloading… (${store.search.bulk.done}/${store.search.bulk.total})`
          : `Download selected (${store.search.selected.length})`
      }}
    </button>
    <p v-else-if="store.search.searched && !store.search.searching" class="hint">
      no feeds found.
    </p>
  </div>
</template>
