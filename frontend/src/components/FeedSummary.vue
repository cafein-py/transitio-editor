<script setup>
import { computed } from "vue";
import { store } from "../store.js";
import { currentFeed } from "../catalogue.js";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));
</script>

<template>
  <div id="summary" class="panel">
    <div v-if="feed" class="current-feed">
      <span class="swatch" :style="{ background: feed.color }"></span>
      <span>{{ feed.name }}</span>
    </div>
    <div>{{ store.source || "new feed" }}</div>
    <table>
      <tr v-for="(count, name) in store.tables" :key="name">
        <td>{{ name }}</td>
        <td>{{ count }}</td>
      </tr>
    </table>
  </div>
</template>
