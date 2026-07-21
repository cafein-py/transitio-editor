<script setup>
import { computed } from "vue";

import { store } from "../store.js";
import { clearHighlight, highlightContext } from "../map.js";
import { validateFeed } from "../actions.js";
import { describeContext, groupNotices, severityCounts } from "../notices.js";
import { ref } from "vue";

const groups = computed(() => groupNotices(store.report));
const counts = computed(() => severityCounts(store.report));
const rowCounts = computed(() =>
  store.report ? Object.entries(store.report.row_counts || {}) : [],
);
const serviceWindow = computed(() => store.report && store.report.service_window);

const expandedCode = ref(null);
function toggleGroup(code) {
  expandedCode.value = expandedCode.value === code ? null : code;
}
</script>

<template>
  <div class="report">
    <div class="panel">
      <button @click="validateFeed">Validate</button>
      <span v-if="store.reportStale" class="hint">edited since — revalidate</span>
    </div>

    <div v-if="!store.report" class="panel hint">
      Run validation to inspect the feed's notices.
    </div>

    <template v-else>
      <div class="panel report-summary">
        <span class="count error">{{ counts.ERROR }} errors</span>
        <span class="count warning">{{ counts.WARNING }} warnings</span>
        <span class="count info">{{ counts.INFO }} infos</span>
        <div v-if="serviceWindow" class="hint">
          service window {{ serviceWindow[0] }}–{{ serviceWindow[1] }}
        </div>
      </div>

      <details class="panel" v-if="rowCounts.length">
        <summary>Row counts</summary>
        <table>
          <tr v-for="[name, count] in rowCounts" :key="name">
            <td>{{ name }}</td>
            <td>{{ count }}</td>
          </tr>
        </table>
      </details>

      <div class="panel">
        <div v-if="!groups.length" class="hint">no notices — the feed is clean</div>
        <div v-for="group in groups" :key="group.code" class="notice">
          <div
            class="notice-head"
            :class="group.severity.toLowerCase()"
            @click="toggleGroup(group.code)"
          >
            {{ group.severity }} · {{ group.code }} × {{ group.count }}
          </div>
          <ol v-if="expandedCode === group.code">
            <li
              v-for="(context, index) in group.contexts"
              :key="index"
              class="context"
              @click="highlightContext(context)"
            >
              {{ describeContext(context) }}
            </li>
          </ol>
        </div>
        <button v-if="store.highlightActive" @click="clearHighlight">
          Clear highlight
        </button>
      </div>
    </template>
  </div>
</template>
