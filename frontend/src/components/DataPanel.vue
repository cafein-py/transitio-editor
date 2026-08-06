<script setup>
import { computed, reactive, ref } from "vue";

import {
  createGroup,
  deleteGroup,
  dropFeedInGroup,
  mergeSelected,
  renameGroup,
  reorderGroup,
  setFeedsActive,
  toggleMergeSelected,
} from "../actions/catalogue.js";
import { openBrowser } from "../actions.js";
import { setShapeColorBy } from "../actions/mapView.js";
import { toggleNetworkVisible } from "../actions/streets.js";
import { groupedCatalogue } from "../catalogue.js";
import { bboxLabel } from "../streets.js";
import { store } from "../store.js";
import FeedCard from "./FeedCard.vue";
import FileBrowser from "./FileBrowser.vue";
import Icon from "./Icon.vue";

const q = ref("");
const collapsed = reactive(new Set());
const dragOver = ref(null); // group name ("" for ungrouped) under a drag
const renaming = ref(null);
const renameDraft = ref("");

const matches = (feed) =>
  !q.value.trim() ||
  feed.name.toLowerCase().includes(q.value.trim().toLowerCase());

const grouped = computed(() => {
  const { sections, ungrouped } = groupedCatalogue(
    store.catalogue,
    store.groups,
  );
  return {
    sections: sections.map((section) => ({
      ...section,
      all: section.feeds,
      feeds: section.feeds.filter(matches),
    })),
    ungrouped: ungrouped.filter(matches),
  };
});

const activeCount = computed(
  () => store.catalogue.filter((feed) => feed.active).length,
);

// "Layers" spans the feeds AND the street network.
const allShown = computed(
  () =>
    activeCount.value === store.catalogue.length &&
    (!store.network.available || store.network.visible),
);
const allHidden = computed(
  () =>
    activeCount.value === 0 &&
    (!store.network.available || !store.network.visible),
);

async function showAllLayers() {
  await setFeedsActive(store.catalogue, true);
  if (store.network.available && !store.network.visible) {
    toggleNetworkVisible();
  }
}

async function hideAllLayers() {
  await setFeedsActive(store.catalogue, false);
  if (store.network.available && store.network.visible) {
    toggleNetworkVisible();
  }
}

const tint = (hex, alpha) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
};

const groupTint = (section) =>
  section.all.length ? tint(section.all[0].color, 0.1) : "var(--track)";

function toggleCollapsed(name) {
  if (collapsed.has(name)) collapsed.delete(name);
  else collapsed.add(name);
}

function startRename(name) {
  renaming.value = name;
  renameDraft.value = name;
}

async function commitRename(name) {
  const value = renameDraft.value;
  renaming.value = null;
  await renameGroup(name, value);
}

// The dashed button creates the group right away under a placeholder
// name and drops straight into renaming it.
async function newGroup() {
  const base = "New group";
  let name = base;
  for (let n = 2; store.groups.includes(name); n += 1) name = `${base} ${n}`;
  await createGroup(name);
  if (store.groups.includes(name)) startRename(name);
}

function onDrop(group) {
  dragOver.value = null;
  dropFeedInGroup(group);
}

const osmName = computed(() => {
  if (store.network.displayName) return store.network.displayName;
  const source = store.network.source;
  return source ? source.split("/").pop() : "OSM network";
});

const osmRenaming = ref(false);
const osmDraft = ref("");

function startOsmRename() {
  osmDraft.value = osmName.value;
  osmRenaming.value = true;
}

// The extract's name is display state (saved with the workspace), not a
// server-side property — renaming needs no request.
function commitOsmRename() {
  const value = osmDraft.value.trim();
  osmRenaming.value = false;
  if (value) store.network.displayName = value;
}

const osmMeta = computed(() => {
  const parts = [];
  if (store.network.loaded) {
    parts.push(
      `${store.network.wayCount.toLocaleString()} ways`,
      `${store.network.nodeCount.toLocaleString()} nodes`,
    );
  }
  const label = bboxLabel(store.network.bbox);
  if (label) parts.push(label);
  return parts.join(" · ");
});

const canMerge = computed(() => store.merge.selected.length >= 2);
</script>

