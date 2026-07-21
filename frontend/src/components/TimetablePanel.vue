<script setup>
import { store } from "../store.js";
import {
  applyTripTimes,
  deleteTrip,
  loadTrip,
  loadTrips,
  onTimetableToggle,
  shiftTrip,
} from "../actions.js";
</script>

<template>
  <details class="panel" @toggle="onTimetableToggle($event.target.open)">
    <summary>Timetable</summary>
    <select v-model="store.timetableRoute" @change="loadTrips">
      <option disabled value="">route…</option>
      <option
        v-for="route in store.routes"
        :key="route.route_id"
        :value="route.route_id"
      >
        {{ route.route_short_name || route.route_id }}
      </option>
    </select>
    <ul id="trip-list">
      <li
        v-for="trip in store.routeTrips"
        :key="trip.trip_id"
        :class="{ selected: store.trip && store.trip.trip_id === trip.trip_id }"
        @click="loadTrip(trip.trip_id)"
      >
        {{ trip.trip_id }} · dir {{ trip.direction_id || "0" }} ·
        {{ trip.first_departure || "—" }} · {{ trip.stop_count }} stops
      </li>
    </ul>
    <div v-if="store.trip">
      <table class="times">
        <tr>
          <th>stop</th>
          <th>arrival</th>
          <th>departure</th>
        </tr>
        <tr v-for="row in store.trip.times" :key="row.stop_sequence">
          <td>{{ row.stop_name || row.stop_id }}</td>
          <td><input v-model="row.arrival_time" /></td>
          <td><input v-model="row.departure_time" /></td>
        </tr>
      </table>
      <div class="mode-row">
        <button @click="applyTripTimes">Apply times</button>
        <button @click="deleteTrip">Delete trip</button>
      </div>
      <label>
        shift by
        <input v-model.number="store.shiftSeconds" type="number" class="offset" />
        s <button @click="shiftTrip">Shift</button>
      </label>
    </div>
  </details>
</template>
