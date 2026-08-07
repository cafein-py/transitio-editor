// The latest layer data, held outside the reactive store: large feeds
// and street networks would make deep-reactive features expensive, so
// panels read these getters and re-run off store.dataVersion /
// store.networkVersion, which map.js bumps on refresh.
let stopsFeatures = [];

export function setStopsData(features) {
  stopsFeatures = features || [];
}

export function stopsData() {
  return stopsFeatures;
}

let networkWayFeatures = [];
let networkNodesById = new Map();

export function setNetworkEntities(nodes, ways) {
  networkWayFeatures = (ways && ways.features) || [];
  networkNodesById = new Map(
    ((nodes && nodes.features) || []).map((f) => [f.properties.id, f]),
  );
}

export function waysData() {
  return networkWayFeatures;
}

export function nodeById(id) {
  return networkNodesById.get(id);
}
