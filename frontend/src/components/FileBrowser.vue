<script setup>
import { store } from "../store.js";
import { browseTo, chooseBrowsedDir, closeBrowser } from "../actions.js";

// A folder picker: a web page cannot read absolute paths from a native
// file dialog, but the loopback backend can list them. Rendered by
// whichever panel owns the open browser's target, so the listing appears
// next to the path box it fills in.
defineProps({ target: { type: String, required: true } });
</script>

<template>
  <div
    v-if="store.browse.open && store.browse.target === target"
    class="dir-browser"
  >
    <div class="dir-path">{{ store.browse.path }}</div>
    <p v-if="store.browse.error" class="hint net-error">
      {{ store.browse.error }}
    </p>
    <ul class="dir-list">
      <li v-if="store.browse.parent">
        <button type="button" @click="browseTo(store.browse.parent)">..</button>
      </li>
      <li v-for="name in store.browse.dirs" :key="name">
        <button type="button" @click="browseTo(`${store.browse.path}/${name}`)">
          {{ name }}/
        </button>
      </li>
    </ul>
    <div class="mode-row">
      <button type="button" @click="chooseBrowsedDir">Use this folder</button>
      <button type="button" @click="closeBrowser">Cancel</button>
    </div>
  </div>
</template>
