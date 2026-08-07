<script setup>
import { capitalize, dismissToast, runToastAction, toasts } from "../toasts.js";
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div v-for="toast in toasts" :key="toast.id" class="toast">
      <div class="toast-text">
        <div class="toast-title">{{ capitalize(toast.title) }}</div>
        <div v-if="toast.body" class="toast-body">
          {{ capitalize(toast.body) }}
        </div>
      </div>
      <button
        v-if="toast.action"
        class="toast-action"
        @click="runToastAction(toast.id)"
      >
        {{ capitalize(toast.action.label) }}
      </button>
      <button
        class="toast-close"
        aria-label="Dismiss"
        @click="dismissToast(toast.id)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  z-index: 50;
  pointer-events: none;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--ink);
  color: #fff;
  border-radius: var(--r-card);
  padding: 9px 12px;
  box-shadow: 0 4px 16px rgba(20, 22, 26, 0.24);
  max-width: 440px;
}
.toast-title {
  font-size: 12.5px;
  font-weight: 600;
}
.toast-body {
  font-size: 11.5px;
  color: rgba(255, 255, 255, 0.75);
  margin-top: 1px;
}
.toast-action {
  font: 500 11.5px var(--sans);
  color: #fff;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: var(--r-btn-sm);
  padding: 4px 10px;
  cursor: pointer;
  flex: none;
}
.toast-action:hover {
  background: rgba(255, 255, 255, 0.22);
}
.toast-close {
  border: 0;
  background: none;
  color: rgba(255, 255, 255, 0.55);
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 3px;
  flex: none;
}
.toast-close:hover {
  color: #fff;
}
</style>
