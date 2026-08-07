<script setup>
defineProps({
  chips: { type: Array, required: true }, // { key, label, count, disabled }
  modelValue: { type: String, required: true },
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <div class="chips">
    <button
      v-for="chip in chips"
      :key="chip.key"
      class="flag-chip"
      :class="{ active: modelValue === chip.key }"
      :disabled="chip.disabled"
      :title="chip.disabled ? 'Needs backend support' : null"
      @click="emit('update:modelValue', chip.key)"
    >
      {{ chip.label }}
      <span v-if="chip.count !== null" class="mono count">{{ chip.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.flag-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 11.5px var(--sans);
  color: var(--ink-3);
  background: var(--surface);
  border: 1px solid var(--border-3);
  border-radius: var(--r-pill);
  padding: 3px 9px;
  cursor: pointer;
}
.flag-chip:hover {
  border-color: var(--border-4);
}
.flag-chip.active {
  color: var(--accent);
  border-color: var(--accent-border);
  background: var(--accent-tint);
}
.flag-chip:disabled {
  color: var(--ink-disabled);
  cursor: default;
  background: transparent;
}
.count {
  font-size: 9.5px;
}
</style>
