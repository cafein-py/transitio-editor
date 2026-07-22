// Pure helpers for presenting the feed catalogue. The api-calling
// actions live in actions.js; these are the display-only functions.

export function feedTableSummary(tables) {
  const stops = (tables && tables.stops) || 0;
  const routes = (tables && tables.routes) || 0;
  const stopWord = stops === 1 ? "stop" : "stops";
  const routeWord = routes === 1 ? "route" : "routes";
  return `${stops} ${stopWord}, ${routes} ${routeWord}`;
}

export function currentFeed(catalogue, currentFeedId) {
  return catalogue.find((feed) => feed.feed_id === currentFeedId) || null;
}
