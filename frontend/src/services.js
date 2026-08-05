// Pure helpers for the Cal (services) panel: calendar.txt rows as form
// state, day summaries, and the feed's calendar span.

export const DAY_KEYS = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

export const DAY_ABBR = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

// calendar.txt rows (from the attribute-table endpoint) as display rows.
export function serviceRows(tableRows) {
  return (tableRows || []).map((row) => ({
    serviceId: String(row.service_id ?? ""),
    days: DAY_KEYS.map((key) => String(row[key] ?? "0") === "1"),
    from: String(row.start_date ?? ""),
    to: String(row.end_date ?? ""),
  }));
}

// "Mo–Fr", "Sa, Su", "Mo–We, Fr" — consecutive runs collapse to ranges.
export function daySummary(days) {
  const runs = [];
  let start = null;
  for (let i = 0; i <= 7; i += 1) {
    const on = i < 7 && days[i];
    if (on && start === null) start = i;
    if (!on && start !== null) {
      runs.push(
        i - start >= 3
          ? `${DAY_ABBR[start]}–${DAY_ABBR[i - 1]}`
          : DAY_ABBR.slice(start, i).join(", "),
      );
      start = null;
    }
  }
  return runs.join(", ") || "no days";
}

// The feed's calendar span (min start, max end) as YYYYMMDD, or null.
export function calendarSpan(rows) {
  const froms = rows.map((row) => row.from).filter((d) => /^\d{8}$/.test(d));
  const tos = rows.map((row) => row.to).filter((d) => /^\d{8}$/.test(d));
  if (!froms.length || !tos.length) return null;
  return {
    from: froms.reduce((a, b) => (a < b ? a : b)),
    to: tos.reduce((a, b) => (a > b ? a : b)),
  };
}

// GTFS YYYYMMDD ↔ <input type="date"> yyyy-mm-dd.
export function gtfsToInput(date) {
  return /^\d{8}$/.test(date || "")
    ? `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`
    : "";
}

export function inputToGtfs(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(value || "") ? value.replace(/-/g, "") : "";
}

// The weekday names the add-service endpoint takes.
export function dayNames(days) {
  return DAY_KEYS.filter((key, index) => days[index]);
}
