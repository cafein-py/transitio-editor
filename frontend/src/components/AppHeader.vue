<script setup>
import { computed, ref } from "vue";

import { loadTable, saveFeed, toggleEditMode } from "../actions.js";
import { saveWorkspace, saveWorkspaceAs } from "../actions/workspace.js";
import { currentFeed } from "../catalogue.js";
import { store } from "../store.js";
import { pushToast } from "../toasts.js";
import SaveWorkspaceDialog from "./SaveWorkspaceDialog.vue";

const feed = computed(() => currentFeed(store.catalogue, store.currentFeedId));
const activeFeeds = computed(
  () => store.catalogue.filter((entry) => entry.active).length,
);
// A strip of feed colours identifies the workspace at a glance.
const feedColors = computed(() =>
  store.catalogue.slice(0, 6).map((entry) => entry.color),
);

const dialogOpen = ref(false);
const menuOpen = ref(false);

async function onSaveWorkspace() {
  menuOpen.value = false;
  if (!(await saveWorkspace())) dialogOpen.value = true;
}

function onSaveWorkspaceAs() {
  menuOpen.value = false;
  dialogOpen.value = true;
}

async function onDialogSave(name, dir) {
  if (await saveWorkspaceAs(name, dir)) dialogOpen.value = false;
}

const LAYOUTS = [
  { key: "sidebar", label: "Sidebar" },
  { key: "inspector", label: "Narrow panel" },
  { key: "table", label: "Table" },
];

function setLayout(key) {
  store.layout = key;
  if (key === "table") {
    store.tableView.open = true;
    loadTable({ offset: 0 });
  } else {
    store.tableView.open = false;
  }
}

async function onSaveValidate() {
  await saveFeed();
  const result = store.saveResult;
  if (result) {
    pushToast({
      title: result.clean ? "saved and validated" : "saved with issues",
      body: result.message,
    });
  }
}
</script>

<template>
  <header class="header">
    <div class="mark">
      <span class="mark-dot"></span>
      <span class="mark-name">transitio</span>
    </div>

    <div class="ws-chip" :title="store.session.path || 'Workspace not saved yet'">
      <span class="ws-colors">
        <span
          v-for="(color, index) in feedColors"
          :key="index"
          :style="{ background: color }"
        ></span>
      </span>
      <span class="ws-text">
        <span class="ws-name">{{ store.session.wsName || "Untitled workspace" }}</span>
        <span class="ws-meta">{{ activeFeeds }}/{{ store.catalogue.length }} feeds</span>
      </span>
    </div>

    <button class="search-pill" @click="store.activePanel = 'search'">
      <svg viewBox="0 0 14 14" fill="none" stroke="currentColor">
        <circle cx="6" cy="6" r="3.6" stroke-width="1.5" />
        <path d="M8.8 8.8L12 12" stroke-width="1.5" stroke-linecap="round" />
      </svg>
      <span>Search places…</span>
      <span class="kbd">⌘K</span>
    </button>

    <button
      class="edit-pill"
      :class="{ on: store.editMode }"
      :disabled="!store.catalogue.length"
      :title="store.editMode ? 'Turn editing off' : 'Turn editing on'"
      @click="toggleEditMode"
    >
      <span class="knob"></span>
      <template v-if="store.editMode && feed">
        <span class="swatch" :style="{ background: feed.color }"></span>
        <span class="edit-feed">{{ feed.name }}</span>
      </template>
      <span v-else class="edit-label">Read-only</span>
    </button>

    <div class="seg">
      <button
        v-for="layout in LAYOUTS"
        :key="layout.key"
        :class="{ active: store.layout === layout.key }"
        :title="layout.label"
        @click="setLayout(layout.key)"
      >
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor">
          <rect x="1.5" y="2.5" width="13" height="11" rx="1.5" stroke-width="1.3" />
          <path
            v-if="layout.key === 'sidebar'"
            d="M6 2.5v11"
            stroke-width="1.3"
          />
          <path
            v-else-if="layout.key === 'inspector'"
            d="M4.5 2.5v11"
            stroke-width="1.3"
          />
          <path v-else d="M1.5 9.5h13" stroke-width="1.3" />
        </svg>
        <span v-if="layout.key === 'sidebar'">Sidebar</span>
      </button>
    </div>

    <div class="spacer"></div>

    <button
      class="history-btn"
      :class="{ open: store.session.historyOpen }"
      title="Session log"
      @click="store.session.historyOpen = !store.session.historyOpen"
    >
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor">
        <circle cx="8" cy="8" r="6" stroke-width="1.4" />
        <path d="M8 4.5V8l2.4 1.6" stroke-width="1.4" stroke-linecap="round" />
      </svg>
      <span v-if="store.session.log.length" class="history-badge">
        {{ store.session.log.length }}
      </span>
    </button>

    <span v-if="store.dirty" class="dirty-dot" title="Edited since last save"></span>

    <div class="save-split">
      <button class="btn" :disabled="store.session.saving" @click="onSaveWorkspace">
        Save workspace
      </button>
      <button class="btn caret" aria-label="More save options" @click="menuOpen = !menuOpen">
        ▾
      </button>
      <div v-if="menuOpen" class="menu-backdrop" @click="menuOpen = false"></div>
      <div v-if="menuOpen" class="menu">
        <button @click="onSaveWorkspaceAs">Save as…</button>
      </div>
    </div>

    <button
      class="btn dark"
      :disabled="!store.currentFeedId || store.saving"
      @click="onSaveValidate"
    >
      {{ store.saving ? "Saving…" : "Save & validate" }}
    </button>

    <SaveWorkspaceDialog
      v-if="dialogOpen"
      @close="dialogOpen = false"
      @save="onDialogSave"
    />
  </header>
