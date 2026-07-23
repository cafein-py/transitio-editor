<script setup>
import { computed, ref, watch } from "vue";
import { store } from "../store.js";
import { networkTags } from "../network.js";
import {
  acquireOsm,
  cancelAcquire,
  cancelDrawWay,
  deleteNetworkNode,
  deleteNetworkWay,
  finishDrawWay,
  loadNetwork,
  resetNetwork,
  resolveOsmByPlace,
  resolveOsmByView,
  retagNetworkNode,
  saveNetwork,
  retagNetworkWay,
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

const selected = computed(() => store.network.selected);
const selectedTags = computed(() =>
  selected.value ? networkTags(selected.value) : [],
);
const isWay = computed(() => selected.value && selected.value.osm_type === "way");
const isNode = computed(() => selected.value && selected.value.osm_type === "node");

const tagKey = ref("");
const tagValue = ref("");
function applyTag() {
  if (isWay.value) retagNetworkWay(tagKey.value, tagValue.value);
  else retagNetworkNode(tagKey.value, tagValue.value);
  tagKey.value = "";
  tagValue.value = "";
}
function deleteSelected() {
  if (isWay.value) deleteNetworkWay();
  else deleteNetworkNode();
}

const drawTagKey = ref("highway");
const drawTagValue = ref("footway");
function finishDraw() {
  const key = drawTagKey.value.trim();
  if (!key) return; // a way needs at least one tag
  finishDrawWay({ [key]: drawTagValue.value });
}
const savePath = ref("edited.osm.pbf");
</script>

<template>
  <div class="panel network">
    <div class="net-acquire">
      <div class="net-acquire-title">Acquire OSM extract</div>
      <div class="net-retag">
        <input
          v-model="store.network.acquire.place"
          placeholder="place name (e.g. Helsinki)"
          :disabled="store.network.acquire.downloading"
          @keyup.enter="resolveOsmByPlace"
        />
        <button
          :disabled="
            !store.network.acquire.place.trim() ||
            store.network.acquire.resolving ||
            store.network.acquire.downloading
          "
          @click="resolveOsmByPlace"
        >
          Find
        </button>
      </div>
      <button
        class="mode"
        :disabled="
          store.network.acquire.resolving || store.network.acquire.downloading
        "
        @click="resolveOsmByView"
      >
        Use current map view
      </button>
      <p v-if="store.network.acquire.resolving" class="hint">resolving…</p>
      <p v-if="store.network.acquire.error" class="hint net-error">
        {{ store.network.acquire.error }}
      </p>
      <div v-if="store.network.acquire.resolved" class="net-resolved">
        <p class="hint">
          extract:
          <strong>{{ store.network.acquire.resolved.name }}</strong> — downloads
          and crops to the area.
        </p>
        <div class="mode-row">
          <button
            :disabled="store.network.acquire.downloading"
            @click="acquireOsm(false)"
          >
            {{ store.network.acquire.downloading ? "downloading…" : "Download" }}
          </button>
          <button @click="cancelAcquire">Cancel</button>
        </div>
      </div>
    </div>

    <p v-if="!store.network.available" class="hint">
      No OSM network loaded yet — acquire one above, or start the editor with
      <code>--osm-pbf</code>.
    </p>
    <fieldset
      v-else
      class="net-edit"
      :disabled="store.network.acquire.downloading"
    >
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
        <button
          class="mode"
          :class="{ active: store.network.mode === 'draw-way' }"
          @click="setNetworkMode('draw-way')"
        >
          Draw way
        </button>
      </div>

      <div v-if="store.network.mode === 'draw-way'" class="net-draw">
        <p class="hint">
          Click the map to add points; click a node or way to connect to it
          ({{ store.network.draw.length }} points).
        </p>
        <div class="net-retag">
          <input v-model="drawTagKey" placeholder="tag key" />
          <input v-model="drawTagValue" placeholder="value" />
        </div>
        <div class="mode-row">
          <button
            :disabled="store.network.draw.length < 2 || !drawTagKey.trim()"
            @click="finishDraw"
          >
            Finish
          </button>
          <button @click="cancelDrawWay">Cancel</button>
        </div>
      </div>

      <p v-if="store.network.loading" class="hint">loading network…</p>
      <p v-else-if="store.network.error" class="hint net-error">
        {{ store.network.error }}
      </p>
      <p v-else-if="store.network.loaded" class="hint">
        {{ store.network.wayCount }} ways, {{ store.network.nodeCount }} nodes —
        zoom in to see nodes.
      </p>

      <div v-if="selected" class="net-inspector">
        <div class="net-head">
          {{ selected.osm_type || "element" }} {{ selected.id }}
        </div>
        <table v-if="selectedTags.length" class="net-tags">
          <tr v-for="[key, value] in selectedTags" :key="key">
            <td>{{ key }}</td>
            <td>{{ value }}</td>
          </tr>
        </table>
        <p v-else class="hint">no tags</p>

        <template v-if="isNode || isWay">
          <div class="mode-row">
            <button v-if="isNode" @click="startMoveNode">Move</button>
            <button class="remove" @click="deleteSelected">Delete</button>
          </div>
          <form class="net-retag" @submit.prevent="applyTag">
            <input v-model="tagKey" placeholder="tag key" />
            <input v-model="tagValue" placeholder="value" />
            <button type="submit" :disabled="!tagKey.trim()">Set tag</button>
          </form>
        </template>
      </div>
      <p v-else-if="store.network.loaded && store.network.mode === 'select'" class="hint">
        click a node or way to inspect or edit it.
      </p>

      <form
        v-if="store.network.loaded"
        class="net-save"
        @submit.prevent="saveNetwork(savePath)"
      >
        <input v-model="savePath" placeholder="output .osm.pbf path" />
        <button type="submit" :disabled="!savePath.trim()">Save network</button>
      </form>
      <button
        v-if="store.network.loaded"
        class="net-reset"
        @click="resetNetwork"
      >
        Discard network edits
      </button>
    </fieldset>
  </div>
</template>
