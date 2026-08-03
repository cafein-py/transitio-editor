# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- A "show stops" toggle: the Edit tab's legend panel (now "Map display")
  can hide the stop markers independently of the route shapes.
- Catalogue entries show which transport modes a feed contains, as colored
  chips matching the map legend (from a new `modes` field in the catalogue
  API: the distinct normalised route types among the feed's routes).
- Search results that are already in the catalogue show a green check
  instead of the Download button (removing the feed from the catalogue
  brings the button back), so it is easy to see which of an area's many
  feeds still need downloading. Catalogue entries record the Mobility
  Database id they were downloaded from (`origin` in the catalogue API).
- A current-feed bar on the Edit and Report tabs: with several feeds in the
  catalogue, the feed that edits, validation and save target is now always
  visible (color swatch + name) and switchable in place; the validation
  report header also names the feed it was produced for.
- The Catalogue tab lists the loaded OSM extract alongside the GTFS feeds,
  so all loaded data is visible in one place: an OSM row with the extract
  name, node/way counts and the show-on-map toggle. GTFS and OSM entries
  carry color-coded badges (matching their map layers) to tell the kinds
  apart; `GET /api/network` now reports the extract source and, once
  loaded, its node/way counts.
- Route shapes are colored by transport mode (tram, metro, rail, bus,
  ferry, cable tram, aerial lift, funicular, trolleybus, monorail), with a
  collapsible legend on the Edit tab whose checkboxes hide or show each
  mode and a color-by mode/feed switch that restores the per-feed coloring
  for overlaid feeds. The palette is colorblind-validated (OKLab CVD
  separation checked across co-occurring pairs against the basemap tone),
  the common modes follow widely used semantic transit colors (blue bus,
  green tram, orange metro, purple rail, cyan ferry), and a white casing
  under the lines keeps them readable on the busy basemap. `/api/shapes`
  features now carry a `route_type` resolved through each shape's trips,
  with extended (Google-extension) route types normalised to their base
  families.

### Changed

- Downloading a feed no longer switches the view to the Catalogue tab, so
  several of an area's feeds can be downloaded in a row without the GUI
  bouncing away from the search results.
- Routes whose type could not be determined are a toggleable "other /
  unknown" legend row of their own — hidden by default so unclassifiable
  lines don't clutter the map — instead of staying always visible, and the
  shape-to-route join tolerates stray whitespace in feed id columns. The
  legend lists only modes that exist in the loaded feeds and gains
  select-all / deselect-all buttons.
- The default `--max-network-ways` guard is 200000 (was 50000), so a
  mid-size city's routable network — e.g. Oulu at ~86k ways — loads without
  tripping the limit when acquired from the GUI; the limit error now also
  suggests using a smaller area.

### Fixed

- The Catalogue tab's per-feed summary counted stops and routes under the
  wrong table keys and therefore always showed "0 stops, 0 routes"; it now
  reads the filename-keyed counts the API serves.
- The sidebar is wide enough (with slightly more compact tab buttons) for
  all five tabs to share one row, so the Report tab is no longer wrapped or
  cut off.

## 0.6.1 — 2026-08-03

### Changed

- The `transitio-editor` command can now start without a GTFS feed: the
  positional feed argument is optional, and when omitted the editor opens on
  an empty feed to build from scratch on the Edit tab — or load, search and
  download feeds (and acquire an OSM extract) entirely from the GUI.

## 0.6.0 — 2026-07-23

### Added

- Acquire an OSM extract from the editor: `POST /api/osm/resolve` resolves the
  smallest covering Geofabrik extract for an area (a place name or a bounding
  box) from pyrosm's bundled index without downloading, and `POST
  /api/osm/download` downloads and crops it via `transitio.osm.fetch_pbf` and
  loads it as the editable network. The Network panel gains an "Acquire OSM
  extract" control (place, current map view or a drawn area) with a confirm
  step; acquiring replaces the current network at runtime rather than requiring
  the `--osm-pbf` argument, refusing to discard unsaved edits without
  confirmation and keeping the previous network if the download fails.
- Crop a downloaded GTFS feed to an area: `POST /api/catalogue/download` takes
  an optional `aoi` bounding box and crops the dataset to it via
  `transitio.gtfs.crop_feed` (keeping trips that serve a stop inside the box,
  cascading to a referentially consistent feed) before it enters the
  catalogue, with a provenance sidecar recording the source, bbox and row
  counts.
- Draw an area on the map: a rectangle-draw tool stores one bounding box shared
  by both flows, so a single drawn area can drive downloading and cropping the
  PBF and the GTFS feed together. The Search tab's map-bounds checkbox becomes
  a none / current map view / drawn area selector plus a "crop downloaded feed
  to area" toggle.

## 0.5.0 — 2026-07-23

### Added

- View the OSM network (backend + Network tab): start the editor with
  ``--osm-pbf`` to load a local ``.osm.pbf``; ``GET
  /api/network/{nodes,ways,features}`` serve the routable network as
  GeoJSON. A Network tab draws the network alongside the GTFS layers with
  per-group visibility toggles and inspects a clicked node or way. The
  network loads lazily on first access, behind a ``--max-network-ways``
  size guard, with a broad ``--network-filter`` selecting the ways.
- Edit network nodes: add, move, delete and retag nodes (``POST/PATCH/
  DELETE /api/network/nodes``). New elements get a provisional negative id
  that is their stable identity for the session.
- Edit network ways: draw a new way (``POST /api/network/ways`` with
  per-vertex descriptors) with connectivity — each drawn point reuses a
  clicked existing node, splits a clicked way at a shared junction node,
  or creates a new node — and retag (``PATCH``) or delete (``DELETE``) a
  way. Vertices that meet at one point (a crossing, a shared node) splice
  a single node into every way involved. A Draw-way mode with a live
  preview and a tag key/value, plus Move/Delete/retag on a selected
  element.
- Save the edited network and snap to it: ``POST /api/network/save``
  writes the edited network to a chosen ``*.osm.pbf`` via
  ``OsmEditor.save`` (network-only, atomic) with a ``.provenance.json``
  sidecar (source, edit counts, save time); it refuses a non-``.pbf``
  path, a path resolving to the source extract, and 409s when no network
  is loaded. Snapping (``POST /api/shapes/snap``) routes through the
  edited network whenever one is loaded, so drawn shapes follow network
  edits. A Save-network control in the Network panel.

## 0.4.0 — 2026-07-22

### Added

- Multi-feed catalogue (backend): the editor now holds a registry of
  loaded feeds instead of a single feed. New endpoints — ``GET/POST
  /api/catalogue``, ``PATCH /api/catalogue/{feed_id}`` (activate/rename),
  ``PUT /api/catalogue/current`` and ``DELETE /api/catalogue/{feed_id}``
  — list feeds, load more from local paths, toggle which are active, pick
  the current edit target and remove feeds. ``/api/stops`` and
  ``/api/shapes`` aggregate across the active feeds, tagging every
  feature with its ``feed_id`` and a per-feed color so overlaid feeds
  (e.g. a city's separate bus and rail feeds) stay distinguishable;
  mutations, save and validation target the current feed. The CLI still
  opens one feed as the initial catalogue entry.
- Catalogue tab (frontend): a tab lists the loaded feeds with their
  per-feed color, a show toggle (which feeds draw together on the map), a
  current-feed selector (the edit target), a table summary and a remove
  button, plus a form to load another feed from a local path. Stop
  selection, validation highlighting and edits are scoped to the current
  feed, and switching feeds clears the previous feed's editing state.
- Validation-report tab: the sidebar now has Edit and Report tabs; the
  Report tab investigates the full transitio validation report —
  severity totals, the computed service window, row counts, and notices
  grouped by code and severity, each expandable to sample contexts that
  highlight the offending stops and shapes on the map. A Vitest harness
  (``npm --prefix frontend test``) covers the report-grouping helpers.
- Mobility Database feed search: a Search tab and ``GET /api/search``
  query the Mobility Database (refresh token from the environment, else
  the CSV catalogue export) by country, subdivision, municipality and
  current-map-view bounding box, listing results in a click-to-sort
  table with license links and location details.
- Download feeds into the catalogue: ``POST /api/catalogue/download`` and
  a Download button on each search result fetch the latest hosted dataset
  and load it as an active catalogue feed.

### Changed

- The frontend is now a Vite + single-file-component Vue application
  (`frontend/`), replacing the previous hand-written single-file
  `app.js` and inline template. The UI is split into an API client, a
  MapLibre bridge, a reactive store, shared actions and one component
  per sidebar panel. MapLibre and Vue are npm dependencies bundled by
  the build (no vendored blobs). Built assets are committed under
  `transitio_editor/static/` so the wheel needs no Node; edit the source
  under `frontend/src/` and rebuild with `npm --prefix frontend run
  build`. No user-facing behavior change.

## 0.3.0 — 2026-07-21

### Added

- Snap to tram or rail networks: the draw panel's snap control now picks
  the OSM network — streets, tram rails or rail — and the snapping
  endpoint accepts a pyrosm ``custom_filter`` (per request, or a server
  default via the new ``--snap-filter`` CLI option and
  ``create_app(snap_custom_filter=)``), so route shapes can be snapped
  to tram rails instead of only the driving network. Requires
  ``transitio >= 0.3``.

- Jupyter helpers (``transitio_editor.notebook``, extra
  ``transitio-editor[notebook]``): ``feed_map(feed)`` renders a feed's
  stops and shapes on an ipyleaflet map for inspection, and
  ``serve(feed)`` runs the full editor in a background thread and embeds
  it as an IFrame — both accept a ``FeedEditor``/``FeedBuilder`` or a
  feed-zip path.

## 0.2.0 — 2026-07-21

### Added

- Timetable editing: a sidebar panel lists a route's trips (first
  departures, directions, frequency windows) and opens any trip as an
  editable stop-times table — apply changed arrival/departure times
  (strictly parsed), shift the whole trip by seconds, or delete the
  trip with its stop_times and frequencies. Backed by new trip-level
  endpoints (``GET /api/routes``, ``GET /api/routes/{id}/trips``,
  ``GET``/``PUT /api/trips/{id}/times``, ``DELETE /api/trips/{id}``).

## 0.1.0 — 2026-07-21

### Added

- Validation-notices panel: a Validate button checks the current
  in-memory feed without saving (new ``POST /api/validate`` endpoint,
  validating a temporary snapshot), and both it and Save populate a
  grouped notice list in the sidebar — ordered by severity, expandable
  to individual notice contexts, and clicking a context highlights the
  offending stops and shapes on the map (flying to the first stop).

### Changed

- The frontend is now a Vue application (vendored ``vue.global.prod.js``,
  no build step, no CDN): the sidebar, forms, inspector and status
  surfaces render declaratively from a reactive store, with Vue's
  interpolation escaping all feed-derived values; MapLibre stays
  imperative behind a small bridge. Behavior is unchanged; trip-stop
  picking now activates precisely while the trip form is open.

### Added

- First standalone release of the editor, split out of the transitio core
  library (where it lived as ``transitio.gui`` up to transitio 0.1.x):
  the ``transitio-editor`` command serves a MapLibre-based local GUI over
  a ``transitio.FeedEditor`` — map editing of stops and route shapes with
  optional street snapping, sidebar forms for agencies, services, routes
  and frequency trips, and validated saving.
