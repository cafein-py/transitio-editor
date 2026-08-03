<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import {
  closeInspector,
  startMovingStop,
  updateInspectedStop,
} from "../actions.js";

// Edits target the current feed; a stop selected from another active feed
// (possible while viewing) stays read-only until its feed is made current.
const editable = computed(
  () =>
    store.editMode &&
    (!store.inspector.feedId || store.inspector.feedId === store.currentFeedId),
);
</script>

<template>
  <div id="inspector" class="panel" v-if="store.inspector">
    <div class="inspector-head">
      <b>stop {{ store.inspector.stopId }}</b>
      <button class="inspector-close" title="deselect" @click="closeInspector">
        ×
      </button>
    </div>
    <template v-if="editable">
      <label>name <input v-model="store.inspector.name" /></label>
      <button @click="updateInspectedStop">Update</button>
      <button @click="startMovingStop">Move (click map)</button>
    </template>
    <template v-else>
      <div class="hint">{{ store.inspector.name }}</div>
      <div
        v-if="
          store.editMode &&
          store.inspector.feedId &&
          store.inspector.feedId !== store.currentFeedId
        "
        class="hint"
      >
        belongs to another feed — make it current to edit
      </div>
    </template>
  </div>
</template>
