# transitio-editor

A local map GUI for editing and building [GTFS](https://gtfs.org/) feeds,
built on the [transitio](https://github.com/cafein-py/transitio) library.

```
pip install "transitio-editor[snap]"
transitio-editor feed.zip --osm-pbf helsinki.osm.pbf
```

The editor opens on `http://127.0.0.1:8300`: stops and route shapes render
on a map where they can be added, renamed, moved and drawn — with an OSM
extract (as fetched by `transitio.fetch_pbf`), drawn route shapes snap to
the street network. Routes, services and frequency-based trips are created
from sidebar forms, and saving runs transitio's validator, reporting the
notice counts of the written feed.

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

## License

MIT. Map data © OpenStreetMap contributors.
