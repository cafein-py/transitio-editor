"""Trip-level timetable operations over a FeedEditor's tables.

These mutate the editor's pandas tables directly (the documented escape
hatch of ``transitio.FeedBuilder``); save-time validation remains the
correctness net.
"""

from __future__ import annotations


def parse_time(value):
    """Seconds since midnight from ``H:MM:SS`` (hours may exceed 24)."""
    parts = str(value).strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"invalid GTFS time: {value!r}")
    try:
        hours, minutes, seconds = (int(part) for part in parts)
    except ValueError:
        raise ValueError(f"invalid GTFS time: {value!r}") from None
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError(f"invalid GTFS time: {value!r}")
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds):
    """``HH:MM:SS`` from seconds since midnight (over-midnight kept)."""
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def list_routes(editor):
    """Route identity rows for the timetable panel."""
    routes = editor.tables.get("routes.txt")
    if routes is None:
        return []
    columns = [
        column
        for column in ("route_id", "route_short_name", "route_long_name", "route_type")
        if column in routes.columns
    ]
    return routes[columns].to_dict(orient="records")


def list_trips(editor, route_id):
    """The trips of one route, with first departures and frequency info."""
    trips = editor.tables.get("trips.txt")
    if trips is None:
        return []
    selected = trips[trips["route_id"] == str(route_id)]
    times = editor.tables.get("stop_times.txt")
    frequencies = editor.tables.get("frequencies.txt")
    records = []
    for _, row in selected.iterrows():
        trip_id = row["trip_id"]
        record = {
            "trip_id": trip_id,
            "service_id": row.get("service_id", ""),
            "direction_id": row.get("direction_id", ""),
            "shape_id": row.get("shape_id", ""),
            "stop_count": 0,
            "first_departure": None,
            "frequency_windows": [],
        }
        if times is not None:
            rows = times[times["trip_id"] == trip_id]
            record["stop_count"] = int(len(rows))
            departures = [
                value for value in rows.get("departure_time", []) if str(value).strip()
            ]
            if departures:
                record["first_departure"] = min(departures)
        if frequencies is not None and "trip_id" in frequencies.columns:
            windows = frequencies[frequencies["trip_id"] == trip_id]
            record["frequency_windows"] = windows[
                [
                    column
                    for column in ("start_time", "end_time", "headway_secs")
                    if column in windows.columns
                ]
            ].to_dict(orient="records")
        records.append(record)
    records.sort(
        key=lambda record: (record["first_departure"] or "", record["trip_id"])
    )
    return records


def trip_times(editor, trip_id):
    """One trip's stop_times, with stop names joined in."""
    times = editor.tables.get("stop_times.txt")
    if times is None:
        return None
    rows = times[times["trip_id"] == str(trip_id)]
    if rows.empty:
        return None
    stops = editor.tables.get("stops.txt")
    names = {}
    if stops is not None and "stop_name" in stops.columns:
        names = dict(zip(stops["stop_id"], stops["stop_name"]))
    records = []
    for _, row in rows.iterrows():
        records.append(
            {
                "stop_sequence": row.get("stop_sequence", ""),
                "stop_id": row.get("stop_id", ""),
                "stop_name": names.get(row.get("stop_id", ""), ""),
                "arrival_time": row.get("arrival_time", ""),
                "departure_time": row.get("departure_time", ""),
            }
        )
    records.sort(key=lambda record: _sequence_key(record["stop_sequence"]))
    return records


def _sequence_key(value):
    try:
        return (0, int(str(value)))
    except ValueError:
        return (1, 0)


def set_trip_times(editor, trip_id, updates):
    """Replace a trip's arrival/departure times.

    ``updates`` maps stop_sequence (string) to
    ``{"arrival_time": ..., "departure_time": ...}``; every entry must
    name an existing sequence of the trip, and times are normalized
    through the strict parser.
    """
    times = editor.tables.get("stop_times.txt")
    if times is None:
        raise LookupError("feed has no stop_times.txt")
    mask = times["trip_id"] == str(trip_id)
    if not mask.any():
        raise LookupError(f"no trip {trip_id!r}")
    existing = set(times.loc[mask, "stop_sequence"].astype(str))
    unknown = set(updates) - existing
    if unknown:
        raise ValueError(f"unknown stop sequences: {sorted(unknown)}")
    # Two phases: normalize every value first, then apply — a bad entry
    # must never leave a partial edit behind. An empty string clears the
    # time (legal for non-timepoint stops).
    normalized = []
    for sequence, entry in updates.items():
        for column in ("arrival_time", "departure_time"):
            if column in entry and entry[column] is not None:
                raw = str(entry[column]).strip()
                value = "" if raw == "" else format_time(parse_time(raw))
                normalized.append((str(sequence), column, value))
    for sequence, column, value in normalized:
        row_mask = mask & (times["stop_sequence"].astype(str) == sequence)
        times.loc[row_mask, column] = value


def drop_trip(editor, trip_id):
    """Remove one trip with its stop_times and frequencies."""
    trips = editor.tables.get("trips.txt")
    if trips is None or not (trips["trip_id"] == str(trip_id)).any():
        raise LookupError(f"no trip {trip_id!r}")
    editor.tables["trips.txt"] = trips[trips["trip_id"] != str(trip_id)].reset_index(
        drop=True
    )
    for filename, columns in (
        ("stop_times.txt", ("trip_id",)),
        ("frequencies.txt", ("trip_id",)),
        ("attributions.txt", ("trip_id",)),
        ("transfers.txt", ("from_trip_id", "to_trip_id")),
    ):
        table = editor.tables.get(filename)
        if table is None:
            continue
        keep = None
        for column in columns:
            if column not in table.columns:
                continue
            match = table[column] == str(trip_id)
            keep = ~match if keep is None else keep & ~match
        if keep is not None:
            editor.tables[filename] = table[keep].reset_index(drop=True)
