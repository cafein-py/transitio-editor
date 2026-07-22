<script setup>
import { store } from "../store.js";
import { feedTableSummary } from "../catalogue.js";
import {
  addFeed,
  removeFeed,
  setCurrentFeed,
  toggleFeedActive,
} from "../actions.js";
</script>

<template>
  <div class="panel catalogue">
    <p class="hint">
      Activate the feeds to show together on the map; the current feed is the
      target of edits, validation and save.
    </p>
    <table v-if="store.catalogue.length" class="catalogue-table">
      <thead>
        <tr>
          <th title="shown on map">show</th>
          <th>feed</th>
          <th title="edit target">edit</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="feed in store.catalogue"
          :key="feed.feed_id"
          :class="{ current: feed.current }"
        >
          <td>
            <input
              type="checkbox"
              :checked="feed.active"
              @change="toggleFeedActive(feed)"
            />
          </td>
          <td>
            <span class="swatch" :style="{ background: feed.color }"></span>
            <span class="feed-name">{{ feed.name }}</span>
            <span class="feed-tables">{{ feedTableSummary(feed.tables) }}</span>
          </td>
          <td>
            <input
              type="radio"
              name="current-feed"
              :checked="feed.current"
              @change="setCurrentFeed(feed)"
            />
          </td>
          <td>
            <button
              class="remove"
              title="remove from catalogue"
              @click="removeFeed(feed)"
            >
              ×
            </button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="hint">no feeds loaded.</p>

    <form class="add-feed" @submit.prevent="addFeed">
      <input
        v-model="store.newFeedPath"
        placeholder="path to a GTFS feed (zip or directory)"
      />
      <button class="primary" type="submit" :disabled="!store.newFeedPath.trim()">
        Load feed
      </button>
    </form>
  </div>
</template>
