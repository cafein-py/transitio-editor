import { reactive } from "vue";

// pyrosm tag filters behind the snap-network presets; "streets" uses the
// server's default network (no filter).
export const SNAP_FILTERS = {
  streets: null,
  tram: { railway: ["tram"] },
  rail: { railway: ["rail", "light_rail"] },
};

export const store = reactive({
  activeTab: "edit",
  source: null,
  tables: {},
  catalogue: [], // [{ feed_id, name, active, color, current, source, tables }]
  currentFeedId: null,
  newFeedPath: "",
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
  network: {
    available: false, // an OSM extract was loaded (--osm-pbf)
    loaded: false, // node/way GeoJSON fetched into the map
    loading: false,
    visible: true, // layer visibility toggle
    nodeCount: 0,
    wayCount: 0,
    selected: null, // inspected feature properties, or null
    error: "",
  },
  search: {
    country: "",
    subdivision: "",
    municipality: "",
    officialOnly: false,
    useMapBounds: false,
    limit: 50,
    results: [],
    searching: false,
    searched: false,
    csvFallback: false,
    sortKey: null,
    sortDir: "asc",
    downloadingId: null,
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
