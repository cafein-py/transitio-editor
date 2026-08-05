import { reactive } from "vue";

import { DEFAULT_BASEMAP } from "./basemaps.js";

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
  timetableRoute: "",
  routeTrips: [],
  trip: null, // { trip_id, times: [...] }
  shiftSeconds: 600,
  report: null, // last validation report
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
    loaded: false, // node/way GeoJSON fetched into the map
    loading: false,
    visible: true, // layer visibility toggle
    nodeCount: 0,
    wayCount: 0,
    selected: null, // inspected feature properties, or null
    mode: "select", // "select" | "add-node" | "draw-way"
    movingNode: null, // id of a node awaiting its new location
    draw: [], // vertices of a way being drawn: [{ vertex, coord }]
    error: "",
    acquire: {
      place: "", // place-name input for OSM extract acquisition
      resolving: false,
      resolved: null, // { bbox, url, name } awaiting confirmation
      downloading: false,
      error: "",
    },
  },
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

const defaultForms = () => ({
  route: { route_id: "", route_short_name: "", route_type: 3, agency_id: "" },
  trip: {
    route_id: "",
    service_id: "",
    trip_id: "",
    shape_id: "",
    start: "06:00:00",
    end: "22:00:00",
    headway: 600,
  },
  agency: {
    agency_id: "",
    agency_name: "",
    agency_url: "",
    agency_timezone: "",
  },
  service: {
    service_id: "",
    days: "weekdays",
    start_date: "20260101",
    end_date: "20261231",
  },
});

export const forms = reactive(defaultForms());

// Form drafts reference feed-scoped ids; reset them to defaults when the
// edit target changes so stale ids can't be submitted to another feed.
export function resetForms() {
  const defaults = defaultForms();
  for (const key of Object.keys(defaults)) {
    Object.assign(forms[key], defaults[key]);
  }
}
