<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { cancelShape, finishShape, setMode } from "../actions.js";
import { cancelCropDraw, closeCropPolygon, startCropDraw } from "../map.js";

const activeFeeds = computed(
  () => store.catalogue.filter((feed) => feed.active).length,
);
</script>

<template>
  <!-- Floating creation tools over the map, present only in editing mode. -->
  <div v-if="store.editMode && store.activeTab === 'view'" class="map-toolbar">
    <button
      class="mode"
      :class="{ active: store.mode === 'select' }"
      @click="setMode('select')"
    >
      Select
    </button>
    <button
      class="mode"
      :class="{ active: store.mode === 'add-stop' }"
      @click="setMode('add-stop')"
    >
      + Stop
    </button>
    <button
      class="mode"
      :class="{ active: store.mode === 'draw' }"
      @click="setMode('draw')"
    >
      + Shape
    </button>
    <template v-if="store.mode === 'draw'">
      <label v-if="store.snapAvailable" class="snap">
        <input type="checkbox" v-model="store.snapOn" /> snap
        <select v-model="store.snapNetwork">
          <option value="streets">streets</option>
          <option value="tram">tram rails</option>
          <option value="rail">rail</option>
        </select>
      </label>
      <button @click="finishShape">Finish</button>
      <button @click="cancelShape">Cancel</button>
    </template>

    <!-- Cropping: draw an area, then confirm in the panel below the map. -->
    <template v-if="!store.cropDrawing && !store.cropShape">
      <button
        class="mode"
        :disabled="!activeFeeds"
        :title="
          activeFeeds
            ? `crop the ${activeFeeds} feeds shown on the map`
            : 'no feeds shown on the map'
        "
        @click="startCropDraw('box')"
      >
        ⬚ Crop box
      </button>
      <button
        class="mode"
        :disabled="!activeFeeds"
        title="click to place corners, Enter to close"
        @click="startCropDraw('polygon')"
      >
        ⬠ Crop area
      </button>
    </template>
    <template v-else-if="store.cropDrawing">
      <span class="hint">
        {{
          store.cropDrawing === "box"
            ? "drag a box over the area"
            : "click corners; Enter closes, Escape cancels"
        }}
      </span>
      <button v-if="store.cropDrawing === 'polygon'" @click="closeCropPolygon">
        Close area
      </button>
      <button @click="cancelCropDraw">Cancel</button>
    </template>
  </div>
</template>