<template>
  <div class="data-panel">
    <div class="head">
      <h1>Data</h1>
      <span class="mono meta">
        {{ activeCount }}/{{ store.catalogue.length }} shown
      </span>
    </div>
    <p class="intro">
      Show the feeds you want on the map together; the
      <b>current feed</b> is the target of edits, validation and save.
    </p>

    <div class="filter-row">
      <input v-model="q" placeholder="Filter feeds…" />
      <button
        class="add-btn"
        title="Find and add feeds"
        @click="store.paletteOpen = true"
      >
        +
      </button>
    </div>

    <div class="view-row">
      <span class="label">Colour by</span>
      <div class="seg">
        <button
          :class="{ active: store.shapeColorBy === 'mode' }"
          @click="setShapeColorBy('mode')"
        >
          Mode
        </button>
        <button
          :class="{ active: store.shapeColorBy === 'feed' }"
          @click="setShapeColorBy('feed')"
        >
          Feed
        </button>
      </div>
    </div>

    <div class="layer-row">
      <button class="btn small" :disabled="allShown" @click="showAllLayers">
        Show all layers
      </button>
      <button class="btn small" :disabled="allHidden" @click="hideAllLayers">
        Hide all layers
      </button>
    </div>

    <!-- Group cards; each is a drop target, empty groups persist. -->
    <div
      v-for="section in grouped.sections"
      :key="section.name"
      class="group"
      :class="{ over: dragOver === section.name }"
      @dragover.prevent="dragOver = section.name"
      @dragleave="dragOver === section.name && (dragOver = null)"
      @drop.prevent="onDrop(section.name)"
    >
      <div class="group-head" :style="{ background: groupTint(section) }">
        <span class="grip">⠿</span>
        <button class="caret" @click="toggleCollapsed(section.name)">
          {{ collapsed.has(section.name) ? "▸" : "▾" }}
        </button>
        <button
          class="eye"
          :class="{ off: !section.all.some((feed) => feed.active) }"
          :title="
            section.all.some((feed) => feed.active)
              ? 'Hide the group from the map'
              : 'Show the group on the map'
          "
          @click="
            setFeedsActive(
              section.all,
              !section.all.some((feed) => feed.active),
            )
          "
        >
          <Icon
            :name="section.all.some((feed) => feed.active) ? 'eye' : 'eye-off'"
          />
        </button>
        <template v-if="renaming === section.name">
          <input
            v-model="renameDraft"
            class="rename"
            @keyup.enter="commitRename(section.name)"
            @keyup.escape="renaming = null"
            @blur="commitRename(section.name)"
          />
        </template>
        <button
          v-else
          class="group-name"
          title="Double-click to rename"
          @dblclick="startRename(section.name)"
        >
          {{ section.name }}
        </button>
        <span class="mono count">
          {{ section.all.filter((feed) => feed.active).length }}/{{
            section.all.length
          }}
        </span>
        <button
          class="tool"
          title="Move the group up"
          @click="reorderGroup(section.name, 'up')"
        >
          ↑
        </button>
        <button
          class="tool"
          title="Move the group down"
          @click="reorderGroup(section.name, 'down')"
        >
          ↓
        </button>
        <button
          class="tool"
          title="Remove the group; its feeds stay"
          @click="deleteGroup(section.name)"
        >
          <Icon name="trash" />
        </button>
      </div>

      <div v-if="!collapsed.has(section.name)" class="group-body">
        <FeedCard
          v-for="feed in section.feeds"
          :key="feed.feed_id"
          :feed="feed"
        />
        <p v-if="!section.feeds.length" class="empty mono">drag feeds here</p>
      </div>
    </div>

    <!-- Ungrouped feeds; also the "file it nowhere" drop target. -->
    <div
      class="group plain"
      :class="{ over: dragOver === '' }"
      @dragover.prevent="dragOver = ''"
      @dragleave="dragOver === '' && (dragOver = null)"
      @drop.prevent="onDrop(null)"
    >
      <div
        v-if="grouped.sections.length && grouped.ungrouped.length"
        class="ungrouped-head mono"
      >
        Ungrouped
      </div>
      <div class="group-body">
        <FeedCard
          v-for="feed in grouped.ungrouped"
          :key="feed.feed_id"
          :feed="feed"
        />
        <p v-if="!store.catalogue.length" class="empty mono">
          no feeds loaded — use + to find some
        </p>
      </div>
    </div>

    <!-- The one OSM extract, so all loaded data is visible in one place. -->
    <div
      v-if="store.network.available"
      class="osm-row"
      :class="{ inactive: !store.network.visible }"
    >
      <div class="osm-left">
        <button
          class="eye"
          :class="{ off: !store.network.visible }"
          :title="store.network.visible ? 'Hide from the map' : 'Show on the map'"
          @click="toggleNetworkVisible"
        >
          <Icon :name="store.network.visible ? 'eye' : 'eye-off'" />
        </button>
        <span class="osm-badge mono">OSM</span>
      </div>
      <span class="osm-icon" :class="{ bad: store.network.error }">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor">
          <path
            d="M6 2.5v13M12 2.5v13M2.5 6h13M2.5 12h13"
            stroke-width="1.5"
            stroke-linecap="round"
          />
        </svg>
      </span>
      <div class="osm-main">
        <div class="osm-name-row">
          <input
            v-if="osmRenaming"
            v-model="osmDraft"
            class="rename"
            @keyup.enter="commitOsmRename"
            @keyup.escape="osmRenaming = false"
            @blur="commitOsmRename"
            @vue:mounted="({ el }) => el.focus()"
          />
          <span
            v-else
            class="osm-name"
            :title="store.network.source + '\nDouble-click to rename'"
            @dblclick="startOsmRename"
          >
            {{ osmName }}
          </span>
        </div>
        <span v-if="osmMeta" class="mono osm-meta">{{ osmMeta }}</span>
      </div>
      <button
        v-if="!store.network.loaded && store.network.error"
        class="btn small"
        title="The network did not load — details on the Streets panel"
        @click="store.activePanel = 'streets'"
      >
        Not loaded
      </button>
    </div>

    <button class="new-group" @click="newGroup">+ New group</button>

    <!-- Merging keeps its pre-redesign form for now. -->
    <div class="legacy">
      <details class="panel">
        <summary>Merge feeds</summary>
        <p class="hint">Pick at least two feeds to merge into a new one.</p>
        <label
          v-for="feed in store.catalogue"
          :key="feed.feed_id"
          class="check"
        >
          <input
            type="checkbox"
            :checked="store.merge.selected.includes(feed.feed_id)"
            @change="toggleMergeSelected(feed)"
          />
          {{ feed.name }}
        </label>
        <form v-if="canMerge" class="merge-form" @submit.prevent="mergeSelected">
          <input
            v-model="store.merge.name"
            placeholder="name for the merged feed"
          />
          <div class="dir-row">
            <input
              v-model="store.merge.directory"
              placeholder="folder to save it in (optional)"
            />
            <button
              type="button"
              @click="
                openBrowser('mergeDir', store.merge.directory.trim() || null)
              "
            >
              Browse…
            </button>
          </div>
          <FileBrowser target="mergeDir" />
          <button class="primary" type="submit" :disabled="store.merge.merging">
            {{
              store.merge.merging
                ? "Merging…"
                : `Merge ${store.merge.selected.length} feeds`
            }}
          </button>
        </form>
      </details>

    </div>
  </div>