</template>

<style scoped>
.header {
  height: 46px;
  flex: none;
  background: var(--surface);
  border-bottom: 1px solid var(--border-3);
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 12px;
}
.mark {
  display: flex;
  align-items: center;
  gap: 6px;
}
.mark-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
}
.mark-name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.ws-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-2);
  background: var(--panel);
  border-radius: var(--r-input);
  padding: 4px 10px 4px 7px;
  max-width: 220px;
}
.ws-colors {
  display: flex;
  gap: 1.5px;
  flex: none;
}
.ws-colors span {
  width: 3.5px;
  height: 16px;
  border-radius: 1px;
}
.ws-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.ws-name {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ws-meta {
  font: 9.5px var(--mono);
  color: var(--ink-5);
  white-space: nowrap;
}
.search-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-2);
  background: var(--surface);
  border-radius: var(--r-pill);
  height: 28px;
  padding: 0 6px 0 10px;
  color: var(--ink-5);
  font: 11.5px var(--sans);
  cursor: pointer;
}
.search-pill:hover {
  border-color: var(--border-4);
  color: var(--ink-3);
}
.search-pill svg {
  width: 13px;
  height: 13px;
}
.edit-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid var(--border-2);
  background: var(--surface);
  border-radius: var(--r-pill);
  height: 28px;
  padding: 0 11px 0 5px;
  cursor: pointer;
  font: 11.5px var(--sans);
  color: var(--ink-4);
  max-width: 190px;
}
.edit-pill:disabled {
  color: var(--ink-disabled);
  cursor: default;
}
.edit-pill .knob {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--track);
  border: 1px solid var(--border-3);
  flex: none;
  transition: background 0.12s;
}
.edit-pill.on {
  border-color: var(--accent-border);
  background: var(--accent-tint);
  color: var(--ink);
}
.edit-pill.on .knob {
  background: var(--accent);
  border-color: var(--accent);
}
.edit-feed {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
}
.seg {
  display: flex;
  background: var(--track);
  border-radius: var(--r-input);
  padding: 2px;
  gap: 1px;
}
.seg button {
  display: flex;
  align-items: center;
  gap: 5px;
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 4px 8px;
  font: 500 11.5px var(--sans);
  color: var(--ink-4);
  cursor: pointer;
}
.seg button svg {
  width: 14px;
  height: 14px;
}
.seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-thumb);
}
.spacer {
  flex: 1;
}
.history-btn {
  position: relative;
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-2);
  border-radius: 50%;
  background: var(--surface);
  color: var(--ink-4);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.history-btn.open {
  color: var(--accent);
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.history-badge {
  position: absolute;
  top: -4px;
  right: -5px;
  min-width: 15px;
  height: 15px;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  font: 500 9px var(--mono);
  display: grid;
  place-items: center;
  padding: 0 3px;
}
.history-btn:hover {
  color: var(--ink-2);
  background: var(--panel);
}
.history-btn svg {
  width: 15px;
  height: 15px;
}
.dirty-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--warning);
  flex: none;
}
.save-split {
  position: relative;
  display: flex;
}
.save-split .btn {
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
}
.save-split .caret {
  border-top-left-radius: 0;
  border-bottom-left-radius: 0;
  border-left: 0;
  padding: 0 6px;
  color: var(--ink-4);
}
.menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 29;
}
.menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 30;
  background: var(--surface);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  box-shadow: 0 4px 16px rgba(20, 22, 26, 0.12);
  padding: 3px;
  min-width: 130px;
}
.menu button {
  display: block;
  width: 100%;
  text-align: left;
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 6px 9px;
  font: 12px var(--sans);
  color: var(--ink);
  cursor: pointer;
}
.menu button:hover {
  background: var(--panel);
}
</style>
