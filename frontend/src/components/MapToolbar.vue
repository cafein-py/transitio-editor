<script setup>
import { store } from "../store.js";
import { cancelShape, finishShape, setMode } from "../actions.js";
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
  </div>
</template>
