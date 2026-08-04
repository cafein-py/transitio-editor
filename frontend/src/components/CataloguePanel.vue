<script setup>
import { computed, ref } from "vue";

import { store } from "../store.js";
import { groupedCatalogue } from "../catalogue.js";
import {
  addFeed,
  cancelLoadSession,
  confirmLoadSession,
  createGroup,
  deleteGroup,
  dropFeedInGroup,
  loadSession,
  mergeSelected,
  openBrowser,
  renameGroup,
  saveSession,
  toggleNetworkVisible,
} from "../actions.js";
import FeedRow from "./FeedRow.vue";
import FileBrowser from "./FileBrowser.vue";

const osmName = computed(() => {
  const source = store.network.source;
  return source ? source.split("/").pop() : "OSM network";
});

const canMerge = computed(() => store.merge.selected.length >= 2);
const grouped = computed(() => groupedCatalogue(store.catalogue, store.groups));

// The group whose name is being edited, and its draft name.
const editing = ref(null);
const draft = ref("");

function startRename(name) {
  editing.value = name;
  draft.value = name;
}

async function commitRename(name) {
  const value = draft.value;
  editing.value = null;
  await renameGroup(name, value);
}
</script>

<template>
  <div class="panel catalogue">
    <p class="hint">
      Activate the feeds to show together on the map; the current feed is the
      target of edits, validation and save.
    </p>
    <table
      v-if="store.catalogue.length || store.groups.length"
      class="catalogue-table"
    >
      <thead>
        <tr>
          <th title="shown on map">show</th>
          <th>feed</th>
          <th title="edit target">edit</th>
          <th title="pick feeds to merge">merge</th>
          <th></th>
        </tr>
      </thead>
      <!-- One tbody per group, so dropping anywhere in a group's block
           files the feed there; columns stay aligned across groups. -->
      <tbody
        v-for="section in grouped.sections"
        :key="section.name"
        class="feed-group"
        @dragover.prevent
        @drop.prevent="dropFeedInGroup(section.name)"
      >
        <tr class="group-heading">
          <td colspan="5">
            <template v-if="editing === section.name">
              <input
                v-model="draft"
                class="group-rename"
                @keyup.enter="commitRename(section.name)"
                @keyup.escape="editing = null"
              />
              <button type="button" @click="commitRename(section.name)">
                Save
              </button>
              <button type="button" @click="editing = null">Cancel</button>
            </template>
            <template v-else>
              <span class="group-name">{{ section.name }}</span>
              <span class="feed-tables">{{ section.feeds.length }} feeds</span>
              <button type="button" @click="startRename(section.name)">
                Rename
              </button>
              <button
                type="button"
                title="remove the group; its feeds stay"
                @click="deleteGroup(section.name)"
              >
                Ungroup
              </button>
            </template>
          </td>
        </tr>
        <FeedRow
          v-for="feed in section.feeds"
          :key="feed.feed_id"
          :feed="feed"
        />
        <tr v-if="!section.feeds.length" class="group-empty">
          <td colspan="5">drag feeds here</td>
        </tr>
      </tbody>
      <tbody
        class="feed-group ungrouped"
        @dragover.prevent
        @drop.prevent="dropFeedInGroup(null)"
      >
        <tr v-if="grouped.sections.length" class="group-heading">
          <td colspan="5"><span class="group-name">ungrouped</span></td>
        </tr>
        <FeedRow
          v-for="feed in grouped.ungrouped"
          :key="feed.feed_id"
          :feed="feed"
        />
      </tbody>
    </table>
    <p v-else class="hint">no feeds loaded.</p>
    <p v-if="!store.catalogue.length && store.groups.length" class="hint">
      no feeds loaded.
    </p>

    <!-- The one OSM extract loads via the Network tab or --osm-pbf; it lists
         here so all loaded data is visible in one place. -->
    <div v-if="store.network.available" class="osm-row">
      <input
        type="checkbox"
        title="shown on map"
        :checked="store.network.visible"
        @change="toggleNetworkVisible"
      />
      <span class="kind-badge osm">OSM</span>
      <span class="feed-name" :title="store.network.source">{{ osmName }}</span>
      <span v-if="store.network.loaded" class="feed-tables">
        {{ store.network.wayCount }} ways, {{ store.network.nodeCount }} nodes
      </span>
    </div>

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
            openBrowser('mergeDir', 'dir', store.merge.directory.trim() || null)
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

    <!-- Sessions: save what is loaded, or bring a saved session back. -->
    <div class="add-feed session-block">
      <div class="dir-row">
        <input
          v-model="store.session.path"
          placeholder="session file (.json)"
        />
        <button
          type="button"
          @click="
            openBrowser(
              'sessionPath',
              'session',
              store.session.path.trim() || null,
            )
          "
        >
          Browse…
        </button>
      </div>
      <FileBrowser target="sessionPath" />
      <div v-if="store.session.confirm" class="crop-panel">
        <p class="hint">
          {{
            store.session.confirm.reason === "osm-edits"
              ? "Loading this session discards your unsaved OSM network edits."
              : `Loading this session replaces the ${store.session.confirm.feeds}
                 loaded feed${store.session.confirm.feeds === 1 ? "" : "s"} (and groups).`
          }}
        </p>
        <div class="mode-row">
          <button class="primary" type="button" @click="confirmLoadSession">
            Load anyway
          </button>
          <button type="button" @click="cancelLoadSession">Cancel</button>
        </div>
      </div>
      <div class="mode-row">
        <button
          type="button"
          class="primary"
          :disabled="!store.session.path.trim() || store.session.saving"
          @click="saveSession"
        >
          {{ store.session.saving ? "Saving…" : "Save session" }}
        </button>
        <button
          type="button"
          :disabled="!store.session.path.trim() || store.session.loading"
          @click="loadSession()"
        >
          {{ store.session.loading ? "Loading…" : "Load session" }}
        </button>
      </div>
    </div>

    <form class="add-feed" @submit.prevent="createGroup">
      <div class="dir-row">
        <input v-model="store.newGroupName" placeholder="new group name" />
        <button type="submit" :disabled="!store.newGroupName.trim()">
          Add group
        </button>
      </div>
    </form>

    <form class="add-feed" @submit.prevent="addFeed">
      <div class="dir-row">
        <input
          v-model="store.newFeedPath"
          placeholder="path to a GTFS feed (.zip)"
        />
        <button
          type="button"
          @click="
            openBrowser('feedPath', 'feed', store.newFeedPath.trim() || null)
          "
        >
          Browse…
        </button>
      </div>
      <FileBrowser target="feedPath" />
      <button
        class="primary"
        type="submit"
        :disabled="!store.newFeedPath.trim()"
      >
        Load feed
      </button>
    </form>
  </div>
</template>
