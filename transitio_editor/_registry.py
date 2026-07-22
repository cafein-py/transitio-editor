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

    def __init__(self, feed_id, editor, name, color, source=None):
        self.feed_id = feed_id
        self.editor = editor
        self.name = name
        self.color = color
        self.source = source
        self.active = True


class FeedRegistry:
    """An ordered collection of loaded feeds with a current one."""

    def __init__(self):
        self._feeds = {}
        self.current = None
        self._counter = 0

    def add(self, editor, name, source=None):
        self._counter += 1
        feed_id = f"feed-{self._counter}"
        color = _PALETTE[(self._counter - 1) % len(_PALETTE)]
        entry = FeedEntry(feed_id, editor, name, color, source)
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


def entry_dict(entry, registry):
    """The JSON view of one catalogue entry."""
    return {
        "feed_id": entry.feed_id,
        "name": entry.name,
        "active": entry.active,
        "color": entry.color,
        "current": registry.current == entry.feed_id,
        "source": entry.source,
        "tables": {
            name: len(table) for name, table in sorted(entry.editor.tables.items())
        },
    }
