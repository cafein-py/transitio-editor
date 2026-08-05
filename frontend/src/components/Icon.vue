<script setup>
// Small stroke-drawn glyphs for row tools; emoji/Unicode stand-ins render
// too differently across platforms to match the design.
defineProps({ name: { type: String, required: true } });
</script>

<template>
  <svg
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.4"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'eye'">
      <path d="M1.8 8C3.6 4.9 5.7 3.4 8 3.4S12.4 4.9 14.2 8c-1.8 3.1-3.9 4.6-6.2 4.6S3.6 11.1 1.8 8Z" />
      <circle cx="8" cy="8" r="2" />
    </template>
    <template v-else-if="name === 'eye-off'">
      <path
        d="M1.8 8C3.6 4.9 5.7 3.4 8 3.4S12.4 4.9 14.2 8c-1.8 3.1-3.9 4.6-6.2 4.6S3.6 11.1 1.8 8Z"
        opacity="0.55"
      />
      <path d="M2.8 13.2 13.2 2.8" />
    </template>
    <template v-else-if="name === 'pencil'">
      <path d="m3 13 .9-3.2 6.8-6.8a1.55 1.55 0 0 1 2.3 2.3l-6.8 6.8L3 13Z" />
      <path d="m9.2 3.7 2.3 2.3" />
    </template>
    <template v-else-if="name === 'map'">
      <path d="M1.8 3.6 6 2.2l4 1.4 4.2-1.4v10.6L10 14.2l-4-1.4-4.2 1.4Z" />
      <path d="M6 2.2v10.6M10 3.6v10.6" opacity="0.6" />
    </template>
    <template v-else-if="name === 'trash'">
      <path d="M2.8 4.6h10.4" />
      <path d="M6.2 4.6V3.2h3.6v1.4" />
      <path d="m4.2 4.6.6 8a1.4 1.4 0 0 0 1.4 1.2h3.6a1.4 1.4 0 0 0 1.4-1.2l.6-8" />
      <path d="M6.7 7.2v3.9M9.3 7.2v3.9" />
    </template>
  </svg>
</template>
