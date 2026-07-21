<script setup>
import { store } from "../store.js";
</script>

<template>
  <div id="summary" class="panel">
    <div>{{ store.source || "new feed" }}</div>
    <table>
      <tr v-for="(count, name) in store.tables" :key="name">
        <td>{{ name }}</td>
        <td>{{ count }}</td>
      </tr>
    </table>
  </div>
</template>
