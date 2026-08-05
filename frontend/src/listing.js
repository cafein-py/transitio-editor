// Pure helpers behind the Stops/Routes list panels: text filtering,
// paging and the row-window label.

// Case-insensitive substring match over the given field values.
export function filterItems(items, query, fields) {
  const needle = (query || "").trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) =>
    fields(item).some((value) =>
      String(value ?? "")
        .toLowerCase()
        .includes(needle),
    ),
  );
}

// The page kept within range after filters shrink the list.
export function clampPage(page, total, size) {
  const last = Math.max(0, Math.ceil(total / size) - 1);
  return Math.min(Math.max(0, page), last);
}

export function pageSlice(items, page, size) {
  const start = clampPage(page, items.length, size) * size;
  return items.slice(start, start + size);
}

// "1–12 of 38 matches" (or "of 38 routes"); empty lists say so plainly.
export function pageLabel(page, total, size, noun) {
  if (!total) return `no ${noun}`;
  const start = clampPage(page, total, size) * size;
  const end = Math.min(total, start + size);
  return `${start + 1}–${end} of ${total} ${noun}`;
}

// The page a row must be on for its selection to be visible.
export function pageOf(index, size) {
  return index < 0 ? 0 : Math.floor(index / size);
}
