# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- First standalone release of the editor, split out of the transitio core
  library (where it lived as ``transitio.gui`` up to transitio 0.1.x):
  the ``transitio-editor`` command serves a MapLibre-based local GUI over
  a ``transitio.FeedEditor`` — map editing of stops and route shapes with
  optional street snapping, sidebar forms for agencies, services, routes
  and frequency trips, and validated saving.
