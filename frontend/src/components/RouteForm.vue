<script setup>
import { forms } from "../store.js";
import { submitRoute } from "../actions.js";
</script>

<template>
  <details class="panel">
    <summary>New route</summary>
    <form @submit.prevent="submitRoute">
      <input v-model="forms.route.route_id" placeholder="route_id" required />
      <input
        v-model="forms.route.route_short_name"
        placeholder="short name"
        required
      />
      <select v-model.number="forms.route.route_type">
        <option value="0">tram</option>
        <option value="1">subway</option>
        <option value="2">rail</option>
        <option value="3">bus</option>
        <option value="4">ferry</option>
      </select>
      <input v-model="forms.route.agency_id" placeholder="agency_id (optional)" />
      <button>Add route</button>
    </form>
  </details>
</template>
