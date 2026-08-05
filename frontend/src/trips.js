// Pure helpers for the Trips panel: time parsing, trip-id suggestions,
// frequency estimates and stop-offset derivation.

// "H:MM" or "H:MM:SS" → seconds since midnight (over-midnight allowed,
// as GTFS does), or null.
export function toSeconds(text) {
  const match = String(text || "").match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return null;
  const [, h, m, s] = match;
  if (Number(m) > 59 || Number(s || 0) > 59) return null;
  return Number(h) * 3600 + Number(m) * 60 + Number(s || 0);
}

export function validStart(text) {
  return toSeconds(text) !== null;
}

// "SHORT_HHMM_dir", the overridable suggestion.
export function suggestTripId(shortName, start, dir) {
  const seconds = toSeconds(start);
  if (seconds === null) return "";
  const hhmm = `${String(Math.floor(seconds / 3600)).padStart(2, "0")}${String(
    Math.floor((seconds % 3600) / 60),
  ).padStart(2, "0")}`;
  const short = String(shortName || "trip").replace(/\s+/g, "").toUpperCase();
  return `${short}_${hhmm}_${dir}`;
}

// Runs a frequency window generates (the template run + one per headway).
export function estimateTrips(start, end, headwaySeconds) {
  const from = toSeconds(start);
  const to = toSeconds(end);
  if (from === null || to === null || to <= from || !headwaySeconds) return 0;
  return Math.floor((to - from) / headwaySeconds) + 1;
}

// Relative stop offsets from an existing trip's stop_times rows —
// the template for new trips and frequency runs on the same route.
export function offsetsFromTimes(times) {
  const rows = (times || [])
    .map((row) => ({
      stopId: row.stop_id,
      at: toSeconds(row.departure_time) ?? toSeconds(row.arrival_time),
    }))
    .filter((row) => row.stopId && row.at !== null);
  if (!rows.length) return [];
  const first = rows[0].at;
  return rows.map((row) => [row.stopId, row.at - first]);
}

// Trip search: by id or by start time ("A_0530" or "05:3").
export function tripMatches(trip, query) {
  const needle = (query || "").trim().toLowerCase();
  if (!needle) return true;
  return (
    String(trip.trip_id || "")
      .toLowerCase()
      .includes(needle) ||
    String(trip.first_departure || "").startsWith(needle)
  );
}
