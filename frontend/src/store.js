import { reactive } from "vue";

// pyrosm tag filters behind the snap-network presets; "streets" uses the
// server's default network (no filter).
export const SNAP_FILTERS = {
  streets: null,
  tram: { railway: ["tram"] },
  rail: { railway: ["rail", "light_rail"] },
};

export const store = reactive({
  activeTab: "view",
  editMode: false, // the View/Edit tab's switch: map features editable
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
  currentFeedId: null,
  newFeedPath: "",
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
    target: null, // "downloadDir" | "feedPath" | "mergeDir"
    mode: "dir", // "dir" (choose a folder) | "feed" (choose a .zip)
    path: "",
    parent: null,
    dirs: [],
    feeds: [],
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
    country: "",
    subdivision: "",
    municipality: "",
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
