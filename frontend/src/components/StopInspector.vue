<script setup>
import { store } from "../store.js";
import { startMovingStop, updateInspectedStop } from "../actions.js";
</script>

<template>
  <div id="inspector" class="panel" v-if="store.inspector">
    <b>stop {{ store.inspector.stopId }}</b>
    <template v-if="store.editMode">
      <label>name <input v-model="store.inspector.name" /></label>
      <button @click="updateInspectedStop">Update</button>
      <button @click="startMovingStop">Move (click map)</button>
    </template>
    <div v-else class="hint">{{ store.inspector.name }}</div>
  </div>
</template>
