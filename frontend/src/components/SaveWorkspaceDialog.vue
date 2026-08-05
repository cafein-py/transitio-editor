<script setup>
import { onMounted, ref } from "vue";

import { defaultWorkspaceDir, workspaceFileName } from "../actions/workspace.js";
import { store } from "../store.js";

const emit = defineEmits(["close", "save"]);

const name = ref(store.session.wsName);
const dir = ref(store.session.dir);
const nameInput = ref(null);

onMounted(async () => {
  nameInput.value?.focus();
  if (!dir.value) {
    try {
      dir.value = await defaultWorkspaceDir();
    } catch (error) {
      /* leave the folder to type */
    }
  }
});

function submit() {
  if (!workspaceFileName(name.value) || !dir.value.trim()) return;
  emit("save", name.value.trim(), dir.value.trim());
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" @keydown.esc="emit('close')">
      <h2>Save workspace</h2>
      <label class="field">
        <span class="mono-label">Workspace name</span>
        <input
          ref="nameInput"
          v-model="name"
          class="accent"
          placeholder="Name this workspace…"
          @keydown.enter="submit"
        />
      </label>
      <label class="field">
        <span class="mono-label">Folder</span>
        <input v-model="dir" placeholder="Folder to save into…" @keydown.enter="submit" />
      </label>
      <p class="note">
        Saved as a session .json next to a data folder for feeds that only
        exist in this workspace.
      </p>
      <div class="dialog-actions">
        <button class="btn" @click="emit('close')">Cancel</button>
        <button
          class="btn dark"
          :disabled="!workspaceFileName(name) || !dir.trim() || store.session.saving"
          @click="submit"
        >
          Save
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.note {
  margin: 0;
  font-size: 11px;
  color: var(--ink-4);
}
</style>
