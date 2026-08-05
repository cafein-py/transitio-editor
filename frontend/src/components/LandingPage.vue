<script setup>
import { computed, onMounted, ref } from "vue";

import {
  cancelLoadSession,
  confirmLoadSession,
  loadSession,
} from "../actions.js";
import { defaultWorkspaceDir } from "../actions/workspace.js";
import { api } from "../api.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";
import UnifiedSearch from "./UnifiedSearch.vue";

const recents = ref([]); // session file names in the default folder
const recentsDir = ref("");
const opening = ref(null);

onMounted(async () => {
  try {
    recentsDir.value = await defaultWorkspaceDir();
    const listing = await api(
      "GET",
      `/api/fs/dirs?path=${encodeURIComponent(recentsDir.value)}`,
    );
    recents.value = listing.sessions || [];
  } catch (error) {
    recents.value = [];
  }
});

function enter() {
  store.screen = "app";
}

function finishOpen(name) {
  enter();
  store.session.historyOpen = true;
  pushToast({
    title: "workspace restored",
    body: name ? name.replace(/\.json$/, "") : store.session.wsName,
  });
}

async function openWorkspace(name) {
  opening.value = name;
  store.session.path = `${recentsDir.value}/${name}`;
  await loadSession();
  opening.value = null;
  if (store.session.confirm) return; // the confirm block takes over
  finishOpen(name);
}

async function confirmOpen() {
  await confirmLoadSession();
  if (!store.session.confirm) finishOpen(null);
}

const extractName = computed(() => {
  if (store.network.displayName) return store.network.displayName;
  const source = store.network.source;
  return source ? source.split("/").pop() : null;
});
</script>

<template>
  <div v-if="store.screen === 'launch'" class="landing">
    <div class="column">
      <div class="mark">
        <span class="mark-dot"></span>
        <span class="mark-name">transitio</span>
        <span class="mono mark-meta">editor</span>
      </div>

      <h1>Find, edit and build public transport data on a map</h1>
      <p class="intro">
        Search and download GTFS feeds from the Mobility Database, pull an
        OpenStreetMap street network for the same area, then edit stops, draw
        route shapes and create services and trips — validated on save. Load
        as many operators as a region needs into one workspace and edit them
        one at a time.
      </p>

      <UnifiedSearch context="landing" />

      <div class="cards">
        <div class="card recents">
          <div class="card-head">
            <span class="mono-label">Recent workspaces</span>
            <span class="mono card-hint">
              Reopening restores edits + activity log
            </span>
          </div>
          <div v-if="store.session.confirm" class="confirm">
            <p class="confirm-text">
              {{
                store.session.confirm.reason === "osm-edits"
                  ? "Loading this workspace discards your unsaved street-network edits."
                  : "Loading this workspace replaces the feeds already loaded."
              }}
            </p>
            <div class="confirm-actions">
              <button class="btn small dark" @click="confirmOpen">
                Load anyway
              </button>
              <button class="btn small" @click="cancelLoadSession">Cancel</button>
            </div>
          </div>
          <button
            v-for="name in recents.slice(0, 6)"
            :key="name"
            class="recent"
            :disabled="opening !== null"
            @click="openWorkspace(name)"
          >
            <span class="recent-name">{{ name.replace(/\.json$/, "") }}</span>
            <span class="mono recent-meta">
              {{ opening === name ? "opening…" : "session file" }}
            </span>
          </button>
          <p v-if="!recents.length" class="mono empty">
            no saved workspaces in {{ recentsDir || "the default folder" }}
          </p>
        </div>

        <div class="card network">
          <div class="card-head">
            <span class="mono-label">Street network</span>
          </div>
          <p class="card-text">
            An OSM extract lets drawn shapes snap to real streets. One extract
            covers every feed in the workspace.
          </p>
          <div v-if="extractName" class="extract-row">
            <span class="dot"></span>
            <span class="mono extract-name">{{ extractName }}</span>
          </div>
          <p v-else class="mono empty">
            none yet — search a place above to fetch one
          </p>
          <button class="btn dark open" @click="enter">Open workspace</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.landing {
  position: fixed;
  inset: 0;
  z-index: 50;
  overflow-y: auto;
  background:
    radial-gradient(
      120% 90% at 50% 0%,
      #fdfdfc 0%,
      var(--panel) 55%,
      #f4f3f1 100%
    );
  display: grid;
  justify-items: center;
  align-content: start;
  padding: 34px 24px 48px;
}
.column {
  width: 100%;
  max-width: 780px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.mark {
  display: flex;
  align-items: center;
  gap: 9px;
}
.mark-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
}
.mark-name {
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.mark-meta {
  font-size: 10.5px;
  color: var(--ink-5);
  padding-top: 3px;
}
h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.15;
  max-width: 30ch;
}
.intro {
  margin: -6px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-3);
  max-width: 68ch;
}
.cards {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 14px;
  align-items: start;
}
.card {
  background: var(--surface);
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  padding: 12px 13px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.card-hint {
  font-size: 9px;
  color: var(--ink-6);
}
.recent {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  border: 0;
  background: none;
  border-top: 1px solid var(--border-1);
  padding: 8px 2px;
  cursor: pointer;
  text-align: left;
}
.recent:hover .recent-name {
  color: var(--accent);
}
.recent-name {
  font-size: 13px;
  font-weight: 600;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-meta {
  font-size: 9.5px;
  color: var(--ink-6);
  flex: none;
}
.confirm {
  border: 1px solid var(--accent-border);
  background: var(--accent-tint);
  border-radius: var(--r-chip);
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.confirm-text {
  margin: 0;
  font-size: 11.5px;
  color: var(--ink-2);
}
.confirm-actions {
  display: flex;
  gap: 6px;
}
.card-text {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-3);
}
.extract-row {
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--panel);
  border: 1px solid var(--border-2);
  border-radius: var(--r-input);
  padding: 7px 9px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ok);
  flex: none;
}
.extract-name {
  font-size: 10.5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.empty {
  margin: 0;
  font-size: 10px;
  color: var(--ink-6);
}
.open {
  justify-content: center;
  margin-top: 2px;
}
</style>
