import { reactive } from "vue";

import { DEFAULT_BASEMAP } from "./basemaps.js";
import { DEFAULT_HIDDEN_CLASSES } from "./streets.js";

// pyrosm tag filters behind the snap-network presets; "streets" uses the
// server's default network (no filter).
export const SNAP_FILTERS = {
  streets: null,
  tram: { railway: ["tram"] },
  rail: { railway: ["rail", "light_rail"] },
};

export const store = reactive({
  // Active left-panel key: data | stops | routes | cal | trips | agencies |
  // streets | validate (+ search until the ⌘K palette replaces it).
  activePanel: "data",
  layout: "sidebar", // header layout switcher: "sidebar" | "inspector" | "table"
  dirty: false, // edits since the workspace was last saved (header dot)
  dataVersion: 0, // bumped on layer refresh; panel lists recompute off it
  mapMoved: 0, // bumped on map moveend, for the "In map view" scope
  selectedStopId: null, // { stopId, feedId } — two-way with the Stops list
  selectedRouteId: null, // route of the current feed picked in the Routes list
  basemap: DEFAULT_BASEMAP, // background tile style, switchable on the map
  editMode: false, // map features of the current feed editable
  tableView: {
    open: false, // attribute table shown below the map
    file: "", // GTFS file being browsed
    q: "", // search text (server-side substring filter)
    offset: 0,
    limit: 100,
    total: 0,
    columns: [],
    rows: [],
    loading: false,
  },
  source: null,
  tables: {},
  catalogue: [], // [{ feed_id, name, active, color, current, source, tables }]
  groups: [], // user-named feed groups, in creation order
  draggingFeedId: null, // feed being dragged between groups
  currentFeedId: null,
  newFeedPath: "",
  // The crop tool on the View/Edit tab: a drawn area plus its options.
  cropDrawing: null, // "box" | "polygon" while drawing, else null
  cropShape: null, // the finished GeoJSON Polygon, or null
  crop: {
    group: "Cropped feeds", // destination group for the copies
    fullTripsOnly: false, // keep only trips entirely inside the area
    running: false,
  },
  // The panel the user last worked in, excluding the Data panel — what a
  // saved workspace reopens.
  workingPanel: null,
  session: {
    wsName: "", // workspace name, set by the save dialog
    named: false, // once named, Save workspace saves without asking
    savedAt: null, // epoch ms of the last successful save
    dir: "", // folder the workspace .json is saved into
    path: "", // the session .json to save to / load from
    saving: false,
    loading: false,
    confirm: null, // { reason: "feeds"|"osm-edits", feeds } awaiting the user
    historyOpen: false, // the Session drawer
    log: [], // activity log entries (see session.js)
    redoStack: [], // entries undone and re-appliable
  },
  merge: {
    selected: [], // feed ids ticked for merging
    name: "", // optional name for the merged feed
    directory: "", // optional folder to write the merged feed into
    merging: false,
  },
  // The server-side file browser, shared by every path box: `target` names
  // the field the choice lands in, `mode` whether a feed file can be picked.
  browse: {
    open: false,
    target: null, // "downloadDir" | "feedPath" | "mergeDir" | "sessionPath"
    mode: "dir", // "dir" (folder) | "feed" (.zip) | "session" (.json)
    path: "",
    parent: null,
    dirs: [],
    feeds: [],
    sessions: [],
    error: "",
  },
  snapAvailable: false,
  mode: "select",
  snapOn: true,
  snapNetwork: "streets",
  inspector: null, // { stopId, name }
  movingStop: null,
  tripStops: [], // [{ stopId, offset }]
  tripPicking: false,
  saving: false,
  saveResult: null, // { clean, message }
  undoLabel: null, // what the next undo would revert (server-peeked)
  redoLabel: null,
  routes: [],
  services: [], // current feed's calendar rows (Cal panel)
  agencies: [], // current feed's agency rows (Agencies panel)
  timetableRoute: "",
  routeTrips: [],
  trip: null, // { trip_id, times: [...] }
  shiftSeconds: 600,
  report: null, // last validation report of the current feed
  reports: {}, // feed_id → report, the workspace-wide roll-up
  validating: false, // a workspace validation sweep is running
  reportStale: false, // edits happened after the last validation
  highlightActive: false,
  feedVisible: true, // GTFS layer group visibility toggle
  stopsVisible: true, // stop markers shown (within the feed group)
  shapeColorBy: "mode", // shapes colored by transport "mode" | "feed"
  // route_type codes hidden from the shapes layer; unknown-mode shapes
  // (sentinel -1) start hidden so unclassifiable lines don't clutter the map.
  hiddenModes: [-1],
  presentModes: [], // mode codes present in the loaded feeds' shapes
  aoi: null, // a drawn [minx, miny, maxx, maxy] area, shared by OSM + GTFS
  aoiDrawing: false, // a rectangle drag is in progress
  network: {
    available: false, // an OSM extract is loaded (--osm-pbf or acquired)
    source: null, // path of the current OSM extract, for the catalogue row
    displayName: null, // readable area name (resolver name or file stem)
    bbox: null, // the crop area of a map-view extract, shown as metadata
    loaded: false, // node/way GeoJSON fetched into the map
    loading: false,
    visible: true, // layer visibility toggle
    editing: false, // the Streets panel's own editing toggle
    vertexEdit: false, // shape-vertex handles shown for the selected way
    nodeCount: 0,
    wayCount: 0,
    selected: null, // inspected way properties, or null
    savePath: "", // where Save writes the edited .osm.pbf
    error: "",
    acquire: {
      place: "", // place-name input for OSM extract acquisition
      resolving: false,
      resolved: null, // { bbox, url, name } awaiting confirmation
      downloading: false,
      error: "",
    },
  },
  // Highway classes hidden from the map and the way list (legend filter).
  hiddenHighwayClasses: [...DEFAULT_HIDDEN_CLASSES],
  networkVersion: 0, // bumped when network data changes; lists recompute
  search: {
    q: "", // one box: a place name, geocoded and flown to
    officialOnly: false,
    aoiMode: "none", // search-area source: "none" | "map" | "drawn"
    cropToAoi: false, // crop a downloaded feed to the selected area
    downloadDir: "", // optional folder for downloads (default: the cache)
    limit: 50,
    results: [],
    searching: false,
    searched: false,
    csvFallback: false,
    sortKey: null,
    sortDir: "asc",
    downloadingId: null,
    selected: [], // ids picked for a bulk download
    bulk: { running: false, done: 0, total: 0 },
  },
  status: "",
});

// Panel forms hold their own local state since the redesign; this stays
// as the (now empty) reset hook until the last legacy form is gone.
const defaultForms = () => ({});

export const forms = reactive(defaultForms());

// Form drafts reference feed-scoped ids; reset them to defaults when the
// edit target changes so stale ids can't be submitted to another feed.
export function resetForms() {
  const defaults = defaultForms();
  for (const key of Object.keys(defaults)) {
    Object.assign(forms[key], defaults[key]);
  }
}
