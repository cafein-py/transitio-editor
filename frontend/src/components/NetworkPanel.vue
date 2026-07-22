<script setup>
import { computed, watch } from "vue";
import { store } from "../store.js";
import { networkTags } from "../network.js";
import {
  loadNetwork,
  toggleFeedVisible,
  toggleNetworkVisible,
} from "../actions.js";

// The network loads eagerly at startup; retry on tab open in case that
// failed (loadNetwork no-ops once loaded).
watch(
  () => store.activeTab,
  (tab) => {
    if (tab === "network") loadNetwork();
  },
);

const selectedTags = computed(() =>
  store.network.selected ? networkTags(store.network.selected) : [],
);
</script>

<template>
  <div class="panel network">
    <p v-if="!store.network.available" class="hint">
      No OSM network loaded. Start the editor with <code>--osm-pbf</code> to view
      and edit the OSM network.
    </p>
    <template v-else>
      <label class="check">
        <input
          type="checkbox"
          :checked="store.network.visible"
          @change="toggleNetworkVisible"
        />
        show network on map
      </label>
      <label class="check">
        <input
          type="checkbox"
          :checked="store.feedVisible"
          @change="toggleFeedVisible"
        />
        show GTFS feed on map
      </label>
      <p v-if="store.network.loading" class="hint">loading network…</p>
      <p v-else-if="store.network.error" class="hint net-error">
        {{ store.network.error }}
      </p>
      <p v-else-if="store.network.loaded" class="hint">
        {{ store.network.wayCount }} ways, {{ store.network.nodeCount }} nodes —
        zoom in to see nodes.
      </p>

      <div v-if="store.network.selected" class="net-inspector">
        <div class="net-head">
          {{ store.network.selected.osm_type || "element" }}
          {{ store.network.selected.id }}
        </div>
        <table v-if="selectedTags.length" class="net-tags">
          <tr v-for="[key, value] in selectedTags" :key="key">
            <td>{{ key }}</td>
            <td>{{ value }}</td>
          </tr>
        </table>
        <p v-else class="hint">no tags</p>
      </div>
      <p v-else-if="store.network.loaded" class="hint">
        click a way or node to inspect its tags.
      </p>
    </template>
  </div>
</template>
