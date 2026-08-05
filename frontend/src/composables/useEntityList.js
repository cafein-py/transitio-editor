// The shared mechanics of the Stops/Routes list panels: text filter,
// flag filter, paging, and revealing a selected row (jump to its page,
// then scrollTop math on the aside — never scrollIntoView).
import { computed, nextTick, ref, watch } from "vue";

import {
  clampPage,
  filterItems,
  pageLabel,
  pageOf,
  pageSlice,
} from "../listing.js";

export function useEntityList({ items, fields, noun, pageSize = 12 }) {
  const q = ref("");
  const flag = ref("all");
  const page = ref(0);
  const listEl = ref(null);

  // Flag predicates are registered by the panel (keyed by chip).
  const flagFns = new Map();
  function defineFlag(key, predicate) {
    flagFns.set(key, predicate);
  }

  const flagged = computed(() => {
    const predicate = flagFns.get(flag.value);
    return predicate ? items.value.filter(predicate) : items.value;
  });
  const filtered = computed(() => filterItems(flagged.value, q.value, fields));
  const total = computed(() => filtered.value.length);
  const rows = computed(() => pageSlice(filtered.value, page.value, pageSize));
  const label = computed(() =>
    pageLabel(page.value, total.value, pageSize, noun),
  );

  // The count a chip shows: its predicate over the text-filtered list.
  function flagCount(key) {
    const predicate = flagFns.get(key);
    const base = filterItems(items.value, q.value, fields);
    return predicate ? base.filter(predicate).length : base.length;
  }

  watch([q, flag], () => {
    page.value = 0;
  });

  const canPrev = computed(
    () => clampPage(page.value, total.value, pageSize) > 0,
  );
  const canNext = computed(
    () => (clampPage(page.value, total.value, pageSize) + 1) * pageSize < total.value,
  );
  const prev = () => {
    page.value = clampPage(page.value, total.value, pageSize) - 1;
  };
  const next = () => {
    page.value = clampPage(page.value, total.value, pageSize) + 1;
  };

  // Bring a (map-)selected row into view within the scrolling aside.
  async function reveal(matches) {
    const index = filtered.value.findIndex(matches);
    if (index === -1) return;
    page.value = pageOf(index, pageSize);
    await nextTick();
    const container = listEl.value && listEl.value.closest(".shell-aside");
    const row =
      listEl.value && listEl.value.querySelector('[data-selected="true"]');
    if (!container || !row) return;
    const delta =
      row.getBoundingClientRect().top -
      container.getBoundingClientRect().top;
    // keep the row comfortably below the panel's control stack
    container.scrollTop += delta - container.clientHeight / 3;
  }

  return {
    q,
    flag,
    page,
    listEl,
    rows,
    total,
    label,
    defineFlag,
    flagCount,
    canPrev,
    canNext,
    prev,
    next,
    reveal,
  };
}
