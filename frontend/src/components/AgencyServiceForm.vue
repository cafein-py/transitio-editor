<script setup>
import { forms } from "../store.js";
import { submitAgency, submitService } from "../actions.js";
</script>

<template>
  <details class="panel">
    <summary>New agency / service</summary>
    <form @submit.prevent="submitAgency">
      <input v-model="forms.agency.agency_id" placeholder="agency_id" required />
      <input v-model="forms.agency.agency_name" placeholder="name" required />
      <input v-model="forms.agency.agency_url" placeholder="https://…" required />
      <input
        v-model="forms.agency.agency_timezone"
        placeholder="Europe/Helsinki"
        required
      />
      <button>Add agency</button>
    </form>
    <form @submit.prevent="submitService">
      <input v-model="forms.service.service_id" placeholder="service_id" required />
      <select v-model="forms.service.days">
        <option>daily</option>
        <option>weekdays</option>
        <option>weekend</option>
      </select>
      <input v-model="forms.service.start_date" required />
      <input v-model="forms.service.end_date" required />
      <button>Add service</button>
    </form>
  </details>
</template>
