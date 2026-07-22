// Pure helpers for presenting Mobility Database search results. The
// api-calling action lives in actions.js.

export function feedLocation(feed) {
  const labels = (feed.locations || [])
    .map((location) =>
      [location.municipality, location.subdivision, location.country]
        .filter(Boolean)
        .join(", "),
    )
    .filter(Boolean);
  return labels.length ? labels.join("; ") : "—";
}

// Only http(s) links are safe to bind to an href; a catalog-supplied
// `javascript:` (or other) scheme would run on click, so reject it.
export function safeHttpUrl(url) {
  return /^https?:\/\//i.test(url || "") ? url : null;
}

const SORT_VALUES = {
  provider: (feed) => (feed.provider || feed.id || "").toLowerCase(),
  location: (feed) => feedLocation(feed).toLowerCase(),
  status: (feed) => (feed.status || "").toLowerCase(),
};

export function sortFeeds(feeds, key, direction) {
  const value = SORT_VALUES[key];
  if (!value) return feeds.slice();
  const sign = direction === "desc" ? -1 : 1;
  return feeds.slice().sort((a, b) => sign * value(a).localeCompare(value(b)));
}
