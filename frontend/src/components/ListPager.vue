<script setup>
defineProps({
  label: { type: String, required: true },
  canPrev: { type: Boolean, required: true },
  canNext: { type: Boolean, required: true },
});
const emit = defineEmits(["prev", "next"]);
</script>

<template>
  <div class="pager">
    <span class="mono label">{{ label }}</span>
    <button :disabled="!canPrev" aria-label="Previous page" @click="emit('prev')">
      ‹
    </button>
    <button :disabled="!canNext" aria-label="Next page" @click="emit('next')">
      ›
    </button>
  </div>
</template>

<style scoped>
.pager {
  display: flex;
  align-items: center;
  gap: 5px;
}
.label {
  flex: 1;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-5);
}
.pager button {
  width: 24px;
  height: 22px;
  border: 1px solid var(--border-3);
  border-radius: var(--r-btn-sm);
  background: var(--surface);
  color: var(--ink-2);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}
.pager button:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
</style>
