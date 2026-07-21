<script setup>
import { computed, ref } from "vue";

import { store } from "../store.js";
import { clearHighlight, highlightContext } from "../map.js";
import { validateFeed } from "../actions.js";

const expandedCode = ref(null);
function toggleGroup(code) {
  expandedCode.value = expandedCode.value === code ? null : code;
}

const noticeGroups = computed(() => {
  if (!store.report) return [];
  const order = { ERROR: 0, WARNING: 1, INFO: 2 };
  const groups = new Map();
  for (const notice of store.report.notices) {
    let group = groups.get(notice.code);
    if (!group) {
      group = { code: notice.code, severity: notice.severity, count: 0, contexts: [] };
      groups.set(notice.code, group);
    }
    group.count += 1;
    if (group.contexts.length < 20) {
      group.contexts.push(notice.context || {});
    }
  }
  return [...groups.values()].sort(
    (a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3) || b.count - a.count,
  );
});

function describeContext(context) {
  const parts = Object.entries(context).map(([key, value]) => `${key}=${value}`);
  return parts.length ? parts.join(", ") : "(no context)";
}
</script>

<template>
  <div class="panel">
    <button @click="validateFeed">Validate</button>
    <span v-if="store.reportStale" class="hint">edited since — revalidate</span>
    <div v-if="noticeGroups.length" id="notices">
      <div v-for="group in noticeGroups" :key="group.code" class="notice">
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
    <div v-else-if="store.report" class="hint">no notices</div>
  </div>
</template>
