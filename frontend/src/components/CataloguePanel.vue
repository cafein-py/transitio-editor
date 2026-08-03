<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { feedModes, feedTableSummary } from "../catalogue.js";
import {
  addFeed,
  removeFeed,
  setCurrentFeed,
  toggleFeedActive,
  toggleNetworkVisible,
} from "../actions.js";

const osmName = computed(() => {
  const source = store.network.source;
  return source ? source.split("/").pop() : "OSM network";
});
</script>

<template>
  <div class="panel catalogue">
    <p class="hint">
      Activate the feeds to show together on the map; the current feed is the
      target of edits, validation and save.
    </p>
    <table v-if="store.catalogue.length" class="catalogue-table">
      <thead>
        <tr>
          <th title="shown on map">show</th>
          <th>feed</th>
          <th title="edit target">edit</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="feed in store.catalogue"
          :key="feed.feed_id"
          :class="{ current: feed.current }"
        >
          <td>
            <input
              type="checkbox"
              :checked="feed.active"
              @change="toggleFeedActive(feed)"
            />
          </td>
          <td>
            <span class="swatch" :style="{ background: feed.color }"></span>
            <span class="kind-badge gtfs">GTFS</span>
            <span class="feed-name">{{ feed.name }}</span>
            <span class="feed-tables">{{ feedTableSummary(feed.tables) }}</span>
            <span v-if="feedModes(feed.modes).length" class="feed-modes">
              <span
                v-for="mode in feedModes(feed.modes)"
                :key="mode.code"
                class="mode-chip"
              >
                <span class="swatch" :style="{ background: mode.color }"></span
                >{{ mode.label }}
              </span>
            </span>
          </td>
          <td>
            <input
              type="radio"
              name="current-feed"
              :checked="feed.current"
              @change="setCurrentFeed(feed)"
            />
          </td>
          <td>
            <button
              class="remove"
              title="remove from catalogue"
              @click="removeFeed(feed)"
            >
              ×
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="hint">no feeds loaded.</p>

    <!-- The one OSM extract loads via the Network tab or --osm-pbf; it lists
         here so all loaded data is visible in one place. -->
    <div v-if="store.network.available" class="osm-row">
      <input
        type="checkbox"
        title="shown on map"
        :checked="store.network.visible"
        @change="toggleNetworkVisible"
      />
      <span class="kind-badge osm">OSM</span>
      <span class="feed-name" :title="store.network.source">{{ osmName }}</span>
      <span v-if="store.network.loaded" class="feed-tables">
        {{ store.network.wayCount }} ways, {{ store.network.nodeCount }} nodes
      </span>
    </div>

    <form class="add-feed" @submit.prevent="addFeed">
      <input
        v-model="store.newFeedPath"
        placeholder="path to a GTFS feed (zip or directory)"
      />
      <button class="primary" type="submit" :disabled="!store.newFeedPath.trim()">
        Load feed
      </button>
    </form>
  </div>
</template>
