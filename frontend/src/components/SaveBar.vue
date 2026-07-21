<script setup>
import { store } from "../store.js";
import { saveFeed } from "../actions.js";
</script>

<template>
  <div class="panel">
    <button class="primary" @click="saveFeed">Save &amp; validate</button>
    <div id="save-result">
      <span v-if="store.saving">saving…</span>
      <span
        v-else-if="store.saveResult"
        :class="store.saveResult.clean ? 'clean' : 'dirty'"
      >
        {{ store.saveResult.message }}
      </span>
    </div>
  </div>
</template>
