<script setup>
import { store } from "../store.js";
import {
  browseTo,
  chooseBrowsedDir,
  chooseBrowsedFeed,
  chooseBrowsedSession,
  closeBrowser,
} from "../actions.js";

// Rendered by whichever panel owns the open browser's target, so the
// listing appears next to the path box it fills in.
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
      <li
        v-for="name in store.browse.mode === 'feed' ? store.browse.feeds : []"
        :key="name"
      >
        <button
          type="button"
          class="feed-entry"
          @click="chooseBrowsedFeed(name)"
        >
          {{ name }}
        </button>
      </li>
      <li
        v-for="name in store.browse.mode === 'session'
          ? store.browse.sessions
          : []"
        :key="name"
      >
        <button
          type="button"
          class="feed-entry"
          @click="chooseBrowsedSession(name)"
        >
          {{ name }}
        </button>
      </li>
    </ul>
    <p
      v-if="store.browse.mode === 'feed' && !store.browse.feeds.length"
      class="hint"
    >
      no feed archives in this folder.
    </p>
    <p
      v-if="store.browse.mode === 'session' && !store.browse.sessions.length"
      class="hint"
    >
      no session files in this folder.
    </p>
    <div class="mode-row">
      <button
        v-if="store.browse.mode === 'dir'"
        type="button"
        @click="chooseBrowsedDir"
      >
        Use this folder
      </button>
      <button type="button" @click="closeBrowser">Cancel</button>
    </div>
  </div>
</template>