</template>

<style scoped>
.data-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}
.head h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.meta {
  font-size: 9.5px;
  color: var(--ink-5);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.intro {
  margin: 0;
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--ink-3);
}
.filter-row {
  display: flex;
  gap: 6px;
}
.filter-row input {
  flex: 1;
  font: 12px var(--sans);
  border: 1px solid var(--border-3);
  border-radius: var(--r-input);
  padding: 6px 10px;
  background: var(--surface);
}
.filter-row input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.add-btn {
  width: 31px;
  border: 1px solid var(--border-4);
  background: var(--surface);
  border-radius: var(--r-input);
  font-size: 15px;
  color: var(--ink-2);
  cursor: pointer;
}
.add-btn:hover {
  background: var(--track);
}
.view-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.view-row .label {
  font-size: 11.5px;
  color: var(--ink-4);
}
.seg {
  display: flex;
  background: var(--track);
  border-radius: var(--r-input);
  padding: 2px;
  gap: 1px;
}
.seg button {
  border: 0;
  background: none;
  border-radius: 6px;
  padding: 3px 10px;
  font: 500 11.5px var(--sans);
  color: var(--ink-4);
  cursor: pointer;
}
.seg button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: var(--shadow-thumb);
}
.layer-row {
  display: flex;
  gap: 6px;
}
.layer-row .btn {
  flex: 1;
  justify-content: center;
}

