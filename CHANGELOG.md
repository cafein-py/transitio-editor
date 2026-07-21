# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
