// The latest stops layer data, held outside the reactive store: a large
// feed would make deep-reactive features expensive, so panels read these
// getters and re-run off store.dataVersion, which map.js bumps on every
// layer refresh.
let stopsFeatures = [];

export function setStopsData(features) {
  stopsFeatures = features || [];
}

export function stopsData() {
  return stopsFeatures;
}