.group {
  border: 1px solid var(--border-2);
  border-radius: var(--r-card);
  background: var(--surface);
  overflow: hidden;
}
.group.plain {
  border: 0;
  background: none;
  overflow: visible;
}
.group.over {
  box-shadow: 0 0 0 3px var(--accent-border);
}
.group-head {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-1);
}
.grip {
  color: var(--ink-6);
  cursor: grab;
  font-size: 11px;
  flex: none;
}
.caret {
  border: 0;
  background: none;
  color: var(--ink-4);
  cursor: pointer;
  font-size: 10px;
  padding: 1px 2px;
  flex: none;
}
.eye {
  border: 0;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
  padding: 1px 2px;
  flex: none;
}
.eye svg {
  width: 14px;
  height: 14px;
  display: block;
}
.eye.off {
  color: var(--ink-disabled);
}
.group-name {
  border: 0;
  background: none;
  font: 600 12px var(--sans);
  color: var(--ink);
  cursor: text;
  padding: 0;
  text-align: left;
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rename {
  flex: 1;
  min-width: 0;
  font: 600 12px var(--sans);
  border: 1px solid var(--accent-border);
  border-radius: 5px;
  padding: 1px 5px;
  background: var(--surface);
}
.count {
  font-size: 9.5px;
  color: var(--ink-4);
  flex: none;
}
.tool {
  border: 0;
  background: none;
  color: var(--ink-5);
  cursor: pointer;
  font-size: 11px;
  padding: 2px 3px;
  border-radius: 5px;
  flex: none;
}
.tool svg {
  width: 13px;
  height: 13px;
  display: block;
}
.tool:hover {
  color: var(--ink);
  background: rgba(20, 22, 26, 0.06);
}
.group-body {
  padding: 7px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.empty {
  margin: 2px;
  font-size: 10px;
  color: var(--ink-6);
  text-align: center;
}
.ungrouped-head {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--ink-5);
  padding: 2px 2px 0;
}
.osm-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  border: 1px solid rgba(122, 79, 191, 0.3);
  /* the purple spine + soft tint say "not a feed" without the noise a
     pattern brings */
  border-left: 3px solid rgba(122, 79, 191, 0.55);
  border-radius: var(--r-card);
  padding: 8px 9px;
  background: rgba(122, 79, 191, 0.055);
}
.osm-row.inactive .osm-main,
.osm-row.inactive .osm-icon,
.osm-row.inactive .osm-badge {
  opacity: 0.55;
}
.osm-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  flex: none;
}
.osm-icon {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  background: rgba(122, 79, 191, 0.24);
  color: #5e3a99;
  display: grid;
  place-items: center;
  flex: none;
}
.osm-icon svg {
  width: 13px;
  height: 13px;
}
.osm-icon.bad {
  background: rgba(184, 58, 58, 0.12);
  color: var(--error);
}
.osm-main {
  flex: 1;
  min-width: 0;
}
.osm-name-row {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}
.osm-name {
  font-size: 12.5px;
  font-weight: 550;
  line-height: 1.25;
  overflow-wrap: anywhere;
  cursor: text;
}
.osm-badge {
  font-size: 8.5px;
  letter-spacing: 0.05em;
  color: #fff;
  background: rgba(122, 79, 191, 0.85);
  border-radius: 4px;
  padding: 2px 5px;
  flex: none;
}
.osm-meta {
  display: block;
  font-size: 10px;
  color: var(--ink-6);
  margin-top: 3px;
  line-height: 1.4;
}
.new-group {
  border: 1px dashed var(--border-4);
  background: transparent;
  border-radius: 9px;
  padding: 7px;
  font: 11.5px var(--sans);
  color: var(--ink-5);
  cursor: pointer;
}
.new-group:hover {
  border-color: var(--accent-border);
  color: var(--accent);
}
</style>
