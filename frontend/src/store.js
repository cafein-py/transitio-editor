import { reactive } from "vue";

// pyrosm tag filters behind the snap-network presets; "streets" uses the
// server's default network (no filter).
export const SNAP_FILTERS = {
  streets: null,
  tram: { railway: ["tram"] },
  rail: { railway: ["rail", "light_rail"] },
};

export const store = reactive({
  source: null,
  tables: {},
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
  status: "",
});

export const forms = reactive({
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
