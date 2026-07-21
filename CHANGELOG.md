# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Validation-report tab: the sidebar now has Edit and Report tabs; the
  Report tab investigates the full transitio validation report —
  severity totals, the computed service window, row counts, and notices
  grouped by code and severity, each expandable to sample contexts that
  highlight the offending stops and shapes on the map. A Vitest harness
  (``npm --prefix frontend test``) covers the report-grouping helpers.

## Unreleased

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
