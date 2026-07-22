<script setup>
import { computed, ref, watch } from "vue";
import { store } from "../store.js";
import { networkTags } from "../network.js";
import {
  deleteNetworkNode,
  loadNetwork,
  resetNetwork,
  retagNetworkNode,
  setNetworkMode,
  startMoveNode,
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
const selectedNode = computed(
  () => store.network.selected && store.network.selected.osm_type === "node",
);

const tagKey = ref("");
const tagValue = ref("");
function applyTag() {
  retagNetworkNode(tagKey.value, tagValue.value);
  tagKey.value = "";
  tagValue.value = "";
}
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

      <div v-if="store.network.loaded" class="mode-row">
        <button
          class="mode"
          :class="{ active: store.network.mode === 'select' }"
          @click="setNetworkMode('select')"
        >
          Select
        </button>
        <button
          class="mode"
          :class="{ active: store.network.mode === 'add-node' }"
          @click="setNetworkMode('add-node')"
        >
          Add node
        </button>
      </div>

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

        <template v-if="selectedNode">
          <div class="mode-row">
            <button @click="startMoveNode">Move</button>
            <button class="remove" @click="deleteNetworkNode">Delete</button>
          </div>
          <form class="net-retag" @submit.prevent="applyTag">
            <input v-model="tagKey" placeholder="tag key" />
            <input v-model="tagValue" placeholder="value" />
            <button type="submit" :disabled="!tagKey.trim()">Set tag</button>
          </form>
        </template>
      </div>
      <p v-else-if="store.network.loaded" class="hint">
        click a node to inspect or edit it; Add node then click the map.
      </p>

      <button
        v-if="store.network.loaded"
        class="net-reset"
        @click="resetNetwork"
      >
        Discard network edits
      </button>
    </template>
  </div>
</template>
