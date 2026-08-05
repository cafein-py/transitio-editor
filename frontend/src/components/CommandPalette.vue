<script setup>
import { store } from "../store.js";
import UnifiedSearch from "./UnifiedSearch.vue";

function close() {
  store.paletteOpen = false;
}
</script>

<template>
  <div v-if="store.paletteOpen" class="palette-backdrop" @click.self="close">
    <div class="palette" @keydown.esc="close">
      <UnifiedSearch context="app" />
      <div class="footer mono">
        <span>esc — close</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.palette-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(20, 22, 26, 0.32);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 9vh;
  z-index: 55;
}
.palette {
  width: 620px;
  max-width: calc(100vw - 40px);
  background: var(--surface);
  border-radius: 14px;
  box-shadow: 0 12px 48px rgba(20, 22, 26, 0.28);
  padding: 13px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.footer {
  font-size: 9px;
  color: var(--ink-6);
  border-top: 1px solid var(--border-1);
  padding-top: 7px;
}
</style>
