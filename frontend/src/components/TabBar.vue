<script setup>
import { store } from "../store.js";
</script>

<template>
  <div class="tab-bar">
    <button :class="{ active: store.activeTab === 'edit' }" @click="store.activeTab = 'edit'">
      Edit
    </button>
    <button
      :class="{ active: store.activeTab === 'catalogue' }"
      @click="store.activeTab = 'catalogue'"
    >
      Catalogue
      <span v-if="store.catalogue.length > 1" class="badge">{{ store.catalogue.length }}</span>
    </button>
    <button
      :class="{ active: store.activeTab === 'report' }"
      @click="store.activeTab = 'report'"
    >
      Report
      <span v-if="store.reportStale" class="dot" title="edited since last validation"></span>
    </button>
  </div>
</template>
