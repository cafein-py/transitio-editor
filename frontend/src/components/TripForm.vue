<script setup>
import { forms, store } from "../store.js";
import { submitTrip } from "../actions.js";
</script>

<template>
  <details class="panel" @toggle="store.tripPicking = $event.target.open">
    <summary>New frequency trip</summary>
    <form @submit.prevent="submitTrip">
      <input v-model="forms.trip.route_id" placeholder="route_id" required />
      <input v-model="forms.trip.service_id" placeholder="service_id" required />
      <input v-model="forms.trip.trip_id" placeholder="trip_id" required />
      <input v-model="forms.trip.shape_id" placeholder="shape_id (optional)" />
      <input v-model="forms.trip.start" required />
      <input v-model="forms.trip.end" required />
      <input v-model.number="forms.trip.headway" type="number" required />
      <p class="hint">Click stops on the map in visit order:</p>
      <ol>
        <li v-for="(entry, index) in store.tripStops" :key="index">
          {{ entry.stopId }} +
          <input v-model.number="entry.offset" type="number" class="offset" />s
        </li>
      </ol>
      <button type="button" @click="store.tripStops.length = 0">Clear stops</button>
      <button>Add trip</button>
    </form>
  </details>
</template>
