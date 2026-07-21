# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

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
