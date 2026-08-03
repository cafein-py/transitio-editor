"""The editor's multi-feed registry.

Holds the feeds loaded into one editor session, which are active (shown
on the map together), and which is current (the target of edits).
"""

from __future__ import annotations

import os

# Distinct colors assigned round-robin so overlaid feeds stay
# distinguishable on the map.
_PALETTE = [
    "#35507a",
    "#c0392b",
    "#2c7a3d",
    "#8a6d00",
    "#6d3a7a",
    "#2c6f7a",
    "#a3562c",
    "#7a2c53",
]


class FeedEntry:
    """One loaded feed and its display state."""

    def __init__(self, feed_id, editor, name, color, source=None, origin=None):
        self.feed_id = feed_id
        self.editor = editor
        self.name = name
        self.color = color
        self.source = source
        # The Mobility Database feed id this entry was downloaded from (None
        # for locally loaded feeds); lets the search list mark downloaded ones.
        self.origin = origin
        self.active = True


class FeedRegistry:
    """An ordered collection of loaded feeds with a current one."""

    def __init__(self):
        self._feeds = {}
        self.current = None
        self._counter = 0

    def add(self, editor, name, source=None, origin=None):
        self._counter += 1
        feed_id = f"feed-{self._counter}"
        color = _PALETTE[(self._counter - 1) % len(_PALETTE)]
        entry = FeedEntry(feed_id, editor, name, color, source, origin)
        self._feeds[feed_id] = entry
        if self.current is None:
            self.current = feed_id
        return entry

    def get(self, feed_id):
        return self._feeds.get(feed_id)

    def current_entry(self):
        return self._feeds.get(self.current) if self.current else None

    def active_entries(self):
        return [entry for entry in self._feeds.values() if entry.active]

    def entries(self):
        return list(self._feeds.values())

    def remove(self, feed_id):
        removed = self._feeds.pop(feed_id, None)
        if removed is not None and self.current == feed_id:
            self.current = next(iter(self._feeds), None)
        return removed


def default_name(editor):
    """A display name for a feed, from its source filename when known."""
    source = getattr(editor, "source", None)
    if source is not None:
        return os.path.basename(os.fspath(source))
    return "feed"


def base_route_type(value):
    """Normalise a GTFS route_type (incl. extended codes) to a base mode.

    Extended types (Google extension, 100-1799) map onto their base GTFS
    family so the frontend only sees codes 0-12; unknown values yield None.
    """
    try:
        code = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0 <= code <= 12:
        return code
    if 100 <= code < 200:  # railway service
        return 2
    if 200 <= code < 300:  # coach service
        return 3
    if 300 <= code < 400:  # suburban railway service
        return 2
    if code == 405:  # monorail
        return 12
    if 400 <= code < 500:  # urban railway / metro service
        return 1
    if 500 <= code < 700:  # metro / underground service
        return 1
    if 700 <= code < 800:  # bus service
        return 3
    if code == 800:  # trolleybus service
        return 11
    if 900 <= code < 1000:  # tram service
        return 0
    if 1000 <= code < 1100:  # water transport service
        return 4
    if 1200 <= code < 1300:  # ferry service
        return 4
    if 1300 <= code < 1400:  # aerial lift service
        return 6
    if 1400 <= code < 1500:  # funicular service
        return 7
    return None


def _feed_modes(editor):
    # The distinct base transport modes among the feed's routes, sorted.
    routes = getattr(editor, "tables", {}).get("routes.txt")
    if routes is None or "route_type" not in getattr(routes, "columns", ()):
        return []
    modes = {base_route_type(value) for value in routes["route_type"]}
    return sorted(mode for mode in modes if mode is not None)


def entry_dict(entry, registry):
    """The JSON view of one catalogue entry."""
    return {
        "feed_id": entry.feed_id,
        "name": entry.name,
        "active": entry.active,
        "color": entry.color,
        "current": registry.current == entry.feed_id,
        "source": entry.source,
        "origin": entry.origin,
        "modes": _feed_modes(entry.editor),
        "tables": {
            name: len(table) for name, table in sorted(entry.editor.tables.items())
        },
    }
