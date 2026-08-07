# transitio-editor

A local map GUI for editing and building [GTFS](https://gtfs.org/) feeds,
built on the [transitio](https://github.com/cafein-py/transitio) library.

```
pip install "transitio-editor[snap]"
transitio-editor feed.zip --osm-pbf helsinki.osm.pbf
```

The editor opens on `http://127.0.0.1:8300`, on a search for GTFS feeds
and OpenStreetMap extracts by place. Feeds are loaded into one workspace
sharing one map, where the current feed is the target of edits, validation
and save. Panels list its stops, routes, services, trips and agencies —
selecting a row highlights it on the map, and clicking the map selects the
row — while stops and route shapes are added, renamed, moved and drawn on
the map itself. With an OSM extract (as fetched by `transitio.fetch_pbf`)
drawn shapes snap to the street network, whose ways can also be
reclassified, reshaped and written back. Every edit is recorded in the
workspace's activity log and can be undone, and saving runs transitio's
validator, reporting the notice counts of the written feed.

With the transitio core library installed, `transitio edit feed.zip` is an
alias for the same editor.

The map assets (MapLibre GL) are vendored — the only network use at
runtime is base-map tiles from openstreetmap.org in the browser. The HTTP
API behind the interface publishes its schema at `/openapi.json`. The
server binds to loopback and is single-user; it has no authentication.

## Installation

```
pip install transitio-editor          # the editor
pip install "transitio-editor[snap]"  # + street snapping (networkx)
```

## Developing the frontend

The editor UI is a Vite + Vue single-file-component app under
`frontend/`. The built assets are committed under
`transitio_editor/static/`, so installing the package needs no Node —
only editing the UI does:

```
cd frontend
npm install
npm run build     # rebuilds transitio_editor/static/
```

## License

MIT. Map data © OpenStreetMap contributors.
