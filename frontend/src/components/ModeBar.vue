<script setup>
import { store } from "../store.js";
import { cancelShape, finishShape, setMode } from "../actions.js";
</script>

<template>
  <div class="panel">
    <div class="mode-row">
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
        Add stop
      </button>
      <button
        class="mode"
        :class="{ active: store.mode === 'draw' }"
        @click="setMode('draw')"
      >
        Draw shape
      </button>
    </div>
    <label v-show="store.mode === 'draw' && store.snapAvailable">
      <input type="checkbox" v-model="store.snapOn" /> snap to
      <select v-model="store.snapNetwork">
        <option value="streets">streets</option>
        <option value="tram">tram rails</option>
        <option value="rail">rail</option>
      </select>
    </label>
    <div v-show="store.mode === 'draw'">
      <button @click="finishShape">Finish shape</button>
      <button @click="cancelShape">Cancel</button>
    </div>
  </div>
</template>
